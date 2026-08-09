// The chat statusline's FAST badge — a fourth meta control (mode · model · effort · fast) toggling the
// CLI's fast mode (/fast, Opus-only research preview). The badge exists only when the session REPORTS a
// fast state — the SDK init's fast_mode_state ("on"/"off"/"cooldown"), threaded kernel → status → badge —
// so a session that can't run fast mode (or a tmux session whose statusline doesn't publish it yet) shows
// no dead control. Picking On/Off posts setFast; the kernel delivers the literal "/fast on|off", which the
// SDK input stream interprets (its CLI descriptor is marked supportsNonInteractive, unlike /model).
// render.ts has no jsdom harness → source pins (kernel pins ride along, as in the other meta tests).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");
const KERNEL = fs.readFileSync(path.resolve(process.cwd(), "..", "kernel", "kernel.py"), "utf8");
const SDK = fs.readFileSync(path.resolve(process.cwd(), "..", "kernel", "sdk_backend.py"), "utf8");

test("the fast badge is a meta control that appears only when the session reports a state", () => {
  assert.match(RENDER, /fast\?: string;/);                                   // status carries it
  assert.match(RENDER, /type MetaKind = "mode" \| "model" \| "effort" \| "fast" \| "auth";/);
  assert.match(RENDER, /st\.fast \? "fast" : ""/);                           // no state → no badge
  assert.match(RENDER, /meta\.appendChild\(metaButton\("fast", prettyFast\(st\.fast\)\)\)/);
});

test("the picker offers On/Off and posts setFast; ON wears the CLI's fast orange", () => {
  assert.match(RENDER, /\{ label: "On", value: "on" \}/);
  assert.match(RENDER, /\{ label: "Off", value: "off" \}/);
  assert.match(RENDER, /fast: FAST_CHOICES/);
  assert.match(RENDER, /kind === "fast" \? "setFast"/);                      // the pick posts the op
  assert.match(RENDER, /"on" \? "var\(--fast\)" : ""/);                      // ON tint, off/cooldown default
  assert.match(CSS, /--fast: #ff6a00;/);                                     // the CLI's own fastMode orange
});

test("the kernel threads fast_mode_state from the SDK init to the chat status", () => {
  assert.match(SDK, /d\.get\("fast_mode_state"\)/);                          // init is the authoritative source
  assert.match(SDK, /"fast": self\.fast/);                                   // snapshot carries it
  assert.match(KERNEL, /"fast": st\.get\("fast", ""\)/);                     // merged into the live map
  // a disabled_reason (org-gated / unsupported) hides the toggle rather than offering a dead control
  assert.match(KERNEL, /"fast": "" if tm\.get\("fastReason"\) else tm\.get\("fast", ""\)/);
});

test("setFast is a drive op that parks like /model and /effort", () => {
  assert.match(KERNEL, /"setModel", "setEffort", "setMode", "setFast",/);    // in the drive-op allowlist
  assert.match(KERNEL, /def _set_fast_or_park\(be, sid, value\)/);
  assert.match(KERNEL, /op\[0\] in \("model", "effort", "fast"\)/);          // repeat pick replaces in place
  assert.match(KERNEL, /elif op\[0\] == "fast":/);                           // parked delivery branch
});
