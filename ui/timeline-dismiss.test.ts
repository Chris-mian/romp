// Dead-lane "Clear" pill (the user 2026-07-02): a DEAD session lingers in the timeline as a faded/struck lane
// while it's still in the activity window, with NONE of the live controls (no feed/postal toggle, no model
// picker, no chip, no ctx battery). A small Clear pill — the feed cards' clear-button chrome — sits just right
// of the struck name to dismiss the leftover lane; the kernel forgets the dismissal on restart so it can come
// back. No DOM harness for the SVG draw path, so pin the wiring at the source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js"), "utf8");

test("only DEAD lanes draw the Clear pill (gated on !s.live), placed at the empty controls column", () => {
  assert.match(SRC, /if \(!s\.live\) \{[\s\S]*?ctx\.textContent = 'Clear';/);
  // positioned at eyeColX — the controls column, empty for a dead lane, just right of the name
  assert.match(SRC, /const cw = Math\.ceil\(this\.ctxWidth\('Clear'\)\), bw = cw \+ CL_PAD \* 2, bx = eyeColX/);
});

test("the pill mirrors the feed clear button: outlined+dim, red fill on hover", () => {
  assert.match(SRC, /const CL_H = 15, CL_PAD = 7, CL_RED = '#c74e39';/);
  // resting = MODEL_FG outline; hover = red fill + white text
  assert.match(SRC, /box\.setAttribute\('fill', CL_RED\); box\.setAttribute\('stroke', CL_RED\)[\s\S]*?ctx\.setAttribute\('fill', '#ffffff'\)/);
});

test("clicking the pill dismisses on pointerdown (poll-redraw-safe) + optimistically drops the lane", () => {
  // pointerdown, not click: a poll rebuild between mousedown/up would eat a native click (as the toggles do)
  assert.match(SRC, /chit\.addEventListener\('pointerdown', \(e\) => \{[\s\S]*?this\._dismissLane\(s\.id\); this\.draw\(\);/);
  // optimistic: drop it from the current frame so it vanishes at once (the kernel push is authoritative)
  assert.match(SRC, /this\.data\.sessions = this\.data\.sessions\.filter\(\(x\) => x\.id !== s\.id\)/);
});

test("_dismissLane posts via the web-shell hook only (no persistence path)", () => {
  assert.match(SRC, /_dismissLane\(id\) \{[\s\S]*?window\.__rompTimelineDismiss === 'function'[\s\S]*?window\.__rompTimelineDismiss\(id\)/);
});
