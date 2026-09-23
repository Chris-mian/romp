// A tail element leaving the DOM — even for part of one frame — is on the record (T262j, the user 2026-09-08). The
// remaining snap lands at scrollHeight − clientHeight − h, the bubble's height, from any position, 93 ms after a
// land that took, with scrollHeight unchanged at the next read and NO tail-change row: a clamp against a transcript
// momentarily h px shorter WITHIN a frame. A ResizeObserver reports frame-end sizes and cannot see that; a
// MutationObserver on the active view's element (and on the live-ask host) sees every child removed at the tail,
// including one re-appended in the same task, so a "tailmut" row names what left, whether it came back, and the
// scroll height before (the last one the pane recorded) and after. Pure summary executed here; wiring pinned.
//
// The HONEST row (2026-09-23): the rows were read as proof that messages vanished, and they could not say so. A window slide
// or a re-render re-creates the same turn as a new element, which the classes alone read exactly like a turn that left; the
// lists were clipped to four with no lengths; and `reAdded` compared the pane's per-record wrappers, never the node, so it
// read false for every real batch. Now each node carries its unit's uuid, the row carries the full lengths, `gone` names
// the uuids that came back nowhere, `slide` marks a batch that touched the top spacer, and a re-add is judged by the node.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { summarizeTailMutations, tailMutRow } from "./scroll-write";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const SID = "11111111-2222-4333-8444-000000000201";
const U1 = "11111111-2222-4333-8444-0000000002a1", U2 = "11111111-2222-4333-8444-0000000002a2";
const n = (cls: string, uuid = "") => ({ cls, uuid });

test("a removal at the END of the container is a tail removal; a node removed and re-added in the same task is re-added", () => {
  const bubble = n("turn turn-queued");
  const s = summarizeTailMutations([
    { removed: [bubble], added: [], atEnd: true },
    { removed: [], added: [bubble], atEnd: true },
  ]);
  assert.deepEqual(s, { removedTail: ["turn turn-queued"], addedTail: ["turn turn-queued"], reAdded: true, removedUuids: [""], addedUuids: [""], gone: [], slide: false });
});

test("a removal in the MIDDLE is not a tail removal; a removal with a different node appended is not a re-add", () => {
  const a = n("turn turn-assistant"), b = n("turn turn-tool");
  assert.equal(summarizeTailMutations([{ removed: [a], added: [], atEnd: false }]), null, "nothing left the tail");
  assert.deepEqual(summarizeTailMutations([{ removed: [a], added: [b], atEnd: true }]),
                   { removedTail: ["turn turn-assistant"], addedTail: ["turn turn-tool"], reAdded: false, removedUuids: [""], addedUuids: [""], gone: [], slide: false });
  assert.equal(summarizeTailMutations([{ removed: [], added: [b], atEnd: true }]), null, "an append alone is the append path's business");
});

test("the SAME node under a fresh wrapper per record is a re-add: identity is the node, not the wrapper", () => {
  // the pane maps every MutationRecord's nodes to new objects, so the wrapper a removal carries is never the one its re-add
  // carries; comparing wrappers read false for every real batch, and the row said nothing ever came back
  const node = {};
  const s = summarizeTailMutations([
    { removed: [{ cls: "turn turn-queued", uuid: "", node }], added: [], atEnd: true },
    { removed: [], added: [{ cls: "turn turn-queued", uuid: "", node }], atEnd: true },
  ]);
  assert.equal(s!.reAdded, true);
});

test("a turn re-created as a NEW element with the same uuid did not vanish; one whose uuid came back nowhere did", () => {
  // a re-render (the append path repainting the last turn from its first changed event): a new element, the same uuid
  const rerender = summarizeTailMutations([
    { removed: [{ cls: "turn turn-assistant", uuid: U1, node: {} }], added: [], atEnd: true },
    { removed: [], added: [{ cls: "turn turn-assistant", uuid: U1, node: {} }], atEnd: true },
  ]);
  assert.equal(rerender!.reAdded, false, "not the same node");
  assert.deepEqual(rerender!.gone, [], "…and not gone: its uuid came back");
  assert.deepEqual(rerender!.removedUuids, [U1]);
  assert.deepEqual(rerender!.addedUuids, [U1]);
  // a real vanish: the user turn left and only the assistant turn came back
  const vanish = summarizeTailMutations([
    { removed: [{ cls: "turn turn-user", uuid: U2, node: {} }, { cls: "turn turn-assistant", uuid: U1, node: {} }], added: [], atEnd: true },
    { removed: [], added: [{ cls: "turn turn-assistant", uuid: U1, node: {} }], atEnd: true },
  ]);
  assert.deepEqual(vanish!.gone, [U2]);
  // a uuid re-inserted anywhere in the batch (not at the end: an in-place replace) came back too
  const moved = summarizeTailMutations([
    { removed: [{ cls: "turn turn-user", uuid: U2, node: {} }], added: [], atEnd: true },
    { removed: [], added: [{ cls: "turn turn-user", uuid: U2, node: {} }], atEnd: false },
  ]);
  assert.deepEqual(moved!.gone, []);
});

test("a batch that removed or added the TOP SPACER is a window slide (renderWindowItems replaces every child, the spacer first)", () => {
  const top = { cls: "tx-spacer tx-spacer-top", uuid: "", node: {} };
  // the whole-window replace: the spacer and the first units come off mid-list, the tail unit at the end, then everything is appended
  const s = summarizeTailMutations([
    { removed: [top], added: [], atEnd: false },
    { removed: [{ cls: "turn turn-user", uuid: U2, node: {} }], added: [], atEnd: false },
    { removed: [{ cls: "turn turn-assistant", uuid: U1, node: {} }], added: [], atEnd: true },
    { removed: [], added: [{ cls: "tx-spacer tx-spacer-top", uuid: "", node: {} }], atEnd: true },
    { removed: [], added: [{ cls: "turn turn-user", uuid: U2, node: {} }], atEnd: true },
    { removed: [], added: [{ cls: "turn turn-assistant", uuid: U1, node: {} }], atEnd: true },
  ]);
  assert.equal(s!.slide, true);
  assert.deepEqual(s!.gone, [], "the window re-render re-created every unit");
  // a bottom spacer alone is not the mark
  const bot = summarizeTailMutations([{ removed: [{ cls: "tx-spacer tx-spacer-bot", uuid: "" }], added: [], atEnd: true }]);
  assert.equal(bot!.slide, false);
});

test("the row carries what left, whether it came back, the uuids beside the classes, the full lengths, gone and slide", () => {
  const m = { removedTail: ["turn turn-queued"], addedTail: ["turn turn-queued"], reAdded: true, removedUuids: [""], addedUuids: [""], gone: [], slide: false };
  assert.deepEqual(tailMutRow(SID, m, 9114, 9114, 8148.3, 902, "view"),
                   { sid: SID, where: "view", removed: ["turn turn-queued"], added: ["turn turn-queued"], removedUuids: [""], addedUuids: [""], nRemoved: 1, nAdded: 1,
                     reAdded: true, gone: [], slide: false, shBefore: 9114, shAfter: 9114, st: 8148.3, ch: 902 });
  assert.equal(tailMutRow(SID, { ...m, removedTail: ["x".repeat(80)], addedTail: [], reAdded: false }, 1, 2, 3, 4, "live-ask").removed[0].length, 40, "classes bounded");
  // clipped to four, the lengths full: a window re-render of eighty units reads as one
  const many = Array.from({ length: 80 }, (_, i) => "turn u" + i), ids = Array.from({ length: 80 }, (_, i) => "id" + i);
  const row = tailMutRow(SID, { removedTail: ["turn last"], addedTail: many, reAdded: false, removedUuids: ["id79"], addedUuids: ids, gone: [], slide: true }, 1, 1, 0, 1, "view");
  assert.equal(row.added.length, 4); assert.equal(row.addedUuids.length, 4);
  assert.equal(row.nAdded, 80); assert.equal(row.nRemoved, 1);
  assert.equal(row.slide, true);
});

test("render.ts observes the active view's children and the live-ask host's, and files the row through the capped diag path", () => {
  assert.match(RENDER, /import \{[^}]*\bsummarizeTailMutations\b[^}]*\btailMutRow\b[^}]*\} from "\.\/scroll-write";/);
  assert.match(RENDER, /function scrollDiagRow\(kind: "scrollwrite" \| "scrollgesture" \| "tailchange" \| "spacer" \| "tailmut" \| "unitchange" \| "regionask" \| "landmiss", data: any\): void \{/);
  assert.match(RENDER, /mo\?: MutationObserver; \}/, "the View carries its mutation observer");
  assert.match(RENDER, /v\.mo = new MutationObserver\(\(records\) => \{/);
  assert.match(RENDER, /v\.mo\.observe\(elv, \{ childList: true \}\);/);
  assert.equal((RENDER.match(/v\.ro\?\.disconnect\(\); v\.mo\?\.disconnect\(\); v\.el\.remove\(\);/g) || []).length, 2, "both view-removal sites disconnect it");
  assert.match(RENDER, /const tailMo = new MutationObserver\(\(records\) => \{/, "the live-ask host too");
  assert.equal((RENDER.match(/scrollDiagRow\("tailmut", tailMutRow\(/g) || []).length, 2);
  // the "before" is the last scroll height the pane recorded, kept current by every write and every scroll event
  assert.match(RENDER, /let lastKnownSh = 0;/);
  assert.match(RENDER, /lastKnownSh = content\.scrollHeight;/);
  // each node as its class, its unit's uuid and the node itself (the identity a re-add is judged by), every record's nodes
  const fn = RENDER.slice(RENDER.indexOf("function tailMutations(records: MutationRecord[])"), RENDER.indexOf("\n}\n", RENDER.indexOf("function tailMutations(records: MutationRecord[])")));
  assert.match(fn, /uuid: n instanceof HTMLElement \? \(n\.dataset\.uuid \|\| ""\) : ""/);
  assert.match(fn, /node: n \}\)/);
  assert.doesNotMatch(fn, /\.map\(\(m\) => \(\{ removed: m\.removed/, "no second map that re-wraps the nodes");
});
