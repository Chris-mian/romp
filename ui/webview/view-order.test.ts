// The VIEWER's session order (the user 2026-07-31): order became a property of how you are LOOKING at the
// fleet rather than of the fleet, so it lives in the browser and can interleave hosts — which no kernel can
// do, since none of them knows another's sids. SYNTHETIC ids only.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import {
  applyViewOrder, applyViewOrderTo, pruneViewOrder, parseViewOrder,
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
