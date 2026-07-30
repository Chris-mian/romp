// AskUserQuestion option rows must survive a narrow screen (the user 2026-07-30, on a phone). Every row
// was a flex line of [mark] [label] [description] with a RIGID label (flex: 0 0 auto): a label wider than
// the card pushed past its right edge, and the description, squeezed to its one-character min width
// BEYOND the label, wrapped a letter per line — the answered card rendered as a clipped option above a
// screen-tall stretch of blank box.
//
// Two treatments, because flex can't wrap text BESIDE a sibling (a flex line breaks before a too-wide
// item, orphaning the mark on a line of its own):
//  - the ANSWERED transcript row (.ask-opt: mark + label + desc) is INLINE with a hanging indent — the
//    mark hangs in the indent, the label wraps beside it like prose, the description takes its own line;
//  - the LIVE picker rows (.ask-live-opt / .ask-check: no mark glyph) stay flex but WRAP, with labels
//    allowed to shrink and break.
// Source-level pin (no jsdom for the chat renderer).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("the answered row is inline with a hanging indent — the mark can never be orphaned", () => {
  assert.match(CSS, /\.ask-opt \{ display: block; padding: 2px 0 2px 18px;/);
  assert.match(CSS, /\.ask-opt \.ask-mark \{ display: inline-block; width: 18px; margin-left: -18px;/);
  // the description and a free-text "Other" answer each take their own line under the label
  assert.match(CSS, /\.ask-opt \.ask-optdesc \{ display: block; \}/);
  assert.match(CSS, /\.ask-answer-text \{ display: block;/);
});

test("option labels may shrink and wrap instead of overflowing the card", () => {
  // overflow-wrap breaks a long unspaced label (a path, a flag) rather than letting it push out of the
  // card; the flex props serve the live rows, and are inert in the inline answered row
  assert.match(CSS, /\.ask-optlabel \{ flex: 0 1 auto; min-width: 0; overflow-wrap: anywhere; \}/);
  assert.match(CSS, /\.ask-live-opt \.ask-optlabel \{ flex: 0 1 auto; min-width: 0; overflow-wrap: anywhere; font-weight: 600; \}/);
  assert.match(CSS, /\.ask-check \.ask-optlabel \{ flex: 0 1 auto; min-width: 0; overflow-wrap: anywhere; font-weight: 600; \}/);
});

test("the live picker rows wrap, and a description claims a readable column or a full line — never a sliver", () => {
  assert.match(CSS, /\.ask-live-opt \{\s*\n\s*display: flex; flex-wrap: wrap;/);
  assert.match(CSS, /\.ask-check \{ display: flex; flex-wrap: wrap;/);
  // flex-basis 14em is the narrowest column worth reading beside the label; when even that doesn't fit,
  // flex-wrap drops the description to its own line at full card width
  assert.match(CSS, /\.ask-optdesc \{[^}]*flex: 1 1 14em; min-width: 0; \}/);
});
