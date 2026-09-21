// Pending-host placeholder rows on the timeline (the user 2026-09-02): an attached host whose lanes
// have not arrived yet — a kernel restart, a phone re-foreground, a fresh attach — used to leave NO
// trace on the board, and the user read the blank as wiped state. The merged lanes payload now names
// such hosts (federation.ts mergeHostTimelines.pendingHosts, retired only by the host's first lanes
// payload or its detach), and draw() reserves one placeholder row per name under the lanes: the romp
// swirl (reverse-spun) + "loading sessions from <host>…" (or "reconnecting to <host>…" on a dead link).
// Executed through the real draw() on the headless DOM shim timeline-render.test.ts uses. Synthetic only.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import { createRequire } from "node:module";
import * as path from "node:path";

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

const LANE_GAP = 26;   // the view's lane pitch (romp-timeline-view.js) — one placeholder row = one lane slot
function synthData(): any {
  const now = 1_781_000_000;
  const turn = (id: string, dt0: number, dt1: number) => ({
    id, promptId: id + "#p", workId: id + "#w", start: now - dt0, end: now - dt1, prompt: "do the thing", src: "typed", mids: [],
    pending: false, summary: "did the thing", reply: "did it", tid: "fork-" + id, uuid: "u-" + id, workUuid: "w-" + id, replyUuid: "r-" + id,
  });
  const sess = (id: string, name: string) => ({
    id, name, color: "#7aa2f7", state: "working", live: true, model: "Opus 4.8", effort: "xhigh",
    context: 40, since: now - 60, awaiting: [], compacting: [], pendingMail: 0, compactions: [], faded: false, stale: false,
  });
  return { now, sessions: [sess("S1", "web"), sess("S2", "api")],
           turns: { S1: [turn("S1:1:aa", 300, 60)], S2: [turn("S2:1:cc", 200, 30)] },
           messages: [], activeChat: null, focus: null, hover: null, usage: null };
}
function findAll(node: any, pred: (n: any) => boolean, out: any[] = []): any[] {
  if (pred(node)) out.push(node);
  for (const c of node.children || []) findAll(c, pred, out);
  return out;
}
const pendingTexts = (svg: any) => findAll(svg, (n) => n.tag === "text" && n._attrs["data-pending-host"]);
const svgH = (svg: any) => Number(svg.getAttribute("height"));

test("a pending host draws ONE placeholder row under the lanes — swirl + 'loading sessions from <host>…' — and _vis stays the real lanes", () => {
  const panel = new TimelinePanel(makeNode("div"));
  const base: any = synthData();
  panel.data = base;
  panel.draw();
  const h0 = svgH(panel.svg);
  const data: any = Object.assign(synthData(), { pendingHosts: ["TESTHOST"], pendingDead: [] });
  panel.data = data;
  assert.doesNotThrow(() => panel.draw());
  const rows = pendingTexts(panel.svg);
  assert.equal(rows.length, 1, "one row per pending host");
  assert.equal(rows[0].textContent, "loading sessions from TESTHOST…");
  assert.equal(rows[0]._attrs["font-style"], "italic", "the quiet italic the host: prefix wears — chrome, not a lane name");
  assert.equal(panel._vis.length, 2, "the placeholder is NOT a lane: vis/vidx untouched");
  assert.equal(svgH(panel.svg), h0 + LANE_GAP, "the SVG grew by exactly one lane slot");
  // the swirl: the shared romp glyph, reverse-spun (360 → 0), sitting in the name column of that row
  const imgs = findAll(panel.svg, (n) => n.tag === "image" && /romp-swirl-glyph\.svg/.test(String(n._attrs.href)));
  assert.equal(imgs.length, 1);
  const spin = imgs[0].children.find((c: any) => c.tag === "animateTransform");
  assert.ok(spin && spin._attrs.type === "rotate" && /^360 /.test(String(spin._attrs.from)) && /^0 /.test(String(spin._attrs.to)),
    "reverse spin, like every romp loader");
  assert.equal(Number(rows[0]._attrs.y) > Number(imgs[0]._attrs.y), true, "text baseline sits below the glyph's top edge (same row)");
  // the row sits UNDER the last lane, never over one
  const laneNames = findAll(panel.svg, (n) => n.tag === "text" && (n.textContent === "web" || n.textContent === "api"));
  const maxLaneY = Math.max(...laneNames.map((n) => Number(n._attrs.y)));
  assert.ok(Number(rows[0]._attrs.y) > maxLaneY, "placeholder row below every real lane");
});

test("a pending host on a DEAD link says it is reconnecting — and the row leaves on the host's first lanes payload", () => {
  const panel = new TimelinePanel(makeNode("div"));
  const dead: any = Object.assign(synthData(), { pendingHosts: ["TESTHOST"], pendingDead: ["TESTHOST"] });
  panel.data = dead;
  panel.draw();
  assert.equal(pendingTexts(panel.svg)[0].textContent, "reconnecting to TESTHOST…");
  // the retire event is the MERGE dropping the name (its first lanes payload / detach) — nothing here ages it out
  const arrived: any = Object.assign(synthData(), { pendingHosts: [], pendingDead: [] });
  panel.data = arrived;
  panel.draw();
  assert.equal(pendingTexts(panel.svg).length, 0, "gone the moment the merge stops naming it");
  const h1 = svgH(panel.svg);
  panel.data = synthData();   // a payload with no field at all (single-kernel path) is identical
  panel.draw();
  assert.equal(svgH(panel.svg), h1, "no pendingHosts field = no rows = the byte-for-byte single-kernel geometry");
});

test("two pending hosts stack — one row each, in the merge's order", () => {
  const panel = new TimelinePanel(makeNode("div"));
  panel.data = Object.assign(synthData(), { pendingHosts: ["HOSTB", "TESTHOST"], pendingDead: [] });
  panel.draw();
  const rows = pendingTexts(panel.svg);
  assert.deepEqual(rows.map((r) => r._attrs["data-pending-host"]), ["HOSTB", "TESTHOST"]);
  assert.equal(Number(rows[1]._attrs.y) - Number(rows[0]._attrs.y), LANE_GAP, "one lane pitch apart");
});
