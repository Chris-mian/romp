// The new-session DIRECTORY field + per-session dir display (the user 2026-06-22). A session's working
// directory is fixed at creation, so the picker lets you choose it (prefilled from the gear default, recent
// dirs autocompleting), and every session shows its dir — dimmed basename on the lane tab (full path on
// hover) and in the system-context card's collapsed summary. Source-level pins (no jsdom for the renderer).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");
const SETTINGS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "settings.ts"), "utf8");

test("the picker has a directory field with a recent-dirs datalist", () => {
  assert.match(RENDER, /el\("input", "picker-dir-input"\)/);
  assert.match(RENDER, /dirInput\.setAttribute\("list", "picker-dir-list"\)/);
  assert.match(RENDER, /createElement\("datalist"\); dirList\.id = "picker-dir-list"/);
  // appended into the picker box
  assert.match(RENDER, /box\.appendChild\(dirWrap\);/);
});

test("createSession carries the chosen dir, alongside name + backend", () => {
  assert.match(RENDER, /type: "createSession", name, backend: loadSettings\(\)\.backend, dir: dirInput\.value\.trim\(\)/);
});

test("the dir field is prefilled with the gear default and hidden in pick-mode", () => {
  assert.match(RENDER, /di\.value = loadSettings\(\)\.defaultDir \|\| kernelDefaultDir \|\| ""/);
  assert.match(RENDER, /dirWrap\.style\.display = pick \? "none" : ""/);
});

test("renderPicker populates the datalist from items' dirs (unique, non-empty)", () => {
  assert.match(RENDER, /getElementById\("picker-dir-list"\)/);
  assert.match(RENDER, /const d = \(it\.dir \|\| ""\)\.trim\(\);/);
  assert.match(RENDER, /seen\.has\(d\)/);
});

test("a session carries cwd, shown on the statusline just left of the mode/model/effort controls", () => {
  assert.match(RENDER, /interface Session \{[^}]*cwd\?: string/);
  assert.match(RENDER, /cwd: msg\.cwd \?\? \(prev \? prev\.cwd : ""\)/);
  // a status-dir element (basename + full path on hover), appended BEFORE #spinner-meta (the controls cluster)
  assert.match(RENDER, /el\("span", "status-dir"\)/);
  assert.match(RENDER, /dir\.title = s\.cwd/);
  assert.match(RENDER, /sl\.appendChild\(dir\);[\s\S]*?const meta = el\("span", "spinner-meta"\)/);
  // and NOT on the tab anymore (the user 2026-06-23)
  assert.doesNotMatch(RENDER, /tab-dir/);
});

test("the system-context card shows the dir basename in its collapsed summary", () => {
  assert.match(RENDER, /bits\.push\("📁 " \+ \(ev\.cwd/);
});

test("the status-dir and picker-dir-input styles exist", () => {
  assert.match(CSS, /\.status-dir \{/);
  assert.match(CSS, /\.picker-dir-input \{/);
});

test("a Browse button opens the host-native folder dialog (browseDir → browseResult fills the field)", () => {
  assert.match(RENDER, /el\("button", "picker-browse"\)/);
  assert.match(RENDER, /postMessage\(\{ type: "browseDir" \}\)/);
  assert.match(RENDER, /m\.type === "browseResult"[\s\S]*?di\.value = m\.path/);
  assert.match(CSS, /\.picker-browse \{/);
});

test("the dir field prefills with the kernel's real default path (not blank), still editable", () => {
  assert.match(RENDER, /if \(typeof m\.defaultDir === "string"\) kernelDefaultDir = m\.defaultDir/);
  assert.match(RENDER, /di\.value = loadSettings\(\)\.defaultDir \|\| kernelDefaultDir \|\| ""/);
});

test("defaultDir is a persisted setting with an empty default", () => {
  assert.match(SETTINGS, /defaultDir: string;/);
  assert.match(SETTINGS, /defaultDir: ""/);
});
