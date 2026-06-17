// The ledger overview tree (the summary below the tab title) as a checklist (the user 2026-06-16):
//  - the "(Xm ago)" times sit close to the content (the tree hugs its widest row) instead of way out at
//    the box's right edge, while staying right-aligned with each other;
//  - a DONE item uses the blue ✓ disc (same as the chat to-do / feed), a not-yet-done item a hollow ○;
//  - a done item's text is tinted to the SAME recency colour as its time.
// The chat renderer has no jsdom harness, so — like render-rail.test.ts — pin it at the source level.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "styles.css"), "utf8");

test("ledger marks: ▸ working, blue ✓ disc done, hollow ○ not-yet-done, ⏸ blocked", () => {
  assert.match(RENDER, /n\.current \? "▸" : n\.done \? "✓" : n\.blocked \? "⏸" : "○"/);
  // the done ✓ is the chat-style blue disc (white ✓ on --check-bg, round)
  assert.match(CSS, /\.ledger-tnode\.done \.ledger-tmark \{[^}]*var\(--check-bg\)/);
  assert.match(CSS, /\.ledger-tnode\.done \.ledger-tmark \{[^}]*border-radius: 50%/);
});

test("ledger: a done item's text takes its time's recency colour (ticks with the clock)", () => {
  // set on first render and again in refreshLedgerAges as the wall clock advances
  const hits = RENDER.match(/if \(n\.done && n\.t\) txt\.style\.color = ageColorReadable\(now - n\.t\)/g) || [];
  assert.equal(hits.length, 1, "render-loop tint");
  assert.match(RENDER, /if \(n && txt && n\.done && n\.t\) txt\.style\.color = ageColorReadable\(now - n\.t\)/);
});

test("ledger times hug the content (tree is fit-content) yet stay right-aligned", () => {
  assert.match(CSS, /\.ledger-tree \{[^}]*width: fit-content/);
});

test("the blue ✓ disc is standardized: ledger + feed card check carry the chat to-do's 9px/700 ✓", () => {
  const FEED_CSS = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "feed.css"), "utf8");
  assert.match(CSS, /\.ledger-tnode\.done \.ledger-tmark \{[^}]*font-size: 9px; font-weight: 700/);
  assert.match(FEED_CSS, /\.fcheck\.done \.fcheck-mark \{[^}]*font-size: 9px; font-weight: 700/);
});

test("the most-recently-changed ledger node gets a → marker on its left (kernel flags it `recent`)", () => {
  assert.match(RENDER, /n\.recent \? " recent" : ""/);                 // row carries the .recent class
  assert.match(RENDER, /el\("span", "ledger-recent"\)/);               // a → arrow element
  assert.match(RENDER, /arr\.textContent = "→"/);
  assert.match(RENDER, /recent\?: boolean/);                           // LedgerTreeNode carries the flag
  assert.match(CSS, /\.ledger-recent \{/);
});
