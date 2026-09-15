#!/usr/bin/env python3
"""The chat's fork control carries a FORK glyph beside its word (T381; the user 2026-09-12: a horizontal line from
the left that branches into two lines which continue to the right), in the stroke family the other glyphs use
(icons.ts ICON_FORK), with Fork in the title and the accessible name.

This lab drives the real /chat page of a hermetic kernel with synthetic sessions (the notes-api demo world, host
TESTHOST, placeholder sids), hovers the LAST assistant bubble of the active session (the fork spot rides it,
revealed on hover) and reads the control: an inline SVG with the two branch polylines, the word fork beside it, the
aria-label Fork, and the hover opacity. FORK_GLYPH_DIST=<dir> serves another tree's UI bundle (the red run's
before); FORK_GLYPH_SHOTS=<prefix> writes <prefix>-dark.png and <prefix>-light.png of the control under its bubble.
Skips LOUDLY without the extension deps or a Playwright browser, and never otherwise (CI turns a skip in a served
module into a failure). SYNTHETIC fixtures only."""
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
import test_ship_reship_served as _lab   # noqa: E402  the lab kernel's environment: a list of names, never a copy of the runner's

# the notes-api demo world: twenty sessions, enough to wrap the strip onto several rows at a narrow width
NAMES = ["web", "api", "deploy", "tests", "docs", "auth", "search", "cache", "ingest", "export", "billing", "mailer",
         "worker", "scheduler", "metrics", "backup", "importer", "notifier", "gateway", "indexer"]
SIDS = {n: "%s-1111-2222-3333-444444444444" % (chr(ord("a") + i) * 8) for i, n in enumerate(NAMES)}
PALETTE = [("#9cd2ff", "#0c1a2e"), ("#1EA1EB", "#ffffff"), ("#54B204", "#ffffff"), ("#c98cff", "#1a0c2e"),
           ("#e5a50a", "#1a1200"), ("#4EC9B0", "#00201a")]


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
const page = await browser.newPage({ viewport: { width: 1000, height: 700 } });
await page.goto(cfg.chat);
await page.waitForSelector("#tabs .tab[data-id]", { timeout: 30000 });
await page.waitForSelector("#content .turn-assistant .fork-spot .msg-fork", { timeout: 30000 });   // the tip run's spot
await page.waitForTimeout(300);
const measure = (label) => page.evaluate((label) => {
  const b = document.querySelector("#content .turn-assistant .fork-spot .msg-fork");
  if (!b) return { label, missing: true };
  const cs = getComputedStyle(b);
  const svg = b.querySelector("svg");
  return { label, svg: !!svg, paths: svg ? Array.from(svg.querySelectorAll("*")).map((n) => n.outerHTML).join("") : "",
    word: (b.querySelector(".msg-fork-word") || {}).textContent || "", text: b.textContent.trim(), aria: b.getAttribute("aria-label"),
    title: b.title, opacity: cs.opacity, color: cs.color, display: cs.display, svgW: svg ? svg.getBoundingClientRect().width : 0 };
}, label);
const out = { themes: {} };
for (const theme of ["dark", "light"]) {
  await page.evaluate((t) => document.body.classList.toggle("theme-light", t === "light"), theme);
  await page.waitForTimeout(150);
  const turn = await page.$("#content .turn-assistant:has(.fork-spot)");
  const box = await turn.boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + Math.min(box.height / 2, 40));
  await page.waitForFunction(() => { const b = document.querySelector("#content .fork-spot .msg-fork"); return !!b && parseFloat(getComputedStyle(b).opacity) > 0.5; }, null, { timeout: 5000 });
  await page.waitForTimeout(100);
  out.themes[theme] = await measure(theme);
  if (cfg.shots) {
    const bb = await (await page.$("#content .fork-spot .msg-fork")).boundingBox();
    await page.screenshot({ path: cfg.shots + "-" + theme + ".png", clip: { x: Math.max(0, bb.x - 260), y: Math.max(0, bb.y - 60), width: 460, height: 100 } });
  }
  await page.mouse.move(5, 690); await page.waitForTimeout(100);
}
await page.evaluate(() => document.body.classList.remove("theme-light"));
fs.writeFileSync(cfg.out, JSON.stringify(out));
await browser.close();
console.log("RESULT: ok");
"""


class ServedForkGlyph(unittest.TestCase):
    maxDiff = None
    result = None

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
            raise unittest.SkipTest("extension deps absent (npm ci not run here) — the served guard needs them")
        probe = subprocess.run(["node", "-e", "const p=require(process.argv[1]);process.stdout.write(p.chromium.executablePath())",
                                os.path.join(EXT, "node_modules", "playwright")], capture_output=True, text=True)
        if probe.returncode != 0 or not os.path.exists(probe.stdout.strip()):
            raise unittest.SkipTest("no playwright browser on this box — the served guard needs one (CI installs none)")
        cls.lab = tempfile.mkdtemp(prefix="fork-glyph-")
        before = os.environ.get("FORK_GLYPH_DIST", "")
        if before:
            src = before
        else:
            b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
            if b.returncode != 0:
                raise unittest.SkipTest("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
            src = os.path.join(EXT, "dist")
        dist = os.path.join(cls.lab, "dist")
        copy_dist(src, dist)
        state = os.path.join(cls.lab, "xdg", "romp")
        claude = os.path.join(cls.lab, "claude")
        cwd = os.path.join(cls.lab, "proj")
        for d in ("names", "sdk", "states"):
            os.makedirs(os.path.join(state, d), exist_ok=True)
        # a lab root writes its own session-hosts off (the conftest rule): hosts are on by default, and a kernel-side boot
        # attach for twenty alive sessions would otherwise spawn twenty real session hosts on a developer's machine
        Path(state, "session-hosts").write_text("off\n")
        os.makedirs(cwd, exist_ok=True)
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        t0 = int(time.time()) - 900
        for i, name in enumerate(NAMES):
            sid = SIDS[name]
            bg, fg = PALETTE[i % len(PALETTE)]
            Path(state, "names", sid).write_text("%s\t%s\t%s\t%s\n" % (name, cwd, bg, fg))
            Path(state, "sdk", sid + ".json").write_text(json.dumps(
                {"sid": sid, "name": name, "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": sid, "alive": True,
                 "model": "claude-opus-5", "liveModel": "Opus 5"}))
            recs = [{"type": "user", "timestamp": iso(t0 + i), "uuid": "u1", "parentUuid": None, "promptSource": "typed", "sessionId": sid,
                     "message": {"role": "user", "content": "what does the %s session do in notes-api?" % name}},
                    {"type": "assistant", "timestamp": iso(t0 + i + 5), "uuid": "a1", "parentUuid": "u1", "sessionId": sid,
                     "message": {"role": "assistant", "model": "claude-opus-5", "stop_reason": "end_turn",
                                 "content": [{"type": "text", "text": "It keeps the %s side of the notes-api tidy." % name}]}}]
            Path(proj, sid + ".jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
        Path(state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 10}, "seven_day": {"pct": 10}}))
        cls.port, cls.token = _free_port(), "testtok-forkglyph"
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
    def tearDownClass(cls):
        k = getattr(cls, "kernel", None)
        if k:
            k.kill(); k.wait()
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

    @classmethod
    def _run(cls):
        if cls.result is not None:
            if isinstance(cls.result, BaseException):
                raise cls.result
            return cls.result
        try:
            cls.result = cls._drive()
        except BaseException as e:
            cls.result = e
            raise
        return cls.result

    @classmethod
    def _drive(cls):
        cfg = os.path.join(cls.lab, "cfg.json")
        out = os.path.join(cls.lab, "result.json")
        with open(cfg, "w") as f:
            json.dump({"chat": "http://127.0.0.1:%d/chat?token=%s" % (cls.port, cls.token), "count": len(NAMES), "out": out,
                       "shots": os.environ.get("FORK_GLYPH_SHOTS", "")}, f)
        driver = os.path.join(cls.lab, "driver.mjs")
        with open(driver, "w") as f:
            f.write(DRIVER)
        p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=240,
                           env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
        if p.returncode == 3:
            raise unittest.SkipTest("no playwright browser on this box — the served guard needs one (CI installs none)")
        if p.returncode != 0:
            raise AssertionError("driver failed:\n" + p.stdout[-3000:] + p.stderr[-3000:] + "\nkernel:\n" + open(cls.klog).read()[-1500:])
        if not os.path.exists(out):
            raise AssertionError("driver printed no result:\n" + p.stdout[-3000:])
        return json.loads(Path(out).read_text())

    def _theme(self, theme):
        m = self._run()["themes"][theme]
        self.assertFalse(m.get("missing"), "the fork control is under the last assistant bubble: " + json.dumps(m))
        return m

    def _assert_glyph(self, m):
        table = "\n  " + json.dumps(m)[:900]
        self.assertTrue(m["svg"], "a glyph on the control" + table)
        self.assertIn('points="2 12 9 12 15 7 22 7"', m["paths"], "the trunk from the left and the upper branch to the right edge" + table)
        self.assertIn('points="9 12 15 17 22 17"', m["paths"], "the lower branch to the right edge" + table)
        self.assertNotIn("marker", m["paths"], "no arrowheads" + table)
        self.assertEqual(m["word"], "fork", "the word stays beside the glyph" + table)
        self.assertEqual(m["aria"], "Fork", "Fork in the accessible name" + table)
        self.assertIn("Fork the session", m["title"], table)
        self.assertGreater(float(m["opacity"]), 0.5, "revealed by hovering the response" + table)
        self.assertGreater(m["svgW"], 8, "the glyph is drawn at size" + table)

    def test_dark_theme_the_fork_control_carries_the_glyph_beside_its_word(self):
        self._assert_glyph(self._theme("dark"))

    def test_light_theme_the_fork_control_carries_the_glyph_beside_its_word(self):
        self._assert_glyph(self._theme("light"))


if __name__ == "__main__":
    unittest.main()
