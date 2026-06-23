// The chat tab's hover tooltip names which BACKEND the session runs on — tmux | SDK (the user 2026-06-23),
// from the kernel's per-session `backend` field (_session_backend). Source-pin over render.ts.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");

test("the session Status type carries the backend the kernel publishes", () => {
  assert.match(RENDER, /interface Status \{[^}]*backend\?: string;/);
});

test("a tab's title tooltip names its backend (SDK | tmux), plus the model", () => {
  assert.match(RENDER, /const beLabel = s\.status\.backend === "sdk" \? "SDK" : s\.status\.backend === "tmux" \? "tmux" : "";/);
  assert.match(RENDER, /if \(beLabel\) tab\.title = s\.name \+ " · " \+ beLabel \+ " backend"/);
  // it rides the model so the hover is a useful one-line session summary, not just the backend
  assert.match(RENDER, /\(s\.status\.model \? " · " \+ s\.status\.model : ""\)/);
});
