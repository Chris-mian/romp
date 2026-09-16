"""The chat status line's stop button sits beside the state chip, after its timer, in one non-wrapping unit (the user
2026-09-16: back where it sat from 2026-06-19 until bd9a1dab moved it to the right cluster so a wrapped narrow line
kept it with the controls). Served, in a browser, at two pane widths: wide (1440) the unit leads the line and the right
cluster sits on the same row to its right; narrow (420) the right cluster wraps below the unit as a whole, and the
button stays on the chip's row, adjacent to the timer. The session is left mid-turn (a typed prompt, no reply) so its
chip reads Working and the button shows. Hermetic: a temp state root, one synthetic session in the notes-api demo
world, the lab kernel of test_ship_reship_served."""
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
from datetime import datetime, timezone
from pathlib import Path

from tests.dist_copy import copy_dist

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
EXT = os.path.join(ROOT, "vscode-extension")
sys.path.insert(0, HERE)
import test_ship_reship_served as _lab   # noqa: E402  the lab kernel's environment

SID = "aaaaaaaa-1111-2222-3333-444444444444"   # web, the notes-api demo world
WIDTHS = {"wide": 1440, "narrow": 420}


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));
let browser;
try { browser = await chromium.launch(); }
catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
const out = {};
// the geometry of the line's parts, read wherever they stand, so the same read at a base that mounts the button in
// the right cluster measures that placement and the assertions say so
const readLine = (chatF) => chatF.evaluate(() => {
  const sl = document.getElementById("statusline");
  const rect = (n) => { if (!n) return null; const b = n.getBoundingClientRect(); return { top: b.top, bottom: b.bottom, left: b.left, right: b.right, cy: (b.top + b.bottom) / 2 }; };
  const left = sl.querySelector(".sl-left"), right = sl.querySelector(".sl-right"), stop = sl.querySelector(".stop-btn");
  return { chip: rect(sl.querySelector(".chip")), timer: rect(document.getElementById("work-timer")), stop: rect(stop),
           stopParent: stop ? stop.parentElement.className : null,
           leftKids: left ? Array.from(left.children).map((n) => n.className) : null,
           right: rect(right), rightKids: right ? Array.from(right.children).map((n) => rect(n)) : null,
           line: rect(sl), width: window.innerWidth, chipCls: (sl.querySelector(".chip") || {}).className || null };
});
for (const [name, width] of Object.entries(cfg.widths)) {
  const ctx = await browser.newContext({ viewport: { width, height: 800 } });
  const page = await ctx.newPage();
  await page.goto(cfg.url);
  await page.waitForSelector("#rail-gear", { state: "attached", timeout: 20000 });   // attached, not visible: the narrow rail hides the gear
  let chatF = page.frames().find((f) => f.url().includes("/chat"));
  for (let i = 0; i < 100 && !chatF; i++) { await page.waitForTimeout(100); chatF = page.frames().find((f) => f.url().includes("/chat")); }
  if (!chatF) { console.error("no chat frame"); process.exit(1); }
  await chatF.waitForFunction(() => document.querySelectorAll("#tabs .tab[data-id]").length >= 1, null, { timeout: 30000 });
  await chatF.click('#tabs .tab[data-id="' + cfg.sid + '"]');
  await chatF.waitForSelector("#statusline .sl-right #spinner-meta", { state: "attached", timeout: 20000 });
  await chatF.waitForSelector("#statusline .stop-btn", { state: "attached", timeout: 20000 });   // the chip reads Working: the button shows
  await chatF.evaluate(() => (document.fonts && document.fonts.ready) || null).catch(() => {});
  await chatF.waitForTimeout(400);
  out[name] = await readLine(chatF);
  await ctx.close();
}
fs.writeFileSync(cfg.out, JSON.stringify(out));
await browser.close();
process.exit(0);
"""


class ServedStopButtonBesideTheChip(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        try:
            cls._boot()
            cls._run()
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def _boot(cls):
        if not os.path.isdir(os.path.join(EXT, "node_modules", "playwright")):
            raise unittest.SkipTest("extension deps absent (npm ci not run here): the served guard needs them")
        probe = subprocess.run(["node", "-e", "const p=require(process.argv[1]);process.stdout.write(p.chromium.executablePath())",
                                os.path.join(EXT, "node_modules", "playwright")], capture_output=True, text=True)
        if probe.returncode != 0 or not os.path.exists(probe.stdout.strip()):
            raise unittest.SkipTest("no playwright browser on this box: the served guard needs one (CI installs none)")
        cls.lab = tempfile.mkdtemp(prefix="statusline-stop-left-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            raise unittest.SkipTest("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
        dist = os.path.join(cls.lab, "dist")
        copy_dist(os.path.join(EXT, "dist"), dist)
        state = os.path.join(cls.lab, "xdg", "romp")
        claude = os.path.join(cls.lab, "claude")
        cwd = os.path.join(cls.lab, "notes-api")
        for d in ("names", "sdk", "states"):
            os.makedirs(os.path.join(state, d), exist_ok=True)
        Path(state, "session-hosts").write_text("off\n")   # a lab root writes its own session-hosts off (the conftest rule)
        os.makedirs(cwd, exist_ok=True)
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        Path(state, "names", SID).write_text("web\t%s\t#1EA1EB\t#ffffff\n" % cwd)
        Path(state, "sdk", SID + ".json").write_text(json.dumps(
            {"sid": SID, "name": "web", "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": SID, "alive": True,
             "model": "claude-opus-5", "liveModel": "Opus 5", "liveCtx": 62}))
        # a typed prompt with no reply yet: the turn is open, so the chip reads Working with its timer and the stop button
        recs = [{"type": "user", "timestamp": iso(int(time.time()) - 60), "uuid": "u1", "parentUuid": None, "promptSource": "typed",
                 "sessionId": SID, "cwd": cwd, "gitBranch": "search-module",
                 "message": {"role": "user", "content": "tidy the search module's tests in notes-api"}}]
        Path(proj, SID + ".jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
        Path(state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 10}, "seven_day": {"pct": 10}}))
        cls.port, cls.token = _free_port(), "testtok-stopleft"
        env = _lab.kernel_env(cls.lab, claude, dist, cls.port, cls.token, ROMP_HOST_NAME="TESTHOST")
        cls.klog = os.path.join(cls.lab, "kernel.log")
        cls.kernel = subprocess.Popen([os.path.join(BIN, "romp-kernel")], stdout=open(cls.klog, "w"), stderr=subprocess.STDOUT, env=env)
        for _ in range(120):
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/healthz" % cls.port, timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        else:
            raise unittest.SkipTest("hermetic kernel never served /healthz here")

    @classmethod
    def _run(cls):
        cfg = os.path.join(cls.lab, "cfg.json")
        outp = os.path.join(cls.lab, "out.json")
        with open(cfg, "w") as f:
            json.dump({"url": "http://127.0.0.1:%d/?token=%s" % (cls.port, cls.token), "out": outp, "sid": SID, "widths": WIDTHS}, f)
        driver = os.path.join(cls.lab, "driver.mjs")
        with open(driver, "w") as f:
            f.write(DRIVER)
        p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=420,
                           env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
        if p.returncode == 3:
            raise unittest.SkipTest("no playwright browser on this box: the served guard needs one")
        if p.returncode != 0:
            raise AssertionError("driver failed:\n" + p.stdout[-3000:] + p.stderr[-3000:] + "\nkernel:\n" + open(cls.klog).read()[-1500:])
        cls.out = json.load(open(outp))

    @classmethod
    def tearDownClass(cls):
        k = getattr(cls, "kernel", None)
        if k:
            k.kill(); k.wait()
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

    def _unit(self, name):
        """The button is on the chip's row, right after the timer, inside the left unit, at this width."""
        o = self.out[name]
        self.assertIn("chip-working", o["chipCls"] or "", "the seeded open turn reads Working (else no button to place)")
        self.assertTrue(o["stop"] and o["timer"] and o["chip"], "chip, timer and stop button all on the line")
        self.assertEqual(o["stopParent"], "sl-left", "the button rides the left unit, not the right cluster")
        self.assertEqual([k.split(" ")[0] for k in o["leftKids"]], ["chip", "status-timer", "stop-btn"], "chip, then its timer, then the button")
        self.assertLess(abs(o["stop"]["cy"] - o["chip"]["cy"]), 4, "the button sits on the chip's row")
        gap = o["stop"]["left"] - o["timer"]["right"]
        self.assertTrue(-1 <= gap <= 16, "adjacent to the timer (gap %.1f px)" % gap)

    def test_wide_the_unit_leads_the_line_and_the_right_cluster_shares_its_row(self):
        self._unit("wide")
        o = self.out["wide"]
        self.assertLess(abs(o["right"]["cy"] - o["chip"]["cy"]), 6, "one row at 1440")
        self.assertGreater(o["right"]["left"], o["stop"]["right"], "the right cluster stands to the right of the unit")

    def test_narrow_the_right_cluster_wraps_below_the_unit_whole_and_the_button_stays_with_its_badge(self):
        self._unit("narrow")
        o = self.out["narrow"]
        self.assertEqual(o["width"], 420)
        self.assertGreaterEqual(o["right"]["top"], o["stop"]["bottom"] - 2, "the right cluster begins below the unit")
        for k in o["rightKids"]:
            self.assertGreaterEqual(k["top"], o["stop"]["bottom"] - 2, "no control of the right cluster shares the chip's row")


if __name__ == "__main__":
    unittest.main()
