#!/usr/bin/env python3
"""The comment thread you had open comes back after a reload, executed in a real browser (the user 2026-09-23,
finishing the reload-place work T265 started: the scroll position survived a reload, the thread popup beside it did
not, and unsent TEXT is deliberately not kept).

The source pins in ui/webview/reload-comment.test.ts say the wiring exists and node executes the record's readings;
nothing there proves the box the reader sees comes back. This is the executed guard. A hermetic kernel serves the
real /chat page with a synthetic session (the notes-api demo world: session `web`, host TESTHOST) whose transcript
is long enough to scroll and carries two seeded comment threads — the store shape the kernel's own create writes —
and the driver walks:

  kept    — open the first thread, DRAG its box to a distinctive corner, scroll the transcript to a third of the
            way down (not the bottom), reload; the popup is back on the same thread, within a pixel or two of where
            it was dragged (never the default right-aligned geometry), the reader's place is restored, and the
            caret is NOT in the popup's input — where the SAME thread opened by hand one gesture later does take
            it, which is the A/B that makes "no focus steal" mean something. The record is read out of the page's
            own sessionStorage through the product seam (window.__rompPersistForReload) before the reload, and is
            gone from it afterwards: one reload, one restore.
  deleted — open the second thread, delete it from the kernel's store, reload; its mark is gone and NOTHING
            reopens. (The store is rewritten milliseconds before the reload, so the page still holds the thread
            when it records it. Should a pusher cycle slip in between, the popup closes and the writer clears the
            record instead — the same user-visible outcome, nothing reopened, which is what this asserts.)

Skips LOUDLY without the extension deps or a Playwright browser (CI installs none). All fixtures synthetic:
placeholder UUIDs, invented prose, host TESTHOST."""
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
import test_ship_reship_served as _lab   # noqa: E402  the lab kernel's environment (the module, not its classes: an
#                                    imported TestCase would be collected here a second time)

WEB = "aaaaaaaa-1111-2222-3333-444444444444"
KEEP = "bbbbbbbb-1111-2222-3333-444444444444"     # the thread that is still there after the reload
GONE = "cccccccc-1111-2222-3333-444444444444"     # the thread deleted before the reload
KEEP_ANCHOR, GONE_ANCHOR = "a06", "a11"
KEEP_EXACT = "the retry budget lives in one table keyed by the failing endpoint"
GONE_EXACT = "every sync writes its own row before it touches the network"
TURNS = 30                                        # enough transcript that #content really scrolls at 900px
W, H = 1200, 900
DRAG_X, DRAG_Y = 40, 300                          # where the driver parks the box: nowhere near the default


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def user(t, uuid, parent, text, sid):
    return {"type": "user", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent, "promptSource": "typed",
            "sessionId": sid, "message": {"role": "user", "content": text}}


def agent(t, uuid, parent, text, sid):
    return {"type": "assistant", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent, "sessionId": sid,
            "message": {"role": "assistant", "model": "claude-opus-5", "stop_reason": "end_turn",
                        "content": [{"type": "text", "text": text}]}}


DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));
const KEY = "romp:reloadComment";
let browser;
try { browser = await chromium.launch(); }
catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
const page = await browser.newPage({ viewport: { width: cfg.W, height: cfg.H } });

async function landed(tid) {
  // 60 s, not 20: the highlight lands with the kernel's comments frame, which on a loaded runner can follow the
  // chat frame by tens of seconds (the pop-size lab's note). The wait is the event; only its ceiling is generous.
  await page.waitForSelector("#content .turn p", { timeout: 60000 });
  await page.waitForSelector(`mark.cmt-hl[data-tid="${tid}"]`, { timeout: 60000 });
}
const popGeom = () => page.evaluate(() => {
  const pop = document.getElementById("cmt-pop");
  if (!pop) return null;
  const r = pop.getBoundingClientRect();
  return { tid: pop.dataset.tid, mode: pop.dataset.mode, left: Math.round(r.left), top: Math.round(r.top),
           w: pop.offsetWidth, h: pop.offsetHeight, storedSize: localStorage.getItem("romp:cmtPopSize") };
});
const place = () => page.evaluate(() => {
  const c = document.getElementById("content");
  return { top: Math.round(c.scrollTop), h: c.scrollHeight, ch: c.clientHeight };
});
const caret = () => page.evaluate(() => {
  const a = document.activeElement;
  return { tag: a ? a.tagName : null, cls: a ? String(a.className || "") : null,
           inPop: !!(a && a.closest && a.closest("#cmt-pop")),
           isCmtInput: !!(a && a.classList && a.classList.contains("cmt-input")),
           hasInput: !!document.querySelector("#cmt-pop .cmt-input") };
});
async function openByMark(tid) {
  await page.click(`mark.cmt-hl[data-tid="${tid}"]`);
  await page.waitForSelector('#cmt-pop[data-mode="thread"]', { timeout: 15000 });
  await page.waitForTimeout(200);   // the open geometry is applied in the same task; one frame to settle
}
async function closePop() {
  await page.click("#cmt-pop .cmt-x");
  await page.waitForSelector("#cmt-pop", { state: "detached", timeout: 5000 });
}
// the record the page keeps on the way down, read through the product seam the reload core calls
const record = () => page.evaluate(() => { window.__rompPersistForReload(); return sessionStorage.getItem("romp:reloadComment"); });

const out = {};
// ── kept: the dragged box, the reader's place, no stolen caret ───────────────────────────────────
await page.goto(cfg.chat);
await landed(cfg.keep);
await openByMark(cfg.keep);
out.opened = await popGeom();
// DRAG the whole box by its title to (DRAG_X, DRAG_Y): the grab offset is preserved, so aim the pointer at the
// target corner plus that offset
const grab = await page.evaluate(() => {
  const t = document.querySelector("#cmt-pop .cmt-title").getBoundingClientRect();
  const p = document.getElementById("cmt-pop").getBoundingClientRect();
  return { x: Math.round(t.left + 6), y: Math.round(t.top + t.height / 2), dx: Math.round(t.left + 6 - p.left), dy: Math.round(t.top + t.height / 2 - p.top) };
});
await page.mouse.move(grab.x, grab.y);
await page.mouse.down();
await page.mouse.move(cfg.DRAG_X + grab.dx, cfg.DRAG_Y + grab.dy, { steps: 6 });
await page.mouse.up();
await page.waitForTimeout(150);
out.dragged = await popGeom();
// the reader's place: a third of the way down, which is neither the top nor the bottom
await page.evaluate(() => { const c = document.getElementById("content"); c.scrollTop = Math.round(c.scrollHeight / 3); });
await page.waitForTimeout(400);
out.placeBefore = await place();
out.recordKept = await record();
await page.reload();
await landed(cfg.keep);
await page.waitForSelector('#cmt-pop[data-mode="thread"]', { timeout: 30000 });
await page.waitForTimeout(300);
out.back = await popGeom();
out.placeAfter = await place();
out.caretAfterReload = await caret();
out.storageAfterReload = await page.evaluate(() => sessionStorage.getItem("romp:reloadComment"));
// the A/B: the SAME thread opened BY HAND takes the caret, which the restore deliberately did not
await closePop();
await openByMark(cfg.keep);
out.caretByHand = await caret();
out.byHand = await popGeom();
await closePop();
// ── deleted: the thread is gone from the store before the page comes back ────────────────────────
await openByMark(cfg.gone);
out.recordGone = await record();
fs.writeFileSync(cfg.store, JSON.stringify({ threads: cfg.threadsAfterDelete }));
await page.reload();
await landed(cfg.keep);
await page.waitForFunction((tid) => !document.querySelector(`mark.cmt-hl[data-tid="${tid}"]`), cfg.gone, { timeout: 60000 });
await page.waitForTimeout(800);   // …and a beat past the frame that decided, so a late reopen would show
out.afterDelete = { pop: await popGeom(), marks: await page.evaluate((tid) => document.querySelectorAll(`mark.cmt-hl[data-tid="${tid}"]`).length, cfg.gone),
                    storage: await page.evaluate(() => sessionStorage.getItem("romp:reloadComment")) };

fs.writeSync(1, "RESULT:" + JSON.stringify(out) + "\n");
await browser.close();
process.exit(0);
"""


class ServedCommentReopenAfterReload(unittest.TestCase):
    maxDiff = None

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
        cls.lab = tempfile.mkdtemp(prefix="cmt-reopen-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            raise unittest.SkipTest("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
        dist = os.path.join(cls.lab, "dist")
        copy_dist(os.path.join(EXT, "dist"), dist)   # tests/dist_copy: skips the bundler's staging files
        state = os.path.join(cls.lab, "xdg", "romp")
        claude = os.path.join(cls.lab, "claude")
        cwd = os.path.join(cls.lab, "proj")
        for d in ("names", "sdk", "states", "comments"):
            os.makedirs(os.path.join(state, d), exist_ok=True)
        os.makedirs(cwd, exist_ok=True)
        # per-session hosts are ON by default (T348) and this lab mints its own state root, outside the runner's
        # floor: without this the first connect would spawn a real bin/romp-session-host on the developer's box
        Path(state, "session-hosts").write_text("off\n")
        Path(state, "names", WEB).write_text("web\t%s\t#9cd2ff\t#0c1a2e\n" % cwd)
        Path(state, "sdk", WEB + ".json").write_text(json.dumps(
            {"sid": WEB, "name": "web", "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": WEB, "alive": True,
             "model": "claude-opus-5", "liveModel": "Opus 5"}))
        Path(state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 10}, "seven_day": {"pct": 10}}))
        t0 = int(time.time()) - 3600
        # a long-enough transcript: thirty closed turn pairs about the notes-api retry work, two of whose answers
        # carry the passages the seeded threads highlight
        recs, parent = [], None
        for i in range(1, TURNS + 1):
            uu, au = "u%02d" % i, "a%02d" % i
            recs.append(user(t0 + 60 * i, uu, parent, "step %d: what is left on the notes-api retry work?" % i, WEB))
            if au == KEEP_ANCHOR:
                body = ("Two things are settled now. First, %s, holding the attempt count, the next allowed time and "
                        "the last error text, so one endpoint can be reset without touching the others. Second, the "
                        "dashboard reads that table directly rather than guessing from the log." % KEEP_EXACT)
            elif au == GONE_ANCHOR:
                body = ("The ordering rule is simple: %s, so a crash mid-flight leaves a row to resume from rather "
                        "than a silent gap. Nothing else in the loop needs to know about it." % GONE_EXACT)
            else:
                body = ("Step %d is done: the sync loop backs off with jitter, the tests cover the slow endpoint, and "
                        "the operator's page still reads in one glance. Nothing is blocked on you here." % i)
            recs.append(agent(t0 + 60 * i + 20, au, uu, body, WEB))
            parent = au
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        Path(proj, WEB + ".jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
        # two threads, each a fork cut at its anchor whose conversation has NOT started yet (the copied history and
        # nothing after it): the popover then holds its opening loader — and, msgs being empty, an ordinary open
        # takes the caret, which is what makes the restore's refusal to take it a real difference
        cls.rows = []
        for i, (tsid, anchor, exact) in enumerate([(KEEP, KEEP_ANCHOR, KEEP_EXACT), (GONE, GONE_ANCHOR, GONE_EXACT)]):
            cut = next(k for k, r in enumerate(recs) if r["uuid"] == anchor)
            hist = [dict(r, sessionId=tsid) for r in recs[:cut + 1]]
            Path(proj, tsid + ".jsonl").write_text("".join(json.dumps(r) + "\n" for r in hist))
            Path(state, "sdk", tsid + ".json").write_text(json.dumps(
                {"sid": tsid, "name": "web-comment-%d" % (i + 1), "cwd": cwd, "lastSid": tsid, "threadOf": WEB,
                 "forkOf": WEB, "forkAt": anchor, "alive": False, "mode": "auto", "effort": "high",
                 "model": "claude-opus-5"}))
            cls.rows.append({"tid": tsid, "sid": tsid, "anchorUuid": anchor, "cutUuid": anchor, "anchorT": t0,
                             "exact": exact, "status": "open", "createdT": t0 + 3000, "lastSeenT": t0 + 3000,
                             "name": "web-comment-%d" % (i + 1), "color": "#e8b220"})
        cls.store = os.path.join(state, "comments", WEB + ".json")
        Path(cls.store).write_text(json.dumps({"threads": cls.rows}))
        cls.port, cls.token = _free_port(), "testtok-cmtreopen"
        env = _lab.kernel_env(cls.lab, claude, dist, cls.port, cls.token, ROMP_HOST_NAME="TESTHOST")
        cls.klog = os.path.join(cls.lab, "kernel.log")
        cls.kernel = subprocess.Popen([os.path.join(BIN, "romp-kernel")], stdout=open(cls.klog, "w"),
                                      stderr=subprocess.STDOUT, env=env)
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

    def _drive(self):
        # ONE browser run for both cases, memoised: its second phase deletes a thread from the kernel's store, so a
        # second run would start in a different world
        if getattr(type(self), "_result", None) is None:
            type(self)._result = self._run()
        return type(self)._result

    def _run(self):
        cfg = os.path.join(self.lab, "cfg.json")
        with open(cfg, "w") as f:
            json.dump({"chat": "http://127.0.0.1:%d/chat?token=%s" % (self.port, self.token),
                       "W": W, "H": H, "DRAG_X": DRAG_X, "DRAG_Y": DRAG_Y, "keep": KEEP, "gone": GONE,
                       "store": self.store, "threadsAfterDelete": [r for r in self.rows if r["tid"] != GONE]}, f)
        driver = os.path.join(self.lab, "driver.mjs")
        with open(driver, "w") as f:
            f.write(DRIVER)
        p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=420,
                           env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
        if p.returncode == 3:
            raise unittest.SkipTest("no playwright browser on this box — the served guard needs one (CI installs none)")
        klog = open(self.klog).read()[-2000:]
        self.assertEqual(p.returncode, 0, "driver failed:\n" + p.stdout[-4000:] + p.stderr[-4000:] + "\nkernel:\n" + klog)
        line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
        self.assertIsNotNone(line, "driver printed no result:\n" + p.stdout[-4000:])
        return json.loads(line[len("RESULT:"):])

    def test_the_open_thread_comes_back_where_it_was_without_taking_the_caret(self):
        r = self._drive()
        dragged, back = r["dragged"], r["back"]
        # the drag really moved the box off its default right-aligned geometry, so the restore below can't be that
        self.assertEqual(dragged["tid"], KEEP, dragged)
        self.assertLessEqual(abs(dragged["left"] - DRAG_X), 2, "the box was parked here: %r" % dragged)
        self.assertLessEqual(abs(dragged["top"] - DRAG_Y), 2, "the box was parked here: %r" % dragged)
        self.assertGreater(r["opened"]["left"], DRAG_X + 200, "the default geometry is nowhere near it: %r" % r["opened"])
        # the record the page kept: this tab, thread mode, the thread, the box's live position — and no draft text
        rec = json.loads(r["recordKept"])
        self.assertEqual(rec["id"], WEB, rec)
        self.assertEqual(rec["mode"], "thread", rec)
        self.assertEqual(rec["tid"], KEEP, rec)
        self.assertLessEqual(abs(rec["pos"]["x"] - DRAG_X), 2, rec)
        self.assertLessEqual(abs(rec["pos"]["y"] - DRAG_Y), 2, rec)
        self.assertEqual(set(rec), {"id", "mode", "tid", "pos"}, "nothing else rides along: %r" % rec)
        # …and the popup is back, on the same thread, where they left it
        self.assertIsNotNone(back, "the popup came back: %r" % r)
        self.assertEqual((back["tid"], back["mode"]), (KEEP, "thread"), back)
        self.assertLessEqual(abs(back["left"] - dragged["left"]), 2, "back where it was: %r vs %r" % (back, dragged))
        self.assertLessEqual(abs(back["top"] - dragged["top"]), 2, "back where it was: %r vs %r" % (back, dragged))
        self.assertLessEqual(abs(back["w"] - dragged["w"]), 2, back)
        self.assertLessEqual(abs(back["h"] - dragged["h"]), 2, back)
        # one reload, one restore: the record is out of storage the moment the page loads
        self.assertIsNone(r["storageAfterReload"], "the record is spent: %r" % r["storageAfterReload"])
        # the reader's place survived too (T265), and it was never the bottom or the top
        pb, pa = r["placeBefore"], r["placeAfter"]
        self.assertGreater(pb["h"], pb["ch"] + 400, "the transcript really scrolls: %r" % pb)
        self.assertGreater(pb["top"], 100, "…and the reader was not at the top: %r" % pb)
        self.assertLess(pb["top"], pb["h"] - pb["ch"] - 100, "…nor at the bottom: %r" % pb)
        self.assertLessEqual(abs(pa["top"] - pb["top"]), 40, "reopening the thread did not cost the reader their place: %r vs %r" % (pa, pb))
        # NO stolen caret: the restore leaves the keyboard where the reader left it, so someone who starts typing
        # in the composer the instant the page lands is not hijacked
        c = r["caretAfterReload"]
        self.assertTrue(c["hasInput"], "the popup has an input to steal: %r" % c)
        self.assertFalse(c["inPop"], "the caret is not inside the reopened popup: %r" % c)
        self.assertFalse(c["isCmtInput"], c)
        # …and the A/B that gives that teeth: the SAME thread opened by hand DOES take the caret
        self.assertEqual(r["byHand"]["tid"], KEEP, r["byHand"])
        self.assertTrue(r["caretByHand"]["isCmtInput"], "an ordinary open of this thread focuses its input: %r" % r["caretByHand"])

    def test_a_thread_deleted_before_the_reload_reopens_nothing(self):
        r = self._drive()
        rec = json.loads(r["recordGone"])
        self.assertEqual((rec["mode"], rec["tid"]), ("thread", GONE), "the page recorded the thread it had open: %r" % rec)
        a = r["afterDelete"]
        self.assertEqual(a["marks"], 0, "the deleted thread has no highlight left: %r" % a)
        self.assertIsNone(a["pop"], "nothing reopens for a thread that is gone: %r" % a)
        self.assertIsNone(a["storage"], "and no record is left behind: %r" % a)


if __name__ == "__main__":
    unittest.main()
