// Stacked-layout column controls (the user 2026-08-16): a caret LEFT of each category chip folds the
// whole section to its header, and a hover-revealed grip drags the section to a new slot in the
// stack. Both live on the build-once headers (click-safe across the feed's constant re-renders),
// both persist with the view state, and both exist ONLY in the stacked layout — the side-by-side
// layout hides them and ignores the dragged order entirely. Source pins.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

test("the caret folds a category to its header and persists like every other disclosure", () => {
  assert.match(FEED, /const fold = el\("button", "fcol-fold"\);/);
  assert.match(FEED, /if \(collapsedCols\.has\(key\)\) collapsedCols\.delete\(key\); else collapsedCols\.add\(key\);/);
  assert.match(FEED, /cols: \[\.\.\.collapsedCols\],\s*\n\s*order: stackOrder\.slice\(\)/, "rides the persisted view state");
  assert.match(CSS, /\.feed-col\.col-collapsed \.feed-col-list \{ display: none; \}/);
  assert.match(FEED, /fold\.textContent = folded \? "▸" : "▾";/);
});

test("the grip is quiet-until-wanted, findable on touch, and drags only the stacked layout", () => {
  assert.match(CSS, /\.fcol-fold, \.fcol-grip \{ display: none; \}/, "side-by-side shows neither control");
  assert.match(CSS, /\.feed-col-head:hover \.fcol-grip, \.fcol-grip:focus-visible \{ opacity: 1; \}/);
  assert.match(CSS, /@media \(hover: none\) \{ \.fcol-grip \{ opacity: 0\.35; \} \}/, "touch has no hover");
  assert.match(CSS, /\.feed-col\.col-completed\s+\{ order: var\(--stack-order, 1\); \}/,
    "the dragged order overrides the stacked default and only there");
  assert.match(FEED, /grip\.setPointerCapture\(down\.pointerId\);/, "the drag survives leaving the grip");
  assert.match(FEED, /grip\.addEventListener\("pointercancel", up\);/, "a cancelled drag still cleans up + persists");
});

test("both controls live on the build-once header — click-safe across re-renders", () => {
  const build = FEED.slice(FEED.indexOf("function ensureCols"), FEED.indexOf("return {", FEED.indexOf("function ensureCols")));
  assert.ok(build.includes('el("button", "fcol-fold")') && build.includes('el("span", "fcol-grip")'),
    "wired inside ensureCols' one-time scaffold, never in a render loop");
});
