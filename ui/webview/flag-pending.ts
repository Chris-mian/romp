// Per-session VIEW FLAGS (the bell, the feed mute, the mail mute) are flipped OPTIMISTICALLY by the tab menu's rows and
// the bell command (render.ts setSessionFlag): the local copy takes the value at the click and the kernel is told. The
// kernel's frames carry the flags back — every chatTail on both chat wires (2026-09-11) and every full session frame —
// and a frame BUILT before the kernel applied the click can land after it with the old value, reverting the copy for one
// push cycle without new information (the cards-move-on-new-information rule; the review of 2026-09-14: the bell row read
// "Notify me" again after the toast said enabled, and a second press in that window flipped from the stale value). So a
// click records its expectation here, and a frame that still disagrees is held off while it stands: a frame that agrees
// is the echo and clears it; three disagreeing frames yield, because the kernel is the store of record and setSessionFlag
// has no per-write ack beyond the settingRefused frame, which drops the expectation outright. tab-meta.ts's pending guard
// for the label and the colour is the precedent; this is the same shape for booleans. Pure and DOM-free so node executes it.

export type SessionFlag = "notify" | "hideFromFeed" | "postalServiceOff";
export const SESSION_FLAGS: readonly SessionFlag[] = ["notify", "hideFromFeed", "postalServiceOff"];
export interface PendingFlag { value: boolean; age: number }
/** sid → flag → the value the click expects and how many disagreeing frames it has held off */
export type PendingFlags = Map<string, Map<SessionFlag, PendingFlag>>;
export const PENDING_FLAG_MAX_AGE = 3;

/** A click's expectation: the frames that follow cannot show the other value while it stands. */
export function notePendingFlag(pending: PendingFlags, id: string, flag: SessionFlag, value: boolean): void {
  let m = pending.get(id);
  if (!m) { m = new Map(); pending.set(id, m); }
  m.set(flag, { value, age: 0 });
}

/** The kernel refused the click (settingRefused), or the session left: nothing to hold any more. */
export function dropPendingFlag(pending: PendingFlags, id: string, flag?: SessionFlag): void {
  const m = pending.get(id);
  if (!m) return;
  if (flag) m.delete(flag); else m.clear();
  if (!m.size) pending.delete(id);
}

/** Apply the flags a frame carries to the session's copy, under the guard. A flag the frame does not carry is left
 *  alone. Returns the flags whose value on the copy changed. */
export function applyFrameFlags(s: Partial<Record<SessionFlag, boolean>>, frame: Record<string, unknown>, pending: PendingFlags, id: string): SessionFlag[] {
  const changed: SessionFlag[] = [];
  const m = pending.get(id);
  for (const f of SESSION_FLAGS) {
    const v = frame[f];
    if (typeof v !== "boolean") continue;
    let next = v;
    const p = m?.get(f);
    if (p) {
      if (p.value === v || p.age >= PENDING_FLAG_MAX_AGE) m!.delete(f);   // the echo; or the kernel's view standing after three silent frames
      else { p.age++; next = p.value; }                                  // a frame built before the click: held off
    }
    if (s[f] !== next) { s[f] = next; changed.push(f); }
  }
  if (m && !m.size) pending.delete(id);
  return changed;
}
