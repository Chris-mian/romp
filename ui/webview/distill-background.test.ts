// The card's TWO collapsible distiller sections (the user 2026-07-02): a returning reader often forgot
// what the thread was about, so the distiller now writes a BACKGROUND section (re-orientation) above the
// takeaway. Disclosure is BARE muted text in the chat followup-header's own language — collapsed rows
// read "▸ (background)" / "▸ (summary)" at the body's size; open, the label disappears (the text is its
// own label) and the collapse control is a small inline "less" button in the Clear button's chrome,
// trailing the last line. One empty line always separates the background from the summary. Collapse
// state is keyed by itemId in module sets so the keyed incremental re-render never snaps a section
// shut. No jsdom — pin the wiring at source (repo convention).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

test("the card builds both sections and registers their refs", () => {
  assert.match(FEED, /const bgSec = el\("div", "fask-sec fask-bg"\); bgSec\.style\.display = "none";/);
  assert.match(FEED, /const takeSec = el\("div", "fask-sec fask-take"\); takeSec\.style\.display = "none";/);
  assert.match(FEED, /bgName\.textContent = "\(background\)"/, "parenthesized collapsed label");
  assert.match(FEED, /takeName\.textContent = "\(summary\)"/, "parenthesized collapsed label");
  assert.match(FEED, /takeSec\.append\(takeBtn, distill\)/, "the takeaway section WRAPS the existing distill line");
  assert.match(FEED, /a\._bgSec = bgSec; a\._bgBtn = bgBtn; a\._bgBody = bgBody; a\._bgLess = bgLess;/);
  assert.match(FEED, /background\?: string \| null;/, "the AskItem carries the kernel's background field");
});

test("disclosure is the chat's ▸ language; open, BOTH labels vanish and an inline 'less' trails the text", () => {
  // same glyph the ↩ Follow-up header uses — one visual language across chat + feed
  assert.match(FEED, /bgTri\.textContent = "▸";/);
  assert.match(FEED, /takeTri\.textContent = "▸";/);
  // open = symmetric for both sections: label row hidden, the "less" button appended after the text
  assert.match(FEED, /bgLess\.textContent = "less"/);
  assert.match(FEED, /takeLess\.textContent = "less"/);
  assert.match(FEED, /a\._bgBtn\.style\.display = open \? "none" : "";/, "the background label vanishes when open");
  assert.match(FEED, /a\._takeBtn\.style\.display = open \? "none" : "";/);
  assert.match(FEED, /a\._bgBody\.appendChild\(a\._bgLess\);/, "the less button trails the background's last line");
  assert.match(FEED, /\(a\._distill as HTMLElement\)\.appendChild\(a\._takeLess\);/, "and the summary's");
});

test("defaults: background collapsed, takeaway expanded; the flips drive per-card sets", () => {
  assert.match(FEED, /const bgOpen = new Set<string>\(\);/);
  assert.match(FEED, /const takeClosed = new Set<string>\(\);/);
  assert.match(FEED, /const open = bgOpen\.has\(id\);/);
  assert.match(FEED, /const open = !takeClosed\.has\(id\);/);
  // both flips stop propagation — the card-body click opens the modal
  const flips = FEED.match(/ev\.stopPropagation\(\);\s*\n\s*if \((?:bgOpen|takeClosed)\.has\(id\)\)/g) || [];
  assert.equal(flips.length, 2, "each section's flip stops the card-body click");
  assert.match(FEED, /a\._takeBtn\.onclick = flipTake;\s*\n\s*a\._takeLess\.onclick = flipTake;/);
  assert.match(FEED, /a\._bgBtn\.onclick = flipBg;\s*\n\s*a\._bgLess\.onclick = flipBg;/);
});

test("background shows only alongside a produced takeaway, and the takeaway keeps its deep-link", () => {
  assert.match(FEED, /const bg = distillShown && it\.background \? it\.background : null;/);
  assert.match(FEED, /applyDistillSections\(a, it, distillShown\);/);
  assert.match(FEED, /dl\.classList\.add\("fask-distill-link"\)/);
});

test("the chrome is BARE text: no borders, no pills; typography matches the summary", () => {
  assert.match(CSS, /\.fask-sec \{ display: flex; flex-wrap: wrap;/);
  assert.match(CSS, /\.fask-sec-head \{[^}]*border: 0/, "no box around the disclosure row");
  assert.match(CSS, /\.fask-sec-head \{[^}]*background: none/);
  assert.match(CSS, /\.fask-sec-head \{[^}]*font-size: 0\.86em/, "collapsed rows read at BODY size (the user 2026-07-02)");
  assert.match(CSS, /\.fask-sec-head:hover \{ color: var\(--fg\); \}/, "hover brightens — that IS the affordance");
  // the trailing "less" wears the Clear button's chrome (border + radius), inline after the text
  assert.match(CSS, /\.fask-sec-less \{[^}]*border: 1px solid var\(--card-border\)/);
  assert.match(CSS, /\.fask-sec-less \{[^}]*border-radius: 6px/);
  assert.match(CSS, /\.fask-sec-less \{[^}]*margin-left: 18px/, "a wide gap before the less button");
  // one empty line separates the sections ONLY while either is expanded; collapsed rows fall together
  assert.match(CSS, /\.fask-sec\.fask-bg\.gap \{ margin-bottom: 1\.2em; \}/);
  assert.match(FEED, /a\._bgSec\.classList\.toggle\("gap", !!bg && \(bgOpen\.has\(id\) \|\| !takeClosed\.has\(id\)\)\);/);
  // the background body is typographically IDENTICAL to the summary (.fask-distill)
  assert.match(CSS, /\.fask-bg-body \{[^}]*font-size: 0\.86em/);
  assert.match(CSS, /\.fask-bg-body \{[^}]*opacity: 0\.82/);
  assert.doesNotMatch(CSS, /\.fask-bg-body \{[^}]*margin-left/);
  assert.match(CSS, /\.fask-bg-body \{[^}]*pre-wrap/);
  // feed.css must define --box-border itself (border shorthand with an undefined var() is VOID — the
  // await-paused outline silently lost its border this way; the user 2026-07-02)
  assert.match(CSS, /--box-border: rgba\(255, 255, 255, 0\.12\)/);
});

test("the footer Collapse button compacts every card in one click, then flips to Expand", () => {
  // the user 2026-07-02: a bulk view action beside Sub-goals / Clear all — closes every background AND
  // summary; with nothing open it restores the DEFAULTS (takeClosed.clear() — summaries open, backgrounds
  // stay closed, never force-opened). View-only: no kernel message.
  assert.match(FEED, /function anySectionOpen\(\): boolean \{\s*\n\s*return asks\.some\(\(it\) => !takeClosed\.has\(it\.itemId\) \|\| bgOpen\.has\(it\.itemId\)\);/);
  assert.match(FEED, /b\.id = "feed-collapseall";/);
  assert.match(FEED, /bgOpen\.clear\(\);\s*\n\s*for \(const it of asks\) takeClosed\.add\(it\.itemId\);/);
  assert.match(FEED, /takeClosed\.clear\(\);\s+\/\/ back to defaults/);
  assert.match(FEED, /collapseAll\.textContent = anySectionOpen\(\) \? "Collapse" : "Expand";/);
  // same footer chrome as Undo clear (blue hover), rendered whenever the footer shows cards
  assert.match(FEED, /const b = el\("button", "fdismiss ffollow"\);   \/\/ view action/);
  const mk = FEED.slice(FEED.indexOf("function makeCollapseAllBtn"), FEED.indexOf("function ensureCollapseAll"));
  assert.doesNotMatch(mk, /postMessage/, "view-only — collapsing never talks to the kernel");
});
