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
  assert.match(FEED, /row2\.append\(idwrap, origin, reBadge, fupBadge, nfBadge, intBadge, warnChip, waitOnBadge\)/);
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

// nudge HISTORY (the user 2026-07-02): the chip label says "stalled"; the EVIDENCE that romp did follow
// up — how many times, and when — rides the card as `nudged` (kernel _nudge_times) and surfaces on the
// chip tooltip + a modal line. Born of the SSH-thread confusion: two auto-nudges had fired, but nothing
// card-side said so, so "stalled" read like romp never tried.
test("the card carries the auto-nudge history and the chip tooltip cites it", () => {
  assert.match(FEED, /nudged\?: \{ count: number; times: number\[\] \} \| null;/);
  assert.match(FEED, /a\._nudgeFailed\.title = it\.nudged && it\.nudged\.times\.length/,
    "with history the tooltip is dynamic…");
  assert.match(FEED, /romp followed up \$\{it\.nudged\.count\}× \(\$\{it\.nudged\.times\.map\(clockHM\)\.join\(", "\)\}\)/);
  assert.match(FEED, /: "romp followed up on this stalled goal once; the response didn't resolve it/,
    "…and the static wording stays as the no-history floor");
});

test("the modal shows the follow-up history line for a single ask", () => {
  assert.match(FEED, /const nudges = el\("div", "feed-modal-nudges"\)/, "built once in the modal foot chrome");
  assert.match(FEED, /nudEl\.textContent = `romp followed up \$\{nu\.count\}× — \$\{nu\.times\.map\(clockHM\)\.join\(", "\)\}`;/);
  assert.match(FEED, /nudEl\.style\.display = "none";/, "hidden when the target has no recorded fires");
  assert.match(CSS, /\.feed-modal-nudges \{[^}]*color: var\(--dim\)/, "dim meta text, not a shouting banner");
});
