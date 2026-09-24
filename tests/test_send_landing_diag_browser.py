#!/usr/bin/env python3
"""The send-landing watch, end to end in a real browser (2026-09-23): a composer send in a hermetic kernel is followed to its
landed turn, and the rows land in the kernel's client-diag.jsonl stamped with the page's build and the boot it loaded against.

The real /chat page against a hermetic kernel whose one session is mid-turn (the send reaches the kernel and is queued
there; tests/test_send_bubble_visible_browser.py's lab). The page sends through its composer; then, through the pane's own
message channel and in the kernel's frame shape on the kernel's real frame as the base (that lab's variant G idiom), a frame
that LANDS the send (a user row wearing the press's id), and then the same list without the row and without a watermark (an
older kernel's frame, which the page applies). The page's watch must file, through the real shim and the real kernel:
- the `send` row naming the send's id (`key`);
- `landed` with that id, the landed row's uuid, a positive delay and the frame type that brought it;
- `landed-lost` with the same uuid and id, the frame type, and the word that the frame's own events no longer carry it;
and every one of those rows carries `build` (the page's own dist token, read off the page) and `boot` (the kernel's, read
off /version). SYNTHETIC fixtures only; skips loudly without the extension deps or a Playwright browser.
"""
import json
import os
import re
import shutil
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
import test_ship_reship_served as _lab            # noqa: E402  the lab kernel's environment
import test_send_bubble_visible_browser as _sb    # noqa: E402  its mid-turn seed and helpers (the module, never its classes)

SID = _sb.SID
LANDED = "11111111-2222-3333-4444-bbbbbbbbbbbb"
DRIVER_TIMEOUT_S = 300

DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));
let browser;
try { browser = await chromium.launch(); }
catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
const page = await browser.newPage({ viewport: { width: 1000, height: 600 } });
page.on("pageerror", (e) => fs.appendFileSync(cfg.consoleLog, "pageerror: " + e + "\n"));
await page.addInitScript(() => {
  window.__frames = 0; window.__sockets = []; window.__sent = []; window.__last = null;
  window.addEventListener("message", (e) => { const m = e.data;
    if (m && (m.type === "session" || m.type === "update" || m.type === "chatTail")) { window.__frames++; if (m.type === "session" && Array.isArray(m.events)) window.__last = m; } });
  const origSend = WebSocket.prototype.send;
  WebSocket.prototype.send = function (d) {
    try { const m = JSON.parse(d); if (m && m.type === "sendMessage") window.__sent.push({ qid: m.qid }); } catch (e) {}
    if (!window.__sockets.includes(this)) window.__sockets.push(this);
    return origSend.call(this, d);
  };
});
await page.goto(cfg.chat);
await page.waitForSelector("#tabs .tab, #tabs [data-sid]", { timeout: 20000 });
await page.waitForSelector(".turn.turn-user", { timeout: 20000 });
const painted = () => page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 0)))));
// a real whole frame from THIS kernel as the base: the redial's (the sockets closed, the shim redials and the kernel serves the tab whole)
await page.evaluate(() => { window.__last = null; for (const ws of window.__sockets) { try { ws.close(); } catch (e) {} } });
try { await page.waitForFunction(() => !!window.__last, null, { timeout: 15000 }); } catch (e) {}
await page.waitForTimeout(400);
const text = "please rebuild the notes-api search index";
const before = await page.evaluate(() => window.__frames);
await page.fill("#composer-input", text); await page.press("#composer-input", "Enter");
try { await page.waitForFunction((b) => window.__frames > b, before, { timeout: 5000 }); } catch (e) {}
await painted();
const base = await page.evaluate(() => window.__last);
const qid = await page.evaluate(() => (window.__sent[window.__sent.length - 1] || {}).qid);
const out = { qid, baseOk: !!(base && base.wm && Array.isArray(base.wm.tx)), build: await page.evaluate(() => window.__rompReload ? window.__rompReload.loaded : null),
              version: await page.evaluate(() => fetch("/version", { cache: "no-store" }).then((r) => r.json()).catch(() => null)) };
if (out.baseOk && qid) {
  const strip = (evs) => evs.filter((e) => !(e && e.kind === "queued") && !(e && e.kind === "user" && typeof e.uuid === "string" && e.uuid.startsWith("echo:")));
  const bump = (wm, dSize, dLive) => ({ leaf: wm.leaf, tx: wm.tx.map((r, i) => (i === 0 ? [r[0] + (dSize > 0 ? 1 : 0), r[1] + dSize] : r)), live: (typeof wm.live === "number" ? wm.live : 0) + dLive });
  const landedRow = { kind: "user", uuid: cfg.landed, md: text, qid, human: true, ts: new Date().toISOString().replace(/\.\d{3}Z$/, ".000Z") };
  const newer = { ...base, events: [...strip(base.events), landedRow], wm: bump(base.wm, 400, 1) };
  const bare = { ...base, events: strip(base.events) }; delete bare.wm;   // an older kernel's frame: no watermark, the row absent
  const inject = (f) => page.evaluate((x) => { window.postMessage(x, "*"); }, f);
  await inject(newer); await painted();
  out.landedShown = await page.evaluate((u) => !!document.querySelector('#content .turn[data-uuid="' + u + '"]'), cfg.landed);
  await inject(bare); await painted();
  out.afterBare = await page.evaluate((u) => !!document.querySelector('#content .turn[data-uuid="' + u + '"]'), cfg.landed);
}
await page.waitForTimeout(500);   // the rows are on the socket; the kernel writes each as it reads it
fs.writeFileSync(cfg.out, JSON.stringify(out));
fs.writeSync(1, "RESULT-FILE:" + cfg.out + "\n");
await browser.close();
process.exit(0);
"""


class ServedSendLandingDiag(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(os.path.join(EXT, "node_modules", "playwright")):
            raise unittest.SkipTest("extension deps absent (npm ci not run here) — the served guard needs them")
        cls.lab = tempfile.mkdtemp(prefix="send-landing-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            raise unittest.SkipTest("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
        copy_dist(os.path.join(EXT, "dist"), os.path.join(cls.lab, "dist"))
        cls.t0 = int(time.time()) - 900
        cls.port, cls.token = _sb._free_port(), "testtok-sendlanding"
        try:
            cls.kernel, cls.klog, cls.transcript = _sb._kernel(cls.lab, "k", cls.port, cls.token, records=_sb._seed_records(cls.t0))
        except unittest.SkipTest:
            shutil.rmtree(cls.lab, ignore_errors=True)
            raise
        cls.diag = os.path.join(cls.lab, "k", "xdg", "romp", "client-diag.jsonl")

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "kernel", None):
            cls.kernel.kill()
            cls.kernel.wait()
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

    def _rows(self, want, bound_s=10.0):
        """client-diag.jsonl's rows once every kind in `want` is there, or as they stand at the bound (the socket delivers the
        rows the driver left behind; the kernel appends each as its handler reads it)."""
        deadline = time.time() + bound_s
        rows = []
        while True:
            try:
                rows = [json.loads(ln) for ln in Path(self.diag).read_text(encoding="utf-8").splitlines() if ln.strip()]
            except OSError:
                rows = []
            if all(any(r.get("what") == w for r in rows) for w in want) or time.time() > deadline:
                return rows
            time.sleep(0.2)

    def test_a_send_is_followed_to_its_landing_and_its_loss_with_the_pages_build_and_boot_on_every_row(self):
        cfg = os.path.join(self.lab, "cfg.json")
        console_log = os.path.join(self.lab, "console.log")
        Path(console_log).write_text("")
        with open(cfg, "w") as f:
            json.dump({"chat": "http://127.0.0.1:%d/chat?token=%s" % (self.port, self.token), "landed": LANDED,
                       "consoleLog": console_log, "out": os.path.join(self.lab, "result.json")}, f)
        driver = os.path.join(self.lab, "driver.mjs")
        with open(driver, "w") as f:
            f.write(DRIVER)
        try:
            p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=DRIVER_TIMEOUT_S,
                               env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
        except subprocess.TimeoutExpired as e:
            out = e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
            self.fail("the driver ran past its %d s budget:\n%s\n%s" % (DRIVER_TIMEOUT_S, out[-3000:], _sb._kernel_tail(("kernel", self.klog))))
        if p.returncode == 3:
            raise unittest.SkipTest("no playwright browser on this box — the served guard needs one")
        self.assertEqual(p.returncode, 0, "driver failed:\n" + p.stdout[-3000:] + p.stderr[-3000:] + "\n" + _sb._kernel_tail(("kernel", self.klog)))
        line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT-FILE:")), None)
        self.assertIsNotNone(line, "driver printed no result:\n" + p.stdout[-3000:])
        with open(line[len("RESULT-FILE:"):]) as f:
            r = json.load(f)
        self.assertEqual(open(console_log).read().strip(), "", "the page threw")
        self.assertTrue(r["baseOk"], "the kernel's real frame, with its watermark, is the base: %r" % (r,))
        self.assertTrue(re.fullmatch(r"echo:[0-9a-f]{32}", r["qid"] or ""), "the press minted its id: %r" % r["qid"])
        self.assertTrue(r["landedShown"], "the landing frame put the landed row on the page")
        self.assertFalse(r["afterBare"], "the older kernel's frame took it off again (the loss the watch must name)")
        build, boot = r["build"], (r["version"] or {}).get("boot")
        self.assertIsInstance(build, int)
        self.assertTrue(boot, "/version names the kernel's boot: %r" % r["version"])
        rows = self._rows(["send", "landed", "landed-lost"])
        chat = [x for x in rows if x.get("surface") == "chat"]
        send = [x for x in chat if x["what"] == "send" and (x.get("data") or {}).get("key") == r["qid"]]
        landed = [x for x in chat if x["what"] == "landed" and (x.get("data") or {}).get("key") == r["qid"]]
        lost = [x for x in chat if x["what"] == "landed-lost" and (x.get("data") or {}).get("uuid") == LANDED]
        self.assertEqual(len(send), 1, "the send row names its id: %r" % [x["what"] for x in chat])
        self.assertEqual(len(landed), 1, "one landed row for the send: %r" % [x["what"] for x in chat])
        self.assertEqual(landed[0]["data"]["uuid"], LANDED)
        self.assertEqual(landed[0]["data"]["path"], "session")
        self.assertEqual(landed[0]["data"]["by"], "id", "the row wore the press's id")
        self.assertGreater(landed[0]["data"]["ms"], 0)
        self.assertEqual(len(lost), 1, "the loss is named: %r" % [(x["what"], x.get("data")) for x in chat if x["what"].startswith("land")])
        self.assertEqual((lost[0]["data"]["key"], lost[0]["data"]["path"], lost[0]["data"]["inKernel"], lost[0]["data"]["wm"], lost[0]["data"]["fromEnd"]),
                         (r["qid"], "session", False, None, 1))
        self.assertIn("user:" + LANDED, lost[0]["data"]["before"])
        self.assertNotIn("user:" + LANDED, lost[0]["data"]["after"])
        # every row this page filed carries its build and the boot it loaded against, the watch's and the rest alike
        for x in chat:
            self.assertEqual((x.get("build"), x.get("boot")), (build, boot), "stamped: %r" % (x,))
        self.assertEqual(build, (r["version"] or {}).get("dist_ver"), "the page's build is the dist token the kernel serves")


if __name__ == "__main__":
    unittest.main()
