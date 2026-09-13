// Bidirectional virtualization of the chat transcript (the user 2026-06-25). A long session renders one row
// per event (or per folded compact item) — thousands of nodes — which made switching to / scrolling a big
// session slow. Both modes now render a bounded window of UNITS [winStart, winEnd) with a TOP spacer for the
// hidden head and a BOTTOM spacer for the hidden tail; on scroll we re-render AROUND wherever the viewport
// lands, so random-access jumps work, not just contiguous scroll-back. Source-level pins (no jsdom for the
// renderer), mirroring the other render.ts tests.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("windowing constants are sane: a tail, a render radius and a re-window margin, a switch cap", () => {
  // (the trailing re-check window, TAIL_RECHECK, is gone: the tail path re-renders exactly from the kernel's
  // first changed event — chat-exact-tail.test.ts)
  const tail = Number(/const WINDOW_TAIL = (\d+);/.exec(RENDER)?.[1]);
  const radius = Number(/const WINDOW_RADIUS = (\d+);/.exec(RENDER)?.[1]);
  const margin = Number(/const REVIRT_MARGIN = (\d+);/.exec(RENDER)?.[1]);
  const cap = Number(/const WINDOW_CAP = (\d+);/.exec(RENDER)?.[1]);
  assert.ok(tail > 0, "a tail window");
  assert.ok(radius > margin && margin > 0, "radius > margin > 0");
  assert.ok(cap > tail, "cap > tail");
});

test("units unify both modes: one per event (normal) or the folded compactDisplay stream (compact)", () => {
  assert.match(RENDER, /function displayItems\(s: Session\): DisplayItem\[\]/);
  assert.match(RENDER, /if \(!settings\.compact\) \{[\s\S]*?out\.push\(\{ kind: "event", index: i \}\);/);
  assert.match(RENDER, /out = compactDisplay\([\s\S]*?\n\s*\}\s*\n\s*return withGapItems\(s, out\);/, "the folded stream, then the gaps between the runs interleaved (T386 stage 2)");
});

test("every rendered row is tagged data-unit, so the scroll↔unit map can locate it", () => {
  assert.match(RENDER, /node\.dataset\.unit = String\(u\);/);          // appendItem (window build)
  assert.match(RENDER, /node\.dataset\.unit = String\(i\);\s*\/\/ unit === event/); // normal incremental append
});

test("renderWindowItems renders [unitStart, unitEnd) with a TOP and a BOTTOM spacer", () => {
  assert.match(RENDER, /function renderWindowItems\(v: View, s: Session, items: DisplayItem\[\], unitStart: number, unitEnd: number, working: boolean\): void/);
  assert.match(RENDER, /if \(unitStart > 0\) v\.el\.appendChild\(el\("div", "tx-spacer tx-spacer-top"\)\);/);
  assert.match(RENDER, /if \(unitEnd < total\) v\.el\.appendChild\(el\("div", "tx-spacer tx-spacer-bot"\)\);/);
  assert.match(RENDER, /v\.winStart = unitStart; v\.winEnd = unitEnd;/);
  assert.match(RENDER, /v\.spacerCount = unitStart; v\.spacerCountBot = total - unitEnd;/);
});

test("sizeSpacers sizes BOTH spacers by hidden-unit count × avg, caching only a visible measurement", () => {
  assert.match(RENDER, /function sizeSpacers\(v: View\): void/);
  assert.match(RENDER, /const topAfter = top \? hiddenHeight\(v, 0, v\.spacerCount \?\? 0, avg\) : 0, botAfter = bot \? hiddenHeight\(v, total - \(v\.spacerCountBot \?\? 0\), total, avg\) : 0;/, "both spacers by the hidden units' own heights: a gap's estimate, else the average (T386 stage 2)");
  assert.match(RENDER, /if \(top\) top\.style\.height = topAfter \+ "px";\s*\n\s*if \(bot\) bot\.style\.height = botAfter \+ "px";/);
  assert.match(RENDER, /if \(h > 0 && n > 0\) v\.avgTurnH = h \/ n;/);   // don't cache a display:none 0
});

test("unitAtScroll maps a spacer by avg height and a rendered row by its data-unit", () => {
  assert.match(RENDER, /function unitAtScroll\(v: View, content: HTMLElement\): number/);
  assert.match(RENDER, /if \(st < topH\) \{[^\n]*\n\s*if \(!v\.gapUnits\) return Math\.max\(0, Math\.floor\(st \/ avg\)\);/, "in the top spacer: the average when no gap sits in it, else a walk over the hidden units' heights (T386 stage 2)");
  assert.match(RENDER, /if \(st < t0 \+ c\.offsetHeight\) return lastUnit;/);                  // straddling a rendered row
  assert.match(RENDER, /return \(v\.winEnd \?\? 0\) \+ Math\.floor\(\(st - bTop\) \/ avg\);/);  // in the bottom spacer
});

test("scroll re-windows around the viewport (steady scroll OR jump) when near a rendered edge", () => {
  assert.match(RENDER, /function virtualizeToViewport\(\): void/);
  // CHEAP px pre-check on every scroll; the precise unit walk only runs when near a rendered edge
  assert.match(RENDER, /const nearTopEdge = \(v\.winStart \?\? 0\) > 0 && st < topH \+ edgePx;/);
  assert.match(RENDER, /const nearBotEdge = \(v\.winEnd \?\? total\) < total && st \+ vh > renderedBottom - edgePx;/);
  assert.match(RENDER, /if \(!nearTopEdge && !nearBotEdge\) return;/);
  assert.match(RENDER, /const idx = unitAtScroll\(v, content\);/);
  assert.match(RENDER, /renderWindowItems\(v, s, items, Math\.max\(0, c - WINDOW_RADIUS\), Math\.min\(items\.length, c \+ WINDOW_RADIUS\), working\);/);
  // it re-anchors the focus unit so it doesn't jump, coalesced to one frame; a re-window of resident content shows no cue (T402, T386 stage 2)
  assert.match(RENDER, /writeScroll\(content, yNow - beforeY, "rewindow"\);/);   // (T262: every #content write rides writeScroll)
  assert.match(RENDER, /c\.addEventListener\("scroll", virtualizeToViewport, \{ passive: true \}\);/);
});

test("the ONE landing notice shows while a navigation's window is on the wire, pinned top-center of the chat SECTION, never the viewport (T365, T386 stage 2)", () => {
  assert.match(RENDER, /function showLandingNotice\(sid: string, t: number \| null \| undefined\): void/);
  assert.match(RENDER, /landingNoticeEl\.textContent = landingNotice\(t, clockOf\);/, "its words come from the pure rule: the target's time in the reader's clock, and the click to stay");
  assert.match(RENDER, /landingNoticeEl\.addEventListener\("click", \(\) => cancelLanding\(\)\);/, "clicking it is the ONLY cancel");
  const fn = RENDER.slice(RENDER.indexOf("function showLandingNotice(sid: string"), RENDER.indexOf("function hideLandingNotice(): void"));
  // T365 (the user 2026-09-12): a viewport-fixed pill appended to the body sat on the tabs, and on the tabs themselves
  // once the strip wrapped; it now rides a zero-height anchor inserted right before #content, the transcript's top edge
  assert.doesNotMatch(fn, /document\.body\.appendChild/, "the pill no longer lands in the body");
  assert.match(fn, /anchor\.className = "tx-loading-anchor";/);
  assert.match(fn, /content\.parentNode\.insertBefore\(anchor, content\);/, "the anchor sits right before #content, below the strip and the ledger box");
  assert.match(fn, /if \(!landingNoticeEl\.isConnected\)/, "idempotent: one anchor, re-made only if a rebuild dropped it");
  assert.ok(!CSS.includes("#live-paused") && !CSS.includes(".live-paused"), "the paused strip's CSS is gone with the strip (T386 stage 2)");
  const anchorRule = CSS.slice(CSS.indexOf(".tx-loading-anchor {")); const anchorBody = anchorRule.slice(0, anchorRule.indexOf("}"));
  assert.match(anchorBody, /position: relative;/); assert.match(anchorBody, /height: 0;/); assert.match(anchorBody, /pointer-events: none;/);
  const pillRule = CSS.slice(CSS.indexOf(".tx-landing-notice {")); const pillBody = pillRule.slice(0, pillRule.indexOf("}"));
  assert.match(pillBody, /position: absolute; top: 10px; left: 50%; transform: translateX\(-50%\);/);
  assert.doesNotMatch(pillBody, /position: fixed/);
  // the surface is tokened for both themes (reads on cream): no hard-coded dark rgba background or border
  assert.match(pillBody, /background: var\(--vscode-menu-background, var\(--surface-raised\)\);/);
  assert.match(pillBody, /border: 1px solid var\(--menu-border\);/);
  assert.doesNotMatch(pillBody, /rgba\(20, 24, 33/);
  assert.match(pillBody, /pointer-events: auto; cursor: pointer;/, "the notice takes the click: the ONE cancel must be reachable (T386 stage 2, HIGH)");
  assert.match(anchorBody, /pointer-events: none;/, "…while its anchor stays inert, so it never eats the transcript's clicks");
});

test("syncView: a fresh build / rewind renders the TAIL window, clamped to the last compaction boundary", () => {
  // the default window opens AT (never below) the newest compaction — pre-compaction history is scrubbed
  // from the default view (the user 2026-07-07); lastCompactUnit floors the window start.
  assert.match(RENDER, /if \(firstBuild \|\| rewind\) \{\s*\n\s*const start = Math\.max\(0, total - WINDOW_TAIL, lastCompactUnit\(s, items\)\);\s*\n\s*renderWindowItems\(v, s, items, start, total, working\);/);
});

test("syncView: a pure tab switch is a NO-OP render (reveal the cached DOM)", () => {
  assert.match(RENDER, /if \(v\.rendered === len && !v\.stale && v\.el\.childNodes\.length > 0\) return v;/);
});

test("syncView: compact / an in-place change re-renders the CURRENT window; a browse append just grows the bottom spacer", () => {
  // compact mode and any stale (tool-group toggle, off-screen update) re-render where the user is
  assert.match(RENDER, /if \(settings\.compact \|\| v\.stale\) \{[\s\S]*?renderWindowItems\(v, s, items, ws, we, working\);/);
  // browsing history away from the tail: appended events land below the window → grow the bottom spacer only
  assert.match(RENDER, /if \(!wasAtTail\) \{\s*\n\s*v\.spacerCountBot = total - \(v\.winEnd \?\? total\);/);
});

test("a new message while scrolled UP keeps the viewport put (no backwards jump)", () => {
  // appendActive: at the bottom → follow it; scrolled up → restore ANCHOR-relative after the sync (the
  // turn at the viewport top keeps its exact offset — raw scrollTop only when the anchor was evicted; the
  // user 2026-07-05, subagent report cards growing ABOVE the viewport moved the raw offset's meaning), and
  // tell syncView atBottom=stick so a compact append KEEPS winStart (content above the viewport unchanged)
  // instead of evicting the top — which (with the compact full-rebuild that resets scrollTop) was jumping
  // the view "backwards" when messages arrived (the user 2026-06-25).
  assert.match(RENDER, /const before = content\.scrollTop;/);
  assert.match(RENDER, /syncView\(activeId, stick\);/);
  assert.match(RENDER, /else if \(!\(v && restoreScrollAnchor\(content, v, anchor, before\)\)\) writeScroll\(content, before, "append-raw", false, before\);/);
  // the compact branch keeps winStart on a scrolled-up append
  assert.match(RENDER, /const keepTop = wasAtTail && atBottom === false;/);
  assert.match(RENDER, /const ws = keepTop \? \(v\.winStart \?\? 0\)/);
});

test("an oversized view (window grew past the cap) re-collapses to the tail on switch", () => {
  // `!reshow &&` leads since T249: the re-collapse is a SWITCH rule, never applied to a re-show of the view on screen
  assert.match(RENDER, /if \(!reshow && !pendingAnchor && pendingAnchorT == null\s*\n?\s*&& v\.el\.querySelectorAll\("\.turn"\)\.length > WINDOW_CAP\) \{/);
  assert.match(RENDER, /v\.rendered = 0; v\.winStart = 0; v\.avgTurnH = undefined; v\.stick = true;/);
});

test("a deep-link off the current window renders a fresh window AROUND the target unit, then lands", () => {
  assert.match(RENDER, /let u = items\.findIndex\(\(it\) => it\.kind === "toolgroup" \|\| it\.kind === "noticegroup" \? it\.indices\.includes\(idx\) : it\.kind === "event" && it\.index === idx\);/, "a gap item indexes no event (T386 stage 2)");
  assert.match(RENDER, /renderWindowItems\(v, s, items, Math\.max\(0, u - WINDOW_RADIUS\), Math\.min\(items\.length, u \+ WINDOW_RADIUS\), working\);/);
});

test("round two/three code fixes each carry a pin (T386 stage 2, low 1)", () => {
  const winStart = RENDER.indexOf("function chatWindow(msg: any) {");
  const win = RENDER.slice(winStart, RENDER.indexOf("\nfunction ", winStart + 1));
  const cTurns = RENDER.slice(RENDER.indexOf("function chatTurns(msg: any)"), RENDER.indexOf("function chatHead(msg: any)") >= 0 ? RENDER.indexOf("function chatHead(msg: any)") : winStart);
  // the socket death clears every in-flight ask's state, not the glyph alone (medium 1)
  assert.match(RENDER, /window\.addEventListener\("romp:wsdown", \(\) => \{[\s\S]*?gapLoading\.clear\(\); landingGaps\.clear\(\); loadingOlder\.clear\(\);[\s\S]*?hideLandingNotice\(\);/, "wsdown clears the landing's gap, the older-ask set and the notice");
  // sizeSpacers does not average the gap element (medium 3, round one)
  const pxBlock = RENDER.slice(RENDER.indexOf("if (v.pxPerTurn == null) {"), RENDER.indexOf("if (h > 0 && turns > 0) v.pxPerTurn = h / turns;"));
  assert.match(pxBlock, /if \(c\.classList\.contains\("tx-spacer"\) \|\| c\.classList\.contains\("tx-gap"\) \|\| !c\.classList\.contains\("turn"\)\) continue;/, "the px-per-turn measure skips the gap element and every non-turn child (pinned inside its own block; round four low 3, round five)");
  const unitBlock = RENDER.slice(RENDER.indexOf("if (v.avgTurnH == null) {"), RENDER.indexOf("if (h > 0 && n > 0) v.avgTurnH = h / n;"));
  assert.match(unitBlock, /c\.classList\.contains\("tx-gap"\)\) continue;/, "…and so does the per-unit measure");
  // the region-fill view resets (chatTurns, chatWindow) keep the measured averages across fills (low 1); chatHead's prepend reset may still clear them
  assert.ok(cTurns.includes("v.rendered = 0; v.winStart = 0; v.winEnd = 0; v.spacerCount = undefined;"), "chatTurns resets the window");
  assert.doesNotMatch(cTurns, /v\.winEnd = 0; v\.avgTurnH = undefined;/, "…without clearing the measured average (the fill keeps it, low 1)");
  assert.doesNotMatch(win, /v\.winEnd = 0; v\.avgTurnH = undefined;/, "chatWindow's fill keeps the measured average too (low 1)");
  // a second deep link while one is on the wire is refused with a cue, not silently repointed (low 6, low 4)
  assert.match(RENDER, /if \(loadingOlder\.has\(activeId\)\) \{ landTrail\.push\("pointer-fetch-busy"\); landToast\("still going to the earlier message"\); return false; \}/, "the busy refusal toasts a cue");
  // the cancelled mark is read once before any early return (low 2)
  assert.ok(win.indexOf("const cancelled = cancelledLandings.delete(msg.id);") >= 0 && win.indexOf("const cancelled = cancelledLandings.delete(msg.id);") < win.indexOf("!Array.isArray(msg.span)"), "the cancelled mark is read before the missing/span-less return");
  // a mid-transcript gap keeps headTotal null (low 7)
  assert.match(RENDER, /s\.regions && s\.regions\.some\(\(r\) => r\.kind === "gap"\)\)\) s\.headTotal/, "chatTail keeps no head total while a gap holds older history");
});

test("round four and five fixes each carry a pin (T386 stage 2, round five low 1)", () => {
  const fill = RENDER.slice(RENDER.indexOf("function fillInPlace(sid: string, v: View | undefined): void {"), RENDER.indexOf("\nfunction ", RENDER.indexOf("function fillInPlace(sid: string, v: View | undefined): void {") + 1));
  assert.match(fill, /const keepVisible = !!keep && keep\.y < content\.clientHeight - 1;/, "a row anchors the fill when it intersects the viewport, whatever the sign of its top (medium 1)");
  assert.doesNotMatch(fill, /keep\.y >= -1/, "…no lower bound on the row's top");
  assert.match(fill, /const turnsNow = turnOfEvents\(s\);\s*\n\s*const pointBefore = turnUnderTop\(v, s, items, turnsNow, content, topBefore\);/, "the point under the viewport top is named as a turn before the rebuild (medium B)");
  assert.match(fill, /if \(t0 != null\) u = items\.findIndex\(\(it\) => it\.kind === "gap" \? \(t0 >= it\.lo && t0 < it\.hi\)/, "…and the window renders around the unit holding that turn in the NEW items, never a stale unit index");
  assert.match(fill, /const mapped = pointBefore != null \? yOfTurn\(v, s, items, turnsNow, content, pointBefore\) : null;\s*\n\s*y = mapped != null \? mapped : topBefore;/, "…and put back by its turn after it, scrollTop kept only when the point cannot be named (medium A: the anchor row gone falls to the turn, never a doubled write)");
  assert.doesNotMatch(fill, /heightAbove/, "the view-coordinate tautology is gone");
  assert.match(RENDER, /function turnUnderTop\(v: View, s: Session, items: DisplayItem\[\], turns: number\[\], content: HTMLElement, top: number\): number \| null \{/, "the turn-under-top helper");
  assert.match(RENDER, /function yOfTurn\(v: View, s: Session, items: DisplayItem\[\], turns: number\[\], content: HTMLElement, t: number\): number \| null \{/, "the turn-to-scroll helper");
  assert.match(RENDER, /gapLoading\.clear\(\); landingGaps\.clear\(\); loadingOlder\.clear\(\); cancelledLandings\.clear\(\);/, "the socket death clears the cancelled mark too (medium 2)");
  assert.match(RENDER, /const liveLanding = !!landingNoticeSid \|\| Array\.from\(landingGaps\.keys\(\)\)\.some\(\(sid\) => !cancelledLandings\.has\(sid\)\);/, "the wsdown toast fires only for a landing the reader had not cancelled (low 1)");
  assert.match(RENDER, /const nospan = !msg\.missing && Array\.isArray\(msg\.events\) && msg\.events\.length > 0 && !Array\.isArray\(msg\.span\);/, "missing is tested first; only a reply with events and no span is an older host (medium 3; round five low 3)");
  assert.match(RENDER, /const preJumpOrigin = preJumpFrom\.get\(msg\.id\); preJumpFrom\.delete\(msg\.id\);/, "the pre-jump origin is consumed by every window reply (low 2)");
  const px = RENDER.slice(RENDER.indexOf("if (v.pxPerTurn == null) {"), RENDER.indexOf("if (h > 0 && turns > 0) v.pxPerTurn = h / turns;"));
  assert.match(px, /\|\| !c\.classList\.contains\("turn"\)\) continue;/, "px-per-turn counts turn rows only, never cards or dividers (round five)");
});

test("the spacer is invisible, non-interactive vertical space", () => {
  assert.match(CSS, /\.tx-spacer \{ width: 100%; pointer-events: none; \}/);
});
