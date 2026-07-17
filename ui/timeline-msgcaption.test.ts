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
  assert.match(SRC, /req\(t\)\s*\{\s*return t\.msgCaption \? esc\(t\.msgCaption\) : \(t\.prompt \? reqText\(t\.prompt\) : ''\);/);
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
  // both the DOT (req) and the BAR (barBody) run the raw prompt through the SAME shared builder, which
  // strips the markers (then collapses a repeat) before escaping
  assert.match(SRC, /const s = collapseRepeat\(stripRompLabel\(stripRompMarks\(prompt\)\)\);/);
  assert.match(SRC, /req\(t\)[^\n]*reqText\(t\.prompt\)/);
  assert.match(SRC, /barBody[\s\S]*?const reqp = t\.prompt \? reqText\(t\.prompt\) : '';/);
});

// The tip's request line is a GIST (the user 2026-07-17: a kernel-restart notice filled the tooltip and
// hard-cut mid-word — "…history intact. R"). Same idiom as the chat's nudge/romp-system gists: first
// non-empty line only; over 90 chars → truncate at a WORD boundary with an ellipsis.
test("reqText is a gist: first line, word-boundary truncation, ellipsis — never a mid-word 120-char cut", () => {
  const { reqText } = require(path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js"));
  // pin the gist shape at the source level too
  assert.match(SRC, /const first = \(s\.split\('\\n'\)\.find\(\(l\) => l\.trim\(\)\) \|\| s\)\.trim\(\);/);
  assert.match(SRC, /first\.length > 90 \? first\.slice\(0, 88\)\.replace\(\/\\s\+\\S\*\$\/, ''\) \+ '…' : first/);
  // the exact notice from the screenshot: long single line → clean word-boundary prefix + ellipsis
  const CLEAN = "The romp kernel restarted and cut this session's in-flight turn; the session has been resumed with its history intact. Re-read the tail of the conversation and pick the work back up where it stopped.";
  const out = reqText("<!-- romp-injected --><!-- romp-system -->[romp] " + CLEAN);
  assert.ok(out.endsWith("…"), "truncated with an ellipsis, not a hard cut");
  assert.ok(out.length <= 89, "gist-sized (was a 120-char dump)");
  const stem = out.slice(0, -1);
  assert.ok(CLEAN.startsWith(stem), "the gist is a clean prefix of the message");
  assert.match(stem, /\S$/, "no trailing space before the ellipsis");
  assert.equal(CLEAN.charAt(stem.length), " ", "the cut lands on a word boundary");
  // a multi-line prompt shows its FIRST line only — the rest is a click away in the chat
  assert.equal(reqText("first line summary\nsecond line detail\nthird"), "first line summary");
  // a short prompt rides through whole, no ellipsis
  assert.equal(reqText("make the borders subtler"), "make the borders subtler");
});

// An API-error storm auto-retries ("retry", romp-injected). Those sends can COALESCE into ONE delivered user
// message, so the segment's request read "retry retry retry retry …" — fourteen copies of romp's own
// bookkeeping token where the request text belongs (the user 2026-07-16).
test("a request that is only ONE token repeated collapses to that token + its count", () => {
  const { collapseRepeat, reqText } = require(path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js"));
  assert.equal(collapseRepeat("retry retry retry retry"), "retry ×4");
  assert.equal(collapseRepeat("retry"), "retry", "a SINGLE retry is a real request — untouched");
  assert.equal(collapseRepeat("Retry retry"), "Retry ×2", "case-insensitive match, first token's casing kept");
  // a genuine request keeps every word, even one with an incidental repeat
  assert.equal(collapseRepeat("fix the the parser"), "fix the the parser");
  assert.equal(collapseRepeat(""), "");

  // end-to-end through the shared builder: markers stripped, repeats collapsed, then escaped
  const RETRY = "retry\n\n<!-- romp-injected -->\n\n".repeat(14);
  assert.equal(reqText(RETRY), "retry ×14", "the exact storm from the screenshot");
  // a genuine prompt still rides through untouched (and still gets its markers stripped)
  assert.equal(reqText("<!-- romp-injected -->make the borders subtler"), "make the borders subtler");
});

// romp prefixes its own injected notices with a literal "[romp]" label. The dot now wears the romp logo + a
// 'romp' caption, so the label is redundant IN the tip (the user 2026-07-16) — the chat's romp-system card
// already strips it for the same reason ("the chip already says who it's from").
test("the tip drops romp's own '[romp]' label — the dot's logo already says who it's from", () => {
  const { reqText } = require(path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js"));
  // the exact notice from the screenshot: markers + label both go, the sentence survives (esc() escapes
  // only & < > — an apostrophe rides through as itself)
  assert.equal(
    reqText("<!-- romp-injected --><!-- romp-system -->[romp] The romp kernel restarted and cut this session's in-flight turn"),
    "The romp kernel restarted and cut this session's in-flight turn");
  // only a LEADING label is a label; the word elsewhere is content and stays
  assert.equal(reqText("ask [romp] about it"), "ask [romp] about it");
  assert.equal(reqText("a plain human prompt"), "a plain human prompt");
});
