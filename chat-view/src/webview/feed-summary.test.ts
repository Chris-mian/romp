// The DISTILLER's key takeaway (the user, via the judges session, 2026-06-17): a completed goal's
// `summary` — the distiller's substantive "what we learned/shipped", distinct from the planner's one-line
// doneWhy — is surfaced INLINE under a done card. The kernel emits it.summary per card (build_feed
// 9bc0366, = nodes[nid].summary); the card renders it like the why lines but NON-italic + ✦-prefixed,
// and — unlike doneWhy — independent of the Explanations toggle (it's the distiller's deliverable).
// No jsdom harness for the feed, so — like the other feed-*.test.ts — pin it at the source level.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "feed.ts"), "utf8");

test("AskItem carries a summary field (the distiller's key takeaway)", () => {
  assert.match(FEED, /summary\?: string;\s+\/\/ the DISTILLER's key takeaway/);
});

test("the card builds a fask-summary element after fask-donewhy", () => {
  assert.match(FEED, /const summaryLine = el\("div", "fask-summary"\)/);
  // NON-italic (reads as a finding, not a rationale) — must not carry the why lines' italic
  assert.doesNotMatch(FEED, /summaryLine\.style\.cssText = "[^"]*font-style:italic/);
  assert.match(FEED, /main\.append\(row1, blockReason, doneReason, summaryLine, row2/);
  assert.match(FEED, /a\._summary = summaryLine;/);
});

test("the summary deep-links like the why lines (jump to where the goal completed)", () => {
  assert.match(FEED, /summaryLine\.onclick = goNoted;/);
});

test("updateAskCard fills the summary ✦-prefixed and shows it INDEPENDENT of the Explanations toggle", () => {
  assert.match(FEED, /a\._summary\.textContent = it\.summary \? "✦ " \+ it\.summary : "";/);
  // shown whenever there's a summary — NOT gated by showWhy (the distiller's deliverable, judges 9bc0366)
  assert.match(FEED, /a\._summary\.style\.display = it\.summary \? "" : "none";/);
  assert.doesNotMatch(FEED, /a\._summary\.style\.display = \(it\.summary && showWhy\)/);
});
