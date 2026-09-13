// T402 (the user 2026-09-12): the chat's "Loading earlier messages" pill stayed on a reader at the tail and could not be dismissed.
// The rule: the pill shows only while an older-history request the reader made is outstanding; never for the page's own
// re-render or its walk to the tail; it hides when the request lands, fails, or its socket dies; a click ends the wait. Pins over
// render.ts and the sheet; the served lab (tests/test_loading_pill_browser.py) drives the three roads.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");
const fn = (name: string) => RENDER.slice(RENDER.indexOf("function " + name + "("), RENDER.indexOf("\n}\n", RENDER.indexOf("function " + name + "(")));

test("the pill is for the ACTIVE tab's outstanding reader ask only: not the virtualiser's own re-render, not the walk to the tail, not another tab's wait (T402; round two, medium 1)", () => {
  const virt = fn("virtualizeToViewport");
  assert.doesNotMatch(virt, /showLoadingPill\(\)|hideLoadingPill\(\)|syncLoadingPill\(\)/, "a re-window renders resident content and asks for nothing (T402)");
  assert.match(virt, /revirtBusy = true;\s*\n\s*\/\/ no pill here \(T402/);
  assert.match(fn("requestNewer"), /noteAsk\(sid, false\);/, "the walk toward the tail is the page's own ask: in flight, never a reader wait, never a hold on the pill");
  for (const f of ["requestOlder", "fetchOlderForAnchor"]) assert.match(fn(f), /noteAsk\(sid, true\);/, f + ": the reader's ask into unloaded history is a reader wait");
  assert.match(fn("requestAround"), /const nav = !relandAsk;[\s\S]*noteAsk\(sid, nav\);/, "requestAround: a navigation's ask is a reader wait; the re-land of the reader's own row is the page's ask and shows nothing (round three, low 2)");
  assert.match(fn("requestAround"), /if \(nav\) olderCancelled\.delete\(sid\);/, "a navigation's ask ends the click's latch: the reader's own intent (round three)");
  assert.match(fn("fetchOlderForAnchor"), /olderCancelled\.delete\(sid\);/, "the index wire's deep link too");
  for (const f of ["chatHead", "chatMore"]) assert.match(fn(f), /^\s*endAsk\(msg\.id\);/m, f + ": the reply ends the wait and re-evaluates the pill");
  assert.match(fn("chatWindow"), /^\s*if \(!cancelled\) endAsk\(msg\.id\);/m, "chatWindow: an uncancelled reply ends the wait and re-evaluates the pill; a cancelled one ends nothing (round four, medium 2)");
  assert.match(RENDER, /function syncLoadingPill\(\): void \{ if \(activeId && readerWaits\.has\(activeId\)\) showLoadingPill\(\); else hideLoadingPill\(\); \}/, "the pill follows the ACTIVE tab's reader wait");
  assert.match(RENDER, /updateLivePaused\(\);[^\n]*\n\s*syncLoadingPill\(\);/, "…re-evaluated on a tab switch, after the strip's own re-evaluation");
  assert.match(RENDER, /function noteAsk\(sid: string, reader: boolean\): void \{ loadingOlder\.add\(sid\); askedGen\.set\(sid, askGen\); if \(reader\) readerWaits\.set\(sid, askGen\); syncLoadingPill\(\); \}/);
  assert.match(RENDER, /function endAsk\(sid: string\): void \{ loadingOlder\.delete\(sid\); askedGen\.delete\(sid\); readerWaits\.delete\(sid\); syncLoadingPill\(\); \}/);
  const shows = RENDER.match(/showLoadingPill\(\);/g) || [];
  assert.equal(shows.length, 2, "the pill is shown by syncLoadingPill and the geometry lab's hook alone: " + shows.length);
});

test("a click ends the ACTIVE tab's wait and hides the pill whatever the other tabs hold; the in-flight fetch is re-pointed at the reader's own row, a landing's ask files its row as cancelled; a socket flip ends the asks made before it (round two: mediums 1 and 2, lows 1 and 4)", () => {
  const show = fn("showLoadingPill");
  assert.match(show, /loadingPillEl\.textContent = "Loading earlier messages… click to stop waiting";/, "the pill says it can be clicked away");
  assert.match(show, /loadingPillEl\.addEventListener\("click", \(\) => cancelOlderWait\("click"\)\);/);
  const cancel = fn("cancelOlderWait");
  assert.match(cancel, /const sids = why === "flip" \? \[\.\.\.loadingOlder\]\.filter\(\(sid\) => \(askedGen\.get\(sid\) \?\? -1\) < askGen\) : \(activeId \? \[activeId\] : \[\]\);/, "the click ends the active tab's wait; the flip the waits asked before it");
  assert.match(cancel, /const wasLanding = waitingLanding != null && !pendingOlderKeepY\.has\(sid\);/, "a deep link's ask, whether or not the landing's own mark still stands (low 1)");
  assert.match(cancel, /releaseSeekFetch\(sid\);\s*\/\/ the fetch's anchor becomes the reader's own row/, "the in-flight fetch keeps an anchor: the reader's row with its offset, so the chunk is a pure prepend (medium 2)");
  assert.match(cancel, /loadingOlder\.delete\(sid\); askedGen\.delete\(sid\); readerWaits\.delete\(sid\); pendingWindowNav\.delete\(sid\);/, "the in-flight marks go, so the next scroll or click may ask again");
  assert.match(cancel, /if \(why === "click" && wasLanding\) \{\s*\n\s*landTrail\.push\("cancelled"\);/, "a landing waiting on the ask files its row as cancelled");
  assert.match(cancel, /cancelled: true \}\);\s*\n\s*if \(pendingAnchor === waitingLanding\) \{ pendingAnchor = null; pendingAnchorIntent = null; pendingAnchorT = null; pendingAnchorKind = null; \}/, "…and the landing's own mark goes when it still stands");
  assert.match(cancel, /\n\s*syncLoadingPill\(\);\s*$/, "the pill follows the active tab's wait, whatever the other tabs hold");
  assert.match(cancel, /if \(why === "click" && pendingWindowNav\.has\(sid\)\) cancelledAsks\.add\(sid\);/, "a window ask clicked away is remembered for its reply");
  const win = fn("chatWindow");
  assert.match(win, /const cancelled = cancelledAsks\.delete\(msg\.id\);/);
  assert.match(win, /if \(cancelled && msg\.id === activeId && anchorUuid && !\(msg\.events \|\| \[\]\)\.some/, "a cancelled ask's window that lacks the reader's row is not adopted over them");
  assert.match(win, /const target = \(keepY != null && anchorUuid\) \? anchorUuid : \(typeof msg\.anchor === "string" \? msg\.anchor : anchorUuid\);/, "a keep offset names the reader's own row: the arrival restores it, never the window's anchor");
  assert.doesNotMatch(RENDER, /window\.addEventListener\("romp:wsup", \(\) => cancelOlderWait/, "the reopen cancel no longer rides the DOM event the shim fires after flushing the queued asks (low 4)");
  assert.match(RENDER, /window\.addEventListener\("romp:wsdown", \(\) => \{ askGen\+\+; flipPending = true; \}\);/, "the socket's death moves the generation");
  assert.match(RENDER, /function onSocketFlipFrame\(\): void \{ if \(!flipPending\) askGen\+\+; flipPending = false; cancelledAsks\.clear\(\); cancelOlderWait\("flip"\); \}/, "the reopen FRAME forgets the asks clicked away before the flip and ends the waits asked before it (round three, low 1)");
  assert.match(RENDER, /else if \(m\.type === "wsup"\) \{ onSocketUp\(skeletonTabs\); skeletonDiagArmed = true; onSocketFlipFrame\(\); \}/, "…in frame order, as the skeleton machine's socket-flip marker");
  assert.match(CSS, /\.tx-loading-pill \{[^}]*pointer-events: auto; cursor: pointer;/, "the pill takes the click (its anchor stays pointer-events none)");
  assert.match(CSS, /\.tx-loading-pill:hover \{ border-color: var\(--accent\); \}/);
});

test("a reply the kernel could not build is a FAULT routed apart from a genuine miss: the wait ends, nothing is re-based, no 'couldn't locate' (round two, lows 2 and 3)", () => {
  assert.match(fn("chatHead"), /if \(msg\.fault\) \{\s*\n[\s\S]*?forget\(msg\.id\);\s*\n\s*if \(msg\.id === activeId && deepLink && \(hadWait \|\| anchorPendingOlder\)\)/, "chatHead: a fault ends the wait, re-bases nothing, and stands a deep link's landing down (round four, low 2)");
  assert.match(fn("chatHead"), /if \(msg\.missing\) \{ forget\(msg\.id\); return; \}\s*\/\/ the index wire's fault reply/, "the index wire's fault never reads as the head reached");
  assert.match(fn("chatWindow"), /if \(msg\.fault\) \{[\s\S]*?landTrail\.push\("window-fault"\); landToast\("the history could not be loaded just now"\);/, "chatWindow: a fault is not a verdict on the anchor");
  assert.match(fn("chatMore"), /if \(msg\.fault\) return;/, "chatMore: the walked pages stay");
});

test("round three: a click's cancel latches at the edge until the reader's own evidence; a fault stands the landing down by the recorded wait; a flip and the pipe's down edge clear and end", () => {
  assert.match(RENDER, /function olderLatched\(sid: string\): boolean \{\s*\n\s*const at = olderCancelled\.get\(sid\);\s*\n\s*if \(at == null\) return false;\s*\n\s*if \(\(olderEvidence\.get\(sid\) \?\? 0\) > at\) \{ olderCancelled\.delete\(sid\); return false; \}/, "the latch stands until THIS tab's own evidence after the click (round four, medium 1)");
  const inp = RENDER.slice(RENDER.indexOf("function settleInput(e: Event): void {"), RENDER.indexOf("\n}\n", RENDER.indexOf("function settleInput(e: Event): void {")));
  assert.match(inp, /settleLastInput = Date\.now\(\);\s*\n[\s\S]*?if \(e\.type === "wheel" \|\| e\.type === "keydown" \|\| e\.type\.startsWith\("touch"\) \|\| \(e\.type === "pointerdown" && settleScrollerHeld\)\) noteOlderEvidence\(activeId\);/, "the evidence is stamped for the ACTIVE tab, by the inputs the settle machinery accepts (round four, medium 1)");
  assert.ok(inp.indexOf("isContentEditable)) return;") < inp.indexOf("noteOlderEvidence(activeId)") && inp.indexOf("!c.contains(e.target)) return;") < inp.indexOf("noteOlderEvidence(activeId)"), "…after the editable-field and the scroller's-own-box returns: a keystroke into the composer, a hover, a pointer off the scroller stamp nothing");
  assert.doesNotMatch(RENDER, /settleLastOwnInput|settleHeldAt/, "the page-global stamps are gone");
  assert.match(RENDER, /if \(after !== before && writerIsReader\(writer\)\) noteOlderEvidence\(activeId\);/, "a reader writer's own move (a trail or fragment-link jump, the live-tail chip, a key) is evidence too (round four, low 1)");
  const win4 = fn("chatWindow");
  assert.match(win4, /const cancelled = cancelledAsks\.delete\(msg\.id\);\s*\n\s*const later = cancelled && loadingOlder\.has\(msg\.id\);[^\n]*\n\s*const hadWait = !cancelled && readerWaits\.has\(msg\.id\);\s*\n\s*if \(!cancelled\) endAsk\(msg\.id\);/, "the reply answers the ask the reader clicked away, or the one on the books: a cancelled ask's reply ends nothing a later ask holds (round four, medium 2)");
  assert.match(win4, /if \(!later\) \{ pendingOlderAnchor\.delete\(msg\.id\); pendingOlderKeepY\.delete\(msg\.id\); \}/, "…nor the later ask's anchor");
  assert.equal((win4.match(/if \(!cancelled && msg\.id === activeId && \(hadWait \|\| pendingAnchor === anchorUuid\)\)/g) || []).length, 2, "both stand-downs (fault, missing) are silent for a cancelled ask");
  assert.ok(win4.indexOf("const ask = cancelled ? null : (pendingWindowNav.get(msg.id) ?? null);") < win4.indexOf("if (!s) return;") && win4.indexOf("if (!cancelled) pendingWindowNav.delete(msg.id);") < win4.indexOf("if (msg.fault) {"), "the nav entry is read and forgotten before any return (round four, low 3)");
  const head4 = fn("chatHead");
  assert.match(head4, /const hadWait = readerWaits\.has\(msg\.id\);\s*\n\s*const deepLink = pendingOlderAnchor\.has\(msg\.id\) && !pendingOlderKeepY\.has\(msg\.id\);[^\n]*\n\s*endAsk\(msg\.id\);/, "chatHead reads the wait and the deep-link mark before ending the ask");
  assert.match(head4, /if \(msg\.id === activeId && deepLink && \(hadWait \|\| anchorPendingOlder\)\) \{ pendingAnchor = null; anchorPendingOlder = false; landTrail\.push\("head-fault"\); landToast\("the history could not be loaded just now"\); clearSeek\(\); \}/, "the index wire's deep-link fault stands the landing down at once (round four, low 2)");
  assert.match(fn("virtualizeToViewport"), /&& upward && !olderLatched\(activeId\)\) \{ requestOlder\(activeId, v, content\); return; \}/, "the virtualiser asks nothing while the latch stands");
  assert.match(fn("requestOlder"), /\|\| olderLatched\(sid\)\) return;/);
  assert.match(fn("cancelOlderWait"), /if \(why === "click"\) olderCancelled\.set\(sid, Date\.now\(\)\);/);
  const win = fn("chatWindow");
  assert.match(win, /const hadWait = !cancelled && readerWaits\.has\(msg\.id\);/, "the stand-down keys on the wait the ask recorded, for an uncancelled reply (medium 2; round four)");
  assert.match(win, /if \(!cancelled && msg\.id === activeId && \(hadWait \|\| pendingAnchor === anchorUuid\)\) \{ if \(pendingAnchor === anchorUuid\) pendingAnchor = null; anchorPendingOlder = false; landTrail\.push\("window-fault"\); landToast\("the history could not be loaded just now"\); clearSeek\(\); \}/);
  assert.match(win, /landTrail\.push\("window-missing"\); landToast\("couldn't locate this in the transcript"\); clearSeek\(\); \}/);
  assert.match(RENDER, /function onSocketFlipFrame\(\): void \{ if \(!flipPending\) askGen\+\+; flipPending = false; cancelledAsks\.clear\(\); cancelOlderWait\("flip"\); \}/, "a flip clears the cancelled set (low 1)");
  assert.match(fn("requestAround"), /noteAsk\(sid, nav\);/, "a re-land is the page's own ask: no reader wait, no pill (low 2)");
  assert.match(RENDER, /function onPipeDown\(\): void \{ askGen\+\+; flipPending = true; cancelledAsks\.clear\(\); cancelOlderWait\("flip"\); \}/, "the VS Code pipe's down edge ends the asks in flight (low 3)");
  assert.match(RENDER, /if \(m\.type === "pipeState"\) \{ if \(!m\.up\) \{ markPendingLost\("connection"\); onPipeDown\(\); \}/);
});
