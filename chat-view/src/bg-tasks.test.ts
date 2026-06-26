// Background-task box (the user 2026-06-26): the chat shows run_in_background tasks the kernel surfaced in a
// dedicated #bg-tasks box between the transcript and the composer — each a status dot + one-line summary,
// click the header to expand the command + output. Toggle is delegated to the stable container so a rebuild
// never drops it; expansion is keyed by task id. Source pins (no jsdom for the chat render).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("a BgTask type rides on the session and is carried across pushes", () => {
  assert.match(SRC, /interface BgTask \{ id: string; status: string; summary: string;/);
  assert.match(SRC, /bgTasks\?: BgTask\[\];/);
  assert.match(SRC, /bgTasks: \("bgTasks" in msg\) \? msg\.bgTasks : \(prev \? prev\.bgTasks : undefined\)/);
});

test("renderBgTasks renders the active session's tasks, hides the box when there are none", () => {
  assert.match(SRC, /function renderBgTasks\(\)/);
  assert.match(SRC, /if \(!tasks\.length\) \{ host\.style\.display = "none"; return; \}/);
  // the header carries the toggle action + id; expansion is keyed by id and survives the re-render
  assert.match(SRC, /head\.dataset\.act = "bg-toggle"; head\.dataset\.id = t\.id;/);
  assert.match(SRC, /const bgExpanded = new Set<string>\(\);/);
  // expand body = the command + the output, textContent only (untrusted)
  assert.match(SRC, /cmd\.textContent = t\.command;/);
  assert.match(SRC, /out\.textContent = t\.output \|\| "\(no output captured\)";/);
});

test("renderBgTasks is wired into showActive and the toggle is delegated to the stable container", () => {
  assert.match(SRC, /renderBgTasks\(\); \/\/ swap in the active session's background-task box/);
  assert.match(SRC, /delegate\(host, \{\s*"bg-toggle": \(el\) => \{/);
});

test("status tints keep their meaning (running yellow, failed red, completed blue — not the accent)", () => {
  assert.match(CSS, /\.bg-task \{ --bgt: var\(--st-working-bg\)/);
  assert.match(CSS, /\.bg-task\.bg-failed \{ --bgt: var\(--st-blocked-bg\); \}/);
  assert.match(CSS, /\.bg-task\.bg-completed \{ --bgt: var\(--st-ready-bg\); \}/);
});
