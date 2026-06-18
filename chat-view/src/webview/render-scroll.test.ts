// Chat scroll behavior (the user 2026-06-15): a new "session" push must NOT snap the view to the
// bottom. The kernel re-sends the FULL payload every push, so an APPEND (more turns on the same
// transcript) keeps the user's scroll position; only a FORK (the tab re-pointed onto a new
// transcript) rebuilds + lands at the bottom. The chat renderer has no jsdom harness, so — like the
// other render-*.test.ts / feed-*.test.ts files — pin the behavior at the source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "render.ts"), "utf8");

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

// Two-tier PROMPT landing + honest-fail (the user 2026-06-17). Prompt-intent jumps resolve by id
// (promptAnchorUuid) when they can, else fall back to the nearest USER turn — which for a title IS the
// originating message, not a wrong jump. WORK intent has no fallback: a missing work anchor honest-fails.
test("WORK intent has NO time fallback (the blunt any-kind fallback is gone)", () => {
  assert.doesNotMatch(RENDER, /if \(!scrolled && pendingAnchorT != null\) \{ scrolled = scrollToNearestT/,
    "the old blunt (any-kind) fallback is gone — a work-anchor miss honest-fails");
  assert.doesNotMatch(RENDER, /showing the latest instead \(logged\)/, "the old heuristic toasts are gone");
  assert.doesNotMatch(RENDER, /landed nearby \(logged\)/);
});

test("PROMPT intent keeps a nearest-USER-turn fallback after the by-id attempt (covers the ~29% promptAnchorUuid can't resolve)", () => {
  // promptAnchorUuid gives an EXACT landing when it resolves (~71% of cards); the rest mint from a peer
  // opener / autonomous segment / a pruned-or-compacted turn, so tier-2 lands on the nearest USER turn rather
  // than honest-failing. (8a24c16 retired this too eagerly; a fleet measurement showed tier 1 covers ~71%.)
  assert.match(RENDER, /if \(!scrolled && pendingAnchorKind === "user" && pendingAnchorT != null\) scrolled = scrollToNearestT\(pendingAnchorT, "user"\);/);
});

test("honest-fail still fires when even the nearest-user-turn finds nothing (the turn is genuinely gone)", () => {
  assert.match(RENDER, /if \(!scrolled\) landToast\("couldn't locate this in the transcript"\)/);
});

test("scrollToNearestT stays for the ledger's intentional by-time navigation (only the blunt anchor fallback was killed)", () => {
  assert.match(RENDER, /function scrollToNearestT\(/, "the helper still exists");
  assert.match(RENDER, /ev\.stopPropagation\(\); scrollToNearestT\(t, kind\); \}\)/,
    "the ledger zones still navigate by time directly (a primary action, not an anchor fallback)");
});
