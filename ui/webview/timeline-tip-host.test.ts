// Timeline tooltips must not clip at the pane edge (the user 2026-07-17: tips popped too high/low and
// got cut off). Two layers: (1) the tip ADOPTS the topmost same-origin document as its host, so in the
// multi-pane web dashboard it overlays the sibling panes (chat, feed) instead of clipping at a short
// timeline iframe — cross-origin parents (the VS Code webview host) fall back to the local document via
// try/catch; (2) moveTip flips against the HOST viewport and finally CLAMPS, so even the local-document
// fallback pins to an edge rather than rendering off-screen. Source pins + an executed replica of the
// placement math.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js"), "utf8");

test("the tip adopts the topmost same-origin document, guarded for cross-origin parents", () => {
  assert.match(SRC, /this\._tipWin = window;/);
  assert.match(SRC, /while \(this\._tipWin\.parent && this\._tipWin\.parent !== this\._tipWin && this\._tipWin\.parent\.document\) this\._tipWin = this\._tipWin\.parent;/);
  // creation targets the adopted document (never a bare document.body.createDiv)
  assert.match(SRC, /this\.tip = tipDoc\.createElement\('div'\); this\.tip\.className = 'romp-tl-tip'; tipDoc\.body\.appendChild\(this\.tip\);/);
  assert.doesNotMatch(SRC, /document\.body\.createDiv\(\{ cls: 'romp-tl-tip' \}\)/);
});

test("adopting a foreign host carries the tip styles over from OUR stylesheets (one source of truth)", () => {
  assert.match(SRC, /tipDoc\.getElementById\('romp-tl-tip-css'\)/, "injected once, id-guarded");
  assert.match(SRC, /r\.selectorText\.indexOf\('\.romp-tl-tip'\) === 0/, "copied by selector prefix, not duplicated literals");
});

test("an iframe teardown removes the tip from the adopted host document", () => {
  assert.match(SRC, /if \(tipDoc !== document\) window\.addEventListener\('pagehide', \(\) => \{ try \{ this\.tip\.remove\(\); \} catch \(e\) \{\} \}\);/);
});

test("moveTip translates pane-local pointer coords by the intervening iframe offsets", () => {
  const fn = SRC.slice(SRC.indexOf("  moveTip(ev) {"), SRC.indexOf("  hideTip() {"));
  assert.match(fn, /for \(let w = window; w !== this\._tipWin && w\.frameElement; w = w\.parent\)/);
  assert.match(fn, /const fr = w\.frameElement\.getBoundingClientRect\(\); px \+= fr\.left; py \+= fr\.top;/);
  assert.match(fn, /hw = this\._tipWin\.innerWidth; hh = this\._tipWin\.innerHeight;/, "flip/clamp against the HOST viewport");
  assert.match(fn, /lx = Math\.max\(0, Math\.min\(lx, hw - r\.width\)\); ly = Math\.max\(0, Math\.min\(ly, hh - r\.height\)\);/, "final on-screen clamp");
});

// Executed replica of moveTip's placement math (pad/flip/clamp verbatim).
function placeTip(px: number, py: number, hw: number, hh: number, w: number, h: number) {
  const pad = 14;
  let lx = px + pad, ly = py + pad;
  if (lx + w > hw) lx = px - w - pad;
  if (ly + h > hh) ly = py - h - pad;
  lx = Math.max(0, Math.min(lx, hw - w)); ly = Math.max(0, Math.min(ly, hh - h));
  return { lx, ly };
}

test("executed: a flip that overshoots the top edge clamps to 0 instead of clipping", () => {
  // mid-window pointer, tall tip: below overflows, the flip above overshoots negative — old code
  // rendered it at -64 and the top clipped; the clamp pins it at the edge, fully visible
  const p = placeTip(50, 100, 800, 200, 300, 150);
  assert.equal(p.ly, 0);
});

test("executed: a roomy host viewport means no flip at the pane's edge at all", () => {
  // same pointer y, but the adopted host is tall (the dashboard page): the tip simply renders below,
  // overlaying whatever pane sits there
  const p = placeTip(50, 100, 800, 1000, 300, 150);
  assert.equal(p.ly, 114);
});

test("executed: right-edge flip still works, then clamps within the host", () => {
  const p = placeTip(790, 20, 800, 600, 300, 100);
  assert.equal(p.lx, 790 - 300 - 14);
  assert.equal(p.ly, 34);
});
