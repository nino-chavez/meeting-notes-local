import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const cli = join(here, "installed-review.mjs");
const planPath = join(here, "review-plan.json");
const planBytes = readFileSync(planPath);
const plan = JSON.parse(planBytes);
const uiRoot = dirname(here);
const digest = (value) => createHash("sha256").update(value).digest("hex");
const sixtyFour = "a".repeat(64);

function baseRun() {
  return {
    schema: "yawn-installed-review-run/1",
    run_id: "fixture",
    generated_at: "2026-08-09T00:00:00.000Z",
    app: { executable_sha256: sixtyFour },
    source: { review_plan_sha256: digest(planBytes) },
    evidence: [],
    checks: plan.surfaces.flatMap((surface) => surface.gates.map((gateId) => ({
      gate_id: gateId,
      surface_id: surface.surface_id,
      state: "all-required",
      appearance: "all-required",
      geometry: "all-required",
      verdict: "unproven",
      evidence_ids: [],
      expected: "fixture",
      observed: "fixture",
      defect_id: null,
    }))),
    operator_verdict: null,
  };
}

function validate(run) {
  const directory = mkdtempSync(join(tmpdir(), "yawn-installed-review-"));
  const file = join(directory, "run.json");
  writeFileSync(file, `${JSON.stringify(run, null, 2)}\n`);
  const result = spawnSync(process.execPath, [cli, "validate", file], { encoding: "utf8" });
  rmSync(directory, { recursive: true, force: true });
  return result;
}

function evidence(overrides = {}) {
  return {
    id: "fixture-evidence",
    environment: "browser",
    stimulus: "synthetic",
    observer: "automated",
    assistive_mode: "none",
    app_executable_sha256: sixtyFour,
    artifact: { privacy: "committable", sha256: sixtyFour, path: "fixture.png" },
    observed_at: "2026-08-09T00:00:00.000Z",
    notes: "fixture",
    ...overrides,
  };
}

function pass(run, surfaceId, gateId, item) {
  run.evidence = [item];
  const row = run.checks.find((candidate) => candidate.surface_id === surfaceId && candidate.gate_id === gateId);
  row.verdict = "pass";
  row.evidence_ids = [item.id];
}

test("review plan covers every production screen and native Settings pane", () => {
  const html = readFileSync(join(uiRoot, "index.html"), "utf8");
  const settings = readFileSync(join(uiRoot, "settings.html"), "utf8");
  const screenIds = [...html.matchAll(/<section\b[^>]*class="[^"]*\bscreen\b[^"]*"[^>]*id="([^"]+)"|<section\b[^>]*id="([^"]+)"[^>]*class="[^"]*\bscreen\b/g)]
    .map((match) => match[1] || match[2]);
  const plannedScreens = plan.surfaces.flatMap((surface) => surface.screen_ids);
  assert.deepEqual([...new Set(plannedScreens)].sort(), [...new Set(screenIds)].sort());
  const paneIds = [...settings.matchAll(/data-pane="([^"]+)"/g)].map((match) => match[1]);
  const plannedPanes = plan.surfaces.flatMap((surface) => surface.settings_panes || []);
  assert.deepEqual([...new Set(plannedPanes)].sort(), [...new Set(paneIds)].sort());
});

test("an all-unproven prepared shape is valid and cannot imply acceptance", () => {
  const result = validate(baseRun());
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /"unproven":/);
});

test("browser evidence cannot pass an installed native gate", () => {
  const run = baseRun();
  pass(run, "main.shell", "native.window", evidence());
  const result = validate(run);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /requires installed-tauri evidence/);
});

test("synthetic installed evidence cannot pass live capture", () => {
  const run = baseRun();
  pass(run, "capture.recording", "live.capture", evidence({ environment: "installed-tauri", observer: "agent-assisted" }));
  const result = validate(run);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /requires installed-tauri live-device evidence/);
});

test("agent observation cannot pass visual approval or cold comprehension", () => {
  for (const [surface, gate] of [["main.shell", "human.visual"], ["capture.consent", "human.cold-comprehension"]]) {
    const run = baseRun();
    pass(run, surface, gate, evidence({ environment: "installed-tauri", stimulus: "retained-local", observer: "agent-assisted" }));
    const result = validate(run);
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /requires installed human-operator evidence/);
  }
});

test("evidence bound to another executable is rejected", () => {
  const run = baseRun();
  pass(run, "main.shell", "native.window", evidence({ environment: "installed-tauri", app_executable_sha256: "b".repeat(64) }));
  const result = validate(run);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /another executable/);
});

test("a changed review plan invalidates a run", () => {
  const run = baseRun();
  run.source.review_plan_sha256 = "b".repeat(64);
  const result = validate(run);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /review plan digest changed/);
});

test("partial is not an atomic verdict", () => {
  const run = baseRun();
  run.checks[0].verdict = "partial";
  const result = validate(run);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /invalid verdict/);
});
