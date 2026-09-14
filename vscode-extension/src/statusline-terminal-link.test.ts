// Any local-folder location in the chat is a click-to-open link (the user 2026-06-27): the statusline 📁 AND
// the System-context "Directory" row both open the folder. asFolderLink wires a data-act caught by ONE
// document-level openFolder delegate (works under any re-rendering surface). Source pins (no jsdom for render.ts).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

// the rule itself lives beside the status line's folder widget since T409 (status-widgets.ts folderLink); render.ts keeps
// asFolderLink as a thin delegate for its other callers (the System-context Directory row)
const SW = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "status-widgets.ts"), "utf8");
test("asFolderLink routes by host: BROWSE on the web, folder-open in VS Code (the user 2026-08-14)", () => {
  assert.match(SRC, /function asFolderLink\(elem: HTMLElement, cwd: string, sid\?: string\): void \{\n\s*folderLink\(elem, cwd, sid\);/);
  // web dashboard → the file browser (works from every device); VS Code keeps the host-side open
  assert.match(SW, /elem\.dataset\.act = web \? "browseFiles" : "openFolder";/);   // pane-local browse needs no shell frame (2026-08-24)
  assert.match(SW, /elem\.dataset\.cwd = cwd;/);
  assert.match(SW, /elem\.classList\.add\("folder-link"\)/);
  assert.match(SW, /click to browse this folder/);
  assert.match(SW, /click to open this folder/);
  // OS-open demoted, not deleted: the folder link's right-click still posts the old openFolder
  assert.match(SRC, /item\.textContent = "Open folder window";/);
});

test("it's applied to the statusline folder AND the System-context Directory row, carrying the session id", () => {
  // the session id (possibly host-prefixed) rides along too — the user 2026-07-03, so a REMOTE session's
  // click can SSH out instead of treating the path as local
  assert.match(SW, /folderLink\(dir, rec\.cwd, rec\.id\);/);                                                // the statusline folder widget (T409), the session id from the record slice
  assert.match(SRC, /host: hostOf\(id\) \};/);                                                                // ...built by render.ts from the active session's id
  assert.match(SRC, /if \(k === "Directory"\) asFolderLink\(ve, val, renderingSid \|\| undefined\)/);            // system-context cwd row
});

test("ONE openFolder delegate covers the whole chat (document.body, survives every rebuild), forwarding the id", () => {
  assert.match(SRC, /openFolder: \(el\) => \{\s*\n\s*const cwd = el\.dataset\.cwd; if \(!cwd \|\| !vscodeApi\) return;\s*\n\s*const id = el\.dataset\.id;\s*\n\s*vscodeApi\.postMessage\(id \? \{ type: "openFolder", cwd, id \} : \{ type: "openFolder", cwd \}\);/);
});

test("the folder link has a quiet pointer/hover affordance", () => {
  assert.match(CSS, /\.folder-link \{ cursor: pointer; \}/);
  assert.match(CSS, /\.folder-link:hover \{ color: var\(--accent\); \}/);
});
