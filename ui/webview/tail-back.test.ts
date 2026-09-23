// The TAILBACK instrument (2026-09-23): after the chat-sync fix the page's event instruments (landed, landed-lost,
// landed-missing) read clean on the user's sessions, yet `tailmut` rows kept showing landed user turns' ELEMENTS leaving
// the active view's painted DOM and not coming back within that mutation batch. A row per batch cannot say whether each
// was a MOVE (the same uuid re-inserted elsewhere in a later batch) or a GAP (off the screen while the events still hold
// it): nothing linked a later re-insertion to the earlier removal. This watch follows every uuid that left the tail of
// the active view, batch by batch, until it next appears in that view's DOM (one `tailback` row: how many batches and
// how many ms between the two batches, the same slot or not, the neighbour above before and after) or the view is
// switched away or torn down (a row saying so, so a tab switch never reads as a loss). Observation only: the lifted glue
// runs here over a FROZEN fake DOM and frozen events, so any write it attempted would throw. Synthetic ids throughout.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { createRequire } from "node:module";
import { TailBackWatch, TAILBACK_MAX_PER_VIEW, priorChildren, spotAt, tailGoneInfo, tailKind, type TailFound } from "./tail-back";
import { summarizeTailMutations } from "./scroll-write";

const requireCjs = createRequire(__filename);
const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const SID = "11111111-2222-4333-8444-000000000301", SID2 = "11111111-2222-4333-8444-000000000302";
const U = (n: number) => "11111111-2222-4333-8444-0000000003" + String(n).padStart(2, "0");
const A = U(10), B = U(11), C = U(12), D = U(13);

/** The view's DOM as a list of uuids ("" for a child with none: a day divider, a spacer), and locate over it. */
const world = (list: string[]) => (u: string): TailFound | null => {
  const i = list.lastIndexOf(u);
  return i >= 0 ? spotAt(list, i) : null;
};
const gone = (uuid: string, list: string[], kind = "user", inEv = true) => ({ uuid, kind, inEv, ...spotAt(list, list.lastIndexOf(uuid)) });

test("spotAt: the slot counted from the tail over uuid-bearing children, and the nearest uuid-bearing neighbour above", () => {
  assert.deepEqual(spotAt([A, "", B, C], 3), { fromEnd: 0, above: B });
  assert.deepEqual(spotAt([A, "", B, C], 2), { fromEnd: 1, above: A }, "a divider is neither a slot nor a neighbour");
  assert.deepEqual(spotAt([A], 0), { fromEnd: 0, above: "" });
});

test("a turn removed in one batch and re-inserted IN PLACE two batches later files one row: a blink, sameIndex true", () => {
  const w = new TailBackWatch();
  const before = [A, B, C];
  assert.deepEqual(w.batch(SID, 1000, [gone(C, before)], world([A, B])), [], "a removal alone files nothing yet");
  assert.equal(w.tracking(SID), 1);
  assert.deepEqual(w.batch(SID, 1100, [], world([A, B])), [], "a batch it is still absent from");
  const rows = w.batch(SID, 1250, [], world([A, B, C]));
  assert.deepEqual(rows, [{ sid: SID, uuid: C, kind: "user", inEv: true, end: "back", viewSwitched: false, gapBatches: 2, gapMs: 250,
                            sameIndex: true, fromEnd: [0, 0], neighbourAbove: [B, B] }]);
  assert.equal(w.tracking(SID), 0, "filed once, then forgotten");
  assert.deepEqual(w.batch(SID, 1300, [], world([A, B, C])), [], "no second row for the same return");
});

test("a turn re-inserted ELSEWHERE is a move: sameIndex false, the neighbour above before and after", () => {
  const w = new TailBackWatch();
  w.batch(SID, 5000, [gone(C, [A, B, C], "queued", false)], world([A, B]));
  const [row] = w.batch(SID, 5040, [], world([A, C, B, D]));
  assert.equal(row.end, "back");
  assert.equal(row.gapBatches, 1, "the next batch");
  assert.equal(row.gapMs, 40, "between the two batches");
  assert.equal(row.sameIndex, false);
  assert.deepEqual(row.fromEnd, [0, 2]);
  assert.deepEqual(row.neighbourAbove, [B, A]);
  assert.equal(row.kind, "queued"); assert.equal(row.inEv, false);
});

test("a TAB SWITCH before the uuid returns files viewSwitched: true with no re-insertion; a return later files nothing", () => {
  const w = new TailBackWatch();
  w.batch(SID, 2000, [gone(C, [A, B, C])], world([A, B]));
  w.batch(SID, 2100, [], world([A, B]));
  assert.deepEqual(w.show(SID, 2150), [], "re-showing the same view is not a switch");
  const rows = w.show(SID2, 2400);
  assert.deepEqual(rows, [{ sid: SID, uuid: C, kind: "user", inEv: true, end: "switch", viewSwitched: true, gapBatches: 1, gapMs: 400,
                            sameIndex: null, fromEnd: [0, null], neighbourAbove: [B, null] }]);
  assert.equal(w.tracking(SID), 0);
  assert.deepEqual(w.batch(SID, 3000, [], world([A, B, C])), [], "back on the old tab: tracking ended at the switch");
});

test("a batch of ANOTHER view ends the first view's tracking as a switch (only the active view's batches are fed)", () => {
  const w = new TailBackWatch();
  w.batch(SID, 0, [gone(C, [A, B, C])], world([A, B]));
  const rows = w.batch(SID2, 30, [], world([D]));
  assert.equal(rows.length, 1); assert.equal(rows[0].sid, SID); assert.equal(rows[0].viewSwitched, true); assert.equal(rows[0].gapMs, 30);
});

test("a view torn down (its tab closed, a fork replacing it) ends its tracking as a teardown, not a switch", () => {
  const w = new TailBackWatch();
  w.batch(SID, 0, [gone(C, [A, B, C])], world([A, B]));
  const [row] = w.end(SID, "teardown", 70);
  assert.equal(row.end, "teardown"); assert.equal(row.viewSwitched, false); assert.equal(row.sameIndex, null); assert.equal(row.gapMs, 70);
  assert.deepEqual(w.end(SID, "teardown", 80), [], "nothing left to end");
});

test("a uuid that left but is still on screen in the settled batch (a duplicate) is no gap and is not tracked", () => {
  const w = new TailBackWatch();
  assert.deepEqual(w.batch(SID, 0, [gone(C, [A, C, B, C])], world([A, C, B])), []);
  assert.equal(w.tracking(SID), 0);
});

test("the tracking set is bounded per view: past the bound the OLDEST is dropped with a row saying so", () => {
  const w = new TailBackWatch();
  const list = Array.from({ length: TAILBACK_MAX_PER_VIEW + 6 }, (_, i) => "11111111-2222-4333-8444-00000000" + String(4000 + i));
  const rows = w.batch(SID, 0, list.map((u) => gone(u, list)), world([]));
  assert.equal(TAILBACK_MAX_PER_VIEW, 64);
  assert.equal(w.tracking(SID), 64);
  assert.deepEqual(rows.map((r) => r.uuid), list.slice(0, 6), "the six oldest");
  assert.ok(rows.every((r) => r.end === "evicted" && r.viewSwitched === false && r.sameIndex === null));
});

test("inEv reflects the page's resident events at the removal; kind from the event, the optimistic and held prefixes, else the class", () => {
  const evs = Object.freeze([
    Object.freeze({ kind: "user", uuid: A }),
    Object.freeze({ kind: "queued", uuid: B }),
    Object.freeze({ kind: "queued", uuid: "optimistic:11111111-2222-4333-8444-000000000399" }),
    Object.freeze({ kind: "tool", uuid: C, resultUuid: D }),   // an AskUserQuestion turn anchors on its answer line's uuid
  ]);
  const cls: Record<string, string> = { [U(20)]: "turn turn-user", [U(21)]: "turn turn-toolgroup expanded" };
  const got = tailGoneInfo([A, B, "optimistic:11111111-2222-4333-8444-000000000399", D, U(20), U(21), U(22)], evs, (u) => cls[u] || "");
  assert.deepEqual(got, [{ kind: "user", inEv: true }, { kind: "queued", inEv: true }, { kind: "optimistic", inEv: true }, { kind: "tool", inEv: true },
                         { kind: "user", inEv: false }, { kind: "tool", inEv: false }, { kind: "?", inEv: false }]);
  assert.equal(tailKind("", "held:11111111-2222-4333-8444-000000000398", "turn turn-queued"), "held");
  assert.equal(tailKind("", U(23), "turn turn-assistant"), "assistant");
});

test("priorChildren undoes a batch's records to the painted list before it: appends, removals, an insert-before, a replaceChildren", () => {
  const a = { n: "a" }, b = { n: "b" }, c = { n: "c" }, d = { n: "d" }, e = { n: "e" }, x = { n: "x" };
  // the tail turn removed, a new one appended, then the removed one re-created as a new element
  assert.deepEqual(priorChildren([a, b, d, x], [
    { removed: [c], added: [], prev: b, next: null },
    { removed: [], added: [d], prev: b, next: null },
    { removed: [], added: [x], prev: d, next: null },
  ]), [a, b, c]);
  assert.deepEqual(priorChildren([a, e, b], [{ removed: [], added: [e], prev: a, next: b }]), [a, b], "an insert before a sibling");
  assert.deepEqual(priorChildren([x, e], [{ removed: [a, b, c], added: [x, e], prev: null, next: null }]), [a, b, c], "replaceChildren");
  assert.deepEqual(priorChildren([b, c], [{ removed: [a], added: [], prev: null, next: b }]), [a, b, c], "the first child removed");
});

// ── the glue, lifted from render.ts and executed over a frozen fake DOM ───────────────────────────────────────────

function liftGlue(): string {
  const start = "const tailBack = new TailBackWatch();", end = "// the cap is the default unless the page's localStorage";
  const a = RENDER.indexOf(start), b = RENDER.indexOf(end, a);
  assert.ok(a > 0 && b > a, "the tailback glue moved; re-anchor");
  return requireCjs("esbuild").transformSync(RENDER.slice(a, b), { loader: "ts" }).code;
}
type FakeEl = Readonly<{ dataset: Readonly<{ uuid?: string }>; className: string; childNodes: readonly FakeEl[] }>;
/** A node: itself, its dataset and its child list frozen, so any write the glue attempted would throw (strict mode). */
const fakeEl = (uuid: string, cls: string, kids: FakeEl[] = []): FakeEl =>
  Object.freeze({ dataset: Object.freeze(uuid ? { uuid } : {}), className: cls, childNodes: Object.freeze(kids.slice()) });
/** A view whose element holds `kids`, frozen the same way. */
const fakeView = (kids: FakeEl[]) => Object.freeze({ el: fakeEl("", "thread", kids) });
const dump = (n: FakeEl): unknown => ({ u: n.dataset.uuid || "", c: n.className, k: n.childNodes.map(dump) });
const asRecord = (removed: FakeEl[], added: FakeEl[], prev: FakeEl | null, next: FakeEl | null) =>
  Object.freeze({ removedNodes: Object.freeze(removed), addedNodes: Object.freeze(added), previousSibling: prev, nextSibling: next });
const summary = (records: ReturnType<typeof asRecord>[]) => summarizeTailMutations(records.map((r) => ({
  removed: r.removedNodes.map((n) => ({ cls: n.className, uuid: n.dataset.uuid || "", node: n })),
  added: r.addedNodes.map((n) => ({ cls: n.className, uuid: n.dataset.uuid || "", node: n })),
  atEnd: r.nextSibling === null })));

function glueWorld() {
  const filed: { kind: string; data: any }[] = [], fails: { what: string; data: any }[] = [];
  const sessions = new Map<string, { events: readonly object[] }>();
  const scope = { TailBackWatch, priorChildren, spotAt, tailGoneInfo, sessions,
                  scrollDiagRow: (kind: string, data: any) => { filed.push({ kind, data }); },
                  chatDiagRow: (what: string, data: any) => { fails.push({ what, data }); } };
  const api = new Function("S", `"use strict"; const { TailBackWatch, priorChildren, spotAt, tailGoneInfo, sessions, scrollDiagRow, chatDiagRow } = S;\n`
    + liftGlue() + "\nreturn { tailBackBatch, tailBackShow, tailBackEnd };")(scope);
  return { api, filed, fails, sessions };
}

test("EXECUTED over a frozen DOM: the glue files the tailmut row's kind and inEv, then a tailback row on the return, and writes nothing", () => {
  const { api, filed, fails, sessions } = glueWorld();
  const deep = (o: any): any => { Object.values(o).forEach((v) => { if (v && typeof v === "object") deep(v); }); return Object.freeze(o); };
  sessions.set(SID, deep({ events: [{ kind: "assistant", uuid: A }, { kind: "user", uuid: B }, { kind: "user", uuid: C }] }));
  const a = fakeEl(A, "turn turn-assistant"), b = fakeEl(B, "turn turn-user"), c = fakeEl(C, "turn turn-user");
  // batch 1: the user turn at the tail leaves and nothing brings it back
  const v1 = fakeView([a, b]);
  const r1 = [asRecord([c], [], b, null)];
  const before1 = JSON.stringify(dump(v1.el as any));
  const info = api.tailBackBatch(SID, v1, r1, summary(r1));
  assert.deepEqual(info, [{ kind: "user", inEv: true }], "the tailmut row's goneKind/goneInEv, aligned with its gone list");
  assert.equal(filed.length, 0);
  assert.equal(JSON.stringify(dump(v1.el as any)), before1, "the DOM is exactly as the render left it");
  // batch 2: an append-only batch (tailMutations reads null) brings the uuid back as a NEW element in the same slot
  const c2 = fakeEl(C, "turn turn-user");
  const v2 = fakeView([a, b, c2]);
  const before2 = JSON.stringify(dump(v2.el as any));
  assert.equal(api.tailBackBatch(SID, v2, [asRecord([], [c2], b, null)], null), undefined, "no tail removal: no tailmut row to feed");
  assert.equal(JSON.stringify(dump(v2.el as any)), before2);
  assert.equal(filed.length, 1);
  assert.equal(filed[0].kind, "tailback");
  assert.deepEqual({ ...filed[0].data, gapMs: 0 }, { sid: SID, uuid: C, kind: "user", inEv: true, end: "back", viewSwitched: false, gapBatches: 1, gapMs: 0,
                                                   sameIndex: true, fromEnd: [0, 0], neighbourAbove: [B, B] });
  assert.ok(filed[0].data.gapMs >= 0);
  // batch 3: it leaves again; the user switches tabs before it returns
  const v3 = fakeView([a, b]);
  const r3 = [asRecord([c2], [], b, null)];
  const before3 = JSON.stringify(dump(v3.el as any));
  api.tailBackBatch(SID, v3, r3, summary(r3));
  api.tailBackShow(SID2);
  assert.equal(JSON.stringify(dump(v3.el as any)), before3);
  assert.equal(filed.length, 2); assert.equal(filed[1].data.viewSwitched, true); assert.equal(filed[1].data.end, "switch");
  // a teardown of a view that holds nothing files nothing
  api.tailBackEnd(SID, "teardown");
  assert.equal(filed.length, 2);
  assert.deepEqual(fails, [], "no instrument failure along the way");
});

test("EXECUTED: an instrument error is swallowed into ONE failure row, so it can cost a row and never a render", () => {
  const { api, filed, fails } = glueWorld();
  const broken = Object.freeze({ get el(): never { throw new Error("synthetic"); } });
  const r = [asRecord([fakeEl(C, "turn turn-user")], [], null, null)];
  assert.doesNotThrow(() => api.tailBackBatch(SID, broken, r, summary(r)));
  assert.doesNotThrow(() => api.tailBackBatch(SID, broken, r, summary(r)));
  assert.equal(fails.length, 1); assert.equal(fails[0].what, "tailback-failed");
  assert.deepEqual(filed, []);
});

test("render.ts wiring: every batch of the active view feeds the watch, switches and teardowns end it, rows ride the capped diag path", () => {
  assert.match(RENDER, /import \{ TailBackWatch, priorChildren, spotAt, tailGoneInfo, type TailFound, type TailGone \} from "\.\/tail-back";/);
  assert.match(RENDER, /function scrollDiagRow\(kind: "scrollwrite" \| "scrollgesture" \| "tailchange" \| "spacer" \| "tailmut" \| "tailback" \| "unitchange" \| "regionask" \| "landmiss", data: any\): void \{/);
  // the view's observer: an inactive view's batch ends its tracking; the active view's EVERY batch is fed, before the
  // no-tail-removal return (a return comes in a batch that removed nothing), and the tailmut row carries kind and inEv
  const mo = RENDER.slice(RENDER.indexOf("v.mo = new MutationObserver((records) => {"), RENDER.indexOf("v.mo.observe(elv, { childList: true });"));
  assert.match(mo, /if \(activeId !== id \|\| !view2\.shown\) \{ tailBackEnd\(id, "switch"\); return; \}/);
  assert.match(mo, /const m = tailMutations\(records\);\n\s+const gi = tailBackBatch\(id, view2, records, m\);[^\n]*\n\s+if \(!m\) return;/);
  assert.match(mo, /scrollDiagRow\("tailmut", tailMutRow\(id, m, lastKnownSh, content\.scrollHeight, content\.scrollTop, content\.clientHeight, "view", gi\)\);/);
  // the rows: through scrollDiagRow (its per-session, per-minute cap), never a bare postMessage
  assert.match(RENDER, /for \(const r of rows\) scrollDiagRow\("tailback", r\);/);
  // showActive: every place that decides which view is on screen tells the watch (the snapshot and no-session hides, the flip)
  assert.equal((RENDER.match(/for \(const v of views\.values\(\)\) v\.el\.style\.display = "none";\n\s+tailBackShow\(null\);/g) || []).length, 2);
  assert.match(RENDER, /for \(const \[vid, vv\] of views\) vv\.el\.style\.display = vid === activeId \? "" : "none";\n[^\n]*\n\s+tailBackShow\(activeId\);/);
  // both view-removal sites end the view's tracking as a teardown
  assert.equal((RENDER.match(/v\.el\.remove\(\); views\.delete\((?:msg\.id|id)\); tailBackEnd\((?:msg\.id|id), "teardown"\); \}/g) || []).length, 2);
});
