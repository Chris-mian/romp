// A context compaction renders as a NOTICE CARD in romp's system-event family (renderCompact → noticeCard,
// variant "compact") — the same boxed, chip-headed, default-collapsed treatment as the agent/romp/reminder
// notices, distinguished only by the COMPACTION TEAL accent. The head says WHY at a glance (trigger + token
// before→after); the model's summary is the collapsible body — never the raw Claude payload or hook stdout
// (both dropped kernel-side). The kernel emits a {kind:"compact"} event carrying the boundary metadata; this
// pins the card render + the token formatter (the user 2026-07-01, reworked 2026-07-07). Source pins.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("renderCompact builds a 'compact' notice card dispatched off kind:'compact'", () => {
  assert.match(RENDER, /ev\.kind === "compact"\) return renderCompact\(ev\)/);
  assert.match(RENDER, /noticeCard\(\{ variant: "compact", chip: "compacted"/);
  assert.match(RENDER, /const head = "Context compacted"/);
  // the compact event carries the boundary metadata the head notes
  assert.match(RENDER, /kind: "compact"; trigger\?: string; preTokens\?: number; postTokens\?: number;/);
});

test("the head's muted meta names the trigger + the token win (before → after)", () => {
  assert.match(RENDER, /if \(ev\.trigger === "auto"\) bits\.push\("auto"\);/);
  assert.match(RENDER, /else if \(ev\.trigger === "manual"\) bits\.push\("manual"\);/);
  assert.match(RENDER, /\$\{compactTokens\(ev\.preTokens\)\} → \$\{compactTokens\(ev\.postTokens\)\}/);
  assert.match(RENDER, /const head = "Context compacted" \+ \(bits\.length \? " · " \+ bits\.join\(" · "\) : ""\)/);
});

test("it wears the compaction TEAL as its notice-card variant accent — a system event, not a bespoke line", () => {
  assert.match(CSS, /\.notice-card-compact \{[^}]*border-left-color: var\(--st-compacting-bg/);
  assert.match(CSS, /\.notice-chip-compact \{[^}]*color: var\(--st-compacting-bg/);
});

// executed: mirror compactTokens' logic to guard its intent (compact + human-readable)
test("the token formatter is compact + human-readable", () => {
  const compactTokens = (n: number): string => {
    if (n < 1000) return String(n);
    const k = n / 1000;
    return (k < 10 ? k.toFixed(1).replace(/\.0$/, "") : Math.round(k)) + "k";
  };
  assert.equal(compactTokens(900), "900");
  assert.equal(compactTokens(6514), "6.5k");
  assert.equal(compactTokens(795232), "795k");
  assert.equal(compactTokens(9000), "9k");
});
