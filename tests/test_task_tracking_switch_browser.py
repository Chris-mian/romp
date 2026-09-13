#!/usr/bin/env python3
"""The Task tracking master switch on the served dashboard (T404 PR 2, the user 2026-09-13). Over the queued lab's boot (a
hermetic kernel, a session with a transcript), the real landing page: the gear's Task tracking row reads on and the rail
shows the Outline and Feed buttons. The switch is flipped IN THE GEAR (a real click: the gear posts setTaskTracking over its
own socket and tells the shell), and the page is read: the shell wears body.no-task-tracking, the two buttons are gone, the
kernel's /version reports the switch off, the feed pane's frame carries the off flag and the pane shows the kernel's notice
in place of its list, a fresh /feed page renders the notice unhidden, the judge rows and the pane toggles wear rs-off with
the one tooltip and their inputs are disabled, the Automation rows show their waiting note, and /perf's tierStarts stays flat
across the wait while it grew before and grows again after. Flipped back, the buttons return, /version reads on and the notice hides. The producer's gate
itself is executed with stubs in tests/test_task_tracking_switch.py (this boot's session is live to the kernel, so
the counter moves while on and stands still while off: the switch's proof on the real producer). Skips LOUDLY without the
extension deps or a browser (a failure under ROMP_SERVED_TESTS_REQUIRE=1, the file name being a served module's).
SYNTHETIC fixtures only.
"""
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
from test_queued_rescind_browser import QueuedLab, SID   # noqa: E402  the shared boot

DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));
let browser;
try { browser = await chromium.launch(); }
catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
const ctx = await browser.newContext({ viewport: { width: 1280, height: 860 } });
const page = await ctx.newPage();
await page.goto(cfg.landing);
await page.waitForSelector("#rail-gear", { timeout: 20000 });
const frameBy = async (part) => { let f = page.frames().find((x) => x.url().includes(part)); for (let i = 0; i < 100 && !f; i++) { await page.waitForTimeout(100); f = page.frames().find((x) => x.url().includes(part)); } return f; };
await page.evaluate(() => window.__rompOpenSettings("tasks"));
await page.waitForFunction(() => document.body.classList.contains("settings-open"), null, { timeout: 20000 }).catch(() => {});
const setF = await frameBy("/settings");
await setF.waitForSelector("#rsettings:not([hidden])", { timeout: 15000 });
await setF.waitForFunction(() => document.getElementById("rs-tasktrack") !== null, null, { timeout: 15000 });
const feedF = await frameBy("/feed");
// every feed frame the pane receives from here on, by either path (the window message, federation's direct delivery): the
// flag it carried and its keys, so a notice that does not show is attributable to the wire or to the handler
if (feedF) await feedF.evaluate(() => { const w = window; w.__ttFrames = [];
  const note = (m, via) => { if (m && m.type === "feed") w.__ttFrames.push({ via, off: m.off === true, keys: Object.keys(m).length }); };
  window.addEventListener("message", (e) => note(e.data, "window"));
  const fed = w.__rompFed; if (fed && typeof fed.onFrame === "function") fed.onFrame((e) => note(e.data, "fed")); });
const feedFrames = () => feedF ? feedF.evaluate(() => window.__ttFrames) : Promise.resolve(null);
const shell = () => page.evaluate(() => {
  const vis = (sel) => { const b = document.querySelector(sel); return !!b && getComputedStyle(b).display !== "none"; };
  return { noTracking: document.body.classList.contains("no-task-tracking"), fleetBtn: vis(".rail-btn[data-pane=fleet]"), feedBtn: vis(".rail-btn[data-pane=feed]"), chatBtn: vis(".rail-btn[data-pane=chat]"),
           poFeed: document.body.classList.contains("po-feed"), poFleet: document.body.classList.contains("po-fleet") };
});
const gear = () => setF.evaluate(() => {
  const tk = document.getElementById("rs-tasktrack");
  const jrows = Array.from(document.querySelectorAll("#rsettings .rs-pane[data-pane=tasks] .rs-jrow"));
  const dep = (id) => { const el = document.getElementById(id); const row = el && el.closest("label"); return row ? { off: row.classList.contains("rs-off"), title: row.getAttribute("title") || "", disabled: el.disabled } : null; };
  return { checked: tk ? tk.checked : null, jrows: jrows.length, jrowsOff: jrows.filter((r) => r.classList.contains("rs-off")).length, jrowTitle: jrows[0] ? (jrows[0].getAttribute("title") || "") : null,
           judgeSelectsDisabled: Array.from(document.querySelectorAll("#rsettings .rs-pane[data-pane=tasks] .rs-jrow select")).filter((s) => s.disabled).length,
           fleet: dep("rs-pane-fleet"), feed: dep("rs-pane-feed"), jix: dep("rs-judges-index"), jtr: dep("rs-judges-triage"),
           nudgeNote: !document.getElementById("rs-autonudge-tt").hidden, compactNote: !document.getElementById("rs-suggestcompact-tt").hidden };
});
const kernel = async () => { const v = await page.evaluate(async (u) => (await fetch(u, { cache: "no-store" })).json(), cfg.version); const p = await page.evaluate(async (u) => (await fetch(u, { cache: "no-store" })).json(), cfg.perf);
  const feedPage = await page.evaluate(async (u) => (await fetch(u, { cache: "no-store" })).text(), cfg.feedPage);
  return { taskTracking: v.taskTracking, settingsTaskTracking: v.settings && v.settings.taskTracking, tierStarts: p.judge ? p.judge.tierStarts : null, feedNoticeShown: /id=tt-off class=tt-off style=/.test(feedPage), feedNoticeHidden: /class=tt-off hidden/.test(feedPage) }; };
const feedPane = () => feedF ? feedF.evaluate(() => { const o = document.getElementById("tt-off"), l = document.getElementById("feed-list"); return { present: !!o, noticeShown: !!o && !o.hidden, listHidden: !!l && l.hidden }; }) : Promise.resolve(null);
const out = {};
out.before = { shell: await shell(), gear: await gear(), kernel: await kernel(), feedPane: await feedPane() };
// THE FLIP, in the gear: a real click on the switch
await setF.click("#rs-tasktrack");
await page.waitForFunction(() => document.body.classList.contains("no-task-tracking"), null, { timeout: 10000 }).catch(() => {});
await page.waitForFunction(async (u) => (await (await fetch(u, { cache: "no-store" })).json()).taskTracking === false, cfg.version, { timeout: 10000 }).catch(() => {});
if (feedF) await feedF.waitForFunction(() => { const o = document.getElementById("tt-off"); return !!o && !o.hidden; }, null, { timeout: 15000 }).catch(() => {});
out.off = { shell: await shell(), gear: await gear(), kernel: await kernel(), feedPane: await feedPane(), feedFrames: await feedFrames() };
await page.waitForTimeout(4000);   // several producer passes' worth of wall time while off: the counter must not move
out.afterWait = await kernel();
// BACK ON
await setF.click("#rs-tasktrack");
await page.waitForFunction(() => !document.body.classList.contains("no-task-tracking"), null, { timeout: 10000 }).catch(() => {});
await page.waitForFunction(async (u) => (await (await fetch(u, { cache: "no-store" })).json()).taskTracking === true, cfg.version, { timeout: 10000 }).catch(() => {});
if (feedF) await feedF.waitForFunction(() => { const o = document.getElementById("tt-off"); return !!o && o.hidden; }, null, { timeout: 15000 }).catch(() => {});
out.on = { shell: await shell(), gear: await gear(), kernel: await kernel(), feedPane: await feedPane(), feedFrames: await feedFrames() };
await browser.close();
process.stdout.write("RESULT:" + JSON.stringify(out) + "\n", () => process.exit(0));
"""


class ServedTaskTrackingSwitch(QueuedLab):
    _r = None

    def _result(self):
        cls = type(self)
        if cls._r is None:
            base = "http://127.0.0.1:%d" % self.port
            cfg = os.path.join(self.lab, "cfg.json")
            with open(cfg, "w") as f:
                json.dump({"landing": base + "/?token=" + self.token, "version": base + "/version", "perf": base + "/perf?token=" + self.token,
                           "feedPage": base + "/feed?token=" + self.token, "sid": SID}, f)
            driver = os.path.join(self.lab, "driver_tt.mjs")
            with open(driver, "w") as f:
                f.write(DRIVER)
            p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=300,
                               env=dict(os.environ, EXT_PKG=os.path.join(self.EXT, "package.json"), CFG=cfg))
            if p.returncode == 3:
                raise unittest.SkipTest("no playwright browser on this box — the served guard needs one (CI installs none)")
            self.assertEqual(p.returncode, 0, "driver failed:\n" + p.stdout[-3000:] + p.stderr[-3000:] + "\nkernel:\n" + open(self.klog).read()[-1500:])
            line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
            self.assertIsNotNone(line, "driver printed no result:\n" + p.stdout[-3000:])
            cls._r = json.loads(line[len("RESULT:"):])
            if os.environ.get("TASK_TRACKING_DUMP"):
                with open(os.environ["TASK_TRACKING_DUMP"], "w") as f:
                    json.dump(cls._r, f, indent=1)
        print("RESULT:" + json.dumps(cls._r), file=sys.stderr)
        return cls._r

    def test_the_switch_reads_on_by_default_with_the_panes_and_their_controls_live(self):
        b = self._result()["before"]; table = "\n  " + json.dumps(b)[:1500]
        self.assertTrue(b["gear"]["checked"], "the gear's row reads on" + table)
        self.assertTrue(b["kernel"]["taskTracking"] and b["kernel"]["settingsTaskTracking"], "/version says on, top level and in settings" + table)
        self.assertFalse(b["shell"]["noTracking"], table)
        self.assertTrue(b["shell"]["fleetBtn"] and b["shell"]["feedBtn"], "the Outline and Feed buttons show" + table)
        self.assertEqual(b["gear"]["jrowsOff"], 0, "no judge row greyed" + table)
        self.assertFalse(b["gear"]["nudgeNote"] or b["gear"]["compactNote"], "the Automation notes are hidden while on" + table)
        self.assertTrue(b["kernel"]["feedNoticeHidden"] and not b["kernel"]["feedNoticeShown"], "/feed carries the notice hidden" + table)
        self.assertIsNotNone(b["kernel"]["tierStarts"], "/perf reports tierStarts" + table)

    def test_off_hides_the_panes_and_their_buttons_and_the_kernel_says_so(self):
        o = self._result()["off"]; table = "\n  " + json.dumps(o)[:1500]
        self.assertFalse(o["gear"]["checked"], table)
        self.assertFalse(o["kernel"]["taskTracking"], "/version says off" + table)
        self.assertFalse(o["kernel"]["settingsTaskTracking"], "…and in the settings dict" + table)
        self.assertTrue(o["shell"]["noTracking"], "the shell wears body.no-task-tracking" + table)
        self.assertFalse(o["shell"]["fleetBtn"] or o["shell"]["feedBtn"], "the Outline and Feed buttons are gone" + table)
        self.assertTrue(o["shell"]["chatBtn"], "the chat's button stays" + table)
        self.assertFalse(o["shell"]["poFeed"] or o["shell"]["poFleet"], "an open pane of theirs closed on the same apply" + table)
        self.assertTrue(o["kernel"]["feedNoticeShown"] and not o["kernel"]["feedNoticeHidden"], "a fresh /feed renders the notice unhidden" + table)

    def test_off_the_feed_pane_shows_the_notice_in_place_of_its_list_on_the_off_frame(self):
        r = self._result(); o = r["off"]["feedPane"]; table = "\n  " + json.dumps(r["off"]["feedPane"]) + " before: " + json.dumps(r["before"]["feedPane"]) + " frames after the flip: " + json.dumps(r["off"].get("feedFrames"))
        self.assertTrue(r["off"].get("feedFrames"), "the pane received a feed frame after the flip" + table)
        self.assertTrue(any(f["off"] for f in r["off"]["feedFrames"]), "…carrying the off flag" + table)
        self.assertIsNotNone(o, "the feed pane is loaded (Feed is on by default in the Panes section)" + table)
        self.assertTrue(o["present"] and o["noticeShown"] and o["listHidden"], "the off frame swapped the list for the notice" + table)
        self.assertFalse(r["before"]["feedPane"]["noticeShown"], "…which was hidden while on" + table)

    def test_off_greys_every_dependent_control_with_the_one_tooltip_and_disables_it(self):
        g = self._result()["off"]["gear"]; table = "\n  " + json.dumps(g)
        self.assertGreater(g["jrows"], 5, table)
        self.assertEqual(g["jrowsOff"], g["jrows"], "every judge row wears rs-off" + table)
        self.assertEqual(g["jrowTitle"], "Enable task tracking to use this (Settings, Task tracking).", table)
        self.assertGreater(g["judgeSelectsDisabled"], 0, "the judge pickers' selects are disabled" + table)
        for k in ("fleet", "feed", "jix", "jtr"):
            self.assertTrue(g[k] and g[k]["off"] and g[k]["disabled"], k + ": greyed and disabled" + table)
            self.assertEqual(g[k]["title"], "Enable task tracking to use this (Settings, Task tracking).", k + table)
        self.assertTrue(g["nudgeNote"] and g["compactNote"], "the Automation rows say what waits and what still goes out" + table)

    def test_off_starts_no_judge_tier_while_on_starts_them_again(self):
        # the kernel's own producer passes: this boot's session is live to the kernel, so tiers start while on (the counter reads
        # above zero before the flip), none start while off (flat across the wait), and they start again once on
        r = self._result(); table = "\n  before: " + json.dumps(r["before"]["kernel"]) + " off: " + json.dumps(r["off"]["kernel"]) + " after the wait: " + json.dumps(r["afterWait"]) + " on: " + json.dumps(r["on"]["kernel"])
        self.assertGreater(r["before"]["kernel"]["tierStarts"], 0, "tiers start in this boot while on, so the flat count below means something" + table)
        self.assertEqual(r["afterWait"]["tierStarts"], r["off"]["kernel"]["tierStarts"], "tierStarts flat while off" + table)
        self.assertGreater(r["on"]["kernel"]["tierStarts"], r["off"]["kernel"]["tierStarts"], "…and growing once on again" + table)

    def test_back_on_restores_the_buttons_the_controls_and_the_panes(self):
        o = self._result()["on"]; table = "\n  " + json.dumps(o)[:1500]
        self.assertTrue(o["gear"]["checked"] and o["kernel"]["taskTracking"], table)
        self.assertFalse(o["shell"]["noTracking"], table)
        self.assertTrue(o["shell"]["fleetBtn"] and o["shell"]["feedBtn"], "the buttons return" + table)
        self.assertEqual(o["gear"]["jrowsOff"], 0, "the judge rows lift" + table)
        self.assertFalse(o["gear"]["fleet"]["off"] or o["gear"]["feed"]["off"], table)
        self.assertTrue(o["feedPane"] and not o["feedPane"]["noticeShown"], "the feed pane's notice hides on the next real frame" + table)


if __name__ == "__main__":
    unittest.main()
