// Chat bottom-bar git branch (the user 2026-06-23): the statusline shows the session's git branch (when it's
// in a repo) just right of the directory, read from the TOP-LEVEL session.gitBranch field. A Settings toggle
// ("Show git branch", ON by default) hides it. The renderer has no jsdom harness, so pin the wiring at source.
// The branch MUST NOT be dug out of the head system event: that event lives at events[0] and the WIRE_TAIL
// window ships only the last 250 events, so on any >250-event session it (and its branch) fall off the wire —
// which blanked the branch on most sessions until the top-level field was added (the user 2026-06-30).
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

test("updateStatusline appends a status-branch span from the top-level gitBranch, gated on the setting", () => {
  // gated on the live setting (default-ON: only `=== false` hides it) AND on a known branch
  assert.match(RENDER, /loadSettings\(\)\.showBranch !== false && s\.gitBranch/);
  // reads the branch off the TOP-LEVEL session field, NOT the windowed head system event
  assert.match(RENDER, /br\.textContent = "⎇ " \+ s\.gitBranch/);
  assert.match(RENDER, /el\("span", "status-branch"\)/);
  // upsert carries the top-level field, falling back to the last-known on a chatTail delta that omits it
  assert.match(RENDER, /gitBranch: msg\.gitBranch \?\? \(prev \? prev\.gitBranch : ""\)/);
});

test("the branch span sits right after the dir, before the meta cluster", () => {
  // ordering: status-dir append → branch block → spinner-meta
  assert.match(RENDER, /right\.appendChild\(dir\);[\s\S]*?status-branch[\s\S]*?const meta = el\("span", "spinner-meta"\)/);
});

test("styles define .status-branch (dim mono, shrinks before the dir)", () => {
  assert.match(CSS, /\.status-branch \{/);
});
