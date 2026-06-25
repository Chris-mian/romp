// Background pre-build planner (the user 2026-06-25) — pure + DOM-free so it's unit-testable, mirroring
// compact.ts / time-marker.ts.
//
// The chat webview builds each tab's transcript DOM LAZILY, on the FIRST switch to it (showActive's "heavy"
// gate). So opening a big transcript lagged, and on startup the tabs appeared to "open one at a time" — each
// one paid its O(events) DOM build the first time you looked at it. content-visibility:auto already skips an
// OFF-screen turn's layout/paint, but the nodes still have to be CREATED once; that creation is the cost.
//
// The remedy is to build off-screen tabs AHEAD of time, during browser idle. This module owns the POLICY —
// which off-screen tabs still need building, and in what order — so a refactor of the DOM plumbing in
// render.ts can't silently drop the optimization: the test pins the policy here. render.ts just walks the
// plan, calling syncView until the idle deadline.

export interface ViewState {
  events: number; // s.events.length — how many events the session currently has
  hasDom: boolean; // the view's DOM has been built at least once (childNodes > 0)
  stale: boolean; // marked dirty by an update that arrived while the tab was hidden
  rendered: number; // how many events the built DOM currently reflects
}

// A view is "current" — a switch to it is ALREADY instant (showActive's non-heavy path) — when its DOM is
// built, not stale, and reflects every event. This is the SAME predicate that makes a switch non-heavy, so
// any tab the plan builds is guaranteed to then switch instantly. Keeping the two in lockstep is the whole
// point: pre-building must target exactly the views a switch would otherwise have to build.
export function isViewCurrent(v: ViewState): boolean {
  return v.hasDom && !v.stale && v.rendered === v.events;
}

// The off-screen tabs that still need a (re)build, MOST-RECENTLY-USED first (the likeliest next switch) then
// tab order, deduped. The active tab is excluded (showActive owns it); empty / not-yet-loaded sessions are
// skipped (nothing to build). Pure: callers pass `view(id)` to look up each tab's render state.
export function prebuildPlan(
  activeId: string | null,
  mru: readonly string[],
  order: readonly string[],
  view: (id: string) => ViewState | null,
): string[] {
  const seen = new Set<string>();
  const plan: string[] = [];
  for (const id of [...mru, ...order]) {
    if (id === activeId || seen.has(id)) continue;
    seen.add(id);
    const v = view(id);
    if (!v || v.events === 0) continue; // unknown / not loaded yet / empty → nothing to pre-build
    if (isViewCurrent(v)) continue; // already instant → skip (no wasted work)
    plan.push(id);
  }
  return plan;
}
