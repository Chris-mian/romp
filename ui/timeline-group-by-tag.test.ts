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
  assert.equal(V.toggleSectionFold("backend"), true, "folded");
  blob = JSON.parse(store.get("romp:tabgroups")!);
  assert.deepEqual([blob.collapsed, blob.expanded, blob.pinned, blob.followed, blob.on, blob.timeline], [["qa", "backend"], [], [{ sid: WEB, name: "qa" }], { g1: "qa" }, false, true]);
  assert.equal(V.toggleSectionFold("archived"), false, "the default-folded tag opens…");
  blob = JSON.parse(store.get("romp:tabgroups")!);
  assert.deepEqual([blob.collapsed, blob.expanded], [["qa", "backend"], ["archived"]], "…remembered under expanded, as tab-groups.ts setSectionCollapsed does");
  assert.equal(V.toggleSectionFold("archived"), true);
  assert.deepEqual(JSON.parse(store.get("romp:tabgroups")!).expanded, [], "folding it again drops the memory");
  V.setTlGroupByTag(false);
  assert.equal("timeline" in JSON.parse(store.get("romp:tabgroups")!), false, "off drops the field: the blob as before T399");
  assert.ok(events.length >= 5 && events.every((e) => e === "romp-tabgroups"), "every write tells the window (tab-groups.ts TABGROUPS_EVENT)");
  // a corrupt or absent entry costs the preference, never the pane
  store.set("romp:tabgroups", "not json");
  assert.deepEqual([V.tlGroupByTag(), V.sectionFolded(V.tabGroupsState(), "archived"), V.sectionFolded(V.tabGroupsState(), "qa")], [false, true, false]);
});

test("drift pins: the key, the event, the default-folded set and the chip's numbers are tab-groups.ts's and tag-menu.ts's own", () => {
  assert.match(TABGROUPS, new RegExp('export const TABGROUPS_KEY = "' + V.TABGROUPS_KEY + '"'));
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

test("source pins: the draw pass lays rows out through tlRows, the focus pulse and the drag read the row model", () => {
  const src = fs.readFileSync(viewPath, "utf8");
  assert.match(src, /const rows = tlRows\(vis, grouped \? viewTagUnion\(this\._curViews\(\)\) : \[\], tabGroupsState\(\), grouped\);/);
  assert.match(src, /this\._rows = rows; this\._rowOf = vidx; this\._grouped = grouped;/);
  assert.match(src, /const i = \(sid in rowOf\) \? rowOf\[sid\] : \(this\._vis \|\| \[\]\)\.findIndex\(\(s\) => s\.id === sid\);/, "the pulse lands on the first lane row");
  assert.match(src, /if \(d\.mode === 'row' && d\.noReorder\) \{ this\._drag = null; return; \}/, "grouped lanes follow the tag order: a vertical drag is a click");
  assert.equal((src.match(/    vis\.forEach\(\(s, i\) => \{\n/g) || []).length, 0, "no lane pass indexes the visible list by position any more");
  assert.match(src, /window\.addEventListener\('storage', \(e\) => \{ if \(e && e\.key === TABGROUPS_KEY\) this\.draw\(\); \}\);/, "a fold or the switch in another window repaints (its own listener: the tab lock's pins on the settings listener stand)");
});
