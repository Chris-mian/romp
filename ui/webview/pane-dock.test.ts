// THE PANE DOCKING ENGINE's pure half, executed (plans/pane-docking.md phase two): the half-zones by nearest
// edge, the strip join zone for a tab payload only, the landing rectangle the accent outline shows, the grab
// gate and the slop, the seed from the shipped stores (today's row over a fixed-px band) and the reconcile
// with the shown set (park what is off, open what is on at its default dock, the band's px following --tl).
// No DOM. Shipped pane ids (chat-pane, fleet-pane the outline's legacy key, feed-pane, files-pane, tl-pane).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import {
  GUTTER, RING, SLOP, CHAT, FLEET, FEED, FILES, BAND,
  edgeZone, zoneAt, landingRect, grabbable, crossedSlop, growKey, seedLayout, defaultDock, reconcileShown,
  bandPxOf, roundRect, colNumberOf, ownerColumn, planTabDrop, type Shown,
} from "./pane-dock";
import { layout, leaves, isSplit, has, setFixed, move, resize, parse, serialise, type Split, type Layout, type Node, type PaneId } from "./pane-tree";
import * as PDockNS from "./pane-dock";
import * as PDock from "./pane-dock";
// the divider drag's pure half is read by name off the module so a build at a base without it still builds and the pins red on behaviour
const edgeClamp = (PDock as unknown as Record<string, (a0: number, b0: number, px: number, minPx: number) => number>).edgeClamp;
const dragEdge = (PDock as unknown as Record<string, (start: Split, path: number[], i: number, px: number, avail: number, minFrac: number) => Split>).dragEdge;

const R = (x: number, y: number, w: number, h: number) => ({ x, y, w, h });
const chat = { pane: CHAT, rect: R(0, 0, 600, 800) }, fleet = { pane: FLEET, rect: R(607, 0, 300, 800) }, feed = { pane: FEED, rect: R(914, 0, 400, 800) };
const rects = [chat, fleet, feed];

test("edgeZone: the nearest edge by fraction of the rect's own dimension; null outside", () => {
  const r = R(0, 0, 600, 800);
  assert.equal(edgeZone(r, { x: 10, y: 400 }), "left");
  assert.equal(edgeZone(r, { x: 590, y: 400 }), "right");
  assert.equal(edgeZone(r, { x: 300, y: 10 }), "top");
  assert.equal(edgeZone(r, { x: 300, y: 790 }), "bottom");
  // a wide short pane: a point 20% in from the left and 10% from the top is TOP (fractions, not px)
  assert.equal(edgeZone(R(0, 0, 1000, 100), { x: 200, y: 10 }), "top");
  assert.equal(edgeZone(r, { x: 601, y: 10 }), null, "outside the rect");
  assert.equal(edgeZone(R(0, 0, 0, 10), { x: 0, y: 5 }), null, "a degenerate rect offers nothing");
});

test("zoneAt: a pane drag sees four half-zones per OTHER pane, none over itself, none over no pane", () => {
  const o = { self: FEED, payload: "pane" as const };
  assert.deepEqual(zoneAt(rects, { x: 20, y: 400 }, o), { target: CHAT, edge: "left" });
  assert.deepEqual(zoneAt(rects, { x: 580, y: 400 }, o), { target: CHAT, edge: "right" });
  assert.deepEqual(zoneAt(rects, { x: 750, y: 20 }, o), { target: FLEET, edge: "top" });
  assert.deepEqual(zoneAt(rects, { x: 750, y: 780 }, o), { target: FLEET, edge: "bottom" });
  assert.equal(zoneAt(rects, { x: 1000, y: 400 }, o), null, "over the dragged pane itself: no zone (a drop cancels)");
  assert.equal(zoneAt(rects, { x: 603, y: 400 }, o), null, "over the gutter: no zone");
  assert.equal(zoneAt(rects, { x: 2000, y: 400 }, o), null, "off every pane");
});

test("zoneAt: the strip is a join zone for a TAB payload and stays a zone for a pane too (the engine refuses it)", () => {
  const strips = { [CHAT]: 32 };
  assert.deepEqual(zoneAt(rects, { x: 300, y: 10 }, { self: null, payload: "tab", strips }), { target: CHAT, strip: true });
  assert.deepEqual(zoneAt(rects, { x: 300, y: 40 }, { self: null, payload: "tab", strips }), { target: CHAT, edge: "top" }, "below the strip: the top half");
  assert.deepEqual(zoneAt(rects, { x: 300, y: 10 }, { self: FEED, payload: "pane", strips }), { target: CHAT, strip: true }, "a pane over the strip names the strip, so the engine can show it refused");
  assert.deepEqual(zoneAt(rects, { x: 750, y: 10 }, { self: null, payload: "tab", strips }), { target: FLEET, edge: "top" }, "a non-chat pane has no strip");
});

test("landingRect: the target's half on the edge (less the gutter's share), or the strip band", () => {
  assert.deepEqual(landingRect(rects, { target: CHAT, edge: "left" }), R(0, 0, (600 - GUTTER) / 2, 800));
  assert.deepEqual(landingRect(rects, { target: CHAT, edge: "right" }), R(600 - (600 - GUTTER) / 2, 0, (600 - GUTTER) / 2, 800));
  assert.deepEqual(landingRect(rects, { target: FLEET, edge: "top" }), R(607, 0, 300, (800 - GUTTER) / 2));
  assert.deepEqual(landingRect(rects, { target: FLEET, edge: "bottom" }), R(607, 800 - (800 - GUTTER) / 2, 300, (800 - GUTTER) / 2));
  assert.deepEqual(landingRect(rects, { target: CHAT, strip: true }, { [CHAT]: 32 }), R(0, 0, 600, 32));
  assert.equal(landingRect(rects, { target: BAND, edge: "top" }), null, "a target with no rect");
});

test("grabbable: primary button, not a control; the ring, a top-row run, or Option anywhere", () => {
  const base = { button: 0, alt: false, onRing: false, onTopRun: false, onControl: false };
  assert.equal(grabbable(base), false, "a plain press over content is never a grab");
  assert.equal(grabbable({ ...base, onRing: true }), true);
  assert.equal(grabbable({ ...base, onTopRun: true }), true);
  assert.equal(grabbable({ ...base, alt: true }), true, "Option-drag anywhere");
  assert.equal(grabbable({ ...base, alt: true, onControl: true }), false, "a control yields to itself even with Option");
  assert.equal(grabbable({ ...base, onRing: true, button: 2 }), false, "the primary button only");
  assert.equal(crossedSlop(SLOP - 1, 0), false); assert.equal(crossedSlop(SLOP, 0), true); assert.equal(crossedSlop(0, -SLOP), true);
  assert.equal(RING, 6, "the grab ring: six px since the user's first press on a three px ring landed nothing (2026-09-19)");
});

test("growKey: the shipped store keys, chat<n> for a column", () => {
  assert.deepEqual([CHAT, FLEET, FEED, FILES, "chat-pane-3"].map(growKey), ["chat", "fleet", "feed", "files", "chat3"]);
});

test("seedLayout: today's row by grow weights over the band as a FIXED kid; parity with the shipped flex row", () => {
  const lay = seedLayout({ row: [CHAT, FEED], band: true, bandPx: 200, grow: { chat: 60, feed: 40, fleet: 34, files: 40 } });
  assert.deepEqual(lay.parked, []);
  const root = lay.tree as Split;
  assert.ok(isSplit(root) && root.dir === "col" && root.fixed && root.fixed[1] === 200, "a column, the band fixed at 200 px");
  const rs = layout(lay.tree, R(0, 0, 1007, 1007), GUTTER);
  const by = Object.fromEntries(rs.map((r) => [r.pane, r.rect]));
  assert.equal(by[BAND].h, 200, "the band keeps its px");
  assert.equal(by[BAND].y, 1007 - 200);
  assert.equal(by[CHAT].h, 800, "the row takes the rest, less the gutter");
  assert.equal(Math.round(by[CHAT].w), 600); assert.equal(Math.round(by[FEED].w), 400);   // 60:40 of 1000
  const noBand = seedLayout({ row: [CHAT], band: false, bandPx: 0, grow: {} });
  assert.deepEqual(noBand.tree, { pane: CHAT }, "one pane, no band: a bare leaf");
});

test("defaultDock: a column right of the last chat, the outline right of the chat side, the feed right of the outline, files at the right end, the chat at the left, the band against the root", () => {
  const t = seedLayout({ row: [CHAT, "chat-pane-2", FLEET, FEED], band: false, bandPx: 0, grow: {} }).tree;
  assert.deepEqual(defaultDock(t, "chat-pane-3"), { target: "chat-pane-2", edge: "right" });
  assert.deepEqual(defaultDock(t, FILES), { target: FEED, edge: "right" });
  const t2 = seedLayout({ row: [CHAT, FEED], band: false, bandPx: 0, grow: {} }).tree;
  assert.deepEqual(defaultDock(t2, FLEET), { target: CHAT, edge: "right" });
  assert.deepEqual(defaultDock({ pane: FEED }, FEED), { target: FEED, edge: "left" }, "the feed with no chat and no outline: the left of what is there");
  assert.deepEqual(defaultDock({ pane: FLEET }, FEED), { target: FLEET, edge: "right" });
  assert.deepEqual(defaultDock(t2, CHAT), { target: CHAT, edge: "left" });
  assert.equal(defaultDock(t2, BAND), null, "the band docks against the whole tree");
  assert.deepEqual(defaultDock({ pane: BAND }, FEED), { target: BAND, edge: "top" }, "only the band present: a pane opens ABOVE it (the round-three read: docking against the root put a row beside the band)");
});

test("reconcileShown: a pane turned off PARKS, one turned on opens at its default dock, the band follows --tl", () => {
  let lay: Layout = seedLayout({ row: [CHAT, FLEET, FEED], band: true, bandPx: 200, grow: { chat: 60, fleet: 34, feed: 40 } });
  // the rail hides the outline
  lay = reconcileShown(lay, { row: [CHAT, FEED], band: true, bandPx: 200, grow: {} });
  assert.deepEqual(leaves(lay.tree), [CHAT, FEED, BAND]);
  assert.deepEqual(lay.parked, [FLEET]);
  // ...and brings it back: right of the chat, un-parked
  lay = reconcileShown(lay, { row: [CHAT, FLEET, FEED], band: true, bandPx: 200, grow: {} });
  assert.deepEqual(leaves(lay.tree), [CHAT, FLEET, FEED, BAND]);
  assert.deepEqual(lay.parked, []);
  // the band's px follows the shell's --tl
  lay = reconcileShown(lay, { row: [CHAT, FLEET, FEED], band: true, bandPx: 312, grow: {} });
  const root = lay.tree as Split;
  assert.equal(root.fixed && root.fixed[1], 312);
  // the band turned off parks it and drops the fixed kid; turned on again it returns at the bottom, fixed
  lay = reconcileShown(lay, { row: [CHAT, FLEET, FEED], band: false, bandPx: 312, grow: {} });
  assert.equal(has(lay.tree, BAND), false); assert.deepEqual(lay.parked, [BAND]);
  assert.equal((lay.tree as Split).fixed, undefined, "no fixed kid left: the row's split carries none");
  lay = reconcileShown(lay, { row: [CHAT, FLEET, FEED], band: true, bandPx: 250, grow: {} });
  const rs = layout(lay.tree, R(0, 0, 1000, 1000), GUTTER);
  const band = rs.find((r) => r.pane === BAND)!.rect;
  assert.deepEqual([band.y, band.h, band.w], [750, 250, 1000], "back at the bottom, full width, its px");
  assert.deepEqual(lay.parked, []);
  // a column opened by the chat split lands right of the last chat leaf; closing it parks it and the next
  // reconcile without it in the row keeps it parked (the DOM element is gone, the park is bookkeeping)
  lay = reconcileShown(lay, { row: [CHAT, "chat-pane-2", FLEET, FEED], band: true, bandPx: 250, grow: {} });
  assert.deepEqual(leaves(lay.tree), [CHAT, "chat-pane-2", FLEET, FEED, BAND]);
  lay = reconcileShown(lay, { row: [CHAT, FLEET, FEED], band: true, bandPx: 250, grow: {} });
  assert.deepEqual(leaves(lay.tree), [CHAT, FLEET, FEED, BAND]);
  assert.deepEqual(lay.parked, ["chat-pane-2"]);
});

test("reconcileShown: a parked pane whose element is gone (a closed chat column) is pruned; a hidden dashboard pane's park stays", () => {
  let lay: Layout = seedLayout({ row: [CHAT, "chat-pane-2", FLEET], band: false, bandPx: 0, grow: {} });
  // the rail hides the outline and the column closes: both leave the row; only the outline's element remains
  lay = reconcileShown(lay, { row: [CHAT], band: false, bandPx: 0, grow: {}, present: [CHAT, FLEET, FEED, FILES, BAND] });
  assert.deepEqual(leaves(lay.tree), [CHAT]);
  assert.deepEqual(lay.parked, [FLEET], "the outline parks (its iframe is mounted and hidden); the column's park is pruned (nothing is mounted)");
  // without a present list every park is kept (an older caller)
  const kept = reconcileShown(seedLayout({ row: [CHAT, "chat-pane-2"], band: false, bandPx: 0, grow: {} }), { row: [CHAT], band: false, bandPx: 0, grow: {} });
  assert.deepEqual(kept.parked, ["chat-pane-2"]);
});

test("reconcileShown: every shown pane parked (a store from a browser whose panes were all off) restarts from the shown set", () => {
  const lay = reconcileShown({ v: 1, tree: { pane: FILES }, parked: [CHAT, FEED] }, { row: [CHAT, FEED], band: false, bandPx: 0, grow: {} });
  assert.deepEqual(leaves(lay.tree), [CHAT, FEED]);
  assert.deepEqual(lay.parked, [FILES], "the files pane, hidden by the rail, parks");
});

test("reconcileShown is idempotent on a layout that already matches the shown set", () => {
  const lay = seedLayout({ row: [CHAT, FLEET, FEED], band: true, bandPx: 200, grow: { chat: 60, fleet: 34, feed: 40 } });
  const again = reconcileShown(lay, { row: [CHAT, FLEET, FEED], band: true, bandPx: 200, grow: {} });
  assert.deepEqual(again, lay);
});

test("bandPxOf and roundRect", () => {
  assert.equal(bandPxOf("312px"), 312); assert.equal(bandPxOf(""), 200); assert.equal(bandPxOf(null), 200); assert.equal(bandPxOf("nope"), 200);
  assert.deepEqual(roundRect(R(0.4, 0.6, 99.7, 10.2)), R(0, 1, 100, 10), "far edges rounded as edges, so neighbours meet");
});

test("colNumberOf and ownerColumn: the first chat pane is column 1, chat-pane-<n> is n, any other pane none; a session's column from the sets", () => {
  assert.equal(colNumberOf(CHAT), 1); assert.equal(colNumberOf("chat-pane-3"), 3); assert.equal(colNumberOf(FEED), null); assert.equal(colNumberOf(BAND), null);
  const sets = { "2": ["s-a", "s-b"], "3": ["s-c"] };
  assert.equal(ownerColumn(sets, "s-b"), 2); assert.equal(ownerColumn(sets, "s-c"), 3);
  assert.equal(ownerColumn(sets, "s-z"), 1, "unlisted: the first column holds the rest"); assert.equal(ownerColumn(null, "s-a"), 1);
});

test("planTabDrop: a strip joins that column, a non-chat strip refuses, an edge opens a new column, a lone later column moves itself and refuses its own edge", () => {
  const sets = { "2": ["s-a", "s-b"], "3": ["s-c"] };
  assert.deepEqual(planTabDrop({ target: CHAT, strip: true }, "s-a", sets), { kind: "join", col: 1 });
  assert.deepEqual(planTabDrop({ target: "chat-pane-2", strip: true }, "s-z", sets), { kind: "join", col: 2 });
  assert.equal(planTabDrop({ target: FEED, strip: true }, "s-a", sets).kind, "refuse", "a non-chat pane has no strip to join");
  assert.deepEqual(planTabDrop({ target: FEED, edge: "bottom" }, "s-a", sets), { kind: "newColumn" }, "a tab from a column of two: a new column with it");
  assert.deepEqual(planTabDrop({ target: FEED, edge: "bottom" }, "s-z", sets), { kind: "newColumn" }, "a tab from the first column: a new column with it");
  assert.deepEqual(planTabDrop({ target: FEED, edge: "left" }, "s-c", sets), { kind: "moveColumn", pane: "chat-pane-3" }, "alone in column 3: the column's pane moves, nothing is minted");
  assert.equal(planTabDrop({ target: "chat-pane-3", edge: "left" }, "s-c", sets).kind, "refuse", "a lone column on its own edge");
  assert.deepEqual(planTabDrop({ target: FEED, edge: "top" }, "s-a", null), { kind: "newColumn" }, "no sets: the first column");
});

test("reconcileShown: a dock hint puts the next new chat column at the drop edge; without one it lands right of the last chat", () => {
  const base = seedLayout({ row: [CHAT, FLEET, FEED], band: false, bandPx: 0, grow: { chat: 50, fleet: 25, feed: 25 } });
  const hinted = reconcileShown(base, { row: [CHAT, "chat-pane-2", FLEET, FEED], band: false, bandPx: 0, grow: {}, newChatDock: { target: FEED, edge: "bottom" } });
  const row = hinted.tree as Split;
  assert.equal(row.dir, "row"); assert.deepEqual(leaves(hinted.tree), [CHAT, FLEET, FEED, "chat-pane-2"]);
  const last = row.kids[2] as Split;
  assert.ok(isSplit(last) && last.dir === "col", "the feed's slot became a column: the feed over the new pane");
  assert.deepEqual(row.ratios.map((r) => Math.round(r * 100) / 100), [0.5, 0.25, 0.25], "the other panes' shares are untouched");
  const plain = reconcileShown(base, { row: [CHAT, "chat-pane-2", FLEET, FEED], band: false, bandPx: 0, grow: {} });
  assert.deepEqual(leaves(plain.tree), [CHAT, "chat-pane-2", FLEET, FEED], "no hint: right of the last chat");
  // the hint names a target that is not in the tree, or the pane itself: the default dock
  const stray = reconcileShown(base, { row: [CHAT, "chat-pane-2", FLEET, FEED], band: false, bandPx: 0, grow: {}, newChatDock: { target: "ghost", edge: "left" } });
  assert.deepEqual(leaves(stray.tree), [CHAT, "chat-pane-2", FLEET, FEED]);
});

// The kit reads the pane list (plans/panes-as-data.md, phase two): a pane the shell rendered from the registry (a data
// pane, the Artifacts pane) is keyed by its element id without `-pane`, weighted by that key's grow, opened at the right
// end after the shipped columns in the ROW's order (the rail's, read off the DOM), and needs no entry in this module.
test("growKey: the pane element's id without -pane for every pane the registry renders, chat<n> for a column", () => {
  assert.deepEqual(["artifacts-pane", "notes-pane", "docs-pane", "chat-pane-2"].map(growKey), ["artifacts", "notes", "docs", "chat2"]);
});

test("seedLayout weights a data pane by its own grow key, and reconcileShown opens data panes at the right end in row order", () => {
  const sh: Shown = { row: [CHAT, FEED, "artifacts-pane", "notes-pane"], band: false, bandPx: 0, grow: { chat: 60, feed: 40, artifacts: 40, notes: 80 } };
  const lay = seedLayout(sh);
  const rects = layout(lay.tree, { x: 0, y: 0, w: 1000, h: 500 }, 0);
  const w = Object.fromEntries(rects.map((r) => [r.pane, Math.round(r.rect.w)]));
  assert.deepEqual(w, { [CHAT]: 273, [FEED]: 182, "artifacts-pane": 182, "notes-pane": 364 }, "60:40:40:80 of 1000 px: the data pane's key is its own, not its element id");
  // a data pane turned on later opens at the right end; two at once open in the row's order (docs before notes, as the rail lists them)
  const base = seedLayout({ row: [CHAT, FEED], band: false, bandPx: 0, grow: {} });
  const next = reconcileShown(base, { row: [CHAT, FEED, "artifacts-pane", "docs-pane", "notes-pane"], band: false, bandPx: 0, grow: {} });
  assert.deepEqual(leaves(next.tree), [CHAT, FEED, "artifacts-pane", "docs-pane", "notes-pane"]);
  assert.deepEqual(defaultDock(next.tree, "later-pane"), { target: "notes-pane", edge: "right" }, "the right end: the pane this module never heard of docks after the last leaf");
  const off = reconcileShown(next, { row: [CHAT, FEED, "notes-pane"], band: false, bandPx: 0, grow: {}, present: [CHAT, FEED, "artifacts-pane", "docs-pane", "notes-pane"] });
  assert.deepEqual(leaves(off.tree), [CHAT, FEED, "notes-pane"]); assert.deepEqual(off.parked.sort(), ["artifacts-pane", "docs-pane"], "a data pane toggled off parks like any pane");
  // the ROW's order is read off the DOM, not a fixed list (the 1920 read: the earlier row put every shipped column before a data pane
  // whatever the DOM said, and a test over a row in the fixed order could not tell the two apart): an INTERLEAVED row opens as written
  const inter = reconcileShown(seedLayout({ row: [CHAT], band: false, bandPx: 0, grow: {} }), { row: [CHAT, "notes-pane", FILES], band: false, bandPx: 0, grow: {} });
  assert.deepEqual(leaves(inter.tree), [CHAT, "notes-pane", FILES], "notes before files, as the row lists them (the fixed list opened files first)");
  assert.equal((PDockNS as unknown as Record<string, unknown>).ROW_ORDER, undefined, "no fixed row list is exported any more");
});

test("seedLayout: a pane the grow store never named takes the mean of the named weights, never a sliver", () => {
  const sh: Shown = { row: [CHAT, FEED, "later-pane"], band: false, bandPx: 0, grow: { chat: 60, feed: 40 } };
  const rects = layout(seedLayout(sh).tree, { x: 0, y: 0, w: 1500, h: 500 }, 0);
  const w = Object.fromEntries(rects.map((r) => [r.pane, Math.round(r.rect.w)]));
  assert.deepEqual(w, { [CHAT]: 600, [FEED]: 400, "later-pane": 500 }, "60 : 40 : 50 (the mean of 60 and 40), so a pane defined after the store was written opens at a fair width");
  const empty = layout(seedLayout({ row: [CHAT, "notes-pane"], band: false, bandPx: 0, grow: {} }).tree, { x: 0, y: 0, w: 1000, h: 500 }, 0);
  assert.deepEqual(empty.map((r) => Math.round(r.rect.w)), [500, 500], "no store at all: equal weights, as before");
});

// A divider drag is ABSOLUTE against the press (plans/pane-docking.md section 12, the 1927 read): every frame moves the edge
// by the pointer's whole travel from the press, applied to the tree as it was at the press, and the clamp holds against the
// pair's sizes at the press. Clamping the travel against the tree the drag rewrote each frame shrank the window every frame
// and the edge converged on half its range (1000 px pair, 500 px of travel: the edge stopped near 250).
test("edgeClamp: the travel is held so neither side drops under the minimum, against the PRESS geometry; a pair too small to seat two minimums does not move", () => {
  assert.equal(typeof edgeClamp, "function", "the kit exports its clamp");
  assert.equal(edgeClamp(600, 400, 100, 120), 100, "inside the window: the pointer's travel as is");
  assert.equal(edgeClamp(600, 400, 500, 120), 280, "far right: the right pane stops at the minimum (400 - 120)");
  assert.equal(edgeClamp(600, 400, -900, 120), -480, "far left: the left pane stops at the minimum (120 - 600)");
  assert.equal(edgeClamp(600, 400, 280, 120), 280, "the clamp's own value passes unchanged");
  assert.equal(edgeClamp(100, 100, 30, 120), 0, "a pair that cannot seat two minimums does not move");
  assert.equal(edgeClamp(300, 400, 60, 75), 60, "the minimum is the caller's (the engine's, a quarter of the tree or 120 px)");
});

test("dragEdge: a horizontal edge follows the pointer's absolute travel from the press to the minimum (120 px) and no further; the start tree is never touched", () => {
  assert.equal(typeof dragEdge, "function", "the kit exports its per-frame drag");
  // chat 600 | outline 300 | feed 400 over 1300 px: the outline|feed edge (i = 1); the engine's minimum is min(0.25, 120/avail)
  const start: Split = { dir: "row", kids: [{ pane: CHAT }, { pane: FLEET }, { pane: FEED }], ratios: [600 / 1300, 300 / 1300, 400 / 1300] };
  const frozen = JSON.stringify(start);
  const avail = 1300, minFrac = Math.min(0.25, 120 / avail);
  const px = (n: Split) => n.ratios.map((r) => Math.round(r * avail));
  // three frames of one drag, each from the SAME start with the pointer's whole travel: the edge is at the pointer
  assert.deepEqual(px(dragEdge(start, [], 1, 50, avail, minFrac)), [600, 350, 350], "50 px right: the outline takes 50 from the feed");
  assert.deepEqual(px(dragEdge(start, [], 1, 150, avail, minFrac)), [600, 450, 250], "150 px right, from the start, not from the frame before");
  const clamp = edgeClamp(300, 400, 900, minFrac * avail);
  assert.equal(clamp, 280, "the clamp against the press geometry: the feed's 400 less the 120 minimum");
  assert.deepEqual(px(dragEdge(start, [], 1, clamp, avail, minFrac)), [600, 580, 120], "at the clamp the feed sits at the real minimum, 120 px");
  assert.deepEqual(px(dragEdge(start, [], 1, 900, avail, minFrac)), [600, 580, 120], "the tree's own clamp agrees: past it, the edge goes no further");
  assert.deepEqual(px(dragEdge(start, [], 1, edgeClamp(300, 400, -900, minFrac * avail), avail, minFrac)), [600, 120, 580], "far left: the outline at the minimum");
  assert.equal(JSON.stringify(start), frozen, "the press tree is the drag's fixed reference and is never mutated: Escape restores it as it was");
  // the commit is the last frame's tree, the same function of start and travel (the engine writes the store once after it)
  const committed = dragEdge(start, [], 1, 150, avail, minFrac);
  assert.deepEqual(dragEdge(start, [], 1, 150, avail, minFrac), committed, "the release lands the last recorded position: a pure function of the press and the travel");
  assert.deepEqual(px(dragEdge(start, [], 1, 0, avail, 0)), [600, 300, 400], "no travel: the start");
});

// A drag's edge under a BAND RE-SIZE (the 1927 read, round four): a divider between stacked panes under the band's split moves with
// the band, and so do its avail and the pair's sizes; the engine re-reads them from the rebased press tree with these two pure reads
// (the press values clamped and resized against a geometry that was gone: the edge 87 px behind the pointer, the pushed pane
// persisted at 96 px under the 120 minimum). Read off the module so a build at a base without them still builds.
test("edgeAt and pressGeometry: the edge between stacked panes under the band re-read after the band grows, its avail smaller by the growth, the pair's sizes with it, the far clamp at the real minimum", () => {
  const edgeAt = (PDockNS as unknown as Record<string, (t: Split, box: { x: number; y: number; w: number; h: number }, g: number, path: number[], i: number) => { rect: { x: number; y: number; w: number; h: number }; avail: number; dir: string; fixed: boolean; path: number[]; i: number } | null>).edgeAt;
  const pressGeometry = (PDockNS as unknown as Record<string, (t: Split, e: unknown) => { a0: number; b0: number }>).pressGeometry;
  assert.equal(typeof edgeAt, "function", "the edge re-read"); assert.equal(typeof pressGeometry, "function", "the pair's sizes");
  // the lab's dock-under-chat tree: a column of [the row [the chat over the feed, the outline, the files pane], the band fixed 97]
  const tree: Split = { dir: "col", kids: [{ dir: "row", kids: [{ dir: "col", kids: [{ pane: CHAT }, { pane: FEED }], ratios: [0.5, 0.5] }, { pane: FLEET }, { pane: FILES }], ratios: [0.6, 0.2, 0.2] }, { pane: BAND }], ratios: [1, 0], fixed: [null, 97] };
  const box = { x: 0, y: 0, w: 1500, h: 870 };
  const e0 = edgeAt(tree, box, GUTTER, [0, 0], 0);
  assert.ok(e0 && e0.dir === "col" && !e0.fixed, "the chat|feed edge, between stacked panes");
  const g0 = pressGeometry(tree, e0);
  assert.equal(Math.round(e0!.avail), Math.round(870 - GUTTER - 97 - GUTTER), "its avail is the column's height less the band and two gutters");
  assert.equal(Math.round(g0.a0 + g0.b0), Math.round(e0!.avail), "the pair fills it");
  // the band grows 150 px under the drag (the shell's autosize): the same edge, re-read from the rebased press tree
  const t2 = setFixed(tree, BAND, 247) as Split;
  const e2 = edgeAt(t2, box, GUTTER, [0, 0], 0)!;
  assert.equal(Math.round(e0!.avail - e2.avail), 150, "its avail is smaller by the growth");
  assert.equal(Math.round(e0!.rect.y - e2.rect.y), 75, "and the divider moved up by the chat's share of it (the origin shift the engine applies)");
  const g2 = pressGeometry(t2, e2);
  assert.equal(Math.round(g2.a0 + g2.b0), Math.round(e2.avail), "the pair's sizes re-derived from the new avail");
  // the far drag clamps at the REAL minimum against the re-derived geometry (against the press values it landed the feed at 96 px)
  const minFrac = Math.min(0.25, 120 / e2.avail);
  const want = edgeClamp(g2.a0, g2.b0, 900, minFrac * e2.avail);
  const after = dragEdge(t2, [0, 0], 0, want, e2.avail, minFrac) as Split;
  const inner = (after.kids[0] as Split).kids[0] as Split;
  assert.equal(Math.round(inner.ratios[1] * e2.avail), 120, "the feed at 120 px");
  const stale = edgeClamp(g0.a0, g0.b0, 900, Math.min(0.25, 120 / e0!.avail) * e0!.avail);
  const staleAfter = dragEdge(t2, [0, 0], 0, stale, e0!.avail, Math.min(0.25, 120 / e0!.avail)) as Split;
  assert.ok(Math.round(((staleAfter.kids[0] as Split).kids[0] as Split).ratios[1] * e2.avail) < 120, "the press values would have left it under the minimum (the review's 96 px)");
});

// ── THE REMEMBERED ARRANGEMENT (plans/pane-buttons-with-many-chats.md section 6, the user 2026-09-21): a hide remembers the tree
//    and a show restores it, for every rail button; the memory rides the layout beside `parked` while anything is parked. ──
const mem = (l: Layout | null) => (l as unknown as { remembered?: Node } | null)?.remembered;
const shape = (n: Node): string => (isSplit(n) ? n.dir + "[" + n.kids.map(shape).join(",") + "]" : n.pane);
const rectsOf = (n: Node) => Object.fromEntries(layout(n, R(0, 0, 1000, 1000), GUTTER).map((r) => [r.pane, r.rect]));
const sameRects = (a: Node, b: Node, what: string) => {
  const ra = rectsOf(a), rb = rectsOf(b);
  assert.deepEqual(Object.keys(ra).sort(), Object.keys(rb).sort(), what + ": the same panes");
  for (const p of Object.keys(ra)) for (const k of ["x", "y", "w", "h"] as const) assert.ok(Math.abs(ra[p][k] - rb[p][k]) < 1e-6, what + ": " + p + "." + k + " " + ra[p][k] + " vs " + rb[p][k]);
};
const seed3 = () => seedLayout({ row: [CHAT, FLEET, FEED], band: true, bandPx: 200, grow: { chat: 60, fleet: 34, feed: 40 } });
const shown = (row: PaneId[], extra: Partial<Shown> = {}): Shown => ({ row, band: true, bandPx: 200, grow: {}, ...extra });

test("remembered: the feed moved under the chat, hidden and shown, comes back under the chat (its default dock is right of the outline)", () => {
  let lay: Layout = seed3();
  lay = { ...lay, tree: move(lay.tree, FEED, CHAT, "bottom") };
  const before = lay.tree;
  assert.equal(shape(before), "col[row[col[chat-pane,feed-pane],fleet-pane],tl-pane]");
  lay = reconcileShown(lay, shown([CHAT, FLEET]));
  assert.deepEqual(lay.parked, [FEED]);
  assert.ok(mem(lay), "a memory stands while a pane is parked");
  lay = reconcileShown(lay, shown([CHAT, FLEET, FEED]));
  assert.equal(shape(lay.tree), shape(before), "the feed is back under the chat, not right of the outline");
  sameRects(lay.tree, before, "the same rectangles as before the hide");
  assert.deepEqual(lay.parked, []);
  assert.equal(mem(lay), undefined, "nothing parked: nothing to remember");
});

test("remembered: a chat column docked under the feed, both chats hidden and shown, comes back under the feed with the first chat where it was", () => {
  let lay: Layout = seed3();
  lay = { ...lay, tree: move(lay.tree, CHAT, FEED, "right") };                               // the chat moved to the right end
  lay = reconcileShown(lay, shown([CHAT, "chat-pane-2", FLEET, FEED], { newChatDock: { target: FEED, edge: "bottom" } }));   // a tab dropped into the feed's bottom half
  const before = lay.tree;
  assert.equal(shape(before), "col[row[fleet-pane,col[feed-pane,chat-pane-2],chat-pane],tl-pane]");
  lay = reconcileShown(lay, shown([FLEET, FEED]));                                          // the rail's chat button: every chat column parks
  assert.deepEqual(lay.parked.slice().sort(), [CHAT, "chat-pane-2"]);
  assert.equal(shape(lay.tree), "col[row[fleet-pane,feed-pane],tl-pane]");
  lay = reconcileShown(lay, shown([CHAT, "chat-pane-2", FLEET, FEED]));
  assert.equal(shape(lay.tree), shape(before), "both chats back where they were (the default docks would put the chat at the left and the column right of it)");
  sameRects(lay.tree, before, "the arrangement before the hide");
});

test("remembered: a column closed while hidden leaves the memory with it; the chat comes back where it was without it", () => {
  let lay: Layout = seed3();
  lay = { ...lay, tree: move(lay.tree, CHAT, FEED, "right") };
  lay = reconcileShown(lay, shown([CHAT, "chat-pane-2", FLEET, FEED], { newChatDock: { target: FEED, edge: "bottom" } }));
  lay = reconcileShown(lay, shown([FLEET, FEED]));
  // the column closes while hidden: its element is gone, so its park is pruned, and so is its remembered place
  lay = reconcileShown(lay, shown([FLEET, FEED], { present: [CHAT, FLEET, FEED, BAND] }));
  assert.deepEqual(lay.parked, [CHAT]);
  assert.ok(mem(lay) && !has(mem(lay)!, "chat-pane-2"), "no record of the closed column: " + (mem(lay) ? shape(mem(lay)!) : "none"));
  lay = reconcileShown(lay, shown([CHAT, FLEET, FEED], { present: [CHAT, FLEET, FEED, BAND] }));
  assert.equal(shape(lay.tree), "col[row[fleet-pane,feed-pane,chat-pane],tl-pane]", "the chat at the right end, where it was (its default dock is the left)");
  assert.equal(mem(lay), undefined);
});

test("remembered: a pane toggled while another is hidden: the returning pane sits beside the neighbour it had, the toggled one returns to its own place", () => {
  let lay: Layout = seed3();
  lay = { ...lay, tree: move(lay.tree, FLEET, CHAT, "left") };                               // the outline left of the chat
  lay = { ...lay, tree: move(lay.tree, FEED, CHAT, "bottom") };                              // then the feed under the chat: a column beside the outline
  const before = lay.tree;
  assert.equal(shape(before), "col[row[fleet-pane,col[chat-pane,feed-pane]],tl-pane]");
  lay = reconcileShown(lay, shown([FLEET, FEED]));                                          // the chat hidden
  lay = reconcileShown(lay, shown([FEED]));                                                 // then the outline hidden too
  assert.deepEqual(lay.parked.slice().sort(), [CHAT, FLEET]);
  lay = reconcileShown(lay, shown([CHAT, FEED]));                                           // the chat shown: above the feed, as remembered (its default is left of everything, a row)
  assert.equal(shape(lay.tree), "col[col[chat-pane,feed-pane],tl-pane]");
  lay = reconcileShown(lay, shown([CHAT, FLEET, FEED]));                                    // the outline shown: left of the chat column, as remembered
  assert.equal(shape(lay.tree), shape(before));
  sameRects(lay.tree, before, "the arrangement before the hides");
});

test("remembered: a pane moved while another is hidden is respected: the returning pane docks beside its remembered neighbour where that neighbour is now", () => {
  let lay: Layout = seed3();
  lay = { ...lay, tree: move(lay.tree, FEED, CHAT, "bottom") };                              // the feed under the chat
  lay = reconcileShown(lay, shown([CHAT, FLEET]));                                          // the feed hidden (its neighbour: the chat, above it)
  lay = { ...lay, tree: move(lay.tree, FLEET, CHAT, "left") };                              // the outline moved left of the chat meanwhile
  assert.equal(shape(lay.tree), "col[row[fleet-pane,chat-pane],tl-pane]");
  lay = reconcileShown(lay, shown([CHAT, FLEET, FEED]));
  assert.equal(shape(lay.tree), "col[row[fleet-pane,col[chat-pane,feed-pane]],tl-pane]", "the feed back under the chat where the chat is now (its default dock is right of the outline)");
});

test("remembered: a resize while a pane is hidden stands; the returning pane takes its remembered share beside its neighbour", () => {
  let lay: Layout = seed3();
  const feedShare = (lay.tree as Split).kids[0] as Split;                                    // the row: chat 60, fleet 34, feed 40 of 134
  const r0 = feedShare.ratios.slice();
  lay = reconcileShown(lay, shown([CHAT, FLEET]));
  lay = { ...lay, tree: resize(lay.tree, [0], 0, 0.2, 0.05) };                              // the chat|outline edge dragged: the chat wider
  const rowHidden = (lay.tree as Split).kids[0] as Split;
  const chatToFleet = rowHidden.ratios[0] / rowHidden.ratios[1];
  lay = reconcileShown(lay, shown([CHAT, FLEET, FEED]));
  const row = (lay.tree as Split).kids[0] as Split;
  assert.deepEqual(leaves(row), [CHAT, FLEET, FEED]);
  assert.ok(Math.abs(row.ratios[0] / row.ratios[1] - chatToFleet) < 1e-9, "the resize made while the feed was hidden stands: " + row.ratios.join(","));
  assert.ok(Math.abs(row.ratios[2] / row.ratios[1] - r0[2] / r0[1]) < 1e-9, "the feed's share beside the outline is what it was: " + row.ratios.join(","));
});

test("remembered: the band keeps its own road (the root's bottom, fixed) and a tab's drop hint wins over the memory for its column", () => {
  let lay: Layout = seed3();
  lay = reconcileShown(lay, shown([CHAT, FLEET, FEED], { band: false }));
  assert.deepEqual(lay.parked, [BAND]);
  lay = reconcileShown(lay, shown([CHAT, FLEET, FEED], { bandPx: 250 }));
  const rs = rectsOf(lay.tree);
  assert.deepEqual([rs[BAND].y, rs[BAND].h, rs[BAND].w], [750, 250, 1000], "the band back at the bottom, fixed, full width");
  assert.equal(mem(lay), undefined);
  // a column hidden with the chat, then shown by a tab drop whose hint names a place: the hint places it
  lay = reconcileShown(lay, shown([CHAT, "chat-pane-2", FLEET, FEED]));                     // the column right of the chat
  lay = reconcileShown(lay, shown([FLEET, FEED]));
  lay = reconcileShown(lay, shown([CHAT, "chat-pane-2", FLEET, FEED], { newChatDock: { target: FEED, edge: "bottom" } }));
  assert.equal(shape(lay.tree), "col[row[chat-pane,fleet-pane,col[feed-pane,chat-pane-2]],tl-pane]", "the hint's place for the column, the memory's for the chat");
});

test("remembered: the layout store carries the memory beside parked, an older store reads with none, and a bad memory is dropped while the layout stands", () => {
  let lay: Layout = seed3();
  lay = { ...lay, tree: move(lay.tree, FEED, CHAT, "bottom") };
  lay = reconcileShown(lay, shown([CHAT, FLEET]));
  const s = serialise(lay);
  assert.ok(s.startsWith('{"v":1,"tree":'), "the phase-one prefix");
  assert.ok(s.indexOf('"parked":["feed-pane"]') > 0 && s.indexOf('"remembered":{') > s.indexOf('"parked"'), "the memory appended after parked: " + s);
  const back = parse(s);
  assert.ok(back && mem(back) && has(mem(back)!, FEED), "the memory round-trips");
  const restored = reconcileShown(back!, shown([CHAT, FLEET, FEED]));
  assert.equal(shape(restored.tree), "col[row[col[chat-pane,feed-pane],fleet-pane],tl-pane]", "a store read back restores the arrangement");
  const old = parse(JSON.stringify({ v: 1, tree: lay.tree, parked: lay.parked }));
  assert.ok(old && mem(old) === undefined, "an older store: no memory, the feed would return at its default dock");
  const bad = parse(JSON.stringify({ v: 1, tree: lay.tree, parked: lay.parked, remembered: { dir: "row", kids: [{ pane: "a" }], ratios: [1] } }));
  assert.ok(bad && mem(bad) === undefined && has(bad.tree, CHAT), "a bad memory costs the remembered place, never the dashboard");
  const noMemory = serialise({ v: 1, tree: lay.tree, parked: [] });
  assert.equal(noMemory.indexOf("remembered"), -1, "a layout without a memory serialises as before, byte for byte");
});

// ── round three (the review of 2026-09-21): the band as a neighbour of last resort, the memory rebuilt from the shown tree at
//    every park (strangers and resizes respected), a stranger in the neighbour's split ──
test("remembered: every row pane hidden, then shown in rail order, rebuilds the seed above the band (the band came back as a column at the left)", () => {
  const seed = seed3();
  let lay: Layout = seed;
  lay = reconcileShown(lay, shown([]));
  assert.deepEqual(leaves(lay.tree), [BAND]);
  assert.deepEqual(lay.parked.slice().sort(), [CHAT, FEED, FLEET].sort());
  lay = reconcileShown(lay, shown([CHAT]));
  assert.equal(shape(lay.tree), "col[chat-pane,tl-pane]", "the chat above the band, never a row beside it");
  const rs = rectsOf(lay.tree);
  assert.deepEqual([rs[BAND].y, rs[BAND].h, rs[BAND].w], [800, 200, 1000], "the band fixed at the bottom, full width");
  lay = reconcileShown(lay, shown([CHAT, FLEET, FEED]));
  assert.equal(shape(lay.tree), shape(seed.tree), "the seed's shape back");
  sameRects(lay.tree, seed.tree, "the seed's rectangles back");
  assert.equal(mem(lay), undefined);
});

test("defaultDock: with only the band shown a pane opens ABOVE it (the memory-less road heals too, never a row beside the band)", () => {
  assert.deepEqual(defaultDock({ pane: BAND }, FEED), { target: BAND, edge: "top" });
  const lay = reconcileShown({ v: 1, tree: { pane: BAND }, parked: [CHAT] } as Layout, shown([CHAT]));
  assert.equal(shape(lay.tree), "col[chat-pane,tl-pane]");
  const rs = rectsOf(lay.tree);
  assert.deepEqual([rs[BAND].y, rs[BAND].h], [800, 200]);
});

test("remembered: a pane turned on while another is hidden keeps the hidden pane its place (files on, the outline hidden, the feed back under the chat)", () => {
  let lay: Layout = seed3();
  lay = { ...lay, tree: move(lay.tree, FEED, CHAT, "bottom") };
  const before = lay.tree;
  lay = reconcileShown(lay, shown([CHAT, FLEET]));                                              // the feed hidden: the memory taken
  lay = reconcileShown(lay, shown([CHAT, FLEET, FILES]));                                       // the files pane turned on: a stranger to the memory
  lay = reconcileShown(lay, shown([CHAT, FILES]));                                              // the outline hidden: the memory rebuilt from the shown tree, the feed re-placed
  const m = mem(lay);
  assert.ok(m && has(m, FEED) && has(m, FILES) && has(m, FLEET), "the memory knows the feed, the outline and the files pane: " + (m ? shape(m) : "none"));
  lay = reconcileShown(lay, shown([CHAT, FLEET, FEED, FILES]));
  assert.equal(shape(lay.tree), "col[row[col[chat-pane,feed-pane],fleet-pane,files-pane],tl-pane]", "the feed back under the chat, the outline beside it, the files pane where it opened");
  lay = reconcileShown(lay, shown([CHAT, FLEET, FEED]));                                        // the files pane hidden again
  assert.equal(shape(lay.tree), shape(before), "the arrangement before the files pane, with the feed under the chat");
});

test("remembered: a column dragged out and closed while a pane is hidden leaves the hidden pane its place", () => {
  let lay: Layout = seed3();
  lay = { ...lay, tree: move(lay.tree, FEED, CHAT, "bottom") };
  const before = lay.tree;
  lay = reconcileShown(lay, shown([CHAT, FLEET]));                                                                   // the feed hidden
  lay = reconcileShown(lay, shown([CHAT, "chat-pane-2", FLEET], { newChatDock: { target: FLEET, edge: "bottom" } }));   // a tab dragged out under the outline
  assert.equal(shape(lay.tree), "col[row[chat-pane,col[fleet-pane,chat-pane-2]],tl-pane]");
  lay = reconcileShown(lay, shown([CHAT, FLEET], { present: [CHAT, FLEET, FEED, FILES, BAND] }));                   // the column closed, its element gone
  assert.equal(shape(lay.tree), "col[row[chat-pane,fleet-pane],tl-pane]");
  assert.ok(mem(lay) && has(mem(lay)!, FEED) && !has(mem(lay)!, "chat-pane-2"), "the memory keeps the feed and drops the closed column: " + (mem(lay) ? shape(mem(lay)!) : "none"));
  lay = reconcileShown(lay, shown([CHAT, FLEET, FEED]));
  assert.equal(shape(lay.tree), shape(before), "the feed back under the chat");
  sameRects(lay.tree, before, "as before the hide");
});

test("remembered: a resize made while a pane is hidden stands when another pane is hidden and shown after it", () => {
  let lay: Layout = seed3();
  lay = reconcileShown(lay, shown([CHAT, FLEET]));                                              // the feed hidden: the memory taken with the seed's ratios
  lay = { ...lay, tree: resize(lay.tree, [0], 0, 0.25, 0.05) };                                // the chat|outline edge dragged
  const dragged = (lay.tree as Split).kids[0] as Split;
  const ratio = dragged.ratios[0] / dragged.ratios[1];
  assert.ok(ratio > 3, "the drag took: " + dragged.ratios.join(","));
  lay = reconcileShown(lay, shown([CHAT]));                                                     // the outline hidden: the memory rebuilt from the dragged tree
  lay = reconcileShown(lay, shown([CHAT, FLEET]));                                              // the outline shown: the drag stands
  const row = (lay.tree as Split).kids[0] as Split;
  assert.ok(Math.abs(row.ratios[0] / row.ratios[1] - ratio) < 1e-9, "the resize stands through the outline's hide and show: " + row.ratios.join(","));
  lay = reconcileShown(lay, shown([CHAT, FLEET, FEED]));                                        // the feed shown: beside the outline with its remembered share, the drag still standing
  const row2 = (lay.tree as Split).kids[0] as Split;
  assert.deepEqual(leaves(row2), [CHAT, FLEET, FEED]);
  assert.ok(Math.abs(row2.ratios[0] / row2.ratios[1] - ratio) < 1e-9, "still standing with the feed back: " + row2.ratios.join(","));
});

test("remembered: a stranger pane in the neighbour's split does not stop the returning pane joining that split as a sibling", () => {
  let lay: Layout = seed3();
  lay = reconcileShown(lay, shown([CHAT, FLEET]));                                              // the feed hidden
  lay = reconcileShown(lay, shown([CHAT, FLEET, FILES]));                                       // the files pane turned on at the right end: the memory never knew it
  lay = reconcileShown(lay, shown([CHAT, FLEET, FEED, FILES]));
  assert.equal(shape(lay.tree), "col[row[chat-pane,fleet-pane,feed-pane,files-pane],tl-pane]", "the feed a sibling right of the outline, not a nested pair with it");
  const row = (lay.tree as Split).kids[0] as Split;
  assert.ok(Math.abs(row.ratios[2] / row.ratios[1] - 40 / 34) < 1e-9, "the feed's share beside the outline is its remembered one: " + row.ratios.join(","));
});

// ── round four (the second review): the last-resort road only for a lone band; the band as a parked pane through the rebuild; the
//    nearest-leaf fallback ──
test("remembered: with a stranger shown above the band, a returning pane whose neighbours are all hidden takes its default dock, never a full-width row of its own under the stranger", () => {
  const seed = seed3();
  let lay: Layout = seed;
  lay = reconcileShown(lay, shown([]));                                                          // every row pane hidden: the band alone
  lay = reconcileShown(lay, shown([FILES]));                                                     // a stranger turned on above the band
  assert.equal(shape(lay.tree), "col[files-pane,tl-pane]");
  lay = reconcileShown(lay, shown([CHAT, FILES]));                                               // the chat back: its neighbours hidden, the band no longer alone
  assert.equal(shape(lay.tree), "col[row[chat-pane,files-pane],tl-pane]", "the chat docks beside the stranger (its default), not as a row of its own between the stranger and the band");
  const rs = rectsOf(lay.tree);
  assert.ok(rs[CHAT].w < 600 && rs[CHAT].h > 700, "the chat a column beside the files pane, full height: " + JSON.stringify(rs[CHAT]));
  lay = reconcileShown(lay, shown([CHAT, FLEET, FEED, FILES]));                                  // the outline and the feed: beside the chat, as remembered
  assert.equal(shape(lay.tree), "col[row[chat-pane,fleet-pane,feed-pane,files-pane],tl-pane]");
  lay = reconcileShown(lay, shown([CHAT, FLEET, FEED]));                                         // the stranger off: the seed
  assert.equal(shape(lay.tree), shape(seed.tree));
  sameRects(lay.tree, seed.tree, "the seed back once the stranger is off");
});

test("remembered: the band as a parked pane rides the rebuild fixed (band off, then the feed off, both back: the seed)", () => {
  const seed = seed3();
  let lay: Layout = seed;
  lay = reconcileShown(lay, shown([CHAT, FLEET, FEED], { band: false }));                        // the band off: the memory taken with the band in it
  assert.deepEqual(lay.parked, [BAND]);
  lay = reconcileShown(lay, shown([CHAT, FLEET], { band: false }));                              // the feed off: the memory rebuilt from the row alone, the band re-inserted by the rebuild
  const m = mem(lay) as Split;
  assert.equal(shape(m), "col[row[chat-pane,fleet-pane,feed-pane],tl-pane]", "the memory holds the band under the row");
  assert.equal(m.fixed && m.fixed[1], 200, "the band fixed at its px in the memory");
  assert.equal(m.ratios[1], 0, "with a zero ratio, as a fixed kid has");
  lay = reconcileShown(lay, shown([CHAT, FLEET, FEED]));                                         // both back
  assert.equal(shape(lay.tree), shape(seed.tree));
  sameRects(lay.tree, seed.tree, "the seed's rectangles back, the band at the bottom");
  assert.equal(mem(lay), undefined);
});

test("remembered: a remembered neighbour whose leaves are shown but no longer one node (a stranger inside it) takes the returning pane at its nearest leaf", () => {
  let lay: Layout = seed3();
  lay = { ...lay, tree: move(lay.tree, FEED, FLEET, "bottom") };                                 // the feed under the outline: row[chat, col[fleet, feed]]
  lay = reconcileShown(lay, shown([FLEET, FEED]));                                               // the chat hidden
  lay = reconcileShown(lay, shown([FLEET, FEED, FILES]));                                        // the files pane on: right of the feed, inside the outline's column
  assert.equal(shape(lay.tree), "col[col[fleet-pane,row[feed-pane,files-pane]],tl-pane]");
  lay = reconcileShown(lay, shown([CHAT, FLEET, FEED, FILES]));                                  // the chat back: its neighbour col[fleet, feed] is scattered, so it docks left of the outline, the unit's first leaf
  assert.equal(shape(lay.tree), "col[col[row[chat-pane,fleet-pane],row[feed-pane,files-pane]],tl-pane]");
  assert.deepEqual(leaves(lay.tree), [CHAT, FLEET, FEED, FILES, BAND]);
});
