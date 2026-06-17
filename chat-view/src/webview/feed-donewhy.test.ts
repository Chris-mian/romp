// The done page (the user 2026-06-17): a COMPLETED card surfaces the planner's one-sentence "why done"
// INLINE under the title — the mirror of blockWhy on a blocked card — instead of only revealing it on
// hover in the modal. The kernel computes the card-level doneWhy; the card renders it like blockReason.
// No jsdom harness for the feed, so — like the other feed-*.test.ts — pin it at the source level.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "feed.ts"), "utf8");

test("AskItem carries a doneWhy field", () => {
  assert.match(FEED, /doneWhy\?: string;\s+\/\/ planner's one-sentence "why done"/);
});

test("the card builds a fask-donewhy element next to fask-blockwhy, styled the same", () => {
  assert.match(FEED, /const doneReason = el\("div", "fask-donewhy"\)/);
  // same inline style as blockReason (no styles.css rule — ui owns that file): dim italic, hidden by default
  assert.match(FEED, /doneReason\.style\.cssText = "display:none;[^"]*font-style:italic/);
  // it sits right after blockReason, between the title (row1) and the session name (row2)
  assert.match(FEED, /main\.append\(row1, blockReason, doneReason, summaryLine, row2/);
  assert.match(FEED, /a\._donewhy = doneReason;/);
});

test("updateAskCard fills + toggles the doneWhy from it.doneWhy (gated by the Explanations pref)", () => {
  assert.match(FEED, /a\._donewhy\.textContent = it\.doneWhy \|\| "";/);
  // shown only when there's a doneWhy AND the "Explanations" card pref is on (the user 2026-06-17)
  assert.match(FEED, /a\._donewhy\.style\.display = \(it\.doneWhy && showWhy\) \? "" : "none";/);
});
