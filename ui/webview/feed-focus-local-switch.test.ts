import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

// T416 (the user 2026-09-14): the feed's focused-session section follows a tab change AT ONCE, whatever surface the
// change came from. Measured on the served page, the kernel's relay is one to two frames; the lag was the feed's own
// hover-freeze parking the kernel's frame while the pointer rested on the header or card the reader had just clicked.
// The section now moves on the LOCAL signal: this pane's own jump (noted in the one place every jump passes, the host
// api's postMessage) and the chat's tab change handed across the page by the shell; the kernel's frame reconciles
// under a pending record (the strip's rule). T414's jump scroll rides the same switch, so no record waits on a frame.
// These pins hold the mechanism's shape; the served labs execute it (tests/test_feed_focus_latency_served.py on the
// dashboard page, tests/test_feed_focus_scroll_served.py on the feed page).
const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const KERNEL = fs.readFileSync(path.resolve(process.cwd(), "..", "kernel", "kernel.py"), "utf8");
const slice = (src: string, from: string, to: string): string => {
  const a = src.indexOf(from);
  assert.ok(a >= 0, "missing: " + from);
  const b = src.indexOf(to, a);
  assert.ok(b > a, "missing after " + from + ": " + to);
  return src.slice(a, b);
};

test("every jump this pane posts is noted in ONE place, the host api's postMessage; no click handler notes its own", () => {
  assert.match(FEED, /const vscodeApi = hostApi \? \{ postMessage: \(m: any\) => \{ noteOwnJump\(m\); hostApi\.postMessage\(m\); \} \} : undefined;/,
    "the wrapper every post passes: the split summary's paragraphs, the session headers, the chips, all of them");
  assert.doesNotMatch(FEED, /noteFocusJump|pendingFocusScroll|settleFocusScroll|progScrollGuard/,
    "no per-handler note, no record waiting on a kernel frame, no scroll guard (T414's first cut, folded here)");
  const fn = slice(FEED, "function noteOwnJump(", "function applyLocalFocus(");
  assert.match(fn, /if \(!m \|\| \(m\.type !== "openSession" && m\.type !== "showOnTimeline"\)\) return;/, "the two posts that jump into a session");
  assert.match(fn, /if \(!sid \|\| !focusedIdentity\(sid\)\.live\) return;/, "a closed session's jump changes no tab (the chat's confirmRevive), so it moves nothing here");
  assert.match(fn, /applyLocalFocus\(sid, true\);/, "this pane's own jump: the switch and the T414 scroll together");
});

test("the local switch paints at once through the hover-freeze, defers only to an open card menu, and scrolls to the top on this pane's own jump", () => {
  const fn = slice(FEED, "function applyLocalFocus(", "// The section's OWN block layout (T410");
  assert.match(fn, /const changed = sid !== focusedSid;\s*\n\s*focusedSid = sid;\s*\n\s*if \(changed\) focusPending = \{ sid, age: 0 \};/,
    "the pending record holds the locally applied session; an unchanged one has nothing to reconcile");
  assert.match(fn, /if \(!showFocused\) return;/, "with the section off nothing paints or scrolls");
  assert.doesNotMatch(fn, /freezeKey/, "the pointer resting on the clicked card is no gate: the reader's own gesture, never a push");
  assert.match(fn, /if \(tabScopeKey\) focusStale = true;[^\n]*\n\s*else \{ render\(\); focusStale = false; \}/, "an open card menu's anchor stands; else the paint is the switch");
  assert.match(fn, /if \(jump\) scrollFeedTop\(\);/, "the jump scroll rides the switch, the already-focused session included");
  const top = slice(FEED, "function scrollFeedTop(", "/** This pane's own jump");
  assert.match(top, /list\.scrollTop = 0;/, "a plain scroll to the top of the feed's box");
  assert.doesNotMatch(top, /scrollTo\(|behavior|smooth|scrollIntoView|requestAnimationFrame|setTimeout/, "no animated chase, no clock");
});

test("the shell's relay of the chat's tab change is a local signal too, without the jump scroll", () => {
  assert.match(FEED, /if \(m\.romp === "activeChat"\) \{ applyLocalFocus\(typeof m\.id === "string" && m\.id \? m\.id : null, false\); return; \}/,
    "a strip click or a hot key in the chat lands here ahead of the kernel's frame");
});

test("the kernel's frame reconciles: the pending session's frame settles, a disagreeing one yields until two in a row or a reaffirm, an unchanged one is no event", () => {
  const branch = slice(FEED, '} else if (m.type === "activeChat") {', '} else if (m.type === "hoverCards") {');
  assert.match(branch, /const id = typeof m\.id === "string" && m\.id \? m\.id : null;/);
  assert.match(branch, /if \(focusPending\) \{\s*\n\s*if \(m\.reaffirm \|\| id === focusPending\.sid\) focusPending = null;\s*\n\s*else if \(\+\+focusPending\.age < FOCUS_PENDING_MAX_AGE\) return;\s*\n\s*else focusPending = null;\s*\n\s*\}/,
    "the strip's pending rule (tab-meta.ts): echo clears, disagreement ages, the kernel's answer wins at once");
  assert.match(FEED, /const FOCUS_PENDING_MAX_AGE = 2;/);
  assert.match(branch, /if \(id === focusedSid\) return;\s*\n\s*focusedSid = id;/, "an unchanged session is no event");
  assert.match(branch, /if \(!showFocused\) return;\s*\n\s*if \(freezeKey \|\| tabScopeKey\) \{ focusStale = true; return; \}\s*\n\s*render\(\);/,
    "a kernel frame that does change the session still waits for the hover release (T347's contract, for pushes)");
  assert.doesNotMatch(branch, /setTimeout|setInterval|requestAnimationFrame/);
});

test("the chat tells the shell its tab on every switch, and re-announces it when a jump reached a closed session", () => {
  const fn = slice(RENDER, "function notifyActive() {", "// Move id to the front of the recency stack");
  assert.match(fn, /if \(vscodeApi\) vscodeApi\.postMessage\(\{ type: "activeTab", id: activeId \}\);/, "the kernel's copy, unchanged");
  assert.match(fn, /window\.parent\.postMessage\(\{ romp: "activeTab", id: activeId \}, "\*"\)/, "the shell's copy, for the feed pane on the same page");
  assert.match(RENDER, /else if \(m\.type === "confirmRevive" && m\.id\) \{\s*\n\s*notifyActive\(\);/,
    "no tab changed: the standing tab is re-announced, so a section that moved on the click comes back");
});

test("the shell hands the chat's tab to the feed pane, from a child frame of this page only", () => {
  assert.match(KERNEL, /if\(!m\|\|m\.romp!=='activeTab'\|\|!e\.source\|\|e\.source===window\|\|e\.origin!==location\.origin\)return;/, "a chat column of this page, same origin");
  assert.match(KERNEL, /var ff=document\.getElementById\('f-feed'\);try\{ff&&ff\.contentWindow&&ff\.contentWindow\.postMessage\(\{romp:'activeChat',id:\(typeof m\.id==='string'\?m\.id:null\)\},'\*'\);\}catch\(x\)\{\}\}\);/,
    "the feed pane gets {romp:'activeChat', id}");
});

test("the kernel answers a jump that reached a closed session with a marked activeChat frame for the asking window's feeds", () => {
  const fn = slice(KERNEL, "def _send_active_chat(client, reaffirm=False):", "def _forget_active_chat_if_last(client):");
  assert.match(fn, /if reaffirm:\s*\n(\s*#[^\n]*\n)*\s*frame\["reaffirm"\] = True\s*\n\s*frame\["nonce"\] = _next_nonce\(\)/, "marked, and never swallowed by the slot's dedup");
  assert.match(fn, /def _reaffirm_active_chat\(client\):/);
  const dead = slice(KERNEL, "def _reveal_or_confirm(sid, focus_msg, client=None):", "def _folder_opener():");
  assert.match(dead, /_reveal_chat_for\(client, \{"type": "confirmRevive", "id": sid, "name": _name_of\(sid\) or sid\}\)\s*\n\s*if client:\s*\n\s*_reaffirm_active_chat\(client\)/,
    "the confirmRevive answer reaches the window's feeds as the reaffirm");
});
