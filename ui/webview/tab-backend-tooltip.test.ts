// The chat tab's hover tooltip — a CUSTOM DOM tooltip (a native `title` can't colour/bold its text)
// showing the backend BOLD in its own colour (sdk=blue, tmux=green), the full directory path, and
// mode / model / effort / context each on its own line (the user 2026-06-23). Source-pin over render.ts +
// styles.css. (Supersedes the v1 native-title tooltip.)
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
  assert.doesNotMatch(RENDER, /tab\.title = s\.name \+ " · " \+ beLabel/);   // v1 native title gone
});

test("the tooltip shows the backend BOLD in its own colour (sdk=blue, tmux=green)", () => {
  assert.match(RENDER, /el\("div", "tab-tip-be " \+ \(be === "sdk" \? "be-sdk" : "be-tmux"\)\)/);
  assert.match(CSS, /\.tab-tip-be \{[\s\S]*?font-weight: 700/);
  assert.match(CSS, /\.tab-tip-be\.be-sdk \{ color: var\(--check-bg\)/);     // romp blue
  assert.match(CSS, /\.tab-tip-be\.be-tmux \{ color: var\(--green\)/);        // romp green
});

test("the tooltip shows the full path + mode/model/effort/context, each on its own line", () => {
  assert.match(RENDER, /el\("div", "tab-tip-path"\); d\.textContent = s\.cwd/);
  assert.match(RENDER, /rows\.push\(\["Mode", prettyMode\(s\.status\.mode\)\]\)/);
  assert.match(RENDER, /rows\.push\(\["Model", s\.status\.model\]\)/);
  assert.match(RENDER, /rows\.push\(\["Effort", s\.status\.effort\]\)/);
  assert.match(RENDER, /rows\.push\(\["Context", s\.status\.ctx \+ "%"\]\)/);
  assert.match(CSS, /\.tab-tip-row \{ display: flex/);
});
