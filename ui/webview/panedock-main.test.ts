// THE PANE DOCKING ENGINE's switch read, executed (plans/pane-docking.md phase two). isPaneDockingOn is
// the pure gate: only the literal true in romp:settings turns the kit on, everything else is OFF (the
// fail-safe default for an opt-in that gates a whole layout engine). No DOM.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import { isPaneDockingOn, PANE_DOCKING_CLASS } from "./panedock-main";

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
