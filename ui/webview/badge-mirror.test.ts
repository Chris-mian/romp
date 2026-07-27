// Card trouble badges mirror into the shell's bell (the user 2026-07-27) — the chip stays on the
// card; the bell gets ONE durable entry per episode. EXECUTES ./badge-mirror; the feed plumbing
// (seen-set persistence + the {romp:'notify'} post) is source-pinned.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { badgeNotices, type BadgeItem } from "./badge-mirror";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");

const base = (over: Partial<BadgeItem>): BadgeItem =>
  ({ itemId: "TESTSID:g1", name: "api", text: "ship the notes-api", ...over });

test("every trouble chip becomes one entry, in the session's name", () => {
  const items = [base({
    warns: [{ kind: "distill", t: 100, msg: "the summarizer gave up" }],
    stalled: { why: "reviver not retiring", since: 200, note: "romp is holding this" },
    nudgeFailed: true,
    retrying: { since: 300 },
    blocked: { state: "apiError", status: 529 },
  })];
  const { notices } = badgeNotices(items, new Set());
  assert.deepEqual(notices.map((n) => n.kind), ["warn", "stalled", "nudge", "retry", "apierror"]);
  assert.ok(notices.every((n) => n.text.startsWith("api — ")), "each entry names the session");
  assert.match(notices[0].text, /warning: the summarizer gave up/);
  assert.match(notices[1].text, /stalled: romp is holding this/, "the staller's note beats the mechanical why");
  assert.match(notices[4].text, /API error 529/);
});

test("a seen signature stays quiet; the SAME badge next push logs nothing", () => {
  const items = [base({ stalled: { why: "w", since: 200 } })];
  const first = badgeNotices(items, new Set());
  assert.equal(first.notices.length, 1);
  const second = badgeNotices(items, new Set(first.active));
  assert.equal(second.notices.length, 0, "the persisted active set is exactly the next call's seen set");
});

test("a NEW episode (different since/t) is a new entry; a cleared badge leaves the active set", () => {
  const s1 = badgeNotices([base({ stalled: { why: "w", since: 200 } })], new Set());
  const s2 = badgeNotices([base({ stalled: { why: "w", since: 999 } })], new Set(s1.active));
  assert.equal(s2.notices.length, 1, "a fresh stall episode logs again");
  const gone = badgeNotices([base({})], new Set(s2.active));
  assert.equal(gone.active.size, 0, "no badge → no active sigs → the next occurrence re-logs");
});

test("only the API-error block mirrors — an ordinary permission ask is not an error", () => {
  const { notices } = badgeNotices([base({ blocked: { state: "ask" } })], new Set());
  assert.equal(notices.length, 0);
});

test("spend-limit and prompt-too-long blocks say what they are", () => {
  const sl = badgeNotices([base({ blocked: { state: "apiError", spendLimit: true } })], new Set()).notices[0];
  const tl = badgeNotices([base({ blocked: { state: "apiError", tooLong: true } })], new Set()).notices[0];
  assert.match(sl.text, /spend limit reached/);
  assert.match(tl.text, /prompt too long/);
});

test("the feed posts each notice to the shell and persists only the ACTIVE set", () => {
  assert.match(FEED, /mirrorBadges\(incomingAsks\);/, "runs on every feed payload, against the FULL list");
  assert.match(FEED, /window\.parent\?\.postMessage\(\{ romp: "notify", kind: n\.kind, text: n\.text \}, "\*"\)/);
  assert.match(FEED, /localStorage\.setItem\(BADGE_SEEN_KEY, JSON\.stringify\(Array\.from\(active\)\)\)/,
    "active-only persistence is what re-arms a cleared badge and bounds the store");
});
