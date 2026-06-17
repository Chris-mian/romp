// Feed modal sub-node nav + hover (the user 2026-06-16): clicking a sub-item in a card's tree must
// jump to where THAT step happened, and hovering it must light THAT step's timeline bars — not the
// top-level goal's. Both used to key on the top (it.t / the goal-node id), so every sub-item pointed
// at the initial message and sub-node hover never lit anything (it emitted a goal-node id, which the
// timeline matches against SEGMENT ids). No jsdom harness — pin at source level, like the sibling tests.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "feed.ts"), "utf8");

test("a tree-node click navigates to the NODE's own time, not the card's top turn", () => {
  // the tree-node onclick must send a per-node time (navT), and must NOT fall back to it.t
  assert.match(FEED, /showOnTimeline".*sid: navSid, t: navT/);
  assert.doesNotMatch(FEED, /const navT = node\.kind === "handoff" \? node\.t : it\.t/, "the old it.t nav fallback must be gone");
});

test("a blocked/done node deep-links to where it RESOLVED (node.mt), landing on the assistant action", () => {
  // the user 2026-06-16: "for blocked and completed things jump to places in the chat that are NOT
  // the user's message." A resolved (done/blocked) node sends node.mt (the block/done segment); an
  // open node sends node.t (its own start); the click sends anchor:"work" so the chat lands on the
  // ASSISTANT turn, never anchor:"prompt" (which would land on the user's message).
  assert.match(FEED, /const resolved = node\.status === "done" \|\| node\.status === "question"/);
  assert.match(FEED, /const navT = \(resolved && node\.mt\) \? node\.mt : node\.t/);
  assert.match(FEED, /line\.onclick = .*showOnTimeline".*t: navT, anchor: "work"/, "the tree-line click lands on the assistant action");
  assert.doesNotMatch(FEED, /line\.onclick = .*showOnTimeline".*anchor: "prompt"/, "a tree-line click must NOT land on the user's message");
});

test("a tree-node hover lights the NODE's own segments via showAskPath(node.id)", () => {
  assert.match(FEED, /mouseenter".*showAskPath", itemId: node\.id, locate: false/);
  assert.match(FEED, /mouseleave".*showAskPath", itemId: it\.itemId, locate: false/, "leaving restores the card's full path");
});

test("the broken collectHoverIds path (emitted goal-node ids the timeline can't match) is gone", () => {
  assert.doesNotMatch(FEED, /function collectHoverIds/);
});

test("clicking the CARD title locates the originating user message (anchor:prompt), like the modal", () => {
  assert.match(FEED, /title\.onclick = .*showOnTimeline".*itemId: it\.itemId.*anchor: "prompt"/);
  assert.doesNotMatch(FEED, /title\.onclick = .*showAskPath", itemId: it\.itemId/, "the card title no longer just lights the timeline");
});

test("a blocked card has NO follow-up button — the follow-up is modal-only", () => {
  assert.doesNotMatch(FEED, /a\._fup/, "no card-level follow-up button wiring");
  assert.doesNotMatch(FEED, /actions\.append\([^)]*\bfup\b/, "fup is not appended to the card actions row");
  assert.match(FEED, /id = "feed-modal-follow"/, "the modal keeps its follow-up button");
});
