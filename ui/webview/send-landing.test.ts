// The send-landing invariant's decisions, EXECUTED (send-landing.ts, 2026-09-23): a send followed from the kernel's copy of it to
// its landed turn (`landed`), a landed human turn a frame takes off the newest few (`landed-lost`) told apart from a window slide
// off the top, a fork and a removal the page expects, and a send the kernel took and answered while the page holds no record of
// it (`landed-missing`). And the watch reads its inputs and never writes them. Synthetic events and ids only.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import { LandingWatch, LAND_MAX_SENDS, LAND_RECENT_TURNS, tailKeys, type LandCtx, type LandEvent } from "./send-landing";

const SID = "11111111-2222-4333-8444-000000000301";
const KEY = "echo:" + "a1".repeat(16);             // the copy's id, in the kernel's echo form (send-pending.ts mintQid)
const KEY2 = "echo:" + "b2".repeat(16);
const LANDED = "11111111-2222-4333-8444-0000000003a1";

const user = (uuid: string, extra: Partial<LandEvent> = {}): LandEvent => ({ kind: "user", uuid, ...extra });
const asst = (uuid: string): LandEvent => ({ kind: "assistant", uuid });
const tool = (uuid: string): LandEvent => ({ kind: "tool", uuid });
const echo = (key: string, extra: Partial<LandEvent> = {}): LandEvent => ({ kind: "user", uuid: key, ...extra });
const queued = (uuid: string, qid: string): LandEvent => ({ kind: "queued", uuid, texts: [{ qid }] });
const ours = (qid: string): LandEvent => ({ kind: "queued", uuid: "optimistic:1700000000000", texts: [{ qid }] });   // the page's own bubble
const ctx = (over: Partial<LandCtx> = {}): LandCtx => ({ path: "chatTail", now: 1_700_000_005_000, pending: new Set([KEY]), ...over });
const T0 = 1_700_000_000_000;

// a transcript: three asks answered, the newest last
const BASE: LandEvent[] = [user("u1"), asst("a1"), user("u2"), asst("a2"), tool("t2"), user("u3"), asst("a3")];

test("landed: the record wearing the send's id enters the resident events, one row with the id, the uuid and the ms since the press", () => {
  const w = new LandingWatch();
  w.send(SID, KEY, T0);
  const withEcho = [...BASE, echo(KEY, { hiddenByPending: true }), ours(KEY)];
  assert.deepEqual(w.apply(SID, BASE, withEcho, ctx()), [], "the echo is the kernel's copy, not a landing");
  const landedList = [...BASE, user(LANDED, { qid: KEY }), ours(KEY)];
  const rows = w.apply(SID, withEcho, landedList, ctx({ path: "session" }));
  assert.deepEqual(rows, [{ what: "landed", data: { sid: SID, key: KEY, uuid: LANDED, ms: 5000, path: "session", by: "id", fromEnd: 1 } }]);
  assert.deepEqual(w.apply(SID, landedList, [...landedList, asst("a4")], ctx()), [], "once per send");
  // a record of several sends names each by its block ids
  const w2 = new LandingWatch();
  w2.send(SID, KEY2, T0);
  assert.equal(w2.apply(SID, BASE, [...BASE, user(LANDED, { qids: [KEY, KEY2] })], ctx({ pending: new Set([KEY2]) }))[0].data.uuid, LANDED);
});

test("landed by text: a record without the id that the pending reconcile matched is the landing, and says so", () => {
  const w = new LandingWatch();
  w.send(SID, KEY, T0);
  w.claim(SID, KEY, LANDED);
  const rows = w.apply(SID, BASE, [...BASE, user(LANDED)], ctx({ pending: new Set() }));
  assert.equal(rows.length, 1);
  assert.equal(rows[0].data.by, "text");
  assert.equal(rows[0].data.uuid, LANDED);
  // a claim for another session's send, or for an unknown id, is ignored
  w.claim("other", KEY2, "x"); w.claim(SID, undefined, "x");
});

test("landed-lost: a frame that takes the newest landed human turn off the page files it, with the frame, the tails and the kernel's word", () => {
  const w = new LandingWatch();
  w.send(SID, KEY, T0);
  const held = [...BASE, user(LANDED, { qid: KEY }), asst("a4")];
  w.apply(SID, BASE, held, ctx({ pending: new Set() }));                       // landed
  const after = [...BASE, asst("a4"), asst("a5")];                              // the delta's suffix no longer carries it
  const wm = { leaf: "L", tx: [[1, 100]], live: 4 };
  const rows = w.apply(SID, held, after, ctx({ path: "chatTail", wm, frame: [asst("a4"), asst("a5")], pending: new Set() }));
  assert.equal(rows.length, 1);
  assert.deepEqual(rows[0], { what: "landed-lost", data: { sid: SID, uuid: LANDED, key: KEY, ms: 5000, fromEnd: 1, path: "chatTail", wm, inKernel: false,
                                                           before: tailKeys(held), after: tailKeys(after) } });
  // the frame CARRIED it and the page's merge dropped it anyway: inKernel true names the page's side
  const again = new LandingWatch();
  const rows2 = again.apply(SID, held, after, ctx({ path: "session", frame: [...held], pending: new Set() }));
  assert.equal(rows2[0].data.inKernel, true);
  assert.equal(rows2[0].data.key, null, "a turn no send on this page made: no key");
  // no frame events at all (a frame that carried none): unknown, not false
  assert.equal(new LandingWatch().apply(SID, held, after, ctx({ frame: null, pending: new Set() }))[0].data.inKernel, null);
});

test("a window SLIDE off the top is not a loss: every event above the turn went with it", () => {
  const w = new LandingWatch();
  // the kernel re-windows the tail: u1..a2 slide off, and u2 was one of the newest three human turns
  const after = [tool("t2"), user("u3"), asst("a3"), asst("a4")];
  assert.deepEqual(w.apply(SID, BASE, after, ctx({ path: "session", pending: new Set() })), []);
  // …but the same turn taken from the MIDDLE, with the events above it kept, is one
  const mid = [user("u1"), asst("a1"), asst("a2"), tool("t2"), user("u3"), asst("a3")];
  const rows = w.apply(SID, BASE, mid, ctx({ path: "session", pending: new Set() }));
  assert.deepEqual(rows.map((r) => [r.what, r.data.uuid, r.data.fromEnd]), [["landed-lost", "u2", 2]]);
});

test("an expected removal files nothing here: a rewind the page asked for, a rebased full, a fork that shares nothing", () => {
  const w = new LandingWatch();
  const cut = BASE.slice(0, 5);   // u3 and its answer gone
  assert.deepEqual(w.apply(SID, BASE, cut, ctx({ expected: "rewind", pending: new Set() })), []);
  assert.deepEqual(w.apply(SID, BASE, cut, ctx({ expected: "rebased", pending: new Set() })), []);
  assert.deepEqual(w.apply(SID, BASE, [user("f1"), asst("f2")], ctx({ path: "session", pending: new Set() })), [], "a fork: nothing shared");
  assert.equal(w.apply(SID, BASE, cut, ctx({ pending: new Set() })).length, 1, "the same cut, unexpected, is filed");
});

test("only the newest few human turns are watched; romp's own lines, transient keys and the page's injections are not human turns", () => {
  const w = new LandingWatch();
  const long: LandEvent[] = [user("old"), asst("x0")];
  for (let i = 0; i < LAND_RECENT_TURNS; i++) long.push(user("r" + i), asst("y" + i));
  const dropOld = long.filter((e) => e.uuid !== "old");
  // the oldest is outside the newest three, and the list above it is not a slide (x0 stays)
  assert.deepEqual(w.apply(SID, long, dropOld, ctx({ pending: new Set() })), []);
  const noise: LandEvent[] = [user("u1"), asst("a1"), user("n1", { romp: true }), user("n2", { source: { kind: "agent" } }), user("cmd:1:model"), user("echo-ab"), echo(KEY)];
  assert.deepEqual(w.apply(SID, noise, [user("u1"), asst("a1")], ctx({ pending: new Set() })), [], "none of those is a landed human turn");
});

test("landed-missing: the kernel's copies are gone, no landed turn is resident, and an agent message lands below the copy", () => {
  const w = new LandingWatch();
  w.send(SID, KEY, T0);
  const pending = new Set([KEY]);
  assert.deepEqual(w.apply(SID, BASE, [...BASE, ours(KEY)], ctx({ pending })), [], "before the kernel holds it: nothing to say");
  const withEcho = [...BASE, echo(KEY, { hiddenByPending: true }), ours(KEY)];
  assert.deepEqual(w.apply(SID, BASE, withEcho, ctx({ pending })), []);
  assert.equal(w.peek(KEY)!.received, "echo");
  // the running turn's steps stream below the HIDDEN echo: the normal wait, never a row
  const streaming = [...BASE, echo(KEY, { hiddenByPending: true }), asst("s1"), tool("s2"), ours(KEY)];
  assert.deepEqual(w.apply(SID, withEcho, streaming, ctx({ pending })), []);
  // the echo retires (the kernel read the record) and the answer lands, but no record of the send is resident
  const gone = [...BASE, asst("s1"), tool("s2"), asst("ans"), ours(KEY)];
  const wm = { leaf: "L", tx: [[1, 200]], live: 9 };
  const rows = w.apply(SID, streaming, gone, ctx({ path: "session", wm, frame: gone, pending }));
  assert.deepEqual(rows, [{ what: "landed-missing", data: { sid: SID, key: KEY, ms: 5000, path: "session", wm, echo: "gone", was: "echo", answer: "ans",
                                                            inFrame: false, tail: tailKeys(gone) } }]);
  assert.deepEqual(w.apply(SID, gone, [...gone, asst("more")], ctx({ pending })), [], "once per send");
  // …and the landing that comes late is still filed, with its real delay
  const late = w.apply(SID, gone, [...gone, user(LANDED, { qid: KEY })], ctx({ pending, now: T0 + 9000 }));
  assert.deepEqual(late.map((r) => [r.what, r.data.ms]), [["landed", 9000]]);
});

test("landed-missing says whether the frame carried the record: the page dropped it, or the kernel never sent it", () => {
  const w = new LandingWatch();
  w.send(SID, KEY, T0);
  const pending = new Set([KEY]);
  const q = [...BASE, queued("queued", KEY), ours(KEY)];
  w.apply(SID, BASE, q, ctx({ pending }));
  assert.equal(w.peek(KEY)!.received, "queued");
  const after = [...BASE, asst("ans"), ours(KEY)];
  const rows = w.apply(SID, q, after, ctx({ path: "session", frame: [...BASE, user(LANDED, { qid: KEY }), asst("ans")], pending }));
  assert.equal(rows[0].what, "landed-missing");
  assert.equal(rows[0].data.inFrame, true);
  assert.equal(rows[0].data.was, "queued");
});

test("landed-missing is NOT filed for a send taken back, one the kernel never delivered, one whose held copy stands, or one that landed", () => {
  const pending = new Set([KEY]);
  const withEcho = [...BASE, echo(KEY), ours(KEY)];
  const answered = [...BASE, asst("ans")];
  // taken back: the cross dropped the pending entry (no landing, no bubble)
  const a = new LandingWatch(); a.send(SID, KEY, T0); a.apply(SID, BASE, withEcho, ctx({ pending }));
  assert.deepEqual(a.apply(SID, withEcho, answered, ctx({ pending: new Set() })), []);
  assert.equal(a.peek(KEY)!.done, "withdrawn");
  // never delivered: the reconcile's verdict
  const b = new LandingWatch(); b.send(SID, KEY, T0); b.apply(SID, BASE, withEcho, ctx({ pending })); b.lost(SID, KEY);
  assert.deepEqual(b.apply(SID, withEcho, answered, ctx({ pending })), []);
  // the page holds the copy that left the kernel's queue (T262i's held group): the fed gap, not a loss
  const c = new LandingWatch(); c.send(SID, KEY, T0); c.apply(SID, BASE, withEcho, ctx({ pending }));
  assert.deepEqual(c.apply(SID, withEcho, [...BASE, asst("ans"), queued("held:" + SID, KEY), ours(KEY)], ctx({ pending })), []);
  // the never-delivered echo stays on the list: the copy is not gone
  const d = new LandingWatch(); d.send(SID, KEY, T0); d.apply(SID, BASE, withEcho, ctx({ pending }));
  assert.deepEqual(d.apply(SID, withEcho, [...BASE, echo(KEY, { undelivered: true }), asst("ans")], ctx({ pending })), []);
  // landed in the same frame: `landed`, never missing
  const e = new LandingWatch(); e.send(SID, KEY, T0); e.apply(SID, BASE, withEcho, ctx({ pending }));
  assert.deepEqual(e.apply(SID, withEcho, [...BASE, user(LANDED, { qid: KEY }), asst("ans")], ctx({ pending })).map((r) => r.what), ["landed"]);
  // an answer ABOVE where the copy sat (an older message re-sent in the frame) is not this send's answer
  const f = new LandingWatch(); f.send(SID, KEY, T0);
  f.apply(SID, BASE, withEcho, ctx({ pending }));
  assert.deepEqual(f.apply(SID, withEcho, [asst("pre"), ...BASE], ctx({ pending })), []);
  // another session's frame says nothing about this send
  const g = new LandingWatch(); g.send(SID, KEY, T0); g.apply(SID, BASE, withEcho, ctx({ pending }));
  assert.deepEqual(g.apply("11111111-2222-4333-8444-000000000399", withEcho, answered, ctx({ pending })), []);
});

test("the watch remembers a bounded number of sends, the oldest forgotten first (a bound, not a clock)", () => {
  const w = new LandingWatch();
  for (let i = 0; i < LAND_MAX_SENDS + 5; i++) w.send(SID, "echo:" + String(i).padStart(32, "0"), T0 + i);
  assert.equal(w.peek("echo:" + String(0).padStart(32, "0")), undefined);
  assert.ok(w.peek("echo:" + String(LAND_MAX_SENDS + 4).padStart(32, "0")));
  w.send(SID, "", T0); w.send("", KEY, T0);
  assert.equal(w.peek(""), undefined); assert.equal(w.peek(KEY), undefined, "a send with no session or no id is not tracked");
});

/** A write-trapping view of `v`, recursively: every set or delete on it or anything reached through it is recorded. */
function trap<T>(v: T, writes: string[], at = "$"): T {
  if (!v || typeof v !== "object") return v;
  if (v instanceof Set || v instanceof Map) {   // a collection's own methods need the real receiver; its mutators are recorded
    return new Proxy(v as any, {
      get: (t, k) => {
        if (k === "add" || k === "set" || k === "delete" || k === "clear") return () => { writes.push(at + "." + String(k) + "()"); };
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

test("OBSERVATION ONLY: the watch never writes the events, the frame or the pending set it reads, whatever it files", () => {
  const writes: string[] = [];
  const w = new LandingWatch();
  w.send(SID, KEY, T0);
  const steps: LandEvent[][] = [
    BASE,
    [...BASE, echo(KEY, { hiddenByPending: true }), ours(KEY)],
    [...BASE, asst("s1"), asst("ans"), ours(KEY)],                      // missing
    [...BASE, asst("s1"), asst("ans"), user(LANDED, { qid: KEY })],     // landed
    [...BASE, asst("s1"), asst("ans")],                                 // lost
  ];
  const snapshot = JSON.stringify(steps);
  const filed: string[] = [];
  for (let i = 1; i < steps.length; i++) {
    const c = ctx({ path: "session", frame: steps[i], wm: { leaf: "L", tx: [[1, i]], live: i }, pending: new Set([KEY]) });
    for (const r of w.apply(SID, trap(steps[i - 1], writes, "before"), trap(steps[i], writes, "after"), trap(c, writes, "ctx"))) filed.push(r.what);
  }
  assert.deepEqual(filed, ["landed-missing", "landed", "landed-lost"], "every row kind was exercised");
  assert.deepEqual(writes, [], "no write reached anything the watch was handed");
  assert.equal(JSON.stringify(steps), snapshot);
});
