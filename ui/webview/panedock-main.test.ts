// THE PANE DOCKING ENGINE's switch read, executed (plans/pane-docking.md phase two). isPaneDockingOn is
// the pure gate: only the literal true in romp:settings turns the kit on, everything else is OFF (the
// fail-safe default for an opt-in that gates a whole layout engine). No DOM.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import { isPaneDockingOn, PANE_DOCKING_CLASS, paneTitle } from "./panedock-main";
import * as PDM from "./panedock-main";
// the frame helpers are read by name off the module so a build at a base without them still builds and the test reds on its behaviour
const frameOnce = (PDM as unknown as Record<string, (f: () => void) => number>).frameOnce;
const cancelFrame = (PDM as unknown as Record<string, (h: number) => void>).cancelFrame;
// read by name off the module so a build at a base without the export still builds and the test reds on its behaviour
const titleMapOf = (PDM as unknown as Record<string, (b: ReadonlyArray<{ key: string; text: string }>, rows: unknown) => Record<string, string>>).titleMapOf;
import * as PD from "./panedock-main";
// read by name off the module so a build without the export still builds and this test alone reds (the base run measures it)
const speaksProtocol = (PD as unknown as Record<string, (f: { getAttribute(name: string): string | null }) => boolean>).speaksProtocol;

test("isPaneDockingOn: only the literal true turns the kit on; everything else is OFF", () => {
  assert.equal(isPaneDockingOn('{"paneDocking":true}'), true, "the literal true");
  assert.equal(isPaneDockingOn('{"paneDocking":true,"denseChrome":false}'), true, "beside other keys");
  assert.equal(isPaneDockingOn("{}"), false, "absent: off (the default)");
  assert.equal(isPaneDockingOn(null), false, "no store: off");
  assert.equal(isPaneDockingOn('{"paneDocking":false}'), false, "explicit false: off");
  assert.equal(isPaneDockingOn('{"paneDocking":"yes"}'), false, "a string is not the literal true: off");
  assert.equal(isPaneDockingOn('{"paneDocking":1}'), false, "1 is not the literal true: off");
  assert.equal(isPaneDockingOn("not json"), false, "garbage: off, never a throw");
  assert.equal(isPaneDockingOn("null"), false, "a bare null store: off");
  assert.equal(isPaneDockingOn('"paneDocking"'), false, "a non-object JSON: off");
});

test("the body-class hook is the stable name the later slices key on", () => {
  assert.equal(PANE_DOCKING_CLASS, "pane-docking");
});

// The pane protocol's exclusion (plans/panes-as-data.md, section 3): a URL-source pane is a foreign, sandboxed iframe the
// shell marks data-protocol=none. The kit's mark and detector (markDoc), its message handling (protocolFrame) and the tab
// drag's frame lookup all read this one function; every other frame, marked romp or not marked at all, speaks the protocol.
test("speaksProtocol: only the shell's data-protocol=none mark excludes a frame", () => {
  assert.equal(typeof speaksProtocol, "function", "the engine exports its one protocol read");
  const frame = (attrs: Record<string, string>) => ({ getAttribute: (n: string) => (n in attrs ? attrs[n] : null) });
  assert.equal(speaksProtocol(frame({ "data-protocol": "none" })), false, "a URL pane: no mark, no detector, no message heard");
  assert.equal(speaksProtocol(frame({ "data-protocol": "romp" })), true, "a registry pane in the protocol");
  assert.equal(speaksProtocol(frame({})), true, "the shipped panes carry no mark and speak it");
  assert.equal(speaksProtocol(frame({ "data-protocol": "" })), true, "an empty mark is not the exclusion");
});

// The outline's words come from the pane records (plans/panes-as-data.md section 4): the engine reads the rail's buttons
// (every pane the kernel rendered, shipped and data, by rail key) and the body's data-panes rows into one map, and
// paneTitle names a pane by it; the shipped four keep their words when no map is given, a column is "Chat n".
test("paneTitle names a data pane and the Artifacts pane as the rail does; the shipped words stand without a map", () => {
  assert.equal((paneTitle as unknown as (id: string, t?: Record<string, string>) => string)("notes-pane", { notes: "Notebook" }), "Notebook", "the record's word first (the base names a data pane by its id)");
  const titles = titleMapOf(
    [{ key: "chat", text: "Chat" }, { key: "timeline", text: "Sessions" }, { key: "fleet", text: "Outline" }, { key: "feed", text: "Feed" },
     { key: "files", text: "Files" }, { key: "artifacts", text: "Artifacts" }, { key: "notes", text: "Notes" }, { key: "", text: "stray" }],
    [{ id: "notes", title: "Notebook" }, { id: "docs", title: "Docs" }, { id: 7, title: "x" }, { id: "bad" }]);
  assert.deepEqual(titles, { chat: "Chat", timeline: "Sessions", fleet: "Outline", feed: "Feed", files: "Files", artifacts: "Artifacts", notes: "Notebook", docs: "Docs" },
    "the rail's words, the records' titles over them, a keyless button and a malformed row dropped");
  assert.equal(paneTitle("notes-pane", titles), "Notebook");
  assert.equal(paneTitle("artifacts-pane", titles), "Artifacts");
  assert.equal(paneTitle("docs-pane", titles), "Docs");
  assert.equal(paneTitle("tl-pane", titles), "Sessions");
  assert.equal(paneTitle("chat-pane-3", titles), "Chat 3", "a column keeps its number");
  assert.equal(paneTitle("later-pane", titles), "later-pane", "a pane no record names is its id");
  assert.deepEqual(["chat-pane", "fleet-pane", "feed-pane", "files-pane", "tl-pane"].map((id) => paneTitle(id)), ["Chat", "Outline", "Feed", "Files", "Sessions"], "no map: the shipped words");
  assert.equal(titleMapOf([], "not an array") && Object.keys(titleMapOf([], null)).length, 0, "no rows: no titles, never a throw");
});

// One layout per animation frame for a divider drag (plans/pane-docking.md section 12): frameOnce arms the callback with the
// window's requestAnimationFrame and returns its handle; a window without one (a test's stub) runs it at once and returns 0;
// cancelFrame drops an armed callback and is inert for a 0 handle or a window without cancelAnimationFrame.
test("frameOnce arms one animation frame, runs at once without one; cancelFrame drops an armed frame", () => {
  assert.equal(typeof frameOnce, "function", "the engine exports its frame helper"); assert.equal(typeof cancelFrame, "function");
  const g = globalThis as unknown as { window?: unknown };
  const saved = g.window;
  try {
    const armed: Array<{ id: number; cb: () => void }> = []; let ids = 0; const cancelled: number[] = [];
    g.window = { requestAnimationFrame: (cb: () => void) => { armed.push({ id: ++ids, cb }); return ids; }, cancelAnimationFrame: (h: number) => { cancelled.push(h); } };
    let ran = 0;
    const h = frameOnce(() => { ran++; });
    assert.equal(h, 1, "the frame's handle"); assert.equal(ran, 0, "not run yet: the frame runs it"); assert.equal(armed.length, 1);
    armed[0].cb(); assert.equal(ran, 1);
    cancelFrame(2); assert.deepEqual(cancelled, [2]); cancelFrame(0); assert.deepEqual(cancelled, [2], "a 0 handle cancels nothing");
    g.window = {};
    let now = 0; const h2 = frameOnce(() => { now++; });
    assert.equal(h2, 0, "no requestAnimationFrame: run at once, handle 0"); assert.equal(now, 1);
    assert.doesNotThrow(() => cancelFrame(5), "no cancelAnimationFrame: inert");
  } finally { g.window = saved; }
});
