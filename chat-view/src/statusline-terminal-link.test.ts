// The statusline folder (📁 <dir>) is a click-to-open link (the user 2026-06-27): clicking it posts
// openFolder{cwd} to the kernel, which runs the configured opener for that dir (default: the OS opener;
// overridable to a terminal/editor via ROMP_OPEN_FOLDER / ~/.config/romp/open-folder). Click-safe via a
// delegate on the stable #statusline (it rebuilds every push). Source pins (no jsdom for render.ts).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("the folder span carries the openFolder action + its cwd, and reads as a link", () => {
  assert.match(SRC, /dir\.dataset\.act = "openFolder";/);
  assert.match(SRC, /dir\.dataset\.cwd = s\.cwd;/);
  assert.match(SRC, /dir\.classList\.add\("status-dir-link"\)/);
  assert.match(SRC, /click to open this folder/);
});

test("the action is DELEGATED to the stable #statusline (survives the per-push rebuild)", () => {
  assert.match(SRC, /const sl = document\.getElementById\("statusline"\);[\s\S]*?delegate\(sl, \{/);
  assert.match(SRC, /openFolder: \(el\) => \{ const cwd = el\.dataset\.cwd; if \(cwd && vscodeApi\) vscodeApi\.postMessage\(\{ type: "openFolder", cwd \}\); \}/);
});

test("the link has a quiet pointer/hover affordance", () => {
  assert.match(CSS, /\.status-dir-link \{ cursor: pointer; \}/);
  assert.match(CSS, /\.status-dir-link:hover \{ color: var\(--accent\); \}/);
});
