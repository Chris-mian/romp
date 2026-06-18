// The DISTILLER's key takeaway for a completed goal (the user 2026-06-17): the ONE most-useful thing — a
// copy-pasteable artifact (command / path / URL / snippet) verbatim, else a 1-3 sentence outcome. Shown in
// the single-ask MODAL (renderTreeNode), NOT on the card (which keeps the closer's one-line doneWhy — ui owns
// that removal). Source-assertion, like the other feed-*.test.ts (no jsdom for the feed renderer).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "feed.css"), "utf8");

test("the modal tree renders node.summary (the distiller takeaway) as a prominent per-node block", () => {
  assert.match(FEED, /summary\?: string \| null;/);          // consumed off AskTreeNode (emitted by the kernel flatten)
  assert.match(FEED, /const summaryText = node\.summary;/);
  assert.match(FEED, /el\("div", "ftree-summary"\)/);
  // brighter than the dim italic why-line, pre-wrap so a copied artifact stays intact
  assert.match(CSS, /\.ftree-summary \{[^}]*white-space: pre-wrap/);
});

test("the summary is plain selectable text — no copy button (the user 2026-06-18)", () => {
  // the ⧉ copy affordance was removed; the takeaway is just selectable text now.
  assert.doesNotMatch(FEED, /ftree-summary-copy/);
  assert.doesNotMatch(FEED, /navigator\.clipboard\?\.writeText\(summaryText\)/);
  assert.doesNotMatch(CSS, /\.ftree-summary-copy/);
});

test("the distiller summary SUPERSEDES the one-line doneWhy in the modal (no redundant rationale)", () => {
  // when a summary is present, the done node's why-line (doneWhy) is skipped — the richer takeaway stands in
  assert.match(FEED, /node\.status === "done" \? \(summaryText \? undefined : node\.doneWhy\)/);
});

test("the card ALSO uses the distiller summary now — as its one auto-line (the human reversed this 2026-06-18)", () => {
  // the card's auto-line shows it.summary (done) / it.blockSummary (blocked), else "(generating…)";
  // the modal block above is unchanged. (The earlier ✦ .fask-summary sub-line is NOT how it's done — the
  // existing fask-donewhy/fask-blockwhy elements are repurposed as the auto-line.)
  assert.match(FEED, /setAutoLine\(a\._donewhy, it\.summary, it\.doneWhy/);
  assert.doesNotMatch(CSS, /\.fask-summary/);
});
