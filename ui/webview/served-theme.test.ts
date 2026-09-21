// SERVED-VALUE discipline for chrome tokens (T151, closing the T141 verification gap): every
// kernel-served page inlines THEME_CSS (kernel/kernel.py), which DEFINES the --vscode-* variables
// — so a var()'s fallback is dead code in the browser, and a token choice must be validated
// against the SERVED definitions, not the fallback path (the T141 probe validated fallbacks and
// shipped a false 'already dark' claim; the user saw #252526). This test resolves the chrome
// surfaces' background tokens under the actual THEME_CSS map.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const read = (...p: string[]) => fs.readFileSync(path.resolve(process.cwd(), "..", ...p), "utf8");
const KERNEL = read("kernel", "kernel.py");
const STYLES = read("ui", "webview", "styles.css");
const FEED = read("ui", "webview", "feed.css");
const STRIP = read("ui", "webview", "strip.css");

// the served var map: THEME_CSS's :root block, plus each sheet's own :root definitions
function varsOf(src: string): Map<string, string> {
  const m = new Map<string, string>();
  for (const hit of src.matchAll(/(--[a-zA-Z-]+)\s*:\s*([^;}]+)[;}]/g)) m.set(hit[1], hit[2].trim());
  return m;
}
const themeAt = KERNEL.indexOf('THEME_CSS = """');
assert.ok(themeAt > 0, "THEME_CSS must exist in the kernel");
const THEME = KERNEL.slice(themeAt, KERNEL.indexOf('"""', themeAt + 20));
const SERVED = varsOf(THEME);

function resolve(expr: string, sheets: Map<string, string>[]): string {
  // resolve var(--x, fb) chains: the SERVED definition wins (it exists on the page), else fallback
  let out = expr.trim();
  for (let i = 0; i < 8; i++) {
    const m = out.match(/^var\((--[a-zA-Z-]+)\s*(?:,\s*(.*))?\)$/s);
    if (!m) return out;
    const defined = SERVED.get(m[1]) ?? sheets.map((s) => s.get(m[1])).find(Boolean);
    out = (defined ?? m[2] ?? "").trim();
  }
  return out;
}
const bgOf = (src: string, sel: string): string => {
  const at = src.indexOf(sel);
  assert.ok(at >= 0, sel + " rule exists");
  const block = src.slice(at, src.indexOf("}", at));
  const m = [...block.matchAll(/background:\s*([^;]+);/g)].pop();
  assert.ok(m, sel + " declares a background");
  return m![1].trim();
};

test("THEME_CSS defines the trap: sideBar/widget tokens are LIGHTER than the page dark", () => {
  assert.equal(SERVED.get("--vscode-editor-background"), "#1e1e1e");
  assert.equal(SERVED.get("--vscode-sideBar-background"), "#252526");
  assert.equal(SERVED.get("--vscode-editorWidget-background"), "#252526");
});

test("the strip, the feed foot, and the network strip all resolve to the page dark WHEN SERVED", () => {
  const sheets = [varsOf(STYLES.slice(0, STYLES.indexOf("* { box-sizing")))];
  assert.equal(resolve(bgOf(STYLES, "#tabbar {"), sheets), "#1e1e1e", "#tabbar under THEME_CSS");
  const feedSheets = [varsOf(FEED.slice(0, 4000))];
  assert.equal(resolve(bgOf(FEED, "#feed-foot {"), feedSheets), "#1e1e1e", "#feed-foot under THEME_CSS");
  assert.equal(resolve(bgOf(STRIP, "#romp-strip {"), []), "#1e1e1e", "#romp-strip under THEME_CSS");
});

test("no chrome background rides the sideBar token, and the notice chrome is tokenized", () => {
  for (const [name, src] of [["styles.css", STYLES], ["feed.css", FEED], ["strip.css", STRIP]] as const) {
    assert.ok(!/background:\s*var\(--vscode-sideBar-background/.test(src),
      name + ": sideBar-background is #252526 on every served page — never a chrome plane");
  }
  assert.ok(!/background:\s*#252526/.test(FEED), "feed notice chrome references the token, not the hex");
  assert.ok(!/background:\s*#333[;\s]/.test(FEED), "the jl-switch rest is tokenized too");
});

test("the missed family rests are the one button rest now (transparent + the feed hairline)", () => {
  for (const sel of [".picker-be-opt {", ".picker-action {", ".path-full-retry {"]) {
    const at = STYLES.indexOf(sel);
    const block = STYLES.slice(at, STYLES.indexOf("}", at));
    assert.match(block, /background: transparent/, sel);
    assert.match(block, /var\(--card-border\)/, sel);
  }
  for (const [src, name] of [[STYLES, "styles"], [FEED, "feed"]] as const) {
    const at = src.indexOf(".fileview-btn {");
    const block = src.slice(at, src.indexOf("}", at));
    assert.match(block, /background: transparent/, ".fileview-btn (" + name + ")");
  }
  const fq = FEED.slice(FEED.indexOf(".fq-send {"), FEED.indexOf("}", FEED.indexOf(".fq-send {")));
  assert.match(fq, /background: transparent/);
});
