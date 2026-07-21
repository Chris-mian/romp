// The card's distiller line (decision brief / takeaway) keys on the kernel's GENUINE resolution state
// (distillState), NOT the transient `column`. recheck/rejudging drop a still-blocked card to the Working
// column every time its session takes a turn; when the line keyed on `column` the brief flickered OFF each
// time, so a busy session's blocked card read as "unblocked, no summary" (the docs thread, the user
// 2026-07-21). The RULE is executed in distiller-line.test.ts (distillInputs); this pins that feed.ts and the
// kernel actually WIRE that rule in — no jsdom for the feed renderer, so pin at the source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");

test("the card routes the distiller line through distillInputs(distillState, column), not column directly", () => {
  assert.match(FEED, /import \{ distillText, distillInputs, applyDistillLine, distillPending \}/);
  // the card computes (completed, blocked) from the genuine state via the shared helper
  assert.match(FEED, /const \{ completed: dCompleted, blocked: dBlocked \} = distillInputs\(it\.distillState, it\.column\);/);
  // both the shown line AND the pending swirl use those, so a blocked card mid-flip keeps showing/spinning
  assert.match(FEED, /applyDistillLine\(a\._distill as HTMLElement, dCompleted, dBlocked,/);
  assert.match(FEED, /distillPending\(dCompleted, dBlocked,/);
  // it no longer keys the line on the transient column (the old `it.column === "needs_input"` at the call)
  assert.doesNotMatch(FEED, /applyDistillLine\([^)]*it\.column === "needs_input"/);
});

test("the recheck/rejudging 'Analyzing…' swirl YIELDS to a present brief (the flicker fix)", () => {
  // when a decision brief exists it fills the distiller-line spot; the swirl only shows when there's nothing
  // to say yet — so a still-blocked card keeps its brief on screen instead of blanking to a swirl every turn.
  assert.match(FEED, /\} else if \(it\.recheck && !briefText\) \{/);
  assert.match(FEED, /\} else if \(it\.rejudging && !briefText\) \{/);
  assert.match(FEED, /const briefText = distillText\(dCompleted, dBlocked, it\.summary, it\.blockSummary\);/);
});

test("AskItem carries distillState from the kernel", () => {
  assert.match(FEED, /distillState\?: "completed" \| "blocked" \| null;/);
});
