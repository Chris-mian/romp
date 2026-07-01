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

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

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
  // it's a direct child of the wrapping row2 (NOT nested in idwrap) so a narrow card wraps it under the
  // name instead of overlapping the chips (the user 2026-06-20)
  assert.match(FEED, /row2\.append\(idwrap, origin, reBadge, fupBadge, waitOnBadge\)/, "the origin marker rides the name row beside the chips");
  assert.doesNotMatch(FEED, /idwrap\.append\(name, origin\)/, "origin is no longer nested inside idwrap");
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
  // Clear off the card's right edge (the user 2026-06-18); origin sits left of it on the same wrapping row
  assert.match(FEED, /row2\.append\(idwrap, origin, reBadge, fupBadge, waitOnBadge\)/);
  // the chip now serves both states: a soft-block you answered with a TARGETED follow-up shows "↩ re-judging"
  // (recheck), else a settled card you followed up on shows "↻ Followed up" (the user 2026-06-27/30).
  assert.match(FEED, /if \(it\.recheck\) \{/);
  assert.match(FEED, /a\._followedup\.textContent = "↩ re-judging"/);
  assert.match(FEED, /\} else if \(it\.followupPending\) \{/);
  assert.match(CSS, /\.fask-followedup \{/);
});

test("session-STATE badges (⏸ approval / ⚠ API error / ⏳ waiting) ride the name row; the footer is buttons only (the user 2026-06-19)", () => {
  // the bug: ⏸ approval + buttons + Clear in the SAME footer row shoved them off a narrow card.
  // Fix: the state badges move up beside the session name; the action row holds only the buttons.
  assert.match(FEED, /idwrap\.append\(waitBadge, apiBadge, blkBadge\)/, "state badges sit beside the name");
  assert.match(FEED, /actions\.append\(apiRetry, revive, cardFup, clr\)/, "footer = buttons only (Retry/Revive/Follow up/Clear) — manual Nudge removed");
  // the badges keep their refs so updateAskCard still toggles them by display
  assert.match(FEED, /a\._blocked = blkBadge; a\._wait = waitBadge;/);
});

test("a cleared card CONTRACTS in on itself (scale + collapse), not a slide to one side (the user 2026-06-18)", () => {
  // no translateX exit; the card scales down + fades while its height collapses so neighbours close the gap
  assert.doesNotMatch(CSS, /\.fitem\.dismissing \{[^}]*translateX/);
  assert.match(CSS, /\.fitem\.dismissing \{[^}]*animation: fask-dismiss/);
  assert.match(CSS, /@keyframes fask-dismiss \{[\s\S]*transform: scale\(0\.78\)[\s\S]*max-height: 0/);
  assert.match(CSS, /prefers-reduced-motion: reduce[\s\S]*\.fitem\.dismissing \{ animation: none/);
});

test("the footer action row WRAPS its buttons so they can NEVER run off the card edge (the user 2026-06-22)", () => {
  // ROBUST, GENERAL mechanism (not per-button width tuning, which kept regressing): .fask-actions takes the
  // width left after the age, right-aligns, and flex-WRAPS its buttons onto extra lines when they don't fit;
  // .fask-row3 wraps as a backstop. min-width:0 lets it shrink to the card so the wrap actually triggers.
  // Verified headless: 4 footer buttons on a 230px card wrap to 2 lines with ZERO overflow.
  assert.match(CSS, /\.fask-actions \{[^}]*flex: 1 1 auto;[^}]*min-width: 0;[^}]*flex-wrap: wrap;[^}]*justify-content: flex-end/);
  assert.match(CSS, /\.fask-row3 \{[^}]*flex-wrap: wrap/);
  // margin-left:auto is GONE — justify-content:flex-end right-aligns the (now wrapping) buttons instead
  assert.doesNotMatch(CSS, /\.fask-actions \{[^}]*margin-left: auto/);
});

test("a long no-space token (file/func/type name) WRAPS instead of overflowing the card (the user 2026-06-23)", () => {
  // overflow-wrap: anywhere (not break-word) so a token like SdkBackend.pending_queued(sid:str) breaks to
  // fit — the title used break-word (kept the longest word as min-width) and the summary had NO wrap at all.
  assert.match(CSS, /\.fcard-title \{[^}]*overflow-wrap: anywhere/);
  // (the .fask-blockwhy/.fask-donewhy auto-line was removed 2026-06-27, so its wrap rule is gone too)
});
