#!/usr/bin/env python3
"""The billing-thread window bug, page side, LOCAL leg: a DOCUMENTED long session (stage 1b wrote its first
assembly document, so the floor sits near the tail: turns above it are lazy pre-cut atoms owed to the proto-2
history wire) served to a proto-2 page. romp_metrics confirmed the kernel side is clean for this shape (the
floored build carries the floor and the last few events plus a head card; every loadTurns/loadOlder returns
events). So this reads the PAGE: does it hold s.regions from that frame, does the head gap ask loadTurns, does
the reply render and the gap scroll. If the page shows the tail alone with no gap and no ask, that is the bug.

The document is seeded the way romp_metrics did it (tests/test_chat_pages.py Harness): whole-parse the leaf,
em.asm_checkpoint_write into the kernel's own STATE/checkpoints, then boot the kernel over that state root so
its first parse restores from the document. SYNTHETIC transcript only (the 4a served fixture's builder)."""
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
import test_ship_reship as _lab   # noqa: E402
from test_asm_checkpoint_served import transcript   # noqa: E402  the compacted long-transcript builder

SID = "eeee1111-2222-3333-4444-555555555555"
COLOR = ("#64b5f6", "#0c1a2e")


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));
let browser;
try { browser = await chromium.launch(cfg.launch || {}); }
catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
const page = await browser.newPage({ viewport: { width: 1000, height: 640 } });
await page.addInitScript(() => {
  const send = WebSocket.prototype.send;
  window.__sent = [];
  WebSocket.prototype.send = function (d) { try { const m = JSON.parse(d); if (m && m.type) window.__sent.push(m); } catch (e) {} return send.call(this, d); };
});
const frames = [];   // the session frames the kernel served for this sid (Node-side, via the WS route)
await page.routeWebSocket((u) => /\/ws(\?|$)/.test(u.pathname + (u.search || "")), (ws) => {
  const server = ws.connectToServer();
  ws.onMessage((m) => server.send(m));
  server.onMessage((m) => {
    try { const f = JSON.parse(m); if (f && f.type === "session" && f.id === cfg.sid) frames.push({ proto: f.proto, floor: f.floor, tailLo: f.tailLo, headKnown: f.headKnown, headTotal: f.headTotal, events: Array.isArray(f.events) ? f.events.length : null, headCards: Array.isArray(f.headCards) ? f.headCards.length : null }); } catch (e) {}
    ws.send(m);
  });
  server.onClose(() => ws.close()); ws.onClose(() => server.close());
});
await page.goto(cfg.chat);
await page.waitForSelector("#tabs .tab, #tabs [data-sid]", { timeout: 20000 });
await page.waitForFunction(() => document.querySelectorAll("#content .turn[data-uuid]").length >= 1, null, { timeout: 30000 }).catch(() => {});
await page.waitForTimeout(800);
const regions = await page.evaluate((sid) => (typeof window.__rompRegions === "function" ? window.__rompRegions(sid) : null), cfg.sid);
const boot = await page.evaluate(() => {
  const c = document.getElementById("content");
  const gaps = Array.from(document.querySelectorAll("#content .tx-gap")).map((g) => ({ lo: Number(g.dataset.lo), hi: Number(g.dataset.hi), h: g.offsetHeight }));
  const turns = Array.from(document.querySelectorAll("#content .turn[data-uuid]")).length;
  return { top: c.scrollTop, sh: c.scrollHeight, ch: c.clientHeight, canScroll: c.scrollHeight - c.clientHeight > 4, gaps, turns };
});
const askedBefore = await page.evaluate((s) => window.__sent.filter((m) => m.type === "loadTurns" && m.id === s).length, cfg.sid);
await page.evaluate(() => { const c = document.getElementById("content"); c.scrollTop = 0; c.dispatchEvent(new Event("scroll")); });
await page.waitForTimeout(300);
await page.evaluate(() => { const c = document.getElementById("content"); c.scrollTop = 0; c.dispatchEvent(new Event("scroll")); });
let asked = false;
try { await page.waitForFunction(([s, n]) => window.__sent.filter((m) => m.type === "loadTurns" && m.id === s).length > n, [cfg.sid, askedBefore], { timeout: 8000 }); asked = true; } catch (e) {}
await page.waitForTimeout(1500);
const regionsAfter = await page.evaluate((sid) => (typeof window.__rompRegions === "function" ? window.__rompRegions(sid) : null), cfg.sid);
const after = await page.evaluate(() => { const c = document.getElementById("content"); return { canScroll: c.scrollHeight - c.clientHeight > 4, turns: document.querySelectorAll("#content .turn[data-uuid]").length, gaps: document.querySelectorAll("#content .tx-gap").length }; });
if (cfg.shots) { fs.mkdirSync(cfg.shots, { recursive: true }); await page.screenshot({ path: cfg.shots + "/romp_chat-documented-history.png", fullPage: false }); }
process.stdout.write("RESULT:" + JSON.stringify({ frame: frames[0] || null, framesN: frames.length, regions, boot, asked, regionsAfter, after }) + "\n");
await browser.close();
"""


class ServedDocumentedHistory(unittest.TestCase):
    _r = None

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
        cls.lab = tempfile.mkdtemp(prefix="doc-history-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            raise unittest.SkipTest("esbuild failed: " + (b.stderr or b.stdout)[-200:])
        copy_dist(os.path.join(EXT, "dist"), os.path.join(cls.lab, "dist"))
        # the kernel's layout (matches _lab.kernel_env: STATE = <sub>/xdg/romp)
        sub = os.path.join(cls.lab, "solo")
        state = os.path.join(sub, "xdg", "romp")
        claude = os.path.join(sub, "claude")
        cwd = os.path.join(sub, "proj")
        for d in ("names", "sdk", "states", "checkpoints"):
            os.makedirs(os.path.join(state, d), exist_ok=True)
        os.makedirs(cwd, exist_ok=True)
        Path(state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 10}, "seven_day": {"pct": 10}}))
        Path(state, "session-hosts").write_text("off\n")
        Path(state, "names", SID).write_text("web\t%s\t%s\t%s\n" % (cwd, COLOR[0], COLOR[1]))
        Path(state, "sdk", SID + ".json").write_text(json.dumps(
            {"sid": SID, "name": "web", "cwd": cwd, "mode": "auto", "effort": "high",
             "lastSid": SID, "alive": True, "model": "claude-opus-5", "liveModel": "Opus 5"}))
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        leaf = os.path.join(proj, SID + ".jsonl")
        now = int(time.time())
        recs = transcript(now - 86400, turns=600, compact_every=150)   # ~300 events after the cut: longer than the wire tail
        Path(leaf).write_text("".join(json.dumps(r) + "\n" for r in recs))

        # SEED the assembly document into the kernel's OWN checkpoints dir, so its first parse restores lazily (cutTurn near tail)
        os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
        km = load_source("romp_kernel_doc_seed", os.path.join(BIN, "romp-kernel"))
        jd, em = km.jd, km.em
        saved_state = jd.STATE
        try:
            jd._rebind_state(Path(state))
            em.set_checkpoint_dir(lambda: jd.STATE / "checkpoints")
            row = {"sid": SID, "name": "web", "path": leaf, "mtime": now, "anchor": SID}
            saved = (km._sessions, km._live_map)
            km._sessions = lambda now=None, **kw: [row]
            km._live_map = lambda: {}
            try:
                km.build_session(SID, now, {}, floor=0)                     # a whole parse (populates the assembly entry, sdk_human True for an sdk session)
                ok = em.asm_checkpoint_write(leaf, SID, sdk_human=True, tree=km._parse(leaf, SID, now))   # the current writer, sdk_human matching the entry
                import glob as _glob
                ckpts = [os.path.basename(f) for f in _glob.glob(os.path.join(str(state), "checkpoints", "*.asm.json.gz"))]
            finally:
                km._sessions, km._live_map = saved
            cls.seed = {"ok": bool(ok), "ckpts": ckpts, "sdkHuman": bool(km._display_sdk_human(SID))}
            if not ok or not ckpts:
                raise unittest.SkipTest("could not write a documented leaf (ok=%r, files=%r): %r" % (ok, ckpts, em.asm_checkpoint_stats()))
        finally:
            em.set_checkpoint_dir(None)
            jd._rebind_state(saved_state)

        cls.port, cls.token = _free_port(), "testtok-doc-hist"
        env = _lab.kernel_env(sub, claude, os.path.join(cls.lab, "dist"), cls.port, cls.token)
        cls.klog = os.path.join(cls.lab, "kernel.log")
        cls.kernel = subprocess.Popen([os.path.join(BIN, "romp-kernel")], stdout=open(cls.klog, "w"), stderr=subprocess.STDOUT, env=env)
        for _ in range(120):
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/healthz" % cls.port, timeout=1); break
            except Exception:
                time.sleep(0.5)
        else:
            cls.kernel.kill(); raise unittest.SkipTest("kernel never served /healthz")

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "kernel", None):
            cls.kernel.kill(); cls.kernel.wait()
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

    def _result(self):
        if type(self)._r is None:
            cfg = os.path.join(self.lab, "doc.json")
            with open(cfg, "w") as f:
                json.dump({"chat": "http://127.0.0.1:%d/chat?token=%s" % (self.port, self.token), "sid": SID,
                           "shots": os.environ.get("DOC_HISTORY_SHOTS", "")}, f)
            driver = os.path.join(self.lab, "doc.mjs")
            Path(driver).write_text(DRIVER)
            p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=400,
                               env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
            if "browser-launch-failed" in p.stderr:
                raise unittest.SkipTest("no playwright browser")
            line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
            klog = ""
            try:
                klog = open(self.klog).read()[-1500:]
            except OSError:
                pass
            self.assertIsNotNone(line, "no RESULT (stderr: %s)\nkernel:\n%s" % (p.stderr[-1500:], klog))
            type(self)._r = json.loads(line[len("RESULT:"):])
        print("DOCHIST seed=%r r=%s" % (getattr(type(self), "seed", None), json.dumps(type(self)._r)), file=sys.stderr)
        return type(self)._r

    def test_the_kernel_served_a_floor_near_tail_frame(self):
        # first: the seeded document restored on the real kernel's boot (the served frame carries floor near the tail)
        r = self._result()
        f = r.get("frame")
        self.assertIsNotNone(f, "the page received a session frame for the sid: %r seed=%r" % (r.get("boot"), getattr(type(self), "seed", None)))
        self.assertEqual(f.get("proto"), 2, "proto 2: %r" % f)
        self.assertIsInstance(f.get("floor"), int, "the frame carries a floor: %r" % f)
        self.assertGreater(f.get("floor") or 0, 100, "the floor is near the tail (the document restored), not 0: %r seed=%r" % (f, getattr(type(self), "seed", None)))
        self.assertEqual(f.get("tailLo"), f.get("floor"), "tailLo equals the floor: %r" % f)
        self.assertEqual(f.get("headKnown"), False, "headKnown false (older history above the floor): %r" % f)

    def test_the_page_holds_regions_asks_and_scrolls_for_that_frame(self):
        r = self._result()
        self.assertIsNotNone(r["regions"], "the page holds regions from the floor-near-tail frame (a head gap over the tail): boot=%r frame=%r" % (r["boot"], r.get("frame")))
        kinds = [x["kind"] for x in r["regions"]]
        self.assertIn("gap", kinds, "there is a head gap for the turns below the floor: %r" % r["regions"])
        self.assertTrue(r["asked"], "scrolling to the top asked for the head page (loadTurns): %r" % r)
        self.assertTrue(r["after"]["canScroll"], "the content scrolls: %r" % r["after"])


if __name__ == "__main__":
    unittest.main()
