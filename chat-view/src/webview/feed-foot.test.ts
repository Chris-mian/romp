// The feed's Clear-all / Undo-clear controls sit in a small bordered sub-pane in the BOTTOM-RIGHT of
// the feed, not a full-width footer bar, and the button label is two words "Undo clear" (the user
// 2026-06-16). The chat renderer has no jsdom harness, so — like the ledger tests — pin at the source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "feed.css"), "utf8");

test("the Undo-clear button label is two words", () => {
  assert.match(FEED, /b\.textContent = "Undo clear"/);
  assert.doesNotMatch(FEED, /"UndoClear"/);
});

test("#feed-foot is a small bottom-right sub-pane, not a full-width bar", () => {
  assert.match(CSS, /#feed-foot \{[^}]*width: fit-content/);     // hugs the buttons
  assert.match(CSS, /#feed-foot \{[^}]*align-self: flex-end/);   // pinned to the right
  assert.match(CSS, /#feed-foot \{[^}]*border: 1px solid var\(--card-border\)/);  // a boxed sub-pane…
  assert.match(CSS, /#feed-foot \{[^}]*border-radius/);          // …with rounded corners
});
