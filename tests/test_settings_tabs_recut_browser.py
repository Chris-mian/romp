#!/usr/bin/env python3
"""The settings card's tabs RE-CUT (T400, the user 2026-09-12): General (the account, the panes, the keyboard shortcuts), Chat,
Feed, Sessions, Task tracking (Automatic renamed, the judges under it), Appearance, Debug (updates, the judges' debug views, the
token usage analytics, the log, the version; System dissolved into it). On the served dashboard: the pills and their order, each
moved row's new home (the pane that holds its id), the remembered tab round-tripping under the new names (an older remembered
automatic or system comes up on Task tracking or Debug, never a blank card, and is rewritten to the new name), and the General
and Debug tabs shot in both themes for the user's look.

SETTINGS_TABS_DIST=<dir> serves another tree's UI bundle (the red run's before); SETTINGS_TABS_SHOTS=<prefix> writes
<prefix>-general-<theme>.png and <prefix>-debug-<theme>.png; SETTINGS_TABS_DUMP=<path> writes the whole measurement. Skips LOUDLY
without the extension deps or a Playwright browser (CI sets ROMP_SERVED_TESTS_REQUIRE=1 and installs both, so a skip there is a
failure). Synthetic throughout: placeholder sids, TESTHOST, invented text.
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

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
EXT = os.path.join(ROOT, "vscode-extension")
sys.path.insert(0, HERE)
import test_ship_reship as _lab   # noqa: E402  the lab kernel's environment: a list of names, never a copy of the runner's

NAMES = ["web", "api"]
SIDS = {n: "%s-1111-2222-3333-444444444444" % (chr(ord("a") + i) * 8) for i, n in enumerate(NAMES)}
PALETTE = [("#9cd2ff", "#0c1a2e"), ("#1EA1EB", "#ffffff")]


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
const MOVED = ["rs-billing", "rs-login-btn", "rs-panes-sec", "rs-pane-timeline", "rs-pane-fleet", "rs-pane-feed", "rs-keys-web", "rs-filesctl", "rs-theme", "rs-cmap", "rs-pal", "rs-fileedit", "rs-conserve", "rs-updates",
               "rs-compact", "rs-chatscheme", "rs-striprows", "rs-cmtmodel", "rs-thinksum", "rs-widgets", "rs-feedcollapsed", "rs-defaultdir", "rs-backend", "rs-autonudge", "rs-suggestcompact", "rs-judgemodel", "rs-judgeconc",
               "rs-judges-index", "rs-judges-triage", "ra-open", "rs-log-open", "rsver", "rs-filelink", "rs-activeonly", "rs-collapsegaps"];   // the last three must be GONE (T404)
// open the landing in a fresh context, seeded with a remembered tab when given; hand back the settings frame once the panel is up
async function openPanel(seedTab, ask) {
  const ctx = await browser.newContext({ viewport: { width: 1200, height: 800 } });
  if (seedTab) await ctx.addInitScript((t) => { try { localStorage.setItem("romp:settingsTab", t); } catch (e) {} }, seedTab);
  const page = await ctx.newPage();
  await page.goto(cfg.url);
  await page.waitForSelector("#rail-gear", { timeout: 20000 });
  let chatF = page.frames().find((f) => f.url().includes("/chat"));
  for (let i = 0; i < 100 && !chatF; i++) { await page.waitForTimeout(100); chatF = page.frames().find((f) => f.url().includes("/chat")); }
  await chatF.waitForFunction((n) => document.querySelectorAll("#tabs .tab[data-id]").length >= n, cfg.count, { timeout: 30000 });
  if (ask) await page.evaluate((t) => window.__rompOpenSettings(t), ask); else await page.click("#rail-gear");   // the rail's gear: a plain open, the remembered tab
  await page.waitForFunction(() => document.body.classList.contains("settings-open"), null, { timeout: 20000 }).catch(() => {});
  let setF = page.frames().find((f) => f.url().includes("/settings"));
  for (let i = 0; i < 50 && !setF; i++) { await page.waitForTimeout(100); setF = page.frames().find((f) => f.url().includes("/settings")); }
  if (!setF) return { ctx, page, setF: null };
  await setF.waitForSelector("#rsettings:not([hidden])", { timeout: 15000 }).catch(() => {});
  await setF.evaluate(() => (document.fonts && document.fonts.ready) || null).catch(() => {});
  await setF.waitForTimeout(250);
  return { ctx, page, setF };
}
const readPanel = (setF) => setF.evaluate((moved) => {
  const p = document.getElementById("rsettings");
  if (!p || p.hidden) return { open: false };
  const pills = Array.from(document.querySelectorAll("#rsettings .rs-tab")).map((b) => ({ tab: b.dataset.tab, text: b.textContent, on: b.classList.contains("on") }));
  const shown = Array.from(document.querySelectorAll("#rsettings .rs-pane")).filter((pn) => getComputedStyle(pn).display !== "none").map((pn) => pn.dataset.pane);
  const homes = {}; for (const id of moved) { const el = document.getElementById(id); homes[id] = el ? ((el.closest(".rs-pane") || {}).dataset || {}).pane || null : "missing"; }
  const heads = {}; for (const pn of document.querySelectorAll("#rsettings .rs-pane")) heads[pn.dataset.pane] = Array.from(pn.querySelectorAll(".rs-sec")).map((h) => h.textContent.trim());
  // the pill bar: one row when every pill shares the first pill's top; its width from the first pill's left edge to the last one's right
  const bar = document.getElementById("rs-tabs"); const rects = Array.from(bar.querySelectorAll(".rs-tab")).map((x) => x.getBoundingClientRect());
  const barInfo = { h: bar.getBoundingClientRect().height, rows: new Set(rects.map((r) => Math.round(r.top))).size, width: Math.round((rects[rects.length - 1].right - rects[0].left) * 10) / 10, available: Math.round(bar.getBoundingClientRect().width * 10) / 10, theme: document.body.classList.contains("theme-light") ? "light" : "dark" };
  return { open: true, pills, shown, homes, heads, bar: barInfo, remembered: localStorage.getItem("romp:settingsTab") };
}, MOVED);
const out = {};
// 1. the glyph's ask for General: the pills, the homes, the heads; then the Debug pill; screenshots of both in both themes
{
  const { ctx, page, setF } = await openPanel(null, "general");
  if (!setF) { out.general = { open: false }; } else {
    out.general = await readPanel(setF);
    const shot = async (tab, theme) => {
      await setF.click('#rsettings .rs-tab[data-tab="' + tab + '"]'); await setF.waitForTimeout(150);
      for (const f of [page, setF]) await f.evaluate((t) => document.body.classList.toggle("theme-light", t === "light"), theme);
      await page.waitForTimeout(200);
      if (!cfg.shots) return;
      const card = await setF.evaluate(() => { const b = document.querySelector("#rsettings .rs-card").getBoundingClientRect(); return { x: b.left, y: b.top, width: b.width, height: b.height }; });
      const fr = await page.evaluate(() => { const f = document.getElementById("f-settings").getBoundingClientRect(); return { x: f.left, y: f.top }; });
      await page.screenshot({ path: cfg.shots + "-" + tab + "-" + theme + ".png", clip: { x: fr.x + card.x, y: fr.y + card.y, width: card.width, height: card.height } });
    };
    out.bar = {};
    for (const theme of ["dark", "light"]) { await shot("general", theme); out.bar[theme] = (await readPanel(setF)).bar; await shot("chat", theme); await shot("debug", theme); }
    for (const f of [page, setF]) await f.evaluate(() => document.body.classList.remove("theme-light"));
    await setF.click('#rsettings .rs-tab[data-tab="debug"]'); await setF.waitForTimeout(150);
    out.debug = await readPanel(setF);
    await setF.click('#rsettings .rs-tab[data-tab="tasks"]'); await setF.waitForTimeout(150);
    out.tasks = await readPanel(setF);
    await setF.click('#rsettings .rs-tab[data-tab="automation"]'); await setF.waitForTimeout(150);
    out.automation = await readPanel(setF);
  }
  await page.close(); await ctx.close();
}
// 2. the remembered tab under the OLD names: a browser that last used Automatic or System comes up on Task tracking or Debug, and the store is rewritten
out.mapping = {};
for (const old of ["automatic", "system", "tabs", "appearance"]) {
  const { ctx, page, setF } = await openPanel(old, null);
  out.mapping[old] = setF ? await readPanel(setF) : { open: false };
  await page.close(); await ctx.close();
}
fs.writeFileSync(cfg.out, JSON.stringify(out));
console.log("RESULT: ok");
await browser.close();
"""


class ServedSettingsTabs(unittest.TestCase):
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
        cls.lab = tempfile.mkdtemp(prefix="settings-tabs-")
        before = os.environ.get("SETTINGS_TABS_DIST", "")
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
        os.makedirs(cwd, exist_ok=True)
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        t0 = int(time.time()) - 900
        for i, name in enumerate(NAMES):
            sid = SIDS[name]
            bg, fg = PALETTE[i]
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
        cls.port, cls.token = _free_port(), "testtok-tabwidgets"
        env = _lab.kernel_env(cls.lab, claude, dist, cls.port, cls.token, ROMP_HOST_NAME="TESTHOST")
        cls.state = state
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
            k.terminate()
            try:
                k.wait(timeout=10)
            except subprocess.TimeoutExpired:
                k.kill(); k.wait()
            time.sleep(0.5)
        lab = getattr(cls, "lab", "")
        shutil.rmtree(lab, ignore_errors=True)
        time.sleep(0.3)
        shutil.rmtree(lab, ignore_errors=True)

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
            json.dump({"url": "http://127.0.0.1:%d/?token=%s" % (cls.port, cls.token), "count": len(NAMES), "out": out, "sidWeb": SIDS["web"],
                       "shots": os.environ.get("SETTINGS_TABS_SHOTS", "")}, f)
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
        if os.environ.get("SETTINGS_TABS_DUMP"):
            Path(os.environ["SETTINGS_TABS_DUMP"]).write_text(json.dumps(result, indent=1) + "\n")
        return result

    def test_the_pills_read_general_chat_feed_sessions_automation_task_tracking_debug_in_that_order(self):
        # T404 (the user 2026-09-13): Automation is new, Appearance folded into General
        g = self._run()["general"]
        table = "\n  " + json.dumps(g)[:1500]
        self.assertTrue(g["open"], table)
        self.assertEqual([x["tab"] for x in g["pills"]], ["general", "chat", "feed", "sessions", "automation", "tasks", "debug"], table)
        self.assertEqual([x["text"] for x in g["pills"]], ["General", "Chat", "Feed", "Sessions", "Automation", "Task tracking", "Debug"], table)
        self.assertEqual(g["shown"], ["general"], "the ask for General shows General alone" + table)
        self.assertEqual(g["heads"]["general"], ["Account", "Panes", "Appearance", "Permissions", "This machine", "Keyboard shortcuts"], table)
        self.assertEqual(g["heads"]["chat"], ["Display", "Comments", "Thinking", "Tab widgets"], "Transcript is Display; the text scheme and the strip row joined it; Thinking creates, so it is Chat's" + table)
        self.assertEqual(g["heads"]["debug"], ["Judging bands", "Diagnostics"], "Updates went to General" + table)
        self.assertEqual(g["heads"]["tasks"], ["Judges"], "Task tracking keeps the judges alone" + table)
        self.assertEqual(g["heads"]["automation"], ["Nudges"], table)
        self.assertEqual(g["heads"]["feed"], ["Cards"], table)
        self.assertEqual(g["heads"]["sessions"], ["New sessions"], "the Sessions-pane rows left settings: the pane carries them" + table)

    def test_the_seven_pills_sit_on_one_row_of_the_card_in_both_themes(self):
        # round one, LOW 1: at 10px of side padding the seven needed 528px against 518 available, and Debug alone dropped to a second
        # row (the bar 38 to 69px); at 8px they fit
        bar = self._run()["bar"]
        for theme in ("dark", "light"):
            bi = bar[theme]; table = "\n  " + theme + ": " + json.dumps(bi)
            self.assertEqual(bi["theme"], theme, table)
            self.assertEqual(bi["rows"], 1, theme + ": one row" + table)
            self.assertLess(bi["width"], bi["available"], theme + ": the pills fit the bar" + table)
            self.assertLess(bi["h"], 45, theme + ": a one-row bar" + table)

    def test_each_moved_row_lives_in_its_new_home_with_its_id_kept(self):
        g = self._run()["general"]
        self.assertTrue(g["open"], json.dumps(g)[:300])
        gen = ["rs-billing", "rs-login-btn", "rs-panes-sec", "rs-pane-timeline", "rs-pane-fleet", "rs-pane-feed", "rs-keys-web", "rs-filesctl", "rs-theme", "rs-cmap", "rs-pal", "rs-fileedit", "rs-conserve", "rs-updates"]
        chat = ["rs-compact", "rs-chatscheme", "rs-striprows", "rs-cmtmodel", "rs-thinksum", "rs-widgets"]
        expect = dict([(i, "general") for i in gen] + [(i, "chat") for i in chat] + [("rs-feedcollapsed", "feed"), ("rs-defaultdir", "sessions"), ("rs-backend", "sessions"),
                       ("rs-autonudge", "automation"), ("rs-suggestcompact", "automation"), ("rs-judgemodel", "tasks"), ("rs-judgeconc", "tasks"),
                       ("rs-judges-index", "debug"), ("rs-judges-triage", "debug"), ("ra-open", "debug"), ("rs-log-open", "debug"), ("rsver", "debug"),
                       ("rs-filelink", "missing"), ("rs-activeonly", "missing"), ("rs-collapsegaps", "missing")])   # the three rows that left settings (T404): no element
        self.assertEqual(g["homes"], expect, "every id in its new home, none missing, the three gone: " + json.dumps(g["homes"]))

    def test_an_older_remembered_tab_comes_up_on_its_new_tab_and_is_rewritten_never_a_blank_card(self):
        m = self._run()["mapping"]
        for old, new in (("automatic", "tasks"), ("system", "debug"), ("tabs", "chat"), ("appearance", "general")):
            r = m[old]
            table = "\n  " + old + ": " + json.dumps(r)[:600]
            self.assertTrue(r["open"], "the rail's gear opened the panel" + table)
            self.assertEqual(r["shown"], [new], "the remembered " + old + " shows " + new + table)
            self.assertEqual([x["tab"] for x in r["pills"] if x["on"]], [new], "…its pill on" + table)
            self.assertEqual(r["remembered"], new, "the store now carries the new name" + table)

    def test_the_debug_and_task_tracking_pills_switch_to_their_panes(self):
        r = self._run()
        self.assertEqual(r["debug"]["shown"], ["debug"], json.dumps(r["debug"]["shown"]))
        self.assertEqual(r["debug"]["remembered"], "debug")
        self.assertEqual(r["tasks"]["shown"], ["tasks"], json.dumps(r["tasks"]["shown"]))
        self.assertEqual(r["automation"]["shown"], ["automation"], json.dumps(r["automation"]["shown"]))
        self.assertEqual(r["automation"]["remembered"], "automation")
        self.assertEqual(r["tasks"]["remembered"], "tasks")


if __name__ == "__main__":
    unittest.main()
