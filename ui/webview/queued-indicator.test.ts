// The "queued" indicator (the user's messages submitted while a session is still working). It's the SAME
// generic {kind:"queued"} ChatEvent for BOTH backends — the kernel feeds it from the transcript queue-ops
// for tmux and from SdkBackend.pending_queued for SDK (business 2026-06-23). So pinning the one render path
// confirms the dot shows for either backend. The renderer has no jsdom harness, so pin the wiring at source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("a queued ChatEvent carries the pending texts (backend-agnostic)", () => {
  assert.match(RENDER, /kind: "queued"; texts: string\[\]/);
});

test("renderQueued draws the ⌛ header (singular/plural) + one bubble per queued text", () => {
  assert.match(RENDER, /ev\.kind === "queued"\) return renderQueued\(ev\)/);
  assert.match(RENDER, /el\("div", "turn turn-queued"\)/);
  // header: "⌛ N queued message(s)" — pluralizes on count
  assert.match(RENDER, /`⌛ \$\{n\} queued message\$\{n === 1 \? "" : "s"\}`/);
  assert.match(RENDER, /el\("div", "queued-head"\)/);
  // one faint "you" bubble per pending text
  assert.match(RENDER, /for \(const t of ev\.texts\)[\s\S]*?el\("div", "queued-bubble"\)/);
});

test("the queued turn + bubbles are styled (so the dot is actually visible)", () => {
  assert.match(CSS, /\.turn-queued/);
  assert.match(CSS, /\.queued-head/);
  assert.match(CSS, /\.queued-bubble/);
});
