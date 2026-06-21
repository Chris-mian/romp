// Chat scroll behavior (the user 2026-06-15): a new "session" push must NOT snap the view to the
// bottom. The kernel re-sends the FULL payload every push, so an APPEND (more turns on the same
// transcript) keeps the user's scroll position; only a FORK (the tab re-pointed onto a new
// transcript) rebuilds + lands at the bottom. The chat renderer has no jsdom harness, so — like the
// other render-*.test.ts / feed-*.test.ts files — pin the behavior at the source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");

test("upsert tells append from fork by transcript identity (firstUuid)", () => {
  assert.match(RENDER, /function firstUuid\(/, "a helper identifies the transcript by its first event uuid");
  assert.match(RENDER, /const forked = [\s\S]*?firstUuid\(msg\.events\) !== firstUuid\(prev\.events\)/,
    "fork = the transcript identity changed (not just any full payload)");
});

test("a content refresh appends (preserves scroll); only a fork drops the DOM", () => {
  assert.match(RENDER, /if \(forked\) \{[\s\S]{0,120}?v\.el\.remove\(\)/,
    "the cached DOM is dropped only on a fork, not on every push");
  assert.match(RENDER, /if \(existed && !forked\) appendActive\(\); else showActive\(\)/,
    "a refresh of the active tab appends instead of snapping to the bottom");
});

test("appendActive snaps only when the user is already near the bottom", () => {
  assert.match(RENDER, /const stick = nearBottom\(content\);[\s\S]*?if \(stick\) content\.scrollTop = content\.scrollHeight/,
    "tail-append follows the live edge only if the reader was already at the bottom");
});

// BY-ID landing only — NO time-based fallback anywhere (the user 2026-06-20: "shrink the 29%, then remove
// the time fallback"). Prompt-intent jumps resolve by id (promptAnchorUuid → a user turn OR a peer's postal
// card, see the kind-guard test below); the genuinely-unanchorable (autonomous / pruned-or-compacted) honest-
// fail with a toast. The whole time-nearest mechanism (scrollToNearestT) is deleted.
test("scrollToNearestT is GONE — no time-based navigation remains in the chat", () => {
  assert.doesNotMatch(RENDER, /function scrollToNearestT/, "the time-nearest helper is deleted");
  assert.doesNotMatch(RENDER, /scrollToNearestT\(/, "nothing calls it");
});

test("the PROMPT-tier time fallback is removed — an unresolvable prompt anchor honest-fails (no clock-nearest)", () => {
  assert.doesNotMatch(RENDER, /pendingAnchorKind === "user" && pendingAnchorT != null/,
    "the nearest-USER-turn time fallback (8a24c16) is gone");
});

test("the kind guard accepts a peer's postal card as a valid PROMPT target (recovers peer openers by id)", () => {
  // a peer-opened node's promptAnchorUuid is the postal atom's uuid; the card is .turn-postal, not
  // .turn-user. The guard used to refuse it (→ the time fallback); now it accepts user OR postal, so the
  // click lands on the originating message BY ID — shrinking the ~29% before the fallback was removed (the user 2026-06-20).
  assert.match(RENDER, /pendingAnchorIntent === "user"\s+&& !target\.classList\.contains\("turn-user"\) && !target\.classList\.contains\("turn-postal"\)/);
});

test("honest-fail fires whenever the deep-link can't resolve by id (the turn is genuinely gone)", () => {
  assert.match(RENDER, /if \(!scrolled\) landToast\("couldn't locate this in the transcript"\)/);
});

test("the ledger zones deep-link BY UUID ONLY — no time-based fallback (the user 2026-06-19)", () => {
  // the kernel plumbs promptAnchorUuid/anchorUuid to each ledger node (the SAME anchors build_feed gives its
  // cards), so the ledger and the feed for one node land on the SAME chat turn. A zone that can't resolve its
  // uuid honest-fails with a toast — no clock-nearest guessing anywhere. scrollToNearestT is now deleted
  // entirely (the ledger never used it; the prompt-tier fallback that did is gone too).
  assert.match(RENDER, /if \(!scrollToAnchor\(uuid\)\) landToast\("couldn't locate this in the transcript"\)/,
    "a ledger zone lands by uuid and honest-fails if it can't");
  assert.doesNotMatch(RENDER, /scrollToNearestT\(t, kind\)/, "the ledger's by-time fallback is gone");
});

test("timeline→chat glow matches turns BY UUID, not a ±2s time window (the user 2026-06-19)", () => {
  // applyGlow lights .turn[data-uuid] against the segment's atom uuids the kernel sends (kernel
  // _segment_atom_uuids); the old data-t range match was a flaky time heuristic and is gone.
  assert.match(RENDER, /function applyGlow\(groups: Array<\{ sid: string; uuids: string\[\] \}>/);
  assert.match(RENDER, /uset\.has\(n\.dataset\.uuid \|\| ""\)/, "glow matches by uuid set");
  assert.doesNotMatch(RENDER, /t >= s - 2 && t <= e \+ 2/, "the old ±2s data-t window match is gone");
});

test("ledger bullet click lands by uuid locally — the dead ledgerLocate host message is gone (the user 2026-06-19)", () => {
  // b.id is the turn's atom uuid (build_session); scroll to it directly. The old `ledgerLocate` host
  // message was never handled (a dead click) and would have been time-based.
  assert.doesNotMatch(RENDER, /type: "ledgerLocate"/, "the never-handled host message is removed");
  assert.match(RENDER, /if \(!scrollToAnchor\(b\.id\)\) landToast/, "the bullet lands by uuid, honest-fail");
});

test("a postal deep-link resolves to the message's card BY data-mid, not just data-uuid (the user 2026-06-20)", () => {
  // the timeline connector / feed delegation passes the postal message id as the anchor; postal cards carry
  // data-mid, so scrollToAnchor matches it to the EXACT card instead of falling through to a nearest-time
  // guess that drifts onto whatever turn was closest in time (e.g. a 'retry' the user typed nearby).
  assert.match(RENDER, /querySelector\(`\.turn\[data-mid="\$\{cssEscape\(uuid\)\}"\]`\)/,
    "scrollToAnchor resolves a postal anchor by data-mid");
});
