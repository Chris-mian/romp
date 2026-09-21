// T235's display half: the rail's spend hover reads "1 month" as a ROLLING 30 days (a superset window
// can never read lower than "1 week" again) with "this month" — the calendar figure the bill accrues —
// directly under it; a ledger younger than 30 days says "since <date>"; and a host on an older build
// (calendar `month`, no monthToDate) files its figure under "this month" and is LEFT OUT of the rolling
// row, which then says how many machines it does not count. The strip's cell title carries both rows.
// The kernel half (window math, budget attachment) executes in tests/test_spend_windows.py.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const KERNEL = fs.readFileSync(path.resolve(process.cwd(), "..", "kernel", "kernel.py"), "utf8");
const STRIP = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "strip.ts"), "utf8");

test("the hover renders both rows: rolling '1 month' and calendar 'this month'", () => {
  assert.match(KERNEL, /var SPEND_WINS=\[\['hour','1 hour'\],\['day','1 day'\],\['week','1 week'\],\['month','1 month'\],\['monthToDate','this month'\]\];/);
  assert.match(KERNEL, /"month": rolling_month,\s*\n\s*"monthToDate": _sum\(v for k, v in days\.items\(\) if isinstance\(k, str\) and k\.startswith\(month\)\)/,
    "the kernel ships both keys — rolling under the old name, the bill figure under its own");
  assert.match(KERNEL, /win\["monthToDate" if k == "month" else k\]\["budget"\] = v/, "the bill-cycle budget rides the bill figure, never the rolling window");
});

test("the version-skew arm: an older host's calendar month is filed honestly and never mixed into the rolling sum", () => {
  assert.match(KERNEL, /var legacy=\(sp\.month&&typeof sp\.month\.usd==='number'&&!sp\.monthToDate\);/);
  assert.match(KERNEL, /if\(legacy&&k==='monthToDate'\)k='month';else if\(legacy&&k==='month'\)return;/,
    "calendar → 'this month'; its rolling share is left out rather than summed as a different window");
  assert.match(KERNEL, /' \\u00b7 '\+legacyN\+' machine'\+\(legacyN>1\?'s':''\)\+' not counted \(older build\)'/,
    "…and the rolling row says how many it does not count");
});

test("a ledger younger than 30 days marks the rolling row with its reach", () => {
  assert.match(KERNEL, /win\["month"\]\["since"\] = oldest/, "the kernel states how far back the ledger truly goes");
  assert.match(KERNEL, /if\(k==='month'&&v\.since\)lab\+=' \\u00b7 complete since '\+esc\(v\.since\);/, "…and the hover shows it on the row");
  // T235b: folded to the YOUNGEST ledger — the summed window is complete only from there (MIN overstated coverage)
  assert.match(KERNEL, /if\(v\.since&&\(!t\.since\|\|v\.since>t\.since\)\)t\.since=v\.since;/, "across hosts, the youngest reach bounds the sum");
});

test("the strip's cell title carries both rows too", () => {
  assert.match(STRIP, /\["month", "1 month"\], \["monthToDate", "this month"\]\] as const/);
});

test("T235b: the collapsed API cell follows the hover's skew rule, and the since caveat folds to the youngest ledger", () => {
  const cell = KERNEL.slice(KERNEL.indexOf("function apiCellHTML"), KERNEL.indexOf("// The collapsed rail is the AGGREGATE story"));
  assert.match(cell, /_spendLegacyMonth/, "a legacy host's calendar month is never folded into the rolling segment");
  assert.match(cell, /var monthCav=legacyN>0;/, "…and the month segment wears the ⚠ glyph — the words live on the rich tip's rolling row, the ONE hover surface");
  assert.match(KERNEL, /if\(v\.since&&\(!t\.since\|\|v\.since>t\.since\)\)t\.since=v\.since;/, "MAX — complete only from the youngest reach");
  assert.match(KERNEL, /' \\u00b7 complete since '\+esc\(v\.since\)/);
});
