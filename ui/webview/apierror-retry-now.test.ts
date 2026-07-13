// "Retry now" on an API-error card (the user 2026-07-06): on the SDK backend it did NOTHING and gave no
// feedback — because the kernel's apiRetry gate (global pause / a thread the user interrupted) blocked the
// SAME message the AUTO-retry loop uses, and the button never acknowledged the click. Now the manual click
// posts manual:true (an explicit override the kernel fires past the gate) AND acknowledges at once (disabled
// + "Retrying…", self-restoring). render.ts has no jsdom harness → source pins.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
// isolate the Retry button's click handler
const H = (RENDER.match(/const retry = el\("button", "apierror-retry"\)[\s\S]*?head\.appendChild\(retry\);/) || [""])[0];

test("Retry now posts an explicit MANUAL override so it fires even when auto-retry is paused/suppressed", () => {
  assert.ok(H, "found the Retry button block");
  assert.match(H, /vscodeApi\.postMessage\(\{ type: "apiRetry", id: activeId, manual: true \}\)/);
});

test("Retry now acknowledges the click immediately (disabled + 'Retrying…'), then self-restores", () => {
  assert.match(H, /retry\.disabled = true;/);
  assert.match(H, /retry\.textContent = "Retrying…";/);
  assert.match(H, /setTimeout\(\(\) => \{ if \(retry\.isConnected\) \{ retry\.disabled = false; retry\.textContent = "Retry now"; \} \}/);
});

test("the AUTO-retry tick stays a plain apiRetry (no manual) so the pause/suppression gate still holds it", () => {
  // only the button overrides; the 10s auto-loop must remain gated
  assert.match(RENDER, /vscodeApi\.postMessage\(\{ type: "apiRetry", id \}\)/);   // apiRetryTick's post — no manual flag
});

test("a usage-limit pause counts down to the window reset instead of a mute label (the user 2026-07-13)", () => {
  // the kernel's globalRetryPaused push carries resumeAt (the limiting window's reset epoch, seconds)
  assert.match(RENDER, /globalRetryResumeAt = typeof m\.resumeAt === "number" \? m\.resumeAt : null;/);
  assert.match(RENDER, /usage limit — retrying at \$\{hm\} \(in \$\{durLabel\(dt\)\}\)/);
  // the tick updates the countdown every second EVEN while paused (only the schedule loop is gated)
  assert.match(RENDER, /if \(globalRetryPaused\) \{\s*\n\s*cd\.textContent = retryPausedText\(\);/);
  // the LIVE (newest) error card ticks — older cards in the transcript are settled history
  assert.match(RENDER, /const cd = cds\.length \? \(cds\[cds\.length - 1\] as HTMLElement\) : null;/);
});
