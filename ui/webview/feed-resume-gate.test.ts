// Resume-gate decision card in the feed (the user 2026-07-21): a boot-deferred high-context SDK session
// surfaces as a needs_input card (blocked.state "largeResume") with Proceed / Compact on resume / Skip
// buttons that post the resumeGate op. Source-pin (no jsdom for the feed renderer), like the other feed-*.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");

test("the three resume-gate buttons are created and ride the action row", () => {
  assert.match(FEED, /const rgProceed = el\("button", "fdismiss frg"\)[\s\S]*?rgProceed\.textContent = "Proceed"/);
  assert.match(FEED, /const rgCompact = el\("button", "fdismiss frg"\)[\s\S]*?rgCompact\.textContent = "Compact on resume"/);
  assert.match(FEED, /const rgSkip = el\("button", "fdismiss frg"\)[\s\S]*?rgSkip\.textContent = "Skip"/);
  assert.match(FEED, /actions\.append\(apiRetry, revive, rgProceed, rgCompact, rgSkip\)/);
});

test("the buttons show only for a largeResume card and each posts resumeGate with its choice", () => {
  assert.match(FEED, /const isResumeGate = it\.blocked\?\.state === "largeResume"/);
  assert.match(FEED, /\[a\._rgProceed as HTMLButtonElement, "proceed", "Resuming…"\]/);
  assert.match(FEED, /\[a\._rgCompact as HTMLButtonElement, "compact", "Compacting…"\]/);
  assert.match(FEED, /\[a\._rgSkip as HTMLButtonElement, "skip", "Skipped"\]/);
  assert.match(FEED, /btn\.style\.display = isResumeGate \? "" : "none"/);
  assert.match(FEED, /vscodeApi\?\.postMessage\(\{ type: "resumeGate", id: it\.sid, choice \}\)/);
  // one decision per card: clicking any of the three disables all three + acknowledges immediately
  assert.match(FEED, /for \(const \[b\] of rgBtns\) b\.disabled = true;/);
  // OPTIMISTIC CLEAR: the card leaves immediately on click (same machinery as the Clear button) — it
  // used to linger until the kernel round-trip (the user 2026-07-21)
  assert.match(FEED, /vscodeApi\?\.postMessage\(\{ type: "resumeGate"[\s\S]*?pendingCleared\.add\(it\.itemId\);\s*\n\s*card\.classList\.add\("dismissing"\);/);
  assert.match(FEED, /card\.remove\(\); askEls\.delete\(it\.itemId\); dropDismissed\(\[it\.itemId\]\); \} \}, 180\);/);
});

test("a largeResume card suppresses the block chip and the generic Clear (Skip is its dismissal)", () => {
  assert.match(FEED, /it\.blocked\.state !== "largeResume"/);   // block badge hidden for the resume card
  assert.match(FEED, /\(a\._clr as HTMLElement\)\.style\.display = isResumeGate \? "none" : ""/);
});

test("the blocked type carries the largeResume ctx/reason fields", () => {
  assert.match(FEED, /ctx\?: number \| null; reason\?: string \};\s*\/\/ largeResume/);
});
