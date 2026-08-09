#!/usr/bin/env node

import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const planPath = join(here, "review-plan.json");
const planBytes = readFileSync(planPath);
const plan = JSON.parse(planBytes);
const verdicts = new Set(plan.verdicts);
const evidenceClasses = new Set(plan.evidence_classes);
const stimuli = new Set(plan.stimuli);
const observers = new Set(plan.observers);

function die(message) {
  process.stderr.write(`installed-review: ${message}\n`);
  process.exit(1);
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function command(name, args, options = {}) {
  return execFileSync(name, args, { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"], ...options }).trim();
}

function argument(name, args) {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : undefined;
}

function plistValue(plist, key) {
  return command("plutil", ["-extract", key, "raw", "-o", "-", plist]);
}

function prepare(args) {
  const app = resolve(argument("--app", args) || "../../target/release/bundle/macos/Yawn.app");
  const out = resolve(argument("--out", args) || "../../docs/desktop-installed-app-reviews/pending");
  const plist = join(app, "Contents", "Info.plist");
  if (!existsSync(plist)) die(`app bundle is missing Info.plist: ${app}`);
  const executableName = plistValue(plist, "CFBundleExecutable");
  const executable = join(app, "Contents", "MacOS", executableName);
  if (!existsSync(executable)) die(`app executable is missing: ${executable}`);
  try {
    command("codesign", ["--verify", "--deep", "--strict", app]);
  } catch {
    die(`codesign verification failed: ${app}`);
  }
  const repo = command("git", ["rev-parse", "--show-toplevel"], { cwd: here });
  const status = command("git", ["status", "--porcelain=v1", "-z"], { cwd: repo });
  const executableSha = sha256(readFileSync(executable));
  const generatedAt = new Date().toISOString();
  const checks = plan.surfaces.flatMap((surface) => surface.gates.map((gateId) => ({
    gate_id: gateId,
    surface_id: surface.surface_id,
    state: "all-required",
    appearance: "all-required",
    geometry: "all-required",
    verdict: "unproven",
    evidence_ids: [],
    expected: `Complete ${gateId} for ${surface.surface_id} under the canonical installed-app protocol.`,
    observed: "No admissible evidence recorded.",
    defect_id: null,
  })));
  const run = {
    schema: "yawn-installed-review-run/1",
    run_id: basename(out),
    generated_at: generatedAt,
    app: {
      bundle_path: app,
      identifier: plistValue(plist, "CFBundleIdentifier"),
      version: plistValue(plist, "CFBundleShortVersionString"),
      executable_name: executableName,
      executable_sha256: executableSha,
      signature: "codesign --verify --deep --strict passed",
    },
    source: {
      git_head: command("git", ["rev-parse", "HEAD"], { cwd: repo }),
      working_tree_state_sha256: sha256(status),
      working_tree_clean: status.length === 0,
      review_plan_sha256: sha256(planBytes),
    },
    evidence: [],
    checks,
    operator_verdict: null,
    notes: [
      "Prepared rows are unproven by design. The preparer cannot create human approval.",
      "Owner-only screenshots stay outside Git; record only their opaque identifier and digest.",
    ],
  };
  mkdirSync(out, { recursive: true });
  const output = join(out, "run.json");
  if (existsSync(output)) die(`refusing to overwrite existing run: ${output}`);
  writeFileSync(output, `${JSON.stringify(run, null, 2)}\n`);
  process.stdout.write(`${output}\n`);
}

function validateEvidence(item, errors) {
  if (!item.id || typeof item.id !== "string") errors.push("evidence item has no stable id");
  if (!evidenceClasses.has(item.environment)) errors.push(`${item.id}: invalid environment`);
  if (!stimuli.has(item.stimulus)) errors.push(`${item.id}: invalid stimulus`);
  if (!observers.has(item.observer)) errors.push(`${item.id}: invalid observer`);
  if (!item.observed_at) errors.push(`${item.id}: missing observed_at`);
  if (!item.artifact?.privacy || !["committable", "owner-only"].includes(item.artifact.privacy)) {
    errors.push(`${item.id}: artifact privacy must be committable or owner-only`);
  }
  if (!/^[a-f0-9]{64}$/.test(item.artifact?.sha256 || "")) errors.push(`${item.id}: artifact sha256 is invalid`);
  if (item.artifact?.privacy === "owner-only" && item.artifact.path) {
    errors.push(`${item.id}: owner-only evidence must not place a private path in the receipt`);
  }
}

function passRequirements(check, evidence, errors) {
  if (check.verdict !== "pass") return;
  const installed = evidence.some((item) => item.environment === "installed-tauri");
  const live = evidence.some((item) => item.environment === "installed-tauri" && item.stimulus === "live-device");
  const human = evidence.some((item) => item.environment === "installed-tauri" && item.observer === "human-operator");
  if ((check.gate_id.startsWith("native.") || check.gate_id.startsWith("keyboard.")) && !installed) {
    errors.push(`${check.surface_id}/${check.gate_id}: pass requires installed-tauri evidence`);
  }
  if (check.gate_id.startsWith("live.") && !live) {
    errors.push(`${check.surface_id}/${check.gate_id}: pass requires installed-tauri live-device evidence`);
  }
  if ((check.gate_id === "human.visual" || check.gate_id === "human.cold-comprehension") && !human) {
    errors.push(`${check.surface_id}/${check.gate_id}: pass requires installed human-operator evidence`);
  }
  if (check.gate_id === "accessibility.voiceover" && !evidence.some((item) => item.assistive_mode === "voiceover" && item.observer === "human-operator")) {
    errors.push(`${check.surface_id}/${check.gate_id}: pass requires spoken human VoiceOver evidence`);
  }
}

function validate(args) {
  const runPath = resolve(args[0] || "");
  if (!existsSync(runPath)) die(`run manifest not found: ${runPath}`);
  const run = JSON.parse(readFileSync(runPath, "utf8"));
  const errors = [];
  if (run.schema !== "yawn-installed-review-run/1") errors.push("unsupported run schema");
  if (run.source?.review_plan_sha256 !== sha256(planBytes)) errors.push("review plan digest changed; prepare a new run");
  if (!/^[a-f0-9]{64}$/.test(run.app?.executable_sha256 || "")) errors.push("invalid app executable digest");
  const evidenceById = new Map();
  for (const item of run.evidence || []) {
    validateEvidence(item, errors);
    if (evidenceById.has(item.id)) errors.push(`duplicate evidence id: ${item.id}`);
    evidenceById.set(item.id, item);
  }
  const expectedRows = new Set(plan.surfaces.flatMap((surface) => surface.gates.map((gate) => `${surface.surface_id}\0${gate}`)));
  const actualRows = new Set();
  for (const check of run.checks || []) {
    const key = `${check.surface_id}\0${check.gate_id}`;
    if (!expectedRows.has(key)) errors.push(`unknown check row: ${check.surface_id}/${check.gate_id}`);
    if (actualRows.has(key)) errors.push(`duplicate check row: ${check.surface_id}/${check.gate_id}`);
    actualRows.add(key);
    if (!verdicts.has(check.verdict)) errors.push(`${check.surface_id}/${check.gate_id}: invalid verdict`);
    const evidence = (check.evidence_ids || []).map((id) => {
      if (!evidenceById.has(id)) errors.push(`${check.surface_id}/${check.gate_id}: missing evidence ${id}`);
      return evidenceById.get(id);
    }).filter(Boolean);
    for (const item of evidence) {
      if (item.app_executable_sha256 && item.app_executable_sha256 !== run.app.executable_sha256) {
        errors.push(`${item.id}: evidence is bound to another executable`);
      }
    }
    passRequirements(check, evidence, errors);
  }
  for (const key of expectedRows) if (!actualRows.has(key)) errors.push(`missing check row: ${key.replace("\0", "/")}`);
  if (run.operator_verdict?.decision === "accept") {
    if (run.operator_verdict.run_manifest_sha256 !== sha256(readFileSync(runPath))) {
      errors.push("operator accept is not bound to the current run manifest bytes");
    }
    if (run.operator_verdict.app_executable_sha256 !== run.app.executable_sha256) {
      errors.push("operator accept is bound to another executable");
    }
  }
  if (errors.length) die(errors.join("\n"));
  const counts = Object.fromEntries(plan.verdicts.map((verdict) => [verdict, 0]));
  for (const check of run.checks) counts[check.verdict] += 1;
  process.stdout.write(`${JSON.stringify({ valid: true, checks: run.checks.length, verdicts: counts })}\n`);
}

const [subcommand, ...args] = process.argv.slice(2);
if (subcommand === "prepare") prepare(args);
else if (subcommand === "validate") validate(args);
else die("usage: installed-review.mjs prepare --app <Yawn.app> --out <run-dir> | validate <run.json>");
