// The per-card notification bell (the user 2026-07-28): every goal card wears a bell BUTTON in its
// bottom-right corner (round 2 — promoted from right-click-only) that arms an OS notification for
// when THIS card enters needs_input or completed (kernel notify-cards.json; the session-wide bell
// rides session-flags "notify" on the lane/tab menu). Right-click still opens the labelled menu.
// Source pins against feed.ts + feed.css (the render path has no jsdom harness), like badge-mirror's.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

test("every card carries the corner bell button, riding the CARD (absolute), not the flex rows", () => {
  assert.match(SRC, /const bellBtn = el\("button", "fask-bellbtn"\);/);
  assert.match(SRC, /card\.append\(main, bellBtn\);/);
  assert.match(CSS, /\.fitem\.ask \{ cursor: pointer; position: relative; \}/);   // the corner's anchor
  assert.match(CSS, /\.fask-bellbtn \{\s*\n\s*position: absolute; right: 4px; bottom: 3px;/);
});

test("off = hover-revealed slashed dim bell; armed (.on) = accent, always visible (mechanics, not status)", () => {
  assert.match(CSS, /\.fask-bellbtn[\s\S]{0,400}opacity: 0;/);                    // quiet feed stays quiet
  assert.match(CSS, /\.fitem\.ask:hover \.fask-bellbtn \{ opacity: 0\.55; \}/);   // the tab-close idiom
  assert.match(CSS, /\.fask-bellbtn\.on \{ opacity: 0\.85; color: var\(--accent\); \}/);
});

test("the bell click toggles without opening the modal, off the FRESHEST payload copy", () => {
  assert.match(SRC, /bellBtn\.onclick = \(ev: Event\) => \{\s*\n\s*ev\.stopPropagation\(\);/);
  assert.match(SRC, /const cur = \(card as any\)\._it as AskItem \| undefined;/);
  assert.match(SRC, /setCardNotify\(card, live, !cardNotifyOn\(live\)\);/);
});

test("right-click still opens the labelled menu; both paths land on the ONE setCardNotify", () => {
  assert.match(SRC, /card\.addEventListener\("contextmenu", \(ev\) => \{\s*\n\s*if \(it\.provisional\) return;/);
  assert.match(SRC, /showCardMenu\(ev, card\);/);
  assert.match(SRC, /function setCardNotify\(card: HTMLElement, it: AskItem, value: boolean\): void \{/);
  assert.match(SRC, /vscodeApi\?\.postMessage\(\{ type: "cardNotify", itemId: it\.itemId, sid: it\.sid, value \}\)/);
  assert.match(SRC, /notify\?: boolean \| null;/);   // the kernel echoes the armed state back on the ask
});

test("optimism is sticky until the kernel confirms, and the click acknowledges instantly", () => {
  assert.match(SRC, /const pendingNotify = new Map<string, boolean>\(\);/);
  assert.match(SRC, /pendingNotify\.set\(it\.itemId, value\);/);
  assert.match(SRC, /paintCardBell\(card, value\);\s*\/\/ acknowledge instantly/);
  // retired the moment the payload agrees (event-based), then whichever value stands renders
  assert.match(SRC, /if \(pendingNotify\.has\(it\.itemId\) && !!it\.notify === pendingNotify\.get\(it\.itemId\)\) pendingNotify\.delete\(it\.itemId\);/);
});

test("repaints are state-gated so a routine push never churns the svg under a press (click-safety)", () => {
  assert.match(SRC, /if \(\(btn as any\)\._bellOn === on\) return;/);
});

test("a provisional placeholder hides its bell (no stable identity to arm)", () => {
  assert.match(SRC, /\.style\.display = it\.provisional \? "none" : "";/);
});

test("the menu wears the tab menu's chrome (feed.css has its own copy — the feed page loads only feed.css)", () => {
  assert.match(CSS, /\.ctx-menu \{\s*\n\s*position: fixed; z-index: 100;/);
  assert.match(CSS, /\.ctx-item-toggle \.ctx-icon\.off \{ color: var\(--dim\); \}/);
  // the standard dismissers: outside mousedown (capture), Escape, scroll, blur
  assert.match(SRC, /if \(cardMenuEl && !cardMenuEl\.contains\(e\.target as Node\)\) dismissCardMenu\(\)/);
  assert.match(SRC, /if \(e\.key === "Escape"\) dismissCardMenu\(\)/);
  assert.match(SRC, /window\.addEventListener\("scroll", dismissCardMenu, true\);/);
});
