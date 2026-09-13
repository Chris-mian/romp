// The proto-2 client's DOM-side rules, EXECUTED (T323 stage 4b, review round 3; T386 stage 2): functions lifted from render.ts by
// anchor, transpiled with esbuild at run time and run over a Proxy scope that answers every free identifier the function reaches
// for with a stub, plus the real chat-window and chat-regions rules where the function uses them. Driven: renderEvent stamps an
// orphan note's record uuid on its turn; upsert builds the session's regions from the frame's tailLo, keeping the history runs
// the page holds below it and dropping the rest; requestAround marks each window ask with whether a navigation made it.
// Synthetic events only.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { createRequire } from "node:module";
import { mergeWindow, keyOf } from "./chat-window";
import { insertRun, regionsFromRuns, runsOf, turnsBeforeTail, type Region } from "./chat-regions";

const requireCjs = createRequire(__filename);
const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");

function liftBetween(startAnchor: string, endAnchor: string): string {
  const a = RENDER.indexOf(startAnchor), b = RENDER.indexOf(endAnchor, a);
  assert.ok(a > 0 && b > a, `anchors moved: ${startAnchor.slice(0, 40)} / ${endAnchor.slice(0, 40)}`);
  return requireCjs("esbuild").transformSync(RENDER.slice(a, b), { loader: "ts" }).code;
}

/** Run lifted code with `scope` as the world: every identifier the code reads that `scope` lacks resolves to a no-op
 *  function (a Proxy behind `with`), so a function can be executed for the ONE rule under test without its whole world. */
function liftWith(js: string, scope: Record<string, unknown>, names: string[]): Record<string, any> {
  const proxy = new Proxy(scope, {
    has: (t, k) => k in t || !(k in globalThis),   // a real global (Math, Map, JSON) stays itself; the rest is the scope's or a stub
    get: (t, k) => (k in t ? (t as any)[k] : (typeof k === "symbol" ? undefined : (() => undefined))),
    set: (t, k, v) => { (t as any)[k] = v; return true; },
  });
  const body = `with (SCOPE) { ${js}\n return { ${names.join(", ")} }; }`;
  return (new Function("SCOPE", body) as (s: unknown) => Record<string, any>)(proxy);
}

function fakeEl(): any {
  const el: any = { hidden: false, style: {}, className: "", id: "", textContent: "", children: [] as any[], dataset: {}, type: "",
                    querySelector: () => null, querySelectorAll: () => [], setAttribute() {}, removeAttribute() {}, addEventListener() {},
                    classList: { add() {}, remove() {}, toggle() {} },
                    appendChild(c: any) { el.children.push(c); return c; }, getBoundingClientRect: () => ({ bottom: 500, top: 0 }) };
  return el;
}

test("renderEvent stamps an orphan note's record uuid on its turn beside the note's own key", () => {
  const scope: Record<string, unknown> = {
    renderEventInner: () => fakeEl(), isOptimistic: () => false, eventEpoch: () => 1700000000,
    el: (_t: string, cls: string) => { const e = fakeEl(); e.className = cls; return e; },
  };
  const js = liftBetween("function renderEvent(ev: ChatEvent, prevEpoch?: number | null, worked?: number | null): HTMLElement {", "\nfunction renderEventInner(");
  const api = liftWith(js, scope, ["renderEvent"]);
  const turn = api.renderEvent({ kind: "assistant", uuid: "orphan:1700000000:1", orphaned: true, orphanOf: "rec-9", md: "salvaged" });
  assert.equal(turn.dataset.uuid, "orphan:1700000000:1", "the note's own key lands the walks");
  assert.equal(turn.dataset.orphanOf, "rec-9", "…and the record uuid lands a deep link by the reply's uuid");
  const plain = api.renderEvent({ kind: "assistant", uuid: "a1", md: "hi" });
  assert.equal(plain.dataset.orphanOf, undefined, "an ordinary reply carries none");
});

// ── upsert: the tail run's regions (T386 stage 2) ────────────────────────────────────────────────
function liftUpsert(sessions: Map<string, any>, pendingFullWhy: Map<string, string>, activeId: string | null) {
  const scope: Record<string, unknown> = {
    sessions, pendingFullWhy, activeId, awaitingFull: new Set<string>(), skeletonTabs: { ids: new Set() }, tabMeta: new Map(), pendingTabMeta: new Map(),
    emptyFrameDiagSent: new Set(), ledgers: new Map(), views: new Map(),
    document: { getElementById: () => null, createElement: () => fakeEl(), body: fakeEl(), querySelector: () => null },
    window: { innerHeight: 800, requestAnimationFrame: () => 0 },
    keepResidentEvents: () => false, onFull: () => false, hostOf: () => "", mergeWindow, keyOf, regionsFromRuns, runsOf, insertRun, turnsBeforeTail, stripOptimistic: () => {},
  };
  const js = liftBetween("function upsert(msg: any) {", "\nfunction ");
  return liftWith(js, scope, ["upsert"]);
}
const shape = (rs: readonly Region[] | undefined) => (rs ?? []).map((r) => r.kind === "gap" ? "gap[" + r.lo + "," + r.hi + ")" : "run[" + r.lo + "," + (r.hi ?? "tail") + "):" + r.events.map((e: any) => e.uuid).join(","));

test("upsert builds the regions from the frame's tailLo: the tail run from there, the held history runs below it kept, one the tail now covers dropped (T386 stage 2)", () => {
  const ev = (u: string) => ({ uuid: u, kind: "user", md: u });
  const held = { id: "A", name: "web", events: [ev("t1")], status: { state: "idle" }, proto: 2, headKnown: false, headTotal: null, firstUuid: "t1", lastUuid: "t1", events0: null,
                 tailLo: 200, regions: [{ kind: "gap", lo: 0, hi: 96 }, { kind: "run", lo: 96, hi: 128, events: [ev("w1")] }, { kind: "gap", lo: 128, hi: 200 }, { kind: "run", lo: 200, hi: null, events: [ev("t1")] }] };
  const frame = (events: any[], extra: Record<string, unknown>) => ({ type: "session", id: "A", name: "web", proto: 2, events, headKnown: false, headTotal: null, firstUuid: events[0].uuid, lastUuid: events[events.length - 1].uuid, status: { state: "idle" }, pageTurns: 16, ...extra });
  // the tail grew: the same tailLo, the history run kept, the gaps as they were
  let sessions = new Map<string, any>([["A", { ...held }]]);
  liftUpsert(sessions, new Map(), "A").upsert(frame([ev("t1"), ev("t2")], { tailLo: 200 }));
  let s = sessions.get("A");
  assert.deepEqual(shape(s.regions), ["gap[0,96)", "run[96,128):w1", "gap[128,200)", "run[200,tail):t1,t2"]);
  assert.equal(s.tailLo, 200); assert.equal(s.pageTurns, 16);
  // the kernel's tail now starts lower (a window joined it): a history run the tail covers is dropped, one below it stays
  sessions = new Map<string, any>([["A", { ...held }]]);
  liftUpsert(sessions, new Map(), "A").upsert(frame([ev("w1"), ev("t1")], { tailLo: 120 }));
  assert.deepEqual(shape(sessions.get("A").regions), ["gap[0,120)", "run[120,tail):w1,t1"], "the run ending at 128 overlaps the new tail and goes with it");
  sessions = new Map<string, any>([["A", { ...held, regions: [{ kind: "gap", lo: 0, hi: 32 }, { kind: "run", lo: 32, hi: 48, events: [ev("v1")] }, { kind: "gap", lo: 48, hi: 200 }, { kind: "run", lo: 200, hi: null, events: [ev("t1")] }] }]]);
  liftUpsert(sessions, new Map(), "A").upsert(frame([ev("t1")], { tailLo: 120 }));
  assert.deepEqual(shape(sessions.get("A").regions), ["gap[0,32)", "run[32,48):v1", "gap[48,120)", "run[120,tail):t1"], "a run wholly below the new tail stays");
  // the kernel's cut moved DOWN after a live append: the frame's tail is the two turns past the cut; the held tail is bounded at the
  // frame's start and the two touch, so they are one run with the held events and the new ones (the landing lab's live turn, 2026-09-13)
  sessions = new Map<string, any>([["A", { ...held, events: [ev("t1"), ev("t2")], regions: [{ kind: "gap", lo: 0, hi: 195 }, { kind: "run", lo: 195, hi: null, events: [ev("t1"), ev("t2")] }], tailLo: 195 }]]);
  liftUpsert(sessions, new Map(), "A").upsert(frame([ev("live1"), ev("live2")], { tailLo: 320 }));
  assert.deepEqual(shape(sessions.get("A").regions), ["gap[0,195)", "run[195,tail):t1,t2,live1,live2"], "the held tail keeps its events before the cut and the frame's follow: never a blank");
  assert.equal(sessions.get("A").tailLo, 195, "the merged tail starts where the held one did");
  // a frame that re-sends the held tail from the same start replaces it (the frame is authoritative for its span)
  sessions = new Map<string, any>([["A", { ...held, events: [ev("t1"), ev("t2")], regions: [{ kind: "gap", lo: 0, hi: 195 }, { kind: "run", lo: 195, hi: null, events: [ev("t1"), ev("t2")] }], tailLo: 195 }]]);
  liftUpsert(sessions, new Map(), "A").upsert(frame([ev("t1"), ev("t2"), ev("t3")], { tailLo: 195 }));
  assert.deepEqual(shape(sessions.get("A").regions), ["gap[0,195)", "run[195,tail):t1,t2,t3"], "replaced, not doubled");
  // a frame from the head (headKnown, no tailLo): one run, no gap
  sessions = new Map<string, any>([["A", { ...held }]]);
  liftUpsert(sessions, new Map(), "A").upsert(frame([ev("h1"), ev("t1")], { headKnown: true }));
  assert.deepEqual(shape(sessions.get("A").regions), ["run[0,tail):h1,t1"]);
  // a frame naming no tail start and no head: no regions until the kernel says where the tail begins
  sessions = new Map<string, any>([["A", { ...held, regions: undefined, tailLo: null }]]);
  liftUpsert(sessions, new Map(), "A").upsert(frame([ev("t1")], {}));
  assert.ok(!sessions.get("A").regions, "no regions without a tail start");
});

// ── the window ask's mark (T366, verifier medium 1) ───────────────────────────────────────────────────────────────────
// requestAround marks each ask with whether a NAVIGATION made it. The one ask that is no navigation is the keep-offset
// re-land of the reader's own row across a rebuild (relandAsk, raised only around keepPlaceAcrossWindow's landing). The
// page-reload restore of a reader's saved place arms the same keep offset, so a rule that read the keep offset refused
// the restore's window too and a reader reloaded while reading older history lost their place: that ask must land.
function liftAsk(relandAsk: boolean, keepY: number | null, anchorT: number | null, kind: string | null) {
  const rows: any[] = [], posted: any[] = [];
  const scope: Record<string, unknown> = {
    sessions: new Map<string, any>([["A", { id: "A", proto: 2, events: [] }]]),
    loadingOlder: new Set<string>(), relandAsk, pendingAnchorKeepY: keepY, pendingAnchorT: anchorT, pendingAnchorKind: kind, pendingAnchorIntent: null,
    document: { getElementById: () => null }, atBottom: () => false, landTrail: ["pointer-fetch-window"],
    scrollDiagRow: (k: string, d: any) => rows.push({ k, d }), pendingOlderAnchor: new Map(), pendingOlderKeepY: new Map(),
    showLandingNotice: () => undefined, preJumpIntoGap: () => undefined, landingNoticeSid: null, vscodeApi: { postMessage: (m: any) => posted.push(m) },
  };
  const js = liftBetween("interface WindowAsk {", "\nfunction chatWindow(msg: any) {");
  const api = liftWith(js, scope, ["requestAround", "windowAsks"]);
  (api as any).mark = (anchor: string) => { const r = (api.windowAsks as Map<string, any[]>).get("A")!.find((x) => x.anchor === anchor); return { nav: r.nav, named: r.named, t: r.t, kind: r.kind }; };   // the ask's record, the four mark fields (round eight)
  return { api, rows, posted };
}

test("the reload restore's window ask (a keep offset, no re-land) is a navigation and lands; the re-land's is refused; a card's carries its time (T366)", () => {
  const restore = liftAsk(false, 12, null, null);
  assert.equal(restore.api.requestAround("A", "u1"), true);
  assert.deepEqual(restore.api.mark("u1"), { nav: true, named: false, t: null, kind: null }, "the reader's saved place is theirs to get back: a navigation, and no click (the plain strip sentence)");
  const reland = liftAsk(true, 12, null, null);
  reland.api.requestAround("A", "u2");
  assert.deepEqual(reland.api.mark("u2"), { nav: false, named: false, t: null, kind: null }, "the re-land of the reader's own row is the one ask that is no navigation");
  const card = liftAsk(false, null, 1700000000, null);
  card.api.requestAround("A", "u3");
  assert.deepEqual(card.api.mark("u3"), { nav: true, named: true, t: 1700000000, kind: null }, "a card's or lane's frame carried the message's time: named, and the strip says the clock; the time rides to the adoption (T386)");
  const kindOnly = liftAsk(false, null, null, "prompt");
  kindOnly.api.requestAround("A", "u4");
  assert.deepEqual(kindOnly.api.mark("u4"), { nav: true, named: true, t: null, kind: "prompt" }, "a kind without a time: named, and the strip says the message was opened without a clock; the kind rides to the adoption (T386)");
  const notch = liftAsk(false, null, null, null);
  notch.api.requestAround("A", "u5");
  assert.deepEqual(notch.api.mark("u5"), { nav: true, named: true, t: null, kind: null }, "a notch, a reply chip or a comment tick arm neither kind, time nor keep offset: still a click the strip names (verifier low, round two)");
  assert.equal(restore.rows.length, 1); assert.equal(restore.rows[0].k, "regionask"); assert.equal(restore.rows[0].d.why, "landing");
  assert.deepEqual({ nav: restore.rows[0].d.nav, keep: restore.rows[0].d.keep, reland: restore.rows[0].d.reland, trail: restore.rows[0].d.trail }, { nav: true, keep: true, reland: false, trail: ["pointer-fetch-window"] }, "the ask's diagnostic row names the keep offset and the re-land flag apart, under the scroll rows' budget");
  assert.deepEqual(restore.posted, [{ type: "loadAround", id: "A", uuid: "u1" }], "the ask itself goes out after the mark");
});
