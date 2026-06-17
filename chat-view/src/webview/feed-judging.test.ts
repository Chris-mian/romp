// The "needs judging" pill (the user 2026-06-17): a per-session BLUE outlined pill sitting just right of
// each card's "Xm ago" age, lit while the TRIAGE judges (planner/closer) still have an ended turn from
// that session to file into the goal tree. The kernel pushes a `judging` name-set parallel to `working`;
// the card mirrors `setWorkDot` with `setJudgingPill`. No jsdom harness for the feed, so — like the other
// feed-*.test.ts — pin it at the source level.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "feed.ts"), "utf8");

test("a judgingSet is parsed from the feed message's `judging` field, parallel to working", () => {
  assert.match(FEED, /let judgingSet = new Set<string>\(\);/);
  assert.match(FEED, /judgingSet = new Set\(Array\.isArray\(m\.judging\) \? m\.judging : \[\]\);/);
});

test("setJudgingPill inserts a blue outlined `.fjudging` pill immediately AFTER the time element", () => {
  assert.match(FEED, /function setJudgingPill\(timeEl: HTMLElement \| null, on: boolean\)/);
  // labelled "judging", inserted right after the age (insertBefore time's nextSibling)
  assert.match(FEED, /pill\.textContent = "judging";/);
  assert.match(FEED, /timeEl\.parentElement\?\.insertBefore\(pill, timeEl\.nextSibling\)/);
  // blue outline === blue text, transparent fill (no background), pill (oval) radius — inline-styled
  // because `ui` owns styles.css (same pattern as blockReason/doneReason)
  assert.match(FEED, /border:1px solid #5aa2ff;border-radius:999px;/);
  assert.match(FEED, /color:#5aa2ff;/);
  // idempotent on re-render: only add when absent, only remove when present
  assert.match(FEED, /const has = !!next && next\.classList\.contains\("fjudging"\);/);
});

test("every card type that shows an age toggles the pill from judgingSet by session name", () => {
  // standalone deliverable, ask card, and group card all carry the marker (it.name / g.name)
  const calls = FEED.match(/setJudgingPill\(a\._time, judgingSet\.has\((?:it|g)\.name\)\)/g) || [];
  assert.ok(calls.length >= 3, `expected the pill on all 3 card updaters, saw ${calls.length}`);
});
