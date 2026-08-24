// The timeline's corner control panel (the user 2026-08-18; filter-chip form + TAG model
// 2026-08-23): "Filter ▾" in the bottom-left corner — the strip under the lane gutter, left of the
// time labels. The dropdown picks the active VIEW (default = UNTAGGED sessions / the named tags),
// holds New tag… / Sessions & tags…, and carries the two timeline display toggles (collapse idle
// gaps, active only) so they finally work in every host. The dialog is TAG-CENTRIC: one row per
// session wearing its tag chips (✕ leaves a tag; [+] joins or mints one) — a tagged session leaves
// the default view and shows under its tags. House pattern: execute the pure helpers + reconcile
// on a bare prototype, regex-pin the SVG/menu wiring.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { createRequire } from "node:module";

const requireCjs = createRequire(__filename);
const VIEW_PATH = path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js");
const SRC = fs.readFileSync(VIEW_PATH, "utf8");
const { TimelinePanel, viewVisible, viewLabel, viewMoreCount, viewToggleHidden, viewToggleMember } = requireCjs(VIEW_PATH);

const G = { id: "g1", name: "pool", color: "#DD42FF", members: ["s2", "s3"] };
const V = (active: string, hidden: string[] = [], tags: any[] = [G]) => ({ active, hidden, tags });

test("executed: the default view shows UNTAGGED minus hidden; a tag view its members exactly", () => {
  assert.equal(viewVisible(null, "s1"), true, "no blob yet → everything shows");
  assert.equal(viewVisible(V("all", ["s9"]), "s9"), false, "hidden");
  assert.equal(viewVisible(V("all"), "s2"), false, "TAGGED → out of the default view (the user 2026-08-23)");
  assert.equal(viewVisible(V("all"), "s1"), true, "untagged → shown");
  assert.equal(viewVisible(V("g1", ["s2"]), "s2"), true, "a tag view shows its members, hidden or not");
  assert.equal(viewVisible(V("g1"), "s1"), false, "a tag view shows exactly its members");
  assert.equal(viewVisible(V("ghost", [], []), "s1"), true, "an orphaned active falls back open");
  assert.equal(viewVisible({ active: "all", groups: [G] }, "s2"), false,
    "the legacy `groups` key an un-updated kernel pushes reads identically");
});

test("executed: the trigger label and the N-more cue (live sessions outside the view)", () => {
  assert.equal(viewLabel(null), "default");
  assert.equal(viewLabel(V("g1")), "pool");
  const sessions = [{ id: "s1", live: true }, { id: "s2", live: true }, { id: "s4", live: false }];
  assert.equal(viewMoreCount(V("g1"), sessions), 1, "s1 is live and outside; dead s4 never counts");
  assert.equal(viewMoreCount(V("all", ["s1"]), sessions), 2, "hidden live s1 AND tagged live s2 count; dead s4 never");
});

test("executed: an optimistic edit holds until the kernel echoes it — then yields to authority", () => {
  const p: any = Object.create(TimelinePanel.prototype);
  p._views = null; p._pendingViews = V("g1"); p._pendingViewsAge = 0;
  p._reconcileViews();
  assert.ok(p._pendingViews, "no echo yet → still pending");
  // the kernel echoes the same shape with re-sorted lists → canonical comparison clears it
  p._views = { active: "g1", hidden: [], tags: [{ id: "g1", name: "pool", color: "#DD42FF", members: ["s3", "s2"] }] };
  p._reconcileViews();
  assert.equal(p._pendingViews, null, "echo match (order-insensitive) clears the pending edit");
  // a pending edit the kernel never echoes yields after three pushes — the kernel is authoritative
  p._pendingViews = V("g1"); p._pendingViewsAge = 0;
  p._views = { active: "all", hidden: [], tags: [] };
  p._reconcileViews(); p._reconcileViews();
  assert.ok(p._pendingViews, "two silent pushes → still holding");
  p._reconcileViews();
  assert.equal(p._pendingViews, null, "the third silent push adopts the kernel's blob");
});

test("the lane gate composes the view filter first, and the all-quiet fallback respects it", () => {
  assert.match(SRC, /const inView = \(s\) => viewVisible\(this\._curViews\(\), s\.id\);/);
  assert.match(SRC, /let vis = data\.sessions\.filter\(inView\)\.filter\(active\);/);
  assert.match(SRC, /if \(this\._activeOnly && !vis\.length\) vis = data\.sessions\.filter\(inView\)\.filter\(\(s\) => s\.live \|\| hasWork\(s\)\);/,
    "the fallback can never resurrect a view-hidden lane");
});

test("the trigger sits in the corner strip and opens on pointerdown, like every timeline control", () => {
  assert.match(SRC, /_drawViewsTrigger\(svg, axisY\);/);
  // named for what it does (the user 2026-08-23): it FILTERS the lanes — "Show:" read as a passive label
  assert.match(SRC, /t\.textContent = 'Filter ▾';/);
  assert.match(SRC, /t\.addEventListener\('pointerdown', \(e\) => \{ e\.preventDefault\(\); e\.stopPropagation\(\); this\._openViewsMenu\(t\); \}\);/);
  assert.match(SRC, /const tailStr = more \? more \+ ' more' : '';/, "a filtered-out live session is always one glance away");
});

test("an active tag is a REMOVABLE CHIP: outline only in its colour, a dim separate ✕, air below (the user 2026-08-24)", () => {
  // the chip's own pointerdown clears the filter without a menu trip; stopPropagation keeps the
  // text element's menu handler out of it (both are pointerdown — the redraw-eats-click rule)
  assert.match(SRC, /grp\.addEventListener\('pointerdown', \(e\) => \{\n\s*e\.preventDefault\(\); e\.stopPropagation\(\);\n\s*const nv = JSON\.parse\(JSON\.stringify\(v\)\); nv\.active = 'all'; this\._setViews\(nv\);/);
  // OUTLINE only on the page's own ground (the tinted fill was too much — the user 2026-08-24),
  // and the ✕ is dim and SEPARATE, the composer context chip's read — never baked into the name
  assert.match(SRC, /fill: 'transparent',\n\s*stroke: g\.color \|\| '#cccccc', 'stroke-width': 1/);
  assert.match(SRC, /y: y - 13, width: cw, height: 18, rx: 9,/, "taller chip");
  assert.match(SRC, /cx\.textContent = '✕';/);
  assert.match(SRC, /fill: MODEL_FG, opacity: 0\.75/);
  assert.match(SRC, /fill: g\.color \|\| '#cccccc', 'font-weight': 650/);
  assert.match(SRC, /click to remove the filter \(back to the default view\)/);
  // no chip on the default view — nothing to remove
  assert.match(SRC, /const active = !!g && v\.active && v\.active !== 'all';/);
  // …and the bottom strip grew so the taller chip has air
  assert.match(SRC, /bottom: 27 \}/);
});

test("a pointerdown-opened menu survives its OWN opening click (the user 2026-08-24, click-and-hold bug)", () => {
  // the browser fires a click after pointerup; unstopped it bubbles to the document's menu-closer
  // and shuts the menu the instant it opened — only a mid-press redraw (element swapped, no click
  // at all) let it survive, which read as "hold to open". Every pointerdown anchor swallows it.
  assert.match(SRC, /this\._openViewsMenu\(t\); \}\);[\s\S]{0,400}t\.addEventListener\('click', \(e\) => e\.stopPropagation\(\)\);/);
  assert.match(SRC, /this\._openLaneMenu\(s, ghit\);\n\s*\}\);[\s\S]{0,300}ghit\.addEventListener\('click', \(e\) => e\.stopPropagation\(\)\);/);
  assert.match(SRC, /grp\.addEventListener\('click', \(e\) => e\.stopPropagation\(\)\);/);
});

test("the dropdown and dialog wear the shared menu vocabulary and adopt into the menu host", () => {
  assert.match(SRC, /'position:fixed;z-index:1001;min-width:200px;' \+ MENU_STYLE/);
  assert.match(SRC, /c\.setAttribute\('style', MENU_CHECK_STYLE\);/, "the ✓-in-circle current mark");
  assert.match(SRC, /'position:fixed;inset:0;z-index:1002;background:rgba\(0,0,0,0\.55\);'/,
    "the one modal dim, over the topmost same-origin document");
  assert.match(SRC, /const h = this\._menuHost\(anchorEl\.getBoundingClientRect\(\)\);[\s\S]{0,400}this\._viewsMenu = menu;/);
});

test("the sessions dialog is TAG-CENTRIC: chips per row, a [+] to join or mint, the feed toggle rides along", () => {
  // the user 2026-08-23: multi-tag assignment in one visit — each row wears its tags as removable
  // chips (the tag's colour, the trigger chip's dress) and a [+] menu of the tags it lacks + a
  // new-tag input. The menu items say so: New tag… / Sessions & tags…
  assert.match(SRC, /item\('New tag…', \{ dim: true \}\)/);
  assert.match(SRC, /item\('Sessions & tags…', \{ dim: true \}\)/);
  assert.match(SRC, /ch\.createSpan\(\{ text: t\.name \}\);/);
  assert.match(SRC, /const chx = ch\.createSpan\(\{ text: '✕' \}\);/, "the ✕ is its own dim span — the composer chip's read");
  assert.doesNotMatch(SRC, /background:color-mix/, "no tinted chip grounds anywhere in the dialog");
  assert.match(SRC, /this\._setViews\(viewToggleMember\(this\._curViews\(\), t\.id, s\.id\)\); build\(\);/,
    "chip click = leave that tag; [+] option = join — both through the one pure mutation");
  assert.match(SRC, /ni\.placeholder = 'new tag…';/, "minting a tag right from a session row");
  assert.match(SRC, /nv\.tags = viewTags\(nv\)\.concat\(\[nt\]\); delete nv\.groups;/,
    "a write normalizes onto the tags key, never re-emitting the legacy one");
  // the eye-off appears ONLY on a hidden session, to un-hide it (hiding lives on the chat tab)
  assert.match(SRC, /if \(\(v\.hidden \|\| \[\]\)\.indexOf\(s\.id\) >= 0\) \{/);
  // the feed toggle still rides every live row (the user 2026-08-19 pool-builder rule): a
  // background worker wants BOTH edits — tagged out of the default view AND off the feed — in one
  // visit. Reused machinery, never a new one; NOT auto-coupled to membership.
  assert.match(SRC, /const ft = LANE_TOGGLES\.find\(\(t\) => t\.flag === 'hideFromFeed'\);/);
  assert.match(SRC, /\(this\._pendingFlags\[s\.id\] = this\._pendingFlags\[s\.id\] \|\| \{\}\)\.hideFromFeed = next;/,
    "the same optimistic sticky flags the lane gear uses");
  assert.match(SRC, /this\._setSessionFlag\(s, 'hideFromFeed', next\);\s*\n\s*this\._reconcilePendingFlags\(\);/);
});

test("the two display toggles write the host's own romp:settings — reachable in every host now", () => {
  assert.match(SRC, /item\('Collapse idle gaps', \{ current: !!this\._collapseGaps, dim: true \}\)/);
  assert.match(SRC, /item\('Active sessions only', \{ current: !!this\._activeOnly, dim: true \}\)/);
  assert.match(SRC, /localStorage\.setItem\('romp:settings', JSON\.stringify\(s\)\);/);
});

test("_setViews posts through the host hook with a GUARDED, atomic Obsidian fallback", () => {
  assert.match(SRC, /window\.__rompTimelineSetViews === 'function'/);
  // Electron-gated (a bare-node test run must never touch the real file — the 2026-07-02 lesson),
  // env-aware state root, tmp+rename so a reader never sees a torn blob
  assert.match(SRC, /process\.versions && process\.versions\.electron/);
  assert.match(SRC, /process\.env\.ROMP_STATE_DIR\n?\s*\|\| path\.join\(process\.env\.XDG_STATE_HOME \|\| path\.join\(os\.homedir\(\), '\.local', 'state'\), 'romp'\)/);
  assert.match(SRC, /fs\.renameSync\(fp \+ '\.tmp', fp\);/);
  assert.match(SRC, /this\._pendingViews = v; this\._pendingViewsAge = 0;/);
  assert.match(SRC, /this\._reconcileViews\(\);\s*\/\/ \.\.\.and an optimistic view edit/);
});

test("executed: the dialog's two checkbox mutations, pure", () => {
  const v = { active: "all", hidden: ["a"], tags: [{ id: "g1", members: ["m"] }] };
  assert.deepEqual(viewToggleHidden(v, "a").hidden, [], "unhide");
  assert.deepEqual(viewToggleHidden(v, "b").hidden, ["a", "b"], "hide");
  assert.deepEqual(viewToggleMember(v, "g1", "m").tags[0].members, [], "leave");
  assert.deepEqual(viewToggleMember(v, "g1", "n").tags[0].members, ["m", "n"], "join");
  assert.deepEqual(viewToggleMember(v, "ghost", "n"), v, "an unknown tag mutates nothing");
});

test("the trigger measures its WHOLE string against the gutter, and the dialog's Escape hook dies on every close", () => {
  // the fit measures the whole line as LAID OUT: trigger + gap + padded chip + gap + tail
  assert.match(SRC, /const width = \(n\) => this\.labelWidth\('Filter ▾'\)\n\s*\+ \(active \? GAP \+ PADH \* 2 \+ this\.labelWidth\(n\) \+ XGAP \+ this\.labelWidth\('✕'\) : 0\)\n\s*\+ \(tailStr \? GAP \+ this\.labelWidth\(tailStr\) : 0\);/);
  assert.match(SRC, /const fits = \(n\) => width\(n\) <= this\.M\.left - PADL - 6;/);
  assert.match(SRC, /this\._viewsDialogKey = \{ doc: h\.doc, fn: onKey \};/);
  assert.match(SRC, /this\._viewsDialogKey\.doc\.removeEventListener\('keydown', this\._viewsDialogKey\.fn\);/);
});

test("the views menu closes with its siblings on outside click / Escape / pagehide", () => {
  assert.match(SRC, /this\._onDocClick = \(\) => \{ this\._closeMetaMenu\(\); this\._closeLaneMenu\(\); this\._closeViewsMenu\(\); \};/);
  assert.match(SRC, /if \(e\.key === 'Escape'\) \{ this\._closeMetaMenu\(\); this\._closeLaneMenu\(\); this\._closeViewsMenu\(\); \}/);
  assert.match(SRC, /this\._closeViewsMenu\(\); this\._closeViewsDialog\(\);/, "pagehide drops both overlays");
});
