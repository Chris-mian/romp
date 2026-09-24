// The arrangement is the KERNEL'S to keep, and it follows the viewer across their devices (the user
// 2026-09-23). This file executes the storage + migration half of view-order.ts; view-order.test.ts
// executes the layering rule it feeds, and federation-shared-order.test.ts drives two viewers through a
// manager against one kernel. SYNTHETIC ids only.
//
// The 2026-07-31 ruling (commit e9870995) split in two here and only one half moved. Its technical claim
// still holds and is pinned below: the ARRANGEMENT is computed in the browser over every attached host at
// once, which no kernel can do. Its preference — that two machines reading the same sessions each keep
// their own order — is what reverses: the finished list goes to the kernel as opaque data, and every
// viewer of that kernel reads it.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import {
  adoptSharedOrder, applyViewOrder, hearSharedOrder, mergeOrder, readViewOrder, setViewOrderPublisher, viewOrderPublisher,
  viewOrderToPublish, writeViewOrder,
  VIEW_ORDER_EVENT, VIEW_ORDER_KEY, VIEW_ORDER_PENDING_KEY, VIEW_ORDER_SHARED_KEY,
} from "./view-order";

const A = "11111111-2222-4333-8444-000000000001";
const B = "11111111-2222-4333-8444-000000000002";
const FAR = "TESTHOST:11111111-2222-4333-8444-000000000003";

/** One browser: its own localStorage and its own window, with the publishes and the announcements it made
 *  recorded. Everything in this module is synchronous, so swapping the globals IS having two browsers. */
function inBrowser(fn: (b: { store: Map<string, string>; published: string[][]; announced: number }) => void,
                   seed: Record<string, unknown> = {}): void {
  const g: any = globalThis;
  const saved: Record<string, [boolean, unknown]> = {};
  for (const k of ["window", "localStorage"]) saved[k] = [k in g, g[k]];
  const store = new Map<string, string>();
  for (const [k, v] of Object.entries(seed)) store.set(k, JSON.stringify(v));
  const b = { store, published: [] as string[][], announced: 0 };
  g.localStorage = {
    getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
    setItem: (k: string, v: string) => { store.set(k, v); },
    removeItem: (k: string) => { store.delete(k); },
  };
  g.window = { dispatchEvent: (e: any) => { if (e && e.type === VIEW_ORDER_EVENT) b.announced++; return true; } };
  setViewOrderPublisher((o) => b.published.push(o.slice()));
  try { fn(b); } finally {
    setViewOrderPublisher(null);
    for (const k of Object.keys(saved)) { const [had, v] = saved[k]; if (had) g[k] = v; else delete g[k]; }
  }
}

const read = (b: { store: Map<string, string> }, key: string) => {
  const raw = b.store.get(key);
  return raw === undefined ? undefined : JSON.parse(raw);
};

// ── what the page shows ───────────────────────────────────────────────────────────────────────────
test("the kernel's arrangement is what the page reads, and the pre-move local key is the fallback", () => {
  inBrowser((b) => {
    assert.deepEqual(readViewOrder(), [B, A], "before the kernel's first frame: the order this browser had");
    adoptSharedOrder([A, FAR, B]);
    assert.deepEqual(readViewOrder(), [A, FAR, B], "once the kernel has spoken, its arrangement is the one");
    assert.deepEqual(read(b, VIEW_ORDER_KEY), [B, A], "and the local key is untouched — a revert is harmless");
  }, { [VIEW_ORDER_KEY]: [B, A] });
});

test("an EMPTY shared arrangement is a real answer, not a missing one", () => {
  // the viewer arranged nothing, or their last session went away: the page must not fall back through to
  // a local key from before the move and resurrect an order nobody asked for
  inBrowser(() => {
    adoptSharedOrder([]);
    assert.deepEqual(readViewOrder(), []);
    assert.deepEqual(applyViewOrder([A, B, FAR], readViewOrder()), [A, B, FAR], "…and stays the identity");
  }, { [VIEW_ORDER_KEY]: [B, A] });
});

test("no arrangement anywhere is the identity transform, exactly as before this change", () => {
  inBrowser(() => {
    assert.deepEqual(readViewOrder(), []);
    assert.deepEqual(applyViewOrder([A, B, FAR], readViewOrder()), [A, B, FAR]);
  });
});

// ── the migration ─────────────────────────────────────────────────────────────────────────────────
test("a browser with a local arrangement meeting a kernel with NONE publishes its own", () => {
  assert.deepEqual(viewOrderToPublish(false, [B, A]), [B, A], "nobody's existing order is lost in the move");
});

test("a kernel that HAS an arrangement wins, whatever this browser holds", () => {
  assert.equal(viewOrderToPublish(true, [B, A]), null);
  assert.equal(viewOrderToPublish(true, []), null);
});

test("a kernel with an EMPTY arrangement is not refilled from somebody's old local key", () => {
  // `stored` is the whole signal: an emptied arrangement is an answer, an absent one is a question
  assert.equal(viewOrderToPublish(true, [B, A]), null, "empty-but-stored stands");
  assert.equal(viewOrderToPublish(false, []), null, "nothing to publish either");
});

test("the migration leaves the local key in place, so reverting hands back the order they had", () => {
  inBrowser((b) => {
    // the kernel already has an arrangement (another device published first): it wins
    const mine = viewOrderToPublish(true, readViewOrder());
    assert.equal(mine, null);
    adoptSharedOrder([FAR, A, B]);
    assert.deepEqual(read(b, VIEW_ORDER_KEY), [B, A], "never rewritten");
    assert.deepEqual(read(b, VIEW_ORDER_SHARED_KEY), [FAR, A, B]);
  }, { [VIEW_ORDER_KEY]: [B, A] });
});

// ── publishing ────────────────────────────────────────────────────────────────────────────────────
test("a drag caches the arrangement, hands it to the kernel, and tells the other panes — once each", () => {
  inBrowser((b) => {
    writeViewOrder([FAR, A, B]);
    assert.deepEqual(b.published, [[FAR, A, B]], "the kernel gets the whole list, ids still host-prefixed");
    assert.deepEqual(read(b, VIEW_ORDER_SHARED_KEY), [FAR, A, B], "and this browser paints from it at once");
    assert.equal(b.announced, 1, "one CustomEvent: `storage` reaches only OTHER contexts");
    assert.equal(read(b, VIEW_ORDER_KEY), undefined, "the pre-move key is never written again");
  });
});

test("adopting an arrangement this browser already holds announces nothing", () => {
  // every viewer sees its own publish come back on the kernel's push; re-announcing it would claim a move
  // that did not happen, and the cards-move-on-new-information rule forbids exactly that
  inBrowser((b) => {
    assert.equal(adoptSharedOrder([A, B]), true);
    assert.equal(b.announced, 1);
    assert.equal(adoptSharedOrder([A, B]), false, "unchanged");
    assert.equal(b.announced, 1);
    assert.equal(adoptSharedOrder([B, A]), true, "a real change from another device does announce");
    assert.equal(b.announced, 2);
  });
});

test("adopting never publishes: only a gesture writes, or two viewers would echo forever", () => {
  inBrowser((b) => {
    adoptSharedOrder([A, B]);
    assert.deepEqual(b.published, []);
  });
});

test("non-strings never reach the kernel or the cache", () => {
  inBrowser((b) => {
    writeViewOrder([A, 7 as any, null as any, FAR]);
    assert.deepEqual(b.published, [[A, FAR]]);
    assert.deepEqual(read(b, VIEW_ORDER_SHARED_KEY), [A, FAR]);
  });
});

test("with no publisher at all the arrangement is this browser's alone — a page with no manager", () => {
  // a chat pane whose federation.js never came up refuses the drag outright (render.ts fedMissing); this
  // is the softer case, a surface that simply has nowhere to publish, and it must still not throw
  inBrowser((b) => {
    setViewOrderPublisher(null);
    assert.equal(viewOrderPublisher(), null);
    writeViewOrder([B, A]);
    assert.deepEqual(read(b, VIEW_ORDER_SHARED_KEY), [B, A]);
  });
});

test("the window slot federation.js publishes outranks a directly installed publisher", () => {
  // each pane bundle holds its own MODULE copy of view-order.ts, so the slot on the window is the only
  // channel that crosses them: a drag in the chat's bundle must reach the manager's socket, not a stale
  // publisher some other surface left installed
  inBrowser((b) => {
    const viaWindow: string[][] = [];
    (globalThis as any).window.__rompPublishViewOrder = (o: readonly string[]) => viaWindow.push(o.slice());
    writeViewOrder([A, FAR]);
    assert.deepEqual(viaWindow, [[A, FAR]]);
    assert.deepEqual(b.published, [], "the direct publisher is the fallback, not a second listener");
  });
});

// ── the half of the 2026-07-31 ruling that did NOT move ───────────────────────────────────────────
test("the list handed to the kernel interleaves hosts — the thing no kernel could have computed", () => {
  inBrowser((b) => {
    const seed = [A, B, FAR];                         // the per-host concatenation: local block, then TESTHOST's
    const dragged = applyViewOrder(seed, [A, FAR, B]);
    writeViewOrder(dragged);
    assert.deepEqual(b.published, [[A, FAR, B]],
      "a local session sits between two of the server's, and that whole list is what the kernel keeps");
  });
});

// ── the hearing gate (review find on #2062, 2026-09-23) ────────────────────────────────────────────────
// A page that has not heard the kernel's arrangement does not speak for it: a new device used to answer the
// connect push's strip by publishing the kernel's seed order over the arrangement on every other device.
const C = "11111111-2222-4333-8444-000000000004";
const D = "11111111-2222-4333-8444-000000000005";

test("mergeOrder: with nothing moved since the base, the kernel's arrangement stands exactly", () => {
  assert.deepEqual(mergeOrder([A, B, C], [A, B, C], [C, B, A]), [C, B, A]);
  assert.deepEqual(mergeOrder([], [], [C, A]), [C, A], "no drag at all");
});

test("mergeOrder: a moved id is put back beside the neighbour it was dropped next to, in the kernel's order", () => {
  // shown [A,B,C,D]; the user dropped B after C; meanwhile another device brought D to the front
  assert.deepEqual(mergeOrder([A, B, C, D], [A, C, B, D], [D, A, B, C]), [D, A, C, B]);
  // a move to the very front goes before its nearest unmoved follower
  assert.deepEqual(mergeOrder([A, B, C], [C, A, B], [B, A, C]), [B, C, A]);
});

test("mergeOrder: an id the base never showed is not attributed to the drag", () => {
  // a newcomer the page showed at the end AFTER the base was taken keeps the kernel's place (first), not the end
  assert.deepEqual(mergeOrder([A, B], [B, A, FAR], [FAR, A, B]), [FAR, B, A]);
});

test("mergeOrder: a dragged id the kernel's arrangement does not hold is still placed where it was dropped", () => {
  assert.deepEqual(mergeOrder([A, B, C], [B, A, C], [C, A]), [C, B, A]);
});

test("before the kernel's arrangement is heard, a drag is shown and kept pending — never published", () => {
  inBrowser((b) => {
    setViewOrderPublisher(null);                                    // not heard: no publisher on this page
    (globalThis as any).window.__rompShownOrder = () => [A, B, C];  // what the strip shows (federation.ts)
    writeViewOrder([B, A, C]);
    assert.deepEqual(b.published, []);
    assert.deepEqual(read(b, VIEW_ORDER_SHARED_KEY), [B, A, C], "the page shows the drag at once");
    assert.deepEqual(read(b, VIEW_ORDER_PENDING_KEY), [A, B, C], "measured from what the user was looking at");
    writeViewOrder([C, B, A]);
    assert.deepEqual(read(b, VIEW_ORDER_PENDING_KEY), [A, B, C], "a second drag keeps the first base: the pending change is every drag since");
  });
});

test("hearing a kernel that holds an arrangement: a cold page adopts it and publishes nothing", () => {
  inBrowser((b) => {
    setViewOrderPublisher(null);
    const sent: string[][] = [];
    let installed: unknown = null;
    const changed = hearSharedOrder([B, A], true, (o) => sent.push(o.slice()), (fn) => { installed = fn; });
    assert.equal(changed, true);
    assert.deepEqual(sent, [], "nothing published: the kernel's arrangement wins over an empty page");
    assert.deepEqual(readViewOrder(), [B, A]);
    assert.equal(typeof installed, "function", "…and only now does the page get its publisher");
  });
});

test("hearing lands a pending drag over the kernel's arrangement and publishes the merge once", () => {
  inBrowser((b) => {
    setViewOrderPublisher(null);
    (globalThis as any).window.__rompShownOrder = () => [A, B, C, D];
    writeViewOrder([A, C, B, D]);                                   // B dropped after C, unheard
    const sent: string[][] = [];
    hearSharedOrder([D, A, B, C], true, (o) => sent.push(o.slice()), () => {});
    assert.deepEqual(sent, [[D, A, C, B]], "the drag and the other device's move, together");
    assert.equal(read(b, VIEW_ORDER_PENDING_KEY), undefined, "consumed");
    assert.deepEqual(readViewOrder(), [D, A, C, B]);
  });
});

test("hearing a kernel that holds NONE still receives this browser's arrangement — the migration is unchanged", () => {
  inBrowser(() => {
    setViewOrderPublisher(null);
    const sent: string[][] = [];
    hearSharedOrder([], false, (o) => sent.push(o.slice()), () => {});
    assert.deepEqual(sent, [[B, A]], "the pre-move arrangement goes up");
  }, { [VIEW_ORDER_KEY]: [B, A] });
});
