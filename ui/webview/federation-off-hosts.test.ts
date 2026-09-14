// The Task tracking switch across kernels (T404 round six). mergeHostFeeds builds the merged frame as the local host's
// with the lists overridden, so before this a remote host's off frame (the switch's stand-in: no cards built) merged
// under a local frame with the switch on left no trace: the merged frame had no `off`, its cards were the local host's
// alone, and the pane's mirror pruned every card-side seen mark of the remote host by absence, re-ringing the bell for
// its cards once the switch came back. The merge now names the off hosts beside their counters, the pane reads the
// frame's cards as unknown while any host is named, and the mirror's card half keeps the stored card marks in that
// state while still minting the on hosts' notices; with every host on the marks prune by absence exactly as before.
// The frame's own `off` stays the LOCAL kernel's word, so the notice and the gear row (both read this dashboard's
// kernel) agree. Same harness as federation-cleared-overlay.test.ts; the helpers are read through the module
// namespace so a tree without them fails as a test and not as a build.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { mergeHostFeeds } from "./federation";
import * as badgeMirror from "./badge-mirror";

const SID = "11111111-2222-3333-4444-555555555555";
const REMOTE = "HOSTA";

type Half = { notices: { kind: string; itemId?: string }[]; active: Set<string> };
const frameCardsUnknown = (badgeMirror as any).frameCardsUnknown as ((m: any) => boolean) | undefined;
const badgeCardHalf = (badgeMirror as any).badgeCardHalf as ((items: any[], seen: Set<string>, unknown: boolean) => Half) | undefined;

// one card per host carrying a warn chip, so the mirror has a notice to mint and a mark to keep
function card(host: string) {
  const pre = host ? host + ":" : "";
  return { itemId: pre + SID + ":g1", sid: pre + SID, name: pre + "api", text: "ship the notes-api",
           warns: [{ kind: "distill", t: 100, msg: "the summarizer gave up" }] };
}
function onFrame(host: string) {
  return { type: "feed", now: 100, buildId: 3, asks: [card(host)], items: [], working: [], awaiting: [], clearNotices: [], sdkNotices: [], syncNotices: [] };
}
function offFrame() {
  return { type: "feed", now: 100, buildId: 3, off: true, asks: [], items: [], working: [], awaiting: [], clearNotices: [], sdkNotices: [], syncNotices: [],
           dismissedCount: 0, showDismissed: false, canUndoClear: false };
}
// the mark the mirror stored for a host's card the last time that card was on screen (badgeNotices' w| sig shape)
function markFor(host: string, seen: Set<string>): string {
  const minted = badgeMirror.badgeNotices([card(host)] as any, new Set());
  const w = Array.from(minted.active).find((s) => s.startsWith("w|"));
  assert.ok(w, "the minter names the card's warn");
  seen.add(w!);
  return w!;
}

test("the helpers exist: the pane's reading of a frame and the mirror's card half", () => {
  assert.equal(typeof frameCardsUnknown, "function");
  assert.equal(typeof badgeCardHalf, "function");
});

test("local on, remote off: the merged frame names the remote host off and keeps its own signal on; the mirror keeps the remote host's card mark and still mints the local card's notice", () => {
  const merged = mergeHostFeeds({ "": onFrame(""), [REMOTE]: offFrame() }, ["", REMOTE]);
  assert.equal(merged.off, undefined, "the local kernel's word: the switch is on here");
  assert.deepEqual(merged.offHosts, [REMOTE]);
  assert.deepEqual(merged.asks.map((a: any) => a.itemId), [SID + ":g1"], "the local host's cards alone");
  assert.equal(frameCardsUnknown!(merged), true, "one host's cards are unknown");
  const seen = new Set<string>();
  const remoteMark = markFor(REMOTE, seen);
  const half = badgeCardHalf!(merged.asks, seen, frameCardsUnknown!(merged));
  assert.ok(half.active.has(remoteMark), "the off host's card mark is kept");
  assert.equal(half.notices.length, 1, "the local card's warn still rings");
  assert.equal(half.notices[0].itemId, SID + ":g1");
  assert.ok(Array.from(half.active).some((s) => s.startsWith("w|" + SID + ":g1")), "the local card's own mark is written too");
});

test("local off, remote on: the merged frame says off (the local kernel's word, as the gear row does) and names the local host; the pane's off write keeps both hosts' card marks", () => {
  const merged = mergeHostFeeds({ "": offFrame(), [REMOTE]: onFrame(REMOTE) }, ["", REMOTE]);
  assert.equal(merged.off, true);
  assert.deepEqual(merged.offHosts, [""]);
  assert.deepEqual(merged.asks.map((a: any) => a.itemId), [REMOTE + ":" + SID + ":g1"], "the remote host's cards ride the frame");
  assert.equal(frameCardsUnknown!(merged), true);
  const seen = new Set<string>();
  const localMark = markFor("", seen);
  const remoteMark = markFor(REMOTE, seen);
  // the pane's off branch mirrors no items with the cards unknown (feed.ts); the stored card marks all survive the write
  const half = badgeCardHalf!([], seen, true);
  assert.ok(half.active.has(localMark) && half.active.has(remoteMark));
  assert.deepEqual(half.notices, [], "nothing minted from a frame whose cards were not built");
});

test("the order of the hosts changes nothing: remote first, local second", () => {
  const a = mergeHostFeeds({ [REMOTE]: offFrame(), "": onFrame("") }, [REMOTE, ""]);
  assert.equal(a.off, undefined); assert.deepEqual(a.offHosts, [REMOTE]); assert.equal(frameCardsUnknown!(a), true);
  const b = mergeHostFeeds({ [REMOTE]: onFrame(REMOTE), "": offFrame() }, [REMOTE, ""]);
  assert.equal(b.off, true); assert.deepEqual(b.offHosts, [""]); assert.equal(frameCardsUnknown!(b), true);
  const both = mergeHostFeeds({ [REMOTE]: offFrame(), "": offFrame() }, [REMOTE, ""]);
  assert.equal(both.off, true); assert.deepEqual(both.offHosts, [REMOTE, ""]);
});

test("both on: no host is named, the cards are known, and a mark whose card left the frame prunes by absence as before", () => {
  const merged = mergeHostFeeds({ "": onFrame(""), [REMOTE]: onFrame(REMOTE) }, ["", REMOTE]);
  assert.equal(merged.off, undefined);
  assert.deepEqual(merged.offHosts, []);
  assert.equal(frameCardsUnknown!(merged), false);
  const seen = new Set<string>(["w|" + REMOTE + ":" + SID + ":gone|100|distill", "n|" + SID + ":gone"]);
  const live = markFor("", seen); markFor(REMOTE, seen);
  const half = badgeCardHalf!(merged.asks, seen, frameCardsUnknown!(merged));
  assert.equal(half.notices.length, 0, "both cards' warns were already seen");
  assert.ok(half.active.has(live), "the live card's mark stands");
  assert.ok(!half.active.has("w|" + REMOTE + ":" + SID + ":gone|100|distill") && !half.active.has("n|" + SID + ":gone"), "the absent cards' marks are pruned");
  // a host that sent nothing yet is neither on nor off: it is pending, not named here
  const pending = mergeHostFeeds({ "": onFrame("") }, ["", REMOTE]);
  assert.deepEqual(pending.offHosts, []); assert.deepEqual(pending.pendingHosts, [REMOTE]);
});

test("the pane's normal branch hands the mirror the frame's reading, and the mirror's card half is the one helper (source pins on feed.ts)", () => {
  const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
  assert.match(FEED, /mirrorBadges\(incomingAsks,[^;]*\{ cardsUnknown: frameCardsUnknown\(m\) \}\);/, "the normal branch asks the frame");
  assert.match(FEED, /const badges = badgeCardHalf\(items, seenSet, !!opts\?\.cardsUnknown\);/, "one card half for both branches");
  assert.match(FEED, /import \{[^}]*\bbadgeCardHalf\b[^}]*\} from "\.\/badge-mirror"/);
  assert.match(FEED, /import \{[^}]*\bframeCardsUnknown\b[^}]*\} from "\.\/badge-mirror"/);
});
