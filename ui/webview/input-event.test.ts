import { test } from "node:test";
import * as assert from "node:assert/strict";
import { INPUT_EVENT_TYPES, isInputEvent, inInputEvent } from "./input-event";

// T416 round two: a jump the feed notes must have run inside the reader's input event, and the chat's announcement to
// the shell says whether the reader made the switch. The rule is read off window.event, the event under dispatch.
test("the reader's input events: clicks, keys, pointer and touch presses and releases", () => {
  for (const t of ["click", "auxclick", "dblclick", "contextmenu", "keydown", "keyup", "keypress", "pointerdown", "pointerup", "mousedown", "mouseup", "touchstart", "touchend"]) {
    assert.ok(INPUT_EVENT_TYPES.has(t), t);
    assert.equal(isInputEvent({ type: t }), true, t);
  }
});

test("a message frame, a timer's nothing, a scroll, a focus change or a garbage value is not the reader's input", () => {
  for (const v of [undefined, null, 0, "click", {}, { type: 7 }, { type: "message" }, { type: "scroll" }, { type: "focus" }, { type: "input" }, { type: "load" }]) {
    assert.equal(isInputEvent(v), false, String(v && (v as any).type));
  }
});

test("inInputEvent reads the window's current event", () => {
  assert.equal(inInputEvent({ event: { type: "keydown" } }), true);
  assert.equal(inInputEvent({ event: { type: "message" } }), false);
  assert.equal(inInputEvent({}), false, "no dispatch under way: a timer, a promise, a render");
});
