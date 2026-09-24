// The delta's BASE CHECK (2026-09-23): the page half of the chat wire's resync, pure so node executes it
// (chat-resync.test.ts); render.ts chatTail and upsert wire it to the frames.
//
// A proto-2 chatTail says "truncate after afterUuid and append". That is right only when the page's events up to that
// anchor are the ones the kernel computed the delta against, and the kernel cannot know that: a client's base advances
// when a frame is SENT, not when the page applies it, and the kernel diffs against a baseline shared by every client.
// When the two disagreed before the anchor, the delta applied cleanly onto a page missing a turn, every later delta
// anchored past the hole, and only a reload repaired it (the user, from 2026-09-19: a message just sent that showed only
// after a reload). So the kernel stamps every proto-2 delta with `baseFp`: [n, crc32] over the keys of the n events ending
// at the anchor, in the list it cut the delta from (kernel.py _chat_base_fp, CHAT_BASE_FP_K). The page recomputes it over
// its own tail run and, when the two differ, applies nothing and asks for the full.
//
// Bounded by event, never by time: one outstanding full per session (render.ts awaitingFull), and a session whose resyncs do
// not converge stops asking. Two asks in a row with no agreeing delta between them disarm the check for that session, which
// then applies deltas as it did before the check existed (observing, filing one row), and re-arms on the first delta that
// agrees or on a new socket. Agreeing deltas, the steady state, cost one crc over at most 64 short keys and no frame.

/** The slice of a chat event this module reads: its wire key (render.ts keyOf: `key`, else `uuid`). */
export type FpEvent = { uuid?: string; key?: string };

let CRC_TABLE: Uint32Array | null = null;
function crcTable(): Uint32Array {
  if (CRC_TABLE) return CRC_TABLE;
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  CRC_TABLE = t;
  return t;
}

/** CRC-32 (IEEE 802.3, the polynomial zlib.crc32 uses) of `s` encoded as UTF-8, unsigned. */
export function crc32Utf8(s: string): number {
  const bytes = new TextEncoder().encode(s);
  const t = crcTable();
  let c = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) c = t[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

const keyOf = (e: FpEvent | null | undefined): string => (e ? (e.key ?? e.uuid ?? "") : "");

/** [n, crc32] over the keys of `events` joined by newlines: kernel.py _chat_base_fp, byte for byte. */
export function baseFingerprint(events: readonly FpEvent[]): [number, number] {
  return [events.length, crc32Utf8(events.map(keyOf).join("\n"))];
}

/** A delta's `baseFp` as the kernel sends it, or null for anything else (an older kernel sends none; a malformed one is
 *  treated as absent, never as a mismatch: the check must not turn a wire change into a storm of fulls). */
export function readBaseFp(fp: unknown): [number, number] | null {
  if (!Array.isArray(fp) || fp.length !== 2) return null;
  const [n, h] = fp;
  if (!Number.isInteger(n) || n < 0 || !Number.isInteger(h) || h < 0 || h > 0xffffffff) return null;
  return [n, h];
}

export type BaseVerdict =
  | { ok: true }
  | { ok: false; reason: "short" | "differs"; n: number; kernel: number; page: number | null; held: number };

/** Does the page's tail run agree with the base the delta was cut against? `tail` is the page's resident KERNEL events of its
 *  tail run (no optimistic bubble, no held group), `at` the anchor's index in it, `fp` the delta's [n, crc]. The page's n
 *  events ending at the anchor must hash to the kernel's; fewer than n resident before it is a disagreement too (the kernel's
 *  window starts at the client's own first edge at most, so an in-sync page always holds it). */
export function checkBase(tail: readonly FpEvent[], at: number, fp: [number, number]): BaseVerdict {
  const [n, kernel] = fp;
  const lo = at + 1 - n;
  if (at < 0 || lo < 0) return { ok: false, reason: "short", n, kernel, page: null, held: Math.max(0, at + 1) };
  const page = baseFingerprint(tail.slice(lo, at + 1))[1];
  return page === kernel ? { ok: true } : { ok: false, reason: "differs", n, kernel, page, held: at + 1 };
}

/** Per-session resync bookkeeping: how many asks in a row went out with no agreeing delta between them, and the sessions
 *  whose check is disarmed (its one row filed). */
export type ResyncState = { strikes: Map<string, number>; disarmed: Set<string> };
export function newResyncState(): ResyncState {
  return { strikes: new Map(), disarmed: new Set() };
}

/** Asks in a row, with no agreeing delta between them, after which the check stops asking for that session. Two: the first
 *  ask heals a genuine gap; a second covers a full that was itself stale; a third mismatch means the page and the kernel
 *  disagree about something a full does not change, and asking again would be a loop. */
export const RESYNC_MAX_STRIKES = 2;

/** A delta whose base disagreed: "ask" (request the full; the caller skips the delta), or "observe" (the check is disarmed
 *  for this session: apply the delta as before). `firstObserve` is true exactly once per disarm, for its one row. */
export function onMismatch(st: ResyncState, sid: string): { act: "ask" | "observe"; firstObserve: boolean } {
  const n = st.strikes.get(sid) ?? 0;
  if (n >= RESYNC_MAX_STRIKES) {
    const first = !st.disarmed.has(sid);
    st.disarmed.add(sid);
    return { act: "observe", firstObserve: first };
  }
  st.strikes.set(sid, n + 1);
  return { act: "ask", firstObserve: false };
}

/** A delta whose base agreed: the session is in sync, its strikes clear and a disarmed check re-arms. */
export function onAgree(st: ResyncState, sid: string): void {
  st.strikes.delete(sid);
  st.disarmed.delete(sid);
}

/** A new socket (a fresh kernel-side client) or a tab that left the strip: forget the session's history, or every one. */
export function forgetResync(st: ResyncState, sid?: string): void {
  if (sid === undefined) { st.strikes.clear(); st.disarmed.clear(); return; }
  st.strikes.delete(sid);
  st.disarmed.delete(sid);
}

/** The page asked for this session whole and the answer is OLDER than what it holds (frame-guard.ts frameOlder): "reask"
 *  once per ask for a fresh build (the kernel keeps the page's watermark as a floor through the ask and builds afresh when it
 *  refuses an older copy), and "apply" the second time, since a full always wins: refusing the kernel's repeated answer would
 *  leave the page diverged from what the kernel believes it holds, with its one ask spent. `reasked` is the set of sessions
 *  whose current ask has already been re-sent; the caller clears a session from it whenever a full applies. */
export function staleAnswer(reasked: Set<string>, sid: string): "reask" | "apply" {
  if (reasked.has(sid)) return "apply";
  reasked.add(sid);
  return "reask";
}
