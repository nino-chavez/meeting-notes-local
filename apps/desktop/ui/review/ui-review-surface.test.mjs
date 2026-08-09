import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const main = readFileSync(new URL("../main.js", import.meta.url), "utf8");
const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const css = readFileSync(new URL("../native-calibration.css", import.meta.url), "utf8");
const config = JSON.parse(readFileSync(new URL("../../src-tauri/tauri.ui-review.conf.json", import.meta.url), "utf8"));
const capability = JSON.parse(readFileSync(new URL("../../src-tauri/capabilities/review/ui-review.json", import.meta.url), "utf8"));
const rust = readFileSync(new URL("../../src-tauri/src/ui_review_surface.rs", import.meta.url), "utf8");

test("installed synthetic review is separately identified and backend-free", () => {
  assert.equal(config.identifier, "com.ninochavez.local-meeting-notes.ui-review");
  assert.equal(config.app.windows[0].url, "index.html?review=synthetic");
  assert.equal(config.bundle.resources, null);
  assert.deepEqual(config.app.security.capabilities, ["ui-review-window"]);
  assert.deepEqual(capability.permissions, ["core:window:allow-start-dragging"]);
  assert.doesNotMatch(JSON.stringify(capability.permissions), /capture|meeting|storage|permission-request|filesystem|shell|process|dialog/);
  assert.doesNotMatch(rust, /invoke_handler|initialize_application|TrayIcon|first_run|start_meeting/);
});

test("review query disables product invocation and leaves a persistent warning", () => {
  assert.match(main, /rawInvoke && shellParams\.get\("review"\) === "synthetic"/);
  assert.match(main, /const invoke = installedUiReview \? null : rawInvoke/);
  assert.match(main, /dataset\.syntheticReview = "true"/);
  assert.match(main, /installedUiReview \? 18 : startedAt/);
  assert.match(html, /SYNTHETIC UI REVIEW · no device opened · no meeting data read/);
  assert.match(css, /html\[data-synthetic-review="true"\] \.ui-review-watermark/);
});

test("review geometry matches the production acceptance sizes", () => {
  const window = config.app.windows[0];
  assert.equal(window.width, 1120);
  assert.equal(window.height, 720);
  assert.equal(window.minWidth, 720);
  assert.equal(window.minHeight, 560);
  assert.equal(window.resizable, true);
});
