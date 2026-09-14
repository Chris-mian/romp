// THE STRIP'S GEAR JUMPS STRAIGHT TO THE SETTINGS, AND THE TAB LOCK IS A SECTION THERE (T415, the user 2026-09-14): a click
// on the tab strip's gear opens the settings' Chat tab scrolled to the strip's own section, no menu in between; the tab lock,
// a row in that gear's menu since T405, is a switch in a small "Tab strip" section that sits ABOVE Tab widgets; with the lock
// moved the gear's menu kept nothing, so the menu and the rows-menu helper it alone used are gone, and the gear renders only
// where the settings can be reached (the shell, or a host with its own gear). The three way-back texts that named the gear's
// menu name the settings' section. Source pins; the lab (tests/test_tab_lock_browser.py) drives the road.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const ui = (...p: string[]) => fs.readFileSync(path.resolve(process.cwd(), "..", "ui", ...p), "utf8");
const RENDER = ui("webview", "render.ts");
const GEAR = ui("webview", "gear.js");
const MENU = ui("webview", "tag-menu.ts");
const VIEW = ui("romp-timeline-view.js");
const KERNEL = fs.readFileSync(path.resolve(process.cwd(), "..", "kernel", "kernel.py"), "utf8");

test("the strip's gear: one click, straight to the settings' Tab strip section; no menu, no popup role; drawn only where the settings can be reached", () => {
  const block = RENDER.slice(RENDER.indexOf("// THE STRIP'S GEAR (T379"), RENDER.indexOf("  bar.appendChild(end);"));
  assert.match(block, /if \(settingsReachable\) \{\s*\n\s*const gear = el\("button", "tab-widgets-gear"\) as HTMLButtonElement;/, "the gear is drawn only where a settings card can open (the shell, or a host with its own gear)");
  assert.match(block, /gear\.title = "Tab strip settings";/);
  assert.match(block, /gear\.setAttribute\("aria-label", "Tab strip settings"\);/);
  assert.doesNotMatch(block, /aria-haspopup/, "no menu behind the gear any more");
  assert.match(block, /gear\.addEventListener\("click", \(e\) => \{ e\.stopPropagation\(\); openSettingsOn\("chat", "tabstrip"\); \}\);/, "the jump, direct");
  assert.doesNotMatch(block, /openRowsMenu|Lock the tabs in place|ICON_LOCK/, "the menu and its lock row left the strip");
  assert.doesNotMatch(RENDER, /openRowsMenu/, "the rows-menu helper has no caller left");
  assert.doesNotMatch(MENU, /export function openRowsMenu|RowsMenuRow/, "and is gone from the menu module with its type");
});

test("the settings: a Tab strip section with the lock switch sits above Tab widgets in the Chat tab, wired like every checkbox row", () => {
  const chat = GEAR.slice(GEAR.indexOf("data-pane=chat"), GEAR.indexOf("data-pane=feed"));
  const iStrip = chat.indexOf("<div class='rs-sec' data-section=tabstrip>Tab strip</div>"), iWidgets = chat.indexOf("<div class='rs-sec' data-section=tabwidgets>Tab widgets</div>");
  assert.ok(iStrip > 0 && iWidgets > iStrip, "Tab strip head, then Tab widgets");
  assert.ok(chat.indexOf(">Thinking<") < iStrip, "after Thinking");
  assert.match(chat, /<label class='rs-row'><input type=checkbox id=rs-tablock>"\s*\+\s*'<span><b>Lock the tabs in place<\/b>/, "the lock row: the house checkbox row");
  assert.ok(chat.indexOf("id=rs-tablock") > iStrip && chat.indexOf("id=rs-tablock") < iWidgets, "the row is the section's");
  assert.match(GEAR, /tl = document\.getElementById\('rs-tablock'\)/, "the row's element");
  assert.match(GEAR, /tl\.checked = !!s\.tabsLocked;/, "filled from the store on every open, like the other checkboxes");
  assert.match(GEAR, /tl\.addEventListener\('change', function \(\) \{ var s = load\(\); s\.tabsLocked = tl\.checked; save\(s\); \}\);/, "a change saves through the one gear save, which the strip hears (tabsLocked is in its signature)");
});

test("the way-back texts name the settings' Tab strip section, not a gear menu", () => {
  assert.match(KERNEL, /var LOCKED='The tabs are locked: unlock them in the settings \(Chat, Tab strip\) to move this session\.';/);
  assert.match(VIEW, /const LOCKED_TEXT = 'the tabs are locked: unlock them in the settings \(Chat, Tab strip\) to move sessions';/);
  assert.match(RENDER, /bodyE\.title = "Tabs are locked: the lock is in the settings \(Chat, Tab strip\)";/);
  for (const [name, src] of [["render.ts", RENDER], ["kernel.py", KERNEL], ["the timeline view", VIEW]] as const)
    assert.doesNotMatch(src, /gear menu \(Lock the tabs in place\)|tab strip's gear menu|strip\\u2019s gear menu/, name + " no longer points at a gear menu");
});
