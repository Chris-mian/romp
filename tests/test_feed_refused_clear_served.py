"""The feed page under a Clear the clears log refuses (plans/needs-you.md, phase three; the verifier of PR 1967, 2026-09-21): a hermetic
kernel over one synthetic session with one card, the real feed page served from a copy of the built bundle, driven by Playwright. The
clears log is made read-only, Clear is pressed, and the page must show the refusal AS A DIALOG THE USER CAN READ AND DISMISS (the title,
the detail and a Dismiss button in the DOM: the dialog's box used to be built and never attached to its overlay, so a refusal painted a
bare dim sheet that swallowed the next click) and put the card back where it was (the second review of PR 1967: the click's suppression
let go and the collapse undone, in either window). Dismiss closes the dialog; with the write bit back, Clear takes the card off.
Synthetic only: a placeholder id, invented text, hostname TESTHOST."""
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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from tests.dist_copy import copy_dist  # noqa: E402

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
EXT = os.path.join(ROOT, "vscode-extension")
sys.path.insert(0, HERE)
import test_ship_reship_served as _lab  # noqa: E402  the lab kernel's environment

SID = "eeeeeeee-1111-2222-3333-444444444444"
QUESTION = "which database does the suite target?"


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));
let browser;
try { browser = await chromium.launch(); }
catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
const errors = []; page.on("pageerror", (e) => errors.push(String(e).slice(0, 300)));
const out = { errors };
const cardSel = '[data-key="a:' + cfg.gid + '"]';
const readDialog = () => page.evaluate(() => {
  const o = document.getElementById("err-dialog"); if (!o) return null;
  const box = o.querySelector(".pickdlg-box");
  return { hasBox: !!box, title: (o.querySelector(".pickdlg-title") || {}).textContent || null, detail: (o.querySelector(".pickdlg-detail") || {}).textContent || null,
           buttons: Array.from(o.querySelectorAll("button")).map((b) => b.textContent) };
});
const readCard = () => page.evaluate((sel) => { const c = document.querySelector(sel); return { present: !!c, dismissing: !!c && c.classList.contains("dismissing"), col: c ? c.parentElement.id : null }; }, cardSel);
await page.goto(cfg.feed);
await page.waitForSelector(cardSel, { state: "attached", timeout: 60000 });
out.before = await readCard();
// 1. the log read-only, Clear pressed: the dialog with its words and its button, the card back on the board
fs.chmodSync(cfg.ledger, 0o444);
await page.locator(cardSel + " .fdismiss", { hasText: /^Clear$/ }).first().click();
out.refused = { dialog: await page.waitForSelector("#err-dialog .pickdlg-box .pickdlg-title", { timeout: 30000 }).then(() => true).catch(() => false) };
out.refused.read = await readDialog();
out.refused.cardBack = await page.waitForFunction((sel) => { const c = document.querySelector(sel); return !!c && !c.classList.contains("dismissing"); }, cardSel, { timeout: 30000 }).then(() => true).catch(() => false);
out.refused.card = await readCard();
// 2. Dismiss closes the dialog; the next click on the board is not swallowed
await page.locator("#err-dialog button", { hasText: /^Dismiss$/ }).click();
out.dismissed = await page.waitForSelector("#err-dialog", { state: "detached", timeout: 10000 }).then(() => true).catch(() => false);
// 3. the write bit back: Clear takes the card off with the kernel's next frame
fs.chmodSync(cfg.ledger, 0o644);
await page.locator(cardSel + " .fdismiss", { hasText: /^Clear$/ }).first().click();
out.landed = await page.waitForFunction((sel) => !document.querySelector(sel), cardSel, { timeout: 60000 }).then(() => true).catch(() => false);
out.noDialog = await readDialog();
process.stdout.write("RESULT:" + JSON.stringify(out) + "\n");
await browser.close();
"""


class FeedRefusedClearServed(unittest.TestCase):
    maxDiff = None

    @classmethod
    def _skip(cls, why):
        if os.environ.get("ROMP_SERVED_TESTS_REQUIRE") == "1":
            raise AssertionError("ROMP_SERVED_TESTS_REQUIRE=1 but the served lab could not run: " + why)
        raise unittest.SkipTest(why)

    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(os.path.join(EXT, "node_modules", "playwright")):
            cls._skip("extension deps absent (npm ci not run here): the served guard needs them")
        cls.lab = tempfile.mkdtemp(prefix="feed-refused-clear-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            cls._skip("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
        dist = os.path.join(cls.lab, "dist")
        copy_dist(os.path.join(EXT, "dist"), dist)
        state = os.path.join(cls.lab, "xdg", "romp")
        cwd = os.path.join(cls.lab, "notes-api")
        for d in ("names", "sdk", "states", "goals"):
            os.makedirs(os.path.join(state, d), exist_ok=True)
        os.makedirs(cwd, exist_ok=True)
        Path(state, "session-hosts").write_text("off\n")
        claude = os.path.join(cls.lab, "claude")
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        Path(state, "names", SID).write_text("web\t%s\t#9cd2ff\t#0c1a2e\n" % cwd)
        Path(state, "sdk", SID + ".json").write_text(json.dumps(
            {"sid": SID, "name": "web", "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": SID, "alive": True,
             "model": "claude-opus-5", "liveModel": "Opus 5"}))
        t0 = int(time.time()) - 3600
        iso = lambda t: time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t))
        recs = [{"type": "user", "uuid": "u1", "parentUuid": None, "timestamp": iso(t0), "sessionId": SID, "promptSource": "typed",
                 "message": {"role": "user", "content": "wire the fixtures directory into the integration suite"}},
                {"type": "assistant", "uuid": "a1", "parentUuid": "u1", "timestamp": iso(t0 + 4), "sessionId": SID,
                 "message": {"role": "assistant", "model": "claude-opus-5", "stop_reason": "end_turn", "content": [{"type": "text", "text": QUESTION}]}}]
        Path(proj, SID + ".jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
        Path(state, "states", SID + ".jsonl").write_text(json.dumps({"t": t0 + 10, "state": "idle"}) + "\n")
        cls.gid = SID + ":g1"
        Path(state, "goals", SID + ".json").write_text(json.dumps(
            {"rompUuid": SID, "seq": 1, "lastNode": cls.gid, "closedTurns": [], "placements": {}, "status": {cls.gid: "blocked"},
             "nodes": {cls.gid: {"id": cls.gid, "text": "wire the fixtures directory into the integration suite", "parentId": None, "nodeComplete": False,
                                 "blocked": True, "blockWhy": QUESTION, "cleared": False, "trail": [], "t": t0,
                                 "log": [{"ev_t": t0 + 5, "src": "planner", "kind": "block", "why": "asked: " + QUESTION, "at": t0 + 5}]}}}))
        cls.ledger = os.path.join(state, "cleared.jsonl")
        Path(cls.ledger).write_text("")                       # present, so the leg can take its write bit away and give it back
        cls.port = _free_port()
        cls.token = "testtok-refusedclear"
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
            cls.kernel.kill()
            cls._skip("hermetic kernel never served /healthz here")
        cls._r = None

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "kernel", None):
            cls.kernel.kill()
            cls.kernel.wait()
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

    def _result(self):
        if getattr(type(self), "_fail", None):
            self.fail(type(self)._fail)
        if self._r is None:
            cfg = os.path.join(self.lab, "refused.json")
            with open(cfg, "w") as f:
                json.dump({"feed": "http://127.0.0.1:%d/feed?token=%s" % (self.port, self.token), "gid": self.gid, "ledger": self.ledger}, f)
            driver = os.path.join(self.lab, "refused.mjs")
            Path(driver).write_text(DRIVER)
            p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=600,
                               env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
            if "browser-launch-failed" in p.stderr:
                self._skip("no playwright browser on this box")
            line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
            if line is None:
                type(self)._fail = "the driver produced no RESULT (stderr: %s; kernel: %s)" % (p.stderr[-2000:], open(self.klog).read()[-1500:])
                self.fail(type(self)._fail)
            type(self)._r = json.loads(line[len("RESULT:"):])
        return self._r

    def test_a_refused_clear_shows_a_dialog_the_user_can_read_and_dismiss_and_the_card_comes_back(self):
        r = self._result()
        self.assertEqual(r["errors"], [], "no page error")
        self.assertTrue(r["before"]["present"], "the card is on the board before the press")
        self.assertTrue(r["refused"]["dialog"], "the refusal's box is IN the overlay, with its title: %r" % r["refused"])
        d = r["refused"]["read"]
        self.assertTrue(d and d["hasBox"])
        self.assertEqual(d["title"], "That clear did not land")
        self.assertIn("nothing was cleared", d["detail"] or "", "the detail says what did not happen")
        self.assertIn("Dismiss", d["buttons"], "and there is a button to press: %r" % d["buttons"])
        self.assertTrue(r["refused"]["cardBack"], "the card is back on the board, its collapse undone: %r" % r["refused"]["card"])
        self.assertEqual(r["refused"]["card"]["col"], "col-needsInput-list", "where it was")

    def test_dismiss_closes_the_dialog_and_a_clear_that_lands_takes_the_card_off(self):
        r = self._result()
        self.assertTrue(r["dismissed"], "Dismiss closes the dialog (the overlay used to swallow the next click with nothing to press)")
        self.assertTrue(r["landed"], "with the write bit back, Clear takes the card off")
        self.assertIsNone(r["noDialog"], "and no dialog for a clear that landed")


if __name__ == "__main__":
    unittest.main()
