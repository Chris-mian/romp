// GROUP BY TAG in the Sessions pane (T399, the user 2026-09-12: the pane's lanes sectioned by tag the way the chat tab
// strip is). The pane is served raw and loads no module, so it mirrors tab-groups.ts: ONE blob (romp:tabgroups) for both
// surfaces, the folds one truth (collapsed / expanded, archived folded by default, the pins carried through), the pane's
// switch its own field (`timeline`, present only while on). The row model is a pure function (tlRows), executed here:
// off, the rows ARE the visible lanes in their order (the pane as before T399, row for row); on, each section's head
// (a folded one keeps its head alone), its lanes, a session under two tags in both, the untagged trail behind a divider.
// The head's chip mirrors tagChip's pill: its numbers are parsed from TAG_CHIP_STYLE, and this pins them against
// tag-menu.ts's own bytes. The Filter menu's row is executed over the house three-helper host (the tagbtn-click harness).
// Synthetic sessions and tags only (the notes-api demo world).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { createRequire } from "node:module";

function makeNode(tag: string): any {
  const n: any = {
    tag, _attrs: {}, children: [] as any[], style: {}, dataset: {}, textContent: "", parentNode: null,
    classList: { _s: new Set<string>(), add(...a: string[]) { a.forEach((c) => this._s.add(c)); },
      remove(...a: string[]) { a.forEach((c) => this._s.delete(c)); },
      toggle(c: string, f?: boolean) { f ? this._s.add(c) : this._s.delete(c); }, contains(c: string) { return this._s.has(c); } },
    setAttribute(k: string, v: any) { this._attrs[k] = v; }, getAttribute(k: string) { return k in this._attrs ? this._attrs[k] : null; },
    setAttributeNS(_n: any, k: string, v: any) { this._attrs[k] = v; }, removeAttribute(k: string) { delete this._attrs[k]; },
    appendChild(c: any) { if (c.parentNode) { const i = c.parentNode.children.indexOf(c); if (i >= 0) c.parentNode.children.splice(i, 1); } c.parentNode = n; this.children.push(c); return c; },
    insertBefore(c: any, ref: any) { c.parentNode = n; const i = this.children.indexOf(ref); i < 0 ? this.children.push(c) : this.children.splice(i, 0, c); return c; },
    removeChild(c: any) { const i = this.children.indexOf(c); if (i >= 0) this.children.splice(i, 1); return c; },
    get firstChild() { return this.children[0] || null; },
    remove() { if (n.parentNode) n.parentNode.removeChild(n); },
    _listeners: {} as any,
    addEventListener(t: string, fn: any) { n._listeners[t] = fn; }, removeEventListener() {},
    querySelector() { return null; }, querySelectorAll() { return []; },
    getBoundingClientRect() { return { width: 32, height: 18, left: 8, top: 400, right: 40, bottom: 418 }; },
    closest() { return null; }, focus() {},
    createEl(t: string, o: any) { const e = makeNode(t); if (o && o.cls) e.classList.add(o.cls); if (o && o.text) e.textContent = o.text; this.appendChild(e); return e; },
    createDiv(o: any) { return this.createEl("div", o); }, createSpan(o: any) { return this.createEl("span", o); },
  };
  return n;
}
const store = new Map<string, string>();
const g: any = global;
g.document = {
  createElement(t: string) { return t === "canvas" ? { getContext() { return { font: "", measureText(s: string) { return { width: (s ? s.length : 0) * 6 }; } }; } } : makeNode(t); },
  createElementNS(_n: any, t: string) { return makeNode(t); },
  createTextNode(text: string) { const n = makeNode("#text"); n.textContent = text; return n; },
  body: makeNode("body"), documentElement: makeNode("html"), head: makeNode("head"),
  getElementById() { return null; }, addEventListener() {}, removeEventListener() {},
};
g.localStorage = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => { store.set(k, v); }, removeItem: (k: string) => { store.delete(k); } };
g.getComputedStyle = () => ({ backgroundColor: "rgb(30,30,30)" });
g.requestAnimationFrame = (fn: any) => 0;
const events: string[] = [];
g.window = g; g.innerWidth = 1400; g.innerHeight = 800;
g.dispatchEvent = (e: any) => { events.push(e && e.type); return true; };
g.CustomEvent = class { type: string; constructor(t: string) { this.type = t; } };
g.addEventListener = () => {}; g.removeEventListener = () => {};

const viewPath = path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js");
const V: any = createRequire(__filename)(viewPath);
const TABGROUPS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "tab-groups.ts"), "utf8");
const TAGMENU = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "tag-menu.ts"), "utf8");
const VIEW_SRC = fs.readFileSync(viewPath, "utf8");

const WEB = "11111111-2222-3333-4444-000000000001", API = "11111111-2222-3333-4444-000000000002", TESTS = "11111111-2222-3333-4444-000000000003",
  DOCS = "11111111-2222-3333-4444-000000000004", OLD = "11111111-2222-3333-4444-000000000006";
const S = (id: string, name: string) => ({ id, name, color: "#9cd2ff" });
const vis = [S(API, "api"), S(WEB, "web"), S(TESTS, "tests"), S(DOCS, "docs"), S(OLD, "old-notes")];
const unions = [{ name: "backend", color: "#1EA1EB", members: [API, WEB] }, { name: "frontend", color: "#e0a54a", members: [WEB, DOCS] },
                { name: "archived", color: "#8a8a8a", members: [OLD] }, { name: "empty", color: "#fff", members: ["nobody"] }];
const st = (o: any = {}) => ({ raw: o, on: o.on !== false, collapsed: o.collapsed || [], expanded: o.expanded || [], timeline: o.timeline === true });

test("off: the rows are the visible lanes in their order and nothing else (the pane as before T399, row for row)", () => {
  const rows = V.tlRows(vis, unions, st(), false);
  assert.deepEqual(rows.map((r: any) => [r.kind, r.s && r.s.name]), vis.map((s) => ["lane", s.name]));
  assert.equal(V.tlRows([], unions, st(), true).length, 0, "no lanes, no rows: the empty-window line is the draw's, as before");
});

test("on: one section per tag in the user's tag order, a session under two tags in both, a tag holding no visible lane skipped, the untagged trail behind a divider", () => {
  const rows = V.tlRows(vis, unions, st(), true);
  assert.deepEqual(rows.map((r: any) => r.kind === "head" ? "head:" + r.name + (r.folded ? "(folded)" : "") + "=" + r.count : r.kind === "lane" ? r.s.name : r.kind),
    ["head:backend=2", "api", "web", "head:frontend=2", "web", "docs", "head:archived(folded)=1", "trail", "tests"],
    "web under both; archived folded by default keeps its head alone; empty has no visible member and no row; tests trails");
  const heads = rows.filter((r: any) => r.kind === "head");
  assert.deepEqual(heads.map((h: any) => h.color), ["#1EA1EB", "#e0a54a", "#8a8a8a"], "the head carries the tag's colour for its chip");
  // the folds are the strip's: a collapsed name folds, an expanded default-folded name opens
  const rows2 = V.tlRows(vis, unions, st({ collapsed: ["backend"], expanded: ["archived"] }), true);
  assert.deepEqual(rows2.map((r: any) => r.kind === "head" ? r.name + (r.folded ? "-" : "+") : r.kind === "lane" ? r.s.name : r.kind),
    ["backend-", "frontend+", "web", "docs", "archived+", "old-notes", "trail", "tests"]);
  // every visible session untagged: no heads, no divider, the lanes alone
  assert.deepEqual(V.tlRows(vis, [], st(), true).map((r: any) => r.kind), ["lane", "lane", "lane", "lane", "lane"]);
});

test("the fold and the switch are written in the strip's own shape, every other field carried through, and the same-window event fires", () => {
  store.clear(); events.length = 0;
  store.set("romp:tabgroups", JSON.stringify({ on: false, collapsed: ["qa"], expanded: [], pinned: [{ sid: WEB, name: "qa" }], followed: { g1: "qa" } }));
  assert.equal(V.tlGroupByTag(), false, "absent reads as off");
  V.setTlGroupByTag(true);
  let blob = JSON.parse(store.get("romp:tabgroups")!);
  assert.deepEqual(blob, { on: false, collapsed: ["qa"], expanded: [], pinned: [{ sid: WEB, name: "qa" }], followed: { g1: "qa" }, timeline: true }, "the switch is one field; nothing else moved");
  assert.equal(V.tlGroupByTag(), true);
  // the FOLDS are every device's since 2026-09-23 (tab-groups.ts TabFolds): written to the kernel's cached copy, the fold
  // fields the pre-move key carried left exactly as they were (read, never written: reverting hands them back)
  assert.deepEqual(JSON.parse(store.get("romp:tabgroups:shared")!), { collapsed: ["qa"], expanded: [], pinned: [{ sid: WEB, name: "qa" }], followed: { g1: "qa" } },
    "the switch's write carries the folds into the shared copy, unchanged");
  assert.equal(V.toggleSectionFold("backend"), true, "folded");
  blob = JSON.parse(store.get("romp:tabgroups")!);
  const shared = () => JSON.parse(store.get("romp:tabgroups:shared")!);
  assert.deepEqual([shared().collapsed, shared().expanded, shared().pinned, shared().followed, blob.on, blob.timeline], [["qa", "backend"], [], [{ sid: WEB, name: "qa" }], { g1: "qa" }, false, true]);
  assert.deepEqual(blob.collapsed, ["qa"], "the pre-move key's folds stand where they were");
  assert.equal(V.toggleSectionFold("archived"), false, "the default-folded tag opens…");
  assert.deepEqual([shared().collapsed, shared().expanded], [["qa", "backend"], ["archived"]], "…remembered under expanded, as tab-groups.ts setSectionCollapsed does");
  assert.equal(V.toggleSectionFold("archived"), true);
  assert.deepEqual(shared().expanded, [], "folding it again drops the memory");
  V.setTlGroupByTag(false);
  assert.equal("timeline" in JSON.parse(store.get("romp:tabgroups")!), false, "off drops the field: the blob as before T399");
  assert.ok(events.length >= 5 && events.every((e) => e === "romp-tabgroups"), "every write tells the window (tab-groups.ts TABGROUPS_EVENT)");
  // a corrupt or absent entry costs the preference, never the pane
  store.set("romp:tabgroups", "not json"); store.set("romp:tabgroups:shared", "not json either");
  assert.deepEqual([V.tlGroupByTag(), V.sectionFolded(V.tabGroupsState(), "archived"), V.sectionFolded(V.tabGroupsState(), "qa")], [false, true, false]);
  // and on a page with a federation manager the write is the one implementation on the window (federation.ts
  // __rompWriteTabGroups: tab-groups.ts writeTabGroups, which also publishes the folds to the kernel)
  const handed: any[] = [];
  g.__rompWriteTabGroups = (b: unknown) => handed.push(b);   // `window` is the global here
  try {
    store.clear();
    V.toggleSectionFold("backend");
  } finally {
    delete g.__rompWriteTabGroups;
  }
  assert.deepEqual(handed.map((b) => [b.collapsed, b.on]), [[["backend"], true]], "handed the whole blob, folded");
  assert.equal(store.size, 0, "and nothing written here: the one implementation does the writing");
});

test("drift pins: the key, the event, the default-folded set and the chip's numbers are tab-groups.ts's and tag-menu.ts's own", () => {
  assert.match(TABGROUPS, new RegExp('export const TABGROUPS_KEY = "' + V.TABGROUPS_KEY + '"'));
  // the folds' key and fields (2026-09-23): the view mirrors tab-groups.ts's split, so the kernel's copy is read first here too
  assert.match(TABGROUPS, /export const TABGROUPS_SHARED_KEY = "romp:tabgroups:shared";/);
  assert.match(VIEW_SRC, /const TABGROUPS_SHARED_KEY = 'romp:tabgroups:shared';/);
  assert.match(TABGROUPS, /export type TabFolds = Pick<TabGroupsState, "collapsed" \| "expanded" \| "pinned" \| "followed" \| "followedSeq">;/);
  assert.match(VIEW_SRC, /const TABGROUPS_FOLD_FIELDS = \['collapsed', 'expanded', 'pinned', 'followed', 'followedSeq'\];/);
  assert.match(TABGROUPS, /export const TABGROUPS_EVENT = "romp-tabgroups"/);
  const m = /DEFAULT_COLLAPSED: ReadonlySet<string> = new Set\(\[([^\]]*)\]\)/.exec(TABGROUPS);
  assert.ok(m, "tab-groups.ts declares DEFAULT_COLLAPSED as a literal set");
  assert.deepEqual(V.TABGROUPS_DEFAULT_COLLAPSED, Array.from(m![1].matchAll(/"([^"]+)"/g)).map((x) => x[1]));
  assert.match(TABGROUPS, /timeline\?: boolean;/, "the pane's switch is a field of the shared state");
  assert.match(TABGROUPS, /\.\.\.\(o\.timeline === true \? \{ timeline: true \} : \{\}\)/, "parsed only when true");
  assert.match(TABGROUPS, /if \(st\.timeline === true\) blob\.timeline = true;/, "carried through the strip's writes");
  // the SVG chip's geometry is the parse of TAG_CHIP_STYLE, which is tagChip's pill byte for byte up to the colour
  const chip = /"display:inline-flex;align-items:center;gap:5px;padding:(\d+)px (\d+)px;"\s*\+ "border-radius:(\d+)px;" \+ \(opts && opts\.inheritSize \? "" : "font-size:([\d.]+)em;"\)\s*\+ "border:(\d+)px solid "/.exec(TAGMENU);
  assert.ok(chip, "tag-menu.ts tagChip's pill, as written");
  assert.deepEqual(V.TAG_CHIP_GEOM, { padY: +chip![1], padX: +chip![2], radius: +chip![3], fontEm: +chip![4], border: +chip![5] });
  assert.deepEqual(V.TAG_CHIP_GEOM, { padY: 2, padX: 7, radius: 9, fontEm: 0.82, border: 1 });
});

test("the Filter menu carries a Group by tag row with the ✓ when on, and its click toggles the switch and repaints in place", () => {
  store.clear();
  const panel = new V.TimelinePanel(makeNode("div"));
  const rows = (menu: any) => menu.children.filter((c: any) => c.tag === "div" && c.children.some((k: any) => k.tag === "#text"));
  const labelOf = (row: any) => row.children.filter((k: any) => k.tag === "#text").map((k: any) => k.textContent).join("");
  const checked = (row: any) => row.children.some((k: any) => k.tag === "span" && k.textContent === "✓");
  panel._openViewsMenu(makeNode("button"));
  let menu = panel._viewsMenu;
  let row = rows(menu).find((r: any) => labelOf(r) === "Group by tag");
  assert.ok(row, "the row sits in the Filter menu, before Configure tags…");
  assert.equal(checked(row), false, "off by default");
  const labels = rows(menu).map(labelOf);
  assert.ok(labels.indexOf("Group by tag") < labels.indexOf("Configure tags…"), "beside the lens rows, above Configure tags…");
  row._listeners.click();
  assert.equal(V.tlGroupByTag(), true, "the click turns it on");
  menu = panel._viewsMenu;
  row = rows(menu).find((r: any) => labelOf(r) === "Group by tag");
  assert.ok(row && checked(row), "the menu repainted in place with the ✓ (a settings panel, not a command)");
  row._listeners.click();
  assert.equal(V.tlGroupByTag(), false);
});

test("a reveal for a session behind a FOLDED section pulses nowhere; a visible one pulses on its first lane's row", async () => {
  // the fold verifier's MEDIUM 1 (2026-09-13): the pulse fell back to the session's index in the ungrouped visible list
  // and drew the ring on another row (the backend head) for a session folded away under archived
  const panel = new V.TimelinePanel(makeNode("div"));
  panel.svg = makeNode("svg");
  panel._geom = { top: 8, ml: 130, plotW: 800, winSec: 3600, cT0: 0, compress: null };
  panel._vis = [S(API, "api"), S(WEB, "web"), S(TESTS, "tests"), S(DOCS, "docs"), S(OLD, "old-notes")];   // old-notes: behind the folded archived head
  panel._grouped = true;
  panel._rows = V.tlRows(panel._vis, unions, st(), true);
  panel._rowOf = Object.create(null); panel._rows.forEach((r: any, i: number) => { if (r.kind === "lane" && !(r.s.id in panel._rowOf)) panel._rowOf[r.s.id] = i; });
  panel._pulseFocus(OLD, 600, null);
  assert.equal(panel.svg.children.length, 0, "no visible lane, no ring: it used to land on the visible index's row");
  panel._pulseFocus(WEB, 600, null);
  const ring = panel.svg.children[0];
  assert.ok(ring && ring.tag === "circle", "a visible session pulses a ring");
  assert.equal(+ring.getAttribute("cy"), 8 + 2 * 26 + 13, "on web's FIRST lane, row 2 under backend");
});

test("the arrow walk steps the rows the pane shows: section order, copies included, heads skipped, never a hidden lane, no auto-open of one", async () => {
  // the fold verifier's MEDIUM 2: the walk stepped the ungrouped visible list, hidden lanes included, and auto-opened a
  // session folded away
  const panel = new V.TimelinePanel(makeNode("div"));
  const opened: string[] = [];
  panel.openChat = (tid: string) => { opened.push(tid); };
  panel.draw = () => {};
  panel._vis = [S(API, "api"), S(WEB, "web"), S(TESTS, "tests"), S(DOCS, "docs"), S(OLD, "old-notes")];
  panel._grouped = true;
  panel._rows = V.tlRows(panel._vis, unions, st(), true);   // head, api, web, head, web, docs, head(archived folded), trail, tests (a section's lanes keep the visible order)
  panel.selectedSid = null;
  const down: string[] = [];
  for (let k = 0; k < 7; k++) { panel.moveSelection(1); down.push(panel.selectedSid); }
  assert.deepEqual(down.map((id) => id.slice(-1)), [API, WEB, WEB, DOCS, TESTS, TESTS, TESTS].map((id) => id.slice(-1)),
    "down: api, web (backend), web (its frontend copy, the next row), docs, tests (the trail), then it stays; old-notes is never reached");
  panel.selectedSid = null;
  const up: string[] = [];
  for (let k = 0; k < 6; k++) { panel.moveSelection(-1); up.push(panel.selectedSid); }
  assert.deepEqual(up.map((id) => id.slice(-1)), [TESTS, DOCS, WEB, WEB, API, API].map((id) => id.slice(-1)),
    "up from nothing lands on the LAST visible lane and walks back over the copies");
  await new Promise((r) => setTimeout(r, 250));                                          // the auto-open debounce (120 ms)
  assert.ok(!opened.includes(OLD), "a hidden session is never auto-opened: " + JSON.stringify(opened));
  assert.equal(opened[opened.length - 1], API, "the last landing is what opens");
  // ungrouped: the walk is the visible list, as before
  panel._grouped = false; panel._rows = V.tlRows(panel._vis, [], st(), false); panel.selectedSid = null;
  const flat: string[] = [];
  for (let k = 0; k < 5; k++) { panel.moveSelection(1); flat.push(panel.selectedSid); }
  assert.deepEqual(flat, panel._vis.map((s: any) => s.id));
});

// the round-two fixture: the frontend section lists docs BEFORE web, so web's two copies are rows 2 and 5 with docs between
const VIS2 = [S(API, "api"), S(DOCS, "docs"), S(WEB, "web"), S(TESTS, "tests"), S(OLD, "old-notes")];
function grouped(panel: any) {
  panel._vis = VIS2; panel._grouped = true; panel._rows = V.tlRows(VIS2, unions, st(), true);   // head, api(1), web(2), head, docs(4), web(5), head, trail, tests(8)
  panel._rowOf = Object.create(null); panel._rows.forEach((r: any, i: number) => { if (r.kind === "lane" && !(r.s.id in panel._rowOf)) panel._rowOf[r.s.id] = i; });
  panel.draw = () => {};
}

test("a click hands its row to the selection, a click on the selected session's other copy too, and the walk resumes from that row", () => {
  // the round-two MEDIUM: a click carried no row, so the walk resumed from the session's FIRST copy: a click on web's frontend
  // copy (row 5) then ArrowDown landed on docs (row 4), one row ABOVE the row just clicked
  const panel = new V.TimelinePanel(makeNode("div"));
  grouped(panel);
  panel._select(WEB, 5);
  assert.equal(panel._selRow, 5, "the clicked row is the cursor");
  panel.moveSelection(1);
  assert.deepEqual([panel.selectedSid, panel._selRow], [TESTS, 8], "down from the clicked copy: the next row below it, tests");
  panel._select(WEB, 2);
  panel._select(WEB, 5);                                   // the selected session again, its other copy: the row moves all the same
  assert.equal(panel._selRow, 5, "a click on a copy of the already-selected session resets the row");
  panel.moveSelection(-1);
  assert.deepEqual([panel.selectedSid, panel._selRow], [DOCS, 4], "up from the clicked copy: docs above it");
  panel._select(API);                                        // a selection carrying no row (the chat's active tab): the first lane
  assert.equal(panel._selRow, null);
  panel.moveSelection(1);
  assert.equal(panel.selectedSid, WEB);
});

test("the selection band paints the cursor's row only when the selected session has copies; one lane, or ungrouped, as before", () => {
  // the round-two LOW 1: every copy wore the band, so the row cursor was invisible between two copies
  const rows = V.tlRows(VIS2, unions, st(), true);
  assert.deepEqual(V.selBandRows(rows, WEB, 5, true), [5], "the cursor on the frontend copy");
  assert.deepEqual(V.selBandRows(rows, WEB, 2, true), [2]);
  assert.deepEqual(V.selBandRows(rows, WEB, null, true), [2], "no row known (the chat's active tab): the first lane");
  assert.deepEqual(V.selBandRows(rows, WEB, 4, true), [2], "a stale row that is not this session's lane: the first lane");
  assert.deepEqual(V.selBandRows(rows, DOCS, null, true), [4], "one lane: its row");
  assert.deepEqual(V.selBandRows(rows, OLD, null, true), [], "folded away: no band anywhere");
  const flat = V.tlRows(VIS2, [], st(), false);
  assert.deepEqual(V.selBandRows(flat, WEB, null, false), [2], "ungrouped: the one lane, as before");
});

test("a focus on a session folded away unfolds its first lane's section through the shared key; Enter and the debounced open never act on a hidden session", async () => {
  // the round-two LOW 2, the ruling: the user asked for THAT session, so its section opens (the strip follows through the
  // shared blob) and the pan and pulse land on the lane; the walk, Enter and the open resolve from the drawn rows, not _vis
  store.clear();
  store.set("romp:tabgroups", JSON.stringify({ on: true, collapsed: [], expanded: [], pinned: [], timeline: true }));
  const panel = new V.TimelinePanel(makeNode("div"));
  grouped(panel);
  panel._curViews = () => ({ active: "all", tagOrder: ["backend", "frontend", "archived"], tags: unions.map((u, k) => ({ id: "t" + k, name: u.name, color: u.color, members: u.members })) });
  assert.equal(panel._unfoldFor(WEB), null, "a visible session unfolds nothing");
  assert.equal(panel._unfoldFor(OLD), "archived", "old-notes' first lane sits under archived, folded by default: it opens");
  assert.deepEqual(JSON.parse(store.get("romp:tabgroups:shared")!).expanded, ["archived"], "written to the shared key, so the strip follows");
  const opened: string[] = [];
  panel.openChat = (tid: string) => { opened.push(tid); };
  panel.selectedSid = OLD;                                   // hidden (the rows above still have archived folded)
  panel.openSelected(true); panel.composeSelected();
  assert.deepEqual(opened, [], "no open, no compose, for a session with no drawn lane");
  panel.selectedSid = WEB;
  panel.openSelected(true);
  assert.deepEqual(opened, [WEB]);
});

test("the unfold reaches only a session the pane would draw: one the lens or the active filter removed stays folded (the round-three low)", () => {
  // a focus at a lens-filtered session unfolded its section in the shared blob (the strip's group sprang open) while the pane
  // drew nothing: the unfold asked only whether the session had a drawn row, never why
  store.clear();
  store.set("romp:tabgroups", JSON.stringify({ on: true, collapsed: [], expanded: [], pinned: [], timeline: true }));
  const panel = new V.TimelinePanel(makeNode("div"));
  grouped(panel);
  panel._curViews = () => ({ active: "all", tagOrder: ["backend", "frontend", "archived"], tags: unions.map((u, k) => ({ id: "t" + k, name: u.name, color: u.color, members: u.members })) });
  panel._vis = VIS2.filter((s) => s.id !== OLD);            // the lens removed old-notes: it is not in the visible set
  panel._rows = V.tlRows(panel._vis, unions, st(), true);
  panel._rowOf = Object.create(null); panel._rows.forEach((r: any, i: number) => { if (r.kind === "lane" && !(r.s.id in panel._rowOf)) panel._rowOf[r.s.id] = i; });
  assert.equal(panel._unfoldFor(OLD), null, "not in the visible set: nothing unfolds");
  assert.equal(store.get("romp:tabgroups:shared"), undefined, "and the shared blob is untouched");
  panel._vis = VIS2;                                        // visible but folded: unfolds, as before
  assert.equal(panel._unfoldFor(OLD), "archived");
});

test("a focus at a session whose other copy the user clicked pulses that copy, the band's row", () => {
  // the round-three cosmetic: the pulse landed on the first lane while the band stayed on the clicked copy
  const panel = new V.TimelinePanel(makeNode("div"));
  grouped(panel);
  panel.svg = makeNode("svg");
  panel._geom = { top: 8, ml: 130, plotW: 800, winSec: 3600, cT0: 0, compress: null };
  panel._select(WEB, 5);                                    // the frontend copy, row 5
  panel._pulseFocus(WEB, 600, null);
  const ring = panel.svg.children[0];
  assert.ok(ring && ring.tag === "circle");
  assert.equal(+ring.getAttribute("cy"), 8 + 5 * 26 + 13, "the ring on the clicked copy's row, where the band is");
  panel._select(API);                                       // no row known: web's first lane, as before
  panel.svg = makeNode("svg");
  panel._pulseFocus(WEB, 600, null);
  assert.equal(+panel.svg.children[0].getAttribute("cy"), 8 + 2 * 26 + 13);
});

test("source pins: a click on a message stub aimed at a folded-away recipient unfolds through _unfoldFor before it selects (the round-three low)", () => {
  const src = fs.readFileSync(viewPath, "utf8");
  assert.match(src, /const msgNav = \(mm\) => \(\) => \{ const an = this\.nearestTurnAnchor\(mm\.toId, execAt\(mm\)\); if \(this\._unfoldFor\(mm\.toId\) != null\) this\.draw\(\); this\._select\(mm\.toId, this\._rowOf\[mm\.toId\]\);/,
               "the message handler unfolds the recipient's section, redraws, and selects the row the redraw gave it");
});

// a panel whose draw() is a stand-in: it recomputes the visible set, the rows and the row index from the store's fold state,
// the way the real draw does after the lens and the active filter; `windowHas` says which sessions the pane's window holds
function drawingPanel(windowHas: () => string[]) {
  const panel = new V.TimelinePanel(makeNode("div"));
  panel._curViews = () => ({ active: "all", tagOrder: ["backend", "frontend", "archived"], tags: unions.map((u, k) => ({ id: "t" + k, name: u.name, color: u.color, members: u.members })) });
  panel.svg = makeNode("svg");
  panel._geom = { top: 8, ml: 130, plotW: 800, winSec: 3600, cT0: 0, compress: null };
  panel._grouped = true;
  panel.draws = 0;
  panel.draw = () => {
    panel.draws++;
    panel._vis = VIS2.filter((s) => windowHas().indexOf(s.id) >= 0);
    panel._rows = V.tlRows(panel._vis, unions, V.tabGroupsState(), true);
    panel._rowOf = Object.create(null); panel._rows.forEach((r: any, i: number) => { if (r.kind === "lane" && !(r.s.id in panel._rowOf)) panel._rowOf[r.s.id] = i; });
  };
  panel.draw();
  return panel;
}

test("a reveal at a session whose work sits outside the window pans FIRST, then unfolds against the set the panned draw shows (the round-four medium)", () => {
  // with the active-sessions filter on, the window at thirty minutes and an archived session's work hours back, the unfold
  // used to test the PRE-pan visible set (the session absent), refuse, and only then pan: at the redraw the session was
  // visible but its section stayed folded, no lane, no band, no pulse, the chat opened against a collapsed head
  store.clear();
  store.set("romp:tabgroups", JSON.stringify({ on: true, collapsed: [], expanded: [], pinned: [], timeline: true }));
  let panned = false;
  const panel = drawingPanel(() => panned ? [API, DOCS, WEB, TESTS, OLD] : [API, DOCS, WEB, TESTS]);   // old-notes enters the window only after the pan
  panel.data = { sessions: VIS2 };
  panel._panToTime = () => { panned = true; return true; };
  panel._laneForFocusSid = (sid: string) => sid;
  panel.revealEvent(OLD, 600, null);
  assert.deepEqual(JSON.parse(store.get("romp:tabgroups:shared")!).expanded, ["archived"], "archived unfolded, through the shared blob");
  assert.ok(OLD in panel._rowOf, "old-notes has its lane after the redraw");
  const ring = panel.svg.children.find((c: any) => c.tag === "circle");
  assert.ok(ring, "and the pulse landed");
  assert.equal(+ring.getAttribute("cy"), 8 + panel._rowOf[OLD] * 26 + 13, "on its row");
  assert.ok(panel.draws >= 3, "the panned draw, then the draw after the unfold");
  // a session the lens would still exclude after the pan keeps refusing
  store.set("romp:tabgroups", JSON.stringify({ on: true, collapsed: [], expanded: [], pinned: [], timeline: true }));
  store.delete("romp:tabgroups:shared");   // the folds back to the defaults too (archived folded)
  panned = false;
  const panel2 = drawingPanel(() => [API, DOCS, WEB, TESTS]);   // old-notes never in the visible set (the lens removed it)
  panel2.data = { sessions: VIS2 }; panel2._panToTime = () => { panned = true; return true; }; panel2._laneForFocusSid = (sid: string) => sid;
  panel2.revealEvent(OLD, 600, null);
  assert.equal(store.get("romp:tabgroups:shared"), undefined, "nothing unfolds for a session the pane will not draw");
  assert.equal(panel2.svg.children.length, 0, "and nothing pulses");
});

test("a message stub's click on a folded-away recipient: the unfold, the redraw, the row select, driven against the store (the round-four low)", () => {
  store.clear();
  store.set("romp:tabgroups", JSON.stringify({ on: true, collapsed: [], expanded: [], pinned: [], timeline: true }));
  const panel = drawingPanel(() => [API, DOCS, WEB, TESTS, OLD]);
  assert.equal(OLD in panel._rowOf, false, "old-notes is folded away under archived");
  // the handler's three steps, as msgNav runs them
  const opened = panel._unfoldFor(OLD);
  assert.equal(opened, "archived");
  if (opened != null) panel.draw();
  assert.ok(OLD in panel._rowOf, "the redraw gave it a lane");
  panel._select(OLD, panel._rowOf[OLD]);
  assert.deepEqual([panel.selectedSid, panel._selRow], [OLD, panel._rowOf[OLD]], "the selection sits on the redrawn row");
  assert.deepEqual(V.selBandRows(panel._rows, OLD, panel._selRow, true), [panel._rowOf[OLD]], "the band on that row");
  // a visible recipient: no unfold, the select as before
  assert.equal(panel._unfoldFor(WEB), null);
});

test("source pins: the draw pass lays rows out through tlRows, the focus pulse and the drag read the row model", () => {
  const src = fs.readFileSync(viewPath, "utf8");
  assert.match(src, /const rows = tlRows\(vis, grouped \? viewTagUnion\(this\._curViews\(\)\) : \[\], tabGroupsState\(\), grouped\);/);
  assert.match(src, /this\._rows = rows; this\._rowOf = vidx; this\._grouped = grouped;/);
  assert.match(src, /const i = onCursor \? cur : \(sid in rowOf\) \? rowOf\[sid\] : \(this\._grouped \? -1 : \(this\._vis \|\| \[\]\)\.findIndex\(\(s\) => s\.id === sid\)\);/, "the pulse lands on the cursor's row when it is this session's, else the first lane, nowhere for a folded-away session");
  assert.match(src, /if \(this\._grouped && this\._rows\) this\._rows\.forEach\(\(r, i\) => \{ if \(r\.kind === 'lane'\) walk\.push\(\{ s: r\.s, i \}\); \}\);/, "the arrow walk steps the rows shown, its position a row index");
  assert.match(src, /this\._mc\.font = '400 ' \+ fs \+ 'px ' \+ this\._fontFace\(\);/, "the chip's name is measured at the drawn weight");
  assert.match(src, /if \(d\.mode === 'row' && d\.noReorder\) \{ this\._drag = null; return; \}/, "grouped lanes follow the tag order: a vertical drag is a click");
  assert.equal((src.match(/    vis\.forEach\(\(s, i\) => \{\n/g) || []).length, 0, "no lane pass indexes the visible list by position any more");
  assert.equal((src.match(/this\._select\(s\.id\)/g) || []).length, 0, "every click hands the selection its row (round two)");
  assert.ok((src.match(/this\._select\(s\.id, i\)/g) || []).length >= 9, "the lane passes pass the row index");
  assert.match(src, /if \(this\.selectedSid === s\.id && selBand\.has\(i\)\) \{/, "the band paints the cursor's row only");
  assert.match(src, /this\._panToTime\(t\);[^\n]*\n\s+if \(sid\) this\.selectedSid = sid;\n\s+this\.draw\(\);[^\n]*\n(\s+\/\/[^\n]*\n)*\s+if \(sid && this\._unfoldFor\(sid\) != null\) this\.draw\(\);\n\s+this\._pulseFocus\(sid, t,/, "focusEvent pans and draws, then unfolds against that draw's visible set and draws again, before the pulse");
  assert.match(src, /this\._panToTime\(tt\);\n\s+if \(lane\) this\.selectedSid = lane;\n\s+this\.draw\(\);[^\n]*\n\s+if \(lane && this\._unfoldFor\(lane\) != null\) this\.draw\(\);/, "revealEvent the same");
  assert.match(src, /openSelected\(preserveFocus\) \{\s*\n\s*const s = this\._selectedLane\(\);/, "the debounced open reads the drawn rows");
  assert.match(src, /composeSelected\(\) \{\s*\n\s*const s = this\._selectedLane\(\);/, "Enter reads the drawn rows");
  assert.match(src, /window\.addEventListener\('storage', \(e\) => \{ if \(e && e\.key === TABGROUPS_KEY\) this\.draw\(\); \}\);/, "a fold or the switch in another window repaints (its own listener: the tab lock's pins on the settings listener stand)");
  // …and so does a fold that reached this browser from another DEVICE (2026-09-23): cached by another pane (the storage event on
  // the shared key), or adopted by this page's own federation manager off the kernel's push (the same-window event)
  assert.match(src, /window\.addEventListener\('storage', \(e\) => \{ if \(e && e\.key === TABGROUPS_SHARED_KEY\) this\.draw\(\); \}\);/);
  assert.match(src, /window\.addEventListener\(TABGROUPS_EVENT, \(\) => this\.draw\(\)\);/);
});
