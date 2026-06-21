// The DISTILLER's key takeaway for a completed goal (the user 2026-06-17): the ONE most-useful thing — a
// copy-pasteable artifact (command / path / URL / snippet) verbatim, else a 1-3 sentence outcome. Shown in
// the single-ask MODAL (renderTreeNode), NOT on the card (which keeps the closer's one-line doneWhy — ui owns
// that removal). Source-assertion, like the other feed-*.test.ts (no jsdom for the feed renderer).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

test("the modal tree renders node.summary (the distiller takeaway) as a prominent per-node block", () => {
  assert.match(FEED, /summary\?: string \| null;/);          // consumed off AskTreeNode (emitted by the kernel flatten)
  assert.match(FEED, /blockSummary\?: string \| null;/);   // AskTreeNode carries it (kernel emits per node)
  assert.match(FEED, /const distillText = node\.status === "done" \? node\.summary : node\.status === "question" \? node\.blockSummary/);
  assert.match(FEED, /el\("div", "ftree-summary" \+ \(distillText \? "" : " generating"\)\)/);
  // brighter than the dim italic why-line, pre-wrap so a copied artifact stays intact
  assert.match(CSS, /\.ftree-summary \{[^}]*white-space: pre-wrap/);
});

test("the summary is plain selectable text — no copy button (the user 2026-06-18)", () => {
  // the ⧉ copy affordance was removed; the takeaway is just selectable text now.
  assert.doesNotMatch(FEED, /ftree-summary-copy/);
  assert.doesNotMatch(FEED, /navigator\.clipboard/);
  assert.doesNotMatch(CSS, /\.ftree-summary-copy/);
});

test("done/blocked nodes use the distiller line (summary/blockSummary/'(generating…)'); reason → tooltip; why-line is OPEN-only", () => {
  // the modal auto-line for a done/blocked node is the distiller text else "(generating…)" — NEVER a
  // doneWhy/blockWhy fallback (the user 2026-06-18); the planner's reason demotes to the line's hover title;
  // the visible "why" line now renders for OPEN nodes only.
  assert.match(FEED, /if \(\(node\.status === "done" \|\| node\.status === "question"\) && distillText !== ""\) \{/);
  assert.match(FEED, /stext\.textContent = distillText \|\| "\(generating…\)"/);
  assert.match(FEED, /if \(reasonTip\) sum\.title = reasonTip/);
  assert.match(FEED, /if \(node\.status === "open" && node\.why\) \{/);
  assert.match(CSS, /\.ftree-summary\.generating \{/);
});

test("a settled-empty distiller field (\"\") suppresses the modal summary line — not a stuck \"(generating…)\"", () => {
  // "" = the distiller ran and had no takeaway (an umbrella/verify goal with no work of its own); the modal
  // shows NO summary line for it, only null/undefined keeps the "(generating…)" placeholder.
  assert.match(FEED, /&& distillText !== ""\) \{/);
});

test("the card ALSO uses the distiller summary now — as its one auto-line (the human reversed this 2026-06-18)", () => {
  // the card's auto-line shows it.summary (done) / it.blockSummary (blocked), else "(generating…)";
  // the modal block above is unchanged. (The earlier ✦ .fask-summary sub-line is NOT how it's done — the
  // existing fask-donewhy/fask-blockwhy elements are repurposed as the auto-line.)
  assert.match(FEED, /setAutoLine\(a\._donewhy, it\.summary, it\.doneWhy/);
  assert.doesNotMatch(CSS, /\.fask-summary/);
});
