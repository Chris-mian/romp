// romp-authored marking on the timeline (the user 2026-06-23): the ⚡ lightning bolt that flagged an
// auto-nudge on the JUDGE band is removed entirely. (The main-timeline dot's romp-message marker — the
// favicon-on-black-dot replacing its ⚡ — and the auto-vs-Nudge-button distinction it needs land in a
// follow-up once that signal exists.) Source-pin over the served timeline view.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js"), "utf8");

test("judges are split into index/triage sets, gated by the two settings toggles with debug migration (the user 2026-06-29)", () => {
  // the captioner + archiver are the 'index' set; the rest are 'triage'
  assert.match(SRC, /\{ key: 'captioner', color: '#1EA1EB', group: 'index' \}/);
  assert.match(SRC, /\{ key: 'archiver', color: '#54B204', group: 'index' \}/);
  assert.match(SRC, /\{ key: 'planner', color: '#E0B020', group: 'triage' \}/);
  assert.match(SRC, /\{ key: 'courier', color: '#9088F0', group: 'triage' \}/);
  // judgesShown() reads the two toggles, falling back to the legacy `debug` flag when a toggle is unset
  assert.match(SRC, /function judgesShown\(\)/);
  assert.match(SRC, /s\.showIndexJudges !== undefined \? !!s\.showIndexJudges : !!s\.debug/);
  assert.match(SRC, /s\.showTriageJudges !== undefined \? !!s\.showTriageJudges : !!s\.debug/);
  assert.match(SRC, /JUDGES\.filter\(\(j\) => \(j\.group === 'index' \? idx : tri\)\)/);
});

test("the judge band no longer draws auto-nudge ⚡ marks, and its visibility doesn't depend on nudges", () => {
  // the ⚡ band loop over data.nudges is gone
  assert.doesNotMatch(SRC, /for \(const n of \(data\.nudges \|\| \[\]\)\.filter/, "the auto-nudge ⚡ band loop is removed");
  assert.doesNotMatch(SRC, /g\.textContent = '⚡'/, "no ⚡ text glyph on the judge band");
  // the band shows for ENABLED-judge run-spans ONLY now (no || data.nudges.some); the two judge-set toggles gate it
  assert.match(SRC, /const jShow = !!\(shownJudges\.length && data\.judging && data\.judging\.some\(\(e\) => shownKeys\.has\(e\.judge\) && inWin\(e\.t\)\)\)/);
  assert.doesNotMatch(SRC, /jShow[\s\S]{0,160}data\.nudges && data\.nudges\.some/, "band visibility no longer keys on nudges");
});

test("an auto-nudge dot's hover: 'romp · nudge' in WHITE + a stock 'romp nudged <name>' line (no captioned text) (the user 2026-06-23)", () => {
  // the 'romp · nudge' identity reads in plain white, not the session colour
  assert.match(SRC, /<span class="who" style="color:#fff">romp · nudge<\/span>/);
  // the body is a STOCK line — we know the auto-nudge text, so don't captionize it: "romp nudged <session>"
  assert.match(SRC, /this\.body\('romp nudged ' \+ esc\(s\.name\)\)/);
  // …and it no longer pipes the captioned/raw nudge text (this.req) into the auto-nudge tooltip
  assert.doesNotMatch(SRC, /romp · nudge<\/span>[\s\S]{0,120}this\.body\(this\.req\(t\)\)/);
});
