// Subagent (Task/Agent) display (the user 2026-06-14): not a big IN text box. The prompt folds onto
// the head line; the agent's report renders as a faded, green-edged sub-transcript (clamped). No jsdom
// harness for the chat renderer, so — like the other webview tests — pin it at the source level.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "styles.css"), "utf8");

test("a Task/Agent call folds its prompt and renders the report as an agent-report block", () => {
  // the prompt is folded onto the head, not shown as a big IN box (no more ioClamp for the signal path)
  assert.match(RENDER, /inlineFold\(head, turn, "prompt", preEl\(ev\.input\)\)/);
  assert.match(RENDER, /el\("div", "agent-report md"\)/);
  assert.match(RENDER, /el\("div", "io-clamp agent-clamp"\)/);
  // styled green + faded
  assert.match(CSS, /\.io-clamp\.agent-clamp \{[^}]*border-left: 2px solid rgba\(87, 181, 15/);
  assert.match(CSS, /\.agent-report \{/);
});
