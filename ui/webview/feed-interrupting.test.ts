// The "interrupting…" badge (the user 2026-07-07): a stop is IN FLIGHT — the CLI hasn't reached a stream
// boundary yet — so the card holds a steady "interrupting…" badge from the click until the interrupt
// settles, THEN swaps to the past-tense "interrupted" badge. Before this it flickered "working" ↔
// "interrupted" as the SDK live-tail retired mid-settle. Kernel-side the state comes from the SDK backend's
// own in-flight flag (never the transcript tail); client-side it's a source pin like feed-interrupted.test.ts.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8") + fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "card-sections.ts"), "utf8");   // the card's sections, tree and badges moved to card-sections.ts, one builder with the Needs you row (plans/needs-you.md)
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8") + fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "card-sections.css"), "utf8");   // the badge and paragraph rules moved to the sheet both pages import (plans/needs-you.md)

test("the interrupting badge is built once and rides the wrapping chip row", () => {
  assert.match(FEED, /badge\("fask-interrupting", BADGE_WORDS\.interrupting\.text, ""\); setTip\(b, BADGE_WORDS\.interrupting\.title\);/);   // the badges moved to card-sections.ts (round two of the box content PR: one builder for the card and the Needs you row)
  assert.match(FEED, /interrupting: \{ text: "interrupting…", title: /, "text label, no emoji/glyph (the words in card-sections.ts, worn by the Needs you row too)");
  // sits immediately left of the past-tense interrupted badge on the same wrapping row
  assert.match(FEED, /row2\.append\(idwrap, retryBadge, apiBadge, apiRetry, apiLogin, capLine, capBtn, jauthBadge, blkBadge, badges\)/);
  assert.match(FEED, /a\._badges = badges;/);
});

test("it.interrupting toggles the badge; the two interrupt badges are mutually exclusive", () => {
  assert.match(FEED,
    /if \(it\.interrupting && !it\.nudgeFailed\) \{ const b = badge\("fask-interrupting"/,
    "shown while the stop is in flight (stalled chip still outranks)");
  assert.match(FEED,
    /if \(it\.interrupted && !it\.interrupting && !it\.nudgeFailed\) out\.push\(badge\("fask-interrupted"/,
    "the past-tense badge is suppressed while the in-flight one shows — never both");
  assert.match(FEED, /interrupting\?: boolean;/, "the card payload carries the kernel flag");
});

test("the tooltip explains that the stop is dispatched and pending", () => {
  assert.match(FEED, /stop sent — waiting for this session to reach a stopping point/);
});

test("it wears the WORKING treatment (filled yellow, faded) — an active state, not the interrupted outline", () => {
  // matches the chat chip's .chip-interrupting; the design system's working = filled --st-working-bg
  assert.match(CSS, /\.fask-interrupting \{[^}]*background: var\(--st-working-bg\)/);
  assert.match(CSS, /\.fask-interrupting \{[^}]*opacity: 0\.75/, "faded like the chat chip");
  assert.match(CSS, /\.fask-interrupting \{[^}]*font-size: 0\.66em/, "same size as its sibling pills");
});
