// The chat frame's watermark guard (2026-09-22; frame-guard.ts): a frame built from an older reading than the one the page holds
// is ignored and filed, and a frame that removes a landed human turn is filed whatever its watermark said. The decisions run
// here; the wiring in render.ts (both wires, the rows' names) is pinned by source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { frameOlder, landedHumanKeys, droppedLandedHuman, dropsLandedRow } from "../../ui/webview/frame-guard";

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
  assert.equal(frameOlder(wm(2000, 7), wm(2000, "9" as unknown as number)), false);                  // a backend without a counter answers a string
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

test("the dropped set is the landed human turns the page held that the frame no longer carries, in the page's order", () => {
  const before = [{ kind: "user", uuid: "u1" }, { kind: "assistant", uuid: "a1" }, { kind: "user", uuid: "u2" }, { kind: "user", uuid: "echo:q" }, { kind: "queued", uuid: "optimistic:1" }];
  assert.deepEqual(droppedLandedHuman(before, [{ kind: "user", uuid: "u1" }, { kind: "assistant", uuid: "a1" }, { kind: "assistant", uuid: "a2" }]), ["u2"]);
  assert.deepEqual(droppedLandedHuman(before, before), []);
  assert.deepEqual(droppedLandedHuman(before, []), ["u1", "u2"]);
  assert.deepEqual(droppedLandedHuman(null, before), []);
});

test("the frame-drops-landed row names the wire, the count, the uuids' tails and never the text, the watermark's presence and the expected cause", () => {
  const row = dropsLandedRow("11111111-2222-3333-4444-555555555555", "chatTail", ["71c0681d-aaaa-bbbb-cccc-dddddddddddd"], true, null);
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
