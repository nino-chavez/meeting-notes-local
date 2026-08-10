import test from "node:test";
import assert from "node:assert/strict";

import {
  DESKTOP_LAYOUTS,
  effectiveDesktopLayout,
  normalizeDesktopLayout,
  opensMeetingBesideList,
} from "./layout-preference.mjs";

test("desktop layout preference has one closed persisted vocabulary", () => {
  assert.deepEqual(DESKTOP_LAYOUTS, ["automatic", "focus", "library"]);
  for (const layout of DESKTOP_LAYOUTS) assert.equal(normalizeDesktopLayout(layout), layout);
  assert.equal(normalizeDesktopLayout("unknown"), "automatic");
  assert.equal(normalizeDesktopLayout(null), "automatic");
});

test("automatic opens list and record only when the record stays usable", () => {
  assert.equal(effectiveDesktopLayout("automatic", 960), "split");
  assert.equal(effectiveDesktopLayout("automatic", 799), "focus");
  assert.equal(opensMeetingBesideList("automatic", 960), true);
  assert.equal(opensMeetingBesideList("automatic", 720), false);
});

test("focus stays single pane and library yields before squeezing the record", () => {
  assert.equal(effectiveDesktopLayout("focus", 1400), "focus");
  assert.equal(effectiveDesktopLayout("library", 1200), "library");
  assert.equal(effectiveDesktopLayout("library", 899), "split");
  assert.equal(opensMeetingBesideList("focus", 1400), false);
  assert.equal(opensMeetingBesideList("library", 720), true);
});
