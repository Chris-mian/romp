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
from pathlib import Path

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
// a pill click LATCHES the tab's older asks until the reader's own scroll evidence (round three, medium 1), so a road that stands in for
// the reader's scroll with a script jump first gives that evidence: one real wheel tick over the transcript, waited on by its event
const unlatch = async () => { const b = await page.evaluate(() => { const r = document.getElementById("content").getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2, n: window.__wheels }; }); await page.mouse.move(b.x, b.y); await page.mouse.wheel(0, -1); await page.waitForFunction((n) => window.__wheels > n, b.n, { timeout: 3000 }); };
// the drop hook rides the same send wrapper the head installs: a frame whose type is in __drop is recorded and not sent
await page.evaluate(() => { const orig = WebSocket.prototype.send; window.__hold = new Set(); window.__heldRaw = []; window.__in = []; window.__wheels = 0; window.addEventListener("wheel", () => { window.__wheels++; }, { capture: true, passive: true });
  window.addEventListener("message", (e) => { const m = e.data; if (m && m.type && e.source !== window) window.__in.push(m.type); }, true);
  WebSocket.prototype.send = function (d) { window.__ws = this; try { const m = JSON.parse(d); if (m && m.type && window.__drop.has(m.type)) { window.__sent.push(m); return; } if (m && m.type && window.__hold.has(m.type)) { window.__sent.push(m); window.__heldRaw.push(d); return; } } catch (e) {} return orig.call(this, d); };
  window.__release = () => { const ws = window.__ws; const held = window.__heldRaw; window.__heldRaw = []; for (const d of held) orig.call(ws, d); return held.length; }; });
// the page opens on the NEWEST session, the second one this lab writes after the boot (as a session created while the kernel runs
// takes the strip's focus); the roads are the first session's, so its tab is activated first and its view lands at the bottom
await page.evaluate((sid) => { const t = document.querySelector('#tabs .tab[data-id="' + sid + '"]'); if (t && !t.classList.contains("active")) t.click(); }, cfg.sid);
await page.waitForFunction((sid) => { const t = document.querySelector('#tabs .tab[data-id="' + sid + '"]'); return !!t && t.classList.contains("active"); }, cfg.sid, { timeout: 8000 });
await page.waitForFunction(() => { const c = document.getElementById("content"); return c.scrollHeight > c.clientHeight + 2 && c.scrollHeight - c.scrollTop - c.clientHeight < 2; }, null, { timeout: 8000 });
await page.waitForTimeout(500);
// ROAD 3 first, on the fresh page at the bottom: live turns arrive, the pill never shows
const start = await pill(); const b0 = await atBottom();
for (let i = 0; i < 3; i++) {
  fs.appendFileSync(cfg.transcript, JSON.stringify({ type: "user", uuid: cfg.liveU.slice(0, -1) + i, parentUuid: cfg.lastUuid, timestamp: new Date().toISOString().replace(/\.\d{3}Z$/, ".000Z"), promptSource: "sdk", sessionId: cfg.sid, message: { role: "user", content: "another live question " + i } }) + "\n");
  await page.waitForTimeout(1200);
}
await page.waitForTimeout(1500);
const grown = await pill(); const bGrown = await atBottom();
const liveRows = await page.evaluate(() => document.querySelectorAll('#content .turn-user').length);
// ROAD 6, second, while older history is still on the server (round two, medium 1): two tabs. The reader's older ask on tab A is dropped at the socket, so its wait stands; on
// tab B, which waits on nothing, the pill must not show, and a click there is inert; back on A the pill is there, and the click ends it.
await page.evaluate(() => { window.__drop.add("loadOlder"); });
const olderBefore6 = await sentOf("loadOlder");
await page.evaluate(() => { const c = document.getElementById("content"); c.scrollTop = 0; });
await page.waitForFunction((n) => window.__sent.filter((m) => m.type === "loadOlder").length > n, olderBefore6, { timeout: 8000 }).catch(() => {});
await page.waitForFunction(() => { const p = document.querySelector(".tx-loading-pill"); return !!p && getComputedStyle(p).display !== "none"; }, null, { timeout: 4000 }).catch(() => {});
const onA6 = await pill();
const asked6 = { older: (await sentOf("loadOlder")) - olderBefore6, state: await state(), sentTail: await page.evaluate(() => window.__sent.slice(-8).map((m) => m.type + (m.what ? ":" + m.what + (m.data && m.data.writer ? ":" + m.data.writer : "") : ""))) };
const tabB = await page.evaluate((sid2) => { const t = document.querySelector('#tabs .tab[data-id="' + sid2 + '"]'); if (!t) return false; t.click(); return true; }, cfg.sid2);
await page.waitForFunction((sid2) => { const t = document.querySelector('#tabs .tab[data-id="' + sid2 + '"]'); return !!t && t.classList.contains("active"); }, cfg.sid2, { timeout: 8000 }).catch(() => {});
await page.waitForTimeout(400);
const onB6 = await pill();
await page.evaluate(() => { const p = document.querySelector(".tx-loading-pill"); if (p) p.click(); });   // inert on B: nothing to end there
await page.waitForTimeout(300);
const onBClicked6 = await pill();
await page.evaluate((sid) => { const t = document.querySelector('#tabs .tab[data-id="' + sid + '"]'); if (t) t.click(); }, cfg.sid);
await page.waitForFunction((sid) => { const t = document.querySelector('#tabs .tab[data-id="' + sid + '"]'); return !!t && t.classList.contains("active"); }, cfg.sid, { timeout: 8000 }).catch(() => {});
await page.waitForTimeout(400);
const backOnA6 = await pill();
await page.evaluate(() => { const p = document.querySelector(".tx-loading-pill"); if (p) p.click(); });
await page.waitForFunction(() => { const p = document.querySelector(".tx-loading-pill"); return !p || getComputedStyle(p).display === "none"; }, null, { timeout: 4000 }).catch(() => {});
const endedOnA6 = await pill();
await page.evaluate(() => { window.__drop.delete("loadOlder"); });   // the roads after ask with a live socket
// ROAD 4, third, on the page still at its fresh tail (the user's first sentence: at the bottom it said loading): a deep link lands the reader in a history run the page holds
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
// ROAD 5 (round two, medium 2 and low 1): a deep link into history the page does not hold asks for a window; the ask is HELD at the
// socket; the reader clicks the pill away (the landing files its row as cancelled); the reply is then released. The late window must
// insert nothing under the reader and move nothing: the reader's spot and their place at the tail are what they were.
const deep5 = "11111111-2222-3333-4444-" + pad(2 * 30);
await page.evaluate(() => { window.__hold.add("loadAround"); });
const aroundBefore5 = await sentOf("loadAround"); const locateBefore5 = await page.evaluate(() => window.__sent.filter((m) => m.type === "locateDiag").length);
await page.evaluate((frame) => window.postMessage(frame, "*"), { type: "focus", id: cfg.sid, anchor: deep5, anchorT: cfg.base + 2 * 30 });
await page.waitForFunction((n) => window.__sent.filter((m) => m.type === "loadAround").length > n, aroundBefore5, { timeout: 8000 }).catch(() => {});
await page.waitForFunction(() => { const p = document.querySelector(".tx-loading-pill"); return !!p && getComputedStyle(p).display !== "none"; }, null, { timeout: 4000 }).catch(() => {});
const shown5 = await pill(); const pos5 = await atBottom();
await page.evaluate(() => { const p = document.querySelector(".tx-loading-pill"); if (p) p.click(); });
await page.waitForFunction(() => { const p = document.querySelector(".tx-loading-pill"); return !p || getComputedStyle(p).display === "none"; }, null, { timeout: 4000 }).catch(() => {});
const clicked5 = await pill();
const cancelled5 = await page.evaluate((n) => window.__sent.filter((m) => m.type === "locateDiag").slice(n).map((m) => ({ ok: m.ok, cancelled: m.cancelled === true, anchor: m.anchor })), locateBefore5);
const afterClick5 = await atBottom();
await page.evaluate(() => { window.__hold.delete("loadAround"); });
const released5 = await page.evaluate(() => window.__release());
await page.waitForFunction(() => window.__in.includes("chatWindow"), null, { timeout: 8000 }).catch(() => {});
await page.waitForTimeout(1500);   // the reply's adoption, its re-base ask and the frame that answers it
const afterReply5 = await atBottom(); const pillAfterReply5 = await pill();
// ROAD 7 (round three, medium 2): the ordinary deep-link road (landActive clears the landing's own mark while the ask is in flight),
// the ask HELD, and a FAULT reply arriving in its place through the shim's door: the landing must stand down at once (the toast, the
// seek note gone, no pill), not thirty seconds later by the backstop
const deep7 = "11111111-2222-3333-4444-" + pad(2 * 10);   // turn 10: no earlier road loads it (road 5 released a window around turn 60, road 4 landed around 100)
await page.evaluate(() => { window.__hold.add("loadAround"); });
const aroundBefore7 = await sentOf("loadAround");
await page.evaluate((frame) => window.postMessage(frame, "*"), { type: "focus", id: cfg.sid, anchor: deep7, anchorT: cfg.base + 2 * 10 });
await page.waitForFunction((n) => window.__sent.filter((m) => m.type === "loadAround").length > n, aroundBefore7, { timeout: 8000 }).catch(() => {});
const asked7 = await pill();
await page.evaluate(([sid, anchor]) => window.postMessage({ type: "chatWindow", id: sid, anchor, events: [], moreBefore: false, moreAfter: false, missing: true, fault: true, error: "synthetic fault" }, "*"), [cfg.sid, deep7]);
await page.waitForFunction(() => !!document.querySelector(".locate-toast"), null, { timeout: 3000 }).catch(() => {});
await page.waitForTimeout(300);
const faulted7 = { pill: await pill(), toast: await page.evaluate(() => { const t = document.querySelector(".locate-toast"); return t ? t.textContent : null; }), seekNote: await page.evaluate(() => !!document.getElementById("seek-note")) };
await page.evaluate(() => { window.__hold.delete("loadAround"); window.__heldRaw = []; });   // the held ask is dropped, not released: one ask has one reply
// ROAD 1: the ask goes out and the socket dies with it in flight (the clicks of roads 6 and 5 latched the tab: the reader's wheel first)
await unlatch();
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
await unlatch();
await page.evaluate(() => { window.__drop.add("loadOlder"); });
const olderBefore2 = await sentOf("loadOlder");
await page.evaluate(() => { const c = document.getElementById("content"); c.scrollTop = 0; });
await page.waitForFunction((n) => window.__sent.filter((m) => m.type === "loadOlder").length > n, olderBefore2, { timeout: 8000 }).catch(() => {});
await page.waitForTimeout(300);
const shown2 = await pill();
if (shown2.visible) await page.evaluate(() => { const p = document.querySelector(".tx-loading-pill"); if (p) p.click(); });   // a DOM click: at main the pill takes no pointer and a real click hangs on the turn beneath
await page.waitForTimeout(300);
const clicked2 = await pill();
// the cancel LATCHES (round three, medium 1): at the edge with no move of the reader's own, no re-ask and no pill, sampled twice
await page.waitForTimeout(500);
const held2a = { pill: await pill(), older: (await sentOf("loadOlder")) - olderBefore2 };
await page.waitForTimeout(1000);
const held2b = { pill: await pill(), older: (await sentOf("loadOlder")) - olderBefore2 };
// a scroll with no input behind it (a script, the browser's own anchoring) is not the reader's evidence: the edge still asks nothing.
// Down and back up to the top band in two frames, far enough for the virtualiser to run its edge check (a one-pixel move did not, so the
// base stayed green on this sample); at the base the check asks again here
await page.evaluate(() => { const c = document.getElementById("content"); c.scrollTop = 300; });
await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
await page.evaluate(() => { const c = document.getElementById("content"); c.scrollTop = 0; });
await page.waitForFunction((n) => window.__sent.filter((m) => m.type === "loadOlder").length > n + 1, olderBefore2, { timeout: 1500 }).catch(() => {});
const held2c = { pill: await pill(), older: (await sentOf("loadOlder")) - olderBefore2 };
// …until the reader's OWN evidence: a real wheel over the transcript (the latch clears), then the edge asks again
await page.evaluate(() => { window.__drop.delete("loadOlder"); });   // the drop lifted: the re-ask reaches the kernel and is answered, so nothing stays outstanding
const box2 = await page.evaluate(() => { const r = document.getElementById("content").getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; });
await page.mouse.move(box2.x, box2.y);
await page.evaluate(() => { const c = document.getElementById("content"); c.scrollTop = 200; });
await page.waitForTimeout(200);
await page.mouse.wheel(0, -400);
await page.waitForFunction((n) => window.__sent.filter((m) => m.type === "loadOlder").length > n + 1, olderBefore2, { timeout: 8000 }).catch(() => {});
const olderAfter2 = await sentOf("loadOlder");
const reasked2 = await pill();
await browser.close();
process.stdout.write("RESULT:" + JSON.stringify({ start, b0, grown, bGrown, liveRows, olderBefore1, asked1, down1, reopened, back1, bBack1, olderBefore2, shown2, clicked2, held2a, held2b, held2c, olderAfter2, reasked2, deepLanded4, deepResident4, kFirst4: kFirst, asks4, landed4, backLive4, newerBefore4, newerAfter4, bottom4, pill4, asked7, faulted7, shown5, pos5, clicked5, cancelled5, afterClick5, released5, afterReply5, pillAfterReply5, onA6, asked6, tabB, onB6, onBClicked6, backOnA6, endedOnA6 }) + "\n", () => process.exit(0));
"""


SID2 = "33333333-4444-5555-6666-000000000099"   # a second session, for the two-tab road (round two, medium 1)


class ServedLoadingPill(WindowLab):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # a second session beside the first: its name, its backend record and a short transcript in the same project, so the
        # kernel lists a second tab; written after the boot, which the kernel picks up like any session created while it runs
        cwd = os.path.join(cls.lab, "proj")
        Path(cls.state, "names", SID2).write_text("api\t%s\t\t\n" % cwd)
        Path(cls.state, "sdk", SID2 + ".json").write_text(json.dumps(
            {"sid": SID2, "name": "api", "cwd": cwd, "mode": "auto", "effort": "high",
             "lastSid": SID2, "alive": True, "model": "claude-fable-5-1", "liveModel": "Fable 5.1"}))
        proj = os.path.dirname(cls.transcript)
        recs, prev, base = [], None, 1789000000 + 5000
        for k in range(4):
            u = "77777777-8888-9999-aaaa-%012d" % (2 * k); a = "88888888-9999-aaaa-bbbb-%012d" % (2 * k + 1)
            tu = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(base + 2 * k)); ta = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(base + 2 * k + 1))
            recs.append({"type": "user", "uuid": u, "parentUuid": prev, "timestamp": tu, "sessionId": SID2, "message": {"role": "user", "content": "api question %d" % k}})
            recs.append({"type": "assistant", "uuid": a, "parentUuid": u, "timestamp": ta, "sessionId": SID2, "message": {"role": "assistant", "model": "claude-fable-5-1", "stop_reason": "end_turn", "content": [{"type": "text", "text": "api answer %d" % k}]}})
            prev = a
        Path(proj, SID2 + ".jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))

    _r = None

    def _result(self):
        cls = type(self)
        if cls._r is None:
            cls._r = self._drive(DRIVER, "loading-pill", extra={"sid2": SID2, "liveU": LIVE_U, "liveA": LIVE_A, "turns": TURNS, "lastUuid": "22222222-3333-4444-5555-%012d" % (2 * TURNS - 1)})
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
        for k in ("held2a", "held2b", "held2c"):   # round three, medium 1 (held2c: a script scroll at the edge is not the reader's evidence): the cancel holds at the edge with no move of the reader's own
            self.assertFalse(r[k]["pill"]["visible"], "%s: the pill stays hidden after the click: %r" % (k, r[k]))
            self.assertEqual(r[k]["older"], 1, "%s: no re-ask while the latch stands: %r" % (k, r[k]))
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

    def test_a_click_on_a_landings_ask_files_the_row_as_cancelled_and_the_late_reply_moves_nothing(self):
        # round two, medium 2 and low 1: the ask held at the socket, the pill clicked away, the reply released afterwards
        r = self._result()
        self.assertTrue(r["shown5"]["visible"], "the landing's ask showed the pill: %r" % r["shown5"])
        self.assertFalse(r["clicked5"]["visible"], "the click hid it: %r" % r["clicked5"])
        self.assertTrue(any(c["cancelled"] and c["ok"] is False and c["anchor"] for c in r["cancelled5"]), "the landing filed its row as cancelled at the click: %r" % r["cancelled5"])
        self.assertEqual(r["afterClick5"]["top"], r["pos5"]["top"], "the click moved nothing: %r → %r" % (r["pos5"], r["afterClick5"]))
        self.assertGreaterEqual(r["released5"], 1, "the held ask went out after the click")
        self.assertEqual(r["afterReply5"]["top"], r["afterClick5"]["top"], "the late reply moved nothing: %r → %r" % (r["afterClick5"], r["afterReply5"]))
        self.assertEqual(r["afterReply5"]["atBottom"], r["afterClick5"]["atBottom"], "…and the reader's place at the tail is what it was")
        self.assertFalse(r["pillAfterReply5"]["visible"], "no pill after the reply: %r" % r["pillAfterReply5"])

    def test_the_pill_is_the_active_tabs_own_wait_and_a_click_ends_it_whatever_the_other_tab_holds(self):
        # round two, medium 1: two tabs; the wait on A never shows on B and B's click is inert; back on A the pill stands and ends
        r = self._result()
        self.assertTrue(r["tabB"], "the second tab was on the strip")
        self.assertTrue(r["onA6"]["visible"], "the dropped ask on A showed the pill: %r" % r["onA6"])
        self.assertFalse(r["onB6"]["visible"], "on B, with nothing outstanding, no pill: %r" % r["onB6"])
        self.assertFalse(r["onBClicked6"]["visible"], "a click on B changes nothing: %r" % r["onBClicked6"])
        self.assertTrue(r["backOnA6"]["visible"], "back on A the wait still stands: %r" % r["backOnA6"])
        self.assertFalse(r["endedOnA6"]["visible"], "the click on A ends it: %r" % r["endedOnA6"])

    def test_a_fault_on_the_ordinary_deep_link_road_stands_the_landing_down_at_once(self):
        # round three, medium 2: the stand-down keys on the wait the ask recorded, not on the landing's mark landActive clears
        r = self._result()
        self.assertTrue(r["asked7"]["visible"], "the deep link's ask showed the pill: %r" % r["asked7"])
        f = r["faulted7"]
        self.assertFalse(f["pill"]["visible"], "the fault ended the wait: %r" % f)
        self.assertEqual(f["toast"], "the history could not be loaded just now", "the reader is told at once, in the fault's own words: %r" % f)
        self.assertFalse(f["seekNote"], "the seek note is gone with the landing")


if __name__ == "__main__":
    unittest.main()
