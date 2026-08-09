import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { adjacentPane, paneWindowTitle, validPane } from "./settings-state.mjs";

const root = new URL("./", import.meta.url);

test("pane order is stable and wraps for keyboard navigation", () => {
  assert.equal(validPane("missing"), "capture");
  assert.equal(adjacentPane("capture", "ArrowLeft"), "about");
  assert.equal(adjacentPane("about", "ArrowRight"), "capture");
  assert.equal(adjacentPane("voice", "Home"), "capture");
  assert.equal(adjacentPane("voice", "End"), "about");
  assert.equal(paneWindowTitle("voice"), "Voice profile — Yawn Settings");
});

test("reference markup keeps one complete Capture pane and seven stable tabs", async () => {
  const html = await readFile(new URL("settings.html", root), "utf8");
  assert.equal(html.match(/role="tab"/g)?.length, 7);
  assert.equal(html.match(/role="tabpanel"/g)?.length, 7);
  assert.match(html, /id="pane-capture"/);
  assert.match(html, /Devices/);
  assert.match(html, /Permissions/);
  assert.match(html, /Recording behavior/);
  assert.match(html, /do not affect Yawn/);
  assert.doesNotMatch(html, /Back to|Save settings|Apply/);
});

test("appearance and accessibility behavior are system-derived", async () => {
  const css = await readFile(new URL("styles.css", root), "utf8");
  const script = await readFile(new URL("settings.js", root), "utf8");
  assert.match(css, /prefers-color-scheme: dark/);
  assert.match(css, /prefers-reduced-motion: reduce/);
  assert.match(css, /prefers-contrast: more/);
  assert.match(css, /prefers-reduced-transparency: reduce/);
  assert.match(script, /localStorage\.setItem\(PANE_STORAGE_KEY, pane\)/);
  assert.match(script, /getCurrentWindow\(\)\.setTitle\(title\)/);
});
