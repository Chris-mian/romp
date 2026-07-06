// LIVE compaction indicator in the chat flow (the user 2026-07-06): while the session compacts, an ANIMATED
// inline element ("Compacting context…" + the compressing teal bar) renders in the transcript — not only in
// the statusline/tab. The kernel appends kind:"compacting" BEFORE kind:"queued", so a message sent
// mid-compaction stacks BELOW it instead of clobbering it; once the boundary lands, the {kind:"compact"}
// divider ("✦ Context compacted") it visually becomes takes over. Source pins (render.ts has no jsdom harness).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("a live compacting event has its own ChatEvent kind, dispatched to renderCompacting", () => {
  assert.match(RENDER, /kind: "compacting"; ts\?: string; uuid\?: string/);
  assert.match(RENDER, /ev\.kind === "compacting"\) return renderCompacting\(\)/);
});

test("the compacting dispatch is checked BEFORE the done 'compact' divider (a live signal, not a boundary)", () => {
  const live = RENDER.indexOf('ev.kind === "compacting") return renderCompacting()');
  const done = RENDER.indexOf('ev.kind === "compact") return renderCompact(ev)');
  assert.ok(live > 0 && done > 0, "both dispatch lines present");
  assert.ok(live < done, "the live compacting case must precede the compact-boundary case");
});

test("renderCompacting draws an animated teal element that rhymes with the compacted divider", () => {
  assert.match(RENDER, /function renderCompacting\(\): HTMLElement/);
  assert.match(RENDER, /el\("div", "turn turn-compacting"\)/);
  assert.match(RENDER, /el\("div", "compacting-inline"\)/);
  assert.match(RENDER, /el\("span", "compacting-bar"\)/);
  assert.match(RENDER, /el\("span", "compacting-bar-fill"\)/);   // the animated compressing bar
  assert.match(RENDER, /Compacting context…/);
});

test("the animated bar reuses the statusline ctx-compress motion, in the compacting teal", () => {
  // the fill runs the SAME keyframe as the ctx-bar scan, so the two surfaces read as one motion
  assert.match(CSS, /\.compacting-bar-fill \{[^}]*animation: ctx-compress/);
  assert.match(CSS, /\.compacting-inline \{[^}]*color: var\(--st-compacting-bg/);
  assert.match(CSS, /\.turn-compacting \.dot \{[^}]*background: var\(--st-compacting-bg/);
  assert.match(CSS, /@keyframes ctx-compress/);   // the reused keyframe still exists
});
