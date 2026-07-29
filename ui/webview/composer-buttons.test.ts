// Send and Attach are sized to be hit (the user 2026-07-29, on an iPad). They were 26px squares tucked
// in the corner of the message box: passable with a mouse, a poor target for a thumb, and on a touch
// layout — where the resting box is already two lines tall — they read as a stray row under the
// placeholder rather than as the pane's controls.
//
// Send is the primary action of the whole chat, so it gets real width instead of matching the paperclip
// beside it, and on a coarse pointer both become a 44px row along the bottom of the box with the text
// running full width above them.
//
// The offsets are measured from #composer, so they depend on ITS padding — which the kernel's mobile
// shell narrows from 24px to 10px. That coupling is what the paired media queries below are about, and
// tests/test_shell_mobile_composer_pad.py pins the kernel end of it.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");
const coarse = CSS.slice(CSS.indexOf("/* TOUCH (the user 2026-07-29"));

test("the old 26px squares are gone", () => {
  assert.doesNotMatch(CSS, /#composer-attach, #composer-send \{[^}]*width: 26px; height: 26px/);
  assert.match(CSS, /#composer-attach, #composer-send \{ bottom: 10px; height: 30px; \}/);
});

test("send is the widest control in the corner, not a twin of the paperclip", () => {
  assert.match(CSS, /#composer-send \{ right: 28px; width: 46px; font-size: 16px; \}/);
  assert.match(CSS, /#composer-attach \{ right: 82px; width: 34px; font-size: 16px; \}/);
  // 28 + 46 = 74, so the paperclip at 82 clears it with room; the text stops clear of both
  assert.match(CSS, /#composer-input \{ padding-right: 92px; \}/);
});

test("a coarse pointer gets a 44px row: the tap target a finger expects", () => {
  assert.match(coarse, /#composer-attach, #composer-send \{ bottom: 12px; height: 44px; border-radius: 8px; \}/);
  assert.match(coarse, /#composer-send \{ right: 28px; width: 96px; font-size: 21px; \}/);
  assert.match(coarse, /#composer-attach \{ right: 136px; width: 60px; font-size: 19px; \}/);
  // 28 + 96 = 124, so 136 clears the send button by 12px
});

test("on touch, send wears the accent as a FILL and the glyph flips to the on-accent colour", () => {
  assert.match(coarse, /background: var\(--accent\); color: var\(--accent-fg\); opacity: 1;/);
  // hover is included on purpose: a touch device can leave a sticky :hover that would otherwise
  // repaint the fill with the toolbar hover grey
  assert.match(coarse, /#composer-send, #composer-send:not\(:disabled\), #composer-send:hover:not\(:disabled\)/);
});

test("disabled is a muted fill, not a ghost", () => {
  // 0.3 opacity on a 96px button reads as a rendering fault rather than a disabled control
  assert.match(coarse, /#composer-send:disabled \{ background: rgba\(255, 255, 255, 0\.10\); color: var\(--dim\); opacity: 1; \}/);
});

test("on touch the text runs full width, with the button row's height reserved under it", () => {
  assert.match(coarse, /#composer-input \{ padding-right: 12px; padding-bottom: 62px; min-height: calc\(2\.8em \+ 62px\); \}/);
});

test("the narrow offsets are matched to the query that narrows #composer's padding", () => {
  // A landscape iPad is coarse but WIDER than 1024, so it keeps desktop padding. Phone offsets applied
  // there would hang both buttons outside the box — hence the second, narrower query rather than
  // folding these into the coarse block above.
  assert.match(CSS, /@media \(pointer: coarse\) and \(max-width: 1024px\) \{\s*\n\s*#composer-send \{ right: 14px; \}\s*\n\s*#composer-attach \{ right: 122px; \}/);
  // 14 + 96 = 110, so 122 clears send by 12px at the narrow padding too
});
