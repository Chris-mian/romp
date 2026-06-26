// The chat tab's right-click menu gained the timeline lane's per-session toggles (the user 2026-06-26): Feed
// (hideFromFeed) and Mail (postalServiceOff), each an icon + a label + a faint "what it does" sub-line. The
// toggle posts the same setSessionFlag the timeline sends. Source pins (no jsdom for the chat render).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("the flags ride on the session and are carried across pushes", () => {
  assert.match(SRC, /hideFromFeed\?: boolean; postalServiceOff\?: boolean;/);
  assert.match(SRC, /hideFromFeed: \("hideFromFeed" in msg\) \? !!msg\.hideFromFeed/);
  assert.match(SRC, /postalServiceOff: \("postalServiceOff" in msg\) \? !!msg\.postalServiceOff/);
});

test("setSessionFlag posts the same message the timeline lane toggles send, and updates locally", () => {
  assert.match(SRC, /function setSessionFlag\(id: string, flag: "hideFromFeed" \| "postalServiceOff", value: boolean\)/);
  assert.match(SRC, /vscodeApi\.postMessage\(\{ type: "setSessionFlag", id, flag, value \}\)/);
});

test("the tab menu adds Feed + Mail toggle items with state-dependent labels", () => {
  assert.match(SRC, /toggle\("feed", offFeed,\s*offFeed \? "Show in feed" : "Hide from feed"/);
  assert.match(SRC, /setSessionFlag\(id, "hideFromFeed", !offFeed\)/);
  assert.match(SRC, /toggle\("mail", offMail,\s*offMail \? "Rejoin mail" : "Mute mail"/);
  assert.match(SRC, /setSessionFlag\(id, "postalServiceOff", !offMail\)/);
});

test("each toggle item carries an icon (slashed when off) and a sub-description", () => {
  assert.match(SRC, /function ctxIcon\(kind: "feed" \| "mail", off: boolean\)/);
  assert.match(SRC, /off \? '<line /);   // slash when the flag is off
  assert.match(SRC, /ctx-item-sub/);
  assert.match(CSS, /\.ctx-item-toggle \{ display: flex;/);
  assert.match(CSS, /\.ctx-item-toggle \.ctx-icon\.off \{ color: var\(--dim\); \}/);
});
