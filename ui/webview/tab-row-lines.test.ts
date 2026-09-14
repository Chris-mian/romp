// A hairline under EVERY row of tabs (T134, the user 2026-08-27, overturning the T125 survey's
// one-outer-line design — flagged then as their call to make, now made: with three rows and a
// short third, row 2's tabs "look like they're sitting there floating"). CSS cannot select
// flex-wrap rows, so render.ts paints them; these pins hold the mechanism and the scope.
import { test } from "node:test";
import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("the painter groups rendered tabs by row and lines every row but the last", () => {
  const at = RENDER.indexOf("function paintTabRowLines(");
  assert.ok(at > 0);
  const body = RENDER.slice(at, RENDER.indexOf("\n}", at));
  assert.match(body, /rows\.set\(top, Math\.max\(rows\.get\(top\) \?\? 0, bot\)\);/, "a row = the tabs sharing an offsetTop; its line sits at the tallest bottom");
  assert.match(body, /bottoms\.pop\(\);/, "the LAST row already has #tabbar's own border-bottom beneath it — no double line");
  assert.match(body, /el\("div", "tab-row-line"\)/);
  assert.match(body, /bar\.appendChild\(line\);   \/\/ at the row's bottom edge: the strip's 1px row gap is the line's own pixel row/);
  // T417 (the user 2026-09-14): the line at a row's bottom edge overlapped the top pixel of the row below, and the active tab's inset
  // identity ring there, beginning one pixel under that edge, read cut off at the top; a 1px ROW gap gives each line its own pixel row
  assert.match(CSS, /\n#tabs \{ display: flex; flex: 1 1 auto; flex-wrap: wrap; align-items: stretch; gap: 1px 0; position: relative; \}/, "a 1px row gap, no column gap: the T134 line sits between the rows, over neither");
});

test("repaints are event-keyed: every strip rebuild, plus wrap changes via ResizeObserver", () => {
  assert.match(RENDER, /paintTabRowLines\(bar\);\s*\n\s*ensureTabRowObserver\(bar\);/, "renderTabs ends by painting + arming the observer once");
  assert.match(RENDER, /tabRowObserver = new ResizeObserver\(\(\) => paintTabRowLines\(bar\)\);/, "a width resize re-wraps rows without a rebuild — the observer catches it, no polling");
});

test("full-bleed hairlines in the strip's own border color, Classic-scoped", () => {
  assert.match(CSS, /body:not\(\.chat-theme-yatharth\) #tabs \.tab-row-line \{\n  position: absolute; left: -8px; right: -8px; height: 1px; background: var\(--box-border\); pointer-events: none; \}/,
    "the negative bleed spans the bar's 8px side padding, like the outer close");
  assert.match(CSS, /body\.chat-theme-yatharth #tabs \.tab-row-line \{ display: none; \}/, "Yatharth keeps his merged look");
});
