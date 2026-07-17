// The hover rail band TRACES the rail's detour through an expanded tool-group (the user 2026-07-17 ×2:
// a straight run at one x beside indented dots read as confusion between the sub-rail and the main
// rail). A run whose bounding dots sit at different x's crosses a corner — the arm at the upper dot's
// turn-box bottom — and splits into an L: down the upper rail, along the arm, down the lower rail.
// Same-x runs and dotless clamps stay straight. Source pins + an executed replica of the run splitting.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");

test("railDotsBetween reports each dot's center x, not just y", () => {
  const fn = SRC.slice(SRC.indexOf("function railDotsBetween"), SRC.indexOf("function drawRailBand"));
  assert.match(fn, /Array<\{ el: HTMLElement; y: number; x: number \}>/);
  assert.match(fn, /const x = r\.left \+ r\.width \/ 2 - hostR\.left;/);
});

test("a cross-x run splits into an L at the corner (the upper dot's turn-box bottom)", () => {
  const fn = SRC.slice(SRC.indexOf("function drawRailBand"), SRC.indexOf("function clearRailRings"));
  assert.match(fn, /const upper = dots\[i - 1\] \?\? null;/);
  assert.match(fn, /const lower = dots\[i\] \?\? dots\[dots\.length - 1\] \?\? null;/);
  assert.match(fn, /if \(upper && lower && Math\.abs\(upper\.x - lower\.x\) > 1\)/);
  assert.match(fn, /upper\.el\.closest\("\.turn"\)/, "the corner y comes from the upper dot's turn box");
  assert.match(fn, /put\(upper\.x - 2, a, 4, cornerY - a\);/, "down the upper rail");
  assert.match(fn, /put\(Math\.min\(upper\.x, lower\.x\) - 2, cornerY - 2, Math\.abs\(upper\.x - lower\.x\) \+ 4, 4\);/, "along the arm");
  assert.match(fn, /put\(lower\.x - 2, cornerY, 4, b - cornerY\);/, "down the lower rail");
  // straight runs center on the lower dot (else the reference rail)
  assert.match(fn, /const lx = lower \? lower\.x : fallbackCx;/);
  assert.match(fn, /put\(lx - 2, a, 4, b - a\);/);
});

// Executed replica of drawRailBand's run loop (stops/clearance/L-split verbatim; cornerY injected in
// place of the DOM box lookup). Geometry of an expanded group: main rail center 11.5, sub-rail 35.5.
type Dot = { y: number; x: number; boxBottom?: number };
function bandRects(dots: Dot[], top: number, bottom: number, fallbackCx: number) {
  const CLEAR = 7;
  const out: Array<{ left: number; top: number; w: number; h: number }> = [];
  const put = (left: number, top_: number, w: number, h: number) => { if (w > 0 && h > 0) out.push({ left, top: top_, w, h }); };
  const stops = [top, ...dots.map((d) => d.y), bottom];
  for (let i = 0; i < stops.length - 1; i++) {
    const a = stops[i] + CLEAR, b = stops[i + 1] - CLEAR;
    if (b <= a) continue;
    const upper = dots[i - 1] ?? null;
    const lower = dots[i] ?? dots[dots.length - 1] ?? null;
    const lx = lower ? lower.x : fallbackCx;
    if (upper && lower && Math.abs(upper.x - lower.x) > 1) {
      const cornerY = upper.boxBottom != null ? upper.boxBottom - 1 : null;
      if (cornerY != null && cornerY > a && cornerY < b) {
        put(upper.x - 2, a, 4, cornerY - a);
        put(Math.min(upper.x, lower.x) - 2, cornerY - 2, Math.abs(upper.x - lower.x) + 4, 4);
        put(lower.x - 2, cornerY, 4, b - cornerY);
        continue;
      }
    }
    put(lx - 2, a, 4, b - a);
  }
  return out;
}

const MAIN = 11.5, CHILD = 35.5;

test("executed: the band goes in, down, and back — L runs at both corners, sub-rail in between", () => {
  // toolgroup dot (main, box ends at y 30 → the IN arm) → 3 children (sub-rail) → next main dot;
  // the last child's box ends at y 150 (→ the BACK arm)
  const dots: Dot[] = [
    { y: 15, x: MAIN, boxBottom: 30 },
    { y: 45, x: CHILD, boxBottom: 70 },
    { y: 85, x: CHILD, boxBottom: 110 },
    { y: 125, x: CHILD, boxBottom: 150 },
    { y: 175, x: MAIN },
  ];
  const rects = bandRects(dots, 15, 175, MAIN);
  // entry gap splits into 3 (upper vertical at MAIN, arm, lower vertical at CHILD)
  assert.deepEqual(rects[0], { left: MAIN - 2, top: 22, w: 4, h: 7 });                       // main rail down to the IN corner (29)
  assert.deepEqual(rects[1], { left: MAIN - 2, top: 27, w: CHILD - MAIN + 4, h: 4 });       // along the IN arm
  assert.deepEqual(rects[2], { left: CHILD - 2, top: 29, w: 4, h: 38 - 29 });               // sub-rail to the first child dot
  // the two mid-branch runs stay straight on the sub-rail
  assert.deepEqual(rects[3], { left: CHILD - 2, top: 52, w: 4, h: 26 });
  assert.deepEqual(rects[4], { left: CHILD - 2, top: 92, w: 4, h: 26 });
  // exit gap splits at the BACK corner (149): sub-rail down, arm back, main rail on to the next dot
  assert.deepEqual(rects[5], { left: CHILD - 2, top: 132, w: 4, h: 149 - 132 });
  assert.deepEqual(rects[6], { left: MAIN - 2, top: 147, w: CHILD - MAIN + 4, h: 4 });
  assert.deepEqual(rects[7], { left: MAIN - 2, top: 149, w: 4, h: 168 - 149 });
  assert.equal(rects.length, 8);
});

test("executed: an all-main-rail span stays straight — every run at the main x", () => {
  const dots: Dot[] = [{ y: 0, x: MAIN, boxBottom: 20 }, { y: 50, x: MAIN, boxBottom: 70 }, { y: 100, x: MAIN }];
  const rects = bandRects(dots, 0, 100, MAIN);
  assert.deepEqual(rects.map((r) => [r.left, r.w]), [[MAIN - 2, 4], [MAIN - 2, 4]]);
});

test("executed: no dots at all → the reference turn's rail x carries the run", () => {
  const rects = bandRects([], 0, 100, 11.5);
  assert.deepEqual(rects.map((r) => r.left), [9.5]);
});
