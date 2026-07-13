// GROUPED mode (the user 2026-07-13): a footer "Group" toggle organizes each column BY SESSION — session
// order = the kernel's session-order list (the same order the chat tabs + timeline lanes hold), a
// name+working-dot header on the column backdrop opens each session's run, and the cards below drop their
// own name row (the header carries the identity). Clear re-homes beside the timestamp (float-right: on the
// time line when it fits, else its own right-justified line — the compactness ladder). Source pins.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");
const FED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "federation.ts"), "utf8");

test("the footer Group toggle persists `grouped` in romp:settings like Newest first / Collapsed", () => {
  assert.match(FEED, /grouped: s\.grouped === true/);
  assert.match(FEED, /ensureFeedToggle\("feed-grouped", "Group", \(\) => feedPrefs\(\)\.grouped, "grouped",/);
  assert.match(FEED, /ensureGroupToggle\(\)\.style\.display = showCA \? "" : "none";/);
});

test("session rank = the kernel's session-order list (tab/lane order); unknown sids keep time order after it", () => {
  // the order rides every feed push; the kernel emits session-order.json, federation concatenates per host
  assert.match(FEED, /if \(Array\.isArray\(m\.order\)\) sessionOrder = m\.order\.filter/);
  assert.match(FEED, /const rank = new Map\(sessionOrder\.map\(\(s, i\) => \[s, i\] as const\)\);/);
  assert.match(FEED, /return rank\.has\(s\) \? rank\.get\(s\)! : 1e9 \+ \(extra\.get\(s\) \|\| 0\);/);
  // stable sort: per-session cards keep the column's newest/oldest order
  assert.match(FEED, /buckets\[k\]\.sort\(\(x, y\) => rk\(x\) - rk\(y\)\);/);
  assert.match(FED, /if \(Array\.isArray\(f\.order\)\) merged\.order\.push\(\.\.\.f\.order\);/);
});

test("a name+dot header entry opens each session's run; only runs that exist get one", () => {
  assert.match(FEED, /\{ kind: "sess"; t: number; sid: string; name: string; color: \{ bg: string; fg: string \} \| null; live: boolean \}/);
  assert.match(FEED, /if \(s !== cur\) \{/);
  assert.match(FEED, /withHeads\.push\(\{ kind: "sess", t: e\.t, sid: s, name: src\.name, color: src\.color \|\| null, live: !!src\.live \}\);/);
  // reconcile keys headers per (column, sid) — one session can head a run in EVERY column
  assert.match(FEED, /key = "s:" \+ listEl\.id \+ ":" \+ e\.sid;/);
  // the header carries the identity: colored name, host prefix treatment, the yellow working dot
  assert.match(FEED, /nm\.replaceChildren\(\.\.\.hostNameNodes\(e\.name, e\.sid\)\);/);
  assert.match(FEED, /setWorkDot\(nm, workingSet\.has\(e\.name\)\);/);
  // headers aren't cards: the column count chips exclude them
  assert.match(FEED, /const nCards = \(es: Entry\[\]\) => es\.filter\(\(e\) => e\.kind !== "sess"\)\.length;/);
  assert.match(CSS, /\.feed-sess-head \{ display: flex; align-items: center;/);
});

test("grouped cards drop their own name row; Clear re-homes beside the timestamp (guarded move)", () => {
  // the name row hides (the header carries it); Clear moves ONLY on a mode change (click-safety) — a
  // steady-state re-render never detaches the button mid-press
  assert.match(FEED, /\(\(a\._name as HTMLElement\)\.parentElement as HTMLElement\)\.style\.display = gmode \? "none" : "";/);
  assert.match(FEED, /if \(\(a\._clr as HTMLElement\)\.parentElement !== clrHome\) clrHome\.append\(a\._clr\);/);
  // row2 hides once nothing on it shows (ask card: badges may remain; group card: always name+Clear)
  assert.match(FEED, /r2\.style\.display = gmode && !r2live \? "none" : "";/);
  // float-right = right-justified beside the time when it fits, else its own right-aligned line
  assert.match(CSS, /\.fask-row1 \.fdismiss \{ float: right; margin-left: 8px; \}/);
});
