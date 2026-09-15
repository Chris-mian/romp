// The remote dial URL a federated pane builds, and the ready it posts (or does not) on a redial (2026-09-15).
// A hub pane dials each remote socket with the served page's own terms (remoteDialUrl, from the shim's
// __rompDialTerms); this pins them on the wire and pins the redial handshake: reconnect=1&proto rides a
// socket the remote served whole before (a ready acked with a `caps` frame), and that socket's open posts NO
// ready, because a ready would run the remote's ready reset and pop the reconnect the URL just armed (the same
// reason the shim's own redial posts none). No standing test read a /remote/HOST/ws URL. Executed against the
// real FederationManager with a fake WebSocket that records its sends. Synthetic only (host TESTHOST,
// placeholder uuids).
import { test } from "node:test";
import assert from "node:assert/strict";
import { FederationManager, REMOTE_REDIAL_MS } from "./federation";

const SID = "11111111-2222-3333-4444-555555555555";        // a session TESTHOST owns
const LOCAL_SID = "99999999-8888-7777-6666-555555555555";  // a bare (local) session id
const PAGE_IID = "PAGEIID-0001";                            // the shim's per-page instance id

class FakeWS {
  static made: FakeWS[] = [];
  readyState = 0;
  sent: any[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((ev: any) => void) | null = null;
  onclose: ((ev: any) => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(public url: string) { FakeWS.made.push(this); }
  send(d: string): void { try { this.sent.push(JSON.parse(d)); } catch (e) { this.sent.push(d); } }
  open(): void { this.readyState = 1; this.onopen && this.onopen(); }
  frame(data: any): void { this.onmessage && this.onmessage({ data: JSON.stringify(data) }); }
  close(): void { this.readyState = 3; }
}

let clock = 1_000_000_000;

// The page's live dial terms, as the shim's __rompDialTerms would return them: a skeleton posture watching a
// REMOTE tab (host-prefixed, as the dashboard carries it), proto 2.
function terms(): any {
  return { app: "chat", iid: PAGE_IID, active: "TESTHOST:" + SID, col: "", skeleton: 1, provrows: 0, proto: 2, delta: 1 };
}

async function withManager(fn: (fm: any) => void | Promise<void>, opts: { noWid?: boolean } = {}): Promise<void> {
  const g: any = globalThis;
  const saved: Record<string, any> = {};
  const set = (k: string, v: any) => { saved[k] = { had: k in g, v: g[k] }; g[k] = v; };
  FakeWS.made = [];
  const realNow = Date.now;
  Date.now = () => clock;
  set("WebSocket", FakeWS);
  set("location", { protocol: "http:", host: "hub.local:1", search: opts.noWid ? "" : "?wid=hublab" });
  set("localStorage", { getItem: () => null, setItem: () => {} });
  set("window", {
    dispatchEvent: () => {},
    __rompLocalSend: () => {},
    __rompDialTerms: () => terms(),
    sessionStorage: { getItem: () => "" },
    parent: { postMessage: () => {} },
  });
  try {
    await fn(new FederationManager());
  } finally {
    Date.now = realNow;
    for (const [k, r] of Object.entries(saved)) { if (r.had) g[k] = r.v; else delete g[k]; }
  }
}

function qOf(url: string): URLSearchParams {
  return new URLSearchParams(url.split("?")[1] || "");
}

test("the first dial carries the page's terms: skeleton, delta, the bare-sid active, a wid-namespaced iid, no reconnect", async () => {
  await withManager((fm) => {
    fm.outbound({ type: "ready", proto: 2 });     // the page's proto, remembered for every remote socket
    fm.openRemote("TESTHOST", true);
    assert.equal(FakeWS.made.length, 1, "an up host is dialed at once");
    const q = qOf(FakeWS.made[0].url);
    assert.equal(q.get("app"), "chat");
    assert.equal(q.get("delta"), "1");
    assert.equal(q.get("skeleton"), "1", "the page's skeleton posture rides the remote dial");
    assert.equal(q.get("active"), SID, "the watched remote tab, stripped to its bare sid");
    assert.equal(q.get("iid"), "hublab:" + PAGE_IID, "the iid is namespaced by the hub's wid");
    assert.equal(q.get("reconnect"), null, "a FIRST dial is no reconnect");
    fm.conns.get("TESTHOST").closed = true;
  });
});

test("a redial that got a ready acked states reconnect=1&proto and the same iid, and posts NO ready on its open", async () => {
  await withManager((fm) => {
    fm.outbound({ type: "ready", proto: 2 });
    fm.openRemote("TESTHOST", true);
    const first = FakeWS.made[0];
    first.open();
    assert.deepEqual(first.sent, [{ type: "ready", proto: 2 }], "the first dial posts the page's ready");
    first.frame({ type: "caps" });                 // the remote's ready arm acked it → readyAcked latched
    first.readyState = 3;                           // the socket drops with no onclose timer (the throttled-tab case)
    clock += REMOTE_REDIAL_MS + 1000;
    fm.watchdog(clock);
    assert.equal(FakeWS.made.length, 2, "the watchdog dialed a fresh socket");
    const redial = FakeWS.made[1];
    const q = qOf(redial.url);
    assert.equal(q.get("reconnect"), "1", "a redial after a ready acked states reconnect");
    assert.equal(q.get("proto"), "2", "…with the page's last proto");
    assert.equal(q.get("iid"), "hublab:" + PAGE_IID, "the SAME namespaced iid, so the remote retires the twin");
    assert.equal(q.get("active"), SID, "the watched tab still rides the redial");
    redial.open();
    assert.deepEqual(redial.sent, [], "a REDIAL posts NO ready: its reconnect=1 IS the handshake, and a ready would clear the diet");
    fm.conns.get("TESTHOST").closed = true;
  });
});

test("a redial that never got a ready acked dials as a FIRST dial (no reconnect) and posts a ready", async () => {
  await withManager((fm) => {
    fm.outbound({ type: "ready", proto: 2 });
    fm.openRemote("TESTHOST", true);
    const first = FakeWS.made[0];
    first.open();                                  // ready posted, but NO caps frame ever comes: never acked
    first.readyState = 3;
    clock += REMOTE_REDIAL_MS + 1000;
    fm.watchdog(clock);
    const redial = FakeWS.made[1];
    assert.equal(qOf(redial.url).get("reconnect"), null, "no ready acked → dial fresh, the remote holds nothing to reconnect to");
    redial.open();
    assert.deepEqual(redial.sent, [{ type: "ready", proto: 2 }], "…so this dial posts a ready, like any first dial");
    fm.conns.get("TESTHOST").closed = true;
  });
});

test("with no wid the remote iid is namespaced by a stable per-page fallback, never bare", async () => {
  await withManager((fm) => {
    fm.openRemote("TESTHOST", true);
    const iid = qOf(FakeWS.made[0].url).get("iid") || "";
    assert.notEqual(iid, PAGE_IID, "never the bare page iid (it would retire the remote's own local page's socket)");
    assert.ok(iid.startsWith("hub-") && iid.endsWith(":" + PAGE_IID), "namespaced by a per-page fallback: " + iid);
    fm.conns.get("TESTHOST").closed = true;
  }, { noWid: true });
});

test("moving the active off a remote host sends that host an activeTab clear, so it stops building the departed tab first", async () => {
  await withManager((fm) => {
    fm.openRemote("TESTHOST", true);
    const ws = FakeWS.made[0];
    ws.open();
    fm.outbound({ type: "activeTab", id: "TESTHOST:" + SID, nonce: 1 });   // watching the remote tab
    fm.outbound({ type: "activeTab", id: LOCAL_SID, nonce: 2 });           // …then switch to a LOCAL tab
    const toHost = ws.sent.filter((m) => m && m.type === "activeTab");
    assert.deepEqual(toHost.map((m) => m.id), [SID, ""], "the host got the bare-sid focus, then a clear when it left");
    fm.conns.get("TESTHOST").closed = true;
  });
});
