// The "Sub-goals" toggle (now in the feed FOOTER, the user 2026-06-18) gates the inline sub-goal checklist
// on feed CARDS; the MODAL is never gated. The old "Explanations" toggle is GONE — cards show the
// distiller's summary as their one auto-line, not the planner's why. The feed reads the shared
// 'romp:settings' directly and re-renders when the gear / footer (same document) flips it. Source-level pin.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");

test("feed reads the sub-goals pref from romp:settings, defaulting ON; explanations is gone", () => {
  assert.match(FEED, /function feedPrefs\(\)/);
  assert.match(FEED, /localStorage\.getItem\("romp:settings"\)/);
  assert.match(FEED, /return \{ subgoals: s\.subgoals !== false \};/);   // oldestFirst pref removed (always oldest-first now)
  assert.doesNotMatch(FEED, /explanations/);   // every trace of the old pref is gone from the feed
});

test("the card has NO auto-written why/distiller line (removed 2026-06-27 — just the goals)", () => {
  assert.doesNotMatch(FEED, /const setAutoLine =/);
  assert.doesNotMatch(FEED, /"\(generating…\)"/, "no '(generating…)' placeholder anywhere");
  assert.doesNotMatch(FEED, /fask-blockwhy|fask-donewhy/);
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
