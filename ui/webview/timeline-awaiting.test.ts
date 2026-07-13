// Timeline AWAITING badge (the user 2026-07-01, working-state audit): the chat chip folds "awaiting
// dispatched/background work" into its yellow working dot, but the timeline lane showed a bare READY —
// the last designed split between the surfaces' working models. The kernel now emits `awaitingBg` per
// live lane (the same _session_awaiting signal), and badgeFor renders it as an AWAITING badge in the
// working-yellow family — in flight elsewhere, not on you, never claiming the session itself is producing.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const TL = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js"), "utf8");

test("an awaitingBg lane renders an Awaiting badge in the working-yellow family", () => {
  assert.match(TL, /else if \(s\.awaitingBg\) m = \{ label: 'Awaiting', kind: 'working' \};/);
});

test("precedence: blocked-on-you beats awaiting, awaiting beats Ready", () => {
  const blocked = TL.indexOf("m = { label: 'Blocked', kind: 'attention' }");
  const awaiting = TL.indexOf("label: 'Awaiting'");
  const ready = TL.indexOf("m = { label: 'Ready', kind: 'ready' }");
  assert.ok(blocked > 0 && awaiting > 0 && ready > 0, "all three badge branches exist");
  assert.ok(blocked < awaiting, "a hard block (on you) outranks the awaiting cue");
  assert.ok(awaiting < ready, "awaiting is checked before the plain Ready fallback");
});

test("the legacy lane state 'awaiting' (blocked-on-you) still maps to Blocked, untouched", () => {
  assert.match(TL, /s\.state === 'permission' \|\| s\.state === 'awaiting'\) m = \{ label: 'Blocked', kind: 'attention' \}/);
});

test("an idle awaitingBg lane draws a thin dashed stretch with its own hover (the user 2026-07-13)", () => {
  // from the last work period's end to the live edge, lane-colored, thinner than a work bar
  assert.match(TL, /if \(s\.live && s\.awaitingBg\) \{/);
  assert.match(TL, /'stroke-dasharray': '5 4'/);
  // the hover lists the live task descriptions (kernel awaitingTasks), falling back to the why line
  assert.match(TL, /s\.awaitingTasks && s\.awaitingTasks\.length\) \? s\.awaitingTasks : \[s\.awaitingBg\]/);
  assert.match(TL, /ln\.setAttribute\('stroke-width', '2\.6'\); this\.showTip\(tip, e\);/);
  // the stretch keeps empty-row behaviors: drag to pan/reorder, click to select/open
  assert.match(TL, /wh\.addEventListener\('mousedown', \(e\) => this\._beginDrag\(s\.id, e\)\);/);
});
