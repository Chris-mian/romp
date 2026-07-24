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
  assert.match(RENDER, /function stopButton\(state\?: ChipState\)/);
  assert.match(RENDER, /vscodeApi\.postMessage\(\{ type: "interrupt", id: activeId \}\)/);
  // three interrupt senders now, all the SAME path: the composer Ctrl+C, this button, and the retrying
  // card's "Stop retrying" (the user 2026-07-24 — the CLI owns the api_retry backoff and the SDK exposes no
  // handle on it, so interrupting the stalled turn is the one honest stop).
  const senders = RENDER.match(/postMessage\(\{ type: "interrupt", id: activeId \}\)/g) || [];
  assert.equal(senders.length, 3, "Ctrl+C, the stop button, and Stop retrying — one interrupt path");
});

test("the button renders while busy (working/compacting) AND while stuck retrying/blocked, never when idle", () => {
  // retrying/blocked were added (the user 2026-07-06): there the interrupt doubles as the per-thread
  // auto-retry off-switch. Still omitted in ready/idle/awaiting/interrupting — nothing to stop.
  assert.match(RENDER, /s\.status\.state === "working" \|\| s\.status\.state === "compacting"\s*\n\s*\|\| s\.status\.state === "retrying" \|\| s\.status\.state === "blocked"\) sl\.appendChild\(stopButton\(s\.status\.state\)\)/);
  // no busy/idle CLASS toggle — it's drawn only when there's something to stop, so the bare .stop-btn is the live look
  assert.ok(!/"stop-btn" \+ \(busy \? " active" : ""\)/.test(RENDER), "no idle variant — omitted, not grayed");
});

test("it carries a stop icon + a state-aware tooltip and aria-label", () => {
  assert.match(RENDER, /el\("span", "stop-icon"\)/);
  assert.match(RENDER, /same as Ctrl\+C/);
  // idle-busy states keep the plain label; the stuck states get the retry-specific one
  assert.match(RENDER, /setAttribute\("aria-label", stuck \? "Stop retrying this session" : "Interrupt session"\)/);
});

test("it's a white square that reveals the pale-red stop tint ONLY on hover, with a press flash", () => {
  const base = (CSS.match(/\.stop-btn \{[^}]*\}/) || [""])[0];
  assert.match(base, /color: var\(--fg\)/, "neutral white-ish square by default");
  assert.match(base, /cursor: pointer;/);
  assert.ok(!/st-blocked-bg/.test(base), "no red until you hover");
  const hoverRule = (CSS.match(/\.stop-btn:hover \{[^}]*\}/) || [""])[0];
  assert.match(hoverRule, /color: var\(--st-blocked-bg\)/, "pale red square on hover");
  assert.match(hoverRule, /background: rgba\(229, 72, 77/, "pale red background on hover");
  assert.doesNotMatch(CSS, /stop-flash/, "the old flash rule is fully gone (its JS was removed; 2026-07-07 CSS audit)");
  assert.match(CSS, /\.stop-icon \{[^}]*background: currentColor/, "the square stop glyph");
});
