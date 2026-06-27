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

test("a queued ChatEvent carries the pending messages (backend-agnostic, per-message md)", () => {
  assert.match(RENDER, /kind: "queued"; texts: \{ md: string; followUp\?: boolean; goal\?: string \}\[\]/);
});

test("renderQueued draws a wireframe-hourglass header (singular/plural) + one markdown bubble per queued message", () => {
  assert.match(RENDER, /ev\.kind === "queued"\) return renderQueued\(ev\)/);
  assert.match(RENDER, /el\("div", "turn turn-queued"\)/);
  // header: a stroked accent-blue hourglass ICON (no ⌛ emoji) + "N queued message(s)" — pluralizes on count
  assert.doesNotMatch(RENDER, /⌛/, "no hourglass emoji — it clashes with the app's line-icon style");
  assert.match(RENDER, /head\.appendChild\(hourglassIcon\(\)\)/);
  assert.match(RENDER, /function hourglassIcon\(\): HTMLElement/);
  assert.match(RENDER, /stroke="currentColor"[\s\S]*?<path d="M4 3 H12 L8 8 L12 13 H4 L8 8 Z"\/>/, "wireframe hourglass path");
  assert.match(RENDER, /label\.textContent = `\$\{n\} queued message\$\{n === 1 \? "" : "s"\}`/);
  assert.match(RENDER, /el\("div", "queued-head"\)/);
  // one faint "you" bubble per pending message, rendered as markdown (like a landed message)
  assert.match(RENDER, /for \(const t of ev\.texts\)[\s\S]*?el\("div", "queued-bubble md"\)/);
  assert.match(RENDER, /bubble\.innerHTML = md\(t\.md\)/);
});

test("the queued-header hourglass uses the accent blue, like the feed/mail toggle icons", () => {
  assert.match(CSS, /\.queued-head \.queued-icon \{ color: var\(--accent\)/);
});

test("the queued turn + bubbles are styled (so the dot is actually visible)", () => {
  assert.match(CSS, /\.turn-queued/);
  assert.match(CSS, /\.queued-head/);
  assert.match(CSS, /\.queued-bubble/);
});
