// Clear → "animate away → pop back → disappear" bug (the user 2026-06-19): a feed push that arrives in
// the ~180ms dismiss window still lists the card; re-rendering it (updateAskCard resets className) strips
// `.dismissing`, reversing the collapse so it pops back, then a later push drops it. Fix: optimistically-
// cleared ids are suppressed from incoming payloads until the kernel's payload confirms the clear, and a
// mid-dismiss card is never yanked by a push (its own 180ms timer finishes the animation). Source-level.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");

test("there is a pendingCleared suppression set", () => {
  assert.match(FEED, /const pendingCleared = new Set<string>\(\);/);
});

test("Clear marks the id pending so a stale push can't resurrect the dismissing card", () => {
  // every Clear handler records the id before posting askClear
  const adds = FEED.match(/pendingCleared\.add\(/g) || [];
  assert.ok(adds.length >= 3, "ask card, standalone item, and group-member clears all suppress");
});

test("incoming feed payloads drop still-pending ids, and release once the kernel confirms the clear", () => {
  // confirmed = the kernel's payload no longer lists it → stop suppressing
  assert.match(FEED, /if \(!incomingAsks\.some\(\(a\) => a\.itemId === id\)\) pendingCleared\.delete\(id\)/);
  // otherwise filter the still-pending ones out of this payload
  assert.match(FEED, /asks = pendingCleared\.size \? incomingAsks\.filter\(\(a\) => !pendingCleared\.has\(a\.itemId\)\) : incomingAsks;/);
});

test("a mid-dismiss card is NOT removed by a push — its own timer finishes the collapse", () => {
  assert.match(FEED, /const undismissed = \(el\?: HTMLElement\) => !!el && !el\.classList\.contains\("dismissing"\);/);
  assert.match(FEED, /!desired\.has\("a:" \+ id\) && undismissed\(askEls\.get\(id\)\)/);
});

test("Undo clears the suppression so a restored card re-appears even mid-window", () => {
  assert.match(FEED, /pendingCleared\.clear\(\); vscodeApi\?\.postMessage\(\{ type: "undoClear" \}\)/);
});
