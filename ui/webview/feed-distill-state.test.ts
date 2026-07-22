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

test("the brief and the recheck/rejudging swirl BOTH show — neither suppresses the other", () => {
  // The flicker this fix chased came from keying the LINE on the transient `column`; distillState fixed
  // that. Gating the swirl on `!briefText` as well went too far (the user 2026-07-21): a blocked card being
  // re-judged then showed its brief and nothing else, reading as a working card that inexplicably has a
  // summary, with no cue that it was in motion or still blocked underneath. They are SIBLING elements
  // (feed.ts appends `secs` then `awaitSpin`), never rivals for one spot.
  assert.doesNotMatch(FEED, /it\.recheck && !briefText/);
  assert.doesNotMatch(FEED, /it\.rejudging && !briefText/);
  // the swirl's rule is EXECUTED in spin-caption.test.ts; the line's in distiller-line.test.ts
  assert.match(FEED, /const spin = spinFor\(it, distillPending\(/);
});

test("AskItem carries distillState from the kernel", () => {
  assert.match(FEED, /distillState\?: "completed" \| "blocked" \| null;/);
});
