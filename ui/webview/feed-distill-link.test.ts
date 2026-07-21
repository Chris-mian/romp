// The distiller line is a LINK (the user 2026-06-29): clicking the takeaway/decision-brief follows to where
// it was written — the card jumps to it.summaryAnchorUuid (the biggest assistant-text block in the work span),
// the modal node jumps to the node's work anchor (same target as its mark/time zones). The click was lost when
// the line was restored via applyDistillLine (which only sets text), so the summary read as plain, dead text.
// No jsdom for the feed renderer, so pin at the source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

test("the CARD's distiller line links to it.summaryAnchorUuid (work anchor), only when shown + anchored", () => {
  // applyDistillLine returns whether the line is shown; the link wires only when shown AND there's an anchor
  assert.match(FEED, /const distillShown = applyDistillLine\(a\._distill as HTMLElement,/);
  assert.match(FEED, /if \(distillShown && it\.summaryAnchorUuid\) \{/);
  assert.match(FEED, /dl\.classList\.add\("fask-distill-link"\)/);
  assert.match(FEED, /type: "showOnTimeline", itemId: it\.itemId, sid: it\.sid, t: it\.t, anchor: "work", anchorUuid: it\.summaryAnchorUuid/);
  // stopPropagation so the link doesn't ALSO open the modal (the card-body click)
  assert.match(FEED, /dl\.onclick = \(ev: Event\) => \{ ev\.stopPropagation\(\);/);
  // and it's cleared (non-clickable) when there's nothing to link to
  assert.match(FEED, /dl\.classList\.remove\("fask-distill-link"\);\s*\n\s*dl\.onclick = null;/);
});

test("the MODAL node summary is also a link (parity), to the node's work anchor via goWork", () => {
  // wired on EITHER anchor (the user 2026-07-20): the work anchor goes cold-null on every transcript
  // write (cache-only parse), and gating on it alone dead-ended the summary line for a beat — goWork
  // itself falls to the prompt anchor, so the line stays live whenever ANY anchor exists.
  assert.match(FEED, /if \(!repeat && \(node\.anchorUuid \|\| node\.promptAnchorUuid\)\) \{[\s\S]*?sum\.classList\.add\("ftree-summary-link"\);[\s\S]*?sum\.onclick = goWork;/);
});

test("both link variants get a pointer + hover affordance in CSS", () => {
  assert.match(CSS, /\.fask-distill-link \{[^}]*cursor: pointer/);
  assert.match(CSS, /\.fask-distill-link:hover \{[^}]*text-decoration: underline/);
  assert.match(CSS, /\.ftree-summary-link \{[^}]*cursor: pointer/);
});

test("the card summary hover lights the TEXT (brighten + underline), NOT a box behind it (the user 2026-07-15)", () => {
  assert.match(CSS, /\.fask-distill-link:hover \{[^}]*opacity: 1;[^}]*text-decoration: underline/);
  assert.doesNotMatch(CSS, /\.fask-distill-link:hover \{[^}]*background/);   // no box fill on hover
});

test("an anchorless summary still acknowledges the click with a visible toast (the user 2026-07-20)", () => {
  // A card minted from a postal delegate (or with a not-yet-landed completion turn) has no anchor uuid;
  // the line used to render as silently dead text — no hover affordance, no click, no error anywhere.
  // It must keep the link affordance and honestly say why the jump can't happen.
  assert.match(FEED, /\} else if \(distillShown\) \{/);
  assert.match(FEED, /dl\.title = "no anchor recorded for this card";/);
  assert.match(FEED, /feedToast\("couldn't locate this in the transcript — no anchor was recorded for this card"\)/);
});
