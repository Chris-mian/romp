#!/usr/bin/env python3
"""The VERTICAL chat split, LOCAL face (drag a tab to a pane's bottom edge; the chat vertical split, 2026-09-16).
A column splits into a top and a bottom pane: the top keeps the column's own session, the bottom holds the one
split off. This drives the split through __rompMoveTab(sid,'down') (the drag's mutation; PR2 drives the pointer)
and pins the model the design decided: a long session in EVERY pane fills to turn 0, ESPECIALLY the non-focused
one after a shell reload (the scroll-back wall lesson, #1754); the bottom pane dials /chat?col=N&skeleton=1 with
its own iid; the two panes are STACKED (same left, greater top) with a row-resize gutter between; and the split
persists across a reload as a cols entry with place:'below', parent and ratio under v:2.

One hermetic kernel. Both panes hold a documented (cut-floor) long session, so fill-to-turn-0 is a real
transition, not an already-short transcript. Synthetic only: placeholder uuids, hostname TESTHOST, the served
builder's invented text."""
import glob
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
from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
EXT = os.path.join(ROOT, "vscode-extension")
sys.path.insert(0, HERE)
import test_ship_reship_served as _lab                      # noqa: E402
from test_asm_checkpoint_served import transcript           # noqa: E402

os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)
_ST0 = Path(os.environ["XDG_STATE_HOME"]) / "romp"
_ST0.mkdir(parents=True, exist_ok=True)
(_ST0 / "session-hosts").write_text("off\n")

SID_TOP = "dddd1111-2222-4333-8444-000000000a01"    # stays in the top pane (the column's own session)
SID_BOT = "dddd1111-2222-4333-8444-000000000a02"    # split down into the bottom pane
COLOR = ("#64b5f6", "#0c1a2e")


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));   // {url, top, bot}
let browser;
try { browser = await chromium.launch(cfg.launch || {}); }
catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
const page = await browser.newPage({ viewport: { width: 1400, height: 820 } });
page.on("pageerror", () => {});
// clear the split store on the TOP frame only (a column iframe's load must not wipe it mid-flight), and record
// every frame's WebSocket dial URLs (the bottom pane's included) so we can read its skeleton=1 and its iid.
await page.addInitScript(() => {
  try { if (window === window.top && !localStorage.getItem("__vsplit_started")) { localStorage.removeItem("romp-chat-cols"); Object.keys(localStorage).filter((k) => k.indexOf("romp-vscode-state-chat") === 0).forEach((k) => localStorage.removeItem(k)); localStorage.setItem("__vsplit_started", "1"); } } catch (e) {}   // clear ONCE (first load); the reload must keep the split to test persistence
  try { window.__dials = []; const N = window.WebSocket; window.WebSocket = function (u, p) { try { window.__dials.push(String(u)); } catch (e) {} return p === undefined ? new N(u) : new N(u, p); }; window.WebSocket.prototype = N.prototype; } catch (e) {}
});
const out = { died: null };
const frameOf = async (fid) => { const h = await page.$("#" + fid); return h ? await h.contentFrame() : null; };
// the fill observable for one pane: scroll #content to the top twice, let the observer fire and the head page land,
// then read __rompRegions (a run region at lo 0 = filled to turn 0; a gap region at boot = a real head gap).
const colState = async (fid, sid) => {
  const fr = await frameOf(fid);
  if (!fr) return { missing: true };
  await fr.waitForFunction(() => document.querySelectorAll("#content .turn[data-uuid]").length >= 1, null, { timeout: 30000 }).catch(() => {});
  const boot = await fr.evaluate((id) => {
    const c = document.getElementById("content");
    const regions = (typeof window.__rompRegions === "function") ? window.__rompRegions(id) : null;
    return { active: (document.querySelector("#tabs .tab.active[data-id]") || {}).getAttribute ? document.querySelector("#tabs .tab.active[data-id]").getAttribute("data-id") : null,
             turns: document.querySelectorAll("#content .turn[data-uuid]").length,
             hasGapRegion: !!(regions && regions.some((r) => r.kind === "gap")), regions };
  }, sid);
  await fr.evaluate(() => { const c = document.getElementById("content"); if (c) { c.scrollTop = 0; c.dispatchEvent(new Event("scroll")); } });
  await page.waitForTimeout(300);
  await fr.evaluate(() => { const c = document.getElementById("content"); if (c) { c.scrollTop = 0; c.dispatchEvent(new Event("scroll")); } });
  await page.waitForTimeout(1800);
  const after = await fr.evaluate((id) => {
    const regions = (typeof window.__rompRegions === "function") ? window.__rompRegions(id) : null;
    return { turns: document.querySelectorAll("#content .turn[data-uuid]").length, regions };
  }, sid);
  return { boot, after };
};
// the dial URL a given frame opened (full url), from the WebSocket hook the initscript installed
const dialsOf = async (fid) => { const fr = await frameOf(fid); return fr ? await fr.evaluate(() => (window.__dials || []).slice()) : []; };
try {
  await page.goto(cfg.url);
  await page.waitForFunction((t) => { const f = document.getElementById("f-chat"); const d = f && f.contentDocument; return !!(d && d.querySelector('#tabs .tab[data-id="' + t + '"]')); }, cfg.top, { timeout: 40000 });
  // show the top session, then split the bottom one DOWN
  await frameOf("f-chat").then((fr) => fr && fr.locator('#tabs .tab[data-id="' + cfg.top + '"]').first().click().catch(() => {}));
  await page.waitForTimeout(400);
  out.split = await page.evaluate((bot) => { const f = window.__rompMoveTab(bot, "down"); return { frameId: f && f.id, cols: localStorage.getItem("romp-chat-cols") }; }, cfg.bot);
  const botFid = out.split.frameId;
  out.botFid = botFid;
  await page.waitForFunction((fid) => !!document.getElementById(fid), botFid, { timeout: 20000 });
  await page.waitForTimeout(600);
  // GEOMETRY: the bottom pane is stacked UNDER the top (same left, greater top), and the gutter between is row-resize
  out.geom = await page.evaluate((fid) => {
    const top = document.getElementById("f-chat"), bot = document.getElementById(fid);
    const tr = top.getBoundingClientRect(), br = bot.getBoundingClientRect();
    const g = document.querySelector(".pane.split-v .gh-chat");
    return { sameLeft: Math.abs(tr.left - br.left) <= 2, belowTop: br.top > tr.top + tr.height / 2,
             widthClose: Math.abs(tr.width - br.width) <= 2, gutterCursor: g ? getComputedStyle(g).cursor : null,
             paneSplit: !!(top.closest(".pane") && top.closest(".pane").classList.contains("split-v")) };
  }, botFid);
  // DIAL: the bottom frame dialed /chat?col=<n>&skeleton=1 with an iid distinct from the top pane's
  out.topDials = await dialsOf("f-chat");
  out.botDials = await dialsOf(botFid);
  // FILL at creation (both panes): the bottom is focused now, the top is non-focused
  out.topFill = await colState("f-chat", cfg.top);
  out.botFill = await colState(botFid, cfg.bot);
  // RELOAD: the ring lands on one pane, both redial; the non-focused pane must still fill (the wall guard), and the split persists
  await page.reload();
  await page.waitForFunction((t) => { const f = document.getElementById("f-chat"); const d = f && f.contentDocument; return !!(d && d.querySelector('#tabs .tab[data-id="' + t + '"]')); }, cfg.top, { timeout: 40000 });
  await page.waitForTimeout(400);
  out.afterReload = await page.evaluate(() => ({ cols: localStorage.getItem("romp-chat-cols"), botExists: !!document.querySelector('iframe[id^="f-chat-"]'),
    botId: (document.querySelector(".pane.split-v .chat-sub iframe") || {}).id || null }));
  const botFid2 = out.afterReload.botId || botFid;
  await page.waitForFunction((fid) => !!document.getElementById(fid), botFid2, { timeout: 20000 });
  await page.waitForTimeout(500);
  out.topReloadFill = await colState("f-chat", cfg.top);
  out.botReloadFill = await colState(botFid2, cfg.bot);
} catch (e) {
  out.died = String(e).slice(0, 500);
}
process.stdout.write("RESULT:" + JSON.stringify(out) + "\n");
await browser.close();
"""


class VSplitLocal(unittest.TestCase):
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
        cls.lab = tempfile.mkdtemp(prefix="chat-vsplit-")
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
        for sid, sname, age in ((SID_TOP, "api", 86400), (SID_BOT, "web", 90000)):
            Path(state, "names", sid).write_text("%s\t%s\t%s\t%s\n" % (sname, cwd, COLOR[0], COLOR[1]))
            Path(state, "sdk", sid + ".json").write_text(json.dumps(
                {"sid": sid, "name": sname, "cwd": cwd, "mode": "auto", "effort": "high",
                 "lastSid": sid, "alive": True, "model": "claude-opus-5", "liveModel": "Opus 5"}))
            Path(proj, sid + ".jsonl").write_text("".join(json.dumps(r) + "\n" for r in transcript(now - age, turns=600, compact_every=150)))
        # seed a cut-floor (documented) checkpoint for BOTH sessions, so each pane has a real head gap to fill
        os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
        km = load_source("romp_kernel_vsplit_seed", os.path.join(BIN, "romp-kernel"))
        jd, em = km.jd, km.em
        saved_state = jd.STATE
        try:
            jd._rebind_state(Path(state))
            em.set_checkpoint_dir(lambda: jd.STATE / "checkpoints")
            saved = (km._sessions, km._live_map)
            cls.seed = {}
            try:
                for sid in (SID_TOP, SID_BOT):
                    leaf = os.path.join(proj, sid + ".jsonl")
                    row = {"sid": sid, "name": "s", "path": leaf, "mtime": now, "anchor": sid}
                    km._sessions = lambda now=None, _r=row, **kw: [_r]
                    km._live_map = lambda: {}
                    km.build_session(sid, now, {}, floor=0)
                    cls.seed[sid] = bool(em.asm_checkpoint_write(leaf, sid, sdk_human=True, tree=km._parse(leaf, sid, now)))
            finally:
                km._sessions, km._live_map = saved
            ckpts = [os.path.basename(f) for f in glob.glob(os.path.join(str(state), "checkpoints", "*.asm.json.gz"))]
            if not all(cls.seed.values()) or len(ckpts) < 2:
                raise unittest.SkipTest("could not seed cut-floor documents: %r ckpts=%r" % (cls.seed, ckpts))
        finally:
            em.set_checkpoint_dir(None)
            jd._rebind_state(saved_state)
        cls.port, cls.token = _free_port(), "testtok-vsplit"
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
                json.dump({"url": "http://127.0.0.1:%d/?token=%s" % (self.port, self.token),
                           "top": SID_TOP, "bot": SID_BOT}, f)
            driver = os.path.join(self.lab, "driver.mjs")
            Path(driver).write_text(DRIVER)
            p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=420,
                               env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
            if "browser-launch-failed" in p.stderr:
                raise unittest.SkipTest("no playwright browser")
            line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
            self.assertIsNotNone(line, "no RESULT (stderr: %s)" % p.stderr[-1500:])
            type(self)._cache = json.loads(line[len("RESULT:"):])
        r = type(self)._cache
        print("VSPLIT %s" % json.dumps(r)[:2000], file=sys.stderr)
        self.assertIsNone(r.get("died"), "driver error: %s" % r.get("died"))
        return r

    @staticmethod
    def _filled(colfill):
        after = (colfill or {}).get("after") or {}
        return any(x.get("kind") == "run" and x.get("lo") == 0 for x in (after.get("regions") or []))

    def test_1_split_stacks_the_bottom_pane_under_the_top_with_a_row_resize_gutter(self):
        g = self._result().get("geom") or {}
        self.assertTrue(g.get("paneSplit"), "the parent .pane is .split-v: %r" % g)
        self.assertTrue(g.get("sameLeft") and g.get("belowTop"), "the bottom pane is stacked UNDER the top (same left, greater top): %r" % g)
        self.assertEqual(g.get("gutterCursor"), "row-resize", "the between-panes gutter is row-resize, not col-resize: %r" % g)

    def test_2_the_bottom_pane_dials_col_skeleton_with_its_own_iid(self):
        r = self._result()
        bot = [u for u in (r.get("botDials") or []) if "/ws" in u]
        self.assertTrue(bot, "the bottom frame opened a /ws dial: %r" % r.get("botDials"))
        self.assertTrue(any("skeleton=1" in u for u in bot), "the bottom dial carries skeleton=1: %r" % bot)
        import re as _re
        def iid(us):
            for u in us:
                m = _re.search(r"[?&]iid=([^&]+)", u)
                if m:
                    return m.group(1)
            return None
        bi, ti = iid(bot), iid([u for u in (r.get("topDials") or []) if "/ws" in u])
        self.assertTrue(bi, "the bottom dial carries an iid: %r" % bot)
        self.assertNotEqual(bi, ti, "the bottom pane's iid is distinct from the top pane's: bot=%r top=%r" % (bi, ti))

    def test_3_both_panes_fill_to_turn_0_at_creation(self):
        r = self._result()
        self.assertTrue((r.get("topFill", {}).get("boot") or {}).get("hasGapRegion"), "the top pane boots with a head gap: %r" % r.get("topFill"))
        self.assertTrue(self._filled(r.get("topFill")), "the TOP pane fills to turn 0: %r" % r.get("topFill"))
        self.assertTrue(self._filled(r.get("botFill")), "the BOTTOM pane fills to turn 0: %r" % r.get("botFill"))

    def test_4_the_non_focused_pane_fills_after_a_reload_the_wall_guard(self):
        r = self._result()
        cols = r.get("afterReload", {}).get("cols") or ""
        self.assertIn('"place":"below"', cols, "the split persists as a place:'below' cols entry: %r" % cols)
        self.assertIn('"parent":1', cols, "the bottom pane records its parent column (1): %r" % cols)
        self.assertTrue(self._filled(r.get("topReloadFill")), "the top pane fills to turn 0 after a reload: %r" % r.get("topReloadFill"))
        self.assertTrue(self._filled(r.get("botReloadFill")), "the NON-FOCUSED bottom pane fills to turn 0 after a reload (the wall guard): %r" % r.get("botReloadFill"))


if __name__ == "__main__":
    unittest.main()
