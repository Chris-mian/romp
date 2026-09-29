// DRAGGING A TAB INTO (and OUT OF) A TAG GROUP (the user 2026-09-23, who wanted a tab dragged onto a
// group to put that session IN the group rather than only reorder it, and the ungrouped row to take it
// back out). The strip's sections ARE tags (tab-groups.ts), so the gesture is a tag edit, and both
// halves write through the tag path the tab menu's Tags flyout already owns — a targeted `addMember` /
// `removeMember` op by the tag's stored id, or the `editTag` wire for a name homed on another kernel —
// so one writer owns tags in both directions. This module is the DECISION: given the strip's unions,
// where a drop landed and which session was dragged, what the drop does to that session's tags. Pure
// and DOM-free (the tab-order.ts / dragslot.ts pattern), so the rule executes in node
// (drag-join.test.ts); render.ts's #tabs dragover/drop handlers paint and post it.
//
// THE RULE, in the user's terms: the place a tab is dropped states WHERE THEY WANT IT TO APPEAR NOW.
// That one sentence gives both halves, and explains why they are not symmetric:
//   - a group IS a tag, so "appear in this group" is satisfied by ADDING that tag. The session's other
//     tags are untouched and may well go on showing it elsewhere — the strip draws one copy per tag.
//   - the ungrouped row is NOT a group. It is the set of sessions carrying no tags at all, so "appear
//     here" can only be satisfied by CLEARING EVERY TAG the session has.
// The asymmetry is deliberate, not an oversight (the user 2026-09-23, correcting an earlier reading in
// which a trail drop took off only the dragged copy's tag). Its cost is that reversibility is weaker
// one way: dragging the tab back into a group restores THAT tag, not the others, so a multi-tag clear is
// not undone by one drag. There is no undo stack and no timed undo affordance; the pre-release cue,
// which names every tag about to come off (leaveWords), is the safety.
//
// WHERE A DROP LANDED is read from the PROVISIONAL TAB's own place in the strip — the nearest section
// header before it, or the untagged boundary it has passed (render.ts dropZoneOf) — never from the
// element under the pointer. The live reorder has already slid the dragged tab into a row by the time
// the drop lands, and that row is what the user is looking at, so the cue and the drop read one input
// and cannot disagree. It also makes the rule fall out for free in the cases that have no tab to
// hit-test: a folded group (its members are hidden, and the slot after its bare header is inside it)
// and a folded header PACKED onto the folded header before it (PR 1792: no row break between them, so
// the slot between the two heads is the end of the first group's row and joins THAT group, the one the
// provisional tab is sitting in).
//
// THE UNGROUPED ROW IS THE ONE PLACE A TAB LEAVES ITS GROUPS. The slot ahead of the strip's FIRST header
// resolves to no section either, but it is not the ungrouped row — it is the head of the strip — so it
// clears nothing: `zone.trail` is the untagged boundary actually crossed, not merely "no header found",
// and a drop aimed a little left of the first group's chip can never strip a tag.
//
// A HEADER dragged onto another header still reorders the groups: that path is chosen by WHAT IS BEING
// DRAGGED (render.ts's dragover/drop branch on `draggedGroup`), never by where the pointer is, so a tab
// dropped on a header and a header dropped on a header are two different gestures on the same pixel.
import type { TagUnion } from "./session-views";

/** Where the provisional tab sits when the drop lands: the section header's tag name, or the untagged
 *  trail (`trail`, past the boundary the strip draws for the sessions in no tag). Neither, with `trail`
 *  false, is the head of the strip or a flat (unsectioned) strip — a plain reorder. */
export interface DropZone { section: string | null; trail: boolean }

/** One tag the drop writes, and the routes that carry the write: `tid` is the LOCAL store's tag,
 *  addressed by its stored id (never its name — a name is what a refused rename would have changed,
 *  views-writes.ts TagEditOp), and `hosts` the kernels the `editTag` wire must carry it to. A join
 *  lands on the local tag when one holds the name and otherwise on the name's single remote home; a
 *  removal goes to EVERY store holding the (name, member) pair, which is the Tags flyout's rule. */
export interface TagRoute { tag: string; tid: string | null; hosts: string[] }

/** What a drop does to the dragged session's tags. `reorder` = nothing (the reorder the strip has always
 *  done is the whole gesture), and `why` says which reorder-only case it is, for a diagnostic reader —
 *  never user-facing copy. `join` carries the ONE tag added; `leave` carries EVERY tag the session has,
 *  all of which come off (see the rule above). */
export interface TabDrop {
  kind: "join" | "leave" | "reorder";
  tags: TagRoute[];
  why: "" | "trail" | "head" | "untagged" | "unknown" | "already" | "pending";
}

const REORDER = (why: TabDrop["why"]): TabDrop => ({ kind: "reorder", tags: [], why });

/** The routes a REMOVAL of `sid` from this union takes: the local tag that actually HOLDS the member
 *  (not simply the union's first local tag — two local tags may share a name, and the op must land on
 *  the one whose membership is going), and every remote home holding the pair. Null when nothing holds
 *  it: the strip drew a copy the blob no longer explains, and there is nothing to write. */
function removalRoute(g: TagUnion, sid: string): TagRoute | null {
  const local = g.locals.find((t) => (t.members || []).includes(sid) && !/^pending-/.test(t.id));
  const hosts = g.remotes.filter((rt) => (rt.members || []).includes(sid)).map((rt) => rt.host || "");
  if (!local && !hosts.length) return null;
  return { tag: g.name, tid: local ? local.id : null, hosts };
}

/** THE RULE (the account above). `zone` is where the provisional tab sits, `sid` the session dragged.
 *  - a group's row, and the session does NOT carry the tag → `join`: it gains that tag and lands at the
 *    drop index among the group's members (the reorder still applies, render.ts runs it unchanged)
 *  - a group's row, and the session already carries the tag → `reorder` (`already`): no tag write at
 *    all, so a drag inside one group is exactly what it has always been — and render.ts lights no cue
 *    for it, so nothing flashes
 *  - the ungrouped row, dragging a TAGGED session → `leave`: every tag it carries comes off, and the
 *    tab lands in that row at the drop index, under no group
 *  - the ungrouped row, dragging an untagged tab → `reorder` (`untagged`): trail to trail is a plain
 *    reorder, as it has always been
 *  - the head of the strip, or a flat strip → `reorder` (`head`): not the ungrouped row, nothing cleared
 *  - a name no union holds → `reorder` (`unknown`): the strip drew a section the blob no longer explains
 *  - a union whose local tag is a CREATE still in flight, with no remote home → `reorder` (`pending`):
 *    its id is the placeholder the ack replaces and the kernel would refuse an op addressed by it (the
 *    Tags flyout stands down on the same union for the same reason) */
export function resolveTabDrop(unions: readonly TagUnion[], zone: DropZone, sid: string): TabDrop {
  if (zone.section !== null) {
    const g = unions.find((u) => u.name === zone.section);
    if (!g) return REORDER("unknown");
    if ((g.members || []).includes(sid)) return REORDER("already");
    if (g.localId && !g.pending) return { kind: "join", tags: [{ tag: g.name, tid: g.localId, hosts: [] }], why: "" };
    if (g.remotes.length) return { kind: "join", tags: [{ tag: g.name, tid: null, hosts: [g.remotes[0].host || ""] }], why: "" };
    return REORDER("pending");
  }
  if (!zone.trail) return REORDER("head");
  const holders = unions.filter((u) => (u.members || []).includes(sid));
  if (!holders.length) return REORDER("untagged");
  const tags = holders.map((g) => removalRoute(g, sid)).filter((r): r is TagRoute => r !== null);
  return tags.length ? { kind: "leave", tags, why: "" } : REORDER("unknown");
}

/** Does this drop write a tag — the one bit the dragover's cue needs (the group about to be joined
 *  wears the accent ring, a release that clears tags names them; nothing shows for a reorder). Stated
 *  here so the cue and the drop can only ever read the same rule. */
export function writesTag(d: TabDrop): boolean {
  return d.kind !== "reorder";
}

/** The words the LEAVE cue carries BEFORE the release. Clearing every tag is more than a one-tag change,
 *  so the cue must name what is going while the hand can still move: `leaving` is the tags coming off,
 *  capped at `limit` with `more` counting the rest (the many-tags rule: dozens of tags on every surface,
 *  so a cue is a bounded run and never a list of them all). Empty for a join — the ring on the target
 *  header is that half's cue — and for an untagged tab dropped on the ungrouped row, which writes
 *  nothing. This label is the whole safety on a clear: there is no undo stack (see the account above). */
export interface LeaveWords { leaving: string[]; more: number }
export function leaveWords(d: TabDrop, limit = 3): LeaveWords {
  if (d.kind !== "leave") return { leaving: [], more: 0 };
  const names = d.tags.map((t) => t.tag);
  return { leaving: names.slice(0, limit), more: Math.max(0, names.length - limit) };
}
