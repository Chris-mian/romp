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
  assert.match(SRC, /req\(t\)\s*\{\s*return t\.msgCaption \? esc\(t\.msgCaption\) : \(t\.prompt \? esc\(stripRompMarks\(t\.prompt\)\.slice\(0, 120\)\) : ''\);/);
  // it must NOT read the WORK caption (t.summary) for the dot anymore — that's the bar's
  assert.doesNotMatch(SRC, /req\(t\)\s*\{\s*return t\.summary \?/);
});

test("the work BAR hover still reads the WORK caption (t.summary), kept separate from the dot", () => {
  assert.match(SRC, /barBody\(t, ongoing\)\s*\{[\s\S]*?t\.summary/);
});

test("both hover bodies strip romp's HTML-comment markers from the raw prompt (the user 2026-07-15)", () => {
  // an injected romp-system notice (bg-task death) carries <!-- romp-injected --><!-- romp-system --> — the
  // chat hides these in markdown, but the ESCAPED timeline tips leaked them as literal text. Strip before show.
  const { stripRompMarks } = require(path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js"));
  assert.equal(
    stripRompMarks("<!-- romp-injected --><!-- romp-system -->[romp] 1 background task this session had running died"),
    "[romp] 1 background task this session had running died");
  assert.equal(stripRompMarks("<!-- romp-goal-id: 11111111-2222:g3 -->follow-up text"), "follow-up text");
  assert.equal(stripRompMarks("a plain user prompt"), "a plain user prompt");   // untouched
  // both the DOT (req) and the BAR (barBody) run the raw prompt through the stripper before escaping
  assert.match(SRC, /req\(t\)[^\n]*esc\(stripRompMarks\(t\.prompt\)\.slice/);
  assert.match(SRC, /barBody[\s\S]*?const reqp = t\.prompt \? esc\(stripRompMarks\(t\.prompt\)\.slice\(0, 120\)\)/);
});
