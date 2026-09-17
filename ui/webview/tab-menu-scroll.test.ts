// The tab menu in a window shorter than itself (CI find 2026-09-13, from the Billing lab's 300px-tall window): the menu
// is position: fixed and clamped to the top edge, so its last rows sat below the window, unreachable, and a row the hot-key
// work added moved the Billing row's centre off-screen. The menu clamps to the window and scrolls; the page-scroll dismissal
// exempts the menu's own scroll. Source pins (no DOM harness runs the menu).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const read = (f: string) => fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", f), "utf8");
const RENDER = read("render.ts");
const CSS = read("styles.css");

test("a tab menu taller than the window scrolls inside it, and its own scroll does not dismiss it (CI find 2026-09-13: with one more row the Billing row sat below a 300px window's edge)", () => {
  assert.match(CSS, /\.ctx-menu \{\s*\n\s*position: fixed; z-index: 100; min-width: 110px; padding: 4px;\n(?:\s*\/\*[\s\S]*?\*\/\n)?\s*max-height: calc\(100vh - 8px\); overflow-y: auto; overscroll-behavior: contain;/, "the menu clamps to the window and scrolls");
  const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");
  assert.match(FEED, /\.ctx-menu \{\s*\n\s*position: fixed; z-index: 100; min-width: 110px; padding: 4px;\n\s*max-height: calc\(100vh - 8px\); overflow-y: auto; overscroll-behavior: contain;/, "feed.css mirrors the clamp");
  const CTX = read("ctx-menu.ts");   // the dismissal is the shared builder's since the v0.16.0 tidy: the tab menu is shown through it
  assert.match(RENDER, /ctxMenuEl = showMenuCard\(menu, e\.clientX, e\.clientY, \{ onClose: onTabMenuClosed \}\);/, "the tab menu opens through the builder");
  assert.match(CTX, /const onScroll = \(e: Event\) => \{ if \(!menu\.contains\(e\.target as Node\)\) closeContextMenu\(\); \};/, "a scroll inside the menu is not a dismissal; the page's still is");
  assert.doesNotMatch(RENDER, /window\.addEventListener\("scroll", dismissTabMenu, true\);/, "the bare dismissal is gone");
});
