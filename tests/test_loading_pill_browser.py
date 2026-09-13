#!/usr/bin/env python3
"""T402 (the user 2026-09-12, paraphrased): the chat's "Loading earlier messages" pill is not reliable: scrolled to the bottom it
says loading and cannot be made to go away; if they are not looking at older messages it should not offer to load them, and at
least it should be dismissible. The rule shipped, the same object as stage 2's one cancelable notice (plans/chat-history-regions.md):
the pill shows only while an older-history request the reader made is outstanding (a scroll or a landing into unloaded history),
never for the live tail's own growth or the page's own re-render; it hides the moment the request lands, fails, or the socket the
ask rode dies (every in-flight ask dies with it); a click on it ends the wait; a reader at the bottom with nothing outstanding
never sees it.

The served lab (the T366 boot: a hermetic kernel over a synthetic 320-turn transcript, the real /chat page) drives three roads:
  1. the stuck case, reproduced: the reader scrolls into unloaded history (one loadOlder goes out), the page's socket dies with
     the ask in flight (the lab drops the frame at the socket and closes it; the shim redials), the reader returns to the bottom:
     at the base the pill stays on for good; now the reopen ends the wait and the pill is gone;
  2. the dismissal: the ask goes out and is never answered (the lab drops it); the pill shows; a click hides it and frees the next
     ask (a second scroll into history sends a second loadOlder);
  3. the tail's own growth: the reader at the bottom, live turns arriving; the pill is never visible for a moment.
Skips LOUDLY without the extension deps or a Playwright browser (CI installs none). All fixtures synthetic.
"""
import json
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
from test_live_paused_window_browser import WindowLab, DRIVER_HEAD, SID, TURNS   # noqa: E402  the shared boot

LIVE_U = "33333333-4444-5555-6666-000000000011"
LIVE_A = "33333333-4444-5555-6666-000000000012"

DRIVER = DRIVER_HEAD + r"""
// the pill's every visible moment, recorded by an observer on its style (an event, not a poll), and the outgoing frames; a
// frame type in window.__drop never reaches the socket (the ask the kernel never sees), and __ws is the page's socket
await page.evaluate(() => {
  window.__pillSeen = 0; window.__drop = new Set();
  const watch = () => { const p = document.querySelector(".tx-loading-pill"); if (!p) return false; new MutationObserver(() => { if (getComputedStyle(p).display !== "none") window.__pillSeen++; }).observe(p, { attributes: true, attributeFilter: ["style"] }); if (getComputedStyle(p).display !== "none") window.__pillSeen++; return true; };
  if (!watch()) new MutationObserver((_, o) => { if (watch()) o.disconnect(); }).observe(document.body, { childList: true, subtree: true });
});
const pill = () => page.evaluate(() => { const p = document.querySelector(".tx-loading-pill"); return { present: !!p, visible: !!p && p.isConnected && getComputedStyle(p).display !== "none", text: p ? p.textContent : null, seen: window.__pillSeen }; });
const atBottom = () => page.evaluate(() => { const c = document.getElementById("content"); return { top: c.scrollTop, max: c.scrollHeight - c.clientHeight, atBottom: c.scrollHeight - c.scrollTop - c.clientHeight < 2 }; });
// the drop hook rides the same send wrapper the head installs: a frame whose type is in __drop is recorded and not sent
await page.evaluate(() => { const orig = WebSocket.prototype.send; WebSocket.prototype.send = function (d) { window.__ws = this; try { const m = JSON.parse(d); if (m && m.type && window.__drop.has(m.type)) { window.__sent.push(m); return; } } catch (e) {} return orig.call(this, d); }; });
// ROAD 3 first, on the fresh page at the bottom: live turns arrive, the pill never shows
const start = await pill(); const b0 = await atBottom();
for (let i = 0; i < 3; i++) {
  fs.appendFileSync(cfg.transcript, JSON.stringify({ type: "user", uuid: cfg.liveU.slice(0, -1) + i, parentUuid: cfg.lastUuid, timestamp: new Date().toISOString().replace(/\.\d{3}Z$/, ".000Z"), promptSource: "sdk", sessionId: cfg.sid, message: { role: "user", content: "another live question " + i } }) + "\n");
  await page.waitForTimeout(1200);
}
await page.waitForTimeout(1500);
const grown = await pill(); const bGrown = await atBottom();
const liveRows = await page.evaluate(() => document.querySelectorAll('#content .turn-user').length);
// ROAD 4, second, on the page still at its fresh tail (the user's first sentence: at the bottom it said loading): a deep link lands the reader in a history run the page holds
// apart from the live tail; at that run's BOTTOM the page asks the kernel for the newer turns, an ask the reader never made and
// is not waiting on, so no pill shows for it (before T402, requestNewer showed one)
// the target: the hundredth question, deep in history the fresh page does not hold (the boot holds the wire tail) and clear of the
// transcript's head, so the window the kernel serves around it leaves older turns above for the roads that follow
const kFirst = 100;
const deep = "11111111-2222-3333-4444-" + pad(2 * kFirst);
const deepResident4 = await page.evaluate((u) => !!document.querySelector('#content .turn[data-uuid="' + u + '"]'), deep);
await page.evaluate(() => { window.__in4 = []; window.addEventListener("message", (e) => { const m = e.data; if (m && m.type) window.__in4.push(m.type + (m.missing ? ":missing" : "")); }, true); });
const aroundBefore4 = await sentOf("loadAround"); const olderBefore4 = await sentOf("loadOlder");
await page.evaluate((frame) => window.postMessage(frame, "*"), { type: "focus", id: cfg.sid, anchor: deep, anchorT: cfg.base + 2 * kFirst });
let deepLanded4 = true;
try { await page.waitForFunction((u) => !!document.querySelector('#content .turn[data-uuid="' + u + '"]'), deep, { timeout: 20000 }); } catch (e) { deepLanded4 = false; }
const asks4 = { around: (await sentOf("loadAround")) - aroundBefore4, older: (await sentOf("loadOlder")) - olderBefore4, inbound: await page.evaluate(() => window.__in4.slice(-12)), state: await state(), sent: await page.evaluate(() => window.__sent.slice(-6).map((m) => m.type + ":" + JSON.stringify(m).slice(0, 120))) };
await page.waitForTimeout(1500);   // the landing settles (its own rule); the pill must not be showing for a landing either
const landed4 = await pill();
const newerBefore4 = await sentOf("loadNewer");
await page.evaluate(() => { const c = document.getElementById("content"); c.scrollTop = c.scrollHeight; });
await page.waitForFunction((n) => window.__sent.filter((m) => m.type === "loadNewer").length > n, newerBefore4, { timeout: 8000 }).catch(() => {});
await page.waitForTimeout(1200);
const newerAfter4 = await sentOf("loadNewer");
const bottom4 = await atBottom();
const pill4 = await pill();
// back to the live tail for the roads that follow (the feed's go-to-live chip: one focus frame with live true); the window's turns
// above stay unloaded, which roads 1 and 2 need
await page.evaluate((frame) => window.postMessage(frame, "*"), { type: "focus", id: cfg.sid, live: true });
await page.waitForFunction(() => { const c = document.getElementById("content"); return c.scrollHeight - c.scrollTop - c.clientHeight < 2; }, null, { timeout: 8000 }).catch(() => {});
await page.waitForTimeout(800);
const backLive4 = await atBottom();
// ROAD 1: the ask goes out and the socket dies with it in flight
await page.evaluate(() => { window.__drop.add("loadOlder"); });
const olderBefore1 = await sentOf("loadOlder");
await page.evaluate(() => { const c = document.getElementById("content"); c.scrollTop = 0; });   // a jump to the top: the head band asks once
await page.waitForFunction((n) => window.__sent.filter((m) => m.type === "loadOlder").length > n, olderBefore1, { timeout: 8000 }).catch(() => {});
await page.waitForTimeout(300);
const asked1 = await pill();
await page.evaluate(() => { window.__drop.delete("loadOlder"); window.__ws.close(); });   // the socket dies; the shim redials
await page.waitForTimeout(400);
const down1 = await pill();
let reopened = true;
try { await page.waitForFunction(() => document.querySelector(".tx-loading-pill") && getComputedStyle(document.querySelector(".tx-loading-pill")).display === "none", null, { timeout: 12000 }); } catch (e) { reopened = false; }
// back to the bottom: the reopened socket replays the tail and the page re-renders under the jump, so the jump is re-written until
// the content under it stops growing (a bounded Playwright poll, not a pause; the first run ended 50 px short, 2026-09-13)
await page.waitForFunction(() => { const c = document.getElementById("content"); if (c.scrollHeight - c.scrollTop - c.clientHeight >= 2) { c.scrollTop = c.scrollHeight; return false; } return true; }, null, { timeout: 8000, polling: 250 }).catch(() => {});
await page.waitForTimeout(1500);
await page.evaluate(() => { const c = document.getElementById("content"); if (c.scrollHeight - c.scrollTop - c.clientHeight >= 2) c.scrollTop = c.scrollHeight; });
await page.waitForTimeout(800);
const back1 = await pill(); const bBack1 = await atBottom();
// ROAD 2: an ask never answered, the click ends the wait and frees the next ask
await page.evaluate(() => { window.__drop.add("loadOlder"); });
const olderBefore2 = await sentOf("loadOlder");
await page.evaluate(() => { const c = document.getElementById("content"); c.scrollTop = 0; });
await page.waitForFunction((n) => window.__sent.filter((m) => m.type === "loadOlder").length > n, olderBefore2, { timeout: 8000 }).catch(() => {});
await page.waitForTimeout(300);
const shown2 = await pill();
if (shown2.visible) await page.evaluate(() => { const p = document.querySelector(".tx-loading-pill"); if (p) p.click(); });   // a DOM click: at main the pill takes no pointer and a real click hangs on the turn beneath
await page.waitForTimeout(300);
const clicked2 = await pill();
await page.evaluate(() => { window.__drop.delete("loadOlder"); const c = document.getElementById("content"); c.scrollTop = 200; });   // the drop lifted: the re-ask reaches the kernel and is answered, so nothing stays outstanding
await page.waitForTimeout(200);
await page.evaluate(() => { const c = document.getElementById("content"); c.scrollTop = 0; });
await page.waitForFunction((n) => window.__sent.filter((m) => m.type === "loadOlder").length > n + 1, olderBefore2, { timeout: 8000 }).catch(() => {});
const olderAfter2 = await sentOf("loadOlder");
const reasked2 = await pill();
await browser.close();
process.stdout.write("RESULT:" + JSON.stringify({ start, b0, grown, bGrown, liveRows, olderBefore1, asked1, down1, reopened, back1, bBack1, olderBefore2, shown2, clicked2, olderAfter2, reasked2, deepLanded4, deepResident4, kFirst4: kFirst, asks4, landed4, backLive4, newerBefore4, newerAfter4, bottom4, pill4 }) + "\n", () => process.exit(0));
"""


class ServedLoadingPill(WindowLab):
    _r = None

    def _result(self):
        cls = type(self)
        if cls._r is None:
            cls._r = self._drive(DRIVER, "loading-pill", extra={"liveU": LIVE_U, "liveA": LIVE_A, "turns": TURNS, "lastUuid": "22222222-3333-4444-5555-%012d" % (2 * TURNS - 1)})
        print("RESULT:" + json.dumps(cls._r), file=sys.stderr)
        return cls._r

    def test_the_live_tails_own_growth_never_shows_the_pill(self):
        r = self._result()
        self.assertTrue(r["b0"]["atBottom"], "the reader began at the bottom: %r" % r["b0"])
        self.assertGreaterEqual(r["liveRows"], 3, "the live turns arrived: %s user turns" % r["liveRows"])
        self.assertTrue(r["bGrown"]["atBottom"], "the reader is still at the bottom after the growth: %r" % r["bGrown"])
        self.assertEqual(r["grown"]["seen"], r["start"]["seen"], "the pill was visible for no moment while the tail grew: %r → %r" % (r["start"], r["grown"]))
        self.assertFalse(r["grown"]["visible"], "…and is not visible now: %r" % r["grown"])

    def test_an_ask_that_dies_with_its_socket_ends_its_wait_when_the_socket_reopens(self):
        r = self._result()
        self.assertTrue(r["asked1"]["visible"], "the scroll into unloaded history showed the pill: %r" % r["asked1"])
        self.assertTrue(r["down1"]["visible"] or r["reopened"], "the pill stood while the socket was down: %r" % r["down1"])
        self.assertTrue(r["reopened"], "the reopened socket ended the wait: the pill hid within the redial: %r" % r["back1"])
        self.assertTrue(r["bBack1"]["atBottom"], "the reader returned to the bottom: %r" % r["bBack1"])
        self.assertFalse(r["back1"]["visible"], "at the bottom with nothing outstanding, no pill: %r" % r["back1"])

    def test_a_click_on_the_pill_ends_the_wait_and_frees_the_next_ask(self):
        r = self._result()
        self.assertTrue(r["shown2"]["visible"], "the unanswered ask showed the pill: %r" % r["shown2"])
        self.assertIn("click to stop waiting", r["shown2"]["text"] or "", "the pill says it can be clicked away: %r" % r["shown2"])
        self.assertFalse(r["clicked2"]["visible"], "the click hid it: %r" % r["clicked2"])
        self.assertGreaterEqual(r["olderAfter2"] - r["olderBefore2"], 2, "the next scroll into history asked again (the in-flight mark went with the click): %s asks" % (r["olderAfter2"] - r["olderBefore2"]))

    def test_the_reader_at_the_bottom_of_a_history_run_sees_no_pill_for_the_newer_ask(self):
        # the user's first sentence (2026-09-12): scrolled to the bottom, it said loading. The page's own ask for the newer turns at
        # a history run's bottom is not the reader's wait; the pill is only for the reader's outstanding older ask
        r = self._result()
        self.assertFalse(r["deepResident4"], "the target was history the page did not hold (first held question %s): %r" % (r["kFirst4"], r["asks4"]))
        self.assertTrue(r["deepLanded4"], "the deep link landed in history: %r" % r["asks4"])
        self.assertGreater(r["newerAfter4"], r["newerBefore4"], "the bottom of the history run asked for the newer turns: %s → %s" % (r["newerBefore4"], r["newerAfter4"]))
        # the landing's own ask may show the pill (the reader asked for that history and can click it away); once landed, nothing
        # shows, and the page's newer ask at the run's bottom adds no visible moment
        self.assertFalse(r["landed4"]["visible"], "once landed, no pill: %r" % r["landed4"])
        self.assertEqual(r["pill4"]["seen"], r["landed4"]["seen"], "the newer ask at the run's bottom showed the pill for no moment: %r → %r" % (r["landed4"], r["pill4"]))
        self.assertFalse(r["pill4"]["visible"], "…and none is visible now: %r" % r["pill4"])
        self.assertTrue(r["backLive4"]["atBottom"], "the live chip returned the reader to the tail for the roads after: %r" % r["backLive4"])


if __name__ == "__main__":
    unittest.main()
