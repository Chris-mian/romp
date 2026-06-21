// Compact mode + settings gear wiring (the user 2026-06-14). The pure logic is covered by
// compact.test.ts / settings.test.ts; the chat renderer has no jsdom harness, so — like the other
// webview tests — these pin the DOM wiring at the source level: the compact branch in syncView, the
// tool-group summary line, and the gear → settings modal.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("syncView takes the compact rebuild path when the setting is on", () => {
  assert.match(RENDER, /if \(settings\.compact\) \{ rebuildCompact\(/);
  // the rail timestamp chain runs over the compacted display list (prevEpoch threaded through it)
  assert.match(RENDER, /compactDisplay\(s\.events\.map\(/);
});

test("a collapsed tool run renders bold tool labels via toolCounts and is click-to-expand", () => {
  assert.match(RENDER, /el\("div", "toolgroup-line"\)/);
  assert.match(RENDER, /toolCounts\(tools\.map\(/);
  assert.match(RENDER, /el\("span", "toolgroup-tool"\)/, "each tool word is its own bold span");
  // the "N Edits" summary shows only when collapsed; expanded → just the arrow
  assert.match(RENDER, /if \(!open\) \{/);
  // clicking the line toggles expand → the full non-compact cards for that span, indented
  assert.match(RENDER, /line\.addEventListener\("click",[\s\S]*?toggleToolGroup\(key\)/);
  assert.match(RENDER, /function toggleToolGroup/);
  assert.match(RENDER, /expandedGroups\.has\(key\)/);
  assert.match(RENDER, /classList\.add\("tg-child"\)/, "expanded children are tagged for indent");
  assert.match(CSS, /\.toolgroup-tool \{[^}]*font-weight: 700/);
  assert.match(CSS, /\.tg-child \{[^}]*margin-left/);
});

test("the chat has NO gear of its own — it only consumes the shared setting (gear is on the timeline)", () => {
  assert.doesNotMatch(RENDER, /chat-settings-gear/, "the gear was moved to the timeline");
  assert.match(RENDER, /onExternalSettingsChange\(\(s\) => \{ settings = s; rerenderAll\(\); \}\)/);
});
