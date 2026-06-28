// The feed's Clear-all / Undo-clear controls sit in a small bordered sub-pane in the BOTTOM-RIGHT of
// the feed, not a full-width footer bar, and the button label is two words "Undo clear" (the user
// 2026-06-16). The chat renderer has no jsdom harness, so — like the ledger tests — pin at the source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

test("the Undo-clear button label is two words", () => {
  assert.match(FEED, /b\.textContent = "Undo clear"/);
  assert.doesNotMatch(FEED, /"UndoClear"/);
});

test("#feed-foot FLOATS as a small bottom-right sub-pane (no reserved full-width row that clips cards)", () => {
  // the user 2026-06-27: in-flow it reserved a full-width row that shortened #feed-list and clipped the card
  // columns early. It now floats over the bottom-right corner so the columns use the full pane height.
  assert.match(CSS, /#feed-foot \{[^}]*position: absolute/);
  assert.match(CSS, /#feed-foot \{[^}]*right: 12px; bottom: 12px/);
  assert.match(CSS, /#feed-foot \{[^}]*width: fit-content/);     // still hugs the buttons (not a bar)
  assert.match(CSS, /#feed-foot \{[^}]*border: 1px solid var\(--card-border\)/);  // a boxed sub-pane…
  assert.match(CSS, /#feed-foot \{[^}]*border-radius/);          // …with rounded corners
  assert.doesNotMatch(CSS, /#feed-foot \{[^}]*align-self: flex-end/);   // no longer an in-flow flex item
});

test("the floating footer is anchored + cleared so it never reserves a band or covers a card", () => {
  assert.match(CSS, /body \{ display: flex; flex-direction: column; position: relative; \}/);   // positioning context
  assert.match(CSS, /#feed-list \{[^}]*min-height: 0;/);          // proper scroll container
  assert.match(CSS, /#feed-list \{[^}]*padding: 12px 12px 46px;/); // bottom clearance for the floating footer
});
