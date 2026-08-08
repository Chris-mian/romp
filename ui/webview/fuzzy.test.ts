// The palette's fuzzy matcher (ui/webview/fuzzy.ts) — real unit tests, it's pure and DOM-free.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import { fuzzyMatch } from "./fuzzy";

test("matches subsequences, rejects non-subsequences", () => {
  assert.ok(fuzzyMatch("ops", "Open settings"));
  assert.ok(fuzzyMatch("log", "Open the log"));
  assert.equal(fuzzyMatch("xyz", "Open settings"), null);
  assert.equal(fuzzyMatch("settingsx", "Open settings"), null);   // every query char must land
});

test("is case-insensitive both ways", () => {
  assert.ok(fuzzyMatch("OPEN", "open settings"));
  assert.ok(fuzzyMatch("open", "OPEN SETTINGS"));
});

test("empty or blank query matches everything with score 0", () => {
  assert.deepEqual(fuzzyMatch("", "anything"), { score: 0, ranges: [] });
  assert.deepEqual(fuzzyMatch("   ", "anything"), { score: 0, ranges: [] });
});

test("spaces in the query separate words without needing their own match", () => {
  // the greedy walk consumes "open" then finds "set" later; the space itself is skipped
  assert.ok(fuzzyMatch("open set", "Open settings"));
  assert.ok(fuzzyMatch("o s", "Open settings"));
});

test("word starts outrank mid-word scatter", () => {
  // "os" as two word-initials ("Open settings") must beat "os" buried mid-word ("ghosts")
  const initials = fuzzyMatch("os", "open settings")!;
  const buried = fuzzyMatch("os", "ghosts")!;
  assert.ok(initials.score > buried.score);
});

test("consecutive runs outrank spread matches of the same letters", () => {
  const run = fuzzyMatch("log", "log")!;
  const spread = fuzzyMatch("log", "lxoxg")!;   // same letters, buried mid-word with gaps
  assert.ok(run.score > spread.score);
});

test("ranges merge adjacent characters and cover exactly the matched chars", () => {
  const hit = fuzzyMatch("open", "Open settings")!;
  assert.deepEqual(hit.ranges, [[0, 4]]);   // one merged run, not four single-char ranges
  const split = fuzzyMatch("ose", "Open settings")!;
  assert.deepEqual(split.ranges, [[0, 1], [5, 7]]);   // "O" + "se" of settings
});
