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
import { tabDotClass, tabDotTitle } from "./tab-state";
import { ctxFallbackColor, pickTone } from "./ctx-color";
import { effectiveChord, loadOverrides, resolveChord } from "./keybindings";

export type WidgetSlot = "before" | "after";
export interface WidgetChoice { value: string; label: string }
export interface WidgetOption { key: string; label: string; choices: WidgetChoice[]; default: string }
export interface WidgetStatus { state?: string; ctx?: string; ctxColor?: number[]; ctxTone?: number[]; faded?: boolean }
export interface TabWidget {
  id: string;                 // "dot" | "ctx" | "hotkey" | a contributor's id
  label: string;              // the settings row's name
  description: string;        // one line: what it shows and when
  defaultOn: boolean;         // the default set
  slot: WidgetSlot;           // before the name, after the name
  options?: WidgetOption[];
  render(sid: string, status: WidgetStatus, opts: Record<string, string>): HTMLElement | null;   // null = nothing on this tab
  demo?: WidgetStatus;        // the settings row's live rendering renders over this status (else DEMO_STATUS)
  demoSid?: string;           // …for this sid (a widget that reads a per-session store answers for it)
}
export interface TabWidgetPrefs { on: Record<string, boolean>; order: string[]; opts: Record<string, Record<string, string>> }

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

/** The stored prefs, normalized: every field present, junk dropped. With no stored object the ctx widget's prefs
 *  derive from the older tabCtx mode (the mirror), so a store from before the widgets keeps its gauge setting. */
export function tabWidgetPrefs(v: unknown, tabCtx?: unknown): TabWidgetPrefs {
  const o = (v && typeof v === "object" ? v : null) as Record<string, unknown> | null;
  const out: TabWidgetPrefs = { on: {}, order: [], opts: {} };
  if (!o) {
    if (tabCtx === "never") out.on.ctx = false;
    else if (tabCtx === "always") out.opts.ctx = { show: "always" };
    return out;
  }
  const on = (o.on && typeof o.on === "object" ? o.on : {}) as Record<string, unknown>;
  for (const k of Object.keys(on)) if (typeof on[k] === "boolean") out.on[k] = on[k] as boolean;
  if (Array.isArray(o.order)) out.order = o.order.filter((x): x is string => typeof x === "string");
  const opts = (o.opts && typeof o.opts === "object" ? o.opts : {}) as Record<string, unknown>;
  for (const k of Object.keys(opts)) {
    const w = opts[k];
    if (!w || typeof w !== "object") continue;
    const row: Record<string, string> = {};
    for (const key of Object.keys(w as Record<string, unknown>)) { const val = (w as Record<string, unknown>)[key]; if (typeof val === "string") row[key] = val; }
    out.opts[k] = row;
  }
  return out;
}

/** The ctx widget's prefs as the older tabCtx mode, for the mirror older readers keep reading. */
export function tabCtxOfPrefs(prefs: TabWidgetPrefs): "always" | "over50" | "never" {
  const ctx = tabWidget("ctx");
  if (ctx ? !widgetOn(prefs, ctx) : prefs.on.ctx === false) return "never";
  return (prefs.opts.ctx && prefs.opts.ctx.show === "always") ? "always" : "over50";
}

export function widgetOn(prefs: TabWidgetPrefs, w: TabWidget): boolean {
  const v = prefs.on[w.id];
  return typeof v === "boolean" ? v : w.defaultOn;
}

/** A widget's options as it reads them: every key present, an unknown stored value falls to the option's default. */
export function widgetOpts(prefs: TabWidgetPrefs, w: TabWidget): Record<string, string> {
  const out: Record<string, string> = {};
  const stored = prefs.opts[w.id] || {};
  for (const o of w.options || []) {
    const v = stored[o.key];
    out[o.key] = o.choices.some((c) => c.value === v) ? v : o.default;
  }
  return out;
}

/** The registered widgets in composition order: the stored order first for the ids it names, then the rest in
 *  registration order; an id the registry does not know is not drawn. Filtered to one slot when asked. */
export function orderedWidgets(prefs: TabWidgetPrefs, slot?: WidgetSlot): TabWidget[] {
  const byId = new Map(REGISTRY.map((w) => [w.id, w] as const));
  const out: TabWidget[] = [];
  for (const id of prefs.order) { const w = byId.get(id); if (w && !out.includes(w)) out.push(w); }
  for (const w of REGISTRY) if (!out.includes(w)) out.push(w);
  return slot ? out.filter((w) => w.slot === slot) : out;
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
// session.hotkey.<sid>; nothing in this tree writes them yet, so the keycap composes the day an assignment ships, and
// renders nothing until a hot key is assigned. No options.
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
