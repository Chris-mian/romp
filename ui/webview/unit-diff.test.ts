// The keyed paint's pure rules (unit-diff.ts, 2026-09-23), executed: what a unit's shape is, when the units above a window
// keep their numbering, the content half of a signature, and the first object a pass swapped. The DOM half (render.ts
// tailDiff) runs against a real page in tests/test_send_tail_append_browser.py. Synthetic events only.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import { contentHash, firstReplaced, hash53, sameUnit, sameUnits, unitEvents, unitLastEvent } from "./unit-diff";
import type { DisplayItem } from "./compact";

const ev = (index: number): DisplayItem => ({ kind: "event", index });
const tg = (...indices: number[]): DisplayItem => ({ kind: "toolgroup", indices });
const gap = (lo: number, hi: number, before: number): DisplayItem => ({ kind: "gap", lo, hi, before });

test("a unit's events and its last event: one for an event, the run's members for a run, none for a gap", () => {
  assert.deepEqual(unitEvents(ev(4)), [4]);
  assert.deepEqual(unitEvents(tg(5, 7, 8)), [5, 7, 8]);
  assert.deepEqual(unitEvents(gap(0, 30, 0)), []);
  assert.equal(unitLastEvent(ev(4)), 4);
  assert.equal(unitLastEvent(tg(5, 7, 8)), 8);
  assert.equal(unitLastEvent(gap(0, 30, 0)), -1, "a gap paints no event: never trusted by the first changed event");
});

test("two units share a shape when they are the same kind over the same events (a gap: the same span before the same event)", () => {
  assert.ok(sameUnit(ev(3), ev(3)));
  assert.ok(!sameUnit(ev(3), ev(4)));
  assert.ok(!sameUnit(ev(3), tg(3, 4)), "a lone tool that became a run is a different unit");
  assert.ok(sameUnit(tg(3, 4), tg(3, 4)));
  assert.ok(!sameUnit(tg(3, 4), tg(3, 4, 5)), "a run that grew is a different unit");
  assert.ok(sameUnit(gap(0, 30, 0), gap(0, 30, 0)));
  assert.ok(!sameUnit(gap(0, 30, 0), gap(0, 31, 0)));
  assert.ok(!sameUnit(undefined, ev(0)));
});

test("the units above a window keep their numbering only when every one keeps its shape; a shorter list never does", () => {
  const painted = [gap(0, 40, 0), ev(0), ev(1), ev(2), ev(3)];
  assert.ok(sameUnits(painted, [gap(0, 40, 0), ev(0), ev(1), ev(2), ev(3), ev(4)], 0, 3), "an append below the window leaves them alone");
  assert.ok(!sameUnits(painted, [gap(0, 32, 0), ev(0), ev(1), ev(2)], 0, 3), "a gap that shrank above the window renumbers nothing but reshapes a unit");
  assert.ok(!sameUnits(painted, [ev(0), ev(1)], 0, 3), "fewer units than the window's start");
  assert.ok(sameUnits(painted, painted, 0, 0), "a window starting at the top has nothing above it");
});

test("the content half of a signature: the same fields hash the same, any changed field does not, an undefined field reads as absent", () => {
  const a = { kind: "assistant", uuid: "11111111-2222-3333-4444-000000000001", md: "Paragraph one." };
  assert.equal(contentHash(a), contentHash({ ...a }), "an event re-sent unchanged (a fresh object from the wire) hashes the same");
  assert.notEqual(contentHash(a), contentHash({ ...a, md: "Paragraph one, revised." }));
  assert.notEqual(contentHash({ kind: "user", md: "x" }), contentHash({ kind: "user", md: "x", hiddenByPending: true }), "a page-side mark counts");
  assert.equal(contentHash({ kind: "user", md: "x" }), contentHash({ kind: "user", md: "x", hiddenByPending: undefined }), "a strip's undefined is the unmarked shape");
  const loop: Record<string, unknown> = { kind: "x" }; loop.self = loop;
  assert.notEqual(contentHash(loop), contentHash(loop), "an event JSON cannot carry never matches anything: it always repaints");
  assert.notEqual(hash53("ab"), hash53("ba"));
  assert.match(hash53(""), /^[0-9a-z]+\.0$/, "the length rides beside the hash");
});

test("the first swapped object: every pass that changes an event swaps it, one that leaves it keeps it", () => {
  const e = [{ i: 0 }, { i: 1 }, { i: 2 }];
  assert.equal(firstReplaced(e, e.slice()), -1, "nothing swapped");
  assert.equal(firstReplaced(e, [e[0], { ...e[1] }, e[2]]), 1, "an equal but fresh object is a swap: the view compares from there by content");
  assert.equal(firstReplaced(e, e.slice(0, 2)), 2, "a removal at the tail");
  assert.equal(firstReplaced(e, [...e, { i: 3 }]), 3, "an append");
  assert.equal(firstReplaced([], [{ i: 0 }]), 0);
});
