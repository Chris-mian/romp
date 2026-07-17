// The hover rail band FOLLOWS the rail's detour through an expanded tool-group (the user 2026-07-17:
// with the branch indent restored, one fixed x couldn't highlight everything properly — band runs next
// to indented children floated off their sub-rail). Each inter-dot run now hugs the x of the dot at its
// LOWER edge: descending INTO the branch → the sub-rail x (with the child dots), leaving it → back to
// the main rail x (whose pass-through line runs behind the branch). Source pins + an executed replica
// of the per-run x selection.
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

test("each band run centers on its lower-edge dot's x; dotless runs fall back to the reference rail", () => {
  const fn = SRC.slice(SRC.indexOf("function drawRailBand"), SRC.indexOf("function clearRailRings"));
  assert.match(fn, /const lower = dots\[i\] \?\? dots\[dots\.length - 1\];/);
  assert.match(fn, /band\.style\.left = `\$\{lower \? lower\.x - 1 : fallbackLeft\}px`;/);
  assert.match(fn, /const fallbackLeft = xRef\.getBoundingClientRect\(\)\.left - hostR\.left \+ 10\.5;/);
  // the old single-x band (every run at the reference turn's rail) is gone
  assert.doesNotMatch(fn, /band\.style\.left = left;/);
});

// Executed replica of drawRailBand's run loop (stops/clearance/lower-dot selection verbatim), fed the
// geometry of an expanded group: main dots at x 11.5, three indented children at x 35.5.
function bandRuns(dots: Array<{ y: number; x: number }>, top: number, bottom: number, fallbackLeft: number) {
  const CLEAR = 7;
  const stops = [top, ...dots.map((d) => d.y), bottom];
  const out: Array<{ left: number; top: number; height: number }> = [];
  for (let i = 0; i < stops.length - 1; i++) {
    const a = stops[i] + CLEAR, b = stops[i + 1] - CLEAR;
    if (b <= a) continue;
    const lower = dots[i] ?? dots[dots.length - 1];
    out.push({ left: lower ? lower.x - 1 : fallbackLeft, top: a, height: b - a });
  }
  return out;
}

test("executed: the band detours onto the sub-rail with the children and returns on the main rail", () => {
  const MAIN = 11.5, CHILD = 35.5;
  // toolgroup dot (main) → 3 children (sub-rail) → next main dot; top/bottom clamp to the boundary dots
  const dots = [
    { y: 0, x: MAIN },      // the group's own dot
    { y: 40, x: CHILD },
    { y: 80, x: CHILD },
    { y: 120, x: CHILD },
    { y: 160, x: MAIN },    // first dot after the group
  ];
  const runs = bandRuns(dots, 0, 160, MAIN - 1);
  assert.equal(runs.length, 4);
  assert.deepEqual(runs.map((r) => r.left), [CHILD - 1, CHILD - 1, CHILD - 1, MAIN - 1],
    "runs into + along the branch hug the sub-rail; the run leaving it hugs the main rail");
});

test("executed: an all-main-rail span is unchanged — every run at the main x", () => {
  const MAIN = 11.5;
  const dots = [{ y: 0, x: MAIN }, { y: 50, x: MAIN }, { y: 100, x: MAIN }];
  const runs = bandRuns(dots, 0, 100, MAIN - 1);
  assert.deepEqual(runs.map((r) => r.left), [MAIN - 1, MAIN - 1]);
});

test("executed: no dots at all → the reference turn's rail x carries the run", () => {
  const runs = bandRuns([], 0, 100, 10.5);
  assert.deepEqual(runs.map((r) => r.left), [10.5]);
});
