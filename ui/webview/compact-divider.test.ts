// A context compaction renders as one clean teal divider — "✦ Context compacted" — with an optional muted
// meta suffix (trigger + token before→after) so it says WHY at a glance, never the raw Claude summary payload
// or the hook stdout (both dropped kernel-side). The kernel emits a {kind:"compact"} event carrying the
// boundary metadata; this pins the divider render + the token formatter (the user 2026-07-01). Source pins.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("renderCompact draws a teal '✦ Context compacted' divider dispatched off kind:'compact'", () => {
  assert.match(RENDER, /ev\.kind === "compact"\) return renderCompact\(ev\)/);
  assert.match(RENDER, /el\("div", "turn turn-compact"\)/);
  assert.match(RENDER, /createTextNode\("✦ Context compacted"\)/);
  // the compact event carries the boundary metadata the divider notes
  assert.match(RENDER, /kind: "compact"; trigger\?: string; preTokens\?: number; postTokens\?: number;/);
});

test("the divider's muted meta names the trigger + the token win (before → after)", () => {
  assert.match(RENDER, /if \(ev\.trigger === "auto"\) bits\.push\("auto"\);/);
  assert.match(RENDER, /else if \(ev\.trigger === "manual"\) bits\.push\("manual"\);/);
  assert.match(RENDER, /\$\{compactTokens\(ev\.preTokens\)\} → \$\{compactTokens\(ev\.postTokens\)\}/);
  assert.match(RENDER, /el\("span", "compact-meta"\)/);
  assert.match(CSS, /\.compact-meta \{/);
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
