// Feed card layout (the user 2026-06-14): the ask / standalone / group cards stack into THREE
// rows — title (full width), session name (own row), then a bottom row with the age on the left
// and the badges + Clear on the right. This frees the title and the (often long) session name to
// use the full card width instead of competing with the age/actions, and lets a long name wrap
// rather than overrun.
// No jsdom harness for the feed, so — like the other feed-*.test.ts — pin it at the source level.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "feed.css"), "utf8");

test("all three main cards build a row3 with the age (left) and actions (right)", () => {
  const row3s = FEED.match(/const row3 = el\("div", "fask-row3"\); row3\.append\(time, actions\)/g) || [];
  assert.equal(row3s.length, 3, "standalone + ask + group each get a row3");
  // the title row no longer carries the time in those builders (it moved to row3)
  assert.match(FEED, /row1\.append\(title\);/);
});

test("row3 + name-wrap are styled", () => {
  assert.match(CSS, /\.fask-row3 \{[^}]*display: flex/);
  assert.match(CSS, /\.fask-id \.fname \{[^}]*overflow-wrap: anywhere/, "a long session name wraps instead of overflowing");
});

test("the ⏸ blocked (permission/picker) badge is a rounded-rect pill outlined in its own red", () => {
  // mirrors the Clear button's chrome (.fdismiss) — a border + rounded corners + padding — but kept in
  // the badge's own red (the user 2026-06-16), so a live permission/picker block reads as a pill
  assert.match(CSS, /\.fask-blocked \{[^}]*border: 1px solid #c0392b/);
  assert.match(CSS, /\.fask-blocked \{[^}]*border-radius:/);
  assert.match(CSS, /\.fask-blocked \{[^}]*padding:/);
  // no longer bare text with an underline hover — the pill fills on hover like Clear
  assert.match(CSS, /\.fask-blocked:hover \{[^}]*background: #c0392b/);
  assert.doesNotMatch(CSS, /\.fask-blocked:hover \{[^}]*text-decoration: underline/);
});

test("courier handoff: the '↪ from <sender>' origin marker is wired and styled", () => {
  // a chip beside the session name, hidden until the card carries a courier origin
  assert.match(FEED, /const origin = el\("a", "fask-origin"\); origin\.style\.display = "none"/);
  assert.match(FEED, /idwrap\.append\(name, origin\)/, "the origin marker sits beside the session name");
  // populated from it.origin in the update path: "↪ from <peer>", click opens the sender
  assert.match(FEED, /og\.textContent = "↪ from " \+ it\.origin\.peer/);
  assert.match(FEED, /type: "openSession", id: it\.origin!\.peerSid/, "clicking the marker opens the sender");
  assert.match(CSS, /\.fask-origin \{[^}]*cursor: pointer/);
});
