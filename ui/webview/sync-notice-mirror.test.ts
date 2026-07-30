// Automatic fleet syncs mirror into the shell's Log (the user 2026-07-30). romp moves commits between
// machines on its own, and the only trace was the network panel's live phase line — which disappears the
// instant the sync ends. So a push that LANDED and a push that FAILED while you were looking elsewhere
// were, after the fact, equally invisible. Successes log too: what was asked for is a record of what romp
// did to your machines, not another alarm.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { syncNotices } from "./badge-mirror";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");

const row = (sig: string, text: string, ok = true) => ({ sig, t: 1000, text, ok });

test("a finished sync logs once, under its own kind", () => {
  const { notices, active } = syncNotices(
    [row("sync|100|1", "pushed this machine's build (v0.2.0+) to api; it is restarting into it"),
      row("sync|100|2", "could not pull web's commits: dirty tree", false)], new Set());
  assert.equal(notices.length, 2);
  assert.deepEqual(notices.map((n) => n.kind), ["sync", "sync"]);
  assert.match(notices[0].text, /pushed this machine's build/);
  assert.deepEqual([...active].sort(), ["sync|100|1", "sync|100|2"]);
});

test("a SUCCESS is an entry, not only a failure", () => {
  // the whole point: an unwatched push that worked used to leave no record either
  const { notices } = syncNotices([row("sync|100|1", "pushed this machine's build to api")], new Set());
  assert.equal(notices.length, 1);
});

test("a re-sent row does NOT re-log — a re-render or reload is not a second sync", () => {
  const { notices, active } = syncNotices(
    [row("sync|100|1", "pushed to api")], new Set(["sync|100|1"]));
  assert.equal(notices.length, 0);
  assert.deepEqual([...active], ["sync|100|1"], "still active, so the seen-set keeps holding it");
});

test("the same sync happening AGAIN is a new occurrence and logs again", () => {
  const { notices } = syncNotices([row("sync|100|7", "pushed to api")], new Set(["sync|100|1"]));
  assert.equal(notices.length, 1);
});

test("blank or unsigned rows are not entries", () => {
  const { notices, active } = syncNotices(
    [row("", "orphaned"), row("sync|100|9", ""), null as any], new Set());
  assert.equal(notices.length, 0);
  assert.equal(active.size, 0);
});

test("a remote's own long error is capped so one entry can't swallow the list", () => {
  const { notices } = syncNotices([row("sync|100|1", "x".repeat(900), false)], new Set());
  assert.equal(notices[0].text.length, 240);
  assert.ok(notices[0].text.endsWith("…"));
});

test("the feed mirrors syncNotices through the same seen-set and bell bridge", () => {
  assert.match(FEED, /const syncs = syncNotices\(sync, seenSet\);/);
  assert.match(FEED, /Array\.isArray\(m\.syncNotices\) \? m\.syncNotices : \[\]/);
});
