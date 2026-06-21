// Dead sessions strike their name in the feed (the user 2026-06-13: a dead agent's name should be
// struck through wherever it appears — feed list cards AND the detail modal). The feed has no jsdom
// harness, so — like feed-focus.test.ts — these pin the behaviour at the source level. The list cards
// already carry a `.dead`/`.live` class (set from the data-model `live` field); the modal reuses one
// shared agent element, so it must TOGGLE the class per target.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

test("a dead session's feed-card name is struck through", () => {
  assert.match(CSS, /\.fitem\.dead \.fname \{[^}]*text-decoration: line-through/);
});

test("the modal's agent name is struck through for a dead session", () => {
  assert.match(CSS, /\.feed-modal-agent\.dead \{[^}]*text-decoration: line-through/);
  // ask / group / standalone-deliverable modals carry the strike when their session is dead
  assert.match(FEED, /agent\.classList\.toggle\("dead", !grp\.live\)/);
  assert.match(FEED, /agent\.classList\.toggle\("dead", !it\.live\)/);
  assert.match(FEED, /agent\.classList\.toggle\("dead", !fitem\.live\)/);
});
