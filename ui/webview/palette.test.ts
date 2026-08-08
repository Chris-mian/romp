// The quick-pick hotkeys — Cmd/Ctrl+O session jump switcher, Cmd/Ctrl+Shift+O new-session
// picker, Cmd/Ctrl+P command palette — and the one-modal-treatment conversions that came with
// them (the user 2026-08-08). Source-level pins (no jsdom for the DOM pieces); fuzzy.ts and
// commands.ts have real unit tests, and the kernel-side shell CSS/wiring is pinned in
// tests/test_kernel.py.
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

test("palette keyboard model: arrows wrap, Enter runs, Shift+Enter is the alt action, Esc closes, backdrop click closes", () => {
  assert.match(PALETTE, /e\.key === "ArrowDown"[\s\S]*?\(active \+ 1\) % rows\.length/);
  assert.match(PALETTE, /e\.key === "ArrowUp"[\s\S]*?\(active - 1 \+ rows\.length\) % rows\.length/);
  assert.match(PALETTE, /e\.key === "Enter" && e\.shiftKey && spec\.altEnter/);
  assert.match(PALETTE, /e\.key === "Enter"[\s\S]*?run\(r\.item\)/);
  assert.match(PALETTE, /e\.key === "Escape"[\s\S]*?close\(\)/);
  assert.match(PALETTE, /if \(e\.target === back\) close\(\);/);
});

test("running an item closes the palette FIRST so its own modal never lands underneath", () => {
  assert.match(PALETTE, /function run\(item: PickItem\): void \{\s*\n\s*close\(\);[\s\S]*?item\.run\(\);/);
});

test("session rows wear the TAB identity language: bold name in the session color, host: prefix dim italic", () => {
  // the user 2026-08-08: visual consistency across surfaces — .tab.colored .tab-label is 600-weight
  // in the identity color; .host-prefix is dim italic at 0.88em. The switcher copies both, and the
  // fuzzy-match marks underline instead of recoloring so the identity color stays intact.
  assert.match(PALETTE, /\.rpal-name\{font-weight:600\}/);
  assert.match(PALETTE, /\.rpal-host\{color:#9aa0a6;font-weight:400;font-style:italic;font-size:0\.88em\}/);
  assert.match(PALETTE, /\.rpal-name b,\.rpal-host b\{color:inherit;font-weight:inherit;text-decoration:underline\}/);
  assert.match(PALETTE, /n\.style\.color = item\.color;/);
  assert.match(PALETTE, /\.rpal-dim\{[^}]*font-size:11px/);
  // one fuzzy match over "host:name", split across the two styled spans
  assert.match(PALETTE, /clipRanges\(hit\.ranges, 0, hl\)/);
  assert.match(PALETTE, /clipRanges\(hit\.ranges, hl, item\.title\.length\)/);
  // …and the same treatment the tabs use, pinned at its source so the two can't drift silently
  const STYLES = read("styles.css");
  assert.match(STYLES, /\.tab\.colored \.tab-label \{ color: var\(--chip-bg\); font-weight: 600; \}/);
  assert.match(STYLES, /\.host-prefix \{ color: var\(--dim\); font-weight: 400; font-style: italic; font-size: 0\.88em; \}/);
});

// ── the shell boot: three combos, wired into every pane ────────────────────────────────────
test("Cmd/Ctrl+O = jump switcher, +Shift = new-session picker, Cmd/Ctrl+P = palette (Shift+P left alone)", () => {
  assert.match(MAIN, /if \(!\(e\.metaKey \|\| e\.ctrlKey\) \|\| e\.altKey \|\| e\.repeat\) return;/);
  assert.match(MAIN, /if \(e\.shiftKey\) openNewSessionPicker\(\); else openSessionSwitcher\(\);/);
  assert.match(MAIN, /k === "p" && !e\.shiftKey/);
  assert.match(MAIN, /e\.preventDefault\(\); e\.stopPropagation\(\);[\s\S]*?palette\.toggle\(\);/);
});

test("key wiring mirrors the Alt+Arrow pane nav: capture on the shell doc AND every pane doc, re-wired on load", () => {
  assert.match(MAIN, /document\.addEventListener\("keydown", onKey, true\);/);
  assert.match(MAIN, /\["f-chat", "f-fleet", "f-feed", "f-timeline"\]\.forEach/);
  assert.match(MAIN, /f\.contentDocument\.addEventListener\("keydown", onKey, true\)/);
  assert.match(MAIN, /f\.addEventListener\("load", wire\);\s*\n\s*wire\(\);/);
});

test("the jump switcher merges the chat registry (remote sessions included) with /sessions, MRU-first, current excluded", () => {
  assert.match(MAIN, /__rompSessionList/);                           // the chat page's merged registry — the only source of federated remotes
  assert.match(MAIN, /fetch\("\/sessions"\)/);                       // …unioned with locals whose tab is closed
  assert.match(MAIN, /if \(!seen\.has\(l\.id\)\) rows\.push/);
  assert.match(MAIN, /__rompMru/);
  assert.match(MAIN, /for \(const id of mru\.slice\(1\)\)/);          // previous session first → Cmd+O Enter toggles back
  assert.match(MAIN, /if \(byId\.has\(r\.id\) && r\.id !== mru\[0\]\)/); // current session excluded
  assert.match(MAIN, /chatPost\(\{ type: "jumpSession", id: r\.id \}\)/);
  // remote rows split the "host:" prefix off with the shared helper (host-prefix.ts, never federation.ts)
  assert.match(MAIN, /import \{ hostPrefix \} from "\.\/host-prefix";/);
  assert.match(MAIN, /title: p \? p\.host \+ p\.rest : r\.name,/);
  assert.match(MAIN, /hostLen: p \? p\.host\.length : 0,/);
  // render.ts publishes the registry snapshot the shell reads
  assert.match(RENDER, /__rompSessionList/);
  assert.match(RENDER, /order\.map\(\(id\) => \{\s*\n\s*const m = tabMeta\.get\(id\);/);
});

test("the switcher fails loudly when the kernel doesn't answer, and Shift+Enter reaches the new-session picker", () => {
  assert.match(MAIN, /Couldn't load sessions — the kernel didn't answer/);
  assert.match(MAIN, /altEnter: \{ label: "new session…", run: openNewSessionPicker \}/);
});

test("the new-session picker opens via the chat pane, revealed first (one code path)", () => {
  assert.match(MAIN, /__rompPaneToggle\("chat", true\)/);
  assert.match(MAIN, /postMessage\(msg, "\*"\)/);
  assert.match(MAIN, /chatPost\(\{ type: "openPicker", toggle: true \}\)/);
});

test("built-in commands call the same globals the rail buttons use", () => {
  for (const g of ["__rompOpenErrs", "__rompOpenNet", "__rompUsagePanel", "__rompRestart", "__rompPaneToggle"]) {
    assert.ok(MAIN.includes(g), g + " missing from palette-main.ts");
  }
  assert.match(MAIN, /id: "session\.jump", title: "Jump to a session"/);
  assert.match(MAIN, /id: "session\.new", title: "New session"/);
});

test("palette-main is bundled for the shell page", () => {
  assert.match(ESBUILD, /"\.\.\/ui\/webview\/palette-main\.ts"/);
});

// ── the chat page: MRU + jumpSession, and the in-page fallback standing down in the shell ──
test("render.ts tracks a session MRU on window for the shell's switcher", () => {
  assert.match(RENDER, /\(window as any\)\.__rompMru = sessionMru;/);
  assert.match(RENDER, /function setActive\([\s\S]{0,200}?noteMru\(id\);/);
});

test("jumpSession activates an open tab like a feed jump, and opens a closed session through the host", () => {
  assert.match(RENDER, /m\.type === "jumpSession" && typeof m\.id === "string"/);
  assert.match(RENDER, /if \(order\.includes\(m\.id\)\) \{ revealSelfPane\(\); closingTabs\.delete\(m\.id\); setActive\(m\.id\); \}/);
  assert.match(RENDER, /else if \(vscodeApi\) vscodeApi\.postMessage\(\{ type: "openSession", id: m\.id \}\);/);
});

test("the in-page Cmd+O fallback stands down inside the romp shell and toggles the picker elsewhere", () => {
  assert.match(RENDER, /function inRompShell\(\): boolean/);
  assert.match(RENDER, /if \(inRompShell\(\)\) return;/);
  assert.match(RENDER, /\(e\.key \|\| ""\)\.toLowerCase\(\) !== "o"\) return;/);
  assert.match(RENDER, /if \(pickerVisible\(\)\) closePicker\(\); else openPicker\(\);/);
});

test("the openPicker message accepts toggle:true (the hotkey form relayed by the shell)", () => {
  assert.match(RENDER, /if \(m\.toggle && pickerVisible\(\)\) closePicker\(\);\s*\n\s*else openPicker\(!!m\.pick, m\.prompt, !!m\.allowNew\);/);
});

// ── lifted overlays paint their pane's content in place (no black hole behind the modal) ───
test("picker lift pins the body to the pane's old rect and keeps painting; hidden panes fall back to .pane-gone", () => {
  assert.match(RENDER, /document\.documentElement\.classList\.toggle\("picker-lifted", on\);\s*\n\s*document\.body\.classList\.toggle\("picker-lifted", on\);/);
  assert.match(RENDER, /getElementById\("chat-pane"\)/);
  assert.match(RENDER, /st\.setProperty\("--pane-x", r!\.left \+ "px"\);/);
  assert.match(RENDER, /window\.addEventListener\("resize", onLiftResize\);/);
  assert.match(CSS, /html\.picker-lifted \{ background: transparent !important; \}/);
  assert.match(CSS, /body\.picker-lifted \{\s*\n\s*position: fixed;\s*\n\s*left: var\(--pane-x, 0\); top: var\(--pane-y, 0\);/);
  assert.match(CSS, /body\.picker-lifted\.pane-gone > \* \{ visibility: hidden; \}/);
  assert.match(CSS, /body\.picker-lifted\.pane-gone > #picker \{ visibility: visible; \}/);
});

test("settings lift does the same via rs-lifted / rs-pane-gone", () => {
  assert.match(GEAR, /document\.body\.classList\.add\('rs-lifted'\); placeLifted\(5\);/);
  assert.match(GEAR, /getElementById\('feed-pane'\)/);
  assert.match(GEAR_CSS, /body\.rs-lifted \{ position: fixed; left: var\(--pane-x, 0\); top: var\(--pane-y, 0\);/);
  assert.match(GEAR_CSS, /body\.rs-pane-gone #feed-head, body\.rs-pane-gone #feed-list, body\.rs-pane-gone #feed-foot \{ visibility: hidden; \}/);
});

test("overlay dims are the one standard 0.55", () => {
  assert.match(CSS, /\.picker-overlay \{[\s\S]*?background: rgba\(0, 0, 0, 0\.55\);/);
  assert.match(GEAR_CSS, /#rsettings \{ position: fixed; inset: 0; z-index: 60; background: rgba\(0, 0, 0, 0\.55\);/);
});

// ── discoverability: the settings' shortcut list names all three hotkeys ───────────────────
test("the gear's shortcut rows document Cmd/Ctrl+O, Cmd/Ctrl+Shift+O and Cmd/Ctrl+P", () => {
  assert.match(GEAR, /<kbd>⌘\/Ctrl<\/kbd> \+ <kbd>O<\/kbd>[\s\S]*?Jump to a session \(quick switcher\)/);
  assert.match(GEAR, /<kbd>⌘\/Ctrl<\/kbd> \+ <kbd>Shift<\/kbd> \+ <kbd>O<\/kbd>[\s\S]*?New session picker/);
  assert.match(GEAR, /<kbd>⌘\/Ctrl<\/kbd> \+ <kbd>P<\/kbd>[\s\S]*?Command palette/);
});
