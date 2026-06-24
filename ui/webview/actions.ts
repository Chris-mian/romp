// Click-safe, always-acknowledged actions for the romp dashboard.
//
// WHY THIS EXISTS — the "I had to click it several times" bug.
// The dashboard re-renders on every kernel push: a 0.5–3s backstop poll, PLUS an
// immediate push on each SDK stream event and on every hook /tick (turn ended,
// prompt landed, postal message). Surfaces that rebuild their DOM wholesale —
// renderTabs()'s `#tabs`.replaceChildren(), Fleet's `#fleet-list`.replaceChildren()
// — DESTROY and recreate the very node you are clicking. A native `click` only
// fires when the mousedown and the mouseup land on the same element; when a
// rebuild slips between them the click is silently dropped. While a session works
// the pushes are frequent, so the drop is frequent: the button feels dead until
// you happen to click in a gap between rebuilds.
//
// THE RULE (see CLAUDE.md ## Design → "Buttons must stay click-safe…"):
//   1. Never hang an action on a node you rebuild. Put the action on a STABLE
//      ancestor — the container fetched by id survives replaceChildren(); only its
//      children are swapped — and key it off a `data-act` attribute. A click whose
//      original target was swapped mid-press still bubbles up to that ancestor (the
//      browser dispatches `click` to the nearest still-connected common ancestor),
//      so the action always lands no matter how often the children churn.
//   2. Every activation gives IMMEDIATE feedback (a press flash), independent of
//      the kernel round-trip, so the user always sees the click registered — then
//      any dialog / error / result follows. A button that "does nothing visible
//      yet" is the other half of the multi-click problem: the user re-clicks
//      because nothing told them the first one took.
//
// delegate() does both: one listener per stable root, `data-act` dispatch, and an
// automatic feedback flash on every matched activation.
//
// For full-canvas redraw surfaces (the SVG timeline) where threading every action
// param through data-attrs is impractical, the sibling technique is deferRedraw:
// hold the rebuild while a pointer is pressed over the surface, flushing it on
// release — so the pressed element survives until the click completes.

export type ActionHandler = (el: HTMLElement, ev: Event) => void;

// Mark the activated control so the user sees the press took, even before the
// kernel responds. CSS animates `.romp-acted` (a brief press pulse). Safe if the
// node is rebuilt before the timer fires — removing a class off a detached node is
// a no-op. Re-triggered cleanly on a rapid re-click via a forced reflow.
export function flash(el: HTMLElement): void {
  el.classList.remove("romp-acted");
  void el.offsetWidth; // reflow so the animation restarts on a fast second click
  el.classList.add("romp-acted");
  setTimeout(() => el.classList.remove("romp-acted"), 280);
}

// Install ONE delegated click listener on a stable root. `handlers` maps a
// `data-act` value to its action. Children carry `data-act="<name>"` plus whatever
// data-* the handler needs (data-id, data-sid, …); they may be freely rebuilt. The
// nearest ancestor WITH a data-act wins, so a control nested inside a larger
// clickable row (e.g. a ✕ inside a tab) routes to its own action without needing
// stopPropagation. Call once per root — never inside a render loop.
export function delegate(root: HTMLElement | Document, handlers: Record<string, ActionHandler>): void {
  root.addEventListener("click", (ev) => {
    const start = ev.target as Element | null;
    const el = start && typeof start.closest === "function"
      ? (start.closest("[data-act]") as HTMLElement | null)
      : null;
    if (!el) return;
    const within = root === document ? document.contains(el) : (root as HTMLElement).contains(el);
    if (!within) return;
    const act = el.dataset.act;
    if (!act) return;
    const h = handlers[act];
    if (!h) return;
    flash(el);
    h(el, ev);
  });
}
