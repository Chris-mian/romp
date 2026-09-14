// REORDER, the divider and the previews for both widget sections (the user's additions to T409, 2026-09-13). The order
// rules execute in tab-widgets.test.ts (widgetSlot, tabListOrder, moveId); the gear's wiring has no DOM harness, so it
// is pinned at source: one grip per widget row with an accessible name, pointer events with one capture per drag and
// Escape cancelling, the arrow keys on the focused grip through the same moveId rule, the order stored WHOLE (the
// divider's id included) by one writer, the Tab widgets divider as a separator with the name's place in subtle text
// (never a fake name), and a preview under each section's rows drawn by the surfaces' own composers over the demo
// records.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const W = path.resolve(process.cwd(), "..", "ui", "webview");
const GEAR = fs.readFileSync(path.join(W, "gear.js"), "utf8");
const GEAR_CSS = fs.readFileSync(path.join(W, "gear.css"), "utf8");
const SECTION = GEAR.slice(GEAR.indexOf("  function widgetSection(cfg) {"), GEAR.indexOf("  // the tab widgets: settings.tabWidgets with tabCtx as the mirror"));

test("every widget row carries a grip with an accessible name; the grip is the drag handle and the keyboard handle", () => {
  assert.match(SECTION, /var grip = document\.createElement\('button'\); grip\.type = 'button'; grip\.className = 'rs-grip'; grip\.textContent = '⠿';/, "the six-dot grip glyph");
  assert.match(SECTION, /grip\.setAttribute\('aria-label', 'Drag to reorder: ' \+ w\.label\); grip\.title = 'Drag to reorder, or press the arrow keys';/);
  assert.match(SECTION, /row\.appendChild\(grip\); row\.appendChild\(demo\); row\.appendChild\(name\); row\.appendChild\(sw\); row\.appendChild\(opts\);/, "the grip leads the row");
  assert.match(SECTION, /wireGrip\(grip, row, w\.id\);/);
});

test("the drag: pointer events heard on the document (a capture on the grip would end with the row's first move), the row moved live past the midpoints of the others, the drop stored whole, Escape and a cancel restore", () => {
  assert.match(SECTION, /grip\.addEventListener\('pointerdown', function \(e\) \{\s*\n\s*if \(e\.button !== 0\) return;/, "the primary button only");
  assert.doesNotMatch(SECTION, /setPointerCapture/, "no capture on the grip: re-inserting the row releases it and the drag stops after one step (the lab caught it)");
  assert.match(SECTION, /document\.addEventListener\('pointermove', move\); document\.addEventListener\('pointerup', end\); document\.addEventListener\('pointercancel', cancel\); document\.addEventListener\('keydown', esc, true\);/, "mouse, pen and touch are one road: pointer events, on the document for the drag's life; Escape heard in the capture phase");
  assert.doesNotMatch(SECTION, /if \(e\.button !== 0\) return;\s*\n\s*e\.preventDefault\(\);/, "no preventDefault on the grip's pointerdown: the grip takes the focus, so the frame hears Escape and the arrow keys");
  assert.match(SECTION, /if \(y > b\.top \+ b\.height \/ 2\) after = r;/, "the midpoint rule");
  assert.match(SECTION, /if \(after\) \{ if \(after\.nextSibling !== row\) cfg\.host\.insertBefore\(row, after\.nextSibling\); \}\s*\n\s*else if \(cfg\.host\.firstChild !== row\) cfg\.host\.insertBefore\(row, cfg\.host\.firstChild\);/, "the row moves live, never rebuilt");
  assert.match(SECTION, /var now = currentList\(\);\s*\n\s*if \(now\.join\(\) !== before\.join\(\)\) commit\(now\); else paint\(\);/, "the drop commits the visual order whole; a drop in place writes nothing");
  assert.match(SECTION, /var esc = function \(ev\) \{ if \(ev\.key === 'Escape'\) \{ ev\.preventDefault\(\); ev\.stopPropagation\(\); placeRows\(before\); end\(\); \} \};/, "Escape restores the order, ends the drag and goes no further (the panel stays open)");
  assert.match(SECTION, /var cancel = function \(\) \{ placeRows\(before\); end\(\); \};/, "a pointercancel restores too");
  assert.match(SECTION, /document\.removeEventListener\('pointermove', move\); document\.removeEventListener\('pointerup', end\); document\.removeEventListener\('pointercancel', cancel\); document\.removeEventListener\('keydown', esc, true\);/, "every listener a drag adds, it removes");
  assert.match(GEAR_CSS, /#rsettings \.rs-grip \{[^}]*cursor: grab; touch-action: none;/, "touch-action none, so a finger drags the row and not the page");
  // the shell wires its own Escape handler into the settings frame ahead of the drag's, and asks the gear's close hook: a drag in
  // flight answers no there, one Escape level at a time (the lab caught the panel closing under Escape mid-drag)
  assert.match(GEAR, /var widgetDrag = false;/);
  assert.match(SECTION, /row\.classList\.add\('rs-dragging'\); widgetDrag = true;/);
  assert.match(SECTION, /row\.classList\.remove\('rs-dragging'\); widgetDrag = false;/);
  assert.match(GEAR, /window\.__rompSettingsClose = function \(\) \{ if \(p\.hidden \|\| \(lgM && !lgM\.hidden\) \|\| openHousePick \|\| widgetDrag\) return false; closeSettings\(\); return true; \};/);
  // the click the release synthesizes is the drag's: swallowed once in the capture phase, disarmed by that click or the next press
  // (the lab caught the panel closing under a drag whose grip had moved: the click landed on the body, outside the card)
  assert.match(SECTION, /var swallow = function \(ce\) \{ ce\.stopImmediatePropagation\(\); ce\.preventDefault\(\); disarm\(\); \};/, "immediate: the click targets the document, where the panel's click-outside listener sits beside the swallow");
  assert.match(SECTION, /document\.addEventListener\('click', swallow, true\); document\.addEventListener\('pointerdown', disarm, true\);/);
});

test("the keyboard road: ArrowUp and ArrowDown on the focused grip move the row one place through the same moveId rule, and the grip keeps the focus", () => {
  assert.match(SECTION, /grip\.addEventListener\('keydown', function \(e\) \{\s*\n\s*if \(e\.key !== 'ArrowUp' && e\.key !== 'ArrowDown'\) return;\s*\n\s*e\.preventDefault\(\);/);
  assert.match(SECTION, /var list = currentList\(\), i = list\.indexOf\(id\), to = e\.key === 'ArrowUp' \? i - 1 : i \+ 1;\s*\n\s*if \(i < 0 \|\| to < 0 \|\| to >= list\.length\) return;\s*\n\s*commit\(WP\.moveId\(list, id, to\)\);\s*\n\s*grip\.focus\(\);/);
  assert.match(GEAR, /var WP = require\('\.\/widget-prefs\.ts'\);/);
});

test("the order is stored whole by one writer, the divider's id among the tab widgets' ids; the rows follow the stored order on every paint without a rebuild", () => {
  assert.match(SECTION, /function commit\(list\) \{ var prefs = cfg\.prefs\(load\(\)\); prefs\.order = list; cfg\.save\(prefs\); \}/);
  assert.equal((SECTION.match(/prefs\.order = /g) || []).length, 1, "one writer of the order");
  assert.match(SECTION, /function currentList\(\) \{ return Array\.from\(cfg\.host\.children\)\.map\(function \(r\) \{ return r\.getAttribute\('data-widget'\) \|\| r\.getAttribute\('data-divider'\); \}\)\.filter\(Boolean\); \}/, "the visual list reads widgets and the divider alike");
  assert.match(SECTION, /placeRows\(cfg\.order\(prefs\)\);   \/\/ the rows in the stored order \(nodes move, never rebuild: click-safe, focus kept\)/);
  assert.match(GEAR, /order: TW\.tabListOrder, divider: \{ id: TW\.NAME_DIVIDER, label: 'session name' \},/, "the tab section's order carries the divider");
  assert.match(GEAR, /order: function \(prefs\) \{ return SW\.orderedStatusWidgets\(prefs\)\.map\(function \(w\) \{ return w\.id; \}\); \}, divider: null,/, "the status line has no divider: its slots stay the registry's");
});

test("the Tab widgets divider is a separator named for the session name's place, a line with subtle text and never a fake name", () => {
  assert.match(SECTION, /dividerRow = document\.createElement\('div'\); dividerRow\.className = 'rs-widget rs-divider'; dividerRow\.setAttribute\('data-divider', cfg\.divider\.id\);/);
  assert.match(SECTION, /dividerRow\.setAttribute\('role', 'separator'\); dividerRow\.setAttribute\('aria-label', cfg\.divider\.label\);/);
  assert.match(SECTION, /lbl\.className = 'rs-divider-label'; lbl\.textContent = cfg\.divider\.label;/);
  assert.doesNotMatch(SECTION, /dividerRow\.appendChild\(grip\)|rs-divider[^\n]*rs-switch/, "no grip and no switch on the divider: it is not a widget");
  assert.match(GEAR_CSS, /#rsettings \.rs-divider::before, #rsettings \.rs-divider::after \{ content: ""; flex: 1 1 auto; height: 2px; background: var\(--hairline\);/, "a thicker line either side of the words");
  assert.match(GEAR_CSS, /#rsettings \.rs-divider \{[^}]*text-transform: uppercase;/, "small subtle text, not a rendered name");
});

test("the previews are drawn by the surfaces' own composers over the demo records, under each section's rows, repainted with every paint", () => {
  assert.match(SECTION, /var box = document\.createElement\('div'\); box\.className = 'rs-preview';/);
  assert.match(SECTION, /cfg\.host\.parentNode\.insertBefore\(box, cfg\.host\.nextSibling\);/, "right under the rows");
  assert.match(SECTION, /if \(previewBody\) \{ var pv = cfg\.preview\(prefs\); if \(pv\) previewBody\.replaceChildren\(pv\); else previewBody\.replaceChildren\(\); \}/, "repainted in place on every paint");
  // the tab preview: a tab as the strip draws it, both slots around the name, through the strip's own composer
  assert.match(GEAR, /TW\.composeTabWidgets\(tab, 'before', TW\.DEMO_SID, TW\.DEMO_STATUS, prefs\);\s*\n\s*var label = document\.createElement\('span'\); label\.className = 'tab-label'; label\.textContent = 'web'; tab\.appendChild\(label\);\s*\n\s*TW\.composeTabWidgets\(tab, 'after', TW\.DEMO_SID, TW\.DEMO_STATUS, prefs\);/);
  // the status preview: the left slot, the state chip, the right slot ahead of the controls, through the line's own composer
  assert.match(GEAR, /SW\.composeStatusWidgets\(line, 'left', SW\.DEMO_RECORD, prefs\);/);
  assert.match(GEAR, /chip\.className = 'chip rs-sl-chip'; chip\.textContent = 'Ready';/);
  assert.match(GEAR, /SW\.composeStatusWidgets\(right, 'right', SW\.DEMO_RECORD, prefs\);/);
  assert.match(GEAR, /ctl\.className = 'rs-sl-ctl'; ctl\.textContent = 'Auto · Opus 5 · high';/, "the fixed controls, drawn as words in the preview");
  assert.match(GEAR_CSS, /#rsettings \.rs-preview-label \{[^}]*text-transform: uppercase;/);
});
