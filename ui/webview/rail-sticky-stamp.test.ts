// Sticky rail stamp (the user 2026-07-22). restampMarkers can only stamp at a turn boundary, so a single
// message taller than the viewport leaves the rail blank while you scroll through it. paintRailSticky keeps a
// stamp in the top slot at a fixed buffer line (cTop + 6). A real marker LEADS while its top is at or below
// that line; the instant it crosses ABOVE the line the sticky takes the slot — same position, same time — and
// the crossed marker is hidden. So the hand-off is seamless: no gap where the slot goes empty, and no clipped
// duplicate sliding past (the user 2026-07-23). Exactly one stamp sits at the line at all times.
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

test("the hand-off happens at the buffer line, with the crossed marker hidden", () => {
  const fn = SRC.slice(SRC.indexOf("function paintRailSticky"), SRC.indexOf("// Debounced rAF wrapper"));
  // the buffer line doubles as the sticky's rest position AND the hand-off threshold
  assert.match(fn, /const BUFFER = 6;/);
  assert.match(fn, /const line = cTop \+ BUFFER;/);
  assert.match(fn, /if \(t\.getBoundingClientRect\(\)\.top <= line\) marker = m;/, "the turn whose content sits at the line");
  // a real stamp LEADS while the topmost visible one is at or below the line; sticky takes over once it crosses
  assert.match(fn, /leadTop = r\.top;/);
  assert.match(fn, /const realLeads = leadTop !== null && leadTop >= line;/);
  assert.match(fn, /if \(!hm \|\| realLeads\) \{/);
  // when the sticky leads, every marker that crossed ABOVE the line is hidden so no clipped duplicate shows
  assert.match(fn, /for \(const \[m, top\] of all\) m\.style\.visibility = top < line \? "hidden" : "";/);
  // and it rests exactly at the line
  assert.match(fn, /stamp\.style\.top = line \+ "px";/);
  // ...while a real stamp leading means nothing is suppressed
  assert.match(fn, /for \(const \[m\] of all\) m\.style\.visibility = "";/);
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
// Faithful to paintRailSticky: line = cTop + BUFFER; marker = last turn whose top <= line (its time sits at
// the line); leadTop = the topmost timed marker still on screen (mBottom > cTop, mTop < cBottom). A real stamp
// LEADS while leadTop >= line; otherwise the sticky leads at the line and every marker with mTop < line is
// hidden. A turn models {top} and its marker {id, hm, text, mTop, mBottom} in viewport coords.
const BUFFER = 6;
type Marker = { id: string; hm: string; text: string; mTop: number; mBottom: number };
type Turn = { top: number; marker: Marker | null };
function decideSticky(turns: Turn[], cTop: number, cBottom: number): { show: boolean; hm: string; hidden: string[] } {
  const line = cTop + BUFFER;
  let marker: Marker | null = null;
  let leadTop: number | null = null;
  const all: Marker[] = [];
  for (const t of turns) {
    const m = t.marker;
    if (!m) continue;
    if (t.top <= line) marker = m;
    all.push(m);
    if (m.text && leadTop === null && m.mBottom > cTop && m.mTop < cBottom) leadTop = m.mTop;
  }
  const hm = marker ? (marker.hm || "") : "";
  const realLeads = leadTop !== null && leadTop >= line;
  if (!hm || realLeads) return { show: false, hm: "", hidden: [] };
  // the code hides EVERY marker with top < line (so a straggler resets when it scrolls back); only the TIMED
  // ones are visually meaningful, so the replica reports those — hiding an empty same-minute marker is a no-op
  return { show: true, hm, hidden: all.filter((m) => m.text && m.mTop < line).map((m) => m.id) };
}

const CTOP = 100, CBOT = 700, LINE = CTOP + BUFFER;   // #content spans [100, 700]; the line sits at 106

test("executed: tall turn, no stamp on screen → the sticky leads, showing its time", () => {
  const turns: Turn[] = [{ top: 40, marker: { id: "a", hm: "09:12", text: "", mTop: 55, mBottom: 68 } }];
  assert.deepEqual(decideSticky(turns, CTOP, CBOT), { show: true, hm: "09:12", hidden: [] });
});

test("executed: a real stamp resting BELOW the line leads — the sticky stays hidden (no double)", () => {
  // the reported earlier double: a revealed same-minute neighbour sits at mTop 133 (>= line 106). No sticky.
  const turns: Turn[] = [
    { top: 96, marker: { id: "top", hm: "12:02", text: "", mTop: 111, mBottom: 124 } },
    { top: 118, marker: { id: "nb", hm: "12:02", text: "12:02", mTop: 133, mBottom: 146 } },
  ];
  assert.deepEqual(decideSticky(turns, CTOP, CBOT), { show: false, hm: "", hidden: [] });
});

test("executed: the moment a stamp crosses ABOVE the line, the sticky takes over and hides it (eager)", () => {
  // mTop 102 is above the line (106) but still on screen — the previous rule left the slot empty here; now
  // the sticky pins at the line with the same time and the crossed marker is hidden. No gap, no clipped sliver.
  const turns: Turn[] = [{ top: 90, marker: { id: "x", hm: "09:12", text: "09:12", mTop: 102, mBottom: 115 } }];
  assert.deepEqual(decideSticky(turns, CTOP, CBOT), { show: true, hm: "09:12", hidden: ["x"] });
});

test("executed: at the line exactly, the real stamp still leads — hand-off is one-sided", () => {
  const turns: Turn[] = [{ top: 92, marker: { id: "x", hm: "09:12", text: "09:12", mTop: LINE, mBottom: LINE + 13 } }];
  assert.deepEqual(decideSticky(turns, CTOP, CBOT), { show: false, hm: "", hidden: [] });
});

test("executed: a partially-clipped stamp at the very top is hidden and covered by the sticky", () => {
  // mTop 96 < cTop 100: half off the top, clipped — exactly the ugly sliver. The sticky covers it.
  const turns: Turn[] = [{ top: 82, marker: { id: "x", hm: "09:12", text: "09:12", mTop: 96, mBottom: 109 } }];
  assert.deepEqual(decideSticky(turns, CTOP, CBOT), { show: true, hm: "09:12", hidden: ["x"] });
});

test("executed: sticky leads at top, a genuine lower stamp stays visible — only the crossed one hides", () => {
  const turns: Turn[] = [
    { top: 88, marker: { id: "crossed", hm: "09:12", text: "09:12", mTop: 100, mBottom: 113 } }, // above line → hidden
    { top: 300, marker: { id: "lower", hm: "09:15", text: "09:15", mTop: 315, mBottom: 328 } },   // below → stays
  ];
  const r = decideSticky(turns, CTOP, CBOT);
  assert.equal(r.show, true);
  assert.deepEqual(r.hidden, ["crossed"], "the lower real stamp is not a double, so it is not hidden");
});

test("executed: it pins the LAST turn whose top is at/above the line when the sticky leads", () => {
  const turns: Turn[] = [
    { top: 20, marker: { id: "a", hm: "09:10", text: "", mTop: 35, mBottom: 48 } },
    { top: 60, marker: { id: "b", hm: "09:11", text: "", mTop: 75, mBottom: 88 } },   // last with top <= line
    { top: 900, marker: { id: "c", hm: "09:20", text: "09:20", mTop: 915, mBottom: 928 } }, // off-screen below
  ];
  assert.deepEqual(decideSticky(turns, CTOP, CBOT).hm, "09:11");
});

test("executed: nothing scrolled to the line yet → no marker chosen, sticky hidden", () => {
  const turns: Turn[] = [{ top: 400, marker: { id: "a", hm: "09:20", text: "09:20", mTop: 415, mBottom: 428 } }];
  assert.deepEqual(decideSticky(turns, CTOP, CBOT), { show: false, hm: "", hidden: [] });
});

test("executed property: exactly one stamp at the line, always — never a gap, never two on top of each other", () => {
  // For each scroll state: EITHER a real stamp leads at/below the line (sticky off), OR the sticky leads and
  // every marker above the line is hidden. There is no state with both a visible sticky and a visible marker
  // above the line, and no state with neither (given a time exists).
  const states: Turn[][] = [
    [{ top: 40, marker: { id: "a", hm: "09:12", text: "", mTop: 55, mBottom: 68 } }],                 // tall: sticky
    [{ top: 92, marker: { id: "a", hm: "09:12", text: "09:12", mTop: 133, mBottom: 146 } }],          // real below line
    [{ top: 90, marker: { id: "a", hm: "09:12", text: "09:12", mTop: 102, mBottom: 115 } }],          // crossing: sticky
    [{ top: 82, marker: { id: "a", hm: "09:12", text: "09:12", mTop: 96, mBottom: 109 } }],           // clipped: sticky
  ];
  for (const turns of states) {
    const r = decideSticky(turns, CTOP, CBOT);
    const visibleAboveLine = turns.some((t) => t.marker && t.marker.text && !r.hidden.includes(t.marker.id)
                                          && t.marker.mTop < LINE && t.marker.mBottom > CTOP);
    assert.equal(r.show && visibleAboveLine, false, "never a sticky AND a visible real stamp above the line");
    assert.equal(!r.show && !turns.some((t) => t.marker && t.marker.text && t.marker.mBottom > CTOP && t.marker.mTop < CBOT), false,
      "and never nothing: if the sticky is off, a real stamp is on screen to hold the slot");
  }
});
