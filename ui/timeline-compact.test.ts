// Timeline compacting + compact-click fixes (the user 2026-06-29). No DOM harness for the SVG draw path, so
// pin the wiring at the source: (1) the compacting battery's "compression" sweep rides a PERSISTENT CSS-animated
// overlay div (not a per-draw-recreated SVG <rect>), so it glides smoothly regardless of the redraw cadence —
// the chat-tab approach; (2) the working-chip breathe is still a SMIL animation that resumes mid-cycle on the
// per-poll rebuild via a negative begin offset; (3) focusing the wrap on mousedown uses preventScroll so the
// first click on the % battery isn't eaten by a focus-scroll. (The lane-state ↔ chip sync lives in the kernel.)
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js"), "utf8");

test("the compacting battery sweep is a persistent CSS-animated overlay div, not a recreated SVG <rect>+SMIL", () => {
  // a persistent overlay layer + per-sid bar map, created once in the constructor
  assert.match(SRC, /this\._compactLayer = document\.createElement\('div'\)/);
  assert.match(SRC, /this\._compactBars = new Map\(\)/);
  // a CSS keyframe animation drives the scaleX compression on the compositor (set once, never restarted)
  assert.match(SRC, /@keyframes romp-tl-compact\{/);
  assert.match(SRC, /animation:romp-tl-compact 3\.2s linear infinite/);
  // draw() REPOSITIONS the persistent bar (create-or-update) + reaps stale ones — it never appends a SMIL sweep
  assert.match(SRC, /_positionCompactBar\(sid, x, y, w, h\)/);
  assert.match(SRC, /this\._positionCompactBar\(s\.id,/);
  assert.match(SRC, /this\._reapCompactBars\(compactSeen\)/);
  assert.doesNotMatch(SRC, /begin: cbeg, repeatCount: 'indefinite'/);   // the old recreated-each-draw SMIL sweep is gone
});

test("the working-chip breathe still resumes at its phase on rebuild (negative SMIL begin from the SVG doc time)", () => {
  assert.match(SRC, /_smilBegin\(dur\) \{[\s\S]*?getCurrentTime\(\)[\s\S]*?'-' \+ \(ct % dur\)\.toFixed\(3\) \+ 's'/);
  assert.match(SRC, /dur: '1\.5s', begin: this\._smilBegin\(1\.5\)/);          // working-chip breathe
  assert.doesNotMatch(SRC, /begin: '0s', repeatCount: 'indefinite'/);          // the snap-back form is gone
});

test("focusing the wrap on mousedown uses preventScroll (so the first % click isn't eaten)", () => {
  assert.match(SRC, /this\.wrap\.focus\(\{ preventScroll: true \}\)/);
});

test("clicking the battery sends /compact + flags the optimistic compacting cue", () => {
  assert.match(SRC, /this\._compactClicked\[s\.id\] = \(Date\.now \? Date\.now\(\) : 0\); this\._compactSession\(s\.name\)/);
  assert.match(SRC, /window\.__rompTimelineCompact === 'function'/);
});
