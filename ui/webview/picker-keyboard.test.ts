// The new-session picker folds for a SHORT window (the user 2026-08-10, Chrome on a phone): with the
// on-screen keyboard up, the picker's lower rows sat behind it and nothing gave. The shell sizes the
// lifted chat iframe to the VISIBLE height (--app-h ← the top-level visualViewport, pinned in
// tests/test_kernel.py + test_shell_viewport_fit.py), so the keyboard opening/closing lands in the
// iframe as its own resize event — render.ts keys the kb-tight fold on exactly that, no timers, no UA
// sniffing. What folds (the user 2026-08-12, revising two earlier folds that each hid the wrong
// half): the keyboard is up because a new session's NAME is being typed, so every create control —
// name, directory, backend, billing, host, Create — stays on screen, and the resume list (the
// occasional alternative, already scrollable) collapses to the leftover height. The same resize
// expands the list back. Source-level pins (no jsdom for the renderer).
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

test("kb-tight keeps every create control — the resume list is what gives way", () => {
  // the 2026-08-10 fold hid dir/backend/billing/host, and the first revision of it inverted the
  // column so the list filled the screen instead — both showed the wrong half (the user
  // 2026-08-12). No kb-tight rule may hide a row or reorder the controls-first layout: the list,
  // last in the column and scrollable, is the ONE element that shrinks, and it needs no rule to
  // do it (an overflow container's flex min-height is zero)
  assert.doesNotMatch(CSS, /kb-tight[^{}]*\{[^}]*display: none/);
  assert.doesNotMatch(CSS, /kb-tight[^{}]*\{[^}]*\border\s*:/);   // \b: flex "order:", not "border:"
  assert.doesNotMatch(CSS, /kb-tight \.picker-actions/);
  // …but the list gives way to a FLOOR, not to nothing: when the control rows alone overflow the
  // cap, a zero flex floor left a 0px scroller under a heading still promising the section — a
  // dead-end (no row visible, scrollable, or clickable). One row stays; it scrolls within itself
  assert.match(CSS, /\.picker-overlay\.kb-tight \.picker-list \{ min-height: 52px; \}/);
});

test("folded, the box hugs the short viewport instead of centering into the keyboard", () => {
  // both contexts tighten to the same 12px frame — the standalone overlay's 56px anchor would
  // otherwise push the bottom of the box off-screen
  assert.match(CSS, /#picker\.kb-tight,\s*\nbody\.picker-lifted > #picker\.kb-tight \{ align-items: flex-start; padding: 12px 16px; \}/);
  // dvh, not vh — standalone on a phone, vh is the LARGEST viewport while the fold keys on the
  // current innerHeight, and the mismatch clipped the bottom of the box behind the browser chrome.
  // overflow-y:auto is the backstop for a window too short for even the control rows alone (a
  // landscape phone): the box scrolls rather than the Create button becoming unreachable
  assert.match(CSS, /\.picker-overlay\.kb-tight \.picker-box \{ max-height: calc\(100dvh - 24px\); overflow-y: auto; \}/);
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
