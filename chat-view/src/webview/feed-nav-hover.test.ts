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

test("a tree-node work-zone click navigates to the NODE's own resolution time, not the card's top turn", () => {
  // the mark/time zones send a per-node time (resolveT), and must NOT fall back to it.t
  assert.match(FEED, /goWork = .*showOnTimeline".*sid: navSid, t: resolveT/);
  assert.doesNotMatch(FEED, /const navT = node\.kind === "handoff" \? node\.t : it\.t/, "the old it.t nav fallback must be gone");
});

test("a blocked/done node's mark+time deep-link to where it RESOLVED (node.mt), the assistant action", () => {
  // the user 2026-06-16: "for blocked and completed things jump to places in the chat that are NOT the
  // user's message." The mark + the time zones send node.mt (the block/done segment) with anchor:"work",
  // so the chat lands on the ASSISTANT turn. (Only the TEXT zone, goMsg, lands on the user's message.)
  assert.match(FEED, /const resolved = node\.status === "done" \|\| node\.status === "question"/);
  assert.match(FEED, /const resolveT = \(resolved && node\.mt\) \? node\.mt : node\.t/);
  assert.match(FEED, /goWork = .*showOnTimeline".*t: resolveT, anchor: "work"/, "the mark/time zones land on the assistant action");
  assert.doesNotMatch(FEED, /goWork = .*anchor: "prompt"/, "the work zones must NOT land on the user's message");
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

test("the work zones deep-link BY ID — forward node.anchorUuid alongside the time fallback", () => {
  // the user 2026-06-17 (via rompinfra, kernel 996ebd7): the chat tries the exact turn uuid first
  // (scrollToAnchor), falling back to t only when the uuid is null/off-path — killing the nearest-time
  // miss where a click landed on an unrelated user message.
  assert.match(FEED, /anchorUuid\?: string \| null/, "AskTreeNode carries the per-node anchor uuid");
  assert.match(FEED, /goWork = .*showOnTimeline".*anchor: "work", anchorUuid: node\.anchorUuid \?\? null/);
});

test("the card title deep-links by id too — anchorUuid from the card's ROOT tree node", () => {
  // the card's root node is the one whose id IS the card's itemId; null when the kernel can't resolve →
  // time fallback (and for a "prompt"-intent normal card the chat's kind guard refuses a reply uuid, so
  // it falls back to time as before — no regression; "work" delegation cards deep-link by id).
  assert.match(FEED, /const cardAnchorUuid = it\.tree\?\.find\(\(n\) => n\.id === it\.itemId\)\?\.anchorUuid \?\? null/);
  assert.match(FEED, /title\.onclick = .*showOnTimeline".*anchor: titleAnchor, anchorUuid: cardAnchorUuid/);
});

test("a blocked card has NO follow-up button — the follow-up is modal-only", () => {
  assert.doesNotMatch(FEED, /a\._fup/, "no card-level follow-up button wiring");
  assert.doesNotMatch(FEED, /actions\.append\([^)]*\bfup\b/, "fup is not appended to the card actions row");
  assert.match(FEED, /id = "feed-modal-follow"/, "the modal keeps its follow-up button");
});

test("the card's why-tagline (block/done reason) deep-links like the title (judges delegation, 2026-06-17)", () => {
  // text the same showOnTimeline as the title, reusing the card's anchorUuid; anchor "work" → where the
  // planner NOTED it (for a DONE card, where it got checked off).
  assert.match(FEED, /const goNoted = \(ev: Event\) => \{ ev\.stopPropagation\(\); vscodeApi\?\.postMessage\(\{ type: "showOnTimeline", itemId: it\.itemId, sid: it\.sid, t: it\.t, anchor: "work", anchorUuid: cardAnchorUuid \}\); \};/);
  assert.match(FEED, /blockReason\.onclick = goNoted;/);
  assert.match(FEED, /doneReason\.onclick = goNoted;/);
  // they read as clickable (cursor) + a hover affordance
  assert.match(FEED, /cursor:pointer/);
  const FEED_CSS = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "feed.css"), "utf8");
  assert.match(FEED_CSS, /\.fask-blockwhy:hover, \.fask-donewhy:hover \{[^}]*text-decoration: underline/);
});
