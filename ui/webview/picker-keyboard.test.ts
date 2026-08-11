// The new-session picker folds for a SHORT window (the user 2026-08-10, Chrome on a phone): with the
// on-screen keyboard up, the picker's lower rows sat behind it and nothing gave. The shell sizes the
// lifted chat iframe to the VISIBLE height (--app-h ← the top-level visualViewport, pinned in
// tests/test_kernel.py + test_shell_viewport_fit.py), so the keyboard opening/closing lands in the
// iframe as its own resize event — render.ts keys the kb-tight fold on exactly that, no timers, no UA
// sniffing. Folded: the advanced create rows (dir, backend, billing, host) hide; the essentials (name
// box, session list, actions) share the height with the keyboard. The same resize expands them back.
// Source-level pins (no jsdom for the renderer).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const W = path.resolve(process.cwd(), "..", "ui", "webview");
const RENDER = fs.readFileSync(path.join(W, "render.ts"), "utf8");
const CSS = fs.readFileSync(path.join(W, "styles.css"), "utf8");

test("the fold is keyed on this window's own resize event", () => {
  assert.match(RENDER, /const kbFit = \(\) => document\.getElementById\("picker"\)\?\.classList\.toggle\("kb-tight", window\.innerHeight < 480\)/);
  assert.match(RENDER, /window\.addEventListener\("resize", kbFit\)/);
  assert.match(RENDER, /kbFit\(\);/);   // synced at build too, not only on the first resize
});

test("kb-tight folds the advanced create rows and keeps the essentials", () => {
  // the advanced rows fold — !important because pick-mode / auth availability drive these rows'
  // visibility via inline styles, and the fold must win while it holds
  assert.match(CSS, /\.picker-overlay\.kb-tight \.picker-dir,\s*\n\.picker-overlay\.kb-tight \.picker-backend \{ display: none !important; \}/);
  // .picker-backend covers billing + host too (they wear the class); actions/list/search have no fold rule
  assert.doesNotMatch(CSS, /kb-tight \.picker-actions/);
  assert.doesNotMatch(CSS, /kb-tight \.picker-list \{ display/);
});

test("folded, the box hugs the short viewport instead of centering into the keyboard", () => {
  assert.match(CSS, /body\.picker-lifted > #picker\.kb-tight \{ align-items: flex-start; padding: 12px 16px; \}/);
  assert.match(CSS, /\.picker-overlay\.kb-tight \.picker-box \{ max-height: calc\(100vh - 24px\); \}/);
});
