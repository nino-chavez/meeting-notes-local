import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const html = readFileSync(new URL("./settings.html", import.meta.url), "utf8");
const css = readFileSync(new URL("./settings-window.css", import.meta.url), "utf8");
const script = readFileSync(new URL("./settings.js", import.meta.url), "utf8");
const production = readFileSync(new URL("./index.html", import.meta.url), "utf8");
const rust = readFileSync(new URL("../src-tauri/src/main.rs", import.meta.url), "utf8");
const mainCapability = JSON.parse(readFileSync(new URL("../src-tauri/capabilities/product/main.json", import.meta.url), "utf8"));
const settingsCapability = JSON.parse(readFileSync(new URL("../src-tauri/capabilities/product/settings-window.json", import.meta.url), "utf8"));

test("production imports the shared system in the owned order", () => {
  const foundation = production.indexOf("system/foundations.css");
  const components = production.indexOf("system/components.css");
  const patterns = production.indexOf("system/patterns.css");
  assert.ok(foundation >= 0 && foundation < components && components < patterns);
  assert.match(production, /data-production-system="desktop-v1"/);
  assert.match(production, /meeting-split-view ys-primary-split/);
  assert.match(production, /id="idle-screen"[^>]*ys-capture-utility|ys-capture-utility" id="idle-screen"/);
  assert.match(production, /id="processing-screen"[^>]*ys-capture-utility|ys-capture-utility" id="processing-screen"/);
});

test("native Settings exposes one complete measured Capture pane", () => {
  assert.equal((html.match(/data-pane="/g) || []).length, 7);
  assert.equal((html.match(/data-pane-panel="/g) || []).length, 7);
  for (const pane of ["capture", "privacy", "connections", "voice", "desktop", "shortcuts", "about"]) {
    assert.match(html, new RegExp(`id="settings-tab-${pane}"[\\s\\S]*?aria-controls="settings-pane-${pane}"`));
    assert.match(html, new RegExp(`id="settings-pane-${pane}"[\\s\\S]*?aria-labelledby="settings-tab-${pane}"`));
  }
  assert.match(html, /id="capture-permissions-title"/);
  assert.match(html, /id="microphone-status"/);
  assert.match(html, /id="system-audio-status"/);
  assert.match(html, /id="refresh-permissions"/);
  assert.equal((html.match(/<select class="ys-select" disabled/g) || []).length, 2);
  assert.match(script, /Settings did not ask/);
  assert.doesNotMatch(html, /data-setting=/);
  assert.match(script, /invoke\?\.\("first_run_permissions"\)/);
  assert.doesNotMatch(script, /first_run_request_/);
});

test("Capture uses compact Settings geometry instead of a scrollable report", () => {
  assert.match(css, /grid-template-rows: 4\.5rem minmax\(0, 1fr\)/);
  assert.match(css, /inline-size: min\(38\.5rem, 100%\)/);
  assert.match(css, /\.ys-settings-pane \{[\s\S]*?gap: var\(--ys-space-4\);[\s\S]*?padding: var\(--ys-space-5\) 0 var\(--ys-space-4\);[\s\S]*?overflow: hidden;/);
  assert.match(css, /\.settings-row \{[\s\S]*?min-block-size: 2\.8rem;[\s\S]*?padding: var\(--ys-space-2\) var\(--ys-space-4\);/);
  assert.match(css, /\.settings-consent \{[\s\S]*?min-block-size: 2\.8rem;[\s\S]*?padding: var\(--ys-space-3\) var\(--ys-space-4\);/);
  assert.match(css, /\.settings-group__rows \{\s*border-block:/);
  assert.doesNotMatch(css, /\.settings-group(?:__rows)? \{[\s\S]*?border-radius:/);
  assert.doesNotMatch(css, /box-shadow:/);

  assert.equal((html.match(/class="settings-group"/g) || []).length, 2);
  assert.equal((html.match(/class="settings-row"/g) || []).length, 4);
  assert.doesNotMatch(html, /ys-settings-section|ys-inline-notice/);
  assert.doesNotMatch(html, /Refresh status|Permissions measured on this Mac/);

  // Scrolling is an accessibility fallback for magnified or constrained
  // webviews, not the standard 720 x 560 page composition.
  assert.match(css, /@media \(max-width: 40rem\), \(max-height: 30rem\)[\s\S]*?overflow-y: auto;/);
});

test("Settings has a narrow native capability and main owns the opener", () => {
  assert.deepEqual(settingsCapability.windows, ["settings"]);
  assert.deepEqual(settingsCapability.permissions, [
    "allow-first-run-permissions",
    "allow-get-desktop-layout",
    "allow-set-desktop-layout",
    "core:window:allow-set-title",
  ]);
  assert.ok(mainCapability.permissions.includes("allow-open-settings-window"));
  assert.ok(mainCapability.permissions.includes("core:window:allow-start-dragging"));
  assert.match(rust, /accelerator\("CmdOrCtrl\+,"\)/);
  assert.match(rust, /window\.label\(\) == ACTIVE_WINDOW_LABEL/);
  assert.match(rust, /SETTINGS_WINDOW_LABEL/);
  assert.match(rust, /\.inner_size\(720\.0, 560\.0\)/);
  assert.match(rust, /\.min_inner_size\(720\.0, 560\.0\)/);
  assert.match(rust, /\.max_inner_size\(720\.0, 560\.0\)/);
  assert.match(rust, /\.resizable\(false\)/);
  assert.match(rust, /\.minimizable\(false\)/);
  assert.match(rust, /\.maximizable\(false\)/);
  assert.match(rust, /\.closable\(true\)/);
  assert.match(rust, /window\.set_focus\(\)\?/);
});

test("Desktop behavior owns one persisted Meetings layout preference", () => {
  for (const value of ["automatic", "focus", "library"]) {
    assert.match(html, new RegExp(`name="desktop-layout" value="${value}"`));
  }
  assert.match(html, /Yawn collapses panes before the meeting becomes too narrow to read/);
  assert.match(script, /invoke\?\.\("get_desktop_layout"\)/);
  assert.match(script, /invoke\?\.\("set_desktop_layout", \{ layout: requested \}\)/);
  assert.match(script, /yawn:desktop-layout-changed/);
  assert.match(css, /\.layout-choice\s*\{/);
  assert.match(rust, /const LAYOUT_MENU_ID: &str = "view-layout"/);
  assert.match(rust, /CheckMenuItemBuilder::with_id\(/);
  assert.match(rust, /SubmenuBuilder::with_id\(app, LAYOUT_MENU_ID, "Layout"\)/);
  assert.match(rust, /durable_replace\(&path, &bytes\)/);
});

test("Settings restores pane, title, and keyboard focus without touching the main window", () => {
  assert.match(script, /const storageKey = "yawn-settings:last-pane"/);
  assert.match(script, /localStorage\.setItem\(storageKey, pane\)/);
  assert.match(script, /localStorage\.getItem\(storageKey\)/);
  assert.match(script, /panel\.hidden = panel\.dataset\.panePanel !== pane/);
  assert.match(script, /if \(selected && focus\) tab\.focus\(\)/);
  assert.match(script, /\["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"\]/);
  assert.match(script, /getCurrentWindow\(\)\.setTitle\(title\)/);
  assert.doesNotMatch(script, /getByLabel\(["']main|navigate|location\.(?:href|assign|replace)/);
});

test("capture completion hands the retained meeting to its Transcript tab", () => {
  const main = readFileSync(new URL("./main.js", import.meta.url), "utf8");
  assert.match(main, /case "transcript-ready":[\s\S]*handoffCompletedCapture\(snapshot\)/);
  assert.match(main, /openMeetingByIdFresh\(meetingId\)/);
  assert.match(main, /selectRetainedMeetingTab\("transcript"/);
});
