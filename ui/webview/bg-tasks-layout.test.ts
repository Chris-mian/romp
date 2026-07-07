// Background-task box (the user 2026-07-07): ONE dedicated full-width rounded box just above the statusline.
// The "N background tasks" header BAR sits at the TOP of the box; clicking it expands the list DOWNWARD
// beneath the header inside the SAME box (a normal flex-direction: column, reading top-to-bottom), so nothing
// spills below the box — the earlier design let a shrink-1 box get squeezed and its rows clipped behind the
// composer. It HOLDS its content (flex 0 0 auto), is capped so it never crowds the composer, and the inner
// list scrolls. Status dots are SOLID (the pulsating yellow was distracting). No jsdom for the chat
// renderer → pin at the source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");
const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const BOX = (CSS.match(/#bg-tasks \{[^}]*\}/) || [""])[0];
const HEAD = (CSS.match(/\.bg-fold-head \{[^}]*\}/) || [""])[0];

test("#bg-tasks is ONE full-width bordered box (distinct bg) that HOLDS its content, capped", () => {
  assert.match(BOX, /flex: 0 0 auto;/);                       // holds its content (not shrink-1 → no squeeze/clip)
  assert.match(BOX, /max-height: min\(50vh, 340px\);/);       // capped so it never crowds the composer
  assert.match(BOX, /border: 1px solid var\(--box-border\);/);
  assert.match(BOX, /border-radius: 8px;/);
  assert.match(BOX, /background: var\(--box-bg\);/);           // a real box, not a faint borderless line
  assert.match(BOX, /margin: 8px 10px 6px;/);                 // a gap/divider above (+ side inset)
});

test("the list expands DOWNWARD beneath the header (header at the top) — nothing spills below the box", () => {
  assert.match(BOX, /flex-direction: column;/);               // first child (header) at top, list below
  assert.doesNotMatch(BOX, /column-reverse/);
  assert.match(CSS, /\.bg-list \{[^}]*flex: 1 1 auto;[^}]*overflow-y: auto;/);   // inner list scrolls, capped by the box
  // the header bar has NO own border (the box provides it); a bottom border separates it from the list when open
  assert.doesNotMatch(HEAD, /border:/);
  assert.match(CSS, /\.bg-fold-head\.open \{ border-bottom: 1px solid var\(--box-border\); \}/);
  // the fold caret points RIGHT when collapsed → DOWN when open (it expands downward)
  assert.match(RENDER, /car\.textContent = open \? "▾" : "▸";/);
});

test("status dots are SOLID — the pulsating yellow animation is gone", () => {
  assert.doesNotMatch(CSS, /animation: bg-pulse/);
  assert.doesNotMatch(CSS, /@keyframes bg-pulse/);
  assert.match(CSS, /\.bg-dot \{[^}]*background: var\(--bgt\);/);   // just the solid status tint
});
