#!/usr/bin/env python3
"""The Task tracking master switch on the served dashboard (T404 PR 2, the user 2026-09-13). Over the queued lab's boot (a
hermetic kernel, a session with a transcript), the real landing page: the gear's Task tracking row reads on and the rail
shows the Outline and Feed buttons. The switch is flipped IN THE GEAR (a real click: the gear posts setTaskTracking over its
own socket and tells the shell), and the page is read: the shell wears body.no-task-tracking, the two buttons are gone, the
kernel's /version reports the switch off, the feed pane's frame carries the off flag and the pane shows the kernel's notice
in place of its list, a fresh /feed page renders the notice unhidden, the judge rows and the pane toggles wear rs-off with
the one tooltip and their inputs are disabled, the Automation rows show their waiting note, and /perf's tierStarts stays flat
across the wait while it grew before and grows again after. Flipped back, the buttons return, /version reads on and the notice hides.
Round two: the Outline pane is turned on first so its page is loaded, and after the flip both panes show the notice ON TOP with
the romp loader gone within seconds, not at its 30 s failsafe (the outline's _keepLoader used to re-assert it forever); a write
the kernel refuses (a directory where the file goes) leaves the switch, the shell and the kernel on and draws the stale toast
with the kept value; the notice's button on a standalone /feed page opens the dashboard at Task tracking. The producer's gate
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
// the Outline pane on (its default is off, so its page is not loaded): the gear's Panes toggle, a same-origin storage event the
// shell's reconcile hears, loads the iframe; the outline's page must be up for its loader to be measured after the flip
await setF.evaluate(() => { const b = document.getElementById("rs-pane-fleet"); if (b && !b.checked) b.click(); });
const fleetF = await frameBy("/fleet");
if (fleetF) await fleetF.waitForSelector("#fleet-list", { timeout: 15000 }).catch(() => {});
await page.waitForTimeout(1500);   // the outline's first frame lands (its loader hides on real data)
const paneRead = (f) => f ? f.evaluate(() => {
  const o = document.getElementById("tt-off"), l = document.getElementById("feed-list") || document.getElementById("fleet-list"), sp = document.getElementById("pane-spin");
  let onTop = null;
  let hitDesc = null;
  if (o && !o.hidden) { const t = o.querySelector("p") || o; const r = t.getBoundingClientRect(); const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    onTop = !!hit && (hit === o || o.contains(hit)); hitDesc = hit ? (hit.tagName + "#" + hit.id + "." + hit.className) : "nothing"; }
  return { present: !!o, noticeShown: !!o && !o.hidden, listHidden: !!l && l.hidden, spinGone: !!sp && sp.classList.contains("gone"), noticeOnTop: onTop, hit: hitDesc };
}) : Promise.resolve(null);
out.before = { shell: await shell(), gear: await gear(), kernel: await kernel(), feedPane: await feedPane(), fleetPane: await paneRead(fleetF) };
// A REFUSED WRITE (round two, medium 4): a directory where the file goes; the read still says on (malformed reads on), the write
// cannot replace it. The click must leave the switch, the shell and the kernel on, and say so in the gear's stale toast.
fs.mkdirSync(cfg.stateFile);
await setF.click("#rs-tasktrack");
const toastText = await setF.waitForFunction(() => { const t = document.querySelector(".rs-stale-toast-msg"); return t ? t.textContent : null; }, null, { timeout: 10000 }).then((h) => h.jsonValue()).catch(() => null);
await setF.waitForFunction(() => document.getElementById("rs-tasktrack").checked === true, null, { timeout: 10000 }).catch(() => {});
await page.waitForTimeout(700);   // time enough for a shell apply that must not come
out.refused = { toast: toastText, gear: await gear(), shell: await shell(), kernel: await kernel(), feedPane: await feedPane() };
fs.rmdirSync(cfg.stateFile);
await setF.evaluate(() => { Array.from(document.querySelectorAll(".rs-stale-toast")).forEach((t) => t.remove()); });
// a gear that flipped its box on the click whatever the kernel did (round one's) leaves it unchecked here while the kernel is on:
// put it back, so the flip below starts from on on every head and each test fails on its own assertion, not on a garbled sequence
if (!(await setF.evaluate(() => document.getElementById("rs-tasktrack").checked))) { await setF.click("#rs-tasktrack"); await page.waitForTimeout(600); }
// THE FLIP, in the gear: a real click on the switch
const flipAt = Date.now();
await setF.click("#rs-tasktrack");
await page.waitForFunction(() => document.body.classList.contains("no-task-tracking"), null, { timeout: 10000 }).catch(() => {});
await page.waitForFunction(async (u) => (await (await fetch(u, { cache: "no-store" })).json()).taskTracking === false, cfg.version, { timeout: 10000 }).catch(() => {});
if (feedF) await feedF.waitForFunction(() => { const o = document.getElementById("tt-off"); return !!o && !o.hidden; }, null, { timeout: 15000 }).catch(() => {});
// the loaders (round two, medium 1): gone within seconds of the off frame, the notice on top; the outline's would otherwise
// be re-asserted every second past its 30 s failsafe
let fleetSpinGoneMs = null;
if (fleetF) { await fleetF.waitForFunction(() => { const o = document.getElementById("tt-off"), sp = document.getElementById("pane-spin"); return !!o && !o.hidden && !!sp && sp.classList.contains("gone"); }, null, { timeout: 12000 }).then(() => { fleetSpinGoneMs = Date.now() - flipAt; }).catch(() => {}); }
if (feedF) await feedF.waitForFunction(() => { const sp = document.getElementById("pane-spin"); return !!sp && sp.classList.contains("gone"); }, null, { timeout: 12000 }).catch(() => {});
await page.waitForTimeout(2500);   // two more _keepLoader ticks: a loader re-asserted would show here
out.off = { shell: await shell(), gear: await gear(), kernel: await kernel(), feedPane: await feedPane(), feedFrames: await feedFrames(),
            fleetPane: await paneRead(fleetF), feedPaneLoader: await paneRead(feedF), fleetSpinGoneMs };
// THE ERROR CENTER WHILE OFF (round four, the ruling: the error center is not task tracking). A state file that cannot be read is
// told while off: the session flags' store becomes a directory, the Sessions pane's next build reads it (a display reader that files
// one ring row per fault episode), the off frame carries the ring, the hidden feed frame mirrors it to the shell, and the error
// center shows the row and its unread cue
const errsBefore = await page.evaluate(() => ({ rows: document.querySelectorAll("#rerr-list .rerr-row").length, cue: ((document.querySelector(".rerr-n") || {}).textContent || "").trim() }));
fs.mkdirSync(cfg.flagsFile);
{ const p4 = await ctx.newPage(); await p4.goto(cfg.tlPage); await p4.waitForTimeout(2500); await p4.close(); }   // a fresh Sessions-pane connect builds the lanes, which read the flags: the fault is filed
await page.waitForFunction((was) => ((document.querySelector(".rerr-n") || {}).textContent || "").trim() !== was, errsBefore.cue, { timeout: 12000 }).catch(() => {});
await page.waitForTimeout(500);
const cueAfter = await page.evaluate(() => ((document.querySelector(".rerr-n") || {}).textContent || "").trim());
await page.evaluate(() => { if (window.__rompOpenErrs) window.__rompOpenErrs(); }); await page.waitForTimeout(300);
out.errsOff = await page.evaluate(() => { const rows = Array.from(document.querySelectorAll("#rerr-list .rerr-row")).map((r) => r.textContent.trim().slice(0, 240)); const back = document.getElementById("rerr-back");
  return { rows, count: rows.length, open: !!back && !back.hidden, stillOff: document.body.classList.contains("no-task-tracking") }; });
out.errsOff.before = errsBefore; out.errsOff.cueAfter = cueAfter;
await page.evaluate(() => { if (window.__rompCloseErrs) window.__rompCloseErrs(); }); await page.waitForTimeout(150);
fs.rmdirSync(cfg.flagsFile);
// THE STANDALONE PAGE (round two, medium 2): /feed on its own, while off, shows the notice; its button has no shell to ask and
// no gear here, so it goes to the dashboard at Task tracking
const p2 = await ctx.newPage();
await p2.goto(cfg.feedPage);
await p2.waitForFunction(() => { const o = document.getElementById("tt-off"); return !!o && !o.hidden; }, null, { timeout: 15000 }).catch(() => {});
// the standalone pages are where the notice is SEEN (the shell closes the panes while off): the loader must be gone and stay gone
// past several _keepLoader ticks, with the notice under the pointer (round two, medium 1: the outline's loader sat over it forever)
const probeStandalone = (pg) => pg.evaluate(() => { const o = document.getElementById("tt-off"), sp = document.getElementById("pane-spin");
  let onTop = null, hitDesc = null;
  if (o && !o.hidden) { const t = o.querySelector("p") || o; const r = t.getBoundingClientRect(); const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    onTop = !!hit && (hit === o || o.contains(hit)); hitDesc = hit ? (hit.tagName + "#" + hit.id + "." + hit.className) : "nothing"; }
  return { noticeShown: !!o && !o.hidden, spinGone: !!sp && sp.classList.contains("gone"), noticeOnTop: onTop, hit: hitDesc, url: location.pathname }; });
await p2.waitForTimeout(3500);
const standaloneBefore = await probeStandalone(p2);
const p3 = await ctx.newPage();
await p3.goto(cfg.fleetPage);
await p3.waitForFunction(() => { const o = document.getElementById("tt-off"); return !!o && !o.hidden; }, null, { timeout: 15000 }).catch(() => {});
await p3.waitForTimeout(3500);
out.fleetStandalone = await probeStandalone(p3);
await p3.close();
await p2.click("#tt-off-btn", { timeout: 5000 }).catch(() => {});   // a hidden button (a page that shows no notice) is this test's red, not a crash
await p2.waitForFunction(() => document.body.classList.contains("settings-open"), null, { timeout: 20000 }).catch(() => {});
let tasksPane = null;
{ let sf = p2.frames().find((x) => x.url().includes("/settings")); for (let i = 0; i < 50 && !sf; i++) { await p2.waitForTimeout(100); sf = p2.frames().find((x) => x.url().includes("/settings")); }
  if (sf) tasksPane = await sf.waitForFunction(() => { const pane = document.querySelector("#rsettings .rs-pane[data-pane=tasks]"); return !!pane && !pane.hidden; }, null, { timeout: 10000 }).then(() => true).catch(() => false); }
out.standalone = { before: standaloneBefore, url: p2.url(), settingsOpen: await p2.evaluate(() => document.body.classList.contains("settings-open")), tasksPane };
await p2.close();
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
                           "feedPage": base + "/feed?token=" + self.token, "fleetPage": base + "/fleet?token=" + self.token, "sid": SID,
                           "stateFile": os.path.join(self.state, "task-tracking.json"),
                           "flagsFile": os.path.join(self.state, "session-flags.json"), "tlPage": base + "/timeline?token=" + self.token}, f)
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

    def test_off_both_panes_show_the_notice_on_top_with_the_loader_gone_within_seconds(self):
        # round two, medium 1: the Outline page showed the romp loader forever over the notice (_keepLoader re-asserting it past the
        # 30 s failsafe, the off frame's early return never marking the page loaded); /feed hid its notice under its loader for 30 s
        r = self._result(); o = r["off"]; table = "\n  fleet: " + json.dumps(o.get("fleetPane")) + " feed: " + json.dumps(o.get("feedPaneLoader")) + " ms: " + json.dumps(o.get("fleetSpinGoneMs")) + " before: " + json.dumps(r["before"].get("fleetPane"))
        self.assertIsNotNone(o.get("fleetPane"), "the Outline pane is loaded (turned on in the gear before the flip)" + table)
        for key in ("fleetPane", "feedPaneLoader"):   # the panes in the shell (closed by the apply, so no pointer can reach them): the class says
            p = o[key]
            self.assertTrue(p and p["present"] and p["noticeShown"] and p["listHidden"], key + ": the notice in place of the list" + table)
            self.assertTrue(p["spinGone"], key + ": the romp loader is gone" + table)
        self.assertIsNotNone(o.get("fleetSpinGoneMs"), "the outline's loader went within the wait" + table)
        self.assertLess(o["fleetSpinGoneMs"], 12000, "…within seconds of the flip, not at the 30 s failsafe" + table)
        # the standalone pages, where the notice is seen: read 3.5 s after it showed, past several _keepLoader ticks
        for key, p in (("feed", r["standalone"]["before"]), ("outline", r.get("fleetStandalone"))):
            tb = table + "\n  " + key + " standalone: " + json.dumps(p)
            self.assertTrue(p and p["noticeShown"], key + ": the standalone page shows the notice" + tb)
            self.assertTrue(p["spinGone"], key + ": the loader is gone and stays gone" + tb)
            self.assertTrue(p["noticeOnTop"], key + ": the notice is what the pointer hits, not the loader (hit: %s)" % p.get("hit") + tb)

    def test_a_write_the_kernel_refuses_leaves_the_switch_the_shell_and_the_kernel_on_and_says_so(self):
        # round two, medium 4: the gear and the shell went off 6 ms after the click while the kernel kept tracking on
        r = self._result()["refused"]; table = "\n  " + json.dumps(r)[:1800]
        self.assertIsNotNone(r["toast"], "the gear's stale toast drew" + table)
        self.assertIn("Task tracking: off was not applied", r["toast"], "the setting by name, the refused value, not applied (low 1)" + table)
        self.assertIn("Keeping on", r["toast"], "the kept value is named" + table)
        self.assertIn("write failed", r["toast"], "and the fault" + table)
        self.assertTrue(r["gear"]["checked"], "the box reads on again (the modal re-read the kernel)" + table)
        self.assertEqual(r["gear"]["jrowsOff"], 0, "no dependent greyed" + table)
        self.assertFalse(r["shell"]["noTracking"], "the shell never went off" + table)
        self.assertTrue(r["shell"]["fleetBtn"] and r["shell"]["feedBtn"], "the buttons stayed" + table)
        self.assertTrue(r["kernel"]["taskTracking"], "/version says on" + table)
        self.assertFalse(r["feedPane"] and r["feedPane"]["noticeShown"], "the feed pane shows no notice" + table)

    def test_the_notices_button_on_a_standalone_feed_page_opens_the_dashboard_at_task_tracking(self):
        # round two, medium 2: the button posted to its own window, and nothing listened
        r = self._result()["standalone"]; table = "\n  " + json.dumps(r)
        self.assertTrue(r["before"]["noticeShown"], "the standalone page shows the notice" + table)
        self.assertTrue(r["before"]["spinGone"], "…with no loader over it" + table)
        self.assertTrue(r["settingsOpen"], "the dashboard opened with the settings up" + table)
        self.assertTrue(r["tasksPane"], "…at the Task tracking tab" + table)
        self.assertNotIn("#settings", r["url"], "the hash was dropped once opened, so a reload does not reopen it" + table)
        self.assertTrue(r["url"].split("?")[0].endswith("/"), "the landing, not the pane" + table)

    def test_off_an_unreadable_state_file_is_told_in_the_shells_error_center(self):
        # round four, the manager's ruling: the error center is not task tracking; an opt-out of judging is not an opt-out of being
        # told when the machine fails. Before: the off frame carried no ring and the feed's off branch returned before the mirror
        e = self._result()["errsOff"]; table = "\n  " + json.dumps(e)[:1600]
        self.assertTrue(e["stillOff"], "tracking stayed off through the fault" + table)
        self.assertTrue(e["open"], "the error center opened" + table)
        self.assertGreater(e["count"], e["before"]["rows"], "a row arrived while off" + table)
        self.assertTrue(any("session-flags" in r for r in e["rows"]), "the unreadable flags store is the row" + table)
        self.assertNotEqual(e["cueAfter"], e["before"]["cue"], "the bell's unread cue moved with it" + table)

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
