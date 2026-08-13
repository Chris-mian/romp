// A slash COMMAND you sent renders as a special keyword chip inside the blue user bubble (the user 2026-06-29)
// — the "/cmd" token becomes a monospace outlined pill, arguments after it stay plain text. Genuine human
// bubbles only, and only when "/cmd" is a WHOLE leading token (so a "/Users/…" path is never chipped). Source
// pins (no jsdom for the chat renderer).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("a leading slash command in a human bubble becomes a .slash-cmd-chip, args follow as text", () => {
  // matched only for a genuine human bubble (not a romp injection / harness note), via the shared helper
  assert.match(RENDER, /if \(!romp && !injected && ev\.md && renderSlashCmd\(bubble, ev\.md\)\) \{/);
  assert.match(RENDER, /const chip = el\("span", "slash-cmd-chip"\); chip\.textContent = m\[1\];/);
  assert.match(RENDER, /const args = el\("span", "slash-cmd-args"\); args\.textContent = rest;/);
  // the non-command path still renders markdown as before (now also linkifies bare file:// URLs)
  assert.match(RENDER, /\} else if \(ev\.md\) \{\s*\n\s*bubble\.innerHTML = md\(ev\.md\);\s*\n\s*linkifyFileUris\(bubble, imgPaths, ev\.spacePaths, ev\.pathLinks\);[^\n]*\n\s*\}/);
});

test("the chip is a monospace, outlined keyword pill that reads on the blue bubble", () => {
  assert.match(CSS, /\.slash-cmd-chip \{[\s\S]*?font-family: ui-monospace/);
  assert.match(CSS, /\.slash-cmd-chip \{[\s\S]*?border: 1px solid rgba\(255, 255, 255, 0\.38\)/);
  assert.match(CSS, /\.slash-cmd-args \{ margin-left: 7px; \}/);
});

test("a command turn reads in the system-event family, not as a said thing (the user 2026-08-13)", () => {
  // a command is a user GESTURE — it changes something rather than saying something — so the turn sheds
  // the blue right-pinned bubble for a dim left-aligned ✦ row, rhyming with the context dividers
  assert.match(RENDER, /turn\.classList\.add\("turn-cmd"\);\s*\n\s*bubble\.classList\.add\("cmd-row"\);/);
  assert.match(CSS, /\.turn-user\.turn-cmd:not\(\.injected\) \{ align-items: flex-start; \}/);
  assert.match(CSS, /\.user-bubble\.cmd-row \{ max-width: none; background: none; border: none;/);
  assert.match(CSS, /\.user-bubble\.cmd-row::before \{ content: "✦"; margin-right: 8px; color: var\(--dim\); \}/);
  assert.match(CSS, /\.turn-cmd \.msg-acts \{ align-self: flex-start; \}/);
});

// guards on the regex's intent (executed): a whole leading token is chipped; a path is not.
test("the chip regex matches a whole leading /token but not a /path", () => {
  const re = /^(\/[A-Za-z][\w-]*)(?=\s|$)([\s\S]*)$/;
  assert.equal("/usage".match(re)?.[1], "/usage");
  assert.equal("/compact do the thing".match(re)?.[1], "/compact");
  assert.equal("/code-review".match(re)?.[1], "/code-review");
  assert.equal("/Users/me/x.ts".match(re), null, "a filesystem path is NOT a command chip");
  assert.equal("hello /usage".match(re), null, "only a LEADING command is chipped");
});
