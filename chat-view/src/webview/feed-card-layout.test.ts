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

test("row3 + name row are styled", () => {
  assert.match(CSS, /\.fask-row3 \{[^}]*display: flex/);
  // the session name stays on ONE line (ellipsis only if truly too long) — it used to wrap mid-word
  // while the "↪ from" provenance crowded it; now the row fills its width and origin goes right (the
  // user 2026-06-16).
  assert.match(CSS, /\.fask-id \.fname \{[^}]*white-space: nowrap/, "the session name stays on one line, never mid-word");
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
  // populated from it.origin in the update path: a dim gray "↪ from" + the peer in the bold session-name
  // style (its own identity colour); click opens the sender (the user 2026-06-16)
  assert.match(FEED, /pre\.textContent = "↪ from "/);
  assert.match(FEED, /peer\.textContent = it\.origin\.peer/);
  assert.match(FEED, /if \(it\.origin\.color\) peer\.style\.color = it\.origin\.color\.bg/);
  assert.match(FEED, /type: "openSession", id: it\.origin!\.peerSid/, "clicking the marker opens the sender");
  assert.match(CSS, /\.fask-origin-pre \{[^}]*var\(--dim\)/);     // "↪ from" dim gray
  assert.match(CSS, /\.fask-origin-peer \{[^}]*font-weight: 600/); // peer bold like other session names
});

test("a 'Followed up' chip shows while the kernel optimistically reopened a followed-up card (judges, 2026-06-17)", () => {
  assert.match(FEED, /followupPending\?: boolean/);
  assert.match(FEED, /el\("span", "fask-followedup"\); fupBadge\.textContent = "↻ Followed up"/);
  // the chip rides the SESSION-NAME row (right-justified), NOT the bottom action row, so it stops crowding
  // Clear off the card's right edge (the user 2026-06-18)
  assert.match(FEED, /actions\.append\(waitBadge, apiBadge, blkBadge, reBadge, apiRetry, nudge, clr\)/);   // + Nudge before Clear (the user 2026-06-18)
  assert.match(FEED, /row2\.append\(idwrap, fupBadge\)/);
  assert.match(FEED, /a\._followedup\.style\.display = it\.followupPending \? "" : "none"/);
  assert.match(CSS, /\.fask-followedup \{/);
});

test("a cleared card CONTRACTS in on itself (scale + collapse), not a slide to one side (the user 2026-06-18)", () => {
  // no translateX exit; the card scales down + fades while its height collapses so neighbours close the gap
  assert.doesNotMatch(CSS, /\.fitem\.dismissing \{[^}]*translateX/);
  assert.match(CSS, /\.fitem\.dismissing \{[^}]*animation: fask-dismiss/);
  assert.match(CSS, /@keyframes fask-dismiss \{[\s\S]*transform: scale\(0\.78\)[\s\S]*max-height: 0/);
  assert.match(CSS, /prefers-reduced-motion: reduce[\s\S]*\.fitem\.dismissing \{ animation: none/);
});
