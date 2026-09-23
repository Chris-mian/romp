// The merged tab order holds its synthetic re-emissions until the LOCAL kernel's strip is in the store (the vanishing
// tab, the user 2026-09-12): a fresh chat column's manager subscribes to the view-order storage event before the local
// kernel's first strip has been absorbed, and another pane's arrangement write in that window re-emitted the merged
// order over an EMPTY per-host store — `order: []`, flagged reemit — which the pane took as the board and reported its
// one member gone; the shell closed the column and the tab was in no column for fifteen seconds. The hold is the one
// emitMergedTimeline already applies to its own payload: the local arrival itself emits, so nothing is lost. A host's
// own FRESH push still emits (its ids are that kernel's current word). And the arrangement prune respects `live`: a
// strip that omits a live id (T258's shape) no longer drops it from the browser's arrangement to re-adopt it at the end.
// Executed against the real manager. Synthetic only (host TESTHOST, placeholder ids).
import { test } from "node:test";
import assert from "node:assert/strict";
import { FederationManager } from "./federation";
import { listenForFrames } from "./frame-listener";
import { VIEW_ORDER_KEY, VIEW_ORDER_SHARED_KEY } from "./view-order";

const A = "11111111-2222-3333-4444-555555555501", B = "11111111-2222-3333-4444-555555555502", C = "11111111-2222-3333-4444-555555555503";
const U = "99999999-8888-7777-6666-555555555555";
const tabs = (...ids: string[]) => ids.map((id) => ({ id, name: id.slice(-3) }));

function withManager(fn: (fm: any, emitted: any[], store: Map<string, string>) => void): void {
  const emitted: any[] = [];
  const store = new Map<string, string>();
  const g: any = globalThis;
  const hadWindow = "window" in g, prevWindow = g.window;
  const hadLS = "localStorage" in g, prevLS = g.localStorage;
  g.window = { dispatchEvent: (ev: any) => { if (ev && ev.data) emitted.push(ev.data); } };
  g.localStorage = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => { store.set(k, v); } };
  try { fn(new FederationManager(), emitted, store); } finally {
    if (hadWindow) g.window = prevWindow; else delete g.window;
    if (hadLS) g.localStorage = prevLS; else delete g.localStorage;
  }
}
const orders = (emitted: any[]) => emitted.filter((m) => m && m.type === "tabOrder");

test("a synthetic re-emission before the local kernel's strip emits no order; a remote host's fresh push emits; the local arrival emits, and re-emissions flow after it", () => {
  withManager((fm, emitted) => {
    fm.inbound("", { type: "viewOrder", order: [], stored: false });   // heard on this connection: the page may fold host reports into the arrangement (view-order.ts ViewOrderPublisher)
    fm.emitMergedOrder();                                            // a view-order storage event, a caps adoption, a closed fold, a host drop
    assert.deepEqual(orders(emitted), [], "an empty store is not the board: nothing is emitted");
    fm.inbound("TESTHOST", { type: "tabOrder", order: [U], tabs: tabs(U) });
    assert.equal(orders(emitted).length, 1, "a host's OWN push is its current word: emitted");
    assert.equal(orders(emitted)[0].freshHost, "TESTHOST");
    assert.deepEqual(orders(emitted)[0].order, ["TESTHOST:" + U]);
    fm.emitMergedOrder();
    assert.equal(orders(emitted).length, 1, "still held: the local kernel has not spoken");
    fm.inbound("", { type: "tabOrder", order: [A, B], tabs: tabs(A, B) });
    assert.equal(orders(emitted).length, 2, "the local arrival itself emits");
    assert.equal(orders(emitted)[1].freshHost, "");
    assert.deepEqual(orders(emitted)[1].order, ["TESTHOST:" + U, A, B], "every host's sessions, in the arrangement's order (the remote's arrival was adopted first)");
    fm.emitMergedOrder();
    assert.equal(orders(emitted).length, 3, "…and from then on re-emissions flow");
    assert.equal(orders(emitted)[2].reemit, true);
    assert.deepEqual(orders(emitted)[2].order, ["TESTHOST:" + U, A, B]);
  });
});

test("through start(): a view-order storage event on a fresh page (the window the vanishing tab fell into) hands the pane no tabOrder; after the local strip it does", () => {
  const g: any = globalThis;
  const saved: Record<string, [boolean, unknown]> = {};
  for (const k of ["window", "document", "localStorage", "setInterval", "fetch"]) saved[k] = [k in g, g[k]];
  const win: any = new EventTarget();
  win.__rompApp = "chat";
  const store = new Map<string, string>();
  g.window = win;
  g.document = Object.assign(new EventTarget(), { visibilityState: "visible" });
  g.localStorage = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => { store.set(k, v); } };
  g.setInterval = () => 0;
  g.fetch = () => new Promise(() => {});   // start()'s first /tunnels poll never answers here: a rejection files a crumb after the finally below restored the globals
  try {
    const fm: any = new FederationManager();
    fm.start();
    const got: any[] = [];
    listenForFrames((e: MessageEvent) => got.push(e.data));   // the bundle's registration: from here every emission reaches the pane
    store.set(VIEW_ORDER_KEY, JSON.stringify([A, B]));
    win.dispatchEvent(new Event("storage"));                   // another pane's arrangement write, before this page's kernel strip
    assert.deepEqual(orders(got), [], "no order reaches the pane: the store holds no host yet, and [] would read as the board");
    fm.inbound("", { type: "tabOrder", order: [A, B], tabs: tabs(A, B), live: [A, B] });
    assert.ok(orders(got).length >= 1, "the local strip lands");
    assert.deepEqual(orders(got).at(-1).order, [A, B]);
    const n = orders(got).length;
    win.dispatchEvent(new Event("storage"));
    assert.equal(orders(got).length, n + 1, "with the local strip in the store the re-emission is served");
    assert.equal(orders(got).at(-1).reemit, true);
  } finally {
    for (const k of Object.keys(saved)) { const [had, v] = saved[k]; if (had) g[k] = v; else delete g[k]; }
  }
});

test("the arrangement prune respects live: a strip omitting a live id (T258) keeps its slot instead of dropping it and re-adopting it at the end", () => {
  withManager((fm, emitted, store) => {
    fm.inbound("", { type: "viewOrder", order: [], stored: false });   // heard on this connection: the page may fold host reports into the arrangement (view-order.ts ViewOrderPublisher)
    fm.inbound("", { type: "tabOrder", order: [A, B, C], tabs: tabs(A, B, C), live: [A, B, C] });
    assert.deepEqual(JSON.parse(store.get(VIEW_ORDER_SHARED_KEY)!), [A, B, C], "the first report adopts every arrival");
    fm.inbound("", { type: "tabOrder", order: [A, C], tabs: tabs(A, C), live: [A, B, C] });   // B's transcript briefly unreadable: omitted, still live
    assert.deepEqual(JSON.parse(store.get(VIEW_ORDER_SHARED_KEY)!), [A, B, C], "a live id is not pruned from the arrangement");
    fm.inbound("", { type: "tabOrder", order: [A, B, C], tabs: tabs(A, B, C), live: [A, B, C] });
    assert.deepEqual(orders(emitted).at(-1).order, [A, B, C], "re-listed, B is where it was, not at the end of the strip");
    fm.inbound("", { type: "tabOrder", order: [A, C], tabs: tabs(A, C), live: [A, C] });   // B ended: omitted and no longer live
    assert.deepEqual(JSON.parse(store.get(VIEW_ORDER_SHARED_KEY)!), [A, C], "…while an id the host no longer lists nor affirms is pruned as before");
  });
});
