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
import { mergeWindow, keyOf, prependHead } from "./chat-window";
import { OVERLAY_KINDS, insertRun, regionsFromRuns, runsOf, splitHeldAgainstFrame, turnsBeforeTail, type Region } from "./chat-regions";

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
// the client's own injections, as render.ts tells them (the optimistic group's and the held group's uuid prefixes)
const isOptimistic = (e: any) => typeof e.uuid === "string" && e.uuid.startsWith("optimistic:");
const isHeldGroup = (e: any) => e.kind === "queued" && typeof e.uuid === "string" && e.uuid.startsWith("held:");
// render.ts's own same-transcript reading (a fork shares no uuid), lifted whole: the harness used to answer it with the Proxy's no-op, so
// PR 1860's guard 3 (which reads it) never ran here and its refusal was untestable in this file (the note on PR 1877, 2026-09-19)
const sharesAnyUuid = liftWith(liftBetween("function sharesAnyUuid(a: ChatEvent[], b: ChatEvent[]): boolean {", "\n\n/** One client-diag row"), {}, ["sharesAnyUuid"]).sharesAnyUuid;
function liftUpsert(sessions: Map<string, any>, pendingFullWhy: Map<string, string>, activeId: string | null, rows: any[] = [], asks: any[] = []) {
  const scope: Record<string, unknown> = {
    sessions, pendingFullWhy, activeId, awaitingFull: new Set<string>(), skeletonTabs: { ids: new Set() }, tabMeta: new Map(), pendingTabMeta: new Map(),
    emptyFrameDiagSent: new Set(), ledgers: new Map(), views: new Map(), pendingRewind: new Map(),
    document: { getElementById: () => null, createElement: () => fakeEl(), body: fakeEl(), querySelector: () => null },
    window: { innerHeight: 800, requestAnimationFrame: () => 0 },
    keepResidentEvents: () => false, onFull: () => false, hostOf: () => "", mergeWindow, keyOf, regionsFromRuns, runsOf, insertRun, turnsBeforeTail, stripOptimistic: () => {},
    // the merge guard's rules (2026-09-19): the real split, the real overlay set, the client's injection tells, and the diag rows recorded
    splitHeldAgainstFrame, OVERLAY_KINDS, isOptimistic, isHeldGroup, chatDiagRow: (what: string, data: any) => rows.push({ what, data }),
    // PR 1860's guard 3 onto 1877: the real same-transcript reading, its latch, the rows it posts directly and the full-frame asks it makes
    sharesAnyUuid, refusedFrameLatch: new Map(), clearRefusedLatch: () => {}, requestFullSession: (id: string, why: string) => asks.push([id, why]),
    vscodeApi: { postMessage: (m: any) => rows.push({ what: m.what, data: m.data }) },
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

// ── upsert: a full frame is authoritative for its open-ended span (the client merge guard, 2026-09-19) ─────────────────────
// A frame's tail run claims every event from tailLo to the transcript's end. A held row the frame lacks is placed by POSITION: before the
// frame's first shared key it is history the frame did not carry and stays above; at or after it, it is covered by the frame and missing
// from it (retracted, or the frame is behind) and leaves the model. Filing it above by key absence put the newest row above older ones
// (s.events t3,t1,t2: the bottom of the view showed older content and the next delta duplicated the row); the same shape with the same
// tailLo dropped the row silently. Now a frame that is behind (its last transcript key resident, a transcript row dropped after it)
// files ONE frame-behind row through the named helper, and every frame is applied as the kernel sent it.
const evU = (u: string) => ({ uuid: u, kind: "user", md: u });
const frame2 = (events: any[], extra: Record<string, unknown>) => ({ type: "session", id: "A", name: "web", proto: 2, events, headKnown: false, headTotal: null, firstUuid: events[0].uuid, lastUuid: events[events.length - 1].uuid, status: { state: "idle" }, pageTurns: 16, ...extra });
const heldTail = (events: any[], lo = 195) => ({ id: "A", name: "web", events: events.slice(), status: { state: "idle" }, proto: 2, headKnown: false, headTotal: null, firstUuid: events[0].uuid, lastUuid: events[events.length - 1].uuid, tailLo: lo,
                                                 regions: [{ kind: "gap", lo: 0, hi: lo }, { kind: "run", lo, hi: null, events: events.slice() }] });
const order = (s: any) => s.events.map((e: any) => e.uuid);
const rowData = (r: any) => ({ id: r.data.id, tailLo: r.data.tailLo, heldLo: r.data.heldLo, frameLast: r.data.frameLast, heldLast: r.data.heldLast, dropped: r.data.dropped, afterLast: r.data.afterLast, rewindPending: r.data.rewindPending });

test("a BEHIND full frame whose tailLo moved down: the resident newest row the frame lacks leaves the model instead of sitting above the frame's tail, and one frame-behind row names it", () => {
  const rows: any[] = []; const sessions = new Map<string, any>([["A", heldTail([evU("t1"), evU("t2"), evU("t3")])]]);
  liftUpsert(sessions, new Map(), "A", rows).upsert(frame2([evU("t1"), evU("t2")], { tailLo: 320 }));   // the kernel's list lacks t3: retracted, or a full built from an older list
  const s = sessions.get("A");
  assert.deepEqual(order(s), ["t1", "t2"], "the frame is authoritative for [tailLo, end): t3 goes; before the fix s.events read t3,t1,t2");
  assert.deepEqual(shape(s.regions), ["gap[0,320)", "run[320,tail):t1,t2"]);
  assert.equal(s.lastUuid, "t2", "the resident newest row is the kernel's last as of this frame");
  assert.deepEqual(rows.map((r) => r.what), ["frame-behind"], "one row, through the named helper");
  assert.deepEqual(rowData(rows[0]), { id: "A", tailLo: 320, heldLo: 195, frameLast: "t2", heldLast: "t3", dropped: 1, afterLast: 1, rewindPending: false });
});

test("a BEHIND full frame with the same tailLo drops the resident newest row as before, and now says so", () => {
  const rows: any[] = []; const sessions = new Map<string, any>([["A", heldTail([evU("t1"), evU("t2"), evU("t3")])]]);
  liftUpsert(sessions, new Map(), "A", rows).upsert(frame2([evU("t1"), evU("t2")], { tailLo: 195 }));
  assert.deepEqual(order(sessions.get("A")), ["t1", "t2"]);
  assert.deepEqual(shape(sessions.get("A").regions), ["gap[0,195)", "run[195,tail):t1,t2"]);
  assert.deepEqual(rows.map((r) => r.what), ["frame-behind"], "a behind full from the kernel is countable now; it was silent");
  assert.equal(rows[0].data.heldLo, 195);
});

test("the echo landing (the kernel's full onto a caught-up client after a send): the held echo leaves with the frame, never a phantom bubble above its tail, and no frame-behind row", () => {
  const rows: any[] = [];
  const echo = { uuid: "echo:x", kind: "user", md: "the send, echoed" };
  const sessions = new Map<string, any>([["A", heldTail([evU("t1"), evU("t2"), evU("t3"), echo])]]);
  liftUpsert(sessions, new Map(), "A", rows).upsert(frame2([evU("t3"), evU("rec"), evU("reply")], { tailLo: 197 }));   // the cut crossed a turn edge: the frame's tail is the last shared turn on
  const s = sessions.get("A");
  assert.deepEqual(order(s), ["t1", "t2", "t3", "rec", "reply"], "the record took the echo's place; the held history before the frame's first key stays above");
  assert.deepEqual(shape(s.regions), ["gap[0,195)", "run[195,tail):t1,t2,t3,rec,reply"]);
  assert.deepEqual(rows, [], "the frame carries events past the last shared key: newer than the page, not behind");
});

test("the client's own bubble in the held tail is never filed into a held run: after the shared keys it is dropped (reconcileOptimistic re-injects it at the tail), and with no shared key it is left out of the history kept above", () => {
  const rows: any[] = [];
  const bubble = { kind: "queued", bare: true, texts: [{ md: "typed", optimistic: true }], uuid: "optimistic:123" };
  let sessions = new Map<string, any>([["A", heldTail([evU("h1"), evU("t1"), evU("t2"), bubble])]]);
  liftUpsert(sessions, new Map(), "A", rows).upsert(frame2([evU("t1"), evU("t2"), evU("t3")], { tailLo: 196 }));
  let s = sessions.get("A");
  assert.deepEqual(shape(s.regions), ["gap[0,195)", "run[195,tail):h1,t1,t2,t3"], "the tail run's events carry no optimistic key (before the fix the bubble landed mid-run and stripOptimistic could not reach it there)");
  assert.deepEqual(rows, [], "a dropped bubble is no evidence of a behind frame");
  sessions = new Map<string, any>([["A", heldTail([evU("t1"), evU("t2"), bubble])]]);
  liftUpsert(sessions, new Map(), "A", rows).upsert(frame2([evU("live1"), evU("live2")], { tailLo: 320 }));   // the floor-cut shape: no shared key
  s = sessions.get("A");
  assert.deepEqual(shape(s.regions), ["gap[0,195)", "run[195,tail):t1,t2,live1,live2"], "the held history stays above the frame, the bubble does not ride in it");
});

test("a tailLo-null frame for a session holding regions drops them (no regions without a tail start) and files one regions-dropped row, so the kernel's null frames become countable", () => {
  const rows: any[] = [];
  const sessions = new Map<string, any>([["A", { ...heldTail([evU("t1"), evU("t2"), evU("t3")]), events: [evU("w1"), evU("t1"), evU("t2"), evU("t3")],
                                                 regions: [{ kind: "gap", lo: 0, hi: 96 }, { kind: "run", lo: 96, hi: 128, events: [evU("w1")] }, { kind: "gap", lo: 128, hi: 195 }, { kind: "run", lo: 195, hi: null, events: [evU("t1"), evU("t2"), evU("t3")] }] }]]);
  liftUpsert(sessions, new Map(), "A", rows).upsert(frame2([evU("t1"), evU("t2"), evU("t3"), evU("t4")], { tailLo: null }));
  const s = sessions.get("A");
  assert.ok(!s.regions, "regions-less, as the documented rule says (the merge into a key-sharing held tail is a parked decision, not this change)");
  assert.deepEqual(order(s), ["t1", "t2", "t3", "t4"], "the frame's list, whole");
  assert.deepEqual(rows.map((r) => [r.what, r.data.id, r.data.why, r.data.heldRuns, r.data.frameEvents]), [["regions-dropped", "A", "no-tail-lo", 2, 4]]);
});

test("a regions-less session holding prepended history that receives a numeric-tailLo full loses that history to the frame, and a regions-dropped row says so", () => {
  const rows: any[] = [];
  const sessions = new Map<string, any>([["A", { ...heldTail([evU("t1"), evU("t2")]), regions: undefined, tailLo: null, events: [evU("o1"), evU("o2"), evU("t1"), evU("t2")], firstUuid: "o1" }]]);   // the older wire prepended o1,o2 into a session with no regions
  liftUpsert(sessions, new Map(), "A", rows).upsert(frame2([evU("t1"), evU("t2"), evU("t3")], { tailLo: 200 }));
  const s = sessions.get("A");
  assert.deepEqual(shape(s.regions), ["gap[0,200)", "run[200,tail):t1,t2,t3"], "the frame's tail run is all the page holds now: the prepended rows had no run to live in");
  assert.deepEqual(rows.map((r) => [r.what, r.data.why, r.data.heldRuns, r.data.heldEvents, r.data.frameEvents]), [["regions-dropped", "regions-less", 0, 4, 3]]);
  // …but a fresh full for a session whose whole list the frame carries (the everyday re-send) files nothing
  const quiet: any[] = [];
  const s2 = new Map<string, any>([["A", { ...heldTail([evU("t1"), evU("t2")]), regions: undefined, tailLo: null }]]);
  liftUpsert(s2, new Map(), "A", quiet).upsert(frame2([evU("t1"), evU("t2"), evU("t3")], { tailLo: 200 }));
  assert.deepEqual(quiet, []);
});

test("guard 3 executed with the real sharesAnyUuid in scope (PR 1860 onto 1877): a proto-2 full frame whose numeric tailLo claims a held run its content does not carry is refused, the held regions and events stand, one full-frame-desync row and one gap ask; the frame that re-carries the run from tailLo applies", () => {
  const rows: any[] = [], asks: any[] = [];
  const sessions = new Map<string, any>([["A", heldTail([evU("t1"), evU("t2"), evU("t3")])]]);
  liftUpsert(sessions, new Map(), "A", rows, asks).upsert(frame2([evU("t3"), evU("t4")], { tailLo: 195 }));   // claims [195, end) but its content starts at t3: t1 and t2 would drop whole across a hole
  const s = sessions.get("A");
  assert.deepEqual(order(s), ["t1", "t2", "t3"], "refused: the held rows stand (with the Proxy's no-op sharesAnyUuid in scope the guard never ran and the frame dropped t1 and t2)");
  assert.deepEqual(shape(s.regions), ["gap[0,195)", "run[195,tail):t1,t2,t3"], "the held regions stand too");
  assert.deepEqual(rows.map((r) => [r.what, r.data.why, r.data.tailLo]), [["full-frame-desync", "would-drop-held", 195]], "one row names the refusal");
  assert.deepEqual(asks, [["A", "gap"]], "one ask for a frame the merge can place");
  // the frame that answers it re-carries the run from tailLo: its split.before is empty, so 1877's merge lands it (and t4 arrives)
  const rows2: any[] = [], asks2: any[] = [];
  liftUpsert(sessions, new Map(), "A", rows2, asks2).upsert(frame2([evU("t1"), evU("t2"), evU("t3"), evU("t4")], { tailLo: 195 }));
  assert.deepEqual([order(sessions.get("A")), shape(sessions.get("A").regions), rows2, asks2], [["t1", "t2", "t3", "t4"], ["gap[0,195)", "run[195,tail):t1,t2,t3,t4"], [], []]);
});

// ── the older wire's wait (the follow-up of 2026-09-19, after the client merge guard): a regions-less proto-2 session's landing rides loadOlder ──
// The window road shows the one landing notice for a navigation's ask, hides it at the reply, carries the click's time and kind in the ask's
// record to the landing, and counts a live landing at the socket's death by that notice. The older wire, which every regions-less navigation
// now takes, did none of these: a reply chip's or the reload restore's jump waited with nothing on screen, a socket death lost it silently,
// and chatHead's re-arm nulled anchorT and kind so the pointer-exact row filed without them.
test("waitOnOlderWire (the older wire's one arm): the landing armed, the trail's word, the click's time and kind marked for chatHead, and the window road's notice for a navigation; a re-attempt on the anchor keeps the first mark, a click on another anchor replaces it, a keep-offset re-land shows nothing", () => {
  const lift = (scope: Record<string, unknown>) => liftWith(liftBetween("function waitOnOlderWire(sid: string, uuid: string): false {", "\n// Scroll the thread to the event carrying"), scope, ["waitOnOlderWire"]).waitOnOlderWire;
  const shows: any[] = [];
  const scope: Record<string, unknown> = { relandAsk: false, pendingAnchorT: 1700000000, pendingAnchorKind: null, pendingAnchorIntent: "user", landTrail: [], showLandingNotice: (sid: string, t: number | null) => shows.push([sid, t]), pendingOlderMark: new Map(), pendingAnchor: null, anchorPendingOlder: false };
  const wait = lift(scope);
  assert.equal(wait("A", "u96"), false, "the attempt does not land this pass");
  assert.deepEqual([scope.pendingAnchor, scope.anchorPendingOlder, scope.landTrail], ["u96", true, ["pointer-fetch-older"]], "armed for chatHead, as before");
  assert.deepEqual(shows, [["A", 1700000000]], "the wait state a window landing shows (before the fix a reply chip's or the reload restore's jump on this wire showed nothing)");
  assert.deepEqual(Array.from(scope.pendingOlderMark as Map<string, unknown>), [["A", { uuid: "u96", t: 1700000000, kind: "user" }]], "the click's time and kind ride the fetch (the kind as requestAround reads it: the kind, else the intent)");
  // the seek's re-attempt pass re-arms the anchor with no time: the first attempt's mark stands and the notice keeps its clock
  scope.pendingAnchorT = null; scope.pendingAnchorIntent = null;
  wait("A", "u96");
  assert.deepEqual([Array.from(scope.pendingOlderMark as Map<string, unknown>), shows[shows.length - 1]], [[["A", { uuid: "u96", t: 1700000000, kind: "user" }]], ["A", 1700000000]]);
  // a click on another anchor while the fetch is in flight (the re-point arm) replaces the mark
  wait("A", "u77");
  assert.deepEqual(Array.from(scope.pendingOlderMark as Map<string, unknown>), [["A", { uuid: "u77", t: null, kind: null }]]);
  const relandShows: number[] = [];
  const reland: Record<string, unknown> = { relandAsk: true, pendingAnchorT: null, pendingAnchorKind: null, pendingAnchorIntent: null, landTrail: [], showLandingNotice: () => relandShows.push(1), pendingOlderMark: new Map(), pendingAnchor: null, anchorPendingOlder: false };
  lift(reland)("A", "u5");
  assert.deepEqual([relandShows, reland.landTrail], [[], ["pointer-fetch-older"]], "the reader's own row re-landed across a rebuild is no navigation: no notice");
});

test("chatHead's re-arm of the older wire's landing carries the click's time and kind from the fetch's mark and leaves the wait's notice up across the reply (the pass re-arms the wire and re-shows it in place); a mark another click left is ignored; a scroll-back's arrival carries neither and leaves a window landing's notice standing; a fault, a stale reply and a missing anchor end the wait with the notice and a word, and the reader is told unless a seek stands behind the landing", () => {
  const run = (opts: { keepY?: number; mark?: any; fault?: boolean; before?: string; missing?: boolean; rec?: any; seek?: any }) => {
    const hides: number[] = [], shows: number[] = [], toasts: string[] = [], seekEnds: number[] = [], fullAsks: any[] = [];
    const s: any = { id: "A", proto: 2, events: [evU("t250"), evU("t251")], firstUuid: "t250", headKnown: false, headTotal: null };
    const scope: Record<string, unknown> = {
      sessions: new Map([["A", s]]), loadingOlder: new Set(["A"]), pendingOlderAnchor: new Map([["A", "u96"]]),
      pendingOlderKeepY: new Map<string, number>(opts.keepY != null ? [["A", opts.keepY]] : []), pendingOlderMark: new Map<string, unknown>(opts.mark ? [["A", opts.mark]] : []),
      landingNoticeSid: "A", liveWindowAsk: () => opts.rec ?? null, seek: opts.seek ?? null,   // the notice's owner, if a window ask's record is live; the seek behind the landing, if any (the review of 2026-09-19, round two)
      hideLandingNotice: () => hides.push(1), showActive: () => shows.push(1), landToast: (t: string) => toasts.push(t), clearSeek: () => seekEnds.push(1), requestFullSession: (id: string, why: string) => fullAsks.push([id, why]),
      activeId: "A", views: new Map(), pendingAnchor: null, pendingAnchorIntent: "user", pendingAnchorT: null, pendingAnchorKind: null, pendingAnchorKeepY: null, flashedAnchor: "x", anchorPendingOlder: true, landTrail: [],
      prependHead, keyOf, isOptimistic, isHeldGroup,
    };
    const js = liftBetween("function chatHead(msg: any) {", "\n// Fetch the next older history chunk");
    const msg = opts.fault ? { type: "chatHead", id: "A", fault: true }
      : opts.missing ? { type: "chatHead", id: "A", beforeUuid: "t250", missing: true, events: [] }
      : { type: "chatHead", id: "A", beforeUuid: opts.before ?? "t250", events: [evU("o1"), evU("o2")], more: true };
    liftWith(js, scope, ["chatHead"]).chatHead(msg);
    return { scope, hides, shows, toasts, seekEnds, fullAsks, s };
  };
  const mark = { uuid: "u96", t: 1700000000, kind: "user" };
  const deep = run({ mark });
  assert.deepEqual(order(deep.s), ["o1", "o2", "t250", "t251"], "the chunk is prepended");
  assert.deepEqual([deep.scope.pendingAnchor, deep.scope.pendingAnchorT, deep.scope.pendingAnchorKind, deep.scope.pendingAnchorIntent, deep.scope.pendingAnchorKeepY, deep.scope.flashedAnchor], ["u96", 1700000000, "user", null, null, null],
                   "re-armed with the click's time and kind (before the fix both were null, so the pointer-exact row of every regions-less navigation filed without them)");
  assert.deepEqual([deep.hides, deep.shows], [[], [1]], "the notice stays up across the reply: the pass re-arms the wire and waitOnOlderWire re-shows it in place (a hide here first, with compact mode's deferred build pass between the two, opened a frame in which onWireDown counted no landing; the review of 2026-09-19, round two)");
  assert.equal((deep.scope.pendingOlderMark as Map<string, unknown>).size, 0, "the mark is consumed with the fetch's other records");
  const stale = run({ mark: { uuid: "u77", t: 1700000000, kind: "user" } });
  assert.deepEqual([stale.scope.pendingAnchor, stale.scope.pendingAnchorT, stale.scope.pendingAnchorKind], ["u96", null, null], "a mark another click left names another anchor: ignored, as before");
  const back = run({ keepY: 12, rec: { anchor: "w1", nav: true, named: true, t: null, kind: null, origin: null, gap: { lo: 96, hi: 128 }, cancelled: false } });
  assert.deepEqual([back.scope.pendingAnchor, back.scope.pendingAnchorT, back.scope.pendingAnchorKind, back.scope.pendingAnchorKeepY, back.hides], ["u96", null, null, 12, []], "a scroll-back's arrival is position preservation, and a notice showing then is a window landing's (its live ask's record owns it): it stands");
  const fault = run({ mark, fault: true });
  assert.deepEqual([fault.hides, fault.scope.pendingAnchor, fault.scope.anchorPendingOlder, fault.toasts, fault.seekEnds, fault.scope.landTrail], [[1], null, false, ["the history could not be loaded just now"], [1], ["head-fault"]], "the fault ends the wait with its notice and its own word");
  // a reply whose beforeUuid is no longer the resident head (a full frame re-based the events under the ask) lands nothing, so the landing it
  // carried is dropped: the wait ends with the notice, its word in the trail, and the reader told as the fault tells them (before the fold
  // the notice went down and nothing was said, where before the notice this wire showed nothing at all)
  const gone = run({ mark, before: "t999" });
  assert.deepEqual(order(gone.s), ["t250", "t251"], "a stale chunk is not prepended, as before");
  assert.deepEqual([gone.hides, gone.shows, gone.scope.anchorPendingOlder, gone.scope.pendingAnchor, gone.scope.landTrail, gone.toasts, gone.seekEnds, (gone.scope.pendingOlderAnchor as Map<string, unknown>).size],
                   [[1], [], false, null, ["head-stale"], ["the history could not be loaded just now"], [], 0], "a stale reply ends the wait with the notice, its word and the reader told; no seek stood behind the landing, so none ends");
  const missing = run({ mark, missing: true });
  assert.deepEqual([missing.hides, missing.scope.landTrail, missing.toasts, missing.fullAsks], [[1], ["head-missing"], ["the history could not be loaded just now"], [["A", "gap"]]], "a missing anchor (a /clear, a fork) ends the wait with its own word and re-bases, as before");
  // a seek stands behind the landing (setActive's durable seek): it re-arms from its own record on the next pass and its backstop speaks for
  // it, so the word is filed and no toast interrupts
  const seekBacked = run({ mark, before: "t999", seek: { sid: "A", uuid: "u96", kind: null, t: null, from0: null } });
  assert.deepEqual([seekBacked.hides, seekBacked.scope.landTrail, seekBacked.toasts, seekBacked.seekEnds], [[1], ["head-stale"], [], []], "a seek-backed landing's stale reply: the word, the notice down, no toast, the seek standing");
});

test("the notice's click on the older wire's landing (no ask record) releases the fetch's claim through the real releaseSeekFetch, so the chunk arrives as a pure prepend re-anchored on the reader's own row and chatHead re-arms nothing but that row; the cancel row names the anchor, time and kind from the fetch's mark (the page's wait state holds them nowhere else); a window landing's cancel marks its record and releases no fetch", () => {
  const run = (rec: any) => {
    const posted: any[] = [], hides: number[] = [], seekEnds: number[] = [], shows: number[] = [];
    const s: any = { id: "A", proto: 2, events: [evU("t250"), evU("t251")], firstUuid: "t250", headKnown: false, headTotal: null };
    const content = { id: "content" };
    const scope: Record<string, unknown> = {
      landingNoticeSid: "A", liveWindowAsk: () => rec, hideLandingNotice: () => { hides.push(1); scope.landingNoticeSid = null; }, views: new Map([["A", { el: fakeEl() }]]), landTrail: [],
      vscodeApi: { postMessage: (m: any) => posted.push(m) }, clearSeek: () => seekEnds.push(1), gapHasAsk: () => false, seek: null,
      sessions: new Map([["A", s]]), activeId: "A", document: { getElementById: (id: string) => (id === "content" ? content : null) },
      captureScrollAnchor: () => ({ uuid: "t250", y: 40 }),   // the row under the viewport top: where the reader stands
      loadingOlder: new Set<string>(rec ? [] : ["A"]), pendingOlderAnchor: new Map<string, string>(rec ? [] : [["A", "u96"]]), pendingOlderKeepY: new Map<string, number>(),
      pendingOlderMark: new Map<string, unknown>(rec ? [] : [["A", { uuid: "u96", t: 1700000000, kind: "user" }]]),
      // the page's wait state at the click (the review of 2026-09-19, round two): landActive nulled the pending fields at the end of the
      // pass that armed the wait, so the fetch's mark alone names the landing
      pendingAnchor: null, pendingAnchorIntent: null, pendingAnchorT: null, pendingAnchorKind: null, pendingAnchorKeepY: null, anchorPendingOlder: true, flashedAnchor: null,
      showActive: () => shows.push(1), landToast: () => {}, requestFullSession: () => {},
      prependHead, keyOf, isOptimistic, isHeldGroup,
    };
    const js = liftBetween("function releaseSeekFetch(sid: string): void {", "\nfunction cancelSeek(): void {")
      + liftBetween("function cancelLanding(): void {", "\n/** The view jumps STRAIGHT") + liftBetween("function chatHead(msg: any) {", "\n// Fetch the next older history chunk");
    const api = liftWith(js, scope, ["cancelLanding", "chatHead"]);
    api.cancelLanding();
    const afterCancel = { claim: Array.from(scope.pendingOlderAnchor as Map<string, string>), keepY: Array.from(scope.pendingOlderKeepY as Map<string, number>), mark: (scope.pendingOlderMark as Map<string, unknown>).size,
                          hides: hides.slice(), seekEnds: seekEnds.slice(), pendingAnchor: scope.pendingAnchor, anchorPendingOlder: scope.anchorPendingOlder, trail: (scope.landTrail as string[]).slice() };
    return { posted, hides, shows, afterCancel, scope, s, chatHead: api.chatHead };
  };
  const older = run(null);
  assert.deepEqual([older.afterCancel.claim, older.afterCancel.keepY, older.afterCancel.mark], [[["A", "t250"]], [["A", 40]], 0],
                   "the older wire's claim is released the way the seek's cancel releases it: the in-flight fetch is re-pointed at the reader's own row and offset, and the mark goes with the claim (before the fix the cancel left the claim, and chatHead re-armed the landing the reader had just canceled)");
  assert.deepEqual([older.afterCancel.hides, older.afterCancel.seekEnds, older.afterCancel.pendingAnchor, older.afterCancel.anchorPendingOlder, older.afterCancel.trail], [[1], [1], null, false, ["cancelled"]]);
  assert.deepEqual(older.posted.map((m) => [m.type, m.cancelled, m.anchor, m.anchorT, m.kind]), [["locateDiag", true, "u96", 1700000000, "user"]],
                   "the cancel row names the landing from the fetch's mark, read before the release deletes it (the pending fields are null at the click, so before the fold the row carried no anchor, time or kind)");
  older.chatHead({ type: "chatHead", id: "A", beforeUuid: "t250", events: [evU("o1"), evU("o2")], more: true });
  assert.deepEqual(order(older.s), ["o1", "o2", "t250", "t251"], "the chunk is prepended");
  assert.deepEqual([older.scope.pendingAnchor, older.scope.pendingAnchorKeepY, older.scope.pendingAnchorT, older.scope.pendingAnchorKind, older.hides, older.shows], ["t250", 40, null, null, [1], [1]],
                   "…re-anchored on the reader's own row at its offset (position preservation), never the canceled target; no time or kind ride a scroll-back's arrival, and nothing further is hidden");
  const rec = { anchor: "u96", nav: true, cancelled: false, origin: 3200, gap: { lo: 96, hi: 128 } };
  const win = run(rec);
  assert.deepEqual([win.afterCancel.claim, rec.cancelled, rec.origin, rec.gap, win.posted.map((m) => [m.anchor, m.anchorT, m.kind])], [[], true, null, null, [["u96", undefined, undefined]]],
                   "a window landing's cancel marks its record and names its anchor from it; no fetch is in flight beside a live ask, so none is released");
});

// ── the seek's own release paths end the older wire's wait (the review of 2026-09-19, round two) ──────────────────────────────────
// The backstop (failSeek), the seek note's cancel (cancelSeek) and a time-only navigation all release the older fetch's claim through
// releaseSeekFetch and never hid the notice waitOnOlderWire showed: on the older wire it stood with no ask behind it (beside the backstop's
// own toast) until a click, a later landing's reply or the socket's death, and the chunk's chatHead, reading the released claim as a
// scroll-back's, hid nothing either. The release brings the notice down; a window landing's notice is its record's and stands.
test("releaseSeekFetch ends the older wire's wait with its notice: the backstop and the seek note's cancel hide it and drop the claim, the chunk's chatHead hides nothing further and re-arms nothing; a window landing's notice stands through the release", () => {
  const run = (opts: { path: "fail" | "cancel"; rec?: any }) => {
    const hides: number[] = [], toasts: string[] = [], seekEnds: number[] = [], shows: number[] = [];
    const s: any = { id: "A", name: "web", proto: 2, events: [evU("t250"), evU("t251")], firstUuid: "t250", headKnown: false, headTotal: null };
    const scope: Record<string, unknown> = {
      seek: { sid: "A", uuid: "u96", kind: null, t: null, from0: null }, sessions: new Map([["A", s]]), activeId: "A", views: new Map(),
      landingNoticeSid: "A", liveWindowAsk: () => opts.rec ?? null, hideLandingNotice: () => { hides.push(1); scope.landingNoticeSid = null; },
      loadingOlder: new Set(["A"]), pendingOlderAnchor: new Map([["A", "u96"]]), pendingOlderKeepY: new Map<string, number>(), pendingOlderMark: new Map([["A", { uuid: "u96", t: 1700000000, kind: "user" }]]),
      document: { getElementById: () => null },   // nothing at the viewport top in this world: the claim is dropped, not converted
      pendingAnchor: null, pendingAnchorIntent: null, pendingAnchorT: null, pendingAnchorKind: null, pendingAnchorKeepY: null, flashedAnchor: null, anchorPendingOlder: true, landTrail: [],
      clearSeek: () => seekEnds.push(1), landToast: (t: string) => toasts.push(t), notifyShell: () => {}, showActive: () => shows.push(1), requestFullSession: () => {},
      prependHead, keyOf, isOptimistic, isHeldGroup,
    };
    const js = liftBetween("function releaseSeekFetch(sid: string): void {", "\n/** The pane-local seek notice") + liftBetween("function chatHead(msg: any) {", "\n// Fetch the next older history chunk");
    const api = liftWith(js, scope, ["failSeek", "cancelSeek", "chatHead"]);
    if (opts.path === "fail") api.failSeek(); else api.cancelSeek();
    const afterRelease = { hides: hides.slice(), toasts: toasts.slice(), seekEnds: seekEnds.slice(), claim: (scope.pendingOlderAnchor as Map<string, unknown>).size, mark: (scope.pendingOlderMark as Map<string, unknown>).size, anchorPendingOlder: scope.anchorPendingOlder };
    api.chatHead({ type: "chatHead", id: "A", beforeUuid: "t250", events: [evU("o1"), evU("o2")], more: true });
    return { scope, hides, toasts, shows, afterRelease, s };
  };
  const fail = run({ path: "fail" });
  assert.deepEqual([fail.afterRelease.hides, fail.afterRelease.claim, fail.afterRelease.mark, fail.afterRelease.anchorPendingOlder, fail.afterRelease.seekEnds, fail.afterRelease.toasts], [[1], 0, 0, false, [1], ["couldn't locate this in the transcript"]],
                   "the backstop ends the wait with its notice (before the fold the notice stood beside the backstop's toast with no ask behind it, until a click or the socket's death)");
  assert.deepEqual([order(fail.s), fail.hides, fail.scope.pendingAnchor, fail.shows], [["o1", "o2", "t250", "t251"], [1], null, [1]], "the chunk arrives as a pure prepend: chatHead hides nothing further and re-arms nothing");
  const cancel = run({ path: "cancel" });
  assert.deepEqual([cancel.afterRelease.hides, cancel.afterRelease.claim, cancel.afterRelease.toasts, cancel.hides, cancel.scope.pendingAnchor], [[1], 0, [], [1], null], "the seek note's cancel takes the same road, without the toast");
  const win = run({ path: "fail", rec: { anchor: "w1", nav: true, named: true, t: null, kind: null, origin: null, gap: { lo: 96, hi: 128 }, cancelled: false } });
  assert.deepEqual([win.afterRelease.hides, win.hides], [[], []], "a window landing's notice is its live ask's record's: the release leaves it standing");
});

// ── insertRegionRun, chatTurns, chatWindow: no run is minted with a lo the kernel did not name (2026-09-19) ────────────────────
// A session with no regions (a proto-2 frame whose tailLo the kernel could not name) used to get a tail run INVENTED at turn 0 the
// moment a page or a window arrived; a non-overlapping older window then touched that run, mergeRuns found no key overlap and no
// lower lo, and the OLDER window landed AFTER the newest events (t250,t251,t252,w96,w97: the confirmed mis-order, permanent for an
// idle session). The insert now refuses and returns false, and its callers rebuild nothing on a refusal.
const REGIONS_JS = () => liftBetween("function eventsFromRegions(s: Session): void {", "\nfunction itemFirstEvent(")
  + liftBetween("function insertRegionRun(s: Session, lo: number, hi: number, events: ChatEvent[])", "\nconst gapLoading");
function liftInsertRegionRun() {
  return liftWith(REGIONS_JS(), { insertRun, regionsFromRuns, keyOf, isOptimistic, isHeldGroup }, ["insertRegionRun"]);
}

test("insertRegionRun refuses a window for a session with no regions (false, nothing touched) and inserts as before for one with regions", () => {
  const api = liftInsertRegionRun();
  const bare: any = { id: "A", proto: 2, events: [evU("t250"), evU("t251"), evU("t252")], regions: undefined, tailLo: null, headKnown: false, firstUuid: "t250", headTotal: null };
  const placed = api.insertRegionRun(bare, 96, 128, [evU("w96"), evU("w97")]);
  assert.deepEqual(order(bare), ["t250", "t251", "t252"], "the events stand; before the fix the window landed after the newest rows (t250,t251,t252,w96,w97)");   // the misplacement first: the case's red is the defect, not the old signature's void return
  assert.equal(bare.regions, undefined, "no run minted at turn 0"); assert.equal(bare.headKnown, false); assert.equal(bare.firstUuid, "t250");
  assert.equal(placed, false, "no lo the kernel named for the tail: the window cannot be placed");
  const withRegions: any = { id: "A", proto: 2, events: [evU("t1")], regions: regionsFromRuns([{ kind: "run", lo: 200, hi: null, events: [evU("t1")] }]), tailLo: 200, headKnown: false };
  assert.equal(api.insertRegionRun(withRegions, 96, 128, [evU("w1")]), true);
  assert.deepEqual(shape(withRegions.regions), ["gap[0,96)", "run[96,128):w1", "gap[128,200)", "run[200,tail):t1"]);
  assert.deepEqual(order(withRegions), ["w1", "t1"]);
});

test("chatTurns on a refused page: the ask is freed, no rebuild, the trail says turns-unplaced and a locateDiag row of kind unplaced is filed; a placed page rebuilds as before", () => {
  const run = (session: any) => {
    const posted: any[] = [], landTrail: string[] = [], fills: any[] = [], v: any = { el: fakeEl(), rendered: 7, stale: false };
    const gapLoading = new Set<string>(["A:96:128"]);
    const scope: Record<string, unknown> = { sessions: new Map([["A", session]]), gapLoading, gapKey: (sid: string, lo: number, hi: number) => sid + ":" + lo + ":" + hi, landTrail,
      vscodeApi: { postMessage: (m: any) => posted.push(m) }, views: new Map([["A", v]]), activeId: "A", stripOptimistic: () => {}, reconcileOptimistic: () => {},
      schedulePrebuild: () => {}, fillInPlace: (sid: string, vv: any) => fills.push(sid), insertRun, regionsFromRuns, keyOf, isOptimistic, isHeldGroup };
    const js = REGIONS_JS() + liftBetween("function chatTurns(msg: any): void {", "\n/** A fill moves nothing");
    liftWith(js, scope, ["chatTurns"]).chatTurns({ type: "chatTurns", id: "A", span: [96, 128], events: [evU("w96"), evU("w97")] });
    return { posted, landTrail, fills, v, gapLoading };
  };
  const bare = { id: "A", proto: 2, events: [evU("t250"), evU("t251"), evU("t252")], regions: undefined, tailLo: null, headKnown: false, firstUuid: "t250" };
  const r = run(bare);
  assert.equal(r.gapLoading.size, 0, "the page ask is cleared either way");
  assert.deepEqual(order(bare), ["t250", "t251", "t252"], "nothing inserted");
  assert.deepEqual([r.v.rendered, r.v.stale, r.fills], [7, false, []], "no rebuild for a reply that changed nothing (cards and views move on new information)");
  assert.deepEqual(r.landTrail, ["turns-unplaced"]);
  assert.deepEqual(r.posted.map((m) => [m.type, m.kind, m.ok]), [["locateDiag", "unplaced", false]]);
  const held = { id: "A", proto: 2, events: [evU("t1")], regions: regionsFromRuns([{ kind: "run", lo: 200, hi: null, events: [evU("t1")] }]), tailLo: 200, headKnown: false };
  const ok = run(held);
  assert.deepEqual(order(held), ["w96", "w97", "t1"]);
  assert.deepEqual([ok.v.rendered, ok.v.stale, ok.fills, ok.landTrail, ok.posted], [0, true, ["A"], [], []], "a placed page rebuilds in place as before");
});

test("chatWindow on a refused window: the pre-jump origin is put back (land-cancel), the ask record is consumed, the trail says window-unplaced with a locateDiag row of kind unplaced, no toast and no end of the seek; a landing no seek covers is re-armed from the ask's record and the pass runs now (the next attempt takes the older wire), a seek-backed one is left to the seek, a dead end with no older wire is filed and not re-asked", () => {
  const run = (seek: any, session: Record<string, unknown> = {}) => {
    const posted: any[] = [], landTrail: string[] = [], writes: any[] = [], toasts: string[] = [], seekEnds: number[] = [], shows: number[] = [];
    const content = { scrollTop: 900, scrollHeight: 5000, clientHeight: 600 };
    const bare: any = { id: "A", proto: 2, events: [evU("t250"), evU("t251"), evU("t252")], regions: undefined, tailLo: null, headKnown: false, firstUuid: "t250", ...session };
    const scope: Record<string, unknown> = {
      sessions: new Map([["A", bare]]), loadingOlder: new Set<string>(), relandAsk: false, pendingAnchorKeepY: null, pendingAnchorT: 1700000000, pendingAnchorKind: "user", pendingAnchorIntent: null,
      pendingAnchor: "u96", anchorPendingOlder: true, activeId: "A", landingNoticeSid: "A", hideLandingNotice: () => {}, landTrail, seek, flashedAnchor: null,
      document: { getElementById: (id: string) => (id === "content" ? content : null) }, atBottom: () => false,
      scrollDiagRow: () => {}, pendingOlderAnchor: new Map(), pendingOlderKeepY: new Map(), showLandingNotice: () => undefined, preJumpIntoGap: () => undefined,
      vscodeApi: { postMessage: (m: any) => posted.push(m) }, writeScroll: (c: any, top: number, writer: string) => writes.push([top, writer]), landToast: (t: string) => toasts.push(t), clearSeek: () => seekEnds.push(1),
      stripOptimistic: () => {}, reconcileOptimistic: () => {}, views: new Map(), fillInPlace: () => {}, schedulePrebuild: () => {}, showActive: () => shows.push(1),
      insertRun, regionsFromRuns, keyOf, isOptimistic, isHeldGroup,
    };
    const js = REGIONS_JS() + liftBetween("function olderOnServer(s: Session): boolean {", "\n// A deep-link anchor past the resident run")
      + liftBetween("interface WindowAsk {", "\nfunction chatWindow(msg: any) {") + liftBetween("function chatWindow(msg: any) {", "\n// ── (the detached client's way back");
    const api = liftWith(js, scope, ["requestAround", "chatWindow", "windowAsks"]);
    assert.equal(api.requestAround("A", "u96"), true);
    (api.windowAsks as Map<string, any[]>).get("A")![0].origin = 3200;   // the pre-jump's origin, as preJumpIntoGap records it
    // landActive ends the pass that asked the window by nulling the armed landing (the notice stays the live ask's): what the reply finds
    scope.pendingAnchor = null; scope.pendingAnchorT = null; scope.pendingAnchorKind = null; scope.anchorPendingOlder = false;
    api.chatWindow({ type: "chatWindow", id: "A", anchor: "u96", span: [96, 128], events: [evU("u96"), evU("w97")] });
    assert.deepEqual(order(bare), ["t250", "t251", "t252"], "nothing inserted: the regions went between the ask and its reply");
    assert.equal(bare.regions, undefined);
    assert.deepEqual(writes, [[3200, "land-cancel"]], "the reader goes back where the pre-jump found them");
    assert.equal((api.windowAsks as Map<string, any[]>).get("A"), undefined, "the ask record is consumed");
    assert.deepEqual(landTrail, ["window-unplaced"]);
    assert.deepEqual(posted.filter((m) => m.type === "locateDiag").map((m) => [m.kind, m.ok, m.anchor]), [["unplaced", false, "u96"]]);
    assert.deepEqual([toasts, seekEnds], [[], []], "no toast and the seek stands: the next attempt takes the older wire and lands the anchor");
    return { shows, scope };
  };
  // no seek covers the landing (a notch's or a comment tick's jump, the reload restore: only setActive arms a seek): re-armed from the
  // record, with the click's time and kind as a placed navigation's landing is, and the pass runs now; before the re-arm the click ended
  // here with the pre-jump undone and no next attempt (the review of 2026-09-19)
  const bareLanding = run(null);
  assert.deepEqual(bareLanding.shows, [1], "showActive runs the landing pass now: its scrollToAnchor takes the older wire for a regions-less session");
  assert.deepEqual([bareLanding.scope.pendingAnchor, bareLanding.scope.pendingAnchorT, bareLanding.scope.pendingAnchorKind, bareLanding.scope.pendingAnchorKeepY, bareLanding.scope.anchorPendingOlder],
                   ["u96", 1700000000, "user", null, false], "the landing is re-armed from the ask's record");
  // a seek covers it (setActive's durable seek): landActive re-arms from the seek on every pass, so the refusal leaves the arming to it
  const seekBacked = run({ sid: "A", uuid: "u96", kind: null, t: null, from0: null });
  assert.deepEqual([seekBacked.shows, seekBacked.scope.pendingAnchor], [[], null], "a seek-backed landing is left to the seek's own re-arm");
  // no seek and no older wire to take (the head is known, no regions): a re-arm would ask the same window again and the two would ping-pong,
  // so the dead end keeps its row and ends here
  const deadEnd = run(null, { headKnown: true });
  assert.deepEqual([deadEnd.shows, deadEnd.scope.pendingAnchor], [[], null], "no re-arm without a wire the next attempt can take");
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
