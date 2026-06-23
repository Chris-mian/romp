// Chat bottom-bar git branch (the user 2026-06-23): the statusline shows the session's git branch (when it's
// in a repo) just right of the directory, pulled from the system-context event. A Settings toggle ("Show git
// branch", ON by default) hides it. The renderer has no jsdom harness, so pin the wiring at source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const W = path.resolve(process.cwd(), "..", "ui", "webview");
const RENDER = fs.readFileSync(path.join(W, "render.ts"), "utf8");
const CSS = fs.readFileSync(path.join(W, "styles.css"), "utf8");
const SETTINGS = fs.readFileSync(path.join(W, "settings.ts"), "utf8");

test("settings carry showBranch, defaulting ON", () => {
  assert.match(SETTINGS, /showBranch: boolean/);
  assert.match(SETTINGS, /DEFAULT_SETTINGS[^;]*showBranch: true/);
});

test("updateStatusline appends a status-branch span from the system event, gated on the setting", () => {
  // gated on the live setting (default-ON: only `=== false` hides it)
  assert.match(RENDER, /loadSettings\(\)\.showBranch !== false/);
  // reads the branch off the system-context event (same source as the tab tooltip)
  assert.match(RENDER, /s\.events\.find\(\(e\) => e\.kind === "system"\)[\s\S]*?sys\?\.gitBranch/);
  assert.match(RENDER, /el\("span", "status-branch"\)/);
});

test("the branch span sits right after the dir, before the meta cluster", () => {
  // ordering: status-dir append → branch block → spinner-meta
  assert.match(RENDER, /sl\.appendChild\(dir\);[\s\S]*?status-branch[\s\S]*?const meta = el\("span", "spinner-meta"\)/);
});

test("styles define .status-branch (dim mono, shrinks before the dir)", () => {
  assert.match(CSS, /\.status-branch \{/);
});
