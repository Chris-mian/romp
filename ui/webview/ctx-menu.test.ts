import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { placeMenu } from "./ctx-menu";

// The shared context menu builder (the Sessions pane's Rename and Delete, the user 2026-09-16): the pure placement rule is
// executed here; the DOM rules (the chat's classes through the theme tokens, dismissal, keyboard reach, the confirm box in the
// chat's classes) are pinned in the source, and the served lab drives them on the real page.
const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "ctx-menu.ts"), "utf8");

test("the card opens right and below the pointer when it fits, flips left or up when it does not, and never leaves the viewport", () => {
  assert.deepEqual(placeMenu(100, 100, 150, 80, 1000, 800), { left: 100, top: 100 });
  assert.deepEqual(placeMenu(950, 100, 150, 80, 1000, 800), { left: 800, top: 100 }, "no room to the right: to the left of the pointer");
  assert.deepEqual(placeMenu(100, 780, 150, 80, 1000, 800), { left: 100, top: 700 }, "no room below: above the pointer");
  assert.deepEqual(placeMenu(2, 2, 150, 80, 1000, 800), { left: 4, top: 4 }, "never past the top-left margin");
  assert.deepEqual(placeMenu(990, 790, 150, 80, 1000, 800), { left: 840, top: 710 }, "both flips, clamped inside");
  assert.deepEqual(placeMenu(20, 20, 300, 200, 200, 100), { left: 4, top: 4 }, "a card larger than the viewport sits at the margin");
});

test("the menu wears the chat's classes and roles, and its rows carry the label, the sub-line and the danger mark", () => {
  assert.match(SRC, /menu\.className = "ctx-menu" \+ \(opts\.className \? " " \+ opts\.className : ""\);/);
  assert.match(SRC, /menu\.setAttribute\("role", "menu"\);/);
  assert.match(SRC, /row\.className = "ctx-item ctx-item-toggle" \+ \(it\.danger \? " ctx-item-danger" : ""\) \+ \(it\.className \? " " \+ it\.className : ""\);/);
  assert.match(SRC, /row\.setAttribute\("role", "menuitem"\);/);
  assert.match(SRC, /label\.className = "ctx-item-label"; label\.textContent = it\.label;/);
  assert.match(SRC, /sub\.className = "ctx-item-sub"; sub\.textContent = it\.sub;/);
  assert.doesNotMatch(SRC, /#[0-9a-fA-F]{6}|rgba?\(/, "no colour in the builder: the sheet's tokens dress it");
});

test("dismissal is a press outside, Escape, any scroll or the window's blur; every listener is removed on close", () => {
  assert.match(SRC, /document\.addEventListener\("pointerdown", onDown, true\);\s*\n\s*document\.addEventListener\("keydown", onKey, true\);\s*\n\s*document\.addEventListener\("scroll", onScroll, true\);\s*\n\s*window\.addEventListener\("blur", onBlur\);/);
  assert.match(SRC, /document\.removeEventListener\("pointerdown", onDown, true\);\s*\n\s*document\.removeEventListener\("keydown", onKey, true\);\s*\n\s*document\.removeEventListener\("scroll", onScroll, true\);\s*\n\s*window\.removeEventListener\("blur", onBlur\);/);
  assert.match(SRC, /const onDown = \(e: Event\) => \{ if \(!menu\.contains\(e\.target as Node\)\) closeContextMenu\(\); \};/, "a press inside the card is not a dismissal");
});

test("keyboard reach: arrows and Home/End move between rows, Enter or Space picks, Escape closes; a keyboard opening focuses the first row", () => {
  assert.match(SRC, /if \(ev\.key === "Escape"\) \{ ev\.preventDefault\(\); ev\.stopPropagation\(\); closeContextMenu\(\); return; \}/);
  assert.match(SRC, /else if \(ev\.key === "ArrowDown"\) \{ ev\.preventDefault\(\); ev\.stopPropagation\(\); move\(list, at, 1\); \}/);
  assert.match(SRC, /else if \(ev\.key === "ArrowUp"\) \{ ev\.preventDefault\(\); ev\.stopPropagation\(\); move\(list, at < 0 \? list\.length : at, -1\); \}/);
  assert.match(SRC, /else if \(\(ev\.key === "Enter" \|\| ev\.key === " "\) && at >= 0\) \{ ev\.preventDefault\(\); ev\.stopPropagation\(\); list\[at\]\.click\(\); \}/);
  assert.match(SRC, /if \(opts\.viaKeyboard && list\.length\) list\[0\]\.focus\(\); else menu\.focus\(\);/);
  assert.match(SRC, /if \(ev\.key === "Tab"\) \{ ev\.preventDefault\(\); ev\.stopPropagation\(\); closeContextMenu\(\); \}/, "Tab closes the card (round two, low b)");
  assert.match(SRC, /menu\.addEventListener\("focusout", \(e\) => \{ const to = e\.relatedTarget as Node \| null; if \(to && !menu\.contains\(to\)\) closeContextMenu\(\); \}\);/, "focus leaving the card closes it");
});

test("the confirm box is the chat's dialog in its classes; Cancel, Escape and the backdrop all answer with the empty value once", () => {
  assert.match(SRC, /overlay\.className = "picker-overlay confirm-overlay"; overlay\.id = "confirm";/);
  assert.match(SRC, /box\.className = "picker-box confirm-box";/);
  assert.match(SRC, /h\.className = "confirm-title"; h\.textContent = title;/);
  assert.match(SRC, /d\.className = "confirm-detail"; d\.textContent = detail;/);
  assert.match(SRC, /btn\.className = "picker-action confirm-btn" \+ \(b\.danger \? " danger" : ""\);/);
  assert.match(SRC, /if \(settled\) return;\s*\n\s*settled = true;\s*\n\s*if \(confirmFinish === finish\) confirmFinish = null;/, "one answer per box");
  assert.match(SRC, /if \(confirmFinish\) confirmFinish\(""\);   \/\/ a box already open answers Cancel and goes, its Escape listener with it/, "a replacing box settles the open one first (round two, low c)");
  assert.match(SRC, /overlay\.addEventListener\("click", \(e\) => \{ if \(e\.target === overlay\) finish\(""\); \}\);/);
  assert.match(SRC, /const onKey = \(e: KeyboardEvent\) => \{ if \(e\.key === "Escape"\) \{ e\.preventDefault\(\); e\.stopPropagation\(\); finish\(""\); \} \};/);
});

test("the tidy (v0.16.0): every menu opens through the builder; a caller with rows of its own builds the card, adds beside the standard rows and shows it", () => {
  assert.match(SRC, /export function menuCard\(opts: CtxMenuOpts = \{\}\): HTMLElement \{/);
  assert.match(SRC, /export function addMenuItem\(menu: HTMLElement, it: CtxItem\): HTMLElement \{/);
  assert.match(SRC, /export function addMenuSep\(menu: HTMLElement\): HTMLElement \{/);
  assert.match(SRC, /export function showMenuCard\(menu: HTMLElement, x: number, y: number, opts: CtxMenuOpts = \{\}\): HTMLElement \{/);
  assert.match(SRC, /if \(opts\.id\) menu\.id = opts\.id;/, "the file browser keeps its #fb-ctx");
  assert.match(SRC, /if \(it\.icon\) row\.appendChild\(it\.icon\);/, "the drawn icon before the body (the tab menu's toggles, the card menu's bell)");
  assert.match(SRC, /if \(typingIn\(ev\.target\)\) return;/, "a key inside a field the menu holds is the field's (the tags flyout's input)");
  assert.match(SRC, /if \(!c\.classList\.contains\("ctx-item"\)\) continue;/, "the card's own rows, never a flyout's");
  assert.match(SRC, /if \(opener && opener !== document\.body && opener\.isConnected && document\.hasFocus\(\)\s*\n\s*&& \(menu\.contains\(active\) \|\| active === document\.body \|\| active === null\)\) opener\.focus\(\{ preventScroll: true \}\);/,
    "the focus goes back to the opener only when the card held it and the document has the focus (the Sessions pane's round-three rule)");
  const read = (f: string) => fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", f), "utf8");
  assert.match(read("render.ts"), /ctxMenuEl = showMenuCard\(menu, e\.clientX, e\.clientY, \{ onClose: onTabMenuClosed \}\);/, "the chat tab menu");
  assert.match(read("render.ts"), /ctxMenuEl = openContextMenu\(e\.clientX, e\.clientY, items, \{ onClose: onTabMenuClosed \}\);/, "the chat selection menu");
  assert.match(read("feed.ts"), /openContextMenu\(e\.clientX, e\.clientY, items\);/, "the feed card menu");
  assert.match(read("file-browse.ts"), /openContextMenu\(e\.clientX, e\.clientY, items, \{ id: "fb-ctx" \}\);/, "the file browser's row menu");
  for (const f of ["render.ts", "feed.ts", "file-browse.ts"]) assert.doesNotMatch(read(f), /el\("div", "ctx-menu"\)/, f + " builds no top-level card by hand");
  assert.doesNotMatch(read("render.ts"), /window\.addEventListener\("(mousedown|scroll)", \(e\) => \{ if \(ctxMenuEl/, "no dismissal listeners of the tab menu's own");
});

test("every key the menu consumes stops at the card: a surface under it never walks on the menu's arrows (round two)", () => {
  // the file browser's document-level handler walked its listing on the same ArrowDown that moved the menu's focus
  const keys = SRC.slice(SRC.indexOf('menu.addEventListener("keydown"'), SRC.indexOf("// the menu never becomes the row's click"));
  for (const k of ["Tab", "ArrowDown", "ArrowUp", "Home", "End"]) assert.match(keys, new RegExp('ev\\.key === "' + k + '"\\) \\{ ev\\.preventDefault\\(\\); ev\\.stopPropagation\\(\\);'), k + " stops");
  assert.doesNotMatch(keys, /preventDefault\(\); (?:move|list\[|closeContextMenu)/, "no consumed key without the stop");
  const browse = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "file-browse.ts"), "utf8");
  assert.match(browse, /if \(document\.getElementById\("fb-ctx"\) \|\| \(e\.key === "Escape" && e\.defaultPrevented\)\) return;/, "the browser yields every key to an open row menu, per its topmost-first comment");
});
