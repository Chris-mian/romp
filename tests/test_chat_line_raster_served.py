#!/usr/bin/env python3
"""Chat message body text keeps a whole-device-pixel vertical rhythm (the user 2026-09-17, from a screen recording: on a
2x display some lines of an assistant message rendered blurred and doubled, a ghost copy a pixel below, while neighbours
were crisp, and a pinch-zoom re-raster cleared it: a rasterisation misalignment, not the text).

MEASURED, not assumed (Chromium at deviceScaleFactor 2 over a hermetic /chat with a long multi-paragraph assistant
message, Range.getClientRects over each paragraph's text): the chat body's line-height was the unitless 1.6, which is
20.8px at the 13px font = 41.6 device px at 2x, so consecutive line boxes step by a fractional number of device rows and
alternate lines straddle two rows (the doubling); .md p's 0.5em (6.5px) margin was a second, 1x-only term (alternate
paragraphs on a half css px). No transform, no fractional virtual-history offset. The fix scopes a whole-css-px
line-height and paragraph margin to the message body: .md { line-height: round(1.6em, 1px) } (21px at 13px) and
.md p { margin: round(0.5em, 1px) 0 }, so every step between consecutive line boxes is a whole device pixel at 1x and 2x.

This lab asserts the STEP (the rhythm on the grid), which the fix holds, not the absolute top. QUEUED LOW (measured
here, not this round, the manager's call 2026-09-17): a uniform base offset remains because the tab strip AND the turn
structure above the message also inherit the body's unitless 1.6, so #content itself starts on a fractional pixel
(measured #content top 38.125px, tab strip height 38.125px at 13px) and every message line inherits that ~0.25 device px
offset equally. A uniform quarter-pixel softens every line the same and reads as nothing (the defect is the alternating
straddle, now gone); making the base whole needs a whole-pixel tab-strip/turn-structure height, a separate change to
non-message chrome. See [[queued-lows-by-worker]].

One hermetic kernel, one seeded session whose tail is a fixed four-paragraph markdown message (synthetic invented prose;
placeholder uuid, hostname TESTHOST, no real data). Synthetic only."""
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
import urllib.request
from pathlib import Path

from tests.dist_copy import copy_dist

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
EXT = os.path.join(ROOT, "vscode-extension")
sys.path.insert(0, HERE)
import test_ship_reship_served as _lab                      # noqa: E402

os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)
_ST0 = Path(os.environ["XDG_STATE_HOME"]) / "romp"
_ST0.mkdir(parents=True, exist_ok=True)
(_ST0 / "session-hosts").write_text("off\n")

SID = "eeee1111-2222-4333-8444-000000000c01"
COLOR = ("#64b5f6", "#0c1a2e")

# A fixed, invented four-paragraph body: each paragraph wraps to several lines at the pane width, so many line boxes are
# measured. No real prompt or transcript text.
PARAS = [
    "The scheduler hands each lane a budget and a deadline, and the lane spends the budget however it likes so long as "
    "the deadline holds; when two lanes want the same slot the older claim wins, and the younger one waits a tick and "
    "asks again rather than forcing a preemption that would strand a half-written frame in the pipe.",
    "A frame carries its own provenance so a reader can tell a fresh push from a re-emission without consulting the "
    "clock, which lies across a restart; the marker rides the tail of the frame, not its head, so a truncated read "
    "still names the lane it came from and a partial frame is dropped whole rather than misattributed to a neighbour.",
    "Backpressure is a count, never a sleep: a lane that outruns its reader parks the surplus in a ring sized to a "
    "second of slack and drops the oldest when the ring is full, and the reader learns the drop from a gap in the "
    "sequence numbers rather than a flag, so a slow consumer degrades to lower resolution instead of blocking a writer.",
    "The whole arrangement survives a cold boot because every durable fact is a file and every derived fact is a memo "
    "keyed on the files it read; a boot that finds a memo whose inputs are unchanged skips the work, and one whose "
    "inputs moved rebuilds behind the memo, so the first pass after a deploy is fast without ever trusting a stale sum.",
]


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def _transcript(t0):
    def iso(t):
        return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t))
    recs, parent, t = [], None, t0
    for k in range(2):
        u, a = "u%d" % k, "a%d" % k
        recs.append({"type": "user", "uuid": u, "parentUuid": parent, "timestamp": iso(t), "promptSource": "typed",
                     "cwd": "/w/notes-api", "message": {"role": "user", "content": "question %d about the lane scheduler" % k}})
        text = ("Here is turn %d. " % k) + ("\n\n".join(PARAS) if k == 1 else "A short first reply before the long one.")
        recs.append({"type": "assistant", "uuid": a, "parentUuid": u, "timestamp": iso(t + 20), "cwd": "/w/notes-api",
                     "message": {"role": "assistant", "content": [{"type": "text", "text": text}], "stop_reason": "end_turn"}})
        parent = a; t += 60
    return recs


DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));   // {url}
let browser;
try { browser = await chromium.launch(cfg.launch || {}); }
catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
const out = { died: null };
// measure the LAST assistant turn's markdown line boxes at a given deviceScaleFactor
const measureAt = async (dsf) => {
  const context = await browser.newContext({ deviceScaleFactor: dsf, viewport: { width: 1000, height: 820 } });
  const page = await context.newPage();
  page.on("pageerror", () => {});
  try {
    await page.goto(cfg.url);
    let probe = null;
    try { await page.waitForFunction(() => document.querySelectorAll("#content .turn[data-uuid]").length >= 1, null, { timeout: 40000 }); }
    catch (e) { probe = "no .turn[data-uuid] rendered in 40s"; }
    await page.waitForTimeout(500);   // let markdown + fonts settle so line boxes are final
    const m = await page.evaluate(() => {
      const turns = Array.from(document.querySelectorAll("#content .turn-assistant, #content .turn.turn-assistant"));
      const md = turns.map((t) => t.querySelector(".md")).filter(Boolean).pop() || Array.from(document.querySelectorAll("#content .md")).pop();
      if (!md) return { missing: true };
      const ps = Array.from(md.querySelectorAll("p"));
      if (ps.length < 4) return { missing: true, pCount: ps.length };
      const cs = getComputedStyle(ps[0]);
      const round3 = (x) => Math.round(x * 1000) / 1000;
      // a Range over each paragraph's contents yields one client rect per rendered line; the tops in document order
      const lineTops = [];
      ps.forEach((p) => {
        const r = document.createRange(); r.selectNodeContents(p);
        Array.from(r.getClientRects()).forEach((rc) => { if (rc.height > 2) lineTops.push(round3(rc.top)); });
      });
      const c = document.getElementById("content");
      return { fontSize: cs.fontSize, lineHeight: cs.lineHeight, lineTops,
               contentTop: c ? round3(c.getBoundingClientRect().top) : null };   // base offset: the queued low's evidence, not asserted
    });
    return probe && (m.missing) ? { probe, m } : m;
  } finally { await context.close(); }
};
try {
  out.dsf2 = await measureAt(2);
  out.dsf1 = await measureAt(1);
} catch (e) { out.died = String(e).slice(0, 500); }
process.stdout.write("RESULT:" + JSON.stringify(out) + "\n");
await browser.close();
"""


class ChatLineRaster(unittest.TestCase):
    maxDiff = None
    _cache = None

    @classmethod
    def setUpClass(cls):
        try:
            cls._boot()
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def _boot(cls):
        if not os.path.isdir(os.path.join(EXT, "node_modules", "playwright")):
            raise unittest.SkipTest("extension deps absent")
        probe = subprocess.run(["node", "-e", "const p=require(process.argv[1]);process.stdout.write(p.chromium.executablePath())",
                                os.path.join(EXT, "node_modules", "playwright")], capture_output=True, text=True)
        if probe.returncode != 0 or not os.path.exists(probe.stdout.strip()):
            raise unittest.SkipTest("no playwright browser")
        cls.lab = tempfile.mkdtemp(prefix="chat-raster-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            raise unittest.SkipTest("esbuild failed: " + (b.stderr or b.stdout)[-200:])
        copy_dist(os.path.join(EXT, "dist"), os.path.join(cls.lab, "dist"))
        sub = os.path.join(cls.lab, "solo")
        state = os.path.join(sub, "xdg", "romp")
        claude = os.path.join(sub, "claude")
        cwd = os.path.join(sub, "proj")
        for d in ("names", "sdk", "states", "checkpoints"):
            os.makedirs(os.path.join(state, d), exist_ok=True)
        os.makedirs(cwd, exist_ok=True)
        Path(state, "session-hosts").write_text("off\n")
        Path(state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 10}, "seven_day": {"pct": 10}}))
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        now = int(time.time())
        Path(state, "names", SID).write_text("%s\t%s\t%s\t%s\n" % ("api", cwd, COLOR[0], COLOR[1]))
        Path(state, "sdk", SID + ".json").write_text(json.dumps(
            {"sid": SID, "name": "api", "cwd": cwd, "mode": "auto", "effort": "high",
             "lastSid": SID, "alive": True, "model": "claude-opus-5", "liveModel": "Opus 5"}))
        Path(proj, SID + ".jsonl").write_text("".join(json.dumps(r) + "\n" for r in _transcript(now - 3600)))
        cls.port, cls.token = _free_port(), "testtok-raster"
        env = _lab.kernel_env(sub, claude, os.path.join(cls.lab, "dist"), cls.port, cls.token)
        cls.klog = os.path.join(cls.lab, "kernel.log")
        cls.kernel = subprocess.Popen([os.path.join(BIN, "romp-kernel")], stdout=open(cls.klog, "w"), stderr=subprocess.STDOUT, env=env)
        cls.procs = [cls.kernel]
        for _ in range(120):
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/healthz" % cls.port, timeout=1); break
            except Exception:
                time.sleep(0.5)
        else:
            cls.kernel.kill(); raise unittest.SkipTest("kernel never served /healthz")

    @classmethod
    def tearDownClass(cls):
        for p in getattr(cls, "procs", []):
            try:
                p.kill(); p.wait()
            except Exception:
                pass
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

    def _result(self):
        if type(self)._cache is None:
            cfg = os.path.join(self.lab, "cfg.json")
            with open(cfg, "w") as f:
                json.dump({"url": "http://127.0.0.1:%d/chat?token=%s" % (self.port, self.token)}, f)
            driver = os.path.join(self.lab, "driver.mjs")
            Path(driver).write_text(DRIVER)
            p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=300,
                               env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
            if "browser-launch-failed" in p.stderr:
                raise unittest.SkipTest("no playwright browser")
            line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
            self.assertIsNotNone(line, "no RESULT (stderr: %s)" % p.stderr[-1500:])
            type(self)._cache = json.loads(line[len("RESULT:"):])
        r = type(self)._cache
        self.assertIsNone(r.get("died"), "driver error: %s" % r.get("died"))
        return r

    def _steps(self, dsf_key):
        d = self._result().get(dsf_key) or {}
        self.assertFalse(d.get("missing"), "the long multi-paragraph assistant message rendered: %r" % d)
        tops = d.get("lineTops") or []
        self.assertGreaterEqual(len(tops), 8, "several line boxes were measured: %r" % tops)
        return d, [round(tops[i + 1] - tops[i], 3) for i in range(len(tops) - 1)]

    def _offenders(self, steps, dsf):
        # a step is a whole number of device px when step * dsf is an integer (tolerance 0.02 device px for sub-pixel noise)
        out = []
        for s in steps:
            dev = s * dsf
            if min(dev % 1.0, 1.0 - (dev % 1.0)) > 0.02:
                out.append((s, round(dev, 3)))
        return out

    def test_the_line_box_step_is_a_whole_device_pixel_at_2x(self):
        d, steps = self._steps("dsf2")
        offenders = self._offenders(steps, 2)
        self.assertEqual(offenders, [],
                         "every step between consecutive message line boxes is a whole device px at 2x (line-height %s); "
                         "offenders (css step, device step): %r" % (d.get("lineHeight"), offenders))

    def test_the_line_box_step_is_a_whole_device_pixel_at_1x(self):
        d, steps = self._steps("dsf1")
        offenders = self._offenders(steps, 1)
        self.assertEqual(offenders, [],
                         "every step between consecutive message line boxes is a whole device px at 1x (line-height %s); "
                         "offenders (css step, device step): %r" % (d.get("lineHeight"), offenders))
