// T390 (the user 2026-09-12): a session's name in a postal card's head is the NAME ITSELF, bold, in the session's identity
// colour, the way the awaiting fold names a peer (bg-await-peer): no chip box, no fill, in either theme. The pins over the
// postal head's builder and the sheet; the served postal lab (tests/test_postal_cards_served.py) measures the computed colour,
// the weight and the contrast on the card's ground in both themes, sweeps every palette colour over every card ground in both
// themes (the fold's high: the dark floor), and screenshots both.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");
const CARD = RENDER.slice(RENDER.indexOf("function renderPostalService("), RENDER.indexOf("\n}\n", RENDER.indexOf("function renderPostalService(")));

test("the postal head names both ends as bold text in the identity colour: no chip class anywhere in the chat", () => {
  assert.doesNotMatch(RENDER, /notice-src-chip/, "the chip class is gone from the builder");
  assert.doesNotMatch(CSS, /\.notice-src-chip\b/, "…and from the sheet");
  assert.match(CARD, /const peer = el\("span", "notice-src-end notice-src-peer"\);/);
  assert.match(CARD, /peer\.dataset\.name = ev\.peer;/, "the bare name for the working set");
  assert.match(CARD, /if \(ev\.color\) peer\.style\.setProperty\("--peer-bg", ev\.color\.bg\);/, "the identity colour rides the token; no chip foreground");
  assert.match(CARD, /makeSessionChip\(peer, ev\.peer\);\s*\n\s*setPeerDot\(peer, workingSet\.has\(ev\.peer\)\);/, "the click to the tab and the working dot stay");
  assert.match(CARD, /const self = el\("span", "notice-src-end notice-src-self"\);/);
  assert.match(CARD, /rail: ev\.color \? ev\.color\.bg : undefined,/, "the card's rail wash in the peer's colour stays");
});

test("the peer's host prefix is muted as the tab wears it; the own end's through hostNameNodes", () => {
  assert.doesNotMatch(RENDER, /peerNameNodes/, "one helper for a host-prefixed name: hostPartsNodes (the fold's low 3)");
  assert.match(CARD, /peer\.append\(\.\.\.hostPartsNodes\(ev\.peerHost, ev\.peer\)\);/);
  assert.match(CARD, /nm\.append\(\.\.\.hostNameNodes\(own\.name, ownId\)\);/);
  assert.match(CSS, /\.notice-src-end \.host-prefix \{ font-weight: 400; \}/, "the prefix keeps the prose weight beside the bold name");
});

test("the sheet: bold, inked from the identity colour at the theme's lightness, no fill; the collapsed own end is the one filled dot", () => {
  assert.match(CSS, /\.notice-src-end \{ letter-spacing: 0\.02em; text-transform: none; font-weight: 700;\s*\n\s*color: var\(--peer-bg, var\(--fg\)\);[^\n]*\n\s*color: oklch\(from var\(--peer-bg, var\(--fg\)\) var\(--peer-ink-l, l\) c h\); \}/,
    "the identity colour itself first, for an engine without relative colour syntax; then the inked colour (the fold's low 1)");
  const rule = CSS.slice(CSS.indexOf(".notice-src-end {"), CSS.indexOf("}", CSS.indexOf(".notice-src-end {")));
  assert.doesNotMatch(rule, /background|padding|border-radius/, "no chip box: no fill, padding or radius on the name");
  const dark = CSS.slice(CSS.indexOf(":root {"), CSS.indexOf("\n}", CSS.indexOf(":root {")));
  const light = CSS.slice(CSS.indexOf("body.theme-light {"), CSS.indexOf("\n}", CSS.indexOf("body.theme-light {")));
  assert.match(dark, /--peer-ink-l: max\(l, 0\.72\);/, "dark: the colour's own lightness, lifted to the floor the palette sweep set (the fold's high)");
  assert.match(light, /--peer-ink-l: 0\.46;/, "cream: deepened on its own hue, the kind words' rule");
  assert.match(CSS, /\.turn-postal-service \.notice-src-self \{ display: inline-block; width: 10px; height: 10px; padding: 0; border-radius: 50%; align-self: center; overflow: hidden;\s*\n\s*background: var\(--peer-bg, var\(--overlay-10\)\); \}/);
});

test("the working dot keys on the bare name, not the prefixed text", () => {
  const fn = RENDER.slice(RENDER.indexOf("function refreshPostalDots()"), RENDER.indexOf("\n}\n", RENDER.indexOf("function refreshPostalDots()")));
  assert.match(fn, /querySelectorAll\("\.notice-src-peer"\)/);
  assert.match(fn, /workingSet\.has\(\(p as HTMLElement\)\.dataset\.name \|\| \(p\.textContent \|\| ""\)\.trim\(\)\)/);
});
