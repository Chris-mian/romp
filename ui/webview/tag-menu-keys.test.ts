// THE TAGS MENU TAKES THE HOUSE ROWS MENU'S KEYBOARD GRAMMAR (T413 round two, the manager's read of 2026-09-14: the checkbox
// rows took no focus and no keys, and the menu had no role). The menu is role menu; every row takes focus (tabindex 0) and the
// keys: Enter and Space press it, ArrowDown and ArrowUp move between the rows (Home and End to the ends), Escape closes the menu
// and hands the focus back to the button; the first row takes the focus when the menu opens; and the button opens on Enter,
// Space and ArrowDown from the keyboard (before, only on the pointer's press, so a keyboard user never reached the menu at all).
// Executed against a stub document (the tag-menu-chips pattern: no jsdom), plus source pins: the unselected ring's token is the
// muted text, which clears 3 to 1 against the menu ground in both themes (the hairline it wore read at 1.5 to 1). Synthetic
// tags only.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const MENU_SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "tag-menu.ts"), "utf8");

type Ev = { key: string; target: any; defaultPrevented: boolean; stopped: boolean; preventDefault(): void; stopPropagation(): void };
const ev = (key = ""): Ev => ({ key, target: null, defaultPrevented: false, stopped: false,
  preventDefault() { this.defaultPrevented = true; }, stopPropagation() { this.stopped = true; } });

let active: any = null;   // the stub document's focused node
const docListeners: Record<string, Function[]> = {};
function mk(tag: string): any {
  const n: any = {
    tag, attrs: {} as Record<string, string>, kids: [] as any[], style: {} as Record<string, string>, listeners: {} as Record<string, Function[]>,
    dataset: {} as Record<string, string>, tabIndex: -1, offsetWidth: 200, offsetHeight: 100, parentNode: null as any, isConnected: true,
    id: "", className: "", title: "", type: "", innerHTML: "", tagName: tag.toUpperCase(),
    get textContent(): string { return n.kids.map((k: any) => k.tag === "#text" ? k.text : k.textContent).join(""); },
    set textContent(v: string) { n.kids = v ? [{ tag: "#text", text: v }] : []; },
    get children(): any[] { return n.kids.filter((k: any) => k.tag !== "#text"); },
    get childElementCount(): number { return n.children.length; },
    get firstElementChild(): any { return n.children[0] || null; },
    get parentElement(): any { return n.parentNode; },   // the roving tab stop reads the row's parent (the strip tidy)
    get lastElementChild(): any { const c = n.children; return c[c.length - 1] || null; },
    setAttribute(k: string, v: string) { n.attrs[k] = String(v); }, getAttribute(k: string) { return k in n.attrs ? n.attrs[k] : null; },
    appendChild(c: any) { c.parentNode = n; n.kids.push(c); return c; },
    remove() { if (n.parentNode) { const i = n.parentNode.kids.indexOf(n); if (i >= 0) n.parentNode.kids.splice(i, 1); n.parentNode = null; n.isConnected = false; } },
    addEventListener(t: string, fn: Function) { (n.listeners[t] = n.listeners[t] || []).push(fn); },
    /** fire `t` here, then up the tree and at the document (the DOM's bubbling); focus and blur never bubble */
    dispatch(t: string, e?: Ev): Ev {
      const x = e || ev(); if (!x.target) x.target = n;
      for (const fn of (n.listeners[t] || []).slice()) fn.call(n, x);
      if (t === "focus" || t === "blur") return x;
      if (!x.stopped) { if (n.parentNode) n.parentNode.dispatch(t, x); else if (n.tag === "body") for (const fn of docListeners[t] || []) fn.call(null, x); }
      return x;
    },
    click() { return n.dispatch("click"); },
    dispatchEvent(e: any) { return n.dispatch(e && e.type ? e.type : "click"); },
    focus() { const was = active; active = n; if (was && was !== n) was.dispatch("blur"); n.dispatch("focus"); },
    blur() { if (active === n) { active = null; n.dispatch("blur"); } },
    contains(c: any): boolean { for (let p = c; p; p = p.parentNode) if (p === n) return true; return false; },
    getClientRects() { return n.isConnected ? [{ width: 30 }] : []; },
    getBoundingClientRect() { return { left: 10, right: 40, top: 10, bottom: 30, width: 30, height: 20 }; },
    querySelectorAll() { return []; }, querySelector() { return null; },
  };
  return n;
}

const g = globalThis as any;
const body = mk("body");
g.document = { createElement: mk, createTextNode: (t: string) => ({ tag: "#text", text: t }), body,
  addEventListener(t: string, fn: Function) { (docListeners[t] = docListeners[t] || []).push(fn); },
  get activeElement() { return active; }, getElementById: () => null,
  querySelector: () => null, querySelectorAll: (sel: string) => body.children.filter((c: any) => sel.startsWith(c.tag) && c.isConnected) };
g.window = { innerWidth: 1400, innerHeight: 800, addEventListener() {} };
g.localStorage = { getItem: () => null, setItem() {}, removeItem() {} };
// eslint-disable-next-line @typescript-eslint/no-var-requires
const mod = require("./tag-menu");

const UNIONS = [{ name: "infra", color: "#DD42FF" }, { name: "qa", color: "#3355aa" }].map((u) => ({ ...u, members: [], ids: [], localId: null, locals: [], remotes: [] }));
const label = (n: any): string => n.textContent.replace("✓", "").trim();
/** the real openTagMenu on a button in the stub body; the rows are the menu's children that carry a role (the separator has none) */
function open(lens: { all?: boolean; none?: boolean; tags?: string[] }, via: "keyboard" | "pointer" = "keyboard") {
  mod.closeTagMenu(); active = null;
  for (const k of body.kids.slice()) k.remove();
  const applies: { lens: any; done: boolean }[] = []; let current: any = lens;
  const composer = mk("textarea"); composer.className = "composer"; body.appendChild(composer);
  const btn = mk("button"); btn.className = "tab-tagfilter"; body.appendChild(btn);
  // a keyboard open: the button had the focus (the user tabbed to it and pressed Enter); a pointer open: the press prevents the
  // button's own focus, so the focus is wherever it was, here the composer's (the strip tidy after T413 round two)
  if (via === "keyboard") btn.focus(); else composer.focus();
  mod.openTagMenu(btn, { lens: () => current, unions: () => UNIONS,
    onApply: (l: any, done: boolean) => { applies.push({ lens: l, done }); current = l; },
    groupToggle: { label: "Group tabs by tag", on: () => false, toggle() { /* a switch */ } }, onConfigure() { /* a route */ } });
  const menu = body.kids[body.kids.length - 1];
  return { btn, composer, menu, applies, rows: () => menu.children.filter((r: any) => r.getAttribute("role")) as any[] };
}
const press = (node: any, key: string) => node.dispatch("keydown", ev(key));

test("the menu is role menu with ONE tab stop (the ARIA menu pattern): the first row is tabindex 0 and the rest -1, every row takes the keys, and a keyboard open puts the focus on the first row", () => {
  const m = open({ all: true });
  assert.equal(m.menu.getAttribute("role"), "menu", "the menu's role");
  const rows = m.rows();
  assert.deepEqual(rows.map(label), ["All", "(no tags)", "infra", "qa", "Group tabs by tag", "Configure tags…"], "every row, the tags between");
  for (const r of rows) {
    assert.equal(r.tabIndex, r === rows[0] ? 0 : -1, label(r) + ": one tab stop, the rest reached by the arrows, so Tab leaves the menu (35 stops before, the strip tidy)");
    assert.ok((r.listeners.keydown || []).length >= 1, label(r) + ": and the keys");
    assert.match(r.attrs.style, /outline:none;/, label(r) + ": the focus ring is the hover wash, not the browser's outline");
  }
  assert.equal(active, rows[0], "the keyboard open (the button had the focus) puts it on the first row");
  assert.match(rows[0].style.background || "", /--menu-hover/, "…and reads focused with the hover wash");
  mod.closeTagMenu();
});

test("a pointer open leaves the focus where it was (the composer's, round one's rule) and still leaves one tab stop on the first row", () => {
  const m = open({ all: true }, "pointer");
  assert.equal(active, m.composer, "the composer keeps the focus: the press never moved it");
  const rows = m.rows();
  assert.deepEqual(rows.map((r: any) => r.tabIndex), [0, -1, -1, -1, -1, -1], "the first row is the one tab stop, unfocused");
  assert.equal(m.menu.parentNode, body, "the menu is open");
  mod.closeTagMenu();
});

test("the tab stop moves with the focus: an arrow or a click on a row makes that row the stop and the others -1", () => {
  const m = open({ all: true });
  const rows = m.rows();
  press(active, "ArrowDown"); press(active, "ArrowDown");
  assert.equal(label(active), "infra"); assert.deepEqual(rows.map((r: any) => r.tabIndex), [-1, -1, 0, -1, -1, -1], "the stop followed the arrows");
  rows[4].focus();   // a pointer press on a row focuses it (tabindex -1 elements take a click's focus)
  assert.deepEqual(rows.map((r: any) => r.tabIndex), [-1, -1, -1, -1, 0, -1], "…and a click's focus too");
  mod.closeTagMenu();
});

test("the Group tabs by tag switch is a checkbox row like the house rows menu's switches: role menuitemcheckbox, aria-checked, the two-state mark", () => {
  const m = open({ all: true });
  const sw = m.rows()[4];
  assert.equal(label(sw), "Group tabs by tag");
  assert.equal(sw.getAttribute("role"), "menuitemcheckbox", "a switch, not a plain item (round two named it menuitem with no state)");
  assert.equal(sw.getAttribute("aria-checked"), "false", "off in this fixture, said so");
  const mark = sw.children.find((c: any) => c.getAttribute("data-check") !== null);
  assert.ok(mark && mark.getAttribute("data-check") === "false", "the two-state mark, the empty ring when off");
  mod.closeTagMenu();
});

test("ArrowDown and ArrowUp walk the rows, Home and End jump to the ends, and neither end wraps", () => {
  const m = open({ all: true });
  assert.ok(active, "a focused row to start from (the first row on a keyboard open)");
  const rows = m.rows();
  press(active, "ArrowDown"); assert.equal(label(active), "(no tags)");
  press(active, "ArrowDown"); assert.equal(label(active), "infra");
  press(active, "ArrowUp"); assert.equal(label(active), "(no tags)");
  const e = press(active, "End"); assert.equal(label(active), "Configure tags…"); assert.ok(e.defaultPrevented, "the page never scrolls on a menu key");
  press(active, "ArrowDown"); assert.equal(label(active), "Configure tags…", "the last row holds at the end");
  press(active, "Home"); assert.equal(label(active), "All");
  press(active, "ArrowUp"); assert.equal(label(active), "All", "the first row holds at the start");
  assert.equal(rows.length, 6);
  mod.closeTagMenu();
});

test("Enter and Space press the focused row: a tag row toggles its tag with the menu staying open and the focus kept on that row; All applies the exclusive pick", () => {
  const m = open({ all: true });
  assert.ok(active, "a focused row to start from (the first row on open)");
  press(active, "ArrowDown"); press(active, "ArrowDown");
  assert.equal(label(active), "infra"); assert.equal(active.getAttribute("aria-checked"), "false");
  const e = press(active, " ");
  assert.ok(e.defaultPrevented && e.stopped, "Space is the row's, not the page's");
  assert.deepEqual(m.applies.map((a) => [a.lens.tags, a.done]), [[["infra"], false]], "the tag toggled on, the menu kept");
  assert.equal(m.menu.parentNode, body, "the menu stands");
  assert.equal(label(active), "infra", "the focus stays on the same row across the repaint"); assert.equal(active.getAttribute("aria-checked"), "true", "…which now reads selected");
  press(active, "ArrowDown"); assert.equal(label(active), "qa");
  press(active, "Enter");
  assert.deepEqual(m.applies[1].lens.tags, ["infra", "qa"], "Enter presses too");
  press(active, "Home"); press(active, "Enter");
  assert.deepEqual([m.applies[2].lens, m.applies[2].done], [{ all: true }, true], "All: the exclusive pick, done");
  mod.closeTagMenu();
});

test("Escape closes the menu and hands the focus back to the button; the document's own Escape closer is not reached", () => {
  const m = open({ all: true });
  assert.ok(active, "a focused row to start from (the first row on open)");
  press(active, "ArrowDown");
  const e = press(active, "Escape");
  assert.ok(e.stopped, "handled in the menu");
  assert.equal(m.menu.parentNode, null, "the menu is gone");
  assert.equal(active, m.btn, "the button holds the focus again");
});

test("the button opens from the keyboard: Enter, Space and ArrowDown (the pointer's press still opens, its click stays swallowed)", () => {
  const opened: any[] = [];
  const btn = mod.tagMenuButton("filter by tag", (b: any) => opened.push(b));
  assert.equal(btn.getAttribute("aria-haspopup"), "menu", "a button that opens a menu says so");
  for (const k of ["Enter", " ", "ArrowDown"]) { const e = press(btn, k); assert.ok(e.defaultPrevented, k + " is the button's"); }
  assert.equal(opened.length, 3, "each key opened");
  press(btn, "a"); press(btn, "Tab"); assert.equal(opened.length, 3, "other keys pass");
  btn.dispatch("pointerdown"); assert.equal(opened.length, 4, "the pointer's press opens as before");
  const c = btn.dispatch("click"); assert.ok(c.stopped, "and the opener's own click is swallowed");
});

test("source pins: the unselected ring wears the muted text token (3 to 1 against the menu ground in both themes), never the hairline", () => {
  const mark = MENU_SRC.slice(MENU_SRC.indexOf("function checkMark("), MENU_SRC.indexOf("\n}\n", MENU_SRC.indexOf("function checkMark(")));
  assert.match(mark, /border:1px solid var\(--text-muted, #9aa0a6\);background:transparent;/, "the ring's token");
  assert.doesNotMatch(mark, /--menu-border/, "the hairline read at 1.5 to 1 against the menu ground (round one, low 1)");
  assert.match(MENU_SRC, /menu\.setAttribute\("role", "menu"\);\s*\n\s*menu\.dataset\.tagMenu = "1";/, "the tags menu's role sits with its marker");
});
