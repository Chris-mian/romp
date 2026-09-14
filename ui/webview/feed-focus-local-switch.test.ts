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
  assert.match(fn, /if \(inRender \|\| inModalRender \|\| !\(inInputEvent\(\) \|\| frameGesture\)\) return;/,
    "only a post made inside the reader's input event (or a frame carrying their gesture: a bell click, a notification tap) and outside a render is a jump (rounds two and three)");
  assert.match(FEED, /\} else if \(m\.sid\) \{\s*\n\s*frameGesture = !!m\.gesture;[^\n]*\n\s*try \{ vscodeApi\?\.postMessage\(\{ type: "openSession", id: String\(m\.sid\) \}\); \} finally \{ frameGesture = false; \}/,
    "the revealCard fallback honours the gesture the shell marked on the frame, for that post alone");
  assert.match(fn, /if \(!sid \|\| !focusedIdentity\(sid\)\.live\) return;/, "a closed session's jump changes no tab (the chat's confirmRevive), so it moves nothing here");
  assert.match(fn, /applyLocalFocus\(sid, m\.type === "showOnTimeline", true, null\);/,
    "this pane's own jump: a Summary or card jump (showOnTimeline) switches and scrolls, a session name or peer chip (openSession) only switches (round two)");
});

test("render time is marked from the paint gate to the end of render, on the empty exit, and around the modal's paint; the group modal's title handler is braced", () => {
  const render = slice(FEED, "function render() {", "let focusStale = false;");
  assert.match(render, /applyFollowMove\(asks\);[^\n]*\n\s*inRender = true;[^\n]*\n\s*try \{ renderBody\(list\); \} finally \{ inRender = false; \}[^\n]*\n\}\s*\nfunction renderBody\(list: HTMLElement\) \{/,
    "set after the hidden-paint gate and the follow-up move (both pinned elsewhere), cleared in a finally around the body (round three: one throw inside render left the mark set and refused the next jump)");
  assert.doesNotMatch(FEED, /^\s*inRender = false;\s*$/m, "no bare clearing: the finally is the one");
  assert.match(FEED, /function renderModal\(\) \{\s*\n\s*inModalRender = true;[^\n]*\n\s*try \{ renderModalNow\(\); \} finally \{ inModalRender = false; \}\s*\n\}/, "the modal's paint is render time too");
  assert.match(FEED, /ttlEl\.onclick = \(\) => \{ focusEcho\(grp\.sid\); vscodeApi\?\.postMessage\(\{ type: "showOnTimeline", itemId: gm0\.itemId, sid: grp\.sid, t: grp\.t, anchor: "prompt", anchorUuid: gm0Prompt \}\); \};/,
    "the pre-existing fault the wrapper amplified: the group modal's title posted its jump at render time (the braces were missing)");
  assert.doesNotMatch(FEED, /onclick = \(\) => focusEcho\([^\n]*\); vscodeApi\?\.postMessage/, "no other handler assignment posts outside its braces");
});

test("the local switch paints at once through the hover-freeze, defers only to an open card menu, and scrolls to the top on this pane's own jump", () => {
  const fn = slice(FEED, "function applyLocalFocus(", "// The section's OWN block layout (T410");
  assert.match(fn, /const changed = sid !== focusedSid;\s*\n\s*focusedSid = sid;\s*\n\s*if \(changed\) focusPending = \{ sid, nonce \};/,
    "the pending record holds the locally applied session and the chat's announcement number; an unchanged one has nothing to reconcile");
  assert.match(fn, /else if \(focusPending && focusPending\.sid === sid && nonce != null\) focusPending\.nonce = nonce;/,
    "the chat's announcement of the switch this pane made adopts its number: that echo is the one to wait for");
  assert.match(fn, /if \(!showFocused\) return;/, "with the section off nothing paints or scrolls");
  assert.match(fn, /if \(changed \|\| \(gesture && focusStale\)\) \{\s*\n\s*if \(tabScopeKey \|\| \(!gesture && freezeKey\)\) focusStale = true;[^\n]*\n\s*else \{ render\(\); focusStale = false; \}/,
    "the reader's gesture paints whether or not it changed the record, releasing a paint the kernel's frame parked under a held card (round three); a kernel-driven switch under a held card defers like a push; an open card menu's anchor stands");
  assert.match(fn, /if \(jump\) scrollFeedTop\(\);/, "the jump scroll rides the switch, the already-focused session included");
  const top = slice(FEED, "function scrollFeedTop(", "/** This pane's own jump");
  assert.match(top, /list\.scrollTop = 0;/, "a plain scroll to the top of the feed's box");
  assert.doesNotMatch(top, /scrollTo\(|behavior|smooth|scrollIntoView|requestAnimationFrame|setTimeout/, "no animated chase, no clock");
});

test("the shell's relay of the chat's tab change is a local signal too, tagged with the gesture and the announcement number, without the jump scroll", () => {
  assert.match(FEED, /if \(m\.romp === "activeChat"\) \{ applyLocalFocus\(typeof m\.id === "string" && m\.id \? m\.id : null, false, !!m\.gesture, typeof m\.nonce === "number" \? m\.nonce : null\); return; \}/,
    "a strip click or a hot key in the chat lands here without waiting for the kernel's frame");
});

test("the kernel's frame reconciles: only the echo (the pending session and its announcement number) or the marked reaffirm clears the record; a disagreeing frame yields and never wins by count; an unchanged session is no event", () => {
  const branch = slice(FEED, '} else if (m.type === "activeChat") {', '} else if (m.type === "hoverCards") {');
  assert.match(branch, /const id = typeof m\.id === "string" && m\.id \? m\.id : null;\s*\n\s*const nonce = typeof m\.nonce === "number" \? m\.nonce : null;/);
  assert.match(branch, /if \(focusPending\) \{\s*\n(\s*\/\/[^\n]*\n)*\s*const echo = id === focusPending\.sid && \(focusPending\.nonce == null \|\| nonce == null \|\| nonce >= focusPending\.nonce\);\s*\n\s*if \(!m\.reaffirm && !echo\) return;\s*\n\s*focusPending = null;\s*\n\s*\}/,
    "an event, never a count (round two): the echo or the kernel's marked answer, nothing else; the echo is an agreeing frame at or above the record's number (round three: a re-announce after a socket flap must not leave the record standing for the page's life)");
  assert.match(branch, /one ordered socket, so an echo can never overtake an earlier frame/, "the caveat for a second delivery path is written where the rule lives");
  assert.doesNotMatch(FEED, /FOCUS_PENDING_MAX_AGE|focusPending\.age/, "no age, no count");
  assert.match(branch, /if \(id === focusedSid\) return;\s*\n\s*focusedSid = id;/, "an unchanged session is no event");
  assert.match(branch, /if \(!showFocused\) return;\s*\n\s*if \(freezeKey \|\| tabScopeKey\) \{ focusStale = true; return; \}\s*\n\s*render\(\);/,
    "a kernel frame that does change the session still waits for the hover release (T347's contract, for pushes)");
  assert.doesNotMatch(branch, /setTimeout|setInterval|requestAnimationFrame/);
});

test("the chat tells the shell its tab on every switch with its announcement number and whether the reader made it, and re-announces it when a jump reached a closed session or landed on the tab already shown", () => {
  const fn = slice(RENDER, "function notifyActive() {", "// Move id to the front of the recency stack");
  assert.match(RENDER, /let activeTabNonce = 0;/);
  assert.match(fn, /const nonce = \+\+activeTabNonce;\s*\n\s*const gesture = inInputEvent\(\);/, "one number per announcement; the gesture read off the event under dispatch");
  assert.match(fn, /if \(vscodeApi\) vscodeApi\.postMessage\(\{ type: "activeTab", id: activeId, nonce \}\);/, "the kernel's copy carries the number it echoes");
  assert.match(fn, /window\.parent\.postMessage\(\{ romp: "activeTab", id: activeId, nonce, gesture \}, "\*"\)/, "the shell's copy, for the feed pane on the same page, tagged");
  assert.match(RENDER, /if \(activeId === m\.id\) notifyActive\(\);/,
    "a focus that lands on the tab already shown is announced again, anchored or not, so the feed's pending record gets its echo (round three: the anchored road announced nothing when another column held the session)");
  assert.match(RENDER, /else if \(m\.type === "confirmRevive" && m\.id\) \{\s*\n\s*revealSelfPane\(\);[^\n]*\n\s*notifyActive\(\);/,
    "no tab changed: the standing tab is re-announced (after the pane's own reveal, whose pin in tests/test_per_viewer_focus.py opens the branch), so a section that moved on the click comes back");
});

test("the shell hands the chat's tab to the feed pane, from a child frame of this page only", () => {
  assert.match(KERNEL, /if\(!m\|\|m\.romp!=='activeTab'\|\|!e\.source\|\|e\.source===window\|\|e\.origin!==location\.origin\)return;/, "a chat column of this page, same origin");
  assert.match(KERNEL, /var ff=document\.getElementById\('f-feed'\);try\{ff&&ff\.contentWindow&&ff\.contentWindow\.postMessage\(\{romp:'activeChat',id:\(typeof m\.id==='string'\?m\.id:null\),nonce:\(typeof m\.nonce==='number'\?m\.nonce:null\),gesture:!!m\.gesture\},'\*'\);\}catch\(x\)\{\}\}\);/,
    "the feed pane gets {romp:'activeChat', id, nonce, gesture}");
  assert.equal((KERNEL.match(/\{romp:'revealCard',itemId:[^}]*,gesture:true\}/g) || []).length, 2, "both revealCard posts (the bell click, the notification tap) carry the reader's gesture (round three)");
});

test("the kernel answers a jump that reached a closed session with a marked activeChat frame for the asking window's feeds", () => {
  const fn = slice(KERNEL, "def _send_active_chat(client, reaffirm=False):", "def _forget_active_chat_if_last(client):");
  assert.match(fn, /if reaffirm:\s*\n(\s*#[^\n]*\n)*\s*frame\["reaffirm"\] = True\s*\n\s*frame\["nonce"\] = _next_nonce\(\)/, "marked, and never swallowed by the slot's dedup");
  assert.match(fn, /if _ACTIVE_CHAT_NONCE_BY_WID\.get\(wid\) is not None:\s*\n\s*frame\["nonce"\] = _ACTIVE_CHAT_NONCE_BY_WID\[wid\]/, "the chat's announcement number rides the relayed frame: the echo");
  assert.match(KERNEL, /_relay_active_chat\(client, msg\.get\("id"\), msg\.get\("nonce"\)\)/, "the activeTab arm hands the number to the relay");
  assert.match(fn, /def _reaffirm_active_chat\(client\):/);
  const dead = slice(KERNEL, "def _reveal_or_confirm(sid, focus_msg, client=None):", "def _folder_opener():");
  assert.match(dead, /_reveal_chat_for\(client, \{"type": "confirmRevive", "id": sid, "name": _name_of\(sid\) or sid\}\)\s*\n\s*if client:\s*\n\s*_reaffirm_active_chat\(client\)/,
    "the confirmRevive answer reaches the window's feeds as the reaffirm");
});
