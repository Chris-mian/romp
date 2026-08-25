// The FEED shows every session's cards, whatever tag view the tabs/timeline hold (the user's
// 2026-08-25 ruling, superseding the 2026-08-24 feed-follows-the-view coupling after living with
// it): the board is the attention/clearing surface — a session hidden from the tabs still lands and
// clears here. The shared views blob still governs the CHAT TABS + TIMELINE (session-views.ts and
// its kernel mirror untouched); the feed's only narrowing is its own local scoping — the session
// combobox's exact filter and the search. The 648/665 gating pins retired WITH this ruling: the
// view gate, the needs-you breakthrough cue, the N-outside line, and the promoted banner were all
// coupling artifacts. Source pins (the repo convention).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const ROOT = path.resolve(process.cwd(), "..");
const FEED = fs.readFileSync(path.join(ROOT, "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.join(ROOT, "ui", "webview", "feed.css"), "utf8");
const KERNEL = fs.readFileSync(path.join(ROOT, "kernel", "kernel.py"), "utf8");

test("the feed reads NO view state for card gating — all sessions' cards render under ANY active view", () => {
  // structural proof: with no views input anywhere in the feed bundle, no tag-home shape (local,
  // remote, union — the fixtures the tab-side deciders still execute against in session-views.test)
  // can narrow the board; only the combobox exact filter and the search do.
  assert.doesNotMatch(FEED, /session-views|feed-view"|viewVisible|cardInView|outsideView|feedViews/,
    "no import, no decider, no adopted blob");
  assert.match(FEED, /let shown = feedOnlySid \? list\.filter\(\(a\) => a\.sid === feedOnlySid\) : list\.filter\(\(a\) => !a\.satellite\);/,
    "viewFiltered's whole composition: the board's own local scoping only");
  assert.match(FEED, /the user's\s*\n\s*\/\/ 2026-08-25 ruling, superseding the 2026-08-24 feed-follows-the-view coupling/,
    "the ruling is cited where the gate used to live");
});

test("the coupling's artifacts are fully retired: cue, N-outside line, promoted banner", () => {
  assert.doesNotMatch(FEED, /fask-viewbreak|viewbreak|feed-viewmore|outsideViewCount|viewLabel/);
  assert.doesNotMatch(CSS, /fask-viewbreak|feed-viewmore/);
});

test("the kernel's views blob serves the tabs/timeline; the feed payload carries it again for the tag mounts", () => {
  assert.ok(KERNEL.includes('"views": _views_client()}'), "tabOrder pushes keep the blob (tabs + timeline consume it)");
  const fp = KERNEL.slice(KERNEL.indexOf('return {"type": "feed", "asks": asks'), KERNEL.indexOf('"clearNotices"'));
  // retired 2026-08-25 morning as unread; REVIVED the same day for the per-surface tag lenses —
  // the outline pane and the feed's own tag filter read the rendered blob off this payload
  assert.ok(fp.includes('"views": _views_client()'), "the tag mounts' read");
});
