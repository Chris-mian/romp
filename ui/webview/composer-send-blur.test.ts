// The composer Send button. On DESKTOP, sending keeps focus in the textarea so a
// follow-up keeps typing (mousedown + preventDefault, then ta.focus()). On a PHONE
// that same focus keeps the on-screen keyboard up and pins the composer above it,
// so after send we blur instead: the keyboard collapses and the box drops back to
// the bottom of the screen (the user 2026-07-22). Enter is already a newline (not a
// send) on touch, so the Send button is the only mobile send path.
// The chat renderer has no jsdom harness, so — like the other webview tests — pin
// the wiring at the source level.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");

test("Send button blurs on touch (collapse keyboard) and focuses on desktop (keep typing)", () => {
  // one handler, branching on the established coarse-pointer signal
  assert.match(
    RENDER,
    /sendBtn\?\.addEventListener\("mousedown", \(e\) => \{ e\.preventDefault\(\); sendComposer\(\); if \(isCoarsePointer\(\)\) ta\.blur\(\); else ta\.focus\(\); \}\)/,
  );
});

test("mobile is gated on pointer:coarse, not viewport width", () => {
  // desktop chat panes are narrow too, so the mobile signal must be the pointer, not a width breakpoint
  assert.match(RENDER, /function isCoarsePointer\(\): boolean/);
  assert.match(RENDER, /matchMedia\("\(pointer:coarse\)"\)\.matches/);
});

test("the desktop-only unconditional refocus after send is gone", () => {
  // regression: the old handler always ran `sendComposer(); ta.focus();`, which re-opened the mobile keyboard
  assert.doesNotMatch(RENDER, /sendComposer\(\); ta\.focus\(\); \}\)/);
});
