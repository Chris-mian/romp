// The chat tab's hover tooltip — a CUSTOM DOM tooltip (a native `title` can't colour/bold). The backend label
// is BOLD and coloured BY BACKEND (tmux → green #54B204, SDK → blue #1EA1EB — the canonical romp _palette
// shades; the user 2026-06-23, superseding v2's session-identity colour). Plus the full directory path, the
// git branch, mode/model/effort, the context BATTERY (not a text %), and the ledger's latest line
// recency-coloured with "(Xm ago)". Source-pin over render.ts + css.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("the session Status type carries the backend the kernel publishes", () => {
  assert.match(RENDER, /interface Status \{[^}]*backend\?: string;/);
});

test("the tab tooltip is a custom DOM tooltip shown on hover, not a native title", () => {
  assert.match(RENDER, /function showTabTip\(tab: HTMLElement, s: Session\)/);
  assert.match(RENDER, /tab\.addEventListener\("mouseenter", \(\) => showTabTip\(tab, s\)\)/);
  assert.match(RENDER, /tab\.addEventListener\("mouseleave", hideTabTip\)/);
  assert.doesNotMatch(RENDER, /tab\.title = s\.name \+ " · " \+ beLabel/);
});

test("backend is bold and coloured BY BACKEND — tmux green / SDK blue, the canonical _palette shades (the user 2026-06-23)", () => {
  // tmux → green #54B204, SDK → blue #1EA1EB (bin/romp _palette); supersedes v2's session-identity colour
  assert.match(RENDER, /b\.style\.color = be === "tmux" \? "#54B204" : "#1EA1EB";/);
  assert.doesNotMatch(RENDER, /b\.style\.color = s\.color\.bg/);   // identity colour dropped (v2 reversed)
  assert.match(CSS, /\.tab-tip-be \{[\s\S]*?font-weight: 700/);
  assert.doesNotMatch(RENDER, /tab-tip-name/);             // session name still dropped
  assert.doesNotMatch(CSS, /\.be-sdk|\.be-tmux/);          // inline hex, not per-backend CSS classes
});

test("v4: git branch + context battery + Summary row + the last 5 worked-on items, recency-coloured (the user 2026-06-24)", () => {
  assert.match(RENDER, /rows\.push\(\["Branch", sys\.gitBranch\]\)/);                 // git branch from the system event
  assert.match(RENDER, /const bar = ctxBar\(\); setCtxBar\(bar, s\.status\.ctx/);     // the battery widget, not "X%"
  assert.match(RENDER, /const lg = ledgers\.get\(s\.id\)/);
  assert.match(RENDER, /k\.textContent = "Summary"[\s\S]*?v\.textContent = lg\.summary/);   // labelled Summary row
  // "Recent" = up to FIVE most-recently-touched ledger nodes (by each node's OWN recency mt??t), each
  // text+time in its recency colour — replaces the single "Latest" top-goal line.
  assert.match(RENDER, /k\.textContent = "Recent"/);
  assert.doesNotMatch(RENDER, /k\.textContent = "Latest"/, "the single Latest line is gone");
  assert.match(RENDER, /\.map\(\(n\) => \(\{ n, t: \(n\.mt \?\? n\.t\) \|\| 0 \}\)\)/);
  assert.match(RENDER, /\.sort\(\(a, b\) => b\.t - a\.t\)\s*\n\s*\.slice\(0, 5\)/);   // newest-first, capped at 5
  assert.match(RENDER, /item\.style\.color = ageColorReadable\(now - t\)/);           // each item in its recency colour
  assert.match(CSS, /\.tab-tip-recent-list \{/);                                      // the list + per-item rules exist
  assert.match(CSS, /\.tab-tip-recent-item \{/);
});

test("the tall context battery gets vertical breathing room", () => {
  assert.match(RENDER, /el\("div", "tab-tip-row tab-tip-ctx"\)/);
  assert.match(CSS, /\.tab-tip-ctx \{ margin: 4px 0/);
});

test("the tooltip still shows the full path + mode/model/effort", () => {
  assert.match(RENDER, /el\("div", "tab-tip-path"\); d\.textContent = s\.cwd/);
  assert.match(RENDER, /rows\.push\(\["Mode", prettyMode\(s\.status\.mode\)\]\)/);
  assert.match(RENDER, /rows\.push\(\["Model", s\.status\.model\]\)/);
  assert.match(RENDER, /rows\.push\(\["Effort", s\.status\.effort\]\)/);
});
