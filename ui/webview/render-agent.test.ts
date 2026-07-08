// Subagent (Task/Agent) display: the PROMPT and the agent's REPORT each get their OWN caret fold, collapsed
// by default and markdown-rendered (the user 2026-07-08). Was a plain <pre> prompt + md report both hidden
// behind ONE "running…" head toggle — but while running that toggle's only content WAS the prompt, so it
// duplicated the box it revealed (and in a worse, monospace font). Now: no head toggle (the amber working
// dot already signals "still going"); each half is a `foldable(...)`. No jsdom harness for the chat
// renderer, so — like the other webview tests — pin it at the source level.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("the PROMPT gets its own collapsed, markdown-rendered caret fold (not a plain <pre> behind the head toggle)", () => {
  // the prompt shown is the actual prompt field (not the raw tool JSON)…
  assert.match(RENDER, /try \{ const o = JSON\.parse\(ev\.input\); if \(o && typeof o\.prompt === "string"\) promptText = o\.prompt; \}/);
  // …rendered as markdown into an agent-report box (the "nicer font" — no more preEl(promptText))…
  assert.match(RENDER, /const box = el\("div", "agent-report md"\); box\.innerHTML = md\(promptText\); highlight\(box\);/);
  // …wrapped in its OWN keyed, collapsed-by-default caret fold labeled "prompt".
  assert.match(RENDER, /turn\.appendChild\(foldable\("prompt", box, akey \? akey \+ ":prompt" : undefined\)\);/);
  // the prompt is NOT rendered as a monospace <pre> anymore, and the whole-dispatch head toggle is gone
  assert.doesNotMatch(RENDER, /body\.appendChild\(preEl\(promptText\)\)/, "the plain <pre> prompt is gone");
  assert.doesNotMatch(RENDER, /inlineFold\(head, turn, summary, body/, "the single head toggle for the dispatch is gone");
  assert.doesNotMatch(RENDER, /el\("div", "agent-fold"\)/, "the shared agent-fold body wrapper is gone");
});

test("the REPORT gets its own caret fold, line-count in the label, still the green-edged sub-transcript", () => {
  assert.match(RENDER, /turn\.appendChild\(foldable\(`report · \$\{countLines\(ev\.output\)\} lines`, box, akey \? akey \+ ":report" : undefined\)\);/);
  assert.match(CSS, /\.agent-report \{[^}]*border-left: 2px solid rgba\(87, 181, 15/);
  // the old per-section uppercase label + the 300px preview clamp are both gone
  assert.doesNotMatch(RENDER, /agent-fold-label/, "the per-section labels are gone (the caret fold labels them)");
  assert.doesNotMatch(CSS, /\.agent-fold-label \{/, "the .agent-fold-label rule is gone");
  assert.doesNotMatch(RENDER, /el\("div", "io-clamp agent-clamp"\)/, "the 300px report clamp block is removed");
});

test("a still-running agent (dispatched, no report yet) reads as RUNNING — amber working dot, not green ✓ (the user 2026-06-24)", () => {
  // mirrors the TUI's clearer running/done split: an Agent/Task with no output yet is still going, so it gets
  // a solid amber working dot instead of the green success dot.
  assert.match(RENDER, /const agentRunning = \(ev\.name === "Task" \|\| ev\.name === "Agent"\) && !ev\.output && !ev\.isError;/);
  assert.match(RENDER, /dot\(ev\.isError \? "ring" : agentRunning \? "working" : "green"\)/);
  assert.match(CSS, /\.dot\.working \{ background: var\(--st-working-bg\)/);
});
