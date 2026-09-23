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
import { VIEW_ORDER_KEY, VIEW_ORDER_SHARED_KEY } from "./view-order";

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
      for (const v of k.viewers) v.deliver(k.frame());
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
    name, store, emitted, fm: null,
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
    fm.outbound = (m: any) => { if (m && m.type === "setViewOrder") k.post(m.order); };
    v.fm = fm;
  });
  k.viewers.push(v);
  return v;
}

const merged = (v: Viewer) => v.emitted.filter((m) => m && m.type === "tabOrder").at(-1);

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
