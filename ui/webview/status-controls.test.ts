// THE SHARED STATUS CONTROLS, EXECUTED (T415 part two): the module render.ts and the settings card both draw the status line's
// controls through. Against a stub document: with no hooks the badges are inert (no click, no tip) and read the demo's words and
// tints; with the chat's hooks a click reaches the picker; the battery fills to its percentage in the colour it is given, hides
// without one, and runs the compaction scan through the chat's sweep hook only. The colormap arithmetic equals the kernel's, and
// the demo's tints are the kernel's rank rule on the given stops. Synthetic values only.
import { test } from "node:test";
import * as assert from "node:assert/strict";

type N = any;
function walk(root: N, f: (x: N) => void) { f(root); for (const k of root.kids || []) if (k.tag !== "#text") walk(k, f); }
function mk(tag: string): N {
  const n: N = {
    tag, attrs: {} as Record<string, string>, kids: [] as N[], style: {} as Record<string, string>, listeners: {} as Record<string, Function[]>,
    dataset: {} as Record<string, string>, title: "", id: "", _cls: new Set<string>(), _html: "", parentNode: null as N,
    get className(): string { return Array.from(n._cls).join(" "); }, set className(v: string) { n._cls = new Set(String(v).split(/\s+/).filter(Boolean)); },
    classList: { add: (...a: string[]) => a.forEach((c) => n._cls.add(c)), remove: (...a: string[]) => a.forEach((c) => n._cls.delete(c)),
      toggle: (c: string, f?: boolean) => { if (f === undefined ? !n._cls.has(c) : f) n._cls.add(c); else n._cls.delete(c); return n._cls.has(c); }, contains: (c: string) => n._cls.has(c) },
    get textContent(): string { return n.kids.map((k: N) => k.tag === "#text" ? k.text : k.textContent).join(""); },
    set textContent(v: string) { n.kids = v ? [{ tag: "#text", text: v }] : []; },
    get innerHTML(): string { return n._html; }, set innerHTML(v: string) { n._html = v; n.kids = []; },
    get children(): N[] { return n.kids.filter((k: N) => k.tag !== "#text"); },
    get firstElementChild(): N { return n.children[0] || null; },
    setAttribute(k: string, v: string) { n.attrs[k] = String(v); }, getAttribute(k: string) { return k in n.attrs ? n.attrs[k] : null; },
    removeAttribute(k: string) { delete n.attrs[k]; },
    appendChild(c: N) { c.parentNode = n; n.kids.push(c); return c; },
    replaceChildren(...cs: N[]) { n.kids = []; for (const c of cs) n.appendChild(c); },
    addEventListener(t: string, fn: Function) { (n.listeners[t] = n.listeners[t] || []).push(fn); },
    dispatch(t: string) { const e = { stopped: false, stopPropagation() { this.stopped = true; }, preventDefault() { /* noop */ } }; for (const fn of n.listeners[t] || []) fn.call(n, e); return e; },
    /** class selectors only (".a", ".a .b" as a descendant walk), what the renderer asks for */
    querySelectorAll(sel: string): N[] { const parts = sel.trim().split(/\s+/); let set: N[] = [n]; for (const part of parts) { const cls = part.slice(1); const next: N[] = []; for (const root of set) walk(root, (x) => { if (x !== root && x._cls && x._cls.has(cls)) next.push(x); }); set = next; } return set; },
    querySelector(sel: string): N { return n.querySelectorAll(sel)[0] || null; },
  };
  return n;
}
const g = globalThis as any;
g.document = { createElement: mk, createTextNode: (t: string) => ({ tag: "#text", text: t }), body: mk("body"), addEventListener() { /* tips */ }, querySelector: () => null };
g.window = { addEventListener() { /* tips */ }, innerWidth: 1200, innerHeight: 800 };
// eslint-disable-next-line @typescript-eslint/no-var-requires
const SC = require("./status-controls");
const AURORA: Array<[number, number, number]> = [[84, 178, 4], [0, 180, 115], [35, 175, 156], [66, 169, 176], [25, 168, 201], [14, 164, 227], [74, 155, 241], [113, 145, 244], [144, 136, 240]];
const rgb = (c: number[]) => `rgb(${c[0]},${c[1]},${c[2]})`;

test("rampOn is the kernel's ramp: the ends, an interior sample, and the clamp", () => {
  assert.deepEqual(SC.rampOn(0, AURORA), [84, 178, 4]); assert.deepEqual(SC.rampOn(1, AURORA), [144, 136, 240]); assert.deepEqual(SC.rampOn(7, AURORA), [144, 136, 240], "clamped");
  // 0.62 on nine stops: x = 4.96, between stop 4 and stop 5 at 0.96
  assert.deepEqual(SC.rampOn(0.62, AURORA), [Math.round(25 + (14 - 25) * 0.96), Math.round(168 + (164 - 168) * 0.96), Math.round(201 + (227 - 201) * 0.96)]);
});

test("the rank rule: families descending, efforts ascending, the first family word the model name contains; unknown = null", () => {
  assert.equal(SC.modelRank("Opus 5"), 2 / 3); assert.equal(SC.modelRank("claude-fable-5-1"), 1); assert.equal(SC.modelRank("haiku"), 0); assert.equal(SC.modelRank("gpt-5"), null);
  assert.equal(SC.effortRank("low"), 0); assert.equal(SC.effortRank("high"), 0.4); assert.equal(SC.effortRank(" ULTRACODE "), 1); assert.equal(SC.effortRank("turbo"), null);
  const d = SC.demoStatus(AURORA);
  assert.deepEqual([d.mode, d.model, d.effort, d.ctx], ["auto", "Opus 5", "high", "62%"]);
  assert.deepEqual(d.modelColor, SC.rampOn(2 / 3, AURORA)); assert.deepEqual(d.effortColor, SC.rampOn(0.4, AURORA)); assert.deepEqual(d.ctxColor, SC.rampOn(0.62, AURORA));
});

test("with no hooks the badges are the line's DOM, inert: mode, model, effort in order, the words and the tints, no click, no tip", () => {
  const meta = mk("span"); meta.className = "spinner-meta";
  const st = SC.demoStatus(AURORA);
  SC.syncMetaControls(meta, st, null, {});
  const btns = meta.querySelectorAll(".meta-btn");
  assert.deepEqual(btns.map((b: N) => b.dataset.kind), ["mode", "model", "effort"], "no fast badge: the demo reports none");
  assert.deepEqual(btns.map((b: N) => b.querySelector(".meta-label").textContent), ["Auto", "Opus 5", "high"]);
  assert.deepEqual(btns.map((b: N) => b.querySelector(".meta-label").style.color), ["", rgb(st.modelColor), rgb(st.effortColor)], "mode untinted; model and effort by rank");
  assert.ok(btns[0].querySelector(".mode-ico") && btns[0].querySelector(".mode-ico").innerHTML.includes("<svg"), "the permission glyph beside its word");
  for (const b of btns) { assert.equal((b.listeners.click || []).length, 0, b.dataset.kind + ": no click"); assert.equal(b._tipText, undefined, b.dataset.kind + ": no tip"); assert.equal(b.querySelector(".meta-caret").textContent, "▾"); }
  SC.syncMetaControls(meta, st, null, {});
  assert.equal(meta.querySelectorAll(".meta-btn").length, 3, "a second sync refreshes in place");
});

test("with the chat's hooks a click reaches the picker with the kind, the badge and the session; the pending hook shows the dots", () => {
  const meta = mk("span"); const presses: any[] = [];
  const hooks = { onPress: (kind: string, btn: N, forSid: string | null) => presses.push([kind, btn.dataset.kind, forSid]), pending: (kind: string) => kind === "model" };
  SC.syncMetaControls(meta, { mode: "plan", model: "Opus 5", effort: "max" }, "s-1", hooks);
  const btns = meta.querySelectorAll(".meta-btn");
  const e = btns[2].dispatch("click");
  assert.deepEqual(presses, [["effort", "effort", "s-1"]]); assert.ok(e.stopped, "the click is the badge's");
  assert.ok(btns[1].querySelector(".meta-dots"), "model pending: the switching dots in the badge"); assert.equal(btns[1]._cls.has("meta-pending"), true);
  assert.equal(btns[2].querySelector(".meta-label").textContent, "max"); assert.equal(btns[0].querySelector(".meta-label").textContent, "Plan");
  assert.equal(typeof btns[0]._tipText, "string", "with a picker the badge wears its tip");
});

test("the battery: filled to its percentage in the colour given, the number inside; hidden without a percentage; the scan only through the sweep hook", () => {
  const bar = SC.ctxBar();
  assert.equal(bar.id, "", "no id from the module: the chat's wrapper names its one live bar");
  assert.deepEqual(bar.children.map((c: N) => c.className), ["ctx-fill", "ctx-text", "ctx-scan"]);
  assert.equal((bar.listeners.click || []).length, 0, "no click without the chat's hook");
  SC.setCtxBar(bar, "62%", false, [20, 168, 208], false);
  assert.equal(bar.querySelector(".ctx-fill").style.width, "62%"); assert.equal(bar.querySelector(".ctx-fill").style.background, "rgb(20,168,208)"); assert.equal(bar.querySelector(".ctx-text").textContent, "62%");
  assert.equal(bar.style.display, "");
  SC.setCtxBar(bar, "100%", false, [1, 2, 3], true); assert.equal(bar.querySelector(".ctx-text").textContent, "100%+", "past the window: the plus");
  SC.setCtxBar(bar, undefined, false, null, false); assert.equal(bar.style.display, "none", "no percentage: hidden");
  const swept: any[] = [];
  SC.setCtxBar(bar, "40%", true, null, false, (scan: N, fresh: boolean) => swept.push([scan.className, fresh]));
  assert.deepEqual(swept, [["ctx-scan", true]], "compacting: the chat's sweep, phase-synced on a fresh scan"); assert.equal(bar._cls.has("ctx-compacting"), true);
  SC.setCtxBar(bar, "40%", true, null, false, (scan: N, fresh: boolean) => swept.push([scan.className, fresh]));
  assert.deepEqual(swept[1], ["ctx-scan", false], "a reused scan keeps its phase");
  const clicked: N[] = []; const live = SC.ctxBar((b: N) => clicked.push(b)); live.dispatch("click"); assert.equal(clicked[0], live, "the chat's hook gets the bar");
});
