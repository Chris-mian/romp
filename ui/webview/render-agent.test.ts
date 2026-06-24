// Subagent (Task/Agent) display: the WHOLE dispatch collapses to ONE line like Bash/Read (the user
// 2026-06-22) — the prompt AND the agent's report both tuck below the head behind a single toggle, hidden
// until clicked. The report still renders as a faded, green-edged sub-transcript when expanded (the user
// 2026-06-14: not a big text box — and now not a big block). No jsdom harness for the chat renderer, so —
// like the other webview tests — pin it at the source level.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("a Task/Agent dispatch collapses to ONE line: prompt + report behind a single head toggle", () => {
  // ONE inlineFold for the whole dispatch (not a separate prompt fold + a 300px report clamp). Default
  // collapsed; click the head toggle to reveal both halves.
  assert.match(RENDER, /const body = el\("div", "agent-fold"\);/);
  assert.match(RENDER, /inlineFold\(head, turn, summary, body, fkey \? fkey \+ ":agent" : undefined\)/);
  // head summary = the report's line count once it's back, else "running…" (in-flight) — clearer than "prompt"
  assert.match(RENDER, /const summary = ev\.output \? `report · \$\{countLines\(ev\.output\)\} lines` : "running…";/);
  // the prompt shown is the actual prompt field (not the raw tool JSON), each half gets a small label
  assert.match(RENDER, /try \{ const o = JSON\.parse\(ev\.input\); if \(o && typeof o\.prompt === "string"\) promptText = o\.prompt; \}/);
  assert.match(RENDER, /el\("div", "agent-fold-label"\)/);
  // the report still renders as the green-edged agent-report sub-transcript
  assert.match(RENDER, /el\("div", "agent-report md"\)/);
  // the big 300px preview block is GONE — no more io-clamp agent-clamp on the signal path
  assert.doesNotMatch(RENDER, /el\("div", "io-clamp agent-clamp"\)/, "the 300px report clamp block is removed");
});

test("a still-running agent (dispatched, no report yet) reads as RUNNING — amber working dot, not green ✓ (the user 2026-06-24)", () => {
  // mirrors the TUI's clearer running/done split: an Agent/Task with no output yet is still going, so it gets
  // a solid amber working dot instead of the green success dot, and its summary says "running…".
  assert.match(RENDER, /const agentRunning = \(ev\.name === "Task" \|\| ev\.name === "Agent"\) && !ev\.output && !ev\.isError;/);
  assert.match(RENDER, /dot\(ev\.isError \? "ring" : agentRunning \? "working" : "green"\)/);
  assert.match(CSS, /\.dot\.working \{ background: var\(--st-working-bg\)/);
});

test("the agent report keeps its faded green-edged styling, now inside the fold", () => {
  assert.match(CSS, /\.agent-report \{[^}]*border-left: 2px solid rgba\(87, 181, 15/);
  assert.match(CSS, /\.agent-fold-label \{/);
  assert.doesNotMatch(CSS, /\.io-clamp\.agent-clamp \{/, "the agent-clamp rule is gone");
});
