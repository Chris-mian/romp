// Composer drafts must survive a full RELOAD, not just a tab switch (the user 2026-06-25: a half-typed message
// "doesn't pop up" after a refresh). The `drafts` Map is in-memory, so it's mirrored into the webview's
// persisted state (the same store that remembers the active tab) and reloaded at startup; an in-progress draft
// is captured on every keystroke and restored ONCE into the box after load, without clobbering live typing.
// No jsdom for this renderer, so pin the wiring at source (the repo convention — see tab-switch-defer.test.ts).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");

test("drafts are persisted to and reloaded from the webview's saved state", () => {
  // persist: mirror the Map into setState, alongside (not replacing) whatever else is saved
  assert.match(RENDER, /function persistDrafts\(\): void \{[\s\S]*setState\?\.\(\{ \.\.\.\(vscodeApi\.getState\?\.\(\) \|\| \{\}\), drafts: Object\.fromEntries\(drafts\) \}\)/);
  // reload: hydrate the Map from saved state at startup (string values only)
  assert.match(RENDER, /const saved = \(\(vscodeApi\?\.getState\?\.\(\) \|\| \{\}\) as any\)\.drafts;/);
  assert.match(RENDER, /for \(const \[k, v\] of Object\.entries\(saved\)\) if \(typeof v === "string"\) drafts\.set\(k, v\);/);
});

test("typing captures the draft (and persists it) every keystroke — so a reload can restore it", () => {
  assert.match(RENDER, /ta\.addEventListener\("input", \(\) => \{[\s\S]*if \(activeId\) \{ if \(ta\.value\) drafts\.set\(activeId, ta\.value\); else drafts\.delete\(activeId\); persistDrafts\(\); \}[\s\S]*\}\);/);
});

test("the post-reload restore is one-shot and never clobbers live typing", () => {
  assert.match(RENDER, /function restoreActiveDraftOnce\(\): void \{/);
  assert.match(RENDER, /if \(draftsRestored\) return;/);                 // one-shot
  assert.match(RENDER, /if \(!ta \|\| !activeId\) return;/);              // wait until the active tab exists post-load
  assert.match(RENDER, /if \(!ta\.value\) \{ const d = drafts\.get\(activeId\); if \(d\) \{ ta\.value = d;/);  // only when the box is empty
  // invoked from showActive once the active view is shown (so activeId is established post-reload)
  assert.match(RENDER, /if \(empty\) empty\.style\.display = "none";\s*\n\s*restoreActiveDraftOnce\(\);/);
});

test("every draft mutation keeps the persisted copy in sync (switch / send / close)", () => {
  // tab switch stashes the leaving tab's draft → persist
  assert.match(RENDER, /ta\.value = drafts\.get\(id\) \?\? "";\s*\n\s*growComposer\(ta\);\s*\n\s*persistDrafts\(\);/);
  // sending clears the draft → persist
  assert.match(RENDER, /drafts\.delete\(activeId\); persistDrafts\(\);\s*\/\/ sent/);
  // closing a tab drops its draft → persist
  assert.match(RENDER, /drafts\.delete\(id\); persistDrafts\(\);/);
});
