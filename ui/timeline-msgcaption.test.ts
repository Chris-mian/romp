// Split captions on the timeline (the user 2026-06-19): the prompt DOT shows the MESSAGE caption
// (a gist of the ask, ready early) falling back to the raw prompt until it lands; the work BAR keeps
// the WORK caption (t.summary). The kernel emits both — `msgCaption` (dot) + `summary` (bar) — per
// segment. No DOM harness for the SVG draw, so pin the hover-body source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js"), "utf8");

test("the prompt DOT hover (req) reads the MESSAGE caption, falling back to the raw prompt", () => {
  assert.match(SRC, /req\(t\)\s*\{\s*return t\.msgCaption \? esc\(t\.msgCaption\) : \(t\.prompt \? esc\(t\.prompt\.slice\(0, 120\)\) : ''\);/);
  // it must NOT read the WORK caption (t.summary) for the dot anymore — that's the bar's
  assert.doesNotMatch(SRC, /req\(t\)\s*\{\s*return t\.summary \?/);
});

test("the work BAR hover still reads the WORK caption (t.summary), kept separate from the dot", () => {
  assert.match(SRC, /barBody\(t, ongoing\)\s*\{[\s\S]*?t\.summary/);
});
