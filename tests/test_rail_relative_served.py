#!/usr/bin/env python3
"""T406 (the user 2026-09-13): the chat rail's time markers for TODAY read how long ago, in the user's words ("now",
"1 min ago", "N min ago", "1 hour ago", "N hours ago"), the exact HH:MM riding each stamp's tooltip; any other
day keeps the clock time exactly as before, its day divider naming the day. Proven on the real /chat page of a hermetic
kernel with the browser's clock INSTALLED (Playwright's fake clock, started at the epoch the fixture was stamped from and
flowing), two synthetic sessions: `web`, two rows yesterday then six today, spaced so every word of the vocabulary shows
("2 hours ago", "1 hour ago", "59 min ago", "5 min ago", "1 min ago", "now"); `api`, four rows all yesterday. Asserted in both
themes: every today stamp reads the label the vocabulary gives for its calendar-minute distance from the page's own clock,
the plural-hours form with "ago" on a line of its own, stamped only where the label CHANGES from the previous timed row's
(the rail's same-minute rule at the label's grain), its title the row's HH:MM; every other-day marker is the HH:MM with no
class and no title; no label overflows the 56px slot (the marker's scrollWidth is its clientWidth) or reaches the dot;
two-line stamps never overlap the next stamp; and the vocabulary's widest forms are measured in the marker's own font per
theme at the default 13px chat font and at 14px, for the record the user asked for (the one-line forms fit the slot at
13px; at 14px the two-digit minute forms are wider than the slot and pre-line wraps them at their space, so nothing ever
overhangs toward the dot). Across the tick a marker whose label did not change is not touched at all (no mutation
records; a selection spanning its stamp survives): the painter writes only what differs. Then the page's clock is
paused and jumped past the next clock-minute boundary: the rail's ONE minute timer fires, the labels move by a minute (the
row "now" reads "1 min ago"; the row at 59 minutes reads "1 hour ago", the same as the row before it, so its stamp goes
quiet), the yesterday markers do
not change, and every turn's box (top, height, left, width) is exactly where it was: the transcript did not move. The
sticky stamp over a today turn scrolled past the top line wears the same two-line label. With RT_SHOTS=<dir> the driver
writes screenshots: the today run (`web`) and the yesterday run (`api`), dark and light. Skips LOUDLY without the extension
deps or a Playwright browser; the extension CI job installs Chromium and runs served files with ROMP_SERVED_TESTS_REQUIRE=1,
which turns any skip into a failure there. SYNTHETIC fixtures only (sessions web and api, the notes-api demo world)."""
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
import test_ship_reship as _lab   # noqa: E402  the lab kernel's environment (the module, not its classes)

SID_A = "aaaaaaaa-1111-2222-3333-444444444444"   # web: two rows yesterday, six today (the today run)
SID_B = "bbbbbbbb-1111-2222-3333-444444444444"   # api: four rows yesterday (the yesterday run)

# the today rows' distance from the fixture's clock, oldest first: one label of each kind
TODAY_OFFSETS = [125 * 60, 60 * 60, 59 * 60, 5 * 60, 60, 5]


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _local_day(days_ago, hour, minute, now):
    """An epoch on the LOCAL day `days_ago` days before `now` at hour:minute (the chat's day keys are the browser's local
    time, the same machine's as this runner's)."""
    lt = time.localtime(now)
    base = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, hour, minute, 0, 0, 0, -1))
    return int(base) - days_ago * 86400


def relative_label(epoch, now_ms):
    """The Python twin of time-marker.ts relativeLabel: the words for a row of the page's local today, "" for any other
    day; calendar minutes (the clock's minute of the row against the clock's minute now)."""
    d, n = time.localtime(epoch), time.localtime(now_ms / 1000)
    if (d.tm_year, d.tm_yday) != (n.tm_year, n.tm_yday):
        return ""
    mins = max(0, now_ms // 60000 - epoch // 60)
    if mins < 1:
        return "now"
    if mins < 60:
        return "%d min ago" % mins
    h = mins // 60
    return "1 hour ago" if h == 1 else "%d hours ago" % h


def relative_lines(label):
    """The twin of relativeLines: the plural-hours form alone takes "ago" on a line of its own."""
    return re.sub(r" ago$", "\nago", label) if re.match(r"^\d+ hours ago$", label) else label


def _records(sid, now, shift):
    def user(uuid, parent, t, text):
        return {"type": "user", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent, "promptSource": "typed", "sessionId": sid,
                "message": {"role": "user", "content": text}}
    def asst(uuid, parent, t, text):
        return {"type": "assistant", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent, "sessionId": sid,
                "message": {"role": "assistant", "model": "claude-opus-5", "stop_reason": "end_turn", "content": [{"type": "text", "text": text}]}}
    if shift == 0:
        y = _local_day(1, 10, 0, now)
        t = [now - o for o in TODAY_OFFSETS]
        return [
            user("u1", None, y, "how should the notes-api retry loop back off?"),
            asst("a1", "u1", y + 60, "Use exponential backoff with a jitter of ten percent."),
            user("u2", "a1", t[0], "please run the notes-api search suite"),
            asst("a2", "u2", t[1], "The search suite is green."),
            user("u3", "a2", t[2], "and the docs suite after it"),
            asst("a3", "u3", t[3], "The docs suite is green too; the search module is done."),
            user("u4", "a3", t[4], "open a pull request for the search module"),
            asst("a4", "u4", t[5], "The pull request is open and its checks are running."),
        ]
    y0 = _local_day(1, 9, 5, now)
    return [
        user("u1", None, y0, "please run the notes-api search suite"),
        asst("a1", "u1", y0 + 60, "Running the search suite now."),
        user("u2", "a1", y0 + 300, "and the docs suite after it"),
        asst("a2", "u2", y0 + 360, "Both suites are green; the search module is done."),
    ]


DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));
let browser;
try { browser = await chromium.launch(); }
catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
const page = await browser.newPage({ viewport: { width: 1100, height: 760 }, deviceScaleFactor: 2 });
await page.clock.install({ time: cfg.nowMs });   // the page's clock starts at the epoch the fixture was stamped from and FLOWS; timers are the fake clock's, so a jump past a minute boundary fires the rail's tick
await page.goto(cfg.chat);
await page.waitForSelector("#tabs .tab[data-id]", { timeout: 20000 });
const show = async (sid, turns) => {
  await page.click('#tabs .tab[data-id="' + sid + '"]');
  await page.waitForFunction((n) => Array.from(document.querySelectorAll("#content .turn")).filter((t) => t.offsetParent !== null).length >= n, turns, { timeout: 30000 });
  await page.mouse.move(700, 600); await page.waitForTimeout(500);
};
const theme = async (light) => {
  await page.evaluate((l) => document.body.classList.toggle("theme-light", l), light);
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(300);
};
const measure = () => page.evaluate(() => {
  const turn0 = Array.from(document.querySelectorAll("#content .turn")).find((t) => t.offsetParent !== null);
  const kids = Array.from(turn0.parentElement.children);
  const threadTop = turn0.parentElement.getBoundingClientRect().top;   // boxes are read against the thread, so a pane that scrolled between two readings is not a layout shift
  const rows = kids.map((n) => {
    const m = n.querySelector(":scope > .time-marker");
    const r = n.getBoundingClientRect(), mr = m ? m.getBoundingClientRect() : null;
    return { cls: n.className, isDiv: n.classList.contains("day-divider"),
             label: n.classList.contains("day-divider") ? n.querySelector(".day-divider-label").textContent : null,
             marker: m ? m.textContent : null, title: m ? m.getAttribute("title") : null, rel: m ? m.classList.contains("rel") : null,
             epoch: m ? m.dataset.epoch : null, hm: m ? m.dataset.hm : null,
             box: [r.top - threadTop, r.height, r.left, r.width],
             mBox: mr ? { top: mr.top, bottom: mr.bottom, right: mr.right, width: mr.width, height: mr.height } : null,
             overflow: m ? m.scrollWidth - m.clientWidth : null,
             dotLeft: n.querySelector(":scope > .dot") ? n.querySelector(":scope > .dot").getBoundingClientRect().left : null };
  });
  // the vocabulary's widest forms in the marker's OWN font, per theme, at the default chat font and at 14px (the fit
  // the user asked to have measured); the second reading gives the probe the size a 14px chat font gives a marker
  const probe = document.createElement("span"); probe.className = "time-marker";
  probe.style.cssText = "position:static;display:inline-block;width:auto;white-space:nowrap;visibility:hidden";
  turn0.appendChild(probe);
  const widths = {}, widths14 = {};
  const FORMS = ["now", "1 min ago", "9 min ago", "59 min ago", "1 hour ago", "2 hours ago", "23 hours ago", "59 min", "2 hours", "23 hours"];
  for (const l of FORMS) { probe.textContent = l; widths[l] = Math.round(probe.getBoundingClientRect().width * 10) / 10; }
  probe.style.fontSize = "10.08px";   // what a 14px chat font gives the marker (0.72em); the page's own --fs is not touched
  for (const l of FORMS) { probe.textContent = l; widths14[l] = Math.round(probe.getBoundingClientRect().width * 10) / 10; }
  probe.style.fontSize = "";
  const cs = getComputedStyle(probe); const font = cs.fontFamily.split(",")[0].replace(/"/g, "") + " " + cs.fontSize
    + (document.fonts.check('9px "Space Grotesk"') ? " (Space Grotesk loaded)" : " (Space Grotesk not loaded)") + (document.fonts.check('9px "Inter"') ? " (Inter loaded)" : " (Inter not loaded)");
  probe.remove();
  const s = document.querySelector(".rail-sticky"); const sr = s ? s.getBoundingClientRect() : null;
  return { now: Date.now(), scrollTop: document.getElementById("content").scrollTop, rows, widths, widths14, font, slot: getComputedStyle(kids.find((n) => n.querySelector(":scope > .time-marker")).querySelector(":scope > .time-marker")).width,
           theme: document.body.classList.contains("theme-light") ? "light" : "dark",
           sticky: s && getComputedStyle(s).display !== "none" ? { text: s.textContent, rel: s.classList.contains("rel"), height: sr.height, width: sr.width } : null };
});
const shot = async (name) => { if (!cfg.shots) return; fs.mkdirSync(cfg.shots, { recursive: true }); await page.screenshot({ path: cfg.shots + "/" + name + ".png", fullPage: false }); };
const out = { web: {}, api: {} };
await show(cfg.web, 8);
await theme(false); out.web.dark = await measure(); await shot("t406-today-dark");
await theme(true); out.web.light = await measure(); await shot("t406-today-light");
await show(cfg.api, 4);
out.api.light = await measure(); await shot("t406-yesterday-light");
await theme(false); out.api.dark = await measure(); await shot("t406-yesterday-dark");
// the clock's minute turns: pause the page's clock, jump past the next boundary (the tick is armed 50ms past it), let a frame run
await show(cfg.web, 8);
const cur = await page.evaluate(() => Date.now());
// a marker whose label does not change across the boundary must not be touched at all (round two): a replaced text
// node is four mutation records a minute per marker and destroys a selection that spans the stamp. Observe the
// two-hour and one-hour rows (their labels survive the minute) and select across the two-hour turn before the tick.
await page.evaluate(() => {
  const rel = Array.from(document.querySelectorAll("#content .turn")).filter((t) => t.offsetParent !== null && t.querySelector(":scope > .time-marker.rel"));
  const w = window;
  w.__t406 = { records: {} };
  for (const i of [0, 1]) {
    const m = rel[i].querySelector(":scope > .time-marker");
    const recs = []; w.__t406.records[String(i)] = recs;
    new MutationObserver((rs) => { for (const r of rs) recs.push(r.type + (r.attributeName ? ":" + r.attributeName : "")); })
      .observe(m, { childList: true, characterData: true, attributes: true, subtree: true });
  }
  const t = rel[0], m = t.querySelector(":scope > .time-marker");
  const c = document.getElementById("content");
  const scroll0 = c.scrollTop;
  const range = document.createRange(); range.setStart(m.firstChild, 0); range.setEndAfter(t.lastChild);
  const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(range);
  w.__t406.selBefore = sel.toString();
  w.__t406.scroll = [scroll0, c.scrollTop];   // the pane must not move for a programmatic selection
  t.dataset.probe = "1";
  w.__t406.steps = [];
  w.__t406.step = (name) => { const s2 = window.getSelection(); const c2 = document.getElementById("content");
    w.__t406.steps.push([name, s2.toString().length, s2.rangeCount, document.activeElement ? document.activeElement.tagName + "#" + document.activeElement.id : null,
                         !!document.querySelector("[data-probe]"), c2.scrollTop, c2.scrollHeight]); };
  w.__t406.step("selected");
});
await page.clock.pauseAt(cur + 100);
await page.evaluate(() => window.__t406.step("paused"));
const jump = 60000 - ((cur + 100) % 60000) + 300;
await page.clock.fastForward(jump);
// the painter's own work is done inside the jump (the tick's timer paints synchronously), so the probes read HERE. A
// frame later this fixture's transcript is rebuilt by a path outside the rail: the page's own retry scheduler (the
// one-second interval, apiRetryTick) fires during the jump for the lab's blocked session, whose API-error card is
// "retrying soon", and the answer rebuilds the view (the selected turn is detached, the pane re-lands at the bottom),
// which would hide what the painter did or did not do
await page.evaluate(() => { window.__t406.step("jumped"); const w = window; const sel = window.getSelection();
  w.__t406.atJump = { sel: sel.toString(), ranges: sel.rangeCount, records: JSON.parse(JSON.stringify(w.__t406.records)) }; });
await page.clock.runFor(200);
await page.evaluate(() => window.__t406.step("frame"));
out.web.ticked = await measure();
out.tick = { cur, jump };
out.web.quiet = await page.evaluate(() => {
  const w = window, sel = window.getSelection();
  w.__t406.step("measured");
  return { records: w.__t406.records, selBefore: w.__t406.selBefore, atJump: w.__t406.atJump, selAfterFrame: sel.toString(),
           scroll: w.__t406.scroll.concat([document.getElementById("content").scrollTop]), steps: w.__t406.steps };
});
// the sticky over a today turn: a short pane, the second today turn scrolled 20px past the top line, so its own stamp has crossed above and the sticky leads with its label
await page.setViewportSize({ width: 1100, height: 330 });
await page.evaluate(() => {
  const turns = Array.from(document.querySelectorAll("#content .turn")).filter((t) => t.offsetParent !== null && t.querySelector(":scope > .time-marker.rel"));
  const t = turns[1];
  const c = document.getElementById("content");
  c.style.paddingBottom = c.clientHeight + "px";
  // an INSTANT scroll: the page's clock is paused, so a smooth scroll (the pane's scroll-behavior) would never arrive
  c.scrollTo({ top: c.scrollTop + t.getBoundingClientRect().top - c.getBoundingClientRect().top + 20, behavior: "instant" });
});
await page.waitForTimeout(300);   // the scroll event is the browser's own frame, real time; only then does the handler ask for a (fake) animation frame
await page.clock.runFor(400);     // ...which the paused clock delivers here: the sticky's paint
await page.waitForTimeout(100);
out.web.stickyRun = await page.evaluate(() => {
  const turns = Array.from(document.querySelectorAll("#content .turn")).filter((t) => t.offsetParent !== null && t.querySelector(":scope > .time-marker.rel"));
  const t = turns[1], m = t.querySelector(":scope > .time-marker");
  const s = document.querySelector(".rail-sticky"); const sr = s.getBoundingClientRect();
  const c = document.getElementById("content"), cr = c.getBoundingClientRect();
  return { tracked: { marker: m.textContent, epoch: m.dataset.epoch, hidden: getComputedStyle(m).visibility === "hidden", top: t.getBoundingClientRect().top - cr.top },
           pane: [c.scrollTop, c.scrollHeight, c.clientHeight],
           sticky: getComputedStyle(s).display !== "none" ? { text: s.textContent, rel: s.classList.contains("rel"), height: sr.height, width: sr.width } : null,
           now: Date.now() };
});
if (cfg.shots) fs.writeFileSync(cfg.shots + "/t406-measure.json", JSON.stringify({ font: { dark: out.web.dark.font, light: out.web.light.font }, slot: out.web.dark.slot, dotGap: 3,
  widthsAt13px: { dark: out.web.dark.widths, light: out.web.light.widths }, widthsAt14px: { dark: out.web.dark.widths14, light: out.web.light.widths14 } }, null, 1));   // the fit the user asked to have measured, beside the screenshots
fs.writeSync(1, "RESULT:" + JSON.stringify(out) + "\n");
await browser.close();
process.exit(0);
"""


class ServedRailRelative(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        try:
            cls._boot()
        except BaseException:          # a skip OR a failure: never leave a kernel or a lab behind
            cls.tearDownClass()
            raise

    @classmethod
    def _boot(cls):
        if not os.path.isdir(os.path.join(EXT, "node_modules", "playwright")):
            raise unittest.SkipTest("extension deps absent (npm ci not run here) — the served guard needs them; CI's extension job has them and requires this file to run")
        probe = subprocess.run(["node", "-e", "const p=require(process.argv[1]);process.stdout.write(p.chromium.executablePath())",
                                os.path.join(EXT, "node_modules", "playwright")], capture_output=True, text=True)
        if probe.returncode != 0 or not os.path.exists(probe.stdout.strip()):
            raise unittest.SkipTest("no playwright browser on this box — the served guard needs one; CI's extension job installs Chromium and requires this file to run")
        cls.lab = tempfile.mkdtemp(prefix="rail-relative-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            raise unittest.SkipTest("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
        dist = os.path.join(cls.lab, "dist")
        copy_dist(os.path.join(EXT, "dist"), dist)
        state = os.path.join(cls.lab, "xdg", "romp")
        claude = os.path.join(cls.lab, "claude")
        for d in ("names", "sdk", "states"):
            os.makedirs(os.path.join(state, d), exist_ok=True)
        # ONE epoch for the fixture and the page's clock, 25s past a clock-minute boundary: the driver's measurements
        # (a few seconds of flowing fake time) stay inside that minute, so "now" is still now when read
        cls.now = int(time.time()) // 60 * 60 + 25
        for sid, name, shift, colour in ((SID_A, "web", 0, ("#9cd2ff", "#0c1a2e")), (SID_B, "api", 1, ("#ffd29c", "#2e1a0c"))):
            cwd = os.path.join(cls.lab, "proj-" + name)
            os.makedirs(cwd, exist_ok=True)
            Path(state, "names", sid).write_text("%s\t%s\t%s\t%s\n" % (name, cwd, colour[0], colour[1]))
            Path(state, "sdk", sid + ".json").write_text(json.dumps(
                {"sid": sid, "name": name, "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": sid, "alive": True,
                 "model": "claude-opus-5", "liveModel": "Opus 5"}))
            proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
            os.makedirs(proj, exist_ok=True)
            Path(proj, sid + ".jsonl").write_text("".join(json.dumps(r) + "\n" for r in _records(sid, cls.now, shift)))
        Path(state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 10}, "seven_day": {"pct": 10}}))
        cls.port, cls.token = _free_port(), "testtok-railrelative"
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

    def _expect_rail(self, m, where):
        """Every marker of a measured thread against the vocabulary at the page's own clock: a today row wears the label
        (two lines) where it changes from the previous timed row's, its HH:MM as title; any other row the HH:MM, no class,
        no title. Returns the today labels shown, in order."""
        now_ms, prev, shown = m["now"], "", []
        timed = [r for r in m["rows"] if r["marker"] is not None]
        self.assertTrue(timed, where)
        for r in timed:
            ep = int(r["epoch"])
            rel = relative_label(ep, now_ms)
            if rel:
                self.assertTrue(r["rel"], "%s: a today row's marker carries the class shown or not: %r" % (where, r))
                if rel != prev:
                    self.assertEqual(r["marker"], relative_lines(rel), "%s: the label at %s, 'ago' on its own line: %r" % (where, r["hm"], r))
                    self.assertEqual(r["title"], r["hm"], "%s: the tooltip is the exact time in the rail's own style: %r" % (where, r))
                    shown.append(rel)
                else:
                    self.assertEqual((r["marker"], r["title"]), ("", None), "%s: the same label as the row before stamps nothing (the same-minute rule at the label's grain): %r" % (where, r))
            else:
                self.assertFalse(r["rel"], "%s: another day's marker is untouched: %r" % (where, r))
                self.assertIsNone(r["title"], "%s: ...and has no tooltip: %r" % (where, r))
                self.assertIn(r["marker"], ("", r["hm"]), "%s: ...and reads the clock time exactly as before: %r" % (where, r))
            self.assertEqual(r["overflow"], 0, "%s: no label wider than the slot: %r" % (where, r))
            if r["marker"] and r["dotLeft"] is not None:
                self.assertLessEqual(r["mBox"]["right"], r["dotLeft"] - 2, "%s: the stamp stays clear of the dot: %r" % (where, r))
            prev = rel
        stamps = [r["mBox"] for r in timed if r["marker"]]
        for a, b in zip(stamps, stamps[1:]):
            self.assertLessEqual(a["bottom"], b["top"], "%s: a two-line stamp never reaches the next stamp: %r / %r" % (where, a, b))
        return shown

    def test_today_reads_how_long_ago_with_the_exact_time_on_hover_and_turns_with_the_clock_without_moving_the_transcript(self):
        cfg = os.path.join(self.lab, "cfg.json")
        with open(cfg, "w") as f:
            json.dump({"chat": "http://127.0.0.1:%d/chat?token=%s" % (self.port, self.token), "web": SID_A, "api": SID_B,
                       "nowMs": self.now * 1000, "shots": os.environ.get("RT_SHOTS", "")}, f)
        driver = os.path.join(self.lab, "driver.mjs")
        with open(driver, "w") as f:
            f.write(DRIVER)
        p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=300,
                           env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
        if p.returncode == 3:
            raise unittest.SkipTest("no playwright browser on this box — the served guard needs one; CI's extension job installs Chromium and requires this file to run")
        self.assertEqual(p.returncode, 0, "driver failed:\n" + p.stdout[-3000:] + p.stderr[-3000:] + "\nkernel:\n" + open(self.klog).read()[-1500:])
        line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
        self.assertIsNotNone(line, "driver printed no result:\n" + p.stdout[-3000:])
        r = json.loads(line[len("RESULT:"):])
        today_rows = [self.now - o for o in TODAY_OFFSETS]
        all_today = all(relative_label(t, self.now * 1000) for t in today_rows)   # false only within ~two hours after local midnight
        for theme in ("dark", "light"):
            m = r["web"][theme]
            self.assertEqual(m["theme"], theme)
            self.assertLess(m["now"] - self.now * 1000, 35000, "the page's clock is the fixture's, still inside the minute the rows were stamped against: %r" % m["now"])
            self.assertEqual(m["slot"], "56px", "the slot is the whole gutter in %s" % theme)
            shown = self._expect_rail(m, "web " + theme)
            if all_today:
                self.assertEqual(shown, ["2 hours ago", "1 hour ago", "59 min ago", "5 min ago", "1 min ago", "now"],
                                 "one stamp of each kind, in the user's words, in %s" % theme)
            self.assertEqual([x["label"] for x in m["rows"] if x["isDiv"]], ["Yesterday"], "the day divider names the other day, once, in %s" % theme)
            w, w14 = m["widths"], m["widths14"]
            for one_line in ("now", "1 min ago", "9 min ago", "59 min ago", "1 hour ago"):
                self.assertLessEqual(w[one_line], 56, "%s fits the 56px slot on one line at the default chat font in %s (%s): %r" % (one_line, theme, m["font"], w))
            for wrapped in ("2 hours ago", "23 hours ago"):
                self.assertGreater(w[wrapped], 56, "%s does not fit on one line in %s, which is why the plural-hours form takes 'ago' on a line of its own: %r" % (wrapped, theme, w))
            for first in ("2 hours", "23 hours"):
                self.assertLessEqual(w14[first], 56, "%s, the wrapped form's first line, fits even at a 14px chat font in %s: %r" % (first, theme, w14))
            for one_line in ("now", "1 min ago", "9 min ago", "1 hour ago"):
                self.assertLessEqual(w14[one_line], 56, "%s still fits the slot at a 14px chat font in %s: %r" % (one_line, theme, w14))
            # at 14px (the VS Code webview's --fs road; the served page pins the body at 13px) the two-digit minute forms are
            # wider than the slot, and white-space: pre-line WRAPS such a line at its space (59 min over ago), the way the
            # plural-hours form is set on purpose: nothing overhangs toward the dot at any chat font
            self.assertGreater(w14["59 min ago"], 56, "the two-digit minute form is wider than the slot at 14px in %s, so it wraps at the space: %r" % (theme, w14))
            self.assertLessEqual(w14["59 min"], 56, "...and its first line fits: %r" % w14)
            # the yesterday run: the clock time exactly as before, no class, no title, its divider once
            a = r["api"][theme]
            self.assertEqual(a["theme"], theme)
            self.assertEqual(self._expect_rail(a, "api " + theme), [], "nothing relative on a past day's transcript in %s" % theme)
            self.assertTrue(all(x["marker"] == x["hm"] for x in a["rows"] if x["marker"] is not None), "every yesterday row wears its HH:MM (distinct minutes): %r" % [(x["marker"], x["hm"]) for x in a["rows"]])
            self.assertEqual([x["label"] for x in a["rows"] if x["isDiv"]], ["Yesterday"])
        # the clock's minute turned: the ONE timer fired and the labels moved a minute, nothing else did
        before, after = r["web"]["dark"], r["web"]["ticked"]
        self.assertEqual(after["theme"], "dark")
        self.assertGreater(after["now"] // 60000, before["now"] // 60000, "the page's clock crossed a minute boundary: %r -> %r (%r)" % (before["now"], after["now"], r["tick"]))
        shown2 = self._expect_rail(after, "web after the tick")
        if all_today and relative_label(today_rows[0], after["now"]):
            self.assertEqual(shown2, ["2 hours ago", "1 hour ago", "6 min ago", "2 min ago", "1 min ago"],
                             "a minute later: the row at 59 minutes reads '1 hour ago' like the row before it and its stamp goes quiet; 'now' is '1 min ago'")
        self.assertEqual([x["marker"] for x in before["rows"] if x["marker"] is not None and not x["rel"]],
                         [x["marker"] for x in after["rows"] if x["marker"] is not None and not x["rel"]], "the other-day markers did not change")
        self.assertEqual([x["box"] for x in before["rows"]], [x["box"] for x in after["rows"]], "no turn moved: every box (top within the thread, height, left, width) is where it was")
        # a marker whose label did not change across the boundary is not touched: no mutation records on the two-hour and
        # one-hour rows, and the selection laid across the two-hour turn before the tick reads the same after it
        q = r["web"]["quiet"]
        self.assertTrue(q["selBefore"].startswith("2 hours"), "the selection began on the two-hour stamp: %r" % q)
        self.assertEqual(q["scroll"][0], q["scroll"][1], "a programmatic selection does not scroll the pane: %r" % q["scroll"])
        self.assertEqual(q["atJump"]["records"], {"0": [], "1": []}, "an unchanged label is not rewritten by the tick (text node, class, title, data-hm): %r" % q)
        self.assertEqual((q["atJump"]["ranges"], q["atJump"]["sel"]), (1, q["selBefore"]), "a selection spanning an untouched stamp survives the tick: %r" % q)
        self.assertEqual(q["records"], {"0": [], "1": []}, "...and nothing touched those markers in the frame after either: %r" % q)
        # the sticky over a today turn scrolled past the top line wears the same two-line label as the stamp it stands in for
        st = r["web"]["stickyRun"]
        self.assertTrue(st["tracked"]["hidden"], "the tracked turn's own stamp crossed above the line and hid: %r" % st)
        self.assertIsNotNone(st["sticky"], "...so the sticky leads: %r" % st)
        want = relative_label(int(st["tracked"]["epoch"]), st["now"])
        self.assertEqual((st["sticky"]["text"], st["sticky"]["rel"]), (relative_lines(want), True), "the sticky reads the turn's own label: %r" % st)
        self.assertEqual(want, "1 hour ago", "the second today turn is the one-hour row: %r" % st)
        self.assertLess(st["sticky"]["height"], 15, "one line tall, as '1 hour ago' fits the slot: %r" % st["sticky"])


if __name__ == "__main__":
    unittest.main()
