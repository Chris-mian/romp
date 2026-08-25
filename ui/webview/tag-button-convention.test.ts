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
import { TAG_BTN_GRAY, TAG_BTN_ACCENT } from "./tag-menu";

const ui = (...p: string[]) => fs.readFileSync(path.resolve(process.cwd(), "..", "ui", ...p), "utf8");
const RENDER = ui("webview", "render.ts");
const FLEET = ui("webview", "fleet.ts");
const FEED = ui("webview", "feed.ts");
const FEEDCSS = ui("webview", "feed.css");
const TL = ui("romp-timeline-view.js");

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

test("timeline spacing grew (the user 2026-08-25: the corner controls were cramped)", () => {
  assert.match(TL, /const ICONW = 22;/, "wider button slots");
  assert.match(TL, /const PADH = 7, GAP = 9;/, "more air between the line's parts");
  assert.match(TL, /if \(hidden > 0\)/, "overflow chips collapse into a +N, one click from the menu");
});
