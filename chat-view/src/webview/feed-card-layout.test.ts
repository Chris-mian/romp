// Feed card layout (the user 2026-06-14): the ask / standalone / group cards stack into THREE
// rows — title (full width), session name (own row), then a bottom row with the age on the left
// and the badges + Clear on the right. This frees the title and the (often long) session name to
// use the full card width instead of competing with the age/actions, and lets a long name wrap
// rather than overrun. The separate blocked (amber) card keeps its inline age (no row 3).
// No jsdom harness for the feed, so — like the other feed-*.test.ts — pin it at the source level.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "feed.css"), "utf8");

test("all three main cards build a row3 with the age (left) and actions (right)", () => {
  const row3s = FEED.match(/const row3 = el\("div", "fask-row3"\); row3\.append\(time, actions\)/g) || [];
  assert.equal(row3s.length, 3, "standalone + ask + group each get a row3");
  // the title row no longer carries the time in those builders (it moved to row3)
  assert.match(FEED, /row1\.append\(title\);/);
});

test("row3 + name-wrap are styled; blocked keeps its inline age", () => {
  assert.match(CSS, /\.fask-row3 \{[^}]*display: flex/);
  assert.match(CSS, /\.fask-id \.fname \{[^}]*overflow-wrap: anywhere/, "a long session name wraps instead of overflowing");
  // the blocked card is untouched: its age still rides row 1
  assert.match(FEED, /row1\.append\(title, time\);/, "blocked card still appends the age inline on row1");
  assert.match(CSS, /\.fitem\.blocked \.fask-row1 \.ftime/);
});
