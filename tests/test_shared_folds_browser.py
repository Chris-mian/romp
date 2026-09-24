#!/usr/bin/env python3
"""A tag group folded on one device is folded on the other, live (the user 2026-09-23, who wanted to collapse tag groups
on the phone too, with the collapsed state synced to the desktop like the tab order).

The folds used to live in each browser's romp:tabgroups, and the phone folded nothing at all (#1770: its session picker
is its only switcher, and a folded group would have hidden sessions). Now the kernel keeps the folds beside the viewer's
arrangement (kernel.py view-folds.json, served and pushed on the one viewOrder frame), every page adopts them and
publishes its own changes (tab-groups.ts), and the phone's picker folds a group from its heading, the same control the
desktop's strip header is.

This lab drives one hermetic kernel's real /chat page from two browser contexts, separate localStorage each, so they are
two devices and not two tabs sharing a store: a desktop (mouse, 1400 px) and a phone (a coarse pointer at 390 px, the
kernel's own media rule). In one driver run:
  1. the desktop clicks the qa header: the phone's picker, without a reload, lists qa's heading alone (its count and
     state as the header's, aria-expanded false) and none of its sessions;
  2. the phone taps that heading: the list stays open and lists qa's sessions again, and the desktop's strip, without a
     reload, shows qa open;
  3. the ACTIVE session's group folds like any other, the desktop's rule: the phone picks web, the desktop folds infra,
     and the phone's picker lists infra's heading alone, marked current, while the current-session chip still names web;
     the phone opening infra brings web's row back, marked active.
The kernel's store is read after each step. Skips LOUDLY without the extension deps or a Playwright browser. The lab
kernel never reaches the machine's user manager: a `systemctl` and a `systemd-run` of the lab's own shadow the real
ones on its PATH (the boot reconcile lists session scopes for any session it finds alive). SYNTHETIC fixtures only
(the notes-api demo world: web, api, tests, docs, auth; host TESTHOST; placeholder sids)."""
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

NAMES = ["web", "api", "tests", "docs", "auth"]
SIDS = {n: "%s-5555-4666-8777-000000000000" % (chr(ord("a") + i) * 8) for i, n in enumerate(NAMES)}
NAME_OF = {v: k for k, v in SIDS.items()}
PALETTE = [("#9cd2ff", "#0c1a2e"), ("#1EA1EB", "#ffffff"), ("#54B204", "#ffffff"), ("#c98cff", "#1a0c2e"), ("#e5a50a", "#1a1200")]
TAGS = [{"id": "tag-qa", "name": "qa", "color": "#DD42FF", "members": [SIDS["tests"], SIDS["docs"]]},
        {"id": "tag-infra", "name": "infra", "color": "#4EC9B0", "members": [SIDS["web"], SIDS["api"]]}]
TAG_ORDER = ["qa", "infra"]


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
const out = { steps: [] };
const T = 20000;
const finish = async (why) => { if (why) out.died = why; fs.writeFileSync(cfg.out, JSON.stringify(out)); fs.writeSync(1, "RESULT:" + cfg.out + "\n"); await browser.close(); process.exit(0); };
const wait = (page, fn, arg, why) => page.waitForFunction(fn, arg, { timeout: T }).catch(async (e) => { await finish(why + " (" + String(e).split("\n")[0] + ")"); });
const store = () => { try { return JSON.parse(fs.readFileSync(cfg.foldsFile, "utf8")); } catch (e) { return null; } };
// what each surface shows: the desktop strip's headers and tabs, the phone picker's headings and rows (the folded-away
// active node is read by the picker's chip and is never a row, so it is left out of the strip reading too)
const readDesk = (page) => page.evaluate(() => Array.from(document.getElementById("tabs").children).map((el) => {
  if (el.matches(".tab-group-head[data-group]")) return "g:" + el.dataset.group + (el.dataset.folded === "1" ? "(folded)" : "");
  if (el.matches(".tab[data-id]:not(.tab-away)")) return "t:" + el.dataset.id;
  return null; }).filter(Boolean));
const readPhone = (page) => page.evaluate(() => ({
  rows: Array.from(document.getElementById("mlist").children).map((el) => {
    if (el.matches(".mhead[data-group]")) return "g:" + el.dataset.group + (el.classList.contains("folded") ? "(folded)" : "");
    if (el.matches(".mrow[data-id]")) return "t:" + el.dataset.id + (el.classList.contains("active") ? "(active)" : "");
    if (el.matches(".msep")) return "sep";
    return null; }).filter(Boolean),
  heads: Object.fromEntries(Array.from(document.querySelectorAll("#mlist .mhead[data-group]")).map((h) => [h.dataset.group, {
    expanded: h.getAttribute("aria-expanded"), current: h.getAttribute("aria-current"), role: h.getAttribute("role"),
    count: (h.querySelector(".mcount") || {}).textContent || null, caret: !!h.querySelector(".mcaret"), height: h.getBoundingClientRect().height }])),
  current: ((document.querySelector("#mcur .nm") || {}).textContent || "").trim(),
  away: Array.from(document.querySelectorAll("#tabs .tab.tab-away[data-id]")).map((t) => t.dataset.id),
  listOpen: !!document.querySelector("#mlist.open"),
  phoneLayout: window.matchMedia("(pointer:coarse) and (max-width:1024px)").matches,
  fresh: window.__rompFoldMark === 1 }));
const deskHead = (page, g) => page.evaluate((g) => { const h = Array.from(document.querySelectorAll("#tabs .tab-group-head[data-group]")).find((x) => x.dataset.group === g);
  return h ? { folded: h.dataset.folded, count: (h.querySelector(".tab-group-count") || {}).textContent || null } : null; }, g);
const deskFresh = (page) => page.evaluate(() => window.__rompFoldMark === 1);
// any action that throws ends the run with what was measured so far, never an uncaught stack
async function run() {

// the DESKTOP: a mouse, a wide window
const desk = await browser.newContext({ viewport: { width: 1400, height: 800 } });
const dpage = await desk.newPage();
await dpage.goto(cfg.chat);
await wait(dpage, (n) => document.querySelectorAll("#tabs .tab[data-id]").length === n, cfg.count, "the desktop strip never showed every session");
await wait(dpage, () => document.querySelectorAll("#tabs .tab-group-head[data-group]").length === 2, null, "the desktop strip never sectioned");
// the PHONE: a coarse pointer under 1024 px (the kernel's own media rule); its own context, so its own localStorage
const phoneCtx = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true, deviceScaleFactor: 3 });
const page = await phoneCtx.newPage();
await page.goto(cfg.chat);
await wait(page, (n) => document.querySelectorAll("#tabs .tab[data-id]").length === n, cfg.count, "the phone strip never showed every session");
await wait(page, () => document.querySelectorAll("#tabs .tab-group-head[data-group]").length === 2, null, "the phone strip never sectioned");
// each page has heard the kernel's folds (its publisher is installed only then): the frame is the event, not a clock
for (const p of [dpage, page]) await wait(p, () => typeof window.__rompPublishViewFolds === "function", null, "a page never heard the kernel's folds");
// the no-reload witness: a property on each page's window, gone if anything reloads it
for (const p of [dpage, page]) await p.evaluate(() => { window.__rompFoldMark = 1; });
await page.tap("#mcur");
await wait(page, () => !!document.querySelector("#mlist.open"), null, "the picker never opened");
await wait(page, (n) => document.querySelectorAll("#mlist .mrow[data-id]").length === n, cfg.count, "the picker never listed every session");
out.start = { desk: await readDesk(dpage), phone: await readPhone(page), store: store() };

// 1. the DESKTOP folds qa with a real click on its header
await dpage.click('#tabs .tab-group-head[data-group="qa"]');
await wait(dpage, () => { const h = document.querySelector('#tabs .tab-group-head[data-group="qa"]'); return !!h && h.dataset.folded === "1"; }, null, "the desktop header never folded");
await wait(page, () => { const h = document.querySelector('#mlist .mhead[data-group="qa"]'); return !!h && h.classList.contains("folded"); }, null, "the phone picker never folded qa");
out.foldedOnDesk = { desk: await readDesk(dpage), deskHead: await deskHead(dpage, "qa"), phone: await readPhone(page), store: store() };

// 2. the PHONE opens it again from the picker's heading, a real tap
await page.tap('#mlist .mhead[data-group="qa"]');
await wait(page, () => { const h = document.querySelector('#mlist .mhead[data-group="qa"]'); return !!h && !h.classList.contains("folded"); }, null, "the phone heading never opened");
await wait(dpage, () => { const h = document.querySelector('#tabs .tab-group-head[data-group="qa"]'); return !!h && h.dataset.folded === "0"; }, null, "the desktop never followed the phone's open");
out.openedOnPhone = { desk: await readDesk(dpage), deskFresh: await deskFresh(dpage), phone: await readPhone(page), store: store() };

// 3. the ACTIVE session's group: the phone picks web, then the desktop folds infra
await page.tap('#mlist .mrow[data-id="' + cfg.web + '"]');
await wait(page, (id) => { const a = document.querySelector("#tabs .tab.active[data-id]"); return !!a && a.dataset.id === id; }, cfg.web, "the phone never opened web");
out.pickedWeb = { phone: await readPhone(page) };
await dpage.click('#tabs .tab-group-head[data-group="infra"]');
await wait(page, () => { const h = document.querySelector('#tabs .tab-group-head[data-group="infra"]'); return !!h && h.dataset.folded === "1"; }, null, "the phone never folded infra");
if (!(await page.$("#mlist.open"))) await page.tap("#mcur");
await wait(page, () => !!document.querySelector("#mlist.open"), null, "the picker never reopened");
await wait(page, () => { const h = document.querySelector('#mlist .mhead[data-group="infra"]'); return !!h && h.classList.contains("folded"); }, null, "the picker never folded infra");
out.activeFolded = { phone: await readPhone(page), store: store() };
await page.tap('#mlist .mhead[data-group="infra"]');
await wait(page, (id) => !!document.querySelector('#mlist .mrow.active[data-id="' + id + '"]'), cfg.web, "web's row never came back");
out.activeOpened = { phone: await readPhone(page), desk: await readDesk(dpage), store: store() };
}
await run().then(() => finish(null), (e) => finish("an action failed: " + String(e && e.message || e).split("\n")[0]));
"""


class SharedFoldsBrowser(unittest.TestCase):
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
        cls.lab = tempfile.mkdtemp(prefix="shared-folds-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            raise unittest.SkipTest("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
        dist = os.path.join(cls.lab, "dist")
        copy_dist(os.path.join(EXT, "dist"), dist)
        state = os.path.join(cls.lab, "xdg", "romp")
        claude = os.path.join(cls.lab, "claude")
        cwd = os.path.join(cls.lab, "proj")
        for d in ("names", "sdk", "states"):
            os.makedirs(os.path.join(state, d), exist_ok=True)
        Path(state, "session-hosts").write_text("off\n")   # a lab root of its own: no per-session host process (CLAUDE.md, 2026-09-11)
        # the machine's user manager is not the lab's: these shadow systemctl and systemd-run on the lab kernel's PATH, so
        # the boot reconcile's scope listing (it lists for every session it finds alive) sees an empty manager
        fakebin = os.path.join(cls.lab, "fakebin")
        os.makedirs(fakebin)
        for tool, body in (("systemctl", "exit 0\n"), ("systemd-run", "echo 'no user manager in this lab' >&2\nexit 1\n")):
            Path(fakebin, tool).write_text("#!/bin/sh\n" + body)
            os.chmod(os.path.join(fakebin, tool), 0o755)
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
            os.utime(Path(proj, sid + ".jsonl"), (t0 + i, t0 + i))
        Path(state, "timeline-views.json").write_text(json.dumps({"active": "all", "tags": TAGS, "tagOrder": TAG_ORDER}))
        Path(state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 10}, "seven_day": {"pct": 10}}))
        cls.state = state
        cls.port, cls.token = _free_port(), "testtok-sharedfolds"
        env = _lab.kernel_env(cls.lab, claude, dist, cls.port, cls.token, ROMP_HOST_NAME="TESTHOST", ROMP_CLI_SCOPE="0")
        env["PATH"] = fakebin + os.pathsep + env.get("PATH", os.environ.get("PATH", ""))
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
            k.kill(); k.wait()   # the exact process this class started, and nothing else
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
                       "web": SIDS["web"], "foldsFile": os.path.join(cls.state, "view-folds.json")}, f)
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
            raise AssertionError("driver printed no result:\n" + p.stdout[-3000:] + p.stderr[-3000:])
        result = json.loads(Path(out).read_text())
        if result.get("died"):
            raise AssertionError("driver stopped: %s\nso far: %s\nkernel:\n%s" % (result["died"], json.dumps(result)[-2500:], open(cls.klog).read()[-1500:]))
        return result

    @staticmethod
    def named(seq):
        def one(tok):
            if tok.startswith("t:"):
                sid, _, rest = tok[2:].partition("(")
                return "t:" + NAME_OF.get(sid, sid) + ("(" + rest if rest else "")
            return tok
        return [one(t) for t in seq]

    # ── the premise ──
    def test_the_two_contexts_are_a_desktop_and_a_phone_with_every_group_open(self):
        r = self._run()["start"]
        self.assertTrue(r["phone"]["phoneLayout"], "a coarse pointer at 390 px: the kernel's phone rule holds")
        desk = self.named(r["desk"])
        self.assertEqual([t for t in desk if t.startswith("g:")], ["g:qa", "g:infra"], "the groups, in tag order")
        self.assertEqual({t for t in desk if t.startswith("t:")}, {"t:" + n for n in NAMES}, "every session on the strip")
        self.assertEqual([t for t in self.named(r["phone"]["rows"]) if t.startswith("g:")], ["g:qa", "g:infra"], "the picker's headings alike")
        self.assertNotIn("(folded)", " ".join(r["desk"] + r["phone"]["rows"]), "nothing folded to start")
        self.assertIsNone(r["store"], "the kernel keeps no folds before anyone folds")

    # ── 1: folded on the desktop, folded on the phone ──
    def test_a_group_folded_on_the_desktop_is_folded_in_the_phone_picker_without_a_reload(self):
        r = self._run()["foldedOnDesk"]
        rows = self.named(r["phone"]["rows"])
        self.assertIn("g:qa(folded)", rows, "the phone's heading folded: %s" % rows)
        self.assertFalse({"t:tests", "t:docs"} & set(t.split("(")[0] for t in rows), "none of qa's sessions listed: %s" % rows)
        self.assertTrue(r["phone"]["fresh"], "no reload: the kernel's push was the event")
        self.assertTrue(r["phone"]["listOpen"], "the list the person had open stays open")
        head = r["phone"]["heads"]["qa"]
        self.assertEqual((head["expanded"], head["count"], head["role"], head["caret"]), ("false", r["deskHead"]["count"], "button", True),
                         "the heading's words are the desktop header's: its fold state, the same folded count, a button with a caret")
        self.assertEqual(r["deskHead"]["count"], "2", "the desktop header counts the two it hides")
        self.assertIn("g:qa(folded)", self.named(r["desk"]))
        self.assertEqual(r["store"], {"collapsed": ["qa"], "expanded": [], "pinned": []}, "the kernel keeps the fold")

    def test_the_heading_is_a_tap_target_a_finger_lands_on(self):
        r = self._run()["foldedOnDesk"]
        self.assertGreaterEqual(r["phone"]["heads"]["qa"]["height"], 40, "the heading is at least 40 px tall on the phone")

    # ── 2: opened on the phone, open on the desktop ──
    def test_a_group_opened_from_the_phone_heading_opens_on_the_desktop_without_a_reload(self):
        r = self._run()["openedOnPhone"]
        rows = self.named(r["phone"]["rows"])
        self.assertIn("g:qa", rows)
        self.assertTrue({"t:tests", "t:docs"} <= set(t.split("(")[0] for t in rows), "qa's sessions listed again: %s" % rows)
        self.assertTrue(r["phone"]["listOpen"], "the heading's tap left the list open for the pick")
        self.assertEqual(r["phone"]["heads"]["qa"]["expanded"], "true")
        desk = self.named(r["desk"])
        self.assertIn("g:qa", desk)
        self.assertTrue({"t:tests", "t:docs"} <= set(desk), "the desktop strip shows qa's tabs again: %s" % desk)
        self.assertTrue(r["deskFresh"], "the desktop followed without a reload")
        self.assertEqual(r["store"], {"collapsed": [], "expanded": [], "pinned": []})

    # ── 3: the active session's group ──
    def test_the_active_sessions_group_folds_like_any_other_and_the_chip_still_names_the_session(self):
        r = self._run()
        self.assertEqual(r["pickedWeb"]["phone"]["current"], "web", "premise: the phone is on web")
        a = r["activeFolded"]["phone"]
        rows = self.named(a["rows"])
        self.assertIn("g:infra(folded)", rows)
        self.assertNotIn("t:web", [t.split("(")[0] for t in rows], "web's row folds away with its group, as its tab does on the desktop")
        self.assertEqual(a["heads"]["infra"]["current"], "true", "the heading stands in for it, marked current (the desktop header's aria-current)")
        self.assertEqual(a["current"], "web", "the current-session chip still names the session the person is in")
        self.assertEqual([NAME_OF.get(x, x) for x in a["away"]], ["web"], "mirrored from the folded-away tab the page paints for the chip")
        self.assertEqual(r["activeFolded"]["store"]["collapsed"], ["infra"])

    def test_opening_the_active_sessions_group_brings_its_row_back_marked_active(self):
        o = self._run()["activeOpened"]
        rows = self.named(o["phone"]["rows"])
        self.assertIn("t:web(active)", rows, rows)
        self.assertEqual(o["phone"]["away"], [], "the tab itself is on the strip again: no stand-in node")
        self.assertEqual(o["phone"]["current"], "web")
        self.assertIn("g:infra", self.named(o["desk"]), "and the desktop followed")


if __name__ == "__main__":
    unittest.main()
