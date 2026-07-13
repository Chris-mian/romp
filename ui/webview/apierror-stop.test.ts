// API-error auto-retry "Stop retrying" (the user 2026-06-24): the loop retried a blocked session every 10s
// with no off-switch. The card now has a Stop/Resume button that PAUSES this session's auto-retry (per
// instance) — it re-arms the moment the session recovers (no longer blocked). Source-level pin (the chat
// renderer has no jsdom harness).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const R = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("the API-error card has a global Stop/Resume retry button that pauses retrying globally", () => {
  assert.match(R, /let globalRetryPaused = false/);
  assert.match(R, /const stop = el\("button", "apierror-stop"\)/);
  assert.match(R, /stop\.textContent = paused \? "Resume all auto-retries" : "Stop all auto-retries"/);
  // clicking toggles the pause globally
  assert.match(R, /globalRetryPaused = !globalRetryPaused/);
  assert.match(R, /vscodeApi\.postMessage\(\{ type: "setGlobalRetryPaused", value: globalRetryPaused \}\)/);
});

test("the retry tick SKIPS all retries when paused globally", () => {
  // paused → the SCHEDULE loop is gated (the countdown text still ticks every second — a usage-limit
  // pause counts down to the window reset, the user 2026-07-13)
  assert.match(R, /if \(!globalRetryPaused\) \{/);
  assert.match(R, /if \(paused\) countdown\.textContent = retryPausedText\(\)/);
  assert.match(R, /return "auto-retry off \(global\)";/);   // a manual pause (no reset ETA) keeps the plain label
});

test("Stop retrying reads as a NEUTRAL action, not the red Retry alarm", () => {
  assert.match(CSS, /\.apierror-stop \{[^}]*color: var\(--dim\)/);
});
