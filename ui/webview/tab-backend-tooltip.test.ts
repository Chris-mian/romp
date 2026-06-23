// The chat tab's hover tooltip — a CUSTOM DOM tooltip (a native `title` can't colour/bold). v2 (the user
// 2026-06-23): backend BOLD in the session's OWN romp identity colour (no fixed per-backend colour, no
// session name), the full directory path, the git branch, mode/model/effort, the context BATTERY (not a
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

test("backend is bold in the session's OWN identity colour; name + fixed per-backend colours dropped (v2)", () => {
  assert.match(RENDER, /if \(s\.color\?\.bg\) b\.style\.color = s\.color\.bg;/);
  assert.match(CSS, /\.tab-tip-be \{[\s\S]*?font-weight: 700/);
  assert.doesNotMatch(RENDER, /tab-tip-name/);             // session name dropped
  assert.doesNotMatch(CSS, /\.be-sdk|\.be-tmux/);          // fixed per-backend colours gone
});

test("v3: git branch + context battery + a labelled Summary row + a recency-coloured Latest top-goal row", () => {
  assert.match(RENDER, /rows\.push\(\["Branch", sys\.gitBranch\]\)/);                 // git branch from the system event
  assert.match(RENDER, /const bar = ctxBar\(\); setCtxBar\(bar, s\.status\.ctx/);     // the battery widget, not "X%"
  assert.match(RENDER, /const lg = ledgers\.get\(s\.id\)/);
  assert.match(RENDER, /k\.textContent = "Summary"[\s\S]*?v\.textContent = lg\.summary/);   // labelled Summary row
  // Latest row = the collapsed ledger's current-top-goal, recency-coloured via nodeRecency
  assert.match(RENDER, /stampSubtreeRecency\(lg\.tree, lg\.current/);
  assert.match(RENDER, /const top = currentTopGoal\(lg\.tree\)/);
  assert.match(RENDER, /k\.textContent = "Latest"/);
  assert.match(RENDER, /const rec = nodeRecency\(top\)/);
  assert.match(RENDER, /ago\.style\.color = ageColorReadable\(now - rec\)/);          // recency colour
  assert.doesNotMatch(CSS, /\.tab-tip-latest/);                                       // bare-paragraph latest line gone
});

test("the tooltip still shows the full path + mode/model/effort", () => {
  assert.match(RENDER, /el\("div", "tab-tip-path"\); d\.textContent = s\.cwd/);
  assert.match(RENDER, /rows\.push\(\["Mode", prettyMode\(s\.status\.mode\)\]\)/);
  assert.match(RENDER, /rows\.push\(\["Model", s\.status\.model\]\)/);
  assert.match(RENDER, /rows\.push\(\["Effort", s\.status\.effort\]\)/);
});
