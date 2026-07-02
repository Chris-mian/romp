// Phase 2b — the pure core of the federated dashboard: prefix inbound session ids by host, route outbound
// messages to the owning kernel (stripping the prefix), and merge per-host tab orders group-by-host. This
// is the risky logic; the WebSocket/DOM wiring in federation.ts's manager is thin glue over these.

import { test } from "node:test";
import assert from "node:assert/strict";
import { prefixId, hostOf, bareId, prefixInbound, routeOutbound, mergeHostOrder, mergeHostFeeds } from "./federation";

const U = "11111111-2222-3333-4444-555555555555";
const V = "99999999-8888-7777-6666-555555555555";

test("prefixId / hostOf / bareId round-trip", () => {
  assert.equal(prefixId("gpu1", U), "gpu1:" + U);
  assert.equal(prefixId("", U), U, "local host adds no prefix");
  assert.equal(hostOf("gpu1:" + U), "gpu1");
  assert.equal(hostOf(U), "", "a bare UUID has no host");
  assert.equal(bareId("gpu1:" + U), U);
  assert.equal(bareId(U), U);
});

test("prefixInbound: local host is the identity transform", () => {
  const m = { type: "session", id: U };
  assert.deepEqual(prefixInbound("", m), m);
});

test("prefixInbound: scalar id (session/chatTail/focus/ledger/renamed/closed)", () => {
  assert.equal(prefixInbound("gpu1", { type: "session", id: U }).id, "gpu1:" + U);
  assert.equal(prefixInbound("gpu1", { type: "focus", id: U, anchor: "x" }).id, "gpu1:" + U);
});

test("prefixInbound: working.names[] array of ids", () => {
  const out = prefixInbound("gpu1", { type: "working", names: [U, V] });
  assert.deepEqual(out.names, ["gpu1:" + U, "gpu1:" + V]);
});

test("prefixInbound: tabOrder order[] and tabs[].id", () => {
  const out = prefixInbound("gpu1", { type: "tabOrder", order: [U, V], tabs: [{ id: U, name: "a" }] });
  assert.deepEqual(out.order, ["gpu1:" + U, "gpu1:" + V]);
  assert.equal(out.tabs[0].id, "gpu1:" + U);
  assert.equal(out.tabs[0].name, "a", "non-id fields are untouched");
});

test("prefixInbound: feed payload asks/items/ledgers[].sid and working[]", () => {
  const out = prefixInbound("gpu1", {
    type: "feed",
    asks: [{ sid: U, q: "?" }],
    items: [{ sid: V, t: 1 }],
    ledgers: [{ sid: U, ledger: {} }],
    working: [U, V],
  });
  assert.equal(out.asks[0].sid, "gpu1:" + U);
  assert.equal(out.asks[0].q, "?", "non-id fields untouched");
  assert.equal(out.items[0].sid, "gpu1:" + V);
  assert.equal(out.ledgers[0].sid, "gpu1:" + U);
  assert.deepEqual(out.working, ["gpu1:" + U, "gpu1:" + V]);
});

test("prefixInbound: messages without ids pass through (no spurious fields touched)", () => {
  const m = { type: "clipboardText", text: "hi" };
  assert.deepEqual(prefixInbound("gpu1", m), m);
  const orig = { type: "session", id: U };
  prefixInbound("gpu1", orig);
  assert.equal(orig.id, U, "input is not mutated (copy returned)");
});

test("routeOutbound: a local (bare) id routes to the local kernel unchanged", () => {
  const routes = routeOutbound({ type: "activeTab", id: U });
  assert.equal(routes.length, 1);
  assert.equal(routes[0].host, "");
  assert.equal(routes[0].msg.id, U);
});

test("routeOutbound: a remote id routes to its host with the prefix stripped", () => {
  const routes = routeOutbound({ type: "send", id: "gpu1:" + U, text: "hello" });
  assert.equal(routes.length, 1);
  assert.equal(routes[0].host, "gpu1");
  assert.equal(routes[0].msg.id, U, "id is stripped back to bare for the owning kernel");
  assert.equal(routes[0].msg.text, "hello");
});

test("routeOutbound: a global message (no session id) goes local", () => {
  const routes = routeOutbound({ type: "setColormap", name: "viridis" });
  assert.deepEqual(routes, [{ host: "", msg: { type: "setColormap", name: "viridis" } }]);
});

test("routeOutbound: a cross-host reorder fans out one route per host with its own sids", () => {
  const order = [U, "gpu1:" + V, "gpu1:" + U, V]; // local U, gpu1 V, gpu1 U, local V
  const routes = routeOutbound({ type: "reorderTabs", order });
  const byHost = Object.fromEntries(routes.map((r) => [r.host, r.msg.order]));
  assert.deepEqual(byHost[""], [U, V], "local kernel gets its sids in their relative order, bare");
  assert.deepEqual(byHost["gpu1"], [V, U], "gpu1 gets its sids in their relative order, bare");
});

test("mergeHostOrder: each host verbatim, concatenated in hostSeq order, deduped", () => {
  const perHost = {
    "": [U, V],
    gpu1: ["gpu1:" + V, "gpu1:" + U],
  };
  const merged = mergeHostOrder(perHost, ["", "gpu1"]);
  assert.deepEqual(merged, [U, V, "gpu1:" + V, "gpu1:" + U]);
  // hostSeq controls grouping order; a missing host contributes nothing.
  assert.deepEqual(mergeHostOrder(perHost, ["gpu1", "", "absent"]), ["gpu1:" + V, "gpu1:" + U, U, V]);
});

test("mergeHostOrder: never re-sorts within a host (kernel order is authoritative)", () => {
  // even though V<U lexically, gpu1's given order is preserved verbatim
  const merged = mergeHostOrder({ gpu1: ["gpu1:" + U, "gpu1:" + V] }, ["gpu1"]);
  assert.deepEqual(merged, ["gpu1:" + U, "gpu1:" + V]);
});

test("mergeHostFeeds: concatenates items/asks/working across hosts (local first), keeps local chrome", () => {
  // Regression: without a merge, the local + remote feed snapshots (each pushed ~2s) clobber each other and
  // the feed visibly flips back and forth. mergeHostFeeds combines them into one stable snapshot.
  const perHost = {
    "": { type: "feed", items: [{ sid: U }], asks: [{ sid: U, itemId: "a" }], working: [U],
          ledgers: [{ sid: U }], now: 1000, dismissedCount: 3, showDismissed: false, canUndoClear: true },
    jetty: { type: "feed", items: [{ sid: "jetty:" + V }], asks: [{ sid: "jetty:" + V, itemId: "b" }],
             working: ["jetty:" + V], ledgers: [{ sid: "jetty:" + V }], now: 999, dismissedCount: 7 },
  };
  const m = mergeHostFeeds(perHost, ["", "jetty"]);
  assert.equal(m.type, "feed");
  assert.deepEqual(m.items.map((i: any) => i.sid), [U, "jetty:" + V], "items concatenated, local first");
  assert.deepEqual(m.asks.map((a: any) => a.sid), [U, "jetty:" + V], "asks concatenated");
  assert.deepEqual(m.working, [U, "jetty:" + V], "working concatenated");
  assert.deepEqual(m.ledgers.map((l: any) => l.sid), [U, "jetty:" + V], "ledgers (fleet) concatenated");
  // local is authoritative for the dashboard's own chrome — remote's counts/clock don't leak in.
  assert.equal(m.now, 1000);
  assert.equal(m.dismissedCount, 3);
  assert.equal(m.showDismissed, false);
  assert.equal(m.canUndoClear, true);
});

test("mergeHostFeeds: single (local) host is an equivalent passthrough", () => {
  const local = { type: "feed", items: [{ sid: U }], asks: [], working: [U], now: 5, dismissedCount: 0 };
  const m = mergeHostFeeds({ "": local }, [""]);
  assert.deepEqual(m.items, [{ sid: U }]);
  assert.deepEqual(m.working, [U]);
  assert.equal(m.now, 5);
});

test("mergeHostFeeds: a host with no feed yet contributes nothing (no crash)", () => {
  const m = mergeHostFeeds({ "": { type: "feed", items: [{ sid: U }], asks: [], working: [] } }, ["", "jetty"]);
  assert.deepEqual(m.items.map((i: any) => i.sid), [U]);
});

test("mergeHostFeeds: ledgers omitted until some host builds them (fleet loader holds)", () => {
  // No host has a ledgers array yet → merged carries no `ledgers` key, so fleet.ts keeps its loader up
  // rather than dropping onto an empty pane.
  const m = mergeHostFeeds({ "": { type: "feed", items: [], asks: [], working: [] } }, [""]);
  assert.equal("ledgers" in m, false);
});
