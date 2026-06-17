// The ledger strip (the per-session digest box below the tabs) appears only once there's something
// REAL to show — a digest headline (l.summary) or a body (goals / working-on / done). A brand-new
// session with nothing yet must render NOTHING, not a bare session-name + caret, which the user found
// confusing (2026-06-16). The chat renderer has no jsdom harness, so — like render-rail.test.ts — pin
// the behaviour at the source level.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "render.ts"), "utf8");

test("renderLedger hides the strip unless there's a summary headline or a body", () => {
  assert.match(RENDER, /const hasBody = !!\(tree\.length \|\| cur \|\| bullets\.length\)/);
  // the guard hides when there's no summary AND no body; the bare session-name fallback no longer
  // keeps the strip on screen
  assert.match(RENDER, /if \(!l \|\| \(!l\.summary && !hasBody\)\) \{[^}]*display = "none"/);
  // titleText still falls back to the session name so an active-but-untitled session keeps a label
  assert.match(RENDER, /sessions\.get\(activeId\)\?\.name/);
});

test("the old name-only guard (hide only when titleText is also empty) is gone", () => {
  assert.doesNotMatch(RENDER, /\(!titleText && !hasBody\)/);
});
