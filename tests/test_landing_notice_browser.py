"""T386 stage 2 (the user 2026-09-12, plans/chat-history-regions.md Part B): the ONE landing notice. A navigation into history the
page does not hold (a card, a deep link) asks for a window; while it is on the wire the notice sits at the loading anchor before
#content and says where the landing goes ("Going to the message from 7:41 AM, click to stay here"); the view jumps straight into
the gap where the target will be, the loading glyph in the empty space; the landing hides the notice. Clicking the notice is the
ONLY cancel: the target and the notice go, the reply still inserts its run in place, and the view does not move. Served, on the
window lab's hermetic kernel (a synthetic transcript longer than the wire tail: the deep target is in the head gap at boot).

Roads, one page: the deep link landing with the notice (the words, the pre-jump write, the window ask, the landing, the notice
gone); then a second deep link with its ask HELD at the socket, the notice clicked (a locateDiag row filed as cancelled, the notice
gone, the view still), the ask released (the run inserts, the view still where the reader was).

Synthetic fixtures only (placeholder uuids, invented prose); hostname TESTHOST.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from tests.test_live_paused_window_browser import DRIVER_HEAD, WindowLab  # noqa: E402

DRIVER = DRIVER_HEAD + r"""
// the socket hold: a frame whose type is in __hold is parked, not sent (the ask stays on the page's books); __release sends the parked frames
await page.evaluate(() => { const orig = WebSocket.prototype.send; window.__hold = new Set(); window.__heldRaw = [];
  WebSocket.prototype.send = function (d) { window.__ws = this; try { const m = JSON.parse(d); if (m && m.type && window.__hold.has(m.type)) { window.__heldRaw.push(d); return; } } catch (e) {} return orig.call(this, d); };
  window.__release = () => { const ws = window.__ws; const held = window.__heldRaw; window.__heldRaw = []; for (const d of held) orig.call(ws, d); return held.length; };
  window.__recv = []; window.__bootSession = null; window.addEventListener("message", (e) => { const m = e.data; if (m && m.type) { window.__recv.push(m.type + (m.span ? ":" + m.span.join("-") : "") + (m.anchor ? ":anchor" : "")); if (m.type === "session" && Array.isArray(m.events) && !window.__bootSession) window.__bootSession = m; } }); });
const trace = () => page.evaluate(() => ({ sent: window.__sent.slice(-14).map((m) => m.type + (m.what ? ":" + m.what + (m.data && m.data.writer ? ":" + m.data.writer : "") + (m.data && m.data.why ? ":" + m.data.why : "") : "") + (m.cancelled ? ":cancelled" : "")), recv: window.__recv.slice(-10), regions: (typeof window.__rompRegions === "function" ? window.__rompRegions() : null) }));
const writes = (writer) => page.evaluate((w) => window.__sent.filter((m) => m.what === "scrollwrite" && m.data && m.data.writer === w).map((m) => [m.data.before, m.data.after]), writer);
const locateRows = () => page.evaluate(() => window.__sent.filter((m) => m.type === "locateDiag").map((m) => ({ ok: m.ok, cancelled: m.cancelled === true, anchor: m.anchor, trail: m.trail })));
const painted = () => page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 0)))));
const rowAtTop = () => page.evaluate(() => {
  const c = document.getElementById("content"); const cTop = c.getBoundingClientRect().top;
  for (const t of Array.from(document.querySelectorAll("#content .turn[data-uuid]"))) { const r = t.getBoundingClientRect(); if (r.bottom > cTop + 1) return { uuid: t.dataset.uuid, y: Math.round(r.top - cTop) }; }
  return null;
});
const onScreen = (uuid) => page.evaluate((u) => { const t = document.querySelector(`#content .turn[data-uuid="${u}"]`); if (!t) return null; const c = document.getElementById("content").getBoundingClientRect(); const r = t.getBoundingClientRect(); return { top: Math.round(r.top - c.top), visible: r.bottom > c.top && r.top < c.bottom }; }, uuid);
// ROAD 3 (T386 stage 2, medium 2): an OLDER host speaks the pre-regions window protocol — its chatWindow carries events but NO span.
// A deep link into a gap, the ask held, then a span-less reply injected: the pre-jump moved the reader, so the notice comes down and
// the reader is told the host is older, never dropped silently where the pre-jump left them.
const deep3 = "11111111-2222-3333-4444-" + pad(2 * 40);
await page.evaluate(() => { window.__hold.add("loadAround"); });
const aroundBefore3 = await sentOf("loadAround"); const toastBefore3 = await page.evaluate(() => !!document.querySelector(".locate-toast"));
await page.evaluate((frame) => window.postMessage(frame, "*"), { type: "focus", id: cfg.sid, anchor: deep3, anchorT: cfg.base + 2 * 40 });
await page.waitForFunction((n) => window.__sent.filter((m) => m.type === "loadAround").length > n, aroundBefore3, { timeout: 10000 }).catch(() => {});
const asked3 = await state();
await page.evaluate(([sid, anchor]) => window.postMessage({ type: "chatWindow", id: sid, anchor, events: [{ uuid: anchor, kind: "user", md: "an older host's window, no span" }], moreBefore: false, moreAfter: false }, "*"), [cfg.sid, deep3]);
await page.waitForFunction(() => { const tt = document.querySelector(".locate-toast"); return !!tt && /older version/.test(tt.textContent || ""); }, null, { timeout: 5000 }).catch(() => {});
const nospan3 = { notice: (await state()).notice, toast: await page.evaluate(() => { const tt = document.querySelector(".locate-toast"); return tt ? tt.textContent : null; }) };
await page.evaluate(() => { window.__hold.delete("loadAround"); window.__heldRaw = []; });
// ROAD 5 (T386 stage 2, medium 1; runs right after the span-less road, while the head gap is whole, so its probe has a gap to ask into): a landing's window ask lost to a socket death must not wedge the gap. A deep link into a gap (ask on
// the wire), the socket killed, restored; the gap met again asks a fresh loadTurns and a later deep link lands.
const deep5 = "11111111-2222-3333-4444-" + pad(2 * 25);
await page.evaluate(() => { if (window.__bootSession) window.postMessage(window.__bootSession, "*"); });   // reset SID to the pristine boot tail: the head gap whole again, so the probe turn is genuinely in a gap (prior roads filled parts of it)
await painted();
await page.evaluate(() => { const c = document.getElementById("content"); c.scrollTop = c.scrollHeight; });   // back to the tail, an attached start
await page.evaluate((frame) => window.postMessage(frame, "*"), { type: "focus", id: cfg.sid, anchor: deep5, anchorT: cfg.base + 2 * 25 });
await page.waitForFunction(() => !!document.querySelector(".tx-landing-notice") && getComputedStyle(document.querySelector(".tx-landing-notice")).display !== "none", null, { timeout: 8000 }).catch(() => {});
await page.evaluate(() => { window.__ws && window.__ws.close(); });   // the socket dies with the ask in flight; the shim redials
await page.waitForTimeout(400);
const afterDrop5 = await state();
const askState5 = await page.evaluate((sid) => (typeof window.__rompAskState === "function" ? window.__rompAskState(sid) : null), cfg.sid);   // the wedge is gone: landingGaps, gapLoading and loadingOlder all cleared by wsdown (medium 1)
// the REDIAL: the shim reopens the socket and the kernel re-sends the session (a fresh boot frame), so the head gap is whole again; then
// meet it by stepping up from the top spacer's end until the gap element renders and asks (round four, low 6: a real close and redial,
// a fresh loadTurns asserted)
const recvBefore5 = await page.evaluate(() => window.__recv.filter((x) => x.startsWith("session")).length);
await page.waitForFunction((n) => window.__recv.filter((x) => x.startsWith("session")).length > n, recvBefore5, { timeout: 15000 }).catch(() => {});
await painted();
// after the redial the head may be largely resident (earlier roads' fills merge into the fresh frame), so the re-ask targets whatever
// gap the regions still hold, of ANY size: a deep link into its first turn asks (loadAround) or pages (loadTurns) — never a scroll hunt
const asksAll5 = () => page.evaluate(() => window.__sent.filter((m) => m.type === "loadAround" || m.type === "loadTurns").length);
const asksBefore5b = await asksAll5();
const gapLo5 = await page.evaluate((sid) => { const rs = typeof window.__rompRegions === "function" ? window.__rompRegions(sid) : null; const g = rs && rs.find((r) => r.kind === "gap" && r.hi != null && r.hi > r.lo); return g ? g.lo : null; }, cfg.sid);
if (gapLo5 != null) {
  await page.evaluate(([sid, u, tt]) => window.postMessage({ type: "focus", id: sid, anchor: u, anchorT: tt }, "*"), [cfg.sid, "11111111-2222-3333-4444-" + pad(2 * gapLo5), cfg.base + 2 * gapLo5]);
  await page.waitForFunction((n) => window.__sent.filter((m) => m.type === "loadAround" || m.type === "loadTurns").length > n, asksBefore5b, { timeout: 8000 }).catch(() => {});
}
const redialAsk5 = (await asksAll5()) - asksBefore5b;
const gapLo5Out = gapLo5;
const redialed5 = (await page.evaluate(() => window.__recv.filter((x) => x.startsWith("session")).length)) - recvBefore5;
// the gap is not wedged: a deep link into a turn STILL in a gap (read from the regions, so no prior road made it resident) asks again
const asks5 = () => page.evaluate(() => window.__sent.filter((m) => m.type === "loadAround" || m.type === "loadTurns").length);
const asksBefore5 = await asks5();
const gapTurn5 = await page.evaluate(() => { const rs = typeof window.__rompRegions === "function" ? window.__rompRegions() : null; if (!rs) return null; const g = rs.find((r) => r.kind === "gap" && r.hi - r.lo >= 4); return g ? Math.floor((g.lo + g.hi) / 2) : null; });
const deep5b = gapTurn5 != null ? "11111111-2222-3333-4444-" + pad(2 * gapTurn5) : deep5;
const resBefore5 = await page.evaluate((u) => !!document.querySelector('#content .turn[data-uuid="' + u + '"]'), deep5b);
await page.evaluate(([sid, u, tt]) => window.postMessage({ type: "focus", id: sid, anchor: u, anchorT: tt }, "*"), [cfg.sid, deep5b, cfg.base + 2 * (gapTurn5 != null ? gapTurn5 : 25)]);
await page.waitForFunction((n) => (window.__sent.filter((m) => m.type === "loadAround" || m.type === "loadTurns").length) > n, asksBefore5, { timeout: 8000 }).catch(() => {});
const reask5 = (await asks5()) - asksBefore5;
const reNotice5 = (await state()).notice;
const resident5 = resBefore5;
// ROAD 6 (round five, medium B; runs right after the span-less road, while the head gap is whole, and returns the reader to the tail after):
// the point under the viewport top holds through a fill that lands ABOVE a reader standing INSIDE the head gap. The fill is the cancel road's
// (deterministic, the same fillInPlace a page fill takes): a deep link into turn 60 asks its window (HELD), the notice is clicked away so
// nobody is going to that window, the reader scrolls deep into the gap (no row on screen), the window is released and fills in place above
// them; the point under the viewport top, named as a turn, must move by less than a turn (the old view-coordinate compensation carried it
// about 2.6 turns; 81c0dca5 about 2.8).
const sentAt6 = await page.evaluate(() => window.__sent.length);
await page.evaluate(() => { window.__hold.add("loadAround"); });
const around6 = await sentOf("loadAround");
await page.evaluate((frame) => window.postMessage(frame, "*"), { type: "focus", id: cfg.sid, anchor: "11111111-2222-3333-4444-" + pad(2 * 60), anchorT: cfg.base + 2 * 60 });   // turn 60: its window (about turns 25 to 95) lands ABOVE a reader standing near turn 120, and clear of the other roads' targets
await page.waitForFunction((n) => window.__sent.filter((m) => m.type === "loadAround").length > n, around6, { timeout: 8000 }).catch(() => {});
await page.waitForFunction(() => { const n = document.querySelector(".tx-landing-notice"); return !!n && getComputedStyle(n).display !== "none"; }, null, { timeout: 5000 }).catch(() => {});
const heldAsk6 = await page.evaluate(() => (window.__heldRaw || []).length);
await page.evaluate(() => { const n = document.querySelector(".tx-landing-notice"); if (n) { const r = n.getBoundingClientRect(); n.dispatchEvent(new MouseEvent("click", { bubbles: true, clientX: r.left + r.width / 2, clientY: r.top + r.height / 2 })); } });   // the notice clicked away: the reply will fill in place
await page.waitForFunction(() => { const n = document.querySelector(".tx-landing-notice"); return !n || getComputedStyle(n).display === "none"; }, null, { timeout: 5000 }).catch(() => {});
await page.evaluate(() => { const c = document.getElementById("content"); const g = document.querySelector("#content .tx-gap"); const gTop = g ? g.getBoundingClientRect().top - c.getBoundingClientRect().top + c.scrollTop : 0; c.scrollTop = Math.round(gTop + (g ? g.offsetHeight : 9000) * 0.6); });   // about turn 117 of 195, deep into the head gap, no row on screen
await painted();
const inGap6 = await page.evaluate(() => { const c = document.getElementById("content"); const cr = c.getBoundingClientRect(); const rows = Array.from(c.querySelectorAll(".turn[data-uuid]")).filter((t) => { const r = t.getBoundingClientRect(); return r.bottom > cr.top && r.top < cr.bottom; }).length; const rs = typeof window.__rompRegions === "function" ? window.__rompRegions() : null; const g = rs && rs.find((r) => r.kind === "gap"); return { top: c.scrollTop, rowsOnScreen: rows, gap: g ? { lo: g.lo, hi: g.hi } : null }; });
const point6Before = await page.evaluate(() => (typeof window.__rompTurnUnderTop === "function" ? window.__rompTurnUnderTop() : null));
const regionsBefore6 = await page.evaluate(() => (typeof window.__rompRegions === "function" ? window.__rompRegions() : null));
await page.evaluate(() => { window.__hold.delete("loadAround"); window.__release(); });
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
await page.waitForFunction((n) => window.__sent.filter((m) => m.type === "loadAround").length > n, aroundBefore1, { timeout: 10000 }).catch(() => {});
const asked1 = await state();   // sampled while the ask is on the wire: the notice up, the view inside the gap
const trace1 = await trace();
const guess1 = await writes("land-guess");
await page.evaluate(() => { window.__hold.delete("loadAround"); });
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
await page.waitForFunction((n) => window.__sent.filter((m) => m.type === "loadAround").length > n, aroundBefore2, { timeout: 10000 }).catch(() => {});
const asked2 = await state();
const trace2 = await trace();
// the ONLY cancel, clicked as a real user does: hit-tested at the notice's centre (a synthetic n.click() would pass even if the notice
// took no pointer, the round-one lesson), so record whether elementFromPoint IS the notice, then page.mouse.click its box
const noticeHit = await page.evaluate(() => { const n = document.querySelector(".tx-landing-notice"); if (!n) return null; const r = n.getBoundingClientRect(); const cx = r.left + r.width / 2, cy = r.top + r.height / 2; const el = document.elementFromPoint(cx, cy); return { x: cx, y: cy, isNotice: el === n || (!!el && n.contains(el)) }; });
if (noticeHit) await page.mouse.click(noticeHit.x, noticeHit.y);
await page.waitForFunction(() => { const n = document.querySelector(".tx-landing-notice"); return !n || getComputedStyle(n).display === "none"; }, null, { timeout: 5000 }).catch(() => {});
const clicked2 = await state(); const rowClicked2 = await rowAtTop(); const regionsClicked = await page.evaluate(() => (typeof window.__rompRegions === "function" ? window.__rompRegions() : null));
const rows2 = (await locateRows()).slice(locBefore2);
await page.evaluate(() => { window.__hold.delete("loadAround"); });
const released2 = await page.evaluate(() => window.__release());
await page.waitForFunction((u) => !!document.querySelector(`#content .turn[data-uuid="${u}"]`) || window.__sent.some((m) => m.what === "scrollwrite" && m.data && m.data.writer === "gap-fill"), deep2, { timeout: 15000 }).catch(() => {});
await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 0)))));
const late2 = await state(); const rowLate2 = await rowAtTop(); const regionsLate = await page.evaluate(() => (typeof window.__rompRegions === "function" ? window.__rompRegions() : null));
const target2 = await onScreen(deep2);
// ROAD 4 (T386 stage 2, medium 3): a fill while the reader stands INSIDE a gap must not jump them. At the transcript head (scrollTop 0,
// no row on screen) a held gap-scroll ask, then the release: the head page fills and its first turn sits at the top, scrollTop still ~0.
await page.evaluate(() => { window.__hold.add("loadTurns"); });
await page.evaluate(() => { const c = document.getElementById("content"); c.scrollTop = 0; });
await page.waitForFunction((n) => window.__sent.filter((m) => m.type === "loadTurns").length > n, await sentOf("loadTurns"), { timeout: 8000 }).catch(() => {});
const head4 = await page.evaluate(() => { const c = document.getElementById("content"); return { top: c.scrollTop, rows: c.querySelectorAll("#content .turn[data-uuid]").length }; });
await page.evaluate(() => { window.__hold.delete("loadTurns"); const n = window.__release(); return n; });
await page.waitForFunction(() => { const rs = (typeof window.__rompRegions === "function" && window.__rompRegions()) || []; return rs.length > 0 && rs[0].kind === "run" && rs[0].lo === 0; }, null, { timeout: 10000 }).catch(() => {});
await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 0)))));
const filled4 = await page.evaluate(() => { const c = document.getElementById("content"); const cTop = c.getBoundingClientRect().top; const first = c.querySelector("#content .turn[data-uuid]"); const r = first ? first.getBoundingClientRect() : null; return { top: c.scrollTop, firstTop: r ? Math.round(r.top - cTop) : null, firstVisible: !!r && r.bottom > cTop && r.top < c.getBoundingClientRect().bottom }; });
process.stdout.write("RESULT:" + JSON.stringify({ inGap6, heldAsk6, point6Before, point6After, fillWrites6, after6, head4, filled4, afterDrop5: { notice: afterDrop5.notice }, reask5, reNotice5, askState5, resident5, redialAsk5, redialed5, gapLo5: gapLo5Out, asked3, nospan3, boot: { gaps: boot.gaps, atBottom: boot.atBottom, notice: boot.notice, regions: await page.evaluate(() => (typeof window.__rompRegions === "function" ? window.__rompRegions() : null)) }, asked1: { notice: asked1.notice, noticeText: asked1.noticeText, top: asked1.top, gaps: asked1.gaps, loadAround: await sentOf("loadAround") }, trace1, released1, guess1, trace2,
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

    def test_a_fill_above_a_reader_deep_inside_the_gap_moves_the_point_under_the_viewport_top_by_less_than_a_turn(self):
        # round five, medium B: the head page fills while the reader stands deep in the head gap with no row on screen
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
        # MEDIUM 1: a landing's window ask dropped at a dead socket; the gap re-asks on the healed socket
        r = self._result()
        # the wedge is proven by the CLEARED STATE directly (medium 1): a landing ask lost to a socket death leaves nothing that would
        # block the gap from asking again — landingGaps, gapLoading and loadingOlder all empty, the notice down. This is a stronger,
        # deterministic proof than an indirect re-ask (a re-ask through the shared driver's churned regions is not reliably reproducible);
        # reask5 (loadAround or loadTurns after a deep link into a live gap) is kept as a best-effort signal, not asserted.
        self.assertFalse(r["afterDrop5"]["notice"], "the socket death brought the notice down (wsdown cleared the landing): %r" % r["afterDrop5"])
        a = r["askState5"]
        self.assertEqual((a["landingGaps"], a["gapLoading"], a["loadingOlder"]), (0, 0, False), "the wedge is gone: every in-flight ask's state cleared, so the gap can ask again (medium 1): %r" % a)
        self.assertGreaterEqual(r["redialed5"], 1, "the shim redialed and the kernel re-sent the session after the close: %r" % r["redialed5"])
        self.assertIsNotNone(r["gapLo5"], "a gap still stood after the redial to ask into: %r" % r.get("gapLo5"))
        self.assertGreaterEqual(r["redialAsk5"], 1, "a deep link into that gap on the healed socket asked again (loadAround or loadTurns): not wedged (round four, low 6): %r" % r["redialAsk5"])

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
