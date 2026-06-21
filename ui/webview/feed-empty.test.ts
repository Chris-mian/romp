// Inbox-zero empty state (the user 2026-06-13): when every card is cleared the feed shows the romp
// otter picture instead of words (it replaced an earlier 🦫 emoji). The image is a CSS background so
// the relative url() resolves under /media in BOTH hosts — the browser (kernel serves /media) and VS
// Code (media/ is a localResourceRoot); an <img src> relative path would not resolve in the VS Code
// webview. No jsdom harness for the feed, so — like feed-focus.test.ts — pin it at the source level.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

test("the inbox-zero state shows the romp swirl logo, stretched to fill (no otters, no emoji)", () => {
  assert.match(CSS, /\.feed-empty \{[^}]*background-image: url\(\.\.\/media\/romp-swirl-square\.svg\)/);
  assert.match(CSS, /\.feed-empty \{[^}]*background-size: contain/);
  assert.doesNotMatch(CSS, /romp-otter/, "the otter image is gone");
  assert.doesNotMatch(FEED, /feed-empty"\); e\.textContent = "/, "the empty state must not set emoji/text on the logo");
  assert.match(FEED, /el\("div", "feed-empty"\)/);
});

test("the empty state stays accessible (role + aria-label, since a background image has no alt)", () => {
  assert.match(FEED, /e\.setAttribute\("role", "img"\)/);
  assert.match(FEED, /e\.setAttribute\("aria-label", "inbox zero/);
});

test("the swirl logo ships in the served + packaged media dir; the otter is gone", () => {
  assert.ok(fs.existsSync(path.resolve(process.cwd(), "media", "romp-swirl-square.svg")), "media/romp-swirl-square.svg must exist (kernel serves /media; .vscodeignore keeps media/)");
  assert.ok(!fs.existsSync(path.resolve(process.cwd(), "media", "romp-otter.png")), "the otter image was deleted (the user 2026-06-15)");
});
