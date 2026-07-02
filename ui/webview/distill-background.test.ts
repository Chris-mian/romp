// The card's TWO collapsible distiller sections (the user 2026-07-02): a returning reader often forgot
// what the thread was about, so the distiller now writes a BACKGROUND section (re-orientation) above the
// takeaway. BACKGROUND is collapsed by default ("+ background"); the takeaway is expanded by default with
// a leading − and collapses to "+ summary". Collapse state is keyed by itemId in module sets so the keyed
// incremental re-render never snaps a section shut. No jsdom — pin the wiring at source (repo convention).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

test("the card builds both sections and registers their refs", () => {
  assert.match(FEED, /const bgSec = el\("div", "fask-sec fask-bg"\); bgSec\.style\.display = "none";/);
  assert.match(FEED, /const takeSec = el\("div", "fask-sec fask-take"\); takeSec\.style\.display = "none";/);
  assert.match(FEED, /bgLabel\.textContent = "background"/);
  assert.match(FEED, /takeLabel\.textContent = "summary"/);
  assert.match(FEED, /takeSec\.append\(takeBtn, takeLabel, distill\)/, "the takeaway section WRAPS the existing distill line");
  assert.match(FEED, /a\._bgSec = bgSec; a\._bgBtn = bgBtn; a\._bgBody = bgBody;/);
  assert.match(FEED, /background\?: string \| null;/, "the AskItem carries the kernel's background field");
});

test("defaults: background collapsed, takeaway expanded; +/− toggles flip per-card sets", () => {
  assert.match(FEED, /const bgOpen = new Set<string>\(\);/);
  assert.match(FEED, /const takeClosed = new Set<string>\(\);/);
  // + when closed, − when open (the user asked for plus/minus buttons)
  assert.match(FEED, /btn\.textContent = open \? "−" : "\+";/);
  // background: open only when the user opened it; takeaway: open unless the user closed it
  assert.match(FEED, /const open = bgOpen\.has\(id\);/);
  assert.match(FEED, /const open = !takeClosed\.has\(id\);/);
  // both toggles stop propagation — the card-body click opens the modal
  const toggles = FEED.match(/ev\.stopPropagation\(\);\s*\n\s*if \((?:bgOpen|takeClosed)\.has\(id\)\)/g) || [];
  assert.equal(toggles.length, 2, "each section's toggle stops the card-body click");
});

test("background shows only alongside a produced takeaway, and the takeaway keeps its deep-link", () => {
  assert.match(FEED, /const bg = distillShown && it\.background \? it\.background : null;/);
  assert.match(FEED, /applyDistillSections\(a, it, distillShown\);/);
  // the takeaway's click-to-anchor wiring is untouched (it lives on the distill line itself)
  assert.match(FEED, /dl\.classList\.add\("fask-distill-link"\)/);
});

test("the section chrome is styled: small square +/− buttons, muted labels, indented background body", () => {
  assert.match(CSS, /\.fask-sec \{ display: flex; flex-wrap: wrap;/);
  assert.match(CSS, /\.fask-sec-btn \{[^}]*cursor: pointer/);
  assert.match(CSS, /\.fask-sec-label \{[^}]*var\(--dim\)/);
  assert.match(CSS, /\.fask-bg-body \{[^}]*pre-wrap/);
});
