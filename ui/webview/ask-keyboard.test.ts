// Keyboard nav for the live AskUserQuestion picker (the user 2026-06-22): ↑/↓ STEP through options and the
// preview FOLLOWS (so you can view each one), Enter selects — like the terminal; and multi-select is fully
// arrow-drivable (↑/↓ move, Space toggles, Enter submits), not click-only. Source-level pins (no jsdom).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");
const TYPES = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "ask-types.ts"), "utf8");

test("an option can carry its own preview (the SDK backend sends one per option)", () => {
  assert.match(TYPES, /preview\?: string;/);
});

test("single-select ↑/↓ steps the preview to the focused option (instant for per-option, cursor-driven for tmux)", () => {
  // paint moves the highlight AND re-renders the preview for the new focus
  assert.match(RENDER, /function paintLiveAskFocus\(\) \{[\s\S]*?renderAskPreview\(\);/);
  // when the focused option has NO preview of its own but the ask has a scraped one (tmux), nudge the TUI
  // cursor so the next scrape captures THIS option's preview — without selecting
  assert.match(RENDER, /if \(o && !o\.preview && ask\.preview\) navLiveAsk\(o\.n\);/);
  // Enter still confirms; ↑/↓ never select
  assert.match(RENDER, /e\.key === "Enter"[^}]*answerLiveAsk\(opts\[liveAskFocus\]\.n\)/);
});

test("navLiveAsk posts a navAsk (move cursor, no select) and is debounced", () => {
  assert.match(RENDER, /function navLiveAsk\(target: number\)/);
  assert.match(RENDER, /if \(navTimer\) clearTimeout\(navTimer\);/);
  assert.match(RENDER, /vscodeApi\?\.postMessage\(\{ type: "navAsk", id, target \}\)/);
});

test("multi-select is keyboard-drivable: ↑/↓ focus, Space toggles, Enter submits", () => {
  // the card grabs keyboard focus + a keydown handler, like the single card
  assert.match(RENDER, /card\.addEventListener\("keydown", onMultiKey\);/);
  assert.match(RENDER, /function onMultiKey\(e: KeyboardEvent\)/);
  assert.match(RENDER, /e\.key === "ArrowDown"[^}]*paintMultiFocus\(\)/);
  assert.match(RENDER, /\(e\.key === " " \|\| e\.key === "Spacebar"\)[^}]*toggleLiveAsk\(opts\[liveAskFocus\]\.n\)/);
  assert.match(RENDER, /e\.key === "Enter"[^}]*submitLiveAsk\(\)/);
  // the focused checkbox row carries a .focus highlight, styled like the single card's
  assert.match(RENDER, /"ask-check" \+ \(i === liveAskFocus \? " focus" : ""\)/);
  assert.match(CSS, /\.ask-check\.focus \{[^}]*box-shadow: inset 2px 0 0/);
});

test("a custom-answer field stops its keys from reaching the card's arrow/Space nav", () => {
  assert.match(RENDER, /inp\.addEventListener\("keydown", \(e\) => \{ e\.stopPropagation\(\);/);
});
