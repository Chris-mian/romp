// The + dialog's HOST picker (federation, the user 2026-07-02): local | each attached SSH host, so a new
// session can be created ON a remote kernel (the federation manager routes createSession over that host's
// tunnel; the tab arrives prefixed host:name). Source-pin over render.ts, like picker-backend.test.ts.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");

test("the + dialog builds a Host row listing local + attached hosts, hidden with none attached", () => {
  assert.match(RENDER, /const hostWrap = el\("div", "picker-backend picker-host"\)/);
  assert.match(RENDER, /box\.appendChild\(hostWrap\)/);
  // options rebuilt each open from the federation manager's live host list
  assert.match(RENDER, /__rompFed\?\.hosts\?\.\(\)/);
  assert.match(RENDER, /hostWrapEl\.style\.display = pick \|\| !hosts\.length \? "none" : ""/);
});

test("createSession carries the picked host (empty = local) so the manager routes it to that kernel", () => {
  assert.match(RENDER, /const hostSel = \(hostWrap\.querySelector\("\.picker-be-opt\.sel"\) as HTMLElement \| null\)\?\.dataset\.host \|\| ""/);
  assert.match(RENDER, /startCreate\(\{ name, backend: beSel\?\.dataset\.be \|\| loadSettings\(\)\.backend,\s*\n\s*dir: dirInput\.value\.trim\(\), host: hostSel \}\)/);
  // the PROVISIONAL tab (2026-07-30, which replaced the "Opening…" cue) must be matched against the
  // PREFIXED tab name a remote create produces — provisionalName() is where that join is spelled
  assert.match(RENDER, /openProvisional\(req\);/);
});

test("picking a remote host disables the (host-local) Browse… dialog", () => {
  assert.match(RENDER, /browse\.disabled = !!h/);
});
