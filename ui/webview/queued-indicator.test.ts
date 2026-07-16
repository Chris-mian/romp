// The "queued" indicator (the user's messages submitted while a session is still working). It's the SAME
// generic {kind:"queued"} ChatEvent for BOTH backends — the kernel feeds it from the transcript queue-ops
// for tmux and from SdkBackend.pending_queued for SDK (business 2026-06-23). So pinning the one render path
// confirms the dot shows for either backend. The renderer has no jsdom harness, so pin the wiring at source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("a queued ChatEvent carries the pending messages (backend-agnostic, per-message md)", () => {
  // idx = backend-queue position (SDK); park = _pending_ops position (compaction/model parking, any backend)
  // `optimistic` (romp's own unconfirmed echo) rides along at the end — see optimistic-send.test.ts
  assert.match(RENDER, /kind: "queued"; texts: \{ md: string; followUp\?: boolean; goal\?: string; fuCtx\?: string; idx\?: number; park\?: number; cancelable\?: boolean; optimistic\?: boolean \}\[\]/);
});

test("renderQueued draws a wireframe-hourglass header (singular/plural) + one markdown bubble per queued message", () => {
  assert.match(RENDER, /ev\.kind === "queued"\) return renderQueued\(ev\)/);
  assert.match(RENDER, /el\("div", "turn turn-queued"\)/);
  // header: a stroked accent-blue hourglass ICON (no ⌛ emoji) + "N queued message(s)" — pluralizes on count
  assert.doesNotMatch(RENDER, /⌛/, "no hourglass emoji — it clashes with the app's line-icon style");
  assert.match(RENDER, /head\.appendChild\(hourglassIcon\(\)\)/);
  assert.match(RENDER, /function hourglassIcon\(\): HTMLElement/);
  assert.match(RENDER, /stroke="currentColor"[\s\S]*?<path d="M4 3 H12 L8 8 L12 13 H4 L8 8 Z"\/>/, "wireframe hourglass path");
  // noun matches the content: all-commands → "command", all-prose → "message", mixed → "item" (the user 2026-07-01)
  assert.match(RENDER, /const noun = nCmd === n \? "command" : nCmd === 0 \? "message" : "item";/);
  assert.match(RENDER, /label\.textContent = `\$\{n\} queued \$\{noun\}\$\{n === 1 \? "" : "s"\}`/);
  assert.match(RENDER, /el\("div", "queued-head"\)/);
  // one faint "you" bubble per pending message, rendered as markdown (like a landed message)
  assert.match(RENDER, /for \(const t of ev\.texts\)[\s\S]*?el\("div", "queued-bubble md" \+ \(t\.cancelable \? " cancelable" : ""\)\)/);
  assert.match(RENDER, /if \(!isCmd\) bubble\.innerHTML = md\(t\.md\)/);
});

test("a queued slash command renders as a command chip, not a plain 'message' (the user 2026-07-01)", () => {
  // the SAME helper the landed user turn uses, so a queued /compact reads as a COMMAND
  assert.match(RENDER, /function renderSlashCmd\(bubble: HTMLElement, text: string\): boolean/);
  assert.match(RENDER, /el\("span", "slash-cmd-chip"\)/);
  // the header counts commands vs. prose to pick the noun
  assert.match(RENDER, /const nCmd = ev\.texts\.filter\(\(t\) => SLASH_CMD_RE\.test\(t\.md\)\)\.length;/);
});

test("a cancelable queued bubble carries an explicit ✕ — messages AND parked commands (the user 2026-07-08)", () => {
  // both queues cancel: the backend's own (idx) and ops parked during compaction/model switches (park)
  assert.match(RENDER, /if \(t\.cancelable && \(t\.idx !== undefined \|\| t\.park !== undefined\)\)/);
  assert.match(RENDER, /el\("button", "queued-x"\)/);
  assert.match(RENDER, /x\.dataset\.act = "qx";/, "the ✕ routes through the stable document.body delegate");
  assert.match(RENDER, /if \(t\.idx !== undefined\) x\.dataset\.qidx = String\(t\.idx\);/);
  assert.match(RENDER, /if \(t\.park !== undefined\) x\.dataset\.qpark = String\(t\.park\);/);
  // the OLD whole-bubble click is gone — it was undiscoverable and a per-render listener (mid-press
  // rebuilds ate the click); the bubble itself must carry no listener now
  assert.doesNotMatch(RENDER, /bubble\.addEventListener\("click"/);
  assert.doesNotMatch(CSS, /\.queued-bubble\.cancelable \{ cursor: pointer/);
  assert.match(CSS, /\.queued-x \{/);
  assert.match(CSS, /\.queued-x:hover \{ color: var\(--vscode-errorForeground/, "red on hover = the remove reading");
});

test("the delegated qx handler cancels click-safely: kernel op + composer restore for messages only", () => {
  // one handler on document.body (stable across every per-push rebuild) — never a per-render listener
  assert.match(RENDER, /qx: \(el\) => \{/);
  assert.match(RENDER, /\{ type: "cancelQueued", id: activeId, md: qmd \}/, "the body rides along as the kernel's drift guard");
  assert.match(RENDER, /if \(el\.dataset\.qidx !== undefined\) msg\.idx = Number\(el\.dataset\.qidx\);/);
  assert.match(RENDER, /if \(el\.dataset\.qpark !== undefined\) msg\.park = Number\(el\.dataset\.qpark\);/);
  // a MESSAGE returns to the composer to re-edit; a slash COMMAND (qcmd) just cancels
  assert.match(RENDER, /if \(qmd && el\.dataset\.qcmd !== "1"\) restoreToComposer\(qmd\);/);
  assert.match(RENDER, /el\.closest\("\.queued-bubble"\)\?\.remove\(\)/, "optimistic removal before the next push");
  // restoreToComposer fills the composer textarea, fires input (autosize/enable), focuses, caret to end
  assert.match(RENDER, /function restoreToComposer\(text: string\)/);
  assert.match(RENDER, /getElementById\("composer-input"\)/);
  assert.match(RENDER, /dispatchEvent\(new Event\("input"/);
});

test("the queued-header hourglass uses the accent blue, like the feed/mail toggle icons", () => {
  assert.match(CSS, /\.queued-head \.queued-icon \{ color: var\(--accent\)/);
});

test("the queued turn + bubbles are styled (so the dot is actually visible)", () => {
  assert.match(CSS, /\.turn-queued/);
  assert.match(CSS, /\.queued-head/);
  assert.match(CSS, /\.queued-bubble/);
});
