// TAB-TITLE WIDGETS (T379, the user 2026-09-12): the small marks a chat tab's title carries (the status dot at the
// left, the slim context bar and the hot-key keycap after the name) are WIDGETS in a registry, composed onto every tab
// in a configured set and order, and configured from the settings gear (the Chat tab's Tab widgets section), where each
// widget is a row showing
// what it does (a live rendering over a synthetic status), an on/off switch and its own options. The default set is
// the dot and the context bar (and the keycap, which shows only when a hot key is assigned); anything can be added by
// registering it.
//
// ONE module for both bundles: the chat (render.ts composes the strip from it) and the gear (gear.js renders the rows'
// live demos from the same render functions), so a row's demo and the strip can never draw a widget differently.
// Pure over the DOM it is handed (document.createElement), so node tests drive it on a tiny DOM.
//
// Storage: settings.tabWidgets = { on: {id: bool}, order: [id...], opts: {id: {key: value}} } in romp:settings (per
// browser, like every gear setting). `tabCtx` (the older "Context gauge in tabs" mode) stays as the ctx widget's
// MIRROR: a store with no tabWidgets derives them from tabCtx (never -> ctx off; always -> the option), and every save
// writes tabCtx back from the prefs, so older readers keep their meaning (settings.ts loadSettings / saveSettings).
// Order: registration order, then the stored order for the ids it names (drag-to-reorder is a later step; the first
// cut composes in registration order: dot, context bar, hot key).
// The store's shape and rules (normalize, the switch, the options, the order) live in widget-prefs.ts since T409, shared
// with the status line's widgets; the names below stay as this module's, re-exported, so callers and pins stand.
import { tabDotClass, tabDotTitle } from "./tab-state";
import { RING_ORDER, RING_TEST, type RingId, type TabStateLike } from "./tab-state";   // the rings' pure twin (2026-09-14): the precedence, the predicates and the status shape they read
import { ctxFallbackColor, pickTone } from "./ctx-color";
import { effectiveChord, loadOverrides, resolveChord } from "./keybindings";
import { type WidgetChoice, type WidgetOption, type WidgetPrefs, emptyWidgetPrefs, normalizeWidgetPrefs, orderWidgets, sanitizeOrder,
         widgetOn as prefOn, widgetOpts as prefOpts } from "./widget-prefs";

export type { WidgetChoice, WidgetOption };
// THE RING SLOT (the rings-as-widgets change, 2026-09-14): a widget of slot "ring" renders no element; it names the
// CLASS the tab wears (`ring`) and a PREDICATE (`on`) that says when. The strip removes every registered ring class from
// the tab on each paint, then adds the first ring's, in registration order, that is switched on and whose predicate
// holds (composeTabRing), so a tab wears ONE ring at a time, a ring never outlives the state that lit it, and the CSS
// pins can name the classes. Rings have no position: the divider and the stored order never carry one (widgetSlot,
// orderedWidgets, tabWidgetPrefs), and the settings list them as their own group with the same switch as the others.
export type WidgetSlot = "before" | "after" | "ring";
// the status a widget reads: the state and the gauge inputs, plus the fields the ring predicates read (tab-state.ts's
// TabStateLike: the on-you API flags and the feed's needsYou)
export interface WidgetStatus extends TabStateLike { ctx?: string; ctxColor?: number[]; ctxTone?: number[]; faded?: boolean }
export interface TabWidget {
  id: string;                 // "dot" | "ctx" | "hotkey" | a ring's id | a contributor's id
  label: string;              // the settings row's name
  description: string;        // one line: what it shows and when
  defaultOn: boolean;         // the default set
  slot: WidgetSlot;           // before the name, after the name, or a ring around the tab
  ring?: string;              // slot "ring": the class the tab wears while `on` holds (the CSS keys the outline on it)
  on?(sid: string, status: WidgetStatus, opts: Record<string, string>): boolean;   // slot "ring": the predicate
  options?: WidgetOption[];
  render(sid: string, status: WidgetStatus, opts: Record<string, string>): HTMLElement | null;   // null = nothing on this tab (a ring's always is)
  demo?: WidgetStatus;        // the settings row's live rendering renders over this status (else DEMO_STATUS)
  demoSid?: string;           // …for this sid (a widget that reads a per-session store answers for it)
}
export type TabWidgetPrefs = WidgetPrefs;

export const DEMO_STATUS: WidgetStatus = { state: "working", ctx: "62%" };
export const DEMO_SID = "demo";

const REGISTRY: TabWidget[] = [];

/** Register a widget (by id: a second registration replaces the first). Registration order is the default order. */
export function registerTabWidget(w: TabWidget): void {
  const i = REGISTRY.findIndex((x) => x.id === w.id);
  if (i >= 0) REGISTRY[i] = w; else REGISTRY.push(w);
}
export function tabWidgets(): TabWidget[] { return REGISTRY.slice(); }
export function tabWidget(id: string): TabWidget | undefined { return REGISTRY.find((w) => w.id === id); }
/** The widgets that render INTO the title (before or after the name): the settings' Tab widgets rows and the divider list. */
export function titleWidgets(): TabWidget[] { return REGISTRY.filter((w) => w.slot !== "ring"); }
/** The ring widgets in registration order, which IS their precedence: rings take no stored order. */
export function ringWidgets(): TabWidget[] { return REGISTRY.filter((w) => w.slot === "ring"); }

/** The stored prefs, normalized: every field present, junk dropped. With no stored object the ctx widget's prefs
 *  derive from the older tabCtx mode (the mirror), so a store from before the widgets keeps its gauge setting. */
export function tabWidgetPrefs(v: unknown, tabCtx?: unknown): TabWidgetPrefs {
  const o = normalizeWidgetPrefs(v);
  if (o) { o.order = sanitizeOrder(o.order, (id) => id === NAME_DIVIDER || REGISTRY.some((w) => w.id === id && w.slot !== "ring")); return o; }   // the divider's id is an order entry too; a ring's never is (rings have no position)
  const out = emptyWidgetPrefs();
  if (tabCtx === "never") out.on.ctx = false;
  else if (tabCtx === "always") out.opts.ctx = { show: "always" };
  return out;
}

/** The ctx widget's prefs as the older tabCtx mode, for the mirror older readers keep reading. */
export function tabCtxOfPrefs(prefs: TabWidgetPrefs): "always" | "over50" | "never" {
  const ctx = tabWidget("ctx");
  if (ctx ? !widgetOn(prefs, ctx) : prefs.on.ctx === false) return "never";
  return (prefs.opts.ctx && prefs.opts.ctx.show === "always") ? "always" : "over50";
}

export function widgetOn(prefs: TabWidgetPrefs, w: TabWidget): boolean { return prefOn(prefs, w); }

/** A widget's options as it reads them: every key present, an unknown stored value falls to the option's default. */
export function widgetOpts(prefs: TabWidgetPrefs, w: TabWidget): Record<string, string> { return prefOpts(prefs, w); }

/** The DIVIDER (the user's addition to T409): the session NAME's place in the Tab widgets list, a fixed row the widget
 *  rows are dragged above or below. In the stored order it is this id, and a widget's slot is its side of it: before
 *  the divider renders before the name, after it after. A store with no order, or an order without the divider, or a
 *  widget the order does not name, renders the widget's registered slot, so nothing moves until the user drags. */
export const NAME_DIVIDER = "name";
export function widgetSlot(prefs: TabWidgetPrefs, w: TabWidget): WidgetSlot {
  if (w.slot === "ring") return "ring";   // a ring is on neither side of the name, whatever a stored order says
  const at = prefs.order.indexOf(NAME_DIVIDER), i = prefs.order.indexOf(w.id);
  if (at < 0 || i < 0) return w.slot;
  return i < at ? "before" : "after";
}

/** The registered widgets in composition order: the stored order first for the ids it names, then the rest in
 *  registration order; an id the registry does not know is not drawn. Filtered to one slot when asked, the slot being
 *  the widget's side of the divider (widgetSlot). */
export function orderedWidgets(prefs: TabWidgetPrefs, slot?: WidgetSlot): TabWidget[] {
  if (slot === "ring") return ringWidgets();   // registration order, never the stored one
  const out = orderWidgets(prefs, REGISTRY);
  return slot ? out.filter((w) => widgetSlot(prefs, w) === slot) : out;
}

/** The settings rows' visual order: every registered widget's id and the divider, the before-side widgets, the divider,
 *  the after-side widgets, each side in composition order. This is the list a drag or an arrow key reorders (moveId)
 *  and stores back as the order, divider included, so every slot is explicit from the first drag on. */
export function tabListOrder(prefs: TabWidgetPrefs): string[] {
  return [...orderedWidgets(prefs, "before").map((w) => w.id), NAME_DIVIDER, ...orderedWidgets(prefs, "after").map((w) => w.id)];
}

/** Compose one slot onto a tab: every enabled widget of the slot, in order, appended when it renders something.
 *  Returns the nodes appended. */
export function composeTabWidgets(tab: HTMLElement, slot: WidgetSlot, sid: string, status: WidgetStatus, prefs: TabWidgetPrefs): HTMLElement[] {
  const out: HTMLElement[] = [];
  for (const w of orderedWidgets(prefs, slot)) {
    if (!widgetOn(prefs, w)) continue;
    let node: HTMLElement | null = null;
    try { node = w.render(sid, status, widgetOpts(prefs, w)); } catch { node = null; }   // a contributed widget's throw never costs the tab
    if (!node) continue;
    tab.appendChild(node);
    out.push(node);
  }
  return out;
}

/** A settings row's live rendering: the widget over its demo status, as the strip would draw it. */
export function renderWidgetDemo(w: TabWidget, prefs: TabWidgetPrefs): HTMLElement | null {
  try { return w.render(w.demoSid || DEMO_SID, w.demo || DEMO_STATUS, widgetOpts(prefs, w)); } catch { return null; }
}

/** A ring's predicate, guarded: a switched-off ring, a ring without one, and a predicate that throws all read false. */
function ringOn(w: TabWidget, sid: string, status: WidgetStatus, prefs: TabWidgetPrefs): boolean {
  if (w.slot !== "ring" || !w.ring || !w.on || !widgetOn(prefs, w)) return false;
  try { return !!w.on(sid, status, widgetOpts(prefs, w)); } catch { return false; }
}
/** The ring a tab wears: the FIRST registered ring that is switched on and whose predicate holds, or null. */
export function tabRing(sid: string, status: WidgetStatus, prefs: TabWidgetPrefs): TabWidget | null {
  for (const w of ringWidgets()) if (ringOn(w, sid, status, prefs)) return w;
  return null;
}
/** Compose the ring onto a tab: EVERY registered ring class comes off first, then the winner's goes on, so a ring never
 *  survives the state that ended it and two rings never paint at once. Returns the class applied, or null. */
export function composeTabRing(tab: HTMLElement, sid: string, status: WidgetStatus, prefs: TabWidgetPrefs): string | null {
  for (const w of ringWidgets()) if (w.ring) tab.classList.remove(w.ring);
  const win = tabRing(sid, status, prefs);
  if (!win || !win.ring) return null;
  tab.classList.add(win.ring);
  return win.ring;
}
/** The Needs-you PHRASE, one source for the badge dot's aria-label and a cold tab's title
 *  (plans/tab-state-badge.md): a count carries the number, an absent or zero count (an older kernel with the
 *  needsYou bit but no number) reads the bare phrase. Never capped, so the phone leg agrees with the desktop
 *  label above 99, where the visible dot reads "99+". */
export function needsYouPhrase(count: number): string {
  return count > 1 ? count + " things need you" : count === 1 ? "1 thing needs you" : "needs you";
}
/** Badge mode (the tabStateBadge setting, plans/tab-state-badge.md): adjust a tab already composed for ring mode. The
 *  magenta (Needs you) and amber (retrying) rings give way, the Needs-you state becomes a top-right magenta dot and the
 *  retrying state moves to the left status dot in amber; the red ring (Blocked) stays, since Blocked outranks the run
 *  states. Called when the setting is on from render.ts (once per tab per paint) AND from the gear's ring-section demo
 *  (gear.js), so ring mode never touches this and stays byte-identical to today. Idempotent: clears any prior badge dot first (a reused tab). The Needs-you dot carries
 *  status.needsYouCount as a number (the numbered style, plans/tab-state-badge.md): black on the dark magenta, the state's
 *  --st-needs-fg token (white) on the lighter light-theme magenta, "99+" past 99, a bare dot when
 *  the count is absent (an older kernel). Returns the Needs-you dot when one is drawn, else null. */
export function applyTabBadgeMode(tab: HTMLElement, sid: string, status: WidgetStatus, prefs: TabWidgetPrefs): HTMLElement | null {
  for (const d of Array.from(tab.getElementsByClassName("tab-badge"))) d.remove();
  tab.classList.remove("ring-waiting-on-you");   // the Needs-you dot (appended below) replaces the magenta ring, whether or not there is a status-dot slot
  const rt = tabWidget("ring-retrying");
  if (rt && ringOn(rt, sid, status, prefs)) {
    const slot = tab.querySelector<HTMLElement>(".tab-dot");
    if (slot) {
      // move the amber from the ring to the left status dot: toggle the classes, never overwrite the slot's className
      // (it may carry an option class). Drop BOTH `none` and `idle` before adding `retrying`: under the dot widget's
      // "grey dot when idle" option a none-state slot renders as `tab-dot idle`, and the idle rule follows the retrying
      // rule at equal specificity, so a leftover `idle` would paint the amber at idle's dim opacity. The ring comes off
      // and the slot is re-inked in one synchronous pass below, so no paint ever sees the amber missing.
      tab.classList.remove("ring-retrying");
      slot.classList.remove("none", "idle");
      slot.classList.add("retrying");
      slot.title = "retrying an API error on its own";
    }
    // else: the Status dot widget is switched OFF, so there is no slot to carry the amber. This runs after BOTH the
    // before- and after-side widgets compose (render.ts calls it from appendTabAfterWidgets; the gear demo composes both
    // sides before its call too), so a dot dragged past the name is found either way and the widget-off case is the only
    // no-slot one; keep the retrying ring rather than drop it for nothing.
  }
  const nu = tabWidget("ring-waiting-on-you");
  if (nu && ringOn(nu, sid, status, prefs)) {
    const dot = el("span", "tab-badge badge-needs");
    const n = typeof status.needsYouCount === "number" ? status.needsYouCount : 0;
    if (n > 0) dot.textContent = n > 99 ? "99+" : String(n);   // a number sized by the CSS (a pill for two-plus digits); black on the dark magenta, --st-needs-fg (white) on the light; empty stays a bare dot (an older kernel with no count)
    // the dot is pointer-events:none (the close glyph sits under it), so its native title never shows; a screen reader
    // reads the aria-label as an image (not the bare digit), and render.ts adds the phrase to the tab's rich tooltip.
    dot.setAttribute("role", "img");
    dot.setAttribute("aria-label", needsYouPhrase(n));
    tab.appendChild(dot);
    return dot;
  }
  return null;
}
/** A settings row's live rendering of a ring: its class when its predicate lights on its demo status and its switch is
 *  on, else null (the row's demo is a plain tab). */
export function ringDemoClass(w: TabWidget, prefs: TabWidgetPrefs): string | null {
  return ringOn(w, w.demoSid || DEMO_SID, w.demo || DEMO_STATUS, prefs) ? w.ring! : null;
}
/** The rings' switches as a predicate on the id, for the pure twin in tab-state.ts (the folded header's pip): a ring the
 *  registry does not know reads as on, so the twin's own order still decides. */
export function ringSwitch(prefs: TabWidgetPrefs): (id: string) => boolean {
  return (id) => { const w = tabWidget(id); return !w || widgetOn(prefs, w); };
}
/** Whether the Needs-you count badge can appear at all: its own widget switch (badge MODE is the caller's to check). The
 *  strip reserves keycap room only when a badge can show (render.ts's strip class), reading this so the caller need not
 *  name the ring id itself (tab-rings.test.ts bans a hand-rolled ring class in render.ts). */
export function needsYouWidgetOn(prefs: TabWidgetPrefs): boolean { return ringSwitch(prefs)("ring-waiting-on-you"); }

// ── the built-in widgets ──────────────────────────────────────────────────────────────────────────────────────────

function el(tag: string, cls: string): HTMLElement { const e = document.createElement(tag); e.className = cls; return e; }

/** The tab strip's vertical context gauge: fill height = context-used %, coloured by the SAME server-computed
 *  global-colormap RGB the statusline battery / timeline use (setCtxBar), with the same traffic-light fallback for an
 *  older kernel that ships no ctxColor. Passive: a click falls through to the tab's own select. */
export function tabCtxGauge(ctxStr: string, ctxColor?: number[]): HTMLElement {
  const pct = Math.max(0, Math.min(100, parseInt(ctxStr, 10) || 0));
  const g = el("span", "tab-ctx");
  const fill = el("span", "tab-ctx-fill");
  fill.style.height = pct + "%";
  fill.style.background = (ctxColor && ctxColor.length === 3) ? `rgb(${ctxColor.join(",")})`
    : ctxFallbackColor(pct);   // theme-aware pair (ctx-color.ts): classic keeps main's 60/85 verbatim.
  // FILLS wear the tone as-is in every theme: readableRgb is for TEXT (re-encoding the warn amber fill made it a
  // muddy brown on light; the user 2026-08-31, off the live preview)
  g.appendChild(fill);
  g.title = `context ${pct}% used`;
  return g;
}

// The status DOT (T262g, the user 2026-09-08: the slot is laid out in EVERY state and merely hidden when the state
// has no dot, so a tab's width never changes with its state); working gold, awaiting green, opening accent, the
// unknown ring; hidden when idle, or (the widget's option) a quiet grey dot when idle.
registerTabWidget({
  id: "dot", label: "Status dot", defaultOn: true, slot: "before",
  description: "working gold, awaiting green, opening accent; hidden when idle, or a quiet grey dot",
  options: [{ key: "idle", label: "When idle", default: "hide",
              choices: [{ value: "hide", label: "Hide when idle" }, { value: "grey", label: "Grey dot when idle" }] }],
  render(_sid, status, opts) {
    const cls = tabDotClass(status.state);
    if (!cls) return null;                                       // compacting: the animated bar takes the slot (render.ts)
    const d = el("span", cls === "tab-dot none" && opts.idle === "grey" ? "tab-dot idle" : cls);
    const tip = tabDotTitle(status.state);
    if (tip) d.title = tip;
    else if (opts.idle === "grey" && cls === "tab-dot none") d.title = "idle";
    return d;
  },
});

// The CONTEXT BAR (the user 2026-08-08): how full the session's context is, in the colormap's colour; skipped while
// compacting (the bar owns that moment, and the % is about to be wrong) and on dead tabs. The option is WHEN it shows:
// only once half full (the default: a gauge on every quiet tab is clutter), or always; off is the widget's switch.
registerTabWidget({
  id: "ctx", label: "Context bar", defaultOn: true, slot: "after",
  description: "how full the session's context is, in the colormap's colour",
  options: [{ key: "show", label: "Show", default: "over50",
              choices: [{ value: "over50", label: "From 50% full" }, { value: "always", label: "Always" }] }],
  render(_sid, status, opts) {
    const st = status.state;
    if (!status.ctx || st === "compacting" || st === "closed") return null;
    const pct = Math.max(0, Math.min(100, parseInt(status.ctx, 10) || 0));
    if (opts.show !== "always" && pct < 50) return null;
    return tabCtxGauge(status.ctx, pickTone(status.ctxColor, status.ctxTone));
  },
});

// The HOT KEY keycap (the user 2026-09-12, amending T379): the chord that switches to this tab, at its shortest, after
// the name. The per-tab hot keys live under romp:tabkeys (a set of sids) with a keybinding override per sid under
// session.hotkey.<sid>; the tab menu's Hot key… row assigns one (render.ts, through the shell's shortcuts recorder) and
// palette-main.ts registers the "Switch to <name>" command per sid from the set (tab-keys.ts owns the set's rules); the
// keycap renders nothing until a hot key is assigned. No options.
export const TABKEYS_KEY = "romp:tabkeys";
export const HOTKEY_PREFIX = "session.hotkey.";
const IS_MAC = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test((navigator as { platform?: string }).platform || "");
export function tabHotkey(sid: string, storage: { getItem(k: string): string | null } | null = typeof localStorage !== "undefined" ? localStorage : null): string {
  if (!storage) return "";
  let set: Record<string, unknown> = {};
  try { const d = JSON.parse(storage.getItem(TABKEYS_KEY) || "{}"); set = d && typeof d === "object" ? d : {}; } catch { set = {}; }
  if (!(sid in set)) return "";
  return effectiveChord(HOTKEY_PREFIX + sid, undefined, loadOverrides(), IS_MAC);
}
/** The keycap's text: the chord at its shortest, symbols and no separators (the shortest keycap form). */
export function miniChord(chord: string, mac = IS_MAC): string {
  if (!chord) return "";
  const c = resolveChord(chord, mac);
  const KEYCAP: Record<string, string> = { ArrowLeft: "←", ArrowRight: "→", ArrowUp: "↑", ArrowDown: "↓", " ": "␣" };
  const SYM: Record<string, string> = { Ctrl: "⌃", Alt: "⌥", Shift: "⇧", Meta: mac ? "⌘" : "◆" };
  return c.split("+").map((p) => SYM[p] || KEYCAP[p] || p).join("");
}
registerTabWidget({
  id: "hotkey", label: "Hot key", defaultOn: true, slot: "after",
  description: "the tab's hot key, when one is assigned",
  render(sid) {
    const chord = sid === DEMO_SID ? "Ctrl+Shift+1" : tabHotkey(sid);
    if (!chord) return null;
    const k = el("span", "tab-key");
    k.textContent = miniChord(chord);
    k.title = "hot key " + chord + ": switches to this tab";
    k.setAttribute("aria-label", k.title);
    return k;
  },
});

// THE RINGS (the rings-as-widgets change, 2026-09-14): the three dashed rings a tab can wear are widgets of slot "ring",
// each with its own switch in the settings' Tab widgets section, registered in PRECEDENCE order, red over magenta over
// amber (composeTabRing paints the first that is switched on and applies; a stored order never moves a ring). The
// predicates are tab-state.ts's RING_TEST, the pure twin the folded header's pip reads, so the strip and the pip cannot
// disagree. The colours are the tokens the tab already wears (styles.css: the red and the amber rings read the state's
// --state, the Needs you ring its own --st-needs-bg); the rows' demos wear the same classes through gear.css. No options.
// The names (plans/needs-you.md, the user 2026-09-20): Blocked is the hard stop, Needs you the category; the ids stay (they key the stored switches).
const RING_ROWS: Record<RingId, { label: string; description: string; demo: WidgetStatus }> = {
  "ring-needs-you": { label: "Blocked", demo: { state: "awaiting" },
                      description: "while the session is stopped: on a prompt, or on an API error only you can clear" },
  "ring-waiting-on-you": { label: "Needs you", demo: { state: "working", needsYou: true, needsYouCount: 2 },
                           description: "while a card of the session's needs you, even as it goes on working; Blocked outranks it, though the state badge shows both at once" },
  "ring-retrying": { label: "Retrying", demo: { state: "retrying" },
                     description: "while the session retries an API error on its own; Blocked outranks it, and Needs you does too, though the state badge shows Needs you and retrying at once" },
};
for (const id of RING_ORDER) {
  registerTabWidget({ id, label: RING_ROWS[id].label, description: RING_ROWS[id].description, defaultOn: true, slot: "ring", ring: id,
                      on: (_sid, status) => RING_TEST[id](status), render: () => null, demo: RING_ROWS[id].demo });
}
