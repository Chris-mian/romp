// Drag-to-Working (the user 2026-07-06): a Blocked/Completed card drags onto the Working column — the
// desktop gesture over the same cardMove op as the modal's "Move to Working" button (which remains the
// touch path). The dragged card dims+dashes, the Working column opens a LANDING SLOT at its bottom (the
// true landing spot — the column auto-sorts by recency and the followupAt stamp lands the moved card
// last), and render() DEFERS while a drag is in flight (a mid-drag reconcile moves/removes the source
// node and the browser cancels the drag) — the timeline _pointerHeld pattern. No jsdom for the feed
// renderer, so pin at the source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

test("card dragging is TEMPORARILY DISABLED — no card is ever armed draggable (the user 2026-07-06)", () => {
  // a single flag turns the gesture off for now; the handlers stay wired but dormant. Flip it back on to
  // restore drag-to-Working (the modal's "Move to Working" button remains the way to move a card meanwhile).
  assert.match(FEED, /const DRAG_CARDS_ENABLED = false;/);
  assert.match(FEED, /const movable = DRAG_CARDS_ENABLED && !it\.provisional && \(it\.column === "needs_input" \|\| it\.column === "completed"\);/);
  assert.match(FEED, /card\.draggable = movable;/);
  assert.match(FEED, /card\.classList\.toggle\("draggable", movable\);/);
  // the machinery stays wired (dormant) on the reused card element (makeAskCard), for the re-enable
  assert.match(FEED, /card\.addEventListener\("dragstart", \(ev\) => \{/);
  assert.match(FEED, /card\.addEventListener\("dragend", finishAskDrag\);/);
});

test("render() defers while a drag is in flight and flushes on dragend/drop", () => {
  assert.match(FEED, /if \(dragAskId\) \{ dragDeferredRender = true; return; \}/);
  assert.match(FEED, /if \(dragDeferredRender\) \{ dragDeferredRender = false; render\(\); \}/);
});

test("the Working column is the drop target, wired once on the stable col element in ensureCols", () => {
  assert.match(FEED, /if \(key === "asks"\) \{/);
  assert.match(FEED, /col\.addEventListener\("dragover", \(ev\) => \{/);
  assert.match(FEED, /col\.addEventListener\("drop", \(ev\) => \{/);
  // drop posts the SAME op as the modal button, with the same plain optimistic flip
  assert.match(FEED, /type: "cardMove", itemId: id, sid: dropped\.sid, to: "working"/);
  assert.match(FEED, /optimisticFollowMove\(id, true\);\s*\/\/ same plain optimistic flip as the modal button/);
});

test("the landing slot opens at the BOTTOM of Working — the honest auto-sort landing spot", () => {
  assert.match(FEED, /function openDropSlot\(\)/);
  assert.match(FEED, /body\.appendChild\(slot\);/, "appended last: the column sorts newest-last, where followupAt lands the card");
  assert.match(FEED, /slot!\.classList\.add\("open"\); slot!\.scrollIntoView\(\{ block: "nearest" \}\);/);
  // dragover opens it, dragleave/finish close it
  assert.match(FEED, /openDropSlot\(\);\s*\/\/ the column makes room at the landing spot/);
  assert.match(FEED, /closeDropSlot\(\);/);
  // the slot animates open (the "cards make way" motion) in accent chrome, never a status color
  assert.match(CSS, /\.fdrop-slot \{[^}]*transition: height/);
  assert.match(CSS, /\.fdrop-slot\.open \{[^}]*height: 46px/);
  assert.match(CSS, /\.fdrop-slot \{[^}]*var\(--accent\)/);
});

test("the in-flight card visibly reads as dragging; the class is applied after the drag-image snapshot", () => {
  assert.match(FEED, /requestAnimationFrame\(\(\) => card\.classList\.add\("dragging"\)\);/);
  assert.match(FEED, /document\.querySelector\("\.fitem\.ask\.dragging"\)\?\.classList\.remove\("dragging"\);/);
  assert.match(CSS, /\.fitem\.ask\.dragging \{[^}]*opacity: 0\.35/);
  assert.match(CSS, /\.fitem\.ask\.draggable \{ cursor: grab; \}/);
  // while dragging, the whole Working column invites the drop (accent, hot on hover-over)
  assert.match(CSS, /body\.feed-dragging \.feed-col\.col-asks \{[^}]*var\(--accent\)/);
  assert.match(CSS, /\.feed-col\.col-asks\.drop-hot \{[^}]*var\(--accent\)/);
});
