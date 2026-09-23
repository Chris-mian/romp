// The chat view's KEYED PAINT (2026-09-23): what a painted display unit is, so a frame repaints only the units that changed.
//
// A unit's DOM is a pure function of its inputs: the unit's shape (an event, a folded run, a gap), the content of its
// events, and the context the paint reads around it (the previous timed epoch its time marker compares against, the day
// walk's mark its divider decision reads, its turn number, a fold's open state, a user bubble's editable affordance). The
// page records those inputs per painted unit as a SIGNATURE, and a frame whose inputs for a unit equal the recorded ones
// leaves that unit's nodes exactly as they are. Before this, every send and every landing rebuilt the whole window (a
// stale mark), compact mode rebuilt it on every frame, and a kernel repeating the same tail rewrote the last events each
// time: every unit was replaced, the top spacer re-estimated, and the reader moved by tens of thousands of pixels on a
// long transcript. And the exact tail path trimmed by EVENT index where the window build tags by UNIT index (a history
// gap shifts them by one), so the first tail frame after a window build dropped the node above the change: the landed
// message at the first frame of its reply. render.ts syncViewInner wires these rules to the DOM (tailDiff); this module
// is pure so node runs every rule (unit-diff.test.ts).
import type { DisplayItem } from "./compact";

/** The events a unit paints, in order (a gap paints none). */
export function unitEvents(it: DisplayItem): number[] {
  if (it.kind === "event") return [it.index];
  if (it.kind === "gap") return [];
  return it.indices;
}

/** The highest event index a unit paints, or -1 for a gap. */
export function unitLastEvent(it: DisplayItem): number {
  if (it.kind === "event") return it.index;
  if (it.kind === "gap") return -1;
  return it.indices.length ? it.indices[it.indices.length - 1] : -1;
}

/** Two units of the same SHAPE: the same kind over the same event indices (a gap: the same turn span before the same event). */
export function sameUnit(a: DisplayItem | undefined, b: DisplayItem | undefined): boolean {
  if (!a || !b || a.kind !== b.kind) return false;
  if (a.kind === "event") return a.index === (b as typeof a).index;
  if (a.kind === "gap") { const g = b as typeof a; return a.lo === g.lo && a.hi === g.hi && a.before === g.before; }
  const bi = (b as typeof a).indices;
  if (a.indices.length !== bi.length) return false;
  for (let i = 0; i < bi.length; i++) if (a.indices[i] !== bi[i]) return false;
  return true;
}

/** The unit lists agree in shape over [from, to): the units above a painted window keep their numbering, so the window's
 *  data-unit tags still name the same units. False when either list is shorter than `to`. */
export function sameUnits(a: readonly DisplayItem[], b: readonly DisplayItem[], from: number, to: number): boolean {
  if (a.length < to || b.length < to) return false;
  for (let u = from; u < to; u++) if (!sameUnit(a[u], b[u])) return false;
  return true;
}

/** A 53-bit hash of a string (cyrb53): the content half of a unit's signature. A collision would leave a changed unit
 *  painted as it was, so the hash is wide and the string's length rides beside it. */
export function hash53(str: string): string {
  let h1 = 0xdeadbeef, h2 = 0x41c6ce57;
  for (let i = 0; i < str.length; i++) {
    const ch = str.charCodeAt(i);
    h1 = Math.imul(h1 ^ ch, 2654435761);
    h2 = Math.imul(h2 ^ ch, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return (4294967296 * (2097151 & h2) + (h1 >>> 0)).toString(36) + "." + str.length.toString(36);
}

let unserializable = 0;
/** An event's content as its signature half: the JSON of every field the kernel sent and the page added (a hide mark, a
 *  rewind dim, a pending bubble's label), so an event re-sent unchanged hashes the same and one with any field changed does
 *  not. A field set to undefined serializes as absent, the shape a strip leaves. An event JSON cannot carry (never expected)
 *  gets a value no other call returns: it always repaints, never silently stands. */
export function contentHash(ev: unknown): string {
  let json: string;
  try { json = JSON.stringify(ev) ?? "undefined"; } catch { return "!" + (++unserializable); }
  return hash53(json);
}

/** The first index where two event lists stop holding the SAME objects, or -1 when they hold the same objects throughout.
 *  Every pass that edits a session's events in place swaps the object it changes and keeps the one it leaves (the pending
 *  sends' strip and reinjection, the held copies' pass), so this names exactly where the view must start comparing. */
export function firstReplaced(before: readonly unknown[], after: readonly unknown[]): number {
  const n = Math.min(before.length, after.length);
  let i = 0;
  while (i < n && before[i] === after[i]) i++;
  return i === before.length && i === after.length ? -1 : i;
}
