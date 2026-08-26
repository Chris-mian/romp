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

test("menus wear ONE vocabulary (CLAUDE.md): --radius-menu 6px + --shadow-menu on every dropdown", () => {
  // .meta-menu and .tab-tip had drifted onto 0 4px 16px/0.45; .slash-pop onto 8px + 0 6px 22px;
  // .feed-sessmenu onto 0 6px 24px. All resolve through the tokens now. .tab-tip keeps its mono
  // (a statusline tooltip, not a dropdown); .meta-menu joins the menus' sans per the spec.
  assert.match(CHAT, /--radius-menu: 6px;\n  --shadow-menu: 0 4px 12px rgba\(0, 0, 0, 0\.35\);/);
  assert.match(FEED, /--radius-menu: 6px;/);
  assert.match(FEED, /--shadow-menu: 0 4px 12px rgba\(0, 0, 0, 0\.35\);/);
  for (const sel of [".ctx-menu", ".meta-menu", ".tab-tip", ".slash-pop"]) {
    const at = CHAT.indexOf(sel + " {");
    const rule = CHAT.slice(at, CHAT.indexOf("}", at));
    assert.ok(rule.includes("var(--radius-menu)"), sel + " radius through the token");
    assert.ok(rule.includes("var(--shadow-menu)"), sel + " shadow through the token");
  }
  for (const sel of [".ctx-menu", ".feed-sessmenu"]) {
    const at = FEED.indexOf(sel + " {");
    const rule = FEED.slice(at, FEED.indexOf("}", at));
    assert.ok(rule.includes("var(--radius-menu)"), sel + " radius through the token (feed)");
    assert.ok(rule.includes("var(--shadow-menu)"), sel + " shadow through the token (feed)");
  }
  // the retired drift shadows appear nowhere in the sheets
  for (const [name, css] of [["styles.css", CHAT], ["feed.css", FEED]] as const) {
    assert.doesNotMatch(css, /0 4px 16px rgba\(0, 0, 0, 0\.45\)|0 6px 2[24]px rgba\(0, 0, 0, 0\.45\)/, name);
  }
  assert.match(CHAT, /\.meta-menu \{[^}]*font-family: var\(--sans\)/s, "the meta menus read in the menus' sans");
});

test("ONE accent wash: every selected/hovered accent chrome resolves through --accent-wash at 0.12", () => {
  // 0.10 and 0.14 washes had drifted in beside the dominant 0.12 (three alphas for one meaning);
  // the token is declared in both self-sufficient :roots, and no bare wash literal remains in the
  // sheets. The CodeMirror .cm-selectionMatch (editor-chunk.ts) keeps 0.14 — a text-match marker,
  // not chrome — and shell-page inline CSS keeps unified 0.12 literals (no :root to share).
  assert.match(CHAT, /--accent-wash: rgba\(156, 210, 255, 0\.12\);/);
  assert.match(FEED, /--accent-wash: rgba\(156, 210, 255, 0\.12\);/);
  for (const [name, css] of [["styles.css", CHAT], ["feed.css", FEED]] as const) {
    const bare = css.replace(/--accent-wash: rgba\(156, 210, 255, 0\.12\);/g, "");
    assert.doesNotMatch(bare, /rgba\(156, ?210, ?255, ?0?\.1[024]\)/, name + " has no bare wash literal");
  }
  // the selected fileview toggle wears the app's ONE selected language in BOTH sheets: wash at
  // rest, reverse-highlight on hover (styles.css's copy had drifted to a wash hover, 2026-08-25)
  for (const [name, css] of [["styles.css", CHAT], ["feed.css", FEED]] as const) {
    assert.match(css, /\.fileview-btn\.on:hover \{ background: var\(--accent\); color: var\(--accent-fg\); border-color: var\(--accent\); \}/,
      name + " reverse-highlights the selected viewer toggle");
  }
});
