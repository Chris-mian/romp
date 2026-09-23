// The send-landing watch's WIRING (send-landing.ts, 2026-09-23), pinned and executed: its two ends sit around the ONE dispatch chain
// every frame takes, LAND_FRAME_TYPES names every frame whose handler writes a session's resident events (derived from the source,
// so a new writer fails here until it is classified), the send and the reconcile's verdicts reach the watch, and, executed, the
// instruments write nothing and call nothing but the diag post: the real upsert run with the watch around it leaves the same session
// state and makes the same calls, in the same order, as without it. Synthetic events only.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { createRequire } from "node:module";
import { LandingWatch } from "./send-landing";
import { ScrollDiagBudget } from "./scroll-write";
import { mergeWindow, keyOf } from "./chat-window";
import { OVERLAY_KINDS, insertRun, regionsFromRuns, runsOf, splitHeldAgainstFrame, turnsBeforeTail } from "./chat-regions";
import { frameOlder, droppedLandedHuman, dropsLandedRow } from "./frame-guard";

const requireCjs = createRequire(__filename);
const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const SID = "11111111-2222-4333-8444-000000000401";

// ── the source's own statements ────────────────────────────────────────────────────────────────────────────────────────
/** Every top-level function of render.ts whose body writes a session's events (or mints a session), by name. */
function eventWriters(): Map<string, string> {
  const re = /(\.events\s*=[^=>])|(\.events\.length\s*=[^=])|(\.events\.(push|splice|unshift|pop|shift)\()|(\.events\[[^\]]+\]\s*=[^=])|(sessions\.set\()/;
  const out = new Map<string, string>();
  let fn = "(top)";
  for (const line of RENDER.split("\n")) {
    const m = /^(?:export )?(?:async )?function (\w+)/.exec(line);
    if (m) fn = m[1];
    if (re.test(line.replace(/\/\/.*$/, "")) && !out.has(fn)) out.set(fn, line.trim().slice(0, 80));
  }
  return out;
}
function body(name: string, must = true): string {
  const a = RENDER.indexOf("\nfunction " + name + "(");
  if (a < 0 && !must) return "";
  assert.ok(a >= 0, "function " + name + " is in render.ts");
  const b = RENDER.indexOf("\n}\n", a);
  return RENDER.slice(a, b);
}
const LAND_TYPES = (() => {
  const m = /const LAND_FRAME_TYPES: ReadonlySet<string> = new Set\(\[([^\]]*)\]\);/.exec(RENDER);
  assert.ok(m, "LAND_FRAME_TYPES is declared");
  return new Set(m![1].split(",").map((s) => s.trim().replace(/^"|"$/g, "")));
})();

test("every function that writes a session's events is classified: a frame path the watch covers, the page's own injection, or a new tab's mint", () => {
  const FRAME = ["upsert", "update", "chatTail", "chatHead", "eventsFromRegions", "regionsAbsorbTail", "applySubagentFrame"];
  const INJECTION = ["reconcileOptimistic", "reconcileOptimisticInner", "stripOptimistic", "reconcileHeldCopies", "hideQueuedCopy"];   // optimistic/held groups and hide marks: never a landed human turn (frame-guard.ts isLandedHuman)
  const MINT = ["openProvisional", "showReviveLoader", "openSubagentView"];                                                             // a new empty tab, before any frame
  assert.deepEqual([...eventWriters().keys()].sort(), [...FRAME, ...INJECTION, ...MINT].sort(),
                   "a new writer of s.events: classify it here, and if it applies server events, add its frame to LAND_FRAME_TYPES");
  // the region writers are reached only from frame handlers the watch covers
  for (const helper of ["eventsFromRegions", "insertRegionRun", "regionsAbsorbTail"]) {
    const callers = new Set<string>();
    let fn = "(top)";
    for (const line of RENDER.split("\n")) {
      const m = /^(?:export )?(?:async )?function (\w+)/.exec(line);
      if (m) fn = m[1];
      if (new RegExp("\\b" + helper + "\\(").test(line) && !new RegExp("function " + helper + "\\(").test(line)) callers.add(fn);
    }
    for (const c of callers) assert.ok(["insertRegionRun", "chatTail", "chatTurns", "chatWindow"].includes(c), helper + " is called from " + c);
  }
});

test("LAND_FRAME_TYPES is exactly the frames whose dispatched handler applies events (the subagent viewer aside, a tab nobody sends to)", () => {
  const start = RENDER.indexOf("const landSnap = landingBefore(m);"), end = RENDER.indexOf("landingAfter(m, landSnap);");
  const chain = RENDER.slice(start, end);
  const arms = new Map<string, string>();
  for (const m of chain.matchAll(/(?:if|else if) \(m\.type === "(\w+)"\) (\w+)\(m\);/g)) arms.set(m[1], m[2]);
  const applies = new Set<string>();
  for (const [type, fn] of arms) {
    const b = body(fn, false);
    const writes = eventWriters().has(fn) || /\b(eventsFromRegions|insertRegionRun|regionsAbsorbTail)\(/.test(b);
    if (writes && type !== "subagent") applies.add(type);
  }
  assert.deepEqual([...applies].sort(), [...LAND_TYPES].sort());
  assert.ok(arms.get("subagent") === "applySubagentFrame" && eventWriters().has("applySubagentFrame"), "the one writer left out, by name");
});

test("the watch's two ends sit around the ONE dispatch chain: before its first arm, after its last, with no exit between", () => {
  const before = RENDER.indexOf("const landSnap = landingBefore(m);"), after = RENDER.indexOf("landingAfter(m, landSnap);");
  assert.equal(RENDER.split("const landSnap = landingBefore(m);").length, 2, "one first end");
  assert.equal(RENDER.split("landingAfter(m, landSnap);").length, 2, "one second end");
  const first = RENDER.indexOf('if (m.type === "session") upsert(m);'), marks = RENDER.indexOf("applyCommentMarks(String(m.id));", after);
  assert.ok(before > 0 && before < first, "the snapshot is taken before the chain's first arm");
  for (const arm of ['else if (m.type === "chatTail") chatTail(m);', 'else if (m.type === "chatHead") chatHead(m);', 'else if (m.type === "chatWindow") chatWindow(m);',
                     'else if (m.type === "chatTurns") chatTurns(m);', 'else if (m.type === "update") update(m);', 'else if (m.type === "closed") dismissSession(']) {
    const at = RENDER.indexOf(arm, first);
    assert.ok(at > first && at < after, "the chain arm precedes the second end: " + arm);
  }
  assert.ok(after < marks, "…which runs before the comment marks' re-apply, in the same handler");
  // the chain is ONE if/else-if: nothing at the handler's top level between the two ends can leave early
  for (const line of RENDER.slice(before, after).split("\n")) assert.doesNotMatch(line, /^  (?:return\b|if \(.*\) return\b)/, line.trim().slice(0, 80));
});

test("the send, the reconcile's verdicts and the send row reach the watch; each hook is guarded so it can never break its caller", () => {
  assert.match(RENDER, /import \{ type LandEvent, LandingWatch \} from "\.\/send-landing";/);
  const decl = RENDER.indexOf("const landingWatch = new LandingWatch();");
  assert.ok(decl > 0 && decl < RENDER.indexOf("\nfunction registerOptimistic("), "declared ahead of every caller, beside the pending sends");
  assert.match(body("registerOptimistic"), /try \{ if \(p\.qid\) landingWatch\.send\(id, p\.qid, p\.ts\); \} catch \{/);
  assert.match(body("reconcileOptimisticInner"), /const r = reconcilePending\(s\.events as TailEvent\[\], list\);\n\s*noteLandings\(s\.id, s\.events, r\);/);
  const nl = body("noteLandings");
  assert.match(nl, /try \{[\s\S]*landingWatch\.claim\(sid, p\.qid, events\[idx\]\?\.uuid\)[\s\S]*landingWatch\.lost\(sid, p\.qid\)[\s\S]*\} catch \{/);
  assert.match(body("routeUserMessage"), /data: \{ sid, key: qid, ts: Date\.now\(\)/, "the send row carries the id the landed row names");
  assert.match(body("landingBefore"), /^\s*try \{/m);
  assert.match(body("landingAfter"), /\} catch \(err\) \{\n\s*if \(!landWatchFailed\)/);
});

// ── executed ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
function liftBetween(startAnchor: string, endAnchor: string): string {
  const a = RENDER.indexOf(startAnchor), b = RENDER.indexOf(endAnchor, a);
  assert.ok(a > 0 && b > a, `anchors moved: ${startAnchor.slice(0, 40)} / ${endAnchor.slice(0, 40)}`);
  return requireCjs("esbuild").transformSync(RENDER.slice(a, b), { loader: "ts" }).code;
}
/** Run lifted code with `scope` as its world; every identifier it reads that the scope lacks is a stub that RECORDS its call. */
function liftWith(js: string, scope: Record<string, unknown>, names: string[], calls: string[]): Record<string, any> {
  const proxy = new Proxy(scope, {
    has: (t, k) => k in t || !(k in globalThis),
    get: (t, k) => (k in t ? (t as any)[k] : (typeof k === "symbol" ? undefined : ((..._a: unknown[]) => { calls.push(String(k)); return undefined; }))),
    set: (t, k, v) => { (t as any)[k] = v; return true; },
  });
  const src = `with (SCOPE) { ${js}\n return { ${names.join(", ")} }; }`;
  return (new Function("SCOPE", src) as (s: unknown) => Record<string, any>)(proxy);
}
const GLUE = () => liftBetween("const LAND_FRAME_TYPES: ReadonlySet<string>", "\nfunction upsert(msg: any) {");

/** A write-trapping view: every set, delete or collection mutation reached through `v` is recorded (sloppy-mode code cannot throw on a frozen object). */
function trap<T>(v: T, writes: string[], at = "$"): T {
  if (!v || typeof v !== "object") return v;
  if (v instanceof Map || v instanceof Set) {
    return new Proxy(v as any, {
      get: (t, k) => {
        if (k === "add" || k === "set" || k === "delete" || k === "clear") return () => { writes.push(at + "." + String(k) + "()"); };
        if (k === "get") return (key: unknown) => trap(t.get(key), writes, at + ".get(" + String(key) + ")");
        const x = Reflect.get(t, k, t);
        return typeof x === "function" ? x.bind(t) : x;
      },
    });
  }
  return new Proxy(v as any, {
    get: (t, k) => { const x = t[k]; return typeof k === "symbol" || typeof x !== "object" || x === null ? x : trap(x, writes, at + "." + String(k)); },
    set: (_t, k) => { writes.push(at + "." + String(k)); return true; },
    deleteProperty: (_t, k) => { writes.push("delete " + at + "." + String(k)); return true; },
    defineProperty: (_t, k) => { writes.push("define " + at + "." + String(k)); return true; },
  });
}

const ev = (uuid: string, kind = "user", extra: Record<string, unknown> = {}) => ({ uuid, kind, md: kind === "user" ? "synthetic ask " + uuid : "synthetic reply " + uuid, ...extra });

test("EXECUTED: the glue reads the sessions, the pending sends and the rewind marks, writes none of them, and calls nothing but the diag post", () => {
  const writes: string[] = [], calls: string[] = [], rows: { what: string; data: any }[] = [];
  const KEY = "echo:" + "c3".repeat(16);
  const held = [ev("u1"), ev("a1", "assistant"), ev("11111111-2222-4333-8444-0000000004a1", "user", { qid: KEY }), ev("a2", "assistant")];
  const real = new Map<string, any>([[SID, { id: SID, name: "web", events: held.slice(), status: { state: "idle" } }]]);
  const watch = new LandingWatch();
  watch.send(SID, KEY, 1_700_000_000_000);
  const scope: Record<string, unknown> = {
    sessions: trap(real, writes, "sessions"), pendingSent: trap(new Map([[SID, [{ qid: KEY }]]]), writes, "pendingSent"),
    pendingRewind: trap(new Map(), writes, "pendingRewind"), landingWatch: watch, ScrollDiagBudget,
    chatDiagRow: (what: string, data: any) => rows.push({ what, data }),
  };
  const glue = liftWith(GLUE(), scope, ["landingBefore", "landingAfter"], calls);
  // a status frame applies no events: no snapshot, nothing filed
  assert.equal(glue.landingBefore({ type: "status", id: SID }), null);
  // a delta that lands the send, then one that takes it off again (the handler's work done on the REAL map, outside the trap)
  let snap = glue.landingBefore({ type: "chatTail", id: SID });
  real.get(SID).events.push(ev("a3", "assistant"));
  glue.landingAfter({ type: "chatTail", id: SID, events: [ev("a3", "assistant")] }, snap);
  snap = glue.landingBefore({ type: "chatTail", id: SID, wm: { leaf: "L", tx: [[1, 2]], live: 3 } });
  real.get(SID).events = [ev("u1"), ev("a1", "assistant"), ev("a2", "assistant"), ev("a3", "assistant")];
  glue.landingAfter({ type: "chatTail", id: SID, events: [ev("a3", "assistant")], wm: { leaf: "L", tx: [[1, 2]], live: 3 } }, snap);
  assert.deepEqual(rows.map((r) => r.what), ["landed", "landed-lost"]);
  assert.equal(rows[1].data.key, KEY);
  assert.deepEqual(rows[1].data.wm, { leaf: "L", tx: [[1, 2]], live: 3 });
  assert.deepEqual(writes, [], "the instruments wrote nothing they read");
  assert.deepEqual(calls, [], "…and called nothing but the diag post");
  // a watch that throws costs one row, never the frame
  const broken = liftWith(GLUE(), { ...scope, landingWatch: { apply: () => { throw new Error("synthetic fault"); } } }, ["landingBefore", "landingAfter"], calls);
  const s2 = broken.landingBefore({ type: "session", id: SID });
  assert.doesNotThrow(() => broken.landingAfter({ type: "session", id: SID }, s2));
  assert.doesNotThrow(() => broken.landingAfter({ type: "session", id: SID }, s2));
  assert.deepEqual(rows.slice(2).map((r) => r.what), ["landing-watch-failed"], "said once");
});

// the real upsert, run over the scope chat-proto2-exec.test.ts drives it with, its render-side calls recorded
const isOptimistic = (e: any) => typeof e.uuid === "string" && e.uuid.startsWith("optimistic:");
const isHeldGroup = (e: any) => e.kind === "queued" && typeof e.uuid === "string" && e.uuid.startsWith("held:");
function run(frames: any[], withWatch: boolean): { state: string; calls: string[]; rows: { what: string; data: any }[] } {
  const calls: string[] = [], rows: { what: string; data: any }[] = [];
  const held = [ev("u1"), ev("a1", "assistant"), ev("u2"), ev("a2", "assistant")];
  const sessions = new Map<string, any>([[SID, { id: SID, name: "web", events: held.slice(), status: { state: "idle" }, proto: 2, headKnown: true, headTotal: 4, firstUuid: "u1", lastUuid: "a2",
                                                 tailLo: 0, regions: [{ kind: "run", lo: 0, hi: null, events: held.slice() }] }]]);
  const fakeEl = (): any => ({ style: {}, dataset: {}, children: [], classList: { add() {}, remove() {}, toggle() {} }, appendChild() {}, querySelector: () => null, querySelectorAll: () => [] });
  const scope: Record<string, unknown> = {
    sessions, pendingFullWhy: new Map(), activeId: SID, awaitingFull: new Set<string>(), skeletonTabs: { ids: new Set() }, tabMeta: new Map(), pendingTabMeta: new Map(),
    emptyFrameDiagSent: new Set(), ledgers: new Map(), views: new Map(), pendingRewind: new Map(), pendingSent: new Map(),
    document: { getElementById: () => null, createElement: () => fakeEl(), body: fakeEl(), querySelector: () => null },
    window: { innerHeight: 800, requestAnimationFrame: () => 0 },
    keepResidentEvents: () => false, onFull: () => false, hostOf: () => "", mergeWindow, keyOf, regionsFromRuns, runsOf, insertRun, turnsBeforeTail, stripOptimistic: () => {},
    splitHeldAgainstFrame, OVERLAY_KINDS, isOptimistic, isHeldGroup, refusedFrameLatch: new Map(), clearRefusedLatch: () => {}, requestFullSession: () => {},
    frameOlder, droppedLandedHuman, dropsLandedRow, landingWatch: new LandingWatch(), ScrollDiagBudget,
    chatDiagRow: (what: string, data: any) => rows.push({ what, data }),
    vscodeApi: { postMessage: (m: any) => rows.push({ what: m.what, data: m.data }) },
  };
  scope.sharesAnyUuid = liftWith(liftBetween("function sharesAnyUuid(a: ChatEvent[], b: ChatEvent[]): boolean {", "\n\n/** One client-diag row"), {}, ["sharesAnyUuid"], calls).sharesAnyUuid;
  const api = liftWith(GLUE() + "\n" + liftBetween("function upsert(msg: any) {", "\nfunction "), scope, ["upsert", "landingBefore", "landingAfter"], calls);
  for (const f of frames) {
    const snap = withWatch ? api.landingBefore(f) : null;
    api.upsert(f);
    if (withWatch) api.landingAfter(f, snap);
  }
  return { state: JSON.stringify([...sessions.entries()]), calls, rows };
}

test("EXECUTED: rendering is identical with the instruments on: the real upsert leaves the same state and makes the same calls, in order", () => {
  const frame = (i: number, events: any[]) => ({ type: "session", id: SID, name: "web", proto: 2, tailLo: 0, headKnown: true, events, firstUuid: events[0].uuid,
                                                 lastUuid: events[events.length - 1].uuid, status: { state: "idle" }, wm: { leaf: "L", tx: [[1, 100 + i]], live: 1 } });
  const frames = [
    frame(1, [ev("u1"), ev("a1", "assistant"), ev("u2"), ev("a2", "assistant"), ev("a3", "assistant")]),                        // an append
    frame(2, [ev("u1"), ev("a1", "assistant"), ev("a2", "assistant"), ev("a3", "assistant")]),                                   // the newest ask retracted
    frame(3, [ev("u1"), ev("a1", "assistant"), ev("a2", "assistant"), ev("a3", "assistant"), ev("u4"), ev("a4", "assistant")]),  // a new ask
  ];
  const off = run(frames, false), on = run(frames, true);
  assert.equal(on.state, off.state, "the same sessions, byte for byte");
  assert.deepEqual(on.calls, off.calls, "the same render-side calls (appendActive, renderTabs, the reconciles, …), in the same order");
  assert.ok(off.calls.length > 0, "the handler's render-side calls were recorded");
  const landing = on.rows.filter((r) => /^land/.test(r.what));
  assert.deepEqual(landing.map((r) => [r.what, r.data.uuid, r.data.path]), [["landed-lost", "u2", "session"]], "the instrument ran, and filed the retraction");
  assert.deepEqual(on.rows.filter((r) => !/^land/.test(r.what)), off.rows, "every other row as before");
});
