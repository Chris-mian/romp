// The TAILBACK watch (2026-09-23): follows every uuid that left the tail of the ACTIVE view's painted DOM until it next
// appears in that view's DOM, and files one row per uuid saying how that ended.
//
// Why it exists: after the chat-sync fix the page's event instruments (send-landing.ts: landed, landed-lost,
// landed-missing) read clean on the user's sessions, every send landed and nothing took a landed turn off the resident
// events, yet the screen-level `tailmut` rows (scroll-write.ts) kept showing landed user turns' ELEMENTS leaving the
// active view and not coming back within that mutation batch, on remote sessions, seconds after landing. A row per batch
// cannot say whether each was a MOVE (the same uuid re-inserted elsewhere in a later batch: a queued message repositioned)
// or a GAP (absent from the screen while the events still hold it): nothing linked a later re-insertion to the removal.
//
// What it states, decided at mutation batches and view switches, never on a timer:
//   end "back"      the uuid is in the view's DOM again at the end of a later batch: `gapBatches` batches of that view
//                   after the removal, `gapMs` between the two batches (Date.now() read at each batch, an interval
//                   between two events), `sameIndex` whether it came back in the same slot counted from the tail, the
//                   slots themselves (`fromEnd` [before, after]) and the nearest unit above it before and after
//                   (`neighbourAbove`);
//   end "switch"    the view stopped being the one on screen before the uuid came back (`viewSwitched: true`): a tab
//                   switch, the section overview, no session to show; never mistaken for a loss;
//   end "teardown"  the view was removed (its tab closed, a fork replaced it) before the uuid came back;
//   end "evicted"   the view already held TAILBACK_MAX_PER_VIEW uuids and this, the oldest, was dropped to make room: a
//                   bound on memory, filed so the drop is on the record, never silent.
// Every row carries `kind` (the event's kind when the page's resident events hold the uuid; "optimistic"/"held" for the
// page's own copies; else read off the element's class) and `inEv` (the resident events held the uuid at the removal).
//
// Observation only and DOM-free, so node --test executes it; render.ts's glue feeds it and files its rows through the
// capped diag path (scrollDiagRow, one per-minute budget per row kind), and swallows any error into one row.

export const TAILBACK_MAX_PER_VIEW = 64;

/** A unit's place in a view's children: how many uuid-bearing children sit below it, and the nearest uuid above it. */
export type TailSpot = { fromEnd: number; above: string };
/** Where a uuid is in the settled DOM of a batch: a child of the view (the level a tail removal is read at). */
export type TailFound = TailSpot;
/** A uuid that left the tail in this batch, with its painted spot before the batch, its kind and whether the events hold it. */
export type TailGone = TailSpot & { uuid: string; kind: string; inEv: boolean };
export type TailGoneInfo = { kind: string; inEv: boolean };
export type TailBackEnd = "back" | "switch" | "teardown" | "evicted";
export type TailBackRow = {
  sid: string; uuid: string; kind: string; inEv: boolean; end: TailBackEnd; viewSwitched: boolean;
  gapBatches: number; gapMs: number; sameIndex: boolean | null; fromEnd: [number, number | null]; neighbourAbove: [string, string | null];
};

/** `list` is a view's children as uuids ("" for a child with none: a day divider, a spacer, a hidden echo). */
export function spotAt(list: readonly string[], i: number): TailSpot {
  let fromEnd = 0;
  for (let j = i + 1; j < list.length; j++) if (list[j]) fromEnd++;
  let above = "";
  for (let j = i - 1; j >= 0; j--) if (list[j]) { above = list[j]; break; }
  return { fromEnd, above };
}

/** One childList record, reduced: the nodes it removed and added, and the siblings they sat between. */
export type ChildRecord<N> = { removed: readonly N[]; added: readonly N[]; prev: N | null; next: N | null };
/** The children as they were BEFORE a batch (the painted list a removed unit left), from the settled list and the
 *  batch's records undone in reverse: each record's added nodes come out, its removed nodes go back between the siblings
 *  it names. Exact for a complete batch; a sibling that cannot be found (a record set not from this list) appends. */
export function priorChildren<N>(now: readonly N[], records: readonly ChildRecord<N>[]): N[] {
  const list = now.slice();
  for (let r = records.length - 1; r >= 0; r--) {
    const rec = records[r];
    for (const a of rec.added) { const i = list.indexOf(a); if (i >= 0) list.splice(i, 1); }
    if (!rec.removed.length) continue;
    let at: number;
    if (rec.prev != null) { const i = list.indexOf(rec.prev); at = i >= 0 ? i + 1 : -1; }
    else if (rec.next != null) at = list.indexOf(rec.next);
    else at = 0;
    if (at < 0) at = list.length;
    list.splice(at, 0, ...rec.removed);
  }
  return list;
}

/** A gone unit's kind: the page's own copies by their uuid prefix, else the event's kind, else the element's class. */
export function tailKind(evKind: string, uuid: string, cls: string): string {
  if (uuid.startsWith("optimistic:")) return "optimistic";
  if (uuid.startsWith("held:")) return "held";
  if (evKind) return evKind;
  const c = " " + String(cls || "") + " ";
  if (c.indexOf(" turn-queued ") >= 0) return "queued";
  if (c.indexOf(" turn-user ") >= 0) return "user";
  if (c.indexOf(" turn-assistant ") >= 0) return "assistant";
  if (c.indexOf(" turn-tool ") >= 0 || c.indexOf(" turn-toolgroup ") >= 0) return "tool";
  return "?";
}

type EvLike = { kind?: unknown; uuid?: unknown; resultUuid?: unknown };
/** For each gone uuid: whether the resident events hold it (by its uuid, or an answer line's, the anchor an
 *  AskUserQuestion turn wears) and its kind. One pass over the events, only when a batch has gone uuids. */
export function tailGoneInfo(gone: readonly string[], events: readonly EvLike[], clsOf: (uuid: string) => string): TailGoneInfo[] {
  if (!gone.length) return [];
  const byUuid = new Map<string, EvLike>();
  for (const e of events) {
    if (!e) continue;
    if (typeof e.uuid === "string") byUuid.set(e.uuid, e);
    if (typeof e.resultUuid === "string") byUuid.set(e.resultUuid, e);
  }
  return gone.map((u) => {
    const ev = byUuid.get(u);
    return { kind: tailKind(ev && ev.kind != null ? String(ev.kind) : "", u, clsOf(u)), inEv: !!ev };
  });
}

type Held = TailGone & { seq: number; t: number };
type Track = { seq: number; held: Map<string, Held> };

function rowOf(sid: string, h: Held, end: TailBackEnd, seq: number, now: number, at: TailFound | null): TailBackRow {
  return { sid, uuid: h.uuid, kind: h.kind, inEv: h.inEv, end, viewSwitched: end === "switch", gapBatches: seq - h.seq, gapMs: now - h.t,
           sameIndex: at ? at.fromEnd === h.fromEnd : null, fromEnd: [h.fromEnd, at ? at.fromEnd : null],
           neighbourAbove: [h.above, at ? at.above : null] };
}

export class TailBackWatch {
  private views = new Map<string, Track>();   // sid → the uuids its view is waiting on, in removal order
  constructor(private max = TAILBACK_MAX_PER_VIEW) {}

  /** How many uuids the view of `sid` is waiting on. */
  tracking(sid: string): number { return this.views.get(sid)?.held.size ?? 0; }

  /** One mutation batch of the ACTIVE view `sid`, read at `now`: `gone` the uuids that left its tail in this batch (with
   *  their painted spot before it), `locate` where a uuid sits in the settled DOM, or null. Only the active view's
   *  batches come here, so another view still waiting was switched away from. Returns the rows to file. */
  batch(sid: string, now: number, gone: readonly TailGone[], locate: (uuid: string) => TailFound | null): TailBackRow[] {
    const rows = this.endOthers(sid, now);
    let v = this.views.get(sid);
    if (!v) {
      if (!gone.length) return rows;
      v = { seq: 0, held: new Map() };
      this.views.set(sid, v);
    }
    v.seq += 1;
    for (const [u, h] of v.held) {
      const at = locate(u);
      if (!at) continue;
      v.held.delete(u);
      rows.push(rowOf(sid, h, "back", v.seq, now, at));
    }
    for (const g of gone) {
      if (!g.uuid || v.held.has(g.uuid) || locate(g.uuid)) continue;   // a duplicate still on screen is no gap
      v.held.set(g.uuid, { ...g, seq: v.seq, t: now });
      while (v.held.size > this.max) {
        const first = v.held.values().next().value;
        if (!first) break;
        v.held.delete(first.uuid);
        rows.push(rowOf(sid, first, "evicted", v.seq, now, null));
      }
    }
    if (!v.held.size) this.views.delete(sid);
    return rows;
  }

  /** The view of `sid` (null: none) is the one on screen now: every other view still waiting was switched away from. */
  show(sid: string | null, now: number): TailBackRow[] { return this.endOthers(sid, now); }

  /** The view of `sid` stopped being watched: switched away from, or torn down. */
  end(sid: string, why: "switch" | "teardown", now: number): TailBackRow[] {
    const v = this.views.get(sid);
    if (!v) return [];
    this.views.delete(sid);
    const rows: TailBackRow[] = [];
    for (const h of v.held.values()) rows.push(rowOf(sid, h, why, v.seq, now, null));
    return rows;
  }

  private endOthers(sid: string | null, now: number): TailBackRow[] {
    if (!this.views.size || (this.views.size === 1 && sid != null && this.views.has(sid))) return [];
    const rows: TailBackRow[] = [];
    for (const other of Array.from(this.views.keys())) if (other !== sid) rows.push(...this.end(other, "switch", now));
    return rows;
  }
}
