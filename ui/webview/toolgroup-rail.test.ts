// An expanded tool group's children are a DETOUR of the main rail (the user 2026-07-17 ×2): the rail
// goes IN (a right-turn arm under the open arrow), DOWN a 24px-indented sub-rail, and BACK (a return
// arm at the last child's bottom) to rejoin the main rail — ONE path, never two parallel verticals.
// The main rail is ELIMINATED behind the branch. The return arm is gated on a following turn, so a
// group that ends the transcript keeps the last-turn 16px stub instead of a dangling arm (the
// disconnected-looking arm was the 2026-07-07 complaint). Source-level pins (no jsdom).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("expanded children are indented onto a 24px sub-rail (the detour)", () => {
  assert.match(CSS, /\.tg-child \{ margin-left: 24px; \}/);
});

test("IN: a right-turn arm hangs off the open arrow line onto the sub-rail", () => {
  const arm = CSS.match(/\.turn-toolgroup\.expanded::after \{[^}]*\}/);
  assert.ok(arm, "expanded toolgroup has a connector ::after");
  assert.match(arm![0], /left: 10\.5px; bottom: 0; width: 26px; height: 2px;/);
});

test("BACK: a return arm at the last child's bottom rejoins the main rail — gated on a following turn", () => {
  const back = CSS.match(/\.tg-child\.tg-last:has\(~ \.turn\)::after \{[^}]*\}/);
  assert.ok(back, "return arm exists when the transcript continues");
  assert.match(back![0], /left: -13\.5px; bottom: 0; width: 26px; height: 2px;/);
  // no unconditional arm — a group that ENDS the transcript must not dangle one (2026-07-07)
  assert.doesNotMatch(CSS, /\.tg-child\.tg-last::after \{/);
  // …that tail case terminates via the generic last-turn 16px stub instead
  assert.match(CSS, /\.turn:not\(:has\(~ \.turn\)\)::before \{ bottom: auto; height: 16px; \}/);
});

test("the main rail is ELIMINATED behind the branch — one path, not a parallel pair", () => {
  // the old pass-through (a second vertical at the main x behind the children) is gone
  assert.doesNotMatch(CSS, /\.tg-child:has\(~ \.turn:not\(\.tg-child\)\)::after/);
  // and the sub-rail runs full height into both corners — no mid-branch stub on the last child
  assert.doesNotMatch(CSS, /\.tg-child\.tg-last::before \{ bottom: auto/);
});

test("the hover band's dotless fallback still centers on the reference turn's rail", () => {
  assert.match(RENDER, /xRef\.getBoundingClientRect\(\)\.left - hostR\.left \+ 11\.5/);
});
