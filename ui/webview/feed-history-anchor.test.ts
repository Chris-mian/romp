// The modal "history"/linked rows deep-link to the reply turn BY ID (link_audit's audit, 2026-06-20): the
// onclick passed reply_id only as `itemId`, never as `anchorUuid`, so the chat got no uuid to land on and
// the click honest-failed (no deep-link) — and there's no time fallback to catch it anymore (scrollToNearestT
// deleted in 3d0a80d). reply_id IS the assistant reply turn's rendered data-uuid, so it doubles as anchorUuid.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");

test("history rows are gone with the AskLinked subsystem; node nav still lands by id (2026-07-07)", () => {
  assert.doesNotMatch(FEED, /node\.rows/);   // the rows/AskLinked machinery was dead (kernel always sent rows: []) and is removed
  assert.match(
    FEED,
    /anchorUuid: node\.anchorUuid/,
    "tree-node navigation still passes an exact anchor uuid",
  );
});
