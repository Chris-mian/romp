// The feed search filter (the user 2026-08-23): type-to-filter the board by session name, HOST PREFIX
// INCLUDED — a machine name keeps every session on it, and host:name narrows to one. Pure rule
// executed here; the feed wiring and the expandable footer control pinned by source.
import { test } from "node:test";
import assert from "node:assert";
import * as fs from "node:fs";
import * as path from "node:path";
import { searchMatches, searchSids } from "./feed-search";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

test("substring match over the full display name, case-insensitive, host prefix included", () => {
  assert.ok(searchMatches("TESTHOST", "TESTHOST:notes-api"), "a machine name finds its sessions");
  assert.ok(searchMatches("notes", "TESTHOST:notes-api"));
  assert.ok(searchMatches("TESTHOST:NOTES", "TESTHOST:notes-api"), "case-insensitive");
  assert.ok(searchMatches("t:n", "TESTHOST:notes-api"), "plain substring — spans the host separator");
  assert.ok(!searchMatches("otherbox", "TESTHOST:notes-api"));
  assert.ok(searchMatches("  api ", "api"), "the query is trimmed");
});

test("a blank query is the filter OFF, never matched-none", () => {
  assert.ok(searchMatches("", "anything"));
  assert.ok(searchMatches("   ", "anything"));
  assert.ok(searchMatches(null, "anything"));
  assert.equal(searchSids("", [{ sid: "a", name: "web" }]), null, "null = no filter, distinct from an empty set");
});

test("searchSids collects the matching sids; a query matching nothing yields an EMPTY set", () => {
  const metas = [{ sid: "a", name: "TESTHOST:web" }, { sid: "b", name: "otherbox:web" }, { sid: "c", name: "otherbox:api" }];
  assert.deepEqual([...searchSids("web", metas)!].sort(), ["a", "b"]);
  assert.deepEqual([...searchSids("otherbox", metas)!].sort(), ["b", "c"]);
  assert.equal(searchSids("zzz", metas)!.size, 0, "an empty board is the honest answer, not filter-off");
});

test("the feed composes search WITH the session filter, and cards fall back to their own label", () => {
  assert.match(FEED, /const sMatch = searchSids\(feedSearchQ, sessionsMeta\);/);
  assert.match(FEED, /sMatch\.has\(a\.sid\) \|\| searchMatches\(feedSearchQ, \(a as \{ name\?: string \}\)\.name\)/,
               "a just-died session's cards keep matching by their per-card label");
});

test("the footer control is ensure-once, expandable, and an active query can never be hidden", () => {
  assert.match(FEED, /function ensureSearchBox\(\): HTMLElement/);
  assert.match(FEED, /if \(active\) wrap\.classList\.add\("open"\);/,
               "a live query forces the input open — the compact state never hides an active filter");
  assert.match(FEED, /if \(inp\.value\.trim\(\)\) \{ inp\.value = ""; setFeedSearch\(""\); render\(\); \}/,
               "folding with a live query clears it, never hides it");
  assert.match(FEED, /sessionStorage\.getItem\("romp:feedSearch"\)/,
               "same storage lifetime as the session filter: reload-proof, never a fresh window");
  assert.match(CSS, /#feed-search\.open input \{ width: \d+px/, "the expansion is a real width transition");
});
