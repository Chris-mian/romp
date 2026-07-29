// The kernel's LOUD channel (the user 2026-07-29). An op naming a session this kernel doesn't have used to
// degrade into a no-op — the tmux backend typed at a pane that wasn't there — so typed messages vanished with
// no bubble, no error and no record. The kernel now refuses and emits `err`; this pins the two panes that can
// fire such an op rendering it as a DIALOG rather than a fading toast, and handing the text back.
//
// `err` is deliberately a separate type from `warn`: warn is right for "that name has a bad character" and
// wrong for "the message you just typed was never sent." No jsdom for these renderers, so pin at source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

test("chat: an `err` takes the confirm MODAL, not the warn toast", () => {
  assert.match(RENDER, /else if \(m\.type === "err" && typeof m\.text === "string" && m\.text\) \{/);
  assert.match(RENDER, /showConfirm\(typeof m\.title === "string" && m\.title \? m\.title : "That action was not delivered", m\.text,/);
  // the fading toast stays for the soft cases it was written for
  assert.match(RENDER, /m\.type === "warn" && typeof m\.text === "string" && m\.text\) warnToast\(m\.text\);/);
});

test("chat: the refused text is offered back, because the composer already cleared it", () => {
  assert.match(RENDER, /const copy = typeof m\.copy === "string" \? m\.copy : "";/);
  assert.match(RENDER, /copy \? \[\{ label: "Copy my text", value: "copy" \}, \{ label: "Dismiss", value: "ok" \}\]/);
  assert.match(RENDER, /\(v\) => \{ if \(v === "copy"\) navigator\.clipboard\?\.writeText\(copy\); \}/);
  // no text to hand back (an interrupt, a compact) → just the dismiss
  assert.match(RENDER, /: \[\{ label: "Dismiss", value: "ok" \}\],/);
});

test("feed: the pane that fires card ops gets an error dialog of its own", () => {
  // it had NONE: kernel `warn` has no handler on this page at all, and feedToast fades
  assert.doesNotMatch(FEED, /m\.type === "warn"/);
  assert.match(FEED, /function showErrDialog\(title: string, text: string, copy: string\)/);
  assert.match(FEED, /\} else if \(m\.type === "err" && typeof m\.text === "string" && m\.text\) \{/);
  assert.match(FEED, /showErrDialog\(typeof m\.title === "string" && m\.title \? m\.title : "That action was not delivered",/);
});

test("feed: the dialog reuses the resume-picker chrome rather than inventing another look", () => {
  const dlg = FEED.split("function showErrDialog(")[1].split("\n}")[0];
  assert.match(dlg, /el\("div", "pickdlg-overlay"\)/);
  assert.match(dlg, /el\("div", "pickdlg-box"\)/);
  assert.match(dlg, /el\("div", "pickdlg-title"\)/);
  // one style is added, for prose the all-buttons picker dialog never needed
  assert.match(dlg, /el\("div", "pickdlg-detail"\)/);
  assert.match(CSS, /\.pickdlg-detail \{/);
  // dismissible by button OR backdrop — an error must never trap the pane
  assert.match(dlg, /ok\.onclick = \(\) => overlay\.remove\(\);/);
  assert.match(dlg, /overlay\.onclick = \(e\) => \{ if \(e\.target === overlay\) overlay\.remove\(\); \};/);
});

test("feed: copying acknowledges the click, per the always-acknowledge rule", () => {
  const dlg = FEED.split("function showErrDialog(")[1].split("\n}")[0];
  assert.match(dlg, /c\.onclick = \(\) => \{ navigator\.clipboard\?\.writeText\(copy\); c\.textContent = "Copied"; \};/);
});
