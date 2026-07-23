// Sticky rail stamp (the user 2026-07-22). restampMarkers can only stamp at a turn boundary, so a single
// message taller than the viewport leaves the rail blank while you scroll through it. paintRailSticky pins
// the current turn's HH:MM at the top of the gutter and DEFERS — hides itself the instant ANY real timestamp
// is visible in the view (the tracked turn's own, a restamp-revealed neighbour, or the previous one still
// partially in view), so the sticky and a real marker never both show (the user 2026-07-23: a transient
// double-stamp during the scroll). There is always exactly one stamp visible, never two.
//
// The chat renderer has no jsdom harness, so — like the other render.ts tests — pin at the source, plus an
// executed replica of the pure selection + defer decision (the property most worth protecting).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("the sticky stamp is a fixed overlay on <body>, not a child of the swapped #content", () => {
  const fn = SRC.slice(SRC.indexOf("function ensureRailSticky"), SRC.indexOf("function paintRailSticky"));
  assert.match(fn, /el\("div", "time-marker rail-sticky"\)/, "carries the marker's type styling plus its own");
  assert.match(fn, /document\.body\.appendChild\(railSticky\)/, "lives on body so a #content rebuild can't destroy it");
  assert.match(fn, /railSticky\.isConnected/, "re-creates itself if it ever gets detached");
});

test("the defer condition: hide whenever ANY real timestamp is visible in the viewport", () => {
  const fn = SRC.slice(SRC.indexOf("function paintRailSticky"), SRC.indexOf("// Debounced rAF wrapper"));
  // the reading edge and the last turn at/above it (the tracked turn whose time the sticky would pin)
  assert.match(fn, /const fold = cTop \+ 2;/);
  assert.match(fn, /if \(t\.getBoundingClientRect\(\)\.top <= fold\) marker = m;/, "the turn spanning the top of the view");
  // a real timestamp is on screen: it RENDERS a time (suppressed same-minute = empty) and its glyph
  // intersects the content viewport — partial occlusion at the top edge (bottom > cTop) still counts
  assert.match(fn, /if \(m\.textContent\) \{/);
  assert.match(fn, /if \(r\.bottom > cTop && r\.top < cBottom\) \{ timedVisible = true; break; \}/);
  assert.match(fn, /if \(!hm \|\| timedVisible\) \{ stamp\.style\.display = "none"; return; \}/,
    "no time to pin, or a real stamp is already visible → the sticky steps aside");
  // positioned off #content's LIVE geometry each paint (it owns no layout inside the scroll)
  assert.match(fn, /stamp\.style\.top = \(cTop \+ 6\) \+ "px";/);
});

test("scroll drives it (passive, rAF-coalesced) and a resize re-measures it", () => {
  assert.match(SRC, /function scheduleRailSticky\(\): void \{[^}]*railStickyPending[^}]*requestAnimationFrame/s);
  assert.match(SRC, /addEventListener\("scroll", scheduleRailSticky, \{ passive: true \}\)/,
    "passive: it measures, never blocks the scroll it annotates");
  assert.match(SRC, /window\.addEventListener\("resize", scheduleRailSticky\)/);
  // the reveal pass can change which markers show a time, so the restamp rAF re-evaluates the sticky too
  assert.match(SRC, /if \(v\) restampMarkers\(v\.el\);\s*\n\s*paintRailSticky\(\);/);
});

test("the CSS pins it to the viewport, above the rail, click-through", () => {
  assert.match(CSS, /\.rail-sticky \{[^}]*position: fixed/s);
  assert.match(CSS, /\.rail-sticky \{[^}]*pointer-events: none/s, "a passive annotation never eats a click behind it");
});

// ── executed replica of the selection + defer decision ───────────────────────────────────────────────────
// Faithful to paintRailSticky: pick the last marker whose TURN starts at/above the fold (its hm is what the
// sticky would pin); then defer if ANY marker renders a time AND its glyph intersects the content viewport
// [cTop, cBottom]. A turn models {top} and its marker {hm, text, mTop, mBottom} in viewport coords.
type Marker = { hm: string; text: string; mTop: number; mBottom: number };
type Turn = { top: number; marker: Marker | null };
function decideSticky(turns: Turn[], cTop: number, cBottom: number): { show: boolean; hm: string } {
  const fold = cTop + 2;
  let marker: Marker | null = null;
  let timedVisible = false;
  for (const t of turns) {
    const m = t.marker;
    if (!m) continue;
    if (t.top <= fold) marker = m;
    if (m.text && m.mBottom > cTop && m.mTop < cBottom) { timedVisible = true; break; }
  }
  const hm = marker ? (marker.hm || "") : "";
  if (!hm || timedVisible) return { show: false, hm: "" };
  return { show: true, hm };
}

const CTOP = 100, CBOT = 700;   // #content spans [100, 700] in viewport space

test("executed: tall turn, its marker scrolled off and NO stamp on screen → the sticky shows its time", () => {
  // one message taller than the viewport; its marker is above #content, its own line renders no time
  const turns: Turn[] = [{ top: 40, marker: { hm: "09:12", text: "", mTop: 55, mBottom: 68 } }];
  assert.deepEqual(decideSticky(turns, CTOP, CBOT), { show: true, hm: "09:12" });
});

test("executed: the reported bug — a real stamp is visible just below → the sticky defers, no double", () => {
  // several short same-minute turns: the top turn's stamp is suppressed (empty), but a restamp-revealed
  // neighbour shows 12:02 at mTop 130 (well on screen). The sticky must NOT also show 12:02.
  const turns: Turn[] = [
    { top: 96, marker: { hm: "12:02", text: "", mTop: 111, mBottom: 124 } },     // tracked (at the fold), suppressed
    { top: 118, marker: { hm: "12:02", text: "12:02", mTop: 133, mBottom: 146 } }, // real stamp, on screen
  ];
  assert.deepEqual(decideSticky(turns, CTOP, CBOT), { show: false, hm: "" });
});

test("executed: partial occlusion — the previous stamp is half off the top but still readable → defer", () => {
  // its top is above cTop, its bottom still below cTop (bottom > cTop) → counts as visible, no double-stamp
  const turns: Turn[] = [{ top: 88, marker: { hm: "09:12", text: "09:12", mTop: 92, mBottom: 106 } }];
  assert.deepEqual(decideSticky(turns, CTOP, CBOT), { show: false, hm: "" });
});

test("executed: once the previous stamp fully scrolls off the top → the sticky steps in", () => {
  // bottom <= cTop: fully gone, nothing else timed on screen → the gap is real, fill it
  const turns: Turn[] = [{ top: 80, marker: { hm: "09:12", text: "09:12", mTop: 82, mBottom: 96 } }];
  assert.deepEqual(decideSticky(turns, CTOP, CBOT), { show: true, hm: "09:12" });
});

test("executed: it pins the LAST turn at/above the fold when nothing is timed-visible", () => {
  const turns: Turn[] = [
    { top: 20, marker: { hm: "09:10", text: "", mTop: 35, mBottom: 48 } },
    { top: 60, marker: { hm: "09:11", text: "", mTop: 75, mBottom: 88 } },   // the turn you're inside
    { top: 900, marker: { hm: "09:20", text: "09:20", mTop: 915, mBottom: 928 } }, // below the viewport, not visible
  ];
  assert.deepEqual(decideSticky(turns, CTOP, CBOT), { show: true, hm: "09:11" });
});

test("executed: nothing scrolled to the fold yet → no marker chosen, sticky hidden", () => {
  const turns: Turn[] = [{ top: 400, marker: { hm: "09:20", text: "09:20", mTop: 415, mBottom: 428 } }];
  assert.deepEqual(decideSticky(turns, CTOP, CBOT), { show: false, hm: "" });
});

test("executed property: sticky-visible IFF no real timestamp is on screen — never two", () => {
  const scenarios: Array<{ turns: Turn[]; stampOnScreen: boolean }> = [
    { turns: [{ top: 40, marker: { hm: "09:12", text: "", mTop: 55, mBottom: 68 } }], stampOnScreen: false },
    { turns: [{ top: 118, marker: { hm: "12:02", text: "12:02", mTop: 133, mBottom: 146 } }], stampOnScreen: true },
    { turns: [{ top: 88, marker: { hm: "09:12", text: "09:12", mTop: 92, mBottom: 106 } }], stampOnScreen: true },
  ];
  for (const s of scenarios) {
    const { show } = decideSticky(s.turns, CTOP, CBOT);
    assert.equal(show, !s.stampOnScreen, "the sticky fills in exactly when no real stamp is visible");
  }
});
