// THE TIMELINE'S VIEWS MENU RENDERS EACH TAG AS ITS CHIP ACTING AS A TOGGLE (T283b, the user 2026-09-09: menus wear
// one vocabulary): the shared tag-lens menu (ui/webview/tag-menu.ts, T283) made each union tag the tag chip itself,
// selected = full colour, unselected = faded at 0.45 with its colour kept, one tag per line with the chip at the left, All
// and (no tags) keeping the ✓ row grammar; since T413 (the user 2026-09-14) the ROW is the control, the house switch
// (menuitemcheckbox, aria-checked) with a two-state mark at its right (the ✓ when selected, an empty ring when not). This pane inlines its own copy of that
// menu (it may live in Obsidian's document and loads no module), so the copy mirrors the chips with the RESOLVED
// palette values it already carries. Executed over the house three-helper host (the tagbtn-click harness), plus
// drift pins between the two menus' chip and row shapes. Synthetic sessions and tags only.
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
    closest() { return null; },
    focus() { n._focused = true; if (n._listeners.focus) n._listeners.focus({}); },   // the strip tidy: a row's focus listener roves the tab stop
    click() { if (n._listeners.click) n._listeners.click({ stopPropagation() {}, preventDefault() {} }); },
    createEl(t: string, o: any) { const e = makeNode(t); if (o && o.cls) e.classList.add(o.cls); if (o && o.text) e.textContent = o.text; this.appendChild(e); return e; },
    createDiv(o: any) { return this.createEl("div", o); }, createSpan(o: any) { return this.createEl("span", o); },
  };
  return n;
}
const g: any = global;
g.document = {
  createElement(t: string) { return t === "canvas" ? { getContext() { return { font: "", measureText(s: string) { return { width: (s ? s.length : 0) * 6 }; } }; } } : makeNode(t); },
  createElementNS(_n: any, t: string) { return makeNode(t); },
  createTextNode(text: string) { const n = makeNode("#text"); n.textContent = text; return n; },
  body: makeNode("body"), documentElement: makeNode("html"), head: makeNode("head"),
  getElementById() { return null; }, addEventListener() {}, removeEventListener() {},
};
g.localStorage = { getItem() { return null; }, setItem() {}, removeItem() {} };
g.getComputedStyle = () => ({ backgroundColor: "rgb(30,30,30)" });
g.requestAnimationFrame = () => 0;
g.addEventListener = () => {}; g.removeEventListener = () => {};
g.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
g.window = g; g.innerWidth = 1400; g.innerHeight = 800;

const viewPath = path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js");
const { TimelinePanel } = createRequire(__filename)(viewPath);
const SRC = fs.readFileSync(viewPath, "utf8");
const MENU = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "tag-menu.ts"), "utf8");

const TAGS: any[] = [{ id: "g1", name: "infra", color: "#DD42FF", members: ["s2"] }, { id: "g2", name: "qa", color: "#3355aa", members: ["s1"] }];
function panelWith(lens: any): any {
  const now = 1_781_000_000;
  const sess = (id: string, name: string, color: string) => ({ id, name, color, state: "working", live: true, model: "Opus", effort: "high",
    context: 40, since: now - 60, awaiting: [], compacting: [], pendingMail: 0, compactions: [], faded: false, stale: false });
  const panel = new TimelinePanel(makeNode("div"));
  panel.update({ now, sessions: [sess("s1", "web", "#f7768e"), sess("s2", "api", "#7aa2f7")],
    turns: { s1: [{ id: "t1", start: now - 400, end: now - 100, prompt: "do the thing", mids: [] }] }, messages: [], judging: {},
    views: { active: "all", tags: TAGS, actives: { timeline: lens } } });
  return panel;
}
const openMenu = (panel: any) => { panel._openViewsMenu(makeNode("button")); return panel._viewsMenu; };
const rows = (menu: any) => menu.children.filter((c: any) => c.tag === "div");
const text = (n: any): string => (n.tag === "#text" ? n.textContent : (n.textContent || "")) + (n.children || []).map(text).join("");
const chipOf = (row: any) => (row.children || []).find((c: any) => c.tag === "span" && /border:1px solid/.test(c._attrs.style || "") && !("data-check" in c._attrs));
const markOf = (row: any) => (row.children || []).find((c: any) => c.tag === "span" && "data-check" in c._attrs);
const hasCheck = (row: any) => (row.children || []).some((c: any) => c.tag === "span" && c.textContent === "✓");

test("executed: each tag row is the house switch (menuitemcheckbox, aria-checked, the ✓ or ring mark), its chip full colour when selected and faded with its colour kept when not", () => {
  const panel = panelWith({ tags: ["infra"] });
  const menu = openMenu(panel);
  const r = rows(menu);
  assert.equal(text(r[0]), "All"); assert.equal(text(r[1]), "(no tags)");
  const infra = chipOf(r[2]), qa = chipOf(r[3]);
  assert.ok(infra && qa, "the two tags render as chips, one per row, after All and (no tags)");
  assert.equal(infra.textContent, "infra"); assert.equal(qa.textContent, "qa");
  assert.equal(r[2]._attrs.role, "menuitemcheckbox"); assert.equal(r[2]._attrs["aria-checked"], "true", "the row is the checkbox and reads selected");
  assert.equal(r[3]._attrs.role, "menuitemcheckbox"); assert.equal(r[3]._attrs["aria-checked"], "false");
  assert.equal(infra._attrs["aria-pressed"], undefined, "the chip carries no control role of its own: the row does"); assert.equal(infra._attrs.role, undefined);
  assert.doesNotMatch(infra._attrs.style, /opacity/, "a selected chip stands at full opacity");
  assert.equal(infra.classList.contains("tag-chip-off"), false);
  assert.match(infra._attrs.style, /border:1px solid #DD42FF;color:#DD42FF;/, "the chip keeps the tag's own colour");
  assert.equal(qa.classList.contains("tag-chip-off"), true, "an unselected chip wears the faded class");
  assert.match(qa._attrs.style, /opacity:0\.45;/, "…and paints the same fade inline: this host loads no sheet");
  assert.match(qa._attrs.style, /border:1px solid #3355aa;color:#3355aa;/, "faded, not recoloured");
  const on = markOf(r[2]), off = markOf(r[3]);
  assert.ok(on && off, "each tag row carries the mark");
  assert.equal(on._attrs["data-check"], "true"); assert.equal(on.textContent, "✓", "selected: the ✓-in-circle (the palette's check)");
  assert.equal(off._attrs["data-check"], "false"); assert.equal(off.textContent, "", "unselected: an empty ring");
  assert.match(off._attrs.style, /border-radius:50%;box-sizing:border-box;border:1px solid #9aa0a6;/, "the ring in the palette's muted text (round two: the hairline read at 1.5 to 1 against the menu ground; this clears 3)");
  assert.match(r[2]._attrs.style, /^padding:3px 22px 3px 8px;border-radius:4px;cursor:pointer;white-space:nowrap;display:flex;align-items:center;position:relative;outline:none;$/, "the chip row's shape, room for the mark, the focus ring the hover wash");
  panel._closeViewsMenu();
});

test("executed: All and (no tags) keep the row grammar with the ✓; an uncoloured tag falls back to the palette's muted text", () => {
  const panel = panelWith({ none: true, tags: ["infra"] });
  panel.update(Object.assign({}, panel.data, { views: { active: "all", tags: TAGS.concat([{ id: "g3", name: "plain", color: null, members: [] }]),
    actives: { timeline: { none: true, tags: ["infra"] } } } }));
  const menu = openMenu(panel);
  const r = rows(menu);
  assert.equal(hasCheck(r[1]), true, "(no tags) selected → its ✓");
  assert.equal(hasCheck(r[0]), false, "All not selected → no ✓");
  const plain = chipOf(r[4]);
  assert.ok(plain, "the uncoloured tag is a chip too");
  assert.match(plain._attrs.style, /border:1px solid #9aa0a6;color:#9aa0a6;/, "the dark palette's muted text, resolved (no var() in this host)");
  panel._closeViewsMenu();
});

test("executed: clicking a chip's row toggles that tag, the menu stays open and repaints in place", () => {
  const panel = panelWith({ tags: ["infra"] });
  const applied: any[] = [];
  panel._setLens = (blob: any) => { applied.push(blob); panel.data.views.actives = blob.actives; };
  const menu = openMenu(panel);
  const before = rows(menu).length;
  rows(menu)[3]._listeners.click();          // qa: off → on
  assert.deepEqual(applied[0].actives.timeline.tags, ["infra", "qa"]); assert.ok(!applied[0].actives.timeline.none);
  assert.equal(panel._viewsMenu, menu, "the menu stayed open");
  assert.equal(rows(menu).length, before, "repainted in place: the same rows");
  assert.equal(rows(menu)[3]._attrs["aria-checked"], "true", "the row now reads selected"); assert.equal(markOf(rows(menu)[3]).textContent, "✓");
  assert.equal(chipOf(rows(menu)[3]).classList.contains("tag-chip-off"), false);
  rows(menu)[2]._listeners.click();          // infra: on → off
  assert.equal(rows(menu)[2]._attrs["aria-checked"], "false"); assert.equal(markOf(rows(menu)[2]).textContent, "");
  assert.equal(chipOf(rows(menu)[2]).classList.contains("tag-chip-off"), true);
  panel._closeViewsMenu();
});

// ROUND TWO of T413 (the manager's read of 2026-09-14): the shared menu took the house rows menu's keyboard grammar, and so does
// this copy: role menu; rows that take focus (tabindex 0) and keys (Enter and Space press, ArrowDown and ArrowUp walk, Home and
// End jump), the first row focused on open; Escape closes and hands the focus back to the button.
test("executed: the inlined menu takes the house rows menu's keyboard grammar: role menu, ONE tab stop that roves with the focus, rows with keys, a pointer open leaving the focus alone, Escape back to the button", () => {
  const panel = panelWith({ tags: ["infra"] });
  const anchor = makeNode("button"); let refocused = 0; anchor.focus = () => { refocused++; };
  let focusedRow: any = null;
  panel._openViewsMenu(anchor); const menu = panel._viewsMenu;   // a POINTER open: the stub document's activeElement is not the anchor
  assert.equal(menu._attrs.role, "menu", "the menu's role");
  const r = rows(menu).filter((x: any) => x._attrs.role);
  assert.deepEqual(r.map(text).map((t: string) => t.replace("✓", "")), ["All", "(no tags)", "infra", "qa", "Group by tag", "Configure tags…"]);
  for (const x of r) {
    assert.equal(x.tabIndex, x === r[0] ? 0 : -1, text(x) + ": one tab stop (the first row), the rest reached by the arrows, so Tab leaves the menu");
    assert.ok(x._listeners.keydown, text(x) + ": and the keys");
    assert.match(x._attrs.style, /outline:none;/, text(x) + ": the focus ring is the hover wash");
  }
  assert.ok(!r[0]._focused, "a pointer open leaves the focus where it was: the first row is the stop but not focused");
  for (const x of r) { const own = x.focus; x.focus = () => { own.call(x); focusedRow = x; }; }
  assert.ok(menu._listeners.keydown, "the menu's own handler: Escape and the walk");
  const key = (k: string) => ({ key: k, target: null as any, prevented: false, stopped: false, preventDefault() { this.prevented = true; }, stopPropagation() { this.stopped = true; } });
  // the walk: from the first row, ArrowDown lands on the second (the menu's handler reads the focused row from the event's target)
  const d = key("ArrowDown"); d.target = r[0]; menu._listeners.keydown(d);
  assert.equal(focusedRow, r[1], "ArrowDown moves to the next row"); assert.ok(d.prevented);
  assert.deepEqual(r.map((x: any) => x.tabIndex), [-1, 0, -1, -1, -1, -1], "the tab stop moved with the focus");
  const e = key("End"); e.target = r[1]; menu._listeners.keydown(e); assert.equal(focusedRow, r[5], "End jumps to the last");
  const u = key("ArrowDown"); u.target = r[5]; menu._listeners.keydown(u); assert.equal(focusedRow, r[5], "the end holds");
  // Space on the qa row toggles it, the menu staying
  const applied: any[] = []; panel._setLens = (blob: any) => { applied.push(blob); panel.data.views.actives = blob.actives; };
  const sp = key(" "); r[3]._listeners.keydown(sp);
  assert.deepEqual(applied[0].actives.timeline.tags, ["infra", "qa"], "Space pressed the row"); assert.ok(sp.prevented && sp.stopped);
  assert.equal(panel._viewsMenu, menu, "the menu stayed open");
  const esc = key("Escape"); esc.target = r[3]; menu._listeners.keydown(esc);
  assert.equal(panel._viewsMenu, null, "Escape closed it"); assert.equal(refocused, 1, "and handed the focus back to the button"); assert.ok(esc.stopped);
});

test("executed: a keyboard open (the button holds the focus) puts the focus on the first row; the Group by tag switch is a checkbox row", () => {
  const panel = panelWith({ tags: ["infra"] });
  const anchor = makeNode("button");
  (g.document as any).activeElement = anchor;   // the button had the focus: a keyboard open
  try {
    panel._openViewsMenu(anchor); const menu = panel._viewsMenu;
    const r = rows(menu).filter((x: any) => x._attrs.role);
    assert.ok(r[0]._focused, "the first row took the focus"); assert.equal(r[0].tabIndex, 0);
    assert.equal(r[4]._attrs.role, "menuitemcheckbox", "Group by tag: a switch row"); assert.equal(r[4]._attrs["aria-checked"], "false");
    panel._closeViewsMenu();
  } finally { delete (g.document as any).activeElement; }
});

test("drift pins: the two-state mark is one drawing in both copies: the shared checkMark's geometry byte for byte, the check from the check token or the palette's accent, the ring from the muted text token or the palette's muted text", () => {
  const mark = MENU.slice(MENU.indexOf("function checkMark("), MENU.indexOf("\n}\n", MENU.indexOf("function checkMark(")));
  const geo = "position:absolute;right:6px;top:50%;transform:translateY(-50%);width:13px;height:13px;border-radius:50%;box-sizing:border-box;";
  assert.ok(mark.includes('"' + geo + '"'), "the shared mark's geometry is where the pin expects it");
  assert.ok(mark.includes('"display:inline-flex;align-items:center;justify-content:center;line-height:1;font-size:9px;font-weight:900;"'), "the shared mark's glyph box");
  assert.match(mark, /background:var\(--check-bg, #1EA1EB\);color:#fff;/, "on: the check token"); assert.match(mark, /border:1px solid var\(--text-muted, #9aa0a6\);background:transparent;/, "off: the muted text token");
  const ring = /const menuRingStyleFor = \(p\) => '([^']+)'\s*\n\s*\+ 'border:1px solid ' \+ p\.modelFg \+ ';background:transparent;';/.exec(SRC);
  assert.ok(ring, "the view's ring maker is where the pin expects it");
  assert.equal(ring![1], geo, "the ring: the shared geometry byte for byte, the palette's muted text (modelFg) standing for --text-muted");
  const check = /const menuCheckStyleFor = \(p\) => 'position:absolute;right:6px;top:50%;transform:translateY\(-50%\);'\s*\n\s*\+ 'background:' \+ p\.accentSolid \+ ';color:#fff;border-radius:50%;width:13px;height:13px;font-size:9px;'\s*\n\s*\+ 'font-weight:900;display:inline-flex;align-items:center;justify-content:center;line-height:1;';/.exec(SRC);
  assert.ok(check, "the view's check maker: the same 13px round box, 9px at weight 900, centred, the palette's accent standing for --check-bg");
});

test("drift pins: the inlined chip is the shared tagChip's pill up to the colour, and the fade and row shape match the shared menu", () => {
  const chipStyle = /const TAG_CHIP_STYLE = '([^']+)';/.exec(SRC)![1];
  const shared = /chip\.setAttribute\("style", "([^"]+)"\s*\n\s*\+ "border-radius:9px;" \+ \(opts && opts\.inheritSize \? "" : "font-size:0\.82em;"\)\s*\n\s*\+ "border:1px solid "/.exec(MENU);
  assert.ok(shared, "the shared tagChip's style is where the pin expects it");
  assert.equal(chipStyle, shared![1] + "border-radius:9px;font-size:0.82em;border:1px solid ", "the pill, byte for byte up to the colour");
  assert.match(SRC, /TAG_CHIP_STYLE \+ col \+ ';color:' \+ col \+ ';background:transparent;white-space:nowrap;font-weight:400;letter-spacing:normal;'/,
    "…and the tail after the colour carries the shared weight and tracking (T321: never bold)");
  assert.match(MENU, /\+ "font-weight:400;letter-spacing:normal;"/, "the shared pill's own tail, the same bytes");
  // the dialog's two other tag pills (its own signatures: the drag cell's pill, the per-pane filter pills): never bold either (T321)
  assert.match(SRC, /pill\.setAttribute\('style', TAG_CHIP_STYLE\.replace\('font-size:0\.82em;', ''\) \+ tc \+ ';color:' \+ tc \+ ';background:transparent;white-space:nowrap;font-weight:400;letter-spacing:normal;'/,
    "the tag row's pill: the shared pill's bytes at the row's size (the inherit case)");
  assert.match(SRC, /s2\.setAttribute\('style', TAG_CHIP_STYLE \+ c2 \+ ';color:' \+ c2 \+ ';background:transparent;white-space:nowrap;font-weight:400;letter-spacing:normal;cursor:pointer;'\s*\n\s*\+ \(selected \? '' : 'opacity:' \+ TAG_CHIP_OFF_OPACITY \+ ';'\)\);\s*\n\s*if \(!selected\) s2\.classList\.add\(TAG_CHIP_OFF_CLASS\);/,
    "the filter pills: the shared pill plus the pointer; selected = the full chip, unselected = the shared fade and class, never a fill");
  assert.doesNotMatch(SRC, /SEL_BG \+ ';opacity:1;'|padding:2px 9px|padding:1px 8px;border-radius:9px/, "no third or fourth pill shape in the pane");
  assert.doesNotMatch(SRC, /font-weight:650;'\s*\n?[^\n]*(tc|c2)\b/, "no bold left on a tag-coloured pill");
  // the view's other inlined chips carry the same tail: the dialog rows' lane chips, the [+] join options, the corner filter chips
  assert.match(SRC, /'color:' \+ tc \+ ';border:1px solid ' \+ tc \+ ';background:transparent;font-weight:400;letter-spacing:normal;'\);\s+\/\/ the one tag chip \(T321\)\n/, "the lane chips");
  assert.match(SRC, /'display:inline-flex;align-items:center;gap:5px;padding:2px 7px;border-radius:9px;font-size:0\.82em;cursor:pointer;white-space:nowrap;'\s*\n\s*\+ 'color:' \+ tc \+ ';border:1px solid ' \+ tc \+ ';background:transparent;font-weight:400;letter-spacing:normal;'\);\s+\/\/ the one tag chip \(T321\): the join option/, "the join options, the chip's shape");
  assert.match(SRC, /\.romp-tl-chip\{display:inline-flex;align-items:center;gap:5px;padding:2px 7px;border-radius:9px;'\s*\n\s*\+ 'font-size:0\.82em;border:1px solid;background:transparent;white-space:nowrap;font-weight:400;letter-spacing:normal\}/, "the corner filter chips");
  assert.match(SRC, /const TAG_CHIP_OFF_OPACITY = '0\.45';/);
  assert.match(SRC, /const TAG_CHIP_OFF_CLASS = 'tag-chip-off';/);
  // the shared menu's own constants and chip row (T283, on main): each pin fails LOUDLY when its anchor moves,
  // never skips, so a reformat of the shared loop cannot leave a later padding or radius change uncaught
  const off = /export const TAG_CHIP_OFF_OPACITY = "([^"]+)";/.exec(MENU);
  assert.ok(off, "the shared fade constant is where the pin expects it");
  assert.equal(off![1], "0.45", "the shared fade");
  const cls = /export const TAG_CHIP_OFF_CLASS = "([^"]+)";/.exec(MENU);
  assert.ok(cls, "the shared state class is where the pin expects it");
  assert.equal(cls![1], "tag-chip-off", "the shared state class");
  const row = /r\.setAttribute\("style", "([^"]+)"\);\s*\n(?:\s*r\.setAttribute\([^\n]*\n)*\s*const chip = tagChip\(u\.name/.exec(MENU);   // T413: the row's role, state and title sit between the style and the chip
  assert.ok(row, "the shared chip row is where the pin expects it");
  assert.equal(/const TAG_CHIP_ROW_STYLE = '([^']+)';/.exec(SRC)![1], row![1], "the chip row's shape");
  // the shared tag rows never carried a dot after T283; this copy's plain rows carry none either
  const views = SRC.slice(SRC.indexOf("  _openViewsMenu(anchorEl) {"), SRC.indexOf("  _openDisplayMenu(anchorEl) {"));
  assert.doesNotMatch(views, /border-radius:50%/, "no colour dot in the views menu");
  assert.match(views, /c\.setAttribute\('style', MENU_CHECK_STYLE\);/, "the ✓-in-circle stays for All and (no tags)");
});
