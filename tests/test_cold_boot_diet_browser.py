"""The cold-boot chat build diet, the client half (the user's ruling 2026-09-14: the selected tab builds first; the strip's other tabs
spread over later refreshes; hidden tabs are not built until shown). A hermetic kernel over TWENTY-SEVEN synthetic sessions, the real
/chat page served from a copy of the built bundle, driven by Playwright. Roads, one browser: (1) the dial: after a reload whose recorded
reason is a kernel RESTART the chat pane's first socket dials skeleton=1 beside active=; after a build reload it does not; (2) the first
refresh: one full session frame, the selected tab's, ahead of the strip's paint, the other tabs as statuses with the strip listing the
skeleton set; (3) the spread: the visible skeletons fill on later idle callbacks one at a time, and tabs the #only= filter hides stay
skeletons until the filter shows them; (4) the measurement: time to the selected tab's first row, to the strip's 27 tabs, to every visible
tab built, for the restart reload and for a fresh open with no record; (5) a plain reload right after a restart reload dials no diet: the
record is consumed by the read that acted on it; (6) after a restart record every pane of the served dashboard dials, and only the chat
pane's dial carries the term; (7) lifting the #only= filter re-arms the idle prefetch: the revealed skeletons are asked for with no kernel
push in between. The fresh open after a boot (no record, no diet) is covered by NEITHER half today: this lab measures it and the design
decision on it is the manager's. Synthetic only (placeholder ids, invented text)."""
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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from tests.dist_copy import copy_dist  # noqa: E402

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
EXT = os.path.join(ROOT, "vscode-extension")
sys.path.insert(0, HERE)
import test_ship_reship as _lab  # noqa: E402  the lab kernel's environment
from test_live_paused_window_browser import _free_port  # noqa: E402

N_SESSIONS = 27
TURNS_EACH = 12
GROUPS = ("web", "api", "tests")   # names web-01.., api-02.., tests-03..: #only=web shows nine of the twenty-seven


def sid_of(i):
    return "%08d-1111-2222-3333-%012d" % (i, i)


def name_of(i):
    return "%s-%02d" % (GROUPS[i % 3], i)


# the lab's own driver head: the shared one (the window lab's) expects one session with forty rendered rows and a bottom landing
DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));
let browser;
try { browser = await chromium.launch(cfg.launch || {}); }
catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
const page = await browser.newPage({ viewport: { width: 1200, height: 700 } });
const pageEvents = [];
page.on("pageerror", (e) => pageEvents.push("pageerror:" + String(e).slice(0, 300)));
page.on("console", (m) => { if (m.type() === "error") pageEvents.push("console:" + m.text().slice(0, 300)); });
// ── the cold-boot diet roads ──
// every dial's URL (the shim's new WebSocket), and every frame the page receives with a clock, from before the page's scripts run
await page.addInitScript(() => {
  window.__dials = []; const W = window.WebSocket;
  window.WebSocket = function (url, protos) { window.__dials.push(String(url)); return protos === undefined ? new W(url) : new W(url, protos); };
  window.WebSocket.prototype = W.prototype; window.WebSocket.CONNECTING = 0; window.WebSocket.OPEN = 1; window.WebSocket.CLOSING = 2; window.WebSocket.CLOSED = 3;
  window.__frames = []; window.__t0 = performance.now(); window.__idles = 0;
  window.__sent = []; const send = WebSocket.prototype.send;   // every frame the page sends its kernel (the prefetch's needFull asks among them)
  WebSocket.prototype.send = function (d) { try { const m = JSON.parse(d); if (m && m.type) window.__sent.push(m); } catch (e) { /* not a frame */ } return send.call(this, d); };
  const ric = window.requestIdleCallback; if (typeof ric === "function") window.requestIdleCallback = function (cb, o) { window.__idles++; return ric.call(window, cb, o); };
  try { window.__loads = Number(sessionStorage.getItem("romp-lab:loads") || "0") + 1; sessionStorage.setItem("romp-lab:loads", String(window.__loads)); } catch (e) { window.__loads = -1; }
  window.addEventListener("message", (e) => { const m = e.data; if (!m || !m.type) return;
    window.__frames.push({ t: Math.round(performance.now() - window.__t0), type: m.type, id: m.id || null, n: Array.isArray(m.events) ? m.events.length : null, skel: Array.isArray(m.skeleton) ? m.skeleton.length : null }); });
  // paint marks: the first transcript row, the strip at twenty-seven tabs
  window.__paint = { firstRow: null, strip27: null, skelAtStrip27: null, skelMax: 0 };
  const mo = new MutationObserver(() => {
    if (window.__paint.firstRow === null && document.querySelector("#content .turn[data-uuid]")) window.__paint.firstRow = Math.round(performance.now() - window.__t0);
    const sk = document.querySelectorAll("#tabs .tab-skeleton").length; if (sk > window.__paint.skelMax) window.__paint.skelMax = sk;
    if (window.__paint.strip27 === null && document.querySelectorAll("#tabs .tab, #tabs [data-sid]").length >= 27) { window.__paint.strip27 = Math.round(performance.now() - window.__t0); window.__paint.skelAtStrip27 = sk; }
  });
  document.addEventListener("DOMContentLoaded", () => mo.observe(document.documentElement, { childList: true, subtree: true, attributes: true }));
});
await page.goto(cfg.chat);
await page.waitForSelector("#tabs .tab, #tabs [data-sid]", { timeout: 20000 });
const sids = cfg.sids, selected = cfg.selected;
const fullsBy = () => page.evaluate(() => { const by = {}; for (const f of window.__frames) if (f.type === "session" && f.n) by[f.id] = (by[f.id] || 0) + 1; return by; });
const firstFrames = (n) => page.evaluate((k) => window.__frames.slice(0, k), n);
const allBuiltT = () => page.evaluate((all) => { const seen = new Set(); for (const f of window.__frames) { if (f.type === "session" && f.n) { seen.add(f.id); if (seen.size >= all.length) return f.t; } } return null; }, sids);
const waitFulls = (k, ms) => page.waitForFunction((k) => { const s = new Set(); for (const f of window.__frames) if (f.type === "session" && f.n) s.add(f.id); return s.size >= k; }, k, { timeout: ms }).catch(() => {});
// ROAD 4a (the FRESH open: the page the driver head opened, no reload record; the kernel half's case, measured here)
await waitFulls(sids.length, 60000);
const skelOf = () => page.evaluate(() => { const f = window.__frames.find((x) => x.skel !== null); return f ? { type: f.type, n: f.skel, t: f.t } : null; });
const painted = () => page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 0)))));
const nav = () => page.evaluate(() => ({ loads: window.__loads, href: location.href.replace(/token=[^&]*/, "token=X"), types: Array.from(new Set(window.__frames.map((f) => f.type))) }));
const fresh = { dial: (await page.evaluate(() => window.__dials[0] || null)), paint: await page.evaluate(() => window.__paint), allBuilt: await allBuiltT(), fulls: Object.keys(await fullsBy()).length,
  first: await firstFrames(40), skel: await skelOf(), nav: await nav() };
// the selected tab: the page's persisted state names it (the shim's ?active= reads activeId from the state blob)
await page.evaluate((sel) => { const k = "romp-vscode-state-chat"; let st = {}; try { st = JSON.parse(localStorage.getItem(k) || "{}") || {}; } catch (e) {} st.activeId = sel; localStorage.setItem(k, JSON.stringify(st)); }, selected);
// ROAD 1 + 2 + 4b: a RESTART reload (the reload core's durable record set as the core writes it)
await page.evaluate(() => { sessionStorage.setItem("romp:reloadReason", JSON.stringify({ reason: "restart", t: Date.now() })); });
await page.reload();
await page.waitForSelector("#tabs .tab, #tabs [data-sid]", { timeout: 20000 });
await page.waitForFunction(() => !!document.querySelector("#content .turn[data-uuid]"), null, { timeout: 30000 }).catch(() => {});
await page.waitForFunction(() => window.__paint.strip27 !== null, null, { timeout: 20000 }).catch(() => {});
const restart = { dial: (await page.evaluate(() => window.__dials[0] || null)), paint: await page.evaluate(() => window.__paint),
  first: await firstFrames(60), skel: await skelOf(), nav: await nav(),
  fullsBeforeFirstRow: await page.evaluate(() => { const t = window.__paint.firstRow; return window.__frames.filter((f) => f.type === "session" && f.n && t !== null && f.t <= t).map((f) => f.id); }),
  firstRowUuid: await page.evaluate(() => { const r = document.querySelector("#content .turn[data-uuid]"); return r ? r.getAttribute("data-uuid") : null; }) };
// ROAD 3 (the spread): the visible skeletons fill over idle callbacks
await waitFulls(sids.length, 60000);
const spread = { allBuilt: await allBuiltT(), fulls: Object.keys(await fullsBy()).length, paint: await page.evaluate(() => window.__paint),
  gaps: await page.evaluate(() => { const ts = window.__frames.filter((f) => f.type === "session" && f.n).map((f) => f.t); const g = []; for (let i = 1; i < ts.length; i++) g.push(ts[i] - ts[i - 1]); return g; }) };
// ROAD 3b (hidden tabs): the #only= filter on this top-level page hides the api-* and tests-* tabs; a restart reload under it must not
// prefetch them; lifting the filter loads them
await page.evaluate(() => { location.hash = "#only=web"; });
await page.evaluate(() => { sessionStorage.setItem("romp:reloadReason", JSON.stringify({ reason: "restart", t: Date.now() })); });
await page.reload();
await page.waitForSelector("#tabs .tab, #tabs [data-sid]", { timeout: 20000 });
const webIds = sids.filter((s, i) => cfg.names[i].startsWith("web"));
// strip facts, not frame accounting (this page's federation manager takes some frames off the message event): a skeleton tab element
// leaves the strip when its full lands, and a hidden tab has no element while the filter hides it
const skelCount = () => page.evaluate(() => document.querySelectorAll("#tabs .tab-skeleton").length);
const tabCount = () => page.evaluate(() => document.querySelectorAll("#tabs .tab, #tabs [data-sid]").length);
await page.waitForFunction(() => document.querySelectorAll("#tabs .tab, #tabs [data-sid]").length >= 9, null, { timeout: 15000 }).catch(() => {});
await painted();
const hiddenStart = { tabs: await tabCount(), skel: await skelCount() };
await page.waitForFunction(() => document.querySelectorAll("#tabs .tab-skeleton").length === 0, null, { timeout: 40000 }).catch(() => {});   // the visible skeletons fill on idle callbacks
await page.waitForTimeout(1500);   // idle callbacks past the visible set: a hidden tab built by mistake would show as a loaded tab when the filter lifts
const hidden = { dial: (await page.evaluate(() => window.__dials[0] || null)), start: hiddenStart, tabs: await tabCount(), skelVisibleAfterWait: await skelCount(), nav: await nav() };
await page.evaluate(() => { location.hash = ""; });
await page.waitForFunction(() => document.querySelectorAll("#tabs .tab, #tabs [data-sid]").length >= 27, null, { timeout: 15000 }).catch(() => {});
const skelAfterReveal = await skelCount();   // the tabs the filter hid come back: skeletons at the head (never built while hidden), loaded tabs at the base
await page.waitForFunction(() => document.querySelectorAll("#tabs .tab-skeleton").length === 0, null, { timeout: 60000 }).catch(() => {});
const revealed = { skelAfterReveal, skelFinal: await skelCount(), tabs: await tabCount() };
// ROAD 5 (round two, medium 1): a PLAIN reload right after a restart reload dials no diet: the record was consumed by the read that acted on it
await page.evaluate(() => { sessionStorage.setItem("romp:reloadReason", JSON.stringify({ reason: "restart", t: Date.now() })); });
await page.reload();
await page.waitForSelector("#tabs .tab, #tabs [data-sid]", { timeout: 20000 });
const restart2 = { dial: (await page.evaluate(() => window.__dials[0] || null)), recordLeft: await page.evaluate(() => sessionStorage.getItem("romp:reloadReason")) };
await page.reload();
await page.waitForSelector("#tabs .tab, #tabs [data-sid]", { timeout: 20000 });
const plain = { dial: (await page.evaluate(() => window.__dials[0] || null)) };
// ROAD 7 (round two, medium 3): the #only= filter lifted with the wire quiet: the revealed skeletons are asked for by the idle prefetch itself
await page.evaluate(() => { location.hash = "#only=web"; });
await page.evaluate(() => { sessionStorage.setItem("romp:reloadReason", JSON.stringify({ reason: "restart", t: Date.now() })); });
await page.reload();
await page.waitForSelector("#tabs .tab, #tabs [data-sid]", { timeout: 20000 });
await page.waitForFunction(() => document.querySelectorAll("#tabs .tab-skeleton").length === 0, null, { timeout: 40000 }).catch(() => {});   // the shown skeletons filled
await page.waitForFunction(() => { const f = window.__frames; const last = f.length ? f[f.length - 1].t : 0; return performance.now() - window.__t0 - last > 1500; }, null, { timeout: 30000 }).catch(() => {});   // the wire quiet: no frame for 1.5 s
const beforeReveal = await page.evaluate(() => ({ idles: window.__idles, frames: window.__frames.length, needFull: window.__sent.filter((m) => m.type === "needFull").length, skel: document.querySelectorAll("#tabs .tab-skeleton").length }));
await page.evaluate(() => { location.hash = ""; });
await painted();
const skelAtReveal = await page.evaluate(() => document.querySelectorAll("#tabs .tab-skeleton").length);   // the revealed tabs appear as skeletons: never built while hidden (a hidden tab has no strip element to count before the reveal)
const skelSidsAtReveal = await page.evaluate(() => Array.from(document.querySelectorAll("#tabs .tab-skeleton")).map((e) => e.getAttribute("data-id")).filter(Boolean));   // a tab carries its session as data-id
await page.waitForFunction((n) => window.__sent.filter((m) => m.type === "needFull").length > n, beforeReveal.needFull, { timeout: 10000 }).catch(() => {});
const afterReveal = await page.evaluate(([b, skelSids]) => { const asks = window.__sent.filter((m) => m.type === "needFull"); const firstAsk = asks.length > b.needFull ? asks[b.needFull] : null;
  // kernel frames that FILL a revealed skeleton, landing between the reveal and the first ask (a re-send for the already loaded active tab is not a fill)
  const fills = window.__frames.slice(b.frames).filter((f) => f.type === "session" && f.n && skelSids.includes(f.id)).length;
  return { idles: window.__idles, needFull: asks.length, firstAskWhy: firstAsk ? firstAsk.why : null, pushesBeforeFirstAsk: fills, skel: document.querySelectorAll("#tabs .tab-skeleton").length, skelSids: skelSids.length }; }, [beforeReveal, skelSidsAtReveal]);
afterReveal.skelAtReveal = skelAtReveal;
await page.waitForFunction(() => document.querySelectorAll("#tabs .tab-skeleton").length === 0, null, { timeout: 60000 }).catch(() => {});
const revealFilled = { skel: await page.evaluate(() => document.querySelectorAll("#tabs .tab-skeleton").length), needFull: await page.evaluate(() => window.__sent.filter((m) => m.type === "needFull" && m.why === "prefetch").length) };
// ROAD 6 (round two, medium 2): the served dashboard's shell after a restart record: every pane dials, the chat pane's dial alone carries the term
await page.evaluate(() => { sessionStorage.setItem("romp:reloadReason", JSON.stringify({ reason: "restart", t: Date.now() })); });
await page.goto(cfg.chat.replace("/chat?", "/?"));
await page.waitForTimeout(4000);
const paneDials = [];
for (const fr of page.frames()) { try { const ds = await fr.evaluate(() => (window.__dials || []).slice()); for (const d of ds) paneDials.push(d.replace(/token=[^&]*/, "token=X")); } catch (e) { /* a frame without the hook */ } }
await page.goto(cfg.chat);
await page.waitForSelector("#tabs .tab, #tabs [data-sid]", { timeout: 20000 });
// ROAD 1b: a BUILD reload dials as before
await page.evaluate(() => { sessionStorage.setItem("romp:reloadReason", JSON.stringify({ reason: "newer build", t: Date.now() })); });
await page.reload();
await page.waitForSelector("#tabs .tab, #tabs [data-sid]", { timeout: 20000 });
const build = { dial: (await page.evaluate(() => window.__dials[0] || null)) };
process.stdout.write("RESULT:" + JSON.stringify({ fresh, restart, spread, hidden, revealed, build, webIds, restart2, plain, beforeReveal, afterReveal, revealFilled, paneDials }) + "\n");
await browser.close();
"""


class ColdBootDiet(unittest.TestCase):
    maxDiff = None

    @classmethod
    def _skip(cls, why):
        if os.environ.get("ROMP_SERVED_TESTS_REQUIRE") == "1":
            raise AssertionError("ROMP_SERVED_TESTS_REQUIRE=1 but the served lab could not run: " + why)
        raise unittest.SkipTest(why)

    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(os.path.join(EXT, "node_modules", "playwright")):
            cls._skip("extension deps absent (npm ci not run here) — the served guard needs them")
        cls.lab = tempfile.mkdtemp(prefix="cold-boot-diet-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            cls._skip("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
        dist = os.path.join(cls.lab, "dist")
        copy_dist(os.path.join(EXT, "dist"), dist)
        cls.state = os.path.join(cls.lab, "xdg", "romp")
        cwd = os.path.join(cls.lab, "proj")
        for d in ("names", "sdk", "states"):
            os.makedirs(os.path.join(cls.state, d), exist_ok=True)
        os.makedirs(cwd, exist_ok=True)
        Path(cls.state, "session-hosts").write_text("off\n")
        Path(cls.state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 100}, "seven_day": {"pct": 10}}))
        claude = os.path.join(cls.lab, "claude")
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        base = int(time.time()) - 3 * 3600
        cls.sids, cls.names = [], []
        for i in range(1, N_SESSIONS + 1):
            sid, name = sid_of(i), name_of(i)
            cls.sids.append(sid); cls.names.append(name)
            Path(cls.state, "names", sid).write_text("%s\t%s\t\t\n" % (name, cwd))
            Path(cls.state, "sdk", sid + ".json").write_text(json.dumps(
                {"sid": sid, "name": name, "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": sid, "alive": True,
                 "model": "claude-fable-5-1", "liveModel": "Fable 5.1"}))
            recs, prev = [], None
            for k in range(TURNS_EACH):
                t0 = base + i * 60 + 2 * k
                u = "%08d-2222-3333-4444-%012d" % (i, 2 * k); a = "%08d-2222-3333-4444-%012d" % (i, 2 * k + 1)
                tu = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t0)); ta = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t0 + 1))
                recs.append({"type": "user", "uuid": u, "parentUuid": prev, "timestamp": tu, "sessionId": sid,
                             "message": {"role": "user", "content": "question %d for %s about the notes api" % (k, name)}})
                recs.append({"type": "assistant", "uuid": a, "parentUuid": u, "timestamp": ta, "sessionId": sid,
                             "message": {"role": "assistant", "model": "claude-fable-5-1", "stop_reason": "end_turn",
                                         "content": [{"type": "text", "text": "answer %d for %s: the notes api keeps its shape." % (k, name)}]}})
                prev = a
            Path(proj, sid + ".jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
        cls.port = _free_port()
        cls.token = "testtok-coldboot"
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
            cls._skip("hermetic kernel never served /healthz here")
        cls._r = None

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "kernel", None):
            cls.kernel.kill()
            cls.kernel.wait()
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

    def _result(self):
        if getattr(type(self), "_fail", None):   # the driver failed once: every test reports that failure instead of re-driving the browser (seven runs of a minute each)
            self.fail(type(self)._fail)
        if self._r is None:
            cfg = os.path.join(self.lab, "diet.json")
            with open(cfg, "w") as f:
                json.dump({"chat": "http://127.0.0.1:%d/chat?token=%s" % (self.port, self.token), "sid": self.sids[0], "sids": self.sids,
                           "names": self.names, "selected": self.sids[2], "shots": ""}, f)   # session 3 (web-03): visible under #only=web
            driver = os.path.join(self.lab, "diet.mjs")
            Path(driver).write_text(DRIVER)
            p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=400,
                               env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
            if "browser-launch-failed" in p.stderr:
                self._skip("no playwright browser on this box")
            line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
            if line is None:
                type(self)._fail = "the driver produced no RESULT (stderr: %s)" % p.stderr[-2000:]
                self.fail(type(self)._fail)
            type(self)._r = json.loads(line[len("RESULT:"):])
        print("DIET:", json.dumps(self._r), file=sys.stderr)   # every test's call: pytest shows the failing test's captured stderr alone
        return self._r

    def test_the_first_dial_after_a_restart_reload_is_a_skeleton_dial_and_a_build_reload_dials_as_before(self):
        r = self._result()
        self.assertIsNotNone(r["restart"]["dial"], "the page dialed after the restart reload")
        self.assertIn("&skeleton=1", r["restart"]["dial"], "the first dial after a kernel restart's reload declares the diet: %r" % r["restart"]["dial"])
        self.assertIn("&active=" + self.sids[2], r["restart"]["dial"], "…beside the selected tab: %r" % r["restart"]["dial"])
        self.assertNotIn("skeleton=1", r["build"]["dial"] or "", "a build reload dials as before: %r" % r["build"]["dial"])
        self.assertNotIn("skeleton=1", r["fresh"]["dial"] or "", "a fresh open dials as before (the kernel half's case): %r" % r["fresh"]["dial"])

    def test_the_first_refresh_after_a_restart_reload_builds_the_selected_tab_first_and_the_rest_as_skeletons(self):
        r = self._result()
        rs = r["restart"]
        self.assertEqual(rs["paint"]["skelMax"], N_SESSIONS - 1, "the strip drew the other twenty-six as skeleton tabs: %r" % rs["paint"])
        self.assertEqual(rs["fullsBeforeFirstRow"], [self.sids[2]], "one full frame, the selected tab's, ahead of the first row painted: %r" % rs["fullsBeforeFirstRow"])
        self.assertIsNotNone(rs["firstRowUuid"], "a row painted: %r" % rs["paint"])
        self.assertIsNotNone(rs["paint"]["firstRow"]); self.assertIsNotNone(rs["paint"]["strip27"])

    def test_the_visible_skeletons_fill_on_later_idle_callbacks_and_hidden_tabs_wait_for_the_filter_to_show_them(self):
        r = self._result()
        self.assertEqual(r["spread"]["fulls"], N_SESSIONS, "every tab built in the end: %r" % r["spread"]["fulls"])
        h = r["hidden"]
        self.assertIn("&skeleton=1", h["dial"] or "")
        hidden_n = N_SESSIONS - len(r["webIds"])   # the strip carries one element beyond the tabs, so the counts are read against the unfiltered strip
        self.assertEqual(rv_tabs := r["revealed"]["tabs"], h["start"]["tabs"] + hidden_n, "the filter hid the eighteen api and tests tabs and showed the nine web tabs: %r then %r" % (h["start"], r["revealed"]))
        self.assertGreaterEqual(h["start"]["skel"], 1, "the shown tabs other than the selected start as skeletons: %r" % h["start"])
        self.assertEqual(h["skelVisibleAfterWait"], 0, "the shown skeletons filled on idle callbacks: %r" % h)
        rv = r["revealed"]
        self.assertGreaterEqual(rv["tabs"], N_SESSIONS, "lifting the filter shows every tab: %r" % rv)
        self.assertEqual(rv["skelAfterReveal"], hidden_n, "the tabs the filter hid come back as SKELETONS: none was built while hidden (at the base they came back loaded): %r" % rv)
        self.assertEqual(rv["skelFinal"], 0, "…and load once shown: %r" % rv)

    def test_a_plain_reload_after_a_restart_reload_dials_no_diet_the_record_consumed_on_the_read(self):
        # round two, medium 1
        r = self._result()
        self.assertIn("&skeleton=1", r["restart2"]["dial"] or "", "the restart reload dialed the diet: %r" % r["restart2"])
        self.assertIsNone(r["restart2"]["recordLeft"], "the read that acted on the record consumed it: %r" % r["restart2"])
        self.assertNotIn("skeleton=1", r["plain"]["dial"] or "", "the plain reload right after dials as before: %r" % r["plain"])

    def test_only_the_chat_panes_dial_carries_the_term_after_a_restart_record(self):
        # round two, medium 2: the served dashboard's shell opens every pane; the term is the chat pane's alone
        r = self._result()
        dials = r["paneDials"]
        apps = sorted(set(re.search(r"app=([a-z]+)", d).group(1) for d in dials if re.search(r"app=([a-z]+)", d)))
        self.assertGreaterEqual(len(apps), 2, "the shell dialed more than one pane: %r" % dials)
        with_term = sorted(set(re.search(r"app=([a-z]+)", d).group(1) for d in dials if "skeleton=1" in d))
        self.assertEqual(with_term, ["chat"] if "chat" in apps else [], "the term rides the chat pane's dial alone: %r" % dials)

    def test_lifting_the_filter_re_arms_the_idle_prefetch_with_no_push_in_between(self):
        # round two, medium 3
        r = self._result()
        b, a = r["beforeReveal"], r["afterReveal"]
        self.assertEqual(b["skel"], 0, "the shown skeletons had filled before the reveal (a hidden tab has no strip element): %r" % b)
        self.assertGreaterEqual(a["skelAtReveal"], 1, "the revealed tabs appeared as skeletons, never built while hidden: %r" % a)
        self.assertGreater(a["idles"], b["idles"], "the reveal scheduled an idle pass: %r -> %r" % (b, a))
        self.assertGreater(a["needFull"], b["needFull"], "…and the prefetch asked for a revealed skeleton: %r -> %r" % (b, a))
        self.assertEqual(a["firstAskWhy"], "prefetch", "…the ask is the prefetch's own: %r" % a)
        self.assertGreaterEqual(a["skelSids"], 1, "the revealed skeletons carry their sids in the strip: %r" % a)
        self.assertEqual(a["pushesBeforeFirstAsk"], 0, "…with no kernel push filling a revealed skeleton between the reveal and the prefetch's first ask: %r" % a)
        self.assertEqual(r["revealFilled"]["skel"], 0, "every revealed skeleton filled: %r" % r["revealFilled"])

    def test_the_measurement_is_reported(self):
        r = self._result()
        m = {"fresh": {"firstRow": r["fresh"]["paint"]["firstRow"], "strip27": r["fresh"]["paint"]["strip27"], "allBuilt": r["fresh"]["allBuilt"], "skeletonTabs": r["fresh"]["paint"]["skelMax"]},
             "restart": {"firstRow": r["restart"]["paint"]["firstRow"], "strip27": r["restart"]["paint"]["strip27"], "allBuilt": r["spread"]["allBuilt"], "skeletonTabs": r["restart"]["paint"]["skelMax"]},
             "hiddenRoad": {"start": r["hidden"]["start"], "skelVisibleAfterWait": r["hidden"]["skelVisibleAfterWait"], "revealed": r["revealed"]}}
        print("MEASURE:", json.dumps(m), file=sys.stderr)
        for k in ("fresh", "restart"):
            self.assertIsNotNone(m[k]["firstRow"], "%s: the selected tab painted a row" % k)
            self.assertIsNotNone(m[k]["strip27"], "%s: the strip painted twenty-seven tabs" % k)


if __name__ == "__main__":
    unittest.main()
