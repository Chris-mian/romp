// The DEBUG judging band renders a ⚡ per auto-nudge fire (the user 2026-06-22): data.nudges =
// [{sid,gid,t,count}] → a lightning bolt at its time, coloured by the nudged session, escalating to a red
// warning bolt + tooltip at count>=4. Source-level pin (no jsdom for the SVG timeline renderer).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js"), "utf8");

test("the debug band shows when there are nudge ⚡ marks, even without judge run-spans", () => {
  assert.match(SRC, /data\.nudges && data\.nudges\.some\(\(e\) => inWin\(e\.t\)\)/);
});

test("a ⚡ is drawn per in-window nudge, coloured by the nudged session", () => {
  assert.match(SRC, /for \(const n of \(data\.nudges \|\| \[\]\)\.filter\(\(e\) => inWin\(e\.t\)\)\)/);
  assert.match(SRC, /g\.textContent = '⚡'/);
  assert.match(SRC, /colorOf\(n\.sid\)/, "the bolt is tinted by the nudged session");
});

test("count>=4 escalates to a red warning bolt + a 'check this goal isn't looping' tooltip", () => {
  assert.match(SRC, /const warn = \(n\.count \|\| 1\) >= 4/);
  assert.match(SRC, /#ff5a5a/, "the warn colour");
  assert.match(SRC, /isn\\'t looping/);
});
