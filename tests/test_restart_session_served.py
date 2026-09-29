#!/usr/bin/env python3
"""Restart session on the real page (the user 2026-09-23): the tab menu's row, end to end over a hermetic kernel.

A session keeps the CLI it launched with, so a long-running one cannot reach a model only a newer binary
knows; End session then Revive was the only way onto the new one. Restart session is that in one gesture,
and its whole claim is that NOTHING ELSE CHANGES — so the thing worth reading in a browser is what the page
looks like afterwards.

The served dashboard (the shell with its chat pane) over a hermetic kernel with synthetic sessions (the
notes-api world: web, api, tests, registered records with closed transcripts, so nothing is ever spawned),
one browser run:
  1. the row is in the tab menu, in a section of its own between Billing and Browse files, with the sub-line
     that says what a restart keeps;
  2. a click on an IDLE session opens no dialog: the row latches "Restarting…" in place with the card still
     up (the acknowledgement), and the op reaches the kernel;
  3. whatever the kernel answers, the session survives the gesture WHOLE: its tab is in the strip, in the
     same position, still the selected one, and the chat still shows its history;
  4. the kernel answers the pane that asked — `restarted` for THIS sid — the row re-arms on that event, and
     nothing else is said: a restart that worked is deliberately invisible, so no toast, no dialog, no move.
WHICH ROAD THE LAB DRIVES: these sessions are registered and alive with no CLI running this life, so the
backend's relaunch takes its dormant road (there is no process to replace; the connect IS the fresh CLI) and
answers "". The road that matters for a browser is the same either way — what the page looks like when the
answer lands — and both verdicts are read here: the strip, the selection and the transcript before, during
and after. The primitive's other roads (a running turn cut with the reconnect armed first, the refusals) are
executed in tests/test_restart_session.py, and the row's whole gesture in a real engine, confirm included, in
ui/webview/restart-row.test.ts.
Red at the merge base on every road (no row, no op, no answer). Skips loudly without the extension deps or
a browser. Synthetic fixtures only: a hermetic state root, placeholder sids, invented prose.
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
from pathlib import Path

from tests.dist_copy import copy_dist

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
EXT = os.path.join(ROOT, "vscode-extension")
sys.path.insert(0, HERE)
import test_ship_reship_served as _lab   # noqa: E402  the lab kernel's environment (the module, not its classes)

SID_WEB = "aaaaaaaa-7000-2222-3333-777777777777"
SID_API = "aaaaaaaa-7000-2222-3333-888888888888"
SID_TESTS = "aaaaaaaa-7000-2222-3333-999999999999"
FIRST_PROMPT = "please keep going with the notes-api search module (part 1)"


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _transcript(sid, tag, cwd, pairs):
    out, parent, t = [], None, 1_700_000_000
    for i in range(pairs):
        u = "11111111-2222-4333-8444-%02x00007a%04x" % (tag, i)
        a = "11111111-2222-4333-8444-%02x00007b%04x" % (tag, i)
        ts = lambda k: time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t + i * 60 + k))
        out.append({"type": "user", "uuid": u, "parentUuid": parent, "timestamp": ts(0), "sessionId": sid, "cwd": cwd,
                    "message": {"role": "user", "content": "please keep going with the notes-api search module (part %d)" % (i + 1)}})
        out.append({"type": "assistant", "uuid": a, "parentUuid": u, "timestamp": ts(5), "sessionId": sid, "cwd": cwd,
                    "message": {"id": "msg_lab_%d_%04d" % (tag, i), "type": "message", "role": "assistant", "model": "claude-sonnet-5",
                                "content": [{"type": "text", "text": "Note %d. The ranking pass reads its weights from the config now." % (i + 1)}],
                                "stop_reason": "end_turn"}})
        parent = a
    return "\n".join(json.dumps(r) for r in out) + "\n"


DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));
let browser;
try { browser = await chromium.launch(); } catch (e) { fs.writeSync(2, "no browser: " + e + "\n"); process.exit(3); }
const out = { roads: {}, errors: [] };
const finish = async () => { fs.writeFileSync(cfg.out, JSON.stringify(out)); await browser.close(); process.exit(0); };
const die = async (why) => { out.died = why; await finish(); };
process.on("unhandledRejection", async (e) => { await die("unhandled: " + String(e).split("\n")[0]); });
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
page.on("pageerror", (e) => out.errors.push(String(e)));
const T = 20000;
const waitFn = async (fn, arg, why) => page.waitForFunction(fn, arg, { timeout: T }).catch(async (e) => { await die(why + " (" + String(e).split("\n")[0] + ")"); });
const chatDoc = (fn, arg) => page.evaluate(([f, a]) => {
  const d = document.getElementById("f-chat").contentDocument;
  return new Function("d", "a", "return (" + f + ")(d, a);")(d, a);
}, [fn.toString(), arg === undefined ? null : arg]);

// the chat menu as it stands: its rows, and the restart row's own label, sub-line and disabled mark
const menuNow = () => chatDoc((d) => {
  const m = d.querySelector(".ctx-menu");
  if (!m) return { open: false };
  const rows = Array.from(m.children).filter((c) => c.classList.contains("ctx-item"));
  const r = m.querySelector(".ctx-item-restart");
  return { open: true, rows: rows.map((x) => (x.querySelector(".ctx-item-label") || x).textContent.trim()),
    restart: r ? { label: r.querySelector(".ctx-item-label").textContent.trim(),
                   sub: (r.querySelector(".ctx-item-sub") || {}).textContent || "",
                   disabled: r.getAttribute("aria-disabled") === "true",
                   // the dividers before it and after it: its own section
                   sepBefore: !!(r.previousElementSibling && r.previousElementSibling.classList.contains("ctx-sep")),
                   sepAfter: !!(r.nextElementSibling && r.nextElementSibling.classList.contains("ctx-sep")) } : null,
    confirm: !!d.getElementById("confirm") };
});
// the strip and the transcript: the whole claim of a restart is that these do not change
const scene = () => chatDoc((d) => ({
  tabs: Array.from(d.querySelectorAll("#tabs .tab[data-id]")).map((t) => t.dataset.id),
  active: (d.querySelector("#tabs .tab.active") || {}).dataset ? d.querySelector("#tabs .tab.active").dataset.id : null,
  struck: Array.from(d.querySelectorAll("#tabs .tab[data-id]")).filter((t) => t.classList.contains("dead") || t.classList.contains("closed")).map((t) => t.dataset.id),
  turns: d.querySelectorAll("#content .turn").length,
  firstUser: (d.querySelector("#content .turn-user") || { textContent: "" }).textContent.trim().slice(0, 80),
}));
const toasts = () => chatDoc((d) => Array.from(d.querySelectorAll(".warn-toast-msg")).map((t) => t.textContent));
// every answer the KERNEL sends this pane about a restart, as the shim delivers it to the page's window
const watchFrames = () => page.evaluate(() => { const w = document.getElementById("f-chat").contentWindow;
  w.__restarts = []; w.addEventListener("message", (e) => { const t = e.data && e.data.type;
    if (t === "restarted" || t === "restartFailed" || (t === "unknownOp" && e.data.op === "restartSession")) w.__restarts.push(e.data); }); });
const framesSeen = () => page.evaluate(() => document.getElementById("f-chat").contentWindow.__restarts || []);

await page.goto(cfg.url);
const tabSel = '#tabs .tab[data-id="' + cfg.web + '"]';
await waitFn((sid) => { const d = document.getElementById("f-chat") && document.getElementById("f-chat").contentDocument;
  return !!(d && d.querySelector('#tabs .tab[data-id="' + sid + '"]')); }, cfg.web, "web's tab never appeared");
await waitFn(() => { const d = document.getElementById("f-chat").contentDocument; return d.querySelectorAll("#content .turn").length > 0; }, null,
             "web's transcript never rendered");
await watchFrames();
const chat = await (await page.$("#f-chat")).contentFrame();
await chat.locator(tabSel).click();                       // the session the user is looking at
await page.waitForTimeout(200);
out.roads.before = await scene();

// 1 + 2: the row, and the click on an idle session
await chat.locator(tabSel).click({ button: "right", timeout: 5000 });
await page.waitForTimeout(120);
out.roads.menu = await menuNow();
// the click and the read in ONE tick: the row's listener is synchronous, and the kernel's answer is a task of
// its own, so this reads the latch the click itself put up — never a race with a round trip that can be faster
out.roads.latched = await chatDoc((d) => {
  const r = d.querySelector(".ctx-menu .ctx-item-restart");
  if (!r) return { missing: true };
  r.click();
  const m = d.querySelector(".ctx-menu");
  const now = m && m.querySelector(".ctx-item-restart");
  return { open: !!m, confirm: !!d.getElementById("confirm"),
           restart: now ? { label: now.querySelector(".ctx-item-label").textContent.trim(), disabled: now.getAttribute("aria-disabled") === "true" } : null };
});
if (out.roads.latched.missing) await die("the tab menu has no Restart session row");
out.roads.duringRestart = await scene();

// 3 + 4: the kernel's answer re-arms the row, and the session is untouched either way
await waitFn(() => (document.getElementById("f-chat").contentWindow.__restarts || []).length > 0, null,
             "the kernel never answered the restart");
out.roads.answers = await framesSeen();
await waitFn(() => { const m = document.getElementById("f-chat").contentDocument.querySelector(".ctx-menu .ctx-item-restart");
  return !!m && m.getAttribute("aria-disabled") !== "true"; }, null, "the row never re-armed on the kernel's answer");
out.roads.settled = await menuNow();
out.roads.toasts = await toasts();
await page.keyboard.press("Escape");
await page.waitForTimeout(300);
out.roads.after = await scene();
await finish();
"""


class RestartSessionServed(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(os.path.join(EXT, "node_modules", "playwright")):
            raise unittest.SkipTest("extension deps absent (npm ci not run here): the served leg needs them")
        cls.lab = tempfile.mkdtemp(prefix="restartsession-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            raise unittest.SkipTest("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
        dist = os.path.join(cls.lab, "dist")
        copy_dist(os.path.join(EXT, "dist"), dist)
        state = os.path.join(cls.lab, "xdg", "romp")
        cwd = os.path.join(cls.lab, "proj")
        for d in ("names", "sdk", "goals"):
            os.makedirs(os.path.join(state, d), exist_ok=True)
        os.makedirs(cwd, exist_ok=True)
        Path(cwd, "README.md").write_text("# notes-api\n\nthe search module's notes\n")
        with open(os.path.join(state, "session-hosts"), "w") as fh:   # a lab root of its own pins the hosts OFF (CLAUDE.md 2026-09-11)
            fh.write("off\n")
        claude = os.path.join(cls.lab, "claude")
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        for sid, name, tag in [(SID_WEB, "web", 1), (SID_API, "api", 2), (SID_TESTS, "tests", 3)]:
            Path(state, "names", sid).write_text("%s\t%s\t\t\n" % (name, cwd))
            Path(state, "sdk", sid + ".json").write_text(json.dumps(
                {"sid": sid, "name": name, "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": sid, "alive": True}))
            Path(proj, sid + ".jsonl").write_text(_transcript(sid, tag, cwd, 4))
        Path(state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 100}, "seven_day": {"pct": 10}}))   # park sends
        cls.port = _free_port()
        cls.token = "testtok-restartsession"
        env = _lab.kernel_env(cls.lab, claude, dist, cls.port, cls.token)
        cls.klog = os.path.join(cls.lab, "kernel.log")
        cls.kernel = subprocess.Popen([os.path.join(BIN, "romp-kernel")], stdout=open(cls.klog, "w"), stderr=subprocess.STDOUT, env=env)
        import urllib.request
        for _ in range(120):
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/healthz" % cls.port, timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        else:
            cls.kernel.kill()
            raise unittest.SkipTest("hermetic kernel never served /healthz here")
        cls.result, cls.driver_error = None, None
        cls._drive()

    @classmethod
    def _drive(cls):
        cfg = os.path.join(cls.lab, "cfg.json")
        res = os.path.join(cls.lab, "result.json")
        with open(cfg, "w") as f:
            json.dump({"url": "http://127.0.0.1:%d/?token=%s" % (cls.port, cls.token), "out": res,
                       "web": SID_WEB, "api": SID_API, "tests": SID_TESTS}, f)
        driver = os.path.join(cls.lab, "driver.mjs")
        with open(driver, "w") as f:
            f.write(DRIVER)
        try:
            p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=300,
                               env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
        except subprocess.TimeoutExpired as e:
            so = e.stdout if isinstance(e.stdout, str) else (e.stdout or b"").decode()
            cls.driver_error = "driver timed out; partial output:\n%s" % so
            return
        if p.returncode == 3:
            raise unittest.SkipTest("no playwright browser on this box: the served leg needs one")
        if p.returncode != 0 or not os.path.exists(res):
            cls.driver_error = "driver failed:\n" + p.stdout[-3000:] + p.stderr[-3000:]
            return
        with open(res) as f:
            r = json.load(f)
        keep = os.environ.get("ROMP_RESTARTSESSION_RESULT")
        if keep:
            shutil.copy(res, keep)
        if "died" in r:
            cls.driver_error = "driver aborted early: %s\n%s" % (r["died"], json.dumps(r, indent=1)[-3000:])
            return
        cls.result = r

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "kernel", None):
            cls.kernel.kill()
            cls.kernel.wait()
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

    def setUp(self):
        if self.driver_error:
            self.fail(self.driver_error)

    def test_0_the_pages_threw_nothing(self):
        self.assertEqual(self.result.get("errors"), [], "the pages threw nothing: %r" % self.result.get("errors"))

    def test_1_the_row_is_in_the_tab_menu_in_a_section_of_its_own(self):
        m = self.result["roads"]["menu"]
        self.assertTrue(m["open"], "the tab menu opened: %r" % m)
        self.assertIn("Restart session", m["rows"], "the row is there: %r" % m["rows"])
        self.assertEqual(m["rows"][-1], "Browse files", "…and Browse files is still last, alone: %r" % m["rows"])
        r = m["restart"]
        self.assertEqual((r["sepBefore"], r["sepAfter"]), (True, True), "a divider on each side: its own section: %r" % r)
        self.assertIn("version installed now", r["sub"], "the sub-line says why a restart exists: %r" % r["sub"])
        self.assertIn("conversation stays", r["sub"], "…and what it keeps: %r" % r["sub"])
        self.assertFalse(r["disabled"], "the row is live before the click")

    def test_2_an_idle_session_takes_no_dialog_and_the_row_latches_in_place(self):
        m = self.result["roads"]["latched"]
        self.assertFalse(m["confirm"], "an idle session restarts with no dialog: %r" % m)
        self.assertTrue(m["open"], "the card stays up under the latched row — the click's only acknowledgement: %r" % m)
        self.assertEqual((m["restart"]["label"], m["restart"]["disabled"]), ("Restarting…", True),
                         "the row says what it is doing and takes no second click: %r" % m["restart"])

    def test_3_the_session_survives_the_gesture_whole(self):
        r = self.result["roads"]
        before, during, after = r["before"], r["duringRestart"], r["after"]
        self.assertEqual(sorted(before["tabs"]), sorted([SID_WEB, SID_API, SID_TESTS]), "the strip as the lab built it: %r" % before)
        self.assertEqual(before["active"], SID_WEB, "web is the tab the user is looking at")
        self.assertGreater(before["turns"], 0, "web's history rendered before the click")
        for when, s in (("mid-restart", during), ("after", after)):
            self.assertEqual(s["tabs"], before["tabs"], "%s: the tab is still in the strip, in its place: %r" % (when, s))
            self.assertEqual(s["active"], SID_WEB, "%s: and still the selected one: %r" % (when, s))
            self.assertEqual(s["struck"], [], "%s: nothing on the board reads as a dead session: %r" % (when, s))
            self.assertGreaterEqual(s["turns"], before["turns"], "%s: the transcript lost nothing: %r" % (when, s))
            self.assertIn(FIRST_PROMPT[:40], s["firstUser"], "%s: …its first turn still first: %r" % (when, s["firstUser"]))

    def test_4_the_kernel_answers_the_asking_pane_and_the_row_re_arms_on_that_event(self):
        r = self.result["roads"]
        self.assertEqual(r["answers"], [{"type": "restarted", "id": SID_WEB, "name": "web"}],
                         "one answer, for this sid, to the pane that asked: %r" % r["answers"])
        self.assertEqual((r["settled"]["restart"]["label"], r["settled"]["restart"]["disabled"]), ("Restart session", False),
                         "the row re-armed on the kernel's own answer, with the card still up: %r" % r["settled"])
        self.assertFalse(r["settled"]["confirm"], "and no dialog was ever raised for an idle session")
        self.assertEqual([t for t in r["toasts"] if "restart" in t.lower()], [],
                         "a restart that worked says nothing: the session is exactly as it was: %r" % r["toasts"])


if __name__ == "__main__":
    unittest.main()
