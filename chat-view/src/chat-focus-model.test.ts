// Chat focus model (the user 2026-06-26): focus is either on the TABS or in the MESSAGE BOX.
//  - clicking a tab leaves focus on the tab (so Enter drops into the box) — the tab rebuild used to drop it;
//  - Enter on a focused tab → the message box (onTabKey);
//  - Escape in the message box → back to the tabs;
//  - cursor in the message box → a thin accent-blue border (the panel-focus blue).
// And the feed/mail icons use the SAME accent blue in the tab menu and the timeline lanes.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");
const TL = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js"), "utf8");

test("clicking a tab focuses the (rebuilt) active tab so Enter drops into the box", () => {
  assert.match(SRC, /select: \(el\) => \{ const id = el\.dataset\.id; if \(id\) \{ setActive\(id\); focusActiveTab\(\); \} \}/);
});

test("Enter on a focused tab → the message box", () => {
  // onTabKey's Enter branch focuses the composer
  const fn = SRC.slice(SRC.indexOf("function onTabKey"), SRC.indexOf("function focusActiveTab"));
  assert.ok(fn.length > 0, "found onTabKey");
  assert.match(fn, /e\.key === "Enter"/);
  assert.match(fn, /getElementById\("composer-input"\)[\s\S]*?\.focus\(\)/);
});

test("Escape in the message box → the tabs", () => {
  // the composer keydown handler maps Escape to focusActiveTab()
  const i = SRC.indexOf('ta.addEventListener("keydown"');
  const block = SRC.slice(i, SRC.indexOf('ta.addEventListener("input"'));
  assert.ok(block.length > 0, "found the composer keydown handler");
  assert.match(block, /if \(e\.key === "Escape"\)[\s\S]*?focusActiveTab\(\)/);
});

test("the message box shows a thin accent-blue border when focused (panel-focus blue, on the border)", () => {
  assert.match(CSS, /#composer-input:focus \{ border-color: var\(--accent\); \}/);
});

test("the tab-menu feed/mail icons use the accent blue when on (matching the timeline lanes)", () => {
  assert.match(CSS, /\.ctx-item-toggle \.ctx-icon \{ flex: 0 0 auto; margin-top: 1px; color: var\(--accent\);/);
  // the timeline lanes already paint their ON icons in the same blue
  assert.match(TL, /const ROMP_BLUE = '#9cd2ff';/);
  assert.match(CSS, /--accent: #9cd2ff;/, "the accent IS that blue → the menu + timeline match");
});
