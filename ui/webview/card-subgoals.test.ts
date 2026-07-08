// Feed cards show an inline sub-goal tree: the top-level goal (= the card title) plus, when "Sub-goals" is
// on, its ENTIRE subtree (the user 2026-07-08 — was only the direct children) as ✓ done / ⏸ blocked / ○ open
// rows indented by depth, with the SAME inclusion rules as the modal/outline tree (renderTreeNode): skip
// handoffs, dedup repeats. No jsdom harness — like feed-dead.test.ts, pin the behaviour at the source level.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

test("ask cards render the goal's WHOLE sub-goal tree (gated on the Sub-goals toggle), not just level 1", () => {
  assert.match(FEED, /a\._checklist/);                       // the card carries a checklist element
  assert.match(FEED, /el\("div", "fask-checklist"\)/);
  assert.match(FEED, /if \(root && feedPrefs\(\)\.subgoals\) \{/);   // the toggle gates the inline tree on cards
  // a RECURSIVE walk from the root's children, descending every level (was root.children only)
  assert.match(FEED, /const walk = \(id: string, depth: number\) =>/);
  assert.match(FEED, /for \(const c of root\.children \|\| \[\]\) walk\(c, 0\)/);
  assert.match(FEED, /for \(const c of n\.children \|\| \[\]\) walk\(c, depth \+ 1\)/);
  assert.doesNotMatch(FEED, /root\.children\.map/, "no longer capped at the direct children");
  assert.match(FEED, /s\.status === "done" \? "✓"/);         // ✓ done / ⏸ question(blocked) / ○ open mark
  assert.match(FEED, /s\.status === "question" \? "⏸"/);     // blocked → the red ⏸ (was an amber ?), the user 2026-06-24
});

test("the inline tree follows the SAME rules as the modal outline: skip handoffs, dedup repeats, indent by depth", () => {
  assert.match(FEED, /n\.kind === "handoff"/);               // delegation nodes render in their own section
  assert.match(FEED, /const repeat = seen\.has\(n\.id\)/);   // a node reached under two parents...
  assert.match(FEED, /if \(repeat\) return;/);               // ...renders once and is NOT re-descended
  assert.match(FEED, /row\.style\.paddingLeft = \(depth \* TREE_INDENT_EM\) \+ "em"/);  // same per-level indent as the modal
  assert.match(FEED, /wireNodeZones\(it, s, mark, txt, null, !repeat\)/);   // a dim repeat is display-only
  assert.match(CSS, /\.fcheck\.repeat \{[^}]*opacity: 0\.5/);   // dim, mirroring .ftree-node.repeat
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
  // ...AND a RED RING around it (the user 2026-06-25): the same 13px hollow circle as the done ✓ disc and
  // the modal's .st-question ⏸-ring, so the card's blocked mark isn't a bare glyph missing its ring.
  assert.match(CSS, /\.fcheck\.question \.fcheck-mark \{[^}]*border: 1\.5px solid var\(--err\)/);
  assert.match(CSS, /\.fcheck\.question \.fcheck-mark \{[^}]*border-radius: 50%/);
});
