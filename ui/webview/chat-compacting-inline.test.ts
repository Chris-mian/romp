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

test("the chat bar sweeps the context colormap like the statusline/tab bars (the user 2026-07-07)", () => {
  // renderCompacting hands its fill to applyCompactSweep (which sets --cmp0..4 the ctx-compress keyframes
  // read) so the bar changes colour through the map, not a flat teal — at the SAME 3200ms as the keyframe.
  const body = RENDER.slice(RENDER.indexOf("function renderCompacting"), RENDER.indexOf("function renderReconnecting"));
  assert.match(body, /applyCompactSweep\(fill, 3200\)/);
});

// ── the compaction boundary is a COLLAPSIBLE box showing the model's summary (the user 2026-07-07) ──
test("the compact ChatEvent carries the model's summary text", () => {
  assert.match(RENDER, /kind: "compact";[^}]*summary\?: string/);
});

test("renderCompact draws a collapsible summary box when a summary is present", () => {
  const body = RENDER.slice(RENDER.indexOf("function renderCompact("), RENDER.indexOf("function toggleCompact"));
  assert.match(body, /const summary = \(ev\.summary \|\| ""\)\.trim\(\)/);
  assert.match(body, /compactExpanded\.has\(uuid\)/);                 // per-uuid open state
  assert.match(body, /el\("span", "compact-caret"\)/);               // ▸/▾ caret only when there's a summary
  assert.match(body, /car\.textContent = open \? "▾" : "▸"/);
  assert.match(body, /line\.classList\.add\("compact-clickable"\)/);
  assert.match(body, /toggleCompact\(uuid\)/);                        // header click toggles
  assert.match(body, /el\("div", "compact-summary md"\)/);           // the summary body, markdown-rendered
  assert.match(body, /body\.innerHTML = md\(summary\)/);
});

test("toggleCompact repaints in place with scroll preserved, like toggleToolGroup", () => {
  const body = RENDER.slice(RENDER.indexOf("function toggleCompact"), RENDER.indexOf("function toggleCompact") + 500);
  assert.match(body, /compactExpanded\.has\(uuid\)\) compactExpanded\.delete\(uuid\); else compactExpanded\.add\(uuid\)/);
  assert.match(body, /if \(v\) v\.stale = true; syncView\(activeId\)/);
  assert.match(body, /content\.scrollTop = top/);
});

test("the default window opens at the last compaction boundary (pre-compaction history scrubbed)", () => {
  assert.match(RENDER, /function lastCompactUnit\(s: Session, items: DisplayItem\[\]\): number/);
  assert.match(RENDER, /if \(s\.events\[i\]\.kind === "compact"\) \{ evIdx = i; break; \}/);
  // the summary box + its caret + clickable header are styled
  assert.match(CSS, /\.compact-summary \{[^}]*border-left: 2px solid var\(--st-compacting-bg/);
  assert.match(CSS, /\.compact-caret \{/);
  assert.match(CSS, /\.compact-line\.compact-clickable \{ cursor: pointer; \}/);
});
