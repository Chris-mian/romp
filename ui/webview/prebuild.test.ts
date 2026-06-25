// The chat keeps switching SNAPPY by pre-building off-screen tabs during browser idle, so a switch lands on
// an already-built view instead of paying its O(events) DOM build on first visit (the user 2026-06-25: tabs
// "open one at a time"; switch delay scales with transcript length). This pins the POLICY — which off-screen
// tabs need building and in what order — so a future refactor of render.ts's DOM plumbing can't silently drop
// the optimization. Behavioral (imports the pure module), not a source regex.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import { prebuildPlan, isViewCurrent, type ViewState } from "./prebuild";

const V = (p: Partial<ViewState>): ViewState => ({ events: 1, hasDom: false, stale: false, rendered: 0, ...p });

test("isViewCurrent matches showActive's non-heavy condition (built, fresh, fully-rendered)", () => {
  assert.equal(isViewCurrent(V({ hasDom: true, rendered: 5, events: 5 })), true, "built + current → instant switch");
  assert.equal(isViewCurrent(V({ hasDom: false, rendered: 0, events: 5 })), false, "unbuilt → must build");
  assert.equal(isViewCurrent(V({ hasDom: true, stale: true, rendered: 5, events: 5 })), false, "stale → must rebuild");
  assert.equal(isViewCurrent(V({ hasDom: true, rendered: 3, events: 5 })), false, "behind on events → must catch up");
});

test("the active tab is excluded — showActive owns it, pre-build only warms the rest", () => {
  const plan = prebuildPlan("a", ["a", "b"], ["a", "b", "c"], () => V({ events: 10 }));
  assert.deepEqual(plan, ["b", "c"]);
  assert.ok(!plan.includes("a"), "never pre-build the tab the user is already looking at");
});

test("most-recently-used first (the likeliest next switch), then tab order, deduped", () => {
  // mru: c was used most recently, then b; the tab strip order is a,b,c,d
  const plan = prebuildPlan("a", ["c", "b"], ["a", "b", "c", "d"], () => V({ events: 10 }));
  assert.deepEqual(plan, ["c", "b", "d"], "c,b from MRU first; d (only one not in MRU) last; a excluded");
});

test("skips already-current, empty, and not-yet-loaded tabs (no wasted idle work)", () => {
  const states: Record<string, ViewState> = {
    b: V({ events: 10, hasDom: true, rendered: 10 }), // current → skip
    c: V({ events: 0 }),                              // empty → skip (nothing to build)
    d: V({ events: 10, hasDom: true, rendered: 4 }), // behind → build
    e: V({ events: 10, hasDom: false }),             // unbuilt → build
  };
  const plan = prebuildPlan("a", [], ["a", "b", "c", "d", "e", "f"], (id) => states[id] ?? null); // f unknown → null → skip
  assert.deepEqual(plan, ["d", "e"]);
});

test("a built-but-stale view is rebuilt — an update that arrived while hidden must not be lost", () => {
  const plan = prebuildPlan("a", [], ["a", "b"], () => V({ events: 10, hasDom: true, rendered: 10, stale: true }));
  assert.deepEqual(plan, ["b"]);
});

test("no active tab (nothing open yet) still plans every loaded tab", () => {
  const plan = prebuildPlan(null, [], ["x", "y"], () => V({ events: 3 }));
  assert.deepEqual(plan, ["x", "y"]);
});
