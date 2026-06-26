// The gray "romp-injected" bubble (the user 2026-06-19): a message romp pasted into the pane (a feed
// nudge / follow-up) renders as a GRAY right-aligned bubble with a "↯ romp" tag — same spot as the blue
// user bubble, but clearly romp, not you. The renderer has no jsdom harness, so pin the wiring at source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("a user ChatEvent can carry a romp flag", () => {
  assert.match(RENDER, /kind: "user";[^}]*romp\?: boolean/);
});

test("a romp event renders the gray romp-bubble + a romp tag, NOT the blue or the note box", () => {
  assert.match(RENDER, /const romp = !!ev\.romp;/);
  // 'injected' (the neutral left note) excludes romp, so romp gets its own branch
  assert.match(RENDER, /const injected = !ev\.human && !romp;/);
  // the tag shows the romp swirl-glyph LOGO (not the old ↯ symbol) + "romp" (the user 2026-06-19)
  assert.match(RENDER, /el\("img", "romp-tag-logo"\)/);
  assert.match(RENDER, /logo\.src = "\/media\/romp-swirl-glyph\.svg"/);
  assert.match(RENDER, /createTextNode\("romp"\)/);
  assert.doesNotMatch(RENDER, /tag\.textContent = "↯ romp"/, "the ↯ placeholder is gone");
  assert.match(RENDER, /\(romp \? "romp-bubble" : injected \? "user-note" : "user-bubble"\)/);
  // its own gray rail dot
  assert.match(RENDER, /dot\(romp \? "romp" : injected \? "ring" : "user"\)/);
  assert.match(RENDER, /"green" \| "ring" \| "user" \| "red" \| "romp"/, "the dot helper knows the romp variant");
});

test("the swirl LOGO is gated on rompAuto (auto-nudge); the 'romp' tag stays on every romp bubble (the user 2026-06-23)", () => {
  assert.match(RENDER, /kind: "user";[^}]*rompAuto\?: boolean/);
  // the <img> logo appends ONLY inside the rompAuto branch; the "romp" textnode is OUTSIDE it (always shown)
  assert.match(RENDER, /if \(ev\.rompAuto\) \{[\s\S]*?el\("img", "romp-tag-logo"\)[\s\S]*?tag\.appendChild\(logo\);\s*\}\s*tag\.appendChild\(document\.createTextNode\("romp"\)\)/);
});

test("a postal card carries the romp swirl (postal is 'from romp' too — the user 2026-06-23)", () => {
  assert.match(RENDER, /el\("img", "postal-service-romp-logo"\)/);
  assert.match(RENDER, /rlogo\.src = "\/media\/romp-swirl-glyph\.svg"/);
  assert.match(CSS, /\.postal-service-romp-logo \{/);
});

test("the romp bubble is a gray, right-aligned bubble (inherits the non-injected right-align)", () => {
  // the turn carries 'romp' (no 'injected'), so .turn-user:not(.injected) right-aligns it
  assert.match(RENDER, /"turn turn-user" \+ \(romp \? " romp" : injected \? " injected" : ""\)/);
  assert.match(CSS, /\.romp-bubble \{[\s\S]*?background: rgba\(255, 255, 255, 0\.08\)/);
  assert.match(CSS, /\.romp-tag \{/);
  assert.match(CSS, /\.dot\.romp \{[^}]*background: var\(--dim\)/);
});
