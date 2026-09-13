// The chat's HISTORY REGIONS (T386 stage 2, plans/chat-history-regions.md Part B): a session's transcript is an ordered list of
// regions over its turns, RUNS the page holds (rendered, virtualised as before) and GAPS it does not (empty space of an estimated
// height with the loading glyph while a request is in flight). The TAIL run is always resident and always live, so no client is
// ever detached, and the kernel never withholds a delta. Pure: node executes every rule here (chat-regions.test.ts); render.ts
// wires them to the DOM.
//
// Spans are TURN indices, [lo, hi), as the kernel numbers them (its pages are PAGE_TURNS-aligned in that numbering). The tail run's
// `hi` is null: it ends wherever the transcript ends now, and grows with every chatTail.
import { keyOf, mergeWindow, type Ev } from "./chat-window";

export type { Ev } from "./chat-window";
export interface Run { kind: "run"; lo: number; hi: number | null; events: Ev[]; }
export interface Gap { kind: "gap"; lo: number; hi: number; }
export type Region = Run | Gap;

export const DEFAULT_TURN_PX = 120;   // the per-TURN estimate the spacers use until a run is measured (a turn is ~two rows; render.ts sizeSpacers measures px-per-turn)

/** The regions a set of runs implies: the runs in turn order with a gap between each pair that does not touch, and a head gap
 *  [0, first.lo) when the first run does not start at the head. Runs must not overlap (insertRun keeps that). */
export function regionsFromRuns(runs: readonly Run[]): Region[] {
  const sorted = runs.slice().sort((a, b) => a.lo - b.lo);
  const out: Region[] = [];
  let at = 0;
  for (const r of sorted) {
    if (r.lo > at) out.push({ kind: "gap", lo: at, hi: r.lo });
    out.push(r);
    if (r.hi == null) return out;   // the tail run ends the list
    at = r.hi;
  }
  return out;
}

export function runsOf(regions: readonly Region[]): Run[] {
  return regions.filter((r): r is Run => r.kind === "run");
}

/** A window's events with the kernel's turn span become a run; the gaps on either side shrink or split; a run that touches or
 *  overlaps a held run merges into it, the T323 order rule carrying over (the held run's part before the window, the window,
 *  the held run's part after, every key once). A window that touches the TAIL run merges into it and the merged run is the
 *  tail (its `hi` stays null). */
export function insertRun(regions: readonly Region[], run: Run): Region[] {
  const runs = runsOf(regions);
  let cur: Run = { kind: "run", lo: run.lo, hi: run.hi, events: run.events.slice() };
  const kept: Run[] = [];
  for (const r of runs) {
    if (touches(r, cur)) cur = mergeRuns(r, cur);
    else kept.push(r);
  }
  kept.push(cur);
  return regionsFromRuns(kept);
}

function touches(a: Run, b: Run): boolean {
  const aHi = a.hi ?? Infinity, bHi = b.hi ?? Infinity;
  return b.lo <= aHi && a.lo <= bHi;
}

/** Two touching or overlapping runs as one, events in turn order. `held` is the run the page had, `win` the arrival. */
function mergeRuns(held: Run, win: Run): Run {
  const lo = Math.min(held.lo, win.lo);
  const hi = held.hi == null || win.hi == null ? null : Math.max(held.hi, win.hi);
  let events: Ev[];
  const keysOverlap = win.events.some((e) => { const k = keyOf(e); return !!k && held.events.some((h) => keyOf(h) === k); });
  if (keysOverlap) events = mergeWindow(held.events, win.events).events;
  else if (win.lo < held.lo || (win.lo === held.lo && (win.hi ?? Infinity) < (held.hi ?? Infinity))) events = win.events.concat(held.events);
  else events = held.events.concat(win.events);
  return { kind: "run", lo, hi, events };
}

/** A gap's height in the thread: its TURN count × the measured px-per-TURN (not px-per-display-unit: a turn is a user row plus its
 *  reply and any tool rows, so multiplying a turn count by a per-unit average drew gaps roughly half their true height), at least a turn. */
export function gapHeight(gap: { lo: number; hi: number }, perTurnPx: number | null | undefined): number {
  const per = perTurnPx ?? DEFAULT_TURN_PX;
  return Math.max(Math.round(per), Math.round((gap.hi - gap.lo) * per));
}

/** The page-aligned span to ask for when a gap enters the viewport: the page nearest the viewport's edge first. Scrolling UP
 *  through a gap meets its bottom edge, so its bottom page; scrolling DOWN into a gap meets its top edge, so its top page; a
 *  landing asks for the anchor's pages instead (loadAround). Pages are PAGE_TURNS-aligned in the kernel's numbering, clipped to
 *  the gap. */
export function pagesToAsk(gap: { lo: number; hi: number }, edge: "top" | "bottom", pageTurns: number): { lo: number; hi: number } {
  const P = Math.max(1, pageTurns | 0);
  if (edge === "bottom") {
    const lo = Math.max(gap.lo, Math.floor((gap.hi - 1) / P) * P);
    return { lo, hi: gap.hi };
  }
  const hi = Math.min(gap.hi, (Math.floor(gap.lo / P) + 1) * P);
  return { lo: gap.lo, hi };
}

/** Where inside a gap an anchor with a time falls, as a fraction of the gap's height: the time's proportion between the gap's
 *  neighbours' times (the run above's last, the run below's first). Without both neighbours the gap's start (0) or, with only
 *  the run above, its end (1) is the honest guess; the caller does not move at all when it has no time. */
export function gapFraction(t: number, tBefore: number | null | undefined, tAfter: number | null | undefined): number {
  if (tBefore != null && tAfter != null && tAfter > tBefore) return Math.max(0, Math.min(1, (t - tBefore) / (tAfter - tBefore)));
  if (tBefore != null && tAfter == null) return 1;
  return 0;
}

/** The ONE landing notice's sentence (the user 2026-09-12): the time in the reader's clock as the strip renders it, or the plain
 *  form when the anchor carries no time. */
export function landingNotice(t: number | null | undefined, clock: (epochS: number) => string): string {
  return t != null ? "Going to the message from " + clock(t) + ", click to stay here" : "Going to the earlier message, click to stay here";
}

export interface LandingState { target: string | null; notice: boolean; askInFlight: boolean; }
/** What the notice's click (the only cancel) leaves: no target and no notice, the ask still in flight (its reply inserts the run;
 *  nothing is thrown away) and the view where it is. */
export function landingCancel(state: LandingState): LandingState {
  return { target: null, notice: false, askInFlight: state.askInFlight };
}

/** The gap a turn span falls in, if any. */
export function gapAt(regions: readonly Region[], turn: number): Gap | null {
  for (const r of regions) if (r.kind === "gap" && turn >= r.lo && turn < r.hi) return r;
  return null;
}

/** The turn count a region list covers before the tail (the tail run's lo), for the scrollbar's estimate. */
export function turnsBeforeTail(regions: readonly Region[]): number {
  const tail = regions.find((r): r is Run => r.kind === "run" && r.hi == null);
  return tail ? tail.lo : regions.reduce((n, r) => Math.max(n, r.hi ?? 0), 0);
}
