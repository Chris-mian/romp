// A postal card shows an interaction-TYPE chip parsed from the message's leading intent token. There are
// THREE top-level categories (the user 2026-06-17): delegation / coordination / question. Legacy lead-words
// fold in (HANDOFF + ASK → delegation, FYI → coordination, Q → question); FYI is no longer its own chip.
// Source-level pin (no jsdom for the chat renderer).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("intent token → ONE of three categories: delegation / coordination / question", () => {
  assert.match(RENDER, /function postalIntent/);
  assert.match(RENDER, /DELEGATE: \{ label: "delegation", cls: "delegate" \}/);
  assert.match(RENDER, /HANDOFF: \{ label: "delegation"/);        // legacy term folds into delegation
  assert.match(RENDER, /ASK: \{ label: "delegation"/);            // legacy "do this" → delegation
  assert.match(RENDER, /COORDINATE: \{ label: "coordination", cls: "coordinate" \}/);
  assert.match(RENDER, /FYI: \{ label: "coordination", cls: "coordinate" \}/);  // FYI folds into coordination, not its own chip
  assert.match(RENDER, /QUESTION: \{ label: "question", cls: "question" \}/);
  assert.match(RENDER, /Q: \{ label: "question"/);                // legacy → question
  assert.doesNotMatch(RENDER, /label: "FYI"/);                    // FYI is no longer its own category
  // parses the leading token, tolerating a markdown-bold wrapper (**QUESTION:**)
  assert.match(RENDER, /\^\\s\*\\\*\{0,2\}\(\[A-Za-z\]\{1,12\}\)/);
});

test("the chip is rendered on the postal head and styled per type (three classes only)", () => {
  assert.match(RENDER, /el\("span", "postal-intent postal-intent-" \+ intent\.cls\)/);
  assert.match(CSS, /\.postal-intent \{/);
  assert.match(CSS, /\.postal-intent-delegate \{/);
  assert.match(CSS, /\.postal-intent-coordinate \{/);
  assert.match(CSS, /\.postal-intent-question \{/);
  assert.doesNotMatch(CSS, /\.postal-intent-fyi \{/);    // FYI chip class is gone
});
