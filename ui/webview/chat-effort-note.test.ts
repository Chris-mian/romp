// Durable "effort set to X" note in the chat (the user 2026-07-16): an /effort change reconnects the SDK
// session to apply --effort and leaves no transcript atom, so the synthesized /effort chip self-destructs on
// the next message and history kept no record of when effort changed. The kernel now interleaves a persistent
// `effortApplied` note by time; render.ts draws it with the same slim rail treatment as `retried`. Source
// pins (render.ts has import-time DOM side effects).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("effortApplied is a ChatEvent, dispatched to its own renderer", () => {
  assert.match(RENDER, /kind: "effortApplied"; effort: string; ts\?: string; uuid\?: string/);
  assert.match(RENDER, /ev\.kind === "effortApplied"\) return renderEffortApplied\(ev\)/);
});

test("renderEffortApplied is a static, muted 'effort set to X' rail note", () => {
  const body = RENDER.slice(RENDER.indexOf("function renderEffortApplied("), RENDER.indexOf("// Compact a token count"));
  assert.match(body, /el\("div", "turn turn-effort"\)/);
  assert.match(body, /turn\.appendChild\(dot\("ring"\)\)/);         // the hollow ring, like the retried note
  assert.match(body, /`effort set to \$\{ev\.effort\}`/);
  assert.match(body, /line\.title = /, "a tooltip explains the reconnect-to-apply + that this marks the apply moment");
});

test("the effort note reuses the retried note's slim treatment (one shared style, per the font rule)", () => {
  // grouped selectors → the effort note inherits the SAME size/colour as the retried note, not a new one
  assert.match(CSS, /\.turn-retried, \.turn-effort \{/);
  assert.match(CSS, /\.retried-line, \.effort-line \{[^}]*font-size: 0\.9em/);
});
