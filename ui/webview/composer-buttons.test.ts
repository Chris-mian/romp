// The composer is a Signal-style compose ROW (the user 2026-07-30): paperclip on the left, a pill input
// growing in the middle, a round send on the right. The two buttons are the SAME circle — the previous
// layout gave send double the paperclip's width on touch, which read as a bar, not the round send every
// messenger app puts there — and both are in-flow flex items, not corner overlays, so no offset
// arithmetic couples them to #composer's padding any more (that coupling once spanned two files; see
// tests/test_shell_mobile_composer_pad.py for the tombstone on the kernel end).
//
// Flex `order` does the placement so the markup both surfaces share (input before the buttons) needn't
// change: chips row 0 (full-width), attach 1, input 2, send 3.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");
const coarse = CSS.slice(CSS.indexOf("/* TOUCH (the user 2026-07-30"));

test("the composer is a flex row with the buttons seated at the bottom", () => {
  assert.match(CSS, /#composer \{[^}]*display: flex; flex-wrap: wrap; align-items: flex-end; gap: 8px;/);
  // the citation chip strip keeps a full-width row of its own above the compose row
  assert.match(CSS, /#composer-chips \{ flex: 1 1 100%;/);
});

test("flex order puts the paperclip LEFT of the input and send on its right", () => {
  assert.match(CSS, /#composer-attach \{ color: var\(--accent\); opacity: 0\.8; order: 1; \}/);
  assert.match(CSS, /#composer-input \{\s*\n\s*order: 2; flex: 1 1 auto; min-width: 0;/);
  assert.match(CSS, /#composer-send \{ order: 3; \}/);
});

test("the two buttons are the SAME circle — equal aspect ratio, by arithmetic", () => {
  const m = CSS.match(/#composer-attach, #composer-send \{\s*\n\s*flex: 0 0 auto; width: (\d+)px; height: (\d+)px; border-radius: 50%;/);
  assert.ok(m, "the shared sizing rule is missing");
  assert.equal(m![1], m![2], "width must equal height — a circle, not a bar");
});

test("the corner-overlay geometry is gone for good", () => {
  // no absolute offsets, no per-button widths: reintroducing either resurrects the padding coupling
  assert.doesNotMatch(CSS, /#composer-(send|attach) \{ right: \d+px/);
  assert.doesNotMatch(CSS, /#composer-(send|attach)[^{]*\{[^}]*position: absolute/);
  assert.doesNotMatch(CSS, /#composer-input \{ padding-right: \d+px; \}/);
});

test("a coarse pointer gets 44px circles: the tap target a finger expects, still 1:1", () => {
  assert.match(coarse, /#composer-attach, #composer-send \{ width: 44px; height: 44px; \}/);
  // and the resting box is ONE line — the pill — not the old two-line floor
  assert.match(coarse, /#composer-input \{ min-height: 40px; border-radius: 20px; padding: 10px 14px; \}/);
  assert.doesNotMatch(CSS, /min-height: calc\(2\.8em/);
});

test("on touch, send wears the accent as a FILL and the glyph flips to the on-accent colour", () => {
  assert.match(coarse, /background: var\(--accent\); color: var\(--accent-fg\); opacity: 1;/);
  // hover is included on purpose: a touch device can leave a sticky :hover that would otherwise
  // repaint the fill with the toolbar hover grey
  assert.match(coarse, /#composer-send, #composer-send:not\(:disabled\), #composer-send:hover:not\(:disabled\)/);
});

test("disabled is a muted fill, not a ghost", () => {
  // 0.3 opacity on a filled 44px circle reads as a rendering fault rather than a disabled control
  assert.match(coarse, /#composer-send:disabled \{ background: rgba\(255, 255, 255, 0\.10\); color: var\(--dim\); opacity: 1; \}/);
});

test("the input is a pill on desktop too", () => {
  assert.match(CSS, /border-radius: 18px; padding: 8px 14px;/);
});
