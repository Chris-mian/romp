// Fleet recency-cutoff slider (the user 2026-06-27): a logarithmic slider (1 minute … 1 month) hides
// sessions whose freshest activity is older than the window. Source pins (fleet.ts runs as a module, no
// jsdom harness) + a behavioral check of the log mapping.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "fleet.ts"), "utf8");

test("the cutoff is a logarithmic 1-minute … OLDEST-IN-FLEET map of the 0..1000 slider (adaptive max, the user 2026-06-27)", () => {
  assert.match(SRC, /const CUT_MIN = 60, CUT_MAX = 30 \* 86400;/);   // CUT_MIN = floor; CUT_MAX = fallback before the first render
  // the right end is the adaptive `fleetMaxAge`, not a fixed CUT_MAX, so the travel always spans the real fleet
  assert.match(SRC, /let fleetMaxAge = CUT_MAX;/);
  assert.match(SRC, /function cutoffSecs\(\): number \{ return CUT_MIN \* Math\.pow\(Math\.max\(fleetMaxAge, CUT_MIN \* 2\) \/ CUT_MIN, cutoffPos\(\) \/ 1000\); \}/);
  // replicate the formula: pos 0 → 1 minute (floor); pos 1000 → the adaptive max; midpoint = geometric mean
  const CUT_MIN = 60;
  const secs = (pos: number, maxAge: number) => CUT_MIN * Math.pow(Math.max(maxAge, CUT_MIN * 2) / CUT_MIN, pos / 1000);
  const MAX = 36 * 3600;   // a fleet that spans ~36h
  assert.equal(Math.round(secs(0, MAX)), 60, "pos 0 → 1 minute floor");
  assert.equal(Math.round(secs(1000, MAX)), MAX, "pos 1000 → the oldest in-fleet age (everything shows)");
  assert.ok(Math.abs(secs(500, MAX) - Math.sqrt(CUT_MIN * MAX)) < 1, "midpoint is the geometric mean (log scale)");
});

test("render() computes the adaptive max from the oldest session BEFORE filtering, and refreshes the label", () => {
  // pass 1: the oldest in-fleet freshest age becomes the slider's right end
  assert.match(SRC, /let maxAge = CUT_MIN \* 2;/);
  assert.match(SRC, /for \(const s of sessions\) \{ const f = sessionFreshest\(s\); if \(f\) maxAge = Math\.max\(maxAge, now - f\); \}/);
  assert.match(SRC, /fleetMaxAge = maxAge;/);
  assert.match(SRC, /refreshCutoffLabel\?\.\(\);/);
  // the label painter is registered so render() can refresh "≤ <age>" as the fleet (and thus the max) shifts
  assert.match(SRC, /refreshCutoffLabel = paint;/);
});

test("the slider persists its position and defaults to the most-inclusive end (show everything)", () => {
  assert.match(SRC, /const CUTOFF_KEY = "romp:fleetCutoffPos";/);
  assert.match(SRC, /Number\.isFinite\(v\) \? Math\.max\(0, Math\.min\(1000, v\)\) : 1000/, "default pos = 1000 (far right = show all)");
  assert.match(SRC, /localStorage\.setItem\(CUTOFF_KEY, String\(p\)\)/);
});

test("render() skips a session whose freshest activity is older than the cutoff", () => {
  assert.match(SRC, /const cutoff = cutoffSecs\(\);/);
  assert.match(SRC, /const freshest = Math\.max\(s\.ledger\?\.current\?\.t \|\| 0, \.\.\.visibleRoots\.map\(nodeRecency\)\);/);
  assert.match(SRC, /if \(freshest && \(now - freshest\) > cutoff\) continue;/);
});

test("the slider + 'Show completed' mount in the docked bar's RIGHT cluster (the user 2026-06-29)", () => {
  // the recency slider + Show-completed sit together in the docked footer's right cluster
  assert.match(SRC, /function mountControls\(\)/);
  assert.match(SRC, /const right = el\("div", "fl-foot-right"\);/);
  assert.match(SRC, /sl\.type = "range"; sl\.min = "0"; sl\.max = "1000"/);
  assert.match(SRC, /lab\.textContent = "≤ " \+ fmtAge\(cutoffSecs\(\)\)/);
  // REVERSED direction + blue fill on the RIGHT (the user 2026-06-29): a horizontal FLIP (scaleX(-1)) of the
  // native slider, value mapped directly to cutoffPos. So dragging RIGHT tightens the window (more-recent only)
  // AND the accent fill (which a native range paints on the low side) lands on the right.
  assert.match(SRC, /sl\.value = String\(cutoffPos\(\)\)/);
  assert.match(SRC, /transform:scaleX\(-1\)/);
  assert.match(SRC, /sl\.addEventListener\("input", \(\) => \{ setCutoffPos\(parseInt\(sl\.value, 10\)\); paint\(\); render\(\); \}\)/);
  assert.match(SRC, /lbl\.appendChild\(document\.createTextNode\("Show completed"\)\)/);
  assert.match(SRC, /right\.appendChild\(lab\); right\.appendChild\(sl\);/);
  assert.match(SRC, /right\.appendChild\(lbl\);/);
  // it's a docked bar now, not a floating "fl-controls" row
  assert.doesNotMatch(SRC, /row\.id = "fl-controls";/);
  assert.doesNotMatch(SRC, /function mountChip\(\)/);
  assert.doesNotMatch(SRC, /function mountCutoff\(\)/);
  assert.match(SRC, /^mountControls\(\);$/m, "mounted at startup");
});
