import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  CAPTURE_PRESENTATIONS,
  CAPTURE_STATES,
  RECORD_PRESENTATIONS,
  RECORD_STATES,
  capturePresentation,
  consentReady,
  normalizePreference,
  recordPresentation,
} from "./state.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const html = readFileSync(join(here, "index.html"), "utf8");
const foundations = readFileSync(join(here, "foundations.css"), "utf8");
const components = readFileSync(join(here, "components.css"), "utf8");
const patterns = readFileSync(join(here, "patterns.css"), "utf8");
const specimenScript = readFileSync(join(here, "specimen.js"), "utf8");

test("capture lifecycle distinguishes live, degraded, stopping, failure, and recovery", () => {
  assert.deepEqual(CAPTURE_STATES, [
    "consent", "arming", "recording", "degraded", "stopping",
    "processing", "ready", "failure", "recovered",
  ]);

  const liveStates = CAPTURE_STATES.filter((state) => CAPTURE_PRESENTATIONS[state].live);
  assert.deepEqual(liveStates, ["recording", "degraded", "stopping"]);
  assert.equal(capturePresentation("arming").status, "Armed, not recording");
  assert.equal(capturePresentation("stopping").primaryDisabled, true);
  assert.equal(capturePresentation("processing").live, false);
  assert.match(capturePresentation("processing").detail, /use the rest of Yawn/);
  assert.match(capturePresentation("failure").detail, /not complete/);
  assert.match(capturePresentation("recovered").status, /not complete/);

  const degraded = capturePresentation("degraded");
  assert.notEqual(degraded.status, capturePresentation("recording").status);
  assert.notEqual(degraded.statusState, capturePresentation("recording").statusState);
});

test("consent stays disabled for every missing prerequisite", () => {
  const complete = {
    startup: "ready",
    retention: "selected",
    participant: true,
    accuracy: true,
    localProcessing: true,
  };
  assert.equal(consentReady(complete), true);

  for (const key of Object.keys(complete)) {
    const missing = { ...complete };
    missing[key] = typeof complete[key] === "boolean" ? false : "missing";
    assert.equal(consentReady(missing), false, `${key} must be required`);
  }
});

test("meeting record covers every honest fallback without inventing a summary", () => {
  assert.deepEqual(RECORD_STATES, [
    "note", "transcript-only", "metadata-only", "summary-failed",
    "transcript-unavailable", "meeting-unavailable",
  ]);
  for (const state of RECORD_STATES) {
    const presentation = recordPresentation(state);
    assert.equal(typeof presentation.title, "string");
    assert.equal(typeof presentation.meta, "string");
    assert.equal(typeof presentation.body, "string");
    assert.doesNotMatch(presentation.body, /generated summary is ready/i);
  }
  assert.match(RECORD_PRESENTATIONS["summary-failed"].body, /retained transcript/);
  assert.match(RECORD_PRESENTATIONS["transcript-unavailable"].body, /not shown as complete/);
});

test("preference normalization fails closed to system behavior", () => {
  assert.equal(normalizePreference("dark", ["system", "light", "dark"]), "dark");
  assert.equal(normalizePreference("sepia", ["system", "light", "dark"]), "system");
});

test("foundations define adaptive appearance and accessibility modes once", () => {
  for (const token of [
    "--ys-font-ui", "--ys-font-record", "--ys-font-mono",
    "--ys-surface-window", "--ys-surface-navigation", "--ys-surface-content",
    "--ys-brand", "--ys-live", "--ys-warning", "--ys-error", "--ys-information",
    "--ys-control-min", "--ys-control-regular", "--ys-focus-width",
  ]) assert.match(foundations, new RegExp(token));

  assert.match(foundations, /data-appearance="dark"/);
  assert.match(foundations, /prefers-color-scheme: dark/);
  assert.match(foundations, /data-contrast="more"/);
  assert.match(foundations, /prefers-contrast: more/);
  assert.match(foundations, /data-motion="reduce"/);
  assert.match(foundations, /prefers-reduced-motion: reduce/);
  assert.match(foundations, /data-transparency="reduce"/);
  assert.match(foundations, /prefers-reduced-transparency: reduce/);
  assert.match(foundations, /forced-colors: active/);
  assert.match(
    foundations,
    /:where\([\s\S]*?\[tabindex\]:not\(\[tabindex="-1"\]\)[\s\S]*?\)\s*\{\s*outline: none;/,
    "the control reset must stay lower-specificity than :focus-visible",
  );
});

test("the initial component set and its state hooks are executable", () => {
  for (const selector of [
    ".ys-toolbar", ".ys-status", ".ys-button", ".ys-icon-button",
    ".ys-sidebar-row", ".ys-meeting-row", ".ys-disclosure-row", ".ys-empty-row",
    ".ys-tab", ".ys-segmented", ".ys-menu-item",
    ".ys-settings-section", ".ys-settings-row", ".ys-select", ".ys-toggle", ".ys-radio-choice", ".ys-help-text",
    ".ys-inline-notice", ".ys-progress-row", ".ys-confirmation", ".ys-popover", ".ys-dialog",
  ]) assert.ok(components.includes(selector), `${selector} is missing`);

  for (const state of ["hover", "active", "focus", "selected", "disabled", "error"]) {
    assert.match(components, new RegExp(state));
  }
  assert.match(components, /:focus-visible/);
  assert.match(components, /aria-current/);
  assert.match(components, /aria-selected/);
  assert.match(components, /aria-pressed/);
});

test("source-first search keeps a retained passage between the query and its action", () => {
  for (const selector of [
    ".ys-search", ".ys-search__form", ".ys-search__input", ".ys-search__results",
    ".ys-search__result", ".ys-search__quote", ".ys-search__empty",
  ]) assert.ok(patterns.includes(selector), `${selector} is missing`);

  const searchStart = html.indexOf("<h3>Source-first search</h3>");
  const searchEnd = html.indexOf("</article>", searchStart);
  assert.ok(searchStart > -1 && searchEnd > searchStart, "Search pattern specimen is missing");
  const searchPattern = html.slice(searchStart, searchEnd);
  assert.match(searchPattern, /Exact local search\. No inference\./);
  assert.match(searchPattern, /Transcript · turn 4/);
  assert.match(searchPattern, /Open transcript/);
  assert.doesNotMatch(searchPattern, /generated answer/i);
});

test("specimen includes all five window roles and explicit browser boundaries", () => {
  for (const role of ["primary", "record", "settings", "capture", "transient"]) {
    assert.match(html, new RegExp(`id="role-${role}"`));
  }
  assert.match(patterns, /data-role="primary"/);
  assert.match(patterns, /data-role="settings"/);
  assert.match(html, /Executable browser specimen/);
  assert.match(html, /Synthetic content/);
  assert.match(html, /does not prove native macOS behavior or product readiness/);
  assert.match(html, /automatic notes remain unavailable/i);
  assert.match(html, /Share note[\s\S]*disabled/);
});

test("specimen exposes deterministic controls for required lifecycle and accessibility states", () => {
  for (const state of CAPTURE_STATES) {
    assert.match(html, new RegExp(`data-capture-state="${state}"`));
  }
  for (const state of RECORD_STATES) {
    assert.match(html, new RegExp(`data-record-state="${state}"`));
  }
  for (const state of ["loading", "empty", "ready", "disabled", "selected", "error", "degraded"]) {
    assert.match(html, new RegExp(`data-state="${state}"`));
  }
  for (const control of [
    "appearance-control", "contrast-control", "motion-control",
    "transparency-control", "zoom-control", "ia-geometry-control",
  ]) assert.match(html, new RegExp(`id="${control}"`));
});

test("primary-window comparison develops three structures before deriving one configurable contract", () => {
  const section = html.match(/<section class="specimen-section" id="meetings-front-door-options"[\s\S]*?(?=\n\s*<section class="specimen-section")/)?.[0];
  assert.ok(section, "Meetings comparison section is missing");

  for (const option of ["persistent-three-pane", "adaptive-two-pane", "single-pane-stack"]) {
    assert.match(section, new RegExp(`data-ia-option="${option}"`));
  }
  assert.equal([...section.matchAll(/data-ia-option="/g)].length, 3);
  const optionGrid = section.match(/<div class="ia-option-grid">[\s\S]*?<div class="ia-task-comparison"/)?.[0];
  assert.ok(optionGrid, "Option grid is missing");
  assert.doesNotMatch(optionGrid, /recommended|why it leads|approved mac split/i);
  assert.match(section, /Production contract/);
  assert.match(section, /Keep one model; make pane visibility configurable/);
  assert.match(section, /value="automatic" checked/);
  assert.match(section, /value="focus"/);
  assert.match(section, /value="library"/);
  assert.match(section, /View → Layout and Settings → Desktop Behavior/);
  assert.match(section, /almost 40% of the 720-pixel minimum width/);
  assert.match(section, /Active capture may take over the window/);
  assert.match(section, /Search returns retained passages, not generated answers/);
  assert.doesNotMatch(section, /<strong>Ask<\/strong>|<strong>Actions<\/strong>|<span>Home<\/span>/);
  assert.doesNotMatch(section, /Name this meeting|Recording audio held on this Mac|\bbytes\b/i);
});

test("Meetings comparison exposes deterministic comfortable and minimum geometry", () => {
  assert.match(html, /id="specimen-main" data-zoom="100" data-ia-geometry="comfortable"/);
  assert.match(html, /value="minimum">720 × 560 minimum/);
  assert.match(specimenScript, /specimenMain\.dataset\.iaGeometry = event\.currentTarget\.value/);
  assert.match(specimenScript, /adaptiveOption\.dataset\.compactView = "record"/);
  assert.match(specimenScript, /stackOption\.dataset\.stackView = "record"/);
  assert.match(readFileSync(join(here, "specimen.css"), "utf8"), /data-ia-geometry="minimum"/);
});

test("ids are unique and local aria references resolve", () => {
  const ids = [...html.matchAll(/\sid="([^"]+)"/g)].map((match) => match[1]);
  assert.equal(new Set(ids).size, ids.length);
  const references = [...html.matchAll(/\saria-(?:controls|labelledby)="([^"]+)"/g)]
    .flatMap((match) => match[1].split(/\s+/));
  const idSet = new Set(ids);
  assert.deepEqual(references.filter((reference) => !idSet.has(reference)), []);
});

test("every icon-only button has an accessible name", () => {
  const iconButtons = [...html.matchAll(/<button\b([^>]*class="[^"]*ys-icon-button[^"]*"[^>]*)>/g)]
    .map((match) => match[1]);
  assert.ok(iconButtons.length > 0);
  for (const attributes of iconButtons) {
    assert.match(attributes, /aria-label="[^"]+"/);
  }
});

test("transient layers dismiss safely and return focus to their triggers", () => {
  assert.match(specimenScript, /if \(dialog\.open\)[\s\S]*dialog\.close\(\)/);
  assert.match(specimenScript, /dialog\?\.addEventListener\("close", \(\) => dialogTrigger\.focus\(\)\)/);
  assert.match(specimenScript, /popoverTrigger\.focus\(\)/);
  assert.match(specimenScript, /if \(!popover\.hidden\)[\s\S]*closePopover\(\)/);
});
