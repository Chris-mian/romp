// The judging band draws each mark as a RUN SPAN [t, t1] = [sent, recv] (the user 2026-06-19, g70): the
// kernel emits one mark per judge call at its real wall-clock interval, and the band's rect spans that
// interval instead of being a point back-placed onto the work. No DOM harness for the SVG band, so pin the
// span block-building at the source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "obsidian", "romp-timeline-view.js"), "utf8");

test("each band mark is a span [t, t1] (recv), merged on its end, not a point", () => {
  assert.match(SRC, /const es = e\.t, ee = \(e\.t1 != null \? e\.t1 : e\.t\);/, "the span end is the run's recv (t1)");
  assert.match(SRC, /last\.end = Math\.max\(last\.end, ee\)/, "merge extends to the latest span end");
  assert.match(SRC, /blocks\.push\(\{ sid: e\.sid, start: es, end: ee/, "a new block spans [sent, recv]");
});
