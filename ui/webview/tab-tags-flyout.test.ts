// The chat-tab context menu's Tags flyout opens on HOVER-INTENT and carries Configure tags…
// (T163, the user 2026-08-28: hovering down to Tags should open the submenu without another
// click, and it should have a thing that goes into the configure-tags dialog). Source pins; the
// hover/tolerance behavior is also driven headless over the built bundle (task harness).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const at = RENDER.indexOf('const tagsItem = el("div", "ctx-item ctx-item-toggle ctx-item-tags");');
const block = RENDER.slice(at, RENDER.indexOf('menu.appendChild(tagsItem);', at));

// the ONE flyout gesture (T380): wireFlyout, declared beside the menu builder, wires Tags and Billing alike
const WIRE = RENDER.slice(RENDER.indexOf("function wireFlyout("), RENDER.indexOf("\n}\n", RENDER.indexOf("function wireFlyout(")));

test("hover-intent opens the flyout: the feed's 120ms, click still instant, hover never steals focus (the one gesture, wireFlyout)", () => {
  assert.match(RENDER, /const HOVER_INTENT_MS = 120;\nfunction wireFlyout\(menu: HTMLElement, item: HTMLElement, sel: string, open: \(byClick: boolean\) => HTMLElement \| null\): void \{/);
  assert.match(block, /wireFlyout\(menu, tagsItem, "\.ctx-sub-tags", openTagsFly\);/, "Tags rides the shared gesture");
  assert.match(WIRE, /item\.addEventListener\("pointerenter", \(\) => \{/);
  assert.match(WIRE, /openT = window\.setTimeout\(\(\) => \{ openT = null; openNow\(false\); \}, HOVER_INTENT_MS\);/,
    "hover opens WITHOUT focusing the input — a graze must not grab the keyboard (open(false))");
  assert.match(WIRE, /openNow\(true\);/, "click opens instantly and may focus");
  assert.match(WIRE, /cancel\(\);\s*\n\s*const fly = menu\.querySelector\(sel\);\s*\n\s*if \(fly\) \{ fly\.remove\(\); return; \}/,
    "a click cancels any pending hover intent before acting; a second click folds the flyout");
  assert.match(block, /if \(focusInput\) \(sub\.querySelector\("\.ctx-tag-input"\) as HTMLInputElement \| null\)\?\.focus\(\);/, "the click's focus is the Tags builder's own");
  // Billing wears the same gesture (T380, the user 2026-09-12): hovering the row opens its flyout, no click needed
  assert.match(RENDER, /wireFlyout\(menu, item, "\.ctx-sub-billing", \(\) => openBillingFly\(\)\);/);
  assert.doesNotMatch(RENDER, /hoverOpenT|hoverCloseT|cancelHoverTimers|armHoverClose/, "the inline Tags copy of the gesture is gone: one definition");
});

test("diagonal tolerance: entering either surface cancels the close; leaving both closes", () => {
  assert.match(WIRE, /fly\.addEventListener\("pointerenter", cancel\);/);
  assert.match(WIRE, /fly\.addEventListener\("pointerleave", armClose\);/);
  assert.match(WIRE, /item\.addEventListener\("pointerleave", armClose\);/);
  assert.match(WIRE, /closeT = window\.setTimeout\(\(\) => \{ closeT = null; menu\.querySelector\(sel\)\?\.remove\(\); \}, HOVER_INTENT_MS\);/, "the close is armed on leave with the same tolerance window");
  assert.match(WIRE, /if \(fly && !fly\.dataset\.flyWired\)/, "the flyout's own tolerance listeners are wired once per flyout node");
  assert.doesNotMatch(WIRE, /window\.addEventListener/, "no window listener: the harness slices count them");
});

test("the flyouts' placement (T380 review, one helper since T387): prefer right, fall left with room, else drop below the row inside the viewport", () => {
  const PLACE = RENDER.slice(RENDER.indexOf("function placeFlyBeside("), RENDER.indexOf("\n}\n", RENDER.indexOf("function placeFlyBeside(")));
  assert.match(PLACE, /if \(ir\.right \+ 2 \+ sr\.width <= window\.innerWidth - 8\) left = Math\.round\(ir\.right \+ 2\);/, "prefer right");
  assert.match(PLACE, /else if \(ir\.left - 2 - sr\.width >= 8\) left = Math\.round\(ir\.left\) - sr\.width - 2;/, "fall left only with room");
  // no room either side: below the row when it fits, else above the row's top, and only then clamped (round 3: a short
  // window's clamp pulled the drop-below back over the row)
  assert.match(PLACE, /left = Math\.max\(8, Math\.min\(Math\.round\(ir\.left\), window\.innerWidth - sr\.width - 8\)\);/, "clamped inside the viewport horizontally");
  assert.match(PLACE, /if \(ir\.bottom \+ 2 \+ sr\.height <= window\.innerHeight - 4\) top = ir\.bottom \+ 2;/, "below the row when it fits");
  assert.match(PLACE, /else if \(ir\.top - 2 - sr\.height >= 0\) top = ir\.top - 2 - sr\.height;/, "else above the row's top");
  assert.match(PLACE, /else top = Math\.max\(0, Math\.min\(ir\.top, window\.innerHeight - sr\.height - 4\)\);/, "only when neither fits, clamped");
  assert.doesNotMatch(PLACE, /Math\.max\(0, Math\.min\(ir\.right \+ 2, window\.innerWidth - sr\.width - 4\)\)/, "the old slide-over-the-row rule is gone");
  const BILL = RENDER.slice(RENDER.indexOf("const openBillingFly = (): HTMLElement | null => {"), RENDER.indexOf('wireFlyout(menu, item, ".ctx-sub-billing"'));
  assert.match(BILL, /placeFlyBeside\(item, sub\);/, "the Billing flyout rides the helper…");
  assert.match(BILL, /placeFlyBeside\(setDef, d\);/, "…and so does its nested default submenu (T387)");
  assert.match(BILL, /if \(choices\.length > 1 && avail\.default && avail\.defaultExplicit !== undefined\) \{/, "an older kernel that takes no auto and marks no default gets no Set default billing entry");
  assert.match(BILL, /if \(explicit\) \{[\s\S]*?auto\.textContent = "Automatic";/, "the way back to the helper rule, only while an explicit default stands");
  // the Default flyout offers every pick the list above does, a stored login among them (the user 2026-09-14; the kernel's
  // scoped arm takes "login:<id>" as the machine default since then)
  assert.doesNotMatch(BILL, /defaultChoices/, "no filtered default list");
  assert.match(BILL, /for \(const c of choices\) \{\s*\n\s*const cur = explicit && avail\.default === c\.value;/, "the flyout lists the same choices");
  const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");
  assert.match(CSS, /\.ctx-sub-billing, \.ctx-sub-default \{ max-width: calc\(100vw - 16px\); \}/, "both levels take their longest label's width, the window the one bound (the user 2026-09-14)");
  assert.doesNotMatch(CSS, /\.ctx-sub-head/, "the group head and its note are gone (T387)");
});

test("expansion follows the standing side rule and the caret faces right", () => {
  assert.match(block, /if \(ir\.right \+ 2 \+ sr\.width <= window\.innerWidth - 8\) sub\.style\.left = Math\.round\(ir\.right \+ 2\) \+ "px";/);
  assert.match(block, /else sub\.style\.left = Math\.max\(8, Math\.round\(ir\.left\) - sr\.width - 2\) \+ "px";/,
    "prefer right, FALL LEFT on clip — never slide over the row");
  assert.match(block, /caret\.textContent = "▸";/);
});

test("Configure tags… sits at the foot behind the divider and rides the ONE dialog route", () => {
  const cfgAt = block.indexOf('cfgL.textContent = "Configure tags…";');
  assert.ok(cfgAt > 0);
  assert.match(block, /sub\.appendChild\(el\("div", "ctx-sep"\)\);\s*\n\s*const cfg = el\("div", "ctx-item ctx-item-configtags"\);/);
  assert.match(block, /vscodeApi\?\.postMessage\(\{ type: "openTagsDialog" \}\);/,
    "the same route the tag-lens menus use — one dialog, no copy");
  assert.match(block, /e2\.stopPropagation\(\); dismissTabMenu\(\);/, "opening the dialog closes the menu");
});
