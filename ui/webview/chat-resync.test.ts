// The delta's base check (chat-resync.ts, 2026-09-23), EXECUTED twice over: the pure rules, and chatTail and upsert lifted
// from render.ts and driven over stubs (the chat-exact-tail-exec.test.ts / chat-proto2-exec.test.ts pattern), so the page
// refuses a delta cut against a base it does not hold, asks for the full exactly once, applies that full, never loops, costs
// nothing when page and kernel agree, and treats an older kernel's delta (no stamp) exactly as before.
//
// The CONSTRUCTED GAP below (a delta computed against a base with one more turn than the page holds) is a test of the
// detector, not a reproduction of the bug: the live reproduction of how a page comes to miss a turn is its own lab.
// Synthetic events only (the notes-api demo world); the fingerprints are computed here the way the kernel computes them.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { createRequire } from "node:module";
import { crc32Utf8, baseFingerprint, readBaseFp, checkBase, newResyncState, onMismatch, onAgree, forgetResync, staleAnswer, RESYNC_MAX_STRIKES } from "./chat-resync";
import { indexOfUuid, keyOf, mergeWindow } from "./chat-window";
import { OVERLAY_KINDS, insertRun, regionsFromRuns, runsOf, splitHeldAgainstFrame, turnsBeforeTail } from "./chat-regions";
import { frameOlder, droppedLandedHuman, dropsLandedRow } from "./frame-guard";

// ── the pure rules ────────────────────────────────────────────────────────────────────────────────

test("the crc is zlib's: the kernel's _chat_base_fp and the page hash the same bytes to the same number", () => {
  // zlib.crc32 reference values (python3 -c "import zlib; print(zlib.crc32(b'...'))")
  assert.equal(crc32Utf8(""), 0);
  assert.equal(crc32Utf8("123456789"), 0xcbf43926, "the IEEE check value");
  assert.equal(crc32Utf8("u1\na1\nu2"), 1439716801);
  assert.equal(crc32Utf8("é"), 235179326, "multi-byte input is hashed as UTF-8");
  assert.deepEqual(baseFingerprint([{ uuid: "u1" }, { uuid: "a1", key: "a1#1" }, { uuid: "u2" }]), [3, crc32Utf8("u1\na1#1\nu2")], "keyed by the wire key: key, else uuid");
});

test("readBaseFp takes the kernel's [n, crc] and nothing else: an older kernel's absent stamp and a malformed one both read as no check", () => {
  assert.deepEqual(readBaseFp([3, 12345]), [3, 12345]);
  for (const bad of [undefined, null, 7, "3:1", [3], [3, -1], [1.5, 2], [3, 2 ** 33], ["3", 1], {}]) assert.equal(readBaseFp(bad), null, JSON.stringify(bad));
});

const ev = (u: string) => ({ uuid: u });
const run = (...us: string[]) => us.map(ev);

test("checkBase: the page's n events ending at the anchor hash to the kernel's, or the delta is refused", () => {
  const tail = run("u0", "a0", "u1", "a1", "u2", "a2");
  const fp = baseFingerprint(tail.slice(2, 5));                       // the kernel's window: u1, a1, u2, anchored at u2
  assert.deepEqual(checkBase(tail, 4, fp), { ok: true });
  const missing = run("u0", "a0", "a1", "u2", "a2");                  // the page never received u1
  const v = checkBase(missing, 3, fp);
  assert.equal(v.ok, false);
  assert.equal((v as any).reason, "differs");
  const short = run("a1", "u2");                                      // a tail run holding fewer events than the window
  assert.equal((checkBase(short, 1, fp) as any).reason, "short", "fewer events than n before the anchor is a disagreement");
  assert.deepEqual(checkBase(tail, 4, baseFingerprint([])), { ok: true }, "an empty window (an anchor at the run's first edge with n 0) agrees");
});

test("the strikes: two asks in a row with no agreeing delta between, then the check disarms and re-arms on agreement", () => {
  const st = newResyncState();
  assert.equal(RESYNC_MAX_STRIKES, 2);
  assert.deepEqual(onMismatch(st, "A"), { act: "ask", firstObserve: false });
  assert.deepEqual(onMismatch(st, "A"), { act: "ask", firstObserve: false }, "a second ask covers a full that was itself stale");
  assert.deepEqual(onMismatch(st, "A"), { act: "observe", firstObserve: true }, "the third disarms, once");
  assert.deepEqual(onMismatch(st, "A"), { act: "observe", firstObserve: false });
  assert.ok(st.disarmed.has("A"));
  assert.deepEqual(onMismatch(st, "B"), { act: "ask", firstObserve: false }, "per session");
  onAgree(st, "A");
  assert.ok(!st.disarmed.has("A") && !st.strikes.has("A"), "an agreeing delta re-arms and clears");
  assert.deepEqual(onMismatch(st, "A"), { act: "ask", firstObserve: false });
  forgetResync(st);
  assert.equal(st.strikes.size + st.disarmed.size, 0, "a new socket forgets every session");
});

test("staleAnswer: an older answer to an ask re-asks once, the second applies", () => {
  const re = new Set<string>();
  assert.equal(staleAnswer(re, "A"), "reask");
  assert.equal(staleAnswer(re, "A"), "apply");
  assert.equal(staleAnswer(re, "B"), "reask");
});

// ── chatTail, executed ────────────────────────────────────────────────────────────────────────────

const requireCjs = createRequire(__filename);
const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
function liftBetween(startAnchor: string, endAnchor: string): string {
  const a = RENDER.indexOf(startAnchor), b = RENDER.indexOf(endAnchor, a);
  assert.ok(a > 0 && b > a, `anchors moved: ${startAnchor.slice(0, 40)} / ${endAnchor.slice(0, 40)}`);
  return requireCjs("esbuild").transformSync(RENDER.slice(a, b), { loader: "ts" }).code;
}

type World = { chatTail: (m: any) => void; upsert: (m: any) => void; set: (p: any) => void; asks: [string, string][]; rows: { what: string; data: any }[];
               awaitingFull: Set<string> };

/** chatTail and upsert over ONE shared world: the real base check (chat-resync.ts), the real anchor helpers and the real watermark
 *  guard; requestFullSession models render.ts's latch (one ask per session until a full lands). */
function world(): World {
  const tailJs = liftBetween("function chatTail(msg: any) {", "// Older history streaming in from a loadOlder request");
  const upJs = liftBetween("function upsert(msg: any) {", "\nfunction ");
  // upsert's stale-answer helpers; absent in a render.ts from before the check, where the Proxy answers them with no-ops (so the
  // behavioural tests below read red there on what they assert, not on a missing anchor)
  const END = "function endStaleAnswer(id: string): void { staleAnswerReasked.delete(id); }";
  const hA = RENDER.indexOf("function applyStaleAnswer(id: string): boolean {"), hB = RENDER.indexOf(END);
  const helpersJs = hA > 0 && hB > hA ? requireCjs("esbuild").transformSync(RENDER.slice(hA, hB + END.length), { loader: "ts" }).code : "";
  const asks: [string, string][] = [], rows: { what: string; data: any }[] = [];
  const awaitingFull = new Set<string>();
  const S: Record<string, unknown> = {
    sessions: new Map(), views: new Map(), activeId: "A", ledgers: new Map(), pendingFlags: new Map(), pendingRewind: new Map(), awaitingFull,
    resync: newResyncState(), staleAnswerReasked: new Set<string>(),
    readBaseFp, checkBase, onMismatch, onAgree, staleAnswer, indexOfUuid, keyOf, frameOlder, droppedLandedHuman, dropsLandedRow,
    requestFullSession: (id: string, why: string) => { if (awaitingFull.has(id)) return; awaitingFull.add(id); asks.push([id, why]); },
    chatDiagRow: (what: string, data: any) => rows.push({ what, data }),
    skeletonTabs: { ids: new Set() }, isOptimistic: (e: any) => typeof e.uuid === "string" && e.uuid.startsWith("optimistic:"), isHeldGroup: () => false,
    stripOptimistic: () => {}, reconcileRewind: () => {}, reconcileHeldCopies: () => {}, reconcileOptimistic: () => {}, awaitKey: () => "",
    scheduleRenderTabs: () => {}, applyFrameFlags: () => [], scheduleAppendActive: () => {}, awaitChanged: () => {}, schedulePrebuild: () => {},
    regionsAbsorbTail: () => true, clearRefusedLatch: () => {},
    // upsert's world, as chat-proto2-exec.test.ts's liftUpsert gives it: the real regions rules and a stub DOM
    mergeWindow, OVERLAY_KINDS, insertRun, regionsFromRuns, runsOf, splitHeldAgainstFrame, turnsBeforeTail, refusedFrameLatch: new Map(),
    emptyFrameDiagSent: new Set(), tabMeta: new Map(), pendingTabMeta: new Map(), pendingFullWhy: new Map(), keepResidentEvents: () => false, onFull: () => false, hostOf: () => "",
    sharesAnyUuid: (a: any[], b: any[]) => { const k = new Set(b.map((e) => e.uuid)); return a.some((e) => k.has(e.uuid)); },
    vscodeApi: { postMessage: (m: any) => rows.push({ what: m.what, data: m.data }) },
    document: { getElementById: () => null, querySelector: () => null, body: {} }, window: { innerHeight: 800, requestAnimationFrame: () => 0 },
  };
  const proxy = new Proxy(S, {
    has: (t, k) => k in t || !(k in globalThis),
    get: (t, k) => (k in t ? (t as any)[k] : (typeof k === "symbol" ? undefined : (() => undefined))),
    set: (t, k, v) => { (t as any)[k] = v; return true; },
  });
  const api = (new Function("SCOPE", `with (SCOPE) { ${helpersJs}\n${tailJs}\n${upJs}\n return { chatTail, upsert }; }`) as any)(proxy);
  return { chatTail: api.chatTail, upsert: api.upsert, set: (p: any) => Object.assign(S, p), asks, rows, awaitingFull };
}

const u = (id: string, kind = "user") => ({ uuid: id, kind, md: id + " of the notes-api search" });
/** The page's held session: a proto-2 tail run over `events` (the regions wire's shape upsert builds). */
function held(events: any[]) {
  return { id: "A", name: "web", events: events.slice(), status: { state: "working" }, proto: 2, headKnown: true, headTotal: events.length,
           firstUuid: events[0].uuid, lastUuid: events[events.length - 1].uuid, tailLo: 0, regions: [{ kind: "run", lo: 0, hi: null, events: events.slice() }] };
}
/** A delta cut from the kernel's list `klist` after `after`, stamped the kernel's way (the window from max(0, start - 64)). */
function delta(klist: any[], after: string, suffix: any[], extra: Record<string, unknown> = {}) {
  const start = klist.findIndex((e) => e.uuid === after) + 1;
  return { type: "chatTail", id: "A", afterUuid: after, events: suffix, status: { state: "working" }, baseFp: baseFingerprint(klist.slice(Math.max(0, start - 64), start)), ...extra };
}

test("agreeing deltas apply and cost nothing: a steady stream of them asks for no full", () => {
  const w = world();
  const k: any[] = [u("u0"), u("a0", "assistant"), u("u1"), u("a1", "assistant")];
  const sessions = new Map([["A", held(k)]]); w.set({ sessions });
  for (let i = 2; i < 40; i++) {                                     // the stream: each delta appends one event after the last
    const nxt = u((i % 2 ? "a" : "u") + i, i % 2 ? "assistant" : "user");
    w.chatTail(delta(k, k[k.length - 1].uuid, [nxt]));
    k.push(nxt);
  }
  assert.deepEqual(w.asks, [], "zero fulls asked in the steady state");
  assert.deepEqual(w.rows.filter((r) => r.what.startsWith("resync")), []);
  assert.deepEqual(sessions.get("A")!.events.map((e: any) => e.uuid), k.map((e) => e.uuid), "every delta applied");
});

test("a CONSTRUCTED gap (a detector test, not the bug's reproduction): a delta cut against a base holding a turn the page lacks is refused, one full is asked, the full lands the missing turn", () => {
  const w = world();
  const pageHas = [u("u0"), u("a0", "assistant"), u("a1", "assistant")];          // the page never received u1
  const kernel = [u("u0"), u("a0", "assistant"), u("u1"), u("a1", "assistant")];  // the kernel's list the delta is cut from
  const sessions = new Map([["A", held(pageHas)]]); w.set({ sessions });
  w.chatTail(delta(kernel, "a1", [u("u2")]));
  assert.deepEqual(w.asks, [["A", "resync"]], "exactly one full asked, named resync");
  assert.deepEqual(sessions.get("A")!.events.map((e: any) => e.uuid), ["u0", "a0", "a1"], "the delta was not applied onto the wrong base");
  const row = w.rows.find((r) => r.what === "resync");
  assert.ok(row, "the heal is counted: one resync row");
  assert.equal(row!.data.sid, "A"); assert.equal(row!.data.reason, "short"); assert.equal(row!.data.n, 4);
  assert.equal(row!.data.kernel, baseFingerprint(kernel)[1], "the row carries the kernel's fingerprint");
  assert.equal(row!.data.page, null, "…and the page's: none, since it holds fewer events up to the anchor than the window");
  assert.equal(row!.data.held, 3, "the page held three events up to the anchor, fewer than the window: still a disagreement");
  // a second delta while the ask is out waits on it: no second ask, nothing applied
  w.chatTail(delta([...kernel, u("u2")], "u2", [u("a2", "assistant")]));
  assert.deepEqual(w.asks, [["A", "resync"]], "one outstanding full per session");
  // the full answers: applied, and the missing turn is present
  const full = { type: "session", id: "A", name: "web", proto: 2, events: [...kernel, u("u2"), u("a2", "assistant")], headKnown: true, headTotal: 6,
                 firstUuid: "u0", lastUuid: "a2", tailLo: 0, status: { state: "working" } };
  w.upsert(full);
  assert.ok(!w.awaitingFull.has("A"), "the full clears the ask");
  assert.deepEqual(sessions.get("A")!.events.map((e: any) => e.uuid), ["u0", "a0", "u1", "a1", "u2", "a2"], "u1 is on the page after the full");
  // …and the next delta, cut from that list, agrees and applies: no further ask
  w.chatTail(delta(full.events, "a2", [u("u3")]));
  assert.deepEqual(w.asks, [["A", "resync"]]);
  assert.equal(sessions.get("A")!.events.at(-1).uuid, "u3");
});

test("a page holding a DIFFERENT event where the kernel's base has another (the same count) refuses the delta too: reason differs, both fingerprints in the row", () => {
  const w = world();
  const pageHas = [u("u0"), u("a0", "assistant"), u("echo:11111111222233334444555555555555"), u("a1", "assistant")];
  const kernel = [u("u0"), u("a0", "assistant"), u("u1"), u("a1", "assistant")];
  const sessions = new Map([["A", held(pageHas)]]); w.set({ sessions });
  w.chatTail(delta(kernel, "a1", [u("u2")]));
  assert.deepEqual(w.asks, [["A", "resync"]]);
  const row = w.rows.find((r) => r.what === "resync")!;
  assert.equal(row.data.reason, "differs");
  assert.deepEqual([row.data.kernel, row.data.page], [baseFingerprint(kernel)[1], baseFingerprint(pageHas)[1]], "the row carries both fingerprints");
  assert.equal(sessions.get("A")!.events.length, 4, "nothing applied");
});

test("no loop: a full that still leaves the page disagreeing asks once more, then the check disarms and deltas apply as before; an agreeing delta re-arms it", () => {
  const w = world();
  const sessions = new Map([["A", held([u("u0"), u("a0", "assistant")])]]); w.set({ sessions });
  const lying = (after: string, sfx: any[]) => ({ ...delta([u("x0"), u("x1"), ...sessions.get("A")!.events], after, sfx) });   // a kernel whose stamp never matches
  const full = () => w.upsert({ type: "session", id: "A", name: "web", proto: 2, events: sessions.get("A")!.events.slice(), headKnown: true, headTotal: sessions.get("A")!.events.length,
                                firstUuid: "u0", lastUuid: sessions.get("A")!.events.at(-1).uuid, tailLo: 0, status: { state: "working" } });
  w.chatTail(lying("a0", [u("u1")])); assert.equal(w.asks.length, 1, "first ask");
  full();
  w.chatTail(lying("a0", [u("u1")])); assert.equal(w.asks.length, 2, "second ask: the first full may itself have been stale");
  full();
  w.chatTail(lying("a0", [u("u1")]));
  assert.equal(w.asks.length, 2, "no third ask: the check disarmed");
  assert.deepEqual(w.rows.filter((r) => r.what === "resync-disarmed").length, 1, "said once");
  assert.equal(sessions.get("A")!.events.at(-1).uuid, "u1", "disarmed, the delta applies as it did before the check");
  for (let i = 0; i < 5; i++) w.chatTail(lying("u1", [u("a1", "assistant")]));
  assert.equal(w.asks.length, 2, "still no ask while disarmed");
  assert.equal(w.rows.filter((r) => r.what === "resync-disarmed").length, 1, "and no row per delta");
  // a delta that agrees re-arms the check; a later genuine disagreement asks again
  const cur = sessions.get("A")!.events.slice();
  w.chatTail(delta(cur, cur.at(-1).uuid, [u("u9")]));
  const again = sessions.get("A")!.events.slice();
  w.chatTail(delta([u("zz"), ...again], "u9", [u("a9", "assistant")]));
  assert.equal(w.asks.length, 3, "re-armed by agreement: a new disagreement asks");
});

test("an older kernel's delta (no stamp) applies exactly as before: no check, no ask", () => {
  const w = world();
  const sessions = new Map([["A", held([u("u0"), u("a0", "assistant"), u("a1", "assistant")])]]); w.set({ sessions });
  const d: any = delta([u("u0"), u("a0", "assistant"), u("u1"), u("a1", "assistant")], "a1", [u("u2")]);
  delete d.baseFp;
  w.chatTail(d);
  assert.deepEqual(w.asks, []);
  assert.equal(sessions.get("A")!.events.at(-1).uuid, "u2", "applied onto the held base, as every delta was before the check");
});

test("the live observation's shape, page half: a tail delivers agent message M, then an older kernel sends a full built without M; the page keeps M and asks for a fresh full once, and a second older answer applies", () => {
  const w = world();
  const wm = (tx: number, live: number) => ({ leaf: "/tmp/TESTHOST/notes-api.jsonl", tx: [[1790000000 + tx, tx]], live });
  const base = [u("u0"), u("a0", "assistant"), u("u1")];
  const s0: any = held(base); s0.wm = wm(100, 5);
  const sessions = new Map([["A", s0]]); w.set({ sessions });
  // the tail that delivers M (the streamed agent message), from a build that read (100, 6)
  w.chatTail({ ...delta(base, "u1", [u("M", "assistant")]), wm: wm(100, 6) });
  assert.equal(sessions.get("A")!.events.at(-1).uuid, "M");
  // unasked: an older full (the same parse, an older live revision, no M) is ignored and filed, as PR 2050's guard does
  const older = { type: "session", id: "A", name: "web", proto: 2, events: base.slice(), headKnown: true, headTotal: 3, firstUuid: "u0", lastUuid: "u1", tailLo: 0,
                  status: { state: "idle" }, wm: wm(100, 5) };
  w.upsert(older);
  assert.equal(sessions.get("A")!.events.at(-1).uuid, "M", "M stays");
  assert.deepEqual(w.asks, []);
  // asked (a resync), and the kernel answers with an older build: the page keeps M and asks once more for a fresh one
  w.awaitingFull.add("A");
  w.upsert(older);
  assert.equal(sessions.get("A")!.events.at(-1).uuid, "M", "the older answer did not take M off the page");
  assert.deepEqual(w.asks, [["A", "stale-full"]], "re-asked once, for a fresh build");
  assert.ok(w.awaitingFull.has("A"), "…and the re-sent ask is the one outstanding");
  // a second older answer to the same ask is applied: a full always wins, and the kernel now believes the page holds it
  w.upsert(older);
  assert.deepEqual(w.asks, [["A", "stale-full"]], "no third ask: never a loop");
  assert.ok(!w.awaitingFull.has("A"), "the ask is answered");
  // a fresh full afterwards (the kernel's newer build, M recorded) lands normally, and the next ask may re-send again
  w.upsert({ ...older, events: [...base, u("M", "assistant")], lastUuid: "M", headTotal: 4, wm: wm(140, 7) });
  assert.equal(sessions.get("A")!.events.at(-1).uuid, "M");
  w.awaitingFull.add("A");
  w.upsert(older);
  assert.deepEqual(w.asks, [["A", "stale-full"], ["A", "stale-full"]], "a NEW ask gets its own one re-send");
});
