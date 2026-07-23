// Sticky rail stamp (the user 2026-07-22). restampMarkers can only stamp at a turn boundary, so a single
// message taller than the viewport leaves the rail blank while you scroll through it. paintRailSticky pins
// the current turn's HH:MM at the top of the gutter and HANDS OFF — hides itself the instant that turn's own
// marker is on screen showing a time — so there is always exactly one stamp visible, never two.
//
// The chat renderer has no jsdom harness, so — like the other render.ts tests — pin at the source, plus an
// executed replica of the pure selection + hand-off decision (the property most worth protecting).
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

test("the hand-off condition: hide when the turn's own marker is on screen AND showing a time", () => {
  const fn = SRC.slice(SRC.indexOf("function paintRailSticky"), SRC.indexOf("// Debounced rAF wrapper"));
  // the reading edge and the last turn at/above it
  assert.match(fn, /const fold = cTop \+ 2;/);
  assert.match(fn, /if \(top > fold\) break;/, "children are in document order; stop at the fold");
  assert.match(fn, /marker = m;/);
  // live = its own marker is on screen (>= cTop) AND actually renders a time (suppressed same-minute = empty)
  assert.match(fn, /const live = !!marker && !!marker\.textContent && marker\.getBoundingClientRect\(\)\.top >= cTop;/);
  assert.match(fn, /if \(!hm \|\| live\) \{ stamp\.style\.display = "none"; return; \}/,
    "no time to show, or the real marker already shows it → the sticky steps aside");
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

// ── executed replica of the selection + hand-off decision ────────────────────────────────────────────────
// Faithful to paintRailSticky: pick the last marker whose TURN starts at/above the fold; show its hm unless
// its own marker is on screen (markerTop >= cTop) AND non-empty. A turn models {top} and its marker
// {hm, text, markerTop}. cTop is #content's top in viewport space.
type Marker = { hm: string; text: string; markerTop: number };
type Turn = { top: number; marker: Marker | null };
function decideSticky(turns: Turn[], cTop: number): { show: boolean; hm: string } {
  const fold = cTop + 2;
  let marker: Marker | null = null;
  let anyMarker: Marker | null = null;
  for (const t of turns) {
    const m = t.marker;
    if (!m) continue;
    if (!anyMarker) anyMarker = m;
    if (t.top > fold) break;
    marker = m;
  }
  const hm = marker ? (marker.hm || "") : "";
  const live = !!marker && !!marker.text && marker.markerTop >= cTop;
  if (!hm || live) return { show: false, hm: "" };
  return { show: true, hm };
}

const CTOP = 100;

test("executed: scrolling through a tall turn whose marker went off-screen → the sticky shows its time", () => {
  // one message taller than the viewport; its marker scrolled above #content, its own line renders no time
  const turns: Turn[] = [{ top: 40, marker: { hm: "09:12", text: "", markerTop: 55 } }];
  assert.deepEqual(decideSticky(turns, CTOP), { show: true, hm: "09:12" });
});

test("executed: hand-off — once the turn's own marker is on screen showing a time, the sticky hides", () => {
  const turns: Turn[] = [{ top: 120, marker: { hm: "09:12", text: "09:12", markerTop: 135 } }];
  assert.deepEqual(decideSticky(turns, CTOP), { show: false, hm: "" });
});

test("executed: a marker showing a time but scrolled ABOVE the fold is not 'live' → the sticky covers it", () => {
  // text present but off-screen up top: the rail looks blank, so the sticky must still step in
  const turns: Turn[] = [{ top: 40, marker: { hm: "09:12", text: "09:12", markerTop: 55 } }];
  assert.deepEqual(decideSticky(turns, CTOP), { show: true, hm: "09:12" });
});

test("executed: it tracks the LAST turn at/above the fold, not the first", () => {
  const turns: Turn[] = [
    { top: 20, marker: { hm: "09:10", text: "", markerTop: 35 } },
    { top: 60, marker: { hm: "09:11", text: "", markerTop: 75 } },   // this one is the turn you're inside
    { top: 400, marker: { hm: "09:20", text: "09:20", markerTop: 415 } }, // still below the fold
  ];
  assert.deepEqual(decideSticky(turns, CTOP), { show: true, hm: "09:11" });
});

test("executed: nothing scrolled to the fold yet → no marker chosen, sticky hidden", () => {
  const turns: Turn[] = [{ top: 400, marker: { hm: "09:20", text: "09:20", markerTop: 415 } }];
  assert.deepEqual(decideSticky(turns, CTOP), { show: false, hm: "" });
});

test("executed property: exactly one stamp is ever visible — never two, never zero-with-a-time-available", () => {
  // Across the whole scroll, sticky-visible XOR own-marker-visible-with-time holds for the tracked turn.
  const scenarios: Array<{ turns: Turn[]; ownVisibleWithTime: boolean }> = [
    { turns: [{ top: 40, marker: { hm: "09:12", text: "", markerTop: 55 } }], ownVisibleWithTime: false },
    { turns: [{ top: 120, marker: { hm: "09:12", text: "09:12", markerTop: 135 } }], ownVisibleWithTime: true },
    { turns: [{ top: 40, marker: { hm: "09:12", text: "09:12", markerTop: 55 } }], ownVisibleWithTime: false },
  ];
  for (const s of scenarios) {
    const { show } = decideSticky(s.turns, CTOP);
    assert.equal(show, !s.ownVisibleWithTime, "the sticky fills in exactly when the real marker doesn't");
  }
});
