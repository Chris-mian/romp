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

test("ONE flex-wrap container holds always-visible toggles + full-width bodies", () => {
  assert.match(FEED, /const secs = el\("div", "fask-secs"\); secs\.style\.display = "none";/);
  assert.match(FEED, /bgBtn\.textContent = "Background"/, "capitalized like Clear (the user 2026-07-02)");
  assert.match(FEED, /takeBtn\.textContent = "Summary"/);
  assert.match(FEED, /secs\.append\(bgBtn, bgBody, takeBtn, distill\)/, "one container, section order kept");
  assert.match(FEED, /a\._secs = secs; a\._bgBtn = bgBtn; a\._bgBody = bgBody; a\._takeBtn = takeBtn;/);
  assert.match(FEED, /background\?: string \| null;/, "the AskItem carries the kernel's background field");
  // side-by-side falls out of layout: buttons are flex:none, bodies flex-basis 100%
  assert.match(CSS, /\.fask-secs \{ display: flex; flex-wrap: wrap;/);
});

test("the buttons wear the Clear chrome with a neutral hover", () => {
  assert.match(CSS, /\.fask-secbtn \{[^}]*border: 1px solid var\(--card-border\)/);
  assert.match(CSS, /\.fask-secbtn \{[^}]*border-radius: 6px/);
  assert.match(CSS, /\.fask-secbtn:hover \{ color: var\(--fg\); border-color: var\(--fg\); \}/,
               "neutral hover — folding is not destructive, no Clear red");
});

test("the buttons ARE the toggles: pressed state reads at a glance, no separate less", () => {
  // round 7 (the user 2026-07-02): clicking Background/Summary expands AND collapses — the button stays
  // pressed (.on, bright + filled) while its section shows. No "less" control anywhere.
  assert.match(FEED, /a\._bgBtn\.classList\.toggle\("on", bgIsOpen\);/);
  assert.match(FEED, /a\._takeBtn\.classList\.toggle\("on", takeIsOpen\);/);
  assert.match(FEED, /a\._bgBtn\.setAttribute\("aria-pressed", bgIsOpen \? "true" : "false"\);/);
  // selected = the rail toggles' accent language: blue text, accent border, faint accent wash, bolder
  assert.match(CSS, /\.fask-secbtn\.on \{ color: var\(--accent\); border-color: var\(--accent\);\n  background: rgba\(156, 210, 255, 0\.10\); font-weight: 600; \}/);
  assert.match(CSS, /--accent: #9cd2ff;/, "feed.css defines --accent in its own :root");
  assert.doesNotMatch(FEED, /fask-less/, "the less control is gone");
  assert.doesNotMatch(CSS, /fask-lessrow/, "and its row styling with it");
});

test("defaults + state: background collapsed, takeaway expanded; flips drive per-card sets", () => {
  assert.match(FEED, /const bgOpen = new Set<string>\(\);/);
  assert.match(FEED, /const takeClosed = new Set<string>\(\);/);
  assert.match(FEED, /const bgIsOpen = !!bg && bgOpen\.has\(id\);/);
  assert.match(FEED, /const takeIsOpen = !takeClosed\.has\(id\);/);
  const flips = FEED.match(/ev\.stopPropagation\(\);\s*\n\s*if \((?:bgOpen|takeClosed)\.has\(id\)\)/g) || [];
  assert.equal(flips.length, 2, "each section's flip stops the card-body click");
  assert.match(FEED, /a\._bgBtn\.onclick = flipBg;/);
  assert.match(FEED, /a\._takeBtn\.onclick = flipTake;/);
});

test("one clear line splits the sections only while the background is open", () => {
  // both collapsed → [Background][Summary] tight on one row; background open → its body (which is what
  // stands between the two sections) carries the one-line gap before the Summary button below it
  assert.match(FEED, /a\._bgBody\.classList\.toggle\("fask-gapend", bgIsOpen\);/);
  assert.match(CSS, /\.fask-bg-body\.fask-gapend \{ margin-bottom: 1\.2em; \}/);
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
