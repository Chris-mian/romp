// The command palette (Cmd/Ctrl+P) + session quick-switcher hotkey (Cmd/Ctrl+O), and the
// one-modal-treatment conversions that came with them (the user 2026-08-08). Source-level
// pins (no jsdom for the DOM pieces); fuzzy.ts and commands.ts have real unit tests, and the
// kernel-side shell CSS/wiring is pinned in tests/test_kernel.py.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const read = (f: string) => fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", f), "utf8");
const PALETTE = read("palette.ts");
const MAIN = read("palette-main.ts");
const RENDER = read("render.ts");
const CSS = read("styles.css");
const GEAR_CSS = read("gear.css");
const GEAR = read("gear.js");
const ESBUILD = fs.readFileSync(path.resolve(process.cwd(), "esbuild.js"), "utf8");

// ── the palette overlay wears the one modal treatment ──────────────────────────────────────
test("palette backdrop is the standard centered 0.55 dim, above every shell panel", () => {
  assert.match(PALETTE, /#rpal-back\{position:fixed;inset:0;z-index:300;display:flex;align-items:flex-start;justify-content:center;/);
  assert.match(PALETTE, /background:rgba\(0,0,0,0\.55\)/);
  assert.match(PALETTE, /#rpal-back\[hidden\]\{display:none\}/);
});

test("palette keyboard model: arrows wrap, Enter runs, Esc closes, backdrop click closes", () => {
  assert.match(PALETTE, /e\.key === "ArrowDown"[\s\S]*?\(active \+ 1\) % rows\.length/);
  assert.match(PALETTE, /e\.key === "ArrowUp"[\s\S]*?\(active - 1 \+ rows\.length\) % rows\.length/);
  assert.match(PALETTE, /e\.key === "Enter"[\s\S]*?run\(r\.cmd\)/);
  assert.match(PALETTE, /e\.key === "Escape"[\s\S]*?close\(\)/);
  assert.match(PALETTE, /if \(e\.target === back\) close\(\);/);
});

test("running a command closes the palette FIRST so its own modal never lands underneath", () => {
  assert.match(PALETTE, /function run\(cmd: PaletteCommand\): void \{\s*\n\s*close\(\);[\s\S]*?cmd\.run\(\);/);
});

// ── the shell boot: hotkeys reach every pane, commands call the rail's own code paths ──────
test("Cmd/Ctrl+O opens the quick switcher and Cmd/Ctrl+P toggles the palette, claimed with preventDefault", () => {
  assert.match(MAIN, /if \(!\(e\.metaKey \|\| e\.ctrlKey\) \|\| e\.altKey \|\| e\.shiftKey \|\| e\.repeat\) return;/);
  assert.match(MAIN, /if \(k === "o"\) \{ e\.preventDefault\(\); e\.stopPropagation\(\); palette\.close\(\); openSwitcher\(\); \}/);
  assert.match(MAIN, /else if \(k === "p"\) \{ e\.preventDefault\(\); e\.stopPropagation\(\); palette\.toggle\(\); \}/);
});

test("key wiring mirrors the Alt+Arrow pane nav: capture on the shell doc AND every pane doc, re-wired on load", () => {
  assert.match(MAIN, /document\.addEventListener\("keydown", onKey, true\);/);
  assert.match(MAIN, /\["f-chat", "f-fleet", "f-feed", "f-timeline"\]\.forEach/);
  assert.match(MAIN, /f\.contentDocument\.addEventListener\("keydown", onKey, true\)/);
  assert.match(MAIN, /f\.addEventListener\("load", wire\);\s*\n\s*wire\(\);/);
});

test("the switcher IS the existing picker (one code path), revealed and toggled via the chat pane", () => {
  assert.match(MAIN, /__rompPaneToggle\("chat", true\)/);
  assert.match(MAIN, /postMessage\(\{ type: "openPicker", toggle: true \}, "\*"\)/);
});

test("built-in commands call the same globals the rail buttons use", () => {
  for (const g of ["__rompOpenErrs", "__rompOpenNet", "__rompUsagePanel", "__rompRestart", "__rompPaneToggle"]) {
    assert.ok(MAIN.includes(g), g + " missing from palette-main.ts");
  }
});

test("palette-main is bundled for the shell page", () => {
  assert.match(ESBUILD, /"\.\.\/ui\/webview\/palette-main\.ts"/);
});

// ── the chat page's own Cmd+O (standalone + VS Code webview, and first-responder in the shell) ──
test("render.ts claims Cmd/Ctrl+O at window capture and toggles the picker", () => {
  assert.match(RENDER, /\(e\.key \|\| ""\)\.toLowerCase\(\) !== "o"\) return;/);
  assert.match(RENDER, /if \(pickerVisible\(\)\) closePicker\(\); else openPicker\(\);/);
});

test("the openPicker message accepts toggle:true (the hotkey form relayed by the shell)", () => {
  assert.match(RENDER, /if \(m\.toggle && pickerVisible\(\)\) closePicker\(\);\s*\n\s*else openPicker\(!!m\.pick, m\.prompt, !!m\.allowNew\);/);
});

// ── the black-out fixes: every layer under a lifted overlay's backdrop goes transparent ────
test("picker lift rides documentElement AND body (THEME_CSS paints both opaque)", () => {
  assert.match(RENDER, /document\.documentElement\.classList\.toggle\("picker-lifted", on\);\s*\n\s*document\.body\.classList\.toggle\("picker-lifted", on\);/);
  assert.match(CSS, /html\.picker-lifted \{ background: transparent !important; \}/);
  assert.match(CSS, /body\.picker-lifted \{ background: transparent !important; \}/);
});

test("overlay dims are the one standard 0.55", () => {
  assert.match(CSS, /\.picker-overlay \{[\s\S]*?background: rgba\(0, 0, 0, 0\.55\);/);
  assert.match(GEAR_CSS, /#rsettings \{ position: fixed; inset: 0; z-index: 60; background: rgba\(0, 0, 0, 0\.55\);/);
});

// ── discoverability: the settings' shortcut list names both hotkeys ────────────────────────
test("the gear's shortcut rows document Cmd/Ctrl+O and Cmd/Ctrl+P", () => {
  assert.match(GEAR, /<kbd>⌘\/Ctrl<\/kbd> \+ <kbd>O<\/kbd>[\s\S]*?quick switcher/);
  assert.match(GEAR, /<kbd>⌘\/Ctrl<\/kbd> \+ <kbd>P<\/kbd>[\s\S]*?Command palette/);
});
