// The "waiting on <peer>" chip (the user 2026-06-22): when it.waitingOn is set (the kernel's _wait_for_graph
// found this session has an unanswered message out to a LIVE peer), the card shows a teal pill "⏳ waiting on
// <peer>" on the wrapping chip row; a mutual-wait CYCLE renders a red "⟲ deadlock: <peer>" instead. Source pin.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

test("a waiting-on chip is built and rides the wrapping chip row (its own line when it doesn't fit)", () => {
  assert.match(FEED, /const waitOnBadge = el\("span", "fask-waiton"\)/);
  assert.match(FEED, /row2\.append\(idwrap, origin, reBadge, fupBadge, waitOnBadge\)/);
  assert.match(FEED, /a\._waitOn = waitOnBadge;/);
});

test("it.waitingOn drives the chip text + the cycle/deadlock variant", () => {
  assert.match(FEED, /wo\.inCycle \? "⟲ deadlock: " : "⏳ waiting on "/);
  assert.match(FEED, /"fask-waiton" \+ \(wo\.inCycle \? " fask-waiton-cycle" : ""\)/);
  assert.match(FEED, /a\._waitOn\.style\.display = "";/, "shown when waitingOn is set");
  assert.match(FEED, /a\._waitOn\.style\.display = "none";/, "hidden when it isn't");
});

test("the chip has its own teal style + a distinct red cycle variant", () => {
  assert.match(CSS, /\.fask-waiton \{[^}]*color: #4ec9b0/);
  assert.match(CSS, /\.fask-waiton-cycle \{ color: #ff6a6a/);
});
