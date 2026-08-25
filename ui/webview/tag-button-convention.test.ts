// THE TAG BUTTON CONVENTION (the user 2026-08-25): at rest (All) the tag icon is GRAY and stands
// alone; narrowed, it wears the ACCENT and the chips of everything selected — each tag in its
// color, the no-tags bucket as its own chip — identical across the timeline, chat, outline, and
// feed mounts. Equality is COMPUTED, not class-shared (the 678 lesson): the executed model is one
// function; the color constants are asserted equal across every home that states them.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { lensChips } from "./tag-lens";
import { TAG_BTN_GRAY, TAG_BTN_ACCENT, TAG_BTN_BORDER, TAG_BTN_WASH } from "./tag-menu";

const ui = (...p: string[]) => fs.readFileSync(path.resolve(process.cwd(), "..", "ui", ...p), "utf8");
const RENDER = ui("webview", "render.ts");
const FLEET = ui("webview", "fleet.ts");
const FEED = ui("webview", "feed.ts");
const FEEDCSS = ui("webview", "feed.css");
const TL = ui("romp-timeline-view.js");
const TAGMENU = ui("webview", "tag-menu.ts");

const UNIONS = [
  { name: "infra", color: "#DD42FF", members: [] },
  { name: "workers", color: "#4EC9B0", members: [] },
];

test("executed: lensChips — All bare; narrowed = every selection incl. the no-tags chip", () => {
  assert.deepEqual(lensChips({ all: true }, UNIONS as never), [], "All → the button stands alone");
  assert.deepEqual(lensChips({ tags: ["infra"] }, UNIONS as never),
    [{ label: "infra", color: "#DD42FF", pick: { tag: "infra" } }]);
  assert.deepEqual(lensChips({ none: true, tags: ["workers"] }, UNIONS as never),
    [{ label: "workers", color: "#4EC9B0", pick: { tag: "workers" } },
     { label: "no tags", color: null, pick: "none" }],
    "the no-tags bucket is its own chip, last");
});

test("cross-mount computed equality: one gray, one accent, everywhere", () => {
  assert.equal(TAG_BTN_GRAY, "#9aa0a6");
  assert.equal(TAG_BTN_ACCENT, "#9cd2ff");
  // the timeline inlines the same values (it loads no modules — Obsidian host)
  assert.match(TL, /const MODEL_FG = '#9aa0a6';/, "the timeline's gray IS the convention gray");
  assert.match(TL, /const tagIconCol = active \? '#9cd2ff' : MODEL_FG;/, "gray at rest, accent narrowed");
  // the feed's class mode resolves to the same accent (its own :root states the literal)
  assert.match(FEEDCSS, /--accent: #9cd2ff;/, "feed.css's accent equals the convention accent");
  assert.match(FEED, /"class"\);/, "the feed mounts in class mode — its .on carries that accent");
});

test("every JS mount renders through the ONE convention function", () => {
  for (const [name, src] of [["render", RENDER], ["fleet", FLEET], ["feed", FEED]] as const)
    assert.match(src, /syncTagFilter\(/, name + " mounts the shared renderer");
  assert.match(RENDER, /tagBtn\.style\.alignSelf = "center";/,
    "the chat button centers against the + tab's box (the user 2026-08-25 — it sat high)");
});

test("THE BUTTON OUTLINE (the user 2026-08-25, round two): every mount wears the feed word-button's box", () => {
  // the box, by value: 1px hairline in the feed's --card-border, 6px radius, the footer's 1px 9px
  // padding; narrowed = accent border + the .on wash. COMPUTED equality (the 678 lesson): the feed
  // states these through classes, the other mounts through the shared literals — assert the values
  // equal, never share the class.
  const flat = FEEDCSS.replace(/\s+/g, "");
  assert.equal(TAG_BTN_BORDER, "rgba(255,255,255,0.10)");
  assert.equal(TAG_BTN_WASH, "rgba(156,210,255,0.12)");
  assert.ok(flat.includes("--card-border:rgba(255,255,255,0.10)"), "the feed's hairline is the shared border literal");
  assert.ok(flat.includes("background:rgba(156,210,255,0.12)"), "the feed .on's wash is the shared wash literal");
  assert.ok(flat.includes("border-radius:6px"), "the feed's radius");
  assert.ok(flat.includes("#feed-foot.fdismiss{font-size:10.5px;padding:1px9px"), "the feed footer instance's padding");
  // the chat/outline builder states the same box inline (inline beats classes, so it must carry it itself)
  assert.match(TAGMENU, /border:1px solid " \+ TAG_BTN_BORDER \+ ";"\s*\n\s*\+ "border-radius:6px;padding:1px 9px;/,
    "tagMenuButton wears the box by the shared literals");
  assert.match(TAGMENU, /btn\.style\.borderColor = narrowed \? TAG_BTN_ACCENT : TAG_BTN_BORDER;/,
    "narrowed = accent border, at rest the hairline");
  assert.match(TAGMENU, /btn\.style\.background = narrowed \? TAG_BTN_WASH : "transparent";/,
    "narrowed = the .on wash");
  // the timeline draws the same box in svg terms, and the BOX is the hit target (the bare 16x16
  // glyph pad read unclickable — the user 2026-08-25)
  assert.match(TL, /const box = el\('rect', \{ x: PADL \+ dx, y: y - 13, width: BTNW, height: BTNH, rx: 6,/,
    "the corner buttons draw the outlined box as their hit rect");
  assert.match(TL, /stroke: narrowed \? '#9cd2ff' : 'rgba\(255,255,255,0\.10\)', 'stroke-width': 1 \}\);/,
    "same hairline at rest, same accent narrowed");
  assert.match(TL, /fill: narrowed \? 'rgba\(156,210,255,0\.12\)' : 'transparent',/,
    "same wash narrowed, transparent (still hit-catching) at rest");
});

test("timeline spacing grew (the user 2026-08-25: the corner controls were cramped)", () => {
  assert.match(TL, /const BTNW = 32, BTNH = 18;/, "the outlined boxes replaced the bare icon slots (round two)");
  assert.match(TL, /const PADH = 7, GAP = 9;/, "more air between the line's parts");
  assert.match(TL, /if \(hidden > 0\)/, "overflow chips collapse into a +N, one click from the menu");
});
