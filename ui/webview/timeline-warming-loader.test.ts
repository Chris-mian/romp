// On a COLD restart the timeline must keep the romp loader (spinning swirl + dots) up until real content
// lands — not flash "no romp activity" (the user 2026-07-03). The kernel's live-first build is PARTIAL
// (warming); an empty warming payload leaves _barsLoaded false so draw() keeps the loader, a backstop
// timer guarantees it can never trap, and a real-content OR settled payload finalizes the load. Source
// pins (no jsdom for the SVG renderer), mirroring timeline-barsloader.test.ts.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js"), "utf8");
const KERNEL = fs.readFileSync(path.resolve(process.cwd(), "..", "bin", "romp-kernel"), "utf8");

test("applyBars no longer latches _barsLoaded unconditionally", () => {
  assert.doesNotMatch(SRC, /_barsLoaded = true;   \/\/ the bars payload has landed \(even if empty\)/,
    "the old unconditional latch is gone");
});

test("a warming-and-empty bars payload keeps the loader; content or a settled build finalizes it", () => {
  assert.match(SRC, /const hasContent = Object\.keys\(this\.data\.turns\)\.some\(\(k\) => \(this\.data\.turns\[k\] \|\| \[\]\)\.length\)\s*\n\s*\|\| \(this\.data\.sessions \|\| \[\]\)\.some\(\(s\) => s\.live\);/);
  assert.match(SRC, /if \(!\(m && m\.warming\) \|\| hasContent\) \{\s*\n\s*this\._barsLoaded = true;/);
  assert.match(SRC, /\} else \{\s*\n\s*this\._armLoaderBackstop\(\);\s*\n\s*\}/);
});

test("a backstop timer guarantees the loader can never trap (CLAUDE.md loader rule)", () => {
  assert.match(SRC, /_armLoaderBackstop\(\) \{/);
  assert.match(SRC, /if \(this\._loaderBackstop != null \|\| this\._barsLoaded\) return;/);
  assert.match(SRC, /this\._loaderBackstop = setTimeout\(/);
  assert.match(SRC, /if \(!this\._barsLoaded\) \{ this\._barsLoaded = true; this\.draw\(\); \}/);
  assert.match(SRC, /this\._loaderBackstop = null;   \/\/ timer id/);
  // real content clears any pending backstop
  assert.match(SRC, /if \(this\._loaderBackstop != null\) \{ clearTimeout\(this\._loaderBackstop\); this\._loaderBackstop = null; \}/);
});

test("the kernel tags the live-first bars build as warming (partial), settled builds as not", () => {
  assert.match(KERNEL, /tl_warming = True\s+# this is the PARTIAL cold build/);
  assert.match(KERNEL, /"nudges": timeline\["nudges"\], "now": timeline\["now"\], "warming": tl_warming\}/);
});
