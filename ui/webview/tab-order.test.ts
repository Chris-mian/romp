// Behavioral tests for the chat tab ordering model (ui/webview/tab-order.ts). Unlike the source-text regex
// pins elsewhere in this suite, these EXECUTE the logic across realistic push sequences and assert the one
// property the user cares about: the order is stable — it changes ONLY on a drag, a new session (append), or
// a close (remove), NEVER on a status/activity update (the user 2026-06-27). This is the layer the kernel's
// own order tests never reached, which is why the jumping survived every "fix".
import { test } from "node:test";
import * as assert from "node:assert/strict";
import { reconcileTabOrder } from "./tab-order";

// A tiny stand-in for the client's tab state: the order array + the set of ids whose session is known. The
// real render.ts drives the SAME three ops (append on a session push, remove on close, reconcile on a kernel
// tabOrder push) plus a drag that sets the array directly.
function model() {
  let order: string[] = [];
  const knownIds = new Set<string>();
  return {
    onSession(id: string) { knownIds.add(id); if (!order.includes(id)) order.push(id); },   // a session push
    onClose(id: string) { knownIds.delete(id); order = order.filter((x) => x !== id); },     // a tab close
    onKernelOrder(kernel: string[]) { order = reconcileTabOrder(kernel, order, (id) => knownIds.has(id)); },
    onDrag(newOrder: string[]) { order = newOrder.slice(); },                                 // user drag
    list() { return order.slice(); },
  };
}

test("a kernel push is adopted verbatim", () => {
  assert.deepEqual(reconcileTabOrder(["A", "B", "C"], [], () => true), ["A", "B", "C"]);
});

test("a session that arrived before its tabOrder push is kept (appended), then reconciled in place", () => {
  const m = model();
  m.onSession("A");                       // session push beats the tabOrder push
  assert.deepEqual(m.list(), ["A"]);
  m.onKernelOrder([]);                    // kernel hasn't caught up yet → A stays (don't vanish)
  assert.deepEqual(m.list(), ["A"]);
  m.onKernelOrder(["A"]);                 // kernel catches up → no duplicate, correct slot
  assert.deepEqual(m.list(), ["A"]);
});

test("a status/activity update never reorders (it simply doesn't touch the order)", () => {
  const m = model();
  m.onSession("A"); m.onSession("B"); m.onSession("C");
  m.onKernelOrder(["A", "B", "C"]);
  const before = m.list();
  // ...B works hard, C goes idle, A gets a new message — none of that calls into the order model at all.
  // Re-adopting the SAME (stable) kernel order must be a no-op.
  m.onKernelOrder(["A", "B", "C"]);
  assert.deepEqual(m.list(), before, "order is unchanged by activity");
  assert.deepEqual(m.list(), ["A", "B", "C"]);
});

test("a new session appends at the end, never jumps to the top", () => {
  const m = model();
  m.onKernelOrder(["A", "B"]);
  m.onSession("C");                       // brand-new session arrives
  assert.deepEqual(m.list(), ["A", "B", "C"]);
  m.onKernelOrder(["A", "B", "C"]);       // kernel agrees (it appends newcomers too)
  assert.deepEqual(m.list(), ["A", "B", "C"]);
});

test("a drag sticks and does NOT snap back on the next poll (kernel echoes the persisted order)", () => {
  const m = model();
  m.onSession("A"); m.onSession("B"); m.onSession("C");
  m.onKernelOrder(["A", "B", "C"]);
  m.onDrag(["C", "A", "B"]);              // user drags C to the front
  assert.deepEqual(m.list(), ["C", "A", "B"]);
  m.onKernelOrder(["C", "A", "B"]);       // kernel persisted + echoes it back → no snap-back
  assert.deepEqual(m.list(), ["C", "A", "B"]);
  m.onKernelOrder(["C", "A", "B"]);       // a later poll → still stable
  assert.deepEqual(m.list(), ["C", "A", "B"]);
});

test("closing a tab drops it and keeps the rest in order", () => {
  const m = model();
  m.onSession("A"); m.onSession("B"); m.onSession("C");
  m.onKernelOrder(["A", "B", "C"]);
  m.onClose("B");
  m.onKernelOrder(["A", "C"]);            // kernel no longer lists B
  assert.deepEqual(m.list(), ["A", "C"]);
});

test("a stale id (not in the kernel order and not locally known) is dropped", () => {
  // GHOST is in the prior local order but its session is gone and the kernel doesn't list it.
  assert.deepEqual(reconcileTabOrder(["A", "B"], ["A", "GHOST", "B"], (id) => id === "A" || id === "B"),
    ["A", "B"]);
});

test("output is deduped and string-only", () => {
  assert.deepEqual(reconcileTabOrder(["A", "A", "B"] as string[], ["B", "B"], () => true), ["A", "B"]);
  assert.deepEqual(reconcileTabOrder(["A", 7 as any, "B"], [], () => true), ["A", "B"]);
});
