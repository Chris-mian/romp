// Subagent (Task/Agent) display, disclosed progressively (the user 2026-07-17: default compact, click to
// go deeper): level 0 is ONE head row (Task + description + the run-state rail dot); the head's inline
// fold reveals the PROMPT and REPORT as their own collapsed caret boxes (the user 2026-07-08 — markdown-
// rendered, the prompt field not the tool JSON); opening either box is level 2. Unlike the pre-07-08
// head toggle, level 1 reveals fold LABELS, never the prompt itself, so nothing renders twice. No jsdom
// harness for the chat renderer, so — like the other webview tests — pin it at the source level.
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
  assert.match(RENDER, /halves\.appendChild\(foldable\("prompt", box, akey \? akey \+ ":prompt" : undefined\)\);/);
  // the prompt is NOT rendered as a monospace <pre> anymore
  assert.doesNotMatch(RENDER, /body\.appendChild\(preEl\(promptText\)\)/, "the plain <pre> prompt is gone");
  assert.doesNotMatch(RENDER, /el\("div", "agent-fold"\)/, "the shared agent-fold body wrapper is gone");
});

test("level 0 is ONE head row: both halves fold behind the head's inline toggle (the user 2026-07-17)", () => {
  // both caret boxes live in a shared wrapper that hangs off the HEAD fold — one row by default
  assert.match(RENDER, /const halves = el\("div", "agent-folds"\);/);
  assert.match(RENDER, /const label = ev\.output \? `prompt \+ report · \$\{countLines\(ev\.output\)\} line\$\{countLines\(ev\.output\) === 1 \? "" : "s"\}` : "prompt";/);
  assert.match(RENDER, /if \(halves\.childElementCount\) \{/);
  assert.match(RENDER, /inlineFold\(head, turn, label, halves, fkey\);/);
});

test("the REPORT gets its own caret fold, line-count in the label, still the green-edged sub-transcript", () => {
  assert.match(RENDER, /halves\.appendChild\(foldable\(`report · \$\{countLines\(ev\.output\)\} lines`, box, akey \? akey \+ ":report" : undefined\)\);/);
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
