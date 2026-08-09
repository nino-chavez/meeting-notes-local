import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  SURFACE_STATES,
  captureToolbarPresentation,
  normalizedOptions,
} from "./reference-surfaces.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const uiRoot = resolve(here, "..");
const html = readFileSync(join(here, "index.html"), "utf8");
const css = readFileSync(join(here, "reference-surfaces.css"), "utf8");
const source = readFileSync(join(here, "reference-surfaces.mjs"), "utf8");
const migration = JSON.parse(readFileSync(join(here, "migration-map.json"), "utf8"));

function splitSelectorList(value) {
  const selectors = [];
  let start = 0;
  let depth = 0;
  for (let index = 0; index < value.length; index += 1) {
    const character = value[index];
    if (character === "(") depth += 1;
    else if (character === ")") depth = Math.max(0, depth - 1);
    else if (character === "," && depth === 0) {
      selectors.push(value.slice(start, index));
      start = index + 1;
    }
  }
  selectors.push(value.slice(start));
  return selectors.map((selector) => selector.trim().replace(/\s+/g, " ")).filter(Boolean);
}

function extractSelectors(value) {
  const clean = value.replace(/\/\*[\s\S]*?\*\//g, "");
  const selectors = [];
  let start = 0;
  for (let index = 0; index < clean.length; index += 1) {
    const character = clean[index];
    if (character === "{") {
      const header = clean.slice(start, index).trim();
      if (header && !header.startsWith("@")) selectors.push(...splitSelectorList(header));
      start = index + 1;
    } else if (character === "}") {
      start = index + 1;
    }
  }
  return [...new Set(selectors)];
}

function relevantSelectors(file) {
  return extractSelectors(readFileSync(file, "utf8"))
    .filter((selector) => migration.relevantFragments.some((fragment) => selector.includes(fragment)));
}

function tagAttributes(tag) {
  return Object.fromEntries([...tag.matchAll(/([\w:-]+)="([^"]*)"/g)].map((match) => [match[1], match[2]]));
}

test("the specimen exposes every required reference and state", () => {
  assert.deepEqual(SURFACE_STATES.primary, ["loading", "empty", "ready", "error"]);
  assert.deepEqual(SURFACE_STATES.capture, ["consent", "recording", "degraded", "processing", "error"]);
  for (const surface of ["primary", "capture"]) {
    assert.match(html, new RegExp(`data-reference-surface="${surface}"`));
    for (const state of SURFACE_STATES[surface]) {
      const attribute = surface === "primary" ? "data-primary-state" : "data-capture-state";
      assert.match(html, new RegExp(`${attribute}="${state}"`), `${surface}/${state} is missing`);
    }
  }
  assert.match(html, /id="capture-continue"[^>]*disabled/);
  assert.match(html, /class="ds-button ds-button-primary" id="capture-continue"/);
  assert.doesNotMatch(html, /ds-button-live" id="capture-continue"/);
  assert.match(css, /button:disabled, input:disabled, select:disabled, textarea:disabled/);
});

test("capture truth stays exact in words, state, and action", () => {
  assert.match(html, /It does not join the call or tell anyone else\./);
  assert.match(html, /The other people on this call know they are being recorded\./);
  assert.match(html, /This confirmation applies only to this recording attempt\./);
  assert.match(html, /Recording · degraded/);
  assert.match(html, /Recording continues with the microphone\. System audio stopped arriving\./);
  assert.match(html, /Stop only when you intend to end this recording\./);
  assert.match(html, /The transcript is made after the meeting ends, not while it runs\./);
  assert.match(html, /Nothing is uploaded\./);
  assert.match(html, /Yawn is making the transcript on this Mac\./);
  assert.match(css, /Reference specimen · no local meeting data or audio is used/);
  assert.doesNotMatch(html, /recording complete/i);
  assert.doesNotMatch(html, /everyone (?:was|has been) notified/i);

  assert.deepEqual(captureToolbarPresentation("recording"), {
    label: "Recording · both channels active", tone: "is-live", stop: true,
  });
  assert.deepEqual(captureToolbarPresentation("degraded"), {
    label: "Recording · channel needs attention", tone: "is-degraded", stop: true,
  });
  assert.equal(captureToolbarPresentation("processing").stop, false);
});

test("normalization refuses undeclared surface states and appearance values", () => {
  assert.deepEqual(normalizedOptions({}), {
    surface: "primary", state: "ready", appearance: "light", geometry: "comfortable", presentation: false,
  });
  assert.equal(normalizedOptions({ surface: "capture", state: "ready" }).state, "consent");
  assert.equal(normalizedOptions({ surface: "primary", state: "degraded" }).state, "ready");
  assert.equal(normalizedOptions({ appearance: "sepia" }).appearance, "light");
  assert.equal(normalizedOptions({ geometry: "tiny" }).geometry, "comfortable");
});

test("the primary and capture references declare comfortable and minimum geometry", () => {
  assert.match(css, /\.primary-reference \{ width: 1120px; height: 720px; \}/);
  assert.match(css, /data-geometry="minimum"\] \.primary-reference \{ width: 720px; height: 560px; \}/);
  assert.match(css, /\.capture-reference \{ width: 620px; height: 560px; \}/);
  assert.match(css, /data-geometry="minimum"\] \.capture-reference \{ width: 520px; height: 520px; \}/);
  assert.match(css, /data-geometry="minimum"\] \.primary-window-body \{ grid-template-columns: 96px 210px minmax\(0, 1fr\); \}/);
});

test("light, dark, focus, reduced motion, contrast, and transparency are explicit", () => {
  assert.match(css, /--brand: #843b31/);
  assert.match(css, /--live: #146b4a/);
  assert.match(css, /data-theme="dark"/);
  assert.match(css, /--brand: #d98f80/);
  assert.match(css, /--live: #68c999/);
  assert.match(css, /:focus-visible[\s\S]*outline: 3px solid var\(--focus\)/);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)/);
  assert.match(css, /@media \(prefers-contrast: more\)/);
  assert.match(css, /@media \(prefers-reduced-transparency: reduce\)/);
  assert.doesNotMatch(css, /animation\s*:/);
});

test("keyboard paths use native controls, roving focus, and safe Escape behavior", () => {
  assert.match(source, /ArrowLeft/);
  assert.match(source, /ArrowRight/);
  assert.match(source, /ArrowUp/);
  assert.match(source, /ArrowDown/);
  assert.match(source, /event\.key === "Home"/);
  assert.match(source, /event\.key === "End"/);
  assert.match(source, /\["recording", "degraded"\]\.includes\(options\.state\)/);
  assert.match(source, /event\.key !== "Escape"/);
  assert.match(html, /role="tablist" data-roving="horizontal"/);
  assert.match(html, /aria-current="page" tabindex="0"/);
  assert.equal((html.match(/>Hide<\/button>/g) || []).length, 0);
});

test("ids are unique and every aria-controls reference resolves", () => {
  const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map((match) => match[1]);
  assert.equal(new Set(ids).size, ids.length, "duplicate ids found");
  const idSet = new Set(ids);
  for (const match of html.matchAll(/\baria-controls="([^"]+)"/g)) {
    assert.ok(idSet.has(match[1]), `aria-controls points to missing #${match[1]}`);
  }
});

test("enabled buttons have visible text or an accessible name", () => {
  for (const match of html.matchAll(/<button\b[^>]*>[\s\S]*?<\/button>/g)) {
    const tag = match[0].slice(0, match[0].indexOf(">") + 1);
    const attributes = tagAttributes(tag);
    const text = match[0].replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
    assert.ok(text || attributes["aria-label"], `unnamed button: ${tag}`);
  }
});

test("the reference does not import comparator product assumptions", () => {
  assert.doesNotMatch(html, /calendar|account|shared workspace|generated summary/i);
  assert.doesNotMatch(html, /share (?:this|meeting|note)|invite (?:a|the) bot/i);
  assert.match(html, /On this Mac/);
});

test("every current relevant selector resolves through the migration map", () => {
  const allRelevant = migration.sourceFiles.flatMap((relative) => {
    const file = resolve(uiRoot, relative.replace(/^apps\/desktop\/ui\//, ""));
    return relevantSelectors(file).map((selector) => ({ relative, selector }));
  });
  assert.ok(allRelevant.length >= 200, `selector inventory unexpectedly small: ${allRelevant.length}`);
  const patterns = migration.mappings.map((entry) => ({ ...entry, regex: new RegExp(entry.sourcePattern) }));
  const unmapped = allRelevant.filter(({ selector }) => !patterns.some(({ regex }) => regex.test(selector)));
  assert.deepEqual(unmapped, [], `unmapped selectors:\n${unmapped.map(({ relative, selector }) => `${relative}: ${selector}`).join("\n")}`);
  for (const mapping of patterns) {
    assert.ok(allRelevant.some(({ selector }) => mapping.regex.test(selector)), `unused migration pattern: ${mapping.sourcePattern}`);
    assert.ok(["shared-component", "state-exception"].includes(mapping.kind));
    assert.ok(mapping.reason.length >= 24);
  }
});
