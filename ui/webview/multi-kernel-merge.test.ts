// Phase 2b — the pure core of the federated dashboard: prefix inbound session ids by host, route outbound
// messages to the owning kernel (stripping the prefix), and merge per-host tab orders group-by-host. This
// is the risky logic; the WebSocket/DOM wiring in federation.ts's manager is thin glue over these.

import { test } from "node:test";
import assert from "node:assert/strict";
import { prefixId, hostOf, bareId, prefixInbound, routeOutbound, mergeHostOrder, mergeHostFeeds,
         prefixTimelineData, mergeHostTimelines, mergeHostBars } from "./federation";

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

test("prefixInbound: tabOrder order[] and tabs[].id (+ display name)", () => {
  const out = prefixInbound("gpu1", { type: "tabOrder", order: [U, V], tabs: [{ id: U, name: "a" }] });
  assert.deepEqual(out.order, ["gpu1:" + U, "gpu1:" + V]);
  assert.equal(out.tabs[0].id, "gpu1:" + U);
  assert.equal(out.tabs[0].name, "gpu1:a", "the tab's display name is host-prefixed too (host:name)");
});

test("prefixInbound: display name is host-prefixed on session-bearing messages", () => {
  // a session's tab + chat header should read "gpu1:foo" so a remote session never collides visually with a
  // local same-named one. Only prefixed when a co-present id/sid marks it as a session name.
  assert.equal(prefixInbound("gpu1", { type: "session", id: U, name: "foo" }).name, "gpu1:foo");
  assert.equal(prefixInbound("gpu1", { type: "renamed", id: U, name: "bar" }).name, "gpu1:bar");
  // feed items carry sid+name → their card name is prefixed too
  const fed = prefixInbound("gpu1", { type: "feed", items: [{ sid: U, name: "baz" }] });
  assert.equal(fed.items[0].sid, "gpu1:" + U);
  assert.equal(fed.items[0].name, "gpu1:baz");
  // a bare `name` with NO id is left alone (not a session name)
  assert.deepEqual(prefixInbound("gpu1", { type: "toast", name: "hi" }), { type: "toast", name: "hi" });
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
  // local is authoritative for the dashboard's own chrome (clock, toggles)…
  assert.equal(m.now, 1000);
  assert.equal(m.showDismissed, false);
  // …but the dismissed/undo chrome spans hosts: counts SUM, undo lights when ANY kernel can undo.
  assert.equal(m.dismissedCount, 10, "3 local + 7 remote dismissed");
  assert.equal(m.canUndoClear, true);
});

test("mergeHostFeeds: a remote-only undo lights the Undo button (clear routed to that kernel)", () => {
  const m = mergeHostFeeds({
    "": { type: "feed", items: [], asks: [], working: [], canUndoClear: false, dismissedCount: 0 },
    jetty: { type: "feed", items: [], asks: [], working: [], canUndoClear: true, dismissedCount: 2 },
  }, ["", "jetty"]);
  assert.equal(m.canUndoClear, true);
  assert.equal(m.dismissedCount, 2);
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

// ── timeline federation (the timeline now rides the same shim + merge as every other pane) ──────

test("prefixInbound: timeline {type:data} payload — sessions, turns keys + bar.tid, marks, activeChat", () => {
  const out = prefixInbound("jetty", {
    type: "data",
    data: {
      sessions: [{ id: U, name: "sess1", state: "idle" }],
      turns: { [U]: [{ id: "ev-1", tid: U, start: 1, end: 2 }] },
      messages: [{ id: "m1", fromId: U, toId: V, sent: 1, exec: 2 }],
      judging: [{ judge: "planner", sid: U, t: 1 }],
      nudges: [{ sid: U, t: 2, count: 1 }],
      activeChat: { tid: U, name: "sess1" },
      now: 1000,
    },
  });
  const d = out.data;
  assert.equal(d.sessions[0].id, "jetty:" + U);
  assert.equal(d.sessions[0].name, "jetty:sess1", "lane label reads host:name");
  assert.deepEqual(Object.keys(d.turns), ["jetty:" + U], "turns re-keyed by prefixed sid");
  assert.equal(d.turns["jetty:" + U][0].tid, "jetty:" + U, "a bar's tid (its sid) is prefixed");
  assert.equal(d.turns["jetty:" + U][0].id, "ev-1", "event uuids stay bare (globally unique)");
  assert.equal(d.messages[0].fromId, "jetty:" + U);
  assert.equal(d.messages[0].toId, "jetty:" + V);
  assert.equal(d.judging[0].sid, "jetty:" + U);
  assert.equal(d.nudges[0].sid, "jetty:" + U);
  assert.equal(d.activeChat.tid, "jetty:" + U, "the active-chat cue lights the prefixed lane");
  assert.equal(d.now, 1000, "scalar fields untouched");
});

test("prefixInbound: timeline {type:bars} detail message (top-level turns/marks)", () => {
  const out = prefixInbound("jetty", {
    type: "bars",
    turns: { [U]: [{ id: "ev-1", tid: U }] },
    judging: [{ judge: "closer", sid: U, t: 5 }],
    messages: [],
    nudges: [],
    now: 7,
  });
  assert.deepEqual(Object.keys(out.turns), ["jetty:" + U]);
  assert.equal(out.turns["jetty:" + U][0].tid, "jetty:" + U);
  assert.equal(out.judging[0].sid, "jetty:" + U);
  assert.equal(out.now, 7);
});

test("prefixTimelineData: local host is the identity transform", () => {
  const d = { sessions: [{ id: U, name: "a" }], turns: {} };
  assert.equal(prefixTimelineData("", d), d);
});

test("mergeHostTimelines: local lanes first, host stamped per session, turns/marks unioned, chrome local", () => {
  const perHost = {
    "": { sessions: [{ id: U, name: "loc" }], turns: {}, messages: [], judging: [], nudges: [],
          now: 1000, usage: { u: 1 }, focus: { nonce: 3 } },
    jetty: { sessions: [{ id: "jetty:" + V, name: "jetty:rem" }], turns: { ["jetty:" + V]: [{ id: "e" }] },
             messages: [{ fromId: "jetty:" + V }], judging: [], nudges: [{ sid: "jetty:" + V, t: 1 }], now: 999 },
  };
  const m = mergeHostTimelines(perHost, ["", "jetty"]);
  assert.deepEqual(m.sessions.map((s: any) => s.id), [U, "jetty:" + V], "local group first, remote below");
  assert.deepEqual(m.sessions.map((s: any) => s.host), ["", "jetty"], "owning host stamped (drives the lane-group gap)");
  assert.deepEqual(Object.keys(m.turns), ["jetty:" + V]);
  assert.equal(m.messages.length, 1);
  assert.equal(m.nudges[0].sid, "jetty:" + V);
  assert.equal(m.now, 1000, "the LOCAL kernel is the clock authority");
  assert.deepEqual(m.usage, { u: 1 }, "usage (account rate-limit bars) stays local");
  assert.deepEqual(m.focus, { nonce: 3 }, "cross-pane focus stays local");
});

test("mergeHostBars: per-host bars union — one host's push can't clobber another's (applyBars replaces wholesale)", () => {
  const perHost = {
    "": { type: "bars", turns: { [U]: [{ id: "a" }] }, messages: [], judging: [{ judge: "planner", sid: U, t: 1 }], nudges: [], now: 50 },
    jetty: { type: "bars", turns: { ["jetty:" + V]: [{ id: "b" }] }, messages: [], judging: [], nudges: [], now: 49 },
  };
  const m = mergeHostBars(perHost, ["", "jetty"]);
  assert.deepEqual(Object.keys(m.turns).sort(), [U, "jetty:" + V].sort());
  assert.equal(m.judging.length, 1);
  assert.equal(m.now, 50, "local clock");
  // a host with no bars yet contributes nothing (no crash)
  const single = mergeHostBars({ "": perHost[""] }, ["", "jetty"]);
  assert.deepEqual(Object.keys(single.turns), [U]);
});

test("routeOutbound: an explicit host field routes there, stripped (createSession's + modal host pick)", () => {
  const remote = routeOutbound({ type: "createSession", name: "web", backend: "sdk", dir: "", host: "jetty" });
  assert.deepEqual(remote, [{ host: "jetty", msg: { type: "createSession", name: "web", backend: "sdk", dir: "" } }],
                   "the kernel handlers are host-blind — the field is stripped");
  const local = routeOutbound({ type: "createSession", name: "web", backend: "sdk", dir: "", host: "" });
  assert.deepEqual(local, [{ host: "", msg: { type: "createSession", name: "web", backend: "sdk", dir: "" } }]);
});

test("routeOutbound: name-addressed messages route to a KNOWN host only (compact / sendCommand / deepLink)", () => {
  const known = new Set(["jetty"]);
  // a remote lane's display name is prefixed → routed + stripped
  assert.deepEqual(routeOutbound({ type: "compact", name: "jetty:sess1" }, known),
                   [{ host: "jetty", msg: { type: "compact", name: "sess1" } }]);
  assert.deepEqual(routeOutbound({ type: "deepLink", session: "jetty:sess1" }, known),
                   [{ host: "jetty", msg: { type: "deepLink", session: "sess1" } }]);
  // a local name that merely CONTAINS a colon must not misroute (unknown host prefix)
  assert.deepEqual(routeOutbound({ type: "compact", name: "odd:name" }, known),
                   [{ host: "", msg: { type: "compact", name: "odd:name" } }]);
  // and with no knownHosts at all, names never route
  assert.deepEqual(routeOutbound({ type: "compact", name: "jetty:sess1" }),
                   [{ host: "", msg: { type: "compact", name: "jetty:sess1" } }]);
  // renameSession routes by ID; its `name` (the user's new title) is never stripped
  const rn = routeOutbound({ type: "renameSession", id: "jetty:" + U, name: "newtitle" }, known);
  assert.deepEqual(rn, [{ host: "jetty", msg: { type: "renameSession", id: U, name: "newtitle" } }]);
});

test("routeOutbound: a feed card action routes by its sid, itemId untouched (askClear/expand/askFollowUp)", () => {
  // Regression (the user 2026-07-02): Clear on a REMOTE card sent {askClear, itemId} with NO sid → routed
  // to the LOCAL kernel (a no-op there), so the card resurrected on every reload. The card's sid now rides
  // along purely for routing; the itemId stays bare — it's already the owning kernel's own id.
  const r = routeOutbound({ type: "askClear", itemId: U + ":g3", sid: "jetty:" + U });
  assert.deepEqual(r, [{ host: "jetty", msg: { type: "askClear", itemId: U + ":g3", sid: U } }]);
  // a local card is unchanged: bare sid → local kernel
  const l = routeOutbound({ type: "askClear", itemId: U + ":g3", sid: U });
  assert.equal(l[0].host, "");
});

test("routeOutbound: a hover CLEAR broadcasts to every kernel (no sid to route by)", () => {
  const routes = routeOutbound({ type: "timelineHover", off: true }, new Set(["jetty", "gpu1"]));
  assert.deepEqual(routes.map((r) => r.host).sort(), ["", "gpu1", "jetty"].sort());
  // …but a hover ON routes to the lane's owner only
  const on = routeOutbound({ type: "timelineHover", sid: "jetty:" + U, segIds: [] }, new Set(["jetty"]));
  assert.deepEqual(on, [{ host: "jetty", msg: { type: "timelineHover", sid: U, segIds: [] } }]);
});
