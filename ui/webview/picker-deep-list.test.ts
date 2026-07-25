// The + picker's LAZY 30-day list. The user 2026-07-24: typing a session's name into the picker found
// nothing unless it had been touched in the last 48h (discover()'s CAPTION horizon, which the picker had
// inherited by accident), so an older session could not be reopened at all and the only way forward was to
// start a new one. The picker now asks for its own 30-day window, but only once the user reaches for
// something off screen — scrolling to the bottom, or typing — so the first paint and kernel boot stay as
// cheap as they were. Source-level pins (no jsdom for the renderer).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");
const KERNEL = fs.readFileSync(path.resolve(process.cwd(), "..", "kernel", "kernel.py"), "utf8");

test("the deep list is a SECOND request, fired at most once per picker open", () => {
  assert.match(RENDER, /function requestDeepSessions\(\) \{\s*if \(pickerDeep !== "none" \|\| !vscodeApi\) return;/);
  assert.match(RENDER, /pickerDeep = "pending";/);
  assert.match(RENDER, /postMessage\(\{ type: "requestSessions", deep: true \}\)/);
  // the first paint is still the plain, cheap request — no deep flag
  assert.match(RENDER, /postMessage\(\{ type: "requestSessions" \}\)/);
});

test("scrolling to the bottom and typing both reach for the older sessions", () => {
  assert.match(RENDER, /list\.addEventListener\("scroll", \(\) => \{ if \(nearBottom\(list\)\) requestDeepSessions\(\); \}\)/);
  assert.match(RENDER, /search\.addEventListener\("input", \(\) => \{ requestDeepSessions\(\);/);
});

test("each picker open starts back on the cheap list", () => {
  assert.match(RENDER, /pickerDeep = "none"; clearPickerDeepBackstop\(\);/);
});

test("a slow fast-reply cannot clobber a deep list already on screen", () => {
  assert.match(RENDER, /if \(m\.deep\) \{ pickerDeep = "loaded"; clearPickerDeepBackstop\(\); \}/);
  assert.match(RENDER, /else if \(pickerDeep === "loaded"\) return;/);
});

test("the loader can never trap the user: a pending deep fetch has a backstop", () => {
  // a kernel too old to know `deep` answers without the flag, so nothing would resolve the pending state
  assert.match(RENDER, /pickerDeepBackstop = window\.setTimeout\(\(\) => \{\s*if \(pickerDeep === "pending"\) \{ pickerDeep = "none"; renderPickerMoreRow\(\); \}\s*\}, \d+\);/);
  assert.match(RENDER, /function clearPickerDeepBackstop\(\) \{[\s\S]*?clearTimeout\(pickerDeepBackstop\)/);
});

test("the wait wears the romp loader dots, and the footer is not a selectable row", () => {
  assert.match(RENDER, /const dots = el\("div", "rl-dots"\);/);
  assert.match(RENDER, /cap\.textContent = "loading older sessions…";/);
  assert.match(RENDER, /more\.textContent = "showing the last 30 days";/);
  assert.match(CSS, /\.picker-more \{/);
  // .picker-more is deliberately NOT a .picker-row, so filterPicker and the keyboard walk skip it
  assert.doesNotMatch(RENDER, /el\("div", "picker-row picker-more"\)/);
});

test("a deep render keeps the scroll position that triggered it", () => {
  assert.match(RENDER, /const keepScroll = list\.scrollTop;/);
  assert.match(RENDER, /list\.scrollTop = keepScroll;/);
});

test("the kernel honors deep and echoes the flag back", () => {
  assert.match(KERNEL, /PICKER_WINDOW = 30 \* 86400/);
  assert.match(KERNEL, /deep = bool\(msg\.get\("deep"\)\)/);
  assert.match(KERNEL, /"type": "sessionList", "deep": deep/);
  assert.match(KERNEL, /PICKER_WINDOW if deep else None/);
});
