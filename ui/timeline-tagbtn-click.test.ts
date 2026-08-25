// The corner tag button must OPEN ITS MENU under a host that installs only the three DOM helpers
// (createEl/createDiv/createSpan — all the browser and VS Code boots provide; timeline-boot.ts /
// the kernel's _TIMELINE_BOOT). The 2026-08-25 "can't click on it": the menu repaint called
// Obsidian's .empty(), which exists in neither host, so every press threw a TypeError before the
// menu appeared — the button looked fine and did nothing. This test EXECUTES the press over the
// house fake-DOM shim (which, like the real boots, has no Obsidian extras) and asserts the menu
// builds; the source scan below bans the whole class of Obsidian-only helper calls.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { createRequire } from "node:module";

// ---- the house fake-DOM shim (timeline-hidden-stub.test.ts's, + createTextNode: the menu rows
// write real text nodes, and the real hosts of course have it) ----
function makeNode(tag: string): any {
  const n: any = {
    tag, _attrs: {}, children: [] as any[], style: {}, dataset: {}, textContent: "", parentNode: null,
    classList: { _s: new Set<string>(), add(...a: string[]) { a.forEach((c) => this._s.add(c)); },
      remove(...a: string[]) { a.forEach((c) => this._s.delete(c)); },
      toggle(c: string, f?: boolean) { f ? this._s.add(c) : this._s.delete(c); }, contains(c: string) { return this._s.has(c); } },
    setAttribute(k: string, v: any) { this._attrs[k] = v; }, getAttribute(k: string) { return this._attrs[k]; },
    setAttributeNS(_n: any, k: string, v: any) { this._attrs[k] = v; }, removeAttribute(k: string) { delete this._attrs[k]; },
    appendChild(c: any) {   // real-DOM semantics: appending an attached node MOVES it (the menu is created on body, then re-appended to the menu host)
      if (c.parentNode) { const i = c.parentNode.children.indexOf(c); if (i >= 0) c.parentNode.children.splice(i, 1); }
      c.parentNode = n; this.children.push(c); return c; },
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
const g: any = global;
g.document = {
  createElement(t: string) { return t === "canvas" ? { getContext() { return { font: "", measureText(s: string) { return { width: (s ? s.length : 0) * 6 }; } }; } } : makeNode(t); },
  createElementNS(_n: any, t: string) { return makeNode(t); },
  createTextNode(text: string) { const n = makeNode("#text"); n.textContent = text; return n; },
  body: makeNode("body"), documentElement: makeNode("html"), head: makeNode("head"),
  getElementById() { return null; },
  addEventListener() {}, removeEventListener() {},
};
g.localStorage = { getItem() { return null; }, setItem() {}, removeItem() {} };
g.getComputedStyle = () => ({ backgroundColor: "rgb(30,30,30)" });
g.requestAnimationFrame = () => 0;
g.addEventListener = () => {}; g.removeEventListener = () => {};
g.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
g.window = g;
g.innerWidth = 1400; g.innerHeight = 800;

const viewPath = path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js");
const { TimelinePanel } = createRequire(__filename)(viewPath);
const SRC = fs.readFileSync(viewPath, "utf8");

function drawnPanel(): any {
  const now = 1_781_000_000;
  const sess = (id: string, name: string, color: string) => ({
    id, name, color, state: "working", live: true, model: "Opus", effort: "high",
    context: 40, since: now - 60, awaiting: [], compacting: [], pendingMail: 0, compactions: [], faded: false, stale: false,
  });
  const panel = new TimelinePanel(makeNode("div"));
  panel.update({
    now,
    sessions: [sess("s1", "web", "#f7768e"), sess("s2", "api", "#7aa2f7")],
    // turns present so draw() runs for real (an empty warm-up keeps the loader up and no corner draws)
    turns: { s1: [{ id: "t1", start: now - 400, end: now - 100, prompt: "do the thing", tid: "f1", mids: [] }] },
    messages: [], judging: [],
    views: { active: "all", tags: [{ id: "g1", name: "infra", color: "#DD42FF", members: ["s2"] }], actives: { timeline: { all: true } } },
  });
  return panel;
}

function findByTitle(root: any, txt: string): any {
  for (const c of root.children || []) {
    if (c.tag === "title" && String(c.textContent).includes(txt)) return root;
    const hit = findByTitle(c, txt);
    if (hit) return hit;
  }
  return null;
}

test("executed: a tag-button press BUILDS the menu under a three-helper host (the 2026-08-25 dead button)", () => {
  const panel = drawnPanel();
  const btn = findByTitle(panel.svg, "filter these lanes by tag");
  assert.ok(btn, "the corner tag button drew");
  const before = g.document.body.children.length;
  btn._listeners.pointerdown({ preventDefault() {}, stopPropagation() {} });   // the press — must not throw
  assert.ok(panel._viewsMenu, "the views menu opened");
  assert.equal(g.document.body.children.length, before + 1, "the menu landed in the host body");
  const labels: string[] = [];
  (function walk(x: any) { for (const c of x.children || []) { if (c.tag === "#text" || c.tag === "span") labels.push(String(c.textContent)); walk(c); } })(panel._viewsMenu);
  for (const want of ["All", "(no tags)", "infra", "Configure tags…"])
    assert.ok(labels.some((l) => l.includes(want)), "menu row present: " + want);
  // a second press on the open menu's button toggles it shut, still without throwing
  btn._listeners.pointerdown({ preventDefault() {}, stopPropagation() {} });
  assert.equal(panel._viewsMenu, null, "re-press toggles shut");
  panel._closeViewsMenu();
});

test("executed: the outlined box is the button's hit geometry — it spans the glyph, not a bare 16x16 pad", () => {
  const panel = drawnPanel();
  const btn = findByTitle(panel.svg, "filter these lanes by tag");
  const box = btn.children[0];
  assert.equal(box.tag, "rect", "the box is the button's base layer");
  assert.equal(box._attrs.width, 32, "full box width (14px glyph + 9px sides)");
  assert.equal(box._attrs.height, 18, "chip-row height");
  assert.equal(box._attrs.rx, 6, "the feed's radius");
  assert.equal(box._attrs.fill, "transparent", "at rest transparent — still pointer-catching in svg");
  assert.equal(box._attrs.stroke, "rgba(255,255,255,0.10)", "the feed's hairline at rest");
  // every glyph part opts out of hits, so the box is the ONE hit surface (the lock's pattern)
  for (const part of btn.children.slice(1))
    if (part.tag !== "title") assert.equal(part._attrs["pointer-events"], "none", part.tag + " opts out of hits");
  // the glyph sits INSIDE the box — the press target covers everything the eye reads as the button
  const glyph = btn.children.find((c: any) => c.tag === "path");
  assert.ok(glyph, "tag glyph drew");
  const d = String(glyph._attrs.d);
  const mx = Number(d.split(" ")[1]);
  assert.ok(mx > Number(box._attrs.x) && mx < Number(box._attrs.x) + 32, "glyph starts inside the box");
});

test("executed: narrowed, the box wears the accent border + the feed .on wash", () => {
  const panel = drawnPanel();
  const v = { active: "all", tags: [{ id: "g1", name: "infra", color: "#DD42FF", members: ["s2"] }], actives: { timeline: { tags: ["infra"] } } };
  panel.update(Object.assign({}, panel.data, { views: v }));
  const btn = findByTitle(panel.svg, "filter these lanes by tag");
  const box = btn.children[0];
  assert.equal(box._attrs.stroke, "#9cd2ff", "accent border while narrowed");
  assert.equal(box._attrs.fill, "rgba(156,210,255,0.12)", "the .on wash while narrowed");
});

test("the view speaks plain DOM: no Obsidian-only helper calls (the hosts install only the three)", () => {
  // .empty()/.setText()/.addClass()/.removeClass()/.toggleClass()/.detach() exist only under
  // Obsidian; a call to any of them is a crash on the web and VS Code timelines — exactly how the
  // tag button died. createEl/createDiv/createSpan stay fine: every boot installs those three.
  for (const bad of [/\.empty\(\)/, /\.setText\(/, /\.addClass\(/, /\.removeClass\(/, /\.toggleClass\(/, /\.detach\(\)/])
    assert.doesNotMatch(SRC, bad, "Obsidian-only helper in the shared view: " + bad);
});
