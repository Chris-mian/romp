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
  assert.match(FEED, /secs\.append\(bgBtn, bgBody, bgLessRow, takeBtn, distill, takeLessRow\)/,
               "one container, section order kept (less rows as siblings)");
  assert.match(FEED, /a\._secs = secs; a\._bgBtn = bgBtn; a\._bgBody = bgBody; a\._bgLess = bgLess; a\._bgLessRow = bgLessRow;/);
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

test("open sections collapse via a 'less' SIBLING row — never a child of the link text", () => {
  assert.match(FEED, /bgLess\.textContent = "less"/);
  assert.match(FEED, /takeLess\.textContent = "less"/);
  // the summary text is a deep-link with its own hover underline/fill; the less button collapses —
  // different functions, so it must hover independently (the user 2026-07-02). A child would inherit
  // the link's hover chrome; a sibling row cannot.
  assert.match(FEED, /const bgLessRow = el\("div", "fask-lessrow"\); bgLessRow\.appendChild\(bgLess\);/);
  assert.match(FEED, /secs\.append\(bgBtn, bgBody, bgLessRow, takeBtn, distill, takeLessRow\);/);
  assert.doesNotMatch(FEED, /_bgBody\.appendChild\(a\._bgLess\)/, "never re-nested into the body");
  assert.doesNotMatch(FEED, /_distill as HTMLElement\)\.appendChild\(a\._takeLess\)/, "never re-nested into the link");
  assert.match(CSS, /\.fask-lessrow \{ flex: 1 1 100%; min-width: 0; margin-top: 2px; \}/,
               "the full-width row gives the button its own line without stretching its box");
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

test("the gap exists only while a section is expanded, riding the bg section's LAST visible row", () => {
  assert.match(FEED, /a\._secs\.classList\.toggle\("gap", !!bg && \(bgIsOpen \|\| takeIsOpen\)\);/);
  assert.match(FEED, /a\._bgBtn\.classList\.toggle\("fask-gapend", !!bg && !bgIsOpen\);/);
  assert.match(FEED, /a\._bgLessRow\.classList\.toggle\("fask-gapend", bgIsOpen\);/,
               "open → the margin sits AFTER the less row, never between the body and its own less");
  assert.match(CSS, /\.fask-secs\.gap > \.fask-gapend \{ margin-bottom: 1\.2em; \}/);
});

test("the MODAL always shows BOTH sections, labeled background / summary", () => {
  assert.match(FEED, /const modalBg = node\.id === it\.itemId && nodeDistill && it\.background \? it\.background : null;/);
  assert.match(FEED, /bl\.textContent = "background"/);
  assert.match(FEED, /sl\.textContent = "summary"/);
  assert.match(CSS, /\.ftree-seclabel \{[^}]*var\(--dim\)/);
  // label size sits BETWEEN the section text (0.86em) and the tree/checklist lines (1em)
  assert.match(CSS, /\.ftree-seclabel \{ font-size: 0\.92em;/);
  // modal times match the checklist lines they correspond to, never bold (the user 2026-07-02)
  assert.match(CSS, /\.ftree-meta \{[^}]*font-size: 0\.9em; font-weight: 400;/);
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
