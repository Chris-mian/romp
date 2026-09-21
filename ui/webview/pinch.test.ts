// Executable geometry for the lightbox pinch-zoom (T162). The DOM/gesture wiring is pinned below;
// real pinch FEEL needs the phone — the user judges that; these pin the math that must never lie.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { identity, zoomAt, pan, clampPan, settle, doubleTapToggle, dist, midpoint,
         PINCH_MIN, PINCH_MAX, PINCH_SNAP, DOUBLE_TAP_SCALE, type PinchView } from "./pinch";

const contentAt = (v: PinchView, qx: number, qy: number) => ({ x: (qx - v.tx) / v.s, y: (qy - v.ty) / v.s });

test("the content point under the gesture midpoint stays under it through any zoom", () => {
  let v = identity();
  for (const [mx, my, f] of [[120, 80, 1.6], [40, 200, 2.0], [90, 90, 0.7], [10, 10, 3.0]] as const) {
    const before = contentAt(v, mx, my);
    v = zoomAt(v, mx, my, f);
    const after = contentAt(v, mx, my);
    assert.ok(Math.abs(before.x - after.x) < 1e-9 && Math.abs(before.y - after.y) < 1e-9,
      `midpoint invariance at s=${v.s.toFixed(2)}`);
  }
});

test("scale clamps to [1, 8] and the clamp keeps the midpoint invariant too", () => {
  const vMax = zoomAt(identity(), 50, 50, 100);
  assert.equal(vMax.s, PINCH_MAX);
  const vMin = zoomAt(vMax, 50, 50, 0.0001);
  assert.equal(vMin.s, PINCH_MIN);
  const before = contentAt(vMax, 50, 50);
  const after = contentAt(zoomAt(vMax, 50, 50, 100), 50, 50);
  assert.ok(Math.abs(before.x - after.x) < 1e-9, "a clamped zoom still pivots on the midpoint");
});

test("pan clamps: an over-scrolled edge never pulls inside the box; a fitting axis centers", () => {
  // content 100×100 at 4× = 400×400 in a 300×200 box
  const v: PinchView = { s: 4, tx: 50, ty: -500 };
  const c = clampPan(v, 100, 100, 300, 200);
  assert.equal(c.tx, 0, "left edge stops at the box edge");
  assert.equal(c.ty, 200 - 400, "bottom edge stops at the box edge");
  // content that FITS (1×) centers on both axes
  const f = clampPan({ s: 1, tx: -40, ty: 999 }, 100, 100, 300, 200);
  assert.deepEqual([f.tx, f.ty], [100, 50]);
});

test("a gesture ending near 1× settles exactly home; a real zoom survives", () => {
  assert.deepEqual(settle({ s: PINCH_SNAP - 0.01, tx: 3, ty: -2 }), identity());
  const kept = { s: 2, tx: -10, ty: -20 };
  assert.deepEqual(settle(kept), kept);
});

test("double-tap toggles: home → 2.5× around the tap; any zoom → home", () => {
  const z = doubleTapToggle(identity(), 60, 40);
  assert.equal(z.s, DOUBLE_TAP_SCALE);
  const under = contentAt(z, 60, 40);
  assert.ok(Math.abs(under.x - 60) < 1e-9 && Math.abs(under.y - 40) < 1e-9, "zooms around the tap point");
  assert.deepEqual(doubleTapToggle(z, 0, 0), identity());
});

test("pointer-pair helpers", () => {
  assert.equal(dist({ x: 0, y: 0 }, { x: 3, y: 4 }), 5);
  assert.deepEqual(midpoint({ x: 0, y: 0 }, { x: 10, y: 6 }), { x: 5, y: 3 });
});

test("the wiring: captured pointers, stage-owned gestures, and the close gesture untouched", () => {
  const PREVIEW = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "preview.ts"), "utf8");
  const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");
  assert.match(PREVIEW, /function wirePinchZoom\(stage: HTMLElement, img: HTMLImageElement\): \{ retarget: \(next: HTMLImageElement\) => void \}/);
  assert.match(PREVIEW, /stage\.setPointerCapture\(e\.pointerId\);/,
    "every gesture pointer is captured — a drag ending anywhere can never read as a backdrop tap");
  assert.match(PREVIEW, /wirePinchZoom\(inner, img\);/, "images only — the PDF branch is untouched");
  assert.match(PREVIEW, /wrap\.onclick = \(ev\) => \{ if \(ev\.target === wrap\) dismiss\(\); \};/,
    "dismissal stays tap-on-backdrop + the ✕, byte-identical");
  assert.match(PREVIEW, /closest\(".romp-lightbox-bar"\)/, "the bar's buttons own their taps");
  assert.match(CSS, /\.romp-lightbox-inner \{ touch-action: none; \}/,
    "the stage owns every touch gesture — the browser's page-zoom never fires here");
  assert.match(CSS, /transform-origin: 0 0; will-change: transform;/);
});
