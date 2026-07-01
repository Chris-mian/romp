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
  assert.match(RENDER, /x\.addEventListener\("click", \(\) => \{ if \(id\) removeCitation\(id\); \}\);/);
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

test("citations persist + restore like drafts (survive reload + tab switch)", () => {
  assert.match(RENDER, /citations: Object\.fromEntries\(composerCitations\)/);
  assert.match(RENDER, /const savedCites = \(\(vscodeApi\?\.getState\?\.\(\) \|\| \{\}\) as any\)\.citations;/);
  // restored on the one-shot post-reload pass, and on every tab switch
  assert.match(RENDER, /renderComposerChips\(activeId\);\s*\/\/ a citation persisted across the reload/);
});
