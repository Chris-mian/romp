// The card's TWO collapsible distiller sections (the user 2026-07-02, round 5): a returning reader often
// forgot what the thread was about, so the distiller writes a BACKGROUND section (re-orientation) above
// the takeaway. Collapsed sections are REAL buttons — "background" / "summary" in the Clear button's
// chrome — sitting side by side on one row when both are collapsed (one flex-wrap container: full-width
// bodies force their own lines, lone buttons share one). Open, the text runs the full card width and
// collapses via a block "less" button on its own line, always bottom-left. One empty line separates the
// two sections only while either is expanded. The MODAL always shows both, labeled. Collapse state is
// keyed by itemId in module sets so re-renders never snap a section shut. No jsdom — source pins.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

test("ONE flex-wrap container holds real buttons + full-width bodies", () => {
  assert.match(FEED, /const secs = el\("div", "fask-secs"\); secs\.style\.display = "none";/);
  assert.match(FEED, /bgBtn\.textContent = "background"/, "a real labeled button, no caret/parens");
  assert.match(FEED, /takeBtn\.textContent = "summary"/);
  assert.match(FEED, /secs\.append\(bgBtn, bgBody, takeBtn, distill\)/, "one container, section order kept");
  assert.match(FEED, /a\._secs = secs; a\._bgBtn = bgBtn; a\._bgBody = bgBody; a\._bgLess = bgLess;/);
  assert.match(FEED, /background\?: string \| null;/, "the AskItem carries the kernel's background field");
  // side-by-side falls out of layout: buttons are flex:none, bodies flex-basis 100%
  assert.match(CSS, /\.fask-secs \{ display: flex; flex-wrap: wrap;/);
  assert.match(CSS, /\.fask-secbtn \{ flex: none;/);
  assert.match(CSS, /\.fask-bg-body \{ flex: 1 1 100%;/);
  assert.match(CSS, /\.fask-secs \.fask-distill \{ flex: 1 1 100%;/);
});

test("the buttons wear the Clear chrome with a neutral hover", () => {
  assert.match(CSS, /\.fask-secbtn \{[^}]*border: 1px solid var\(--card-border\)/);
  assert.match(CSS, /\.fask-secbtn \{[^}]*border-radius: 6px/);
  assert.match(CSS, /\.fask-secbtn:hover \{ color: var\(--fg\); border-color: var\(--fg\); \}/,
               "neutral hover — folding is not destructive, no Clear red");
});

test("open sections collapse via a block 'less' on its own line (bottom-left, never a wrap artifact)", () => {
  assert.match(FEED, /bgLess\.textContent = "less"/);
  assert.match(FEED, /takeLess\.textContent = "less"/);
  assert.match(FEED, /a\._bgBody\.appendChild\(a\._bgLess\);/);
  assert.match(FEED, /\(a\._distill as HTMLElement\)\.appendChild\(a\._takeLess\);/);
  assert.match(CSS, /\.fask-less \{ display: block; margin-top: 5px; \}/,
               "block-level: its own line under the text, left-aligned with it");
});

test("defaults + state: background collapsed, takeaway expanded; flips drive per-card sets", () => {
  assert.match(FEED, /const bgOpen = new Set<string>\(\);/);
  assert.match(FEED, /const takeClosed = new Set<string>\(\);/);
  assert.match(FEED, /const bgIsOpen = !!bg && bgOpen\.has\(id\);/);
  assert.match(FEED, /const takeIsOpen = !takeClosed\.has\(id\);/);
  const flips = FEED.match(/ev\.stopPropagation\(\);\s*\n\s*if \((?:bgOpen|takeClosed)\.has\(id\)\)/g) || [];
  assert.equal(flips.length, 2, "each section's flip stops the card-body click");
  assert.match(FEED, /a\._takeBtn\.onclick = flipTake;\s*\n\s*a\._takeLess\.onclick = flipTake;/);
  assert.match(FEED, /a\._bgBtn\.onclick = flipBg;\s*\n\s*a\._bgLess\.onclick = flipBg;/);
});

test("the gap exists only while a section is expanded, riding the visible bg element", () => {
  assert.match(FEED, /a\._secs\.classList\.toggle\("gap", !!bg && \(bgIsOpen \|\| takeIsOpen\)\);/);
  assert.match(CSS, /\.fask-secs\.gap > \.fask-bg-part \{ margin-bottom: 1\.2em; \}/);
});

test("the MODAL always shows BOTH sections, labeled background / summary", () => {
  assert.match(FEED, /const modalBg = node\.id === it\.itemId && nodeDistill && it\.background \? it\.background : null;/);
  assert.match(FEED, /bl\.textContent = "background"/);
  assert.match(FEED, /sl\.textContent = "summary"/);
  assert.match(CSS, /\.ftree-seclabel \{[^}]*var\(--dim\)/);
});

test("background shows only alongside a produced takeaway, and the takeaway keeps its deep-link", () => {
  assert.match(FEED, /const bg = distillShown && it\.background \? it\.background : null;/);
  assert.match(FEED, /applyDistillSections\(a, it, distillShown\);/);
  assert.match(FEED, /dl\.classList\.add\("fask-distill-link"\)/);
  // the background body stays typographically identical to the summary
  assert.match(CSS, /\.fask-bg-body \{[^}]*font-size: 0\.86em/);
  assert.match(CSS, /\.fask-bg-body \{[^}]*opacity: 0\.82/);
  // feed.css must define --box-border itself (border shorthand with an undefined var() is VOID)
  assert.match(CSS, /--box-border: rgba\(255, 255, 255, 0\.12\)/);
});
