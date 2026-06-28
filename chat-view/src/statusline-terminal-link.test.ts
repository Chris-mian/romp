// Any local-folder location in the chat is a click-to-open link (the user 2026-06-27): the statusline 📁 AND
// the System-context "Directory" row both open the folder. asFolderLink wires a data-act caught by ONE
// document-level openFolder delegate (works under any re-rendering surface). Source pins (no jsdom for render.ts).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("asFolderLink makes an element open the folder (data-act + cwd + affordance)", () => {
  assert.match(SRC, /function asFolderLink\(elem: HTMLElement, cwd: string\): void/);
  assert.match(SRC, /elem\.dataset\.act = "openFolder";/);
  assert.match(SRC, /elem\.dataset\.cwd = cwd;/);
  assert.match(SRC, /elem\.classList\.add\("folder-link"\)/);
  assert.match(SRC, /click to open this folder/);
});

test("it's applied to the statusline folder AND the System-context Directory row", () => {
  assert.match(SRC, /asFolderLink\(dir, s\.cwd\)/);                                  // statusline 📁
  assert.match(SRC, /if \(k === "Directory"\) asFolderLink\(ve, val\)/);            // system-context cwd row
});

test("ONE openFolder delegate covers the whole chat (document.body, survives every rebuild)", () => {
  assert.match(SRC, /delegate\(document\.body, \{\s*\n\s*openFolder: \(el\) => \{ const cwd = el\.dataset\.cwd; if \(cwd && vscodeApi\) vscodeApi\.postMessage\(\{ type: "openFolder", cwd \}\); \}/);
});

test("the folder link has a quiet pointer/hover affordance", () => {
  assert.match(CSS, /\.folder-link \{ cursor: pointer; \}/);
  assert.match(CSS, /\.folder-link:hover \{ color: var\(--accent\); \}/);
});
