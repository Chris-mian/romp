// Chat scroll behavior (the user 2026-06-15): a new "session" push must NOT snap the view to the
// bottom. The kernel re-sends the FULL payload every push, so an APPEND (more turns on the same
// transcript) keeps the user's scroll position; only a FORK (the tab re-pointed onto a new
// transcript) rebuilds + lands at the bottom. The chat renderer has no jsdom harness, so — like the
// other render-*.test.ts / feed-*.test.ts files — pin the behavior at the source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "render.ts"), "utf8");

test("upsert tells append from fork by transcript identity (firstUuid)", () => {
  assert.match(RENDER, /function firstUuid\(/, "a helper identifies the transcript by its first event uuid");
  assert.match(RENDER, /const forked = [\s\S]*?firstUuid\(msg\.events\) !== firstUuid\(prev\.events\)/,
    "fork = the transcript identity changed (not just any full payload)");
});

test("a content refresh appends (preserves scroll); only a fork drops the DOM", () => {
  assert.match(RENDER, /if \(forked\) \{[\s\S]{0,120}?v\.el\.remove\(\)/,
    "the cached DOM is dropped only on a fork, not on every push");
  assert.match(RENDER, /if \(existed && !forked\) appendActive\(\); else showActive\(\)/,
    "a refresh of the active tab appends instead of snapping to the bottom");
});

test("appendActive snaps only when the user is already near the bottom", () => {
  assert.match(RENDER, /const stick = nearBottom\(content\);[\s\S]*?if \(stick\) content\.scrollTop = content\.scrollHeight/,
    "tail-append follows the live edge only if the reader was already at the bottom");
});
