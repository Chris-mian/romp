// A still-RUNNING tool (Bash/Grep/… dispatched, no result yet) keeps its command COLLAPSED behind the head
// fold from the very first render (the user 2026-07-21) — it used to render the IN row expanded and only
// snap shut once the result landed, so a running command flashed its full text then collapsed a beat later.
// Source-level pins (no jsdom for the chat renderer).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");

test("a running (no-output) tool folds its command behind the head instead of showing it expanded", () => {
  // the no-output branch builds a foldable IN box and inlineFolds it — NOT an inline turn.appendChild(io)
  assert.match(RENDER, /} else if \(!ev\.output\) \{[\s\S]*?const io = el\("div", "tool-io tool-io-fold"\);[\s\S]*?inlineFold\(head, turn, ev\.resultUuid \? "no output" : "running…", io, fkey\)/);
  // the old always-expanded inline render is gone
  assert.doesNotMatch(RENDER, /} else if \(!ev\.output\) \{\s*\n\s*const io = el\("div", "tool-io"\); if \(ev\.input\)/);
});

test("the fold reuses the tool's fkey, so a completed tool inherits any expand and the state persists", () => {
  // same fkey ("tool:"+uuid) as the completed and error branches → open-state survives running→done re-render
  assert.match(RENDER, /const fkey = ev\.uuid \? "tool:" \+ ev\.uuid : undefined;/);
  assert.match(RENDER, /inlineFold\(head, turn, ev\.resultUuid \? "no output" : "running…", io, fkey\)/);
});

test("resultUuid distinguishes a still-running command from one that finished with no output", () => {
  // absent resultUuid = running ("running…"); present = done-but-empty ("no output") — never a stuck label
  assert.match(RENDER, /ev\.resultUuid \? "no output" : "running…"/);
});
