// The ledger overview tree (the summary below the tab title) as a checklist (the user 2026-06-16):
//  - the "(Xm ago)" times sit close to the content (the tree hugs its widest row) instead of way out at
//    the box's right edge, while staying right-aligned with each other;
//  - a DONE item uses the blue ✓ disc (same as the chat to-do / feed), a not-yet-done item a hollow ○;
//  - a done item's text is tinted to the SAME recency colour as its time.
// The chat renderer has no jsdom harness, so — like render-rail.test.ts — pin it at the source level.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "styles.css"), "utf8");

test("ledger marks: ▸ working, blue ✓ disc done, hollow ○ not-yet-done, ⏸ blocked", () => {
  assert.match(RENDER, /n\.current \? "▸" : n\.done \? "✓" : n\.blocked \? "⏸" : "○"/);
  // the done ✓ is the chat-style blue disc (white ✓ on --check-bg, round)
  assert.match(CSS, /\.ledger-tnode\.done \.ledger-tmark \{[^}]*var\(--check-bg\)/);
  assert.match(CSS, /\.ledger-tnode\.done \.ledger-tmark \{[^}]*border-radius: 50%/);
});

test("ledger: a done item's text takes its time's recency colour (ticks with the clock)", () => {
  // set on first render and again in refreshLedgerAges as the wall clock advances
  const hits = RENDER.match(/if \(n\.done && n\.t\) txt\.style\.color = ageColorReadable\(now - n\.t\)/g) || [];
  assert.equal(hits.length, 1, "render-loop tint");
  assert.match(RENDER, /if \(n && txt && n\.done && n\.t\) txt\.style\.color = ageColorReadable\(now - n\.t\)/);
});

test("ledger times hug the content (tree is fit-content) yet stay right-aligned", () => {
  assert.match(CSS, /\.ledger-tree \{[^}]*width: fit-content/);
});

test("the blue ✓ disc is standardized: ledger + feed card check carry the chat to-do's 9px/700 ✓", () => {
  const FEED_CSS = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "feed.css"), "utf8");
  assert.match(CSS, /\.ledger-tnode\.done \.ledger-tmark \{[^}]*font-size: 9px; font-weight: 700/);
  assert.match(FEED_CSS, /\.fcheck\.done \.fcheck-mark \{[^}]*font-size: 9px; font-weight: 700/);
});

test("the most-recently-changed ledger node gets a → marker on its left (kernel flags it `recent`)", () => {
  assert.match(RENDER, /n\.recent \? " recent" : ""/);                 // row carries the .recent class
  assert.match(RENDER, /el\("span", "ledger-recent"\)/);               // a → arrow element
  assert.match(RENDER, /arr\.textContent = "→"/);
  assert.match(RENDER, /recent\?: boolean/);                           // LedgerTreeNode carries the flag
  assert.match(CSS, /\.ledger-recent \{/);
});

test("the ledger tree is a COLLAPSIBLE checklist — toggle arrows at every level, done folds by default", () => {
  // recursive render over the kernel's children ids, with a per-node fold state
  assert.match(RENDER, /const ledgerFolded = new Set<string>\(\)/);
  assert.match(RENDER, /const ledgerExpanded = new Set<string>\(\)/);
  assert.match(RENDER, /const renderNode = \(n: LedgerTreeNode, depth: number\)/);
  // a "previous" (done) task folds by default unless it's the recent path; the user can override
  assert.match(RENDER, /const defaultFold = \(n: LedgerTreeNode\) => !!n\.done && !n\.onpath/);
  // a disclosure triangle (▶/▼) at every level; clicking toggles fold state + re-renders
  assert.match(RENDER, /el\("span", "ledger-tri"/);
  assert.match(RENDER, /folded \? "▶" : "▼"/);
  assert.match(RENDER, /ledgerFolded\.add\(n\.id\)/);
  assert.match(RENDER, /ledgerExpanded\.add\(n\.id\)/);
  assert.match(CSS, /\.ledger-tri \{/);
});

test("a cleared node renders as a FADED ✓; completed top goals get ~1.5-line spacing", () => {
  // cleared reuses the dimmed-disc treatment (the .derived rule); the kernel flags `cleared`
  assert.match(RENDER, /\(n\.derived \|\| n\.cleared\) \? " derived" : ""/);
  assert.match(RENDER, /cleared\?: boolean/);
  // spacing above each completed top goal (a .ledger-top.done margin), not a full double-space
  assert.match(RENDER, /depth === 0 \? " ledger-top" : ""/);
  assert.match(CSS, /\.ledger-tnode\.ledger-top\.done \{[^}]*margin-top/);
});

test("leaf-row tri spacers don't inherit the placeholder's 40px padding (no giant ledger gaps)", () => {
  // REGRESSION (the user 2026-06-16): a leaf row's disclosure-triangle slot is a zero-content
  // `el("span", "ledger-tri" + " empty")` spacer. The transcript "No session open" placeholder was
  // styled by a BARE `.empty { padding: 40px }` rule, so its selector also matched the `empty` token on
  // every leaf spacer → an 80×80px box → rows ~86px tall → the dropdown ledger showed giant gaps.
  // The fix scopes the placeholder to its own `.empty-state` class so the generic token no longer
  // collides. Guard both halves so neither can drift back.
  assert.match(RENDER, /el\("span", "ledger-tri" \+ \(expandable \? " nav" : " empty"\)\)/); // the spacer still uses the `empty` token
  // the padded placeholder rule must NOT be a bare `.empty` selector (which would re-match the spacer)
  assert.doesNotMatch(CSS, /(^|[\s,}])\.empty\s*[,{]/m);
  // the placeholder padding now lives on the scoped `.empty-state` class instead
  assert.match(CSS, /\.empty-state \{[^}]*padding:\s*40px/);
  assert.match(RENDER, /el\("div", "empty-state"\); empty\.id = "empty-state"/);
});
