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

test("an oversized view (scrolled to the top → window grew to full) re-collapses to the tail on switch", () => {
  // WINDOW_CAP guards it; above WINDOW_TAIL so a normally-grown tab isn't churned. Switching TO a view with
  // more than WINDOW_CAP rendered turns resets it (rendered/winStart 0, stick) so syncView rebuilds the tail
  // window and lands at the bottom — bounding the reveal to ~WINDOW_TAIL nodes instead of thousands.
  const cap = Number(/const WINDOW_CAP = (\d+);/.exec(RENDER)?.[1]);
  const tail = Number(/const WINDOW_TAIL = (\d+);/.exec(RENDER)?.[1]);
  assert.ok(cap > tail, `WINDOW_CAP (${cap}) must exceed WINDOW_TAIL (${tail})`);
  // skip only when deep-linking (target may be in the collapsed head); applies in BOTH modes (compact windows too)
  assert.match(RENDER, /if \(!pendingAnchor && pendingAnchorT == null\s*\n?\s*&& v\.el\.querySelectorAll\("\.turn"\)\.length > WINDOW_CAP\) \{/);
  assert.match(RENDER, /v\.rendered = 0; v\.winStart = 0; v\.avgTurnH = undefined; v\.stick = true;/);
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
  assert.match(RENDER, /spacer\.style\.height = Math\.max\(0, Math\.round\(\(v\.spacerCount \?\? v\.winStart\) \* \(v\.avgTurnH \?\? 60\)\)\) \+ "px";/);
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

test("scroll-back auto-loads by proximity to the RENDERED TOP, not absolute scrollTop", () => {
  assert.match(RENDER, /function maybeExpandWindow\(\): void/);
  assert.match(RENDER, /if \(!v \|\| v\.winStart <= 0\) return;/);
  // the head folds into a tall spacer, so an `scrollTop < buffer` test never fired once scrolled up — that
  // was the broken scroll-back. Trigger off `gap` = viewport-top distance below the rendered top instead.
  assert.match(RENDER, /const topH = sp && sp\.classList\?\.contains\("tx-spacer"\) \? sp\.offsetHeight : 0;/);
  assert.match(RENDER, /const gap = content\.scrollTop - topH;/);
  assert.match(RENDER, /if \(gap < 0 \|\| gap > EXPAND_TRIGGER_PX\) return;/);
  // a "loading earlier…" cue paints, then the render is deferred one frame; the viewport is re-anchored after
  assert.match(RENDER, /showLoadingPill\(\);/);
  assert.match(RENDER, /content\.scrollTop \+= content\.scrollHeight - before;/);
  assert.match(RENDER, /hideLoadingPill\(\);/);
  assert.match(RENDER, /c\.addEventListener\("scroll", maybeExpandWindow, \{ passive: true \}\);/);
});

test("a loading pill shows while history renders, and the CSS pins it top-center of the chat pane", () => {
  assert.match(RENDER, /function showLoadingPill\(\): void/);
  assert.match(RENDER, /loadingPillEl\.textContent = "Loading earlier messages…";/);
  assert.match(CSS, /\.tx-loading-pill \{[\s\S]*position: fixed[\s\S]*\}/);
});

test("a deep-link into the spacered head expands the window to reveal the target, then lands", () => {
  // scrollToAnchor: when the target isn't in the rendered window, find its event index and expand down to it.
  assert.match(RENDER, /const idx = s\.events\.findIndex\(\(e\) => e\.uuid === uuid \|\| \(e as \{ mid\?: string \}\)\.mid === uuid\);/);
  assert.match(RENDER, /if \(idx >= 0 && idx < v\.winStart\) \{\s*\n\s*expandWindow\(v, s, idx,/);
});

test("compact mode is tail-windowed too — render only the display items reaching into [winStart, len)", () => {
  // a 7000-event session in compact rendered 4000+ folded turns / 43k nodes → slow switch (the user
  // 2026-06-25). rebuildCompact now keys off the SAME event-index winStart as the normal path, renders only
  // the tail display items, and folds the hidden head into a spacer (spacerCount = hidden display items).
  assert.match(RENDER, /const winStart = \(firstBuild \|\| len < v\.rendered\) \? Math\.max\(0, len - WINDOW_TAIL\)/);
  assert.match(RENDER, /const firstShown = winStart > 0 \? disp\.findIndex\(\(it\) => lastIdx\(it\) >= winStart\) : 0;/);
  assert.match(RENDER, /const shown = firstShown <= 0 \? disp : disp\.slice\(firstShown\);/);
  assert.match(RENDER, /v\.spacerCount = firstShown > 0 \? firstShown : 0;/);
  // scroll-up in compact rebuilds a larger window (no incremental prepend over a folded stream)
  assert.match(RENDER, /if \(settings\.compact\) \{[\s\S]*?v\.winStart = newStart; v\.stale = true; rebuildCompact\(v, s, working\);/);
});

test("the spacer is invisible, non-interactive vertical space", () => {
  assert.match(CSS, /\.tx-spacer \{ width: 100%; pointer-events: none; \}/);
});
