"""The served WINDOW LAB base (T366; T386 stage 2): a hermetic kernel over a synthetic transcript long enough that older history
stays on the server and the page's run is a tail, driven by Playwright through the driver head below (DRIVER_HEAD: the pad, sentOf,
state and frame hooks). The regions labs (test_history_regions_browser.py, test_landing_notice_browser.py)
build on WindowLab; this module holds no tests of its own since stage 2 retired the paused strip and the detached client (the tail
run is always resident and live, so no window ever pauses live updates: plans/chat-history-regions.md Part B).
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
TOOL_TURN = 40   # the turn whose reply opens with four tool calls and ends with the words (T386's card-anchor road)
TOOL_TURN_TEXT = ("The four checks passed. Two questions for you: which bound do we keep for the retry curve, "
                  "and do we drop the second plot?")


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
try { browser = await chromium.launch(cfg.launch || {}); }   // a lab may ask for classic scrollbars (the settle lab's drag road): Playwright hides them headless by default
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
const pageEvents = [];   // the page's own errors, printed with a boot that fails (a lab's red should name the page's fault, not a bare timeout)
page.on("pageerror", (e) => pageEvents.push("pageerror:" + String(e).slice(0, 300)));
page.on("console", (m) => { if (m.type() === "error") pageEvents.push("console:" + m.text().slice(0, 300)); });
await page.addInitScript(() => {   // the session frames the page receives, for a boot that stalls: how many events each carried, and its tail start
  window.__bootFrames = [];
  window.addEventListener("message", (e) => { const m = e.data; if (m && (m.type === "session" || m.type === "chatTail" || m.type === "chatWindow" || m.type === "chatTurns")) window.__bootFrames.push({ type: m.type, id: String(m.id || "").slice(0, 8), n: Array.isArray(m.events) ? m.events.length : null, tailLo: m.tailLo, headKnown: m.headKnown, skeleton: m.skeleton, proto: m.proto, first: m.firstUuid, last: m.lastUuid, keys: Object.keys(m).slice(0, 14), source: e.source === window ? "page" : "socket" }); });
});
await page.goto(cfg.chat);
await page.waitForSelector("#tabs .tab, #tabs [data-sid]", { timeout: 20000 });
try { await page.waitForFunction(() => document.querySelectorAll("#content .turn[data-uuid]").length >= 40, null, { timeout: 30000 }); }
catch (e) {
  const seen = await page.evaluate(() => ({ turns: document.querySelectorAll("#content .turn[data-uuid]").length, units: document.querySelectorAll("#content [data-unit]").length, gaps: document.querySelectorAll("#content .tx-gap").length, regions: typeof window.__rompRegions === "function" ? window.__rompRegions() : null, sh: (document.getElementById("content") || {}).scrollHeight, frames: (window.__bootFrames || []).slice(0, 12), sent: (window.__sent || []).slice(0, 16).map((m) => m.type + (m.why ? ":" + m.why : "")) })).catch(() => null);
  console.error("boot did not reach forty rows: " + JSON.stringify(seen) + " page events: " + JSON.stringify(pageEvents.slice(0, 6)));
  throw e;
}
await page.waitForTimeout(500);
const state = () => page.evaluate(() => {
  const c = document.getElementById("content");
  const notice = document.querySelector(".tx-landing-notice");   // the ONE landing notice (T386 stage 2); the paused strip is retired
  // the run's rendered EVENT turns: a notice unit at the tail (an api-error note) carries a word, not a uuid
  const turns = Array.from(document.querySelectorAll("#content .turn[data-uuid]")).filter((t) => /^[0-9a-f-]{36}$/.test(t.dataset.uuid));
  return { top: c.scrollTop, sh: c.scrollHeight, ch: c.clientHeight,
           atBottom: c.scrollHeight - c.scrollTop - c.clientHeight <= 2,
           strip: !!document.getElementById("live-paused"),   // must stay absent: no window ever pauses live updates (T386 stage 2)
           notice: !!notice && getComputedStyle(notice).display !== "none", noticeText: notice ? notice.textContent : "",
           gaps: Array.from(document.querySelectorAll("#content .tx-gap")).map((g) => ({ lo: Number(g.dataset.lo), hi: Number(g.dataset.hi), h: g.offsetHeight, loading: g.classList.contains("tx-gap-loading") })),
           firstUuid: turns.length ? turns[0].dataset.uuid : null, lastUuid: turns.length ? turns[turns.length - 1].dataset.uuid : null,
           turns: turns.length,
           frames: (window.__bootFrames || []).slice(-8),   // the last frames the page received (type, id, event count, tail start, source)
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

# road 1 and road 2 in one page: the unasked window first (the reader attached, above the bottom), then the deep link
class WindowLab(unittest.TestCase):
    """The boot: a hermetic kernel over a synthetic transcript longer than the wire tail, the real /chat page served
    from a copy of the built bundle. Subclassed by this module's tests and by the landing lab (T386,
    tests/test_landing_settles_browser.py); carries no tests of its own."""
    maxDiff = None

    @classmethod
    def _skip(cls, why):
        if os.environ.get("ROMP_SERVED_TESTS_REQUIRE") == "1":
            raise AssertionError("ROMP_SERVED_TESTS_REQUIRE=1 but the served lab could not run: " + why)
        raise unittest.SkipTest(why)

    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(os.path.join(EXT, "node_modules", "playwright")):
            cls._skip("extension deps absent (npm ci not run here) — the served guard needs them")
        cls.lab = tempfile.mkdtemp(prefix="live-paused-window-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            cls._skip("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
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
            text = "Answer %d: the handler reads the note by id and returns it." % k
            pa = u
            if k == TOOL_TURN:
                # one turn whose FIRST atoms are tool calls (four, like a card's anchor on a Bash) and whose words come last
                # (T386): a card anchored on the first atom must land the reader on the words, not on the tool group
                for i in range(4):
                    tu_id = "toolu_%03d_%d" % (k, i)
                    tuu = "44444444-5555-6666-7777-%012d" % (10 * k + i)
                    tru = "55555555-6666-7777-8888-%012d" % (10 * k + i)
                    recs.append({"type": "assistant", "uuid": tuu, "parentUuid": pa, "timestamp": ta, "sessionId": SID,
                                 "message": {"role": "assistant", "model": "claude-fable-5-1", "stop_reason": "tool_use",
                                             "content": [{"type": "tool_use", "id": tu_id, "name": "Bash", "input": {"command": "true # check %d" % i}}]}})
                    recs.append({"type": "user", "uuid": tru, "parentUuid": tuu, "timestamp": ta, "sessionId": SID,
                                 "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tu_id, "content": "ok"}]},
                                 "toolUseResult": {"stdout": "ok", "stderr": "", "interrupted": False, "isImage": False}})
                    pa = tru
                text = TOOL_TURN_TEXT
            recs.append({"type": "assistant", "uuid": a, "parentUuid": pa, "timestamp": ta, "sessionId": SID,
                         "message": {"role": "assistant", "model": "claude-fable-5-1", "stop_reason": "end_turn",
                                     "content": [{"type": "text", "text": text}]}})
            prev = a
        Path(proj, SID + ".jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
        cls.transcript = os.path.join(proj, SID + ".jsonl")      # a lab that appends a live turn writes here (T386)
        cls.deep_uuid = "11111111-2222-3333-4444-%012d" % 20   # the eleventh question: far above the tail the page holds
        cls.deep_t = base + 20                                     # …and its time, as a card's focus frame carries it
        cls.tool_uuid = "44444444-5555-6666-7777-%012d" % (10 * TOOL_TURN)   # the tool turn's FIRST atom: a card's anchor (T386)
        cls.tool_t = base + 2 * TOOL_TURN + 1
        cls.tool_quote = "which bound do we keep for the retry curve"
        cls.base = base
        cls.port = _free_port()
        cls.token = "testtok-livepaused"
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
            cls._skip("hermetic kernel never served /healthz here")

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "kernel", None):
            cls.kernel.kill()
            cls.kernel.wait()
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

    def _drive(self, script, name, extra=None):
        cfg = os.path.join(self.lab, name + ".json")
        with open(cfg, "w") as f:
            json.dump({"chat": "http://127.0.0.1:%d/chat?token=%s" % (self.port, self.token), "sid": SID,
                       "deepUuid": self.deep_uuid, "deepT": self.deep_t, "base": self.base, "transcript": self.transcript,
                       "toolUuid": self.tool_uuid, "toolT": self.tool_t, "toolQuote": self.tool_quote,
                       "shots": os.environ.get("LIVE_PAUSED_SHOTS", ""), **(extra or {})}, f)
        driver = os.path.join(self.lab, name + ".mjs")
        with open(driver, "w") as f:
            f.write(script)
        p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=240,
                           env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
        if p.returncode == 3:
            if os.environ.get("ROMP_SERVED_TESTS_REQUIRE") == "1":
                raise AssertionError("ROMP_SERVED_TESTS_REQUIRE=1 but no playwright browser to run the served lab")
            raise unittest.SkipTest("no playwright browser on this box — the served guard needs one (CI installs none)")
        klog = ""
        try:
            with open(self.klog) as f:
                klog = f.read()[-2500:]
        except OSError:
            pass
        self.assertEqual(p.returncode, 0, "driver failed:\n" + p.stdout[-3000:] + p.stderr[-3000:] + "\nkernel:\n" + klog)
        line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
        self.assertIsNotNone(line, "driver printed no result:\n" + p.stdout[-3000:])
        r = json.loads(line[len("RESULT:"):])
        if isinstance(r, dict):
            r["_klog"] = klog[-1500:]   # the kernel's own words for the run, beside the measure (a passing run's log is otherwise lost with the lab dir)
        return r


if __name__ == "__main__":
    unittest.main()
