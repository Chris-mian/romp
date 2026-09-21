// The opt-in LIGHT theme on the timeline surface (2026-08-28). The settings toggle puts
// body.theme-light on every pane document; this pane consults it through ONE indirection — PAL(),
// refreshed at the top of every draw() — so a theme flip repaints on the next draw. The Obsidian
// host never sets the class, so dark stays its default there; the DARK values must therefore stay
// byte-identical when the class is absent. Pins here:
//   (a) timeline-pane.css carries a body.theme-light block re-defining the SAME tokens :root defines,
//   (b) the injected corner/metadots/loader CSS and the tip CSS carry body.theme-light variants,
//   (c) draw() output is unchanged in dark and re-inks under the class (headless DOM shim render).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { createRequire } from "node:module";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "timeline-pane.css"), "utf8");

// ---- (a) the stylesheet's light block re-points the same tokens its :root defines ----
test("timeline-pane.css: body.theme-light re-defines every :root token (muted/faint ink)", () => {
  assert.match(CSS, /:root\{--text-muted:#9aa0a6;--text-faint:#6e7681;\}/, "the dark tokens are untouched");
  assert.match(CSS, /body\.theme-light \{\n  --text-muted: #5D574E;\n  --text-faint: #8A8378;/, "the light block re-points both tokens");
});
test("timeline-pane.css: the tip card gets a scoped light re-skin (white card, black hairline, dark ink)", () => {
  assert.match(CSS, /body\.theme-light \.romp-tl-tip\{background:var\(--tl-card, #FFFFFF\);border:1px solid var\(--tl-hairline, rgba\(0,0,0,0\.12\)\);/);   // literal fallbacks: tip rules are adopted into a host that defines none of the tokens
  // and the dark tip rule is byte-identical (the Obsidian default)
  assert.match(CSS, /\.romp-tl-tip\{position:fixed;pointer-events:none;z-index:1000;max-width:320px;background:#1c2430;/);
});

// ---- (b) the injected <style> strings carry scoped light variants (no re-injection needed) ----
test("injected corner CSS: dark rules byte-identical + body.theme-light variants appended", () => {
  // dark rules unchanged (the tagbtn-click test pins the .on rule verbatim; the hover here)
  assert.match(SRC, /\.romp-tl-cbtn:hover\{border-color:var\(--accent,#9cd2ff\);color:var\(--accent,#9cd2ff\);background:rgba\(156,210,255,0\.12\)\}/);
  // light variants: muted ink, black hairline, the CLAY accent standing in for the blue
  assert.match(SRC, /body\.theme-light \.romp-tl-cbtn\{color:#5D574E;border-color:rgba\(0,0,0,0\.12\)\}/);
  assert.match(SRC, /body\.theme-light \.romp-tl-cbtn\.on\{color:#C2410C;border-color:#C2410C;background:rgba\(194,65,12,0\.10\)\}/);
  assert.match(SRC, /body\.theme-light \.romp-tl-ctail\{color:#5D574E\}/);
});
test("injected metadots + loader dots: accent-blue in dark, clay under body.theme-light", () => {
  assert.match(SRC, /background:' \+ PAL_DARK\.accent \+ ';display:inline-block;animation:romp-tl-metadots/);
  assert.match(SRC, /body\.theme-light \.romp-tl-meta-dots i\{background:' \+ PAL_LIGHT\.accent \+ '\}/);
  assert.match(SRC, /body\.theme-light \.tl-loader \.rl-dots i\{background:#C2410C\}/);
});
test("the tip adopt-copy carries the scoped light rules (substring match, not prefix)", () => {
  assert.match(SRC, /r\.selectorText\.indexOf\('\.romp-tl-tip'\) !== -1/);
});

// ---- (c) headless render: dark output unchanged; the class re-inks on the NEXT draw ----
// minimal DOM shim (same shape as timeline-render.test.ts)
function makeNode(tag: string): any {
  const n: any = {
    tag, _attrs: {}, children: [] as any[], style: {}, dataset: {}, textContent: "", parentNode: null,
    classList: { _s: new Set<string>(), add(...a: string[]) { a.forEach((c) => this._s.add(c)); },
      remove(...a: string[]) { a.forEach((c) => this._s.delete(c)); },
      toggle(c: string, f?: boolean) { f ? this._s.add(c) : this._s.delete(c); }, contains(c: string) { return this._s.has(c); } },
    setAttribute(k: string, v: any) { this._attrs[k] = v; }, getAttribute(k: string) { return this._attrs[k]; },
    setAttributeNS(_n: any, k: string, v: any) { this._attrs[k] = v; }, removeAttribute(k: string) { delete this._attrs[k]; },
    appendChild(c: any) { c.parentNode = n; this.children.push(c); return c; },
    insertBefore(c: any, ref: any) { c.parentNode = n; const i = this.children.indexOf(ref); i < 0 ? this.children.push(c) : this.children.splice(i, 0, c); return c; },
    removeChild(c: any) { const i = this.children.indexOf(c); if (i >= 0) this.children.splice(i, 1); return c; },
    get firstChild() { return this.children[0] || null; },
    addEventListener() {}, removeEventListener() {}, querySelector() { return null; }, querySelectorAll() { return []; },
    getBoundingClientRect() { return { width: 1400, height: 420, left: 0, top: 0, right: 1400, bottom: 420 }; },
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

function synthData() {
  const now = 1_781_000_000;
  const turn = (id: string, dt0: number, dt1: number) => ({
    id, promptId: id + "#p", workId: id + "#w",
    start: now - dt0, end: now - dt1, prompt: "do the thing", src: "typed", mids: [],
    pending: false, summary: "did the thing", reply: "did it", tid: "fork-" + id, uuid: "u-" + id,
    workUuid: "w-" + id, replyUuid: "r-" + id,
  });
  const sess = (id: string, name: string) => ({
    id, name, color: "#7aa2f7", state: "working", live: true, model: "Opus 4.8", effort: "xhigh",
    context: 40, since: now - 60, awaiting: [], compacting: [], pendingMail: 0, compactions: [], faded: false, stale: false,
  });
  return {
    now,
    sessions: [sess("S1", "web"), sess("S2", "api")],
    turns: { S1: [turn("S1:1:aa", 300, 60)], S2: [turn("S2:1:cc", 200, 30)] },
    messages: [], activeChat: null, focus: null, hover: null, usage: null,
  };
}
function strokes(node: any, out: string[] = []): string[] {
  const s = node.getAttribute && node.getAttribute("stroke"); if (s) out.push(s);
  for (const c of node.children || []) strokes(c, out);
  return out;
}
function fills(node: any, out: string[] = []): string[] {
  const f = node.getAttribute && node.getAttribute("fill"); if (f) out.push(f);
  for (const c of node.children || []) fills(c, out);
  return out;
}

test("dark render is byte-identical without the class; body.theme-light re-inks on the next draw", () => {
  const panel: any = new TimelinePanel(makeNode("div"));
  panel.data = synthData();
  assert.doesNotThrow(() => panel.draw());
  // dark: the exact strokes/fills the file always drew
  let st = strokes(panel.svg), fl = fills(panel.svg);
  assert.ok(st.includes("#ffffff10"), "dark gridlines keep their exact value");
  assert.ok(st.includes("#ffffff22"), "dark now-edge keeps its exact value");
  assert.ok(st.includes("#e8eef5"), "dark event-dot halo keeps its exact value");
  assert.ok(!st.includes("#00000010") && !fl.includes("#5D574E"), "no light ink leaks into dark");
  // flip the theme class on the shim body → the NEXT draw repaints in the light palette
  g.document.body.classList.add("theme-light");
  try {
    panel.draw();
    st = strokes(panel.svg); fl = fills(panel.svg);
    assert.ok(st.includes("#00000010"), "light gridlines");
    assert.ok(st.includes("#00000026"), "light now-edge");
    assert.ok(fl.includes("#5D574E"), "muted ink re-points to the light value (model labels)");
    assert.ok(!st.includes("#ffffff10"), "no dark gridline survives the flip");
  } finally {
    g.document.body.classList.remove("theme-light");
  }
  // and flipping BACK restores the dark bytes (no latch)
  panel.draw();
  st = strokes(panel.svg);
  assert.ok(st.includes("#ffffff10") && !st.includes("#00000010"), "dark restores exactly");
});
