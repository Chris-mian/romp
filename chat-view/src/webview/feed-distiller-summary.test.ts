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

test("the distiller summary is MODAL-ONLY — no card-side it.summary render remains", () => {
  // judges: shown in the MODAL, not on the card. The card render used it.summary / .fask-summary (removed).
  assert.doesNotMatch(FEED, /it\.summary/);
  assert.doesNotMatch(CSS, /\.fask-summary/);
});
