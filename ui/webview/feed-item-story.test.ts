// The per-item STORY (the user 2026-07-20: a giant card's stale subs, where they couldn't tell if the subs were still
// active): a non-done sub-goal shows a one-line gist of its newest verdict event in OUTCOME words
// ("asked you · 2h ago"), expandable (keyed state, survives re-renders) to the full block/unblock log,
// each row a jump to its own chat turn. The data was always in the goal store's node log — the kernel
// now ships it compacted (_node_log_rows) and the feed renders it. Progressive disclosure: gist →
// history → transcript, each one click. No jsdom for the feed renderer, so pin at the source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");
const KERNEL = fs.readFileSync(path.resolve(process.cwd(), "..", "bin", "romp-kernel"), "utf8");

test("the kernel ships a non-done node's verdict log, compacted with per-row anchors", () => {
  assert.match(KERNEL, /def _node_log_rows\(nd, seg_work, cap=8\):/);
  // per-row exact anchor when the segment resolves in this parse; null → the client's ev-time fallback
  assert.match(KERNEL, /"anchorUuid": seg_work\.get\(_seg_key\(seg\)\) if seg else None/);
  // shipped on the flatten payload for NON-done nodes only (a done node's story is its summary)
  assert.match(KERNEL, /"log": _node_log_rows\(nd, seg_uuid\) if st != "done" else None,/);
});

test("a non-done node renders the gist line — newest event in outcome words + age — and toggles the history", () => {
  assert.match(FEED, /const nodeLogOpen = new Set<string>\(\);/);
  assert.match(FEED, /if \(!repeat && node\.status !== "done" && !node\.cleared && node\.log && node\.log\.length\) \{/);
  assert.match(FEED, /logPhrase\(last\) \+ " · " \+ relAge\(hostNow - logRowT\(last\)\)/);
  // the toggle is keyed (itemId:nodeId) and re-renders — state survives pushes, never a dead-end
  assert.match(FEED, /if \(opened\) nodeLogOpen\.delete\(nodeKey\); else nodeLogOpen\.add\(nodeKey\); render\(\);/);
});

test("the story speaks outcomes, not judge internals", () => {
  assert.match(FEED, /function logPhrase\(r: NodeLogRow\): string/);
  assert.match(FEED, /r\.src === "user" \? "you answered" : "unblocked"/);
  assert.match(FEED, /r\.src === "user" \? "you checked it off" : "marked done"/);
  assert.match(FEED, /return s === "user" \? "you flagged a block" : "asked you";|r\.src === "user" \? "you flagged a block" : "asked you"/);
});

test("each history row jumps to its own chat turn — exact anchor when warm, ev-time nearest otherwise", () => {
  assert.match(FEED, /t: r\.evT \|\| rt, anchor: "work", anchorUuid: r\.anchorUuid \?\? null/);
});

test("the tree re-render signature covers the story state (log-open, row count, cleared)", () => {
  // without these a push would skip the rebuild and the toggle/drop would appear to do nothing
  assert.match(FEED, /nodeLogOpen\.has\(it\.itemId \+ ":" \+ n\.id\) \? "L" : ""/);
  assert.match(FEED, /\(n\.cleared \? "x" : ""\)/);
  assert.match(FEED, /\(\(n\.log \|\| \[\]\)\.length \|\| ""\)/);
});

test("story sizes reuse the modal's section family — no new font fragments (CLAUDE.md fonts rule)", () => {
  assert.match(CSS, /\.ftree-log-gist \{[^}]*font-size: 0\.86em/);
  assert.match(CSS, /\.ftree-log-row \{[^}]*font-size: 0\.86em/);
  assert.match(CSS, /\.ftree-log-when \{[^}]*white-space: nowrap/);
});
