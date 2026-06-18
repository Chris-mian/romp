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

test("ledger marks: every state is the SAME 13px disc — ○ hollow, ✓ done, ⏸ blocked", () => {
  // ✓/⏸ are the mark's own text; not-done = a CSS-drawn hollow ring (no glyph). The CURRENT/active node
  // gets NO special mark — its checkbox is identical to every other item (the user 2026-06-17).
  assert.match(RENDER, /mark\.textContent = n\.done \? "✓" : n\.blocked \? "⏸" : "";/);
  assert.doesNotMatch(RENDER, /n\.current \? "▸"/);                          // the old triangle is gone
  // base mark = a 13px round disc shared by every state (sizes normalized — the user 2026-06-16)
  assert.match(CSS, /\.ledger-tmark \{[^}]*width: 13px;[^}]*border-radius: 50%/);
  assert.match(CSS, /\.ledger-tmark \{[^}]*border: 1\.5px solid var\(--dim\)/);   // not-done = hollow ring
  assert.match(CSS, /\.ledger-tnode\.done \.ledger-tmark \{[^}]*var\(--check-bg\)/);   // done = blue disc
  assert.match(CSS, /\.ledger-tnode\.blocked \.ledger-tmark \{[^}]*var\(--err\)/);    // blocked = red ring
});

test("ledger checkbox tooltip LEADS with why the mark reads as it does — explicit vs inferred (roll-up/down) (the user 2026-06-18)", () => {
  // a markReason() classifies the node and the reason is PREPENDED to the existing jump hint, so hovering
  // an outlined ✓ explains itself instead of needing the rule reverse-engineered.
  assert.match(RENDER, /const markReason = \(\): string =>/);
  assert.match(RENDER, /"done — explicitly checked off"/);                 // explicit (solid ✓)
  assert.match(RENDER, /"done — inferred: every sub-step is complete"/);   // derived via roll-UP
  assert.match(RENDER, /"done — inferred: a parent goal was checked off"/);// derived via roll-DOWN
  assert.match(RENDER, /"dismissed — cleared, not judged done"/);          // cleared
  // roll-up vs roll-down is decided from the node's own children (no kernel round-trip)
  assert.match(RENDER, /kids\.length > 0 && kids\.every\(\(k\) => k\.done\)/);
  // the reason is prepended to the jump hint on the CHECKBOX in both the resolved and open branches
  assert.match(RENDER, /wireZone\(mark, resolveT, "assistant", reason \+ " · " \+ resTitle\)/);
  assert.match(RENDER, /wireZone\(mark, startT, "user", reason \+ " · jump to the message/);
});

test("a CLEARED node links to where it was CREATED, not 'checked off' — it was never resolved (the user 2026-06-18)", () => {
  // cleared carries done=true and would otherwise fall into the resolved branch and link to a nonexistent
  // checkoff point. A dedicated cleared branch (checked FIRST) routes the mark to startT (creation) instead.
  assert.match(RENDER, /if \(n\.cleared\) \{[\s\S]*?wireZone\(mark, startT, "user", reason \+ " · jump to where it was created"\)/);
  assert.match(RENDER, /wireZone\(time, startT, "user", "jump to where it was created"\)/);
  // the cleared branch precedes the done/blocked branch, so a cleared node never reaches the "checked off" hint
  assert.ok(RENDER.indexOf("if (n.cleared) {") < RENDER.indexOf('n.done ? "jump to where this got checked off"'),
    "cleared is handled before the resolved branch");
});

test("the CURRENT node highlights the ROW only — never mutates its checkbox or text (the user 2026-06-17)", () => {
  // the active line gets a row highlight (faint background + a bright left accent bar) and the live "(Xm)"
  // parenthesised time — that's the whole signal. The earlier filled-dot-on-the-mark + bold/recoloured text
  // are GONE, so the checkbox + text read exactly like every other item.
  assert.match(CSS, /\.ledger-tnode\.current \{[^}]*background:[^}]*box-shadow: inset 2px 0 0 var\(--fg\)/);  // row highlight kept
  assert.doesNotMatch(CSS, /\.ledger-tnode\.current \.ledger-tmark/);   // NO checkbox override (the white dot is gone)
  assert.doesNotMatch(CSS, /\.ledger-tnode\.current \.ledger-ttext/);   // NO text recolour/bold
  // a current+blocked node now shows its normal red ⏸ ring: `current` no longer suppresses .blocked
  assert.match(RENDER, /\(n\.blocked && !n\.done \? " blocked" : ""\)/);
  assert.doesNotMatch(RENDER, /n\.blocked && !n\.current && !n\.done/);
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

test("the → 'most recent' arrow is GONE — the highlight alone marks the node (the user 2026-06-17)", () => {
  // arrow + highlight were unified onto the same node, so the arrow was redundant; dropped per the user.
  assert.doesNotMatch(RENDER, /el\("span", "ledger-recent"\)/);        // no arrow element
  assert.doesNotMatch(RENDER, /arr\.textContent = "→"/);
  assert.doesNotMatch(CSS, /\.ledger-recent \{/);                      // no arrow CSS
  // the kernel's `recent` flag still exists — it drives the auto-expand (onpath) of that node's branch
  assert.match(RENDER, /recent\?: boolean/);
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

test("explicit done = solid ✓; derived AND cleared share ONE outlined ✓ (no separate opacity-fade) (the user 2026-06-17)", () => {
  // both flags still get their own class, but the CSS gives both the SAME outlined treatment — one
  // "secondary/inferred" check style, not two mechanisms (was an outline for derived + an opacity-fade for
  // cleared). A strong solid check must never be confusable with the weaker outlined one.
  assert.match(RENDER, /\(n\.derived \? " derived" : ""\) \+ \(n\.cleared \? " cleared" : ""\)/);
  assert.match(RENDER, /cleared\?: boolean/);
  assert.match(CSS, /\.ledger-tnode\.done \.ledger-tmark \{[^}]*background: var\(--check-bg\)/);   // explicit = solid
  // derived AND cleared in ONE rule → the single outlined style (blue ring + blue ✓ on transparent)
  assert.match(CSS, /\.ledger-tnode\.done\.derived \.ledger-tmark,\s*\.ledger-tnode\.done\.cleared \.ledger-tmark \{[^}]*background: transparent;[^}]*border-color: var\(--check-bg\);[^}]*color: var\(--check-bg\)/);
  assert.doesNotMatch(CSS, /\.ledger-tnode\.cleared \.ledger-tmark \{[^}]*opacity/);   // the opacity-fade mechanism is gone
});

test("top-level goals are separated by a thin rule", () => {
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
  assert.match(CSS, /\.ledger-tree \{[^}]*row-gap: 4px/);                   // a little more vertical space between rows (the user 2026-06-17)
  assert.match(CSS, /\.ledger-tnode\.ledger-top \{[^}]*margin-top: 9px/);   // extra space between top-level goals
});

test("ledger keeps a small left indent so the marks aren't clipped at the edge (the user 2026-06-17)", () => {
  // the wider 20px gutter was for the (now-removed) → arrow's -19px hang; tightened to a small indent that
  // still keeps the disc marks off the overflow-x:hidden edge.
  assert.match(CSS, /\.ledger-tree \{[^}]*padding-left: 8px/);
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

test("ledger row = 3 zones: text→message (user turn @t), mark+time→checked-off (@mt) (the user 2026-06-17)", () => {
  assert.match(RENDER, /mt\?: number/);                                     // node carries the resolution time
  // two distinct anchors: where it was STATED (t → the user message) vs where it got CHECKED OFF (mt)
  assert.match(RENDER, /const startT = n\.t;/);
  assert.match(RENDER, /const resolveT = n\.mt \?\? n\.t;/);
  // the text zone jumps to the nearest USER turn (the message); the mark + time to the resolution turn
  assert.match(RENDER, /wireZone\(txt, startT, "user",/);
  assert.match(RENDER, /wireZone\(mark, resolveT, "assistant",/);
  assert.match(RENDER, /wireZone\(time, resolveT, "assistant",/);
  assert.match(RENDER, /z\.addEventListener\("click", \(ev\) => \{ ev\.stopPropagation\(\); scrollToNearestT\(t, kind\); \}\)/);
  // the whole-row jump is gone — no row-level click or .nav class anymore
  assert.doesNotMatch(RENDER, /row\.classList\.add\("nav"\)/);
  // the hover highlight is per-ZONE (.lz-hl, JS-toggled): a halo on the mark disc, a fill on text/time
  assert.match(RENDER, /z\.classList\.add\("lz-nav"\)/);
  assert.match(CSS, /\.ledger-tnode \.lz-nav \{[^}]*cursor: pointer/);
  assert.match(CSS, /\.ledger-tmark\.lz-hl \{[^}]*box-shadow/);       // mark = halo ring (fill untouched)
  assert.match(CSS, /\.ledger-ttext\.lz-hl[^{]*\{[^}]*background/);   // text = rounded fill
});

test("ledger checkbox + time are LINKED — hovering either lights both; text lights alone (the user 2026-06-17)", () => {
  // a class-driven group (not :hover) so one zone can light its partner across the text between them
  assert.match(RENDER, /const linkHover = \(group: HTMLElement\[\]\) =>/);
  assert.match(RENDER, /group\.forEach\(\(g\) => g\.classList\.add\("lz-hl"\)\)/);
  assert.match(RENDER, /linkHover\(\[txt\]\);/);                                   // (resolved) text on its own
  assert.match(RENDER, /linkHover\(time\.textContent \? \[mark, time\] : \[mark\]\)/);  // (resolved) mark + time together
});

test("ledger UNRESOLVED node: checkbox + text light together, checkbox STAYS a circle (the user 2026-06-17)", () => {
  // not yet checked off / blocked → the mark points at the SAME message as the text and they light together,
  // but each keeps its own shape: the checkbox is its CIRCULAR halo, never a square (no .lz-merge fill).
  assert.match(RENDER, /if \(n\.done \|\| n\.blocked\) \{/);                       // the split is gated on resolved
  assert.match(RENDER, /wireZone\(mark, startT, "user", reason \+ " · jump to the message that asked for this"\)/);
  assert.match(RENDER, /linkHover\(\[mark, txt\]\)/);                              // light together, normal shapes
  assert.match(CSS, /\.ledger-tmark\.lz-hl \{[^}]*box-shadow/);                    // checkbox highlight = circular halo
  assert.doesNotMatch(CSS, /lz-merge/);                                            // no square/bridged merge fill
});

test("scrollToNearestT: 'assistant' PREFERS the assistant turn (fallback any); 'user' stays strict", () => {
  // this is what makes the text zone (user turn) and the checkbox/time zones (assistant turn) land on
  // DIFFERENT turns within one prompt→response exchange (the user 2026-06-17)
  assert.match(RENDER, /kind === "user" \? pick\("turn-user"\) : kind === "assistant" \? pick\("turn-assistant"\) : pick\(null\)/);
  assert.match(RENDER, /if \(kind === "assistant" && \(!hit\.el \|\| hit\.d > 6 \* 3600\)\) hit = pick\(null\)/);
});

test("expanding the ledger preserves the scroll position (no jump to top) (the user 2026-06-17)", () => {
  // fold/expand re-render restores the tree scroll-pane
  assert.match(RENDER, /const prevTreeScroll = \(host\.querySelector\(".ledger-tree"\) as HTMLElement \| null\)\?\.scrollTop \?\? 0/);
  assert.match(RENDER, /wrap\.scrollTop = prevTreeScroll/);
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

test("collapsed ledger shows the CURRENT top-level goal; expanded shows the title + full tree (the user 2026-06-18)", () => {
  // the current top goal = the depth-0 root on the active path (current/onpath), else the freshest unfinished root
  assert.match(RENDER, /const curTop = roots0\.find\(\(r\) => r\.current \|\| r\.onpath\)/);
  // collapsed line = that goal's text; expanded keeps the archiver title (with the tree below)
  assert.match(RENDER, /sum\.textContent = \(ledgerCollapsed && curTop\) \? curTop\.text : titleText;/);
  // the early return still bails after the head in collapsed mode (no tree)
  assert.match(RENDER, /if \(ledgerCollapsed\) return;/);
});

test("expanding PINS the current top goal to the top of the tree + marks it, so it doesn't jump down (the user 2026-06-18)", () => {
  // expanding used to drop curTop into its sorted position (further down) — disorienting. Pin it first.
  assert.match(RENDER, /const orderedRoots = curTop \? \[curTop, \.\.\.sorted\.filter\(\(r\) => r\.id !== curTop\.id\)\] : sorted;/);
  // and the pinned row carries a marker class so the collapsed line visibly maps onto it
  assert.match(RENDER, /depth === 0 && curTop && n\.id === curTop\.id \? " ledger-curtop" : ""/);
  assert.match(CSS, /\.ledger-tnode\.ledger-curtop \{[^}]*box-shadow: inset 2px 0 0 #8fb3ff/);
});
