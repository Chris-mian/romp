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

test("sending with a GOAL citation routes as an askFollowUp (reopen) and consumes the chip", () => {
  assert.match(RENDER, /const cite = composerCitations\.get\(activeId\);/);
  assert.match(RENDER, /if \(cite\?\.itemId\) vscodeApi\.postMessage\(\{ type: "askFollowUp", itemId: cite\.itemId, text \}\);/);
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
  assert.match(RENDER, /if \(c\.itemId && gone\.has\(c\.itemId\)\) \{ composerCitations\.delete\(sid\);/);   // quote chips cite no goal → never dropped by a card clear
});

test("a sub-goal click cites ITSELF, not the card's top goal (the user 2026-07-01)", () => {
  // wireNodeZones posts the clicked node's own id as showOnTimeline.itemId — the kernel's _cite_for then
  // seeds the chip (title + audit preview) from THAT node, so the chip context is specific, never the
  // generic top-goal quote. The kernel uses itemId only for the citation; navigation is anchorUuid-based.
  assert.match(FEED, /const navId = node\.id \|\| it\.turnId;/);
  assert.doesNotMatch(FEED, /const navId = node\.kind === "handoff" \? node\.id : it\.turnId;/);
});

test("highlighting transcript text seeds a QUOTE chip — the same chip, reply-context flavored (the user 2026-07-13)", () => {
  // two flavors on one Citation: a goal chip (itemId) or a quote chip (quote [+ the turn's uuid])
  assert.match(RENDER, /interface Citation \{ itemId\?: string; title: string; quote\?: string; uuid\?: string \| null; src\?: string \}/);
  // event-based on selectionchange; BOTH endpoints must sit inside transcript turns, so composer/tab
  // selections never seed; a collapse never clears (clicking into the composer must not eat the chip)
  assert.match(RENDER, /document\.addEventListener\("selectionchange", \(\) => \{/);
  assert.match(RENDER, /if \(!sel \|\| !sel\.rangeCount \|\| sel\.isCollapsed\) return;\s*\/\/ never clear on collapse/);
  assert.match(RENDER, /const a = turnOf\(sel\.anchorNode\), f = turnOf\(sel\.focusNode\);/);
  assert.match(RENDER, /if \(!a \|\| !f\) return;/);
  // seeding NEVER focuses the composer — a focus steal would collapse the selection mid-drag
  const seeder = RENDER.split("function setQuoteCitation(")[1].split("\n}")[0];
  assert.doesNotMatch(seeder, /focusComposer/);
  assert.match(seeder, /quote: quote\.slice\(0, QUOTE_CAP\)/);
});

test("a quote chip sends a plain message wrapped by quoteReplyBody — never askFollowUp (no goal to reopen)", () => {
  assert.match(RENDER, /if \(cite\?\.itemId\) vscodeApi\.postMessage\(\{ type: "askFollowUp", itemId: cite\.itemId, text \}\);/);
  assert.match(RENDER, /else if \(cite\?\.quote\) vscodeApi\.postMessage\(\{ type: "sendMessage", id: activeId, text: quoteReplyBody\(cite\.quote, text, cite\.src\) \}\);/);
  // the wrap: a lead-in + the highlighted text as a markdown quote block, then the typed message
  assert.match(RENDER, /return lead \+ "\\n" \+ q \+ "\\n\\n" \+ text;/);
  // the chip's audit preview shows the SAME composed body, client-side (no /followup-preview fetch)
  assert.match(RENDER, /body\.textContent = quoteReplyBody\(cite\.quote \|\| "", draft \|\| "\(your message\)", cite\.src\);/);
  // a quote chip wears the typographic quote mark; the goal chip keeps ↩
  assert.match(RENDER, /mark\.textContent = cite\.quote \? "“" : "↩";/);
  // clearing a card drops only GOAL chips citing it — a quote chip cites no goal
  assert.match(RENDER, /if \(c\.itemId && gone\.has\(c\.itemId\)\)/);
});

test("right-click Reply drops the auto-seeded quote chip — the quote is in the composer now, never sent twice", () => {
  // the selection that opened the context menu also seeded the chip (selectionchange); quoting it into the
  // composer text must consume the chip, or the send would wrap an already-quoted message again
  assert.match(RENDER, /if \(c\?\.quote\) \{ composerCitations\.delete\(activeId\); renderComposerChips\(activeId\); \}/);
});

test("a VS Code EDITOR highlight seeds the same chip, labeled + wrapped with its file:lines origin (the user 2026-07-13)", () => {
  // the extension host posts editorSelection {text, src} on onDidChangeTextEditorSelection (see
  // vscode-extension/src editor-selection pins); the webview seeds the quote chip from it
  assert.match(RENDER, /m\.type === "editorSelection" && typeof m\.text === "string" && m\.text\.trim\(\) && activeId/);
  assert.match(RENDER, /setQuoteCitation\(activeId, m\.text, null, typeof m\.src === "string" \? m\.src : undefined\);/);
  // the chip title leads with the origin; the wrap lead-in points at the code, not the conversation
  assert.match(RENDER, /const title = \(src \? src \+ " — " \+ snip : snip\)\.slice\(0, 140\);/);
  assert.match(RENDER, /const lead = src \? "Replying to this highlighted code \(" \+ src \+ "\):" : "Replying to this part of the conversation:";/);
  // both consumers thread the origin through: the send wrap and the chip's audit preview
  assert.match(RENDER, /quoteReplyBody\(cite\.quote, text, cite\.src\)/);
  assert.match(RENDER, /quoteReplyBody\(cite\.quote \|\| "", draft \|\| "\(your message\)", cite\.src\)/);
});
