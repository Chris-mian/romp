#!/usr/bin/env python3
"""A HIDDEN tab's thread takes its frames through the keyed paint too (2026-09-23): only the units that changed touch its DOM.

The page keeps one thread per session and brings a hidden one up to date on its frames (in idle, so a switch is instant). Before
the keyed paint, every such frame rebuilt the hidden thread's whole window, in compact mode on every frame and in normal mode on
every full frame or shrink: on a dashboard with many sessions that was most of the page's DOM work, competing with the thread
the user was reading. The lab: the real /chat page against a hermetic kernel holding two sessions, each with a transcript longer
than the kernel's tail (so each thread opens on a top spacer over a gap). The page shows `web`; `api` stays hidden while its
transcript grows. On the hidden thread:
  1. the frame for a new reply adds that reply's unit and touches nothing else: no node painted before it is removed, the top
     spacer is never touched;
  2. the same tail again, several times over (a kernel repeating itself), mutates nothing;
  3. switching to the tab shows the thread as it now stands with no rebuild: nothing painted while it was hidden is removed.
Compact mode (the default) and normal mode. SYNTHETIC fixtures only (a notes-api dashboard with sessions named web and api);
skips loudly without the extension deps or a Playwright browser.
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
import urllib.request
from pathlib import Path

from tests.dist_copy import copy_dist

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
EXT = os.path.join(ROOT, "vscode-extension")
sys.path.insert(0, HERE)
import test_ship_reship_served as _lab            # noqa: E402  the lab kernel's environment
import test_send_bubble_visible_browser as _sb    # noqa: E402  its helpers (the module, never its classes)
import test_send_tail_append_browser as _ta       # noqa: E402  the long transcript (the module, never its classes)

WEB = _sb.SID
API = "bbbbbbbb-1111-2222-3333-444444444444"
DRIVER_TIMEOUT_S = 300


def _records(sid, t0):
    """The long synthetic transcript, re-keyed for `sid` (its uuids prefixed, so the two sessions share none)."""
    out = []
    for r in _ta._records(t0):
        r = dict(r, sessionId=sid)
        if sid != WEB:
            r["uuid"] = "b-" + r["uuid"]
            if r.get("parentUuid"):
                r["parentUuid"] = "b-" + r["parentUuid"]
        out.append(r)
    return out


def _kernel(lab, port, token, t0):
    """One hermetic kernel holding both sessions (the send-bubble lab's helper, for two)."""
    state = os.path.join(lab, "xdg", "romp")
    claude = os.path.join(lab, "claude")
    for d in ("names", "sdk", "states"):
        os.makedirs(os.path.join(state, d), exist_ok=True)
    Path(state, "session-hosts").write_text("off\n")   # a test that mints its own state root pins the hosts off (CLAUDE.md)
    Path(state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 10}, "seven_day": {"pct": 10}}))
    transcripts = {}
    for sid, name in ((WEB, "web"), (API, "api")):
        cwd = os.path.join(lab, "proj-" + name)
        os.makedirs(cwd, exist_ok=True)
        Path(state, "names", sid).write_text("%s\t%s\t\t\n" % (name, cwd))
        Path(state, "sdk", sid + ".json").write_text(json.dumps(
            {"sid": sid, "name": name, "cwd": cwd, "mode": "auto", "effort": "high",
             "lastSid": sid, "alive": True, "model": "claude-fable-5-1", "liveModel": "Fable 5.1"}))
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        transcripts[sid] = os.path.join(proj, sid + ".jsonl")
        Path(transcripts[sid]).write_text("".join(json.dumps(r) + "\n" for r in _records(sid, t0)))
    env = _lab.kernel_env(lab, claude, os.path.join(lab, "dist"), port, token)
    log = os.path.join(lab, "kernel.log")
    proc = subprocess.Popen([os.path.join(BIN, "romp-kernel")], stdout=open(log, "w"), stderr=subprocess.STDOUT, env=env)
    for _ in range(120):
        try:
            urllib.request.urlopen("http://127.0.0.1:%d/healthz" % port, timeout=1)
            return proc, log, transcripts
        except Exception:
            time.sleep(0.5)
    proc.kill(); proc.wait()
    raise unittest.SkipTest("hermetic kernel never served /healthz here")


DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));
let browser;
try { browser = await chromium.launch(); }
catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
const page = await browser.newPage({ viewport: { width: 1000, height: 700 } });
page.on("pageerror", (e) => fs.appendFileSync(cfg.consoleLog, "pageerror: " + e + "\n"));
await page.addInitScript(({ compact, api }) => {
  try { localStorage.setItem("romp:settings", JSON.stringify({ compact })); } catch (e) {}
  window.__apiFrames = 0; window.__apiTail = null;
  window.addEventListener("message", (e) => { const m = e.data; if (!m || m.__injected || m.id !== api) return;
    if (m.type === "session" || m.type === "chatTail") window.__apiFrames++;
    if (m.type === "chatTail" && Array.isArray(m.events) && m.events.length) window.__apiTail = JSON.parse(JSON.stringify(m)); });
}, { compact: cfg.compact, api: cfg.api });
await page.goto(cfg.chat);
await page.waitForSelector("#tabs .tab", { timeout: 20000 });
const webTab = page.locator("#tabs .tab", { hasText: "web" }).first();
await webTab.waitFor({ timeout: 20000 }); await webTab.click();
await page.waitForSelector('#content .thread[data-session="' + cfg.web + '"] .turn.turn-user', { timeout: 20000 });
const waitFor = async (fn, arg, ms) => { try { await page.waitForFunction(fn, arg, { timeout: ms }); return true; } catch (e) { return false; } };
const painted = () => page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 0)))));
const idle = async () => { await painted(); await page.evaluate(() => new Promise((r) => (window.requestIdleCallback || setTimeout)(() => r(), { timeout: 2000 }))); await page.waitForTimeout(300); await painted(); };
const out = {};
// the hidden api thread, built in idle from its full frame
out.hiddenBuilt = await waitFor((sid) => { const th = document.querySelector('#content .thread[data-session="' + sid + '"]');
  return !!th && th.style.display === "none" && !!th.querySelector(".turn.turn-user") && !!th.querySelector(":scope > .tx-spacer-top"); }, cfg.api, 20000);
await idle();
const arm = (sid) => page.evaluate((sid) => {
  const th = document.querySelector('#content .thread[data-session="' + sid + '"]');
  const w = { kept: new Set(Array.from(th.children)), batches: [] };
  w.mo = new MutationObserver((recs) => { const b = { removed: [], added: [], keptRemoved: 0, spacer: 0 };
    for (const x of recs) {
      x.removedNodes.forEach((n) => { b.removed.push(String(n.className || n.nodeName).slice(0, 30) + "|" + ((n.dataset && n.dataset.uuid) || "")); if (w.kept.has(n)) b.keptRemoved++; if (n.classList && n.classList.contains("tx-spacer-top")) b.spacer++; });
      x.addedNodes.forEach((n) => { b.added.push(String(n.className || n.nodeName).slice(0, 30) + "|" + ((n.dataset && n.dataset.uuid) || "")); if (n.classList && n.classList.contains("tx-spacer-top")) b.spacer++; });
    }
    w.batches.push(b); });
  w.mo.observe(th, { childList: true });
  window.__hw = w;
}, sid);
const take = () => page.evaluate(() => { const w = window.__hw; const b = w.batches.splice(0); return b.map((x) => ({ ...x, removed: x.removed.slice(0, 6), added: x.added.slice(0, 6), nr: x.removed.length, na: x.added.length })); });
if (out.hiddenBuilt) {
  await arm(cfg.api);
  // 1. a new reply lands in the hidden session
  const f0 = await page.evaluate(() => window.__apiFrames);
  const reply = { type: "assistant", timestamp: new Date((cfg.t0 + 5000) * 1000).toISOString().replace(/\.\d{3}Z$/, ".000Z"), uuid: "b-hidden-r1", parentUuid: "b-aopen", sessionId: cfg.api,
                  message: { role: "assistant", model: "claude-fable-5-1", stop_reason: "tool_use", content: [{ type: "text", text: "A reply that landed while the api tab was hidden." }] } };
  fs.appendFileSync(cfg.apiTranscript, JSON.stringify(reply) + "\n");
  out.replyFrame = await waitFor((b) => window.__apiFrames > b, f0, 8000);
  out.replyPainted = await waitFor((sid) => !!document.querySelector('#content .thread[data-session="' + sid + '"] [data-uuid="b-hidden-r1"]'), cfg.api, 8000);
  await idle();
  out.reply = await take();
  out.stillHidden = await page.evaluate((sid) => document.querySelector('#content .thread[data-session="' + sid + '"]').style.display === "none", cfg.api);
  // 2. the same tail, eight times over
  out.repeatBase = await page.evaluate(() => !!window.__apiTail);
  await page.evaluate(() => { for (let k = 0; k < 8; k++) window.postMessage({ ...JSON.parse(JSON.stringify(window.__apiTail)), __injected: true }, "*"); });
  await idle(); await page.waitForTimeout(400); await idle();
  out.repeat = await take();
  // 3. the switch shows it as it stands
  await page.locator("#tabs .tab", { hasText: "api" }).first().click();
  await waitFor((sid) => document.querySelector('#content .thread[data-session="' + sid + '"]').style.display !== "none", cfg.api, 5000);
  await painted(); await page.waitForTimeout(400); await painted();
  out.show = await take();
  out.shownReply = await page.evaluate((sid) => !!document.querySelector('#content .thread[data-session="' + sid + '"] [data-uuid="b-hidden-r1"]'), cfg.api);
}
fs.writeFileSync(cfg.out, JSON.stringify(out));
fs.writeSync(1, "RESULT-FILE:" + cfg.out + "\n");
await browser.close();
process.exit(0);
"""


class ServedHiddenThreadKeyedPaint(unittest.TestCase):
    """Compact mode, the default."""
    maxDiff = None
    COMPACT = True

    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(os.path.join(EXT, "node_modules", "playwright")):
            raise unittest.SkipTest("extension deps absent (npm ci not run here) — the served guard needs them")
        cls.lab = tempfile.mkdtemp(prefix="hidden-keyed-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            raise unittest.SkipTest("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
        copy_dist(os.path.join(EXT, "dist"), os.path.join(cls.lab, "dist"))
        cls.t0 = int(time.time()) - 3000
        cls.port, cls.token = _sb._free_port(), "testtok-hiddenkeyed"
        try:
            cls.kernel, cls.klog, cls.transcripts = _kernel(cls.lab, cls.port, cls.token, cls.t0)
        except unittest.SkipTest:
            shutil.rmtree(cls.lab, ignore_errors=True)
            raise

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "kernel", None):
            cls.kernel.kill()
            cls.kernel.wait()
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

    def test_a_hidden_thread_repaints_only_what_changed_and_shows_without_a_rebuild(self):
        cfg = os.path.join(self.lab, "cfg.json")
        console_log = os.path.join(self.lab, "console.log")
        Path(console_log).write_text("")
        with open(cfg, "w") as f:
            json.dump({"chat": "http://127.0.0.1:%d/chat?token=%s" % (self.port, self.token), "web": WEB, "api": API, "compact": self.COMPACT,
                       "apiTranscript": self.transcripts[API], "t0": self.t0, "consoleLog": console_log, "out": os.path.join(self.lab, "result.json")}, f)
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
        print("HIDDEN-THREAD %s %s" % ("compact" if self.COMPACT else "normal", json.dumps(r)[:2500]))
        self.assertTrue(r.get("hiddenBuilt"), "the hidden api thread was built, on a top spacer, while web was shown: %r" % r)
        self.assertTrue(r["replyFrame"] and r["replyPainted"], "the hidden session's reply reached its thread: %r" % r)
        self.assertTrue(r["stillHidden"], "…while the thread stayed hidden")
        # 1. the reply's frame added its unit and touched nothing painted before it
        self.assertTrue(r["reply"], "the reply was painted into the hidden thread")
        for b in r["reply"]:
            self.assertEqual(b["keptRemoved"], 0, "no node painted before the reply left the hidden thread: %s" % json.dumps(r["reply"]))
            self.assertEqual(b["spacer"], 0, "the hidden thread's top spacer was never touched: %s" % json.dumps(r["reply"]))
        self.assertTrue(any("b-hidden-r1" in a for b in r["reply"] for a in b["added"]), "the reply's unit was added: %s" % json.dumps(r["reply"]))
        # 2. the same tail again and again: nothing
        self.assertTrue(r["repeatBase"], "the kernel's last tail for the hidden session was captured")
        self.assertEqual(r["repeat"], [], "an identical tail for a hidden thread, eight times, mutated nothing: %s" % json.dumps(r["repeat"])[:1500])
        # 3. the switch shows it as it stands: no rebuild
        self.assertTrue(r["shownReply"], "the reply is on the shown thread")
        for b in r["show"]:
            self.assertEqual(b["keptRemoved"], 0, "showing the tab removed nothing painted while it was hidden: %s" % json.dumps(r["show"])[:1500])
            self.assertEqual(b["spacer"], 0, "…nor re-made its top spacer: %s" % json.dumps(r["show"])[:1500])


class ServedHiddenThreadKeyedPaintNormal(ServedHiddenThreadKeyedPaint):
    """Normal mode (compact off)."""
    COMPACT = False


if __name__ == "__main__":
    unittest.main()
