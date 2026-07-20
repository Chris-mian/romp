// Sub-minute ages read "<1m ago" (the user 2026-07-20): after the optimistic Working flip stamps a card's
// sort time to "now", its age label showed a counting "0s ago" — churn without information. Everything
// under a minute now wears the same "<1m ago"; minutes and up are unchanged. Pin + executed replica.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");

test("relAge renders every sub-minute age as \"<1m ago\", never a seconds count", () => {
  assert.match(FEED, /if \(s < 60\) return `<1m ago`;/);
  assert.doesNotMatch(FEED, /\$\{Math\.round\(s\)\}s ago/, "the counting seconds label is gone");
});

test("executed replica: 0s and 59s collapse to <1m ago; 60s+ keep the minute/hour/day ladder", () => {
  const relAge = (sec: number): string => {
    const s = Math.max(0, sec);
    if (s < 60) return `<1m ago`;
    if (s < 3600) return `${Math.round(s / 60)}m ago`;
    if (s < 86400) return `${Math.round(s / 3600)}h ago`;
    return `${Math.round(s / 86400)}d ago`;
  };
  assert.equal(relAge(0), "<1m ago");
  assert.equal(relAge(14), "<1m ago");
  assert.equal(relAge(59), "<1m ago");
  assert.equal(relAge(-5), "<1m ago");   // clock skew clamps to 0 → still the freshest label
  assert.equal(relAge(60), "1m ago");
  assert.equal(relAge(3599), "60m ago");
  assert.equal(relAge(7200), "2h ago");
});
