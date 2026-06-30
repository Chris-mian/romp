// Slash-command autocomplete (the user 2026-06-29): typing "/" at the start of the composer opens a
// filterable, arrow-navigable menu of the session's slash commands (name + description + arg hint), sourced
// from the kernel's /commands (the Agent SDK's get_server_info — works for tmux + SDK alike). Enter/Tab/click
// FILLS "/name " so the user adds args then sends. Source-level pins (no jsdom for the chat renderer).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("commands come from the kernel /commands endpoint, fetched per active session", () => {
  assert.match(RENDER, /interface SlashCmd \{ name: string; description\?: string; argumentHint\?: string; aliases\?: string\[\]; \}/);
  assert.match(RENDER, /fetch\("\/commands\?sid=" \+ encodeURIComponent\(sid\)/);
  // re-load when the active session changes; "" is the kernel-cwd fallback, distinct from the never-loaded null
  assert.match(RENDER, /let slashSid: string \| null = null;/);
  assert.match(RENDER, /const sid = activeId \|\| "";/);
  assert.match(RENDER, /if \(slashSid !== sid\) loadCmds\(sid, updateSlash\)/);
  // pre-warm the (slow) kernel probe on focus, before the user types "/"
  assert.match(RENDER, /ta\.addEventListener\("focus", \(\) => \{ if \(slashSid !== \(activeId \|\| ""\)\) loadCmds\(activeId \|\| ""\); \}\)/);
});

test("the menu is active ONLY while the box is a single leading \"/token\" (no space yet)", () => {
  assert.match(RENDER, /const slashQuery = \(\): string \| null => \(\/\^\\\/\\S\*\$\/\.test\(ta\.value\) \? ta\.value\.slice\(1\) : null\)/);
  // opening/refreshing happens from the composer's input handler
  assert.match(RENDER, /updateSlash\(\);\s*\/\/ open\/refresh\/close the slash-command menu/);
});

test("filtering ranks prefix over substring, across name + aliases", () => {
  assert.match(RENDER, /for \(const n of \[c\.name, \.\.\.\(c\.aliases \|\| \[\]\)\]\)/);
  assert.match(RENDER, /best = Math\.max\(best, ql === "" \? 0 : i === 0 \? 2 : i > 0 \? 1 : -1\)/);   // prefix>substring>miss
});

test("the menu OWNS ↑/↓/⏎/Tab/Esc while open, so they don't send / leave the box", () => {
  // the keydown handler consults slashKey FIRST and returns if it consumed the key
  assert.match(RENDER, /if \(slashKey\(e\)\) return;/);
  assert.match(RENDER, /if \(e\.key === "ArrowDown"\) \{ e\.preventDefault\(\); if \(items\.length\) \{ sel = \(sel \+ 1\) % items\.length/);
  assert.match(RENDER, /if \(e\.key === "ArrowUp"\)/);
  assert.match(RENDER, /if \(\(e\.key === "Enter" \|\| e\.key === "Tab"\) && items\.length\) \{ e\.preventDefault\(\); pickSlash\(items\[sel\]\); return true; \}/);
  assert.match(RENDER, /if \(e\.key === "Escape"\) \{ e\.preventDefault\(\); slashDismissed = true; closeSlash\(\); return true; \}/);
  // when the menu is closed, slashKey returns false so Enter still sends and Esc still leaves the box
  assert.match(RENDER, /const slashKey = \(e: KeyboardEvent\): boolean => \{\s*\n\s*if \(!pop\) return false;/);
});

test("Escape latches the menu DISMISSED — typing more of the same \"/token\" won't re-pop it; clearing the \"/\" re-arms (the user 2026-06-29)", () => {
  // Esc sets the latch; updateSlash refuses to reopen while latched
  assert.match(RENDER, /let slashDismissed = false;/);
  assert.match(RENDER, /if \(slashDismissed\) return;/);
  // the ONLY reset is the "/token" context going away (slashQuery → null): clear the "/" and start over
  assert.match(RENDER, /if \(q === null\) \{ slashDismissed = false; closeSlash\(\); return; \}/);
});

test("picking a command FILLS \"/name \" (does not send) so the user adds args + ⏎", () => {
  assert.match(RENDER, /const pickSlash = \(c: SlashCmd\) => \{\s*\n\s*ta\.value = "\/" \+ c\.name \+ " ";/);
  assert.match(RENDER, /ta\.setSelectionRange\(ta\.value\.length, ta\.value\.length\)/);
  // clicking a row picks it; mousedown (not click) keeps the textarea focused
  assert.match(RENDER, /row\.addEventListener\("mousedown", \(ev\) => \{ ev\.preventDefault\(\); pickSlash\(c\); \}\)/);
});

test("while the kernel warms its probe the menu shows the romp loader, not a blank/empty", () => {
  assert.match(RENDER, /if \(slashWarming && !slashCmds\.length\) \{/);
  assert.match(RENDER, /l\.className = "slash-loading"/);
  assert.match(RENDER, /s\.className = "slash-spin"/);
  // poll again while warming
  assert.match(RENDER, /slashPoll = window\.setTimeout\(\(\) => loadCmds\(sid, then\), 1500\)/);
});

test("the popup + selected-row accent + loader spin are styled", () => {
  assert.match(CSS, /\.slash-pop \{[\s\S]*?position: fixed/);
  assert.match(CSS, /\.slash-row\.sel \{ background: var\(--accent\); \}/);   // selected row = romp accent
  assert.match(CSS, /\.slash-spin \{[\s\S]*?url\(\/media\/romp-swirl-glyph\.svg\)/);
  assert.match(CSS, /@keyframes slash-spin \{ to \{ transform: rotate\(-360deg\); \} \}/);
  assert.match(CSS, /@media \(prefers-reduced-motion: reduce\) \{ \.slash-spin \{ animation: none; \} \}/);
});
