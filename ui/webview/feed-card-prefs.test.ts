// The "Sub-goals" toggle (now in the feed FOOTER, the user 2026-06-18) gates the inline sub-goal checklist
// on feed CARDS; the MODAL is never gated. The old "Explanations" toggle is GONE — cards show the
// distiller's summary as their one auto-line, not the planner's why. The feed reads the shared
// 'romp:settings' directly and re-renders when the gear / footer (same document) flips it. Source-level pin.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");

test("feed reads sub-goals (default ON) + newestFirst/collapsed (default OFF) from romp:settings", () => {
  assert.match(FEED, /function feedPrefs\(\)/);
  assert.match(FEED, /localStorage\.getItem\("romp:settings"\)/);
  // subgoals defaults ON (!== false); the two 2026-07-07 mode toggles default OFF (=== true)
  assert.match(FEED, /return \{ subgoals: s\.subgoals !== false, newestFirst: s\.newestFirst === true, collapsed: s\.collapsed === true \};/);
  assert.doesNotMatch(FEED, /explanations/);   // every trace of the old pref is gone from the feed
});

test("the card shows the DISTILLER's line (summary/blockSummary) but NO why/generating placeholder (restored 2026-06-29)", () => {
  // the card's distiller line is wired through ./distiller-line — the BEHAVIOR is executed in
  // distiller-line.test.ts (completed→summary, blocked→blockSummary, hidden when empty). These pins just
  // confirm the card creates the element and routes through that single rule.
  assert.match(FEED, /const distill = el\("div", "fask-distill"\)/);
  assert.match(FEED, /import \{ distillText, applyDistillLine, distillPending \} from "\.\/distiller-line"/);
  assert.match(FEED, /applyDistillLine\(a\._distill[^)]*it\.column === "completed", it\.column === "needs_input",\s*it\.summary, it\.blockSummary\)/);
  // but the planner's why-rationale AND the stuck "(generating…)" placeholder stay GONE (the user 2026-06-27/29)
  assert.doesNotMatch(FEED, /const setAutoLine =/);
  assert.doesNotMatch(FEED, /"\(generating…\)"/, "no '(generating…)' placeholder anywhere");
  assert.doesNotMatch(FEED, /fask-blockwhy|fask-donewhy/, "the old why-tooltip auto-line stays removed");
  assert.doesNotMatch(FEED, /showWhy/);
});

test("the Sub-goals pref gates the inline checklist on the card", () => {
  assert.match(FEED, /const subs = \(root && feedPrefs\(\)\.subgoals\)/);
});

test("the Sub-goals toggle lives in the feed FOOTER (moved out of the gear), writing the shared pref", () => {
  assert.match(FEED, /function makeSubgoalsToggle\(\)/);
  assert.match(FEED, /function ensureSubgoalsToggle\(\)/);
  assert.match(FEED, /ensureSubgoalsToggle\(\);/);                            // called in render()
  assert.match(FEED, /s\.subgoals = cb\.checked;[\s\S]*localStorage\.setItem\("romp:settings"/);
  assert.match(FEED, /window\.dispatchEvent\(new Event\("romp:settings"\)\)/);  // re-gate cards live
});

test("the feed re-renders when the prefs change (storage cross-pane + same-doc romp:settings event)", () => {
  assert.match(FEED, /window\.addEventListener\("storage", \(e\) => \{ if \(e\.key === "romp:settings"\) render\(\); \}\)/);
  assert.match(FEED, /window\.addEventListener\("romp:settings", \(\) => render\(\)\)/);
});
