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
  assert.match(RENDER, /function postalServiceIntent/);
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

test("the DECLARED kind (ev.intent) drives the chip; the body-token parse is only a legacy fallback", () => {
  // send_message moved the kind from a leading body token ("DELEGATE: …") to an explicit `kind` param
  // (the user 2026-07-15: the chip vanished). The kernel surfaces it as ev.intent; the renderer must
  // PREFER it (mapped through POSTAL_INTENTS), falling back to the body parse only when it's absent.
  assert.match(RENDER, /ev\.intent && POSTAL_INTENTS\[ev\.intent\.toUpperCase\(\)\]/);
  assert.match(RENDER, /\|\| postalServiceIntent\(ev\.body\)/);
  assert.match(RENDER, /intent\?: string;/);   // the event carries the declared kind
});

test("the chip is rendered on the postal head and styled per type (three classes only)", () => {
  assert.match(RENDER, /el\("span", "postal-service-intent postal-service-intent-" \+ intent\.cls\)/);
  assert.match(CSS, /\.postal-service-intent \{/);
  assert.match(CSS, /\.postal-service-intent-delegate \{/);
  assert.match(CSS, /\.postal-service-intent-coordinate \{/);
  assert.match(CSS, /\.postal-service-intent-question \{/);
  assert.doesNotMatch(CSS, /\.postal-service-intent-fyi \{/);    // FYI chip class is gone
});
