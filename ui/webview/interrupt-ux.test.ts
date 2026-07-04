// The interrupt's whole arc is immediately responsive (the user 2026-07-02). Click the stop button →
// it disables and becomes the word "interrupting…" on the spot; the kernel's push then flips the chip
// to INTERRUPTING… (no timer, no re-pressable button) until the stop settles on disk and the chip
// reads READY again. The CLI's "[Request interrupted by user]" stop record renders as a slim rail
// marker in the compact-divider's language — never a person-blue bubble. Source pins (no jsdom).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("the stop button acknowledges its click instantly and cannot be re-pressed", () => {
  const fn = SRC.slice(SRC.indexOf("function stopButton"), SRC.indexOf("function updateStatusline"));
  assert.match(fn, /\(btn as HTMLButtonElement\)\.disabled = true;/);
  assert.match(fn, /lbl\.textContent = "interrupting…";/, "the button becomes the word");
  assert.doesNotMatch(fn, /stop-flash/, "the old 400ms flash (which left the button pressable) is gone");
  assert.match(CSS, /\.stop-btn:disabled \{ opacity: 0\.6; cursor: default; \}/);
});

test("INTERRUPTING is a first-class chip state: labeled, styled, timerless, buttonless", () => {
  assert.match(SRC, /"interrupting";/, "in the ChipState union");
  assert.match(SRC, /interrupting: "Interrupting…",/);
  // the generic chip branch renders it (only working/compacting get the timer / stop button)
  assert.match(SRC, /if \(s\.status\.state === "working" \|\| s\.status\.state === "compacting"\) sl\.appendChild\(stopButton\(\)\);/);
  assert.match(CSS, /\.chip-interrupting \{ background: var\(--st-working-bg\);[^}]*opacity: 0\.75; \}/,
               "busy-yellow but dimmed + static — in flight, not still grinding");
});

test("the stop record renders as a rail marker, not a message bubble", () => {
  assert.match(SRC, /if \(\(ev as any\)\.interruptMarker\) \{/);
  assert.match(SRC, /const turn = el\("div", "turn turn-interrupt"\);/);
  assert.match(SRC, /line\.appendChild\(el\("span", "interrupt-square"\)\);/, "the stop button's own glyph ties cause to effect");
  assert.match(CSS, /\.interrupt-line \{[^}]*font-style: italic/);
  assert.match(CSS, /\.interrupt-square \{ width: 8px; height: 8px;/);
});
