// The overall theme setting (2026-08-28, promoting T113's tab-strip pick): one axis of truth
// (`theme`), a derived legacy alias (`chatTabTheme`), one applier (theme.ts) every pane funnels
// through, and a shell-side inline mirror (the landing loads no bundle). Executable where the
// logic is importable; grep-pinned where it lives in a foreign host (gear.js, kernel.py).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { theme, DEFAULT_SETTINGS, loadSettings } from "./settings";
import { applyTheme } from "./theme";

const read = (...p: string[]) => fs.readFileSync(path.resolve(process.cwd(), "..", ...p), "utf8");

test("the setting round-trips: classic default, both yatharth forms opt-in, junk normalizes", () => {
  assert.equal(DEFAULT_SETTINGS.theme, "classic");
  assert.equal(theme("yatharth"), "yatharth");
  assert.equal(theme("yatharth-light"), "yatharth-light");
  assert.equal(theme("classic"), "classic");
  assert.equal(theme(undefined), "classic");
  assert.equal(theme("sparkles"), "classic");
});

test("migration: a pre-`theme` store seeds from the tab-strip pick; the alias stays derived", () => {
  const store = new Map<string, string>();
  (globalThis as any).localStorage = {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => { store.set(k, v); },
  };
  try {
    // an old store that chose the yatharth strip → the theme follows it
    store.set("romp:settings", JSON.stringify({ chatTabTheme: "yatharth" }));
    let s = loadSettings();
    assert.equal(s.theme, "yatharth");
    assert.equal(s.chatTabTheme, "yatharth");
    // an old classic store → classic
    store.set("romp:settings", JSON.stringify({ chatTabTheme: "classic" }));
    s = loadSettings();
    assert.equal(s.theme, "classic");
    // a NEW store rules regardless of a stale alias, and the alias re-derives
    store.set("romp:settings", JSON.stringify({ theme: "yatharth-light", chatTabTheme: "classic" }));
    s = loadSettings();
    assert.equal(s.theme, "yatharth-light");
    assert.equal(s.chatTabTheme, "yatharth", "the alias derives from theme, never the reverse");
  } finally {
    delete (globalThis as any).localStorage;
  }
});

test("applyTheme is executable and toggles exactly the two classes", () => {
  const classes = new Set<string>();
  const doc = { body: { classList: { toggle: (c: string, on: boolean) => { if (on) classes.add(c); else classes.delete(c); } } } } as unknown as Document;
  applyTheme(doc, { ...DEFAULT_SETTINGS, theme: "yatharth-light" });
  assert.deepEqual([...classes].sort(), ["chat-theme-yatharth", "theme-light"]);
  applyTheme(doc, { ...DEFAULT_SETTINGS, theme: "yatharth" });
  assert.deepEqual([...classes].sort(), ["chat-theme-yatharth"]);
  applyTheme(doc, { ...DEFAULT_SETTINGS, theme: "classic" });
  assert.deepEqual([...classes], []);
});

test("every pane document funnels through the applier (boot + settings changes)", () => {
  for (const f of ["render.ts", "feed.ts", "fleet.ts", "timeline-main.ts"]) {
    const src = read("ui", "webview", f);
    assert.match(src, /applyTheme\(document, /, f + " applies the theme");
  }
});

test("the shell's inline mirror states the same classes and the same migration (it loads no bundle)", () => {
  const K = read("kernel", "kernel.py");
  assert.ok(K.includes("classList.toggle('chat-theme-yatharth',t!=='classic')"), "shell strip class mirrors theme.ts");
  assert.ok(K.includes("classList.toggle('theme-light',t==='yatharth-light')"), "shell light class mirrors theme.ts");
  assert.ok(K.includes("s.chatTabTheme==='yatharth'?'yatharth':'classic'"), "shell migration mirrors loadSettings");
  assert.ok(K.includes("t==='yatharth-light'?'#F1EAE2':'#1e1e1e'"), "the OS chrome color follows the theme");
  // gear.js carries the same migration mirror (its load() reads the raw store)
  const G = read("ui", "webview", "gear.js");
  assert.match(G, /return s\.chatTabTheme === 'yatharth' \? 'yatharth' : 'classic';/);
});

test("adopted .romp-tl-tip rules are self-contained: every var() carries its literal fallback", () => {
  // the timeline ADOPTS every rule mentioning .romp-tl-tip into the topmost document (which
  // defines none of this sheet's tokens) — a fallback-less var() resolves to nothing there
  // (the classic browser dashboard lost the tip's faint ink exactly this way)
  const css = read("ui", "webview", "timeline-pane.css");
  const rules = css.match(/[^{}]*\.romp-tl-tip[^{}]*\{[^}]*\}/g) || [];
  assert.ok(rules.length >= 8, `found only ${rules.length} tip rules — selector drifted?`);
  for (const r of rules) {
    const bare = r.slice(r.indexOf("{")).match(/var\(--[a-z-]+\)/g) || [];
    assert.deepEqual(bare, [], `fallback-less var() in an adopted tip rule: ${r.trim().slice(0, 70)}`);
  }
});
