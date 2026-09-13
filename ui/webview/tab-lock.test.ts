// THE TAB LOCK (T395, the user 2026-09-12): a padlock button in the chat tab strip, right after the + tab and before
// the tags box, that freezes every way a tab moves (the drag reorder, a drag into another column or the split's edge,
// the tab menu's Move to rows) until pressed again. Per browser like the gear's settings, fanned out the same way. The
// drawing is the Sessions pane's lock-to-now glyph, stated once in icons.ts (the timeline is served raw and states the
// same numbers). Pinned at the source here; tests/test_tab_lock_browser.py drives the served strip (a drag with the lock
// on moves nothing, the same drag with it off moves the tab; the box's place and dress; screenshots).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const UI = path.resolve(process.cwd(), "..", "ui", "webview");
const RENDER = fs.readFileSync(path.join(UI, "render.ts"), "utf8");
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

test("the padlock is ONE drawing: icons.ts states the Sessions pane's numbers, and the strip imports both states", () => {
  for (const d of ["M4.8 6.2 V4.4 a2.2 2.2 0 0 1 4.4 0 V6.2", "M9.4 6.2 V5.3 A2.4 2.4 0 0 1 13.6 3.7"]) {
    assert.ok(TIMELINE.includes(d), "the timeline draws the shackle " + d);
    assert.ok(ICONS.includes(d), "icons.ts states the same shackle " + d);
  }
  assert.match(TIMELINE, /x: 3, y: 6\.2, width: 8, height: 5\.6, rx: 1\.2/, "the timeline's body");
  assert.match(ICONS, /const LOCK_BODY = '<rect x="3" y="6\.2" width="8" height="5\.6" rx="1\.2"\/>';/, "the same body");
  assert.match(ICONS, /'<svg viewBox="0 0 15 15" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1\.4"'/, "the timeline's 15-unit drawing and 1.4 stroke, drawn at the tag glyph's 14px so the boxes match (round two)");
  assert.match(ICONS, /^export const ICON_LOCK = lockSvg\(LOCK_SHACKLE_SEATED\);/m);
  assert.match(ICONS, /^export const ICON_LOCK_OPEN = lockSvg\(LOCK_SHACKLE_OPEN\);/m);
  assert.match(TIMELINE, /the same numbers as ui\/webview\/icons\.ts ICON_LOCK \/ ICON_LOCK_OPEN/, "the timeline points back: one drawing, change both");
  assert.match(RENDER, /^import \{ GEAR_GLYPH, ICON_FORK, ICON_LOCK, ICON_LOCK_OPEN \} from "\.\/icons";/m);   // T405: the strip's gear glyph rides the same import
});

test("the lock is a row in the strip's gear menu (T405, the user 2026-09-13), with the button's two titles, toggling the setting and keeping the menu open", () => {
  // the strip's button left (strip-chrome.test.ts pins the gear and its box); the state, the drag rules and the saveSettings road below are as they were
  assert.doesNotMatch(RENDER, /el\("span", "tab-lockbox"\)|el\("button", "tab-lock"/, "no lock button or box in the strip");
  assert.match(RENDER, /\{ label: "Lock the tabs in place", current: settings\.tabsLocked, glyph: settings\.tabsLocked \? ICON_LOCK : ICON_LOCK_OPEN,/, "the row: the ✓ when locked, the padlock seated or open");
  assert.match(RENDER, /title: settings\.tabsLocked \? "Tabs are locked in place: click to allow moving them again" : "Lock the tabs in place: no drag or move until clicked again",/, "the two titles the button wore");
  assert.match(RENDER, /press: \(\) => \{ setTabsLocked\(!settings\.tabsLocked\); return false; \} \},/, "the same toggle; false keeps the menu open and repaints it");
});

test("the dress: the padlock rides the menu row; the strip's gear box has the tags box's floor; the lock's own rules are gone", () => {
  assert.doesNotMatch(CSS, /\n\.tab-lockbox \{|\n\.tab-lock \{|\n\.tab-lock\.on \{/, "no lock button rules");
  assert.match(RENDER, /^import \{ openTagMenu, tagMenuButton, syncTagFilter, tagChip, TAG_BTN_BORDER_CSS, openRowsMenu \} from "\.\/tag-menu";/m, "the rows menu comes from the tag menu's module");
  const box = CSS.match(/\n\.tab-gearbox \{[^}]*\}/)![0];
  assert.match(box, /min-height: 31px;/); assert.match(box, /margin-left: auto;/);
  assert.match(CSS, /\nbody\.dense-chrome \.tab-gearbox \{ min-height: 25px; \}/, "the dense floor follows the dense + tab, as the tags box's does");
});

test("locked, nothing moves: every draggable gate, both dragstart guards, the menu's Move to rows, and the strip's signature", () => {
  assert.equal((RENDER.match(/tab\.draggable = !fedMissing && !settings\.tabsLocked;/g) || []).length, 2, "the skeleton tab and the rename's restore");
  assert.match(RENDER, /tab\.draggable = !s\.sub && !fedMissing && !isProvisionalId\(id\) && !settings\.tabsLocked;/, "the live tab");
  assert.match(RENDER, /if \(fedMissing \|\| settings\.tabsLocked\) \{ e\.preventDefault\(\); return; \}/, "the shared dragstart refuses too (belt and braces)");
  assert.match(RENDER, /head\.draggable = !settings\.tabsLocked;/, "a group drag moves tabs as well");
  assert.match(RENDER, /head\.addEventListener\("dragstart", \(e\) => \{\s*\n\s*if \(settings\.tabsLocked\) \{ e\.preventDefault\(\); return; \}\s*\n\s*draggedGroup = name;/);
  assert.match(RENDER, /if \(settings\.tabsLocked\) \{ row\.classList\.add\("ctx-item-locked"\); row\.setAttribute\("aria-disabled", "true"\); bodyE\.title = "Tabs are locked: the lock is in the tab strip's gear menu"; \}/, "the Move to rows read held: the label, not the +");
  assert.match(RENDER, /plus\.title = "add this tag too \(the session keeps its other tags\)" \+ \(settings\.tabsLocked \? ": adding is not a move, so the lock does not hold it" : ""\);/, "the + keeps its own title");
  assert.match(CSS, /\n\.ctx-sub \.ctx-item\.ctx-item-locked > \.ctx-item-body \{ opacity: 0\.45; \}/, "the dim on the body, so the + keeps full strength (round one, LOW 1)");
  assert.match(CSS, /\n\.ctx-sub \.ctx-item\.ctx-item-locked \{ cursor: default; \}\n\.ctx-sub \.ctx-item\.ctx-item-locked > \.ctx-item-body/);
  assert.match(RENDER, /row\.addEventListener\("click", \(e2\) => \{ e2\.stopPropagation\(\); if \(settings\.tabsLocked\) return; moveUnion\(home, g\);/, "and do nothing");
  assert.match(RENDER, /settings\.tabCtx, settings\.stripGroupRows, settings\.tabsLocked, settings\.theme,/, "in the strip's signature: the toggle repaints");
  assert.match(RENDER, /__rompMovableSession = \(sid: unknown\): boolean => typeof sid === "string" && !!sid && !isProvisionalId\(sid\) && !isSubId\(sid\) && !settings\.tabsLocked;/, "the shell's question before a move into another column answers no while locked");
  assert.match(RENDER, /__rompMoveRefusal = \(sid: unknown\): string => typeof sid !== "string" \|\| !sid \|\| isProvisionalId\(sid\) \|\| isSubId\(sid\) \? "not-open" : settings\.tabsLocked \? "locked" : "";/, "…and the reason behind it (round one, MEDIUM 2)");
  assert.match(KERNEL, /function refusal\(f,sid\)\{try\{var w=f&&f\.contentWindow&&f\.contentWindow\.__rompMoveRefusal;return typeof w==='function'\?String\(w\(sid\)\|\|''\):'';\}catch\(e\)\{return '';\}\}/);
  assert.match(KERNEL, /var LOCKED='The tabs are locked: unlock them in the tab strip\\\\u2019s gear menu \(Lock the tabs in place\) to move this session\.';/, "the toast names the gear's menu, the way back (T405)");
  assert.match(KERNEL, /var why=refusal\(src,sid\);if\(why==='locked'\)return notify\(LOCKED\);if\(why\|\|!movable\(src,sid\)\)return notify\('Only an open session can be moved between columns\.'\);/, "a lock is not \"not an open session\"");
  assert.match(RENDER, /if \(fedMissing \|\| settings\.tabsLocked\) return false;/, "a drop after another window locked mid-drag commits nothing (round one, LOW 3)");
  assert.match(RENDER, /const focusedGear = !!focusedEl\?\.closest\("\.tab-widgets-gear"\);/);
  assert.match(RENDER, /\} else if \(focusedGear\) \(bar\.querySelector\("\.tab-widgets-gear"\) as HTMLElement \| null\)\?\.focus\(\);/, "a keyboard press on the gear (its menu toggled the lock) keeps the focus there across the rebuild (round one, LOW 2; T405)");
});

test("the setting: per browser, off by default, only the literal true locks; the write fans out like the gear's", () => {
  assert.equal(S.DEFAULT_SETTINGS.tabsLocked, false);
  store["romp:settings"] = JSON.stringify({ tabsLocked: true }); assert.equal(S.loadSettings().tabsLocked, true);
  store["romp:settings"] = JSON.stringify({ tabsLocked: "yes" }); assert.equal(S.loadSettings().tabsLocked, false, "only the literal true");
  store["romp:settings"] = JSON.stringify({ compact: true }); assert.equal(S.loadSettings().tabsLocked, false, "a store from before the key reads unlocked");
  delete store["romp:settings"]; assert.equal(S.loadSettings().tabsLocked, false);
  assert.match(RENDER, /function setTabsLocked\(on: boolean\): void \{\s*\n\s*settings = saveSettings\(\{ tabsLocked: on \}\);\s*\n\s*try \{ window\.dispatchEvent\(new Event\("romp:settings"\)\); \} catch \{[^}]*\}\s*\n\s*vscodeApi\?\.postMessage\(\{ type: "settingsSync", settings \}\);\s*\n\}/,
    "the store, the same-document signal (the strip repaints through it), the host relay for VS Code's panes");
});

test("the Sessions pane shares the order, so the padlock holds its drags too: lanes, the dialog's rows and the pills (round one, MEDIUM 1)", () => {
  assert.match(TIMELINE, /^const LOCKED_TEXT = 'the tabs are locked: unlock them in the tab strip\\u2019s gear menu \(Lock the tabs in place\) to move sessions';/m, "the way back names the gear's menu (T405)");
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
