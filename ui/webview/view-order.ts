// THE VIEWER'S OWN session order (the user 2026-07-31), replacing the kernel's as the thing that decides
// what sits where.
//
// Until now each kernel owned the order of its own sessions (session-order.json) and the browser
// CONCATENATED the per-host lists, local first. That made host blocks: a local session could never sit
// between two of a server's, and a drag that mixed them was undone on the next merge, because no single
// kernel can record an order over sids it does not know about.
//
// The user's ruling is that order is a property of how you are LOOKING at the fleet, not of the fleet: two
// machines reading the same sessions should be free to arrange them differently, and dragging a tab on the
// laptop has no business moving it on the desktop. So the arrangement lives in the browser, keyed by
// host-prefixed id, and each kernel's list becomes a SEED — the arrival order new sessions come in on.
//
// The layering is deliberately one-way and lossless:
//   seed  = the per-host concatenation, exactly what shipped before this module
//   view  = the ids this viewer has arranged, in their arranged order
//   shown = every id the view names, in view order, then everything else in SEED order
// An empty view is the identity transform, so a viewer who has never dragged sees precisely the old
// behaviour, and the first drag is what takes ownership.
//
// The three surfaces that must agree on this (chat tab strip, timeline lanes, feed grouped mode) read the
// same key out of the same origin's localStorage, so they cannot drift; federation.ts applies this at all
// three merge points and re-emits when the key changes under it.

export const VIEW_ORDER_KEY = "romp:vieworder";
// Backstop only — the prune below is the real bound (it drops ids the owning host has stopped listing).
// This exists so a bug in that rule can never grow the entry without limit.
export const VIEW_ORDER_CAP = 2000;

/** Fired on the writing window, since `storage` events reach only OTHER contexts. Panes listen to both. */
export const VIEW_ORDER_EVENT = "romp-vieworder";

/** Order `seed` by this viewer's arrangement. Ids `view` names come first, in view order; everything else
 *  keeps its SEED order behind them — so a session that arrives after the last drag lands at the end rather
 *  than in an arbitrary spot. Ids in `view` that are not in `seed` (a cleared session, a detached host) are
 *  simply absent from the result; they stay in storage, because a detached host's sessions come back.
 *
 *  An EMPTY view returns the seed unchanged: this is the identity transform, not a re-sort, so nothing moves
 *  until the viewer moves it. Non-strings and duplicates are dropped from both inputs. */
export function applyViewOrder(seed: readonly string[], view: readonly string[]): string[] {
  const clean = (xs: readonly string[]) => {
    const out: string[] = [];
    const seen = new Set<string>();
    for (const x of xs) if (typeof x === "string" && !seen.has(x)) { seen.add(x); out.push(x); }
    return out;
  };
  const s = clean(seed);
  if (!view || !view.length) return s;
  const want = new Set(s);
  const placed = new Set<string>();
  const out: string[] = [];
  for (const id of clean(view)) if (want.has(id)) { placed.add(id); out.push(id); }
  for (const id of s) if (!placed.has(id)) out.push(id);
  return out;
}

/** Sort `rows` (session-ish objects carrying `idKey`) into the same order applyViewOrder would put their
 *  ids in. Used for the timeline's lanes, which are objects rather than a bare id list. Rows whose id the
 *  merge doesn't name keep their relative position at the end. */
export function applyViewOrderTo<T>(rows: readonly T[], view: readonly string[], idOf: (r: T) => string): T[] {
  const seed = rows.map(idOf);
  const rank = new Map(applyViewOrder(seed, view).map((id, i) => [id, i] as const));
  // index-carrying decorate/sort/undecorate: Array#sort is stable in every engine romp runs on, but being
  // explicit costs nothing and keeps ties (two rows with the same id) in their arrival order.
  return rows
    .map((r, i) => ({ r, i, k: rank.has(idOf(r)) ? rank.get(idOf(r))! : Number.MAX_SAFE_INTEGER }))
    .sort((a, b) => (a.k - b.k) || (a.i - b.i))
    .map((x) => x.r);
}

/** Drop arrangement entries for sessions that are GONE, and only those.
 *
 *  Event-based, not aged out: an id is dropped only when the host that OWNS it is currently reporting its
 *  sessions and that report does not contain it. A host that is detached or unreachable reports nothing, so
 *  its ids are untouched — otherwise a tunnel blip would silently flatten the arrangement of every remote
 *  session, and they would all come back at the end of the list.
 *
 *  @param hostOf   the host key an id belongs to ("" for local) — federation's own hostOf
 *  @param reporting hosts whose session list is in hand this merge
 *  @param live     every id those hosts are currently listing */
export function pruneViewOrder(
  view: readonly string[],
  hostOf: (id: string) => string,
  reporting: ReadonlySet<string>,
  live: ReadonlySet<string>,
): string[] {
  const kept = view.filter((id) => typeof id === "string" && (!reporting.has(hostOf(id)) || live.has(id)));
  return kept.length > VIEW_ORDER_CAP ? kept.slice(kept.length - VIEW_ORDER_CAP) : kept;
}

/** Parse a stored blob. Anything malformed reads as "no arrangement" rather than throwing — a corrupt entry
 *  must cost you your ordering, never the dashboard. */
export function parseViewOrder(raw: string | null | undefined): string[] {
  if (!raw) return [];
  try {
    const o = JSON.parse(raw);
    if (!Array.isArray(o)) return [];
    return o.filter((x): x is string => typeof x === "string");
  } catch {
    return [];
  }
}

export function readViewOrder(): string[] {
  try {
    return parseViewOrder(localStorage.getItem(VIEW_ORDER_KEY));
  } catch {
    return [];   // private mode / blocked storage → the seed order, exactly as before this module
  }
}

/** Persist an arrangement and tell every pane. `storage` fires only in OTHER same-origin contexts, so the
 *  writing window gets the same news through a CustomEvent — one notification path, two deliveries. */
export function writeViewOrder(order: readonly string[]): void {
  const list = order.filter((x) => typeof x === "string");
  try {
    localStorage.setItem(VIEW_ORDER_KEY, JSON.stringify(list));
  } catch {
    /* quota / private mode → this drag just doesn't outlive the page; the strip still shows it */
  }
  try {
    window.dispatchEvent(new CustomEvent(VIEW_ORDER_EVENT));
  } catch {
    /* no window (node test) */
  }
}
