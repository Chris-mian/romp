// THE PANE LAYOUT TREE's fixed-px kid, executed (plans/pane-docking.md phase two, section 11: the timeline band
// keeps a FIXED height via a fixed-px kid; layout allots the fixed kids first and divides the rest among the
// ratio kids). Also the edges list the engine mounts dividers from, setFixed following --tl, dockRoot against
// the whole tree, and the store round-trip with a fixed array. The module is imported as a namespace so each
// test names its own red at the base (a missing export is a TypeError in that test alone; a fixed array the
// base ignores is a wrong rectangle). No DOM.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as PT from "./pane-tree";

const R = (x: number, y: number, w: number, h: number) => ({ x, y, w, h });
const T = PT as any;

test("layout: a fixed kid takes its px first; the ratio kids divide the remainder", () => {
  const tree: PT.Node = { dir: "col", kids: [{ pane: "row" }, { pane: "band" }], ratios: [1, 0], fixed: [null, 200] } as any;
  const rs = PT.layout(tree, R(0, 0, 1000, 1007), 7);
  const by = Object.fromEntries(rs.map((r) => [r.pane, r.rect]));
  assert.deepEqual(by.band, R(0, 807, 1000, 200), "the band: its px, at the bottom");
  assert.deepEqual(by.row, R(0, 0, 1000, 800), "the row: the rest less the gutter");
  // a taller window: the band does NOT grow (the ratio kid did)
  const rs2 = PT.layout(tree, R(0, 0, 1000, 1407), 7);
  assert.equal(rs2.find((r) => r.pane === "band")!.rect.h, 200);
  assert.equal(rs2.find((r) => r.pane === "row")!.rect.h, 1200);
  // three kids, one fixed in the middle
  const three: PT.Node = { dir: "row", kids: [{ pane: "a" }, { pane: "b" }, { pane: "c" }], ratios: [0.25, 0, 0.75], fixed: [null, 100, null] } as any;
  const r3 = Object.fromEntries(PT.layout(three, R(0, 0, 514, 100), 7).map((r) => [r.pane, r.rect]));
  assert.deepEqual([r3.a.w, r3.b.w, r3.c.w], [100, 100, 300]);
  assert.deepEqual([r3.a.x, r3.b.x, r3.c.x], [0, 107, 214]);
});

test("seedRowOverFixedBand: the row over a fixed band; no band, the row alone", () => {
  const t = T.seedRowOverFixedBand(["chat", "feed"], { chat: 60, feed: 40 }, "band", 200) as PT.Split;
  assert.equal(t.dir, "col"); assert.deepEqual(t.fixed, [null, 200]); assert.deepEqual(t.ratios, [1, 0]);
  assert.deepEqual(PT.leaves(t), ["chat", "feed", "band"]);
  assert.deepEqual(T.seedRowOverFixedBand(["chat"], {}, null, 0), { pane: "chat" });
  assert.deepEqual((T.seedRowOverFixedBand(["chat"], {}, "band", 0) as PT.Split).fixed, [null, 200], "a bad px falls to the default 200");
});

test("setFixed: the slot's px follows the shell's --tl; a pane absent or alone leaves the tree as it was", () => {
  const t = T.seedRowOverFixedBand(["chat", "feed"], {}, "band", 200) as PT.Node;
  const t2 = T.setFixed(t, "band", 312) as PT.Split;
  assert.deepEqual(t2.fixed, [null, 312]);
  assert.deepEqual((T.setFixed(t, "band", null) as PT.Split).fixed, undefined, "cleared: back to a ratio kid (an all-null array is dropped)");
  assert.deepEqual(T.setFixed(t, "ghost", 100), t);
  assert.deepEqual(T.setFixed({ pane: "band" }, "band", 100), { pane: "band" });
});

test("splitAt beside a fixed kid: the new pane is a RATIO kid with an equal share; onto a fixed leaf: the split fills the fixed slot", () => {
  const t = T.seedRowOverFixedBand(["chat", "feed"], {}, "band", 200) as PT.Node;
  // dock the files pane ABOVE the band (a same-direction sibling in the column): a ratio kid, the band still fixed
  const above = PT.splitAt(t, "band", "files", "top") as PT.Split;
  assert.deepEqual(PT.leaves(above), ["chat", "feed", "files", "band"]);
  assert.deepEqual(above.fixed, [null, null, 200]);
  assert.deepEqual(above.ratios.map((r) => Math.round(r * 100) / 100), [0.5, 0.5, 0]);
  // dock LEFT of the band (a different direction): the band's slot becomes a row split sharing the fixed height
  const beside = PT.splitAt(t, "band", "files", "left") as PT.Split;
  assert.deepEqual(beside.fixed, [null, 200]);
  const rs = Object.fromEntries(PT.layout(beside, R(0, 0, 1007, 1007), 7).map((r) => [r.pane, r.rect]));
  assert.deepEqual([rs.files.h, rs.band.h, rs.files.y], [200, 200, 807], "both share the band's fixed height at the bottom");
  assert.equal(rs.files.w, rs.band.w);
});

test("detach: a collapse onto a fixed kid carries its px up; removing the fixed kid drops the fixed array", () => {
  const t = T.seedRowOverFixedBand(["chat", "feed"], {}, "band", 200) as PT.Node;
  const above = PT.splitAt(t, "band", "files", "top");
  const { tree: noFiles } = PT.detach(above, "files");
  assert.deepEqual((noFiles as PT.Split).fixed, [null, 200], "the band stays fixed after its sibling leaves");
  const { tree: noBand } = PT.detach(t, "band");
  assert.equal((noBand as PT.Split).fixed, undefined);
  assert.deepEqual(PT.leaves(noBand!), ["chat", "feed"]);
  // a nested split that collapses to the fixed kid: [row, col[band, x]] with the col fixed... the band alone remains and
  // the slot keeps the col's px (the parent's fixed entry names the slot)
  const nested: PT.Node = { dir: "col", kids: [{ pane: "row" }, { dir: "row", kids: [{ pane: "band" }, { pane: "x" }], ratios: [0.5, 0.5] }], ratios: [1, 0], fixed: [null, 200] } as any;
  const { tree: t3 } = PT.detach(nested, "x");
  assert.deepEqual(t3, { dir: "col", kids: [{ pane: "row" }, { pane: "band" }], ratios: [1, 0], fixed: [null, 200] });
});

test("move carries a fixed array along; the moved band becomes a ratio kid where it lands", () => {
  const t = T.seedRowOverFixedBand(["chat", "feed"], {}, "band", 200) as PT.Node;
  const moved = PT.move(t, "band", "chat", "left") as PT.Split;
  assert.deepEqual(PT.leaves(moved), ["band", "chat", "feed"]);
  assert.equal(moved.fixed, undefined, "no fixed kid left anywhere");
  assert.equal(moved.dir, "row");
});

test("resize: an edge touching a fixed kid is a no-op; the other edges still move", () => {
  const t = PT.splitAt(T.seedRowOverFixedBand(["chat", "feed"], {}, "band", 200), "band", "files", "top") as PT.Split;   // col[row, files, band]
  assert.deepEqual(PT.resize(t, [], 1, 0.1, 0.05), t, "the files|band edge: sized in px, never by ratio");
  const r = PT.resize(t, [], 0, 0.1, 0.05) as PT.Split;
  assert.deepEqual(r.ratios.map((x) => Math.round(x * 100) / 100), [0.6, 0.4, 0]);
  assert.deepEqual(r.fixed, [null, null, 200]);
});

test("edges: one gutter rect per internal edge, with its split path, index, direction, fixed flag and the ratio kids' px", () => {
  const t = T.seedRowOverFixedBand(["chat", "feed"], { chat: 60, feed: 40 }, "band", 200) as PT.Node;
  const es = T.edges(t, R(0, 0, 1007, 1007), 7) as PT.EdgeRect[];
  assert.equal(es.length, 2);
  const rowEdge = es.find((e) => e.dir === "row")!, colEdge = es.find((e) => e.dir === "col")!;
  assert.deepEqual([rowEdge.path, rowEdge.i, rowEdge.fixed], [[0], 0, false]);
  assert.deepEqual(rowEdge.rect, R(600, 0, 7, 800), "between the chat (600 of 1000) and the feed, the row's height");
  assert.equal(rowEdge.avail, 1000);
  assert.deepEqual([colEdge.path, colEdge.i, colEdge.fixed], [[], 0, true]);
  assert.deepEqual(colEdge.rect, R(0, 800, 1007, 7), "above the band, full width");
  assert.deepEqual(T.edges({ pane: "x" }, R(0, 0, 10, 10), 7), []);
});

test("dockRoot: wrap the whole tree; a fixed px makes the new kid fixed", () => {
  const t: PT.Node = { pane: "chat" };
  const b = T.dockRoot(t, "band", "bottom", 200) as PT.Split;
  assert.deepEqual(b, { dir: "col", kids: [{ pane: "chat" }, { pane: "band" }], ratios: [1, 0], fixed: [null, 200] });
  const l = T.dockRoot(t, "files", "left") as PT.Split;
  assert.deepEqual(l, { dir: "row", kids: [{ pane: "files" }, { pane: "chat" }], ratios: [0.5, 0.5] });
  assert.throws(() => T.dockRoot(b, "band", "top"), /already in the tree/);
});

test("serialise/parse round-trips a fixed array and refuses a malformed one", () => {
  const lay: PT.Layout = { v: 1, tree: T.seedRowOverFixedBand(["chat", "feed"], {}, "band", 200), parked: [] };
  const back = PT.parse(PT.serialise(lay));
  assert.deepEqual(back, lay);
  assert.ok(PT.serialise(lay).includes('"fixed":[null,200]'));
  const bad = (fixed: unknown, ratios = [1, 0]) => PT.parse(JSON.stringify({ v: 1, parked: [], tree: { dir: "col", kids: [{ pane: "a" }, { pane: "b" }], ratios, fixed } }));
  assert.equal(bad([null]), null, "wrong length");
  assert.equal(bad([null, -5]), null, "a negative px");
  assert.equal(bad([null, "200"]), null, "a string px");
  assert.equal(bad([null, null]), null, "an all-null array is not a shape this module writes");
  assert.equal(PT.parse(JSON.stringify({ v: 1, parked: [], tree: { dir: "col", kids: [{ pane: "a" }, { pane: "b" }], ratios: [0.5, 0.5], fixed: [null, 200] } })), null, "0.5 alone does not sum to 1 over the ratio kids");
  const ok = PT.parse(JSON.stringify({ v: 1, parked: [], tree: { dir: "col", kids: [{ pane: "a" }, { pane: "b" }], ratios: [1, 0.3], fixed: [null, 200] } })) as PT.Layout;
  assert.deepEqual((ok.tree as PT.Split).ratios, [1, 0], "a stray ratio on the fixed kid is normalised to 0");
});
