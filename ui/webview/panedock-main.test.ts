// THE PANE DOCKING ENGINE's switch read, executed (plans/pane-docking.md phase two). isPaneDockingOn is
// the pure gate: only the literal true in romp:settings turns the kit on, everything else is OFF (the
// fail-safe default for an opt-in that gates a whole layout engine). No DOM.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import { isPaneDockingOn, PANE_DOCKING_CLASS, paneTitle } from "./panedock-main";
import * as PDM from "./panedock-main";
import * as fs from "node:fs";
import * as path from "node:path";
const ENGINE = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "panedock-main.ts"), "utf8");
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

// A CHAT COLUMN's frame is classified by the exact id shape the split script mints, never by the `f-chat-` prefix (the 1920 read: a
// registry pane `chat-notes` renders as `f-chat-notes` and was sorted into the chat: no grab detector, the chat's strip style).
test("isChatFrame: f-chat and f-chat-<n> are chat columns; a registry pane whose id begins chat- is not", () => {
  const isChatFrame = (PDM as unknown as Record<string, (id: string) => boolean>).isChatFrame;
  assert.equal(typeof isChatFrame, "function", "the engine exports its one chat-frame read");
  assert.equal(isChatFrame("f-chat"), true); assert.equal(isChatFrame("f-chat-2"), true); assert.equal(isChatFrame("f-chat-14"), true);
  assert.equal(isChatFrame("f-chat-notes"), false, "a registry pane's frame"); assert.equal(isChatFrame("f-chat-"), false); assert.equal(isChatFrame("f-chatter"), false);
  assert.equal(isChatFrame("f-files"), false); assert.equal(isChatFrame("f-notes"), false);
  assert.equal((ENGINE.match(/isChatFrame\(f\.id\)/g) || []).length, 2, "both sites read it: the strip style's injection and the grab detector's exclusion");
  assert.doesNotMatch(ENGINE, /f\.id\.indexOf\("f-chat-"\) === 0/, "no prefix test remains");
});
