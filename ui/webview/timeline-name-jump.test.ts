// Clicking a lane's NAME on the timeline jumps you INTO that session in the chat (focus and all),
// while the name stays a drag handle for reordering (the user 2026-07-03). The empty row only PREVIEWS
// (openChat preserveFocus=true); the name opens with focus (preserveFocus=false). A real drag suppresses
// the jump via _suppressClick, and mousedown starts the same _beginDrag gesture as the rest of the row.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const TL = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js"), "utf8");

test("the name has its own hit rect that starts a drag on mousedown", () => {
  assert.match(TL, /const nhit = el\('rect'.*'pointer-events': 'all'/);
  assert.match(TL, /nhit\.addEventListener\('mousedown', \(e\) => this\._beginDrag\(s\.id, e\)\)/);
});

test("a plain name click jumps into the chat WITH focus (preserveFocus=false), guarded by _suppressClick", () => {
  const m = TL.match(/nhit\.addEventListener\('click', \(\) => \{[\s\S]*?\}\);/);
  assert.ok(m, "the name click handler exists");
  const body = m![0];
  assert.match(body, /if \(this\._suppressClick\)/);                         // a drag doesn't also jump
  assert.match(body, /this\.openChat\(this\._laneTid\(s\), null, false\)/);   // focus=true (preserveFocus false)
});

test("the empty-row (rowHit) click still only PREVIEWS — preserveFocus=true, no focus steal", () => {
  assert.match(TL, /rowHit\.addEventListener\('click'[\s\S]*?this\.openChat\(this\._laneTid\(s\), null, true\)/);
});
