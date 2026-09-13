#!/usr/bin/env python3
"""The image lightbox's bar at the TOP, in the file viewer's dress (T385, the user 2026-09-12: after opening an image the
controls should sit above it, consistent with how a file opens). A hermetic kernel serves a synthetic notes-api session
(TESTHOST, a placeholder sid) whose chat mentions docs/figure.png; the page renders the figure inline, the driver clicks
it and reads the lightbox: the bar's rect above the picture's, its controls (download, copy, close) with their words and
glyphs, the computed dress of its buttons against the file viewer's own buttons for the same file, the bar's tokens under
the light theme (the backdrop is dark in both), and Escape.

LB_DIST=<dir> serves another tree's UI bundle (the red run's before); LB_SHOTS=<prefix> writes <prefix>-dark.png and
<prefix>-light.png of the open lightbox; LB_DUMP=<path> writes the whole measurement. Skips LOUDLY without the extension
deps or a Playwright browser (CI sets ROMP_SERVED_TESTS_REQUIRE=1 and installs both, so a skip there is a failure).
Synthetic throughout: an invented guide, a run-time PNG, no recorded data.
"""
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
import zlib
from datetime import datetime, timezone
from pathlib import Path

from tests.dist_copy import copy_dist

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
EXT = os.path.join(ROOT, "vscode-extension")
sys.path.insert(0, HERE)
import test_ship_reship as _lab   # noqa: E402  the lab kernel's environment: a list of names, never a copy of the runner's

SID = "aaaaaaaa-1111-2222-3333-444444444444"


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _png(w=320, h=200, rgb=(84, 178, 4)):
    """An opaque PNG, assembled at run time (no binary fixture in the repo); wide enough that the bar fits inside it."""
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));
let browser;
try { browser = await chromium.launch(); }
catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
const ctx = await browser.newContext({ viewport: { width: 1100, height: 640 } });
const page = await ctx.newPage();
await page.goto(cfg.chat);
await page.waitForSelector("#tabs .tab, #tabs [data-sid]", { timeout: 20000 });
await page.waitForFunction(() => { const is = Array.from(document.querySelectorAll(".path-full-img")); return is.length >= 3 && is.every((i) => i.complete && i.naturalWidth > 0); }, null, { timeout: 30000 });
await page.waitForTimeout(200);
const r1 = (v) => Math.round(v * 10) / 10;
const rectOf = "(e) => { const b = e.getBoundingClientRect(); const r = (v) => Math.round(v * 10) / 10; return { top: r(b.top), bottom: r(b.bottom), left: r(b.left), right: r(b.right), w: r(b.width), h: r(b.height) }; }";
const dressOf = "(e) => { const s = getComputedStyle(e); return { fontSize: s.fontSize, padding: s.padding, radius: s.borderRadius, borderWidth: s.borderTopWidth, display: s.display, height: Math.round(e.getBoundingClientRect().height * 10) / 10 }; }";
// the file viewer's own buttons for the same image: the dress the lightbox's must equal
await page.evaluate(([path, sid]) => { window.postMessage({ romp: "viewFile", path, sid }, "*"); }, [cfg.figure, cfg.sid]);
await page.waitForSelector("#romp-fileview .fileview-bar", { timeout: 15000 });
await page.waitForTimeout(200);
const viewer = await page.evaluate((src) => {
  const dress = eval(src);
  const bar = document.querySelector("#romp-fileview .fileview-bar");
  const btn = (aria) => Array.from(bar.querySelectorAll("button, a")).find((e) => e.getAttribute("aria-label") === aria);
  return { download: dress(btn("Download")), close: dress(btn("Close the file viewer")), barPadding: getComputedStyle(bar).padding, nameMinWidth: getComputedStyle(bar.querySelector(".fileview-name")).minWidth };
}, dressOf);
await page.evaluate(() => document.getElementById("romp-fileview")?.remove());
await page.waitForTimeout(100);
// the lightbox: a click on the inline figure
await page.click(".path-full-img >> nth=0");
await page.waitForSelector("#romp-lightbox .romp-lightbox-bar", { timeout: 15000 });
await page.waitForFunction(() => { const i = document.querySelector("#romp-lightbox .romp-lightbox-img"); return !!(i && i.complete && i.naturalWidth > 0); }, null, { timeout: 15000 });
await page.waitForTimeout(150);
const measure = (label) => page.evaluate(([label, rectSrc, dressSrc]) => {
  const rect = eval(rectSrc), dress = eval(dressSrc);
  const wrap = document.getElementById("romp-lightbox");
  const inner = wrap.querySelector(".romp-lightbox-inner");
  const bar = inner.querySelector(".romp-lightbox-bar");
  const img = inner.querySelector(".romp-lightbox-img");
  const acts = bar.querySelector(".fileview-acts");   // absent on the bar before T385: the controls are then read off the bar itself
  const controls = Array.from((acts || bar).querySelectorAll("button, a")).map((e) => ({
    tag: e.tagName.toLowerCase(), aria: e.getAttribute("aria-label") || "", title: e.title || "", text: (e.textContent || "").trim(), cls: e.className,
    svg: !!e.querySelector("svg"), group: e.closest(".fileview-group") ? e.closest(".fileview-group").className : "row", rect: rect(e), dress: dress(e), download: e.getAttribute("download") || "" }));
  const base = bar.querySelector(".fileview-base"), dir = bar.querySelector(".fileview-dir");
  return { label, order: Array.from(inner.children).map((c) => c.className), bar: rect(bar), img: rect(img), inner: rect(inner),
    barClasses: bar.className, barBorderBottom: getComputedStyle(bar).borderBottomColor, barPadding: getComputedStyle(bar).padding,
    nameMinWidth: (bar.querySelector(".fileview-name") ? getComputedStyle(bar.querySelector(".fileview-name")).minWidth : ""), barContain: getComputedStyle(bar).contain,
    baseOverflow: base ? getComputedStyle(base).overflow : "", imgNatural: img.naturalWidth,
    title2: { baseWhole: base ? base.scrollWidth <= base.clientWidth + 0.5 : null, dirClipped: dir ? dir.scrollWidth > dir.clientWidth + 0.5 : null, baseW: base ? base.getBoundingClientRect().width : null },
    actsRect: rect(acts), floor: getComputedStyle(inner).minWidth,
    title: { dir: dir && dir.textContent, base: base && base.textContent, full: (bar.querySelector(".fileview-name") || bar.querySelector(".romp-lightbox-name") || {}).title || "", baseColor: base && getComputedStyle(base).color, dirColor: dir && getComputedStyle(dir).color },
    controls, actsChildren: acts ? Array.from(acts.children).map((c) => c.className) : [], bodyLight: document.body.classList.contains("theme-light") };
}, [label, rectOf, dressOf]);
const out = { viewer, dark: await measure("dark") };
if (cfg.shots) {
  const clip = await page.evaluate(() => { const b = document.querySelector("#romp-lightbox .romp-lightbox-inner").getBoundingClientRect(); return { x: Math.max(0, b.left - 24), y: Math.max(0, b.top - 24), width: Math.min(window.innerWidth, b.width + 48), height: Math.min(window.innerHeight, b.height + 48) }; });
  await page.screenshot({ path: cfg.shots + "-dark.png", clip });
}
await page.evaluate(() => document.body.classList.add("theme-light")); await page.waitForTimeout(150);
out.light = await measure("light");
if (cfg.shots) {
  const clip = await page.evaluate(() => { const b = document.querySelector("#romp-lightbox .romp-lightbox-inner").getBoundingClientRect(); return { x: Math.max(0, b.left - 24), y: Math.max(0, b.top - 24), width: Math.min(window.innerWidth, b.width + 48), height: Math.min(window.innerHeight, b.height + 48) }; });
  await page.screenshot({ path: cfg.shots + "-light.png", clip });
}
await page.evaluate(() => document.body.classList.remove("theme-light")); await page.waitForTimeout(60);
await page.keyboard.press("Escape");
await page.waitForTimeout(120);
out.afterEscape = await page.evaluate(() => ({ gone: !document.getElementById("romp-lightbox") }));
// the NARROW picture: 120px wide, narrower than the bar's three controls; the picture sets the column and the bar wraps inside it
await page.click(".path-full-img >> nth=1");
await page.waitForSelector("#romp-lightbox .romp-lightbox-bar", { timeout: 15000 });
await page.waitForFunction(() => { const i = document.querySelector("#romp-lightbox .romp-lightbox-img"); return !!(i && i.complete && i.naturalWidth > 0); }, null, { timeout: 15000 });
await page.waitForTimeout(150);
out.narrow = await measure("narrow");
await page.keyboard.press("Escape"); await page.waitForTimeout(120);
// the TINY picture: 48px, narrower than the three controls; the column keeps a floor of their width and every control stays inside it
await page.click(".path-full-img >> nth=2");
await page.waitForSelector("#romp-lightbox .romp-lightbox-bar", { timeout: 15000 });
await page.waitForFunction(() => { const i = document.querySelector("#romp-lightbox .romp-lightbox-img"); return !!(i && i.complete && i.naturalWidth > 0); }, null, { timeout: 15000 });
await page.waitForTimeout(150);
out.tiny = await measure("tiny");
if (cfg.shots) {
  const clip = await page.evaluate(() => { const b = document.querySelector("#romp-lightbox .romp-lightbox-inner").getBoundingClientRect(); return { x: Math.max(0, b.left - 24), y: Math.max(0, b.top - 24), width: Math.min(window.innerWidth, b.width + 48), height: Math.min(window.innerHeight, b.height + 48) }; });
  await page.screenshot({ path: cfg.shots + "-tiny-dark.png", clip });
}
if (cfg.shots) {
  const clip = await page.evaluate(() => { const b = document.querySelector("#romp-lightbox .romp-lightbox-inner").getBoundingClientRect(); return { x: Math.max(0, b.left - 24), y: Math.max(0, b.top - 24), width: Math.min(window.innerWidth, b.width + 48), height: Math.min(window.innerHeight, b.height + 48) }; });
  await page.screenshot({ path: cfg.shots + "-narrow-dark.png", clip });
}
await page.keyboard.press("Escape");
fs.writeFileSync(cfg.out, JSON.stringify(out));
await browser.close();
console.log("RESULT: ok");
"""


class ServedLightboxBar(unittest.TestCase):
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
        cls.lab = tempfile.mkdtemp(prefix="lightbox-bar-")
        before = os.environ.get("LB_DIST", "")
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
        cwd = os.path.join(cls.lab, "notes-api")
        for d in ("names", "sdk", "states"):
            os.makedirs(os.path.join(state, d), exist_ok=True)
        Path(state, "session-hosts").write_text("off\n")   # a lab root writes its own session-hosts off (the conftest rule)
        os.makedirs(os.path.join(cwd, "docs"), exist_ok=True)
        cls.figure = os.path.join(cwd, "docs", "figure.png")
        Path(cls.figure).write_bytes(_png())
        Path(cwd, "docs", "narrow.png").write_bytes(_png(120, 80, (4, 120, 178)))   # narrower than the bar's controls: the picture must still set the column
        Path(cwd, "docs", "tiny.png").write_bytes(_png(48, 32, (178, 60, 4)))        # narrower than the controls themselves: the column keeps a floor of their width
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        t0 = int(time.time()) - 900
        Path(state, "names", SID).write_text("web\t%s\t#9cd2ff\t#0c1a2e\n" % cwd)
        Path(state, "sdk", SID + ".json").write_text(json.dumps(
            {"sid": SID, "name": "web", "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": SID, "alive": True,
             "model": "claude-opus-5", "liveModel": "Opus 5"}))
        recs = [{"type": "user", "timestamp": iso(t0), "uuid": "u1", "parentUuid": None, "promptSource": "typed", "sessionId": SID,
                 "message": {"role": "user", "content": "where is the figure for the notes-api guide?"}},
                {"type": "assistant", "timestamp": iso(t0 + 5), "uuid": "a1", "parentUuid": "u1", "sessionId": SID,
                 "message": {"role": "assistant", "model": "claude-opus-5", "stop_reason": "end_turn",
                             "content": [{"type": "text", "text": "The guide's figure is at docs/figure.png, its thumbnail at docs/narrow.png and its icon at docs/tiny.png."}]}}]
        Path(proj, SID + ".jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
        Path(state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 10}, "seven_day": {"pct": 10}}))
        cls.port, cls.token = _free_port(), "testtok-lightbox"
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
        origin = "http://127.0.0.1:%d" % cls.port
        with open(cfg, "w") as f:
            json.dump({"chat": "%s/chat?token=%s" % (origin, cls.token), "origin": origin, "sid": SID, "figure": cls.figure,
                       "out": out, "shots": os.environ.get("LB_SHOTS", "")}, f)
        driver = os.path.join(cls.lab, "driver.mjs")
        with open(driver, "w") as f:
            f.write(DRIVER)
        p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=300,
                           env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
        if p.returncode == 3:
            raise unittest.SkipTest("no playwright browser on this box — the served guard needs one (CI installs none)")
        if p.returncode != 0:
            raise AssertionError("driver failed:\n" + p.stdout[-3000:] + p.stderr[-3000:] + "\nkernel:\n" + open(cls.klog).read()[-1500:])
        if not os.path.exists(out):
            raise AssertionError("driver printed no result:\n" + p.stdout[-3000:])
        result = json.loads(Path(out).read_text())
        if os.environ.get("LB_DUMP"):   # a path: the whole measurement, for reading the cases side by side
            Path(os.environ["LB_DUMP"]).write_text(json.dumps(result, indent=1) + "\n")
        return result

    @staticmethod
    def _ctl(m, aria):
        return next((c for c in m["controls"] if c["aria"] == aria), None)

    def test_the_bar_precedes_the_picture_and_spans_its_column(self):
        m = self._run()["dark"]
        self.assertEqual([c.split()[-1] if "romp-lightbox-bar" in c else c for c in m["order"]], ["romp-lightbox-bar", "romp-lightbox-img"],
                         "the column's children: the bar, then the picture: " + json.dumps(m["order"]))
        self.assertLessEqual(m["bar"]["bottom"], m["img"]["top"], "the bar sits ABOVE the picture, not over it: " + json.dumps({"bar": m["bar"], "img": m["img"]}))
        self.assertAlmostEqual(m["bar"]["left"], m["inner"]["left"], delta=1, msg="the bar starts at the column's left edge")
        self.assertAlmostEqual(m["bar"]["right"], m["inner"]["right"], delta=1, msg="…and ends at its right edge")
        self.assertGreaterEqual(m["img"]["left"], m["inner"]["left"] - 0.5)
        self.assertLessEqual(m["img"]["right"], m["inner"]["right"] + 0.5)

    def test_the_bar_is_the_file_viewers_with_download_copy_grouped_and_the_close_alone_at_the_end(self):
        m = self._run()["dark"]
        self.assertEqual(sorted(m["barClasses"].split()), ["fileview-bar", "romp-lightbox-bar"])
        self.assertEqual(m["title"]["base"], "figure.png", "the basename identifies the picture")
        self.assertEqual(m["title"]["dir"], "docs/", "the directory half, dimmed: the path as the chat mentioned it (relative to the session's cwd)")
        self.assertEqual(m["title"]["full"], "docs/figure.png", "the whole path one hover away")
        self.assertEqual([c["aria"] for c in m["controls"]], ["Download", "Copy image", "Close the picture"], json.dumps(m["controls"])[:400])
        dl, cp, close = (self._ctl(m, a) for a in ("Download", "Copy image", "Close the picture"))
        self.assertEqual((dl["tag"], dl["svg"], dl["download"]), ("a", True, "figure.png"), "download is an anchor wearing the tray glyph, saving under the basename")
        self.assertEqual((cp["tag"], cp["svg"]), ("button", True), "copy wears the two-sheets glyph")
        self.assertEqual(close["text"], "✕")
        self.assertEqual(dl["group"], cp["group"], "download and copy share the file group")
        self.assertIn("fileview-group-file", dl["group"])
        self.assertEqual(close["group"], "row", "the close stands alone outside the group")
        self.assertEqual([c.split()[0] for c in m["actsChildren"]], ["fileview-group", "fileview-btn"], "the actions: one group, then the close")
        self.assertLess(cp["rect"]["right"], close["rect"]["left"], "the close is the right-most control")
        self.assertLess(dl["rect"]["right"], cp["rect"]["left"])

    def test_the_lightboxs_buttons_wear_the_file_viewers_computed_dress(self):
        r = self._run()
        m = r["dark"]
        for aria, key in (("Download", "download"), ("Close the picture", "close")):
            mine = dict(self._ctl(m, aria)["dress"])
            theirs = dict(r["viewer"][key])
            self.assertEqual(mine, theirs, "the %s control's computed dress equals the file viewer's %s: one set of rules" % (aria, key))

    def test_the_bars_tokens_stay_the_dark_themes_under_the_light_theme(self):
        r = self._run()
        d, l = r["dark"], r["light"]
        self.assertTrue(l["bodyLight"], "the light theme was applied for the second measurement")
        self.assertEqual(l["title"]["baseColor"], "rgb(232, 232, 232)", "the basename keeps the dark theme's prose tone on the dark backdrop")
        self.assertEqual(l["title"]["baseColor"], d["title"]["baseColor"])
        self.assertEqual(l["title"]["dirColor"], d["title"]["dirColor"])
        self.assertEqual(l["barBorderBottom"], "rgba(255, 255, 255, 0.18)", "the hairline beneath the bar is the lightbox's light seam in both themes")
        self.assertEqual(d["barBorderBottom"], l["barBorderBottom"])
        self.assertEqual(l["bar"], d["bar"], "the theme moves no geometry")

    def test_the_bars_own_placement_rules_win_the_cascade_on_the_served_page(self):
        """Round one: the two rules tied with the viewer's later rules and lost (7px 10px, 12em on the served bar). Measured, not read."""
        r = self._run()
        m = r["dark"]
        self.assertEqual(m["barPadding"], "0px 2px 6px", "the lightbox bar's own padding (the viewer's is %s)" % r["viewer"]["barPadding"])
        self.assertEqual(r["viewer"]["barPadding"], "7px 10px", "…and the viewer keeps its own")
        self.assertEqual(m["nameMinWidth"], "0px", "the title's 12em floor is lifted in the lightbox (the viewer's: %s)" % r["viewer"]["nameMinWidth"])
        self.assertNotEqual(r["viewer"]["nameMinWidth"], "0px", "the viewer keeps its floor")
        self.assertEqual(m["barContain"], "inline-size", "the bar contributes no intrinsic width: the picture sets the column")
        self.assertEqual(m["baseOverflow"], "hidden", "the basename truncates under a narrow picture")

    def test_a_narrow_picture_sets_the_column_width_and_the_bar_wraps_inside_it(self):
        m = self._run()["narrow"]
        self.assertEqual(m["imgNatural"], 120)
        self.assertAlmostEqual(m["img"]["w"], 120, delta=0.5, msg="the narrow picture at its own size")
        self.assertAlmostEqual(m["inner"]["w"], m["img"]["w"], delta=1, msg="the column is the picture's width, not the bar's: " + json.dumps({"inner": m["inner"], "img": m["img"], "bar": m["bar"]}))
        self.assertAlmostEqual(m["bar"]["w"], m["inner"]["w"], delta=1, msg="the bar fills the column and no more")
        self.assertLessEqual(m["bar"]["bottom"], m["img"]["top"], "the bar still sits above the picture")
        for c in m["controls"]:
            self.assertGreaterEqual(c["rect"]["left"], m["inner"]["left"] - 0.5, "every control stays inside the column: " + json.dumps(c["rect"]))
            self.assertLessEqual(c["rect"]["right"], m["inner"]["right"] + 0.5, "every control stays inside the column: " + json.dumps(c["rect"]))

    def test_a_picture_narrower_than_the_controls_gets_a_column_floored_at_their_width_with_every_control_inside(self):
        """Round two's low: at 48px the download and copy group sat 18px outside the column to the left. The column keeps a floor
        of the actions' measured width (a variable the lightbox sets when it mounts), so the controls stay inside it and the
        picture centres under them."""
        m = self._run()["tiny"]
        table = "\n  " + json.dumps({"inner": m["inner"], "img": m["img"], "acts": m["actsRect"], "floor": m["floor"], "controls": [c["rect"] for c in m["controls"]]})
        self.assertEqual(m["imgNatural"], 48)
        self.assertAlmostEqual(m["img"]["w"], 48, delta=0.5, msg="the tiny picture at its own size" + table)
        group = [c for c in m["controls"] if "fileview-group" in c["group"]]
        need = sum(c["rect"]["w"] for c in group) + 4 * (len(group) - 1)
        self.assertGreaterEqual(m["inner"]["w"], need - 0.5, "the column is at least as wide as the download-and-copy group" + table)
        self.assertNotEqual(m["floor"], "0px", "the floor variable is set (the lightbox measured its group)" + table)
        for c in m["controls"]:
            self.assertGreaterEqual(c["rect"]["left"], m["inner"]["left"] - 0.5, "every control inside the column: " + json.dumps(c["rect"]) + table)
            self.assertLessEqual(c["rect"]["right"], m["inner"]["right"] + 0.5, "every control inside the column: " + json.dumps(c["rect"]) + table)
        centre = (m["img"]["left"] + m["img"]["right"]) / 2
        self.assertAlmostEqual(centre, (m["inner"]["left"] + m["inner"]["right"]) / 2, delta=1.5, msg="the picture centres in the wider column" + table)

    def test_under_a_narrow_picture_the_basename_reads_whole_and_the_directory_carries_the_ellipsis(self):
        """Round two's low: both halves shared the deficit (do... narrow.p...), against the viewer's rule that only the directory
        truncates. The directory absorbs the deficit first; the basename shrinks only when it does not fit alone."""
        m = self._run()["narrow"]
        table = "\n  " + json.dumps(m["title2"]) + " " + json.dumps(m["title"])
        self.assertTrue(m["title2"]["baseWhole"], "the basename is not clipped at 120px" + table)
        self.assertTrue(m["title2"]["dirClipped"], "…the directory carries the ellipsis" + table)
        t = self._run()["tiny"]
        self.assertEqual(t["title2"]["dirClipped"], True, "at 48px the directory is gone to its ellipsis first: " + json.dumps(t["title2"]))

    def test_escape_closes_the_lightbox(self):
        self.assertTrue(self._run()["afterEscape"]["gone"])


if __name__ == "__main__":
    unittest.main()
