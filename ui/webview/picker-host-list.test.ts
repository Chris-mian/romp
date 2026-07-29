// Switching Host in the + picker lists THAT machine's sessions (the user 2026-07-29), so a remote
// session can be reopened — or revived, if it has aged out — without going to that machine's own
// dashboard. Before this the list was always local, and a remote session that was not currently a tab
// was reachable from nowhere in this UI.
//
// The mechanism is the prefix. The rows come back with host-prefixed ids, so the click posts
// openSession with that id and routeOutbound sends it to the kernel that owns the session; the revive
// confirmation rides back the same way (`id` is a generic scalar-id field). prefixInbound is EXECUTED
// here; the picker plumbing is source-pinned, like the rest of render.ts.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { prefixInbound, routeOutbound } from "./federation";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");

const list = (items: any[]) => ({ type: "sessionList", items, defaultDir: "~/somewhere" });

test("a remote session list comes back with prefixed ids and names, stamped with its host", () => {
  const out = prefixInbound("TESTHOST", list([
    { id: "1111-2222", name: "api", running: true, time: "running" },
    { id: "3333-4444", name: "tests", running: false, time: "2h ago" }]));
  assert.deepEqual(out.items.map((i: any) => i.id), ["TESTHOST:1111-2222", "TESTHOST:3333-4444"]);
  assert.deepEqual(out.items.map((i: any) => i.name), ["TESTHOST:api", "TESTHOST:tests"]);
  assert.equal(out.host, "TESTHOST", "so the picker can tell whose answer this is");
  assert.equal(out.items[0].running, true, "everything else is left alone");
});

test("the LOCAL list is untouched, host and all", () => {
  const m = list([{ id: "1111-2222", name: "web" }]);
  assert.deepEqual(prefixInbound("", m), m, "no prefix, no host stamp, byte-identical");
});

test("a malformed row is passed through rather than mangled", () => {
  const out = prefixInbound("TESTHOST", list([null, "nope", { name: "no id" }]));
  assert.deepEqual(out.items, [null, "nope", { name: "no id" }]);
});

test("a click on a remote row routes to the kernel that owns the session", () => {
  // this is the whole point of prefixing the ids: the row posts the id it was given
  const [route] = routeOutbound({ type: "openSession", id: "TESTHOST:1111-2222" });
  assert.equal(route.host, "TESTHOST");
  assert.equal(route.msg.id, "1111-2222", "the kernel is host-blind — it gets its own bare id");
  // and reviving a dead one takes the same path
  const [rev] = routeOutbound({ type: "reviveSession", id: "TESTHOST:1111-2222" });
  assert.deepEqual([rev.host, rev.msg.id], ["TESTHOST", "1111-2222"]);
});

test("the request names the host, and every open starts from the local list", () => {
  assert.match(RENDER, /function requestSessionList\(host: string\): void \{\s*\n\s*pickerListHost = host;/);
  assert.match(RENDER, /postMessage\(\{ type: "requestSessions", host \}\)/);
  assert.match(RENDER, /requestSessionList\(""\);   \/\/ the Host row resets to local on open/);
});

test("a reply for a host the picker has moved on from is dropped, not painted", () => {
  // two kernels answer at their own speeds, so arrival order proves nothing about which is current
  assert.match(RENDER, /const from = typeof m\.host === "string" \? m\.host : "";/);
  assert.match(RENDER, /if \(from !== pickerListHost\) return;/);
  // and only the LOCAL reply's defaultDir is adopted — a remote's default belongs to that machine
  assert.match(RENDER, /if \(typeof m\.defaultDir === "string" && !from\) kernelDefaultDir = m\.defaultDir;/);
});

test("switching host swaps the list, with something on screen while it loads", () => {
  assert.match(RENDER, /requestSessionList\(h\);/);
  assert.match(RENDER, /loading \$\{h\}'s sessions…/);
});

test("a reachable host with no sessions says so, instead of looking like a failed search", () => {
  assert.match(RENDER, /if \(!list\.children\.length && pickerListHost\)/);
  assert.match(RENDER, /no sessions on \$\{pickerListHost\} in the last 30 days/);
});
