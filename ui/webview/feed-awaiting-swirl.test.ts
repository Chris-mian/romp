// ⏳ AWAITING swirl (the user 2026-06-29): a card held in Working because it's waiting on dispatched/delegated
// work (it.awaiting, NOT a peer wait) shows a small romp swirl spinning in the body — in the SAME spot the
// distiller takeaway/decision-brief lands for completed/blocked cards. It's a glanceable "in flight, not
// stalled" cue; the awaiting "why" rides beside it (it was tooltip-only on the ⏳ badge). Source pin (no jsdom).
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

test("it.awaiting (and NOT a peer wait) shows the swirl + the why; otherwise it's hidden", () => {
  // gated on the SAME `if (aw && !it.waitingOn)` branch as the ⏳ badge — a peer wait uses the waitingOn chip
  assert.match(FEED, /a\._awaitSpin\.style\.display = "";[^\n]*\n\s*a\._awaitWhy\.textContent = aw\.why \|\| "";/);
  assert.match(FEED, /a\._awaitSpin\.style\.display = "none";/);
});

test("the swirl uses the shared glyph, REVERSE-spins like the loader, and respects reduced-motion", () => {
  assert.match(CSS, /\.fask-awaiting-swirl \{[\s\S]*?url\(\.\.\/media\/romp-swirl-glyph\.svg\)/);
  assert.match(CSS, /animation: fask-swirl-spin 1\.4s linear infinite;/);
  assert.match(CSS, /@keyframes fask-swirl-spin \{ to \{ transform: rotate\(-360deg\); \} \}/);   // reverse, like rl-spin
  assert.match(CSS, /@media \(prefers-reduced-motion: reduce\) \{ \.fask-awaiting-swirl \{ animation: none; \} \}/);
});
