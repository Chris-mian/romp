// Compact-mode transcript caching (the user 2026-06-17, generalized 2026-06-25): a tab switch must NOT
// re-tear-down the whole transcript. Compact now shares the SINGLE virtualization path with normal mode —
// syncView's no-op fast path reveals the cached DOM unless the event set changed (append/rewind), the view
// was updated while hidden (stale), or a tool-group was toggled (which sets stale → re-render the current
// window). Source-level pin (no jsdom for the chat renderer).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");

test("a switch with no change is a NO-OP (the cached DOM is revealed), in compact too", () => {
  assert.match(RENDER, /if \(v\.rendered === len && !v\.stale && v\.el\.childNodes\.length > 0\) return v;/);
});

test("compact / a stale view re-renders the CURRENT window (not a full transcript rebuild)", () => {
  assert.match(RENDER, /if \(settings\.compact \|\| v\.stale\) \{[\s\S]*?renderWindowItems\(v, s, items, ws, we, working\); v\.stale = false; return v;/);
});

test("toggling a tool group forces a re-render past the cache (sets stale) — an expand still repaints", () => {
  assert.match(RENDER, /if \(activeId\) \{ const v = views\.get\(activeId\); if \(v\) v\.stale = true; syncView\(activeId\); \}/);
});
