// The card's ONE auto-written line (the human's redesign, 2026-06-18): a COMPLETED card shows the
// distiller's `summary`, a BLOCKED card shows `blockSummary`, else the literal "(generating…)". It is
// PLAIN TEXT (no deep-link) and never the planner's hand-written why — that demotes to the line's hover
// tooltip. The fask-donewhy / fask-blockwhy elements are repurposed as those auto-lines. Source-level pin.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");

test("AskItem carries the distiller summary + blockSummary (the card's auto-line source)", () => {
  assert.match(FEED, /summary\?: string \| null;\s+\/\/ distiller's key takeaway for a COMPLETED goal/);
  assert.match(FEED, /blockSummary\?: string \| null;\s+\/\/ block-distiller's decision brief for a BLOCKED goal/);
});

test("the card builds the auto-line elements as PLAIN TEXT (no cursor:pointer, no italic baked in)", () => {
  assert.match(FEED, /const blockReason = el\("div", "fask-blockwhy"\)/);
  assert.match(FEED, /const doneReason = el\("div", "fask-donewhy"\)/);
  // plain inline style — no link affordance and no fixed font-style (set dynamically in updateAskCard)
  assert.match(FEED, /doneReason\.style\.cssText = "display:none;font-size:11px;line-height:1\.3;margin:1px 0 3px";/);
  assert.doesNotMatch(FEED, /doneReason\.style\.cssText = "[^"]*cursor:pointer/);
  assert.match(FEED, /main\.append\(row1, blockReason, doneReason, row2/);
  assert.match(FEED, /a\._donewhy = doneReason;/);
});

test("the auto-line is NOT a deep-link — goNoted and its onclick are gone", () => {
  assert.doesNotMatch(FEED, /const goNoted =/);
  assert.doesNotMatch(FEED, /doneReason\.onclick = goNoted/);
  assert.doesNotMatch(FEED, /blockReason\.onclick = goNoted/);
});

test("updateAskCard fills the auto-line with summary-or-(generating…), why as the hover title", () => {
  assert.match(FEED, /el\.textContent = generating \? "\(generating…\)" : text;/);
  assert.match(FEED, /if \(why && why\.trim\(\)\) el\.title = why\.trim\(\);/);
});

test("the auto-line distinguishes null (generating) from \"\" (distiller settled, no takeaway → hide the line)", () => {
  // null/undefined summary = the distiller is still running → "(generating…)"; "" = it settled with nothing to
  // say (an umbrella/verify goal with no work of its own) → no line, never a permanently-stuck placeholder.
  assert.match(FEED, /if \(sum != null && !text\) \{ el\.style\.display = "none"; el\.removeAttribute\("title"\); return; \}/);
  assert.match(FEED, /const generating = !text;/);
});
