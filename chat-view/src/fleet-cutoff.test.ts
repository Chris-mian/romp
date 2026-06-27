// Fleet recency-cutoff slider (the user 2026-06-27): a logarithmic slider (1 minute … 1 month) hides
// sessions whose freshest activity is older than the window. Source pins (fleet.ts runs as a module, no
// jsdom harness) + a behavioral check of the log mapping.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "fleet.ts"), "utf8");

test("the cutoff is a logarithmic 1-minute … 1-month map of the 0..1000 slider", () => {
  assert.match(SRC, /const CUT_MIN = 60, CUT_MAX = 30 \* 86400;/);
  assert.match(SRC, /function cutoffSecs\(\): number \{ return CUT_MIN \* Math\.pow\(CUT_MAX \/ CUT_MIN, cutoffPos\(\) \/ 1000\); \}/);
  // replicate the formula to confirm the endpoints + log spacing
  const CUT_MIN = 60, CUT_MAX = 30 * 86400;
  const secs = (pos: number) => CUT_MIN * Math.pow(CUT_MAX / CUT_MIN, pos / 1000);
  assert.equal(Math.round(secs(0)), 60, "pos 0 → 1 minute");
  assert.equal(Math.round(secs(1000)), CUT_MAX, "pos 1000 → 1 month");
  // log-uniform: equal slider steps cover a constant RATIO, so the midpoint is the geometric mean
  assert.ok(Math.abs(secs(500) - Math.sqrt(CUT_MIN * CUT_MAX)) < 1, "midpoint is the geometric mean (log scale)");
});

test("the slider persists its position and defaults to the most-inclusive end (1 month)", () => {
  assert.match(SRC, /const CUTOFF_KEY = "romp:fleetCutoffPos";/);
  assert.match(SRC, /Number\.isFinite\(v\) \? Math\.max\(0, Math\.min\(1000, v\)\) : 1000/, "default pos = 1000 (1 month)");
  assert.match(SRC, /localStorage\.setItem\(CUTOFF_KEY, String\(p\)\)/);
});

test("render() skips a session whose freshest activity is older than the cutoff", () => {
  assert.match(SRC, /const cutoff = cutoffSecs\(\);/);
  assert.match(SRC, /const freshest = Math\.max\(s\.ledger\?\.current\?\.t \|\| 0, \.\.\.tree\.map\(nodeRecency\)\);/);
  assert.match(SRC, /if \(freshest && \(now - freshest\) > cutoff\) continue;/);
});

test("the slider + 'Show completed' mount as ONE horizontal row (the user 2026-06-27)", () => {
  // a single control strip, not two stacked chips
  assert.match(SRC, /function mountControls\(\)/);
  assert.match(SRC, /row\.id = "fl-controls";/);
  // the row carries BOTH the recency slider and the Show-completed checkbox
  assert.match(SRC, /sl\.type = "range"; sl\.min = "0"; sl\.max = "1000"/);
  assert.match(SRC, /lab\.textContent = "≤ " \+ fmtAge\(cutoffSecs\(\)\)/);
  assert.match(SRC, /sl\.addEventListener\("input", \(\) => \{ setCutoffPos\(parseInt\(sl\.value, 10\)\); paint\(\); render\(\); \}\)/);
  assert.match(SRC, /lbl\.appendChild\(document\.createTextNode\("Show completed"\)\)/);
  assert.match(SRC, /row\.appendChild\(lab\); row\.appendChild\(sl\);/);
  assert.match(SRC, /row\.appendChild\(lbl\);/);
  // the old two-chip mounts are gone
  assert.doesNotMatch(SRC, /function mountChip\(\)/);
  assert.doesNotMatch(SRC, /function mountCutoff\(\)/);
  assert.match(SRC, /^mountControls\(\);$/m, "mounted at startup");
});
