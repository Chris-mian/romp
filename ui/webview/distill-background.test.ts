// The card's TWO collapsible distiller sections (the user 2026-07-02): a returning reader often forgot
// what the thread was about, so the distiller now writes a BACKGROUND section (re-orientation) above the
// takeaway. Disclosure is BARE muted text in the chat followup-header's own language — "▸ background"
// flips to ▾ with the body below, no border/pill/fill (Notion-toggle / Finder-disclosure; the pill and
// circle attempts both read clunky). The open takeaway has no header — its text IS the content, full card
// width — and collapses via a quiet trailing "less" link (the App Store more/less pattern), reopening
// from a "▸ summary" row. Collapse state is keyed by itemId in module sets so the keyed incremental
// re-render never snaps a section shut. No jsdom — pin the wiring at source (repo convention).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

test("the card builds both sections and registers their refs", () => {
  assert.match(FEED, /const bgSec = el\("div", "fask-sec fask-bg"\); bgSec\.style\.display = "none";/);
  assert.match(FEED, /const takeSec = el\("div", "fask-sec fask-take"\); takeSec\.style\.display = "none";/);
  assert.match(FEED, /bgName\.textContent = "background"/);
  assert.match(FEED, /takeName\.textContent = "summary"/);
  assert.match(FEED, /takeSec\.append\(takeBtn, distill\)/, "the takeaway section WRAPS the existing distill line");
  assert.match(FEED, /a\._bgSec = bgSec; a\._bgBtn = bgBtn; a\._bgBody = bgBody; a\._bgLess = bgLess;/);
  assert.match(FEED, /background\?: string \| null;/, "the AskItem carries the kernel's background field");
});

test("disclosure is the chat's ▸ language; open, BOTH labels vanish and only (▾) trails the text", () => {
  // same glyph the ↩ Follow-up header uses — one visual language across chat + feed
  assert.match(FEED, /bgTri\.textContent = "▸";/);
  assert.match(FEED, /takeTri\.textContent = "▸";/);
  // open = symmetric for both sections: label row hidden, "(▾)" appended after the text (no words)
  assert.match(FEED, /bgLess\.textContent = "\(▾\)"/);
  assert.match(FEED, /takeLess\.textContent = "\(▾\)"/);
  assert.match(FEED, /a\._bgBtn\.style\.display = open \? "none" : "";/, "the background label vanishes when open");
  assert.match(FEED, /a\._takeBtn\.style\.display = open \? "none" : "";/);
  assert.match(FEED, /a\._bgBody\.appendChild\(a\._bgLess\);/, "the (▾) trails the background's last line");
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
  assert.match(CSS, /\.fask-sec-less \{[^}]*border: 0/, "the trailing (▾) is naked text, not a button box");
  assert.match(CSS, /\.fask-sec-less \{[^}]*margin-left: 18px/, "a wide ~2-space gap before the (▾)");
  // the background body is typographically IDENTICAL to the summary (.fask-distill)
  assert.match(CSS, /\.fask-bg-body \{[^}]*font-size: 0\.86em/);
  assert.match(CSS, /\.fask-bg-body \{[^}]*opacity: 0\.82/);
  assert.doesNotMatch(CSS, /\.fask-bg-body \{[^}]*margin-left/);
  assert.match(CSS, /\.fask-bg-body \{[^}]*pre-wrap/);
  // feed.css must define --box-border itself (border shorthand with an undefined var() is VOID — the
  // await-paused outline silently lost its border this way; the user 2026-07-02)
  assert.match(CSS, /--box-border: rgba\(255, 255, 255, 0\.12\)/);
});
