#!/usr/bin/env python3
"""The "Loading earlier messages…" pill sits at the top of the CHAT SECTION, never over the tabs (T365; the user
2026-09-12, whose tab strip wraps onto several rows: the pill, placed against the viewport at top 10px, landed on the
tabs themselves). The fix anchors it to the section: showLoadingPill (render.ts) inserts a zero-height
.tx-loading-anchor right before #content, the page's flex column placing it where the transcript starts, below the
tab strip and the ledger box, and the pill is absolute inside it (styles.css), so its top follows the strip's bottom
by layout alone, however many rows the strip wraps into and however that changes while the pill shows.

This lab drives the real /chat page of a hermetic kernel with twenty synthetic sessions (the notes-api demo world,
host TESTHOST, placeholder sids), shows the pill through the page's on-demand hook (window.__rompLoadingPill: the real
showings last the span of a fetch, too brief to measure) and reads getBoundingClientRect of the pill, #tabs, #tabbar
and #content in three layouts: a viewport wide enough for ONE row of tabs, a narrow one where the strip WRAPS onto two
or more rows, and the wrapped one reached by resizing WHILE the pill shows (the rows change under a showing pill).
Each expects the pill's top edge at or below the strip's bottom edge and the pill inside the chat section's box, and
the pill outside the body (its parent the anchor). Where the page has no hook (a build before the fix) the driver
shows the pill the way the old code did, a .tx-loading-pill appended to the body, and says so (shownBy), so a run
against the old build fails on the geometry and the hook pin alike: LOADING_PILL_DIST=<dir> serves another tree's UI
bundle (the red run's before); LOADING_PILL_SHOTS=<prefix> writes <prefix>-dark.png and <prefix>-light.png of the
wrapped layout with the pill showing; the light theme is measured on every run. Skips LOUDLY without the extension
deps or a Playwright browser, and never otherwise (CI turns a skip in a served module into a failure). SYNTHETIC
fixtures only."""
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
import test_ship_reship as _lab   # noqa: E402  the lab kernel's environment: a list of names, never a copy of the runner's

# the notes-api demo world: twenty sessions, enough to wrap the strip onto several rows at a narrow width
NAMES = ["web", "api", "deploy", "tests", "docs", "auth", "search", "cache", "ingest", "export", "billing", "mailer",
         "worker", "scheduler", "metrics", "backup", "importer", "notifier", "gateway", "indexer"]
SIDS = {n: "%s-1111-2222-3333-444444444444" % (chr(ord("a") + i) * 8) for i, n in enumerate(NAMES)}
PALETTE = [("#9cd2ff", "#0c1a2e"), ("#1EA1EB", "#ffffff"), ("#54B204", "#ffffff"), ("#c98cff", "#1a0c2e"),
           ("#e5a50a", "#1a1200"), ("#4EC9B0", "#00201a")]
WIDE, NARROW = 3000, 900   # one row of twenty tabs; two or more rows


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
const page = await browser.newPage({ viewport: { width: cfg.wide, height: 760 } });
await page.goto(cfg.chat);
await page.waitForSelector("#tabs .tab[data-id]", { timeout: 30000 });
await page.waitForFunction((n) => document.querySelectorAll("#tabs .tab[data-id]").length >= n, cfg.count, { timeout: 30000 });
await page.waitForTimeout(600);
// show the pill: the page's hook when the build has one, else the way the old code did (the red run's before)
const show = () => page.evaluate(() => {
  if (typeof window.__rompLoadingPill === "function") { window.__rompLoadingPill(true); return "hook"; }
  let p = document.querySelector(".tx-loading-pill");
  if (!p) { p = document.createElement("div"); p.className = "tx-loading-pill"; p.textContent = "Loading earlier messages…"; document.body.appendChild(p); }
  p.style.display = ""; return "legacy-body-append";
});
const measure = (label, shownBy) => page.evaluate(([label, shownBy]) => {
  const r1 = (v) => Math.round(v * 10) / 10;
  const r = (el) => { const b = el.getBoundingClientRect(); return { top: r1(b.top), bottom: r1(b.bottom), left: r1(b.left), right: r1(b.right), w: r1(b.width), h: r1(b.height) }; };
  const tabs = document.getElementById("tabs"), tabbar = document.getElementById("tabbar"), content = document.getElementById("content");
  const pill = document.querySelector(".tx-loading-pill");
  const tops = [...new Set(Array.from(tabs.querySelectorAll(".tab[data-id]")).map((t) => Math.round(t.getBoundingClientRect().top)))];
  const cs = pill ? getComputedStyle(pill) : null;
  return { label, shownBy, rows: tops.length, tabs: r(tabs), tabbar: r(tabbar), content: r(content), viewport: { w: window.innerWidth, h: window.innerHeight },
           pill: pill ? r(pill) : null, pillShown: !!pill && cs.display !== "none" && cs.visibility !== "hidden",
           inBody: pill ? pill.parentElement === document.body : null, parent: pill ? pill.parentElement.className : null,
           position: cs ? cs.position : null, pointer: cs ? cs.pointerEvents : null, bg: cs ? cs.backgroundColor : null, border: cs ? cs.borderTopColor : null };
}, [label, shownBy]);
const cases = [];
// one row: the wide viewport
let by = await show(); await page.waitForTimeout(100);
cases.push(await measure("one row", by));
// the rows change WHILE the pill shows: the strip wraps under it
await page.setViewportSize({ width: cfg.narrow, height: 760 }); await page.waitForTimeout(300);
cases.push(await measure("wrapped while showing", by));
// the wrapped layout, the pill hidden then shown again there
await page.evaluate(() => { const p = document.querySelector(".tx-loading-pill"); if (p) p.style.display = "none"; });
await page.waitForTimeout(50);
by = await show(); await page.waitForTimeout(100);
cases.push(await measure("wrapped", by));
// the light theme, measured always (the surface must read on cream); the screenshots only when asked
if (cfg.shots) await page.screenshot({ path: cfg.shots + "-dark.png" });
await page.evaluate(() => document.body.classList.add("theme-light")); await page.waitForTimeout(150);
cases.push(await measure("wrapped, light theme", by));
if (cfg.shots) await page.screenshot({ path: cfg.shots + "-light.png" });
await page.evaluate(() => document.body.classList.remove("theme-light"));
// hidden again: the pill stays in place, invisible, no second node
await page.evaluate(() => { if (typeof window.__rompLoadingPill === "function") window.__rompLoadingPill(false); });
const after = await page.evaluate(() => ({ pills: document.querySelectorAll(".tx-loading-pill").length, anchors: document.querySelectorAll(".tx-loading-anchor").length,
  shown: (() => { const p = document.querySelector(".tx-loading-pill"); return !!p && getComputedStyle(p).display !== "none"; })() }));
fs.writeFileSync(cfg.out, JSON.stringify({ cases, after }));
await browser.close();
console.log("RESULT: ok");
"""


class ServedLoadingPillAnchor(unittest.TestCase):
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
        cls.lab = tempfile.mkdtemp(prefix="loading-pill-")
        before = os.environ.get("LOADING_PILL_DIST", "")
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
        cls.port, cls.token = _free_port(), "testtok-pill"
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
                       "wide": WIDE, "narrow": NARROW, "shots": os.environ.get("LOADING_PILL_SHOTS", "")}, f)
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

    def _case(self, label):
        r = self._run()
        c = next((c for c in r["cases"] if c["label"] == label), None)
        self.assertIsNotNone(c, "no such case %r among %r" % (label, [c["label"] for c in r["cases"]]))
        return c

    def _assert_anchored(self, c):
        table = "\n  " + json.dumps(c, sort_keys=True)
        self.assertTrue(c["pillShown"], "the pill is showing" + table)
        pill, tabs, bar, box = c["pill"], c["tabs"], c["tabbar"], c["content"]
        # the geometry first: this is the user's complaint (a build before the fix fails here, the pill on the tabs)
        self.assertGreaterEqual(pill["top"], tabs["bottom"] - 0.5, "the pill's top edge is at or below the strip's bottom edge" + table)
        self.assertGreaterEqual(pill["top"], bar["bottom"] - 0.5, "…and below the tab bar's border" + table)
        self.assertGreaterEqual(pill["top"], box["top"] - 0.5, "inside the chat section's box: top" + table)
        self.assertLessEqual(pill["bottom"], box["bottom"] + 0.5, "inside the chat section's box: bottom" + table)
        self.assertGreaterEqual(pill["left"], box["left"] - 0.5, "inside the chat section's box: left" + table)
        self.assertLessEqual(pill["right"], box["right"] + 0.5, "inside the chat section's box: right" + table)
        mid_pill, mid_box = (pill["left"] + pill["right"]) / 2, (box["left"] + box["right"]) / 2
        self.assertLess(abs(mid_pill - mid_box), 2.0, "centered in the section" + table)
        self.assertLess(pill["top"] - box["top"], 24.0, "at the top of the section (10px in), not floating lower" + table)
        self.assertEqual(c["pointer"], "none", "non-interactive" + table)
        self.assertIs(c["inBody"], False, "the pill no longer lands in the body" + table)
        self.assertEqual(c["parent"], "tx-loading-anchor", "its parent is the zero-height anchor before #content" + table)
        self.assertEqual(c["shownBy"], "hook", "the page shows its own pill (a build without the hook is the old one)" + table)

    def test_one_row_of_tabs_puts_the_pill_at_the_top_of_the_chat_section(self):
        c = self._case("one row")
        self.assertEqual(c["rows"], 1, "the wide viewport holds every tab on one row: " + json.dumps(c))
        self._assert_anchored(c)

    def test_a_wrapped_strip_of_two_or_more_rows_keeps_the_pill_below_it(self):
        c = self._case("wrapped")
        self.assertGreaterEqual(c["rows"], 2, "the narrow viewport wraps the strip: " + json.dumps(c))
        self._assert_anchored(c)

    def test_the_rows_changing_while_the_pill_shows_moves_it_with_the_strip(self):
        c = self._case("wrapped while showing")
        self.assertGreaterEqual(c["rows"], 2, "the resize wrapped the strip under the showing pill: " + json.dumps(c))
        self._assert_anchored(c)

    def test_hiding_leaves_one_pill_and_one_anchor(self):
        r = self._run()
        self.assertEqual((r["after"]["pills"], r["after"]["anchors"], r["after"]["shown"]), (1, 1, False), json.dumps(r["after"]))

    def test_the_light_theme_pill_reads_on_cream(self):
        # never a conditional skip here: CI's served-tests stance (ROMP_SERVED_TESTS_REQUIRE) turns one into a failure
        c = self._case("wrapped, light theme")
        self._assert_anchored(c)
        self.assertNotEqual(c["bg"], "rgba(20, 24, 33, 0.92)", "the surface is tokened, not the dark literal: " + json.dumps(c))


if __name__ == "__main__":
    unittest.main()
