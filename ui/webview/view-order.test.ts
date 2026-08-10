// The VIEWER's session order (the user 2026-07-31): order became a property of how you are LOOKING at the
// fleet rather than of the fleet, so it lives in the browser and can interleave hosts — which no kernel can
// do, since none of them knows another's sids. SYNTHETIC ids only.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import {
  adoptArrivals, applyViewOrder, applyViewOrderTo, churnSwaps, healOrder, pruneViewOrder, parseViewOrder,
  VIEW_ORDER_KEY, VIEW_ORDER_CAP,
} from "./view-order";

const hostOf = (id: string) => { const i = id.indexOf(":"); return i > 0 ? id.slice(0, i) : ""; };

// ── applyViewOrder: the layering rule, executed ──────────────────────────────────────────────────────
test("no arrangement is the IDENTITY — nothing moves until the viewer moves it", () => {
  const seed = ["a", "b", "TESTHOST:c"];
  assert.deepEqual(applyViewOrder(seed, []), seed);
});

test("local and remote sessions INTERLEAVE — the whole point of moving this off the kernel", () => {
  // seed is the old per-host concatenation: both local sessions, then the host's block
  const seed = ["a", "b", "TESTHOST:c", "TESTHOST:d"];
  const view = ["a", "TESTHOST:c", "b", "TESTHOST:d"];
  assert.deepEqual(applyViewOrder(seed, view), ["a", "TESTHOST:c", "b", "TESTHOST:d"],
    "a local tab can sit between two of a server's");
});

test("a session the arrangement has never seen lands at the END, not somewhere arbitrary", () => {
  const view = ["b", "a"];
  assert.deepEqual(applyViewOrder(["a", "b", "new1", "new2"], view), ["b", "a", "new1", "new2"]);
  // …and the newcomers keep their SEED order among themselves (the kernel's arrival order)
  assert.deepEqual(applyViewOrder(["new2", "new1", "a"], ["a"]), ["a", "new2", "new1"]);
});

test("an arranged id that is no longer in the seed simply isn't drawn", () => {
  // its session was cleared, or its host detached — the entry stays in storage (prune decides that), but it
  // cannot conjure a tab that the merge doesn't carry
  assert.deepEqual(applyViewOrder(["a"], ["gone", "a", "TESTHOST:x"]), ["a"]);
});

test("duplicates and non-strings never reach the strip", () => {
  const seed = ["a", "a", null as any, "b"];
  assert.deepEqual(applyViewOrder(seed, ["b", "b", 7 as any]), ["b", "a"]);
});

// ── applyViewOrderTo: the same rule over the timeline's lane OBJECTS ─────────────────────────────────
test("lanes arrange by the same order the tabs do", () => {
  const lanes = [{ id: "a" }, { id: "b" }, { id: "TESTHOST:c" }];
  assert.deepEqual(applyViewOrderTo(lanes, ["TESTHOST:c", "a", "b"], (r) => r.id).map((r) => r.id),
    ["TESTHOST:c", "a", "b"]);
});

test("lanes the arrangement doesn't name keep their arrival order, at the end", () => {
  const lanes = [{ id: "x" }, { id: "a" }, { id: "y" }];
  assert.deepEqual(applyViewOrderTo(lanes, ["a"], (r) => r.id).map((r) => r.id), ["a", "x", "y"]);
});

// ── pruneViewOrder: event-based self-clean ───────────────────────────────────────────────────────────
test("an id its own host has stopped listing is dropped", () => {
  const view = ["a", "b", "TESTHOST:c"];
  const kept = pruneViewOrder(view, hostOf, new Set(["", "TESTHOST"]), new Set(["a", "TESTHOST:c"]));
  assert.deepEqual(kept, ["a", "TESTHOST:c"], "b is gone from the local kernel's list, so it goes");
});

test("a host that ISN'T reporting keeps every one of its placements", () => {
  // the tunnel is down / the host is detached. Pruning here would flatten the arrangement of every remote
  // session and stack them all at the end of the strip the moment the host came back.
  const view = ["a", "TESTHOST:c", "TESTHOST:d"];
  const kept = pruneViewOrder(view, hostOf, new Set([""]), new Set(["a"]));
  assert.deepEqual(kept, view);
});

test("the cap is a backstop that keeps the MOST RECENT arrangement, not the oldest", () => {
  const view = Array.from({ length: VIEW_ORDER_CAP + 10 }, (_, i) => `s${i}`);
  const kept = pruneViewOrder(view, hostOf, new Set<string>(), new Set<string>());
  assert.equal(kept.length, VIEW_ORDER_CAP);
  assert.equal(kept[kept.length - 1], `s${VIEW_ORDER_CAP + 9}`);
});

// ── storage ──────────────────────────────────────────────────────────────────────────────────────────
test("a corrupt or foreign stored value reads as no arrangement, never throws", () => {
  for (const raw of [null, undefined, "", "{", "{}", '"nope"', "7", '[1,2]']) {
    assert.ok(Array.isArray(parseViewOrder(raw as any)), `${String(raw)} parses to a list`);
  }
  assert.deepEqual(parseViewOrder('["a",2,"b"]'), ["a", "b"], "non-strings are filtered, the rest survives");
});

test("the key is namespaced alongside the feed's other browser-owned state", () => {
  assert.match(VIEW_ORDER_KEY, /^romp:/);
});

// ── adoptArrivals / healOrder / churnSwaps: arrivals land at the END, a relaunch keeps its slot ──────
test("adoptArrivals appends never-placed ids at the END, in seed order among themselves", () => {
  assert.deepEqual(adoptArrivals(["b", "a"], ["a", "b", "n1", "TESTHOST:r", "n2"]),
    ["b", "a", "n1", "TESTHOST:r", "n2"]);
  // placed ids never move, and ids the seed doesn't carry (a detached host's) stay put too
  assert.deepEqual(adoptArrivals(["GONEHOST:x", "a"], ["a", "n"]), ["GONEHOST:x", "a", "n"]);
  // an empty arrangement adopts the whole seed verbatim — the shown order is unchanged by the write
  assert.deepEqual(adoptArrivals([], ["a", "TESTHOST:r"]), ["a", "TESTHOST:r"]);
});

test("a NEW local session shows after a remote host's sessions, not in front of them", () => {
  // The 2026-08-10 report: the provisional tab rendered at the very end, then the merge re-derived the
  // host-blocked seed (local block first) and popped the tab to in front of the remote block. Adoption
  // writes the end placement down, so every later merge and reload agrees with what first rendered.
  const view0 = adoptArrivals([], ["a", "b", "TESTHOST:r"]);        // the strip as first adopted
  const seed1 = ["a", "b", "NEW", "TESTHOST:r"];                    // the local kernel appends NEW to ITS block
  const view1 = adoptArrivals(view0, seed1);
  assert.deepEqual(applyViewOrder(seed1, view1), ["a", "b", "TESTHOST:r", "NEW"]);
});

test("healOrder hands a slot to the heir id in place", () => {
  assert.deepEqual(healOrder(["a", "old", "b"], new Map([["old", "new"]])), ["a", "new", "b"]);
  // a swap that would duplicate an id keeps the first occurrence
  assert.deepEqual(healOrder(["a", "old", "new"], new Map([["old", "new"]])), ["a", "new"]);
  assert.deepEqual(healOrder(["a", "b"], new Map()), ["a", "b"], "no swaps → unchanged");
});

test("churnSwaps pairs a vanished id with the appeared id of the same NAME — fsid churn, not a new session", () => {
  // a /clear mints a new transcript fsid for the same logical session; the kernel's own order inherits
  // the slot by name (_ordered, 2026-06-29) and the browser arrangement must follow the same way
  const swaps = churnSwaps(["f1", "s"], new Map([["f1", "web"], ["s", "api"]]),
                           ["f2", "s"], new Map([["f2", "web"], ["s", "api"]]));
  assert.deepEqual([...swaps], [["f1", "f2"]]);
  // no name recorded for the vanished id → no inheritance (a genuinely new session must not be claimed)
  assert.deepEqual([...churnSwaps(["x"], new Map(), ["y"], new Map([["y", "web"]]))], []);
  // an id present in both reports is never treated as churn
  assert.deepEqual([...churnSwaps(["x"], new Map([["x", "web"]]), ["x", "y"],
                                  new Map([["x", "web"], ["y", "web"]]))], []);
});
