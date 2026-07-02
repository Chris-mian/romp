// Click-to-cite (the user 2026-07-01): clicking a feed card's summary or a sub-goal into the chat seeds a
// dismissible "citation" chip in the composer. Sending WITH the chip routes as a follow-up (askFollowUp) so
// the goal's context rides along and the goal reopens (done→working, unless cleared); the chip is dismissible
// by its ✕ or by Backspace at the very start of the box ("like a character"). No jsdom for this renderer, so
// pin the wiring at source (the repo convention).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");
const SKELETON = fs.readFileSync(path.resolve(process.cwd(), "src", "page-skeleton.ts"), "utf8");

test("the composer has a chip strip above the textarea", () => {
  assert.match(SKELETON, /<div id="composer-chips" style="display:none"><\/div><textarea id="composer-input"/);
  assert.match(CSS, /#composer-chips \{ display: flex/);
  assert.match(CSS, /\.composer-chip \{/);
});

test("a focus message carrying a cite seeds the composer citation", () => {
  // the kernel attaches cite:{itemId,title} to the chat focus when a card click resolves to a live goal
  assert.match(RENDER, /if \(m\.cite && typeof m\.cite\.itemId === "string" && typeof m\.cite\.title === "string"\) setCitation\(m\.id, \{ itemId: m\.cite\.itemId, title: m\.cite\.title \}\);/);
  assert.match(RENDER, /const composerCitations = new Map<string, Citation>\(\);/);
  assert.match(RENDER, /function setCitation\(id: string, cite: Citation\): void/);
});

test("the chip renders a pill with the cited title + a dismiss ✕", () => {
  assert.match(RENDER, /function renderComposerChips\(id: string \| null\): void/);
  assert.match(RENDER, /el\("div", "composer-chip"\)/);
  assert.match(RENDER, /el\("span", "composer-chip-label"\); label\.textContent = cite\.title;/);
  assert.match(RENDER, /el\("button", "composer-chip-x"\)/);
  // ✕ dismisses but stops the click from also opening the audit preview
  assert.match(RENDER, /x\.addEventListener\("click", \(e\) => \{ e\.stopPropagation\(\); if \(id\) removeCitation\(id\); \}\);/);
});

test("clicking the chip opens an audit preview of the exact prompt from /followup-preview (the user 2026-07-01)", () => {
  assert.match(RENDER, /chip\.addEventListener\("click", \(\) => \{ if \(id\) openCitePreview\(id, chip\); \}\);/);
  assert.match(RENDER, /function openCitePreview\(id: string, anchor: HTMLElement\): void/);
  // fetches the REAL wrapped body (kernel _followup_body) with the current draft substituted, escaped as text
  assert.match(RENDER, /"\/followup-preview\?itemId=" \+ encodeURIComponent\(cite\.itemId\) \+ "&text=" \+ encodeURIComponent\(draft\)/);
  assert.match(RENDER, /el\("pre", "cite-preview-body"\)/);
  assert.match(RENDER, /body\.textContent = \(d && typeof d\.body === "string" && d\.body\)/);
  // Esc / outside-click / re-render close it
  assert.match(RENDER, /function closeCitePreview\(\): void/);
  assert.match(RENDER, /if \(e\.key === "Escape"\) \{ e\.preventDefault\(\); closeCitePreview\(\); \}/);
});

test("Backspace at the start of the box deletes the citation like a character", () => {
  assert.match(RENDER, /e\.key === "Backspace" && !e\.metaKey && !e\.ctrlKey && ta\.selectionStart === 0 && ta\.selectionEnd === 0\s*\n\s*&& activeId && composerCitations\.has\(activeId\)/);
  assert.match(RENDER, /removeCitation\(activeId\);/);
});

test("sending with a citation routes as an askFollowUp (reopen) and consumes the chip", () => {
  assert.match(RENDER, /const cite = composerCitations\.get\(activeId\);/);
  assert.match(RENDER, /if \(cite\) vscodeApi\.postMessage\(\{ type: "askFollowUp", itemId: cite\.itemId, text \}\);/);
  assert.match(RENDER, /else vscodeApi\.postMessage\(\{ type: "sendMessage", id: activeId, text \}\);/);
  assert.match(RENDER, /if \(cite\) \{ composerCitations\.delete\(activeId\); renderComposerChips\(activeId\); \}/);
});

test("a citation survives a RELOAD but is dropped on tab SWITCH (the user 2026-07-01)", () => {
  // persisted so a mid-reply reload keeps the chip
  assert.match(RENDER, /citations: Object\.fromEntries\(composerCitations\)/);
  assert.match(RENDER, /const savedCites = \(\(vscodeApi\?\.getState\?\.\(\) \|\| \{\}\) as any\)\.citations;/);
  assert.match(RENDER, /renderComposerChips\(activeId\);\s*\/\/ a citation persisted across the reload/);
  // but switching AWAY from a tab abandons its chip (a "reply right now" intent)
  assert.match(RENDER, /if \(ta\.value\) drafts\.set\(activeId, ta\.value\); else drafts\.delete\(activeId\);\s*\n[\s\S]*?composerCitations\.delete\(activeId\);/);
});

test("clearing a card drops any composer chip pointing INTO it (the user 2026-07-01)", () => {
  // the kernel pushes dropCitation{itemId, itemIds: the card's whole subtree} on a single clear — a chip
  // can cite a SUB-goal (wireNodeZones sends the clicked node's id) — and dropCitationsAll on Clear-all
  assert.match(RENDER, /m\.type === "dropCitation" && typeof m\.itemId === "string"\) dropCitationByItem\(m\.itemId, Array\.isArray\(m\.itemIds\)/);
  assert.match(RENDER, /m\.type === "dropCitationsAll"\) \{[\s\S]*?composerCitations\.clear\(\); persistDrafts\(\); renderComposerChips\(activeId\);/);
  // dropCitationByItem removes every chip citing the card OR any node under it
  assert.match(RENDER, /function dropCitationByItem\(itemId: string, itemIds\?: string\[\]\): void/);
  assert.match(RENDER, /const gone = new Set\(itemIds && itemIds\.length \? itemIds : \[itemId\]\);/);
  assert.match(RENDER, /if \(gone\.has\(c\.itemId\)\) \{ composerCitations\.delete\(sid\);/);
});

test("a sub-goal click cites ITSELF, not the card's top goal (the user 2026-07-01)", () => {
  // wireNodeZones posts the clicked node's own id as showOnTimeline.itemId — the kernel's _cite_for then
  // seeds the chip (title + audit preview) from THAT node, so the chip context is specific, never the
  // generic top-goal quote. The kernel uses itemId only for the citation; navigation is anchorUuid-based.
  assert.match(FEED, /const navId = node\.id \|\| it\.turnId;/);
  assert.doesNotMatch(FEED, /const navId = node\.kind === "handoff" \? node\.id : it\.turnId;/);
});
