// TWO VIEWERS OF ONE KERNEL CONVERGE ON ONE ARRANGEMENT (the user 2026-09-23, whose phone and desktop
// showed the same sessions in different orders with no way to reconcile them).
//
// Executed against the real FederationManager, twice over: a browser here is its own `window` and its own
// localStorage, and everything on this path is synchronous, so swapping the globals IS having two of them.
// The fake kernel in the middle does exactly what kernel.py's store does — keeps the list it is handed,
// says whether it has one at all, and pushes a CHANGE to every client — so what is pinned is the protocol
// between the two, not a mock of it.
//
// The half of the 2026-07-31 ruling (commit e9870995) that does NOT move is pinned here too: the merged
// order still interleaves hosts, because the list is computed in the browser over every attached kernel
// and handed over whole. The kernel stores host-prefixed ids it never reads.
//
// SYNTHETIC only: the notes-api demo world, host TESTHOST, placeholder uuids.
import { test } from "node:test";
import assert from "node:assert/strict";
import { FederationManager } from "./federation";
import { VIEW_ORDER_KEY, VIEW_ORDER_SHARED_KEY, writeViewOrder } from "./view-order";

const WEB = "11111111-2222-4333-8444-000000000001";   // two sessions on the kernel the browsers talk to
const API = "11111111-2222-4333-8444-000000000002";
const TESTS = "11111111-2222-4333-8444-000000000003"; // …and one on a machine attached to it
const R_TESTS = "TESTHOST:" + TESTS;

const tabs = (...ids: string[]) => ids.map((id) => ({ id, name: id.slice(-3) }));

/** The kernel's view-order store and its push, as kernel.py implements them. */
function fakeKernel() {
  const k = {
    order: [] as string[],
    stored: false,
    viewers: [] as Viewer[],
    writes: 0,
    frame() { return { type: "viewOrder", order: k.order.slice(), stored: k.stored }; },
    /** setViewOrder: keep it whole and opaque, and push only when it CHANGED (kernel.py _write_view_order) */
    post(order: readonly string[]) {
      k.writes++;
      const next = order.filter((x) => typeof x === "string");
      if (k.stored && k.order.length === next.length && k.order.every((id, i) => id === next[i])) return;
      k.order = next.slice();
      k.stored = true;
      for (const v of k.viewers) if (v.online) v.deliver(k.frame());   // a viewer whose socket is down hears nothing
    },
    /** the connect push: one viewer's `ready` is answered with the arrangement this kernel holds */
    connect(v: Viewer) { v.deliver(k.frame()); },
  };
  return k;
}

interface Viewer {
  name: string;
  store: Map<string, string>;
  fm: any;
  emitted: any[];
  online: boolean;
  queued: string[][];   // setViewOrder posts made while the socket was down: the shim queues them and flushes on reopen
  as<T>(fn: () => T): T;
  deliver(frame: any): void;
  order(): string[] | undefined;
}

function makeViewer(name: string, k: ReturnType<typeof fakeKernel>, seed: Record<string, unknown> = {}): Viewer {
  const g: any = globalThis;
  const store = new Map<string, string>();
  for (const [key, val] of Object.entries(seed)) store.set(key, JSON.stringify(val));
  const emitted: any[] = [];
  const win: any = new EventTarget();
  win.__rompApp = "chat";
  const localStorage = {
    getItem: (key: string) => (store.has(key) ? store.get(key)! : null),
    setItem: (key: string, val: string) => { store.set(key, val); },
    removeItem: (key: string) => { store.delete(key); },
  };
  const v: Viewer = {
    name, store, emitted, fm: null, online: true, queued: [],
    // Every entry point runs with THIS browser's globals installed; nested calls restore what they found,
    // so one viewer's kernel push landing inside another's drag (which is what convergence IS) nests safely.
    as<T>(fn: () => T): T {
      const saved: Record<string, [boolean, unknown]> = {};
      for (const key of ["window", "document", "localStorage", "setInterval", "fetch"]) saved[key] = [key in g, g[key]];
      g.window = win;
      g.document = Object.assign(new EventTarget(), { visibilityState: "visible" });
      g.localStorage = localStorage;
      g.setInterval = () => 0;
      g.fetch = () => new Promise(() => {});   // start()'s first /tunnels poll never answers in a node test
      try { return fn(); } finally {
        for (const key of Object.keys(saved)) { const [had, val] = saved[key]; if (had) g[key] = val; else delete g[key]; }
      }
    },
    deliver(frame: any) { v.as(() => v.fm.inbound("", frame)); },
    order() { const raw = store.get(VIEW_ORDER_SHARED_KEY); return raw === undefined ? undefined : JSON.parse(raw); },
  };
  v.as(() => {
    const fm: any = new FederationManager();
    fm.onFrame((e: MessageEvent) => emitted.push(e.data));
    fm.start();
    // the socket, replaced by the kernel above: setViewOrder is the only thing this test sends
    fm.outbound = (m: any) => { if (m && m.type === "setViewOrder") { if (v.online) k.post(m.order); else v.queued.push(m.order); } };
    v.fm = fm;
  });
  k.viewers.push(v);
  return v;
}

const merged = (v: Viewer) => v.emitted.filter((m) => m && m.type === "tabOrder").at(-1);

/** A drag, as a pane bundle's commitTabOrder makes one: view-order.ts writeViewOrder in this browser. */
const drag = (v: Viewer, order: string[]) => v.as(() => writeViewOrder(order));
const strip = (v: Viewer, ...ids: string[]) => v.as(() => v.fm.inbound("", { type: "tabOrder", order: ids, tabs: tabs(...ids), live: ids }));
/** The socket drops: the shim fires romp:wsdown on the page, and the kernel stops reaching it. */
const drop = (v: Viewer) => { v.online = false; v.as(() => (globalThis as any).window.dispatchEvent(new Event("romp:wsdown"))); };
/** It comes back, in the order the real page sees it: the shim flushes what it queued, enqueues its `wsup` frame,
 *  and the kernel serves the connect push — the strip FIRST (`strip`), then the viewOrder frame. */
const reconnect = (k: ReturnType<typeof fakeKernel>, v: Viewer, ...ids: string[]) => {
  v.online = true;
  for (const o of v.queued.splice(0)) k.post(o);
  v.deliver({ type: "wsup" });
  strip(v, ...ids);
  k.connect(v);
};

function world(fn: (k: ReturnType<typeof fakeKernel>, mk: (name: string, seed?: Record<string, unknown>) => Viewer) => void): void {
  const k = fakeKernel();
  fn(k, (name, seed) => makeViewer(name, k, seed));
}

// ── the headline ─────────────────────────────────────────────────────────────────────────────────
test("a drag on one device reaches the other, with no reload and nothing polling", () => {
  world((k, mk) => {
    const desktop = mk("desktop"), phone = mk("phone");
    for (const v of [desktop, phone]) {
      k.connect(v);
      v.as(() => v.fm.inbound("", { type: "tabOrder", order: [WEB, API], tabs: tabs(WEB, API), live: [WEB, API] }));
    }
    assert.deepEqual(merged(desktop).order, [WEB, API]);
    assert.deepEqual(merged(phone).order, [WEB, API]);

    // the desktop drags api in front of web. The window slot is how a pane bundle's commitTabOrder
    // reaches this manager: each bundle holds its own module copy of view-order.ts, so the slot is the
    // one channel across them (federation.ts start, view-order.ts viewOrderPublisher).
    desktop.as(() => (globalThis as any).window.__rompPublishViewOrder([API, WEB]));

    assert.deepEqual(k.order, [API, WEB], "the kernel keeps the finished list");
    assert.deepEqual(phone.order(), [API, WEB], "…and the phone has it, off the kernel's push");
    assert.deepEqual(merged(phone).order, [API, WEB], "the phone's strip is re-emitted in the new order");
    assert.deepEqual(merged(desktop).order, [API, WEB]);
  });
});

test("a viewer that joins later is served the arrangement on connect", () => {
  world((k, mk) => {
    const desktop = mk("desktop");
    k.connect(desktop);
    desktop.as(() => desktop.fm.inbound("", { type: "tabOrder", order: [WEB, API], tabs: tabs(WEB, API), live: [WEB, API] }));
    desktop.as(() => (globalThis as any).window.__rompPublishViewOrder([API, WEB]));

    const laptop = mk("laptop");
    k.connect(laptop);
    laptop.as(() => laptop.fm.inbound("", { type: "tabOrder", order: [WEB, API], tabs: tabs(WEB, API), live: [WEB, API] }));
    assert.deepEqual(merged(laptop).order, [API, WEB], "it reads the arrangement from its first frame");
  });
});

// ── the migration ────────────────────────────────────────────────────────────────────────────────
test("a browser carrying a local arrangement into a kernel with none publishes it, and the others take it", () => {
  world((k, mk) => {
    const desktop = mk("desktop", { [VIEW_ORDER_KEY]: [API, WEB] });   // dragged before the move
    const phone = mk("phone");
    k.connect(phone);
    k.connect(desktop);
    assert.deepEqual(k.order, [API, WEB], "the upgrading browser's order survives the move");
    assert.deepEqual(phone.order(), [API, WEB], "and every other viewer converges on it");
    for (const v of [desktop, phone]) v.as(() => v.fm.inbound("", { type: "tabOrder", order: [WEB, API], tabs: tabs(WEB, API), live: [WEB, API] }));
    assert.deepEqual(merged(phone).order, [API, WEB]);
  });
});

test("a kernel that already has an arrangement wins, and the local key is left in place", () => {
  world((k, mk) => {
    k.post([WEB, API]);                                              // another device published first
    const desktop = mk("desktop", { [VIEW_ORDER_KEY]: [API, WEB] });
    k.connect(desktop);
    assert.deepEqual(k.order, [WEB, API], "the kernel's stands");
    assert.deepEqual(desktop.order(), [WEB, API]);
    assert.deepEqual(JSON.parse(desktop.store.get(VIEW_ORDER_KEY)!), [API, WEB],
      "the pre-move key is never rewritten — reverting this change hands back the order they had");
  });
});

test("an empty arrangement stays the identity: nothing published, nothing moved", () => {
  world((k, mk) => {
    const desktop = mk("desktop");
    k.connect(desktop);
    assert.equal(k.writes, 0, "nothing to publish");
    assert.equal(k.stored, false);
    desktop.as(() => desktop.fm.inbound("", { type: "tabOrder", order: [WEB, API, TESTS], tabs: tabs(WEB, API, TESTS), live: [WEB, API, TESTS] }));
    assert.deepEqual(merged(desktop).order, [WEB, API, TESTS], "the kernel's seed order, unchanged");
  });
});

test("a viewer republishing the list it was just served pushes nothing back out", () => {
  world((k, mk) => {
    const desktop = mk("desktop"), phone = mk("phone");
    for (const v of [desktop, phone]) k.connect(v);
    desktop.as(() => (globalThis as any).window.__rompPublishViewOrder([API, WEB]));
    const before = k.writes;
    phone.as(() => (globalThis as any).window.__rompPublishViewOrder([API, WEB]));
    assert.equal(k.writes, before + 1, "the post is made…");
    assert.deepEqual(k.order, [API, WEB], "…and changes nothing, so no viewer is told anything moved");
  });
});

// ── the rules that must hold across the move ─────────────────────────────────────────────────────
test("arrivals still adopt at the END, once, and every viewer sees the newcomer in the same place", () => {
  world((k, mk) => {
    const desktop = mk("desktop"), phone = mk("phone");
    for (const v of [desktop, phone]) k.connect(v);
    for (const v of [desktop, phone]) v.as(() => v.fm.inbound("", { type: "tabOrder", order: [WEB, API], tabs: tabs(WEB, API), live: [WEB, API] }));
    desktop.as(() => (globalThis as any).window.__rompPublishViewOrder([API, WEB]));

    // a new session starts; both viewers hear the host's own report
    for (const v of [desktop, phone]) v.as(() => v.fm.inbound("", { type: "tabOrder", order: [WEB, API, TESTS], tabs: tabs(WEB, API, TESTS), live: [WEB, API, TESTS] }));
    assert.deepEqual(k.order, [API, WEB, TESTS], "appended at the end of the WHOLE strip, not its host's block");
    assert.deepEqual(merged(desktop).order, [API, WEB, TESTS]);
    assert.deepEqual(merged(phone).order, [API, WEB, TESTS], "…and in the same place on the other device");
  });
});

test("interleaved hosts survive the merge — the arrangement the kernel keeps is one no kernel could compute", () => {
  world((k, mk) => {
    const desktop = mk("desktop"), phone = mk("phone");
    for (const v of [desktop, phone]) {
      k.connect(v);
      v.as(() => {
        v.fm.inbound("TESTHOST", { type: "tabOrder", order: [TESTS], tabs: tabs(TESTS), live: [TESTS] });
        v.fm.inbound("", { type: "tabOrder", order: [WEB, API], tabs: tabs(WEB, API), live: [WEB, API] });
      });
    }
    // the seed is host-blocked (local first, then the attached machine); the drag puts a remote session
    // BETWEEN two local ones, which is the thing the browser-side list exists for
    desktop.as(() => (globalThis as any).window.__rompPublishViewOrder([WEB, R_TESTS, API]));
    assert.deepEqual(k.order, [WEB, R_TESTS, API], "the kernel keeps an id naming a machine it does not own");
    assert.deepEqual(merged(phone).order, [WEB, R_TESTS, API], "and the other device reads the interleave");

    // …and it holds across the next merge from each host, not just the emission that followed the drag
    for (const v of [desktop, phone]) {
      v.as(() => v.fm.inbound("", { type: "tabOrder", order: [WEB, API], tabs: tabs(WEB, API), live: [WEB, API] }));
      assert.deepEqual(merged(v).order, [WEB, R_TESTS, API], v.name + " after a local re-report");
      v.as(() => v.fm.inbound("TESTHOST", { type: "tabOrder", order: [TESTS], tabs: tabs(TESTS), live: [TESTS] }));
      assert.deepEqual(merged(v).order, [WEB, R_TESTS, API], v.name + " after the remote's re-report");
    }
  });
});

test("a REMOTE kernel's arrangement is ignored: it belongs to whoever sits in front of that machine", () => {
  world((k, mk) => {
    const desktop = mk("desktop");
    k.connect(desktop);
    desktop.as(() => desktop.fm.inbound("", { type: "tabOrder", order: [WEB, API], tabs: tabs(WEB, API), live: [WEB, API] }));
    desktop.as(() => (globalThis as any).window.__rompPublishViewOrder([API, WEB]));
    desktop.as(() => desktop.fm.inbound("TESTHOST", { type: "viewOrder", order: [WEB], stored: true }));
    assert.deepEqual(desktop.order(), [API, WEB], "untouched — one viewer's drag cannot rearrange another's");
  });
});

// ── the page speaks for the arrangement only once it has HEARD the kernel's (review find on #2062, 2026-09-23) ──
// The connect push serves the strip BEFORE the viewOrder frame. A page that published from boot answered that strip
// with whatever it held, and a new device or a cleared browser holds nothing: it adopted every session in the
// kernel's seed order and put THAT over the arrangement the user had made on every other device.
test("a cold browser connecting to a kernel that holds an arrangement adopts it and publishes NOTHING", () => {
  world((k, mk) => {
    k.post([API, WEB]);                               // the arrangement the user made on another device
    const writes = k.writes;
    const fresh = mk("new-phone");                    // no arrangement cached, no pre-move key: a new device
    strip(fresh, WEB, API);                           // the connect push's strip, in the kernel's SEED order, first…
    k.connect(fresh);                                 // …then the viewOrder frame
    assert.equal(k.writes, writes, "nothing published: the page had not heard the kernel's arrangement when the strip landed");
    assert.deepEqual(k.order, [API, WEB], "the arrangement on every other device is untouched");
    assert.deepEqual(fresh.order(), [API, WEB], "the new device adopted it");
    assert.deepEqual(merged(fresh).order, [API, WEB], "and shows it");
  });
});

test("a reconnect does not answer the new connection's strip with the copy it held before the drop", () => {
  world((k, mk) => {
    const desktop = mk("desktop"), phone = mk("phone");
    for (const v of [desktop, phone]) { strip(v, WEB, API); k.connect(v); }
    drop(desktop);
    drag(phone, [API, WEB]);                          // the phone rearranges while the desktop is away
    assert.deepEqual(k.order, [API, WEB]);
    reconnect(k, desktop, WEB, API, TESTS);           // …and a new session started meanwhile
    assert.deepEqual(k.order, [API, WEB, TESTS], "the phone's drag stands; the newcomer is adopted at the end, once heard");
    assert.deepEqual(merged(desktop).order, [API, WEB, TESTS]);
  });
});

test("a drag made while the socket was down lands OVER the kernel's arrangement, and another device's move stands", () => {
  world((k, mk) => {
    const desktop = mk("desktop"), phone = mk("phone");
    for (const v of [desktop, phone]) { strip(v, WEB, API, TESTS); k.connect(v); }
    drop(desktop);
    drag(phone, [TESTS, WEB, API]);                   // the phone brings tests to the front
    drag(desktop, [API, WEB, TESTS]);                 // offline, the desktop drags api in front of web
    assert.deepEqual(desktop.queued, [], "nothing queued to flush blind at the reopen");
    reconnect(k, desktop, WEB, API, TESTS);
    assert.deepEqual(k.order, [TESTS, API, WEB], "both moves: tests first (the phone), api before web (the desktop)");
    assert.deepEqual(phone.order(), [TESTS, API, WEB], "the phone took the merge off the kernel's push");
    assert.deepEqual(merged(desktop).order, [TESTS, API, WEB]);
  });
});

test("a cold browser's drag before it has heard is merged over the kernel's arrangement, not published blind", () => {
  world((k, mk) => {
    k.post([TESTS, WEB, API]);                        // another device's arrangement
    const fresh = mk("new-laptop");
    strip(fresh, WEB, API, TESTS);                    // the strip lands first, in seed order
    drag(fresh, [API, WEB, TESTS]);                   // …and the user drags api to the front before the frame arrives
    assert.deepEqual(k.order, [TESTS, WEB, API], "nothing published yet");
    k.connect(fresh);
    assert.deepEqual(k.order, [TESTS, API, WEB], "the drag lands (api before web) and the other device's order around it stands");
    assert.deepEqual(merged(fresh).order, [TESTS, API, WEB]);
  });
});

test("hearing another viewer's arrangement never prunes it against this page's own session list", () => {
  // Only a host's own report is evidence about what exists (the 2026-08-02 rule). A page whose list lags for a
  // moment (the phone has not had the strip that carries the new session yet) must adopt the desktop's publish,
  // not answer it with a pruned copy — two devices doing that re-prune each other's publish without end.
  world((k, mk) => {
    const desktop = mk("desktop"), phone = mk("phone");
    for (const v of [desktop, phone]) { strip(v, WEB, API); k.connect(v); }
    strip(desktop, WEB, API, TESTS);                  // only the desktop has heard about the new session so far
    const writes = k.writes;
    assert.deepEqual(k.order, [WEB, API, TESTS], "the desktop adopted the arrival and published it");
    assert.deepEqual(phone.order(), [WEB, API, TESTS], "the phone took it off the push");
    assert.equal(k.writes, writes, "…and published nothing back");
    strip(phone, WEB, API, TESTS);                    // its own strip catches up: nothing to change
    assert.equal(k.writes, writes);
  });
});
