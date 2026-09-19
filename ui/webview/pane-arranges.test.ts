// A page with no federation manager arranges its own tab strip (the user 2026-09-19: tabs in the VS Code
// panel never stayed where they were put). Since 2026-07-31 the viewer's order lives in the browser
// (view-order.ts) and federation.js applies it to every kernel tabOrder frame at its merge point; a page
// that never loads that layer consumed the kernel's SEED verbatim, so a drag there wrote the store
// (commitTabOrder) and the next push undid it. The pane now applies the stored arrangement itself at the
// one place it adopts the kernel's order — only on such a page: a page WITH the manager leaves it to the
// manager, and a page whose manager is MISSING (federationMissing) keeps showing the seed and refusing the
// drag. The predicate is pure and executed here; the wiring into applyTabOrder is a source pin (no jsdom
// for the chat render, the repo convention). SYNTHETIC ids only.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { paneArranges, federationMissing } from "./frame-listener";
import { applyViewOrder } from "./view-order";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const send = () => {};

test("the three page kinds: only the page with neither shim nor manager arranges for itself", () => {
  assert.equal(paneArranges({}), true, "a VS Code webview: no shim, no manager — nobody else will apply the arrangement");
  assert.equal(paneArranges({ __rompLocalSend: send, __rompFed: { inbound() {} } }), false, "a healthy kernel page: the manager applies it at its merge point");
  assert.equal(paneArranges({ __rompLocalSend: send }), false, "a kernel page whose manager never came up: federationMissing owns that state");
  assert.equal(federationMissing({ __rompLocalSend: send }), true, "…and does: the two predicates never both hold");
  assert.equal(paneArranges({ __rompFed: { inbound() {} } }), false, "a manager without the shim still applies it itself");
  assert.equal(paneArranges({ __rompLocalSend: "not a function" }), true, "the shim publishes a function; anything else is not the shim (federationMissing's rule, mirrored)");
});

test("what the pane runs per frame: a dragged order survives the kernel's seed push, a newcomer lands at the end", () => {
  // the kernel's seed is arrival order and never changes on its own; the drag wrote the FULL rendered order
  const seed = ["11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222", "33333333-3333-4333-8333-333333333333"];
  const dragged = [seed[2], seed[0], seed[1]];
  assert.deepEqual(applyViewOrder(seed, dragged), dragged, "the next seed push reads back as the drag left it");
  const newcomer = "44444444-4444-4444-8444-444444444444";
  assert.deepEqual(applyViewOrder([...seed, newcomer], dragged), [...dragged, newcomer], "a session that arrives later appends, as on the browser page");
  assert.deepEqual(applyViewOrder(seed, []), seed, "no drag yet: the seed, exactly as before this change");
  assert.deepEqual(applyViewOrder([seed[0], seed[2]], dragged), [seed[2], seed[0]], "a closed session drops out; the rest keep their arranged places");
});

test("applyTabOrder arranges the seed on such a page, before every rule that reads the frame", () => {
  // the ID SET is unchanged by the arrangement, so the omission teardown, the live keep and the reconcile below
  // it read the same ids they always did; only their order differs
  assert.match(RENDER, /const seed = Array\.isArray\(o\) \? o\.filter\(\(x: any\) => typeof x === "string"\) : \[\];\n(?:\s*\/\/[^\n]*\n)*\s*const kernelOrder = paneArranges\(window as any\) \? applyViewOrder\(seed, readViewOrder\(\)\) : seed;\n\s*ackClosingTabs\(kernelOrder, report\);/,
    "arranged once, at the adoption point, ahead of ackClosingTabs and the reconcile");
  assert.match(RENDER, /import \{ applyViewOrder, readViewOrder, writeViewOrder \} from "\.\/view-order";/, "the read and the write come from the one module");
  assert.match(RENDER, /import \{ listenForFrames, federationMissing, federationLoadEntry, fedRetryKey, paneArranges \} from "\.\/frame-listener";/);
  // the arrangement is re-read per frame, never cached (view-order-wiring.test.ts holds the manager to the same rule)
  assert.doesNotMatch(RENDER, /const viewOrder = readViewOrder\(\);/);
  // the write side is untouched: a drag still writes the browser's store and a page without its manager never writes
  assert.match(RENDER, /function commitTabOrder\(\) \{\n\s*if \(fedMissing\) return;[^\n]*\n\s*writeViewOrder\(order\.slice\(\)\);/);
});
