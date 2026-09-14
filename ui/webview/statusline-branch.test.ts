// Chat bottom-bar git branch (the user 2026-06-23): the statusline shows the session's git branch (when it's
// in a repo) just right of the directory, read from the TOP-LEVEL session.gitBranch field. Off by default from
// 2026-08-10 (the user, trimming the statusline for narrow panes), ON by default again since T409 (the user
// 2026-09-13), as the status line's BRANCH WIDGET (status-widgets.ts): the flipped default rides the fresh key
// statusWidgets, and showBranch stays in the store as the widget's MIRROR (a store that carries it keeps that value;
// a fresh install shows the branch). The renderer has no jsdom harness, so pin at source.
// The branch MUST NOT be dug out of the head system event: that event lives at events[0] and the WIRE_TAIL
// window ships only the last 250 events, so on any >250-event session it (and its branch) fall off the wire —
// which blanked the branch on most sessions until the top-level field was added (the user 2026-06-30).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const W = path.resolve(process.cwd(), "..", "ui", "webview");
const RENDER = fs.readFileSync(path.join(W, "render.ts"), "utf8");
const SW = fs.readFileSync(path.join(W, "status-widgets.ts"), "utf8");
const CSS = fs.readFileSync(path.join(W, "styles.css"), "utf8");
const SETTINGS = fs.readFileSync(path.join(W, "settings.ts"), "utf8");
const GEAR = fs.readFileSync(path.join(W, "gear.js"), "utf8");

test("settings carry showBranch as the branch widget's MIRROR (default on since T409); the gear injects no default and has no row of its own", () => {
  assert.match(SETTINGS, /showBranch: boolean/);
  assert.match(SETTINGS, /DEFAULT_SETTINGS[^;]*showBranch: true/);
  assert.match(SETTINGS, /s\.statusWidgets = statusWidgetPrefs\("statusWidgets" in parsed \? parsed\.statusWidgets : undefined\);/,
    "the legacy keys are never read (the one-shot migration): a pre-widgets store's value was the gear's injected default, not a choice");
  assert.doesNotMatch(SETTINGS, /statusWidgetPrefs\([^)]*showBranch/, "no derivation from the legacy keys anywhere in settings.ts");
  assert.doesNotMatch(GEAR, /showBranch: (true|false)/, "no injected default (the fresh-key rule: a merged-in literal would beat a pre-widgets store)");
  assert.doesNotMatch(GEAR, /id=rs-branch|Show git branch|gb = document/, "the checkbox row is gone: the Status line section's Git branch row is the control");
  assert.match(SW, /id: "branch", label: "Git branch", defaultOn: true, slot: "right",/);
});

test("the branch widget renders a status-branch span from the top-level fields, the worktree's branch first; the renderer composes it, never reading the setting itself", () => {
  assert.match(SW, /const liveBr = \(rec\.workTree && rec\.workTree\.branch\) \|\| rec\.gitBranch;/);
  assert.match(SW, /if \(!liveBr\) return null;/, "no branch known: nothing on the line");
  assert.match(SW, /br\.textContent = "⎇ " \+ liveBr;/);
  assert.match(SW, /el\("span", "status-branch"\)/);
  assert.doesNotMatch(RENDER, /loadSettings\(\)\.showBranch|settings\.showBranch/, "the renderer reads the widgets' prefs alone");
  assert.match(RENDER, /composeStatusWidgets\(right, "right", rec, settings\.statusWidgets\);/);
  // upsert carries the top-level field, falling back to the last-known on a chatTail delta that omits it
  assert.match(RENDER, /gitBranch: msg\.gitBranch \?\? \(prev \? prev\.gitBranch : ""\)/);
  assert.match(RENDER, /workTree: msg\.workTree \?\? \(prev \? prev\.workTree : null\)/);
  assert.match(RENDER, /gitBranch: s\.gitBranch \|\| "", workTree: s\.workTree \|\| null/, "the record slice the widgets read carries both");
});

test("the right slot's widgets lead the cluster, before the meta controls", () => {
  assert.match(RENDER, /composeStatusWidgets\(right, "right", rec, settings\.statusWidgets\);[\s\S]*?const meta = el\("span", "spinner-meta"\)/);
});

test("styles define .status-branch (dim mono, shrinks before the dir) and the folder's full-path room", () => {
  assert.match(CSS, /\.status-branch \{/);
  assert.match(CSS, /\.status-dir\.status-dir-full \{ max-width: 380px; \}/);
});
