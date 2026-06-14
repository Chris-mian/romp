// Feed focus policy (the user 2026-06-13): the feed is mouse-driven and must NOT
// hold keyboard focus — clicking a card stole it from the chat iframe, killing the
// chat's keyboard nav. After a feed click, focus returns to the chat-frame UNLESS
// the feed genuinely wants keys (an open modal/help overlay, or a text field). The
// behaviour is iframe focus plumbing with no jsdom harness here, so these pin it at
// the source level, the way the timeline-view / hover-wiring tests do.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "feed.ts"), "utf8");

test("a feed click returns focus to the chat-frame, deferred past the click handler", () => {
  assert.match(FEED, /window\.addEventListener\("click",[\s\S]*?setTimeout\(\(\) => \{ if \(!feedWantsKeys\(t\)\) returnFocusToChat\(\); \}, 0\)/);
  assert.match(FEED, /getElementById\("chat-frame"\)[\s\S]*?contentWindow\?\.focus\(\)/, "focuses the chat iframe window");
});

test("focus is NOT stolen back while a modal/help overlay is open or a text field is focused", () => {
  // open overlay → feed keeps focus (Esc closes it, its fields type)
  assert.match(FEED, /if \(document\.getElementById\("feed-modal"\) \|\| document\.getElementById\("feed-help"\)\) return true;/);
  // text inputs keep focus
  assert.match(FEED, /INPUT\|TEXTAREA\|SELECT/);
  assert.match(FEED, /isContentEditable/);
});

test("returnFocusToChat is a safe no-op when not embedded beside a chat-frame", () => {
  // standalone /feed or VS Code: no sibling frame, or cross-origin → swallow, never throw
  assert.match(FEED, /if \(!window\.parent \|\| window\.parent === window\) return;/);
  assert.match(FEED, /catch \{ \/\* cross-origin \/ not embedded/);
});
