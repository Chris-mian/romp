// The new-session picker folds for a SHORT window (the user 2026-08-10, Chrome on a phone): with the
// on-screen keyboard up, the picker's lower rows sat behind it and nothing gave. The shell sizes the
// lifted chat iframe to the VISIBLE height (--app-h ← the top-level visualViewport, pinned in
// tests/test_kernel.py + test_shell_viewport_fit.py), so the keyboard opening/closing lands in the
// iframe as its own resize event — render.ts keys the kb-tight fold on exactly that, no timers, no UA
// sniffing. Folded: the advanced create rows (dir, backend, billing, host) hide, and the essentials
// rearrange for the keyboard (the user 2026-08-12, after the resume list moved to the dialog's
// bottom): the list flexes to fill the middle directly under the name box, and the actions row pins
// to the box's bottom edge, right above the keyboard. The same resize expands it all back.
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
  // the essentials never fold: no display rule hides actions, list, or search while kb-tight holds
  assert.doesNotMatch(CSS, /kb-tight \.picker-actions \{[^}]*display/);
  assert.doesNotMatch(CSS, /kb-tight \.picker-list \{[^}]*display/);
});

test("folded, the box hugs the short viewport instead of centering into the keyboard", () => {
  // both contexts tighten to the same 12px frame — the fixed-height box below assumes exactly it,
  // and the standalone overlay's 56px anchor would otherwise push the pinned actions row off-screen
  assert.match(CSS, /#picker\.kb-tight,\s*\nbody\.picker-lifted > #picker\.kb-tight \{ align-items: flex-start; padding: 12px 16px; \}/);
  // a FIXED height, not just a cap: the pinned actions row below the list must not shift as typing
  // re-filters the list's height. dvh, not vh — standalone on a phone, vh is the LARGEST viewport
  // while the fold keys on the current innerHeight, and the mismatch clipped the pinned actions row
  assert.match(CSS, /\.picker-overlay\.kb-tight \.picker-box \{ height: calc\(100dvh - 24px\); max-height: calc\(100dvh - 24px\); \}/);
});

test("folded, the list fills the middle and the actions row pins to the bottom edge", () => {
  // the tall layout is controls-first, list last (picker-order.test.ts); the short window inverts
  // exactly that — the filtered matches sit directly under the name box being typed in, and the
  // Create button holds still at the bottom, above the keyboard, where a thumb expects it
  assert.match(CSS, /\.picker-overlay\.kb-tight \.picker-list \{ flex: 1 1 auto; min-height: 0; \}/);
  assert.match(CSS, /\.picker-overlay\.kb-tight \.picker-actions \{ order: 1; \}/);
  // with the create rows between them hidden, the heading sits directly under the name box — its
  // border-top would double the search box's own border-bottom into a thick seam
  assert.match(CSS, /\.picker-overlay\.kb-tight \.picker-alt-head \{ border-top: none; \}/);
});

test("the name box opts the phone keyboard out of predictions and autofill", () => {
  // the keyboard's prediction bar had learned the user's own session names and offered them over
  // this box (the user 2026-08-12, Samsung keyboard) — redundant next to the picker's real list,
  // and mistakable for romp UI. These are the standard opt-out hints; a keyboard may still ignore
  // them (its predictive-text setting is the only sure switch), so the code comment must keep
  // saying so rather than claiming the bar is gone.
  assert.match(RENDER, /search\.setAttribute\("autocomplete", "off"\)/);
  assert.match(RENDER, /search\.autocapitalize = "none"/);
  assert.match(RENDER, /search\.setAttribute\("autocorrect", "off"\)/);
  assert.match(RENDER, /its predictive-text setting is the only sure/);
});
