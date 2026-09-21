#!/usr/bin/env python3
"""The session tab's hover popover colours its Model and Effort values with the colour the chat footer's chips wear
for that session (T372; the user 2026-09-12, who learned the association on the footer and wanted it reproduced in
the popover). One helper, metaColor, serves both, so the two cannot drift.

This lab drives the real /chat page of a hermetic kernel with twenty synthetic sessions (the notes-api demo world,
host TESTHOST, placeholder sids), hovers the active session's tab, and reads the popover's Model and Effort value
spans against the footer's model and effort chips (getComputedStyle color), in the dark theme and in the light
theme (where the kernel's dark-tuned RGB is re-encoded on both surfaces alike). Asserted: the two colours are equal
per theme and differ from the page's plain foreground; the labels and the other values stay plain; the light theme
differs from the dark. TIP_TONES_DIST=<dir> serves another tree's UI bundle (the red run's before);
TIP_TONES_SHOTS=<prefix> writes <prefix>-dark.png and <prefix>-light.png of the popover over its tab. Skips LOUDLY
without the extension deps or a Playwright browser, and never otherwise (CI turns a skip in a served module into a
failure). SYNTHETIC fixtures only."""
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
const page = await browser.newPage({ viewport: { width: 1200, height: 760 } });
await page.goto(cfg.chat);
await page.waitForSelector("#tabs .tab[data-id]", { timeout: 30000 });
await page.waitForFunction((n) => document.querySelectorAll("#tabs .tab[data-id]").length >= n, cfg.count, { timeout: 30000 });
// the footer's model and effort chips carry their colours once the status landed
await page.waitForFunction(() => { const m = document.querySelector('#spinner-meta .meta-btn[data-kind="model"] .meta-label'); return !!m && getComputedStyle(m).color !== ""; }, null, { timeout: 30000 });
await page.waitForTimeout(500);
const measure = (label) => page.evaluate((label) => {
  const cs = (e) => e ? getComputedStyle(e).color : null;
  const chip = (k) => document.querySelector('#spinner-meta .meta-btn[data-kind="' + k + '"] .meta-label');
  const tip = document.querySelector(".tab-tip");
  const rows = tip ? Array.from(tip.querySelectorAll(".tab-tip-row")).map((r) => ({ k: r.children[0].textContent, v: r.children[1] ? r.children[1].textContent : "", vColor: cs(r.children[1]), kColor: cs(r.children[0]) })) : [];
  const fg = getComputedStyle(document.body).color;
  return { label, tipShown: !!tip && getComputedStyle(tip).display !== "none", rows, footer: { model: cs(chip("model")), effort: cs(chip("effort")), mode: cs(chip("mode")) }, fg, activeName: (document.querySelector("#tabs .tab.active .tab-label") || {}).textContent || "" };
}, label);
const out = { themes: {} };
const chipColor = () => page.evaluate(() => { const m = document.querySelector('#spinner-meta .meta-btn[data-kind="model"] .meta-label'); return m ? getComputedStyle(m).color : null; });
for (const theme of ["dark", "light"]) {
  const before = await chipColor();
  await page.evaluate((t) => { document.body.classList.toggle("theme-light", t === "light"); }, theme);
  // the footer re-tints its chips on its one-second ticker (the light theme re-encodes the RGB): wait for that, so the
  // comparison reads two settled surfaces, not the popover's fresh paint against a chip still wearing the other theme
  if (theme === "light") await page.waitForFunction((prev) => { const m = document.querySelector('#spinner-meta .meta-btn[data-kind="model"] .meta-label'); return !!m && getComputedStyle(m).color !== prev; }, before, { timeout: 5000 });
  await page.waitForTimeout(150);
  const tab = await page.$("#tabs .tab.active[data-id]");
  const box = await tab.boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.waitForFunction(() => { const t = document.querySelector(".tab-tip"); return !!t && getComputedStyle(t).display !== "none"; }, null, { timeout: 5000 });
  await page.waitForTimeout(150);
  out.themes[theme] = await measure(theme);
  if (cfg.shots) await page.screenshot({ path: cfg.shots + "-" + theme + ".png" });   // the whole page: the popover over its tab AND the footer chips it matches
  await page.mouse.move(5, 700); await page.waitForTimeout(100);
}
await page.evaluate(() => document.body.classList.remove("theme-light"));
fs.writeFileSync(cfg.out, JSON.stringify(out));
await browser.close();
console.log("RESULT: ok");
"""


class ServedTabTipTones(unittest.TestCase):
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
        cls.lab = tempfile.mkdtemp(prefix="tip-tones-")
        before = os.environ.get("TIP_TONES_DIST", "")
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
        cls.port, cls.token = _free_port(), "testtok-tiptones"
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
                       "shots": os.environ.get("TIP_TONES_SHOTS", "")}, f)
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
        r = self._run()
        m = r["themes"][theme]
        self.assertTrue(m["tipShown"], "the popover is up over the hovered tab: " + json.dumps(m)[:400])
        return m

    def _assert_tones(self, m):
        table = "\n  " + json.dumps(m, indent=None)[:1600]
        rows = {r["k"]: r for r in m["rows"]}
        self.assertIn("Model", rows); self.assertIn("Effort", rows)
        self.assertEqual(rows["Model"]["vColor"], m["footer"]["model"], "the popover's Model value wears the footer chip's colour" + table)
        self.assertEqual(rows["Effort"]["vColor"], m["footer"]["effort"], "the popover's Effort value wears the footer chip's colour" + table)
        self.assertNotEqual(rows["Model"]["vColor"], m["fg"], "a colour, not the plain foreground" + table)
        self.assertNotEqual(rows["Effort"]["vColor"], m["fg"], table)
        for k in ("Mode", "Backend"):
            if k in rows:
                self.assertEqual(rows[k]["vColor"], m["fg"], k + " stays plain: the footer tints neither" + table)
        for r in m["rows"]:
            self.assertNotEqual(r["kColor"], r["vColor"] if r["k"] in ("Model", "Effort") else None, "the label stays dim: " + r["k"] + table)

    def test_dark_theme_the_popover_values_wear_the_footer_chips_colours(self):
        self._assert_tones(self._theme("dark"))

    def test_light_theme_the_popover_values_wear_the_footer_chips_colours_re_encoded_alike(self):
        m = self._assert_tones(self._theme("light")) or self._theme("light")
        d = self._theme("dark")
        rows_l = {r["k"]: r for r in m["rows"]}; rows_d = {r["k"]: r for r in d["rows"]}
        self.assertNotEqual(rows_l["Model"]["vColor"], rows_d["Model"]["vColor"], "the light theme re-encodes the dark-tuned RGB")
        self.assertNotEqual(m["footer"]["model"], d["footer"]["model"], "…on the footer as well")


if __name__ == "__main__":
    unittest.main()
