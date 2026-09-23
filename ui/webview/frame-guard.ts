// The chat frame's WATERMARK guard (2026-09-22): the decisions render.ts applies to every session frame and chatTail
// before it touches the resident events, pure, so node executes them (frame-guard.test.ts).
//
// The kernel stamps every chat frame with what its build READ (kernel.py _chat_wm): `leaf`, the transcript the build
// parsed; `tx`, the parse's fileset key, one [mtime, size] row per file the parse read, taken before the read (so the
// content is at least as new as the rows say); `live`, the live tail's revision read before the merge. Two builders can
// read the transcript in either order and hand a client their lists in either order, and the kernel's senders refuse a
// build older than the one a client holds (kernel.py _chat_wm_older). This is the page's own copy of that rule: a frame
// whose watermark is older than the session's is IGNORED and filed as `frame-stale`, so a kernel that let one through
// (an older kernel, a sender outside the guard) cannot take a landed message off the page. The user (2026-09-22) watched
// a message they had just sent land, vanish two seconds later, and come back only on a reload: the vanishing frame
// carried an older parse (its record not yet read) under a newer live tail (the echo still in it).
//
// And whatever the watermark says, a frame that REMOVES a landed human turn the page held is filed (`frame-drops-landed`),
// so the loss is never silent again: a rewind or a rebased fork removes rows on purpose (the callers pass those cases
// as `expected`), anything else is the kernel's newer list disagreeing with its older one about a record.

export type FrameWm = { leaf?: string; tx?: unknown; live?: unknown };

const isRow = (r: unknown): r is (number | string)[] => Array.isArray(r) && r.length > 0;

/** kernel.py _chat_wm_older, byte for byte in its decisions: `frame` read an OLDER world than `held` when the leaf is the
 *  same and either every parse row is at or behind the held's with one strictly behind, or the rows are equal and the live
 *  revision is a smaller integer. Two leaves, keys of different shapes, a mixed reading (a file ahead, another behind: it
 *  carries something new), a non-integer revision or a missing part are never older: the frame applies. */
export function frameOlder(held: FrameWm | null | undefined, frame: FrameWm | null | undefined): boolean {
  if (!held || !frame || typeof held !== "object" || typeof frame !== "object") return false;
  if ((held.leaf ?? "") !== (frame.leaf ?? "")) return false;
  const a = frame.tx, b = held.tx;
  if (Array.isArray(a) && Array.isArray(b)) {
    if (a.length !== b.length) return false;
    const same = a.every((r, i) => JSON.stringify(r) === JSON.stringify(b[i]));
    if (!same) {
      for (let i = 0; i < a.length; i++) {
        const x = a[i], y = b[i];
        if (!isRow(x) || !isRow(y) || x.length !== y.length) return false;
        // lexicographic row compare, as Python compares tuples: x <= y
        let le = true;
        for (let k = 0; k < x.length; k++) {
          const p = x[k], q = y[k];
          if (typeof p !== "number" || typeof q !== "number") return false;
          if (p < q) { le = true; break; }
          if (p > q) { le = false; break; }
        }
        if (!le) return false;
      }
      return true;
    }
  } else if (a != null || b != null) return false;
  const la = frame.live, lb = held.live;
  return typeof la === "number" && typeof lb === "number" && Number.isInteger(la) && Number.isInteger(lb) && la < lb;
}

/** A RECONNECT forgets the watermarks the page holds (2026-09-23). The kernel's live-tail revision is a per-process counter
 *  (sdk_backend.py _live_rev, read by live_rev as 0 for a sid it has not touched), so after a kernel restart with the dashboard
 *  open every held session whose transcript and states file have not moved is served frames with the same leaf, the same tx
 *  rows and live 0, which frameOlder reads as older than the held revision (say 57): the connect push's full and every frame
 *  after it would be ignored and filed frame-stale until that session's files moved. The kernel's own rule resets a client's
 *  base on reconnect (kernel.py _client_reset_chat_base: a client holding no floor takes any build); this is the page's twin,
 *  called from the three reconnect-class events render.ts sees: the shim's {type:"wsup"} frame (the local socket, every host,
 *  as the kernel-side reset at that socket's ready spans every base), the relay's reopen (romp:hostRelayUp, that host's sids
 *  only) and the extension pane's pipeState up edge (the pane never sees wsup). `ofHost` narrows the reset to the sids it
 *  admits; null forgets every held one. Forgetting is the safe error: a frame the guard would have refused rides in, and the
 *  kernel's own senders still order the sends. Returns the sids forgotten, in the map's order. */
export function forgetHeldWm<S extends { wm?: FrameWm }>(held: Iterable<[string, S]>, ofHost: ((sid: string) => boolean) | null): string[] {
  const out: string[] = [];
  for (const [sid, s] of held) {
    if (!s || s.wm === undefined) continue;
    if (ofHost && !ofHost(sid)) continue;
    delete s.wm;
    out.push(sid);
  }
  return out;
}

/** The slice of a chat event this module reads (render.ts's ChatEvent is a superset). */
export type GuardEvent = { kind?: string; uuid?: string; key?: string; romp?: boolean; rompAuto?: boolean; rompSystem?: boolean;
                           undelivered?: boolean; source?: unknown; hiddenByPending?: boolean };

/** The kernel's TRANSIENT live-tail keys (kernel.py _TRANSIENT_KEY_PREFIXES; frame-guard.test.ts pins the two lists equal): the
 *  SDK send's input echo `echo:<qid>`, the Codex send's echo `echo-<hex>` (codex_backend.py CodexBackend.send) and the /model,
 *  /effort, /auth and Codex /clear acknowledgement chip `cmd:<t>:<name>` (sdk_backend.py _ack_cmd_chip). build_session emits all
 *  three as human user events, and each retires routinely (an echo once its text is in the transcript, a chip when its gesture
 *  lands), so none is a landed turn: a frame that no longer carries one drops nothing. Before 2026-09-23 only `echo:` was
 *  excluded, and every retiring Codex echo and every chip filed a false frame-drops-landed row. */
export const TRANSIENT_KEY_PREFIXES = ["echo:", "echo-", "cmd:"] as const;
export function isTransient(u: string | undefined): boolean {
  if (!u) return false;
  for (const p of TRANSIENT_KEY_PREFIXES) if (u.startsWith(p)) return true;
  return false;
}
const isOptimistic = (u: string | undefined): boolean => !!u && (u.startsWith("optimistic:") || u.startsWith("held:"));

/** A LANDED HUMAN turn: a user event the transcript recorded (a uuid that is neither one of the kernel's transient live-tail
 *  keys nor the page's own injection), typed by the person (not romp's nudge, notice or system line, not a harness-injected record), not a
 *  never-delivered verdict. Keyed by its uuid. */
export function landedHumanKeys(events: readonly GuardEvent[] | null | undefined): string[] {
  const out: string[] = [];
  for (const e of events || []) if (isLandedHuman(e)) out.push(e.uuid);
  return out;
}
/** One event's reading of the rule above (send-landing.ts walks the tail with it, and stops early). */
export function isLandedHuman(e: GuardEvent | null | undefined): e is GuardEvent & { uuid: string } {
  if (!e || e.kind !== "user" || typeof e.uuid !== "string" || !e.uuid) return false;
  return !(isTransient(e.uuid) || isOptimistic(e.uuid) || e.undelivered || e.romp || e.rompAuto || e.rompSystem || e.source);
}

/** The landed human turns `before` held that `after` no longer holds (by uuid), in `before`'s order. */
export function droppedLandedHuman(before: readonly GuardEvent[] | null | undefined, after: readonly GuardEvent[] | null | undefined): string[] {
  const keep = new Set<string>();
  for (const e of after || []) if (e && typeof e.uuid === "string") keep.add(e.uuid);
  return landedHumanKeys(before).filter((u) => !keep.has(u));
}

/** The `frame-drops-landed` row's data: the frame's wire type, how many landed human turns left and their uuids' tails (12
 *  chars each, never the text), whether the frame carried a watermark, and why the caller expected a removal, if it did (a
 *  rebased fork, a rewind the page itself asked for). Filed for every removal, expected or not: an expected one is
 *  information too, and the row says which it was. */
export function dropsLandedRow(id: string, type: string, dropped: readonly string[], hadWm: boolean, expected: string | null): Record<string, unknown> {
  return { id, type, n: dropped.length, keys: dropped.slice(0, 8).map((u) => u.slice(-12)), wm: hadWm, expected: expected ?? null };
}
