// The "stalled" chip + the "stalled" needs-you badge (design/stalled-open-todos-nudge.md; chip label per
// the user 2026-07-02): romp auto-nudges a stalled goal ONCE; if the response turn ends with the goal still
// working-stalled, it is never re-asked — the card carries a red "stalled" pill instead. A FORK-flavored
// failure (the goal had items the agent's OWN to-do list still marks open) additionally floors the card to
// Needs-you, arriving with blocked.state === "stalled" → a "⏸ stalled" badge (and, via !!it.blocked, no
// dangling "Distilling…" swirl on a card that has no brief coming); the chip then yields to the badge so
// the card never says "stalled" twice. Source pin.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

test("the stalled chip is built once and rides the wrapping chip row", () => {
  assert.match(FEED, /const nfBadge = el\("span", "fask-nudgefailed"\)/);
  assert.match(FEED, /nfBadge\.textContent = "stalled"/, "the label is 'stalled' (the user 2026-07-02), no emoji/glyph");
  assert.match(FEED, /row2\.append\(idwrap, origin, reBadge, fupBadge, nfBadge, waitOnBadge\)/);
  assert.match(FEED, /a\._nudgeFailed = nfBadge;/);
});

test("it.nudgeFailed toggles the chip, yielding to the '⏸ stalled' badge (no double 'stalled')", () => {
  assert.match(FEED,
    /a\._nudgeFailed\.style\.display = \(it\.nudgeFailed && it\.blocked\?\.state !== "stalled"\) \? "" : "none";/);
});

test("a stalled floor renders its own '⏸ stalled' badge, not the picker fallback", () => {
  assert.match(FEED, /it\.blocked\.state === "stalled" \? "⏸ stalled" : "⏸ picker"/,
    "the blocked-badge three-way names the stalled state");
});

test("the chip has its own red pill style (waiting on the human now)", () => {
  assert.match(CSS, /\.fask-nudgefailed \{[^}]*color: #ff6a6a/);
});
