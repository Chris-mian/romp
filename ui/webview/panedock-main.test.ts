// THE PANE DOCKING ENGINE's switch read, executed (plans/pane-docking.md phase two). isPaneDockingOn is
// the pure gate: only the literal true in romp:settings turns the kit on, everything else is OFF (the
// fail-safe default for an opt-in that gates a whole layout engine). No DOM.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import { isPaneDockingOn, PANE_DOCKING_CLASS } from "./panedock-main";
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
