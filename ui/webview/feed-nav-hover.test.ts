// Feed modal sub-node nav + hover (the user 2026-06-16): clicking a sub-item in a card's tree must
// jump to where THAT step happened, and hovering it must light THAT step's timeline bars — not the
// top-level goal's. Both used to key on the top (it.t / the goal-node id), so every sub-item pointed
// at the initial message and sub-node hover never lit anything (it emitted a goal-node id, which the
// timeline matches against SEGMENT ids). No jsdom harness — pin at source level, like the sibling tests.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");

test("a tree-node work-zone click navigates to the NODE's own resolution time, not the card's top turn", () => {
  // the mark/time zones send a per-node time (resolveT), and must NOT fall back to it.t
  assert.match(FEED, /goWork = .*showOnTimeline".*sid: navSid, t: resolveT/);
  assert.doesNotMatch(FEED, /const navT = node\.kind === "handoff" \? node\.t : it\.t/, "the old it.t nav fallback must be gone");
});

test("a blocked/done node's mark+time deep-link to where it RESOLVED (node.mt), the assistant action", () => {
  // the user 2026-06-16, who wanted blocked and completed things to jump to places in the chat that are NOT the
  // user's message. The mark + the time zones send node.mt (the block/done segment) with anchor:"work",
  // so the chat lands on the ASSISTANT turn. (Only the TEXT zone, goMsg, lands on the user's message.)
  // auth !== "open" rider (plan-sync authoritative tier): an agent's own OPEN to-do item is never
  // "resolved" even if a judge flat-DONE'd its umbrella — the agent's list is authoritative. And a
  // rolled-up qderived question ancestor is not resolved either: the block landed on a descendant.
  assert.match(FEED, /const resolved = \(node\.status === "done" \|\| \(node\.status === "question" && !node\.qderived\)\) && node\.auth !== "open"/);
  // open nodes fall back to their newest activity (last), matching the newest-seg work anchor (2026-07-20)
  assert.match(FEED, /const resolveT = \(resolved && node\.mt\) \? node\.mt : \(node\.last \|\| node\.t\)/);
  assert.match(FEED, /goWork = .*showOnTimeline".*t: resolveT, anchor: "work"/, "the mark/time zones land on the assistant action");
  assert.doesNotMatch(FEED, /goWork = .*anchor: "prompt"/, "the work zones must NOT land on the user's message");
});

test("a tree-node hover lights the NODE's own segments via showAskPath(node.id)", () => {
  assert.match(FEED, /mouseenter".*showAskPath", itemId: node\.id, sid: it\.sid, locate: false/);
  assert.match(FEED, /mouseleave".*showAskPath", itemId: it\.itemId, sid: it\.sid, locate: false/, "leaving restores the card's full path");
});

test("the broken collectHoverIds path (emitted goal-node ids the timeline can't match) is gone", () => {
  assert.doesNotMatch(FEED, /function collectHoverIds/);
});

test("clicking the CARD title locates the originating user message (prompt-intent), like the modal", () => {
  // the ask card computes titleAnchor ("prompt", falling back to "work" for origin/unresolvable cards);
  // the old literal anchor:"prompt" pin actually matched the removed standalone card (2026-07-07)
  assert.match(FEED, /let titleAnchor = it\.origin \? "work" : "prompt";/);
  assert.match(FEED, /title\.onclick = .*showOnTimeline".*itemId: it\.itemId.*anchor: titleAnchor/);
  assert.doesNotMatch(FEED, /title\.onclick = .*showAskPath", itemId: it\.itemId/, "the card title no longer just lights the timeline");
});

test("the work zones deep-link BY ID — forward node.anchorUuid alongside the time fallback", () => {
  // the user 2026-06-17 (via rompinfra, kernel 996ebd7): the chat tries the exact turn uuid first
  // (scrollToAnchor), falling back to t only when the uuid is null/off-path — killing the nearest-time
  // miss where a click landed on an unrelated user message.
  assert.match(FEED, /anchorUuid\?: string \| null/, "AskTreeNode carries the per-node anchor uuid");
  // the work anchor falls to the prompt anchor before dispatching null (the user 2026-07-20: a cold-beat
  // null could only toast; either uuid lands an exact turn)
  assert.match(FEED, /goWork = .*showOnTimeline".*anchor: "work", anchorUuid: node\.anchorUuid \?\? node\.promptAnchorUuid \?\? null/);
});

test("the card title deep-links by id — promptAnchorUuid for a 'prompt' title, anchorUuid for a 'work' one", () => {
  // the card's root node carries BOTH uuids (kernel 92e23ff). A prompt-intent title resolves by the user's
  // MINTING turn (promptAnchorUuid — a user turn the kind guard accepts, no time-landing); a "work"/origin
  // title keeps the work uuid. cardAnchorUuid stays the work uuid (goNoted / the why-line reuses it).
  assert.match(FEED, /const rootNode = it\.tree\?\.find\(\(n\) => n\.id === it\.itemId\)/);
  assert.match(FEED, /const cardAnchorUuid = rootNode\?\.anchorUuid \?\? null/);
  assert.match(FEED, /let titleUuid = titleAnchor === "prompt" \? \(rootNode\?\.promptAnchorUuid \?\? null\) : cardAnchorUuid/);
  assert.match(FEED, /title\.onclick = .*showOnTimeline".*anchor: titleAnchor, anchorUuid: titleUuid/);
});

test("a 'prompt' title with NO minting message falls back to the work turn instead of toasting", () => {
  // the user 2026-06-30: an autonomous NOTE the agent wrote itself (or an opener compacted off-path) has no
  // promptAnchorUuid, so a "prompt" jump used to honest-fail with "couldn't locate this in the transcript".
  // Fall back to WHERE THE NOTE WAS WRITTEN — the work turn — switching to anchor "work" so the chat's kind
  // guard accepts the assistant uuid (it refuses an assistant turn under a "prompt" intent).
  assert.match(FEED, /if \(titleAnchor === "prompt" && !titleUuid && cardAnchorUuid\) \{ titleAnchor = "work"; titleUuid = cardAnchorUuid; \}/);
});

test("the modal tree TEXT zone (goMsg) also falls back to goWork when a node has no minting message", () => {
  // same fallback as the card title, for the prompt-intent text zone inside the modal tree (the user 2026-06-30):
  // a node with no promptAnchorUuid jumps to where the work happened rather than honest-failing.
  assert.match(FEED, /if \(!node\.promptAnchorUuid && node\.anchorUuid\) \{ goWork\(ev\); return; \}/);
});

test("a blocked card has NO follow-up button — the follow-up is modal-only", () => {
  assert.doesNotMatch(FEED, /a\._fup/, "no card-level follow-up button wiring");
  assert.doesNotMatch(FEED, /actions\.append\([^)]*\bfup\b/, "fup is not appended to the card actions row");
  assert.match(FEED, /id = "feed-modal-follow"/, "the modal keeps its follow-up button");
});

test("the card's auto-line is PLAIN TEXT, not a deep-link (the human's redesign 2026-06-18)", () => {
  // it used to deep-link via goNoted; the line is a synthesized distiller summary with no single chat
  // location now, so it's just text — the planner's why is its hover tooltip (set in updateAskCard).
  assert.doesNotMatch(FEED, /const goNoted =/);
  assert.doesNotMatch(FEED, /blockReason\.onclick = goNoted;/);
  assert.doesNotMatch(FEED, /doneReason\.onclick = goNoted;/);
  const FEED_CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");
  assert.doesNotMatch(FEED_CSS, /\.fask-blockwhy:hover, \.fask-donewhy:hover/);   // no link-hover affordance
});
