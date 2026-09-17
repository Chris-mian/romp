// Exercise the real KernelPipe with synthetic sockets, including the passive status consumer.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import * as vm from "node:vm";
import * as ts from "typescript";
import { intentOp, ReloadHold } from "./pipe-intent";

const src = fs.readFileSync(path.join(process.cwd(), "src/extension.ts"), "utf8");
const ast = ts.createSourceFile("extension.ts", src, ts.ScriptTarget.Latest, true);
const node = ast.statements.find((n) => ts.isClassDeclaration(n) && n.name?.text === "KernelPipe");
assert.ok(node, "the harness must execute the shipped pipe");
const pipeCode = ts.transpileModule(node.getText(ast) + "\nglobalThis.Pipe = KernelPipe;", {
  compilerOptions: { target: ts.ScriptTarget.ES2021, module: ts.ModuleKind.CommonJS },
}).outputText;

function decoder() {
  const file = path.join(process.cwd(), "src/view-deltas.ts");
  if (!fs.existsSync(file)) return undefined; // the old pipe can run and demonstrate the failing wire behavior
  const exports: any = {};
  new Function("exports", ts.transpileModule(fs.readFileSync(file, "utf8"), {
    compilerOptions: { target: ts.ScriptTarget.ES2021, module: ts.ModuleKind.CommonJS },
  }).outputText)(exports);
  return exports;
}

async function harness(app = "feed", passive = false) {
  const sockets: FakeSocket[] = [], delivered: any[] = [], timers: (() => void)[] = [];
  let ensures = 0, health = 0, reconnects = 0;
  class FakeSocket {
    static OPEN = 1;
    readyState = 1;
    sent: any[] = [];
    handlers = new Map<string, ((arg?: any) => void)[]>();
    constructor(readonly url: string) { sockets.push(this); }
    on(name: string, fn: (arg?: any) => void) { this.handlers.set(name, [...(this.handlers.get(name) || []), fn]); }
    emit(name: string, arg?: any) { for (const fn of this.handlers.get(name) || []) fn(arg); }
    frame(m: any) { this.emit("message", JSON.stringify(m)); }
    send(s: string) { this.sent.push(JSON.parse(s)); }
    close() { this.readyState = 3; this.emit("close"); }
  }
  const ctx: any = {
    WebSocket: FakeSocket, HOST: "127.0.0.1", kernelPort: () => 12345,
    vscode: { env: { sessionId: "test-window" } }, serveToken: () => "test",
    ensureKernel: async () => { ensures++; return true; },
    healthz: async () => { health++; return { ok: true }; },
    intentOp, ReloadHold, ViewDeltas: decoder()?.ViewDeltas, JSON,
    maybeBuildNotice: () => {}, setTimeout: (fn: () => void) => timers.push(fn),
  };
  vm.runInNewContext(pipeCode, ctx);
  const pipe = new ctx.Pipe(app, (m: any) => delivered.push(m), () => reconnects++, undefined, passive);
  await new Promise<void>((resolve) => setImmediate(resolve));
  pipe.webviewReady = true;
  sockets[0].emit("open");
  return { pipe, sockets, delivered, timers, stats: () => ({ ensures, health, reconnects }) };
}

const card = (id: string, text = id) => ({ itemId: id, text });
const feed = (asks = [card("a"), card("b")]) => ({ type: "feed", asks, now: 1, working: ["web"], obsolete: true });
const delta = (base = 0, rev = base + 1) => ({ type: "delta", slot: "feed", base, rev, coll: { asks: { set: { b: card("b", "updated") } } }, rest: { now: 2 } });

for (const passive of [false, true]) {
  test(`the ${passive ? "status" : "panel"} pipe negotiates and applies keyed feed deltas`, async () => {
    const h = await harness("feed", passive), ws = h.sockets[0];
    assert.equal(new URL(ws.url).searchParams.get("delta"), "1");
    ws.frame(feed()); ws.frame(delta());
    assert.equal(h.delivered.length, 2);
    assert.equal(h.delivered[1].type, "feed");
    assert.deepEqual(h.delivered[1].asks, [card("a"), card("b", "updated")]);
    assert.equal(h.delivered[1].now, 2);
    assert.deepEqual(h.delivered[0].asks, [card("a"), card("b")], "previously delivered snapshot remains unchanged");
    assert.equal(h.delivered[1].asks[0], h.delivered[0].asks[0], "untouched cards retain identity");
    assert.equal(h.stats().ensures, passive ? 0 : 1, "the passive status pipe never starts the kernel");
  });
}

test("inserts, deletes, explicit order and replacement remainder match the full feed", async () => {
  const h = await harness(), ws = h.sockets[0];
  ws.frame(feed());
  ws.frame({ type: "delta", slot: "feed", base: 0, rev: 1, restAll: true,
    rest: { type: "feed", now: 3, working: [] },
    coll: { asks: { del: ["a"], set: { c: card("c") }, order: ["c", "b"] } } });
  assert.deepEqual(h.delivered[1], { type: "feed", now: 3, working: [], asks: [card("c"), card("b")] });
});

test("each inapplicable delta retries recovery if the earlier request did not produce a full", async () => {
  const h = await harness(), ws = h.sockets[0];
  ws.frame(delta(4)); ws.frame(delta(5));
  assert.deepEqual(ws.sent, [{ type: "needSlot", slot: "feed" }, { type: "needSlot", slot: "feed" }]);
  assert.equal(h.delivered.length, 0);
  ws.frame(feed()); ws.frame(delta());
  assert.equal(h.delivered.at(-1).asks[1].text, "updated");
  ws.frame(delta(8));
  assert.equal(ws.sent.length, 3, "a later gap also requests recovery");
});

test("an unknown newer slot requests whole frames instead of freezing after its first full", async () => {
  const h = await harness(), ws = h.sockets[0];
  const newer = { type: "newerSlot", rows: [{ id: "a" }] };
  ws.frame(newer);
  ws.frame({ type: "delta", slot: "newerSlot", base: 0, rev: 1, coll: {} });
  ws.frame({ type: "delta", slot: "newerSlot", base: 1, rev: 2, coll: {} });
  assert.deepEqual(h.delivered, [newer]);
  assert.deepEqual(ws.sent, [{ type: "needSlot", slot: "newerSlot" }, { type: "needSlot", slot: "newerSlot" }]);
  ws.frame({ ...newer, rows: [{ id: "b" }] });
  assert.deepEqual(h.delivered.at(-1)!.rows, [{ id: "b" }]);
});

test("closing sockets neither send recovery nor replay it onto the next connection", async () => {
  const h = await harness(), old = h.sockets[0];
  old.frame(delta(4));
  assert.equal(h.pipe.queuedIntents(), 0);
  old.readyState = 2;
  old.frame(delta(5)); old.frame(feed());
  assert.equal(old.sent.length, 1);
  assert.equal(h.delivered.length, 0);
  old.close(); h.timers.shift()!();
  await new Promise<void>((resolve) => setImmediate(resolve));
  const current = h.sockets[1]; current.emit("open");
  assert.deepEqual(current.sent, [], "needSlot belongs to its old socket, not the intent replay queue");
  current.frame(delta());
  assert.deepEqual(current.sent, [{ type: "needSlot", slot: "feed" }]);
});

test("timeline lane and message deltas preserve the unchanged lane", async () => {
  const h = await harness("timeline"), ws = h.sockets[0];
  ws.frame({ type: "bars", turns: { web: [{ id: "a", n: 1 }], api: [{ id: "b" }] },
    judging: { web: [{ k: "j1", n: 1 }], empty: [] }, messages: [{ id: "m1" }], now: 1 });
  const old = h.delivered[0];
  ws.frame({ type: "delta", slot: "bars", base: 0, rev: 1, coll: {
    turns: { set: { "web\u001fa": { id: "a", n: 2 } } },
    judging: { set: { "web\u001fj1": { k: "j1", n: 2 } } },
    messages: { del: ["m1"], set: { m2: { id: "m2" } } },
  } });
  const next = h.delivered[1];
  assert.equal(next.type, "bars");
  assert.deepEqual(next.turns.web, [{ id: "a", n: 2 }]);
  assert.equal(next.turns.api, old.turns.api);
  assert.deepEqual(next.judging.web, [{ k: "j1", n: 2 }]);
  assert.deepEqual(next.judging.empty, []);
  assert.deepEqual(next.messages, [{ id: "m2" }]);
});

test("duplicate and absent ids use the kernel positional keys", async () => {
  const h = await harness(), ws = h.sockets[0];
  ws.frame(feed([card("a"), card("a", "duplicate"), { text: "anonymous" } as any]));
  ws.frame({ type: "delta", slot: "feed", base: 0, rev: 1, coll: { asks: {
    set: { "#1": card("a", "second"), "#2": { text: "anonymous updated" } },
  } } });
  assert.deepEqual(h.delivered[1].asks, [card("a"), card("a", "second"), { text: "anonymous updated" }]);
});

test("separate pipes and replacement sockets cannot share or resurrect a base", async () => {
  const h = await harness(), other = await harness("feed", true), old = h.sockets[0];
  old.frame(feed()); other.sockets[0].frame(delta());
  assert.deepEqual(other.sockets[0].sent, [{ type: "needSlot", slot: "feed" }]);
  old.close(); h.timers.shift()!();
  await new Promise<void>((resolve) => setImmediate(resolve));
  const current = h.sockets[1]; current.emit("open");
  old.frame(delta());
  assert.equal(h.delivered.length, 1, "a replaced socket cannot deliver stale data");
  current.frame(delta());
  assert.deepEqual(current.sent, [{ type: "needSlot", slot: "feed" }]);
  current.frame(feed([card("fresh")]));
  assert.equal(h.delivered.at(-1).asks[0].itemId, "fresh");
  h.pipe.dispose(); current.frame(feed());
  assert.equal(h.delivered.length, 2, "disposed pipes do not deliver");
});

test("legacy full frames and unrelated chat frames still pass through", async () => {
  const h = await harness("chat"), ws = h.sockets[0];
  ws.frame(feed()); ws.frame(feed([card("new")]));
  ws.frame({ type: "chatTail", id: "web", from: 2, events: [] });
  assert.deepEqual(h.delivered, [feed(), feed([card("new")]), { type: "chatTail", id: "web", from: 2, events: [] }]);
});

test("a malformed later collection cannot partly mutate a previously delivered frame", async () => {
  const h = await harness("timeline"), ws = h.sockets[0];
  const original = { type: "bars", turns: { web: [{ id: "a", n: 1 }] }, judging: {}, messages: [] };
  ws.frame(original);
  ws.frame({ type: "delta", slot: "bars", base: 0, rev: 1, coll: {
    turns: { set: { "web\u001fa": { id: "a", n: 2 } } }, messages: { order: ["missing"] },
  } });
  assert.deepEqual(h.delivered, [original]);
  assert.deepEqual(ws.sent, [{ type: "needSlot", slot: "bars" }]);
  ws.frame(original);
  ws.frame({ type: "delta", slot: "bars", base: 0, rev: 1, coll: { messages: { set: { m: { id: "m" } } } } });
  assert.deepEqual(h.delivered.at(-1)!.turns, original.turns);
  assert.deepEqual(h.delivered.at(-1)!.messages, [{ id: "m" }]);
});

test("feed and timeline revisions are independent, and a full frame resets only its slot", async () => {
  const h = await harness(), ws = h.sockets[0];
  ws.frame(feed()); ws.frame({ type: "bars", turns: {}, judging: {}, messages: [] }); ws.frame(delta());
  ws.frame({ type: "delta", slot: "bars", base: 0, rev: 1, coll: { messages: { set: { m: { id: "m" } } } } });
  ws.frame(feed()); ws.frame(delta());
  ws.frame({ type: "delta", slot: "bars", base: 1, rev: 2, coll: { messages: { del: ["m"] } } });
  assert.equal(ws.sent.length, 0);
  assert.deepEqual(h.delivered.at(-1).messages, []);
});

test("kernel-produced frames reassemble to every expected full in both receivers", () => {
  const fixture = JSON.parse(fs.readFileSync(path.resolve(process.cwd(), "../tests/fixtures/extension-view-deltas.json"), "utf8"));
  const browser: any = {};
  // Python freshness coverage generates this from the real encoder and the rendered shim (2026-09-16).
  vm.runInNewContext(fixture.decoder, browser);
  const module = decoder();
  assert.ok(module, "the extension needs a receiver before it can advertise deltas");
  const normalize = (x: any) => JSON.parse(JSON.stringify(x));
  assert.deepEqual(module.VIEW_DELTA_KINDS, fixture.kinds);
  assert.deepEqual(normalize(browser.DELTA_KINDS), fixture.kinds);
  const receiver = new module.ViewDeltas(() => assert.fail("the real encoder stream must not request recovery"));
  assert.ok(fixture.steps.some((s: any) => s.wire.coll?.messages?.order), "numeric-id order must cross the wire");
  assert.ok(fixture.steps.some((s: any) => s.wire.restAll === 1), "use the actual sender remainder flag");
  for (const { wire, full } of fixture.steps) {
    const m = normalize(wire);
    let expected;
    if (m.type === "delta") expected = browser.applyDelta(m);
    else { browser.LAST[m.type] = { rev: 0, msg: m, maps: browser.buildMaps(m) }; expected = m; }
    assert.deepEqual(normalize(expected), full);
    assert.deepEqual(normalize(receiver.receive(normalize(wire))), full);
  }
});

test("an unsupported collection kind fails loudly instead of decoding as a list", () => {
  const module = decoder();
  module.VIEW_DELTA_KINDS.feed.asks = "dict";
  const receiver = new module.ViewDeltas(() => assert.fail("a local table implementation error must be fixed"));
  assert.throws(() => receiver.receive(feed()), /unsupported view collection kind/);
});
