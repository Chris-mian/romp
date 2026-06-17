// The ⛭ "Explanations" + "Sub-goals" toggles gate what shows on feed CARDS (the user 2026-06-17): the
// planner's why line under the title, and the inline sub-goal checklist. The MODAL is never gated. The
// feed reads the shared 'romp:settings' directly and re-renders when the gear (same document) flips one.
// Source-level pin (no jsdom for the feed renderer).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "feed.ts"), "utf8");

test("feed reads card-display prefs from romp:settings, defaulting ON", () => {
  assert.match(FEED, /function feedPrefs\(\)/);
  assert.match(FEED, /localStorage\.getItem\("romp:settings"\)/);
  assert.match(FEED, /explanations: s\.explanations !== false, subgoals: s\.subgoals !== false/);
});

test("the Explanations pref gates the card why lines (block + done), not the modal", () => {
  assert.match(FEED, /const showWhy = feedPrefs\(\)\.explanations;/);
  assert.match(FEED, /a\._blockwhy\.style\.display = \(it\.blockWhy && showWhy\) \? "" : "none";/);
  assert.match(FEED, /a\._donewhy\.style\.display = \(it\.doneWhy && showWhy\) \? "" : "none";/);
});

test("the Sub-goals pref gates the inline checklist on the card", () => {
  assert.match(FEED, /const subs = \(root && feedPrefs\(\)\.subgoals\)/);
});

test("the feed re-renders when the prefs change (storage cross-pane + same-doc romp:settings event)", () => {
  assert.match(FEED, /window\.addEventListener\("storage", \(e\) => \{ if \(e\.key === "romp:settings"\) render\(\); \}\)/);
  assert.match(FEED, /window\.addEventListener\("romp:settings", \(\) => render\(\)\)/);
});
