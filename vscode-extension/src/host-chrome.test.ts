// Host-side chrome pins: the editor-font zoom reaches every webview surface,
// and the feed skeleton carries the #feed-foot dock (without it feed.js
// appends its controls to document.body as unstyled full-size buttons — the
// "big buttons" regression, the user 2026-07-13).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { FEED_BODY, FLEET_BODY, TIMELINE_BODY } from "./page-skeleton";

const SRC = fs.readFileSync(path.join(process.cwd(), "src", "extension.ts"), "utf8");

test("every webview builder applies the editor-font zoom", () => {
  const hits = SRC.match(/\$\{zoomStyle\(\)\}/g) || [];
  assert.equal(hits.length, 4, "chat, feed, fleet, and timeline builders must all scale");
  assert.ok(SRC.includes("editor\").get<number>(\"fontSize\")"), "zoom must track editor.fontSize");
});

test("zoom never shrinks below the designed size and re-renders on font changes", () => {
  assert.ok(SRC.includes("Math.max(1, Math.min(2,"), "zoom clamps to [1, 2]");
  assert.ok(SRC.includes('affectsConfiguration("editor.fontSize")'), "font changes must re-render the webviews");
});

test("the feed skeleton docks #feed-foot so feed.js controls land styled", () => {
  assert.ok(FEED_BODY.includes('id="feed-foot"'));
});

test("fleet/timeline skeletons keep their containers", () => {
  assert.ok(FLEET_BODY.includes('id="fleet-foot"'));
  assert.ok(TIMELINE_BODY.includes('id="host"'));
});

test("the romp strip: both builders opt in, chat gets the kernel origin, feed wins visibility", () => {
  const flags = SRC.match(/window\.__rompShowStrip=true/g) || [];
  assert.equal(flags.length, 2, "chat AND feed builders must opt into the strip");
  const stripLinks = SRC.match(/"strip\.css"/g) || [];
  assert.equal(stripLinks.length, 2, "chat AND feed builders must link strip.css");
  assert.ok(SRC.includes('m.type === "openPane"'), "the strips' quick-opens must reach the host");
  assert.ok(SRC.includes('{ type: "stripShow", show: !(feedPanel && feedPanel.visible) }'),
    "feed-over-chat: the chat strip hides while the feed panel is visible");
  const paneBroadcasts = SRC.match(/type: "stripPanes"/g) || [];
  assert.ok(paneBroadcasts.length >= 1, "the host must broadcast the hidden-pane set to the strips");
  assert.ok(SRC.includes("openFleetPanel(true, chatCol)"),
    "the launcher tabs Outline into the chat's group (the user 2026-07-13)");
  // The launcher is PURELY idempotent (the user 2026-07-14): re-clicking it
  // re-reveals the surfaces and must never raise the add-session picker.
  const launcher = SRC.slice(SRC.indexOf('registerCommand("rompChat.open"'), SRC.indexOf('registerCommand("rompChat.openFeed"'));
  assert.ok(launcher.length > 0, "found the rompChat.open registration");
  assert.ok(!launcher.includes("openPicker"), "the launcher must not post openPicker on re-click");
  const gearLinks = SRC.match(/"gear\.css"/g) || [];
  assert.equal(gearLinks.length, 2, "chat AND feed builders must link the gear stylesheet (local modal)");
});

test("the top-right swirl opens romp; the menu lives on the status-bar item", () => {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const pkg = JSON.parse(fs.readFileSync(path.join(process.cwd(), "package.json"), "utf8"));
  const et = pkg.contributes.menus["editor/title"];
  assert.equal(et[0].command, "rompChat.open", "the editor-title button is the plain launcher again");
  assert.ok(SRC.includes('statusItem.command = "rompChat.menu"'), "the status-bar item keeps the menu");
});
