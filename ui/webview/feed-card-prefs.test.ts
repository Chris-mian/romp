// Sub-goals is a PER-CARD "Sub-goals" button (the user 2026-07-08, moved off the footer), whose default
// follows the Collapsed mode; the MODAL is never gated. The old "Explanations" toggle is GONE — cards show
// the distiller's summary as their one auto-line, not the planner's why. The feed reads the shared
// 'romp:settings' directly and re-renders when the gear / footer (same document) flips it. Source-level pin.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");

test("feed reads newestFirst/collapsed (default OFF) from romp:settings; the subgoals pref is gone", () => {
  assert.match(FEED, /function feedPrefs\(\)/);
  assert.match(FEED, /localStorage\.getItem\("romp:settings"\)/);
  // the two mode toggles default OFF (=== true); `subgoals` is no longer a feed-wide pref (per-card button now)
  assert.match(FEED, /return \{ newestFirst: s\.newestFirst === true, collapsed: s\.collapsed === true \};/);
  assert.doesNotMatch(FEED, /s\.subgoals/, "no feed-wide subgoals pref — it's a per-card toggle now");
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

test("Sub-goals is a PER-CARD button whose default follows the Collapsed mode; no footer checkbox", () => {
  // the per-card button (right of Summary) drives an independent on/off; default = !collapsed (mirrors resolveSec)
  assert.match(FEED, /const subBtn = el\("button", "fask-secbtn"\); subBtn\.textContent = "Sub-goals";/);
  assert.match(FEED, /function resolveSub\(id: string\): boolean \{\s*\n\s*return subChoice\.get\(id\) \?\? !feedPrefs\(\)\.collapsed;/);
  // applySubgoals gates the tree on the resolved per-card state and hides the button when there are no sub-goals
  assert.match(FEED, /const on = hasSubs && resolveSub\(id\);/);
  assert.match(FEED, /subBtn\.style\.display = hasSubs \? "" : "none";/);
  assert.match(FEED, /if \(on && root\) \{/, "the tree walks only when the toggle is on");
  // the OLD footer Sub-goals checkbox is gone
  assert.doesNotMatch(FEED, /makeSubgoalsToggle|ensureSubgoalsToggle/, "no footer sub-goals toggle");
  assert.doesNotMatch(FEED, /feedPrefs\(\)\.subgoals/, "the tree no longer gates on a feed-wide subgoals pref");
});

test("the feed re-renders when the prefs change (storage cross-pane + same-doc romp:settings event)", () => {
  assert.match(FEED, /window\.addEventListener\("storage", \(e\) => \{ if \(e\.key === "romp:settings"\) render\(\); \}\)/);
  assert.match(FEED, /window\.addEventListener\("romp:settings", \(\) => render\(\)\)/);
});
