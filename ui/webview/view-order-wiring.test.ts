// Where the viewer's order is READ, WRITTEN and now KEPT. view-order.test.ts executes the layering rule and
// view-order-shared.test.ts the storage and migration; this pins that all three surfaces actually go through
// it, that nothing asks a KERNEL to order its own sids (the half of the 2026-07-31 ruling, commit e9870995,
// that did not move), and that the finished list reaches the local kernel whole so every viewer of it
// converges (the user 2026-09-23).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const p = (f: string) => path.resolve(process.cwd(), "..", "ui", "webview", f);
const FED = fs.readFileSync(p("federation.ts"), "utf8");
const RENDER = fs.readFileSync(p("render.ts"), "utf8");
const BOOT = fs.readFileSync(p("timeline-boot.ts"), "utf8");

test("all THREE surfaces arrange by the same stored order", () => {
  // chat tab strip, feed grouped-mode ranks, timeline lanes — they must agree or the dashboard reads in
  // three different orders at once
  assert.match(FED, /return applyViewOrder\(out, view\);/, "tab strip");
  assert.match(FED, /merged\.order = applyViewOrder\(merged\.order, view\);/, "feed groups");
  assert.match(FED, /merged\.sessions = applyViewOrderTo\(merged\.sessions, view, /, "timeline lanes");
});

test("the arrangement is re-read per emit, never cached", () => {
  // another PANE writes the same key when you drag a tab there; a cached copy would leave that pane's
  // surfaces arranged one way and this one's another until a reload
  assert.match(FED, /private view\(\): string\[\] \{\s*\n\s*return readViewOrder\(\);\s*\n\s*\}/);
  assert.match(FED, /mergeHostOrder\(this\.perHostOrder, this\.hostSeq, this\.view\(\)\)/);
  assert.match(FED, /mergeHostFeeds\(this\.perHostFeed, this\.hostSeq, this\.view\(\), dead, this\.perHostFeedAt, this\.hostsRead\)/);   // the sixth argument: whether the host list has been read (T404 round nine)
  assert.match(FED, /mergeHostTimelines\(this\.perHostTl, this\.hostSeq, this\.view\(\)\)/);
});

test("a drag in any pane moves every pane, through both notification paths", () => {
  // `storage` fires only in OTHER same-origin contexts, so the writer needs its own event. Both keys: the
  // kernel's arrangement as this browser caches it, and the pre-move local key a browser still reads until
  // its kernel serves one.
  assert.match(FED, /w\.addEventListener\("storage", \(e: StorageEvent\) => \{ if \(!e\.key \|\| e\.key === VIEW_ORDER_SHARED_KEY \|\| e\.key === VIEW_ORDER_KEY\) reorder\(\); \}\);/);
  assert.match(FED, /w\.addEventListener\(VIEW_ORDER_EVENT, reorder\);/);
  assert.match(FED, /const reorder = \(\) => \{ this\.emitMergedOrder\(\); this\.emitMergedFeed\(\); this\.emitMergedTimeline\(false\); \};/);
});

test("…and a drag in any pane reaches the KERNEL, through the one window slot that crosses the bundles", () => {
  // federation.ts is never imported into a pane bundle (federation-single-instance.test.ts), so each bundle
  // holds its own module copy of view-order.ts: a slot on the window is the only channel between them, the
  // way __rompFed and __rompWriteOrder already are.
  assert.match(FED, /w\.__rompPublishViewOrder = \(order: readonly string\[\]\) => this\.outbound\(\{ type: "setViewOrder", order: order\.slice\(\) \}\);/);
  assert.match(FED, /if \(msg\.type === "setViewOrder"\) return \[\{ host: LOCAL, msg \}\];/,
    "the whole list goes to the local kernel; splitting it by host is the shape the 2026-07-31 ruling ruled out");
});

test("the kernel's arrangement is taken from the LOCAL kernel only, and never handed on to the panes", () => {
  // a remote kernel's store belongs to whoever sits in front of THAT machine; taking it would let one
  // viewer's drag rearrange another's. The panes read the arrangement through the merged re-emits, as ever.
  assert.match(FED, /if \(m && m\.type === "viewOrder"\) \{\n\s*if \(host !== LOCAL\) return;/);
  assert.match(FED, /const mine = viewOrderToPublish\(m\.stored === true, readViewOrder\(\)\);\n\s*if \(mine\) writeViewOrder\(mine\);[^\n]*\n\s*else adoptSharedOrder\(served\);/,
    "the migration is one decision, shared with the manager-less page");
});

test("the chat strip's drag writes the arrangement, never a per-kernel order op", () => {
  assert.match(RENDER, /function commitTabOrder\(\) \{\s*\n\s*if \(fedMissing\) return;[^\n]*\n\s*writeViewOrder\(order\.slice\(\)\);\s*\n\s*\}/);   // the guard: a page without its manager never writes (federation-missing.test.ts, 2026-09-10)
  assert.doesNotMatch(RENDER, /type: "reorderTabs"/,
    "a kernel can only record an order over its own sids — writing there is what blocked interleaving");
});

test("the timeline's lane drag writes the same store", () => {
  assert.match(BOOT, /__rompTimelineWriteOrder: \(order: unknown\) =>\s*\n\s*writeViewOrder\(/);
  assert.doesNotMatch(BOOT, /type: "writeOrder"/);
  // …and the VS Code timeline, which has no federation manager to publish the window slot, hands the
  // finished list to the kernel through its own host pipe
  assert.match(BOOT, /setViewOrderPublisher\(\(order\) => post\(\{ type: "setViewOrder", order: order\.slice\(\) \}\)\);/);
});

test("a pane answers another pane's drag by re-emitting, never by rewriting the arrangement", () => {
  // The audited failure (the user 2026-08-02): dragging the last tab up between two others permuted the
  // strip and reverted it in the same second, twice per attempt, so it read as a drag that never took.
  // Every revert arrived through the `storage` listener — another context answering the write by running
  // its own gc, which prunes ids ITS session lists don't name and so dropped the tab that had just moved
  // (the newest tab is the one a stale list is likeliest to be missing). An arrangement is not evidence
  // about what exists; only a host's own report is, and that is the one caller allowed to touch the store.
  assert.match(FED, /this\.absorbHostReport\(host, prevOrder, prevTabs\);\s+\/\/ a host just reported/,
    "inbound tabOrder is the one store-mutating moment");
  // (the signature carries provenance since T233 — fresh/host-driven vs synthetic re-emit — but every
  // caller still re-emits from the store, never rewrites it)
  // (…and holds a synthetic re-emission until the local kernel's strip is in the store — the vanishing tab, 2026-09-12;
  // federation-order-hold.test.ts — still without a write: the shell's pending list, the hold, then the merge)
  assert.match(FED, /private emitMergedOrder\(fresh = false, freshHost: string = LOCAL\): void \{\s*\n\s*this\.publishPending\(\);[^\n]*\n(?:\s*\/\/[^\n]*\n)*\s*if \(!fresh && !\(LOCAL in this\.perHostOrder\)\) return;\s*\n\s*const order = mergeHostOrder/,
    "every other caller — both drag paths included — re-emits without touching the stored order");
  assert.doesNotMatch(FED, /private gcView|this\.gcView/,
    "the old gc-on-emit hook is gone, folded into absorbHostReport");
});

test("the host's report heals churn, prunes the gone, and adopts arrivals — one conditional write", () => {
  // heal: a /clear relaunch keeps its slot (the kernel's own name inheritance, mirrored browser-side);
  // prune: the old gcView rule, unchanged — event-based, detached hosts left entirely alone;
  // adopt: a NEW session lands at the end of the WHOLE strip, where its provisional tab already
  // rendered, not at the end of its host's block mid-strip (the user 2026-08-10).
  assert.match(FED, /const healed = healOrder\(cur, churnSwaps\(prevOrder, names\(prevTabs\),/);
  assert.match(FED, /const reporting = new Set\(Object\.keys\(this\.perHostOrder\)\);/);
  assert.match(FED, /const next = adoptArrivals\(pruneViewOrder\(healed, hostOf, reporting, live\), seed\);/);
  assert.match(FED, /if \(next\.length !== cur\.length \|\| next\.some\(\(id, i\) => id !== cur\[i\]\)\) writeViewOrder\(next\);/,
    "written only when it actually changed");
});
