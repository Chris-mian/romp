// Feed cards show an inline sub-goal checklist: the top-level goal (= the card title) plus its DIRECT
// sub-goals (the top 2 levels) as ✓ done / ? question / ▢ open rows; deeper steps stay in the modal
// (the user 2026-06-16). No jsdom harness — like feed-dead.test.ts, pin the behaviour at the source level.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

test("ask cards render an inline checklist of the goal's DIRECT sub-goals", () => {
  assert.match(FEED, /a\._checklist/);                       // the card carries a checklist element
  assert.match(FEED, /el\("div", "fask-checklist"\)/);
  assert.match(FEED, /root\.children\.map/);                 // reads the ROOT goal's direct children (top 2 levels)
  assert.match(FEED, /n\.kind !== "handoff"/);               // handoff nodes render in their own section
  assert.match(FEED, /s\.status === "done" \? "✓"/);         // ✓ done / ⏸ question(blocked) / ○ open mark
  assert.match(FEED, /s\.status === "question" \? "⏸"/);     // blocked → the red ⏸ (was an amber ?), the user 2026-06-24
});

test("the sub-goal checklist is styled (done = blue ✓ disc, dimmed but NOT struck; question = red ⏸)", () => {
  assert.match(CSS, /\.fask-checklist \{/);
  // done mark = the chat view's blue ✓ disc (--check-bg + round), matching .todo-completed .todo-mark
  assert.match(CSS, /\.fcheck\.done \.fcheck-mark \{[^}]*var\(--check-bg\)/);
  assert.match(CSS, /\.fcheck\.done \.fcheck-mark \{[^}]*border-radius: 50%/);
  // the sub-goal text dims to recede but is NOT struck through (the user 2026-06-16)
  assert.match(CSS, /\.fcheck\.done \.fcheck-text \{[^}]*var\(--dim\)/);
  assert.doesNotMatch(CSS, /\.fcheck\.done \.fcheck-text \{[^}]*line-through/);
  // question(blocked) mark = the red ⏸ (var(--err)), not the old amber #d8a657 (the user 2026-06-24)
  assert.match(CSS, /\.fcheck\.question \.fcheck-mark \{[^}]*var\(--err\)/);
  assert.doesNotMatch(CSS, /\.fcheck\.question \.fcheck-mark \{[^}]*#d8a657/);
});
