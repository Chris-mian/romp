// Spinning-swirl + caption on "in motion, not on you" cards (the user 2026-06-29): a small romp swirl spins in
// the card body — the SAME spot the distiller takeaway/decision-brief lands for completed/blocked cards — with a
// couple words saying what's happening. THREE cases, all in the Working column: AWAITING (it.awaiting, not a
// peer wait → the kernel why), PROVISIONAL (a dashed live-prompt placeholder → "Working…"), and RE-CHECK (a
// soft-block you've replied to, dashed pending re-judge → "Re-checking…"). Source pin (no jsdom).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

test("the swirl element is built in the body, right after the distiller line, and registered", () => {
  assert.match(FEED, /const awaitSpin = el\("div", "fask-awaiting"\); awaitSpin\.style\.display = "none";/);
  assert.match(FEED, /const awaitGlyph = el\("span", "fask-awaiting-swirl"\)/);
  assert.match(FEED, /main\.append\(row1, row2, row3, distill, awaitSpin, checklist, delegations\)/);
  assert.match(FEED, /a\._awaitSpin = awaitSpin; a\._awaitWhy = awaitWhy;/);
});

test("the swirl + caption covers awaiting, provisional, and re-check — shown when there's a caption, else hidden", () => {
  // a single computed caption drives the swirl: awaiting → the why; a working provisional placeholder →
  // "Working…"; a re-check (replied soft-block) → "Re-checking…". The blocked placeholder (needs-input) is
  // NOT covered — it's on you, not in motion.
  assert.match(FEED, /if \(aw && !it\.waitingOn\) spinCaption = aw\.why \|\| "Waiting on work it dispatched…";/);
  assert.match(FEED, /else if \(it\.provisional && it\.column === "working"\) spinCaption = "Working…";/);
  assert.match(FEED, /else if \(it\.recheck\) spinCaption = "Re-checking…";/);
  assert.match(FEED, /a\._awaitSpin\.style\.display = spinCaption \? "" : "none";/);
  assert.match(FEED, /if \(spinCaption\) a\._awaitWhy\.textContent = spinCaption;/);
});

test("the swirl uses the shared glyph, REVERSE-spins like the loader, and respects reduced-motion", () => {
  assert.match(CSS, /\.fask-awaiting-swirl \{[\s\S]*?url\(\.\.\/media\/romp-swirl-glyph\.svg\)/);
  assert.match(CSS, /animation: fask-swirl-spin 1\.4s linear infinite;/);
  assert.match(CSS, /@keyframes fask-swirl-spin \{ to \{ transform: rotate\(-360deg\); \} \}/);   // reverse, like rl-spin
  assert.match(CSS, /@media \(prefers-reduced-motion: reduce\) \{ \.fask-awaiting-swirl \{ animation: none; \} \}/);
});
