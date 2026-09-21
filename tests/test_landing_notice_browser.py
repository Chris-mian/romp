"""T386 stage 2 (the user 2026-09-12, plans/chat-history-regions.md Part B): the ONE landing notice. A navigation into history the
page does not hold (a card, a deep link) asks for a window; while it is on the wire the notice sits at the loading anchor before
#content and says where the landing goes ("Going to the message from 7:41 AM, click to stay here"); the view jumps straight into
the gap where the target will be, the loading glyph in the empty space; the landing hides the notice. Clicking the notice is the
ONLY cancel: the target and the notice go, the reply still inserts its run in place, and the view does not move. Served, on the
window lab's hermetic kernel (a synthetic transcript longer than the wire tail: the deep target is in the head gap at boot).

Roads, ten fresh pages (the socket death first, then the notice roads, then the answered-question anchor, the cancel-then-click road, the fault road, three roads on the per-ask records: two cancels, a cancelled origin, a lost cancelled frame, then an older fetch in flight and the pipe's down edge): the deep link landing with the notice (the words, the pre-jump write, the window ask, the landing, the notice
gone); then a second deep link with its ask HELD at the socket, the notice clicked (a locateDiag row filed as cancelled, the notice
gone, the view still), the ask released (the run inserts, the view still where the reader was).

Synthetic fixtures only (placeholder uuids, invented prose); hostname TESTHOST.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from tests.test_live_paused_window_browser import DRIVER_HEAD, SID, WindowLab  # noqa: E402

DRIVER = DRIVER_HEAD + r"""
// the socket hold: a frame whose type is in __hold is parked, not sent (the ask stays on the page's books); __release sends the parked frames
const installShim = () => page.evaluate(() => { const orig = WebSocket.prototype.send; window.__hold = new Set(); window.__heldRaw = [];
  WebSocket.prototype.send = function (d) { window.__ws = this; try { const m = JSON.parse(d); if (m && m.type && window.__hold.has(m.type)) { window.__heldRaw.push(d); return; } } catch (e) {} return orig.call(this, d); };
  window.__release = () => { const ws = window.__ws; const held = window.__heldRaw; window.__heldRaw = []; for (const d of held) orig.call(ws, d); return held.length; };
  window.__releaseOne = () => { const d = window.__heldRaw.shift(); if (d) orig.call(window.__ws, d); return d ? 1 : 0; };
  window.__recv = []; window.__bootSession = null; window.addEventListener("message", (e) => { const m = e.data; if (m && m.type) { window.__recv.push(m.type + (m.span ? ":" + m.span.join("-") : "") + (m.anchor ? ":anchor" : "")); if (m.type === "session" && Array.isArray(m.events) && !window.__bootSession) window.__bootSession = m; } }); });
await installShim();
// a FRESH page (round six, medium 3): the roads that need the head gap whole (the socket death, the answered-question anchor) each start
// from a reload: the boot frame arrives with the tail alone and every gap stands, then the shim is installed again (the init scripts persist)
// …the page's own reload restore (sessionStorage "romp:reloadScroll", written at unload, read at boot) would walk the held history back
// in and fill the head; an init script drops the record before the page reads it, so each reload boots the tail alone
await page.addInitScript(() => { try { sessionStorage.removeItem("romp:reloadScroll"); } catch (e) { /* none */ } });
// the boot frame of every page life, captured before the page's own scripts run (the evaluate-time shim installs after the boot, so after a
// reload its capture stays null): a road that re-posts the boot frame reads it from here
await page.addInitScript(() => { window.__bootFrame = null; window.addEventListener("message", (e) => { const m = e.data; if (m && m.type === "session" && Array.isArray(m.events) && m.events.length && !window.__bootFrame) window.__bootFrame = m; }); });
const reboot = async () => {
  await page.reload();
  await page.waitForSelector("#tabs .tab, #tabs [data-sid]", { timeout: 20000 });
  await page.waitForFunction(() => document.querySelectorAll("#content .turn[data-uuid]").length >= 40, null, { timeout: 30000 });
  await page.waitForTimeout(500);
  await installShim();
  await page.evaluate(() => { const c = document.getElementById("content"); c.scrollTop = c.scrollHeight; });
  await painted();
};
const trace = () => page.evaluate(() => ({ sent: window.__sent.slice(-14).map((m) => m.type + (m.what ? ":" + m.what + (m.data && m.data.writer ? ":" + m.data.writer : "") + (m.data && m.data.why ? ":" + m.data.why : "") : "") + (m.cancelled ? ":cancelled" : "")), recv: window.__recv.slice(-10), regions: (typeof window.__rompRegions === "function" ? window.__rompRegions() : null) }));
const writes = (writer) => page.evaluate((w) => window.__sent.filter((m) => m.what === "scrollwrite" && m.data && m.data.writer === w).map((m) => [m.data.before, m.data.after]), writer);
const locateRows = () => page.evaluate(() => window.__sent.filter((m) => m.type === "locateDiag").map((m) => ({ ok: m.ok, cancelled: m.cancelled === true, anchor: m.anchor, trail: m.trail, kind: m.kind === undefined ? null : m.kind, error: m.error === undefined ? null : m.error })));
const painted = () => page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 0)))));
// the page's sends quiet across two frames: a pre-jump's or a cancel's DEFERRED scroll write posts its row when it runs, and a road that moves
// the reader before it has run is moved back by it (road 6 read scrollTop 8 for a scroll to 60% of the gap once the dead waits were gone)
const quiet = () => page.waitForFunction(() => new Promise((res) => { const n = window.__sent.length; requestAnimationFrame(() => requestAnimationFrame(() => res(window.__sent.length === n))); }), null, { timeout: 8000 }).catch(() => {});
const rowAtTop = () => page.evaluate(() => {
  const c = document.getElementById("content"); const cTop = c.getBoundingClientRect().top;
  for (const t of Array.from(document.querySelectorAll("#content .turn[data-uuid]"))) { const r = t.getBoundingClientRect(); if (r.bottom > cTop + 1) return { uuid: t.dataset.uuid, y: Math.round(r.top - cTop) }; }
  return null;
});
const onScreen = (uuid) => page.evaluate((u) => { const t = document.querySelector(`#content .turn[data-uuid="${u}"]`); if (!t) return null; const c = document.getElementById("content").getBoundingClientRect(); const r = t.getBoundingClientRect(); return { top: Math.round(r.top - c.top), visible: r.bottom > c.top && r.top < c.bottom }; }, uuid);
// ROAD 5 (T386 stage 2, medium 1; round six: runs FIRST, on the fresh boot with the whole head gap): a landing's window ask parked at the
// socket (held: it never reaches the kernel, so the death genuinely loses it), the socket killed with the landing in flight. The death
// clears every in-flight ask's state (landingGaps, gapLoading, loadingOlder: the three-set) and brings the notice down; the shim redials
// and the kernel re-sends the session; the landing is asked again (the redial's flush re-sends the lost ask, else a fresh deep link asks)
// and lands.
const deep5 = "11111111-2222-3333-4444-" + pad(2 * 25);
await page.evaluate(() => { window.__hold.add("loadAround"); });
const winBefore5 = await page.evaluate(() => window.__recv.filter((x) => x.startsWith("chatWindow")).length);
await page.evaluate((frame) => window.postMessage(frame, "*"), { type: "focus", id: cfg.sid, anchor: deep5, anchorT: cfg.base + 2 * 25 });
await page.waitForFunction(() => !!document.querySelector(".tx-landing-notice") && getComputedStyle(document.querySelector(".tx-landing-notice")).display !== "none", null, { timeout: 8000 }).catch(() => {});
const askBefore5 = await page.evaluate((sid) => (typeof window.__rompAskState === "function" ? window.__rompAskState(sid) : null), cfg.sid);   // the landing in flight: its gap held
await page.waitForFunction(() => (window.__heldRaw || []).some((d) => JSON.parse(d).type === "loadAround"), null, { timeout: 10000 }).catch(() => {});   // the ask parked at the socket (a bounded wait, not a paint)
const heldRaw5 = await page.evaluate(() => (window.__heldRaw || []).length);   // the ask parked at the socket: lost for good when it dies
const sentAtDeath5 = await page.evaluate(() => window.__sent.length);
const recvBefore5 = await page.evaluate(() => window.__recv.filter((x) => x.startsWith("session")).length);
const recvLenAtDeath5 = await page.evaluate(() => window.__recv.length);
await page.evaluate(() => { window.__heldRaw = []; window.__hold.delete("loadAround"); if (window.__ws) window.__ws.close(); });   // the parked ask dropped, the socket dead: the ask is lost
// sampled in the SAME evaluation that sees the notice down: the redial's flush may re-arm an ask within milliseconds of the reopen
const afterDrop5 = await (await page.waitForFunction((sid) => { const n = document.querySelector(".tx-landing-notice"); const down = !n || getComputedStyle(n).display === "none"; return down ? { notice: false, ask: (typeof window.__rompAskState === "function" ? window.__rompAskState(sid) : null) } : false; }, cfg.sid, { timeout: 8000 })).jsonValue();
const askState5 = afterDrop5.ask;
const winAtDeath5 = await page.evaluate(() => window.__recv.filter((x) => x.startsWith("chatWindow")).length);   // no window ever answered the lost ask
// the REDIAL: the shim reopens the socket and the kernel re-sends the session (round four, low 6: a real close and redial)
await page.waitForFunction((n) => window.__recv.filter((x) => x.startsWith("session")).length > n, recvBefore5, { timeout: 15000 }).catch(() => {});
await painted();
const redialed5 = (await page.evaluate(() => window.__recv.filter((x) => x.startsWith("session")).length)) - recvBefore5;
const recvAfter5 = await page.evaluate((n) => window.__recv.slice(n), recvLenAtDeath5);   // every frame type received after the death (round eleven: the redial's connect push under the handshake mark)
const sentAfter5 = await page.evaluate((n) => window.__sent.slice(n).map((m) => m.type), sentAtDeath5);

// the re-ask: the redial's flush re-sends the session's bookkeeping (the lost loadAround among it), else a fresh deep link asks
await page.waitForFunction((n) => window.__sent.slice(n).some((m) => m.type === "loadAround"), sentAtDeath5, { timeout: 5000 }).catch(() => {});
const flushAsk5 = await page.evaluate((n) => window.__sent.slice(n).filter((m) => m.type === "loadAround").length, sentAtDeath5);
if (!flushAsk5) await page.evaluate((frame) => window.postMessage(frame, "*"), { type: "focus", id: cfg.sid, anchor: deep5, anchorT: cfg.base + 2 * 25 });
await page.waitForFunction((u) => !!document.querySelector(`#content .turn[data-uuid="${u}"]`), deep5, { timeout: 15000 }).catch(() => {});
await page.waitForFunction(() => { const n = document.querySelector(".tx-landing-notice"); return !n || getComputedStyle(n).display === "none"; }, null, { timeout: 10000 }).catch(() => {});
const reask5 = await page.evaluate((n) => window.__sent.slice(n).filter((m) => m.type === "loadAround").length, sentAtDeath5);
const landed5 = await page.evaluate((u) => !!document.querySelector(`#content .turn[data-uuid="${u}"]`), deep5);
await reboot();   // the roads after need the head gap whole again
await page.evaluate(() => { window.__hold.add("loadTurns"); });   // the head gap's page asks are parked for this page life: a kernel frame's rebuild re-observes the gap under a reader a pre-jump parked at its top and it asks its first page (CI 2026-09-14, thirty-three events), which reshapes the gap every later road on the page assumes whole; a road that wants a fill releases its own ask alone
// ROAD 3 (T386 stage 2, medium 2): an OLDER host speaks the pre-regions window protocol — its chatWindow carries events but NO span.
// A deep link into a gap, the ask held, then a span-less reply injected: the pre-jump moved the reader, so the notice comes down and
// the reader is told the host is older, never dropped silently where the pre-jump left them.
const deep3 = "11111111-2222-3333-4444-" + pad(2 * 40);
await page.evaluate(() => { window.__hold.add("loadAround"); });
const aroundBefore3 = await sentOf("loadAround"); const toastBefore3 = await page.evaluate(() => !!document.querySelector(".locate-toast"));
await page.evaluate((frame) => window.postMessage(frame, "*"), { type: "focus", id: cfg.sid, anchor: deep3, anchorT: cfg.base + 2 * 40 });
await page.waitForFunction((ty) => (window.__heldRaw || []).some((d) => JSON.parse(d).type === ty), "loadAround", { timeout: 10000 }).catch(() => {});   // the HELD ask, where it lands (a parked frame never reaches __sent: the wait this replaces burned its timeout on every run)
const asked3 = await state();
await page.evaluate(([sid, anchor]) => window.postMessage({ type: "chatWindow", id: sid, anchor, events: [{ uuid: anchor, kind: "user", md: "an older host's window, no span" }], moreBefore: false, moreAfter: false }, "*"), [cfg.sid, deep3]);
await page.waitForFunction(() => { const tt = document.querySelector(".locate-toast"); return !!tt && /older version/.test(tt.textContent || ""); }, null, { timeout: 5000 }).catch(() => {});
const nospan3 = { notice: (await state()).notice, toast: await page.evaluate(() => { const tt = document.querySelector(".locate-toast"); return tt ? tt.textContent : null; }) };
await page.evaluate(() => { window.__hold.delete("loadAround"); window.__heldRaw = []; });
// ROAD 6 (round five, medium B; runs right after the span-less road, while the head gap is whole, and returns the reader to the tail after):
// the point under the viewport top holds through a fill that STRADDLES a reader standing INSIDE the head gap (the window around turn 60 spans
// about turns 0 to 123; the reader stands near turn 117 of the gap). The fill is the cancel road's
// (deterministic, the same fillInPlace a page fill takes): a deep link into turn 60 asks its window (HELD), the notice is clicked away so
// nobody is going to that window, the reader scrolls deep into the gap (no row on screen), the window is released and fills in place around
// them; the point under the viewport top, named as a turn, must move by less than a turn (the old view-coordinate compensation carried it
// about 2.6 turns; 81c0dca5 about 2.8).
const sentAt6 = await page.evaluate(() => window.__sent.length);
await page.evaluate(() => { const c = document.getElementById("content"); c.scrollTop = c.scrollHeight; });   // from the tail: the gap above the tail run is rendered, so its element can be measured
await painted();
await page.evaluate(() => { window.__hold.add("loadAround"); });
const around6 = await sentOf("loadAround");
await page.evaluate((frame) => window.postMessage(frame, "*"), { type: "focus", id: cfg.sid, anchor: "11111111-2222-3333-4444-" + pad(2 * 60), anchorT: cfg.base + 2 * 60 });   // turn 60: its window (about turns 0 to 123) STRADDLES the reader, who stands near turn 117 of the head gap
await page.waitForFunction((ty) => (window.__heldRaw || []).some((d) => JSON.parse(d).type === ty), "loadAround", { timeout: 10000 }).catch(() => {});   // the HELD ask, where it lands (a parked frame never reaches __sent: the wait this replaces burned its timeout on every run)
await page.waitForFunction(() => { const n = document.querySelector(".tx-landing-notice"); return !!n && getComputedStyle(n).display !== "none"; }, null, { timeout: 5000 }).catch(() => {});
const heldAsk6 = await page.evaluate(() => (window.__heldRaw || []).length);
await page.evaluate(() => { const n = document.querySelector(".tx-landing-notice"); if (n) { const r = n.getBoundingClientRect(); n.dispatchEvent(new MouseEvent("click", { bubbles: true, clientX: r.left + r.width / 2, clientY: r.top + r.height / 2 })); } });   // the notice clicked away: the reply will fill in place
await page.waitForFunction(() => { const n = document.querySelector(".tx-landing-notice"); return !n || getComputedStyle(n).display === "none"; }, null, { timeout: 5000 }).catch(() => {});
await quiet();   // the cancel's and the pre-jump's deferred writes have run: the road's own scroll below is not moved back by one
await page.evaluate(() => { const c = document.getElementById("content"); const g = document.querySelector("#content .tx-gap"); const gTop = g ? g.getBoundingClientRect().top - c.getBoundingClientRect().top + c.scrollTop : 0; c.scrollTop = Math.round(gTop + (g ? g.offsetHeight : 9000) * 0.6); });   // about turn 117 of 195, deep into the head gap, no row on screen
await painted();
const inGap6 = await page.evaluate(() => { const c = document.getElementById("content"); const cr = c.getBoundingClientRect(); const rows = Array.from(c.querySelectorAll(".turn[data-uuid]")).filter((t) => { const r = t.getBoundingClientRect(); return r.bottom > cr.top && r.top < cr.bottom; }).length; const rs = typeof window.__rompRegions === "function" ? window.__rompRegions() : null; const g = rs && rs.find((r) => r.kind === "gap"); return { top: c.scrollTop, rowsOnScreen: rows, gap: g ? { lo: g.lo, hi: g.hi } : null }; });
const point6Before = await page.evaluate(() => (typeof window.__rompTurnUnderTop === "function" ? window.__rompTurnUnderTop() : null));
const regionsBefore6 = await page.evaluate(() => (typeof window.__rompRegions === "function" ? window.__rompRegions() : null));
await page.evaluate(() => { window.__hold.delete("loadAround"); window.__heldRaw = (window.__heldRaw || []).filter((d) => JSON.parse(d).type === "loadAround"); window.__release(); window.__hold.add("loadAround"); });   // the window alone goes out; parked page asks are dropped; the hold stays for the roads after
await page.waitForFunction((n0) => { const rs = (typeof window.__rompRegions === "function" && window.__rompRegions()) || []; return rs.filter((r) => r.kind === "run").length > n0; }, (regionsBefore6 || []).filter((r) => r.kind === "run").length, { timeout: 10000 }).catch(() => {});
await painted();
const point6After = await page.evaluate(() => (typeof window.__rompTurnUnderTop === "function" ? window.__rompTurnUnderTop() : null));
const after6 = await page.evaluate(() => { const c = document.getElementById("content"); const cr = c.getBoundingClientRect(); return { top: c.scrollTop, sh: c.scrollHeight, spacerTop: (document.querySelector("#content .tx-spacer-top") || {}).offsetHeight || 0, regions: typeof window.__rompRegions === "function" ? window.__rompRegions() : null, gaps: Array.from(document.querySelectorAll("#content .tx-gap")).map((g) => { const r = g.getBoundingClientRect(); return { lo: Number(g.dataset.lo), hi: Number(g.dataset.hi), y0: Math.round(r.top - cr.top + c.scrollTop), h: g.offsetHeight }; }), rows: c.querySelectorAll(".turn[data-uuid]").length }; });
const fillWrites6 = await page.evaluate((n) => window.__sent.slice(n).filter((m) => m.type === "clientDiag" && m.what === "scrollwrite" && m.data && m.data.writer === "gap-fill").map((m) => ({ b: m.data.before, a: m.data.after })), sentAt6);
await page.evaluate(() => { const c = document.getElementById("content"); c.scrollTop = c.scrollHeight; });   // back to the tail: the roads after start from the bottom as they always did
await painted();
// ROAD 1: a deep link into the head gap: the notice, the pre-jump, the ask (HELD at the socket so the wait can be sampled: a local kernel
// answers within the round trip), the landing once released
await page.evaluate(() => { window.__hold.add("loadAround"); });
const aroundBefore1 = await sentOf("loadAround");
await page.evaluate((frame) => window.postMessage(frame, "*"), { type: "focus", id: cfg.sid, anchor: ("11111111-2222-3333-4444-" + pad(2 * 125)), anchorT: (cfg.base + 2 * 125) });
await page.waitForFunction((ty) => (window.__heldRaw || []).some((d) => JSON.parse(d).type === ty), "loadAround", { timeout: 10000 }).catch(() => {});   // the HELD ask, where it lands (a parked frame never reaches __sent: the wait this replaces burned its timeout on every run)
await page.waitForFunction(() => document.querySelectorAll("#content .tx-gap-loading").length >= 1, null, { timeout: 5000 }).catch(() => {});   // the glyph paints on the pre-jump's re-window, a frame after the ask
const asked1 = await state();   // sampled while the ask is on the wire: the notice up, the view inside the gap
const heldAsk1 = await page.evaluate(() => (window.__heldRaw || []).length);   // the ask parked at the socket (a held frame never reaches the send log); sampled HERE: the fresh pages after this road reset that log
const trace1 = await trace();
const guess1 = await writes("land-guess");
await page.evaluate(() => { window.__hold.delete("loadAround"); window.__heldRaw = (window.__heldRaw || []).filter((d) => JSON.parse(d).type === "loadAround"); });
const released1 = await page.evaluate(() => window.__release());
await page.waitForFunction((u) => !!document.querySelector(`#content .turn[data-uuid="${u}"]`), ("11111111-2222-3333-4444-" + pad(2 * 125)), { timeout: 15000 }).catch(() => {});
await page.waitForFunction(() => { const n = document.querySelector(".tx-landing-notice"); return !n || getComputedStyle(n).display === "none"; }, null, { timeout: 10000 }).catch(() => {});
await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 0)))));
await page.waitForFunction((u) => window.__sent.some((m) => m.type === "locateDiag" && m.anchor === u && m.ok === true), ("11111111-2222-3333-4444-" + pad(2 * 125)), { timeout: 8000 }).catch(() => {});   // the landing's own row files when its settle ends
const landed1 = await state(); const regionsLanded = await page.evaluate(() => (typeof window.__rompRegions === "function" ? window.__rompRegions() : null));
const target1 = await onScreen(("11111111-2222-3333-4444-" + pad(2 * 125)));
const rows1 = await locateRows();
// ROAD 2: a second deep link, the ask held; the notice clicked away; the reply released late
const deep2 = "11111111-2222-3333-4444-" + pad(2 * 190);   // turn 190: inside the gap the first landing left (its window covered the head to about turn 70), clear of the tail
await page.evaluate(() => { window.__hold.add("loadAround"); });
const aroundBefore2 = await sentOf("loadAround"); const locBefore2 = rows1.length;
await page.evaluate((frame) => window.postMessage(frame, "*"), { type: "focus", id: cfg.sid, anchor: deep2, anchorT: cfg.base + 2 * 190 });
await page.waitForFunction((ty) => (window.__heldRaw || []).some((d) => JSON.parse(d).type === ty), "loadAround", { timeout: 10000 }).catch(() => {});   // the HELD ask, where it lands (a parked frame never reaches __sent: the wait this replaces burned its timeout on every run)
const asked2 = await state();
const trace2 = await trace();
// the ONLY cancel, clicked as a real user does: hit-tested at the notice's centre (a synthetic n.click() would pass even if the notice
// took no pointer, the round-one lesson), so record whether elementFromPoint IS the notice, then page.mouse.click its box
const noticeHit = await page.evaluate(() => { const n = document.querySelector(".tx-landing-notice"); if (!n) return null; const r = n.getBoundingClientRect(); const cx = r.left + r.width / 2, cy = r.top + r.height / 2; const el = document.elementFromPoint(cx, cy); return { x: cx, y: cy, isNotice: el === n || (!!el && n.contains(el)) }; });
if (noticeHit) await page.mouse.click(noticeHit.x, noticeHit.y);
await page.waitForFunction(() => { const n = document.querySelector(".tx-landing-notice"); return !n || getComputedStyle(n).display === "none"; }, null, { timeout: 5000 }).catch(() => {});
const clicked2 = await state(); const rowClicked2 = await rowAtTop(); const regionsClicked = await page.evaluate(() => (typeof window.__rompRegions === "function" ? window.__rompRegions() : null));
const rows2 = (await locateRows()).slice(locBefore2);
await page.evaluate(() => { window.__hold.delete("loadAround"); window.__heldRaw = (window.__heldRaw || []).filter((d) => JSON.parse(d).type === "loadAround"); });
const released2 = await page.evaluate(() => window.__release());
await page.waitForFunction((u) => !!document.querySelector(`#content .turn[data-uuid="${u}"]`) || window.__sent.some((m) => m.what === "scrollwrite" && m.data && m.data.writer === "gap-fill"), deep2, { timeout: 15000 }).catch(() => {});
await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 0)))));
const late2 = await state(); const rowLate2 = await rowAtTop(); const regionsLate = await page.evaluate(() => (typeof window.__rompRegions === "function" ? window.__rompRegions() : null));
const target2 = await onScreen(deep2);
// ROAD 4 (T386 stage 2, medium 3): a fill while the reader stands INSIDE a gap must not jump them. At the transcript head (scrollTop 0,
// no row on screen) a held gap-scroll ask, then the release: the head page fills and its first turn sits at the top, scrollTop still ~0.
await page.evaluate(() => { window.__hold.add("loadTurns"); });
await page.evaluate(() => { const c = document.getElementById("content"); c.scrollTop = 0; });
await page.waitForFunction((ty) => (window.__heldRaw || []).some((d) => JSON.parse(d).type === ty), "loadTurns", { timeout: 10000 }).catch(() => {});   // the HELD ask, where it lands (a parked frame never reaches __sent: the wait this replaces burned its timeout on every run)
const head4 = await page.evaluate(() => { const c = document.getElementById("content"); return { top: c.scrollTop, rows: c.querySelectorAll("#content .turn[data-uuid]").length }; });
await page.evaluate(() => { window.__hold.delete("loadTurns"); const n = window.__release(); return n; });
await page.waitForFunction(() => { const rs = (typeof window.__rompRegions === "function" && window.__rompRegions()) || []; return rs.length > 0 && rs[0].kind === "run" && rs[0].lo === 0; }, null, { timeout: 10000 }).catch(() => {});
await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 0)))));
const filled4 = await page.evaluate(() => { const c = document.getElementById("content"); const cTop = c.getBoundingClientRect().top; const first = c.querySelector("#content .turn[data-uuid]"); const r = first ? first.getBoundingClientRect() : null; return { top: c.scrollTop, firstTop: r ? Math.round(r.top - cTop) : null, firstVisible: !!r && r.bottom > cTop && r.top < c.getBoundingClientRect().bottom }; });
// ROAD 7 (round six, medium 2; a fresh page): the row under the viewport top is an answered AskUserQuestion, anchored on its ANSWER's
// uuid (a tool_result line no event carries as its own uuid). A fill ABOVE it (the cancel road: a deep link into the head gap, the
// notice clicked away, the window released) must keep that row at its offset and name the point under the viewport top as a turn:
// the row names its own turn (data-turn), the fill reads it, and looks nothing up by uuid.
await reboot();
// ROAD 7a (T386; a fresh page): a READER'S OWN SCROLL brings an answered AskUserQuestion (a row anchored on a tool_result uuid no event
// carries as its own) under the viewport top. A wheel over #content stamps the reader's input, so the scroll it drives is a gesture the
// settling landing YIELDS to (settleGesture), not a page sample it re-lands ("land-realign"); the row stays under the top, the reader's
// promise, whatever the message line-height (whole device px since the raster fix, no longer the exact 20.8 px road 7 once leaned on).
// Parked head-gap page asks (loadTurns) keep the gap whole (CI, 2026-09-14: a rebuild at the gap's top re-asked its first page).
await page.evaluate(() => { window.__hold.add("loadTurns"); });
const auqUser7 = "11111111-2222-3333-4444-" + pad(2 * 100), auqAnswer7 = "66666666-7777-8888-9999-" + pad(2 * 100);
await page.evaluate((frame) => window.postMessage(frame, "*"), { type: "focus", id: cfg.sid, anchor: auqUser7, anchorT: cfg.base + 2 * 100 });   // turn 100: its window (about turns 40 to 160) leaves the head gap above it
await page.waitForFunction((u) => !!document.querySelector(`#content .turn[data-uuid="${u}"]`), auqAnswer7, { timeout: 15000 }).catch(() => {});
await page.waitForFunction(() => { const n = document.querySelector(".tx-landing-notice"); return !n || getComputedStyle(n).display === "none"; }, null, { timeout: 10000 }).catch(() => {});
await painted();
const gestureToTop7 = () => page.evaluate((u) => { const c = document.getElementById("content"); const t = document.querySelector(`#content .turn[data-uuid="${u}"]`); if (c) c.dispatchEvent(new WheelEvent("wheel", { bubbles: true, deltaY: 4 })); if (t && c) c.scrollTop += t.getBoundingClientRect().top - c.getBoundingClientRect().top; }, auqAnswer7);   // the wheel (the reader's input) then the scroll it drives: a gesture the settle yields to, so the answer stays under the top
const nWr7a = await page.evaluate(() => window.__sent.length);
await gestureToTop7();
await page.waitForFunction((n) => window.__sent.slice(n).some((m) => m.type === "locateDiag" && "settled" in m), nWr7a, { timeout: 15000 }).catch(() => {});   // the gesture's takeover ends the settle: its landing row files
await painted();
const top7a = await rowAtTop();
const turnAttr7a = await page.evaluate((u) => { const t = document.querySelector(`#content .turn[data-uuid="${u}"]`); return t ? (t.dataset.turn === undefined ? null : t.dataset.turn) : "absent"; }, auqAnswer7);
const point7a = await page.evaluate(() => (typeof window.__rompTurnUnderTop === "function" ? window.__rompTurnUnderTop() : null));
const realign7a = await page.evaluate((n) => window.__sent.slice(n).filter((m) => m.type === "clientDiag" && m.what === "scrollwrite" && m.data && m.data.writer === "land-realign").length, nWr7a);   // zero: the settle yielded to the gesture, it did not snap the row back
await page.evaluate(() => { window.__hold.delete("loadTurns"); window.__heldRaw = []; });
await reboot();
// ROAD 7b (T386; a fresh page): at the viewport the landing LEAVES (the answered question's turn at the top, NO scroll), a fill ABOVE it (a
// deep link into the head gap, held at the socket, its notice clicked to stay, then released) inserts its run above the reader WITHOUT moving
// the point under the top: it holds at turn 100, named by position through the insertion. No scroll here, so no settle to fight: the reader
// who lands and stays keeps their place while history fills in above them.
await page.evaluate(() => { window.__hold.add("loadTurns"); });
await page.evaluate((frame) => window.postMessage(frame, "*"), { type: "focus", id: cfg.sid, anchor: auqUser7, anchorT: cfg.base + 2 * 100 });
await page.waitForFunction((u) => !!document.querySelector(`#content .turn[data-uuid="${u}"]`), auqAnswer7, { timeout: 15000 }).catch(() => {});
await page.waitForFunction(() => { const n = document.querySelector(".tx-landing-notice"); return !n || getComputedStyle(n).display === "none"; }, null, { timeout: 10000 }).catch(() => {});
await painted();
const sentAt7b = await page.evaluate(() => window.__sent.length);
await page.waitForFunction((sid) => { const a = window.__rompAskState(sid); return a.asks.length === 0 && !a.loadingOlder && !!window.__ws && window.__ws.readyState === 1; }, cfg.sid, { timeout: 15000 }).catch(() => {});   // the landing settled: no window ask in flight, the socket open
const rowTurnAtTop = () => page.evaluate(() => { const c = document.getElementById("content"); const cTop = c.getBoundingClientRect().top; for (const t of Array.from(document.querySelectorAll("#content .turn[data-uuid]"))) { const r = t.getBoundingClientRect(); if (r.bottom > cTop + 1) return { uuid: t.dataset.uuid, turn: t.dataset.turn === undefined ? null : t.dataset.turn, y: Math.round(r.top - cTop) }; } return null; });
const pointUnderTop = () => page.evaluate(() => (typeof window.__rompTurnUnderTop === "function" ? window.__rompTurnUnderTop() : null));
const rowB7Before = await rowTurnAtTop();
const pointB7Before = await pointUnderTop();
await page.evaluate(() => { window.__hold.add("loadAround"); });
await page.evaluate((frame) => window.postMessage(frame, "*"), { type: "focus", id: cfg.sid, anchor: "11111111-2222-3333-4444-" + pad(2 * 10), anchorT: cfg.base + 2 * 10 });   // turn 10: a fill in the head gap above the landed window
await page.waitForFunction(() => (window.__heldRaw || []).some((d) => JSON.parse(d).type === "loadAround"), null, { timeout: 15000 }).catch(() => {});   // the fill's window ask, parked at the socket
await page.waitForFunction(() => { const n = document.querySelector(".tx-landing-notice"); return !!n && getComputedStyle(n).display !== "none"; }, null, { timeout: 5000 }).catch(() => {});
const held7b = await page.evaluate(() => (window.__heldRaw || []).filter((d) => JSON.parse(d).type === "loadAround").length);
const askState7b = await page.evaluate((sid) => ({ ask: window.__rompAskState(sid), socket: window.__ws ? window.__ws.readyState : null, held: (window.__heldRaw || []).map((d) => JSON.parse(d).type) }), cfg.sid);
await page.evaluate(() => { const n = document.querySelector(".tx-landing-notice"); if (n) { const r = n.getBoundingClientRect(); n.dispatchEvent(new MouseEvent("click", { bubbles: true, clientX: r.left + r.width / 2, clientY: r.top + r.height / 2 })); } });   // click to STAY: the turn-10 navigation is cancelled, the reader kept at the landed turn 100
await page.waitForFunction(() => { const n = document.querySelector(".tx-landing-notice"); return !n || getComputedStyle(n).display === "none"; }, null, { timeout: 5000 }).catch(() => {});
await quiet();   // the click's deferred write has run: the reader is back at the landed place
const rowB7Held = await rowTurnAtTop();
const pointB7Held = await pointUnderTop();
const runN7 = () => page.evaluate(() => ((typeof window.__rompRegions === "function" && window.__rompRegions()) || []).filter((r) => r.kind === "run").reduce((a, r) => a + r.n, 0));
const runNBefore7b = await runN7();
await page.evaluate(() => { window.__hold.delete("loadAround"); window.__heldRaw = (window.__heldRaw || []).filter((d) => JSON.parse(d).type === "loadAround"); window.__release(); });   // the fill's window alone goes out; a parked page ask is dropped
await page.waitForFunction((n0) => ((typeof window.__rompRegions === "function" && window.__rompRegions()) || []).filter((r) => r.kind === "run").reduce((a, r) => a + r.n, 0) > n0, runNBefore7b, { timeout: 15000 }).catch(() => {});
await painted();
const rowB7After = await rowTurnAtTop();
const pointB7After = await pointUnderTop();
const runNAfter7b = await runN7();
const fillWrites7b = await page.evaluate((n) => window.__sent.slice(n).filter((m) => m.type === "clientDiag" && m.what === "scrollwrite" && m.data && m.data.writer === "gap-fill").map((m) => ({ b: m.data.before, a: m.data.after })), sentAt7b);
await page.evaluate(() => { window.__hold.delete("loadTurns"); window.__heldRaw = []; });
// ROAD 8 (round seven, medium 3; a fresh page): the notice's click cancels a landing whose ask is still on the wire; the reader's NEXT
// card click must ask, not be refused as "still going to the earlier message" (a cancelled landing is not busy). Two deep links into two
// gaps, both held: A's notice clicked away, then B asked; both released: A's window fills in place under the cancelled mark, B lands.
await reboot();
const deepA8 = "11111111-2222-3333-4444-" + pad(2 * 60), deepB8 = "11111111-2222-3333-4444-" + pad(2 * 170);
await page.evaluate(() => { window.__hold.add("loadAround"); });
const heldN = () => page.evaluate(() => (window.__heldRaw || []).length);   // a HELD ask is parked before the send hook __sent reads, so held asks are counted here
await page.evaluate((frame) => window.postMessage(frame, "*"), { type: "focus", id: cfg.sid, anchor: deepA8, anchorT: cfg.base + 2 * 60 });
await page.waitForFunction(() => (window.__heldRaw || []).length >= 1, null, { timeout: 8000 }).catch(() => {});
await page.waitForFunction(() => { const n = document.querySelector(".tx-landing-notice"); return !!n && getComputedStyle(n).display !== "none"; }, null, { timeout: 5000 }).catch(() => {});
const askedA8 = await heldN();
await page.evaluate(() => { const n = document.querySelector(".tx-landing-notice"); if (n) { const r = n.getBoundingClientRect(); n.dispatchEvent(new MouseEvent("click", { bubbles: true, clientX: r.left + r.width / 2, clientY: r.top + r.height / 2 })); } });
await page.waitForFunction(() => { const n = document.querySelector(".tx-landing-notice"); return !n || getComputedStyle(n).display === "none"; }, null, { timeout: 5000 }).catch(() => {});
await page.waitForFunction(() => document.querySelectorAll("#content .tx-gap-loading").length === 0, null, { timeout: 3000 }).catch(() => {});   // a re-window the pre-jump's write scheduled may still be painting; the glyph count is read once it settles (a glyph that stays is the finding)
const afterCancel8 = { notice: (await state()).notice, ask: await page.evaluate((sid) => (typeof window.__rompAskState === "function" ? window.__rompAskState(sid) : null), cfg.sid), glyphs: await page.evaluate(() => document.querySelectorAll("#content .tx-gap-loading").length),
  // the glyphs and the live asks in ONE evaluation: the reader now stands inside the gap, which asks for its own page when on screen and wears
  // the glyph for THAT ask; a glyph must belong to a live ask, never to the cancelled landing (two reads a moment apart disagreed)
  atomic: await page.evaluate((sid) => ({ glyphGaps: Array.from(document.querySelectorAll("#content .tx-gap-loading")).map((g) => [Number(g.dataset.lo), Number(g.dataset.hi)]), ask: (typeof window.__rompAskState === "function" ? window.__rompAskState(sid) : null) }), cfg.sid),
  regions: await page.evaluate(() => (typeof window.__rompRegions === "function" ? window.__rompRegions() : null)),
  trail: (await state()).sent.slice(-16) };
const trailAt8 = await page.evaluate(() => window.__sent.length);
await page.evaluate((frame) => window.postMessage(frame, "*"), { type: "focus", id: cfg.sid, anchor: deepB8, anchorT: cfg.base + 2 * 170 });
await page.waitForFunction((n) => (window.__heldRaw || []).length > n, askedA8, { timeout: 5000 }).catch(() => {});
const askedB8 = (await heldN()) - askedA8;
const busy8 = await page.evaluate((n) => window.__sent.slice(n).filter((m) => m.type === "locateDiag").flatMap((m) => m.trail || []).filter((w) => w === "pointer-fetch-busy").length, trailAt8);
const toast8 = await page.evaluate(() => { const tt = document.querySelector(".locate-toast"); return tt ? tt.textContent : null; });
const noticeB8 = (await state()).notice;
const runN8Before = await runN7();
await page.evaluate(() => { window.__hold.delete("loadAround"); });
const released8 = await page.evaluate(() => window.__release());
await page.waitForFunction((u) => !!document.querySelector(`#content .turn[data-uuid="${u}"]`), deepB8, { timeout: 15000 }).catch(() => {});
await page.waitForFunction(() => { const n = document.querySelector(".tx-landing-notice"); return !n || getComputedStyle(n).display === "none"; }, null, { timeout: 10000 }).catch(() => {});
await painted();
const targetB8 = await onScreen(deepB8);
const residentA8 = await page.evaluate((u) => !!document.querySelector(`#content .turn[data-uuid="${u}"]`) || (((typeof window.__rompRegions === "function" && window.__rompRegions()) || []).some((r) => r.kind === "run" && r.lo <= 60 && (r.hi == null || 60 < r.hi))), deepA8);
const runN8After = await runN7();
// ROAD 9 (round seven, medium 1; a fresh page): the kernel's FAULT reply to a landing, in the wrapper's exact shape (missing true, fault
// true, the anchor echoed, an error): no verdict on the anchor, so the reader is not told the message is gone; the landing stands down
// with its own word, its row files as a fault, the pre-jump is undone and the state clears.
await reboot();   // a fresh page: road 8's two windows merge with the tail and leave no gap
const deep9 = "11111111-2222-3333-4444-" + pad(2 * 40);   // turn 40: in the head gap
await page.evaluate(() => { window.__hold.add("loadAround"); });
const top9Before = await page.evaluate(() => document.getElementById("content").scrollTop);
const sentAt9 = await page.evaluate(() => window.__sent.length);
await page.evaluate((frame) => window.postMessage(frame, "*"), { type: "focus", id: cfg.sid, anchor: deep9, anchorT: cfg.base + 2 * 40 });
await page.waitForFunction(() => (window.__heldRaw || []).length >= 1, null, { timeout: 8000 }).catch(() => {});
await page.waitForFunction(() => { const n = document.querySelector(".tx-landing-notice"); return !!n && getComputedStyle(n).display !== "none"; }, null, { timeout: 5000 }).catch(() => {});
const asked9 = { notice: (await state()).notice, top: await page.evaluate(() => document.getElementById("content").scrollTop) };
const rowsBefore9 = (await locateRows()).length;
await page.evaluate(([sid, anchor]) => window.postMessage({ type: "chatWindow", id: sid, anchor, missing: true, fault: true, error: "RuntimeError: the page renderer raised (synthetic)" }, "*"), [cfg.sid, deep9]);
await page.waitForFunction(() => { const n = document.querySelector(".tx-landing-notice"); return !n || getComputedStyle(n).display === "none"; }, null, { timeout: 5000 }).catch(() => {});
await painted();
const fault9 = { notice: (await state()).notice, toast: await page.evaluate(() => { const tt = document.querySelector(".locate-toast"); return tt ? tt.textContent : null; }),
  top: await page.evaluate(() => document.getElementById("content").scrollTop), ask: await page.evaluate((sid) => (typeof window.__rompAskState === "function" ? window.__rompAskState(sid) : null), cfg.sid),
  atBottom: await page.evaluate(() => { const c = document.getElementById("content"); return c.scrollHeight - c.scrollTop - c.clientHeight <= 2; }),
  seekNote: await page.evaluate(() => !!document.getElementById("seek-note")) };
const rows9 = (await locateRows()).slice(rowsBefore9);
const writes9 = await page.evaluate((n) => window.__sent.slice(n).filter((m) => m.type === "clientDiag" && m.what === "scrollwrite" && m.data).map((m) => [m.data.writer, m.data.before, m.data.after]), sentAt9);
const pxPerTurn9 = await page.evaluate(() => { const c = document.getElementById("content"); const rows = Array.from(c.querySelectorAll(".turn")); const users = rows.filter((r) => r.classList.contains("turn-user")).length; const h = rows.reduce((a, r) => a + r.offsetHeight, 0); return users ? h / users : null; });
await page.evaluate(() => { window.__hold.delete("loadAround"); window.__heldRaw = []; });
// ROAD 10 (round eight, medium 1; a fresh page): two landings cancelled on one session, their asks held; released ONE at a time, oldest
// first: neither reply moves the reader (each fills in place under its own record), and both runs are resident after.
await reboot();
const deepA10 = "11111111-2222-3333-4444-" + pad(2 * 60), deepB10 = "11111111-2222-3333-4444-" + pad(2 * 170);
const clickCancel = async (anchor, t) => {   // a deep link whose ask is HELD, its notice clicked away
  const before = await heldN();
  await page.evaluate((frame) => window.postMessage(frame, "*"), { type: "focus", id: cfg.sid, anchor, anchorT: t });
  await page.waitForFunction((n) => (window.__heldRaw || []).length > n, before, { timeout: 8000 }).catch(() => {});
  await page.waitForFunction(() => { const n = document.querySelector(".tx-landing-notice"); return !!n && getComputedStyle(n).display !== "none"; }, null, { timeout: 5000 }).catch(() => {});
  await page.evaluate(() => { const n = document.querySelector(".tx-landing-notice"); if (n) { const r = n.getBoundingClientRect(); n.dispatchEvent(new MouseEvent("click", { bubbles: true, clientX: r.left + r.width / 2, clientY: r.top + r.height / 2 })); } });
  await page.waitForFunction(() => { const n = document.querySelector(".tx-landing-notice"); return !n || getComputedStyle(n).display === "none"; }, null, { timeout: 5000 }).catch(() => {});
  return (await heldN()) - before;
};
await page.evaluate(() => { window.__hold.add("loadAround"); });
const askedA10 = await clickCancel(deepA10, cfg.base + 2 * 60);
const askedB10 = await clickCancel(deepB10, cfg.base + 2 * 170);
const asks10 = await page.evaluate((sid) => (typeof window.__rompAskState === "function" ? window.__rompAskState(sid) : null), cfg.sid);
await painted();
const pointNow = () => page.evaluate(() => (typeof window.__rompTurnUnderTop === "function" ? window.__rompTurnUnderTop() : null));   // the point under the viewport top as a TURN: the reader stands inside the head gap, so no row is on screen
const before10 = { top: await page.evaluate(() => document.getElementById("content").scrollTop), row: await rowAtTop(), point: await pointNow() };
const runN10a = await runN7();
await page.evaluate(() => { window.__hold.delete("loadAround"); });
const relA10 = await page.evaluate(() => window.__releaseOne());   // A's reply alone
await page.waitForFunction((n0) => ((typeof window.__rompRegions === "function" && window.__rompRegions()) || []).filter((r) => r.kind === "run").reduce((a, r) => a + r.n, 0) > n0, runN10a, { timeout: 15000 }).catch(() => {});
await painted();
const afterA10 = { top: await page.evaluate(() => document.getElementById("content").scrollTop), row: await rowAtTop(), point: await pointNow(), targetA: await onScreen(deepA10), notice: (await state()).notice };
const runN10b = await runN7();
const relB10 = await page.evaluate(() => window.__releaseOne());   // then B's
await page.waitForFunction((n0) => ((typeof window.__rompRegions === "function" && window.__rompRegions()) || []).filter((r) => r.kind === "run").reduce((a, r) => a + r.n, 0) > n0, runN10b, { timeout: 15000 }).catch(() => {});
await painted();
const afterB10 = { top: await page.evaluate(() => document.getElementById("content").scrollTop), row: await rowAtTop(), point: await pointNow(), targetB: await onScreen(deepB10), notice: (await state()).notice };
const runN10c = await runN7();
const writes10 = await page.evaluate(() => window.__sent.filter((m) => m.type === "clientDiag" && m.what === "scrollwrite" && m.data && (m.data.writer === "land-on" || m.data.writer === "land-cancel")).map((m) => [m.data.writer, m.data.before, m.data.after]));
// ROAD 11 (round eight, medium 2; a fresh page): a cancelled landing's pre-jump origin must die with the cancel. A deep link A (held) is
// cancelled, leaving the reader where the pre-jump put them; a deep link B with NO time (no pre-jump) then dead-ends on a missing reply:
// the reader stays where B found them, never restored to A's origin.
await reboot();
const deepA11 = "11111111-2222-3333-4444-" + pad(2 * 60), deepB11 = "11111111-2222-3333-4444-" + pad(2 * 170);
await page.evaluate(() => { window.__hold.add("loadAround"); });
const originA11 = await page.evaluate(() => document.getElementById("content").scrollTop);   // A's origin: the tail
const askedA11 = await clickCancel(deepA11, cfg.base + 2 * 60);
await painted();
const foundB11 = await page.evaluate(() => document.getElementById("content").scrollTop);   // where B finds the reader: inside the gap, where A's pre-jump left them
const heldBefore11 = await heldN();
await page.evaluate((frame) => window.postMessage(frame, "*"), { type: "focus", id: cfg.sid, anchor: deepB11 });   // no anchorT: no pre-jump
await page.waitForFunction((n) => (window.__heldRaw || []).length > n, heldBefore11, { timeout: 8000 }).catch(() => {});
const askedB11 = (await heldN()) - heldBefore11;
const noticeB11 = (await state()).notice;
const atAsk11 = await page.evaluate(() => document.getElementById("content").scrollTop);
await page.evaluate(([sid, anchor]) => window.postMessage({ type: "chatWindow", id: sid, anchor, missing: true }, "*"), [cfg.sid, deepB11]);   // B's honest end
await page.waitForFunction(() => { const n = document.querySelector(".tx-landing-notice"); return !n || getComputedStyle(n).display === "none"; }, null, { timeout: 5000 }).catch(() => {});
await painted();
const afterMissing11 = { top: await page.evaluate(() => document.getElementById("content").scrollTop), toast: await page.evaluate(() => { const tt = document.querySelector(".locate-toast"); return tt ? tt.textContent : null; }), notice: (await state()).notice };
const writes11 = await page.evaluate(() => window.__sent.filter((m) => m.type === "clientDiag" && m.what === "scrollwrite" && m.data && m.data.writer === "land-cancel").map((m) => [m.data.writer, m.data.before, m.data.after]));
await page.evaluate(() => { window.__hold.delete("loadAround"); window.__heldRaw = []; });
// ROAD 12 (round eight, medium 3; a fresh page): a cancelled ask whose frame is LOST with the socket alive must not eat the next landing on
// the same anchor: click A (held), cancel, drop the parked frame, click A again: it asks and lands.
await reboot();
const deepA12 = "11111111-2222-3333-4444-" + pad(2 * 60);
await page.evaluate(() => { window.__hold.add("loadAround"); });
const askedA12 = await clickCancel(deepA12, cfg.base + 2 * 60);
await page.evaluate(() => { window.__heldRaw = []; window.__hold.delete("loadAround"); });   // the frame is lost; the socket lives
const sentAt12 = await page.evaluate(() => window.__sent.length);
await page.evaluate((frame) => window.postMessage(frame, "*"), { type: "focus", id: cfg.sid, anchor: deepA12, anchorT: cfg.base + 2 * 60 });
await page.waitForFunction((u) => !!document.querySelector(`#content .turn[data-uuid="${u}"]`), deepA12, { timeout: 15000 }).catch(() => {});
await page.waitForFunction(() => { const n = document.querySelector(".tx-landing-notice"); return !n || getComputedStyle(n).display === "none"; }, null, { timeout: 10000 }).catch(() => {});
await painted();
const reask12 = await page.evaluate((n) => window.__sent.slice(n).filter((m) => m.type === "loadAround").length, sentAt12);
const target12 = await onScreen(deepA12);
const trail12 = await page.evaluate((n) => window.__sent.slice(n).filter((m) => m.type === "locateDiag").map((m) => ({ ok: m.ok, trail: (m.trail || []).slice(-4) })), sentAt12);
// ROAD 13 (round nine, medium 1; a fresh page): a proto-2 frame whose tailLo the kernel could not name (the boot frame re-posted with tailLo
// null, headKnown false) leaves the page with no regions and its head asked by loadOlder; with that fetch HELD on the wire, a card click
// must not be refused as busy: the fetch is re-pointed onto the anchor and, once the older page is released, the target lands.
await reboot();
// the kernel would answer the page's own full-frame ask (a tail delta missing its anchor asks needFull) with a frame that names tailLo and
// rebuilds the regions within a frame or two, so that ask is parked too: the fallback must stand while the road runs
await page.evaluate(() => { window.__hold.add("needFull"); window.__hold.add("loadOlder"); window.__hold.add("loadTurns"); });
// …and the kernel's own session frames are parked at the page too (a capturing listener runs before the page's; the lab's re-post is let
// through by its mark): the first try showed the regions rebuilt within a frame of the re-post by a fresh frame from the kernel
await page.evaluate(() => { window.__holdIn = new Set(["session"]); window.__heldIn = []; if (!window.__inHook) { window.__inHook = true; window.addEventListener("message", (e) => { const m = e.data; if (m && m.type && window.__holdIn && window.__holdIn.has(m.type) && !m.__lab) { window.__heldIn.push(m.type + ":" + (m.tailLo === undefined ? "?" : String(m.tailLo))); e.stopImmediatePropagation(); } }, true); } });
const frame13 = await page.evaluate(() => window.__bootFrame ? Object.assign({}, window.__bootFrame, { tailLo: null, headKnown: false, __lab: true }) : null);
const hadFrame13 = !!frame13;
await page.evaluate((f) => { if (f) window.postMessage(f, "*"); }, frame13);
await painted();
const regions13 = await page.evaluate(() => (typeof window.__rompRegions === "function" ? window.__rompRegions() : null));
const heldIn13a = await page.evaluate(() => (window.__heldIn || []).slice());
await page.evaluate(() => { const c = document.getElementById("content"); c.scrollTop = 0; });   // the top edge: the head asked by loadOlder (the fallback), parked
await page.waitForFunction(() => (window.__heldRaw || []).some((d) => { try { return JSON.parse(d).type === "loadOlder"; } catch (e) { return false; } }), null, { timeout: 8000 }).catch(() => {});
const heldOlder13 = await page.evaluate(() => (window.__heldRaw || []).filter((d) => { try { return JSON.parse(d).type === "loadOlder"; } catch (e) { return false; } }).length);
const askState13 = await page.evaluate((sid) => (typeof window.__rompAskState === "function" ? window.__rompAskState(sid) : null), cfg.sid);
const sentAt13 = await page.evaluate(() => window.__sent.length);
const deep13 = "11111111-2222-3333-4444-" + pad(2 * 100);
await page.evaluate((frame) => window.postMessage(frame, "*"), { type: "focus", id: cfg.sid, anchor: deep13, anchorT: cfg.base + 2 * 100 });
await painted();
const trail13 = await page.evaluate(() => (typeof window.__rompLandTrail === "function" ? window.__rompLandTrail() : null));
const toast13 = await page.evaluate(() => { const tt = document.querySelector(".locate-toast"); return tt ? tt.textContent : null; });
const heldIn13 = await page.evaluate(() => { const h = (window.__heldIn || []).slice(); window.__holdIn = new Set(); return h; });   // the kernel's frames flow again
await page.evaluate(() => { window.__hold.delete("loadOlder"); window.__hold.delete("needFull"); window.__hold.delete("loadTurns"); window.__release(); });   // the parked asks go out: the older page (and any full frame) arrives
await page.waitForFunction((u) => !!document.querySelector(`#content .turn[data-uuid="${u}"]`), deep13, { timeout: 20000 }).catch(() => {});
await page.waitForFunction((u) => { const t = document.querySelector(`#content .turn[data-uuid="${u}"]`); if (!t) return false; const c = document.getElementById("content").getBoundingClientRect(), r = t.getBoundingClientRect(); return r.bottom > c.top && r.top < c.bottom; }, deep13, { timeout: 15000 }).catch(() => {});
await painted();
const target13 = await onScreen(deep13);
const asks13 = await page.evaluate((n) => ({ loadOlder: window.__sent.slice(n).filter((m) => m.type === "loadOlder").length, loadAround: window.__sent.slice(n).filter((m) => m.type === "loadAround").length, busy: window.__sent.slice(n).filter((m) => m.type === "locateDiag").flatMap((m) => m.trail || []).filter((w) => w === "pointer-fetch-busy").length }), sentAt13);
// ROAD 14 (round nine, medium 2; a fresh page): the VS Code pane's down edge is the pipeState frame; a landing in flight (its ask held) then
// pipeState down must clear the ask's record, the notice and the busy meaning, and pipeState up must leave the next card click free to ask.
await reboot();
await page.evaluate(() => { window.__hold.add("loadAround"); window.__hold.add("loadTurns"); });   // the gap's own page asks are parked too: a page ask the road produces is read at the socket, never answered under the read
const deep14 = "11111111-2222-3333-4444-" + pad(2 * 60);
await page.evaluate((frame) => window.postMessage(frame, "*"), { type: "focus", id: cfg.sid, anchor: deep14, anchorT: cfg.base + 2 * 60 });
await page.waitForFunction(() => (window.__heldRaw || []).length >= 1, null, { timeout: 8000 }).catch(() => {});
await page.waitForFunction(() => { const n = document.querySelector(".tx-landing-notice"); return !!n && getComputedStyle(n).display !== "none"; }, null, { timeout: 5000 }).catch(() => {});
const before14 = { notice: (await state()).notice, ask: await page.evaluate((sid) => (typeof window.__rompAskState === "function" ? window.__rompAskState(sid) : null), cfg.sid) };
await page.evaluate(() => { window.__heldRaw = []; window.postMessage({ type: "pipeState", up: false, queued: 0 }, "*"); });   // the pipe goes down with the ask lost
await painted();
// CI's order (main red at e7729438): a kernel frame's rebuild lands between the clear and the read. The rebuild re-creates the gap element
// under the reader and the observer's first delivery finds the gap with NO ask on it (the landing's record, which had stood in for the gap's
// own ask, went with the clear), so the gap asks for the page at the edge the reader stands on, its first (turns 0 to 16). The boot frame
// re-posted is that rebuild; the page ask is parked at the socket (loadTurns held), so what stands after is read, not raced.
await page.evaluate(() => { if (window.__bootFrame) window.postMessage(window.__bootFrame, "*"); });
await painted();
const heldDown14 = await page.evaluate(() => (window.__heldRaw || []).map((d) => { const m = JSON.parse(d); return m.type + ":" + (m.lo ?? "") + "-" + (m.hi ?? ""); }));
const down14 = { held: heldDown14, notice: (await state()).notice, ask: await page.evaluate((sid) => (typeof window.__rompAskState === "function" ? window.__rompAskState(sid) : null), cfg.sid), toast: await page.evaluate(() => { const tt = document.querySelector(".locate-toast"); return tt ? tt.textContent : null; }) };
await page.evaluate(() => { window.__heldRaw = []; window.postMessage({ type: "pipeState", up: true, queued: 0 }, "*"); });   // the parked page ask dropped with the down pipe; the pipe comes back
await painted();
await page.evaluate(() => { window.__hold.delete("loadAround"); window.__hold.delete("loadTurns"); });
const sentAt14 = await page.evaluate(() => window.__sent.length);
await page.evaluate((frame) => window.postMessage(frame, "*"), { type: "focus", id: cfg.sid, anchor: deep14, anchorT: cfg.base + 2 * 60 });
await page.waitForFunction((u) => !!document.querySelector(`#content .turn[data-uuid="${u}"]`), deep14, { timeout: 15000 }).catch(() => {});
await page.waitForFunction(() => { const n = document.querySelector(".tx-landing-notice"); return !n || getComputedStyle(n).display === "none"; }, null, { timeout: 10000 }).catch(() => {});
await painted();
const after14 = { asked: await page.evaluate((n) => window.__sent.slice(n).filter((m) => m.type === "loadAround").length, sentAt14), busy: await page.evaluate((n) => window.__sent.slice(n).filter((m) => m.type === "locateDiag").flatMap((m) => m.trail || []).filter((w) => w === "pointer-fetch-busy").length, sentAt14), target: await onScreen(deep14) };
// ROAD 15 (the follow-up after PR 1584, low 1; a fresh page): the notice's pulse is ONE-SHOT. A real second click on the anchor a landing is on
// the wire for pulses the notice once (round eleven, low b); the class must leave on the animation's end, so a LATER landing that re-shows the
// one reused notice element does not replay a pulse it did not earn (before the fix the class stayed and the display flip restarted the
// animation: the verifier saw it running after the re-show). Pulses are counted from the element's own animationstart events.
await reboot();
await page.evaluate(() => { window.__pulses = 0; document.addEventListener("animationstart", (e) => { if (e.animationName === "tx-notice-pulse") window.__pulses++; }, true); window.__hold.add("loadAround");
  // every animationend listener added to or removed from the notice element is counted (the tidy after PR 1642, low 2): a pulse the hide cuts short
  // never fires animationend, so its once listener stayed on the reused element, one dead closure per cut pulse
  window.__aeAdd = 0; window.__aeRemove = 0; const isNotice = (el) => el instanceof Element && el.classList.contains("tx-landing-notice");
  const ael = EventTarget.prototype.addEventListener, rel = EventTarget.prototype.removeEventListener;
  EventTarget.prototype.addEventListener = function (ty, fn, opt) { if (ty === "animationend" && isNotice(this)) window.__aeAdd++; return ael.call(this, ty, fn, opt); };
  EventTarget.prototype.removeEventListener = function (ty, fn, opt) { if (ty === "animationend" && isNotice(this)) window.__aeRemove++; return rel.call(this, ty, fn, opt); }; });
const deepA15 = "11111111-2222-3333-4444-" + pad(2 * 45); const deepB15 = "11111111-2222-3333-4444-" + pad(2 * 160);   // both in the head gap of a fresh page
const focus15 = (u, turn) => page.evaluate((frame) => window.postMessage(frame, "*"), { type: "focus", id: cfg.sid, anchor: u, anchorT: cfg.base + 2 * turn });
const noticeShown = () => page.waitForFunction(() => { const n = document.querySelector(".tx-landing-notice"); return !!n && getComputedStyle(n).display !== "none"; }, null, { timeout: 5000 }).catch(() => {});
const noticeHidden = () => page.waitForFunction(() => { const n = document.querySelector(".tx-landing-notice"); return !n || getComputedStyle(n).display === "none"; }, null, { timeout: 10000 }).catch(() => {});
const pulseState = () => page.evaluate(() => { const n = document.querySelector(".tx-landing-notice"); return { pulses: window.__pulses, cls: !!n && n.classList.contains("pulse"), running: n ? n.getAnimations().length : -1, notice: !!n && getComputedStyle(n).display !== "none" }; });
await focus15(deepA15, 45);
await page.waitForFunction(() => (window.__heldRaw || []).length >= 1, null, { timeout: 8000 }).catch(() => {});
await noticeShown();
const first15 = await pulseState();                                                   // one click: the notice, no pulse
await focus15(deepA15, 45);                                                           // a REAL second click on the same anchor while its ask is on the wire
await page.waitForFunction(() => window.__pulses >= 1, null, { timeout: 3000 }).catch(() => {});
const pulsed15 = await pulseState();
await page.waitForFunction(() => { const n = document.querySelector(".tx-landing-notice"); return !!n && !n.classList.contains("pulse"); }, null, { timeout: 3000 }).catch(() => {});   // the class leaves on the animation's end (500 ms)
const afterEnd15 = await pulseState();
const listeners15 = await page.evaluate(() => ({ add: window.__aeAdd, remove: window.__aeRemove }));   // one completed pulse: one listener added, and gone by its own once
await page.evaluate(() => { window.__hold.delete("loadAround"); window.__release(); });
await page.waitForFunction((u) => !!document.querySelector(`#content .turn[data-uuid="${u}"]`), deepA15, { timeout: 15000 }).catch(() => {});
await noticeHidden(); await painted();
const targetA15 = await onScreen(deepA15);
// a later landing re-shows the same notice element: no pulse it did not earn
await page.evaluate(() => { window.__hold.add("loadAround"); });
await focus15(deepB15, 160);
await page.waitForFunction(() => (window.__heldRaw || []).length >= 1, null, { timeout: 8000 }).catch(() => {});
await noticeShown();
await page.waitForTimeout(200);                                                       // a replayed animation would have started by now (a stale class restarts on the display flip)
const reshow15 = await pulseState();
// a pulse CUT SHORT by the hide: a real second click on B pulses, and the release lands B within the animation's 500 ms, hiding the notice mid-pulse
await focus15(deepB15, 160);
await page.waitForFunction((n) => window.__pulses > n, reshow15.pulses, { timeout: 3000 }).catch(() => {});
const cut15 = await page.evaluate(() => ({ pulses: window.__pulses, add: window.__aeAdd, remove: window.__aeRemove, cls: !!document.querySelector(".tx-landing-notice.pulse") }));
await page.evaluate(() => { window.__hold.delete("loadAround"); window.__release(); });
await page.waitForFunction((u) => !!document.querySelector(`#content .turn[data-uuid="${u}"]`), deepB15, { timeout: 15000 }).catch(() => {});
await noticeHidden(); await painted();
const targetB15 = await onScreen(deepB15);
await page.waitForTimeout(700);                                                       // past the cut animation's own length: a listener the hide did not remove would still be there
const afterCut15 = await page.evaluate(() => ({ add: window.__aeAdd, remove: window.__aeRemove, cls: !!document.querySelector(".tx-landing-notice.pulse"), shown: (() => { const n = document.querySelector(".tx-landing-notice"); return !!n && getComputedStyle(n).display !== "none"; })() }));
process.stdout.write("RESULT:" + JSON.stringify({ listeners15, cut15, afterCut15, first15, pulsed15, afterEnd15, targetA15, reshow15, targetB15, inGap6, regions13, hadFrame13, heldIn13a, heldIn13, heldOlder13, askState13, trail13, toast13, target13, asks13, before14, down14, after14, askedA10, askedB10, asks10, before10, relA10, afterA10, relB10, afterB10, runN10a, runN10b, runN10c, writes10, originA11, askedA11, foundB11, askedB11, noticeB11, atAsk11, afterMissing11, writes11, askedA12, reask12, target12, trail12, askedA8, afterCancel8, askedB8, busy8, toast8, noticeB8, released8, targetB8, residentA8, runN8Before, runN8After, asked9, fault9, rows9, top9Before, writes9, pxPerTurn9, heldAsk6, point6Before, point6After, fillWrites6, after6, head4, filled4, afterDrop5: { notice: afterDrop5.notice }, askBefore5, heldRaw5, askState5, winBefore5, winAtDeath5, redialed5, recvAfter5, sentAfter5, flushAsk5, reask5, landed5, top7a, turnAttr7a, point7a, realign7a, rowB7Before, pointB7Before, rowB7Held, pointB7Held, rowB7After, pointB7After, held7b, askState7b, fillWrites7b, runNBefore7b, runNAfter7b, asked3, nospan3, boot: { gaps: boot.gaps, atBottom: boot.atBottom, notice: boot.notice, regions: await page.evaluate(() => (typeof window.__rompRegions === "function" ? window.__rompRegions() : null)) }, asked1: { notice: asked1.notice, noticeText: asked1.noticeText, top: asked1.top, gaps: asked1.gaps, loadAround: heldAsk1 }, trace1, released1, guess1, trace2,
  landed1: { notice: landed1.notice, gaps: landed1.gaps, turns: landed1.turns, top: landed1.top, strip: landed1.strip, regions: regionsLanded }, target1, rows1,
  asked2: { notice: asked2.notice, noticeText: asked2.noticeText, top: asked2.top }, clicked2: { notice: clicked2.notice, top: clicked2.top, gaps: clicked2.gaps }, rows2, released2,
  late2: { notice: late2.notice, top: late2.top, gaps: late2.gaps, turns: late2.turns, regions: regionsLate }, noticeHit, regionsClicked, rowClicked2, rowLate2, target2, deep2Turn: 190, bootTop: boot.top }) + "\n");
await browser.close();
"""


class ServedLandingNotice(WindowLab):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._r = None

    def _result(self):
        if self._r is None:
            type(self)._r = self._drive(DRIVER, "notice")
        # printed on EVERY test's call, not the first alone: pytest shows a test's captured stderr only when THAT test fails, so a
        # payload printed once under the first (passing) road never reached CI's log for a later road's red (main at e7729438, road 14:
        # the log carried the assertion's dict and nothing else). One line per test is the price of an explainable CI-only red.
        print("NOTICE:", json.dumps(self._r), file=sys.stderr)
        return self._r

    def test_a_deep_link_shows_the_one_notice_with_the_targets_time_jumps_into_the_gap_and_lands(self):
        r = self._result()
        a = r["asked1"]
        self.assertGreaterEqual(a["loadAround"], 1, "the deep link into the head gap asked for a window")
        self.assertTrue(a["notice"], "the notice shows while the window is on the wire: %r" % a)
        self.assertTrue(a["noticeText"].startswith("Going to the message from ") and a["noticeText"].endswith(", click to stay here"),
                        "the notice names the target's time and the click to stay: %r" % a["noticeText"])
        self.assertGreaterEqual(len(r["guess1"]), 1, "the view jumped straight into the gap where the target will be (one land-guess write): %r" % r["guess1"])
        self.assertLess(a["top"], r["bootTop"], "…so the view is up in the gap, not at the tail: %r vs boot %r" % (a["top"], r["bootTop"]))
        self.assertTrue(any(g["loading"] for g in a["gaps"]), "the gap wears the loading glyph while its window is on the wire: %r" % a["gaps"])
        l = r["landed1"]
        self.assertIsNotNone(r["boot"]["regions"] if "regions" in r["boot"] else r.get("trace1", {}).get("regions"), "the page holds no regions (the base has none: no runs and gaps, only the old window protocol)")
        self.assertIsNotNone(r["target1"], "the target's turn is resident after the landing")
        self.assertTrue(r["target1"]["visible"], "the target landed on screen: %r" % r["target1"])
        self.assertFalse(l["notice"], "the landing hid the notice: %r" % l)
        self.assertFalse(l["strip"], "nothing pauses live updates")
        kinds = [x["kind"] for x in l["regions"]]
        self.assertIn(kinds, (["run", "gap", "run"], ["gap", "run", "gap", "run"]), "the window is a run among the regions, a gap between it and the tail (a head gap too when it did not reach the head): %r" % l["regions"])
        self.assertTrue(any(row["ok"] for row in r["rows1"]), "the landing filed its row: %r" % r["rows1"])

    def test_a_fill_straddling_a_reader_deep_inside_the_gap_moves_the_point_under_the_viewport_top_by_less_than_a_turn(self):
        # round five, medium B: the window around turn 60 (about turns 0 to 123) fills while the reader stands near turn 117 of the head
        # gap with no row on screen: the fill straddles them
        r = self._result()
        g = r["inGap6"]["gap"]
        self.assertIsNotNone(g, "a head gap stood before the fill: %r" % r["inGap6"])
        self.assertIsNotNone(r["point6Before"], "the point under the viewport top was named as a turn before the fill")
        self.assertTrue(g["lo"] <= r["point6Before"] < g["hi"], "the point under the viewport top lay INSIDE the head gap (rows of runs below may be on screen): %r in %r" % (r["point6Before"], g))
        self.assertGreaterEqual(r["heldAsk6"], 1, "the window ask was on the wire (held) when they scrolled in")
        self.assertIsNotNone(r["point6Before"], "the point under the viewport top was named as a turn before the fill")
        self.assertIsNotNone(r["point6After"], "…and after it")
        self.assertGreaterEqual(len(r["fillWrites6"]), 1, "the released window filled in place (a gap-fill write): %r" % r["fillWrites6"])
        self.assertLess(abs(r["point6After"] - r["point6Before"]), 1.0, "the point under the viewport top moved by less than a turn across the fill: %r -> %r (write %r)" % (r["point6Before"], r["point6After"], r["fillWrites6"]))

    def test_a_fill_at_the_transcript_head_keeps_the_reader_and_lands_the_head_at_the_top(self):
        # MEDIUM 3: a reader inside a gap (scrollTop 0, no row on screen) is not jumped by the fill
        r = self._result()
        self.assertLessEqual(abs(r["head4"]["top"]), 12, "the reader was near the transcript head before the fill: %r" % r["head4"])
        f = r["filled4"]
        self.assertLessEqual(abs(f["top"] - r["head4"]["top"]), 8, "the head fill did not jump the reader (scrollTop held): %r → %r" % (r["head4"], f))
        self.assertTrue(f["firstVisible"], "the first filled turn is on screen: %r" % f)
        self.assertLessEqual(abs(f["firstTop"]), 8, "…at the top: %r" % f)

    def test_a_landing_ask_lost_to_a_socket_death_does_not_wedge_the_gap(self):
        # MEDIUM 1 (round six: the road runs FIRST, on the fresh boot with the whole head gap): the landing's ask is parked at the socket
        # and the socket dies with the landing in flight; the loss, the cleared state, the redial and the re-ask are each asserted
        r = self._result()
        a = r["askBefore5"]
        self.assertGreaterEqual(a["landingGaps"], 1, "the landing was in flight when the socket died (its gap held): %r" % a)
        self.assertGreaterEqual(r["heldRaw5"], 1, "the window ask was parked at the socket, so the death lost it: %r" % r["heldRaw5"])
        self.assertEqual(r["winAtDeath5"], r["winBefore5"], "no window answered the lost ask (the loss is real): %r vs %r" % (r["winAtDeath5"], r["winBefore5"]))
        self.assertFalse(r["afterDrop5"]["notice"], "the socket death brought the notice down (wsdown cleared the landing): %r" % r["afterDrop5"])
        c = r["askState5"]
        self.assertEqual((c["landingGaps"], c["gapLoading"], c["loadingOlder"]), (0, 0, False),
                         "the wedge is gone: the landing's held gap, the page asks and the older-ask set all cleared by wsdown (medium 1): %r" % c)
        self.assertGreaterEqual(r["redialed5"], 1, "the shim redialed and the kernel re-sent the session after the close: %r" % r["redialed5"])
        self.assertGreaterEqual(r["reask5"], 1, "the landing was asked again on the healed socket (the redial's flush re-sent the lost ask: %r; else a fresh deep link asked): %r" % (r["flushAsk5"], r["reask5"]))
        self.assertTrue(r["landed5"], "…and the lost target landed: %r" % r["landed5"])

    def test_a_readers_scroll_puts_the_answered_question_under_the_viewport_top_and_the_settle_does_not_snap_it_back(self):
        # T386, road 7a: the answered AskUserQuestion is anchored on its ANSWER's uuid, a tool_result line no event carries as its own. A
        # reader's own scroll (a wheel: input evidence) brings that row under the viewport top, and the settling landing YIELDS to the gesture
        # (settleGesture) rather than re-landing ("land-realign") the row off the top. This is the path a real scroll takes, so it holds whatever
        # the message line-height (whole device px since the raster fix): the point names the turn by position, never a uuid lookup.
        r = self._result()
        answer = "66666666-7777-8888-9999-%012d" % 200
        self.assertIsNotNone(r["top7a"], "a row sat under the viewport top after the reader's scroll")
        self.assertEqual(r["top7a"]["uuid"], answer, "the reader's scroll put the answered question (its answer's tool_result uuid) under the viewport top: %r" % r["top7a"])
        self.assertTrue(isinstance(r["turnAttr7a"], str) and r["turnAttr7a"].isdigit(), "the row names its own turn (data-turn), read by position, never a uuid lookup: %r" % r["turnAttr7a"])
        self.assertEqual(int(r["turnAttr7a"]), 100, "…the answered question's turn: %r" % r["turnAttr7a"])
        self.assertEqual(int(r["point7a"]), 100, "the point under the viewport top names turn 100 (its integer part) with the answer (a tool_result row, no event's own uuid) at the top, by position not a uuid lookup: %r" % r["point7a"])
        self.assertEqual(r["realign7a"], 0, "the settle YIELDED to the reader's gesture: no land-realign snapped the row back off the top: %r" % r["realign7a"])

    def test_an_answered_questions_turn_holds_under_the_viewport_top_through_a_fill_above_it(self):
        # T386, road 7b: at the viewport the landing LEAVES (the answered question's turn at the top, no scroll), a fill ABOVE it (a held deep
        # link into the head gap, its notice clicked to stay, then released) inserts its run above the reader WITHOUT moving the point under the
        # top: it holds at turn 100, named by position through the insertion. No scroll here, so no settle to fight: the reader who lands and
        # stays keeps their place while history fills in above them.
        r = self._result()
        self.assertEqual(int(r["pointB7Before"]), 100, "the landing left turn 100 under the viewport top (the point's integer part): %r" % r["pointB7Before"])
        self.assertEqual(r["held7b"], 1, "the fill's window ask was held at the socket: %r" % r["askState7b"])
        self.assertGreater(r["runNAfter7b"], r["runNBefore7b"], "the released window inserted its run above the reader: %r -> %r" % (r["runNBefore7b"], r["runNAfter7b"]))
        self.assertGreaterEqual(len(r["fillWrites7b"]), 1, "the fill wrote the scroll once in place (gap-fill): %r" % r["fillWrites7b"])
        self.assertIsNotNone(r["rowB7Held"], "a row sat under the viewport top when the fill came")
        self.assertEqual(r["rowB7Held"]["turn"], "100", "the row under the top when the fill came names turn 100: %r" % r["rowB7Held"])
        self.assertIsNotNone(r["rowB7After"], "a row is on screen after the fill (no zero-row view)")
        self.assertEqual(r["rowB7After"]["uuid"], r["rowB7Held"]["uuid"], "the same row sits under the viewport top after the fill above it: %r -> %r" % (r["rowB7Held"], r["rowB7After"]))
        self.assertLessEqual(abs(r["rowB7After"]["y"] - r["rowB7Held"]["y"]), 2, "…at its offset: %r -> %r" % (r["rowB7Held"], r["rowB7After"]))
        self.assertEqual(int(r["pointB7After"]), 100, "the point under the top holds at turn 100 after the fill above it: %r" % r["pointB7After"])
        self.assertLess(abs(r["pointB7After"] - r["pointB7Before"]), 1.0, "the point moved by less than a turn through the fill above: %r -> %r" % (r["pointB7Before"], r["pointB7After"]))
    def test_a_cancelled_landing_is_not_busy_the_next_card_click_asks_and_both_replies_land_in_place(self):
        # round seven, medium 3: click, cancel, click
        r = self._result()
        self.assertEqual(r["askedA8"], 1, "the first deep link asked its window (held)")
        a = r["afterCancel8"]
        self.assertFalse(a["notice"], "the notice's click hid the notice: %r" % a)
        self.assertEqual((a["ask"]["loadingOlder"], a["ask"]["landingGaps"]), (False, 0), "a cancelled landing is not busy: the older-ask mark and the held gap are cleared at the cancel, not at the reply: %r" % a["ask"])
        at = a["atomic"]
        self.assertEqual(at["ask"]["landingGaps"], 0, "no landing holds a gap at the same instant the glyphs were read: %r" % at)
        for lo, hi in at["glyphGaps"]:
            self.assertTrue(any(k.split(":")[0] == SID and lo <= int(k.split(":")[1]) and int(k.split(":")[2]) <= hi for k in at["ask"]["gapKeys"]),
                            "a glyph after the cancel belongs to a page ask the gap made for itself (the reader stands in it), never to the cancelled landing: gap %r, live asks %r" % ((lo, hi), at["ask"]["gapKeys"]))
        self.assertEqual(r["askedB8"], 1, "the reader's NEXT card click asked its own window while the cancelled reply was still on the wire: %r" % r["askedB8"])
        self.assertEqual(r["busy8"], 0, "…and was not refused as busy: %r" % r["busy8"])
        self.assertNotEqual(r["toast8"], "still going to the earlier message", "no untrue 'still going' toast: %r" % r["toast8"])
        self.assertTrue(r["noticeB8"], "the second landing shows its notice while its ask is on the wire")
        self.assertEqual(r["released8"], 2, "both asks were parked at the socket and released together: %r" % r["released8"])
        self.assertIsNotNone(r["targetB8"]); self.assertTrue(r["targetB8"]["visible"], "the second deep link landed on screen: %r" % r["targetB8"])
        self.assertTrue(r["residentA8"], "the cancelled reply's run still inserted in place (nothing is thrown away)")
        self.assertGreater(r["runN8After"], r["runN8Before"], "the runs grew by both windows: %r -> %r" % (r["runN8Before"], r["runN8After"]))

    def test_a_kernel_fault_on_a_landing_has_its_own_word_files_as_a_fault_and_never_says_the_message_is_gone(self):
        # round seven, medium 1: the wrapper's exact fault shape (missing true, fault true, the anchor, an error) injected to a held landing
        r = self._result()
        self.assertTrue(r["asked9"]["notice"], "the deep link showed its notice while the ask was held: %r" % r["asked9"])
        self.assertNotEqual(r["asked9"]["top"], r["top9Before"], "the pre-jump moved the reader into the gap")
        f = r["fault9"]
        self.assertFalse(f["notice"], "the fault brought the notice down: %r" % f)
        self.assertIsNotNone(f["toast"], "the reader was told: %r" % f)
        self.assertIn("could not be loaded just now", f["toast"], "…with the fault's own word, not a verdict on the anchor: %r" % f["toast"])
        self.assertNotIn("couldn't locate", f["toast"], "a fault never says the message is not in the transcript (it is): %r" % f["toast"])
        self.assertEqual(len(r["rows9"]), 1, "the landing filed one row: %r" % r["rows9"])
        self.assertEqual(r["rows9"][0]["kind"], "fault", "…as a fault, not missing: %r" % r["rows9"])
        self.assertIn("window-fault", r["rows9"][0]["trail"], "…with the fault's trail word: %r" % r["rows9"][0]["trail"])
        # the restore is exact here; CI's page lands about 87 px short twice over (its writes are in the payload for the read): the bound is a
        # turn's height, so a restore that missed by a row would still pass here and the payload says by how much
        turn_px = r["pxPerTurn9"] or 120
        self.assertLessEqual(abs(f["top"] - r["top9Before"]), turn_px, "the pre-jump was undone: the reader is back at the origin within a turn (CI's page lands tens of pixels short of it after the pre-jump's re-window; round eight, low 4: the delta against the origin alone): %r -> %r (before %r, a turn %r px; the writes %r)" % (r["asked9"]["top"], f["top"], r["top9Before"], turn_px, r["writes9"]))
        self.assertEqual((f["ask"]["landingGaps"], f["ask"]["gapLoading"], f["ask"]["loadingOlder"]), (0, 0, False), "the landing's state cleared: %r" % f["ask"])
        self.assertFalse(f["seekNote"], "the seek ended (no seek note stands)")

    def test_two_cancelled_landings_on_one_session_each_fill_in_place_and_neither_moves_the_reader(self):
        # round eight, medium 1: click A, cancel, click B, cancel; release A alone, then B alone. The behaviour first (the pre-fix red is the
        # landing write), the records after; the reader stands inside the head gap with no row on screen, so "nothing moved" is the point
        # under the viewport top as a turn, as roads six and seven judge a fill
        r = self._result()
        self.assertEqual((r["askedA10"], r["askedB10"]), (1, 1), "both deep links asked (held): %r" % ((r["askedA10"], r["askedB10"]),))
        self.assertEqual((r["relA10"], r["relB10"]), (1, 1), "the two parked asks were released one at a time")
        self.assertEqual([w for w in r["writes10"] if w[0] == "land-on"], [], "no landing write dragged the reader to a target they cancelled: %r" % r["writes10"])
        self.assertIsNotNone(r["before10"]["point"], "the point under the viewport top was named before the releases")
        self.assertIsNotNone(r["afterA10"]["point"]); self.assertIsNotNone(r["afterB10"]["point"])
        self.assertLess(abs(r["afterA10"]["point"] - r["before10"]["point"]), 1.0, "A's reply moved the reader by less than a turn: %r -> %r (scrollTop %r -> %r)" % (r["before10"]["point"], r["afterA10"]["point"], r["before10"]["top"], r["afterA10"]["top"]))
        self.assertLess(abs(r["afterB10"]["point"] - r["before10"]["point"]), 1.0, "B's reply too: %r -> %r (scrollTop %r -> %r)" % (r["before10"]["point"], r["afterB10"]["point"], r["before10"]["top"], r["afterB10"]["top"]))
        # (a target MAY be on screen after its reply: the cancelled reader stays where the pre-jump left them, and the words fill in around them; the point and the writes are the measure)
        self.assertGreater(r["runN10b"], r["runN10a"], "A's reply inserted its run: %r -> %r" % (r["runN10a"], r["runN10b"]))
        self.assertGreater(r["runN10c"], r["runN10b"], "B's reply inserted its run: %r -> %r" % (r["runN10b"], r["runN10c"]))
        self.assertFalse(r["afterA10"]["notice"] or r["afterB10"]["notice"], "no notice returns with either reply")
        asks = r["asks10"].get("asks")
        self.assertIsNotNone(asks, "the ask-state hook lists the per-ask records: %r" % r["asks10"])
        self.assertEqual([a["cancelled"] for a in asks], [True, True], "two records, both cancelled, neither overwritten: %r" % asks)

    def test_a_cancelled_landings_origin_dies_with_the_cancel_so_a_later_dead_end_leaves_the_reader_where_it_found_them(self):
        # round eight, medium 2: click A (pre-jump into the gap), cancel; click B with no time (no pre-jump); B missing
        r = self._result()
        self.assertEqual(r["askedA11"], 1, "A asked (held)")
        self.assertNotEqual(r["foundB11"], r["originA11"], "A's pre-jump moved the reader off A's origin before the cancel: %r vs origin %r" % (r["foundB11"], r["originA11"]))
        self.assertEqual(r["askedB11"], 1, "B asked (held): the cancelled A is not busy")
        self.assertTrue(r["noticeB11"], "B's notice showed")
        self.assertLessEqual(abs(r["atAsk11"] - r["foundB11"]), 2, "B had no time, so no pre-jump moved the reader: %r -> %r" % (r["foundB11"], r["atAsk11"]))
        a = r["afterMissing11"]
        self.assertFalse(a["notice"], "B's missing reply brought its notice down")
        self.assertIsNotNone(a["toast"]); self.assertIn("couldn't locate", a["toast"], "…with the honest word: %r" % a["toast"])
        self.assertLessEqual(abs(a["top"] - r["foundB11"]), 2, "the reader stays where B found them, never restored to A's cancelled origin: %r (B found them at %r; A's origin %r; land-cancel writes %r)" % (a["top"], r["foundB11"], r["originA11"], r["writes11"]))
        self.assertEqual(r["writes11"], [], "no restore write ran for a dead end with no pre-jump of its own: %r" % r["writes11"])

    def test_a_cancelled_ask_whose_frame_is_lost_does_not_eat_the_next_landing_on_its_anchor(self):
        # round eight, medium 3: click A (held), cancel, drop the frame (the socket alive), click A again: it asks and lands
        r = self._result()
        self.assertEqual(r["askedA12"], 1, "A asked (held), then its frame was dropped")
        self.assertGreaterEqual(r["reask12"], 1, "the second click on the same card asked again (a fresh ask supersedes the cancelled twin): %r" % r["reask12"])
        self.assertIsNotNone(r["target12"]); self.assertTrue(r["target12"]["visible"], "…and landed on screen: %r (rows %r)" % (r["target12"], r["trail12"]))

    def test_an_older_fetch_in_flight_does_not_refuse_a_landing_the_anchor_lands_when_the_older_page_arrives(self):
        # round nine, medium 1: the boot frame re-posted with tailLo null (no regions; the head asked by loadOlder), that fetch held, a card click
        r = self._result()
        self.assertTrue(r["hadFrame13"], "the boot frame was captured for the re-post (an init script, before the page's scripts)")
        self.assertIn(r["regions13"], (None, []), "the tailLo-null frame left the page with no regions: %r" % r["regions13"])
        self.assertGreaterEqual(r["heldOlder13"], 1, "the head was asked by loadOlder (the fallback) and the ask is parked: %r" % r["heldOlder13"])
        self.assertTrue(r["askState13"]["loadingOlder"], "…so an older fetch is in flight when the card is clicked: %r" % r["askState13"])
        self.assertNotIn("pointer-fetch-busy", r["trail13"] or [], "the click was not refused as busy: %r" % r["trail13"])
        self.assertIn("pointer-fetch-older", r["trail13"] or [], "the in-flight fetch was re-pointed onto the anchor: %r" % r["trail13"])
        self.assertNotEqual(r["toast13"], "still going to the earlier message", "no untrue busy toast: %r" % r["toast13"])
        self.assertEqual(r["asks13"]["busy"], 0, "no busy row filed: %r" % r["asks13"])
        self.assertIsNotNone(r["target13"]); self.assertTrue(r["target13"]["visible"], "the target landed on screen once the older page arrived (asks after the click %r): %r" % (r["asks13"], r["target13"]))

    def test_the_notices_pulse_is_one_shot_and_a_later_landing_does_not_replay_it(self):
        # the follow-up after PR 1584, low 1: a real second click pulses once; the class leaves on the animation's end; the notice re-shown
        # for a later landing runs no animation and carries no pulse class
        r = self._result()
        f = r["first15"]
        self.assertTrue(f["notice"], "the first click brought the notice up: %r" % f)
        self.assertEqual(f["pulses"], 0, "one click, no pulse: %r" % f)
        p = r["pulsed15"]
        self.assertEqual(p["pulses"], 1, "a real second click on the anchor its landing is on the wire for pulses the notice once: %r" % p)
        e = r["afterEnd15"]
        self.assertFalse(e["cls"], "the pulse class leaves on the animation's end: %r" % e)
        self.assertEqual(e["running"], 0, "…and nothing is animating: %r" % e)
        self.assertIsNotNone(r["targetA15"]); self.assertTrue(r["targetA15"]["visible"], "the first landing landed: %r" % r["targetA15"])
        s = r["reshow15"]
        self.assertTrue(s["notice"], "the later landing re-showed the notice: %r" % s)
        self.assertEqual(s["pulses"], 1, "the re-shown notice replays no pulse: %r" % s)
        self.assertEqual((s["cls"], s["running"]), (False, 0), "…no stale class, nothing animating: %r" % s)
        self.assertIsNotNone(r["targetB15"]); self.assertTrue(r["targetB15"]["visible"], "the later landing landed: %r" % r["targetB15"])
        # the tidy after PR 1642, low 2: every animationend listener the pulse adds leaves the element, the cut pulse's by the hide
        # a once listener that FIRES is consumed by the browser with no removeEventListener call, so a completed pulse reads adds 1, removes 0;
        # a pulse the hide cuts short never fires, and only the hide's own remove takes its handler off: adds minus removes is the count of
        # pulses that completed, and removes counts the cut ones the hide took away
        l = r["listeners15"]
        self.assertEqual((l["add"], l["remove"]), (1, 0), "a completed pulse: one listener added, consumed by its own once: %r" % l)
        c = r["cut15"]
        self.assertGreater(c["pulses"], r["reshow15"]["pulses"], "the second click on B pulsed while its landing was on the wire: %r" % c)
        self.assertEqual(c["add"], 2, "…a second listener added for it: %r" % c)
        a = r["afterCut15"]
        self.assertFalse(a["shown"], "the landing hid the notice: %r" % a)
        self.assertEqual(a["remove"], 1, "the hide removed the cut pulse's handler (before the fix nothing did, and it stayed on the reused element): %r" % a)
        self.assertEqual(a["add"] - a["remove"], 1, "adds minus removes is the one completed pulse: no dead closure left (adds %d, removes %d): %r" % (a["add"], a["remove"], a))
        self.assertFalse(a["cls"], "…and no pulse class: %r" % a)

    def test_the_panes_pipe_down_edge_clears_the_landing_like_the_sockets_death(self):
        # round nine, medium 2: pipeState down with a landing in flight, then up; the next click asks
        r = self._result()
        b = r["before14"]
        self.assertTrue(b["notice"], "a landing was in flight (its notice up): %r" % b)
        self.assertGreaterEqual(len(b["ask"]["asks"]), 1, "…with a live record: %r" % b["ask"])
        d = r["down14"]
        self.assertFalse(d["notice"], "pipeState down brought the notice down: %r" % d)
        self.assertEqual(d["ask"]["asks"], [], "…and cleared the ask's record: %r" % d["ask"])
        self.assertEqual((d["ask"]["landingGaps"], d["ask"]["loadingOlder"]), (0, False), "the landing's gap and the older ask cleared: %r" % d["ask"])
        # main red at e7729438 (CI, this road): the three-set read gapLoading 1 with the key of the head gap's FIRST page after the down edge.
        # The clear owes the asks that were in flight, and every one of those is gone (none of the keys from before the down edge stands);
        # a key standing after it is the gap under the reader asking anew once a rebuild re-observed it with the landing's record gone,
        # which the road now forces (the boot frame re-posted) and reads at the socket: one fresh page ask, the gap's first page, parked.
        self.assertTrue(set(d["ask"]["gapKeys"]).isdisjoint(b["ask"]["gapKeys"]), "no page ask from before the down edge stands: %r vs %r" % (d["ask"]["gapKeys"], b["ask"]["gapKeys"]))
        self.assertEqual([k.split(":", 1)[1] for k in d["ask"]["gapKeys"]], ["0:16"], "the gap under the reader (at the head gap's top after the pre-jump) asked anew for its first page: %r" % d["ask"])
        self.assertEqual([h for h in d["held"] if h.startswith("loadTurns")], ["loadTurns:0-16"], "…parked at the socket, one ask: %r" % d["held"])
        self.assertIsNotNone(d["toast"]); self.assertIn("connection dropped", d["toast"], "the reader was told the jump was lost: %r" % d["toast"])
        a = r["after14"]
        self.assertEqual(a["asked"], 1, "after pipeState up the next card click asked: %r" % a)
        self.assertEqual(a["busy"], 0, "…and was not refused as busy: %r" % a)
        self.assertIsNotNone(a["target"]); self.assertTrue(a["target"]["visible"], "…and landed: %r" % a["target"])

    def test_a_span_less_window_from_an_older_host_tells_the_reader_and_is_not_dropped_silently(self):
        # T386 stage 2, medium 2: a chatWindow with events but no span is an older host's pre-regions reply
        r = self._result()
        self.assertTrue(r["asked3"]["notice"], "the deep link into the gap showed the notice: %r" % r["asked3"])
        n = r["nospan3"]
        self.assertFalse(n["notice"], "the span-less reply brought the notice down: %r" % n)
        self.assertIsNotNone(n["toast"], "…and told the reader, never dropped them silently: %r" % n)
        self.assertIn("older version", n["toast"], "the toast says the host is older: %r" % n["toast"])

    def test_clicking_the_notice_is_the_only_cancel_the_late_reply_fills_in_place_and_the_view_stays(self):
        r = self._result()
        self.assertTrue(r["asked2"]["notice"], "the second deep link's notice shows while its ask is held: %r" % r["asked2"])
        self.assertIsNotNone(r["noticeHit"], "the notice was present to click")
        self.assertTrue(r["noticeHit"]["isNotice"], "elementFromPoint at the notice's centre is the notice, so a real click reaches it (T386 stage 2, HIGH): %r" % r["noticeHit"])
        c = r["clicked2"]
        self.assertFalse(c["notice"], "the click hid the notice: %r" % c)
        self.assertTrue(any(row["cancelled"] and row["ok"] is False for row in r["rows2"]), "the landing filed its row as cancelled at the click: %r" % r["rows2"])
        self.assertEqual(r["released2"], 1, "the one held ask was released (the target was not resident, so the deep link asked): %r" % r["trace2"])
        late = r["late2"]
        self.assertIsNotNone(r["boot"]["regions"] if "regions" in r["boot"] else r.get("trace1", {}).get("regions"), "the page holds no regions (the base has none: no runs and gaps, only the old window protocol)")
        self.assertIsNotNone(r["rowClicked2"], "a row sat under the viewport top when the notice was clicked")
        self.assertEqual(r["rowLate2"]["uuid"], r["rowClicked2"]["uuid"], "the late reply moved nothing: the row under the viewport top is the same row (the run inserted above it, so scrollTop grew by its height): %r → %r" % (r["rowClicked2"], r["rowLate2"]))
        self.assertLessEqual(abs(r["rowLate2"]["y"] - r["rowClicked2"]["y"]), 2, "…at its offset: %r → %r" % (r["rowClicked2"], r["rowLate2"]))
        held = lambda rs: sum(x["n"] for x in rs if x["kind"] == "run")
        self.assertGreater(held(late["regions"]), held(r["regionsClicked"]), "the reply's run still inserted (nothing is thrown away): %r → %r" % (r["regionsClicked"], late["regions"]))
        self.assertTrue(any(x["kind"] == "run" and x["lo"] <= r["deep2Turn"] < (x["hi"] if x["hi"] is not None else 10**9) for x in late["regions"]), "the cancelled target's turn is resident, in place, for the reader to reach by scrolling: %r" % late["regions"])
        self.assertFalse(late["notice"], "no notice returns with the reply")


if __name__ == "__main__":
    unittest.main()
