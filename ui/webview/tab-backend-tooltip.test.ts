// The chat tab's hover tooltip — a CUSTOM DOM tooltip (a native `title` can't colour/bold). It shows the full
// directory path, then labelled field rows — git branch, mode/model/effort, and BACKEND (a plain field now,
// the user 2026-07-08 — no longer a coloured "SDK backend" badge at the top) — the context BATTERY (not a
// text %), and the ledger's latest line recency-coloured with "(Xm ago)". Source-pin over render.ts + css.
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

test("backend is a plain labelled FIELD ROW under the others — no coloured top badge (the user 2026-07-08)", () => {
  // it's just another "Backend: SDK|tmux" row alongside Branch/Mode/Model/Effort, not a bold coloured badge
  assert.match(RENDER, /rows\.push\(\["Backend", be === "sdk" \? "SDK" : "tmux"\]\)/);
  assert.doesNotMatch(RENDER, /"tab-tip-be"/, "no dedicated backend-badge element");
  assert.doesNotMatch(RENDER, /be === "tmux" \? "#54B204" : "#1EA1EB"/, "no per-backend colour on the tooltip");
  assert.doesNotMatch(CSS, /\.tab-tip-be \b/, "the badge's CSS rule is gone");
  assert.doesNotMatch(RENDER, /tab-tip-name/);             // session name still dropped
});

test("v4: git branch + context battery + Summary row + the last 5 worked-on items, recency-coloured (the user 2026-06-24)", () => {
  assert.match(RENDER, /rows\.push\(\["Branch", s\.gitBranch\]\)/);                   // git branch from the top-level session field (resident even when the head system event is windowed out — the user 2026-06-30)
  assert.match(RENDER, /const bar = ctxBar\(\); setCtxBar\(bar, s\.status\.ctx/);     // the battery widget, not "X%"
  assert.match(RENDER, /const lg = ledgers\.get\(s\.id\)/);
  assert.match(RENDER, /k\.textContent = "Summary"[\s\S]*?v\.textContent = lg\.summary/);   // labelled Summary row
  // "Recent" = up to FIVE most-recently-touched ledger nodes (by each node's OWN recency mt??t), each
  // text+time in its recency colour — replaces the single "Latest" top-goal line.
  assert.match(RENDER, /k\.textContent = "Recent"/);
  assert.doesNotMatch(RENDER, /k\.textContent = "Latest"/, "the single Latest line is gone");
  assert.match(RENDER, /recentItems = lg\.recent\.map\(\(r\) => \(\{ text: r\.text, t: r\.t \|\| 0 \}\)\)/);   // prefer the server recent (live + archive)
  assert.match(RENDER, /recentItems = \[\.\.\.timed, \.\.\.untimed\]\.slice\(0, 5\)/);   // fallback: newest-first, capped at 5
  assert.match(RENDER, /item\.style\.color = ageColorReadable\(now - t\)/);           // each item in its recency colour
  assert.match(CSS, /\.tab-tip-recent-list \{/);                                      // the list + per-item rules exist
  assert.match(CSS, /\.tab-tip-recent-item \{/);
  // the tip spans the full chat-pane width (the user 2026-06-25) so the recent names aren't clipped at a
  // narrow fixed box; the positioner clamps it to a small left margin once it's this wide.
  assert.match(CSS, /\.tab-tip \{[\s\S]*?max-width: calc\(100vw - 12px\)/);
  assert.doesNotMatch(CSS, /\.tab-tip \{[\s\S]*?max-width: 440px/);
});

test("the Recent list has NO recency cutoff — it shows the last 5 even if days old, backfilling untimed nodes (the user 2026-06-30)", () => {
  // there is no `now - t < WINDOW` / age-threshold gate anywhere near the Recent list: an idle session must
  // still list what it last worked on rather than going blank once its work ages out.
  const recentBlock = RENDER.slice(RENDER.indexOf('k.textContent = "Recent"') - 1200, RENDER.indexOf('r.appendChild(k); r.appendChild(list)'));
  assert.doesNotMatch(recentBlock, /now - t [<>]=?|Date\.now\(\)[^;]*<|MAX_AGE|RECENT_WINDOW/, "no age cutoff on the Recent list");
  // shown REGARDLESS of completion status (the user 2026-06-30): PREFER the server `recent` (live + archive,
  // any status) so a session whose tops were all cleared still lists them; the fallback tree path is text-only
  // (does NOT exclude done / blocked / cleared)
  assert.match(RENDER, /if \(lg\?\.recent && lg\.recent\.length\) \{/);
  assert.match(RENDER, /recentItems = lg\.recent\.map\(\(r\) => \(\{ text: r\.text, t: r\.t \|\| 0 \}\)\);/);
  assert.match(RENDER, /const named = lg\.tree\.filter\(\(n\) => \(n\.text \|\| ""\)\.trim\(\)\);/);
  assert.doesNotMatch(RENDER, /!n\.cleared\)/);
  // fallback: timed nodes lead; untimed text nodes backfill so a session with >=5 goals always surfaces 5
  assert.match(RENDER, /const untimed = named\.filter\(\(n\) => !\(\(n\.mt \?\? n\.t\) \|\| 0\)\)/);
  assert.match(RENDER, /recentItems = \[\.\.\.timed, \.\.\.untimed\]\.slice\(0, 5\)/);
  // a backfilled (undated) item shows no "(ago)" label and falls back to the oldest-bucket colour
  assert.match(RENDER, /if \(t > 0\) \{[\s\S]*?agehms\(now - t\)/);
  assert.match(RENDER, /item\.style\.color = ageColorReadable\(345600\)/);
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
