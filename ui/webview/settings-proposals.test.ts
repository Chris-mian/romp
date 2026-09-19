// Settings across machines, phase one A (plans/settings-across-machines.md; the user 2026-09-18): a remote machine's newer
// pick is never applied silently. The browser's part: (1) federation stamps every broadcast KERNEL_SETTING copy with its
// ORIGIN ("local" to this dashboard's own kernel, "remote" to every attached host), the field a pinned kernel stands a remote
// click down on; (2) the gear draws the pending proposal /version reports under the affected row, with Apply and Keep mine
// posting the answer to /setting-proposal with the proposal's stamp, and a pinned store's note. routeOutbound is executed;
// the gear, which has no jsdom harness, is pinned at the source with its sheet.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { routeOutbound, LOCAL } from "../../ui/webview/federation";

const GEAR = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "gear.js"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "gear.css"), "utf8");
const FED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "federation.ts"), "utf8");

test("a broadcast kernel setting carries its origin per copy: local to this kernel, remote to every attached host", () => {
  const routes = routeOutbound({ type: "setTaskTracking", enabled: false, gt: 1234 }, new Set(["TESTHOSTA", "TESTHOSTB"]));
  assert.deepEqual(routes.map((r) => [r.host, (r.msg as any).origin]), [[LOCAL, "local"], ["TESTHOSTA", "remote"], ["TESTHOSTB", "remote"]],
    "one copy per kernel, each stamped with where the click came from relative to it");
  for (const r of routes) assert.deepEqual({ ...(r.msg as any), origin: undefined }, { type: "setTaskTracking", enabled: false, gt: 1234, origin: undefined }, "the message itself is unchanged: type, value and the ORIGINAL stamp");
  const solo = routeOutbound({ type: "setAutoNudge", enabled: true, gt: 5 });
  assert.deepEqual(solo.map((r) => [r.host, (r.msg as any).origin]), [[LOCAL, "local"]], "a single kernel: the local copy alone");
  const other = routeOutbound({ type: "setThinkingSummaries", enabled: true, gt: 7 }, new Set(["TESTHOSTA"]));
  assert.ok(other.every((r) => (r.msg as any).origin === undefined), "a per-install setting is not a KERNEL_SETTING and carries no origin");
  assert.match(FED, /msg: \{ \.\.\.msg, origin: h === LOCAL \? "local" : "remote" \}/, "the stamp at the fan-out, per copy");
  // a PIN (round two): the local kernel alone, stamped local, the one origin its kernel takes a pin from
  const pin = routeOutbound({ type: "setSettingPin", store: "task-tracking", pinned: true, gt: 9 }, new Set(["TESTHOSTA"]));
  assert.deepEqual(pin.map((r) => [r.host, (r.msg as any).origin, (r.msg as any).store]), [[LOCAL, "local", "task-tracking"]], "never to an attached host");
});

test("the gear draws a pending proposal under its row with Apply and Keep mine, both posting the answer with the proposal's stamp", () => {
  assert.match(GEAR, /var PROPOSAL_ROWS = \{ 'auto-nudge': 'rs-autonudge', 'compact-suggest': 'rs-suggestcompact', 'file-editing': 'rs-fileedit', 'task-tracking': 'rs-tasktrack' \};/,
    "the four synchronized stores, each to its row");
  assert.match(GEAR, /fillProposals\(v\);\s+\/\/ the pending proposals and this machine's pins under their rows/, "fill() draws them from the same /version read");
  assert.match(GEAR, /txt\.textContent = \(p\.host \|\| 'Another machine'\) \+ ' proposes ' \+ \(p\.value \? 'on' : 'off'\) \+ '; this machine is ' \+ \(p\.current \? 'on' : 'off'\) \+ '\.';/,
    "which machine, from what to what, in the user's terms");
  assert.match(GEAR, /apply\.textContent = 'Apply';/); assert.match(GEAR, /keep\.textContent = 'Keep mine';/);
  assert.match(GEAR, /answerProposal\(store, p\.host, p\.gt, 'apply'\)/); assert.match(GEAR, /answerProposal\(store, p\.host, p\.gt, 'keep'\)/);
  assert.match(GEAR, /rows\.forEach\(function \(p\) \{/, "one line per proposing machine (round two: records are per store and machine)");
  assert.match(GEAR, /fetch\(ku\('\/setting-proposal'\), \{ method: 'POST', headers: \{ 'Content-Type': 'application\/json' \},\s*\n\s*body: JSON\.stringify\(\{ store: store, host: host, gt: gt, answer: answer \}\) \}\)/,
    "the answer rides the route with the stamp the line was drawn for; a moved proposal is refused there and the re-fill shows the new one");
  assert.match(GEAR, /if \(res && res\.ok === false && res\.error\) staleToast\(res\.error\); fill\(\);/, "a refusal is toasted in the modal's own vocabulary, then the panel re-fills");
  assert.match(GEAR, /pin\.textContent = 'Pinned on this machine: other machines\\' picks are not applied here\.';/, "a pinned store says so under its row");
  assert.match(GEAR, /row\.parentNode\.insertBefore\(line, row\.nextSibling\);/, "the line sits right under the row");
});

test("gear.css: the proposal line wears the row's line size and the toast's action dress, through the tokens", () => {
  assert.match(CSS, /#rsettings \.rs-proposal \{[^}]*font-size: 11px; color: var\(--text-muted, #9aa0a6\); \}/);
  assert.match(CSS, /#rsettings \.rs-proposal-act \{[^}]*border: 1px solid var\(--hairline, #3a3a3a\);\s*\n\s*background: var\(--btn-bg, #2a2a2a\); color: var\(--fg, #ccc\);/);
  assert.match(CSS, /#rsettings \.rs-proposal-act:hover \{ border-color: var\(--accent, #9cd2ff\); color: var\(--accent, #9cd2ff\);/);
  assert.match(CSS, /#rsettings \.rs-pinned \{[^}]*font-size: 11px; color: var\(--text-muted, #9aa0a6\); \}/);
  assert.doesNotMatch(CSS, /\.rs-proposal[^{]*\{[^}]*text-transform/, "sentence case, like every label in the settings");
});
