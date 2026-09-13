// THE TAB STRIP'S CHROME (T405, the user 2026-09-13): (1) the strip's gear renders the EXACT glyph the shell's settings
// gear wears at the bottom right of every romp page, from ONE source (icons.ts GEAR_GLYPH: the strip imports it, the kernel
// reads it from the file when it builds the rail), so the two cannot drift; (2) the tab lock left the strip and is a toggle
// row inside that gear's menu, with the two titles the button wore, its state, drag rules and saveSettings road untouched;
// (3) the strip's tag control displays no chips (the tags show in the strip's sections when Group tabs by tag is on, else
// whoever is interested clicks the button; the filter itself is unchanged); (4) the gear sits in a box of its own at the
// strip's farthest right. The rows menu (tag-menu.ts openRowsMenu) is executed over a stub document; the rest are source
// pins on render.ts, styles.css, icons.ts and kernel.py. Synthetic only.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const ui = (...p: string[]) => fs.readFileSync(path.resolve(process.cwd(), "..", ...p), "utf8");
const RENDER = ui("ui", "webview", "render.ts");
const ICONS = ui("ui", "webview", "icons.ts");
const CSS = ui("ui", "webview", "styles.css");
const KERNEL = ui("kernel", "kernel.py");
const TAGMENU = ui("ui", "webview", "tag-menu.ts");

const decodeTs = (lit: string) => lit.replace(/\\u([0-9a-fA-F]{4})/g, (_m, h) => String.fromCharCode(parseInt(h, 16)));

test("one gear, one glyph, one source: the strip renders icons.ts GEAR_GLYPH and the kernel reads the same file for the rail", () => {
  const m = /^export const GEAR_GLYPH = "((?:\\u[0-9a-fA-F]{4}|[^"\\])+)";/m.exec(ICONS);
  assert.ok(m, "icons.ts declares GEAR_GLYPH");
  const glyph = decodeTs(m![1]);
  assert.equal(glyph, "\u26ed", "the gear-without-hub character the rail has worn since 2026-06-29");
  assert.match(RENDER, /^import \{ GEAR_GLYPH, ICON_FORK, ICON_LOCK, ICON_LOCK_OPEN \} from "\.\/icons";/m, "the strip imports it");
  assert.match(RENDER, /gear\.textContent = GEAR_GLYPH;/, "and renders exactly it");
  assert.doesNotMatch(RENDER, /M19\.4 15a1\.7 1\.7 0 0 0 \.3 1\.8/, "the strip's own gear drawing is gone");
  // the rail: the kernel's landing renders _gear_glyph(), which reads icons.ts; no literal gear character in the rail's markup line
  const rail = KERNEL.split("\n").find((l) => l.includes("id=rail-gear")) || "";
  assert.match(rail, /aria-label=Settings>" \+ _gear_glyph\(\) \+ "<\/div>"/, "the rail's markup renders the read glyph");
  assert.equal(rail.includes("\u26ed"), false, "no literal gear character in the rail's line");
  assert.match(KERNEL, /src = \(UI \/ "webview" \/ "icons\.ts"\)\.read_text\(encoding="utf-8"\)/, "_gear_glyph reads icons.ts");
  assert.match(KERNEL, /re\.search\(r'export const GEAR_GLYPH = \\x22\(\(\?:\\\\u\[0-9a-fA-F\]\{4\}\|\[\^\\x22\\\\\]\)\+\)\\x22;', src\)/,
    "with the export's own shape, the quotes as \\x22: api-health-axis.test.ts pairs kernel.py's double quotes to find the landing's rules, so no line may add an odd count");
  const added = KERNEL.slice(KERNEL.indexOf("def _gear_glyph()"), KERNEL.indexOf("\n\n", KERNEL.indexOf("def _gear_glyph()")));
  assert.equal((added.match(/"/g) || []).length % 2, 0, "_gear_glyph's body pairs its double quotes");
  // the failure-mode fallback is pinned equal to the constant, so a change to the glyph moves both or fails here
  const fb = /^_GEAR_GLYPH_FALLBACK = "((?:\\u[0-9a-fA-F]{4}|[^"\\])+)"/m.exec(KERNEL);
  assert.ok(fb, "the kernel names its fallback");
  assert.equal(decodeTs(fb![1]), glyph, "the fallback IS the constant's character");
});

test("the tab lock is a row in the gear's menu with the button's two titles, toggling setTabsLocked and keeping the menu open; Tab widgets… is the other row", () => {
  assert.doesNotMatch(RENDER, /el\("button", "tab-lock"/, "no lock button in the strip");
  assert.doesNotMatch(RENDER, /el\("span", "tab-lockbox"\)/, "no lock box in the strip");
  assert.match(RENDER, /openRowsMenu\(gear, \(\) => \[\s*\n\s*\{ label: "Lock the tabs in place", current: settings\.tabsLocked, glyph: settings\.tabsLocked \? ICON_LOCK : ICON_LOCK_OPEN,\s*\n\s*title: settings\.tabsLocked \? "Tabs are locked in place: click to allow moving them again" : "Lock the tabs in place: no drag or move until clicked again",\s*\n\s*press: \(\) => \{ setTabsLocked\(!settings\.tabsLocked\); return false; \} \},\s*\n\s*\.\.\.\(settingsReachable \? \[\{ label: "Tab widgets…", dim: true, press: \(\) => \{ openSettingsOn\("chat", "tabwidgets"\); \} \}\] : \[\]\),\s*\n\s*\]\);/,
               "the two rows: the lock's toggle (a switch: the menu stays and repaints) and, where a settings gear can be reached, the T379 ask (an action: the menu closes)");
  // the lock's state, its drag rules and its saveSettings road are as they were (tab-lock.test.ts pins them); only the toggle's door moved
  assert.match(RENDER, /const focusedGear = !!focusedEl\?\.closest\("\.tab-widgets-gear"\);/, "a keyboard press on the gear keeps the focus across the strip's rebuild");
  assert.match(RENDER, /\} else if \(focusedGear\) \(bar\.querySelector\("\.tab-widgets-gear"\) as HTMLElement \| null\)\?\.focus\(\);/);
  assert.doesNotMatch(RENDER, /focusedLock/, "the lock's own focus rule went with the button");
});

test("the strip's tag control displays no chips: the host is built for the shared sync and never appended", () => {
  assert.doesNotMatch(RENDER, /const tagChipsHost = el\("span", "tab-tagchips"\);/, "no detached chips host: nothing is built to be dropped (round two, low 3)");
  assert.doesNotMatch(RENDER, /tagBox\.appendChild\(tagChipsHost\);/, "and nothing is appended to the strip's tag box");
  assert.match(RENDER, /syncTagFilter\(tagBtn, null, surfaceLens\(v, "chat"\)/, "the shared sync still runs with no host, so the button's accent says it filters and no chip is built");
  assert.match(TAGMENU, /export function syncTagFilter\(btn: HTMLElement, chipsHost: HTMLElement \| null,/);
  assert.match(TAGMENU, /btn\.setAttribute\("aria-pressed", narrowed \? "true" : "false"\);\s*\n\s*if \(!chipsHost\) return;/, "the sync skips the chip loop with no host");
  // the phone header's mount is untouched: its chips still ride the slot (T161)
  assert.match(RENDER, /mslot\.append\(mBtn, mChips\);/);
});

test("the gear sits in a box of its own appended last, pushed to the strip's farthest right, with the tags box's floor", () => {
  const iTag = RENDER.indexOf("  bar.appendChild(tagBox);\n"), iGear = RENDER.indexOf('const gearBox = el("span", "tab-gearbox");'), iGearAppend = RENDER.indexOf("bar.appendChild(gearBox);");
  assert.ok(iTag > 0 && iTag < iGear && iGear < iGearAppend, "after the tag box, the last thing appended to the bar");
  assert.match(RENDER, /\{\s*\n\s*const settingsReachable = !!\(\(window as any\)\.__rompShowStrip \|\| inRompShell\(\)\);\s*\n\s*const gearBox = el\("span", "tab-gearbox"\);\s*\n\s*const gear = el\("button", "tab-widgets-gear"\) as HTMLButtonElement;/,
               "the gear is everywhere the strip is (the lock's button was); only its Tab widgets row asks whether a settings gear can be reached");
  const box = CSS.match(/\n\.tab-gearbox \{[^}]*\}/)![0];
  assert.match(box, /margin-left: auto;/, "the auto margin pushes it to the right edge of its flex line");
  assert.match(box, /min-height: 31px;/, "the + tab's rendered height, as the tags box");
  assert.match(CSS, /\nbody\.dense-chrome \.tab-gearbox \{ min-height: 25px; \}/, "dense follows");
  assert.match(CSS, /\nbody\.dense-chrome \.tab-widgets-gear \{ line-height: 18px; \}/, "the dense button: 18 + 4 + 2 = 24px inside the 25px row (round two, the medium); dense-chrome-layout.test.ts measures it");
  assert.doesNotMatch(CSS, /\.tab-lockbox|\n\.tab-lock \{|\n\.tab-lock\.on \{/, "the lock button's rules are gone");
  const gear = CSS.match(/\n\.tab-widgets-gear \{[^}]*\}/)![0];
  assert.match(gear, /font-size: 16px;/); assert.match(gear, /line-height: 20px;/);
});

// the rows menu, executed over a stub document (the tag-menu tests' harness): rows, the ✓, a switch keeps the menu and
// repaints, an action closes it, Enter presses, Escape closes and hands the focus back
type Node = { tag: string; attrs: Record<string, string>; kids: Node[]; style: Record<string, string>; handlers: Record<string, (e?: any) => void>;
              dataset: Record<string, string>; offsetWidth: number; offsetHeight: number; textContent: string; innerHTML?: string; tabIndex?: number; title?: string;
              parent?: Node | null; removed?: boolean; focused?: boolean; text?: string;
              setAttribute(k: string, v: string): void; getAttribute(k: string): string | null; appendChild(c: Node): void; addEventListener(k: string, fn: (e?: any) => void): void;
              remove(): void; focus(): void; getBoundingClientRect(): { left: number; right: number; top: number; bottom: number }; children: Node[] };
function harness() {
  let focused: Node | null = null;
  const mk = (tag: string): Node => {
    const n: any = { tag, attrs: {}, kids: [], style: {}, handlers: {}, dataset: {}, offsetWidth: 200, offsetHeight: 100, parent: null,
      get textContent() { return this.kids.map((k: any) => k.tag === "#text" ? k.text || "" : k.textContent).join(""); },
      set textContent(v: string) { this.kids = v ? [{ tag: "#text", text: v }] : []; },
      get children() { return this.kids; },
      setAttribute(k: string, v: string) { this.attrs[k] = v; }, getAttribute(k: string) { return k in this.attrs ? this.attrs[k] : null; },
      appendChild(c: any) { c.parent = this; this.kids.push(c); }, addEventListener(k: string, fn: any) { this.handlers[k] = fn; },
      remove() { this.removed = true; if (this.parent) this.parent.kids = this.parent.kids.filter((k: any) => k !== this); },
      focus() { focused = this; }, getBoundingClientRect() { return { left: 10, right: 40, top: 10, bottom: 30 }; } };
    return n;
  };
  const g = globalThis as any;
  const saved = { document: g.document, window: g.window, localStorage: g.localStorage };
  const body = mk("body");
  g.document = { createElement: mk, createTextNode: (t: string) => ({ tag: "#text", text: t }), body, addEventListener() { /* closers */ } };
  g.window = { addEventListener() { /* storage */ }, innerWidth: 1200, innerHeight: 800 };
  g.localStorage = { setItem() { /* echo */ } };
  const restore = () => { g.document = saved.document; g.window = saved.window; g.localStorage = saved.localStorage; };
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const mod = require("./tag-menu");
  return { mk, body, mod, focused: () => focused, restore };
}
const label = (n: Node): string => n.kids.map((k) => k.tag === "#text" ? (k.text || "") : label(k)).join("");

test("executed: the rows menu renders its rows with the ✓ and titles, a switch keeps it open and repaints, an action closes it, Enter presses, Escape returns the focus", () => {
  const h = harness();
  try {
    let locked = false; const acted: string[] = [];
    const anchor = h.mk("button"); anchor.attrs.class = "tab-widgets-gear";
    h.mod.closeTagMenu();
    h.mod.openRowsMenu(anchor, () => [
      { label: "Lock the tabs in place", current: locked, title: locked ? "Tabs are locked in place: click to allow moving them again" : "Lock the tabs in place: no drag or move until clicked again", press: () => { locked = !locked; return false; } },
      { label: "Tab widgets…", dim: true, press: () => { acted.push("widgets"); } },
    ]);
    const menu = h.body.kids[h.body.kids.length - 1];
    assert.equal(menu.dataset.rowsMenu, "1"); assert.equal(menu.dataset.tagMenu, "1", "the tag menu's closers close it too");
    let rows = menu.kids;
    assert.deepEqual(rows.map(label), ["Lock the tabs in place", "Tab widgets…"]);
    assert.equal(rows[0].attrs["aria-checked"], "false"); assert.equal(rows[0].title, "Lock the tabs in place: no drag or move until clicked again");
    assert.equal(rows[0].tabIndex, 0, "a row takes focus");
    assert.equal(h.focused(), rows[0], "the first row is focused on open: Enter on the gear, then Enter on the row, is the whole path");
    rows[0].handlers.keydown({ key: "Enter", preventDefault() {}, stopPropagation() {} });
    assert.equal(locked, true, "Enter pressed the switch");
    assert.equal(menu.removed, undefined, "a switch keeps the menu open");
    rows = menu.kids;
    assert.equal(rows[0].attrs["aria-checked"], "true", "and repaints it with the ✓"); assert.equal(rows[0].title, "Tabs are locked in place: click to allow moving them again");
    assert.ok(rows[0].kids.some((k) => k.tag === "span" && label(k) === "✓"));
    assert.equal(h.focused(), rows[0], "the focus stays on the row across the repaint");
    assert.equal(rows[0].attrs.role, "menuitemcheckbox", "a row with a current value is a switch");
    assert.equal(rows[1].attrs.role, "menuitem", "a row without one is an action (round two, low 2)…");
    assert.equal(rows[1].attrs["aria-checked"], undefined, "…and carries no checked state");
    rows[1].handlers.click();
    assert.deepEqual(acted, ["widgets"]); assert.equal(menu.removed, true, "an action closes the menu");
    // Escape hands the focus back to the anchor
    h.mod.openRowsMenu(anchor, () => [{ label: "Lock the tabs in place", current: locked, press: () => false }]);
    const menu2 = h.body.kids[h.body.kids.length - 1];
    menu2.handlers.keydown({ key: "Escape", stopPropagation() {} });
    assert.equal(menu2.removed, true); assert.equal(h.focused(), anchor);
    // a press rebuilt the strip: the anchor is detached and a fresh gear stands in its place; Escape focuses the replacement, not the body
    const stale: any = h.mk("button"); stale.attrs.class = "tab-widgets-gear"; stale.className = "tab-widgets-gear"; stale.tagName = "BUTTON"; stale.isConnected = false;
    const fresh = h.mk("button"); fresh.attrs.class = "tab-widgets-gear";
    (globalThis as any).document.querySelector = (sel: string) => (sel === "button.tab-widgets-gear" ? fresh : null);
    h.mod.openRowsMenu(stale, () => [{ label: "Lock the tabs in place", current: locked, press: () => false }]);
    const menu3 = h.body.kids[h.body.kids.length - 1];
    menu3.handlers.keydown({ key: "Escape", stopPropagation() {} });
    assert.equal(menu3.removed, true); assert.equal(h.focused(), fresh, "Escape after a rebuild hands the focus to the live gear, not the detached one");
  } finally { h.mod.closeTagMenu(); h.restore(); }
});

test("the shared rows menu is the tag menu's card and ✓-row grammar, stated once in tag-menu.ts", () => {
  assert.match(TAGMENU, /export function openRowsMenu\(anchor: HTMLElement, rows: \(\) => RowsMenuRow\[\]\): void \{/);
  assert.match(TAGMENU, /if \(anchor\.isConnected !== false\) return anchor;/, "Escape refocuses the anchor's live replacement after the strip rebuilt");
  assert.match(TAGMENU, /closeTagMenu\(\); liveAnchor\(\)\?\.focus\(\); \}/);
  assert.match(TAGMENU, /menu\.dataset\.rowsMenu = "1"; menu\.dataset\.tagMenu = "1";/);
  assert.equal((TAGMENU.match(/background:var\(--check-bg, #1EA1EB\);color:#fff;border-radius:50%;width:13px;height:13px;font-size:9px;/g) || []).length, 2, "the ✓ badge, the tag menu's and the rows menu's, one text");
});

test("the gear's title names the widgets row only where a settings gear can be reached (round two, low 1)", () => {
  assert.match(RENDER, /gear\.title = settingsReachable \? "Tab strip: lock, widgets…" : "Tab strip: lock";/);
  assert.doesNotMatch(RENDER, /gear\.title = "Tab strip: lock, widgets…";/);
});
