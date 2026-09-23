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
  assert.match(RENDER, /const current = v\.rendered === len && !v\.stale && !v\.rediff && v\.el\.childNodes\.length > 0 && !!v\.painted && v\.painted\.items\.length === total;[\s\S]{0,120}?if \(current\) return v;/);
});

test("a stale view re-renders the CURRENT window (not a full transcript rebuild); compact mode takes the keyed paint like normal mode", () => {
  assert.match(RENDER, /if \(!v\.stale && tailDiff\(v, s, items, working, wasAtTail\)\) return v;[\s\S]*?renderWindowItems\(v, s, items, ws, we, working\); v\.stale = false; return v;/);
  assert.doesNotMatch(RENDER, /if \(settings\.compact \|\| v\.stale\) \{/, "compact mode rebuilt the whole window on every frame until 2026-09-23");
});

test("toggling a tool group forces a re-render past the cache (sets stale) — an expand still repaints", () => {
  assert.match(RENDER, /if \(activeId\) \{ const v = views\.get\(activeId\); if \(v\) v\.stale = true; syncView\(activeId\); \}/);
});
