// T233 (the user 2026-09-03): a kernel's `closed` frame folds the session out of the federation manager's
// STORED per-host slices, so no synthetic re-emit can resurrect it.
//
// The false "Couldn't close X — romp still has it open" toast: the kernel killed the session within the
// same second and sent `closed`, but the manager's perHostOrder/perHostTabs for that host were updated
// ONLY by the host's next inbound tabOrder push (one pusher cycle, 20-40s on a loaded box). In between,
// every re-emit from the store — a view-order storage event, VIEW_ORDER_EVENT, a host attach or drop —
// re-served the dead id; past the chat's 15s backstop that read as a refused close. Executed against
// the real manager. Synthetic only (host TESTHOST, placeholder ids).
import { test } from "node:test";
import assert from "node:assert/strict";
import { FederationManager } from "./federation";

const U = "11111111-2222-3333-4444-555555555555";
const V = "99999999-8888-7777-6666-555555555555";

function withManager(fn: (fm: any, emitted: any[]) => void): void {
  const emitted: any[] = [];
  const store = new Map<string, string>();
  const g: any = globalThis;
  const hadWindow = "window" in g, prevWindow = g.window;
  const hadLS = "localStorage" in g, prevLS = g.localStorage;
  g.window = { dispatchEvent: (ev: any) => { if (ev && ev.data) emitted.push(ev.data); } };
  g.localStorage = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => { store.set(k, v); } };
  try { fn(new FederationManager(), emitted); } finally {
    if (hadWindow) g.window = prevWindow; else delete g.window;
    if (hadLS) g.localStorage = prevLS; else delete g.localStorage;
  }
}
const orders = (emitted: any[]) => emitted.filter((m) => m && m.type === "tabOrder");
const last = (emitted: any[]) => orders(emitted).pop()!;

test("closed(H, S) folds S out of H's stored slices; a storage-triggered re-emit no longer carries it", () => {
  withManager((fm, emitted) => {
    fm.inbound("", { type: "tabOrder", order: ["a"], tabs: [{ id: "a", name: "web" }] });
    fm.inbound("TESTHOST", { type: "tabOrder", order: [U, V], tabs: [{ id: U, name: "api" }, { id: V, name: "tests" }] });
    assert.deepEqual(last(emitted).order, ["a", "TESTHOST:" + U, "TESTHOST:" + V]);
    // the kill: TESTHOST's kernel sends `closed` for U (arrives bare, prefixed on the way in)
    fm.inbound("TESTHOST", { type: "closed", id: U });
    // BEFORE the fix the store still listed U here, and this re-emit resurrected it
    fm.emitMergedOrder();                                           // what a view-order storage event / attach / drop does
    assert.deepEqual(last(emitted).order, ["a", "TESTHOST:" + V], "the dead id is gone from every later re-emit");
    assert.deepEqual(last(emitted).tabs.map((t: any) => t.id), ["a", "TESTHOST:" + V], "…and from the tabs meta");
    assert.deepEqual(fm.perHostOrder["TESTHOST"], ["TESTHOST:" + V]);
    assert.equal(fm.perHostSids["TESTHOST"]?.has("TESTHOST:" + U) ?? false, false);
  });
});

test("the closed fold hands the pane its teardown frame first, then a merged order without the id — flagged synthetic", () => {
  withManager((fm, emitted) => {
    fm.inbound("", { type: "tabOrder", order: ["a"], tabs: [{ id: "a", name: "web" }] });
    fm.inbound("TESTHOST", { type: "tabOrder", order: [U], tabs: [{ id: U, name: "api" }] });
    const n = emitted.length;
    fm.inbound("TESTHOST", { type: "closed", id: U });
    const after = emitted.slice(n);
    assert.equal(after[0].type, "closed", "the pane's own teardown (dismissSession) runs first");
    assert.equal(after[0].id, "TESTHOST:" + U);
    assert.equal(after[1].type, "tabOrder");
    assert.deepEqual(after[1].order, ["a"], "the merged order confirms the close by ABSENCE at once");
    assert.equal(after[1].reemit, true, "…but it is a re-emit from the store, so it can never call a close refused");
    assert.equal("freshHost" in after[1], false);
  });
});

test("provenance: a host's own tabOrder push emits FRESH and names the host; every other emission says reemit", () => {
  withManager((fm, emitted) => {
    fm.inbound("", { type: "tabOrder", order: ["a"], tabs: [{ id: "a", name: "web" }] });
    let o = last(emitted);
    assert.equal(o.freshHost, "", "the LOCAL kernel's push: fresh, host ''");
    assert.equal("reemit" in o, false);
    fm.inbound("TESTHOST", { type: "tabOrder", order: [U], tabs: [{ id: U, name: "api" }] });
    o = last(emitted);
    assert.equal(o.freshHost, "TESTHOST", "a remote host's push names ITSELF — only its ids are its current word");
    fm.emitMergedOrder();                                           // storage / attach / drop path
    o = last(emitted);
    assert.equal(o.reemit, true);
    assert.equal("freshHost" in o, false);
  });
});

test("a `closed` for an id the store never held is harmless — passes through, re-emits unchanged", () => {
  withManager((fm, emitted) => {
    fm.inbound("", { type: "tabOrder", order: ["a"], tabs: [{ id: "a", name: "web" }] });
    fm.inbound("", { type: "closed", id: "never-listed" });
    assert.deepEqual(last(emitted).order, ["a"]);
    assert.ok(emitted.some((m) => m.type === "closed" && m.id === "never-listed"), "the pane still hears it");
  });
});
