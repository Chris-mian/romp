// Background-task box layout (the user 2026-07-07): the box sits between the transcript and the composer.
// A shrink-1 flex box got SQUEEZED by the flex column on a constrained chat pane, so expanding it clipped
// the rows behind the composer — a click "slightly expanded" into something you couldn't see. It now HOLDS
// its content (flex 0 0 auto), capped so it never crowds the composer, with the inner list scrolling; and the
// collapsed header has a distinct card background so it reads as a box, not a faint borderless line.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("#bg-tasks HOLDS its content (flex 0 0 auto), capped so it never crowds the composer", () => {
  assert.match(CSS, /#bg-tasks \{ flex: 0 0 auto;[^}]*max-height: min\(50vh, 340px\);[^}]*overflow: hidden;/);
  assert.doesNotMatch(CSS, /#bg-tasks \{ flex: 0 1 auto;/, "no longer shrink-1 (that clipped the expanded rows)");
});

test("the inner list SCROLLS when a run has many tasks (so the box stays capped, never clipped-behind-composer)", () => {
  assert.match(CSS, /\.bg-list \{[^}]*flex: 1 1 auto;[^}]*overflow-y: auto;/);
});

test("the collapsed header has a DISTINCT card background, not the page bg (no more faint mystery line)", () => {
  // [^}]* keeps the match INSIDE the .bg-fold-head rule (don't span into #footer's page-bg fill)
  assert.match(CSS, /\.bg-fold-head \{[^}]*background: var\(--box-bg\);/);
  assert.doesNotMatch(CSS, /\.bg-fold-head \{[^}]*background: var\(--vscode-editor-background/);
});
