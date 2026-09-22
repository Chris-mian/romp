// The session tab's hover popover colours its Model and Effort VALUES with the colour the chat footer's chips
// wear for that session (T372, the user 2026-09-12: the association learned on the footer is reproduced there).
// One helper, metaColor, serves both surfaces, so the two cannot drift: this lifts showTabTip, metaButton and the
// footer's label tinting from render.ts, executes them against a small DOM stand-in with the REAL tone helpers
// (ctx-color.ts), and compares the popover's value spans with the footer chip's computed colour, in the dark theme
// and in the light theme (where readableRgb re-encodes the kernel's dark-tuned RGB). Labels stay dim. The lifted
// slices add no window listener (the harness slices elsewhere count them).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { createRequire } from "node:module";
import { pickTone, readableRgb } from "./ctx-color";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const MODULE = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "status-controls.ts"), "utf8");   // the status line's controls moved here from render.ts (T415 part two)
const require = createRequire(__filename);
const esbuild = require("esbuild");

// a lifted function: from its declaration to the closing brace at column 0
function lift(name: string): string {
  const at = RENDER.indexOf("function " + name + "(");
  assert.ok(at >= 0, name + " declared");
  const end = RENDER.indexOf("\n}\n", at);
  return RENDER.slice(at, end + 3);
}
/** the same, from status-controls.ts (the badges and their tint helper moved there, T415 part two), the export keyword dropped */
function liftMod(name: string): string {
  const at = MODULE.indexOf("export function " + name + "(");
  assert.ok(at >= 0, name + " exported by status-controls.ts");
  const end = MODULE.indexOf("\n}\n", at);
  return MODULE.slice(at + "export ".length, end + 3);
}

class El {
  tagName: string; className = ""; textContent = ""; innerHTML = ""; children: El[] = []; style: Record<string, string> = {};
  dataset: Record<string, string> = {}; attrs = new Map<string, string>(); listeners: string[] = [];
  constructor(tag: string) { this.tagName = tag; }
  get classList() { const self = this; return { toggle: (c: string, on?: boolean) => { const has = self.className.split(" ").includes(c); const want = on === undefined ? !has : on; const parts = self.className.split(" ").filter(Boolean).filter((x) => x !== c); if (want) parts.push(c); self.className = parts.join(" "); }, contains: (c: string) => self.className.split(" ").includes(c), add: (c: string) => self.classList.toggle(c, true), remove: (c: string) => self.classList.toggle(c, false) }; }
  appendChild(c: El): El { this.children.push(c); return c; }
  append(...cs: El[]): void { for (const c of cs) this.children.push(c); }
  replaceChildren(...cs: El[]): void { this.children = [...cs]; }
  setAttribute(k: string, v: string): void { this.attrs.set(k, v); }
  getAttribute(k: string): string | null { return this.attrs.get(k) ?? null; }
  addEventListener(k: string): void { this.listeners.push(k); }
  querySelector(sel: string): El | null { const cls = sel.replace(/^\./, ""); const walk = (n: El): El | null => { for (const c of n.children) { if (c.className.split(" ").includes(cls)) return c; const d = walk(c); if (d) return d; } return null; }; return walk(this); }
  querySelectorAll(sel: string): El[] { const cls = sel.replace(/^\./, ""); const out: El[] = []; const walk = (n: El) => { for (const c of n.children) { if (c.className.split(" ").includes(cls)) out.push(c); walk(c); } }; walk(this); return out; }
  get firstElementChild(): El | null { return this.children[0] ?? null; }
}
const body = new El("body");   // the theme is the body's class (ctx-color's isLightTheme / nonClassic read it live)
const bodyClasses = { clear: () => { body.className = ""; }, add: (c: string) => body.classList.add(c) };
(globalThis as any).document = { createElement: (t: string) => new El(t), body, getElementById: () => null, addEventListener: () => {}, activeElement: null };
(globalThis as any).window = { addEventListener: () => {}, innerWidth: 1200, innerHeight: 800 };

// the slices: the popover builder, the footer's button and its label tinting, and the colour helper they share
const PRELUDE = `
const el = (tag, cls) => { const e = document.createElement(tag); if (cls) e.className = cls; return e; };
const prettyMode = (m) => m; const backendLabel = (b) => b; const authFellTo = () => ""; const ctxBar = () => el("div"); const setCtxBar = () => {};
const ledgers = new Map(); let draggedId = null; let tabTipEl = null; const sessions = new Map();
const setTip = (a: any, text: string) => { a._tipText = text; }; const toggleMetaMenu = () => {}; const modeIconSvg = () => ""; const riskyMode = () => false;
const prettyFast = (f) => f; const metaCurrent = (kind, st) => kind === "model" ? st.model : effortBadgeText(st); const fastAvailable = () => false;   // effortBadgeText is lifted from the module below (2026-09-16)
const metaDots = () => el("span", "meta-dots"); const isMetaPending = () => false;
const needsYouPhrase = (n) => n > 1 ? n + " things need you" : n === 1 ? "1 thing needs you" : "needs you";
`;
const SRC = PRELUDE + liftMod("metaColor") + liftMod("effortBadgeText") + lift("showTabTip") + liftMod("metaButton") + liftMod("syncMetaControls")
  + "\nreturn { showTabTip, metaButton, metaColor, syncMetaControls };";
const js = esbuild.transformSync(SRC, { loader: "ts", format: "cjs", target: "es2020" }).code;
const mod = new Function("pickTone", "readableRgb", "document", "window", js)(pickTone, readableRgb, (globalThis as any).document, (globalThis as any).window);

const status = { state: "ready", sinceEpoch: null, mode: "auto", model: "claude-opus-5", effort: "high", backend: "sdk",
  modelColor: [156, 210, 255], effortColor: [229, 165, 10], modelTone: [120, 200, 240], effortTone: [240, 180, 40] };
const session = { id: "11111111-2222-3333-4444-555555555555", name: "web", cwd: "/tmp/notes-api", status } as any;

const popoverValues = () => {
  mod.showTabTip(new El("div"), session);
  const tip = body.children[body.children.length - 1];
  const rows = tip.children.filter((r) => r.className === "tab-tip-row");
  const byLabel: Record<string, El> = {};
  for (const r of rows) byLabel[r.children[0].textContent] = r.children[1];
  return byLabel;
};
const footerColours = () => {
  const meta = new El("div");
  mod.syncMetaControls(meta, status, null, {});   // no hooks: the badges as a preview draws them; the tints are what this test reads
  const out: Record<string, string> = {};
  for (const b of meta.querySelectorAll(".meta-btn")) out[b.dataset.kind] = b.querySelector(".meta-label")!.style.color || "";
  return out;
};

for (const theme of ["dark", "light"] as const) {
  test(`${theme} theme: the popover's Model and Effort values wear exactly the footer chip's colour; the other values and every label stay plain`, () => {
    bodyClasses.clear();
    if (theme === "light") bodyClasses.add("theme-light");
    const v = popoverValues();
    const f = footerColours();
    assert.match(f.model, /^rgb\(\d+,\d+,\d+\)$/, "the footer tints the model: " + JSON.stringify(f));
    assert.match(f.effort, /^rgb\(\d+,\d+,\d+\)$/, "…and the effort");
    assert.equal(v["Model"].style.color, f.model, "the popover's Model value is the footer's model colour");
    assert.equal(v["Effort"].style.color, f.effort, "the popover's Effort value is the footer's effort colour");
    assert.equal(v["Model"].style.color, mod.metaColor("model", status), "…through the one helper");
    assert.equal(v["Effort"].style.color, mod.metaColor("effort", status));
    assert.equal(v["Mode"].style.color ?? "", "", "the mode is untinted on the footer, so it stays plain here");
    assert.equal(v["Backend"].style.color ?? "", "", "the backend carries no tone");
    assert.equal(v["📁"].style.color ?? "", "", "the directory is plain");
    const tip = body.children[body.children.length - 1];
    for (const r of tip.children) if (r.className === "tab-tip-row") assert.equal(r.children[0].style.color ?? "", "", "labels stay dim: " + r.children[0].textContent);
    assert.equal(v["Model"].className, "tab-tip-v", "the value span keeps its class: the colour is inline, like the footer's");
  });
}

test("the light theme re-encodes the kernel's dark-tuned RGB on BOTH surfaces alike, so the two differ from the dark theme together", () => {
  bodyClasses.clear();
  const dark = { pop: popoverValues()["Model"].style.color, foot: footerColours().model };
  bodyClasses.add("theme-light");
  const light = { pop: popoverValues()["Model"].style.color, foot: footerColours().model };
  bodyClasses.clear();
  assert.notEqual(dark.pop, light.pop, "the light theme re-encodes: " + JSON.stringify({ dark, light }));
  assert.equal(dark.pop, dark.foot); assert.equal(light.pop, light.foot);
});

test("a status without colours (an older kernel) leaves the values plain, as the footer leaves its chips", () => {
  bodyClasses.clear();
  const bare = { ...status, needsYou: true, needsYouCount: 3, modelColor: undefined, effortColor: undefined, modelTone: undefined, effortTone: undefined };
  mod.showTabTip(new El("div"), { ...session, status: bare });
  const tip = body.children[body.children.length - 1];
  for (const r of tip.children) if (r.className === "tab-tip-row" && r.children[0].textContent !== "Mail" && r.children[0].textContent !== "") assert.equal(r.children[1].style.color ?? "", "", r.children[0].textContent);   // the Mail check wears the accent and its held sub-line the dim by design (2026-09-16), not a footer tone
  // the Needs-you row is now among the plain values, not exempt: its magenta value tone was dropped (under the 4.5:1
  // floor on the raised surface, PR 2023), so the loop above covers it; assert it explicitly beside Mail's exemption.
  const nyRow = tip.children.find((r) => r.className === "tab-tip-row" && r.children[0].textContent === "Needs you");
  assert.ok(nyRow, "the Needs-you row is present in the fixture");
  assert.equal(nyRow!.children[1].style.color ?? "", "", "the Needs-you value inherits the foreground, no tone");
  const meta = new El("div"); mod.syncMetaControls(meta, bare, null, {});
  for (const b of meta.querySelectorAll(".meta-btn")) assert.equal(b.querySelector(".meta-label")!.style.color ?? "", "");
});

test("at source: the rows carry the colour as a third member, the value span takes it inline, and metaColor is the footer's helper", () => {
  const stt = RENDER.slice(RENDER.indexOf("function showTabTip("), RENDER.indexOf("\n}\n", RENDER.indexOf("function showTabTip(")));
  assert.match(stt, /const rows: Array<\[string, string, string\?\]> = \[\];/);
  assert.doesNotMatch(stt, /ve\.setAttribute\("aria-label"/, "no inert aria-label on the role-less value span (PR 2033 review)");
  assert.match(stt, /rows\.push\(\["Model", s\.status\.model, metaColor\("model", s\.status\)\]\);/);
  assert.match(stt, /rows\.push\(\["Effort", s\.status\.effort, metaColor\("effort", s\.status\)\]\);/);
  assert.match(stt, /if \(color\) ve\.style\.color = color;/);
  assert.doesNotMatch(stt, /addEventListener\("(resize|keydown|mousedown)"/, "no window listener inside the lifted slice");
  const sync = MODULE.slice(MODULE.indexOf("function syncMetaControls("), MODULE.indexOf("\n}\n", MODULE.indexOf("function syncMetaControls(")));
  assert.match(sync, /label\.style\.color = showDots \? "" : metaColor\(kind, st\);/, "the footer tints through the same helper");
});

test("the Mail row is a glance: an accent check mark when mail is on, the bare word off or held when not, a dim sub-line for the held states alone", () => {
  // the user 2026-09-16, with the session info rows in view: the row read "off: this session neither sends nor receives
  // peer mail" inline; now the state alone. Round two of PR 1803: this rich tip is pointer-inert (tip.ts), so a value tip
  // could never show; the reasons live in the Sessions panel's mail mark title, and the two held states, a session that
  // needs repair, get one dim sub-line under the row; off gets none
  const rowsOf = (extra: any) => {
    mod.showTabTip(new El("div"), { ...session, ...extra });
    const tip = body.children[body.children.length - 1];
    return tip.children.filter((r) => r.className === "tab-tip-row").map((r) => ({ k: r.children[0].textContent, v: r.children[1] }));
  };
  type Row = { k: string; v: any };
  const mailOf = (rows: Row[]) => rows.find((r) => r.k === "Mail")!.v;
  const subOf = (rows: Row[]) => { const i = rows.findIndex((r) => r.k === "Mail"); return rows[i + 1] && rows[i + 1].k === "" ? rows[i + 1].v : null; };
  const on = rowsOf({ postalServiceOff: false, mailOffWhy: "" });
  assert.equal(mailOf(on).textContent, "\u2713", "on: the check mark alone"); assert.equal(mailOf(on).style.color, "var(--accent)", "on the accent");
  assert.equal(subOf(on), null, "no sub-line when mail is on"); assert.equal((mailOf(on) as any)._tipText, undefined, "no tip inside the pointer-inert tab tip");
  const off = rowsOf({ postalServiceOff: true, mailOffWhy: "" });
  assert.equal(mailOf(off).textContent, "off"); assert.equal(mailOf(off).style.color ?? "", "", "the word, untinted");
  assert.equal(subOf(off), null, "off explains nothing here: the Sessions panel's mail mark does");
  const held = rowsOf({ postalServiceOff: true, mailOffWhy: "flags" });
  assert.equal(mailOf(held).textContent, "held", "held reads at a glance");
  assert.equal(subOf(held)!.textContent, "its settings file cannot be read; mail waits until it is written again"); assert.equal(subOf(held)!.style.color, "var(--dim)", "dim, under the row");
  const unread = rowsOf({ postalServiceOff: true, mailOffWhy: "unreadable" });
  assert.equal(mailOf(unread).textContent, "held"); assert.equal(subOf(unread)!.textContent, "its record cannot be read; mail waits until it is repaired");
  const thread = rowsOf({ postalServiceOff: true, mailOffWhy: "thread" });
  assert.equal(mailOf(thread).textContent, "off"); assert.equal(subOf(thread), null);
});

// The Needs-you row (PR 2017; the first contributor's post-merge review of PR 2023, 2026-09-22, MEDIUM): showTabTip's only pointer route to the count phrase, the
// dot's own title being inert under pointer-events:none. Red-first: with the `if (s.status.needsYou)` block deleted from
// showTabTip, rowFor returns null, so the PRESENCE assertions below fail (the absence assertion expects that null and stays green).
test("the Needs-you row: showTabTip carries the count as a short untinted value with no inert aria-label, and is absent when the session does not need you", () => {
  bodyClasses.clear();
  const rowFor = (st: any): El | null => {
    mod.showTabTip(new El("div"), { id: "s", name: "web", cwd: "/tmp/notes-api", status: st } as any);
    const tip = body.children[body.children.length - 1];
    for (const r of tip.children) if (r.className === "tab-tip-row" && r.children[0].textContent === "Needs you") return r.children[1];
    return null;
  };
  assert.equal(rowFor({ state: "ready", sinceEpoch: null }), null, "no Needs-you row when the session does not need you");
  for (const [n, short] of [[1, "1 thing"], [3, "3 things"]] as const) {
    const v = rowFor({ state: "working", sinceEpoch: null, needsYou: true, needsYouCount: n });
    assert.ok(v, n + ": the Needs-you row is present");
    assert.equal(v!.textContent, short, n + ": the value drops the redundant 'need you' (the key already says the state)");
    assert.equal(v!.style.color ?? "", "", n + ": the value inherits the foreground, no magenta tone (under the 4.5:1 floor on the raised surface, PR 2023)");
    assert.equal(v!.getAttribute("aria-label"), null, n + ": no inert aria-label on the role-less value span (the phrase lives on the badge dot and the cold title)");
  }
  const v0 = rowFor({ state: "working", sinceEpoch: null, needsYou: true });
  assert.ok(v0, "needsYou with no count: still a row");
  assert.equal(v0!.textContent, "", "no count: the value is empty (the key says the state)");
  assert.equal(v0!.style.color ?? "", "", "…untinted");
  assert.equal(v0!.getAttribute("aria-label"), null, "…and no inert aria-label");
});
