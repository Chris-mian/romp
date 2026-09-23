// The chat frame's watermark guard (2026-09-22; frame-guard.ts): a frame built from an older reading than the one the page holds
// is ignored and filed, a frame that removes a landed human turn is filed whatever its watermark said, and a reconnect forgets the
// held watermarks (2026-09-23). The decisions run here; the wiring in render.ts (both wires, the rows' names, the three reconnect-class
// call sites) is pinned by source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { frameOlder, landedHumanKeys, droppedLandedHuman, dropsLandedRow, forgetHeldWm, isTransient, TRANSIENT_KEY_PREFIXES, type FrameWm } from "../../ui/webview/frame-guard";

const LEAF = "/tmp/TESTHOST/projects/notes-api/11111111-2222-3333-4444-555555555555.jsonl";
const wm = (size: number, live: number, extra: Partial<{ leaf: string; tx: unknown }> = {}) =>
  ({ leaf: LEAF, tx: [[1790000000.5, size], [1790000001.0, 40]], live, ...extra });

test("an older parse under a newer live tail is older: the shape the user watched (the landed record not read yet, the echo still in)", () => {
  assert.equal(frameOlder(wm(2000, 7), wm(1500, 9)), true);    // fewer transcript bytes read, more live changes: older
  assert.equal(frameOlder(wm(2000, 7), wm(1500, 7)), true);
  assert.equal(frameOlder(wm(1500, 7), wm(2000, 7)), false);   // the newer parse applies
});

test("the same parse with a smaller live revision is older; a larger or equal one is not", () => {
  assert.equal(frameOlder(wm(2000, 7), wm(2000, 6)), true);
  assert.equal(frameOlder(wm(2000, 7), wm(2000, 7)), false);
  assert.equal(frameOlder(wm(2000, 7), wm(2000, 8)), false);
});

test("two leaves (a fork, a rewind), a key of another shape, a mixed reading and a missing part are never older", () => {
  assert.equal(frameOlder(wm(2000, 7), wm(1500, 7, { leaf: LEAF + ".2" })), false);
  assert.equal(frameOlder(wm(2000, 7), { leaf: LEAF, tx: [[1790000000.5, 1500]], live: 7 }), false);   // one row against two
  assert.equal(frameOlder({ leaf: LEAF, tx: [[1, 2000], [1, 40]], live: 7 }, { leaf: LEAF, tx: [[1, 1500], [2, 60]], live: 7 }), false);   // transcript behind, states ahead
  assert.equal(frameOlder(wm(2000, 7), { leaf: LEAF, live: 3 }), false);                              // no key on one side
  assert.equal(frameOlder({ leaf: LEAF, live: 7 }, { leaf: LEAF, live: 3 }), true);                    // no key on either: the revision decides
  assert.equal(frameOlder(wm(2000, 7), wm(2000, "9" as unknown as number)), false);                  // an older kernel's string revision (a backend without a counter)
  assert.equal(frameOlder(wm(2000, 7), wm(2000, null as unknown as number)), false);                 // today's kernel carries no live component for such a backend: the rows alone order its frames
  assert.equal(frameOlder(wm(2000, null as unknown as number), wm(1500, null as unknown as number)), true);
  assert.equal(frameOlder(undefined, wm(1, 1)), false);
  assert.equal(frameOlder(wm(1, 1), null), false);
});

test("a row compares as Python compares a tuple: the mtime first, then the size", () => {
  assert.equal(frameOlder({ leaf: LEAF, tx: [[2.0, 100]], live: 1 }, { leaf: LEAF, tx: [[1.0, 900]], live: 1 }), true);    // an earlier mtime is older whatever the size
  assert.equal(frameOlder({ leaf: LEAF, tx: [[1.0, 900]], live: 1 }, { leaf: LEAF, tx: [[2.0, 100]], live: 1 }), false);
  assert.equal(frameOlder({ leaf: LEAF, tx: [["a", 1]], live: 1 }, { leaf: LEAF, tx: [["b", 1]], live: 1 }), false);       // a row that is not numbers: unordered
});

test("a landed human turn is a recorded user event typed by the person: echoes, the page's own bubbles, romp's lines, harness records and verdicts are not", () => {
  const evs = [
    { kind: "user", uuid: "u1" },
    { kind: "user", uuid: "echo:abc" },
    { kind: "user", uuid: "optimistic:1790" },
    { kind: "queued", uuid: "held:sid" },
    { kind: "user", uuid: "u2", romp: true },
    { kind: "user", uuid: "u3", rompAuto: true },
    { kind: "user", uuid: "u4", rompSystem: true },
    { kind: "user", uuid: "u5", source: { kind: "task" } },
    { kind: "user", uuid: "u6", undelivered: true },
    { kind: "assistant", uuid: "a1" },
    { kind: "user" },
    { kind: "user", uuid: "u7" },
  ];
  assert.deepEqual(landedHumanKeys(evs), ["u1", "u7"]);
});

test("the kernel's transient live-tail keys are not landed turns: a Codex echo or a command chip that retires drops nothing", () => {
  // build_session emits all three as {kind:"user", human:true}; each retires routinely (the echo once its text is in the transcript, the
  // chip when its gesture lands), and before 2026-09-23 only "echo:" was excluded, so every Codex send and every /model filed a false row
  const before = [
    { kind: "user", uuid: "11111111-2222-4333-8444-000000000001", human: true },
    { kind: "user", uuid: "echo-abcd1234", human: true },
    { kind: "user", uuid: "cmd:1700000000:model", human: true },
    { kind: "user", uuid: "echo:11111111222233334444555555555555", human: true },
    { kind: "assistant", uuid: "11111111-2222-4333-8444-00000000000a" },
  ];
  const after = [before[0], before[4], { kind: "user", uuid: "cmdg:1700000000:model" }];   // the chip retired into the durable cmdGesture note, both echoes retired
  assert.deepEqual(droppedLandedHuman(before, after), []);
  assert.deepEqual(landedHumanKeys(before), ["11111111-2222-4333-8444-000000000001"]);
  for (const p of TRANSIENT_KEY_PREFIXES) assert.equal(isTransient(p + "x"), true, p);
  assert.equal(isTransient("cmdg:1700000000:model"), false, "the durable note that takes a chip's slot is a recorded event");
  assert.equal(isTransient("11111111-2222-4333-8444-000000000001"), false);
  assert.equal(isTransient(undefined), false);
});

test("the page's transient-key list is the kernel's tuple, member for member", () => {
  const KERNEL = fs.readFileSync(path.resolve(process.cwd(), "..", "kernel", "kernel.py"), "utf8");
  const m = KERNEL.match(/^_TRANSIENT_KEY_PREFIXES = \(([^)]*)\)/m);
  assert.ok(m, "kernel.py declares _TRANSIENT_KEY_PREFIXES as a tuple literal");
  const members = (m![1].match(/"[^"]+"/g) || []).map((x) => x.slice(1, -1));
  assert.deepEqual([...TRANSIENT_KEY_PREFIXES], members);
  assert.ok(members.length >= 3);
});

test("a reconnect forgets the held watermarks: a restarted kernel's frame, same leaf and rows at live 0, applies with no frame-stale row", () => {
  // the kernel's live-tail revision is a per-process counter (sdk_backend.py _live_rev; live_rev reads 0 for a sid it has not touched),
  // so after a restart with the dashboard open a held session whose files have not moved is served frames frameOlder reads as older
  type S = { wm?: FrameWm; events: unknown[] };
  const sessions = new Map<string, S>([
    ["11111111-2222-4333-8444-000000000001", { wm: wm(2000, 57), events: [] }],
    ["TESTHOST:11111111-2222-4333-8444-000000000002", { wm: wm(900, 12), events: [] }],
    ["11111111-2222-4333-8444-000000000003", { events: [] }],   // a session that never saw a watermark (an older kernel's frames)
  ]);
  const restarted = wm(2000, 0);
  const held = sessions.get("11111111-2222-4333-8444-000000000001")!;
  assert.equal(frameOlder(held.wm, restarted), true, "the defect: without the reset the restarted kernel's frame reads as older and is refused");
  // the relay's reopen (romp:hostRelayUp) forgets that host's sids only
  const hostOf = (id: string) => { const i = id.indexOf(":"); return i > 0 ? id.slice(0, i) : ""; };
  assert.deepEqual(forgetHeldWm(sessions, (sid) => hostOf(sid) === "TESTHOST"), ["TESTHOST:11111111-2222-4333-8444-000000000002"]);
  assert.equal(sessions.get("TESTHOST:11111111-2222-4333-8444-000000000002")!.wm, undefined);
  assert.deepEqual(held.wm, wm(2000, 57), "the local session's watermark stands: its kernel did not restart");
  // the local socket's reopen (the shim's wsup frame; the pane's pipeState up edge) forgets every held one
  assert.deepEqual(forgetHeldWm(sessions, null), ["11111111-2222-4333-8444-000000000001"], "the sids forgotten: not the one already bare");
  assert.equal(held.wm, undefined);
  assert.equal("wm" in held, false, "deleted, as the session record types it optional");
  assert.equal(frameOlder(held.wm, restarted), false, "the frame applies: a page holding no watermark takes any build, as the kernel's reset rule has it");
  // the next frame applied becomes the held watermark again, and the guard resumes from it
  held.wm = restarted;
  assert.equal(frameOlder(held.wm, wm(2000, 1)), false);
  assert.equal(frameOlder(wm(2000, 1), held.wm), true);
  assert.deepEqual(forgetHeldWm(new Map(), null), []);
});

test("render.ts forgets the held watermarks on its three reconnect-class events, in frame order on the local socket", () => {
  const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
  assert.match(RENDER, /import \{ type FrameWm, frameOlder, droppedLandedHuman, dropsLandedRow, forgetHeldWm \} from "\.\/frame-guard";/);
  assert.equal((RENDER.match(/forgetHeldWm\(/g) || []).length, 3, "three call sites and no other");
  // the local socket: the shim's {type:"wsup"} FRAME, not the romp:wsup onopen event, whose reset a dead-socket frame still draining could re-latch
  const up = RENDER.indexOf('else if (m.type === "wsup") {'), upEnd = RENDER.indexOf('else if (m.type === "status")', up);
  assert.ok(up > 0 && upEnd > up, "the wsup frame handler");
  const wsup = RENDER.slice(up, upEnd);
  assert.match(wsup, /onSocketUp\(skeletonTabs\);/);
  assert.match(wsup, /forgetHeldWm\(sessions, null\);/, "every host's, as the kernel's ready reset drops every base");
  for (const line of RENDER.split("\n").filter((l) => l.includes('addEventListener("romp:wsup"'))) assert.doesNotMatch(line, /forgetHeldWm/, "not at onopen: " + line.trim().slice(0, 80));
  // the relay's reopen: that host's sids only
  const rel = RENDER.indexOf('window.addEventListener("romp:hostRelayUp", (e) => {'), relEnd = RENDER.indexOf("\n});", rel);
  assert.ok(rel > 0 && relEnd > rel, "the relay reopen listener");
  assert.match(RENDER.slice(rel, relEnd), /if \(h\) forgetHeldWm\(sessions, \(sid\) => hostOf\(sid\) === h\);/);
  // the extension pane's pipe up edge (it never sees wsup)
  assert.match(RENDER, /if \(m\.type === "pipeState" && m\.up\) \{ reaskWaitingSubagents\(\); forgetHeldWm\(sessions, null\); \}/);
  // the premise: the kernel's counter starts at 0 in every process
  const SDK = fs.readFileSync(path.resolve(process.cwd(), "..", "kernel", "sdk_backend.py"), "utf8");
  assert.match(SDK, /return \(getattr\(self, "_live_rev", None\) or \{\}\)\.get\(sid, 0\)/, "live_rev reads 0 for an untouched sid");
});

test("the dropped set is the landed human turns the page held that the frame no longer carries, in the page's order", () => {
  const before = [{ kind: "user", uuid: "u1" }, { kind: "assistant", uuid: "a1" }, { kind: "user", uuid: "u2" }, { kind: "user", uuid: "echo:q" }, { kind: "queued", uuid: "optimistic:1" }];
  assert.deepEqual(droppedLandedHuman(before, [{ kind: "user", uuid: "u1" }, { kind: "assistant", uuid: "a1" }, { kind: "assistant", uuid: "a2" }]), ["u2"]);
  assert.deepEqual(droppedLandedHuman(before, before), []);
  assert.deepEqual(droppedLandedHuman(before, []), ["u1", "u2"]);
  assert.deepEqual(droppedLandedHuman(null, before), []);
});

test("the frame-drops-landed row names the wire, the count, the uuids' tails and never the text, the watermark's presence and the expected cause", () => {
  const row = dropsLandedRow("11111111-2222-3333-4444-555555555555", "chatTail", ["11111111-2222-4333-8444-dddddddddddd"], true, null);
  assert.deepEqual(row, { id: "11111111-2222-3333-4444-555555555555", type: "chatTail", n: 1, keys: ["dddddddddddd"], wm: true, expected: null });
  assert.equal(dropsLandedRow("s", "session", ["a", "b"], false, "rebased").expected, "rebased");
  assert.equal((dropsLandedRow("s", "session", new Array(20).fill("u"), false, null).keys as string[]).length, 8, "bounded: eight tails at most");
});

test("render.ts applies the guard on both wires and files both rows; the kernel stamps every chat frame and refuses an older build to a base holder", () => {
  const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
  const up = RENDER.indexOf("function upsert(msg: any) {"), tail = RENDER.indexOf("function chatTail(msg: any) {");
  assert.ok(up > 0 && tail > up);
  const upsert = RENDER.slice(up, RENDER.indexOf("\nfunction ", up + 10));
  const chatTail = RENDER.slice(tail, RENDER.indexOf("\nfunction ", tail + 10));
  for (const [name, body] of [["upsert", upsert], ["chatTail", chatTail]] as const) {
    assert.match(body, /frameOlder\(/, name + " reads the watermark");
    assert.match(body, /chatDiagRow\("frame-stale"/, name + " files an ignored older frame");
    assert.match(body, /chatDiagRow\("frame-drops-landed", dropsLandedRow\(/, name + " files a vanished landed turn");
  }
  // the stale check runs BEFORE the ask latch is cleared and before any event is touched (upsert), and before the strip (chatTail)
  assert.ok(upsert.indexOf('chatDiagRow("frame-stale"') < upsert.indexOf("awaitingFull.delete(msg.id)"), "the refusal leaves the ask latch standing");
  assert.ok(chatTail.indexOf('chatDiagRow("frame-stale"') < chatTail.indexOf("stripOptimistic(s);"), "the refusal touches no resident event");
  assert.match(RENDER, /wm\?: FrameWm;/, "the session keeps the newest frame's watermark");
  const KERNEL = fs.readFileSync(path.resolve(process.cwd(), "..", "kernel", "kernel.py"), "utf8");
  assert.match(KERNEL, /"wm": _chat_wm\(sess\["path"\], parsed, _wm_live\)/, "build_session stamps the frame");
  assert.match(KERNEL, /if pc is not None and _chat_wm_older\(m\.get\("wm"\), \(c\.get\("echatWm"\) or \{\}\)\.get\(sid\)\):/, "the sender refuses an older build to a base holder");
  assert.equal((KERNEL.match(/tail\["wm"\] = m\.get\("wm"\)/g) || []).length, 2, "both delta wires carry the watermark");
  assert.equal((KERNEL.match(/_chat_wm_note\(c, sid, m\)/g) || []).length, 4, "every echat write records the watermark handed");
});
