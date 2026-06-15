// Chat rail + dot color model (the user 2026-06-15):
//   - the session's identity color lives on the vertical RAIL (2px, 70%), NOT the window border.
//   - dot colors are DECOUPLED from the session (no per-session disc / no persistent ring, which would
//     clash with the hover-selection ring): white reply (= assistant text color), blue you (= your
//     message bubble #2b6cef), blue ✓ success disc (the cyan --check-bg, consistent with the feed), red ✗.
//   - clickable expanders ("12 lines" / "prompt") and file links carry a persistent dotted underline.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const CSS = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "styles.css"), "utf8");

test("the fold toggle and file links have a persistent dotted-underline link affordance", () => {
  assert.match(CSS, /\.tool-fold-toggle \{[^}]*text-decoration: underline dotted/);
  assert.match(CSS, /\.tool-file \{[^}]*text-decoration: underline dotted/);
});

test("session identity is on the rail (2px, 70%), not the window border", () => {
  assert.match(CSS, /#winframe \{[^}]*border: 2px solid var\(--box-border\)/);
  assert.doesNotMatch(CSS, /#winframe \{[^}]*--active-accent/);
  assert.match(CSS, /\.turn::before \{[^}]*width: 2px[^}]*background: var\(--active-accent[^}]*opacity: 0\.7/);
});

test("dot colors are decoupled from the session (no ring, absolute hues)", () => {
  assert.doesNotMatch(CSS, /\n\.dot \{[^}]*box-shadow/, "the BASE dot has no persistent ring (it'd clash with the hover-selection ring)");
  assert.match(CSS, /\.dot\.ring \{[^}]*background: var\(--fg\)/, "assistant/thinking = the assistant text color (--fg)");
  assert.match(CSS, /\.dot\.green \{[^}]*background: var\(--check-bg\)/, "tool success = the blue ✓ disc (consistent with the feed)");
  assert.match(CSS, /\.dot\.err \{[^}]*background: var\(--err\)/, "tool error = red");
  assert.match(CSS, /\.dot\.user \{ background: #2b6cef/, "your prompt = the bubble blue (#2b6cef)");
});
