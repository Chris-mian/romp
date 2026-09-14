#!/usr/bin/env python3
"""T374 (the verifier of T366, 2026-09-12, executed on both heads): after a page reload, a reader whose saved row sat
MID-run (the restored raw top not in the top band) never asked a window: landActive armed the pending anchor and the keep
offset AFTER its own landing attempt, so the deep-link land waited for a later render pass that an idle session never
supplied (no loadAround, no loadOlder, no needFull; the reader parked at a raw pixel offset instead of their row). The
restore now lands its row in the same pass: resident → landed; outside the fresh window → its window asked at once and
chatWindow lands it on arrival.

Two served roads (the verifier's): two older fetches, a settle MID-run, a persist through the shell's hook, a reload, and
the saved row is back on screen through one window ask; and the same walk to the transcript HEAD, whose reload lands the
saved row at offset 0 with the plain strip (the T366 round-two low: a restore is no click). Both red on main before this
fix: after the reload the page sent nothing but the restore's own write. Shares its boot with
test_live_paused_window_browser.py (a synthetic transcript longer than the wire tail). Skips LOUDLY without the extension
deps or a Playwright browser; all fixtures synthetic.
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests.dist_copy import copy_dist

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
EXT = os.path.join(ROOT, "vscode-extension")
sys.path.insert(0, HERE)
import test_ship_reship as _lab   # noqa: E402  the lab kernel's environment (the module, not its classes)

SID = "aaaaaaaa-1111-2222-3333-444444444444"
TURNS = 320   # 640 events: past the wire tail, so older history stays on the server and the page's run is a tail


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


DRIVER_HEAD = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));
let browser;
try { browser = await chromium.launch(); }
catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
const page = await browser.newPage({ viewport: { width: 1000, height: 600 } });
// every frame the page sends its kernel, by type: the window asks, the older asks and the re-attach ask are the evidence
await page.addInitScript(() => {
  const send = WebSocket.prototype.send;
  window.__sent = [];
  WebSocket.prototype.send = function (d) {
    try { const m = JSON.parse(d); if (m && m.type) window.__sent.push(m); } catch (e) { /* not a frame */ }
    return send.call(this, d);
  };
});
await page.goto(cfg.chat);
await page.waitForSelector("#tabs .tab, #tabs [data-sid]", { timeout: 20000 });
await page.waitForFunction(() => document.querySelectorAll("#content .turn[data-uuid]").length >= 40, null, { timeout: 30000 });
await page.waitForTimeout(500);
const state = () => page.evaluate(() => {
  const c = document.getElementById("content");
  const notice = document.querySelector(".tx-landing-notice");   // the ONE landing notice (T386 stage 2); the paused strip is gone
  // the run's rendered EVENT turns: a notice unit at the tail (an api-error note) carries a word, not a uuid
  const turns = Array.from(document.querySelectorAll("#content .turn[data-uuid]")).filter((t) => /^[0-9a-f-]{36}$/.test(t.dataset.uuid));
  return { top: c.scrollTop, sh: c.scrollHeight, ch: c.clientHeight,
           atBottom: c.scrollHeight - c.scrollTop - c.clientHeight <= 2,
           strip: !!document.getElementById("live-paused"),   // must stay absent: no window ever pauses live updates (T386 stage 2)
           notice: !!notice && getComputedStyle(notice).display !== "none",
           firstUuid: turns.length ? turns[0].dataset.uuid : null, lastUuid: turns.length ? turns[turns.length - 1].dataset.uuid : null,
           turns: turns.length,
           sent: window.__sent.map((m) => m.type + (m.why ? ":" + m.why : "") + (m.what ? ":" + m.what + (m.data && m.data.writer ? ":" + m.data.writer : "") + (m.what === "regionask" && m.data ? ":nav=" + m.data.nav + ":reland=" + m.data.reland : "") : "")) };
});
const sentOf = (type) => page.evaluate((t) => window.__sent.filter((m) => m.type === t).length, type);
const boot = await state();
if (!boot.atBottom) { console.error("the page did not land at the bottom: " + JSON.stringify(boot)); process.exit(1); }
// OLDER events of the transcript itself (turns k0..k1, none resident: the page holds the tail), in the wire's shape, so a
// window around them does not overlap the run and the kernel can place any page ask that follows them
const pad = (n) => String(n).padStart(12, "0");
const older = (k0, k1) => Array.from({ length: k1 - k0 }, (_, i) => k0 + i).flatMap((k) => [
  { uuid: "11111111-2222-3333-4444-" + pad(2 * k), kind: "user", md: "question number " + k + " about the notes api", ts: new Date((cfg.base + 2 * k) * 1000).toISOString() },
  { uuid: "22222222-3333-4444-5555-" + pad(2 * k + 1), kind: "assistant", md: "Answer " + k + ": the handler reads the note by id and returns it.", ts: new Date((cfg.base + 2 * k + 1) * 1000).toISOString() }]);
"""


# the verifier's road: the head page filled into place (T386 stage 2: the gap asks for its page when its edge meets the viewport), a
# settle MID-run on one of its rows, a persist through the shell's hook, a reload; the saved row must be back on screen through one
# window ask (the reload's restore is a navigation: the one notice shows for the ask and is gone at the landing)
DRIVER_RESTORE = DRIVER_HEAD + r"""
// T386 stage 2: older history is a GAP the page asks for by page (loadTurns) when its edge meets the viewport; a jump to scrollTop 1 meets the
// head gap's top edge and asks for the head page, which fills in place and becomes a run from turn 0
const pagesAt = async (n) => page.waitForFunction((k) => window.__sent.filter((m) => m.type === "loadTurns").length >= k, n, { timeout: 20000 }).catch(() => {});   // bounded: at the base nothing asks by page, and the road runs on to its own red
const headFilled = () => page.waitForFunction(() => { const rs = typeof window.__rompRegions === "function" ? window.__rompRegions() : null; return !!rs && rs.length > 0 && rs[0].kind === "run" && rs[0].lo === 0; }, null, { timeout: 15000 }).catch(() => {});
await page.evaluate(() => { const c = document.getElementById("content"); c.scrollTop = 1; });
await pagesAt(1); await headFilled();
await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 0)))));
// settle mid-run: one screen below the head, off the top band, on a row of the head page, far above the tail a fresh page holds
await page.evaluate(() => { const c = document.getElementById("content"); c.scrollTop = c.clientHeight; });
await page.waitForTimeout(600);
const settled = await state();
const savedRow = await page.evaluate(() => {
  const c = document.getElementById("content"); const cTop = c.getBoundingClientRect().top;
  for (const t of Array.from(c.querySelectorAll(".turn[data-uuid]"))) { const r = t.getBoundingClientRect(); if (r.bottom > cTop + 1) return { uuid: t.dataset.uuid, y: r.top - cTop }; }
  return null;
});
await page.evaluate(() => window.__rompPersistForReload());
const saved = await page.evaluate(() => { const raw = sessionStorage.getItem("romp:reloadScroll"); return raw ? JSON.parse(raw) : null; });
await page.reload();
await page.waitForSelector("#tabs .tab, #tabs [data-sid]", { timeout: 20000 });
await page.waitForFunction(() => document.querySelectorAll("#content .turn[data-uuid]").length >= 40, null, { timeout: 30000 });
let landed = false;
try {
  await page.waitForFunction((u) => { const t = document.querySelector('#content .turn[data-uuid="' + u + '"]'); if (!t) return false;
    const c = document.getElementById("content").getBoundingClientRect(), r = t.getBoundingClientRect(); return r.bottom > c.top && r.top < c.bottom; }, savedRow ? savedRow.uuid : "none", { timeout: 15000 });
  landed = true;
} catch (e) { landed = false; }
await page.waitForTimeout(500);
const reloaded = await state();
reloaded.landed = landed;
reloaded.trail = await page.evaluate(() => (typeof window.__rompLandTrail === "function" ? window.__rompLandTrail() : null));   // the landing trail: which branch the restore took (round eight, CI diagnostics)
reloaded.saved = saved;
reloaded.savedRow = savedRow;
reloaded.asks = await page.evaluate(() => ({ loadAround: window.__sent.filter((m) => m.type === "loadAround").length, loadOlder: window.__sent.filter((m) => m.type === "loadOlder").length, needFull: window.__sent.filter((m) => m.type === "needFull").length }));
fs.writeSync(1, "RESULT:" + JSON.stringify({ boot, settled, reloaded }) + "\n");
await browser.close();
process.exit(0);
"""


# the verifier's second road (T366 round two; T386 stage 2): a reader at the transcript HEAD (its page filled into place), persisted
# through the shell's hook and reloaded lands back on their saved row at offset 0, through one window ask, and nothing pauses
DRIVER_RESTORE_HEAD = DRIVER_HEAD + r"""
// T386 stage 2: older history is a GAP the page asks for by page (loadTurns) when its edge meets the viewport; a jump to scrollTop 1 meets the
// head gap's top edge and asks for the head page, which fills in place and becomes a run from turn 0
const pagesAt = async (n) => page.waitForFunction((k) => window.__sent.filter((m) => m.type === "loadTurns").length >= k, n, { timeout: 20000 }).catch(() => {});   // bounded: at the base nothing asks by page, and the road runs on to its own red
const headFilled = () => page.waitForFunction(() => { const rs = typeof window.__rompRegions === "function" ? window.__rompRegions() : null; return !!rs && rs.length > 0 && rs[0].kind === "run" && rs[0].lo === 0; }, null, { timeout: 15000 }).catch(() => {});
await page.evaluate(() => { const c = document.getElementById("content"); c.scrollTop = 1; });
await pagesAt(1); await headFilled();
await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 0)))));
await page.evaluate(() => { const c = document.getElementById("content"); c.scrollTop = 0; });
await page.waitForTimeout(600);
const atHead = await state();
const savedRow = await page.evaluate(() => {
  const c = document.getElementById("content"); const cTop = c.getBoundingClientRect().top;
  for (const t of Array.from(c.querySelectorAll(".turn[data-uuid]"))) { const r = t.getBoundingClientRect(); if (r.bottom > cTop + 1) return { uuid: t.dataset.uuid, y: r.top - cTop }; }
  return null;
});
await page.evaluate(() => window.__rompPersistForReload());
await page.reload();
await page.waitForSelector("#tabs .tab, #tabs [data-sid]", { timeout: 20000 });
await page.waitForFunction(() => document.querySelectorAll("#content .turn[data-uuid]").length >= 40, null, { timeout: 30000 });
let landed = false;
try {
  await page.waitForFunction((u) => { const t = document.querySelector('#content .turn[data-uuid="' + u + '"]'); if (!t) return false;
    const c = document.getElementById("content").getBoundingClientRect(), r = t.getBoundingClientRect(); return Math.abs(r.top - c.top) <= 2; }, savedRow ? savedRow.uuid : "none", { timeout: 15000 });
  landed = true;
} catch (e) { landed = false; }
await page.waitForTimeout(500);
const reloaded = await state();
reloaded.landed = landed;
reloaded.trail = await page.evaluate(() => (typeof window.__rompLandTrail === "function" ? window.__rompLandTrail() : null));   // the landing trail: which branch the restore took (round eight, CI diagnostics)
reloaded.savedRow = savedRow;
reloaded.stripText = await page.evaluate(() => { const n = document.querySelector(".tx-landing-notice"); return n ? n.textContent : ""; });
reloaded.asks = await page.evaluate(() => ({ loadAround: window.__sent.filter((m) => m.type === "loadAround").length, needFull: window.__sent.filter((m) => m.type === "needFull").length }));
fs.writeSync(1, "RESULT:" + JSON.stringify({ boot, atHead, reloaded }) + "\n");
await browser.close();
process.exit(0);
"""


DRIVER_RESTORE_LATEREADY = DRIVER_HEAD + r"""
// T386 stage 2: older history is a GAP the page asks for by page (loadTurns) when its edge meets the viewport; a jump to scrollTop 1 meets the
// head gap's top edge and asks for the head page, which fills in place and becomes a run from turn 0
const pagesAt = async (n) => page.waitForFunction((k) => window.__sent.filter((m) => m.type === "loadTurns").length >= k, n, { timeout: 20000 }).catch(() => {});   // bounded: at the base nothing asks by page, and the road runs on to its own red
const headFilled = () => page.waitForFunction(() => { const rs = typeof window.__rompRegions === "function" ? window.__rompRegions() : null; return !!rs && rs.length > 0 && rs[0].kind === "run" && rs[0].lo === 0; }, null, { timeout: 15000 }).catch(() => {});
await page.evaluate(() => { const c = document.getElementById("content"); c.scrollTop = 1; });
await pagesAt(1); await headFilled();
await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 0)))));
// settle mid-run: one screen below the head, off the top band, on a row of the head page, far above the tail a fresh page holds
await page.evaluate(() => { const c = document.getElementById("content"); c.scrollTop = c.clientHeight; });
await page.waitForTimeout(600);
const settled = await state();
const savedRow = await page.evaluate(() => {
  const c = document.getElementById("content"); const cTop = c.getBoundingClientRect().top;
  for (const t of Array.from(c.querySelectorAll(".turn[data-uuid]"))) { const r = t.getBoundingClientRect(); if (r.bottom > cTop + 1) return { uuid: t.dataset.uuid, y: r.top - cTop }; }
  return null;
});
await page.evaluate(() => window.__rompPersistForReload());
const saved = await page.evaluate(() => { const raw = sessionStorage.getItem("romp:reloadScroll"); return raw ? JSON.parse(raw) : null; });
// the verifier's road (round eleven): the page's own `ready` is DELAYED three seconds at the socket (an init script wraps send before the
// page's scripts run; a flag in sessionStorage survives the reload), so the kernel serves an INDEX frame to the client before its ready
// and the reload restore's first frame is proto-less. The restore must land the same way as the fast case: through one window ask
// once the kernel has answered the ready, never through the older wire.
await page.evaluate(() => sessionStorage.setItem("lab:delayReady", "1"));
await page.addInitScript(() => { const send = WebSocket.prototype.send; WebSocket.prototype.send = function (d) { try { const m = JSON.parse(d); if (m && m.type === "ready" && sessionStorage.getItem("lab:delayReady") === "1") { const ws = this; window.__readyDelayed = (window.__readyDelayed || 0) + 1; setTimeout(() => { try { send.call(ws, d); } catch (e) { /* the socket closed */ } }, 3000); return; } } catch (e) { /* not a frame */ } return send.call(this, d); }; });
await page.reload();
await page.waitForSelector("#tabs .tab, #tabs [data-sid]", { timeout: 20000 });
await page.waitForFunction(() => document.querySelectorAll("#content .turn[data-uuid]").length >= 40, null, { timeout: 30000 });
const early = { delayed: await page.evaluate(() => window.__readyDelayed || 0), trail: await page.evaluate(() => (typeof window.__rompLandTrail === "function" ? window.__rompLandTrail() : null)), asks: await page.evaluate(() => ({ loadAround: window.__sent.filter((m) => m.type === "loadAround").length, loadOlder: window.__sent.filter((m) => m.type === "loadOlder").length, ready: window.__sent.filter((m) => m.type === "ready").length })) };
let landed = false;
try {
  await page.waitForFunction((u) => { const t = document.querySelector('#content .turn[data-uuid="' + u + '"]'); if (!t) return false;
    const c = document.getElementById("content").getBoundingClientRect(), r = t.getBoundingClientRect(); return r.bottom > c.top && r.top < c.bottom; }, savedRow ? savedRow.uuid : "none", { timeout: 20000 });
  landed = true;
} catch (e) { landed = false; }
await page.waitForTimeout(500);
await page.evaluate(() => sessionStorage.removeItem("lab:delayReady"));
const reloaded = await state();
reloaded.landed = landed;
reloaded.early = early;
reloaded.saved = saved;
reloaded.savedRow = savedRow;
reloaded.trail = await page.evaluate(() => (typeof window.__rompLandTrail === "function" ? window.__rompLandTrail() : null));
reloaded.asks = await page.evaluate(() => ({ loadAround: window.__sent.filter((m) => m.type === "loadAround").length, loadOlder: window.__sent.filter((m) => m.type === "loadOlder").length, needFull: window.__sent.filter((m) => m.type === "needFull").length, ready: window.__sent.filter((m) => m.type === "ready").length }));
fs.writeSync(1, "RESULT:" + JSON.stringify({ boot, settled, reloaded }) + "\n");
await browser.close();
process.exit(0);
"""


class ServedReloadRestoreMidRun(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(os.path.join(EXT, "node_modules", "playwright")):
            raise unittest.SkipTest("extension deps absent (npm ci not run here) — the served guard needs them")
        cls.lab = tempfile.mkdtemp(prefix="reload-restore-midrun-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            raise unittest.SkipTest("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
        dist = os.path.join(cls.lab, "dist")
        copy_dist(os.path.join(EXT, "dist"), dist)
        cls.state = os.path.join(cls.lab, "xdg", "romp")
        cwd = os.path.join(cls.lab, "proj")
        for d in ("names", "sdk", "states"):
            os.makedirs(os.path.join(cls.state, d), exist_ok=True)
        os.makedirs(cwd, exist_ok=True)
        Path(cls.state, "session-hosts").write_text("off\n")   # a lab root of its own: no session host (T348)
        Path(cls.state, "names", SID).write_text("web\t%s\t\t\n" % cwd)
        Path(cls.state, "sdk", SID + ".json").write_text(json.dumps(
            {"sid": SID, "name": "web", "cwd": cwd, "mode": "auto", "effort": "high",
             "lastSid": SID, "alive": True, "model": "claude-fable-5-1", "liveModel": "Fable 5.1"}))
        Path(cls.state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 100}, "seven_day": {"pct": 10}}))
        claude = os.path.join(cls.lab, "claude")
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        # TURNS user/assistant pairs, one a second, ending in the past: past the wire tail, so the page holds a tail
        recs, prev = [], None
        base = 1789000000
        for k in range(TURNS):
            u = "11111111-2222-3333-4444-%012d" % (2 * k)
            a = "22222222-3333-4444-5555-%012d" % (2 * k + 1)
            tu = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(base + 2 * k))
            ta = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(base + 2 * k + 1))
            recs.append({"type": "user", "uuid": u, "parentUuid": prev, "timestamp": tu, "sessionId": SID,
                         "message": {"role": "user", "content": "question number %d about the notes api" % k}})
            recs.append({"type": "assistant", "uuid": a, "parentUuid": u, "timestamp": ta, "sessionId": SID,
                         "message": {"role": "assistant", "model": "claude-fable-5-1", "stop_reason": "end_turn",
                                     "content": [{"type": "text", "text": "Answer %d: the handler reads the note by id and returns it." % k}]}})
            prev = a
        Path(proj, SID + ".jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
        cls.deep_uuid = "11111111-2222-3333-4444-%012d" % 20   # the eleventh question: far above the tail the page holds
        cls.deep_t = base + 20                                     # …and its time, as a card's focus frame carries it
        cls.base = base
        cls.port = _free_port()
        cls.token = "testtok-reloadmidrun"
        env = _lab.kernel_env(cls.lab, claude, dist, cls.port, cls.token)
        cls.klog = os.path.join(cls.lab, "kernel.log")
        cls.kernel = subprocess.Popen([os.path.join(BIN, "romp-kernel")],
                                      stdout=open(cls.klog, "w"), stderr=subprocess.STDOUT, env=env)
        import urllib.request
        for _ in range(120):
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/healthz" % cls.port, timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        else:
            cls.kernel.kill()
            raise unittest.SkipTest("hermetic kernel never served /healthz here")

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "kernel", None):
            cls.kernel.kill()
            cls.kernel.wait()
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

    def _drive(self, script, name):
        cfg = os.path.join(self.lab, name + ".json")
        with open(cfg, "w") as f:
            json.dump({"chat": "http://127.0.0.1:%d/chat?token=%s" % (self.port, self.token), "sid": SID,
                       "deepUuid": self.deep_uuid, "deepT": self.deep_t, "base": self.base,
                       "shots": os.environ.get("RELOAD_MIDRUN_SHOTS", "")}, f)
        driver = os.path.join(self.lab, name + ".mjs")
        with open(driver, "w") as f:
            f.write(script)
        p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=240,
                           env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
        if p.returncode == 3:
            raise unittest.SkipTest("no playwright browser on this box — the served guard needs one (CI installs none)")
        self.assertEqual(p.returncode, 0, "driver failed:\n" + p.stdout[-3000:] + p.stderr[-3000:])
        line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
        self.assertIsNotNone(line, "driver printed no result:\n" + p.stdout[-3000:])
        return json.loads(line[len("RESULT:"):])

    def test_a_reload_lands_the_reader_on_their_saved_row_mid_run_through_one_window_ask(self):
        r = self._drive(DRIVER_RESTORE, "restore")
        print("RESULT:" + json.dumps(r), file=sys.stderr)
        st, rl = r["settled"], r["reloaded"]
        self.assertIsNotNone(rl["savedRow"], "a row sat under the viewport top before the reload: %r" % st)
        self.assertIsNotNone(rl["saved"], "the shell's hook saved the record: %r" % rl)
        self.assertEqual(rl["saved"]["anchor"]["uuid"], rl["savedRow"]["uuid"], "the record names the row under the viewport top")
        self.assertTrue(rl["landed"], "the saved row is not back on screen after the reload: %r" % {k: rl[k] for k in ("top", "sh", "asks", "strip")})
        self.assertEqual(rl["asks"]["loadAround"], 1, "the row outside the fresh window is fetched through ONE window ask: %r" % rl["asks"])
        self.assertEqual(rl["asks"]["needFull"], 0, "no forced re-attach: %r" % rl["asks"])

    def test_a_reload_whose_ready_loses_the_race_to_the_kernels_push_still_lands_through_one_window_ask(self):
        # round eleven, the verifier's road: the page's ready delayed three seconds at the socket, so the kernel serves an index frame first
        # (proto absent); the restore must wait for the kernel's answer to the ready and land the saved row through ONE window ask, as the
        # fast case does, never through the older wire (the mid-run red on CI: a reload-restore write, then loadOlder, loadAround 0)
        r = self._drive(DRIVER_RESTORE_LATEREADY, "restore-lateready")
        rl = r["reloaded"]
        self.assertIsNotNone(rl["savedRow"], "a row sat under the viewport top when the page was persisted")
        self.assertGreaterEqual(rl["early"]["delayed"], 1, "the page's ready was parked for three seconds: %r" % rl["early"])
        self.assertTrue(rl["landed"], "the saved row is back on screen: %r" % {k: rl[k] for k in ("top", "asks", "trail")})
        self.assertEqual(rl["asks"]["loadAround"], 1, "the row outside the fresh window is fetched through ONE window ask, as in the fast case: %r (trail %r)" % (rl["asks"], rl["trail"]))
        self.assertEqual(rl["asks"]["loadOlder"], 0, "…never through the older wire: %r (trail %r)" % (rl["asks"], rl["trail"]))
        self.assertEqual(rl["early"]["asks"]["loadOlder"], 0, "no older ask went out while the ready was parked (the kernel serves no chat frame before the handshake): %r" % rl["early"])

    def test_a_reload_from_the_transcript_head_lands_the_saved_row_at_offset_zero_and_pauses_nothing(self):
        r = self._drive(DRIVER_RESTORE_HEAD, "restore-head")
        print("RESULT:" + json.dumps(r), file=sys.stderr)
        rl = r["reloaded"]
        self.assertIsNotNone(rl["savedRow"], "a row sat at the viewport top before the reload: %r" % r["atHead"])
        self.assertTrue(rl["landed"], "the saved row is not back at offset 0 after the reload: %r" % {k: rl[k] for k in ("top", "sh", "asks", "strip", "stripText")})
        self.assertEqual(rl["asks"], {"loadAround": 1, "needFull": 0}, "one window ask for the row, no forced re-attach: %r" % rl["asks"])
        self.assertFalse(rl["strip"], "the paused strip is retired: a reader restored into older history keeps live updates (T386 stage 2): %r" % rl)
        self.assertFalse(rl["notice"], "the landing notice is gone once the saved row landed: %r" % rl)


if __name__ == "__main__":
    unittest.main()
