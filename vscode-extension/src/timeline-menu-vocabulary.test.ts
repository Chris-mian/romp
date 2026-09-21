// The timeline's dropdowns (lane gear, model/effort pickers) wear the ONE romp menu vocabulary
// (CLAUDE.md rule, the user 2026-08-09): the chat pane's .ctx-menu/.meta-menu spec, inlined as
// MENU_STYLE/MENU_CHECK_STYLE because this pane may live in a foreign document (Obsidian) that
// loads neither styles.css nor romp's font stack. Before this, the gear menu wore its own bluish
// card, the HOST app's font, and its own radii/sub-sizes — the drift the rule exists to stop.
// Source pins (no jsdom for the SVG renderer).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js"), "utf8");

test("MENU_STYLE is the chat menu spec, with the font stack DECLARED (never inherited)", () => {
  // composed from the theme palette since the light theme landed; the DARK values stay the chat spec
  // verbatim (card #252526, hairline rgba(255,255,255,0.12), shadow rgba(0,0,0,0.35), ✓ #1EA1EB)
  assert.match(SRC, /menuStyleFor = \(p\) => 'padding:4px;background:' \+ p\.menuBg \+ ';border:1px solid ' \+ p\.hairline \+ ';'/);
  assert.match(SRC, /\+ 'border-radius:6px;box-shadow:0 4px 12px ' \+ p\.menuShadow \+ ';font:12px\/1\.4 ' \+ FONT \+ ';'/);
  assert.match(SRC, /menuBg: '#252526',/);
  assert.match(SRC, /menuBg: '#FBF6EF',/);   // PAL_LIGHT mirrors the sheets' --vscode-menu-background (swept 2026-08-31)
  assert.match(SRC, /hairline: 'rgba\(255,255,255,0\.12\)',/);
  assert.match(SRC, /menuShadow: 'rgba\(0,0,0,0\.35\)',/);
  // the ✓-in-circle current mark, same as the chat meta menus
  // the ✓ mark: one box shared with the ring (MENU_MARK_BOX, the shared checkMark's declaration set, the strip tidy round two), the accent behind the glyph
  assert.match(SRC, /const MENU_MARK_BOX = 'position:absolute;right:6px;top:50%;transform:translateY\(-50%\);width:13px;height:13px;border-radius:50%;box-sizing:border-box;'\s*\n\s*\+ 'display:inline-flex;align-items:center;justify-content:center;line-height:1;font-size:9px;font-weight:900;';/);
  assert.match(SRC, /menuCheckStyleFor = \(p\) => MENU_MARK_BOX \+ 'background:' \+ p\.accentSolid \+ ';color:#fff;';/);
  assert.match(SRC, /accentSolid: '#1EA1EB',/);
});

test("both dropdowns build on MENU_STYLE; no menu carries its own off-brand card", () => {
  assert.match(SRC, /'position:fixed;z-index:1001;min-width:96px;' \+ MENU_STYLE/);   // model/effort picker
  assert.match(SRC, /'position:fixed;z-index:1001;width:280px;' \+ MENU_STYLE/);      // lane gear
  assert.doesNotMatch(SRC, /#1c2430/);   // the old bluish one-off card is gone for good
});

test("the gear rows use the shared sub-line treatment (0.82em at 0.6 — the ctx-item-sub sizes)", () => {
  assert.match(SRC, /sub\.setAttribute\('style', 'opacity:0\.6;font-size:0\.82em;'\);/);
  assert.match(SRC, /'display:flex;gap:8px;align-items:flex-start;padding:4px 10px;border-radius:4px;cursor:pointer;'/);
});
