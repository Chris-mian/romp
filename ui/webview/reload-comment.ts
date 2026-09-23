// The comment thread you had open comes back after a reload (the user 2026-09-23, finishing what T265 started: they
// want the reader's PLACE AND VIEW to survive a reload, and said plainly that unsent TEXT should not — nobody
// expects words they typed to outlive the page). T265 gave the scroll position and follow mode back; the thread
// popup the reader was reading beside the transcript still went down with the page, so a reload that cost them
// nothing else cost them the conversation they had open.
//
// Recorded on the way down, beside the scroll record: render.ts persistCommentForReload rides the same synchronous
// window.__rompPersistForReload hook the reload core calls before the page goes, with `pagehide` as the belt. The
// record is the tab the popup belonged to, its mode, the thread's id, and the box's LIVE position — so it comes
// back where the reader parked it rather than snapping to the default geometry.
//
// ONLY A THREAD popup is kept. A CREATE popup — a comment being written and not yet sent — records nothing at all:
// its whole content is unsent text, so reopening the dialog without the words would put an empty box over a
// passage the reader has moved on from, and keeping the words is the thing they said they do not want. The draft
// text is never persisted by any of this: render.ts's commentDrafts is an in-memory Map and stays one, so a reload
// spends every draft exactly as it always has.
//
// On load the record is taken out of sessionStorage at once — one reload, one restore, this tab's alone (the
// persisted webview state is localStorage on the served page, shared by every dashboard tab of the origin, so a
// record there could reopen one tab's thread in another) — and the marks pass reopens it through the ordinary
// openCommentPopover path. Pure, so node executes the decisions; render.ts's wiring is pinned by
// reload-comment.test.ts.

/** This tab's sessionStorage key for the record (beside romp:reloadScroll and romp:reloadNotices). */
export const RELOAD_COMMENT_KEY = "romp:reloadComment";

export interface ReloadComment {
  id: string;                               // the tab the popup belonged to
  mode: "thread";                           // only ever a thread popup — a create popup is not recorded
  tid: string;                              // the thread it was showing
  pos: { x: number; y: number } | null;      // where the box was, null when it could not be measured
}

/** The record to persist for an open comment popup; null when there is nothing to keep. Nothing to keep means: no
 *  active tab, no popup, or a popup in CREATE mode — a new comment not yet sent, whose content is unsent text. */
export function reloadCommentRecord(id: string | null | undefined, mode: string | null | undefined,
                                    tid: string | null | undefined,
                                    pos: { x: number; y: number } | null | undefined): ReloadComment | null {
  if (!id || mode !== "thread" || !tid) return null;
  return { id, mode: "thread", tid, pos: livePos(pos) };
}

/** The saved record applies to exactly one restore: the tab that was active when the page went down. Anything else
 *  — a different tab, a create-mode or malformed record — gets nothing, and the reader sees the ordinary page. */
export function takeReloadComment(saved: unknown, id: string | null | undefined): ReloadComment | null {
  const s = saved as ReloadComment | null | undefined;
  if (!s || typeof s !== "object" || !id || s.id !== id) return null;
  if (s.mode !== "thread" || typeof s.tid !== "string" || !s.tid) return null;
  return { id: s.id, mode: "thread", tid: s.tid, pos: livePos(s.pos) };
}

/** A position only counts when both numbers are real (a 0×0 box measures nothing, a stored NaN survives no JSON
 *  round-trip): otherwise the reopened box takes its default geometry, which is never wrong, only not theirs. */
function livePos(pos: { x: number; y: number } | null | undefined): { x: number; y: number } | null {
  if (!pos || typeof pos !== "object") return null;
  const { x, y } = pos as { x?: unknown; y?: unknown };
  if (typeof x !== "number" || typeof y !== "number" || !Number.isFinite(x) || !Number.isFinite(y)) return null;
  return { x, y };
}
