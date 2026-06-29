// Timeline compacting + compact-click fixes (the user 2026-06-29). No DOM harness for the SVG draw path, so
// pin the wiring at the source: (1) repeating SMIL animations resume mid-cycle on the per-poll rebuild via a
// negative begin offset (no jumping); (2) focusing the wrap on mousedown uses preventScroll so the first click
// on the % battery isn't eaten by a focus-scroll. (The lane-state ↔ chip compacting sync lives in the kernel.)
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js"), "utf8");

test("a repeating SMIL animation resumes at its phase on rebuild (negative begin from the SVG doc time)", () => {
  assert.match(SRC, /_smilBegin\(dur\) \{[\s\S]*?getCurrentTime\(\)[\s\S]*?'-' \+ \(ct % dur\)\.toFixed\(3\) \+ 's'/);
  // both the compacting battery sweep and the working-chip breathe use it instead of begin:'0s'
  assert.match(SRC, /begin: cbeg, repeatCount: 'indefinite'/);                 // compacting width+opacity
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
