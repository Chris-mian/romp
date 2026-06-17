// Feed modal layout (the user 2026-06-16). The modal "card" is rearranged so the goal CHECKLIST is at
// the top and the chrome wraps it:
//   - TOP bar: the session name at the left, the ✕ at the right (no separate title for a single ask —
//     its top-level goal IS the tree root, a notch larger than its sub-items);
//   - the tree/checklist sits directly below, with per-node "(Xm ago)" times pulled in close to the
//     content (fit-content) and right-aligned, in parentheses;
//   - BOTTOM bar: the (recency-tinted) age + Follow up + Clear in one row, the composer dropping in below.
// No jsdom harness for the feed, so — like the other feed-*.test.ts — pin it at the source level.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "feed.css"), "utf8");

test("single-ask modal: the top-level goal is the tree root, not a separate header title", () => {
  assert.match(FEED, /ttlEl\.style\.display = "none"/);            // no header title for a single ask
  assert.match(FEED, /renderTreeBody\(body, it, false\)/);          // root goal IS the first list line
  assert.doesNotMatch(FEED, /renderTreeBody\(body, it, true\)/, "the single-ask body no longer skips the root");
});

test("TOP bar = session name (left) + ✕ (right); age is no longer in the header", () => {
  assert.match(FEED, /head\.append\(ttl, agent, close\)/);
  assert.doesNotMatch(FEED, /head\.append\(ttl, agent, age/);
  assert.match(CSS, /\.feed-modal-close \{[^}]*margin-left: auto/);   // ✕ pinned far-right
});

test("BOTTOM bar = age + Follow up + Clear in one row, the checklist sitting above it", () => {
  assert.match(FEED, /footRow\.append\(age, fup, clr\)/);
  assert.match(FEED, /foot\.append\(footRow, fubox\)/);
  assert.match(FEED, /inner\.append\(head, body, foot\)/);            // head, then tree, then footer
  assert.match(CSS, /\.feed-modal-foot-row \{[^}]*display: flex/);
  assert.match(CSS, /\.feed-modal-foot-row \.feed-modal-age \{[^}]*margin-right: auto/);   // age left, buttons right
});

test("the root goal reads larger; node times are parenthesized and pulled in (fit-content)", () => {
  assert.match(FEED, /\(depth === 0 \? " ftree-root" : ""\)/);
  assert.match(FEED, /"\(" \+ relAge\(hostNow - node\.last\) \+ "\)"/);
  assert.match(CSS, /\.ftree-node\.ftree-root \.ftree-text \{[^}]*font-size/);
  assert.match(CSS, /\.ftree \{[^}]*width: fit-content/);
});

test("the age is recency-tinted in every modal variant (ask / group / standalone)", () => {
  assert.match(FEED, /ageEl\.style\.color = "rgb\(" \+ it\.trgb\.join\(","\) \+ "\)"/);
  assert.match(FEED, /ageEl\.style\.color = "rgb\(" \+ grp\.trgb\.join\(","\) \+ "\)"/);
  assert.match(FEED, /ageEl\.style\.color = "rgb\(" \+ fitem\.trgb\.join\(","\) \+ "\)"/);
});
