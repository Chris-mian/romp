// Behavioral tests for the Fleet's top-row selection (ui/webview/fleet-roots.ts). EXECUTES the logic (unlike
// the source-regex pins in fleet.test.ts) and locks the behavior the user reported broken: "Show completed"
// must actually reveal completed tasks — including the fully-completed tops that were archived out of the live
// tree, which is why a finished session used to vanish from the Fleet entirely (the user 2026-06-27).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import { fleetVisibleRoots } from "./fleet-roots";

const open = { id: "o", done: false, cleared: false };
const done = { id: "d", done: true, cleared: false };
const clr = { id: "c", done: false, cleared: true };
const arch1 = { id: "a1", done: true, cleared: false };   // archived-completed top (from the kernel)
const arch2 = { id: "a2", done: true, cleared: false };

test("Show completed OFF: only open tops; done/cleared/archived hidden", () => {
  assert.deepEqual(fleetVisibleRoots([open, done, clr], [arch1], false).map((n) => n.id), ["o"]);
});

test("Show completed ON: open + done + cleared live tops, PLUS the archived-completed tops", () => {
  assert.deepEqual(fleetVisibleRoots([open, done, clr], [arch1, arch2], true).map((n) => n.id),
    ["o", "d", "c", "a1", "a2"]);
});

test("a finished+archived session (empty live tree) REAPPEARS under Show completed", () => {
  // This is the exact bug: live tree empty (all goals archived), so OFF → nothing → session skipped.
  assert.deepEqual(fleetVisibleRoots([], [arch1, arch2], false), []);          // OFF → still hidden (correct)
  assert.deepEqual(fleetVisibleRoots([], [arch1, arch2], true).map((n) => n.id), ["a1", "a2"]);  // ON → shows
});

test("archived tops are NEVER shown while the toggle is off, even if present in the payload", () => {
  assert.deepEqual(fleetVisibleRoots([open], [arch1], false).map((n) => n.id), ["o"]);
});

test("a session with only open work shows the same with the toggle either way", () => {
  assert.deepEqual(fleetVisibleRoots([open], [], false).map((n) => n.id), ["o"]);
  assert.deepEqual(fleetVisibleRoots([open], [], true).map((n) => n.id), ["o"]);
});
