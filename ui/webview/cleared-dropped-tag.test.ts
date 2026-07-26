// A cleared (user-dropped) sub-goal must SAY what it is (the user 2026-07-25): the struck-through row
// with a dim check read as unexplained machinery — they guessed cross-session goal propagation — and
// the hover only offered navigation. The strike means DROPPED BY YOU, not completed by the agent. Now
// a one-word "dropped" chip rides every cleared row (card checklist, modal tree, and the optimistic
// Drop click), with the plain-language sentence on hover, and the text zone's tooltip leads with the
// story before the nav hint. Source pins (no jsdom for the feed renderer).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

test("one shared tag helper carries the plain-language story", () => {
  assert.match(FEED, /const DROPPED_TIP = "you cleared this off the board — dropped as no longer needed, not completed"/);
  assert.match(FEED, /function droppedTag\(\): HTMLElement/);
  assert.match(FEED, /tag\.textContent = "dropped"/);
  assert.match(FEED, /tag\.title = DROPPED_TIP/);
});

test("all three cleared surfaces wear the tag: card checklist, modal tree, optimistic Drop", () => {
  assert.match(FEED, /if \(s\.cleared\) row\.appendChild\(droppedTag\(\)\)/);        // card checklist (fcheck)
  assert.match(FEED, /if \(node\.cleared\) line\.appendChild\(droppedTag\(\)\)/);    // modal tree (ftree)
  // the Drop button's instant ack draws the same tag the next re-render will
  assert.match(FEED, /mark\.textContent = "●"; acts\.remove\(\);\s*\n\s*line\.appendChild\(droppedTag\(\)\)/);
});

test("a cleared node's text hover leads with the story, keeping the nav", () => {
  assert.match(FEED, /txt\.title = DROPPED_TIP \+ "; click to jump to the message that asked for it"/);
});

test("the chip sits outside the strikethrough and is styled dim", () => {
  // the strike stays on the TEXT spans only; the tag is its own flex chip
  assert.match(CSS, /\.fcheck\.cleared \.fcheck-text \{[^}]*line-through/);
  assert.match(CSS, /\.ftree-node\.st-cleared \.ftree-text \{[^}]*line-through/);
  assert.match(CSS, /\.fdropped-tag \{[^}]*color: var\(--dim\)/);
  assert.doesNotMatch(CSS, /\.fdropped-tag \{[^}]*line-through/);
});
