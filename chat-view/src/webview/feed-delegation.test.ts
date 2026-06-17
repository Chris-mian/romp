// The feed UI uses the term "delegation", not "handoff" — the backend's courier verdict is
// DELEGATING and the user wants one term repo-wide (rompinfra, the user 2026-06-16). User-facing text
// + CSS class names are renamed; the internal kind data VALUE ("handoff") is intentionally left as-is
// (not user-facing, and changing it would touch the data contract). Source-level pin.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "feed.css"), "utf8");

test("user-facing provenance text says 'delegated', not 'handed off'", () => {
  assert.match(FEED, /delegated from another session/);
  assert.doesNotMatch(FEED, /handed off from another session/);
});

test("the lane + its rows use fask-delegation* classes, defined in feed.css", () => {
  assert.match(FEED, /"fask-delegations"/);
  assert.match(FEED, /"fask-delegation-line"/);
  assert.match(FEED, /"fask-delegation"/);
  assert.doesNotMatch(FEED, /"fask-handoff/);           // no stale class applications
  assert.match(CSS, /\.fask-delegations \{/);
  assert.match(CSS, /\.fask-delegation \{/);
  assert.doesNotMatch(CSS, /\.fask-handoff/);           // no stale rules
});

test("the kind data VALUE stays 'handoff' (not user-facing; keeps the node logic stable)", () => {
  assert.match(FEED, /kind: "ask" \| "handoff"/);
  assert.match(FEED, /n\.kind !== "handoff"/);
});

test("the name row keeps the session name on one line and pushes '↪ from' to the right edge", () => {
  // the user 2026-06-16: the name was wrapping mid-word while the origin crowded it; instead the row
  // fills its width, the name stays one line (ellipsis only if truly too long), origin goes right.
  assert.match(CSS, /\.fask-id \{[^}]*flex: 1 1 auto/);
  assert.match(CSS, /\.fask-id \.fname \{[^}]*white-space: nowrap/);
  assert.match(CSS, /\.fask-origin \{[^}]*margin-left: auto/);
  assert.match(CSS, /\.fask-origin \{[^}]*white-space: nowrap/);
});

test("a delegation card's title anchors on 'work' (not 'prompt') so it doesn't jump to an unrelated user msg", () => {
  // a delegation card has no originating user prompt; anchor:"prompt" landed on the nearest user turn
  // in time (wrong). origin cards anchor on "work" → land where the delegation was processed (rompinfra).
  assert.match(FEED, /const titleAnchor = it\.origin \? "work" : "prompt"/);
  assert.match(FEED, /anchor: titleAnchor/);
});
