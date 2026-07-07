// LIVE compaction indicator in the chat flow (the user 2026-07-06): while the session compacts, an ANIMATED
// inline element ("Compacting context…" + the compressing teal bar) renders in the transcript — not only in
// the statusline/tab. The kernel appends kind:"compacting" BEFORE kind:"queued", so a message sent
// mid-compaction stacks BELOW it instead of clobbering it; once the boundary lands, the {kind:"compact"}
// "Context compacted" notice card it visually becomes (via the shared teal) takes over. Source pins.
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

// ── the compaction boundary is a DEFAULT-COLLAPSED notice card showing the model's summary (the user 2026-07-07) ──
test("the compact ChatEvent carries the model's summary text", () => {
  assert.match(RENDER, /kind: "compact";[^}]*summary\?: string/);
});

test("renderCompact routes the summary through the shared 'compact' notice card as its collapsible body", () => {
  const body = RENDER.slice(RENDER.indexOf("function renderCompact("), RENDER.indexOf("function renderCompacting"));
  assert.match(body, /const summary = \(ev\.summary \|\| ""\)\.trim\(\)/);
  assert.match(body, /body\.innerHTML = md\(summary\)/);                            // the summary, markdown-rendered
  assert.match(body, /noticeCard\(\{ variant: "compact", chip: "compacted", head, body,/);
  // collapsible ONLY when there's a summary; keyed by the boundary uuid so open state survives re-renders
  assert.match(body, /collapsible: !!summary, key: uuid \? "compact:" \+ uuid : undefined/);
});

test("the card is DEFAULT COLLAPSED via the shared keyed fold — the bespoke Set + toggle are gone", () => {
  // noticeCard applies the open class only if the key was remembered open (applyFold → openFolds) → collapsed
  // by default; the head click toggles + persists. No per-uuid compactExpanded Set, no toggleCompact.
  assert.doesNotMatch(RENDER, /compactExpanded/, "the bespoke open-state Set was replaced by the shared fold");
  assert.doesNotMatch(RENDER, /function toggleCompact/, "no bespoke toggle — the notice head IS the toggle");
  const nc = RENDER.slice(RENDER.indexOf("function noticeCard("), RENDER.indexOf("function noticeCard(") + 1500);
  assert.match(nc, /applyFold\(card, "notice-open", o\.key\)/, "collapsed unless the key is remembered open");
});

test("the default window opens at the last compaction boundary (pre-compaction history scrubbed)", () => {
  assert.match(RENDER, /function lastCompactUnit\(s: Session, items: DisplayItem\[\]\): number/);
  assert.match(RENDER, /if \(s\.events\[i\]\.kind === "compact"\) \{ evIdx = i; break; \}/);
});

test("the card wears the compaction TEAL as its notice-card variant accent — a system event, not a bespoke rail line", () => {
  assert.match(CSS, /\.notice-card-compact \{[^}]*border-left-color: var\(--st-compacting-bg/);
  assert.match(CSS, /\.notice-chip-compact \{[^}]*color: var\(--st-compacting-bg/);
});
