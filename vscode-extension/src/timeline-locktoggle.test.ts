// Lock-to-now moved from a toolbar CHECKBOX to a padlock ICON at the now-edge (the user 2026-06-26): drawn
// at the bottom of the rightmost tick, accent-blue when locked / gray when unlocked, click toggles. It gets
// a reserved label slot so the nearest time-axis clock can't render into it. Source pins (no jsdom for the
// SVG renderer): they fail if the checkbox comes back or the now-edge slot/colors regress.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js"), "utf8");

test("the toolbar lock CHECKBOX is gone (no _lockBox/_lockIcon DOM)", () => {
  assert.doesNotMatch(SRC, /this\._lockBox = /);
  assert.doesNotMatch(SRC, /this\._lockIcon = /);
  assert.doesNotMatch(SRC, /lockWrap/);
});

test("draw() reserves a now-edge slot then draws the lock toggle there", () => {
  assert.match(SRC, /const lockCx = x\(t1\), lockHalf = 9;/);
  assert.match(SRC, /placedLabels\.push\(\[lockCx - lockHalf, lockCx \+ lockHalf\]\);/);
  assert.match(SRC, /this\._drawLockToggle\(svg, lockCx, axisY\);/);
});

test("_drawLockToggle is accent-blue when locked and gray when unlocked", () => {
  assert.match(SRC, /_drawLockToggle\(svg, cx, axisY\)/);
  assert.match(SRC, /const color = on \? ACCENT : PAL\(\)\.faintFg;/);   // dark: ROMP_BLUE / #6e7681, via the theme palette
  // seated shackle when locked, swung-out when unlocked (reuses the toolbar lock geometry)
  assert.match(SRC, /on \? 'M4\.8 6\.2 V4\.4 a2\.2 2\.2 0 0 1 4\.4 0 V6\.2'/);
});

test("the padlock toggles on POINTERDOWN (single press even when the pane wasn't focused)", () => {
  // pointerdown, not click: an unfocused iframe spends the first CLICK focusing, but the pointerdown fires
  assert.match(SRC, /g\.addEventListener\('pointerdown', \(ev\) => \{/);
  assert.match(SRC, /const next = !this\._lockNow;\s*this\._setLock\(next\);\s*if \(next\) this\._jumpToNow\(\);/);
});

test("the padlock tooltip uses the romp tip (instant + freezes redraws), not a native <title>", () => {
  // native <title> never appeared — the live edge rebuilds the SVG and resets the browser hover timer
  const fn = SRC.slice(SRC.indexOf("_drawLockToggle(svg, cx, axisY)"), SRC.indexOf("_showLoader(show)"));
  assert.ok(fn.length > 0, "found the _drawLockToggle body");
  assert.doesNotMatch(fn, /el\('title'/, "the lock no longer uses a native <title>");
  assert.match(fn, /hit\.addEventListener\('mouseenter', \(e\) => this\.showTip\(tipHtml, e\)\);/);
  assert.match(fn, /hit\.addEventListener\('mouseleave', \(\) => this\.hideTip\(\)\);/);
  assert.match(fn, /Lock the timeline to the present/);
});
