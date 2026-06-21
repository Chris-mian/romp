// Stop/interrupt button beside the state badge (the user 2026-06-19): a less-fiddly alternative to the
// composer's Ctrl+C. It posts the SAME {type:"interrupt"} message the host turns into an Esc into the
// pane, and renders ONLY while the session is busy (working/compacting) — there's nothing to interrupt
// when idle, so it isn't drawn at all. No jsdom harness for the renderer, so pin the wiring at the source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("the stop button posts the same interrupt message as the composer's Ctrl+C", () => {
  assert.match(RENDER, /function stopButton\(\)/);
  assert.match(RENDER, /vscodeApi\.postMessage\(\{ type: "interrupt", id: activeId \}\)/);
  // there are exactly two interrupt senders now: the composer Ctrl+C and this button
  const senders = RENDER.match(/postMessage\(\{ type: "interrupt", id: activeId \}\)/g) || [];
  assert.equal(senders.length, 2, "Ctrl+C and the stop button — same interrupt path");
});

test("the button renders ONLY while the session is busy (working/compacting), never when idle", () => {
  assert.match(RENDER, /if \(s\.status\.state === "working" \|\| s\.status\.state === "compacting"\) sl\.appendChild\(stopButton\(\)\)/);
  // no busy/idle CLASS toggle anymore — it's drawn only when busy, so the bare .stop-btn is the live look
  assert.ok(!/"stop-btn" \+ \(busy \? " active" : ""\)/.test(RENDER), "no idle variant — omitted, not grayed");
});

test("it carries a stop icon + a Ctrl+C-equivalent tooltip and aria-label", () => {
  assert.match(RENDER, /el\("span", "stop-icon"\)/);
  assert.match(RENDER, /same as Ctrl\+C/);
  assert.match(RENDER, /setAttribute\("aria-label", "Interrupt session"\)/);
});

test("it's a white square that reveals the pale-red stop tint ONLY on hover, with a press flash", () => {
  const base = (CSS.match(/\.stop-btn \{[^}]*\}/) || [""])[0];
  assert.match(base, /color: var\(--fg\)/, "neutral white-ish square by default");
  assert.match(base, /cursor: pointer;/);
  assert.ok(!/st-blocked-bg/.test(base), "no red until you hover");
  const hoverRule = (CSS.match(/\.stop-btn:hover \{[^}]*\}/) || [""])[0];
  assert.match(hoverRule, /color: var\(--st-blocked-bg\)/, "pale red square on hover");
  assert.match(hoverRule, /background: rgba\(229, 72, 77/, "pale red background on hover");
  assert.match(CSS, /\.stop-btn\.stop-flash \{/, "a press-feedback flash");
  assert.match(CSS, /\.stop-icon \{[^}]*background: currentColor/, "the square stop glyph");
});
