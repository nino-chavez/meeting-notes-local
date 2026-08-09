import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const html = readFileSync(new URL("./settings.html", import.meta.url), "utf8");
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
  assert.match(script, /Settings did not ask/);
  assert.doesNotMatch(html, /data-setting=/);
  assert.match(script, /invoke\?\.\("first_run_permissions"\)/);
  assert.doesNotMatch(script, /first_run_request_/);
});

test("Settings has a narrow native capability and main owns the opener", () => {
  assert.deepEqual(settingsCapability.windows, ["settings"]);
  assert.deepEqual(settingsCapability.permissions, [
    "allow-first-run-permissions",
    "core:window:allow-set-title",
  ]);
  assert.ok(mainCapability.permissions.includes("allow-open-settings-window"));
  assert.ok(mainCapability.permissions.includes("core:window:allow-start-dragging"));
  assert.match(rust, /accelerator\("CmdOrCtrl\+,"\)/);
  assert.match(rust, /window\.label\(\) == ACTIVE_WINDOW_LABEL/);
  assert.match(rust, /SETTINGS_WINDOW_LABEL/);
  assert.match(rust, /\.minimizable\(false\)/);
  assert.match(rust, /\.maximizable\(false\)/);
});

test("capture completion hands the retained meeting to its Transcript tab", () => {
  const main = readFileSync(new URL("./main.js", import.meta.url), "utf8");
  assert.match(main, /case "transcript-ready":[\s\S]*handoffCompletedCapture\(snapshot\)/);
  assert.match(main, /openMeetingByIdFresh\(meetingId\)/);
  assert.match(main, /selectRetainedMeetingTab\("transcript"/);
});
