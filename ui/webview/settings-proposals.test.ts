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
  assert.match(FED, /msg: \{ \.\.\.rest, origin: h === LOCAL \? "local" : "remote" \}/, "the stamp at the fan-out, per copy (a stray scope stripped: a broadcast never carries one)");
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
  assert.doesNotMatch(GEAR, /pin\.textContent = 'Pinned on this machine/, "the pinned NOTE folded into the row's pin glyph (phase two)");
  assert.match(GEAR, /function ensurePinGlyphs\(\)/, "one glyph per synchronized row, at the right edge");
  assert.match(GEAR, /var after = row;[^\n]*\n\s*rows\.forEach\(function \(p\) \{/, "the lines follow the row in /version's order");
  assert.match(GEAR, /after\.parentNode\.insertBefore\(line, after\.nextSibling\); after = line;/, "each line after the last drawn one, newest stamp first (round three)");
});

test("gear.css: the proposal line wears the row's line size and the toast's action dress, through the tokens", () => {
  assert.match(CSS, /#rsettings \.rs-proposal \{[^}]*font-size: 11px; color: var\(--text-muted, #9aa0a6\); \}/);
  assert.match(CSS, /#rsettings \.rs-proposal-act \{[^}]*border: 1px solid var\(--hairline, #3a3a3a\);\s*\n\s*background: var\(--btn-bg, #2a2a2a\); color: var\(--fg, #ccc\);/);
  assert.match(CSS, /#rsettings \.rs-proposal-act:hover \{ border-color: var\(--accent, #9cd2ff\); color: var\(--accent, #9cd2ff\);/);
  assert.doesNotMatch(CSS, /\.rs-pinned \{/, "the pinned note's rule left with the note (phase two: the glyph carries it)");
  assert.doesNotMatch(CSS, /\.rs-proposal[^{]*\{[^}]*text-transform/, "sentence case, like every label in the settings");
});

test("phase two: a kernel setting with a hosts list is scoped to those kernels with the scope, a broadcast never carries it, a pin is addressed", () => {
  const scoped = routeOutbound({ type: "setTaskTracking", enabled: false, gt: 1234, hosts: ["TESTHOSTA", ""] }, new Set(["TESTHOSTA", "TESTHOSTB"]));
  assert.deepEqual(scoped.map((r) => [r.host, (r.msg as any).origin, (r.msg as any).scope]), [["TESTHOSTA", "remote", "pinned"], [LOCAL, "local", "pinned"]],
    "the picked kernels alone, each copy with its origin and the scope; TESTHOSTB, unpicked, hears nothing");
  for (const r of scoped) assert.equal((r.msg as any).hosts, undefined, "the list itself does not ride: the kernel's handlers are host-blind");
  const broadcast = routeOutbound({ type: "setTaskTracking", enabled: false, gt: 1235, scope: "pinned" }, new Set(["TESTHOSTA"]));
  assert.ok(broadcast.every((r) => (r.msg as any).scope === undefined), "a broadcast never carries the scope, whatever the message claimed");
  assert.equal(broadcast.length, 2);
  const pinTo = routeOutbound({ type: "setSettingPin", store: "task-tracking", pinned: false, gt: 9, hosts: ["TESTHOSTA"] }, new Set(["TESTHOSTA"]));
  assert.deepEqual(pinTo.map((r) => [r.host, (r.msg as any).origin, (r.msg as any).scope, (r.msg as any).pinned]), [["TESTHOSTA", "remote", "pinned", false]],
    "an explicit un-pin addressed to another machine's kernel carries the scope its arm accepts");
  const pinHere = routeOutbound({ type: "setSettingPin", store: "task-tracking", pinned: true, gt: 10 });
  assert.deepEqual(pinHere.map((r) => [r.host, (r.msg as any).origin, (r.msg as any).scope]), [[LOCAL, "local", undefined]], "no list: the local kernel alone, no scope, as in one A");
});

test("phase two: the gear's machine selector above the tabs, the scoped rows, the differs badge and the pin glyph", () => {
  assert.match(GEAR, /'<div id=rs-scope hidden><button id=rs-scope-btn type=button aria-haspopup=listbox aria-expanded=false>'/, "the selector, hidden until more than one kernel");
  assert.ok(GEAR.indexOf("id=rs-scope") < GEAR.indexOf("'<div class=rs-tabs id=rs-tabs role=tablist>'"), "…above the tabs");
  assert.match(GEAR, /<span id=rs-scope-label>All kernels<\/span><span id=rs-scope-count class=rs-differs hidden><\/span>/, "All kernels by default, the count of differing rows beside it");
  assert.match(GEAR, /function scoped\(m\) \{[^}]*refillSoon\(\);[^}]*m\.hosts = scopeHosts\.slice\(\); m\.scope = 'pinned';/, "a change under a scope names the picked kernels and the scope, and the gear re-reads the kernels through the poll's cadence after every click");
  for (const t of ["setTaskTracking", "setAutoNudge", "setFileEditing", "setCompactSuggest"]) assert.match(GEAR, new RegExp("post\\(scoped\\(\\{ type: '" + t + "'"), t + " rides scoped()");
  assert.match(GEAR, /box\.hidden = !many;/, "hidden with one kernel: the settings look exactly as today");
  assert.match(GEAR, /mark\.textContent = 'differs'; mark\.classList\.add\('rs-differs'\);/, "the flag on a synchronized row in place of the quiet mark");
  assert.match(GEAR, /mark\.title = 'The kernels disagree: ' \+ vals\.join\(', '\)/, "the machines and their values on hover");
  assert.match(GEAR, /post\(\{ type: 'setSettingPin', store: store, pinned: !lit, gt: gclock\.stamp\(store\), hosts: targets, scope: 'pinned' \}\);/, "the glyph toggles the pin on the picked kernels (this machine under All)");
  assert.match(GEAR, /var pinnedAll = targets\.every\(function \(h\) \{ return !!kernelSettings\(h\)\.pinned\[store\]; \}\);/, "lit while the picked kernel pins the store");
  assert.match(GEAR, /Click to un-pin and return to the synchronized value\./, "the hover names the synchronized value and the way back");
  assert.match(CSS, /#rsettings \.rs-mixed\.rs-differs, #rsettings \.rs-differs \{ color: var\(--warn, #d7a23a\); font-weight: 600; \}/, "the warning tone, through the token");
  assert.match(CSS, /#rsettings \.rs-pin \{ margin-left: auto;/, "the glyph at the row's right edge");
});

test("phase two, round two: an empty hosts list is the broadcast, Auto Nudge wears the flag, the glyph shows for a local pin, the popover marks a pinned machine", () => {
  const empty = routeOutbound({ type: "setTaskTracking", enabled: true, gt: 1, hosts: [] }, new Set(["TESTHOSTA"]));
  assert.deepEqual(empty.map((r) => [r.host, (r.msg as any).scope, (r.msg as any).hosts]), [[LOCAL, undefined, undefined], ["TESTHOSTA", undefined, undefined]], "no scope, the list stripped: nobody was routed to before");
  const junk = routeOutbound({ type: "setTaskTracking", enabled: true, gt: 2, hosts: "TESTHOSTA" }, new Set(["TESTHOSTA"]));
  assert.equal(junk.length, 2, "a malformed list is no scope either");
  assert.match(GEAR, /\['compactSuggest', csg\], \['taskTracking', tk\], \['autoNudge', an\],/, "Auto Nudge is in the flagged set (its count was on the selector with no row flagged)");
  assert.doesNotMatch(GEAR, /else if \(box\) \{ box\.indeterminate = false; \}/, "the tri-state box is left alone when the scope is off");
  assert.match(GEAR, /function scoped\(m\) \{[^}]*\n\s*refillSoon\(\);[^}]*\n\s*if \(!scopeOn\(\)\) return m;/, "every click re-reads the kernels, so the count follows a resolved disagreement");
  assert.match(GEAR, /g\.hidden = !\(many \|\| localPinned\);/, "a store this machine pins keeps its glyph with one kernel: the un-pin is there");
  const KERNEL = fs.readFileSync(path.resolve(process.cwd(), "..", "kernel", "kernel.py"), "utf8");
  assert.ok(KERNEL.includes("function pinMark(t,th){var ps=pinnedStores(t);return ps.length?' <span class=rnet-pin title="), "the Remote kernels popover marks a pinned machine");
  assert.ok(KERNEL.includes("'<span class=nm><b>'+th+'</b>'+pinMark(t,th)+' <span class=st"), "…beside the host's name");
  assert.ok(KERNEL.includes('".rnet-pin{margin-left:6px;padding:0 6px;border-radius:9px;border:1px solid var(--accent,#9cd2ff);'), "the quiet chip dress");
});
