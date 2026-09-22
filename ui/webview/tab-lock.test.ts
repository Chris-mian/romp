// THE TAB LOCK (T395, the user 2026-09-12; T405: off the strip; T415: a switch in the settings card's Tab strip section): one
// setting freezes every way a tab moves (the drag reorder, a drag into another column or the split's edge, the tab menu's Move
// to rows) until it is cleared. Per browser like the gear's other settings, written by the card's switch and fanned out the
// gear's way (the same-document signal, the host relay). The strip's padlock button and its icons.ts drawing left with T415;
// the Sessions pane's lock-to-now toggle draws the one padlock now. Pinned at the source here; tests/test_tab_lock_browser.py
// drives the served dashboard (a drag with the lock on moves nothing, the same drag with it off moves the tab; the gear's jump
// to the section; screenshots).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const UI = path.resolve(process.cwd(), "..", "ui", "webview");
const RENDER = fs.readFileSync(path.join(UI, "render.ts"), "utf8");
const GEAR = fs.readFileSync(path.join(UI, "gear.js"), "utf8");   // the settings card: the lock's row since T415
const CSS = fs.readFileSync(path.join(UI, "styles.css"), "utf8");
const ICONS = fs.readFileSync(path.join(UI, "icons.ts"), "utf8");
const TIMELINE = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js"), "utf8");
const KERNEL = fs.readFileSync(path.resolve(process.cwd(), "..", "kernel", "kernel.py"), "utf8");

// a localStorage shim before the settings module loads (load/save read it at call time)
const store: Record<string, string> = {};
(globalThis as any).localStorage = {
  getItem: (k: string) => (k in store ? store[k] : null),
  setItem: (k: string, v: string) => { store[k] = v; },
  removeItem: (k: string) => { delete store[k]; },
};
// eslint-disable-next-line @typescript-eslint/no-var-requires
const S = require("./settings") as typeof import("./settings");

test("the padlock is ONE drawing, the Sessions pane's own since T415 (the strip's copy in icons.ts had no importer left once the lock became the card's switch)", () => {
  for (const d of ["M4.8 6.2 V4.4 a2.2 2.2 0 0 1 4.4 0 V6.2", "M9.4 6.2 V5.3 A2.4 2.4 0 0 1 13.6 3.7"]) {
    assert.ok(TIMELINE.includes(d), "the timeline draws the shackle " + d);
    assert.ok(!ICONS.includes(d), "icons.ts no longer carries a second copy of the shackle " + d);
  }
  assert.match(TIMELINE, /x: 3, y: 6\.2, width: 8, height: 5\.6, rx: 1\.2/, "the timeline's body");
  assert.doesNotMatch(ICONS, /ICON_LOCK|lockSvg|LOCK_BODY|LOCK_SHACKLE/, "the dead padlock constants are gone from icons.ts (T415 part two, low 2)");
  assert.match(TIMELINE, /the one padlock drawing \(T395; the chat strip's copy in ui\/webview\/icons\.ts left with T415/, "the timeline says so");
  assert.match(RENDER, /^import \{ GEAR_GLYPH, ICON_FORK \} from "\.\/icons";/m);   // T405: the strip's gear glyph; the lock icons left render.ts with the gear's menu (T415), icons.ts keeps them for the timeline's drawing
});

test("the lock is a checkbox row in the settings' own Tab strip section, above Tab widgets, where the strip's gear jumps (T415, the user 2026-09-14)", () => {
  // the strip's button left in T405 (strip-chrome.test.ts pins the gear); the gear's menu row left in T415: the state, the drag rules and the saveSettings road below are as they were
  assert.doesNotMatch(RENDER, /el\("span", "tab-lockbox"\)|el\("button", "tab-lock"|Lock the tabs in place|openRowsMenu/, "no lock button, box or menu row in the strip");
  const chat = GEAR.slice(GEAR.indexOf("data-pane=chat"), GEAR.indexOf("data-pane=feed"));
  assert.ok(chat.indexOf("data-section=tabstrip>Tab strip<") > 0 && chat.indexOf("data-section=tabstrip") < chat.indexOf("data-section=tabwidgets"), "the Tab strip section, above Tab widgets");
  assert.match(chat, /<input type=checkbox id=rs-tablock>/, "the lock is the house checkbox row");
  assert.match(GEAR, /tl\.addEventListener\('change', function \(\) \{ var s = load\(\); s\.tabsLocked = tl\.checked; save\(s\); \}\);/, "a change writes tabsLocked through the gear's save, which the strip hears");
  assert.match(GEAR, /tl\.checked = !!s\.tabsLocked;/, "and every open reads it back");
  assert.match(RENDER, /gear\.addEventListener\("click", \(e\) => \{ e\.stopPropagation\(\); openSettingsOn\("chat", "tabstrip"\); \}\);/, "the gear's click is the way there");
});

test("the dress: the strip's right-end wrapper (the tags button and the gear, T412) has the tags box's floor; the lock's own rules are gone", () => {
  assert.doesNotMatch(CSS, /\n\.tab-lockbox \{|\n\.tab-lock \{|\n\.tab-lock\.on \{/, "no lock button rules");
  assert.match(RENDER, /^import \{ openTagMenu, tagMenuButton, syncTagFilter, tagChip, TAG_BTN_BORDER_CSS \} from "\.\/tag-menu";/m, "the rows menu helper left the strip's import with the gear's menu (T415)");
  const end = CSS.match(/\n\.tab-strip-end \{[^}]*\}/)![0];
  assert.match(end, /min-height: 31px;/); assert.match(end, /margin-left: auto;/);
  assert.match(CSS, /\nbody\.dense-chrome \.tab-strip-end \{ min-height: 25px; \}/, "the dense floor follows the dense + tab, as the tags box's does");
});

test("locked, nothing moves: every draggable gate, both dragstart guards, the menu's Move to rows, and the strip's signature", () => {
  assert.equal((RENDER.match(/tab\.draggable = !fedMissing && !settings\.tabsLocked;/g) || []).length, 2, "the skeleton tab and the rename's restore");
  assert.match(RENDER, /tab\.draggable = !s\.sub && !fedMissing && !isProvisionalId\(id\) && !settings\.tabsLocked;/, "the live tab");
  assert.match(RENDER, /if \(fedMissing \|\| settings\.tabsLocked\) \{ e\.preventDefault\(\); return; \}/, "the shared dragstart refuses too (belt and braces)");
  assert.match(RENDER, /head\.draggable = !settings\.tabsLocked;/, "a group drag moves tabs as well");
  assert.match(RENDER, /head\.addEventListener\("dragstart", \(e\) => \{\s*\n\s*if \(settings\.tabsLocked\) \{ e\.preventDefault\(\); return; \}\s*\n\s*draggedGroup = name;/);
  assert.match(RENDER, /if \(settings\.tabsLocked\) \{ row\.classList\.add\("ctx-item-locked"\); row\.setAttribute\("aria-disabled", "true"\); bodyE\.title = "Tabs are locked: the lock is in the settings \(Chat, Tab strip\)"; \}/, "the Move to rows read held: the label, not the +");
  assert.match(RENDER, /plus\.title = "add this tag too \(the session keeps its other tags\)" \+ \(settings\.tabsLocked \? ": adding is not a move, so the lock does not hold it" : ""\);/, "the + keeps its own title");
  assert.match(CSS, /\n\.ctx-sub \.ctx-item\.ctx-item-locked > \.ctx-item-body \{ opacity: 0\.45; \}/, "the dim on the body, so the + keeps full strength (round one, LOW 1)");
  assert.match(CSS, /\n\.ctx-sub \.ctx-item\.ctx-item-locked \{ cursor: default; \}\n\.ctx-sub \.ctx-item\.ctx-item-locked > \.ctx-item-body/);
  assert.match(RENDER, /row\.addEventListener\("click", \(e2\) => \{ e2\.stopPropagation\(\); if \(settings\.tabsLocked\) return; moveUnion\(home, g\);/, "and do nothing");
  assert.match(RENDER, /settings\.tabCtx, settings\.stripGroupRows, settings\.tabsLocked, settings\.tabStateBadge, settings\.theme,/, "in the strip's signature: the toggle repaints");
  assert.match(RENDER, /__rompMovableSession = \(sid: unknown\): boolean => typeof sid === "string" && !!sid && !isProvisionalId\(sid\) && !isSubId\(sid\) && !settings\.tabsLocked;/, "the shell's question before a move into another column answers no while locked");
  assert.match(RENDER, /__rompMoveRefusal = \(sid: unknown\): string => typeof sid !== "string" \|\| !sid \|\| isProvisionalId\(sid\) \|\| isSubId\(sid\) \? "not-open" : settings\.tabsLocked \? "locked" : "";/, "…and the reason behind it (round one, MEDIUM 2)");
  assert.match(KERNEL, /function refusal\(f,sid\)\{try\{var w=f&&f\.contentWindow&&f\.contentWindow\.__rompMoveRefusal;return typeof w==='function'\?String\(w\(sid\)\|\|''\):'';\}catch\(e\)\{return '';\}\}/);
  assert.match(KERNEL, /var LOCKED='The tabs are locked: unlock them in the settings \(Chat, Tab strip\) to move this session\.';/, "the toast names the settings' section, the way back (T415)");
  assert.match(KERNEL, /var why=refusal\(src,sid\);if\(why==='locked'\)return notify\(LOCKED\);if\(why\|\|!movable\(src,sid\)\)return notify\('Only an open session can be moved between columns\.'\);/, "a lock is not \"not an open session\"");
  assert.match(RENDER, /if \(fedMissing \|\| settings\.tabsLocked\) return false;/, "a drop after another window locked mid-drag commits nothing (round one, LOW 3)");
  assert.match(RENDER, /const focusedGear = !!focusedEl\?\.closest\("\.tab-widgets-gear"\);/);
  assert.match(RENDER, /\} else if \(focusedGear\) \(bar\.querySelector\("\.tab-widgets-gear"\) as HTMLElement \| null\)\?\.focus\(\);/, "the gear held the keyboard when a push rebuilt the strip: it keeps the focus, not the active tab (round one, LOW 2; a lock toggle leaves the focus on the menu's row, and the menu's Escape refocuses the live gear itself; T405 round two, low 6)");
});

test("the setting: per browser, off by default, only the literal true locks; the write fans out like the gear's", () => {
  assert.equal(S.DEFAULT_SETTINGS.tabsLocked, false);
  store["romp:settings"] = JSON.stringify({ tabsLocked: true }); assert.equal(S.loadSettings().tabsLocked, true);
  store["romp:settings"] = JSON.stringify({ tabsLocked: "yes" }); assert.equal(S.loadSettings().tabsLocked, false, "only the literal true");
  store["romp:settings"] = JSON.stringify({ compact: true }); assert.equal(S.loadSettings().tabsLocked, false, "a store from before the key reads unlocked");
  delete store["romp:settings"]; assert.equal(S.loadSettings().tabsLocked, false);
  assert.match(GEAR, /tl\.addEventListener\('change', function \(\) \{ var s = load\(\); s\.tabsLocked = tl\.checked; save\(s\); \}\);/,
    "the live road (T415): the card's switch writes the store through the gear's save, which fans out the same-document signal and the host relay");
  assert.doesNotMatch(RENDER, /function setTabsLocked\(/, "the strip's own setter had no caller left and is gone (T415 part two, low 2)");
});

test("the Sessions pane shares the order, so the padlock holds its drags too: lanes, the dialog's rows and the pills (round one, MEDIUM 1)", () => {
  assert.match(TIMELINE, /^const LOCKED_TEXT = 'the tabs are locked: unlock them in the settings \(Chat, Tab strip\) to move sessions';/m, "the way back names the settings' section (T415)");
  assert.match(TIMELINE, /_tabsLocked\(\) \{\s*\n\s*try \{ const s = JSON\.parse\(localStorage\.getItem\('romp:settings'\) \|\| '\{\}'\); return !!\(s && s\.tabsLocked === true\); \}/, "the strip's own store key, read at the gesture (the pane is served raw: no import)");
  assert.match(TIMELINE, /_beginDrag\(sid, e\) \{\s*\n\s*if \(this\._tabsLocked\(\)\) return;/, "a lane drag never starts while locked");
  assert.match(TIMELINE, /_persistOrder\(order, prev, sid, from\) \{\s*\n\s*if \(this\._tabsLocked\(\)\) \{[^]*?this\._applyOrderToData\(prev\);\s*\n\s*this\.settingRefused\(\{ gesture: 'order', sid: sid \|\| '', from: from \|\| '', text: LOCKED_TEXT \}\);\s*\n\s*return;/, "a persist after a mid-drag lock writes nothing and puts the lanes back");
  assert.match(TIMELINE, /rowHit\.style\.cursor = this\._tabsLocked\(\) \? 'default' : 'grab';/);
  assert.match(TIMELINE, /if \(this\._tabsLocked\(\)\) \{ const lt = el\('title', \{\}\); lt\.textContent = LOCKED_TEXT; rowHit\.appendChild\(lt\); \}/, "the lane says why on hover");
  assert.match(TIMELINE, /wh\.style\.cursor = this\._tabsLocked\(\) \? 'default' : 'grab';/);
  assert.match(TIMELINE, /pillCell\.addEventListener\('pointerdown', \(e\) => \{\s*\n\s*if \(this\._tabsLocked\(\)\) return;/, "the pills' order too");
  assert.match(TIMELINE, /if \(!this\._tabsLocked\(\)\) this\._setLens\(\{ tagOrder: names \}, \{ tagOrder: true \}\);/);
  assert.match(TIMELINE, /e\.preventDefault\(\);\s*\n\s*if \(this\._tabsLocked\(\)\) return;[^\n]*\n\s*const cells = Array\.from\(grid\.children\)\.filter\(\(c\) => c\._sid\);/, "the dialog's rows too");
  assert.match(TIMELINE, /window\.addEventListener\('storage', \(e\) => \{\s*\n\s*if \(!e \|\| e\.key !== 'romp:settings'\) return;/, "a lock in another window repaints the lanes through the storage event, the strip's own road");
});
