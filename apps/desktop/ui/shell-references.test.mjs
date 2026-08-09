// The shell calls only names it actually has.
//
// Written 2026-08-07 after an over-broad edit deleted `renderTranscriptNote`
// while a call to it survived. `node --check` passed — it parses, it does not
// resolve — and the Rust contract tests passed too, because they assert strings
// that were still present elsewhere in the file. The failure would have been a
// ReferenceError the first time a transcript rendered, which is to say on every
// finished meeting.
//
// This repo deliberately carries no JS toolchain: no package manager install, no
// node_modules, no lint. So the check is written against `node:test`, which is
// already the harness, rather than by adding ESLint for one rule.
//
// It is intentionally narrow. Only *bare* calls are examined — `name(` not
// preceded by a dot — because member calls resolve against objects this cannot
// see. A name counts as available if the file declares it, imports it, or it is
// on the browser/ECMAScript allowlist below. The allowlist is the maintenance
// cost, and it is the right place for the cost to sit: a new global is one line,
// and forgetting it fails loudly rather than silently.

import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));

// Globals the shell may call without declaring. Kept short on purpose: anything
// long enough to hide a typo defeats the check.
const AVAILABLE_GLOBALS = new Set([
  // ECMAScript
  "Array", "BigInt", "Boolean", "Error", "JSON", "Map", "Math", "Number",
  "Object", "Promise", "Set", "String", "Symbol", "parseFloat", "parseInt",
  "Date", "isNaN", "isFinite", "encodeURIComponent", "decodeURIComponent", "structuredClone",
  // Browser
  "alert", "atob", "btoa", "clearInterval", "clearTimeout", "confirm", "fetch",
  "queueMicrotask", "requestAnimationFrame", "setInterval", "setTimeout",
  // Control flow and operators the call-shaped regex also matches
  "if", "for", "while", "switch", "catch", "return", "typeof", "function",
  "await", "async", "new", "delete", "void", "in", "of", "do", "else", "yield",
]);

function withoutStringsAndComments(source) {
  // Crude but sufficient: the goal is to stop a call-shaped sequence inside a
  // comment or a message string from being read as a call. Replacing rather than
  // deleting keeps every offset, so nothing shifts.
  return source
    .replace(/\/\*[\s\S]*?\*\//g, (match) => " ".repeat(match.length))
    .replace(/(^|[^:])\/\/[^\n]*/g, (match, lead) => lead + " ".repeat(match.length - lead.length))
    .replace(/`(?:\\[\s\S]|[^\\`])*`/g, (match) => `\`${" ".repeat(Math.max(0, match.length - 2))}\``)
    .replace(/"(?:\\[\s\S]|[^\\"\n])*"/g, (match) => `"${" ".repeat(Math.max(0, match.length - 2))}"`)
    .replace(/'(?:\\[\s\S]|[^\\'\n])*'/g, (match) => `'${" ".repeat(Math.max(0, match.length - 2))}'`);
}

function declaredNames(source) {
  const names = new Set();
  for (const [, name] of source.matchAll(/\bfunction\s+([A-Za-z_$][\w$]*)/g)) names.add(name);
  for (const [, name] of source.matchAll(/\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)/g)) names.add(name);
  for (const [, name] of source.matchAll(/\bclass\s+([A-Za-z_$][\w$]*)/g)) names.add(name);
  // Destructured bindings and parameters, which are call targets often enough.
  for (const [, group] of source.matchAll(/\b(?:const|let|var)\s*\{([^}]*)\}/g)) {
    for (const part of group.split(",")) {
      const name = part.split(":").pop().split("=")[0].trim();
      if (/^[A-Za-z_$][\w$]*$/.test(name)) names.add(name);
    }
  }
  for (const [, group] of source.matchAll(/\bimport\s*\{([^}]*)\}\s*from/g)) {
    for (const part of group.split(",")) {
      const name = part.split(" as ").pop().trim();
      if (/^[A-Za-z_$][\w$]*$/.test(name)) names.add(name);
    }
  }
  // Method shorthand in an object literal — `enter() { ... }` — is a definition
  // that reads exactly like a call. Collecting it as declared is what keeps this
  // check usable on `navigation-state.mjs`, which is full of them.
  for (const [, name] of source.matchAll(/([A-Za-z_$][\w$]*)\s*\([^()]*\)\s*\{/g)) {
    names.add(name);
  }
  // Function parameters. Coarse — every identifier inside a parameter list —
  // which errs toward accepting, and accepting is the safe direction for a
  // check whose only job is to catch a name that exists nowhere at all.
  for (const [, group] of source.matchAll(/(?:function\s*[\w$]*\s*|\)\s*=>|\b)\(([^()]*)\)\s*(?:=>|\{)/g)) {
    for (const [, name] of group.matchAll(/([A-Za-z_$][\w$]*)/g)) names.add(name);
  }
  return names;
}

function bareCallTargets(source) {
  const targets = new Map();
  for (const match of source.matchAll(/(^|[^.\w$])([A-Za-z_$][\w$]*)\s*\(/gm)) {
    const name = match[2];
    if (!targets.has(name)) {
      targets.set(name, source.slice(0, match.index).split("\n").length);
    }
  }
  return targets;
}

for (const file of ["main.js", "navigation-state.mjs"]) {
  test(`${file} calls nothing it does not have`, () => {
    const source = withoutStringsAndComments(readFileSync(join(here, file), "utf8"));
    const available = declaredNames(source);
    const missing = [];
    for (const [name, line] of bareCallTargets(source)) {
      if (available.has(name) || AVAILABLE_GLOBALS.has(name)) continue;
      missing.push(`${file}:${line} calls ${name}(), which is never declared or imported`);
    }
    assert.deepEqual(missing, []);
  });
}

test("the shell renders its own transcript note, which an edit once removed", () => {
  // The specific regression, kept beside the general check so the reason the
  // general check exists is not lost if it is ever softened.
  const source = readFileSync(join(here, "main.js"), "utf8");
  assert.match(source, /function renderTranscriptNote\(\)/);
  assert.match(source, /\.then\(renderTranscriptNote\)/);
});

test("the desktop shell exposes the library-first journey without presenting planned work as live", () => {
  const html = readFileSync(join(here, "index.html"), "utf8");
  const source = readFileSync(join(here, "main.js"), "utf8");

  for (const destination of ["Meetings", "Ask", "Actions", "Settings"]) {
    assert.match(html, new RegExp(`>${destination}<`));
  }
  for (const meetingView of ["Note", "Transcript", "Actions", "Evidence", "Details"]) {
    assert.match(html, new RegExp(`data-meeting-(?:tab|panel)=["']${meetingView.toLowerCase()}["']`));
    assert.match(html, new RegExp(`data-retained-meeting-(?:tab|panel)=["']${meetingView.toLowerCase()}["']`));
  }
  assert.match(html, /id="meeting-context-list"/);
  assert.match(html, /Open another meeting\./);
  assert.match(html, /Shell preview · synthetic content/);
  assert.match(html, /No meeting was recorded and nothing on this screen is saved or quotable\./);
  assert.match(html, /Automatic notes and action extraction are not available yet\./);
  assert.match(source, /openPrototypeMeetingDetail\(activeMeetingId \|\| "prototype-meeting", \{ focus: true \}\)/);
  assert.match(source, /selected \? "Current" : "Open"/);
  assert.match(html, /These three meetings are examples\. This browser does not read or save meetings on your Mac\./);
  assert.doesNotMatch(html, /It will not become a task list\./);
  assert.doesNotMatch(html, /current-data fixture/i);
  assert.doesNotMatch(source, /Synthetic (?:retention )?fixture/);
});

test("the approved direction has one Paper Focus shell and no comparison plumbing", () => {
  const html = readFileSync(join(here, "index.html"), "utf8");
  const css = readFileSync(join(here, "styles.css"), "utf8");
  const source = readFileSync(join(here, "main.js"), "utf8");

  assert.doesNotMatch(html, /id=["']treatment-select["']/);
  assert.doesNotMatch(html, /Paper (?:instrument|focus) ·/i);
  assert.doesNotMatch(source, /applyShellTreatment|dataset\.treatment|requestedTreatment|shellTreatment/);
  assert.doesNotMatch(css, /data-treatment|Paper Instrument|Candidate [AB]/);
  assert.match(css, /html\[data-prototype="true"\] \.legacy-home-link,\s*html\[data-prototype="true"\] \.installed-only \{ display: none; \}/);
  assert.match(css, /--brand-accent: #843B31/);
  assert.match(css, /--capture-live: #146B4A/);
  assert.match(css, /--record-font:/);
  assert.match(css, /font-size: 13px/);
  assert.match(css, /"JetBrains Mono", "SFMono-Regular"/);
  assert.match(css, /--radius-panel: 8px/);
  assert.match(css, /overlays may/);
  assert.match(css, /box-shadow: 0 18px 46px rgba\(41, 51, 46, 0\.18\) !important/);
  assert.match(css, /html\[data-prototype="true"\] \.app-workspace \{\s*grid-template-columns: minmax\(0, 1fr\);\s*grid-template-rows: 48px minmax\(0, 1fr\);/);
});

test("Mac Split is the selected prototype shell while comparisons and the wireframe remain available", () => {
  const html = readFileSync(join(here, "index.html"), "utf8");
  const source = readFileSync(join(here, "main.js"), "utf8");
  const calibration = readFileSync(join(here, "native-calibration.css"), "utf8");

  assert.match(html, /href="native-calibration\.css"/);
  assert.match(source, /shellParams\.get\("calibration"\) \|\| "split"/);
  assert.match(source, /requestedNativeCalibration === "wireframe"/);
  assert.match(source, /\["document", "reference"\]\.includes\(requestedNativeCalibration\)/);
  assert.match(source, /shellPrototype \|\| invoke\s*\? "split"/);
  assert.match(source, /dataset\.nativeCalibration = nativeCalibration/);
  assert.match(source, /!\["split", "reference"\]\.includes\(nativeCalibration\)/);
  assert.match(source, /nativeCalibration === "document"\) setMeetingFocus\(true\)/);
  assert.match(calibration, /html\[data-native-calibration="split"\]/);
  assert.match(calibration, /html\[data-native-calibration="document"\]/);
  assert.match(calibration, /html\[data-native-calibration="reference"\]/);
  assert.match(calibration, /Mac Split is the approved H1 composition/);
  assert.match(calibration, /\[data-screen="recording-screen"\]/);
  assert.match(calibration, /\.settings-map button strong/);
  assert.match(calibration, /\.planned-answer-shell/);
  assert.match(calibration, /@media \(max-width: 880px\)/);
  assert.match(calibration, /@media \(max-width: 800px\)/);
  assert.match(calibration, /\.planned-tag/);
  assert.match(calibration, /\.meeting-command-dock/);
  assert.doesNotMatch(calibration, /data-treatment/);
});

test("the installed app adopts Mac Split without drawing browser traffic lights", () => {
  const html = readFileSync(join(here, "index.html"), "utf8");
  const source = readFileSync(join(here, "main.js"), "utf8");
  const calibration = readFileSync(join(here, "native-calibration.css"), "utf8");
  const tauri = JSON.parse(readFileSync(join(here, "../src-tauri/tauri.conf.json"), "utf8"));
  const preview = JSON.parse(readFileSync(join(here, "../src-tauri/tauri.preview.conf.json"), "utf8"));
  const uiReview = JSON.parse(readFileSync(join(here, "../src-tauri/tauri.ui-review.conf.json"), "utf8"));

  assert.match(source, /const shellEnvironment = installedUiReview \? "installed-review" : invoke \? "installed" : "browser"/);
  assert.match(source, /document\.documentElement\.dataset\.shellEnvironment = shellEnvironment/);
  assert.match(html, /<header class="app-header ys-toolbar" data-tauri-drag-region="deep">/);
  assert.match(calibration, /html\[data-shell-environment="browser"\]\[data-native-calibration\] \.app-header::before/);
  assert.equal((calibration.match(/\.app-header::before/g) || []).length, 1);
  for (const config of [tauri, preview, uiReview]) {
    const [window] = config.app.windows;
    assert.equal(window.titleBarStyle, "Overlay");
    assert.equal(window.hiddenTitle, true);
  }
});

test("native calibration keeps one status, adaptive semantic tokens, and quiet structural layers", () => {
  const html = readFileSync(join(here, "index.html"), "utf8");
  const source = readFileSync(join(here, "main.js"), "utf8");
  const styles = readFileSync(join(here, "styles.css"), "utf8");
  const calibration = readFileSync(join(here, "native-calibration.css"), "utf8");

  assert.match(html, /aria-label="Recording status: Ready\. Open quick control\."/);
  assert.match(source, /`Recording status: \$\{presentation\.triggerLabel\}\. Open quick control\.`/);
  assert.match(calibration, /\.product-state \{\s*display: none;/);
  assert.match(styles, /--brand-accent: #843b31;/i);
  assert.match(styles, /--capture-live: #146b4a;/i);
  assert.match(styles, /--locality-ink: #4d6658;/i);
  assert.match(styles, /quick-control-glyph\[data-state="recording"\][^}]*var\(--capture-live\)/s);
  assert.match(styles, /prototype-evidence-preview[^}]*var\(--semantic-info\)/s);
  assert.match(calibration, /@media \(prefers-color-scheme: dark\)/);
  assert.match(calibration, /--brand-accent: #d98f80;/i);
  assert.match(calibration, /--capture-live: #68c999;/i);
  assert.match(calibration, /--surface-sidebar: #222221;/i);
  assert.match(calibration, /--surface-list: #282826;/i);
  assert.match(calibration, /--surface-toolbar: rgba\(37, 37, 35, 0\.9\);/i);
  assert.match(calibration, /--surface-record: #2d2c2a;/i);
  assert.match(calibration, /meeting-context-row\[aria-current="page"\][^}]*border-left: 2px solid var\(--brand-accent\)/s);
  assert.match(calibration, /settings-trust-statement[^}]*border-radius: 0;[^}]*background: transparent;/s);
  assert.match(calibration, /data-production-system="desktop-v1"[^}]*\.meeting-workspace-heading h1[^}]*font-size: var\(--ys-type-record\)/s);
  assert.match(calibration, /#meeting-detail-screen\.screen\.active[^}]*width: 100%/s);
  assert.match(calibration, /\.app-workspace\.ys-window[^}]*border: 0;[^}]*border-radius: 0;/s);
  assert.match(calibration, /\.claim-evidence[^}]*background: transparent;[^}]*text-decoration: underline;/s);
});

test("Paper Focus makes the meeting transition and its return path explicit", () => {
  const html = readFileSync(join(here, "index.html"), "utf8");
  const css = readFileSync(join(here, "styles.css"), "utf8");
  const source = readFileSync(join(here, "main.js"), "utf8");

  for (const control of ["meeting-focus-toggle", "meeting-command-dock", "meeting-dock-record"]) {
    assert.match(html, new RegExp(`id=["']${control}["']`));
  }
  assert.match(html, /Ask this meeting · Planned/);
  assert.match(source, /function setMeetingFocus\(focused\)/);
  assert.match(source, /openPrototypeMeetingDetail\(meetingId, \{ focus: true \}\)/);
  assert.match(source, /openPrototypeMeetingDetail\("prototype-meeting", \{ focus: true \}\)/);
  assert.match(source, /openPrototypeMeetingDetail\(activeMeetingId \|\| "prototype-meeting", \{ focus: true \}\)/);
  assert.match(source, /enabled \? "Show library" : "Focus meeting"/);
  assert.match(source, /if \(focus\) \{\s*meetingDetailTitle\.tabIndex = -1;\s*meetingDetailTitle\.focus\(\{ preventScroll: true \}\);/);
  assert.match(source, /id !== "meeting-detail-screen" && shellPrototype\) setMeetingFocus\(false\)/);
  assert.match(css, /data-meeting-focus="true"\] \.app-sidebar/);
  assert.match(css, /data-meeting-focus="true"\] \.meeting-context-pane/);
  assert.match(css, /meeting-command-dock/);
});

test("synthetic claim evidence stays inside the selected meeting", () => {
  const source = readFileSync(join(here, "main.js"), "utf8");
  const start = source.indexOf("function appendMeetingClaim(");
  const end = source.indexOf("function renderMeetingDetail(", start);
  const renderer = source.slice(start, end);

  assert.match(renderer, /prototype-evidence-preview/);
  assert.match(renderer, /expanded \? "Hide excerpt" : "Show excerpt"/);
  assert.match(renderer, /sourceTab === "evidence" \? "Show excerpt" : "View source"/);
  assert.doesNotMatch(renderer, /selectProductScreen\("prototype-meeting-screen"/);
  assert.match(source, /evidenceText: "Let’s keep first run to three steps\./);
  assert.match(source, /Synthetic transcript ·/);
});

test("the shell makes deletion consequences reviewable without enabling deletion", () => {
  const html = readFileSync(join(here, "index.html"), "utf8");
  const source = readFileSync(join(here, "main.js"), "utf8");

  assert.equal((html.match(/Shell preview only\. You can review this consequence, but nothing can be deleted here\./g) || []).length, 2);
  assert.match(html, /This deletes only this meeting’s local audio\. The transcript, note, evidence, and meeting details remain\./);
  assert.match(html, /This removes the transcript, the note, your own note, and any audio still held\./);
  assert.match(source, /audioDeletionHandle: transcriptAvailable \? `prototype-audio-delete-\$\{meetingId\}` : ""/);
  assert.match(source, /meetingDeletionHandle: `prototype-meeting-delete-\$\{meetingId\}`/);
  assert.match(source, /recordingDeleteConfirm\.disabled = shellPrototype/);
  assert.match(source, /meetingDeleteConfirm\.disabled = shellPrototype/);
  assert.match(source, /renderAudioRetention\(response\.audioRetention, response\.audioDeletionHandle\);[\s\S]*?closeMeetingDeleteReview\(\);[\s\S]*?meetingDeletionHandle = response\.meetingDeletionHandle/);
  assert.equal((source.match(/\? "Deletion unavailable in shell"/g) || []).length, 2);
  assert.match(source, /shellPrototype \? recordingDeleteCancel : recordingDeleteConfirm/);
  assert.match(source, /shellPrototype \? meetingDeleteCancel : meetingDeleteConfirm/);
});

test("planned rooms name their feature boundary at the surface that will own it", () => {
  const html = readFileSync(join(here, "index.html"), "utf8");
  for (const feature of ["D1", "D4", "D5", "B2", "B3", "B7", "A3", "A4", "A5", "E3", "P1", "P4", "P6"]) {
    assert.match(html, new RegExp(`data-feature=["'][^"']*\\b${feature}\\b`));
  }
  assert.match(html, /No account, calendar, cloud store, or destination is connected in this prototype\./);
  assert.match(html, /These controls are intentionally inactive\./);
});

test("the meeting context pane stores durable IDs, not projection handles", () => {
  const source = readFileSync(join(here, "main.js"), "utf8");
  const start = source.indexOf("function renderMeetingContextList()");
  const end = source.indexOf("function setError", start);
  const renderer = source.slice(start, end);

  assert.match(renderer, /dataset\.meetingId = row\.meetingId/);
  assert.doesNotMatch(renderer, /meetingHandle|row\.handle/);
  assert.match(source, /rowForMeetingId\(snapshot, meetingId\)/);
});

test("the shell exposes the complete synthetic capture journey without claiming a recording", () => {
  const html = readFileSync(join(here, "index.html"), "utf8");
  const source = readFileSync(join(here, "main.js"), "utf8");

  for (const step of ["Check", "Record", "Process", "Review"]) {
    assert.match(html, new RegExp(`<strong>${step}</strong>`));
  }
  for (const control of [
    "prototype-arming-ready",
    "prototype-recording-degrade",
    "prototype-processing-complete",
    "prototype-open-result",
  ]) {
    assert.match(html, new RegExp(`id=["']${control}["']`));
  }
  assert.match(html, /No microphone or system-audio device will open here\./);
  assert.match(html, /These example words were not recorded, transcribed, saved, or checked against audio\./);
  assert.match(source, /function prototypeCaptureSnapshot\(/);
  assert.match(source, /renderPrototypeCapture\("transcribing"\)/);
  assert.doesNotMatch(source, /Shell preview only\. The consent and retention review is complete/);
});

test("the shell quick control follows capture state without implying dormant detection", () => {
  const html = readFileSync(join(here, "index.html"), "utf8");
  const source = readFileSync(join(here, "main.js"), "utf8");

  for (const control of [
    "quick-control-trigger",
    "quick-control-popover",
    "quick-control-status-glyph",
    "quick-control-primary",
    "quick-control-secondary",
  ]) {
    assert.match(html, new RegExp(`id=["']${control}["']`));
  }
  assert.match(html, /Automatic meeting detection and an armed countdown remain dormant/);
  assert.match(source, /quickControlPresentation\(snapshot\)/);
  assert.match(source, /lastSnapshot\?\.capture === "recording"/);
  assert.match(source, /lastSnapshot\?\.capture === "transcript-ready"/);
});

test("the command launcher exposes stable Mac routes and state-aware capture actions", () => {
  const html = readFileSync(join(here, "index.html"), "utf8");
  const source = readFileSync(join(here, "main.js"), "utf8");

  for (const control of [
    "command-menu-trigger",
    "command-menu-backdrop",
    "command-menu-input",
    "command-menu-list",
    "command-menu-empty",
  ]) {
    assert.match(html, new RegExp(`id=["']${control}["']`));
  }
  assert.match(html, /Planned functions stay labelled\./);
  assert.match(html, /<kbd[^>]*>⌘K<\/kbd>/);
  assert.match(source, /commandMenuPresentation\(lastSnapshot\)/);
  assert.match(source, /event\.key === "ArrowDown"/);
  assert.match(source, /event\.key === "ArrowUp"/);
  assert.match(source, /event\.metaKey/);
  assert.doesNotMatch(source, /case ["']⌘/);
});

test("the Settings shell separates consequential local controls and chooses no retention default", () => {
  const html = readFileSync(join(here, "index.html"), "utf8");
  const source = readFileSync(join(here, "main.js"), "utf8");

  for (const panel of ["capture", "privacy", "voice", "shortcuts", "about"]) {
    assert.match(html, new RegExp(`data-settings-panel=["']${panel}["']`));
  }
  assert.match(html, /Audio and transcripts have separate lifetimes\./);
  assert.match(html, /No default is chosen\./);
  assert.match(html, /Existing recordings are deliberately unresolved\./);
  assert.match(html, /No account\. No upload\. Meeting data stays on this Mac\./);
  assert.match(html, /Automatic meeting detection<\/dt><dd><strong>Planned<\/strong>/);
  assert.doesNotMatch(html, /help improve transcription/i);

  const retentionStart = html.indexOf('id="settings-retention-preview"');
  const retentionEnd = html.indexOf("</fieldset>", retentionStart);
  const retention = html.slice(retentionStart, retentionEnd);
  assert.doesNotMatch(retention, /checked/);

  assert.match(source, /function selectSettingsPanel\(/);
  assert.match(source, /moveSettingsTab\(tab, 1\)/);
  assert.match(source, /This is not saved and does not change any existing recording\./);
});

test("the first-run shell exposes honest permission and recovery paths without inventing missing steps", () => {
  const html = readFileSync(join(here, "index.html"), "utf8");
  const source = readFileSync(join(here, "main.js"), "utf8");
  const firstRunStart = html.indexOf('id="first-run-screen"');
  const firstRunEnd = html.indexOf('id="idle-screen"', firstRunStart);
  const firstRun = html.slice(firstRunStart, firstRunEnd);

  for (const step of ["welcome", "request-microphone", "request-audio-capture", "enrol-voice", "ready"]) {
    assert.match(firstRun, new RegExp(`data-first-run-progress=["']${step}["']`));
  }
  for (const control of [
    "first-run-exit",
    "prototype-first-run-unavailable",
    "prototype-first-run-deny-microphone",
    "prototype-first-run-deny-system-audio",
    "settings-preview-first-run",
  ]) {
    assert.match(html, new RegExp(`id=["']${control}["']`));
  }
  assert.match(firstRun, /No macOS prompt opens and no permission is measured or changed\./);
  assert.match(firstRun, /No retention choice was made here\./);
  assert.doesNotMatch(firstRun, /data-step-panel=["']choose-retention["']/);
  assert.doesNotMatch(firstRun, /data-step-panel=["']offer-calendar["']/);
  assert.match(source, /function openPrototypeFirstRun\(/);
  assert.match(source, /firstRunDeniedPane\.textContent === "Microphone"/);
  assert.match(source, /Synthetic state: microphone allowed\./);
  assert.match(source, /Synthetic state: system audio allowed\./);
});

test("system-state review stays out of product navigation and names its synthetic boundary", () => {
  const html = readFileSync(join(here, "index.html"), "utf8");
  const source = readFileSync(join(here, "main.js"), "utf8");
  const productNavStart = html.indexOf('id="product-nav"');
  const productNavEnd = html.indexOf("</nav>", productNavStart);
  const productNav = html.slice(productNavStart, productNavEnd);

  for (const state of ["loading", "empty", "failure", "recovery", "repair"]) {
    assert.match(html, new RegExp(`data-state-preview=["']${state}["']`));
  }
  assert.match(html, /No installation, meeting, diagnostic, or recovery evidence was inspected\./);
  assert.match(html, /These are product states, not destinations\./);
  assert.doesNotMatch(productNav, /state-review|system states/i);
  assert.match(source, /function renderStateReview\(/);
  assert.match(source, /shellStatePresentation\(stateId\)/);
  assert.match(source, /stateReviewPrimary\.dataset\.action/);
});

test("Help stays outside product navigation and exposes honest diagnostics and update boundaries", () => {
  const html = readFileSync(join(here, "index.html"), "utf8");
  const source = readFileSync(join(here, "main.js"), "utf8");
  const productNavStart = html.indexOf('id="product-nav"');
  const productNavEnd = html.indexOf("</nav>", productNavStart);
  const productNav = html.slice(productNavStart, productNavEnd);

  for (const topic of ["overview", "recording", "permissions", "privacy", "diagnostics", "updates"]) {
    assert.match(html, new RegExp(`data-help-topic=["']${topic}["']`));
  }
  assert.doesNotMatch(productNav, /help|diagnostic/i);
  assert.match(html, /No permission, meeting, diagnostic file, installed version, or update service was inspected\./);
  assert.match(html, /id="settings-open-help"/);
  assert.match(html, /id="command-menu-trigger"[^>]*aria-label="Open commands"/);
  assert.match(source, /function openHelp\(/);
  assert.match(source, /helpTopicPresentation\(topicId\)/);
  assert.match(source, /activeSettingsTab = "privacy"/);
  assert.match(source, /activeSettingsTab = "about"/);
});

test("desktop behavior mirrors the native window lifecycle without inventing notifications", () => {
  const html = readFileSync(join(here, "index.html"), "utf8");
  const source = readFileSync(join(here, "main.js"), "utf8");
  const cargo = readFileSync(join(here, "../src-tauri/Cargo.toml"), "utf8");

  assert.match(html, /data-settings-tab="desktop"/);
  assert.match(html, /Closing the window hides it; quitting the app ends it\./);
  assert.match(html, /There is no background deletion daemon/);
  assert.match(html, /Yawn does not send system notifications today\./);
  assert.match(html, /No completion notification is implemented or specified\./);
  assert.match(html, /role="dialog" aria-modal="true" aria-labelledby="desktop-preview-title"/);
  assert.match(html, /id="desktop-preview-title" tabindex="-1"/);
  assert.match(source, /function openDesktopBehaviorPreview\(/);
  assert.match(source, /function closeDesktopBehaviorPreview\(/);
  assert.match(source, /node\.inert = true/);
  assert.match(source, /node\.inert = false/);
  assert.doesNotMatch(cargo, /tauri-plugin-notification/);
});

test("keyboard structure and visual state do not borrow the live-recording accent", () => {
  const html = readFileSync(join(here, "index.html"), "utf8");
  const source = readFileSync(join(here, "main.js"), "utf8");
  const styles = readFileSync(join(here, "styles.css"), "utf8");

  assert.match(html, /class="skip-link" href="#main-content"/);
  assert.match(html, /<main id="main-content" tabindex="-1">/);
  assert.match(html, /id="live-note-text"[^>]*aria-labelledby="live-note-title"/s);
  assert.equal((html.match(/role="tablist"/g) || []).length >= 5, true);
  assert.equal((html.match(/role="tabpanel"/g) || []).length >= 18, true);
  assert.match(source, /tab\.tabIndex = selected \? 0 : -1/);
  assert.match(source, /mainRegion\.focus\(\{ preventScroll: true \}\)/);
  assert.match(styles, /:where\(main, h1, h2\)\[tabindex="-1"\]:is\(:focus, :focus-visible\)[^{]*\{[^}]*outline: 0 !important;[^}]*box-shadow: none !important;/s);
  assert.match(source, /event\.key === "Home"/);
  assert.match(source, /const routeShortcut = \{ "1": "meetings", "2": "ask", "3": "actions", ",": "settings" \}/);
  assert.match(html, /<dt>Meetings<\/dt><dd><kbd>⌘1<\/kbd>/);
  assert.match(html, /<dt>Ask<\/dt><dd><kbd>⌘2<\/kbd>/);
  assert.match(html, /<dt>Actions<\/dt><dd><kbd>⌘3<\/kbd>/);
  assert.doesNotMatch(html, /<dt>Home<\/dt><dd><kbd>⌘1<\/kbd>/);
  assert.doesNotMatch(html, /<dt>Actions<\/dt><dd><kbd>⌘4<\/kbd>/);
  assert.doesNotMatch(styles, /animation\s*:/);
  for (const selector of [
    '.capture-progress li[aria-current="step"]',
    '.meeting-tabs button[aria-selected="true"]',
    '.settings-map button[aria-selected="true"]',
  ]) {
    const rule = styles.match(new RegExp(`${selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*\\{[^}]*\\}`))?.[0] || "";
    assert.doesNotMatch(rule, /var\(--accent\)/);
  }
});
