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

test("ledger marks: every state is the SAME 13px disc — ○ hollow, ● working, ✓ done, ⏸ blocked", () => {
  // ✓/⏸ are the mark's own text; not-done (○) and current (●) are CSS-drawn discs (no glyph) so the
  // working mark is a filled dot, NOT a ▸ triangle that read as a clickable caret (the user 2026-06-16).
  assert.match(RENDER, /mark\.textContent = n\.done \? "✓" : \(n\.blocked && !n\.current\) \? "⏸" : "";/);
  assert.doesNotMatch(RENDER, /n\.current \? "▸"/);                          // the old triangle is gone
  // base mark = a 13px round disc shared by every state (sizes normalized — the user 2026-06-16)
  assert.match(CSS, /\.ledger-tmark \{[^}]*width: 13px;[^}]*border-radius: 50%/);
  assert.match(CSS, /\.ledger-tmark \{[^}]*border: 1\.5px solid var\(--dim\)/);   // not-done = hollow ring
  assert.match(CSS, /\.ledger-tnode\.done \.ledger-tmark \{[^}]*var\(--check-bg\)/);   // done = blue disc
  assert.match(CSS, /\.ledger-tnode\.current \.ledger-tmark \{[^}]*background: var\(--fg\)/);  // working = filled dot
  assert.match(CSS, /\.ledger-tnode\.blocked \.ledger-tmark \{[^}]*var\(--err\)/);    // blocked = red ring
});

test("ledger: a done item's text takes its (resolution-time) recency colour (ticks with the clock)", () => {
  // set on first render and again in refreshLedgerAges; keyed on mt (resolution) with a t fallback
  const hits = RENDER.match(/if \(n\.done && \(n\.mt \?\? n\.t\)\) txt\.style\.color = ageColorReadable\(now - \(n\.mt \?\? n\.t\)!\)/g) || [];
  assert.equal(hits.length, 1, "render-loop tint");
  assert.match(RENDER, /if \(n && txt && n\.done && \(n\.mt \?\? n\.t\)\) txt\.style\.color = ageColorReadable\(now - \(n\.mt \?\? n\.t\)!\)/);
});

test("ledger times hug the content (tree is fit-content) yet stay right-aligned", () => {
  assert.match(CSS, /\.ledger-tree \{[^}]*width: fit-content/);
});

test("the blue ✓ disc is standardized: ledger + feed card check carry the chat to-do's 9px/700 ✓", () => {
  const FEED_CSS = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "feed.css"), "utf8");
  assert.match(CSS, /\.ledger-tmark \{[^}]*font-size: 9px; font-weight: 700/);   // now on the shared base mark
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

test("a cleared node renders as a FADED ✓; top-level goals are separated by a thin rule", () => {
  // cleared reuses the dimmed-disc treatment (the .derived rule); the kernel flags `cleared`
  assert.match(RENDER, /\(n\.derived \|\| n\.cleared\) \? " derived" : ""/);
  assert.match(RENDER, /cleared\?: boolean/);
  // a thin separator above every top-level goal so distinct goals read apart (the user 2026-06-16);
  // the first top goal gets none.
  assert.match(RENDER, /depth === 0 \? " ledger-top" : ""/);
  assert.match(CSS, /\.ledger-tnode\.ledger-top \{[^}]*border-top: 1px solid var\(--box-border\)/);
  assert.match(CSS, /\.ledger-tree > \.ledger-tnode\.ledger-top:first-child \{[^}]*border-top: 0/);
});

test("a FLAT ledger (no expandable node anywhere) drops the disclosure column so bullets sit flush", () => {
  // the user 2026-06-16: a caret-less list shouldn't reserve a caret column on every leaf
  assert.match(RENDER, /const anyExpandable = tree\.some\(\(n\) => !!\(n\.children && n\.children\.length\)\)/);
  assert.match(RENDER, /el\("div", "ledger-tree" \+ \(anyExpandable \? "" : " flat"\)\)/);
  assert.match(RENDER, /if \(anyExpandable\) lead\.push\(tri\)/);          // tri appended only when something can expand
  assert.match(CSS, /\.ledger-tree\.flat \.ledger-tri \{[^}]*display: none/);
});

test("ledger spacing: gap before the times; roomy rows + separated top goals (the user 2026-06-16)", () => {
  assert.match(CSS, /\.ledger-ttime \{[^}]*margin-left: 1\.75em/);          // whitespace before the times
  assert.match(CSS, /\.ledger-tnode \{[^}]*line-height: 1\.45/);            // roomy rows so the discs don't kiss
  assert.match(CSS, /\.ledger-tree \{[^}]*row-gap: 2px/);
  assert.match(CSS, /\.ledger-tnode\.ledger-top \{[^}]*margin-top: 9px/);   // extra space between top-level goals
});

test("ledger sorts unfinished goals on top, finished at the bottom (recency within each — the user 2026-06-16)", () => {
  // within each group, most recent first by mt (resolution/last-touched), falling back to t (creation)
  assert.match(RENDER, /const byRecency = \(a: LedgerTreeNode, b: LedgerTreeNode\) => \(\(b\.mt \?\? b\.t\) \|\| 0\) - \(\(a\.mt \?\? a\.t\) \|\| 0\)/);
  assert.match(RENDER, /roots\.filter\(\(r\) => !r\.done\)\.sort\(byRecency\)/);
  assert.match(RENDER, /roots\.filter\(\(r\) => r\.done\)\.sort\(byRecency\)/);
  assert.match(RENDER, /for \(const r of orderedRoots\) renderNode\(r, 0\)/);
  // a finished task's "(Xm ago)" label is time since it RESOLVED/cleared (mt), not since it began
  assert.match(RENDER, /const dt = \(n\.mt \?\? n\.t\)!;/);
});

test("ledger rows click → jump to chat: done/blocked by mt, open by t (the user 2026-06-16)", () => {
  assert.match(RENDER, /mt\?: number/);                                     // node carries the resolution time
  assert.match(RENDER, /const navT = \(n\.done \|\| n\.blocked\) \? \(n\.mt \?\? n\.t\) : n\.t/);
  assert.match(RENDER, /row\.addEventListener\("click", \(\) => \{ scrollToNearestT\(navT, "assistant"\); \}\)/);
  assert.match(RENDER, /row\.classList\.add\("nav"\)/);
  assert.match(CSS, /\.ledger-tnode\.nav \{[^}]*cursor: pointer/);
});

test("expanding preserves scroll; the → arrow doesn't shift the recent row (the user 2026-06-17)", () => {
  // fold/expand re-render restores the tree scroll-pane (no jump to top)
  assert.match(RENDER, /const prevTreeScroll = \(host\.querySelector\(".ledger-tree"\) as HTMLElement \| null\)\?\.scrollTop \?\? 0/);
  assert.match(RENDER, /wrap\.scrollTop = prevTreeScroll/);
  // the recency arrow hangs net-zero (-(width 12 + gap 7)) so a recent row aligns with its siblings
  assert.match(CSS, /\.ledger-recent \{[^}]*margin-left: -19px/);
});

test("the ledger recency colour uses the globally-selected colormap (the user 2026-06-17)", () => {
  assert.match(RENDER, /const COLORMAPS: Record<string, Array<\[number, number, number\]>>/);
  assert.match(RENDER, /viridis:/);
  assert.match(RENDER, /cividis:/);
  // ramp reads the chosen map from settings (kept current + rerenderAll on change), default hawaii
  assert.match(RENDER, /COLORMAPS\[\(settings\.colormap \|\| ""\)\.toLowerCase\(\)\] \|\| COLORMAPS\.hawaii/);
  assert.match(RENDER, /const STOPS = selectedStops\(\);/);
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
