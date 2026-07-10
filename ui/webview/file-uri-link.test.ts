// Bare file:// URLs in a CHAT message (the user 2026-07-06): a link like
// file:///Users/me/analysis/trace.pdf pasted into a message should be clickable and open the file — marked
// doesn't autolink the file: scheme and DOMPurify strips it, so linkifyFileUris wraps them post-render into
// a clickable .file-uri-link that routes to the host opener. NOT applied to tool-use summaries. The renderer
// has no jsdom harness, so pin the wiring at source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("a bare file:// URL becomes a clickable .file-uri-link that opens the file in the host app", () => {
  assert.match(RENDER, /function linkifyFileUris\(root: HTMLElement, skipThumbs\?: string\[\]\): void/);
  assert.match(RENDER, /el\("span", "file-uri-link"\)/);
  // clicking routes to the host opener (kernel `open <path>`), NOT a blocked window.open(file://) — a file://
  // URI is absolute, so it goes through the shared openPathLink's no-session-id branch
  assert.match(RENDER, /function fileUriLink\(uri: string\): HTMLElement \{ return openPathLink\(uri, fileUriToPath\(uri\)\); \}/);
  assert.match(RENDER, /\{ type: "openFile", path: open \}/);
  // the URL is turned into a real filesystem path: scheme stripped, percent-decoded
  assert.match(RENDER, /\.replace\(\/\^file:/);
  assert.match(RENDER, /decodeURIComponent\(p\)/);
});

test("linkify runs on BOTH chat message bodies (assistant reply + user bubble) and nowhere else — never tool summaries", () => {
  assert.match(RENDER, /linkifyFileUris\(body\)/);             // the assistant reply
  assert.match(RENDER, /linkifyFileUris\(bubble, imgPaths\)/); // your own / a romp-injected bubble (in-bubble images don't re-thumb)
  // exactly the definition + those two applications — so tool-use reports/summaries stay untouched
  const uses = RENDER.match(/linkifyFileUris\(/g) || [];
  assert.equal(uses.length, 3, "linkifyFileUris is defined once and applied to exactly the two chat bodies");
});

test("linkify works inside INLINE backticks (agents backtick paths), skips only fenced code + existing links, trims trailing punctuation", () => {
  // inline <code> is NOT skipped — a `file://…` path in backticks still linkifies; only fenced <pre> + links are skipped
  assert.match(RENDER, /closest\("a, \.file-uri-link, pre"\)/);
  assert.doesNotMatch(RENDER, /closest\("a, \.file-uri-link, code, pre"\)/);
  assert.match(RENDER, /tok = tok\.slice\(0, tok\.length - trail\[0\]\.length\)/);
});

test(".file-uri-link is styled as a wrapping accent link", () => {
  assert.match(CSS, /\.file-uri-link \{[\s\S]*?cursor: pointer[\s\S]*?color: var\(--accent\)/);
  assert.match(CSS, /\.file-uri-link:hover \{ text-decoration: underline; \}/);
});
