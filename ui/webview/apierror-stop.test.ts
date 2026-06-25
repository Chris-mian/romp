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

test("the API-error card has a Stop/Resume retry button that pauses retryPaused for the session", () => {
  assert.match(R, /const retryPaused = new Set<string>\(\)/);
  assert.match(R, /const stop = el\("button", "apierror-stop"\)/);
  assert.match(R, /stop\.textContent = paused \? "Resume" : "Stop retrying"/);
  // clicking toggles the pause for the active session; resuming re-arms the countdown
  assert.match(R, /if \(retryPaused\.has\(id\)\) \{ retryPaused\.delete\(id\)[\s\S]*apiRetryNext\.set\(id, Date\.now\(\) \+ API_RETRY_MS\)/);
  assert.match(R, /else \{ retryPaused\.add\(id\)/);
});

test("the retry tick SKIPS a paused session and re-arms it on recovery (per-instance reset)", () => {
  // paused → no auto-retry this pass
  assert.match(R, /if \(retryPaused\.has\(id\)\) return;/);
  // recovered (no longer blocked) → drop from retryPaused so the NEXT error auto-retries again
  assert.match(R, /retryPaused\.forEach\(\(id\) => \{ if \(!blocked\.has\(id\)\) retryPaused\.delete\(id\); \}\)/);
  // the countdown reads "auto-retry off" while paused
  assert.match(R, /retryPaused\.has\(activeId\)\) cd\.textContent = "auto-retry off"/);
});

test("Stop retrying reads as a NEUTRAL action, not the red Retry alarm", () => {
  assert.match(CSS, /\.apierror-stop \{[^}]*color: var\(--dim\)/);
});
