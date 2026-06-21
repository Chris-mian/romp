// Postal cards ALWAYS lead with a one-line summary and expand to the full message on click (the user
// 2026-06-16). Before, incoming mail showed the Haiku caption (full body only as a hover tooltip) while
// outgoing mail showed the whole body — inconsistent. Now both render a summary (the caption, or the
// first line for sent mail with no caption) that opens inline on click. The chat renderer has no jsdom
// harness, so — like render-postal-time.test.ts — pin it at the source level.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("a postal summary is the caption, or the first non-empty line of the body when there's none", () => {
  assert.match(RENDER, /function postalSummary/);
  assert.match(RENDER, /const cap = ev\.summary && ev\.summary\.trim\(\)/);
  assert.match(RENDER, /\.split\("\\n"\)\.map\(\(s\) => s\.trim\(\)\)\.find\(Boolean\)/);
});

test("both directions render the summary + a click-to-expand full body (no hover tooltip)", () => {
  // expandable when the full body differs from the summary — same path for incoming and outgoing
  assert.match(RENDER, /const expandable = .*collapseWs\(fullText\) !== collapseWs\(summaryText\)/);
  assert.match(RENDER, /body\.classList\.add\("postal-expandable"\)/);
  // a click toggles the full message inline; the old hover-tooltip caption is gone
  assert.match(RENDER, /body\.classList\.toggle\("expanded"\)/);
  assert.doesNotMatch(RENDER, /body\.title = ev\.body/, "the old hover-tooltip full body must be gone");
  assert.doesNotMatch(RENDER, /caption \|\| ev\.body/, "no longer 'caption else whole body'");
});

test("the postal expand box is styled (full body hidden until expanded; summary is clickable)", () => {
  assert.match(CSS, /\.postal-full \{[^}]*display: none/);
  assert.match(CSS, /\.postal-expandable\.expanded \.postal-full \{[^}]*display: block/);
  assert.match(CSS, /\.postal-expandable \.postal-summary \{[^}]*cursor: pointer/);
});
