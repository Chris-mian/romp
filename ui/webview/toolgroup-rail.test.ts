// An expanded tool group's children sit on the SAME main rail as every other turn — ONE continuous straight
// line of dots that terminates at the last child's dot (the last-turn 16px ::before stub), NOT an indented
// side-rail bracketed by horizontal connector arms (the user 2026-07-07): the bottom arm read as a floating
// horizontal stub, and the hover-highlight band — drawn straight down the main rail — couldn't follow the
// indent detour, so it sat off to the side of the children. No indent, no connectors. Source-level pin (no jsdom).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("expanded children share the MAIN rail — not indented onto a side-rail", () => {
  assert.match(CSS, /\.tg-child \{ margin-left: 0; \}/);
});

test("the horizontal connector ARMS are gone (they read as a floating stub + broke the highlight alignment)", () => {
  assert.doesNotMatch(CSS, /\.turn-toolgroup\.expanded::after \{/);
  assert.doesNotMatch(CSS, /\.tg-child\.tg-last::after \{/);
});

test("the rail is one straight line that terminates at the LAST turn's dot (the 16px ::before stub)", () => {
  assert.match(CSS, /\.turn:not\(:has\(~ \.turn\)\)::before \{ bottom: auto; height: 16px; \}/);
});

test("the hover-highlight band hugs the main rail — now aligned since children share it (no detour to miss)", () => {
  // drawRailBand pins the band at the reference turn's x + 10.5 (the .turn::before x); with children on the
  // main rail, every turn shares that x, so the band lines up with the rail through the whole group
  assert.match(RENDER, /xRef\.getBoundingClientRect\(\)\.left - hostR\.left \+ 10\.5/);
});
