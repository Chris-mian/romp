// CHAT COLUMNS, the page's half of the partition (the user 2026-09-11, who asked for columns that hold
// different sessions instead of each showing the whole board). The shell owns ONE fact: which sessions each
// later column holds, persisted under `romp-chat-cols` and read by every column page through the parent
// window's `__rompChatSets()` as `{"2": [sid…], "3": [sid…]}`. The first column has no entry: it holds every
// session no entry lists, so a session that arrives with no gesture (a peer's spawn, a remote host's tabs, a
// revive whose column has closed) lands there. Each page filters its strip by that fact through `tabInView`
// (render.ts), so the keyboard walk, the hidden-active re-point, the tag sections and the strip signature
// compose with it for free. Pure: no DOM, no window; render.ts hands it the search string and the sets.
import { hostOf } from "./host-prefix";

export type ColSets = Record<string, string[]>;

/** The column this page is, from its own `location.search`: the pane shim's rule, byte for byte. The first
 *  column is `""` (`?col=1` folds to it, so its state blob keeps the unsuffixed key every older page had);
 *  every later column is its number as a string; a standalone page or the VS Code webview has no search. */
export function colFromSearch(search: string): string {
  let col = "";
  try { col = new URLSearchParams(search || "").get("col") || ""; } catch { col = ""; }
  return col === "1" ? "" : col;
}

/** The column whose entry lists `id`, else `""` (the first column, which derives). A doubly listed id (a
 *  store another dashboard wrote before this shell reconciled it; the shell's own writes never produce one
 *  and its `sets()` resolves one by row order) belongs to ONE column, the first key holding it, so no two
 *  columns ever both show a tab for it. */
export function ownerOf(sets: ColSets, id: string): string {
  for (const col of Object.keys(sets)) {
    const ids = sets[col];
    if (Array.isArray(ids) && ids.includes(id)) return col;
  }
  return "";
}

/** Whether column `col` holds `id` under `sets`. `null` sets means no partition at all (a standalone page,
 *  the VS Code webview, the phone, a shell without the split script): everything is held. A later column
 *  holds the ids its entry lists; the first column (`""`) holds every id no entry lists. */
export function columnHolds(sets: ColSets | null, col: string, id: string): boolean {
  if (sets === null) return true;
  return ownerOf(sets, id) === col;
}

/** What a later column can say about its members from one strip: `held` (a member is on the strip, or the kernel's live
 *  set still affirms one the user has not crossed — or there is nothing to judge), `unknown` (no member is present, and at
 *  least one member's host has not reported on this socket yet), `empty` (every member's host has reported and none is
 *  present: the one verdict that closes the column). */
export type Emptiness = "held" | "unknown" | "empty";

/** A set-like reader: the live set, the closing map and the hosts-seen set only ever answer `has`. */
export interface HasSet { has(key: string): boolean }

/**
 * The column's emptiness verdict (render.ts noteColumnEmptiness): `mine` the ids the shell's entry lists for this column,
 * `listed` the strip's ids this render (closing tabs already excluded), `live` the kernel's affirmed-live set from the last
 * strip (T258: a member the strip omits while live still names it is a transient read failure, never an emptiness — unless
 * this page's own ✕ removed it, `closing`), and `hostsSeen` the hosts whose OWN strip has landed on this socket (tab-order.ts
 * stripHost; the local kernel is host "").
 *
 * The host rule (the user 2026-09-14): a member is ABSENT only when its host has reported and does not list it. Under
 * federation the local kernel's strip lands first and says nothing about a remote host's sessions; a remote's own strip
 * lands a moment later (`hostsPending` names it until then). Before this rule a column opened on a host-prefixed tab
 * judged it gone at the first local strip — the member was in neither the merged order nor the live set, both still
 * local-only — posted colEmpty, and the shell folded the column ~250 ms after the drop that made it, the tab snapping back
 * to the column it left. A loopback board with bare ids never showed it: there the only host IS the one that reported.
 * No timer: the host's strip landing is the event, and a host that never reports (down, detached, never attached) leaves
 * the column standing with its member awaited, the way a down host's tabs stand on the strip.
 */
export function columnEmptiness(mine: readonly string[], listed: readonly string[], live: HasSet, closing: HasSet, hostsSeen: HasSet): Emptiness {
  if (!mine.length) return "held";
  const present = (id: string) => listed.includes(id) || (live.has(id) && !closing.has(id));
  if (mine.some(present)) return "held";
  return mine.every((id) => hostsSeen.has(hostOf(id))) ? "empty" : "unknown";
}
