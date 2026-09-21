// The settings' Chat tabs + Text scheme pickers are DROPDOWNS (T117, the user 2026-08-27,
// screenshot: both pickers rendered every option always-expanded, and the Classic/Yatharth
// description spans ran off the card's right edge). The contract:
//   closed = ONE row (the current option's name + description/preview, ellipsized, never
//   overrunning), options one click away — progressive disclosure;
//   open   = the house menu vocabulary (the chat .ctx-menu spec: #252526 card, hairline border,
//   6px radius, the 0 4px 12px shadow, 12px text, 0.82em sub-lines, #1EA1EB ✓-in-circle);
//   dismissal = outside click, Escape, and the cross-pane menu echo (the tag-menu writer already
//   rides every webview bundle; the dropdown wires the listener half);
//   persistence/live-apply = the callers' save() handlers verbatim (pinned in chat-scheme.test.ts
//   and tab-theme.test.ts — this file pins the dropdown SHAPE, those pin what a pick does).
// Source pins per the repo convention (gear.js builds DOM imperatively; no jsdom here).
import { test } from "node:test";
import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const GEAR = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "gear.js"), "utf8");
const pickBody = (() => {
  const at = GEAR.indexOf("function housePick(");
  assert.ok(at > 0, "housePick must exist");
  return GEAR.slice(at, GEAR.indexOf("\n  // The scheme options", at));
})();

test("closed state is ONE row: a full-width button with the current option + caret, no option list", () => {
  assert.match(pickBody, /btn\.innerHTML = \(cur \? rowHTML\(cur\) : '<span style="flex:1 1 auto;min-width:0;color:#8a8a8a">\\u2026<\/span>'\) \+\n\s*'<span style="flex:0 0 auto;margin-left:auto;opacity:0\.55">\\u25BE<\/span>'/,
    "the button re-paints to the CURRENT option each paint — name + description in one row, caret at the end");
  assert.match(pickBody, /width:100%;min-width:0/, "the button fills the row and can shrink — the ellipsis engages instead of overrunning");
  assert.match(pickBody, /menu\.hidden = true;?\n/, "the option menu starts hidden — options are one click away, never always-expanded");
});

test("the descriptions ellipsize in BOTH states, and the row chain can actually shrink", () => {
  // every description/preview span: nowrap + hidden overflow + ellipsis + min-width:0
  for (const fn of ["schemeRowHTML", "themeRowHTML"]) {
    const at = GEAR.indexOf("function " + fn + "(");
    assert.ok(at > 0, fn + " exists");
    const body = GEAR.slice(at, GEAR.indexOf("\n  }", at));
    assert.match(body, /flex:1 1 auto;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis/,
      fn + ": the flexible span clamps — this is the overrun fix at the span level");
  }
  // ...and the picker ROWS' outer spans gained min-width:0 (without it the nowrap min-content
  // pushed the whole row past the card edge — the screenshot's overrun)
  assert.match(GEAR, /<span style='flex:1 1 auto;min-width:0'><b>Theme<\/b>/, "Theme row outer span shrinks");
  assert.match(GEAR, /<span style='flex:1 1 auto;min-width:0'><b>Text scheme<\/b>/, "Text scheme row outer span shrinks");
});

test("the open menu wears the house vocabulary and cannot overflow the panel", () => {
  // the .ctx-menu reference values, inlined like versionMenu's MSTYLE — through the menu TOKENS
  // since T226 (the dark literal rides only as the var() fallback; menu-theme-tokens.test.ts owns
  // the theme story: in light the same string resolves to the cream card)
  assert.match(pickBody, /background:var\(--menu-bg, #252526\);border:1px solid var\(--menu-border, rgba\(255,255,255,0\.12\)\);border-radius:var\(--radius-menu, 6px\);box-shadow:var\(--shadow-menu, 0 4px 12px rgba\(0,0,0,0\.35\)\)/,
    "the .ctx-menu reference values, inlined like versionMenu's MSTYLE (tokens + dark fallbacks)");
  assert.match(pickBody, /font-size:12px;line-height:1\.4;color:var\(--menu-fg, #cccccc\);user-select:none/);
  assert.match(pickBody, /position:absolute;left:0;right:0;top:100%/,
    "anchored inside the row wrapper (the #rs-cmap/#rs-pal mechanic): width = the card's content width, no sideways overflow");
  assert.match(pickBody, /menu\.scrollIntoView\(\{ block: 'nearest' \}\)/,
    "opening reveals the menu inside the scrolling card — the bottom edge never clips it");
  assert.match(pickBody, /background:var\(--check-bg, #1EA1EB\);color:#fff;border-radius:50%;width:13px;height:13px;font-size:9px/,
    "the current option wears the ✓-in-circle mark (themed through --check-bg since T226)");
  assert.match(pickBody, /var\(--menu-hover, rgba\(255,255,255,0\.09\)\)/, "row hover, the shared menu hover wash (themed)");
});

test("the tab-theme sub-lines wear the menu vocabulary's sub scale", () => {
  const at = GEAR.indexOf("function themeRowHTML(");
  const body = GEAR.slice(at, GEAR.indexOf("\n  }", at));
  assert.match(body, /font-size:0\.82em;color:var\(--fg, #cccccc\);opacity:0\.6/, "0.82em at 0.6 opacity — the house sub-line (fg tokened for the light modal, PR #763 item 10)");
});

test("dismissal is event-based: outside click, Escape, the sibling dropdown, and the cross-pane echo", () => {
  assert.match(pickBody, /document\.addEventListener\('click', close\)/);
  assert.match(pickBody, /if \(e\.key === 'Escape'\) close\(\)/);
  assert.match(pickBody, /if \(e\.key === 'romp:menu-echo' && e\.newValue\) close\(\)/,
    "the storage-event listener half — the pointerdown echo writer already rides every webview bundle (tag-menu.ts)");
  assert.match(pickBody, /if \(openHousePick && openHousePick !== menu\) openHousePick\.hidden = true;/,
    "opening one dropdown closes the other — never two open menus");
});

test("both pickers build on the ONE dropdown, and repaint on every settings open", () => {
  assert.match(GEAR, /var csDrop = housePick\(cs, 'scheme', schemeRowHTML,/);
  assert.match(GEAR, /var ttDrop = housePick\(tt, 'theme', themeRowHTML,/);
  assert.match(GEAR, /tcPaint\(\); paintWidgets\(\); csPaint\(\); ttPaint\(\); if/,
    "openSettings repaints ALL closed rows (and the widget rows, T379) — a pick made in another pane shows current on open");
});

test("an empty option list paints a placeholder, never a crash — the effort selects start blank", () => {
  // The swept effort pickers have NO options until /models resolves; options[0].name on an empty
  // list threw inside initGear and took the whole settings panel down (caught headless, pre-merge).
  assert.match(GEAR, /if \(!cur\) cur = options\.length \? options\[0\] : null;/);
  assert.match(GEAR, /cur \? rowHTML\(cur\) : '<span style="flex:1 1 auto;min-width:0;color:#8a8a8a">\\u2026<\/span>'/);
  assert.match(GEAR, /if \(cur && o\.id === cur\.id\) \{/);
});

test("every remaining native select rides the adapter — one vocabulary across the panel", () => {
  assert.match(GEAR, /selectPick\(upm, 'margin-top:5px'\);/);
  assert.match(GEAR, /selectPick\(bk, 'margin-top:5px'\);/);
  assert.match(GEAR, /selectPick\(je, 'flex:0 0 auto;width:45%'\);/);
  assert.match(GEAR, /selectPick\(ie, 'flex:0 0 auto;width:45%'\);/);
  assert.match(GEAR, /selectPick\(de, 'flex:0 0 auto;width:45%'\);/);
  assert.match(GEAR, /repaintSelectPicks\(\);   \/\/ fill\(\) writes sel\.value directly/,
    "fill() sets values with no change event — the closed rows repaint at its end");
});

test("the Context bar widget's option rides the same builder (the Context-gauge picker moved onto its row, T379); tabCtx is written as the widgets' mirror", () => {
  // The user (2026-08-27) approved the one menu vocabulary across the panel; since T379 the gauge's WHEN is the Context bar
  // widget's option in the Chat tab's Tab widgets section, a house picker per option, and the older tabCtx key is written from the prefs on every
  // widget save so older readers keep their meaning (tab-widgets.ts tabCtxOfPrefs).
  assert.doesNotMatch(GEAR, /id=rs-tabctx\b/, "the old Context gauge row and its hidden select are gone");
  assert.match(GEAR, /var drop = housePick\(wrap, cfg\.pickPrefix \+ w\.id \+ '-' \+ o\.key, widgetOptRowHTML,/);   // one builder for both widget sections since T409; the tab section's prefix stays wopt-
  assert.match(GEAR, /pickPrefix: 'wopt-',/);
  assert.match(GEAR, /save: function \(prefs\) \{ var s = load\(\); s\.tabWidgets = prefs; s\.tabCtx = TW\.tabCtxOfPrefs\(prefs\); save\(s\); paintWidgets\(\); \},/,
    "a widget change writes the prefs and the mirror, then repaints the rows in place");
  assert.match(GEAR, /tcPaint\(\); paintWidgets\(\);/, "openSettings repaints the widget rows from the store");
});
