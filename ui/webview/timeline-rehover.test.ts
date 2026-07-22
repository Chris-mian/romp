// Message-connector tooltips must appear IMMEDIATELY (the user 2026-07-21). draw() wipes and rebuilds the
// whole SVG on every kernel push, so a connector the cursor is resting on comes back as a brand new
// element — and the browser fires mouseenter only when a pointer MOVES across a boundary, never for one
// that has sat still. So the tip never opened until the user happened to jiggle the mouse between
// rebuilds, which reads as a long random delay. _rehover() closes it: after the rebuild, hit-test the
// pointer position we already track and re-run the hover-in of whatever is under it. Event-based (keyed on
// the rebuild finishing + a real pointer position) — no timer, no hover-intent delay.
// Source pins + an executed replica of the re-hover walk.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js"), "utf8");

test("the pointer position is tracked on every move over the plot, and cleared when it leaves", () => {
  // recorded BEFORE the sweep's early-return, so it tracks even while no tip is shown (the whole point:
  // the tip that never opened is the one we need to restore)
  assert.match(SRC, /this\._onTipSweep = \(e\) => \{\n\s*this\._ptr = \{ x: e\.clientX, y: e\.clientY \};/);
  assert.match(SRC, /this\._onPtrOut = \(\) => \{ this\._ptr = null; \};/);
  assert.match(SRC, /this\.wrap\.addEventListener\('mouseleave', this\._onPtrOut\);/);
  assert.match(SRC, /removeEventListener\('mouseleave', this\._onPtrOut\)/, "torn down in destroy()");
});

test("draw() re-arms the hover it just swallowed, as its final act", () => {
  const draw = SRC.slice(SRC.indexOf("    this._drawLockToggle(svg, lockCx, axisY);"));
  assert.match(draw.slice(0, 400), /this\._rehover\(\);/, "_rehover runs after the rebuild completes");
});

test("_rehover no-ops while a tip is already up, and hit-tests in the SVG's own document", () => {
  const fn = SRC.slice(SRC.indexOf("  _rehover() {"), SRC.indexOf("  _rehover() {") + 900);
  // an open tip already holds the redraw off (draw()'s freeze) — nothing was swallowed, nothing to restore
  assert.match(fn, /this\.tip\.classList\.contains\('show'\)\) return;/);
  assert.match(fn, /this\.svg\.ownerDocument\.elementFromPoint\(p\.x, p\.y\)/, "pane-local coords, pane-local doc");
  assert.match(fn, /for \(let n = node; n && n !== this\.svg; n = n\.parentNode\)/, "walks up, stops at the svg");
  assert.match(fn, /n\.__tlHoverIn\(\{ clientX: p\.x, clientY: p\.y, currentTarget: n \}\)/);
});

test("the message connector line and the arrival dot both carry a re-armable hover-in", () => {
  // the connector line + its dot are ONE interactive unit, so BOTH halves must be restorable
  assert.match(SRC, /hit\.__tlHoverIn = mEnter;/, "connector path");
  assert.match(SRC, /hit\.addEventListener\('mouseenter', mEnter\);/, "same fn drives the real event");
  assert.match(SRC, /c\.__tlHoverIn = dEnter;/, "arrival dot");
  assert.match(SRC, /c\.addEventListener\('mouseenter', dEnter\);/);
});

test("no hover-intent delay was introduced anywhere in the show path", () => {
  // the fix must make tips appear SOONER; a debounce/delay here would be the opposite of the ask
  const show = SRC.slice(SRC.indexOf("  showTip(html, ev) {"), SRC.indexOf("  moveTip(ev) {"));
  assert.doesNotMatch(show, /setTimeout/, "showTip opens the tip synchronously");
});

// ── executed replica of _rehover's walk (verbatim control flow) ──
type Node = { __tlHoverIn?: (e: any) => void; parentNode?: Node | null };

function rehover(ptr: { x: number; y: number } | null, tipShown: boolean,
                 elementFromPoint: (x: number, y: number) => Node | null, svg: Node) {
  if (!ptr || tipShown) return null;
  const node = elementFromPoint(ptr.x, ptr.y);
  for (let n: Node | null | undefined = node; n && n !== svg; n = n.parentNode) {
    if (n.__tlHoverIn) { n.__tlHoverIn({ clientX: ptr.x, clientY: ptr.y, currentTarget: n }); return n; }
  }
  return null;
}

test("executed: a stationary cursor over a rebuilt connector gets its tooltip back", () => {
  const svg: Node = {};
  const opened: any[] = [];
  const connector: Node = { __tlHoverIn: (e) => opened.push(e), parentNode: svg };
  const hit = rehover({ x: 120, y: 40 }, false, () => connector, svg);
  assert.equal(hit, connector);
  assert.equal(opened.length, 1);
  assert.deepEqual({ x: opened[0].clientX, y: opened[0].clientY }, { x: 120, y: 40 },
    "the synthetic event carries the real pointer position, so the tip lands at the cursor");
  assert.equal(opened[0].currentTarget, connector, "showTip's _tipOwner resolves to the hit element");
});

test("executed: elementFromPoint landing on a child still finds the handler above it", () => {
  const svg: Node = {};
  const opened: any[] = [];
  const connector: Node = { __tlHoverIn: (e) => opened.push(e), parentNode: svg };
  const child: Node = { parentNode: connector };
  assert.equal(rehover({ x: 1, y: 2 }, false, () => child, svg), connector);
  assert.equal(opened.length, 1);
});

test("executed: an already-open tip is left alone (the redraw was frozen, nothing was swallowed)", () => {
  const svg: Node = {};
  let calls = 0;
  const connector: Node = { __tlHoverIn: () => calls++, parentNode: svg };
  assert.equal(rehover({ x: 1, y: 2 }, true, () => connector, svg), null);
  assert.equal(calls, 0, "never re-opens a tip that is already showing");
});

test("executed: a cursor that has left the plot re-hovers nothing", () => {
  const svg: Node = {};
  let calls = 0;
  const connector: Node = { __tlHoverIn: () => calls++, parentNode: svg };
  assert.equal(rehover(null, false, () => connector, svg), null);
  assert.equal(calls, 0);
});

test("executed: the walk stops at the svg root and never escapes to the page", () => {
  let calls = 0;
  const page: Node = { __tlHoverIn: () => calls++ };      // a handler ABOVE the svg must be ignored
  const svg: Node = { parentNode: page };
  const plain: Node = { parentNode: svg };                 // empty background region, no handler
  assert.equal(rehover({ x: 1, y: 2 }, false, () => plain, svg), null);
  assert.equal(calls, 0);
});

test("executed: hovering empty timeline background opens nothing", () => {
  const svg: Node = {};
  assert.equal(rehover({ x: 5, y: 5 }, false, () => null, svg), null);
});
