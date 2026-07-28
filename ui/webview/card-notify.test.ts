// The per-card notification bell (the user 2026-07-28): right-click a feed card → a one-item context
// menu whose "Notify me" arms an OS notification for when THIS card enters needs_input or completed
// (kernel notify-cards.json; the session-wide bell rides session-flags "notify" on the lane/tab menu).
// Source pins against feed.ts + feed.css (the render path has no jsdom harness), like badge-mirror's.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

test("right-click opens the card menu; a provisional placeholder (no stable identity) gets none", () => {
  assert.match(SRC, /card\.addEventListener\("contextmenu", \(ev\) => \{\s*\n\s*if \(it\.provisional\) return;/);
  assert.match(SRC, /ev\.preventDefault\(\); ev\.stopPropagation\(\);\s*\n\s*showCardMenu\(ev, card\);/);
});

test("the menu reads the FRESHEST payload copy off the card, never the make-time closure", () => {
  // updateAskCard restashes a._it every push; the closure's `it` goes stale after the first one
  assert.match(SRC, /a\._it = it;/);
  assert.match(SRC, /const it = \(card as any\)\._it as AskItem \| undefined;/);
});

test("the toggle posts cardNotify with the card's id + owning session", () => {
  assert.match(SRC, /vscodeApi\?\.postMessage\(\{ type: "cardNotify", itemId: it\.itemId, sid: it\.sid, value: !on \}\)/);
  assert.match(SRC, /notify\?: boolean \| null;/);   // the kernel echoes the armed state back on the ask
});

test("optimism is sticky until the kernel confirms — the lane toggles' pattern, not a timer", () => {
  assert.match(SRC, /const pendingNotify = new Map<string, boolean>\(\);/);
  assert.match(SRC, /pendingNotify\.set\(it\.itemId, !on\);/);
  // retired the moment the payload agrees (event-based), then whichever value stands renders
  assert.match(SRC, /if \(pendingNotify\.has\(it\.itemId\) && !!it\.notify === pendingNotify\.get\(it\.itemId\)\) pendingNotify\.delete\(it\.itemId\);/);
});

test("the click acknowledges instantly: the armed bell shows before the kernel round-trip", () => {
  assert.match(SRC, /if \(bell\) bell\.style\.display = !on \? "" : "none";\s*\/\/ acknowledge instantly/);
});

test("an armed card wears a quiet accent bell beside Clear; labels are state-dependent", () => {
  assert.match(SRC, /const bellOnBadge = el\("span", "fask-bellon"\);/);
  assert.match(SRC, /waitOnBadge, bellOnBadge, clr\);/);
  assert.match(SRC, /on \? "Stop notifying" : "Notify me"/);
  assert.match(SRC, /system notification when this card blocks on you or completes/);
  // accent = mechanics chrome (CLAUDE.md: never a status colour)
  assert.match(CSS, /\.fask-bellon \{ flex: 0 0 auto; display: flex; align-items: center; color: var\(--accent\)/);
});

test("the menu wears the tab menu's chrome (feed.css has its own copy — the feed page loads only feed.css)", () => {
  assert.match(CSS, /\.ctx-menu \{\s*\n\s*position: fixed; z-index: 100;/);
  assert.match(CSS, /\.ctx-item-toggle \.ctx-icon\.off \{ color: var\(--dim\); \}/);
  // the standard dismissers: outside mousedown (capture), Escape, scroll, blur
  assert.match(SRC, /if \(cardMenuEl && !cardMenuEl\.contains\(e\.target as Node\)\) dismissCardMenu\(\)/);
  assert.match(SRC, /if \(e\.key === "Escape"\) dismissCardMenu\(\)/);
  assert.match(SRC, /window\.addEventListener\("scroll", dismissCardMenu, true\);/);
});
