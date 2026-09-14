// WIDGET PREFERENCES: the store shape and the rules the tab-title widgets set (T379) and the status line's widgets
// share (T409, the user 2026-09-13). Per registry, under romp:settings: `{ on: {id: bool}, order: [id...], opts: {id:
// {key: value}} }`. Pure over plain objects, so node tests drive it without a DOM. Moved here from tab-widgets.ts with
// no change in behaviour; that module keeps its names as re-exports, so its callers and its pins stand.
//
// Every registry carries its own ORDER from day one (the user's addition to T409: the settings rows reorder by drag in
// the next step and the order IS the render order): a store with no order renders registration order until the user
// drags, and an id the registry does not know is not drawn.
export interface WidgetChoice { value: string; label: string }
export interface WidgetOption { key: string; label: string; choices: WidgetChoice[]; default: string }
export interface WidgetPrefs { on: Record<string, boolean>; order: string[]; opts: Record<string, Record<string, string>> }
/** What the rules need of a widget: its id, its default switch and its options schema. */
export interface WidgetLike { id: string; defaultOn: boolean; options?: WidgetOption[] }

export function emptyWidgetPrefs(): WidgetPrefs { return { on: {}, order: [], opts: {} }; }

/** A stored order made sane: each id once (its first place kept) and, given the registry's test, only ids it knows,
 *  so a malformed store is rewritten clean by its next save rather than carried forever (review round one of the
 *  status line's widgets). A registry's own normalizer supplies `known`; a widget registered after the store was read
 *  (none today: every widget registers at import) would lose its stored place, which is the price of a clean store. */
export function dedupe(ids: readonly string[]): string[] {
  const out: string[] = [];
  for (const id of ids) if (!out.includes(id)) out.push(id);
  return out;
}
export function sanitizeOrder(order: readonly string[], known: (id: string) => boolean): string[] {
  return dedupe(order.filter(known));
}

/** A stored object normalized: every field present, junk dropped. Null when the store holds no object at all, so the
 *  caller can derive from the keys its widgets replaced (the tab widgets from tabCtx, the status line's from
 *  showBranch and showSessionBadge). */
export function normalizeWidgetPrefs(v: unknown): WidgetPrefs | null {
  const o = (v && typeof v === "object" ? v : null) as Record<string, unknown> | null;
  if (!o) return null;
  const out = emptyWidgetPrefs();
  const on = (o.on && typeof o.on === "object" ? o.on : {}) as Record<string, unknown>;
  for (const k of Object.keys(on)) if (typeof on[k] === "boolean") out.on[k] = on[k] as boolean;
  if (Array.isArray(o.order)) out.order = dedupe(o.order.filter((x): x is string => typeof x === "string"));
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

/** The widget's switch: the stored boolean, else its default. */
export function widgetOn(prefs: WidgetPrefs, w: WidgetLike): boolean {
  const v = prefs.on[w.id];
  return typeof v === "boolean" ? v : w.defaultOn;
}

/** A widget's options as it reads them: every key present, an unknown stored value falls to the option's default. */
export function widgetOpts(prefs: WidgetPrefs, w: WidgetLike): Record<string, string> {
  const out: Record<string, string> = {};
  const stored = prefs.opts[w.id] || {};
  for (const o of w.options || []) {
    const v = stored[o.key];
    out[o.key] = o.choices.some((c) => c.value === v) ? v : o.default;
  }
  return out;
}

/** A registry in composition order: the stored order first for the ids it names, then the rest in registration
 *  order; an id the registry does not know is not drawn. */
export function orderWidgets<W extends WidgetLike>(prefs: WidgetPrefs, registry: readonly W[]): W[] {
  const byId = new Map(registry.map((w) => [w.id, w] as const));
  const out: W[] = [];
  for (const id of prefs.order) { const w = byId.get(id); if (w && !out.includes(w)) out.push(w); }
  for (const w of registry) if (!out.includes(w)) out.push(w);
  return out;
}

/** A row moved within a list of ids (the settings rows' visual order, dividers included): the id taken out and put
 *  back at `to`, an index into the list WITHOUT the id; an unknown id or an out-of-range index leaves the list as it
 *  was. Pure, so the drag and the keyboard road (and their tests) share one rule. */
export function moveId(list: readonly string[], id: string, to: number): string[] {
  const i = list.indexOf(id);
  if (i < 0) return list.slice();
  const rest = list.filter((x) => x !== id);
  const at = Math.max(0, Math.min(rest.length, Math.floor(to)));
  if (!Number.isFinite(to)) return list.slice();
  rest.splice(at, 0, id);
  return rest;
}
