// The revive loader (the user 2026-07-05): reviving a dead session from the + picker takes seconds and
// used to give ZERO feedback after the confirm — and, separately, the revive itself had been silently
// broken since 2b5e181 (kernel-side; tests/test_kernel_revive.py). Per the repo's loading rule the
// Revive click puts up the romp loader — swirl + wordmark + pulsing dots, the SAME .rl-* treatment the
// boot/pane loaders use — with a "reviving <name>…" caption, cleared EVENT-based: the kernel's focus for
// that sid (success) or reviveFailed (the loader morphs into the failure reason — loud, dismissable).
// A 60s backstop can never trap the user. Source pin.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("the Revive click acknowledges at once: post reviveSession AND show the loader", () => {
  assert.match(RENDER,
    /if \(v === "revive"\) \{ vscodeApi\?\.postMessage\(\{ type: "reviveSession", id: m\.id \}\); showReviveLoader\(m\.id, nm\); \}/);
});

test("the loader is the romp treatment: wordmark + swirl + pulsing dots + caption", () => {
  assert.match(RENDER, /const word = el\("div", "rl-word"\)/, "reuses the boot-splash .rl-* styles already on the page");
  assert.match(RENDER, /swirl\.src = "\/media\/romp-swirl-o\.svg"/);
  assert.match(RENDER, /const dots = el\("div", "rl-dots"\)/);
  assert.match(RENDER, /cap\.textContent = `reviving “\$\{name\}”…`/);
});

test("event-based clear: the kernel's focus for the reviving sid retires the loader", () => {
  assert.match(RENDER, /if \(revivePending && m\.id === revivePending\) clearReviveLoader\(\);/);
});

test("failure is loud: reviveFailed morphs the loader into the reason, with Dismiss", () => {
  assert.match(RENDER, /m\.type === "reviveFailed" && m\.id/);
  assert.match(RENDER, /showReviveError\(String\(m\.name \|\| m\.id\), String\(m\.text \|\| "unknown error"\)\)/);
  assert.match(RENDER, /btn\.textContent = "Dismiss"/);
});

test("a 60s backstop keeps the loader from trapping the user", () => {
  assert.match(RENDER, /reviveBackstop = window\.setTimeout\(/);
  assert.match(RENDER, /, 60000\)/);
});

test("the overlay has styles: dimming backdrop, caption, and error box", () => {
  assert.match(CSS, /#revive-loader \{ position: fixed; inset: 0;/);
  assert.match(CSS, /#revive-loader \.revive-cap \{/);
  assert.match(CSS, /#revive-loader \.revive-err-text \{[^}]*errorForeground/);
});
