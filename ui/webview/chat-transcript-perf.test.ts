// A long chat renders thousands of .turn nodes; the browser doing layout/hit-testing over ALL of them made
// focusing the heavy chat iframe laggy — clicking into/out of the chat stalled ~½s even with nothing changing
// (the user 2026-06-25). content-visibility:auto lets the browser skip layout+paint for OFF-screen turns; a
// contain-intrinsic-size keeps the scrollbar roughly stable. No jsdom harness for layout, so pin it at source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("transcript turns skip off-screen layout/paint via content-visibility (the user 2026-06-25)", () => {
  assert.match(CSS, /\.turn \{[\s\S]*?content-visibility: auto/);
  // contain-intrinsic-size with the `auto` keyword → the browser remembers each turn's real height once seen
  // (a 90px first guess), so the scrollbar stays roughly stable as off-screen turns are skipped.
  assert.match(CSS, /\.turn \{[\s\S]*?contain-intrinsic-size: auto 90px/);
});
