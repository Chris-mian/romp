// THE PANE GRAB DETECTOR (plans/pane-docking.md section 3, the empty space inside a pane): a small bundle the
// shell's docking engine (panedock-main.ts) injects into every pane document while the kit is on, the same road
// as its cursor stylesheet. The shell can see only its own chrome; a pane's content is an iframe whose pointer
// events never reach the parent. So the inner page detects a press on its OWN empty background (the feed's list
// and columns where no card is under the pointer, the sessions band's SVG outside every lane and mark, the
// outline's list below its rows, the Files pane's empty state) and forwards it: it CAPTURES the pointer on the
// pressed element, so the moves keep flowing to this document once the pointer leaves the iframe, and posts
// {romp:"paneGrab", clientX, clientY, pointerId} to the shell, which arms exactly the drag it arms on the ring.
// The chat is the deliberate exception: a press-drag over the transcript is a text selection, so its grab surface
// stays the strip's empty run (the shell's own wiring). The open hand shows over exactly the empty targets: a body
// class toggled by the target under the pointer, so a card's text never wears a hand it cannot honour.
//
// Inert unless the page's body carries `pane-docking` (the shell sets it while the kit is on and removes it when
// the kit goes off). The pure decision (`emptyPress`) is node-tested; the listeners are the DOM glue.

export const GRAB_HOVER_CLASS = "pd-grab-hover";
export const KIT_CLASS = "pane-docking";
export const STYLE_ID = "pd-grab-css";

/** A pane page's empty background: the press must land on one of THESE elements itself (a container, not a card
 *  or a row inside it). Keyed by the page's app name (`window.__rompApp`). The chat is absent on purpose. */
export const EMPTY_BY_APP: Record<string, string> = {
  feed: "body, #feed-list, #feed-cols, .feed-cols, .feed-col, .feed-col-list, #feed-foot",
  timeline: "body, #host, .romp-tl-wrap, svg",
  fleet: "body, #fleet-list, #fleet-foot",
  files: "body, #files-empty",
};

/** Anything a press yields to, wherever it sits: controls, links, fields, cards, rows, chips, marks. */
export const CONTROL_SEL = "a, button, input, textarea, select, label, summary, [role], [contenteditable], [draggable=true], [data-act], [data-sid], [data-id], .fitem, .ftask-group, .fcard, .card, .chip, .tag-chip, svg *";

/** The subset of an Element the decision reads, so a node test can hand in a fake. */
export interface TargetLike { matches(sel: string): boolean; closest(sel: string): unknown }

/** Whether a press on `target` in the page for `app` is a press on the page's empty background. */
export function emptyPress(app: string, target: TargetLike | null): boolean {
  const sel = EMPTY_BY_APP[app];
  if (!sel || !target) return false;
  try {
    if (target.closest(CONTROL_SEL)) return false;
    return target.matches(sel);
  } catch {
    return false;
  }
}

/** Whether a pointer press may be forwarded: the primary button, no modifier (Option is the shell's own path). */
export function forwardable(e: { button: number; altKey: boolean; ctrlKey: boolean; metaKey: boolean; shiftKey: boolean }): boolean {
  return e.button === 0 && !e.altKey && !e.ctrlKey && !e.metaKey && !e.shiftKey;
}

export function install(win: Window, app: string): void {
  const doc = win.document;
  if (!EMPTY_BY_APP[app] || (win as any).__rompPaneGrab) return;
  const on = () => !!(doc.body && doc.body.classList.contains(KIT_CLASS));
  if (!doc.getElementById(STYLE_ID)) {
    const st = doc.createElement("style"); st.id = STYLE_ID;
    st.textContent = `body.${KIT_CLASS}.${GRAB_HOVER_CLASS}{cursor:grab}`;
    (doc.head || doc.documentElement).appendChild(st);
  }
  doc.addEventListener("pointermove", (e) => {
    const want = on() && emptyPress(app, e.target as TargetLike | null);
    if (doc.body && doc.body.classList.contains(GRAB_HOVER_CLASS) !== want) doc.body.classList.toggle(GRAB_HOVER_CLASS, want);
  }, { capture: true, passive: true });
  doc.addEventListener("pointerleave", () => { if (doc.body) doc.body.classList.remove(GRAB_HOVER_CLASS); }, true);
  doc.addEventListener("pointerdown", (e) => {
    if (!on() || !forwardable(e) || !emptyPress(app, e.target as TargetLike | null)) return;
    try { (e.target as Element).setPointerCapture(e.pointerId); } catch { /* an old engine: the moves still arrive over the gaps */ }
    e.preventDefault();   // no text selection starts under a press that is a grab
    try { win.parent.postMessage({ romp: "paneGrab", app, clientX: e.clientX, clientY: e.clientY, pointerId: e.pointerId }, "*"); } catch { /* no parent */ }
  }, true);
  (win as any).__rompPaneGrab = { app, empty: (el: Element | null) => emptyPress(app, el) };   // read-only, for the served pins
}

// boot in a pane document (a child frame); an import in node stays inert
if (typeof window !== "undefined" && typeof document !== "undefined" && window.parent && window.parent !== window) {
  const app = String((window as any).__rompApp || "");
  if (document.body) install(window, app); else document.addEventListener("DOMContentLoaded", () => install(window, app));
}
