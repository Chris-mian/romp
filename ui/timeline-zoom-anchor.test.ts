// Pinch-zoom must stay anchored on the TIME UNDER THE CURSOR, so you can hover a thing and pinch, pinch,
// pinch to expand into it (the user 2026-07-21: "it looks like it's fixing the leftmost coordinate").
//
// Why it drifted: the anchor was computed in COMPRESSED seconds, but the compressed axis is not a fixed
// coordinate system. Collapsed idle gaps are `gapCT = winSec * GAP_FRAC` wide, so EVERY zoom step rescales
// the whole axis, and _buildCompressMap pins its origin at the FIRST collapsed gap (near the start of
// history). onWheel pinned `cc` under the old map, then draw() rebuilt the map at the new window and read
// that offset under the new one, so the zoom's true fixed point sat near the compressed origin at the far
// left rather than under the cursor. The fix anchors in REAL time and re-derives the offset under the map
// the next draw will build.
//
// These tests EXECUTE the real onWheel/onTouch* against the real draw(), with a compress map that actually
// has gaps in it — the drift is invisible without them.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as path from "node:path";
import { createRequire } from "node:module";

// ---- minimal DOM shim (same shape as timeline-render.test.ts) ----
function makeNode(tag: string): any {
  const n: any = {
    tag, _attrs: {}, children: [] as any[], style: {}, dataset: {}, textContent: "", parentNode: null,
    classList: { _s: new Set<string>(), add(...a: string[]) { a.forEach((c) => this._s.add(c)); },
      remove(...a: string[]) { a.forEach((c) => this._s.delete(c)); },
      toggle(c: string, f?: boolean) { f ? this._s.add(c) : this._s.delete(c); }, contains(c: string) { return this._s.has(c); } },
    setAttribute(k: string, v: any) { this._attrs[k] = v; }, getAttribute(k: string) { return this._attrs[k]; },
    setAttributeNS(_n: any, k: string, v: any) { this._attrs[k] = v; }, removeAttribute(k: string) { delete this._attrs[k]; },
    appendChild(c: any) { c.parentNode = n; this.children.push(c); return c; },
    insertBefore(c: any, ref: any) { c.parentNode = n; const i = this.children.indexOf(ref); i < 0 ? this.children.push(c) : this.children.splice(i, 0, c); return c; },
    removeChild(c: any) { const i = this.children.indexOf(c); if (i >= 0) this.children.splice(i, 1); return c; },
    get firstChild() { return this.children[0] || null; },
    addEventListener() {}, removeEventListener() {}, querySelector() { return null; }, querySelectorAll() { return []; },
    getBoundingClientRect() { return { width: 1400, height: 420, left: 0, top: 0, right: 1400, bottom: 420 }; },
    closest() { return null; }, focus() {},
    createEl(t: string, o: any) { const e = makeNode(t); if (o && o.cls) e.classList.add(o.cls); if (o && o.text) e.textContent = o.text; this.appendChild(e); return e; },
    createDiv(o: any) { return this.createEl("div", o); }, createSpan(o: any) { return this.createEl("span", o); },
  };
  return n;
}
const g: any = global;
g.document = {
  createElement(t: string) { return t === "canvas" ? { getContext() { return { font: "", measureText(s: string) { return { width: (s ? s.length : 0) * 6 }; } }; } } : makeNode(t); },
  createElementNS(_n: any, t: string) { return makeNode(t); },
  body: makeNode("body"), documentElement: makeNode("html"), head: makeNode("head"),
  getElementById() { return null; }, addEventListener() {}, removeEventListener() {},
};
g.localStorage = { getItem() { return null; }, setItem() {}, removeItem() {} };
g.getComputedStyle = () => ({ backgroundColor: "rgb(30,30,30)" });
g.requestAnimationFrame = () => 0;
g.addEventListener = () => {}; g.removeEventListener = () => {};
g.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
g.window = g;
g.innerWidth = 1400; g.innerHeight = 800;

const viewPath = path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js");
const { TimelinePanel } = createRequire(__filename)(viewPath);

const NOW = 1_781_000_000;
const HOUR = 3600;

// Work in three bursts separated by LONG idle gaps, so the broken-axis compress map is non-trivial:
// two collapsed gaps sit inside the window, which is exactly what made the compressed axis rescale
// under the zoom. Without gaps, compress() is the identity and the bug cannot reproduce.
function gappyData() {
  const turn = (id: string, start: number, end: number) => ({
    id, promptId: id + "#p", workId: id + "#w", start, end,
    prompt: "do the thing", src: "typed", mids: [], pending: false,
    summary: "did the thing", reply: "did it", tid: "fork-" + id, uuid: "u-" + id,
    workUuid: "w-" + id, replyUuid: "r-" + id,
  });
  const sess = (id: string, name: string) => ({
    id, name, color: "#7aa2f7", state: "working", live: true, model: "Opus 4.8", effort: "xhigh",
    context: 40, since: NOW - 60, awaiting: [], compacting: [], pendingMail: 0, compactions: [], faded: false, stale: false,
  });
  return {
    now: NOW,
    sessions: [sess("S1", "alpha")],
    turns: {
      S1: [
        turn("S1:1:aa", NOW - 11 * HOUR, NOW - 10 * HOUR),   // burst 1
        turn("S1:2:bb", NOW - 6 * HOUR, NOW - 5 * HOUR),     // burst 2 (after a ~4h idle gap)
        turn("S1:3:cc", NOW - 1 * HOUR, NOW - 30 * 60),      // burst 3 (after another ~4h gap)
      ],
    },
    messages: [], activeChat: null, focus: null, hover: null, usage: null,
  };
}

function mkPanel(win: number, off = 0) {
  const panel: any = new TimelinePanel(makeNode("div"));
  panel.data = gappyData();
  panel._collapseGaps = true;      // broken axis ON (the default) — this is what rescales under zoom
  panel._winSec = win;
  panel._offSec = off;
  panel._pinned = off <= 0;        // pinned (right edge glued to now) only when there's no offset
  panel._offDirty = true;          // honor the offset we just wrote on this frame
  panel.draw();
  return panel;
}

/** The REAL time sitting at fraction `frac` across the plot, read off the geometry draw() just built. */
function timeAt(panel: any, frac: number): number {
  const g2 = panel._geom;
  return g2.decompress(g2.cT0 + frac * g2.winSec);
}

/** The clientX that lands at `frac` across the plot (the shim's rect is 1400px wide at left:0). */
function xAt(panel: any, frac: number): number {
  const g2 = panel._geom;
  const rect = panel.svg.getBoundingClientRect();
  const scaleX = g2.W / rect.width;
  return rect.left + (g2.ml + frac * g2.plotW) / scaleX;
}

function pinch(panel: any, frac: number, deltaY: number) {
  panel.onWheel({ ctrlKey: true, deltaX: 0, deltaY, clientX: xAt(panel, frac), clientY: 200,
                  preventDefault() {} });
  panel.draw();
}

test("one pinch step keeps the time under the cursor under the cursor", () => {
  const panel = mkPanel(8 * HOUR);
  const frac = 0.7;
  const before = timeAt(panel, frac);
  pinch(panel, frac, -40);                    // deltaY<0 → zoom IN
  assert.ok(panel.winSec() < 8 * HOUR, "the pinch must actually zoom in");
  const after = timeAt(panel, frac);
  // tolerance: one plot pixel's worth of real time, generously rounded (the offset is stored in whole
  // seconds, and a collapsed gap maps many real seconds onto one compressed second)
  const tol = Math.max(60, panel.winSec() * 0.02);
  assert.ok(Math.abs(after - before) < tol,
    `cursor anchor drifted ${Math.round(Math.abs(after - before))}s on one step (tol ${Math.round(tol)}s)`);
});

test("pinch, pinch, pinch expands INTO the hovered spot — drift does not accumulate", () => {
  // the user's actual gesture: hold the cursor still over something and keep pinching
  const panel = mkPanel(12 * HOUR);
  const frac = 0.62;
  const target = timeAt(panel, frac);
  for (let i = 0; i < 6; i++) pinch(panel, frac, -40);
  assert.ok(panel.winSec() < 6 * HOUR, "six pinch steps should zoom in substantially");
  const after = timeAt(panel, frac);
  const tol = Math.max(60, panel.winSec() * 0.05);
  assert.ok(Math.abs(after - target) < tol,
    `after 6 pinches the hovered instant drifted ${Math.round(Math.abs(after - target))}s (tol ${Math.round(tol)}s)`);
});

test("the zoom's fixed point is the CURSOR, not the left edge (the reported symptom)", () => {
  // With the cursor near the right, the LEFT edge must move (it should sweep toward the cursor). The old
  // compressed-time anchor left the left edge nearly parked, which is what "fixing the leftmost
  // coordinate" looked like on screen.
  const panel = mkPanel(12 * HOUR);
  const frac = 0.85;
  const leftBefore = timeAt(panel, 0), cursorBefore = timeAt(panel, frac);
  for (let i = 0; i < 4; i++) pinch(panel, frac, -40);
  const leftAfter = timeAt(panel, 0), cursorAfter = timeAt(panel, frac);
  const cursorMoved = Math.abs(cursorAfter - cursorBefore);
  const leftMoved = Math.abs(leftAfter - leftBefore);
  assert.ok(leftMoved > cursorMoved * 10,
    `zooming in at frac ${frac} must move the left edge far more than the cursor's instant ` +
    `(left moved ${Math.round(leftMoved)}s, cursor moved ${Math.round(cursorMoved)}s)`);
});

test("zooming OUT is anchored at the cursor too", () => {
  // panned back off the live edge, so the window has room to grow to the RIGHT as well as the left
  const panel = mkPanel(2 * HOUR, 5 * HOUR);
  const frac = 0.35;
  const before = timeAt(panel, frac);
  for (let i = 0; i < 3; i++) pinch(panel, frac, 40);    // deltaY>0 → zoom OUT
  assert.ok(panel.winSec() > 2 * HOUR, "the pinch must actually zoom out");
  const after = timeAt(panel, frac);
  const tol = Math.max(60, panel.winSec() * 0.05);
  assert.ok(Math.abs(after - before) < tol,
    `zoom-out drifted ${Math.round(Math.abs(after - before))}s (tol ${Math.round(tol)}s)`);
});

test("zooming OUT at the live edge stops at now instead of scrolling into the future", () => {
  // The one place the cursor anchor CAN'T hold, and it's a real constraint, not drift: with the right
  // edge already at `now`, holding a cursor left of it would push the window past now. The offset clamps
  // at 0, so the window grows leftward and the hovered instant slides left. Pinned so it stays honest.
  const panel = mkPanel(2 * HOUR);
  assert.equal(panel.offSec(), 0, "starts at the live edge");
  for (let i = 0; i < 3; i++) pinch(panel, 0.35, 40);
  assert.ok(panel.winSec() > 2 * HOUR, "it still zooms out");
  assert.equal(panel.offSec(), 0, "…and the right edge stays at now — never past it");
});

test("a pinch at the far right edge holds the right edge; at the far left holds the left edge", () => {
  for (const frac of [0, 1]) {
    const panel = mkPanel(8 * HOUR);
    const before = timeAt(panel, frac);
    pinch(panel, frac, -40);
    const after = timeAt(panel, frac);
    const tol = Math.max(60, panel.winSec() * 0.02);
    assert.ok(Math.abs(after - before) < tol,
      `frac ${frac} must be the fixed point; drifted ${Math.round(Math.abs(after - before))}s`);
  }
});

test("collapse OFF (plain linear axis) is anchored at the cursor as well", () => {
  // guards the identity-compress path, so the fix can't accidentally depend on a map existing
  const panel: any = new TimelinePanel(makeNode("div"));
  panel.data = gappyData();
  panel._collapseGaps = false;
  panel._winSec = 8 * HOUR; panel._offSec = 0;
  panel.draw();
  const frac = 0.4;
  const before = timeAt(panel, frac);
  for (let i = 0; i < 4; i++) pinch(panel, frac, -40);
  const after = timeAt(panel, frac);
  assert.ok(Math.abs(after - before) < Math.max(60, panel.winSec() * 0.02),
    `linear-axis pinch drifted ${Math.round(Math.abs(after - before))}s`);
});

test("a TOUCH pinch is anchored at the two-finger midpoint across the whole gesture", () => {
  // the touch gesture pins its anchor ONCE at touchstart and reuses it for every move, so a stale
  // compressed anchor drifts even harder there than on the trackpad
  const panel = mkPanel(12 * HOUR);
  const frac = 0.66;
  const target = timeAt(panel, frac);
  const cx = xAt(panel, frac);
  const t = (x: number) => ({ clientX: x, clientY: 200 });
  panel.onTouchStart({ touches: [t(cx - 60), t(cx + 60)], preventDefault() {} });
  for (const spread of [160, 260, 420, 700]) {          // fingers spreading → zoom in
    panel.onTouchMove({ touches: [t(cx - spread / 2), t(cx + spread / 2)], preventDefault() {} });
    panel.draw();
  }
  panel.onTouchEnd({ touches: [], preventDefault() {} });
  panel.draw();
  assert.ok(panel.winSec() < 6 * HOUR, "spreading the fingers must zoom in");
  const after = timeAt(panel, frac);
  const tol = Math.max(60, panel.winSec() * 0.05);
  assert.ok(Math.abs(after - target) < tol,
    `touch pinch drifted ${Math.round(Math.abs(after - target))}s (tol ${Math.round(tol)}s)`);
});

test("a pinch over the LANE GUTTER is ignored (the controls there own the gesture)", () => {
  const panel = mkPanel(8 * HOUR);
  const win = panel.winSec(), off = panel.offSec();
  let prevented = false;
  panel.onWheel({ ctrlKey: true, deltaX: 0, deltaY: -40, clientX: 2, clientY: 200,
                  preventDefault() { prevented = true; } });
  assert.equal(prevented, false, "the gutter gesture must fall through, not preventDefault");
  assert.equal(panel.winSec(), win);
  assert.equal(panel.offSec(), off);
});
