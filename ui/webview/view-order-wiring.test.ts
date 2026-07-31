// Where the viewer's order is READ and WRITTEN (the user 2026-07-31). view-order.test.ts executes the rule;
// this pins that all three surfaces actually go through it and that nothing writes order back to a kernel.
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
  assert.match(FED, /mergeHostFeeds\(this\.perHostFeed, this\.hostSeq, this\.view\(\)\)/);
  assert.match(FED, /mergeHostTimelines\(this\.perHostTl, this\.hostSeq, this\.view\(\)\)/);
});

test("a drag in any pane moves every pane, through both notification paths", () => {
  // `storage` fires only in OTHER same-origin contexts, so the writer needs its own event
  assert.match(FED, /w\.addEventListener\("storage", \(e: StorageEvent\) => \{ if \(!e\.key \|\| e\.key === VIEW_ORDER_KEY\) reorder\(\); \}\);/);
  assert.match(FED, /w\.addEventListener\(VIEW_ORDER_EVENT, reorder\);/);
  assert.match(FED, /const reorder = \(\) => \{ this\.emitMergedOrder\(\); this\.emitMergedFeed\(\); this\.emitMergedTimeline\(false\); \};/);
});

test("the chat strip's drag writes the BROWSER, not a kernel", () => {
  assert.match(RENDER, /function commitTabOrder\(\) \{\s*\n\s*writeViewOrder\(order\.slice\(\)\);\s*\n\s*\}/);
  assert.doesNotMatch(RENDER, /type: "reorderTabs"/,
    "a kernel can only record an order over its own sids — writing there is what blocked interleaving");
});

test("the timeline's lane drag writes the same store", () => {
  assert.match(BOOT, /__rompTimelineWriteOrder: \(order: unknown\) =>\s*\n\s*writeViewOrder\(/);
  assert.doesNotMatch(BOOT, /type: "writeOrder"/);
});

test("the stale arrangement self-cleans on the host's own report, not on a clock", () => {
  assert.match(FED, /const reporting = new Set\(Object\.keys\(this\.perHostOrder\)\);/);
  assert.match(FED, /if \(!reporting\.size\) return;/, "no report in hand → prune nothing");
  assert.match(FED, /const kept = pruneViewOrder\(cur, hostOf, reporting, live\);/);
  assert.match(FED, /if \(kept\.length !== cur\.length\) writeViewOrder\(kept\);/, "written only when it changed");
});
