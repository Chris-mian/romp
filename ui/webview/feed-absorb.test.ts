// Absorb animation (the user 2026-06-29): when a top-level ask card becomes a SUB-GOAL of another card, it
// shrinks + flies INTO the parent card instead of vanishing. Detected at reconcile: a card leaving the board
// whose itemId now appears as a NON-root node inside a still-visible ask's tree → that ask's card is the
// parent. Falls back to an instant remove with no parent or under reduced-motion. Source pin (no jsdom).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

test("absorbIntoParent detaches the card to a fixed overlay at its old spot, then flies it to the parent center", () => {
  assert.match(FEED, /function absorbIntoParent\(card: HTMLElement, fromRect: DOMRect, parent: HTMLElement\)/);
  assert.match(FEED, /position: "fixed", left: `\$\{fromRect\.left\}px`/);
  assert.match(FEED, /document\.body\.appendChild\(card\)/);
  // translate by the delta to the parent's center + scale way down + fade
  assert.match(FEED, /const dx = \(to\.left \+ to\.width \/ 2\) - \(fromRect\.left \+ fromRect\.width \/ 2\)/);
  assert.match(FEED, /card\.style\.transform = `translate\(\$\{dx\}px, \$\{dy\}px\) scale\(0\.14\)`/);
  assert.match(FEED, /card\.style\.opacity = "0"/);
  // a transitionend + a setTimeout backstop both remove the node exactly once
  assert.match(FEED, /setTimeout\(done, 650\)/);
});

test("the removal loop routes a sub-goal'd card to absorb, others to an instant remove", () => {
  // build the parent map: each visible ask's NON-root tree-node ids → that ask's card
  assert.match(FEED, /const subgoalParent = new Map<string, HTMLElement>\(\);/);
  assert.match(FEED, /if \(node\.id !== a\.itemId && !subgoalParent\.has\(node\.id\)\) subgoalParent\.set\(node\.id, pcard\)/);
  // a leaving card with a parent + a recorded old rect absorbs; otherwise it's removed instantly
  assert.match(FEED, /if \(parent && first && parent !== leaving\) absorbIntoParent\(leaving, first\.rect, parent\);\s*\n\s*else leaving\.remove\(\);/);
});

test("absorb is suppressed under prefers-reduced-motion (no parent map built → instant remove)", () => {
  assert.match(FEED, /if \(!reduceMotion\) for \(const a of asks\)/);
  assert.match(FEED, /matchMedia\("\(prefers-reduced-motion: reduce\)"\)\.matches/);
});

test("the absorbing card rides ABOVE the board (it dives toward a target, unlike the back-layer flyer)", () => {
  assert.match(CSS, /\.fitem-absorbing \{ z-index: 6;/);
});
