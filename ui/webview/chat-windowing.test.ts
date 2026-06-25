// Tail-windowing of the chat transcript (the user 2026-06-25): a long session renders thousands of .turn
// nodes, and laying out that whole tree is what made focusing a big chat lag ~½s even after delta-send cut
// the wire cost. So only the tail [winStart, len) renders as real turns; the older head collapses into one
// measured `.tx-spacer`, and scrolling near the top lazily reveals older chunks (the chat-app "load more on
// scroll back"). The spacer carries a real height so scrollHeight stays honest and stick-to-bottom never
// snaps (the failure mode of the reverted content-visibility try). Source-level pins (no jsdom for the
// renderer), mirroring the other render.ts tests.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("the window-tail constant exceeds the trailing re-check window so the re-check always renders", () => {
  // WINDOW_TAIL must be > TAIL_RECHECK, else the trailing in-place re-check (tool fills) could reach below
  // the rendered window and try to mutate a turn that lives in the spacer.
  const tail = Number(/const WINDOW_TAIL = (\d+);/.exec(RENDER)?.[1]);
  const recheck = Number(/const TAIL_RECHECK = (\d+);/.exec(RENDER)?.[1]);
  const chunk = Number(/const EXPAND_CHUNK = (\d+);/.exec(RENDER)?.[1]);
  const trigger = Number(/const EXPAND_TRIGGER_PX = (\d+);/.exec(RENDER)?.[1]);
  assert.ok(tail > 0 && recheck > 0 && chunk > 0 && trigger > 0, "all windowing constants are positive");
  assert.ok(tail > recheck, `WINDOW_TAIL (${tail}) must exceed TAIL_RECHECK (${recheck})`);
});

test("a pure tab switch is a NO-OP render — the cached DOM is revealed, not re-built", () => {
  // the normal path mirrors the compact path's cache guard: rendered===len && !stale && hasDOM ⇒ return.
  // without it, every showActive() re-rendered the trailing TAIL_RECHECK turns (markdown + highlight.js),
  // which is what kept switching to a big, tool-heavy session slow (the user 2026-06-25).
  assert.match(RENDER, /if \(v\.rendered === s\.events\.length && !v\.stale && v\.el\.childNodes\.length > 0\) return v;/);
});

test("a fresh build or a rewind renders only the tail; the floor is len − WINDOW_TAIL", () => {
  assert.match(RENDER, /const firstBuild = v\.rendered === 0 \|\| v\.el\.childNodes\.length === 0;/);
  assert.match(RENDER, /const rewind = len < v\.rendered;/);
  assert.match(RENDER, /let winStart = \(firstBuild \|\| rewind\) \? Math\.max\(0, len - WINDOW_TAIL\) : Math\.min\(v\.winStart, len\);/);
});

test("the incremental re-check never re-renders below the window floor", () => {
  // a tool fill / stale re-render starts at `from`, but is clamped UP to winStart so it stays inside the
  // rendered window — a change in the spacered head is picked up only when that head is later expanded.
  assert.match(RENDER, /from = Math\.max\(from, v\.winStart\);/);
  // children removed from the bottom keep the spacer + the turns before `from`
  assert.match(RENDER, /const keep = hasSpacer \+ \(from - v\.winStart\);/);
});

test("renderWindow prepends a measured spacer only when the head is collapsed", () => {
  assert.match(RENDER, /function renderWindow\(v: View, s: Session, winStart: number, working: boolean\): void/);
  assert.match(RENDER, /if \(winStart > 0\) v\.el\.appendChild\(el\("div", "tx-spacer"\)\);/);
  assert.match(RENDER, /sizeSpacer\(v\);/);
});

test("sizeSpacer makes the spacer winStart × the average rendered turn height (honest scrollHeight)", () => {
  assert.match(RENDER, /function sizeSpacer\(v: View\): void/);
  assert.match(RENDER, /spacer\.style\.height = Math\.max\(0, Math\.round\(v\.winStart \* \(v\.avgTurnH \?\? 60\)\)\) \+ "px";/);
  // avgTurnH is measured once (off the tail) and cached, so expansion stays O(chunk), not O(n²)
  assert.match(RENDER, /if \(v\.avgTurnH == null\)/);
});

test("sizeSpacer only CACHES a real (visible) measurement — a display:none pre-built view falls back", () => {
  // a pre-built tab is display:none (offsetHeight 0) → don't cache 0 (that would collapse the spacer);
  // re-measure when the view is shown.
  assert.match(RENDER, /if \(h > 0 && turns > 0\) v\.avgTurnH = h \/ turns;/);
  // landActive re-sizes once the view is visible, so the real height lands on switch even for a pre-built tab
  assert.match(RENDER, /sizeSpacer\(v\);\s+\/\/ the view is now VISIBLE/);
});

test("expandWindow PREPENDS the revealed older turns (existing turns + their markers untouched)", () => {
  assert.match(RENDER, /function expandWindow\(v: View, s: Session, newStart: number, working: boolean\): void/);
  assert.match(RENDER, /v\.el\.insertBefore\(frag, spacer \? spacer\.nextSibling : v\.el\.firstChild\);/);
  // reaching the head removes the spacer entirely
  assert.match(RENDER, /if \(newStart <= 0\) \{ if \(spacer\) v\.el\.removeChild\(spacer\); \}/);
});

test("scrolling near the top lazily expands and counter-scrolls to anchor the viewport", () => {
  assert.match(RENDER, /function maybeExpandWindow\(\): void/);
  // only the active view, only while the head is still collapsed, only near the top
  assert.match(RENDER, /if \(!v \|\| v\.winStart <= 0\) return;/);
  assert.match(RENDER, /if \(!content \|\| content\.scrollTop > EXPAND_TRIGGER_PX\) return;/);
  // counter-scroll by the scrollHeight delta keeps the viewport visually pinned across the prepend
  assert.match(RENDER, /const before = content\.scrollHeight;/);
  assert.match(RENDER, /content\.scrollTop \+= content\.scrollHeight - before;/);
  assert.match(RENDER, /c\.addEventListener\("scroll", maybeExpandWindow, \{ passive: true \}\);/);
});

test("a deep-link into the spacered head expands the window to reveal the target, then lands", () => {
  // scrollToAnchor: when the target isn't in the rendered window, find its event index and expand down to it.
  assert.match(RENDER, /const idx = s\.events\.findIndex\(\(e\) => e\.uuid === uuid \|\| \(e as \{ mid\?: string \}\)\.mid === uuid\);/);
  assert.match(RENDER, /if \(idx >= 0 && idx < v\.winStart\) \{\s*\n\s*expandWindow\(v, s, idx,/);
});

test("compact mode renders the whole stream — no tail-window/spacer", () => {
  assert.match(RENDER, /v\.winStart = 0;\s+\/\/ compact renders the whole stream/);
});

test("the spacer is invisible, non-interactive vertical space", () => {
  assert.match(CSS, /\.tx-spacer \{ width: 100%; pointer-events: none; \}/);
});
