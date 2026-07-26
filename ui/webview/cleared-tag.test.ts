// A cleared (user-dismissed) sub-goal must SAY what it is (the user 2026-07-25): the struck-through
// row read as unexplained machinery, and the hover only offered navigation. Two rules hold it
// legible (the user 2026-07-26): the chip says "cleared" — the same word the Clear button uses, not
// "dropped" — and the strike is INDEPENDENT of the mark, because the box means done and only done
// (a cleared-but-unfinished node keeps its open ring). Source pins (no jsdom for the feed renderer).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");
const FLEET = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "fleet.ts"), "utf8");
const LCSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");
const KERNEL = fs.readFileSync(path.resolve(process.cwd(), "..", "kernel", "kernel.py"), "utf8");

test("one shared tag helper carries the plain-language story, in 'cleared' vocabulary", () => {
  assert.match(FEED, /const CLEARED_TIP = "you cleared this off the board — no longer needed; the box still shows whether it was done"/);
  assert.match(FEED, /function clearedTag\(\): HTMLElement/);
  assert.match(FEED, /tag\.textContent = "cleared"/);
  assert.match(FEED, /tag\.title = CLEARED_TIP/);
  // the old "dropped" vocabulary is gone from every user-facing string
  assert.doesNotMatch(FEED, /textContent = "dropped"/);
  assert.doesNotMatch(FEED, /DROPPED_TIP/);
});

test("the mark means done, and only done — cleared never paints it", () => {
  // nodeMark has no cleared branch: the status alone picks the glyph
  const fn = FEED.slice(FEED.indexOf("function nodeMark"), FEED.indexOf("function nodeStatusClass"));
  assert.doesNotMatch(fn, /cleared\) return/);
  assert.match(fn, /if \(n\.status === "done"\) return "●"/);
  // the optimistic Drop ack strikes + tags the line but leaves the mark alone
  const drop = FEED.slice(FEED.indexOf('line.classList.add("st-cleared")'));
  assert.doesNotMatch(drop.slice(0, drop.indexOf("clearedTag()")), /mark\.textContent/);
});

test("all three cleared surfaces wear the tag: card checklist, modal tree, optimistic Drop", () => {
  assert.match(FEED, /if \(s\.cleared\) row\.appendChild\(clearedTag\(\)\)/);        // card checklist (fcheck)
  assert.match(FEED, /if \(node\.cleared\) line\.appendChild\(clearedTag\(\)\)/);    // modal tree (ftree)
  // the Drop button's instant ack draws the same tag the next re-render will
  assert.match(FEED, /line\.classList\.add\("st-cleared"\);\s*\n\s*line\.appendChild\(clearedTag\(\)\)/);
});

test("a cleared node's text hover leads with the story, keeping the nav", () => {
  assert.match(FEED, /txt\.title = CLEARED_TIP \+ "; click to jump to the message that asked for it"/);
});

test("the Fleet ledger's box means done too — honest kernel flag, strike for the dismissal", () => {
  // kernel: cleared no longer folds into `done`; the dismissal rolls DOWN as `cleared` instead
  assert.match(KERNEL, /"done": explicit or derived, "derived": derived, "cleared": clr/);
  assert.match(KERNEL, /ancestor_cleared=clr/);
  // fleet: the summary-presence guess (cleared-done) is gone — markReason reads the honest flag
  assert.doesNotMatch(FLEET, /cleared-done/);
  assert.match(FLEET, /cleared — dismissed as no longer needed, never done/);
  assert.match(FLEET, /completed, then cleared off the board/);
  // styles: cleared strikes + fades; no outlined-check-for-cleared rule remains
  assert.match(LCSS, /\.ledger-tnode\.cleared \.ledger-ttext \{[^}]*line-through/);
  assert.doesNotMatch(LCSS, /\.done\.cleared \.ledger-tmark/);
});

test("the chip sits outside the strikethrough and is styled dim", () => {
  // the strike stays on the TEXT spans only; the tag is its own flex chip
  assert.match(CSS, /\.fcheck\.cleared \.fcheck-text \{[^}]*line-through/);
  assert.match(CSS, /\.ftree-node\.st-cleared \.ftree-text \{[^}]*line-through/);
  assert.match(CSS, /\.fcleared-tag \{[^}]*color: var\(--dim\)/);
  assert.doesNotMatch(CSS, /\.fcleared-tag \{[^}]*line-through/);
});
