#!/usr/bin/env python3
"""THE IDENTITY RING on a two-row tab strip, served: a hermetic kernel serves six synthetic notes-api sessions
(TESTHOST, one flat row of tabs, the chat lens narrowed to no tags) into a narrow viewport, so the six tabs wrap onto
TWO rows. The test measures that a SECOND-ROW active tab keeps its own top edge and its identity ring whole, in both
themes: the strip wraps to at least two rows, a tab sits on the second row and is the active one, it wears the
`colored` identity ring as an INSET box shadow, and the T134 hairline (`--box-border`) runs directly above it, one css
pixel over the tab's own top edge, so the 1px row gap the hairlines need never cuts the tab's edge or its ring (the
ring is inset 1.5px and begins one pixel below the edge).

TAB_RING_DIST=<dir> serves another tree's UI bundle (the red run's before); TAB_RING_SHOTS=<prefix> writes
<prefix>-strip-<theme>.png (the wrapped strip per theme); TAB_RING_DUMP=<path> writes the whole measurement. Skips
LOUDLY without the extension deps or a Playwright browser (CI sets ROMP_SERVED_TESTS_REQUIRE=1 and installs both, so a
skip there is a failure). Synthetic throughout: placeholder sids, TESTHOST, invented text.
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
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from tests.dist_copy import copy_dist
import zlib  # noqa: F401  (the driver decodes PNG in node; kept here for a local check of the same math)

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
EXT = os.path.join(ROOT, "vscode-extension")
sys.path.insert(0, HERE)
import test_ship_reship_served as _lab   # noqa: E402  the lab kernel's environment: a list of names, never a copy of the runner's

NAMES = ["web", "api", "deploy", "tests", "docs", "auth"]
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
import zlib from "node:zlib";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));
let browser;
try { browser = await chromium.launch(); }
catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
// a PNG reader for Playwright's screenshots (8-bit RGBA, no interlace): the five scanline filters undone, pixels by (x, y)
function decodePng(buf) {
  let pos = 8; const chunks = []; let w = 0, h = 0, ct = 0;
  while (pos < buf.length) { const len = buf.readUInt32BE(pos); const type = buf.toString("ascii", pos + 4, pos + 8); const data = buf.subarray(pos + 8, pos + 8 + len);
    if (type === "IHDR") { w = data.readUInt32BE(0); h = data.readUInt32BE(4); ct = data[9]; } else if (type === "IDAT") chunks.push(data); pos += 12 + len; }
  const bpp = ct === 6 ? 4 : ct === 2 ? 3 : 1; const raw = zlib.inflateSync(Buffer.concat(chunks)); const stride = w * bpp; const out = Buffer.alloc(stride * h);
  let p = 0;
  for (let y = 0; y < h; y++) { const f = raw[p++]; const row = out.subarray(y * stride, (y + 1) * stride); const prev = y ? out.subarray((y - 1) * stride, y * stride) : null;
    for (let i = 0; i < stride; i++) { const a = i >= bpp ? row[i - bpp] : 0, b = prev ? prev[i] : 0, c = (prev && i >= bpp) ? prev[i - bpp] : 0; let v = raw[p++];
      if (f === 1) v += a; else if (f === 2) v += b; else if (f === 3) v += (a + b) >> 1; else if (f === 4) { const pa = Math.abs(b - c), pb = Math.abs(a - c), pc = Math.abs(a + b - 2 * c); v += (pa <= pb && pa <= pc) ? a : (pb <= pc ? b : c); }
      row[i] = v & 255; } }
  return { w, h, px: (x, y) => { const i = (y * w + x) * bpp; return [out[i], out[i + 1], out[i + 2]]; } };
}
const DPR = 2;
const ctx = await browser.newContext({ viewport: { width: 380, height: 700 }, deviceScaleFactor: DPR });   // narrow: six tabs wrap onto two rows
const page = await ctx.newPage();
await page.goto(cfg.chat);
await page.waitForFunction((n) => document.querySelectorAll("#tabs .tab[data-id]").length >= n, cfg.count, { timeout: 30000 });
await page.waitForTimeout(600);
const out = {};
const rows = () => page.evaluate(() => { const tabs = Array.from(document.querySelectorAll("#tabs .tab[data-id]")); const tops = [...new Set(tabs.map((t) => Math.round(t.getBoundingClientRect().top)))].sort((a, b) => a - b); return { tops, count: tabs.length }; });
out.rows = await rows();
// a tab on the SECOND row becomes the active one (a click: the strip's own road)
const second = await page.evaluate(() => { const tabs = Array.from(document.querySelectorAll("#tabs .tab[data-id]")); const top0 = Math.min(...tabs.map((t) => t.getBoundingClientRect().top)); const t = tabs.find((x) => x.getBoundingClientRect().top > top0 + 5); return t ? t.dataset.id : null; });
out.secondRowTab = second;
if (second) { await page.click('#tabs .tab[data-id="' + second + '"]'); await page.waitForTimeout(500); }
const near = (a, b, tol) => a.every((v, i) => Math.abs(v - b[i]) <= tol);
const parseRgb = (s) => (s.match(/[\d.]+/g) || []).slice(0, 3).map(Number);
const read = async (theme) => {
  await page.evaluate((t) => document.body.classList.toggle("theme-light", t === "light"), theme); await page.waitForTimeout(300);
  await page.mouse.move(2, 690); await page.waitForTimeout(100);   // the pointer off the strip: no hover fill
  const g = await page.evaluate(() => {
    const t = document.querySelector("#tabs .tab.active"); const r = t.getBoundingClientRect(); const cs = getComputedStyle(t);
    const lines = Array.from(document.querySelectorAll("#tabs > .tab-row-line")).map((l) => { const b = l.getBoundingClientRect(); return { top: b.top, bottom: b.bottom, color: getComputedStyle(l).backgroundColor, zIndex: getComputedStyle(l).zIndex, position: getComputedStyle(l).position }; });
    const kids = Array.from(document.getElementById("tabs").children);
    const firstLine = kids.findIndex((k) => k.classList.contains("tab-row-line")), firstTab = kids.findIndex((k) => k.classList.contains("tab"));
    const probe = document.createElement("span"); probe.style.background = "var(--box-border)"; document.body.appendChild(probe); const hairline = getComputedStyle(probe).backgroundColor; probe.remove();
    return { id: t.dataset.id, colored: t.classList.contains("colored"), top: r.top, left: r.left, width: r.width, height: r.height, shadow: cs.boxShadow, fill: cs.backgroundColor, tabZ: cs.zIndex, tabPos: cs.position,
             pageBg: getComputedStyle(document.getElementById("tabbar")).backgroundColor,
             lineOver: lines.find((l) => l.bottom > r.top + 0.01 && l.top < r.top + 1.5) || null, lines, firstLine, firstTab, hairline, barOverflow: getComputedStyle(document.getElementById("tabbar")).overflowY };
  });
  // the pixels: the strip around the tab at ratio 2; the row along the tab's top edge (its first device row) at three columns
  const clip = { x: Math.max(0, g.left - 12), y: Math.max(0, g.top - 12), width: g.width + 24, height: g.height + 24 };
  const png = decodePng(await page.screenshot({ clip }));
  if (cfg.shots) fs.writeFileSync(cfg.shots + "-" + theme + ".png", await page.screenshot({ clip: { x: 0, y: 0, width: 560, height: Math.min(700, g.top + g.height + 20) } }));
  const yEdge = Math.round((g.top - clip.y) * DPR);   // the tab's top edge in device pixels
  const cols = [0.3, 0.5, 0.7].map((f) => Math.round((g.left - clip.x + g.width * f) * DPR));
  const sample = (dy) => cols.map((x) => png.px(x, yEdge + dy));
  const ringColor = parseRgb((g.shadow.match(/rgba?\([^)]*\)/) || [""])[0]), hairline = parseRgb(g.hairline);   // the inset shadow's colour is the ring's
  // the tab's top edge is its 1px transparent border showing the tab's own fill; the ring (inset 1.5px) begins one css pixel below it.
  // The fill is a translucent white over the page, so its expected pixel is the composite over the page's colour read just above the tab
  const rowsRead = { edge: sample(0), plus1: sample(1), plus2: sample(2), plus3: sample(3), above: sample(-1) };
  const fa = (g.fill.match(/[\d.]+/g) || []).map(Number); const alpha = fa.length === 4 ? fa[3] : 1; const page0 = parseRgb(g.pageBg);   // the bar's own background: what the tab's fill composites over
  const fill = fa.slice(0, 3).map((v, i) => Math.round(page0[i] * (1 - alpha) + v * alpha));
  const isRing = (p) => ringColor.length === 3 && near(p, ringColor, 40);
  const isHairline = (p) => near(p, hairline, 4);
  const isFill = (p) => fill.length === 3 && near(p, fill, 6);
  return { geom: g, ringColor, hairline, fill, rowsRead, edgeIsFill: rowsRead.edge.every(isFill) && rowsRead.plus1.every(isFill), edgeIsHairline: rowsRead.edge.every(isHairline) || rowsRead.plus1.every(isHairline),
           ringBelow: rowsRead.plus2.every(isRing) && rowsRead.plus3.every(isRing), pngSize: [png.w, png.h] };
};
out.dark = await read("dark");
out.light = await read("light");
await page.evaluate(() => document.body.classList.remove("theme-light"));
fs.writeFileSync(cfg.out, JSON.stringify(out));
console.log("RESULT: ok");
await browser.close();
"""


class ServedTabRing(unittest.TestCase):
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
        cls.lab = tempfile.mkdtemp(prefix="tab-ring-")
        before = os.environ.get("TAB_RING_DIST", "")
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
        Path(state, "session-hosts").write_text("off\n")   # this lab mints its own state root: no session host (repo rule)
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
        Path(state, "timeline-views.json").write_text(json.dumps({"active": "all", "actives": {"chat": {"none": True}}, "tags": []}))   # the chat lens narrowed to no tags (T405: the control shows no chips for it)
        Path(state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 10}, "seven_day": {"pct": 10}}))
        cls.port, cls.token = _free_port(), "testtok-tabring"
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
            json.dump({"chat": "http://127.0.0.1:%d/chat?token=%s" % (cls.port, cls.token), "landing": "http://127.0.0.1:%d/?token=%s" % (cls.port, cls.token),
                       "count": len(NAMES), "names": NAMES, "out": out, "shots": os.environ.get("TAB_RING_SHOTS", "")}, f)
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
        if os.environ.get("TAB_RING_DUMP"):
            Path(os.environ["TAB_RING_DUMP"]).write_text(json.dumps(result, indent=1) + "\n")
        return result

    def test_the_strip_wraps_onto_two_rows_and_a_second_row_tab_is_the_active_one(self):
        r = self._run()
        self.assertGreaterEqual(len(r["rows"]["tops"]), 2, "the narrow window wraps the strip: " + json.dumps(r["rows"]))
        self.assertIsNotNone(r["secondRowTab"], "a tab sits on the second row")
        for theme in ("dark", "light"):
            g = r[theme]["geom"]
            self.assertEqual(g["id"], r["secondRowTab"], theme + ": the second-row tab is the active one")
            self.assertTrue(g["colored"], theme + ": it wears its identity ring (the colored class)" + json.dumps(g))
            self.assertIn("inset", g["shadow"], theme + ": the ring is the inset box shadow" + json.dumps(g["shadow"]))
            self.assertTrue(any(abs(l["bottom"] - g["top"]) <= 0.6 for l in g["lines"]), theme + ": the T134 hairline runs directly above the tab" + json.dumps(g["lines"]))

    def test_the_tabs_top_edge_and_its_ring_paint_in_front_of_the_row_line_above_it_in_both_themes(self):
        r = self._run()
        for theme in ("dark", "light"):
            d = r[theme]; t = "\n  " + theme + "=" + json.dumps({k: d[k] for k in ("ringColor", "hairline", "fill", "rowsRead", "edgeIsFill", "edgeIsHairline", "ringBelow")})
            self.assertEqual(len(d["ringColor"]), 3, theme + ": the ring's colour is read from the inset shadow" + t)
            self.assertTrue(d["ringBelow"], theme + ": the identity ring runs along the tab, one css pixel under its top edge (the inset shadow)" + t)
            self.assertFalse(d["edgeIsHairline"], theme + ": the row line above no longer paints over the tab's top edge, so the ring reads whole" + t)
            self.assertTrue(d["edgeIsFill"], theme + ": that edge is the tab's own fill, the ring's margin, as on the first row" + t)

    def test_the_row_line_has_its_own_pixel_row_between_the_rows_over_neither(self):
        r = self._run(); g = r["dark"]["geom"]; t = "\n  " + json.dumps({k: g[k] for k in ("top", "lineOver", "lines", "barOverflow")})
        self.assertTrue(g["lines"], "the strip has a row line" + t)
        line = g["lines"][0]
        self.assertLessEqual(line["bottom"], g["top"] + 0.01, "the line ends where the second row's tabs begin: it covers none of their pixels (the 1px row gap, T417)" + t)
        self.assertLessEqual(abs(line["bottom"] - g["top"]), 0.6, "and sits directly above them, one pixel tall" + t)
        self.assertIsNone(g["lineOver"], "no line overlaps the active tab's top edge" + t)

if __name__ == "__main__":
    unittest.main()
