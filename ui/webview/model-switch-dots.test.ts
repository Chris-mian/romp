// A /model switch shows animated accent-blue dots in the model badge until the new name lands — the
// server drives it (status.modelPending, event-based, cleared the instant the live model reflects the
// pick) so the badge never lingers on a stale or premature name (the user 2026-07-03: switched to opus,
// the badge kept saying fable). Source-level pins (the statusline DOM isn't jsdom-tested here).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("Status carries the server-driven modelPending flag", () => {
  assert.match(RENDER, /interface Status \{[^}]*modelPending\?: boolean/);
});

test("syncMetaControls renders dots for a pending model, driven by the server flag (+ local click heuristic)", () => {
  // model + effort both drive dots now (effort reconnects to apply); the model clause is still present
  assert.match(RENDER, /const pending = \(kind === "model" && !!st\.modelPending\) \|\| \(kind === "effort" && !!st\.effortPending\)\s*\n\s*\|\| \(kind === "auth" && !!st\.authPending\) \|\| isMetaPending\(kind, st\);/);
  assert.match(RENDER, /const showDots = pending && \(kind === "model" \|\| kind === "effort" \|\| kind === "auth"\);/);
  assert.match(RENDER, /if \(!label\.querySelector\("\.meta-dots"\)\) label\.replaceChildren\(metaDots\(\)\);/);
});

test("metaDots builds three <i> dots", () => {
  assert.match(RENDER, /function metaDots\(\): HTMLElement \{/);
  const body = RENDER.slice(RENDER.indexOf("function metaDots"));
  assert.equal((body.slice(0, body.indexOf("return d;")).match(/el\("i"\)/g) || []).length, 3,
               "exactly three dots");
});

test("the dots are accent-blue, animated, and override the .meta-pending dim", () => {
  assert.match(CSS, /\.meta-dots i \{[^}]*background: var\(--accent\)/, "romp accent blue, not a hardcoded hex");
  assert.match(CSS, /@keyframes meta-dots/);
  assert.match(CSS, /\.meta-pending \.meta-label:has\(\.meta-dots\) \{ opacity: 1; animation: none; \}/,
               "the dots read full-strength, not under the pending dim");
  // staggered so they pulse in sequence
  assert.match(CSS, /\.meta-dots i:nth-child\(2\) \{ animation-delay: 0\.16s; \}/);
  assert.match(CSS, /\.meta-dots i:nth-child\(3\) \{ animation-delay: 0\.32s; \}/);
});
