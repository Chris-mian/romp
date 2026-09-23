// The SEND-LANDING invariant (2026-09-23): an observer that follows each composer send from the kernel's copy of it to its
// landed user turn, and files what it saw in client-diag.jsonl. Observation only: it reads the resident events before and
// after a frame is applied and returns rows; it never writes an event, a view or a pending send, and render.ts's glue swallows
// any error it throws, so a bug here costs a row, never a render.
//
// Why it exists: since about 2026-09-19 the user has seen two things in the chat, a message they just sent missing until a
// reload, and the agent message above a send blinking out and back. The journal could not say where either came from: the
// frame guard's `frame-drops-landed` row (frame-guard.ts) watches two of the paths that apply server events and had never
// fired, and a `tailmut` row cannot tell a vanished turn from a re-rendered one. This watch sits on EVERY path that applies a
// frame to the resident events (render.ts calls it around the one dispatch chain, so a path added later is covered) and
// states three things, each decided at the moment a frame is applied, never on a timer:
//   landed          a send's landed user turn entered the resident events: the send's id (the qid minted at the press), the
//                   turn's uuid, the ms since the press, the frame type that brought it, whether the record wore the send's
//                   id or the pending-send reconcile matched it by text, and how many events sit below it;
//   landed-lost     a frame took a landed human turn off the resident events while it was one of the newest few, and not
//                   because the list slid off the top (every event above it went too), a fork replaced the list (nothing
//                   shared), or the page expected it (a rewind it asked for, a rebased full): the frame type, its watermark,
//                   the tails before and after, and whether the frame's own events still carry the turn;
//   landed-missing  the kernel's copies of a send it had shown (its echo, its queued copy, the page's held copy of it) are
//                   all off the list, no landed turn for it is resident, and an agent message lands below where the copy
//                   sat: the kernel says the send was taken and answered while the page holds no record of it. The
//                   echo merely hidden behind the page's own bubble is the normal wait and never files.
// Synthetic data in every test; ids only in the rows, never text.

import { isLandedHuman, isTransient, type GuardEvent } from "./frame-guard";

/** The slice of a chat event the watch reads (render.ts's ChatEvent is a superset). */
export type LandEvent = GuardEvent & { qid?: string; qids?: (string | null)[]; texts?: { qid?: string }[] };

export const LAND_RECENT_TURNS = 3;   // "the newest few": a landed human turn among the last three the page held
export const LAND_TAIL_KEYS = 6;      // the tail a row carries, before and after
export const LAND_MAX_SENDS = 64;     // sends remembered per page; the oldest is forgotten past it (a bound, not a clock)

export type LandCtx = {
  path: string;                           // the frame's wire type (session, chatTail, update, chatHead, chatWindow, chatTurns)
  now: number;                            // ms, for the rows' ms-since-press
  wm?: unknown;                           // the frame's watermark, when it carried one (kernel.py _chat_wm)
  frame?: readonly LandEvent[] | null;    // the frame's OWN events: the kernel's list (a full) or the suffix it sent (a delta)
  expected?: string | null;               // a removal the page expects: "rewind" (one it asked for), "rebased" (the kernel said so)
  pending: ReadonlySet<string>;           // the send ids the page still holds as pending (its own bubble drawn)
};
export type LandRow = { what: "landed" | "landed-lost" | "landed-missing"; data: Record<string, unknown> };

type Send = {
  sid: string; key: string; t: number;
  uuid?: string;                          // its landed turn, once resident
  claim?: string;                         // the landed turn the pending-send reconcile matched by text (a record without the id)
  received?: "echo" | "queued";           // the kernel's copy the page last saw of it
  anchor?: string | null;                 // the event just above that copy when last seen: an answer lands below it
  missing?: boolean;                      // landed-missing filed (once per send)
  done?: "withdrawn" | "lost";            // nothing will land: taken back (the cross, a refusal, its tab gone) or never delivered
};

const isOpt = (u: unknown): boolean => typeof u === "string" && u.startsWith("optimistic:");

/** The last `n` events as `kind:uuid` (the key when there is no uuid): enough to see what the tail held, no text. */
export function tailKeys(events: readonly LandEvent[], n: number = LAND_TAIL_KEYS): string[] {
  const out: string[] = [];
  for (let i = Math.max(0, events.length - n); i < events.length; i++) {
    const e = events[i];
    out.push(String(e?.kind ?? "?") + ":" + String(e?.uuid ?? e?.key ?? ""));
  }
  return out;
}

/** A landed user record wearing the send's id (the kernel pairs the record with the copy it lands, T252c). */
function carriesKey(e: LandEvent | null | undefined, key: string): boolean {
  if (!e || e.kind !== "user" || isTransient(e.uuid) || isOpt(e.uuid) || e.undelivered) return false;
  return e.qid === key || (Array.isArray(e.qids) && e.qids.includes(key));
}

/** The kernel's provisional copy of the send in `e`: its echo (the echo's uuid IS the send's id, flagged never-delivered or
 *  not), or a queued copy wearing the id, the kernel's own group or the page's held copy of one that left the queue (T262i).
 *  The page's own optimistic group wears the id too, and is not the kernel's. */
function provisionalOf(e: LandEvent | null | undefined, key: string): "echo" | "queued" | null {
  if (!e) return null;
  if (e.kind === "user" && e.uuid === key) return "echo";
  if (e.kind === "queued" && !isOpt(e.uuid) && Array.isArray(e.texts) && e.texts.some((t) => !!t && t.qid === key)) return "queued";
  return null;
}

function uuidSet(events: readonly LandEvent[]): Set<string> {
  const out = new Set<string>();
  for (const e of events) if (e && typeof e.uuid === "string") out.add(e.uuid);
  return out;
}

export class LandingWatch {
  private sends = new Map<string, Send>();   // send id → its record, in press order

  /** A composer send was pressed: `key` is the id it was posted with. */
  send(sid: string, key: string, now: number): void {
    if (!sid || !key || this.sends.has(key)) return;
    this.sends.set(key, { sid, key, t: now });
    while (this.sends.size > LAND_MAX_SENDS) { const first = this.sends.keys().next().value; if (first === undefined) break; this.sends.delete(first); }
  }
  /** The pending-send reconcile retired the send on a landed record it matched (send-pending.ts reconcilePending `landed`). */
  claim(sid: string, key: string | undefined, uuid: string | undefined): void {
    const s = key ? this.sends.get(key) : undefined;
    if (s && s.sid === sid && !s.uuid && uuid) s.claim = uuid;
  }
  /** The reconcile retired the send on the kernel's never-delivered verdict: nothing will land. */
  lost(sid: string, key: string | undefined): void {
    const s = key ? this.sends.get(key) : undefined;
    if (s && s.sid === sid && !s.uuid) s.done = "lost";
  }
  /** The record for a send id, for a test's reading. */
  peek(key: string): Readonly<Send> | undefined { return this.sends.get(key); }

  /** One frame applied to session `sid`: `before` the resident events as they were, `after` as they are. Reads both, writes
   *  neither; returns the rows to file. */
  apply(sid: string, before: readonly LandEvent[], after: readonly LandEvent[], ctx: LandCtx): LandRow[] {
    const rows: LandRow[] = [];
    let beforeKeys: Set<string> | null = null;
    for (const s of this.sends.values()) {
      if (s.sid !== sid || s.done || s.uuid) continue;
      // landed: the record wearing the id, else the one the reconcile matched by text
      let at = -1;
      let by: "id" | "text" = "id";
      for (let i = after.length - 1; i >= 0; i--) if (carriesKey(after[i], s.key)) { at = i; break; }
      if (at < 0 && s.claim) { for (let i = after.length - 1; i >= 0; i--) if (after[i]?.uuid === s.claim) { at = i; by = "text"; break; } }
      if (at >= 0) {
        s.uuid = String(after[at].uuid);
        rows.push({ what: "landed", data: { sid, key: s.key, uuid: s.uuid, ms: ctx.now - s.t, path: ctx.path, by, fromEnd: after.length - 1 - at } });
        continue;
      }
      if (!ctx.pending.has(s.key)) { s.done = "withdrawn"; continue; }   // no landing and no bubble: taken back, or its tab went
      let prov: "echo" | "queued" | null = null, provAt = -1;
      for (let i = after.length - 1; i >= 0; i--) { const p = provisionalOf(after[i], s.key); if (p) { prov = p; provAt = i; break; } }
      if (prov) {
        s.received = prov;
        s.anchor = null;
        for (let i = provAt - 1; i >= 0; i--) { const u = after[i]?.uuid; if (typeof u === "string" && !isOpt(u)) { s.anchor = u; break; } }
        continue;
      }
      if (!s.received || s.missing) continue;   // a frame from before the kernel held the send says nothing about it
      beforeKeys = beforeKeys ?? uuidSet(before);
      let from = 0;
      if (s.anchor) { for (let i = after.length - 1; i >= 0; i--) if (after[i]?.uuid === s.anchor) { from = i + 1; break; } }
      let answer: string | null = null;
      for (let i = from; i < after.length; i++) {
        const e = after[i];
        if (e && e.kind === "assistant" && typeof e.uuid === "string" && !beforeKeys.has(e.uuid)) { answer = e.uuid; break; }
      }
      if (!answer) continue;
      s.missing = true;
      rows.push({ what: "landed-missing", data: { sid, key: s.key, ms: ctx.now - s.t, path: ctx.path, wm: ctx.wm ?? null, echo: "gone", was: s.received,
                                                  answer, inFrame: Array.isArray(ctx.frame) ? ctx.frame.some((e) => carriesKey(e, s.key)) : null, tail: tailKeys(after) } });
    }
    if (ctx.expected) return rows;   // a rewind or a rebased full removes rows on purpose; frame-guard's row says so
    // landed-lost: the newest few landed human turns the page held, each looked for in what it holds now (a walk from the end,
    // which stops once all are found: the common case costs the tail)
    const recent: { u: string; i: number; n: number }[] = [];
    for (let i = before.length - 1; i >= 0 && recent.length < LAND_RECENT_TURNS; i--) {
      const e = before[i];
      if (isLandedHuman(e)) recent.push({ u: e.uuid, i, n: recent.length + 1 });
    }
    if (!recent.length) return rows;
    const want = new Set(recent.map((r) => r.u));
    for (let i = after.length - 1; i >= 0 && want.size; i--) { const u = after[i]?.uuid; if (typeof u === "string") want.delete(u); }
    if (!want.size) return rows;
    const afterKeys = uuidSet(after);
    let firstKept = -1;   // the first event the frame kept: everything above it slid off the top together
    for (let i = 0; i < before.length; i++) { const u = before[i]?.uuid; if (typeof u === "string" && !isOpt(u) && afterKeys.has(u)) { firstKept = i; break; } }
    if (firstKept < 0) return rows;   // nothing shared: the list was replaced (a fork), not a turn lost from it
    for (const r of recent) {
      if (!want.has(r.u) || r.i < firstKept) continue;
      let send: Send | undefined;
      for (const s of this.sends.values()) if (s.sid === sid && s.uuid === r.u) { send = s; break; }
      rows.push({ what: "landed-lost", data: { sid, uuid: r.u, key: send ? send.key : null, ms: send ? ctx.now - send.t : null, fromEnd: r.n, path: ctx.path,
                                               wm: ctx.wm ?? null, inKernel: Array.isArray(ctx.frame) ? ctx.frame.some((e) => e?.uuid === r.u) : null,
                                               before: tailKeys(before), after: tailKeys(after) } });
    }
    return rows;
  }
}
