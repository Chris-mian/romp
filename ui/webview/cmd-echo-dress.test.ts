// The kernel's ECHO of a slash COMMAND wears the queued bubble's provisional dress (T403, the user 2026-09-13): the landed
// command row sheds its bubble with `border: none`, which leaves the border WIDTH at the initial `medium` (3px) and no style;
// the echo dress then set the style alone to dashed, so a provisional /compact wore a thick blue dashed ring while the queued
// /model row under it wore the 1px queued-bubble dress. The fix is in the sheet alone: the echo of a command joins the queued
// bubble's rule by its own selector, the echo dress names its width, and the landed row's chip and ✦ rules stand down on the
// echo. These pins read styles.css as text; the served lab (tests/test_provisional_cmd_dress_browser.py) reads the computed
// styles on the real page.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("the echo of a command is the queued bubble, by the shared rule's own selector list", () => {
  assert.match(CSS, /\.queued-bubble, \.notice\.queued-bubble, \.notice\.notice-slim\.queued-bubble,\s*\n\.turn\.echo \.user-bubble\.cmd-row\.echo-bubble \{/,
    "one provisional vocabulary: the command's echo is named in the queued bubble's rule, not a copy of its values");
  const rule = CSS.slice(CSS.indexOf(".turn.echo .user-bubble.cmd-row.echo-bubble {"), CSS.indexOf("}", CSS.indexOf(".turn.echo .user-bubble.cmd-row.echo-bubble {")));
  assert.match(rule, /border: 1px dashed color-mix\(in srgb, var\(--you\) 55%, transparent\);/, "the shared rule's own 1px dashed border");
  assert.match(rule, /border-radius: 14px; padding: 7px 12px; color: var\(--prov-ink\);/);
});

test("the echo dress names its width: a style alone inherits whatever width the bubble's rules left", () => {
  assert.match(CSS, /\.turn\.echo \.echo-bubble \{ border-width: 1px; border-style: dashed; border-color: color-mix\(in srgb, var\(--you\) 65%, transparent\); opacity: 0\.85; \}/);
  assert.match(CSS, /\.turn\.echo \.user-bubble\.cmd-row\.echo-bubble \{ opacity: 1; \}/, "the queued fade is in the colours (T337), so the command's echo drops the echo dress's opacity");
});

test("the landed command row's ✦ and blue chip are the landed row's alone", () => {
  assert.match(CSS, /\.user-bubble\.cmd-row:not\(\.echo-bubble\)::before \{ content: "✦";/, "no ✦ on the provisional command: a queued /compact has none");
  assert.match(CSS, /\.user-bubble\.cmd-row:not\(\.echo-bubble\) \.slash-cmd-chip \{ background: var\(--bg\); color: var\(--you\);/, "the provisional command's chip is the queued bubble's default chip");
  assert.doesNotMatch(CSS, /\.user-bubble\.cmd-row::before \{/, "the unscoped mark rule is gone");
  assert.doesNotMatch(CSS, /\.user-bubble\.cmd-row \.slash-cmd-chip \{/, "the unscoped chip rule is gone");
  // the landed row itself is unchanged: no bubble, no border, dim ink
  assert.match(CSS, /\.user-bubble\.cmd-row \{ max-width: none; background: none; border: none; border-radius: 0;\s*\n\s*padding: 2px 0; color: var\(--dim\); \}/);
});

test("round two: the args rule is the landed row's alone, the undelivered command row is named at three classes, the provisional chip wears the bubble's tokens", () => {
  // MEDIUM: unscoped, the landed row's args rule won the echo's argument span (dim ink beside the queued bubble's faded ink)
  assert.match(CSS, /\.user-bubble\.cmd-row:not\(\.echo-bubble\) \.slash-cmd-args \{ color: var\(--dim\); \}/);
  assert.doesNotMatch(CSS, /\.user-bubble\.cmd-row \.slash-cmd-args \{/, "the unscoped args rule is gone");
  // LOW 2: the comment counts the selector's classes for the cascade, and there are five
  assert.match(CSS, /by this selector \(five classes: it outranks/);
  assert.equal((".turn.echo .user-bubble.cmd-row.echo-bubble".match(/\./g) || []).length, 5);
  // LOW 3: the undelivered command row's border no longer rides source order against the cmd-row reset (both two classes)
  assert.match(CSS, /\.user-bubble\.cmd-row\.undelivered-bubble, \.user-bubble\.undelivered-bubble, \.romp-bubble\.undelivered-bubble \{\s*\n\s*border: 1px dashed color-mix\(in srgb, var\(--err\) 65%, transparent\); opacity: 0\.85;/);
  // LOW 1: the chip inside a provisional bubble (queued, or the echo of a command) wears the bubble's own tokens, one rule for both
  assert.match(CSS, /\.queued-bubble \.slash-cmd-chip, \.turn\.echo \.user-bubble\.cmd-row\.echo-bubble \.slash-cmd-chip \{\s*\n\s*background: color-mix\(in srgb, var\(--you\) 16%, transparent\); color: var\(--prov-ink\); border-color: color-mix\(in srgb, var\(--you\) 55%, transparent\);/);
});
