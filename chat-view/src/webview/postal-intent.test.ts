// A postal card shows an interaction-TYPE chip parsed from the message's leading intent token (the
// postal norms: DELEGATE / COORDINATE / ASK / Q / FYI / HANDOFF) — scannable in both the compact and
// expanded views (the user 2026-06-16). Source-level pin (no jsdom for the chat renderer).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "styles.css"), "utf8");

test("intent token → type: DELEGATE/HANDOFF=delegation, COORDINATE, ASK, Q, FYI", () => {
  assert.match(RENDER, /function postalIntent/);
  assert.match(RENDER, /DELEGATE: \{ label: "delegation"/);
  assert.match(RENDER, /HANDOFF: \{ label: "delegation"/);     // legacy term folds into delegation
  assert.match(RENDER, /COORDINATE: \{ label: "coordination"/);
  assert.match(RENDER, /FYI: \{ label: "FYI"/);
  // parses the leading token, tolerating a markdown-bold wrapper (**ASK:**)
  assert.match(RENDER, /\^\\s\*\\\*\{0,2\}\(\[A-Za-z\]\{1,12\}\)/);
});

test("the chip is rendered on the postal head and styled per type", () => {
  assert.match(RENDER, /el\("span", "postal-intent postal-intent-" \+ intent\.cls\)/);
  assert.match(CSS, /\.postal-intent \{/);
  assert.match(CSS, /\.postal-intent-delegate \{/);
  assert.match(CSS, /\.postal-intent-coordinate \{/);
  assert.match(CSS, /\.postal-intent-fyi \{/);
});
