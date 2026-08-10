import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const html = readFileSync(new URL("./settings.html", import.meta.url), "utf8");
const css = readFileSync(new URL("./settings-window.css", import.meta.url), "utf8");
const script = readFileSync(new URL("./settings.js", import.meta.url), "utf8");
const voiceWorkflow = readFileSync(new URL("./voice-profile-workflow.mjs", import.meta.url), "utf8");
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
  const capturePane = html.slice(
    html.indexOf('id="settings-pane-capture"'),
    html.indexOf('id="settings-pane-privacy"'),
  );
  assert.match(css, /grid-template-rows: 4\.5rem minmax\(0, 1fr\)/);
  assert.match(css, /inline-size: min\(38\.5rem, 100%\)/);
  assert.match(css, /\.ys-settings-pane \{[\s\S]*?gap: var\(--ys-space-4\);[\s\S]*?padding: var\(--ys-space-5\) 0 var\(--ys-space-4\);[\s\S]*?overflow: hidden;/);
  assert.match(css, /\.settings-row \{[\s\S]*?min-block-size: 2\.8rem;[\s\S]*?padding: var\(--ys-space-2\) var\(--ys-space-4\);/);
  assert.match(css, /\.settings-consent \{[\s\S]*?min-block-size: 2\.8rem;[\s\S]*?padding: var\(--ys-space-3\) var\(--ys-space-4\);/);
  assert.match(css, /\.settings-group__rows \{\s*border-block:/);
  assert.doesNotMatch(css, /\.settings-group \{[^}]*border-radius:/);
  assert.doesNotMatch(css, /\.settings-group__rows \{[^}]*border-radius:/);
  assert.doesNotMatch(css, /box-shadow:/);

  assert.equal((html.match(/class="settings-group"/g) || []).length, 2);
  assert.equal((html.match(/class="settings-row"/g) || []).length, 4);
  assert.doesNotMatch(capturePane, /ys-settings-section|ys-inline-notice/);
  assert.doesNotMatch(capturePane, /Refresh status|Permissions measured on this Mac/);

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
    "allow-preview-profile-snapshot",
    "allow-preview-enrollment-surface",
    "allow-preview-enrollment-start-sitting",
    "allow-preview-enrollment-stop-sitting",
    "allow-preview-enrollment-operating-points",
    "allow-preview-enrollment-build-profile",
    "allow-preview-profile-preserve-legacy",
    "allow-preview-profile-reset",
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

test("Voice owns the established local profile lifecycle in native Settings", () => {
  for (const id of [
    "profile-lede",
    "profile-status-title",
    "profile-status-copy",
    "profile-setup",
    "sitting-form",
    "sitting-start",
    "sitting-stop",
    "profile-operating-points",
    "operating-points-rows",
    "operating-points-build",
    "profile-reset-confirmation",
    "profile-reset-confirm",
  ]) {
    assert.match(html, new RegExp(`id="${id}"`));
  }
  assert.match(html, /Record two short sessions of you talking, at least an hour apart/);
  assert.match(html, /it does not name speakers/);
  assert.match(html, /Meetings, transcripts, notes, evidence, and meeting audio remain/);
  assert.match(html, /logical app-storage deletion, not forensic erasure/);
  assert.match(html, /id="operating-points-rows" disabled/);
  assert.match(html, /id="operating-points-build" data-variant="primary" type="submit" disabled/);
  assert.doesNotMatch(html, /existing measured voice-profile workflow remains in the main app/);

  assert.match(script, /import \{ createVoiceProfileController \} from "\.\/voice-profile-workflow\.mjs"/);
  assert.match(script, /isActive: \(\) => activePane === "voice"/);
  assert.match(script, /window\.addEventListener\("storage"/);
  assert.match(css, /\.voice-profile-pane \{[\s\S]*?overflow-y: auto;/);
  for (const command of [
    "preview_profile_snapshot",
    "preview_enrollment_surface",
    "preview_enrollment_start_sitting",
    "preview_enrollment_stop_sitting",
    "preview_enrollment_operating_points",
    "preview_enrollment_build_profile",
    "preview_profile_preserve_legacy",
    "preview_profile_reset",
  ]) {
    assert.match(voiceWorkflow, new RegExp(`"${command}"`));
  }
  assert.match(voiceWorkflow, /choicesSha256: selection\.choicesSha256/);
  assert.match(voiceWorkflow, /className = "ys-radio-choice voice-profile-choice"/);
  assert.doesNotMatch(voiceWorkflow, /preview_profile_enroll/);
  assert.doesNotMatch(voiceWorkflow, /input\.checked = true/);
  assert.doesNotMatch(settingsCapability.permissions.join("\n"), /core:fs|shell|dialog/);
});

test("Shortcuts and About list only the installed app's current boundaries", () => {
  const shortcutsPane = html.slice(
    html.indexOf('id="settings-pane-shortcuts"'),
    html.indexOf('id="settings-pane-about"'),
  );
  const aboutPane = html.slice(html.indexOf('id="settings-pane-about"'));
  const main = readFileSync(new URL("./main.js", import.meta.url), "utf8");

  assert.match(shortcutsPane, /id="shortcuts-navigation-title"/);
  assert.match(shortcutsPane, /⌘1/);
  assert.match(shortcutsPane, /⌘2/);
  assert.match(shortcutsPane, /⌘,/);
  assert.match(shortcutsPane, /Actions is not listed because cross-meeting action follow-through is not available/);
  assert.doesNotMatch(shortcutsPane, /⌘K|⌘3/);
  assert.match(main, /"1": "meetings"/);
  assert.match(main, /"2": "search"/);
  assert.match(main, /",": "settings"/);
  assert.match(script, /\["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"\]/);
  assert.match(css, /\.settings-shortcut-key,/);

  assert.match(aboutPane, /Shown in Yawn → About Yawn from the native app menu/);
  assert.match(aboutPane, /No sign-in or cloud identity is active/);
  assert.match(aboutPane, /Stored on this Mac\. No upload path is active/);
  assert.match(aboutPane, /Yawn does not create notes or action items/);
  assert.doesNotMatch(aboutPane, /Click-through prototype|Uncommitted interface shell/);
  assert.match(rust, /\.about\(None\)/);
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
  const main = readFileSync(new URL("./main.js", import.meta.url), "utf8");
  assert.match(main, /localStorage\.setItem\("yawn-settings:last-pane", requestedPane\)/);
});

test("capture completion hands the retained meeting to its Transcript tab", () => {
  const main = readFileSync(new URL("./main.js", import.meta.url), "utf8");
  assert.match(main, /case "transcript-ready":[\s\S]*handoffCompletedCapture\(snapshot\)/);
  assert.match(main, /openMeetingByIdFresh\(meetingId\)/);
  assert.match(main, /selectRetainedMeetingTab\("transcript"/);
});
