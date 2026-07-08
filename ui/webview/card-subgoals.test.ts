// Feed cards show an inline sub-goal tree (applySubgoals): the top-level goal (= the card title) plus, when
// the per-card "Sub-goals" button is on, its ENTIRE subtree — as ✓ done / ⏸ blocked / ○ open rows indented by
// depth, WITH the outline's disclosure triangles (▶/▼) to fold branches (the user 2026-07-08). Same inclusion
// rules as the modal/outline tree (renderTreeNode): skip handoffs, dedup repeats. No jsdom — source-level pin.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

test("ask cards render the goal's WHOLE sub-goal tree (gated on the per-card Sub-goals button), not just level 1", () => {
  assert.match(FEED, /a\._checklist/);                       // the card carries a checklist element
  assert.match(FEED, /el\("div", "fask-checklist"\)/);
  assert.match(FEED, /function applySubgoals\(a: any, it: AskItem\): void/);
  assert.match(FEED, /const on = hasSubs && resolveSub\(id\);/);   // the per-card toggle (default follows Collapsed)
  assert.match(FEED, /if \(on && root\) \{/, "the tree walks only when the toggle is on");
  // a RECURSIVE walk from the root's children, descending every level (was root.children only)
  assert.match(FEED, /const walk = \(nid: string, depth: number\) =>/);
  assert.match(FEED, /for \(const c of root\.children \|\| \[\]\) walk\(c, 0\)/);
  assert.match(FEED, /for \(const c of n\.children \|\| \[\]\) walk\(c, depth \+ 1\)/);
  assert.doesNotMatch(FEED, /root\.children\.map/, "no longer capped at the direct children");
  assert.match(FEED, /s\.status === "done" \? "✓"/);         // ✓ done / ⏸ question(blocked) / ○ open mark
  assert.match(FEED, /s\.status === "question" \? "⏸"/);     // blocked → the red ⏸ (was an amber ?), the user 2026-06-24
});

test("the inline tree follows the SAME rules as the modal outline: handoffs, repeats, depth indent, collapse triangles", () => {
  assert.match(FEED, /n\.kind === "handoff"/);               // delegation nodes render in their own section
  assert.match(FEED, /const repeat = seen\.has\(n\.id\)/);   // a node reached under two parents...
  assert.match(FEED, /if \(repeat \|\| collapsed\) return;/); // ...renders once; a collapsed branch is not descended
  assert.match(FEED, /row\.style\.paddingLeft = \(depth \* TREE_INDENT_EM\) \+ "em"/);  // same per-level indent as the modal
  assert.match(FEED, /wireNodeZones\(it, s, mark, txt, null, !repeat\)/);   // a dim repeat is display-only
  assert.match(CSS, /\.fcheck\.repeat \{[^}]*opacity: 0\.5/);   // dim, mirroring .ftree-node.repeat
});

test("each expandable node carries the outline's disclosure triangle (▶/▼), toggling the card's own collapse state", () => {
  assert.match(FEED, /const cardTreeCollapsed = new Set<string>\(\);/);   // card-own, default-expanded collapse state
  assert.match(FEED, /el\("span", "fcheck-tri" \+ \(expandable \? " nav" : " empty"\)\)/);
  assert.match(FEED, /tri\.textContent = expandable \? \(collapsed \? "▶" : "▼"\) : "";/);
  assert.match(FEED, /if \(cardTreeCollapsed\.has\(k\)\) cardTreeCollapsed\.delete\(k\); else cardTreeCollapsed\.add\(k\);/);
  assert.match(FEED, /row\.append\(tri, mark, txt\)/);        // triangle leads the row, then mark + text
  // styled like the modal's .ftree-tri
  assert.match(CSS, /\.fcheck-tri \{[^}]*width: 1em/);
  assert.match(CSS, /\.fcheck-tri\.nav \{ cursor: pointer; \}/);
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

test("the Sub-goals button leads with the WHOLE-tree count — every node, every depth (the user 2026-07-08)", () => {
  assert.match(FEED, /let subCount = 0;/);
  assert.match(FEED, /const stack = \[\.\.\.\(root\.children \|\| \[\]\)\];/);   // full descent, not level 1
  assert.match(FEED, /stack\.push\(\.\.\.\(n\.children \|\| \[\]\)\);/);
  assert.match(FEED, /const hasSubs = subCount > 0;/);
  assert.match(FEED, /subBtn\.textContent = subCount === 1 \? "1 sub-goal" : subCount \+ " sub-goals";/);
});
