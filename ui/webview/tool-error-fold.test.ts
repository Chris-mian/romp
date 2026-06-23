// A FAILED tool (failed Bash / failed Edit / …) collapses to ONE line like the successful ones, kept RED
// and expandable for the error (the user 2026-06-22). Was an always-shown ~300px io-clamp block; now it
// folds onto the head behind a red "error" toggle. Source-level pins (no jsdom for the chat renderer).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("a failed tool folds onto the head (one line) instead of an always-shown io-clamp block", () => {
  // the error branch builds a foldable IN/OUT box and inlineFolds it under a red "error" toggle
  assert.match(RENDER, /if \(ev\.isError\) \{[\s\S]*?const io = el\("div", "tool-io tool-io-fold"\);/);
  assert.match(RENDER, /inlineFold\(head, turn, n \? `error · \$\{n\} line\$\{n === 1 \? "" : "s"\}` : "error", io, fkey\)/);
  // the old "always show" io-clamp path is gone
  assert.doesNotMatch(RENDER, /ioClamp\(ev\.input, ev\.output, true, fkey\)/, "errors no longer use the always-shown io-clamp");
  assert.doesNotMatch(RENDER, /errors: always show/);
});

test("a collapsed error's toggle is RED so it stays loud at a glance", () => {
  assert.match(CSS, /\.turn-tool\.tool-err \.tool-fold-toggle \{[^}]*color: var\(--err\)/);
  // the tool name is already red on error (kept), and the rail dot is the red ✗ disc
  assert.match(CSS, /\.tool-err \.tool-name \{[^}]*color: var\(--err\)/);
});

test("the dead io-clamp helper + CSS are removed (errors fold like every tool now)", () => {
  assert.doesNotMatch(RENDER, /function ioClamp\(/);
  assert.doesNotMatch(CSS, /\.io-clamp \{/, "the io-clamp block style is gone with its only caller");
});
