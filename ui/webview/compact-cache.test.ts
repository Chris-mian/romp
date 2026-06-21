// Compact-mode transcript caching (the user 2026-06-17): rebuildCompact used to tear down + rebuild the
// WHOLE transcript on every showActive() — i.e. on every arrow-key tab switch — which lagged on long
// conversations. It now reuses the cached compact DOM unless the event set actually changed (append/
// rewind), the view was updated while hidden (stale), or a tool-group was toggled (which sets stale).
// Source-level pin (no jsdom for the chat renderer).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");

test("rebuildCompact early-returns when the view is already built for the current event set", () => {
  assert.match(RENDER, /if \(v\.rendered === s\.events\.length && !v\.stale && v\.el\.childNodes\.length > 0\) return;/);
});

test("rebuildCompact clears stale after a real rebuild, so the next switch reuses the cache", () => {
  assert.match(RENDER, /v\.rendered = s\.events\.length;\s*\n\s*v\.stale = false;/);
});

test("toggling a tool group forces a rebuild past the cache (sets stale) — an expand still repaints", () => {
  assert.match(RENDER, /if \(activeId\) \{ const v = views\.get\(activeId\); if \(v\) v\.stale = true; syncView\(activeId\); \}/);
});
