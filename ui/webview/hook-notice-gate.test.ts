// The hook-notice chip rendering must fire ONLY for a slash command's OUTPUT (ev.cmd), never for normal model
// prose. Without the gate, parseHookNotices matched ANY assistant message containing "X [y] completed
// successfully" — including the agent's own prose discussing the feature — and renderHookNotices then replaced
// the whole message with a lone chip, destroying its content (the user 2026-06-30, within 18 min of shipping).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");

test("parseHookNotices is called ONLY under an ev.cmd guard (slash-command output), never on bare prose", () => {
  assert.match(RENDER, /if \(ev\.cmd\)\s*\{\s*const hn = parseHookNotices\(ev\.md\)/);
  // and the ChatEvent assistant variant carries the cmd flag the kernel sets from the command-output atom
  assert.match(RENDER, /kind: "assistant";[^}]*cmd\?: boolean/);
});
