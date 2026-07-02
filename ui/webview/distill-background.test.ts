// The card's TWO collapsible distiller sections (the user 2026-07-02): a returning reader often forgot
// what the thread was about, so the distiller now writes a BACKGROUND section (re-orientation) above the
// takeaway. Collapsed = one small rounded-RECT pill ("background +" / "summary +"); expanded = the
// paragraph runs the full card width with a tiny trailing "−" pill after its last line — no button column,
// no indent (the user 2026-07-02: the circle buttons were clunky and horizontal space is scarce). Collapse
// state is keyed by itemId in module sets so the keyed incremental re-render never snaps a section shut.
// No jsdom — pin the wiring at source (repo convention).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

test("the card builds both sections and registers their refs", () => {
  assert.match(FEED, /const bgSec = el\("div", "fask-sec fask-bg"\); bgSec\.style\.display = "none";/);
  assert.match(FEED, /const takeSec = el\("div", "fask-sec fask-take"\); takeSec\.style\.display = "none";/);
  assert.match(FEED, /bgBtn\.textContent = "background \+"/, "the collapsed pill reads 'background +'");
  assert.match(FEED, /takeBtn\.textContent = "summary \+"/, "the collapsed pill reads 'summary +'");
  assert.match(FEED, /takeSec\.append\(takeBtn, distill\)/, "the takeaway section WRAPS the existing distill line");
  assert.match(FEED, /a\._bgSec = bgSec; a\._bgBtn = bgBtn; a\._bgBody = bgBody; a\._bgMin = bgMin;/);
  assert.match(FEED, /background\?: string \| null;/, "the AskItem carries the kernel's background field");
});

test("defaults: background collapsed, takeaway expanded; the pills flip per-card sets", () => {
  assert.match(FEED, /const bgOpen = new Set<string>\(\);/);
  assert.match(FEED, /const takeClosed = new Set<string>\(\);/);
  // background: open only when the user opened it; takeaway: open unless the user closed it
  assert.match(FEED, /const open = bgOpen\.has\(id\);/);
  assert.match(FEED, /const open = !takeClosed\.has\(id\);/);
  // both flips stop propagation — the card-body click opens the modal — and drive BOTH pills (the
  // collapsed "name +" pill and the expanded trailing "−" pill share one handler per section)
  const flips = FEED.match(/ev\.stopPropagation\(\);\s*\n\s*if \((?:bgOpen|takeClosed)\.has\(id\)\)/g) || [];
  assert.equal(flips.length, 2, "each section's flip stops the card-body click");
  assert.match(FEED, /a\._bgBtn\.onclick = flipBg;\s*\n\s*a\._bgMin\.onclick = flipBg;/);
  assert.match(FEED, /a\._takeBtn\.onclick = flipTake;\s*\n\s*a\._takeMin\.onclick = flipTake;/);
});

test("expanded paragraphs carry the trailing − pill; collapsed shows only the name pill", () => {
  // expanded: the "−" is appended INTO the paragraph so it trails the last line (appendChild re-appends
  // the same node after a re-render reset textContent — no accumulation)
  assert.match(FEED, /a\._bgBody\.appendChild\(a\._bgMin\);/);
  assert.match(FEED, /\(a\._distill as HTMLElement\)\.appendChild\(a\._takeMin\);/);
  // collapsed: the paragraph hides and the "name +" pill shows (and vice versa)
  assert.match(FEED, /a\._bgBtn\.style\.display = open \? "none" : "";/);
  assert.match(FEED, /a\._takeBtn\.style\.display = open \? "none" : "";/);
});

test("background shows only alongside a produced takeaway, and the takeaway keeps its deep-link", () => {
  assert.match(FEED, /const bg = distillShown && it\.background \? it\.background : null;/);
  assert.match(FEED, /applyDistillSections\(a, it, distillShown\);/);
  // the takeaway's click-to-anchor wiring is untouched (it lives on the distill line itself)
  assert.match(FEED, /dl\.classList\.add\("fask-distill-link"\)/);
});

test("the section chrome is styled: rounded-rect pills, full-width bodies, no gutter", () => {
  assert.match(CSS, /\.fask-sec \{ display: flex; flex-wrap: wrap;/);
  assert.match(CSS, /\.fask-sec-pill, \.fask-sec-min \{[^}]*border-radius: 6px/, "rounded RECTANGLES, not circles");
  assert.match(CSS, /\.fask-sec-pill, \.fask-sec-min \{[^}]*cursor: pointer/);
  assert.match(CSS, /\.fask-sec-min \{[^}]*display: inline-block/, "the − pill flows inline after the text");
  // the expanded background body takes the FULL card width — the old 21px gutter wasted horizontal space
  assert.doesNotMatch(CSS, /\.fask-bg-body \{[^}]*margin-left/);
  assert.match(CSS, /\.fask-bg-body \{[^}]*pre-wrap/);
  // feed.css must define --box-border itself (border shorthand with an undefined var() is VOID — the
  // await-paused outline silently lost its border this way; the user 2026-07-02)
  assert.match(CSS, /--box-border: rgba\(255, 255, 255, 0\.12\)/);
});
