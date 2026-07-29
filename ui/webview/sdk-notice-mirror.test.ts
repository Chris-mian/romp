// SDK-backend problems mirror into the shell's error center (the user 2026-07-28): a session thread
// that died, a stream that dropped, a setting the CLI refused used to reach the kernel log alone, so
// the dashboard showed nothing and the session just looked odd. The kernel signs each OCCURRENCE and
// the feed posts it to the bell over the same {romp:'notify'} bridge card badges already use.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { sdkProblemNotices } from "./badge-mirror";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");

const row = (sig: string, text: string) => ({ sig, t: 1000, text });

test("every unseen row logs once, with the sdk kind", () => {
  const { notices, active } = sdkProblemNotices(
    [row("sdk|100|be|1", "sdk session web crashed: AttributeError"),
      row("sdk|100|be|2", "set_model (api -> opus) refused by the SDK")], new Set());
  assert.equal(notices.length, 2);
  assert.deepEqual(notices.map((n) => n.kind), ["sdk", "sdk"]);
  assert.equal(notices[0].text, "sdk session web crashed: AttributeError");
  assert.deepEqual([...active].sort(), ["sdk|100|be|1", "sdk|100|be|2"]);
});

test("a re-sent row does NOT re-log — a re-render or reload is not a new failure", () => {
  const rows = [row("sdk|100|be|1", "sdk session web crashed")];
  const { notices, active } = sdkProblemNotices(rows, new Set(["sdk|100|be|1"]));
  assert.equal(notices.length, 0);
  assert.deepEqual([...active], ["sdk|100|be|1"], "still active, so the seen-set keeps holding it");
});

test("the same failure happening AGAIN is a new occurrence and logs again", () => {
  // the kernel's sequence advances per record; the bell coalesces a flood into one counted row
  const { notices } = sdkProblemNotices(
    [row("sdk|100|be|7", "sdk session web crashed")], new Set(["sdk|100|be|1"]));
  assert.equal(notices.length, 1);
});

test("blank or unsigned rows are not entries", () => {
  const { notices, active } = sdkProblemNotices(
    [row("", "orphaned"), row("sdk|100|be|9", ""), null as any], new Set());
  assert.equal(notices.length, 0);
  assert.equal(active.size, 0);
});

test("a very long problem is capped so one entry can't swallow the list", () => {
  const { notices } = sdkProblemNotices([row("sdk|100|be|1", "x".repeat(900))], new Set());
  assert.equal(notices[0].text.length, 240);
  assert.ok(notices[0].text.endsWith("…"));
});

test("the feed mirrors sdkNotices through the same seen-set and bell bridge", () => {
  assert.match(FEED, /import \{ badgeNotices, clearBoundaryNotices, sdkProblemNotices,/);
  assert.match(FEED, /function mirrorBadges\(items: AskItem\[\], clears: ClearNoticeRow\[\], sdk: SdkNoticeRow\[\]\): void/);
  assert.match(FEED, /const sdkProblems = sdkProblemNotices\(sdk, seenSet\);/);
  assert.match(FEED, /\[\.\.\.badges\.notices, \.\.\.boundary\.notices, \.\.\.sdkProblems\.notices\]/);
  assert.match(FEED, /new Set\(\[\.\.\.badges\.active, \.\.\.boundary\.active, \.\.\.sdkProblems\.active\]\)/);
  assert.match(FEED, /Array\.isArray\(m\.sdkNotices\) \? m\.sdkNotices : \[\]/);
});
