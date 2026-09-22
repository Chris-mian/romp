// THE PANE DOCKING ENGINE (plans/pane-docking.md, phase two), a dashboard-shell bundle loaded like
// palette-main.ts (a `<script src=/dist/panedock-main.js>` in the shell head, kernel.py). It runs ONLY
// when the per-browser gear switch `paneDocking` is on (the user's one constraint: DEFAULT OFF). With the
// switch off this bundle changes nothing: no class, no stylesheet, no listener that acts, no store written,
// so the shipped pane layout (the _LANDING_* inline JS and its three stores) is byte for byte what it is
// today. On, it:
//
// - positions every pane iframe's `.pane` by GEOMETRY from the layout tree (pane-tree.ts): absolute rects
//   inside the shell's `.col`, the row's gutters and the band's `#gh` hidden, the band a fixed-px kid whose
//   px follows the shipped `--tl` (so the inline autosize keeps working). Nothing is ever re-parented: an
//   iframe moved in the DOM reloads and drops its socket (section 2).
// - seeds the layout ONCE from the three shipped stores (romp-panes, romp-pane-grow, the chat columns) and
//   keeps it in `romp-layout` ({v:1, tree, parked}); the old keys are read, never written (section 6). The
//   rail's toggles keep their meaning: a pane turned off PARKS (its iframe stays mounted and hidden, the
//   po-* class exactly as today), a pane turned on opens at its default dock (section 5).
// - arms a pane MOVE from the pane's empty space, never a title bar (section 3): the padding ring around
//   its iframe, the empty run of its existing top row (the chat's tab strip, the Files bar), or Option/Alt
//   held anywhere over it. An open-hand cursor over a grab surface, a closed hand while held; a press lifts
//   only after the slop, so a click, a text selection or a scroll is never a drag; Escape cancels.
// - shows the LIVE ACCENT OUTLINE while a drag is in flight: the rectangle the pane will land in (the
//   target's half on the nearest edge, section 4), a thin ring following the pointer over no zone, a
//   refused ring over a chat strip (a pane is not a tab). The drop is a pure tree move plus a recompute.
// - mounts one divider per internal edge: every edge resizes its pair LIVE, one layout per animation frame, from
//   the tree as it was at the press; the band's edge writes `--tl` (section 12; the store written once, at release).
//
// Tabs as drop payloads (a tab dropped into a zone becomes a pane there; the strip as its join zone) are
// the plan's second seam and ship in the next pull request; until then the shipped tab-drag zones keep
// working and a column they open or close is mirrored into the tree (the romp-chat-cols event).
//
// Pure decisions live in pane-dock.ts and pane-tree.ts (node-tested); this file is the DOM glue. The flag
// read stays the shell's own raw-read idiom, split into a PURE `isPaneDockingOn` for the node test.
import {
  type Edge, type EdgeRect, type Layout, type PaneId, type Rect,
  edges, has, layout as layoutRects, leaves, move, parse, serialise, setFixed,
} from "./pane-tree";
import { paneSourceOk } from "./pane-source";
import {
  BAND, CHAT, DEFAULT_BAND_PX, FEED, FILES, FLEET, GUTTER, LAYOUT_KEY, RING, type Payload, type Shown, type Zone,
  bandPxOf, colNumberOf, crossedSlop, dragEdge, edgeAt, edgeClamp, grabbable, growKey, isChatPane, landingRect, planTabDrop, pressGeometry, reconcileShown, roundRect, seedLayout, zoneAt,
} from "./pane-dock";

export const PANE_DOCKING_CLASS = "pane-docking";
const SETTINGS_KEY = "romp:settings";
const GROW_KEY = "romp-pane-grow";
const DRAG_CLASS = "pd-drag", RESIZE_CLASS = "pd-resize", ALT_CLASS = "pd-alt";
// the cursor a divider drag keeps over EVERY pane (the pane rule below says grab; the resize class alone only makes the iframes
// pointer-transparent): keyed on the cursor the divider carries, col-resize between columns, row-resize between rows and for the band
const RESIZE_X_CLASS = "pd-resize-x", RESIZE_Y_CLASS = "pd-resize-y";
const STYLE_ID = "pd-css";
const GRAB_SCRIPT_ID = "pd-grab";
const MIN_PX = 120;      // a pane never resizes below this or a quarter of its pair (the shipped clamp)
const BAND_MIN = 48;     // the band's floor (the shipped #gh clamp)

/** A CHAT COLUMN's frame by the id the split script mints (`f-chat`, `f-chat-<n>`, kernel.py `frameId`): the chat's transcript
 *  keeps the shell's strip style and gets no grab detector (a press-drag there is a text selection). By the exact shape, never
 *  the prefix (the 1920 read): a registry pane whose id begins `chat-` renders as `f-chat-<id>` and is an ordinary pane. */
export function isChatFrame(id: string): boolean {
  return id === "f-chat" || /^f-chat-\d+$/.test(id);
}

/** Whether a pane frame speaks the pane protocol (plans/panes-as-data.md, section 3): every pane does unless the shell
 *  marked its iframe `data-protocol=none` (a URL-source pane: a foreign, sandboxed document). The kit's mark, its detector
 *  and its message handling are for protocol panes only; the pure read, so the exclusion is pinned without a DOM. */
export function speaksProtocol(f: { getAttribute(name: string): string | null }): boolean {
  return f.getAttribute("data-protocol") !== "none";
}

/** Whether the gear's per-browser `paneDocking` switch is on, from the raw `romp:settings` JSON. Only the
 *  literal `true` turns it on: a store from before the key, a missing value, or any other type reads OFF
 *  (the fail-safe default for an opt-in that gates a whole layout engine). Pure; never throws. */
export function isPaneDockingOn(rawSettings: string | null): boolean {
  try {
    const o = JSON.parse(rawSettings || "{}");
    return !!o && typeof o === "object" && (o as { paneDocking?: unknown }).paneDocking === true;
  } catch {
    return false;
  }
}

/** The shell's title for a pane (the keyboard palette's words, never chrome; the live outline showed it until 2026-09-21,
 *  when the user asked the square to say where by its place alone; kept exported, its mapping pinned by the node tests). `titles`
 *  is the pane records' word by rail key (plans/panes-as-data.md section 4: the engine reads it off the rail's buttons
 *  and the body's data-panes rows), so a data pane and the Artifacts pane are named as the rail names them; the shipped
 *  four keep their words when no map is given. */
export function paneTitle(id: PaneId, titles?: Record<string, string>): string {
  const m = /^chat-pane-(\d+)$/.exec(id);
  if (m) return "Chat " + m[1];
  if (id === BAND) return (titles && titles.timeline) || "Sessions";
  const key = growKey(id);
  if (titles && typeof titles[key] === "string" && titles[key]) return titles[key];
  if (id === CHAT) return "Chat";
  if (id === FLEET) return "Outline";
  if (id === FEED) return "Feed";
  if (id === FILES) return "Files";
  return id;
}

/** The pane records' titles by rail key, read off the shell: the rail's pane buttons (every pane the kernel rendered,
 *  shipped and data, in rail order) and the body's data-panes rows (a data pane's record). Pure over the two reads. */
export function titleMapOf(railButtons: ReadonlyArray<{ key: string; text: string }>, dataPanes: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  for (const b of railButtons) if (b.key && b.text) out[b.key] = b.text;
  if (Array.isArray(dataPanes)) for (const r of dataPanes as Array<{ id?: unknown; title?: unknown }>) {
    if (r && typeof r.id === "string" && typeof r.title === "string" && r.title) out[r.id] = r.title;
  }
  return out;
}

// The SHELL stylesheet, injected only while the kit is on (so the off DOM carries no node of the kit's).
const SHELL_CSS = [
  `body.${PANE_DOCKING_CLASS} .col{position:relative}`,
  // the row stays the flex kid that fills the space above the rail, but lays out nothing itself: every pane is
  // positioned against .col, the shipped gutters and the band's gutter are hidden (the kit mounts its own dividers)
  `body.${PANE_DOCKING_CLASS} .row{display:block;position:static;flex:1 1 auto;min-height:0}`,
  `body.${PANE_DOCKING_CLASS} .row>.gv,body.${PANE_DOCKING_CLASS} #gh{display:none}`,
  `body.${PANE_DOCKING_CLASS} .pane{position:absolute;margin:0;cursor:grab}`,
  `body.${PANE_DOCKING_CLASS} #tl-pane{position:absolute}`,
  // the grab RING: the pane's own padding, the iframe inset by it (a press on the ring is a press on the pane element).
  // The size is EXPLICIT: an absolutely positioned replaced element with width and height auto takes its intrinsic
  // 300 by 150 px and ignores its far offsets (CSS 2.1 10.3.8 and 10.6.5), so inset alone never stretches an iframe
  // (the round-one read: every pane's content sat in a 300 by 150 box at its top-left)
  `body.${PANE_DOCKING_CLASS} .pane>iframe{inset:${RING}px;width:calc(100% - ${2 * RING}px);height:calc(100% - ${2 * RING}px)}`,
  `body.${PANE_DOCKING_CLASS} .pane.split-v{padding:${RING}px;box-sizing:border-box}`,
  `body.${PANE_DOCKING_CLASS} .pane.split-v>iframe{inset:auto;width:100%;height:auto}`,
  // the dividers: the shipped gutter dress (a 1 px line in a 7 px strip), col-resize between columns, row-resize between rows
  `body.${PANE_DOCKING_CLASS} .pd-div{position:absolute;z-index:7;background:linear-gradient(90deg,transparent 3px,#333 3px,#333 4px,transparent 4px);cursor:col-resize}`,
  `body.${PANE_DOCKING_CLASS} .pd-div[data-dir=col]{background:linear-gradient(180deg,transparent 3px,#333 3px,#333 4px,transparent 4px);cursor:row-resize}`,
  // the closed hand from the PRESS on (:active, before any travel: the press registered, the pane is yours), and while
  // a pane is held; the iframes go pointer-transparent so the shell hears every move
  `body.${PANE_DOCKING_CLASS} .pane:active{cursor:grabbing}`,
  `body.${PANE_DOCKING_CLASS}.${DRAG_CLASS},body.${PANE_DOCKING_CLASS}.${DRAG_CLASS} .pane,body.${PANE_DOCKING_CLASS}.${DRAG_CLASS} .pd-div{cursor:grabbing}`,
  `body.${PANE_DOCKING_CLASS}.${DRAG_CLASS} iframe,body.${PANE_DOCKING_CLASS}.${RESIZE_CLASS} iframe{pointer-events:none}`,
  `body.${PANE_DOCKING_CLASS}.${ALT_CLASS} .pane,body.${PANE_DOCKING_CLASS}.${ALT_CLASS} iframe{cursor:grab}`,
  // a divider drag's cursor holds over the panes the pointer crosses (after the pane and Option rules, so it wins)
  `body.${PANE_DOCKING_CLASS}.${RESIZE_X_CLASS},body.${PANE_DOCKING_CLASS}.${RESIZE_X_CLASS} .pane,body.${PANE_DOCKING_CLASS}.${RESIZE_X_CLASS} .pd-div{cursor:col-resize}`,
  `body.${PANE_DOCKING_CLASS}.${RESIZE_Y_CLASS},body.${PANE_DOCKING_CLASS}.${RESIZE_Y_CLASS} .pane,body.${PANE_DOCKING_CLASS}.${RESIZE_Y_CLASS} .pd-div{cursor:row-resize}`,
  // the live outline: the accent wash inside a 2 px accent ring (the shipped #col-ghost dress), never a hit target,
  // above the focus ring; `free` while over no zone (a thin ring following the pointer); `refused` over a strip
  `#pd-outline{display:none;position:fixed;pointer-events:none;z-index:41;background:rgba(156,210,255,0.12);box-shadow:inset 0 0 0 2px var(--accent,#9cd2ff);align-items:center;justify-content:center;font:600 11px 'Inter',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;color:#8a8a8a;letter-spacing:.04em}`,
  `#pd-outline.on{display:flex}`,
  `#pd-outline.free{background:transparent;box-shadow:inset 0 0 0 1px var(--accent,#9cd2ff)}`,
  `#pd-outline.refused{background:transparent;box-shadow:inset 0 0 0 1px var(--accent,#9cd2ff)}`,
  // a TAB drag's hit areas (plans/pane-docking.md section 4: a tab is a drop payload under the kit's own zones): one
  // transparent layer per docked pane, above the pane and the shipped zones inside it, for the gesture's length
  `body.${PANE_DOCKING_CLASS} .pd-tabzone{position:absolute;z-index:12}`,
].join("\n");

// Injected into the CHAT and FILES documents while the kit is on: the open hand over the top row's empty run
// (the strip itself and its end spacer; the tabs and group heads keep the arrow they have today), and the
// Files bar. Removed with the kit.
const PANE_CSS = "#tabbar,#tabs,.tab-strip-end,.fileview-bar{cursor:grab}\n.tab,.tab-group-head,.tab-row-line{cursor:auto}";
const CONTROL_SEL = "button,a,input,textarea,select,[role=button],[contenteditable],.tab,.tab-group-head,.tab-tagchips,.tab-widgets-gear,.col-x";
const TOP_RUN_SEL = "#tabbar,#tabs,.tab-strip-end,.fileview-bar";

interface Press { pane: PaneId; frame: HTMLIFrameElement | null; win: Window; x0: number; y0: number; armed: boolean; zone: Zone | null }
interface DivDrag { edge: EdgeRect; x0: number; y0: number; px: number; py: number; want: number | null; raf: number; start: Layout; tl0: string; a0: number; b0: number }

function byId(id: string): HTMLElement | null { return document.getElementById(id); }
/** One layout per animation frame for a divider drag (plans/pane-docking.md section 12): arm `f` for the next frame and return its
 *  handle; a window without requestAnimationFrame (a test's stub) runs it at once and returns 0. */
export function frameOnce(f: () => void): number {
  const w = window as unknown as { requestAnimationFrame?: (cb: () => void) => number };
  if (typeof w.requestAnimationFrame === "function") return w.requestAnimationFrame(f) || 1;
  f(); return 0;
}
export function cancelFrame(h: number): void {
  const w = window as unknown as { cancelAnimationFrame?: (h: number) => void };
  if (h && typeof w.cancelAnimationFrame === "function") w.cancelAnimationFrame(h);
}
function frameOfPane(id: PaneId): HTMLIFrameElement | null {
  const p = byId(id);
  return p ? (p.querySelector(":scope > iframe") as HTMLIFrameElement | null) : null;
}

class Engine {
  on = false;
  private col: HTMLElement | null = null;
  private row: HTMLElement | null = null;
  private lay: Layout | null = null;
  private style: HTMLStyleElement | null = null;
  private outline: HTMLElement | null = null;
  private dividers: HTMLElement[] = [];
  private divEdges = new Map<HTMLElement, EdgeRect>();
  private press: Press | null = null;
  private pressOff: (() => void) | null = null;
  private div: DivDrag | null = null;
  private divOff: (() => void) | null = null;
  private obs: MutationObserver | null = null;
  private wired = new WeakSet<Document>();
  private offs: Array<() => void> = [];
  private altOn = false;
  private savedWriters: Record<string, unknown> | null = null;
  private tab: { sid: string; name: string; from: PaneId | null; stripH: number } | null = null;   // a session tab in flight (the chat's dragstart)
  private newChatDock: { target: PaneId; edge: Edge } | null = null;   // where the next new column docks (a tab's drop edge), for the reconcile the shipped split's event raises
  private tabZones: HTMLElement[] = [];

  constructor() {
    const w = window as any;
    // read-only hooks for the served pins: the switch, the layout, the panes' viewport rects, the drag state
    w.__rompPaneDock = {
      on: () => this.on,
      layout: () => (this.lay ? parse(serialise(this.lay)) : null),
      rects: () => this.viewportRects(),
      dragging: () => !!(this.press && this.press.armed),
      pressed: () => !!this.press,
      zone: () => (this.press ? this.press.zone : null),
    };
  }

  private mobile(): boolean {
    const w = window as any;
    try { return !!(w.__rompMobileOn && w.__rompMobileOn()); } catch { return false; }
  }

  /** Reflect the switch: on (and not the phone layout) starts the engine, anything else stops it. */
  apply(): void {
    if (!document.body) return;
    let raw: string | null = null;
    try { raw = localStorage.getItem(SETTINGS_KEY); } catch { raw = null; }
    const want = isPaneDockingOn(raw) && !this.mobile();
    if (want && !this.on) this.start();
    else if (!want && this.on) this.stop();
    else if (this.on) this.reconcile();
  }

  // ── lifecycle ────────────────────────────────────────────────────────────────────────────────────────
  private start(): void {
    this.col = document.querySelector(".col") as HTMLElement | null;
    this.row = document.querySelector(".row") as HTMLElement | null;
    if (!this.col || !this.row) return;
    this.on = true;
    document.body.classList.add(PANE_DOCKING_CLASS);
    this.style = document.createElement("style"); this.style.id = STYLE_ID; this.style.textContent = SHELL_CSS;
    document.head.appendChild(this.style);
    this.outline = document.createElement("div"); this.outline.id = "pd-outline"; document.body.appendChild(this.outline);
    // the store, seeded once from the shipped keys when absent, then reconciled with what the rail shows
    let stored: Layout | null = null;
    try { stored = parse(localStorage.getItem(LAYOUT_KEY) || ""); } catch { stored = null; }
    const sh = this.shown();
    this.lay = reconcileShown(stored || seedLayout(sh), sh);
    this.persist();
    this.render();
    // the events the layout follows: the rail's toggles, the chat columns, the band's --tl, the window
    const on = (t: EventTarget, k: string, h: EventListenerOrEventListenerObject, o?: boolean | AddEventListenerOptions) => { t.addEventListener(k, h, o); this.offs.push(() => t.removeEventListener(k, h, o)); };
    on(window, "romp-panes", () => this.reconcile());
    on(window, "romp-chat-cols", (e) => {
      const d = ((e as CustomEvent).detail || {}) as { frame?: HTMLIFrameElement; col?: number | string; open?: boolean };
      if (d.frame) this.wire(d.frame);
      // a column closing under a TAB drag from it ends the drag (the user 2026-09-21): the source page's dragend, which posts the
      // end, dies with the closed frame, so the hit areas would stand over every pane with no gesture behind them
      if (d.open === false && this.tab && this.tab.from === "chat-pane-" + String(d.col)) this.endTabDrag();
      this.reconcile();
    });
    on(window, "resize", () => { if (this.mobile()) this.apply(); else this.render(); });
    on(this.col, "pointerdown", (e) => this.onShellPress(e as PointerEvent), true);
    on(document, "keydown", (e) => this.onKey(e as KeyboardEvent), true);
    on(document, "keyup", (e) => this.onKey(e as KeyboardEvent), true);
    on(window, "blur", () => this.setAlt(false));
    on(window, "message", (e) => { if (!paneSourceOk(e as MessageEvent)) return; this.onGrabMessage(e as MessageEvent); });   // the shell's one check, fail-closed, at the registration (plans/panes-as-data.md section 5; the frame lookup reads it again)
    this.obs = new MutationObserver(() => this.reconcile());
    this.obs.observe(this.col, { attributes: true, attributeFilter: ["style"] });
    this.allFrames().forEach((f) => this.wire(f));
    this.standDownGrowWriters();
  }

  // The shipped geometry writers (_LANDING_JS: a new column halves the rightmost pane's grow, a closing one hands its
  // width left, a re-shown pane takes a fair grow, an unregistered pane drops its key) each write romp-pane-grow. Under
  // the kit the tree owns the geometry and the old keys are the OFF path's source of truth (plans/pane-docking.md
  // section 10), so while the kit is on they are stood down: the same globals answer as no-ops, and the originals
  // return when the kit goes off. The inline pane list they maintain is harmless stale while off (a missing element
  // is filtered by its own shown() check).
  private static WRITERS = ["__rompSplitGrow", "__rompSplitShrink", "__rompGrowFair", "__rompGrowFairIfNew", "__rompUnregisterPane"];
  private standDownGrowWriters(): void {
    const w = window as any;
    if (this.savedWriters) return;
    this.savedWriters = {};
    for (const k of Engine.WRITERS) { this.savedWriters[k] = w[k]; w[k] = () => false; }
  }
  private restoreGrowWriters(): void {
    const w = window as any;
    if (!this.savedWriters) return;
    for (const k of Engine.WRITERS) { if (this.savedWriters[k] !== undefined) w[k] = this.savedWriters[k]; }
    this.savedWriters = null;
  }

  private stop(): void {
    this.on = false;
    this.cancelPress(); this.endDiv(false); this.endTabDrag();
    document.body.classList.remove(PANE_DOCKING_CLASS, DRAG_CLASS, RESIZE_CLASS, RESIZE_X_CLASS, RESIZE_Y_CLASS, ALT_CLASS);
    this.offs.forEach((f) => f()); this.offs = [];
    if (this.obs) { this.obs.disconnect(); this.obs = null; }
    this.dividers.forEach((d) => d.remove()); this.dividers = []; this.divEdges.clear();
    if (this.style) { this.style.remove(); this.style = null; }
    if (this.outline) { this.outline.remove(); this.outline = null; }
    // the panes return to the flex row: every inline geometry the kit wrote goes
    this.allPaneEls().forEach((el) => { el.style.left = el.style.top = el.style.width = el.style.height = ""; });
    this.allFrames().forEach((f) => this.unwire(f));
    this.setAlt(false);
    this.restoreGrowWriters();
  }

  // ── what the shell shows ─────────────────────────────────────────────────────────────────────────────
  private allPaneEls(): HTMLElement[] {
    return Array.from(document.querySelectorAll(".col .pane")).filter((el) => !el.closest(".chat-sub")) as HTMLElement[];
  }
  private allFrames(): HTMLIFrameElement[] {
    return this.allPaneEls().map((p) => p.querySelector(":scope > iframe") as HTMLIFrameElement | null).filter((f): f is HTMLIFrameElement => !!f);
  }
  private poOn(key: string): boolean { return document.body.classList.contains("po-" + key); }
  private shown(): Shown {
    const row: PaneId[] = [];
    if (this.poOn("chat") && byId(CHAT)) {
      row.push(CHAT);
      // the side columns the chat split made, in DOM order (a bottom pane nests inside its parent and is no pane here)
      Array.from((this.row || document).querySelectorAll(".pane.chat-col")).forEach((el) => { if (el.id) row.push(el.id); });
    }
    // every other pane of the row, in DOCUMENT order, which is the rail's: the shipped columns and the registry's data
    // panes alike (plans/panes-as-data.md section 4), shown when its po-<key> class is on (the pane controller's truth)
    for (const el of this.allPaneEls()) {
      const id = el.id;
      if (!id || id === CHAT || isChatPane(id) || id === BAND || el.classList.contains("chat-col")) continue;
      if (this.poOn(growKey(id))) row.push(id);
    }
    let grow: Record<string, number> = {};
    try { const g = JSON.parse(localStorage.getItem(GROW_KEY) || "null"); if (g && typeof g === "object") grow = g; } catch { grow = {}; }
    const band = this.poOn("timeline") && !!byId(BAND);
    const present = this.allPaneEls().map((el) => el.id).filter(Boolean);   // a closed column's element is gone: its park goes with it
    const out: Shown = { row, band, bandPx: this.bandPx(), grow, present };
    if (this.newChatDock) out.newChatDock = this.newChatDock;
    return out;
  }
  private bandPx(): number {
    const c = this.col;
    let v = c ? c.style.getPropertyValue("--tl") : "";
    if (!v && c) { try { v = getComputedStyle(c).getPropertyValue("--tl"); } catch { v = ""; } }
    return bandPxOf(v);
  }

  private reconcile(): void {
    if (!this.on || !this.lay) return;
    const d = this.div;
    if (d && !d.edge.fixed) {
      // a reconcile UNDER a column or row drag (a pane toggled by the rail or the gear, the band re-sized by the shell's
      // autosize): the drag's frames are built from the PRESS tree (applyDiv), so the press tree must learn what changed
      // or the next frame and the commit discard it (the 1927 read: a pane shown mid-drag missing from the store and
      // overlapping, one hidden mid-drag persisted docked and parked, the band dropping to its press px). A change of
      // the LEAF SET ends the drag at its last position, committed: the pointer is still held, but the pair it was
      // sizing is not the pair on the page any more (new information, section 12). The band's px alone is carried
      // into the press tree, so every later frame and the commit keep it.
      const sh = this.shown();
      const next = reconcileShown(this.lay, sh);
      if (!sameSet(leaves(next.tree), leaves(this.lay.tree)) || !sameSet(next.parked, this.lay.parked)) this.endDiv(true, false);   // landed, not written: the reconcile below writes the corrected layout once
      else if (sh.band) {
        d.start = { ...d.start, tree: setFixed(d.start.tree, BAND, sh.bandPx > 0 ? sh.bandPx : DEFAULT_BAND_PX) };
        // the drag's EDGE re-read from the rebased press tree (the 1927 read, round four): under the band's split a divider between
        // stacked panes has its avail, its rect and the pair's sizes move with the band, so the press values would clamp, resize
        // and persist against a geometry that is gone (the edge 87 px behind the pointer with no move; the pushed pane persisted
        // under the minimum). The press origin shifts by the edge's displacement, so the pointer's travel stays relative to the
        // edge; the last pointer place is re-clamped and applied NOW, synchronously (the fifth review: a frame armed here landed
        // one paint late, since the shell's autosize fires from a ResizeObserver after the frame's animation callbacks, and the
        // reconcile's own render below painted the pre-growth ratios for one frame), so the reconcile below sees the corrected
        // layout as this.lay, finds nothing changed, and renders and persists nothing of its own.
        const box = this.box();
        const e2 = box ? edgeAt(d.start.tree, box, GUTTER, d.edge.path, d.edge.i) : null;
        if (e2) {
          d.x0 += e2.rect.x - d.edge.rect.x; d.y0 += e2.rect.y - d.edge.rect.y;
          const g = pressGeometry(d.start.tree, e2);
          d.edge = e2; d.a0 = g.a0; d.b0 = g.b0;
          if (d.want !== null && !e2.fixed) {
            const raw = e2.dir === "row" ? d.px - d.x0 : d.py - d.y0;
            d.want = edgeClamp(d.a0, d.b0, raw, this.minFrac(e2) * e2.avail);
            if (d.raf) { cancelFrame(d.raf); d.raf = 0; }
            this.applyDiv();
          }
        }
      }
    }
    const next = reconcileShown(this.lay, this.shown());
    const changed = serialise(next) !== serialise(this.lay);
    this.lay = next;
    // no store write from a reconcile while a drag is on (the band's px under a column drag reaches the store at the release,
    // or at Escape when the restored layout differs from the stored one); the band edge's own frames change nothing here
    // (applyDiv writes the px into the tree before the height variable), so they neither persist nor render twice
    if (changed && !this.div) this.persist();
    if (changed || !this.div) this.render();
  }

  private persist(): void {
    if (!this.lay) return;
    try { localStorage.setItem(LAYOUT_KEY, serialise(this.lay)); } catch { /* a full store: the layout still shows */ }
  }

  // ── geometry ─────────────────────────────────────────────────────────────────────────────────────────
  private box(): Rect | null {
    const r = this.row;
    if (!r) return null;
    return { x: r.offsetLeft, y: r.offsetTop, w: r.offsetWidth, h: r.offsetHeight };
  }

  private render(): void {
    if (!this.on || !this.lay) return;
    const box = this.box();
    if (!box) return;
    const rects = layoutRects(this.lay.tree, box, GUTTER);
    for (const { pane, rect } of rects) {
      const el = byId(pane);
      if (!el) continue;
      const r = roundRect(rect);
      el.style.left = r.x + "px"; el.style.top = r.y + "px"; el.style.width = r.w + "px"; el.style.height = r.h + "px";
    }
    this.mountDividers(edges(this.lay.tree, box, GUTTER));
  }

  private mountDividers(es: EdgeRect[]): void {
    while (this.dividers.length > es.length) { const d = this.dividers.pop()!; this.divEdges.delete(d); d.remove(); }
    while (this.dividers.length < es.length) {
      const d = document.createElement("div"); d.className = "pd-div";
      d.addEventListener("pointerdown", (e) => this.onDivPress(e, d));
      (this.row || this.col!).appendChild(d); this.dividers.push(d);
    }
    es.forEach((e, i) => {
      const d = this.dividers[i], r = roundRect(e.rect);
      d.setAttribute("data-dir", e.dir);
      d.style.left = r.x + "px"; d.style.top = r.y + "px"; d.style.width = r.w + "px"; d.style.height = r.h + "px";
      this.divEdges.set(d, e);
    });
  }

  /** Every docked pane's rectangle in VIEWPORT px, read from the DOM right now (the zones read these, never a
   *  cached copy: the lesson of every drag lab, re-read the rects right before the release). */
  private viewportRects(): Array<{ pane: PaneId; rect: Rect }> {
    if (!this.lay) return [];
    const out: Array<{ pane: PaneId; rect: Rect }> = [];
    for (const pane of leaves(this.lay.tree)) {
      const el = byId(pane);
      if (!el) continue;
      const b = el.getBoundingClientRect();
      out.push({ pane, rect: { x: b.left, y: b.top, w: b.width, h: b.height } });
    }
    return out;
  }

  /** Each chat pane's tab-strip height (px from the pane's top): its document's #tabbar bottom edge plus the ring. */
  private strips(): Record<PaneId, number> {
    const out: Record<PaneId, number> = {};
    if (!this.lay) return out;
    for (const pane of leaves(this.lay.tree)) {
      if (!isChatPane(pane)) continue;
      const f = frameOfPane(pane);
      try {
        const bar = f && f.contentDocument && f.contentDocument.getElementById("tabbar");
        if (bar) out[pane] = bar.getBoundingClientRect().bottom + RING;
      } catch { /* not ready: no strip zone yet */ }
    }
    return out;
  }

  // ── pane documents: the top-row runs, Option-drag, the keys ──────────────────────────────────────────
  private wire(f: HTMLIFrameElement): void {
    const doWire = () => {
      let d: Document | null = null;
      try { d = f.contentDocument; } catch { d = null; }
      if (!d || d.readyState === "loading") return;
      if (!this.wired.has(d)) {
        this.wired.add(d);
        d.addEventListener("pointerdown", (e) => this.onFramePress(e, f), true);
        d.addEventListener("keydown", (e) => this.onKey(e), true);
        d.addEventListener("keyup", (e) => this.onKey(e), true);
      }
      if (this.on && (isChatFrame(f.id) || f.id === "f-files") && !d.getElementById(STYLE_ID)) {
        const st = d.createElement("style"); st.id = STYLE_ID; st.textContent = PANE_CSS; (d.head || d.documentElement).appendChild(st);
      }
      if (this.on) this.markDoc(d, f);
    };
    f.addEventListener("load", doWire);
    doWire();
  }
  private unwire(f: HTMLIFrameElement): void {
    try {
      const d = f.contentDocument;
      const st = d && d.getElementById(STYLE_ID);
      if (st) st.remove();
      if (d) d.documentElement.style.cursor = "";
      if (d && d.body) d.body.classList.remove(PANE_DOCKING_CLASS, "pd-grab-hover");   // the grab detector reads this: off, it is inert
      // the kit's nodes in the pane document go with it (the plan: byte-identical off pages): the detector's tag, its
      // style and its window global; the listeners it bound stay, answering only to the class, and re-injection never
      // binds them twice (the detector's own wired flag)
      for (const id of [GRAB_SCRIPT_ID, "pd-grab-css"]) { const n = d && d.getElementById(id); if (n) n.remove(); }
      if (d && d.defaultView) { try { delete (d.defaultView as any).__rompPaneGrab; } catch { /* fine */ } }
    } catch { /* gone */ }
  }

  /** The kit's mark on a pane document while on: the body class the grab detector keys on, and the detector itself
   *  (dist/pane-grab.js, the plan's section 3: the inner page detects a press on its own empty background and forwards
   *  it here), injected once per document; the chat is skipped (its grab surface stays the strip's empty run). */
  private markDoc(d: Document, f: HTMLIFrameElement): void {
    if (!speaksProtocol(f)) return;   // a URL-source pane: a foreign, sandboxed document; it gets no mark and no detector (and could not be read anyway)
    if (!d.body) return;
    d.body.classList.add(PANE_DOCKING_CLASS);
    if (isChatFrame(f.id) || d.getElementById(GRAB_SCRIPT_ID)) return;
    const sc = d.createElement("script"); sc.id = GRAB_SCRIPT_ID; sc.src = "/dist/pane-grab.js" + this.distVer();
    (d.head || d.documentElement).appendChild(sc);
  }
  /** The shell's own bundle tag carries the dist version (`?v=N`); the injected detector rides the same, so a rebuild busts both. */
  private distVer(): string {
    try {
      const own = document.querySelector('script[src*="panedock-main.js"]') as HTMLScriptElement | null;
      const v = own ? new URL(own.src, location.href).searchParams.get("v") : null;
      return v ? "?v=" + encodeURIComponent(v) : "";
    } catch { return ""; }
  }

  /** A pane page's forwarded press ({romp:"paneGrab"}, pane-grab.ts): the page captured the pointer on its own empty
   *  background and hands the press here; the shell arms exactly the drag the ring arms, hearing the frame's captured
   *  moves through its window as it does for Option-drag. */
  /** A pane message counts only from a same-origin frame of this document whose pane speaks the protocol: a
   *  URL-source pane (data-protocol none, sandboxed) can still post to its parent, and is ignored here as it is by
   *  every shell handler (plans/panes-as-data.md section 5). */
  private protocolFrame(e: MessageEvent): HTMLIFrameElement | null {
    if (!paneSourceOk(e)) return null;   // the shell's one check first, fail-closed (plans/panes-as-data.md section 5)
    const f = this.allFrames().find((x) => x.contentWindow === e.source) || null;
    return f && speaksProtocol(f) ? f : null;
  }

  private onGrabMessage(e: MessageEvent): void {
    const m = e.data;
    if (!m || !this.on) return;
    if (!this.protocolFrame(e)) return;
    if (m.romp === "paneGrabEnd") {
      // the page's release: a press the shell heard only after the pointer was already up (its message task ran after
      // the pointerup, before this engine's own listeners existed) must not stand with no button held
      if (this.press && !this.press.armed) this.cancelPress();
      return;
    }
    if (m.romp === "tabDrag") { if (m.on) this.startTabDrag(e.source, m); else this.endTabDrag(); return; }
    if (m.romp !== "paneGrab" || this.press || this.div) return;
    const f = this.protocolFrame(e);
    if (!f || !f.contentWindow) return;
    const paneNode = f.closest(".pane") as HTMLElement | null;
    if (!paneNode || !this.lay || !has(this.lay.tree, paneNode.id)) return;
    const b = f.getBoundingClientRect();
    this.beginPress(paneNode.id, f, f.contentWindow, b.left + f.clientLeft + Number(m.clientX || 0), b.top + f.clientTop + Number(m.clientY || 0));
  }

  private onKey(e: KeyboardEvent): void {
    if (!this.on) return;
    if (e.key === "Escape" && this.press && this.press.armed) { e.preventDefault(); e.stopPropagation(); this.cancelPress(); return; }
    if (e.key === "Escape" && this.div && e.type === "keydown") { e.preventDefault(); e.stopPropagation(); this.endDiv(false); return; }   // a divider drag: the press tree back, live (the band's height for its own edge); written only when the restored layout differs from the stored one
    if (e.key === "Alt") this.setAlt(e.type === "keydown");
  }
  /** Option/Alt held: the open hand over every pane, content included (the cursor is inherited, so each pane
   *  document's root carries it and controls with a cursor of their own keep theirs). */
  private setAlt(on: boolean): void {
    if (this.altOn === on) return;
    this.altOn = on;
    document.body.classList.toggle(ALT_CLASS, on && this.on);
    for (const f of this.allFrames()) {
      try { const d = f.contentDocument; if (d) d.documentElement.style.cursor = on && this.on ? "grab" : ""; } catch { /* gone */ }
    }
  }

  // ── the drag arm ─────────────────────────────────────────────────────────────────────────────────────
  private onShellPress(e: PointerEvent): void {
    if (!this.on || this.press || this.div) return;
    const t = e.target;
    if (!(t instanceof HTMLElement)) return;
    if (t.classList.contains("pd-div")) return;   // its own handler
    const pane = t.classList.contains("pane") ? t : null;   // the ring: the pane element itself, never its iframe
    if (!pane || !pane.id || !this.lay || !has(this.lay.tree, pane.id)) return;
    if (!grabbable({ button: e.button, alt: e.altKey, onRing: true, onTopRun: false, onControl: false })) return;
    e.preventDefault();
    // CAPTURE the pointer on the pane: without it the moves over an iframe (a hair below the ring) go to that
    // iframe's document and the shell hears nothing until the pointer crosses a gap (a served find, 2026-09-19)
    try { pane.setPointerCapture(e.pointerId); } catch { /* an old engine: the moves still arrive over the gaps */ }
    this.beginPress(pane.id, null, window, e.clientX, e.clientY);
  }

  private onFramePress(e: PointerEvent, f: HTMLIFrameElement): void {
    if (!this.on || this.press || this.div) return;
    const paneNode = f.closest(".pane") as HTMLElement | null;
    const pane = paneNode && this.lay && has(this.lay.tree, paneNode.id) ? paneNode.id : null;
    if (!pane) return;
    const t = e.target;
    const onControl = !!(t instanceof Element && t.closest(CONTROL_SEL));
    const onTopRun = !!(t instanceof Element && t.closest(TOP_RUN_SEL));
    if (!grabbable({ button: e.button, alt: e.altKey, onRing: false, onTopRun, onControl })) return;
    const b = f.getBoundingClientRect();
    if (e.altKey) e.preventDefault();   // Option-drag: no text selection starts under the press
    const win = f.contentWindow;
    if (!win) return;
    try { if (t instanceof Element) t.setPointerCapture(e.pointerId); } catch { /* as above */ }   // the moves stay with this document
    this.beginPress(pane, f, win, b.left + f.clientLeft + e.clientX, b.top + f.clientTop + e.clientY);
  }

  private beginPress(pane: PaneId, frame: HTMLIFrameElement | null, win: Window, x: number, y: number): void {
    this.press = { pane, frame, win, x0: x, y0: y, armed: false, zone: null };
    const mv = (ev: Event) => this.onPressMove(ev as PointerEvent, win, frame);
    const up = (ev: Event) => this.onPressUp(ev as PointerEvent, win, frame);
    const cancel = () => this.cancelPress();
    win.addEventListener("pointermove", mv, true); win.addEventListener("pointerup", up, true); win.addEventListener("pointercancel", cancel, true);
    if (win !== window) { window.addEventListener("pointermove", mv, true); window.addEventListener("pointerup", up, true); }
    this.pressOff = () => {
      win.removeEventListener("pointermove", mv, true); win.removeEventListener("pointerup", up, true); win.removeEventListener("pointercancel", cancel, true);
      if (win !== window) { window.removeEventListener("pointermove", mv, true); window.removeEventListener("pointerup", up, true); }
    };
  }

  /** The pointer in SHELL viewport px: an event from a pane document is offset by its frame's box. */
  private shellPoint(e: PointerEvent, win: Window, frame: HTMLIFrameElement | null): { x: number; y: number } {
    if (win === window || !frame || e.view === window) return { x: e.clientX, y: e.clientY };
    const b = frame.getBoundingClientRect();
    return { x: b.left + frame.clientLeft + e.clientX, y: b.top + frame.clientTop + e.clientY };
  }

  private onPressMove(e: PointerEvent, win: Window, frame: HTMLIFrameElement | null): void {
    const p = this.press;
    if (!p) return;
    if (e.buttons === 0) { this.cancelPress(); return; }   // no button held: a release this engine never heard; nothing may arm or drop on it
    const pt = this.shellPoint(e, win, frame);
    if (!p.armed) {
      if (!crossedSlop(pt.x - p.x0, pt.y - p.y0)) return;
      p.armed = true;
      document.body.classList.add(DRAG_CLASS);
      try { (frame && frame.contentDocument ? frame.contentDocument : document).getSelection()?.removeAllRanges(); } catch { /* fine */ }
      try { if (frame && frame.contentDocument) frame.contentDocument.documentElement.style.userSelect = "none"; } catch { /* fine */ }
    }
    e.preventDefault();
    this.trackZone(pt, p);
  }

  /** The zone under the pointer and the outline for it, from rects read NOW. */
  private trackZone(pt: { x: number; y: number }, p: Press): void {
    const rects = this.viewportRects();
    const strips = this.strips();
    const zone = zoneAt(rects, pt, { self: p.pane, payload: "pane" as Payload, strips });
    p.zone = zone;
    const o = this.outline;
    if (!o) return;
    o.classList.add("on"); o.classList.remove("free", "refused");
    let r: Rect | null = zone ? landingRect(rects, zone, strips) : null;
    if (zone && zone.strip) {
      const joins = colNumberOf(p.pane) !== null && colNumberOf(zone.target) !== null && colNumberOf(p.pane) !== colNumberOf(zone.target);
      // the square says where by its place alone (the user 2026-09-21: no title, no "joins" in its centre); a refused drop
      // keeps its one line, since a thin ring alone cannot say why the release will do nothing
      if (joins) o.textContent = "";   // a chat pane's sessions join that strip (a group is separable, and rejoinable)
      else { o.classList.add("refused"); o.textContent = "A pane is not a tab"; }
    }
    else if (zone) o.textContent = "";
    else { o.classList.add("free"); o.textContent = ""; r = { x: pt.x - 80, y: pt.y - 40, w: 160, h: 80 }; }
    if (r) { const rr = roundRect(r); o.style.left = rr.x + "px"; o.style.top = rr.y + "px"; o.style.width = rr.w + "px"; o.style.height = rr.h + "px"; }
  }

  private onPressUp(e: PointerEvent, win: Window, frame: HTMLIFrameElement | null): void {
    const p = this.press;
    if (!p) return;
    if (!p.armed) { this.cancelPress(); return; }   // under the slop: a click, a selection; nothing lifted, nothing changes
    e.preventDefault();
    const pt = this.shellPoint(e, win, frame);
    this.trackZone(pt, p);   // re-read the rects right before the release: the zone is decided on what is on screen now
    const zone = p.zone;
    this.cancelPress();
    if (!zone || !this.lay) return;   // no zone: a cancel
    if (zone.strip) { this.joinPaneToStrip(p.pane, zone.target); return; }   // a chat pane on a strip: its sessions join; any other pane: a cancel (the outline said refused)
    this.drop(p.pane, zone.target, zone.edge as Edge);
  }

  private cancelPress(): void {
    const p = this.press;
    if (this.pressOff) { this.pressOff(); this.pressOff = null; }
    this.press = null;
    document.body.classList.remove(DRAG_CLASS);
    if (this.outline) { this.outline.classList.remove("on", "free", "refused"); this.outline.textContent = ""; }
    try { if (p && p.frame && p.frame.contentDocument) p.frame.contentDocument.documentElement.style.userSelect = ""; } catch { /* fine */ }
  }

  /** The drop: a pure tree move, persisted, then one recompute. A refusal (the only pane, a target gone in the
   *  meantime) says why through the shell's notice and changes nothing. */
  private drop(pane: PaneId, target: PaneId, edge: Edge): void {
    if (!this.lay) return;
    let tree;
    try { tree = move(this.lay.tree, pane, target, edge); }
    catch (err) { this.notify(String((err as Error).message || err)); return; }
    this.lay = { ...this.lay, tree };   // parked and the remembered tree ride along
    this.persist();
    this.render();
  }

  private notify(text: string): void {
    const w = window as any;
    try { if (w.__rompNotify) w.__rompNotify("warn", text); } catch { /* no notice surface */ }
  }

  // ── tabs as drop payloads (plans/pane-docking.md section 4; the user 2026-09-19: a tab dragged out of the strip into
  //    a zone becomes its own pane, a group of tabs is separable, a pane dropped on a strip joins it) ──────────────
  /** The chat page's dragstart ({romp:"tabDrag", on:true, sid, name, stripH}): one transparent hit area per docked pane
   *  for the gesture's length, above the pane and the shipped zones inside it (which never hear the pointer now). The
   *  SOURCE pane's strip stays uncovered, so the page's own live reorder keeps its dragover. */
  private startTabDrag(source: MessageEventSource | null, m: any): void {
    if (this.press || this.div || !this.lay || typeof m.sid !== "string" || !m.sid) return;
    const f = this.allFrames().find((x) => x.contentWindow === source && speaksProtocol(x));
    const fromPane = f ? (f.closest(".pane") as HTMLElement | null) : null;
    this.endTabDrag();
    this.tab = { sid: m.sid, name: typeof m.name === "string" ? m.name : "", from: fromPane ? fromPane.id : null, stripH: Math.max(0, Number(m.stripH) || 0) };
    for (const pane of leaves(this.lay.tree)) {
      const el = byId(pane);
      if (!el) continue;
      const z = document.createElement("div"); z.className = "pd-tabzone"; z.setAttribute("data-pane", pane);
      const top = pane === this.tab.from ? this.tab.stripH + RING : 0;
      z.style.left = el.offsetLeft + "px"; z.style.top = (el.offsetTop + top) + "px"; z.style.width = el.offsetWidth + "px"; z.style.height = Math.max(0, el.offsetHeight - top) + "px";
      const over = (ev: DragEvent) => { ev.preventDefault(); try { if (ev.dataTransfer) ev.dataTransfer.dropEffect = "move"; } catch { /* fine */ } this.trackTabZone({ x: ev.clientX, y: ev.clientY }); };
      z.addEventListener("dragenter", over); z.addEventListener("dragover", over);
      z.addEventListener("dragleave", (ev) => { const r = ev.relatedTarget; if (r instanceof Element && r.classList.contains("pd-tabzone")) return; this.hideOutline(); });
      z.addEventListener("drop", (ev) => { ev.preventDefault(); const zone = this.tabZoneAt({ x: ev.clientX, y: ev.clientY }); const t = this.tab; this.endTabDrag(); if (t && zone) this.dropTab(t, zone); });
      (this.col || document.body).appendChild(z); this.tabZones.push(z);
    }
  }
  private endTabDrag(): void {
    this.tabZones.forEach((z) => z.remove()); this.tabZones = [];
    this.tab = null;
    this.hideOutline();
  }
  private hideOutline(): void {
    if (this.outline) { this.outline.classList.remove("on", "free", "refused"); this.outline.textContent = ""; }
  }
  private tabZoneAt(pt: { x: number; y: number }): Zone | null {
    return zoneAt(this.viewportRects(), pt, { self: null, payload: "tab" as Payload, strips: this.strips() });
  }
  /** The outline for a tab in flight: the landing half of the pane under the pointer, or the strip it would join. */
  private trackTabZone(pt: { x: number; y: number }): void {
    const o = this.outline;
    if (!o || !this.tab) return;
    const rects = this.viewportRects(), strips = this.strips();
    const zone = zoneAt(rects, pt, { self: null, payload: "tab" as Payload, strips });
    const r = zone ? landingRect(rects, zone, strips) : null;
    if (!zone || !r) { this.hideOutline(); return; }
    o.classList.add("on"); o.classList.remove("free", "refused");
    // the refusal previewed as the pane drag's outline does over a strip (the 1900 read: a tab's outline never did): the thin ring
    // where the release will change nothing (a lone column on its own edge, a non-chat pane's strip)
    const w = window as any;
    const sets = (typeof w.__rompChatSets === "function" ? w.__rompChatSets() : null) as Record<string, string[]> | null;
    if (planTabDrop(zone, this.tab.sid, sets).kind === "refuse") o.classList.add("refused");
    o.textContent = "";   // the square says where by its place alone (the user 2026-09-21): no name, no "joins"
    const rr = roundRect(r); o.style.left = rr.x + "px"; o.style.top = rr.y + "px"; o.style.width = rr.w + "px"; o.style.height = rr.h + "px";
  }
  /** A tab dropped in a zone: a strip joins that column (the shipped mutation); an edge opens a new column with the
   *  session (or, for a session alone in a later column, takes that column's pane) and moves its leaf to the target's
   *  edge. The membership store stays the shipped script's; the tree owns where the pane sits. */
  private dropTab(t: { sid: string; name: string }, zone: Zone): void {
    const w = window as any;
    const sets = (typeof w.__rompChatSets === "function" ? w.__rompChatSets() : null) as Record<string, string[]> | null;
    const plan = planTabDrop(zone, t.sid, sets);
    if (plan.kind === "refuse") { this.notify(plan.why); return; }
    if (plan.kind === "join") { try { if (typeof w.__rompMoveTab === "function") w.__rompMoveTab(t.sid, plan.col); } catch { /* the shipped mutation says why */ } this.reconcile(); return; }
    if (plan.kind === "newColumn") {
      // the shipped split opens the column; its romp-chat-cols event runs the reconcile at once, and the dock hint puts
      // the new leaf at the drop edge directly (never right of the last chat first, which would halve that chat's share
      // and re-flow the row on the way)
      if (zone.strip) return;
      this.newChatDock = { target: zone.target, edge: zone.edge as Edge };
      try { if (typeof w.__rompMoveTab === "function") w.__rompMoveTab(t.sid, "new"); } catch { /* the shipped mutation says why */ }
      this.reconcile();
      this.newChatDock = null;
      return;
    }
    const pane: PaneId = plan.pane;   // moveColumn: the lone column's own pane goes to the drop edge
    this.reconcile();
    if (!this.lay || !has(this.lay.tree, pane) || zone.strip || pane === zone.target) return;
    try { this.lay = { ...this.lay, tree: move(this.lay.tree, pane, zone.target, zone.edge as Edge) }; }
    catch (err) { this.notify(String((err as Error).message || err)); return; }
    this.persist(); this.render();
  }
  /** A chat pane released over another chat pane's strip: every session it holds joins that column (a group of tabs is
   *  separable and rejoinable); the emptied column closes through the shipped script and its park is pruned. */
  private joinPaneToStrip(pane: PaneId, target: PaneId): void {
    const w = window as any;
    const col = colNumberOf(target), from = colNumberOf(pane);
    if (col === null || from === null) { this.notify("A pane is not a tab: only a chat pane's sessions can join a strip."); return; }
    if (from === col) return;
    const sids = this.sessionsOf(pane, from);
    if (!sids.length) { this.notify("This pane holds no session to move."); return; }
    for (const sid of sids) { try { if (typeof w.__rompMoveTab === "function") w.__rompMoveTab(sid, col); } catch { /* the shipped mutation says why */ } }
    this.reconcile();
  }
  /** The sessions a chat pane holds: a later column's from the shipped membership sets; the first column's from its
   *  page's own tabs (it lists nothing and holds the rest). */
  private sessionsOf(pane: PaneId, col: number): string[] {
    const w = window as any;
    if (col !== 1) {
      const sets = (typeof w.__rompChatSets === "function" ? w.__rompChatSets() : null) as Record<string, string[]> | null;
      return sets && Array.isArray(sets[String(col)]) ? sets[String(col)].slice() : [];
    }
    const f = frameOfPane(pane);
    try {
      const d = f && f.contentDocument;
      return d ? Array.from(d.querySelectorAll("#tabs .tab[data-id]")).map((t) => String(t.getAttribute("data-id") || "")).filter(Boolean) : [];
    } catch { return []; }
  }

  // ── the dividers ─────────────────────────────────────────────────────────────────────────────────────
  private onDivPress(e: PointerEvent, d: HTMLElement): void {
    if (!this.on || this.press || this.div || e.button !== 0) return;
    const edge = this.divEdges.get(d);
    if (!edge) return;
    e.preventDefault();
    // EVERY edge resizes LIVE, one layout per animation frame (plans/pane-docking.md section 12): a move records the clamped
    // position and arms a frame; the frame applies the latest (a burst of moves costs one relayout, a frame without a move
    // nothing); the iframes are pointer-transparent for the drag (RESIZE_CLASS); the store is written once, at release;
    // Escape restores the press tree live (the band's height too for the band's own edge) and writes only when the restored
    // layout differs from the stored one (a reconcile under the drag deferred its write: reconcile, endDiv). No landing line.
    if (!this.lay) return;
    const tl0 = this.col ? this.col.style.getPropertyValue("--tl") : "";
    // the pair's sizes AT THE PRESS are the drag's frame of reference: every frame applies the pointer's absolute travel to the
    // tree as it was at the press, and the clamp holds against these (the 1927 read: clamping against the tree the drag rewrote
    // every frame shrank the window each frame and the edge stopped at half its range)
    const start = parse(serialise(this.lay)) as Layout;
    const { a0, b0 } = pressGeometry(start.tree, edge);
    this.div = { edge, x0: e.clientX, y0: e.clientY, px: e.clientX, py: e.clientY, want: null, raf: 0, start, tl0, a0, b0 };
    document.body.classList.add(RESIZE_CLASS, edge.dir === "row" && !edge.fixed ? RESIZE_X_CLASS : RESIZE_Y_CLASS);   // the divider's own cursor, over every pane
    const mv = (ev: Event) => this.onDivMove(ev as PointerEvent);
    const up = () => this.endDiv(true);
    // Escape reaches the drag from a focused pane through the engine's own keydown wiring on every pane document (wire, onKey)
    window.addEventListener("pointermove", mv, true); window.addEventListener("pointerup", up, true);
    this.divOff = () => { window.removeEventListener("pointermove", mv, true); window.removeEventListener("pointerup", up, true); };
  }

  private minFrac(edge: EdgeRect): number { return Math.min(0.25, MIN_PX / Math.max(1, edge.avail)); }

  private onDivMove(e: PointerEvent): void {
    const d = this.div;
    if (!d) return;
    e.preventDefault();
    d.px = e.clientX; d.py = e.clientY;   // the pointer's last place: a rebase under the drag re-clamps against it (reconcile)
    if (d.edge.fixed) {
      // the band's edge: its height in px follows the pointer, through the shipped --tl (the observer re-renders)
      if (!this.col) return;
      const cb = this.col.getBoundingClientRect(), box = this.box();
      if (!box) return;
      const bottom = cb.top + box.y + box.h;
      d.want = Math.max(BAND_MIN, Math.min(Math.round(window.innerHeight * 0.7), Math.round(bottom - e.clientY)));
    } else {
      const raw = d.edge.dir === "row" ? e.clientX - d.x0 : e.clientY - d.y0;
      d.want = edgeClamp(d.a0, d.b0, raw, this.minFrac(d.edge) * d.edge.avail);   // against the press geometry, the tree's own minimum in px: the edge follows the pointer to it and no further
    }
    if (!d.raf) d.raf = frameOnce(() => this.applyDiv());
  }

  /** The frame's one layout for the divider drag: the band's height, or the edge moved by the pointer's ABSOLUTE travel from the
   *  press, applied to the tree as it was at the press (dragEdge: the tree keeps the sum, the pair trades, nothing compounds). */
  private applyDiv(): void {
    const d = this.div;
    if (!d) return;
    d.raf = 0;
    if (d.want === null) return;
    if (d.edge.fixed) {
      // the band's edge: the px into the TREE first and the frame rendered from it, then the height variable (kept for the
      // shell's autosize and the phone); the style observer's reconcile then reads the same px and sees no change, so the
      // drag's frames never reach the store (the 1927 read: twelve writes over a twelve-step drag, and Escape leaving the
      // mid-drag height in the store)
      if (!this.col || !this.lay) return;
      this.lay = { ...this.lay, tree: setFixed(this.lay.tree, BAND, d.want) }; this.render();
      this.col.style.setProperty("--tl", d.want + "px");
      return;
    }
    if (!this.lay) return;
    const tree = dragEdge(d.start.tree, d.edge.path, d.edge.i, d.want, d.edge.avail, this.minFrac(d.edge));
    this.lay = { ...this.lay, tree }; this.render();
  }

  /** End the drag: `commit` lands the last recorded position (and renders), Escape restores; `write` (the release's default) persists
   *  the commit; a reconcile that ends the drag under a toggled pane lands without writing and writes the corrected layout itself. */
  private endDiv(commit: boolean, write = true): void {
    const d = this.div;
    if (this.divOff) { this.divOff(); this.divOff = null; }
    if (!d) { this.div = null; document.body.classList.remove(RESIZE_CLASS, RESIZE_X_CLASS, RESIZE_Y_CLASS); return; }
    if (d.raf) { cancelFrame(d.raf); d.raf = 0; }
    if (commit) this.applyDiv();   // the last recorded position lands (and renders) before the write
    this.div = null;
    document.body.classList.remove(RESIZE_CLASS, RESIZE_X_CLASS, RESIZE_Y_CLASS);
    if (commit) { if (write) this.persist(); }
    else {
      // Escape (or the kit going off mid-drag): the press tree back, live (rebased with what a reconcile changed under the
      // drag: reconcile). The band's height variable is restored for the BAND'S edge only, and first, so the style observer's
      // reconcile reads the restored px and sees no change; a column drag never touched the band, so Escape leaves it (the
      // 1927 read: the band's content growth undone by an Escape on the chat|feed divider). Nothing written unless the
      // restored layout differs from the stored one (a band re-sized under the drag: the reconcile deferred its write).
      if (d.edge.fixed && this.col) { if (d.tl0) this.col.style.setProperty("--tl", d.tl0); else this.col.style.removeProperty("--tl"); }
      this.lay = d.start;
      let stored: string | null = null;
      try { stored = localStorage.getItem(LAYOUT_KEY); } catch { stored = null; }
      if (stored !== serialise(this.lay)) this.persist();
      this.render();
    }
  }
}

/** The same set of ids in any order (a leaf set, a parked list). */
function sameSet(a: ReadonlyArray<string>, b: ReadonlyArray<string>): boolean {
  if (a.length !== b.length) return false;
  const sa = a.slice().sort(), sb = b.slice().sort();
  return sa.every((x, i) => x === sb[i]);
}

// boot only in a browser TOP document (guards keep an import in node inert, so the pure exports are testable)
if (typeof window !== "undefined" && typeof document !== "undefined" && (!window.parent || window.parent === window)) {
  const engine = new Engine();
  const apply = () => engine.apply();
  if (document.body) apply(); else document.addEventListener("DOMContentLoaded", apply);
  // re-apply on a gear save in this document, and on a write from another tab (the shell's settings idiom)
  window.addEventListener("romp:settings", apply);
  window.addEventListener("storage", (e) => { if (!e || !e.key || e.key === SETTINGS_KEY) apply(); });
}
