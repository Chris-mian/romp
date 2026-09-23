// THE VIEWER'S OWN session order — arranged in the browser, KEPT BY THE KERNEL so it follows you from
// one device to the next (the user 2026-09-23). Two rulings stacked, and they are about different things.
//
// 2026-07-31 (commit e9870995, the maintainer's) moved the order OFF the kernel, for a reason that still
// holds and is not touched here: each kernel owned the order of its own sessions (session-order.json) and
// the browser CONCATENATED the per-host lists, local first. That made host blocks — a local session could
// never sit between two of a server's, and a drag that mixed them was undone on the next merge — because
// no single kernel can ORDER sids it does not know about. Everything below that computes the arrangement
// still runs in the browser, which is the only place that can see every host at once.
//
// What 2026-09-23 reverses is the preference that rode along with it: that two machines reading the same
// sessions should each keep their own arrangement, and that dragging on the laptop has no business moving
// it on the desktop. It turned out to mean a phone and a desktop showing the same sessions in different
// orders with no way to reconcile them, which is the bug the user hit. They want ONE arrangement across
// their devices, as the default. So the computed list is handed to the kernel this browser is talking to,
// which PERSISTS it, SERVES it on connect and PUSHES it when it changes — as OPAQUE DATA. That is not the
// thing the 2026-07-31 objection rules out: the kernel stores an ordered list of host-prefixed ids it
// never reads, never matches against its own sessions and never reorders. The browser still decides the
// order, hosts still interleave, and no kernel is asked to know another's sids.
//
// The layering is unchanged, one-way and lossless:
//   seed  = the per-host concatenation, exactly what shipped before this module
//   view  = the ids this viewer has arranged, in their arranged order
//   shown = every id the view names, in view order, then everything else in SEED order
// An empty view is the identity transform, so a viewer who has never dragged sees precisely the old
// behaviour. Since 2026-08-10 the arrangement is DENSE: a host's own report ADOPTS any id the viewer
// has never placed by appending it at the end (adoptArrivals below, called from federation's
// absorbHostReport) — so a NEW session lands at the end of the whole strip, not at the end of its
// host's block mid-strip, and the placement survives merges and reloads. A drag was already dense
// (commitTabOrder writes the full rendered order); adoption just stops the never-dragged and
// stale-arrangement states from re-deriving host-block positions for newcomers.
//
// The three surfaces that must agree on this (chat tab strip, timeline lanes, feed grouped mode) read the
// same key out of the same origin's localStorage, so they cannot drift; federation.ts applies this at all
// three merge points and re-emits when the key changes under it. What moved on 2026-09-23 is where that
// key's value COMES FROM and how a change is announced — nothing else.

/** The pre-2026-09-23 arrangement: the one this browser kept for itself. READ ONLY from here on — it is
 *  what a browser upgrading into the shared arrangement publishes when the kernel has none yet, and it is
 *  deliberately never written again, so reverting this change hands the viewer back exactly the order they
 *  had. Still the read of last resort, so the first paint after an upgrade (before the kernel's first
 *  viewOrder frame lands) is the order they are used to rather than the seed. */
export const VIEW_ORDER_KEY = "romp:vieworder";
/** The kernel's arrangement, cached for this browser. The kernel is the authority; this is what a reload
 *  paints from before its first frame arrives, and — because `storage` crosses same-origin contexts — it is
 *  also how a drag in one pane reaches every other pane of the same page. */
export const VIEW_ORDER_SHARED_KEY = "romp:vieworder:shared";
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

/** Append every seed id the arrangement has never placed at its END — in seed order among themselves.
 *  This is what puts a NEW session at the end of the WHOLE strip rather than at the end of its host's
 *  block mid-strip (the user 2026-08-10: a fresh session's provisional tab rendered last, then the merge
 *  re-derived host-block order and popped it in front of a remote host's sessions). Adopting writes the
 *  placement down, so it holds across merges and reloads instead of depending on which hosts happen to
 *  sit later in the seed. Ids already placed are untouched — this never re-arranges, only appends. */
export function adoptArrivals(view: readonly string[], seed: readonly string[]): string[] {
  const have = new Set(view.filter((id) => typeof id === "string"));
  const out = view.filter((id) => typeof id === "string");
  for (const id of seed) {
    if (typeof id === "string" && !have.has(id)) {
      have.add(id);
      out.push(id);
    }
  }
  return out;
}

/** Rewrite arrangement ids through `swap` (old id → its heir), keeping their positions: the SLOT follows
 *  the session, not the fsid. Duplicates that a swap would create keep the first occurrence. */
export function healOrder(view: readonly string[], swap: ReadonlyMap<string, string>): string[] {
  if (!swap.size) return view.filter((id) => typeof id === "string");
  const out: string[] = [];
  const seen = new Set<string>();
  for (const id of view) {
    if (typeof id !== "string") continue;
    const next = swap.get(id) || id;
    if (!seen.has(next)) {
      seen.add(next);
      out.push(next);
    }
  }
  return out;
}

/** One host's report, diffed against its previous one: which ids were SWAPPED rather than closed+opened.
 *  A /clear or a relaunch mints a NEW transcript fsid for the SAME logical session, and the kernel's own
 *  order inherits the old slot by the stable session NAME (`_ordered`, the 2026-06-29 fix). The viewer's
 *  arrangement must inherit the same way, or the relaunched session would read as brand-new and jump to
 *  the end of the strip. An id that vanished from the report is matched to an id that appeared in it and
 *  carries the same display name (first unclaimed wins, mirroring the kernel); no name, no match. SDK
 *  session ids are stable, so this fires only for the transcript-fsid (tmux) world. */
export function churnSwaps(
  prevOrder: readonly string[], prevNames: ReadonlyMap<string, string>,
  nextOrder: readonly string[], nextNames: ReadonlyMap<string, string>,
): Map<string, string> {
  const prevSet = new Set(prevOrder);
  const nextSet = new Set(nextOrder);
  const fresh = nextOrder.filter((id) => !prevSet.has(id));
  const swaps = new Map<string, string>();
  const claimed = new Set<string>();
  for (const oldId of prevOrder) {
    if (nextSet.has(oldId)) continue;
    const name = prevNames.get(oldId);
    if (!name) continue;
    const heir = fresh.find((id) => !claimed.has(id) && nextNames.get(id) === name);
    if (heir) {
      claimed.add(heir);
      swaps.set(oldId, heir);
    }
  }
  return swaps;
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

/** One key's stored arrangement, or null when the key is ABSENT (or storage is blocked, which is the same
 *  thing to every reader here). Distinct from `[]`, which is a real, deliberately empty arrangement. */
function readKey(key: string): string[] | null {
  try {
    const raw = localStorage.getItem(key);
    return raw == null ? null : parseViewOrder(raw);
  } catch {
    return null;   // private mode / blocked storage → the seed order, exactly as before this module
  }
}

/** The arrangement to show: the kernel's, once this browser has one, else the pre-move local key (the
 *  order the viewer had before the arrangement was shared — see VIEW_ORDER_KEY), else nothing, which is
 *  the identity transform. Re-read per use, never cached: another PANE of this page writes the same key. */
export function readViewOrder(): string[] {
  const shared = readKey(VIEW_ORDER_SHARED_KEY);
  return shared !== null ? shared : (readKey(VIEW_ORDER_KEY) || []);
}

/** How the arrangement reaches the kernel. federation.js publishes `window.__rompPublishViewOrder` for
 *  every bundle on the page — the pane bundles get their own MODULE copy of this file, so a slot on the
 *  window is the only channel that crosses them, exactly as `__rompFed` and `__rompWriteOrder` do. A page
 *  that never has a federation manager (a VS Code webview, a node test) installs one directly instead
 *  (setViewOrderPublisher). Neither → nothing is published, and the arrangement is this browser's alone,
 *  which is what a page with no manager has always had. */
export type ViewOrderPublisher = (order: readonly string[]) => void;
let directPublisher: ViewOrderPublisher | null = null;

export function setViewOrderPublisher(fn: ViewOrderPublisher | null): void {
  directPublisher = fn;
}

export function viewOrderPublisher(): ViewOrderPublisher | null {
  try {
    const slot = (globalThis as any).window?.__rompPublishViewOrder;
    if (typeof slot === "function") return slot as ViewOrderPublisher;
  } catch { /* no window */ }
  return directPublisher;
}

function cacheShared(list: readonly string[]): void {
  try {
    localStorage.setItem(VIEW_ORDER_SHARED_KEY, JSON.stringify(list));
  } catch {
    /* quota / private mode → this drag just doesn't outlive the page; the strip still shows it */
  }
}

function announce(): void {
  try {
    window.dispatchEvent(new CustomEvent(VIEW_ORDER_EVENT));
  } catch {
    /* no window (node test) */
  }
}

/** Persist an arrangement, PUBLISH it to the kernel, and tell every pane. `storage` fires only in OTHER
 *  same-origin contexts, so the writing window gets the same news through a CustomEvent — one notification
 *  path, two deliveries; the kernel's own push is the third, and it is what carries the change to this
 *  viewer's other devices. Last write wins: the kernel keeps the newest list it was handed and says so. */
export function writeViewOrder(order: readonly string[]): void {
  const list = order.filter((x) => typeof x === "string");
  cacheShared(list);
  const publish = viewOrderPublisher();
  if (publish) {
    try { publish(list); } catch { /* a dead socket: the local cache still holds this drag */ }
  }
  announce();
}

/** Take the arrangement the kernel just served. Writes the cache and tells every pane — but ONLY when it
 *  differs from what this browser already holds: adopting an unchanged list would announce a move that did
 *  not happen, and every viewer sees its own publish come back. Returns whether anything changed. */
export function adoptSharedOrder(order: readonly string[]): boolean {
  const list = order.filter((x): x is string => typeof x === "string");
  const held = readKey(VIEW_ORDER_SHARED_KEY);
  if (held !== null && held.length === list.length && held.every((id, i) => id === list[i])) return false;
  cacheShared(list);
  announce();
  return true;
}

/** The migration, as a decision (2026-09-23). `stored` is the kernel viewOrder frame's word on whether that
 *  kernel has an arrangement AT ALL, which is not the same as an empty one (a viewer may deliberately
 *  arrange nothing, and an emptied arrangement must not be refilled from somebody's old local key).
 *  `local` is what this browser holds (readViewOrder).
 *
 *  Returns the list to PUBLISH, or null to adopt the kernel's:
 *  - the kernel has an arrangement → it wins, whatever this browser holds. The pre-move local key is left
 *    exactly where it is, so reverting this change is harmless.
 *  - the kernel has none and this browser does → publish it, so an existing arrangement survives the move
 *    (and so a kernel whose store was lost is refilled by the first viewer that connects).
 *  - neither → nothing to do; the empty arrangement stays the identity transform. */
export function viewOrderToPublish(stored: boolean, local: readonly string[]): string[] | null {
  if (stored) return null;
  const mine = local.filter((x): x is string => typeof x === "string");
  return mine.length ? mine : null;
}
