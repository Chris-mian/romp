// An expanded tool group's children BRANCH off the main rail: indented 24px onto their own sub-rail,
// entered by a horizontal "right turn" arm under the open arrow, ending at the last child's dot (a 16px
// ::before stub — the same termination idiom as the main rail). Restored 2026-07-17 (the user: flat
// children didn't read as a sub-thing) with BOTH 2026-07-07 complaints designed out: NO bottom return
// arm (it read as a floating horizontal stub), and the MAIN rail continues straight behind the branch
// while the transcript continues below, so the hover-highlight band — drawn at the main rail — still
// has a line to align with. Source-level pin (no jsdom).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("expanded children are indented onto a 24px sub-rail (the branch)", () => {
  assert.match(CSS, /\.tg-child \{ margin-left: 24px; \}/);
});

test("the branch is entered by a right-turn arm hanging off the open arrow line", () => {
  const arm = CSS.match(/\.turn-toolgroup\.expanded::after \{[^}]*\}/);
  assert.ok(arm, "expanded toolgroup has a connector ::after");
  assert.match(arm![0], /left: 10\.5px; bottom: 0; width: 26px; height: 2px;/);
});

test("NO bottom return arm — the sub-rail just ENDS at the last child's dot (16px stub)", () => {
  // the pre-2026-07-07 bottom arm (a horizontal ::after bar on the last child) stays gone
  assert.doesNotMatch(CSS, /\.tg-child\.tg-last::after \{/);
  // instead the last child's ::before is a top stub, mirroring the main rail's last-turn termination
  assert.match(CSS, /\.tg-child\.tg-last::before \{ bottom: auto; height: 16px; \}/);
  assert.match(CSS, /\.turn:not\(:has\(~ \.turn\)\)::before \{ bottom: auto; height: 16px; \}/);
});

test("the main rail continues straight behind the branch while the transcript continues below", () => {
  const thru = CSS.match(/\.tg-child:has\(~ \.turn:not\(\.tg-child\)\)::after \{[^}]*\}/);
  assert.ok(thru, "pass-through main-rail ::after exists on branch children");
  // -13.5px un-does the 24px indent back to the main rail x (10.5px), full height of each child
  assert.match(thru![0], /left: -13\.5px; top: 0; bottom: 0; width: 2px;/);
});

test("the hover-highlight band still hugs the reference turn's rail x", () => {
  // drawRailBand's dotless fallback centers the 4px band on the reference turn's rail (center 11.5 →
  // left 9.5); the main rail runs continuously behind the branch, so a band there always has a line under it
  assert.match(RENDER, /xRef\.getBoundingClientRect\(\)\.left - hostR\.left \+ 9\.5/);
});
