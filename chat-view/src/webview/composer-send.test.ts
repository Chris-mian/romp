// An explicit send button on the right of the composer (the user 2026-06-17), in addition to ⏎ — both go
// through one sendComposer() path. Touch devices have no easy Enter; desktop gets a click affordance too.
// Source-level pin (no jsdom for the chat renderer).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "styles.css"), "utf8");
const SKELETON = fs.readFileSync(path.resolve(process.cwd(), "src", "page-skeleton.ts"), "utf8");

test("the composer markup includes a send button to the right of 📎", () => {
  assert.match(SKELETON, /<button id="composer-send"[^>]*aria-label="Send">/);
  // 📎 then send, so send is rightmost
  assert.match(SKELETON, /id="composer-attach"[\s\S]*id="composer-send"/);
});

test("⏎ and the send button share ONE sendComposer() path", () => {
  assert.match(RENDER, /const sendComposer = \(\) => \{/);
  assert.match(RENDER, /vscodeApi\.postMessage\(\{ type: "sendMessage", id: activeId, text \}\)/);
  // Enter calls it
  assert.match(RENDER, /if \(e\.key === "Enter" && !e\.shiftKey\) \{\s*e\.preventDefault\(\);\s*sendComposer\(\);/);
  // the button calls it (mousedown keeps textarea focus)
  assert.match(RENDER, /sendBtn\?\.addEventListener\("mousedown", \(e\) => \{ e\.preventDefault\(\); sendComposer\(\); ta\.focus\(\); \}\)/);
});

test("the send button is disabled on a closed (read-only) session", () => {
  assert.match(RENDER, /if \(sendBtn\) sendBtn\.disabled = closed/);
});

test("the send button is styled to the right of 📎 and the textarea reserves room for both", () => {
  assert.match(CSS, /#composer-send\s+\{ right: 30px/);
  assert.match(CSS, /#composer-attach \{ right: 58px/);
  assert.match(CSS, /#composer-input \{[\s\S]*padding: 8px 64px 8px 10px/);
});
