// The UI's color/metric vocabulary — pins the dedupes of 2026-08-26 so near-twin values cannot
// creep back in. Each block names ONE vocabulary decision and the drift it retired; a failure here
// means a new rule re-introduced a value the vocabulary already names (use the token / the named
// hex instead). CLAUDE.md Design is the spec these instances serve.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const read = (f: string) => fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", f), "utf8");
const CHAT = read("styles.css");
const FEED = read("feed.css");
const GEAR = read("gear.css");
const STRIP = read("strip.css");
const SHORTCUTS = read("shortcuts-modal.ts");

test("--warn is a real token, one heads-up amber: defined in BOTH self-sufficient :roots", () => {
  // it was a phantom for months — referenced with fallbacks, defined nowhere — while two more
  // ambers one hex digit apart (#e0a020, #e0b341) grew nine lines from each other in feed.css
  assert.match(CHAT, /--warn: #d7a23a;/);
  assert.match(FEED, /--warn: #d7a23a;/);
  for (const [name, css] of [["styles.css", CHAT], ["feed.css", FEED]] as const) {
    assert.doesNotMatch(css, /#e0a020|#e0b341|#d29922/i, name + " uses var(--warn), not a near-twin amber");
  }
  assert.doesNotMatch(SHORTCUTS, /#d29922/, "the shortcuts dialog's conflict amber is the warn amber");
});

test("one elevated small-button gray (#2a2a2a) and one dropdown shadow alpha (#000000aa)", () => {
  // #2a2a2b differed from its sibling #2a2a2a by one digit across gear/strip; the two settings
  // dropdowns (colormap / session palette, 11 lines apart) wore #000000aa vs #00000088
  for (const [name, css] of [["gear.css", GEAR], ["strip.css", STRIP]] as const) {
    assert.doesNotMatch(css, /#2a2a2b/, name);
    assert.doesNotMatch(css, /#00000088/, name);
  }
});

test("gear.css accent chrome references var(--accent) — never a re-hardcoded bare hex (CLAUDE.md)", () => {
  assert.doesNotMatch(GEAR, /outline: 2px solid #9cd2ff/);
  assert.match(GEAR, /outline: 2px solid var\(--accent, #9cd2ff\)/);
});
