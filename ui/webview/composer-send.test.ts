// An explicit send button on the right of the composer (the user 2026-06-17), in addition to ⏎ — both go
// through one sendComposer() path. Touch devices have no easy Enter; desktop gets a click affordance too.
// Source-level pin (no jsdom for the chat renderer).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");
const SKELETON = fs.readFileSync(path.resolve(process.cwd(), "src", "page-skeleton.ts"), "utf8");

test("the composer markup includes a send button to the right of 📎", () => {
  assert.match(SKELETON, /<button id="composer-send"[^>]*aria-label="Send">/);
  // 📎 then send, so send is rightmost
  assert.match(SKELETON, /id="composer-attach"[\s\S]*id="composer-send"/);
});

test("⏎ and the send button share ONE sendComposer() path", () => {
  assert.match(RENDER, /const sendComposer = \(\) => \{/);
  assert.match(RENDER, /vscodeApi\.postMessage\(\{ type: "sendMessage", id: activeId, text \}\)/);
  // Enter calls it (desktop only — the mobile guard is asserted separately below)
  assert.match(RENDER, /if \(e\.key === "Enter" && !e\.shiftKey && !isCoarsePointer\(\)\) \{\s*e\.preventDefault\(\);\s*sendComposer\(\);/);
  // the button calls it (mousedown keeps textarea focus on desktop; on a phone it blurs so the keyboard
  // collapses and the box drops back to the bottom — see composer-send-blur.test.ts)
  assert.match(RENDER, /sendBtn\?\.addEventListener\("mousedown", \(e\) => \{ e\.preventDefault\(\); sendComposer\(\); if \(isCoarsePointer\(\)\) ta\.blur\(\); else ta\.focus\(\); \}\)/);
});

test("on a phone (coarse pointer) Enter is a newline, not send — the Send button is the only send (the user 2026-07-15)", () => {
  // mobile keyboards often can't do Shift+Enter, and the software return key should just return. The Enter-to-send
  // path is gated on !isCoarsePointer(), so on touch Enter falls through to the textarea's native newline; sending
  // is the explicit Send button (its mousedown handler is unguarded, so it still sends on touch).
  assert.match(RENDER, /function isCoarsePointer\(\)/);
  assert.match(RENDER, /matchMedia\("\(pointer:coarse\)"\)\.matches/);
  assert.match(RENDER, /e\.key === "Enter" && !e\.shiftKey && !isCoarsePointer\(\)/);
  // the resting placeholder drops the ⏎/⇧⏎ hint on mobile (it's wrong there and clipped the one-line box)
  assert.match(RENDER, /function composerRestingPlaceholder\(\)/);
  assert.match(RENDER, /isCoarsePointer\(\)\s*\?\s*"Message this session…  \(type \/ for commands\)"/);
});

test("the empty composer floors at two lines on a phone so the wrapped resting placeholder isn't clipped (the user 2026-07-15)", () => {
  assert.match(CSS, /@media \(pointer: coarse\) \{\s*#composer-input \{ min-height: calc\(2\.8em \+ 18px\); \}/);
});

test("⏎ jumps focus to the tab bar after sending so ←/→ switch sessions (the user 2026-06-25)", () => {
  // after the Enter-send, focusActiveTab() moves focus off the composer onto the active tab, so the next
  // ←/→ hits onTabKey (tab switch) instead of the textarea caret. The send BUTTON keeps composer focus.
  assert.match(RENDER, /sendComposer\(\);\s*focusActiveTab\(\);/);
  assert.match(RENDER, /function focusActiveTab\(\)/);
});

test("Escape ↔ Enter toggle focus between the chat box and the tab bar (the user 2026-06-25)", () => {
  // Escape in the composer → tab mode (focus the active tab, ←/→ switch sessions); a draft is untouched.
  assert.match(RENDER, /if \(e\.key === "Escape"\) \{[\s\S]*?focusActiveTab\(\);[\s\S]*?return;/);
  // Enter on a focused tab (onTabKey) → drop back into the chat box of the selected session
  assert.match(RENDER, /else if \(e\.key === "Enter"\) \{[\s\S]*?getElementById\("composer-input"\)[\s\S]*?\?\.focus\(\);/);
});

test("the send button is disabled on a closed (read-only) session", () => {
  assert.match(RENDER, /if \(sendBtn\) sendBtn\.disabled = closed/);
});

test("the send button is styled to the right of 📎 and the textarea reserves room for both", () => {
  // resized 2026-07-29 (send is the primary action, so it is the wider of the two); the touch layout and
  // the arithmetic that keeps the pair inside the box live in composer-buttons.test.ts
  assert.match(CSS, /#composer-send \{ right: 28px; width: 46px/);
  assert.match(CSS, /#composer-attach \{ right: 82px; width: 34px/);
  assert.match(CSS, /#composer-input \{[\s\S]*padding: 8px 64px 8px 10px/);
  assert.match(CSS, /#composer-input \{ padding-right: 92px; \}/, "…widened for the bigger pair");
});

test("the composer sits tight to the bottom — no wasted gap below it (the user 2026-06-23)", () => {
  // the bottom padding was trimmed 12px → 6px so the box hugs the pane's bottom; the 📎/send buttons drop
  // 18px → 12px in step so they stay vertically centred on the one-line textarea.
  assert.match(CSS, /#composer \{[^}]*padding: 8px 24px 6px;/);
  assert.match(CSS, /#composer-attach, #composer-send \{[\s\S]*bottom: 12px;/);
});

test("focusing a tab (after ⏎-send) draws NO white UA focus ring around its colored border (the user 2026-06-25)", () => {
  // ⏎-send / Escape move focus onto the active tab; the base .tab rule sets outline:none so the browser's
  // default focus outline doesn't draw a redundant white ring around the identity-colored border.
  assert.match(CSS, /\.tab \{[^}]*outline: none;[^}]*\}/);
  // the dashed STATE outlines stay (higher specificity than the base .tab rule, so outline:none can't kill them)
  assert.match(CSS, /\.tab\.tab-awaiting, \.tab\.tab-blocked, \.tab\.tab-retrying \{ outline: 2px dashed/);
});
