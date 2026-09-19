"""The client merge guard (2026-09-19), served on the window lab's hermetic kernel over a synthetic transcript longer than the wire tail
(the page boots holding the tail run; a head gap stands above it). Three roads, each on a fresh page, each ending in the shared bottom
assertion (R3, the window lab's driver head): after any history action, scrolling to the bottom shows the transcript's newest row last,
the view is at the bottom, and the rendered rows stand in transcript order.

- R1, the confirmed mis-order: the boot frame re-posted with tailLo null and headKnown false (a frame whose tail start the kernel could not
  name) leaves the page with no regions and files one regions-dropped row. A focus landing on a deep row must then take the OLDER wire
  (loadOlder, landed by key) and never a window ask: before the fix the landing asked a window, and its reply, with no regions to join,
  was concatenated BELOW the newest turns (an invented tail run at turn 0), so the bottom of the view showed the deep history.
- the echo landing: the kernel's full frame onto a caught-up client after a send carries the record and the reply where the page holds
  an `echo:` bubble after the same rows. Before the fix the echo, absent from the frame, was filed ABOVE the frame's tail as a phantom
  user bubble at the seam; now it leaves with the frame, and no frame-behind row is filed (the frame is newer than the page).
- a frame BEHIND the page: a full frame whose list ends two rows before the resident newest and whose tail starts eight turns below the
  held tail's. Before the fix the two newest rows were filed above the frame's tail (the seam read out of order, the tail run kept its
  count). Now they leave the model (the frame is authoritative for its span), one frame-behind row names it, and a real turn appended
  to the transcript afterwards lands as the newest row at the bottom.

Synthetic fixtures only (placeholder uuids, invented prose); hostname TESTHOST.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from tests.test_live_paused_window_browser import DRIVER_HEAD, TURNS, WindowLab  # noqa: E402

LIVE_U = "33333333-4444-5555-6666-000000000011"   # the live turn appended after the behind frame: synthetic uuids
LIVE_A = "33333333-4444-5555-6666-000000000012"

DRIVER = DRIVER_HEAD + r"""
// the socket hold (the landing-notice lab's shim): a frame whose type is in __hold is parked at the socket, not sent; __release sends the parked ones
const installShim = () => page.evaluate(() => { const orig = WebSocket.prototype.send; window.__hold = new Set(); window.__heldRaw = [];
  WebSocket.prototype.send = function (d) { window.__ws = this; try { const m = JSON.parse(d); if (m && m.type && window.__hold.has(m.type)) { window.__heldRaw.push(d); return; } } catch (e) {} return orig.call(this, d); };
  window.__release = () => { const ws = window.__ws; const held = window.__heldRaw; window.__heldRaw = []; for (const d of held) orig.call(ws, d); return held.length; }; });
await installShim();
// each road starts from a reload that boots the tail alone: the page's own reload restore is dropped before the page reads it
await page.addInitScript(() => { try { sessionStorage.removeItem("romp:reloadScroll"); } catch (e) { /* none */ } });
// the boot frame of every page life, captured before the page's own scripts run: the roads re-post or reshape it
await page.addInitScript(() => { window.__bootFrame = null; window.addEventListener("message", (e) => { const m = e.data; if (m && m.type === "session" && Array.isArray(m.events) && m.events.length && !window.__bootFrame) window.__bootFrame = m; }); });
const painted = () => page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 0)))));
const reboot = async () => {
  await page.reload();
  await page.waitForSelector("#tabs .tab, #tabs [data-sid]", { timeout: 20000 });
  await page.waitForFunction(() => document.querySelectorAll("#content .turn[data-uuid]").length >= 40, null, { timeout: 30000 });
  await page.waitForTimeout(500);
  await installShim();
  await page.evaluate(() => { const c = document.getElementById("content"); c.scrollTop = c.scrollHeight; });
  await painted();
};
// the kernel's own session and tail frames parked at the page (a capturing listener runs before the page's; a lab frame is let through by
// its mark), so what the road reads is the road's own frame, never a fresh one from the kernel
const holdIn = () => page.evaluate(() => { window.__holdIn = new Set(["session", "chatTail"]); window.__heldIn = []; if (!window.__inHook) { window.__inHook = true; window.addEventListener("message", (e) => { const m = e.data; if (m && m.type && window.__holdIn && window.__holdIn.has(m.type) && !m.__lab) { window.__heldIn.push(m.type + ":" + (m.tailLo === undefined ? "?" : String(m.tailLo))); e.stopImmediatePropagation(); } }, true); } });
const releaseIn = () => page.evaluate(() => { const h = (window.__heldIn || []).slice(); window.__holdIn = new Set(); return h; });
const diagRows = (what) => page.evaluate((w) => window.__sent.filter((m) => m.type === "clientDiag" && m.what === w).map((m) => m.data), what);
const regions = () => page.evaluate(() => (typeof window.__rompRegions === "function" ? window.__rompRegions() : null));
const tailRun = async () => { const rs = await regions(); return rs && rs.length ? rs[rs.length - 1] : null; };
const onScreen = (uuid) => page.evaluate((u) => { const t = document.querySelector(`#content .turn[data-uuid="${u}"]`); if (!t) return null; const c = document.getElementById("content").getBoundingClientRect(); const r = t.getBoundingClientRect(); return { top: Math.round(r.top - c.top), visible: r.bottom > c.top && r.top < c.bottom }; }, uuid);
const visible = (uuid, ms) => page.waitForFunction((u) => { const t = document.querySelector(`#content .turn[data-uuid="${u}"]`); if (!t) return false; const c = document.getElementById("content").getBoundingClientRect(), r = t.getBoundingClientRect(); return r.bottom > c.top && r.top < c.bottom; }, uuid, { timeout: ms }).then(() => true).catch(() => false);
const inDom = (uuid) => page.evaluate((u) => !!document.querySelector(`#content .turn[data-uuid="${u}"]`), uuid);
const isRecord = (e) => UUID_RE.test(String(e.uuid || ""));
// the index of the n-th user row of a frame's events (turns start at user rows; the frame's tail opens with one)
const nthUser = (events, n) => { let users = 0; for (let i = 0; i < events.length; i++) { if (events[i].kind === "user") { users++; if (users === n) return i; } } return -1; };

// ROAD 1 (R1): the boot frame re-posted with tailLo null and headKnown false; the kernel's frames parked at the page; the page's needFull,
// loadAround and loadTurns parked at the socket, loadOlder parked for the trail read alone and then flowing; no scroll; a focus landing on
// turn 100, deep in the history the page does not hold. The regions-less landing must take the older wire and never a window.
await reboot();
await page.evaluate(() => { window.__hold.add("needFull"); window.__hold.add("loadAround"); window.__hold.add("loadTurns"); });
await holdIn();
const frame1 = await page.evaluate(() => window.__bootFrame ? Object.assign({}, window.__bootFrame, { tailLo: null, headKnown: false, __lab: true }) : null);
const boot1 = frame1 ? { proto: frame1.proto, n: frame1.events.length, tailLo: (await page.evaluate(() => window.__bootFrame.tailLo)) } : null;
const sentAt1 = await page.evaluate(() => window.__sent.length);
await page.evaluate((f) => { if (f) window.postMessage(f, "*"); }, frame1);
await painted();
const regions1 = await regions();
const dropped1 = await diagRows("regions-dropped");
const deep1 = "11111111-2222-3333-4444-" + pad(2 * 100);
// the older ask is parked at the socket for the trail read alone (the landing-notice lab's road 13 does the same): the kernel answers
// loadOlder within milliseconds, chatHead's landing pass starts a fresh trail (landActive: each attempt's own) and lands exactly, so a
// trail read one paint after the focus raced the reply (three of eight reads saw the exact landing's trail, the review of 2026-09-19).
// Parked, the first attempt's trail stands until it is read; then the older ask alone goes out and the landing completes on the wire
await page.evaluate(() => { window.__hold.add("loadOlder"); });
await page.evaluate((frame) => window.postMessage(frame, "*"), { type: "focus", id: cfg.sid, anchor: deep1, anchorT: cfg.base + 2 * 100 });
await painted();
const trail1 = await page.evaluate(() => (typeof window.__rompLandTrail === "function" ? window.__rompLandTrail() : null));   // the FIRST attempt's trail: which wire it armed, read while its ask is parked
const releasedOlder1 = await page.evaluate(() => { window.__hold.delete("loadOlder"); const held = window.__heldRaw || []; const isOlder = (d) => { try { return JSON.parse(d).type === "loadOlder"; } catch (e) { return false; } };
  window.__heldRaw = held.filter(isOlder); const n = window.__release(); window.__heldRaw = held.filter((d) => !isOlder(d)); return n; });   // the parked older ask alone goes out; the parked window, page and full asks stay parked
const landedOnOlder1 = await visible(deep1, 20000);   // the older wire's chunks land it (re-attempting until resident); a parked window never does
const asks1 = await page.evaluate((n) => ({ loadOlder: window.__sent.slice(n).filter((m) => m.type === "loadOlder").length, loadAround: window.__sent.slice(n).filter((m) => m.type === "loadAround").length,
  parkedAround: (window.__heldRaw || []).filter((d) => { try { return JSON.parse(d).type === "loadAround"; } catch (e) { return false; } }).length }), sentAt1);
// before the fix the landing asked a window and it sat parked: releasing it shows what its reply did to the page (the older window concatenated
// below the newest turns); with the fix nothing is parked and this releases nothing
const released1 = await page.evaluate(() => { window.__hold.delete("loadAround"); window.__heldRaw = (window.__heldRaw || []).filter((d) => { try { return JSON.parse(d).type === "loadAround"; } catch (e) { return false; } }); return window.__release(); });
const landed1 = landedOnOlder1 || await visible(deep1, 15000);
const settled1 = await page.waitForFunction((u) => window.__sent.some((m) => m.type === "locateDiag" && m.anchor === u && Array.isArray(m.trail) && m.trail[m.trail.length - 1] === "pointer-exact"), deep1, { timeout: 15000 }).then(() => true).catch(() => false);   // the landing's settle ended: its exact row is filed then, and land-realign stops re-landing the anchor under the bottom check
const target1 = await onScreen(deep1);
const regionsLanded1 = await regions();
const r3a = await bottomCheck(cfg.lastUuid, transcriptOrder());   // read while the kernel's frames are still parked: what the page itself made of the landing
const heldIn1 = await releaseIn();
await page.evaluate(() => { window.__hold.delete("needFull"); window.__hold.delete("loadTurns"); window.__heldRaw = []; });

// ROAD 2 (the echo landing): a fresh page at the bottom, the kernel's frames parked; a synthetic tail appends an `echo:` user bubble after the
// tail's last transcript row (the kernel's provisional echo of a send); then a synthetic FULL frame, the kernel's landing full onto a caught-up
// client: its tail starts one turn below the held tail's start and carries the record and the reply after the last shared row.
await reboot(); await holdIn();
const boot2 = await page.evaluate(() => window.__bootFrame);
const tail2 = await tailRun();
const records2 = boot2.events.filter(isRecord);
const echo2 = "echo:11111111-2222-3333-4444-aaaaaaaaaaaa";
await page.evaluate(([sid, after, echo]) => window.postMessage({ type: "chatTail", id: sid, afterUuid: after, events: [{ uuid: echo, kind: "user", md: "one more question, sent, about the notes api" }], __lab: true }, "*"), [cfg.sid, records2[records2.length - 1].uuid, echo2]);
await painted();
const echoHeld2 = await tailRun();   // the echo joined the tail run
const idx2 = nthUser(boot2.events, 2);
const rec2 = "11111111-2222-3333-4444-" + pad(2 * cfg.turns), reply2 = "22222222-3333-4444-5555-" + pad(2 * cfg.turns + 1);
const events2 = boot2.events.slice(idx2).filter(isRecord).concat([
  { uuid: rec2, kind: "user", md: "one more question, sent, about the notes api", ts: new Date((cfg.base + 2 * cfg.turns) * 1000).toISOString() },
  { uuid: reply2, kind: "assistant", md: "Answer " + cfg.turns + ": the handler reads the note by id and returns it.", ts: new Date((cfg.base + 2 * cfg.turns + 1) * 1000).toISOString() }]);
const frame2 = Object.assign({}, boot2, { events: events2, tailLo: tail2.lo + 1, firstUuid: events2[0].uuid, lastUuid: reply2, __lab: true });
await page.evaluate((f) => window.postMessage(f, "*"), frame2);
await painted();
const tailAfter2 = await tailRun();
const behindRows2 = await diagRows("frame-behind");
const r3b = await bottomCheck(reply2, transcriptOrder().concat([rec2, reply2]));
// the seam: a landing on the frame's first row renders the rows around it; a phantom echo bubble would sit right above it
await page.evaluate((frame) => window.postMessage(frame, "*"), { type: "focus", id: cfg.sid, anchor: events2[0].uuid, anchorT: cfg.base + 2 * (tail2.lo + 1) });
await visible(events2[0].uuid, 10000);
await painted();
const echoBubbles2 = await page.evaluate(() => document.querySelectorAll('#content .turn[data-uuid^="echo:"]').length);
const seam2 = await renderedOrder(transcriptOrder().concat([rec2, reply2]));
await releaseIn();

// ROAD 3 (a frame BEHIND the page): a fresh page at the bottom, the kernel's frames parked; a synthetic full frame = the held tail run's rows
// from its ninth user row on (eight turns below its start), minus the two newest, plus the overlay cards riding the frame's suffix, with
// tailLo eight turns down. Then one real turn appended to the transcript, which the kernel's push lands.
await reboot(); await holdIn();
const boot3 = await page.evaluate(() => window.__bootFrame);
const tail3 = await tailRun();
const records3 = boot3.events.filter(isRecord);
const overlay3 = boot3.events.filter((e) => !isRecord(e));
const idx3 = nthUser(boot3.events, 9);
const kept3 = boot3.events.slice(idx3).filter(isRecord).slice(0, -2);
const events3 = kept3.concat(overlay3);
const newest3 = records3[records3.length - 1].uuid;   // the transcript's newest row, which the frame lacks
const frame3 = Object.assign({}, boot3, { events: events3, tailLo: tail3.lo + 8, firstUuid: events3[0].uuid, lastUuid: kept3[kept3.length - 1].uuid, __lab: true });
await page.evaluate((f) => window.postMessage(f, "*"), frame3);
await painted();
const tailAfter3 = await tailRun();
const behindRows3 = await diagRows("frame-behind");
const after3 = await bottomCheck(frame3.lastUuid, transcriptOrder());   // the frame is authoritative: its last transcript row is the bottom now
// the seam: a landing on the frame's first row renders the rows around it; the two dropped rows, filed above the frame's tail, would sit right there
await page.evaluate((frame) => window.postMessage(frame, "*"), { type: "focus", id: cfg.sid, anchor: events3[0].uuid, anchorT: cfg.base + 2 * (tail3.lo + 8) });
await visible(events3[0].uuid, 10000);
await painted();
const newestInDom3 = await inDom(newest3);
const seam3 = await renderedOrder(transcriptOrder());
// the kernel's frames flow again, and one real turn lands: the push the page cannot anchor on its base asks the full, which rebuilds the tail
const heldIn3 = await releaseIn();
const now3 = new Date();
fs.appendFileSync(cfg.transcript,
  JSON.stringify({ type: "user", uuid: cfg.liveU, parentUuid: newest3, timestamp: now3.toISOString(), sessionId: cfg.sid,
                   message: { role: "user", content: "and one more question, live, about the notes api" } }) + "\n" +
  JSON.stringify({ type: "assistant", uuid: cfg.liveA, parentUuid: cfg.liveU, timestamp: new Date(now3.getTime() + 1000).toISOString(), sessionId: cfg.sid,
                   message: { role: "assistant", model: "claude-fable-5-1", stop_reason: "end_turn", content: [{ type: "text", text: "Live answer: the handler reads the note by id and returns it." }] } }) + "\n");
const liveArrived3 = await page.waitForFunction(([u, n0]) => { const rs = typeof window.__rompRegions === "function" ? window.__rompRegions() : null; if (rs && rs.length && rs[rs.length - 1].n >= n0 + 2) return true; return !!document.querySelector('#content .turn[data-uuid="' + u + '"]'); }, [cfg.liveA, tailAfter3.n], { timeout: 20000 }).then(() => true).catch(() => false);   // the tail run grows by the two rows (its last key is the api-error card riding the frame's suffix), or the reply is rendered
await painted();
const r3c = await bottomCheck(cfg.liveA, transcriptOrder());
const asks3 = await page.evaluate(() => ({ needFull: window.__sent.filter((m) => m.type === "needFull").map((m) => m.why) }));
await browser.close();
process.stdout.write("RESULT:" + JSON.stringify({
  r1: { boot: boot1, hadFrame: !!frame1, regions: regions1, dropped: dropped1, landedOnOlder: landedOnOlder1, trail: trail1, releasedOlder: releasedOlder1, asks: asks1, released: released1, landed: landed1, settled: settled1, target: target1, regionsLanded: regionsLanded1, heldIn: heldIn1, r3: r3a },
  echo: { boot: { proto: boot2.proto, n: boot2.events.length, tailLo: boot2.tailLo }, tail: tail2, records: records2.length, echoHeld: echoHeld2, idx: idx2, frameEvents: events2.length, tailAfter: tailAfter2, behindRows: behindRows2, r3: r3b, echoBubbles: echoBubbles2, seam: seam2 },
  behind: { boot: { proto: boot3.proto, n: boot3.events.length, tailLo: boot3.tailLo }, tail: tail3, idx: idx3, frameEvents: events3.length, kept: kept3.length, overlay: overlay3.length, newest: newest3, frameLast: frame3.lastUuid, tailAfter: tailAfter3, behindRows: behindRows3, after: after3, newestInDom: newestInDom3, seam: seam3, heldIn: heldIn3, liveArrived: liveArrived3, r3: r3c, asks: asks3 } }) + "\n");
"""


class ServedClientMergeGuard(WindowLab):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._r = None

    def _result(self):
        if self._r is None:
            type(self)._r = self._drive(DRIVER, "mergeguard", extra={"turns": TURNS, "lastUuid": "22222222-3333-4444-5555-%012d" % (2 * TURNS - 1), "liveU": LIVE_U, "liveA": LIVE_A})
        # printed on every test's call: pytest shows a test's captured stderr only when THAT test fails
        print("MERGEGUARD:", json.dumps(self._r), file=sys.stderr)
        return self._r

    def _assert_bottom(self, b, what):
        self.assertEqual(b["last"], b["newest"], "%s: the bottom of the view is the transcript's newest row: %r" % (what, b))
        self.assertTrue(b["atBottom"], "%s: the view is at the bottom: %r" % (what, b))
        self.assertTrue(b["ordered"], "%s: the rendered rows stand in transcript order (misordered at %r): %r" % (what, b["misordered"], b))
        self.assertTrue(b["runsOrdered"], "%s: the runs are ordered by lo with the open-ended run last: %r" % (what, b["regions"]))

    def test_a_landing_on_a_page_whose_frame_could_not_name_its_tail_start_takes_the_older_wire_and_the_bottom_stays_the_newest_row(self):
        r = self._result()["r1"]
        self.assertTrue(r["hadFrame"], "the boot frame was captured for the re-post (an init script, before the page's scripts)")
        self.assertEqual(r["boot"]["proto"], 2, "the boot frame is the uuid-anchored wire's: %r" % r["boot"])
        self.assertIn(r["regions"], (None, []), "the tailLo-null frame left the page with no regions: %r" % r["regions"])
        self.assertEqual([(d["why"], d["heldRuns"]) for d in r["dropped"]], [("no-tail-lo", 1)], "one regions-dropped row names the frame that dropped the held runs: %r" % r["dropped"])
        self.assertEqual((r["asks"]["loadAround"], r["asks"]["parkedAround"]), (0, 0), "the regions-less landing asked no window (a window has no regions to join): %r, trail %r" % (r["asks"], r["trail"]))
        self.assertGreaterEqual(r["asks"]["loadOlder"], 1, "…it asked the older wire: %r" % r["asks"])
        self.assertIn("pointer-fetch-older", r["trail"] or [], "the landing armed on the older wire: %r" % r["trail"])
        self.assertEqual(r["releasedOlder"], 1, "the first attempt's one older ask was the frame parked for the trail read: %r" % r["releasedOlder"])
        self.assertTrue(r["landedOnOlder"], "the older wire landed the deep row on screen (asks %r, trail %r): %r" % (r["asks"], r["trail"], r["target"]))
        self._assert_bottom(r["r3"], "after the landing")

    def test_the_echo_landing_drops_the_held_echo_with_the_frame_never_a_phantom_bubble_above_its_tail_and_files_no_behind_row(self):
        r = self._result()["echo"]
        self.assertEqual(r["boot"]["proto"], 2, "the boot frame is the uuid-anchored wire's: %r" % r["boot"])
        self.assertEqual(r["echoHeld"]["n"], r["records"] + 1, "the synthetic tail appended the echo after the tail's last transcript row: %r → %r" % (r["tail"], r["echoHeld"]))
        self.assertEqual(r["tailAfter"]["n"], r["idx"] + r["frameEvents"], "the merged tail run is the held prefix before the frame's first row plus the frame: the echo is not in it (one more before the fix): %r" % r["tailAfter"])
        self.assertEqual(r["echoBubbles"], 0, "no phantom echo bubble at the seam (the rows around the frame's first row are rendered): seam %r" % r["seam"])
        self.assertTrue(r["seam"]["ordered"], "the seam reads in transcript order (misordered at %r): %r" % (r["seam"]["misordered"], r["seam"]))
        self.assertEqual(r["behindRows"], [], "the frame carries rows past the last shared key: newer than the page, no frame-behind row")
        self._assert_bottom(r["r3"], "after the echo landing")

    def test_a_full_frame_behind_the_page_is_authoritative_for_its_span_files_one_behind_row_and_the_next_live_turn_lands_as_the_newest_row(self):
        r = self._result()["behind"]
        self.assertEqual(r["boot"]["proto"], 2, "the boot frame is the uuid-anchored wire's: %r" % r["boot"])
        self.assertEqual(r["tailAfter"]["n"], r["idx"] + r["frameEvents"], "the two newest rows left the model with the frame (before the fix they sat above its tail and the count held): %r" % r["tailAfter"])
        self.assertEqual(len(r["behindRows"]), 1, "one frame-behind row: %r" % r["behindRows"])
        row = r["behindRows"][0]
        self.assertEqual((row["heldLo"], row["tailLo"], row["dropped"], row["afterLast"], row["rewindPending"]), (r["tail"]["lo"], r["tail"]["lo"] + 8, 2, 2, False), "the row names the held run, the frame's start and the two transcript rows dropped after the frame's last: %r" % row)
        self.assertEqual((row["frameLast"], row["heldLast"]), (r["frameLast"][-12:], r["newest"][-12:]), "…and the two last keys, by their tails: %r" % row)
        self.assertFalse(r["newestInDom"], "the dropped newest row is not rendered at the seam (before the fix it sat there, above older rows): seam %r" % r["seam"])
        self.assertTrue(r["seam"]["ordered"], "the seam reads in transcript order (misordered at %r): %r" % (r["seam"]["misordered"], r["seam"]))
        self._assert_bottom(r["after"], "right after the behind frame")
        self.assertTrue(r["liveArrived"], "the real turn appended afterwards reached the tail run (asks %r): %r" % (r["asks"], r["r3"]))
        self._assert_bottom(r["r3"], "after the live turn")


if __name__ == "__main__":
    unittest.main()
