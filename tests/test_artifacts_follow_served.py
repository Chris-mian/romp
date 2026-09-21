"""The Artifacts pane's second pass on the served dashboard (plans/artifacts-pane.md section 9, 2026-09-20): one hermetic kernel
over four synthetic sessions in the notes-api world (web, tests, api, docs), the chat split into two columns (web and tests in
the first, api and docs in the second, seeded the way the split script stores them), the pane enabled in the gear and toggled on.
Roads:
the picker lists exactly the tabs open across BOTH columns, in column order (the scope), and drops a tab the user closes;
the button and the rows wear the strip's label (the name bold in its identity colour) in the menu tokens' card (the dress);
unlocked, the pane follows the chat's tab switches, in either column, and a pick shows a session until the next switch
replaces it; locked, a switch leaves the pane where it is and a pick holds with the lock on; a new Write appended to the shown
session's transcript lists its file with no click and no Refresh control exists (growth); the lock and the shown session
survive a reload. Synthetic only: placeholder sids, invented names and paths under the lab's temp root."""
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
import test_ship_reship_served as _lab  # noqa: E402  the lab kernel's environment
from test_live_paused_window_browser import _free_port  # noqa: E402

SIDW = "11111111-2222-3333-4444-000000000961"   # web, the first column
SIDT = "11111111-2222-3333-4444-000000000962"   # tests, the first column
SIDA = "11111111-2222-3333-4444-000000000963"   # api, the second column
SIDD = "11111111-2222-3333-4444-000000000964"   # docs, the second column too (a switch there needs a second tab)
SESSIONS = ((SIDW, "web", "#1EA1EB"), (SIDT, "tests", "#E5484D"), (SIDA, "api", "#9CD2FF"), (SIDD, "docs", "#7BC96F"))
NAMES = {sid: name for sid, name, _ in SESSIONS}

DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));
let browser;
try { browser = await chromium.launch(cfg.launch || {}); }
catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
const out = { errors: [] };
const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 } });
let page = await ctx.newPage();
page.on("pageerror", (e) => out.errors.push(String(e).slice(0, 200)));
// the pane enabled in the gear's Panes section; the chat split into two columns, the second holding api (the split script's own store)
await page.addInitScript((a) => { try { const s = JSON.parse(localStorage.getItem("romp:settings") || "{}"); s.panes = Object.assign({}, s.panes || {}, { artifacts: true }); localStorage.setItem("romp:settings", JSON.stringify(s));
  localStorage.setItem("romp-chat-cols", JSON.stringify({ v: 2, cols: [{ n: 2, ids: a }] })); } catch (e) {} }, [cfg.api, cfg.docs]);
// every frame's sockets, recorded as they are made, so the reconnect leg can drop the pane's own socket (the shim redials it)
await page.addInitScript(() => { const W = window.WebSocket; const made = []; window.__sockets = made;
  const P = function (...a) { const s = new W(...a); made.push(s); return s; }; P.prototype = W.prototype; Object.assign(P, { CONNECTING: 0, OPEN: 1, CLOSING: 2, CLOSED: 3 }); window.WebSocket = P; });
const findFrame = async (test) => { for (let i = 0; i < 150; i++) { const f = page.frames().find((fr) => test(fr.url())); if (f) return f; await page.waitForTimeout(200); } return null; };
const isChat = (u) => /\/chat(\?|$)/.test(u), colOf = (u) => { const m = /[?&]col=(\d+)/.exec(u); return m ? Number(m[1]) : 1; };
const boot = async () => {
  // every frame records its outbound frames by type and sid (installed before any navigation: the reload's boot is read whole)
await page.addInitScript(() => { window.__sends = []; const orig = WebSocket.prototype.send;
  WebSocket.prototype.send = function (d) { try { const m = JSON.parse(d); if (m && m.type) window.__sends.push({ type: m.type, sid: m.sid || null }); } catch (e) {} return orig.call(this, d); }; });
await page.goto(cfg.landing);
  await page.waitForSelector("#f-chat", { timeout: 30000 });
  const c1 = await findFrame((u) => isChat(u) && colOf(u) === 1), c2 = await findFrame((u) => isChat(u) && colOf(u) === 2);
  if (c1) await c1.waitForSelector('#tabs .tab[data-id="' + cfg.web + '"]', { timeout: 60000 }).catch(() => {});
  if (c2) await c2.waitForSelector('#tabs .tab[data-id="' + cfg.docs + '"]', { timeout: 60000 }).catch(() => {});
  return { c1, c2 };
};
let { c1, c2 } = await boot();
out.columns = await page.evaluate(() => Array.from(document.querySelectorAll('iframe[id^="f-chat"]')).map((f) => f.id));
out.strips = { c1: c1 ? await c1.evaluate(() => Array.from(document.querySelectorAll("#tabs .tab[data-id]")).map((t) => t.getAttribute("data-id"))) : null,
               c2: c2 ? await c2.evaluate(() => Array.from(document.querySelectorAll("#tabs .tab[data-id]")).map((t) => t.getAttribute("data-id"))) : null };
await page.click('.rail-btn[data-pane="artifacts"]');
let fr = await findFrame((u) => /\/artifacts(\?|$)/.test(u));
const shown = () => fr.evaluate(() => { const b = document.getElementById("art-pick"); const n = b ? b.querySelector(".session-name") : null; const l = document.getElementById("art-lock");
  return { name: n ? n.textContent : null, notOpen: !!(b && b.querySelector(".art-not-open")), lock: l ? l.getAttribute("aria-pressed") : null, sid: localStorage.getItem("romp:artifacts:sid"), stored: localStorage.getItem("romp:artifacts:lock"),
    chip: n ? n.style.getPropertyValue("--chip-bg") : null, weight: n ? getComputedStyle(n).fontWeight : null, rows: Array.from(document.querySelectorAll(".art-row .art-name")).map((x) => x.textContent) }; });
const waitShown = (name) => fr.waitForFunction((nm) => { const b = document.getElementById("art-pick"); const n = b && b.querySelector(".session-name"); return !!n && n.textContent === nm; }, name, { timeout: 30000 }).then(() => true).catch(() => false);
const openCard = async () => { await fr.click("#art-pick", { timeout: 15000 }).catch(() => {}); await fr.waitForSelector("#art-picker", { timeout: 15000 }).catch(() => {});
  const card = await fr.evaluate(() => { const card = document.getElementById("art-picker"); if (!card) return null;
    const probe = document.createElement("div"); probe.style.background = "var(--menu-bg)"; probe.style.position = "absolute"; document.body.appendChild(probe); const menuBg = getComputedStyle(probe).backgroundColor; probe.remove();
    return { background: getComputedStyle(card).backgroundColor, menuBg, rows: Array.from(card.querySelectorAll(".ctx-item[data-sid]")).map((r) => ({ sid: r.getAttribute("data-sid"), name: (r.querySelector(".session-name") || {}).textContent, current: r.classList.contains("current"), chip: (r.querySelector(".session-name") || { style: { getPropertyValue: () => null } }).style.getPropertyValue("--chip-bg"), weight: getComputedStyle(r.querySelector(".session-name") || r).fontWeight })) }; });
  return card; };
const closeCard = () => fr.press("body", "Escape");
const pick = async (sid) => { await fr.click("#art-pick", { timeout: 15000 }).catch(() => {}); await fr.waitForSelector('#art-picker .ctx-item[data-sid="' + sid + '"]', { timeout: 15000 }).catch(() => {}); await fr.click('#art-picker .ctx-item[data-sid="' + sid + '"]', { timeout: 15000 }).catch(() => {}); };
const clickTab = async (col, sid) => { await col.click('#tabs .tab[data-id="' + sid + '"] .tab-label'); };
const activeOf = (col) => col.evaluate(() => { const a = document.querySelector("#tabs .tab.active"); return a ? a.getAttribute("data-id") : null; });
// a SWITCH is a click on a tab that is not the column's active one (a click on the active tab announces nothing)
const switchTo = async (col, sid) => { await clickTab(col, sid); await col.waitForFunction((t) => { const a = document.querySelector("#tabs .tab.active"); return !!a && a.getAttribute("data-id") === t; }, sid, { timeout: 15000 }).catch(() => {}); };
const otherIn = (active, pair) => (active === pair[0] ? pair[1] : pair[0]);
if (fr) {
  await fr.waitForSelector("#art-pick", { timeout: 30000 }).catch(() => {});
  // (1) the scope: the union of both columns, in column order (a column's first paint may precede the partition; the union
  // follows the strip's re-paint, so the read waits for the four tabs with the second column's last)
  await fr.waitForFunction((want) => { const ids = Array.from(document.querySelectorAll("#art-picker .ctx-item[data-sid]")).map((r) => r.getAttribute("data-sid")); return ids.length === 4 && ids.slice(2).every((x) => want.indexOf(x) >= 0); }, [cfg.api, cfg.docs], { timeout: 60000 }).catch(() => {});
  out.card = await openCard(); await closeCard();
  // the initial shown session is a chat's active tab (the kernel's frame on ready): whichever column reported last
  await fr.waitForFunction(() => { const b = document.getElementById("art-pick"); return !!(b && b.querySelector(".session-name")); }, null, { timeout: 30000 }).catch(() => {});
  out.initial = await shown();
  // (2) follow, unlocked: a switch in the first column moves the pane; a pick shows its session until a switch in the OTHER column replaces it
  const a1 = await activeOf(c1); const f1 = otherIn(a1, [cfg.web, cfg.tests]);
  await switchTo(c1, f1); out.follow = { want: cfg.names[f1], ok: await waitShown(cfg.names[f1]), ...(await shown()) };
  await switchTo(c1, a1); out.followBack = { want: cfg.names[a1], ok: await waitShown(cfg.names[a1]), ...(await shown()) };
  // (2b) the bar's buttons are built once: a repaint keeps the focused button and its identity (the reviewers of PR 1925). The repaint
  // is an active-chat relay for the shown session posted to the pane's own window (a click in another frame would take the focus
  // itself, so it cannot be the repaint's cause here); the pane repaints its bar on it, and the button under the focus is the same node
  await fr.evaluate(() => { const b = document.getElementById("art-pick"); b.__labMark = 1; b.focus(); window.postMessage({ romp: "activeChat", id: localStorage.getItem("romp:artifacts:sid") }, "*"); });
  await page.waitForTimeout(400);
  out.focusKeep = await fr.evaluate(() => ({ active: document.activeElement ? document.activeElement.id : null, sameNode: document.getElementById("art-pick").__labMark === 1 }));
  await pick(f1); out.pickUnlocked = { want: cfg.names[f1], ok: await waitShown(cfg.names[f1]), ...(await shown()) };
  const a2 = await activeOf(c2); const s2 = otherIn(a2, [cfg.api, cfg.docs]);
  await switchTo(c2, s2); out.replaced = { want: cfg.names[s2], ok: await waitShown(cfg.names[s2]), ...(await shown()) };
  // (3) the lock: a switch leaves the pane; a pick replaces the locked session and the lock stays on
  await fr.click("#art-lock", { timeout: 15000 }).catch(() => {});
  await fr.waitForFunction(() => { const l = document.getElementById("art-lock"); return !!l && l.getAttribute("aria-pressed") === "true"; }, null, { timeout: 10000 }).catch(() => {});
  await switchTo(c1, f1);
  await page.waitForTimeout(800);   // a relay that will not come cannot be awaited: the chat's switch is confirmed above, and the pane is read after it
  out.lockedStay = { want: cfg.names[s2], ...(await shown()) };
  await pick(cfg.web); out.lockedPick = { ok: await waitShown("web"), ...(await shown()) };
  // (3b) unlocking: the shown session stays until the next switch, which the pane follows again
  await fr.click("#art-lock", { timeout: 15000 }).catch(() => {});
  await fr.waitForFunction(() => { const l = document.getElementById("art-lock"); return !!l && l.getAttribute("aria-pressed") === "false"; }, null, { timeout: 10000 }).catch(() => {});
  out.unlocked = await shown();
  const a3 = await activeOf(c2); const s3 = otherIn(a3, [cfg.api, cfg.docs]);
  await switchTo(c2, s3); out.unlockedFollows = { want: cfg.names[s3], ok: await waitShown(cfg.names[s3]), ...(await shown()) };
  await fr.click("#art-lock", { timeout: 15000 }).catch(() => {});
  await fr.waitForFunction(() => { const l = document.getElementById("art-lock"); return !!l && l.getAttribute("aria-pressed") === "true"; }, null, { timeout: 10000 }).catch(() => {});
  await pick(cfg.web); await waitShown("web");
  // (4) the scope follows the strip: closing the tests tab (End session, confirmed) drops it from the picker
  await c1.click('#tabs .tab[data-id="' + cfg.tests + '"] .tab-close');
  await c1.waitForSelector("#confirm", { timeout: 10000 }).catch(() => {});
  await c1.click('#confirm button:has-text("End session")').catch(() => {});
  await c1.waitForFunction((t) => !document.querySelector('#tabs .tab[data-id="' + t + '"]'), cfg.tests, { timeout: 30000 }).catch(() => {});
  await fr.click("#art-pick", { timeout: 15000 }).catch(() => {});
  await fr.waitForFunction((t) => !!document.getElementById("art-picker") && !document.querySelector('#art-picker .ctx-item[data-sid="' + t + '"]'), cfg.tests, { timeout: 30000 }).catch(() => {});
  out.afterClose = await fr.evaluate(() => Array.from(document.querySelectorAll("#art-picker .ctx-item[data-sid]")).map((r) => r.getAttribute("data-sid")));
  await closeCard();
  // (5) growth: a Write appended to the shown session's transcript lists its file with no click
  out.beforeGrowth = await shown();
  fs.mkdirSync(cfg.webCwd + "/notes", { recursive: true }); fs.writeFileSync(cfg.webCwd + "/notes/new-file.md", "# new\n");
  const t = Math.floor(Date.now() / 1000);
  const iso = (x) => new Date(x * 1000).toISOString();
  fs.appendFileSync(cfg.webTranscript, JSON.stringify({ type: "user", uuid: "u9", parentUuid: cfg.webLast, timestamp: iso(t), sessionId: cfg.web, message: { role: "user", content: "and a new note" } }) + "\n"
    + JSON.stringify({ type: "assistant", uuid: "a9", parentUuid: "u9", timestamp: iso(t + 1), sessionId: cfg.web, message: { role: "assistant", model: "claude-fable-5-1", stop_reason: "tool_use", content: [{ type: "tool_use", id: "tu9", name: "Write", input: { file_path: cfg.webCwd + "/notes/new-file.md", content: "# new" } }] } }) + "\n");
  const grew = await fr.waitForFunction(() => Array.from(document.querySelectorAll(".art-row .art-name")).some((n) => n.textContent === "new-file.md"), null, { timeout: 60000 }).then(() => true).catch(() => false);
  out.growth = { grew, ...(await shown()), refresh: await fr.evaluate(() => !!document.getElementById("art-refresh") || /Refresh/.test(document.body.textContent || "")) };
  // (5a) a transcript move that changes no artifact: the signal re-asks, the answer's rows read the same, and the body's node, its rows
  // and the reader's place are untouched (the reviewers of PR 1925, D); the root counts accepted answers for this read
  const answers0 = await fr.evaluate(() => { const b = document.querySelector(".art-body"); b.__labMark = 1; b.scrollTop = 0; return Number(document.getElementById("artifacts-root").dataset.answers || 0); });
  const tq = Math.floor(Date.now() / 1000) + 2;
  fs.appendFileSync(cfg.webTranscript, JSON.stringify({ type: "user", uuid: "u9b", parentUuid: "a9", timestamp: iso(tq), sessionId: cfg.web, message: { role: "user", content: "and how does it read?" } }) + "\n"
    + JSON.stringify({ type: "assistant", uuid: "a9b", parentUuid: "u9b", timestamp: iso(tq + 1), sessionId: cfg.web, message: { role: "assistant", model: "claude-fable-5-1", stop_reason: "end_turn", content: [{ type: "text", text: "It reads well." }] } }) + "\n");
  const reanswered = await fr.waitForFunction((n) => Number(document.getElementById("artifacts-root").dataset.answers || 0) > n, answers0, { timeout: 60000 }).then(() => true).catch(() => false);
  out.sameSig = { reanswered, ...(await fr.evaluate(() => ({ sameBody: (document.querySelector(".art-body") || {}).__labMark === 1, rows: Array.from(document.querySelectorAll(".art-row .art-name")).map((n) => n.textContent) }))) };
  // (5b) the watch survives a socket drop and redial (round two, the medium): the pane's socket is closed, the shim redials it (a fresh
  // client on the kernel, no watch), the pane re-arms on the reopen, and the next Write appended lists with no click
  const sockets0 = await fr.evaluate(() => (window.__sockets || []).length);
  await fr.evaluate(() => { window.__wsups = 0; window.addEventListener("romp:wsup", () => { window.__wsups++; }); });
  await fr.evaluate(() => { for (const s of (window.__sockets || [])) { if (s.readyState === 1) s.close(); } });
  // the Write lands DURING the outage (before the redial): no signal can reach the dead socket, so only the re-ask on the reopen lists it
  fs.writeFileSync(cfg.webCwd + "/notes/after-redial.md", "# after\n");
  const t2 = Math.floor(Date.now() / 1000) + 5;
  fs.appendFileSync(cfg.webTranscript, JSON.stringify({ type: "user", uuid: "u10", parentUuid: "a9b", timestamp: iso(t2), sessionId: cfg.web, message: { role: "user", content: "one more during the outage" } }) + "\n"
    + JSON.stringify({ type: "assistant", uuid: "a10", parentUuid: "u10", timestamp: iso(t2 + 1), sessionId: cfg.web, message: { role: "assistant", model: "claude-fable-5-1", stop_reason: "tool_use", content: [{ type: "tool_use", id: "tu10", name: "Write", input: { file_path: cfg.webCwd + "/notes/after-redial.md", content: "# after" } }] } }) + "\n");
  const redialed = await fr.waitForFunction((n) => (window.__sockets || []).some((s, i) => i >= n && s.readyState === 1) && window.__wsups > 0, sockets0, { timeout: 60000 }).then(() => true).catch(() => false);
  const grewAfter = await fr.waitForFunction(() => Array.from(document.querySelectorAll(".art-row .art-name")).some((n) => n.textContent === "after-redial.md"), null, { timeout: 60000 }).then(() => true).catch(() => false);
  out.reconnect = { sockets0, redialed, grewAfter, ...(await shown()) };
  // (6) a reload keeps the lock and the shown session
  await page.reload(); await page.waitForSelector("#f-chat", { timeout: 30000 });
  fr = await findFrame((u) => /\/artifacts(\?|$)/.test(u));
  if (fr) {
    await fr.waitForFunction(() => { const b = document.getElementById("art-pick"); return !!(b && b.querySelector(".session-name")); }, null, { timeout: 30000 }).catch(() => {});
    await fr.waitForFunction(() => document.querySelectorAll(".art-row").length >= 1, null, { timeout: 60000 }).catch(() => {});
    // (6b) the boot asks ONCE (the reviewers of PR 1925, J): the shim flushes the queued watch and listing on the socket's open and fires
    // romp:wsup; when the bundle evaluated before that open the re-arm hears it and re-sends the watch alone (the base asked twice); when
    // the socket opened first nothing hears it and the boot's pair stands alone. Either way ONE listing
    await page.waitForTimeout(1500);   // a second ask that will not come cannot be awaited: the frames are read after the listing landed and a pause
    out.reloaded = { ...(await shown()), frames: await fr.evaluate((w) => window.__sends.filter((x) => (x.type === "watchArtifacts" || x.type === "listArtifacts") && x.sid === w).map((x) => x.type), cfg.web) };
  }
}
process.stdout.write("RESULT:" + JSON.stringify(out) + "\n");
await browser.close();
"""


def _records(sid, cwd, rel):
    t0 = int(time.time()) - 3600
    iso = lambda t: time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t))
    return [
        {"type": "user", "uuid": "u1", "parentUuid": None, "timestamp": iso(t0), "sessionId": sid, "message": {"role": "user", "content": "write %s" % rel}},
        {"type": "assistant", "uuid": "a1", "parentUuid": "u1", "timestamp": iso(t0 + 2), "sessionId": sid,
         "message": {"role": "assistant", "model": "claude-fable-5-1", "stop_reason": "tool_use",
                     "content": [{"type": "tool_use", "id": "tu1", "name": "Write", "input": {"file_path": os.path.join(cwd, rel), "content": "x"}}]}},
        {"type": "user", "uuid": "u2", "parentUuid": "a1", "timestamp": iso(t0 + 3), "sessionId": sid, "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tu1", "content": "ok"}]}},
        {"type": "assistant", "uuid": "a2", "parentUuid": "u2", "timestamp": iso(t0 + 5), "sessionId": sid,
         "message": {"role": "assistant", "model": "claude-fable-5-1", "stop_reason": "end_turn", "content": [{"type": "text", "text": "Written."}]}},
    ]


class ArtifactsFollowServed(unittest.TestCase):
    _r = None
    _fail = None

    @classmethod
    def _skip(cls, why):
        raise unittest.SkipTest(why)

    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(os.path.join(EXT, "node_modules", "playwright")):
            cls._skip("extension deps absent (npm ci not run here): the served guard needs them")
        cls.lab = tempfile.mkdtemp(prefix="artifacts-follow-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            cls._skip("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
        dist = os.path.join(cls.lab, "dist")
        copy_dist(os.path.join(EXT, "dist"), dist)
        cls.state = os.path.join(cls.lab, "xdg", "romp")
        for d in ("names", "sdk", "states"):
            os.makedirs(os.path.join(cls.state, d), exist_ok=True)
        Path(cls.state, "session-hosts").write_text("off\n")
        claude = os.path.join(cls.lab, "claude")
        cls.cwds, cls.transcripts = {}, {}
        for sid, name, color in SESSIONS:
            cwd = os.path.join(cls.lab, name); os.makedirs(cwd, exist_ok=True)
            Path(cwd, name + "-notes.md").write_text("# %s\n" % name)
            Path(cls.state, "names", sid).write_text("%s\t%s\t%s\t#ffffff\n" % (name, cwd, color))
            Path(cls.state, "sdk", sid + ".json").write_text(json.dumps(
                {"sid": sid, "name": name, "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": sid, "alive": True,
                 "model": "claude-fable-5-1", "liveModel": "Fable 5.1"}))
            proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
            os.makedirs(proj, exist_ok=True)
            tp = os.path.join(proj, sid + ".jsonl")
            Path(tp).write_text("".join(json.dumps(r) + "\n" for r in _records(sid, cwd, name + "-notes.md")))
            cls.cwds[sid], cls.transcripts[sid] = cwd, tp
        cls.port = _free_port()
        cls.token = "testtok-artifacts-follow"
        env = _lab.kernel_env(cls.lab, claude, dist, cls.port, cls.token)
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

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "kernel", None):
            cls.kernel.kill()
            cls.kernel.wait()
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

    def _result(self):
        if type(self)._fail:
            self.fail(type(self)._fail)
        if type(self)._r is None:
            cfg = os.path.join(self.lab, "cfg.json")
            with open(cfg, "w") as f:
                json.dump({"landing": "http://127.0.0.1:%d/?token=%s" % (self.port, self.token), "web": SIDW, "tests": SIDT, "api": SIDA, "docs": SIDD, "names": NAMES,
                           "webCwd": self.cwds[SIDW], "webTranscript": self.transcripts[SIDW], "webLast": "a2"}, f)
            driver = os.path.join(self.lab, "driver.mjs")
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
        print("ARTFOLLOW:", json.dumps(type(self)._r), file=sys.stderr)
        return type(self)._r

    def why(self, r):
        return " (result: %s; kernel log tail: %s)" % (json.dumps({k: r.get(k) for k in ("columns", "strips", "initial", "errors")}), open(self.klog).read()[-600:])

    def test_the_picker_lists_exactly_the_tabs_open_across_both_columns_in_column_order(self):
        r = self._result()
        self.assertEqual(r["errors"], [], "no page error")
        self.assertEqual(r["columns"], ["f-chat", "f-chat-2"], "two chat columns%s" % self.why(r))
        card = r["card"]
        self.assertIsNotNone(card, "the picker's card%s" % self.why(r))
        sids = [row["sid"] for row in card["rows"]]
        self.assertEqual(set(sids), {SIDW, SIDT, SIDA, SIDD}, "exactly the four open tabs: %r" % card["rows"])
        self.assertEqual(set(sids[:2]), {SIDW, SIDT}, "the first column's tabs first, the second column's after, in column order: %r" % sids)
        self.assertEqual(set(r["afterClose"]), {SIDW, SIDA, SIDD}, "the closed tab left the picker with the strip: %r" % r["afterClose"])

    def test_the_picker_wears_the_strips_label_in_the_menu_tokens(self):
        r = self._result()
        card = r["card"]
        self.assertEqual(card["background"], card["menuBg"], "the card's ground is the menu token's colour")
        by = {row["sid"]: row for row in card["rows"]}
        for sid, name, color in SESSIONS:
            self.assertEqual((by[sid]["name"], by[sid]["chip"].lower(), by[sid]["weight"]), (name, color.lower(), "600"), "the row's name bold in its identity colour: %r" % by[sid])
        self.assertEqual((r["initial"]["weight"], (r["initial"]["chip"] or "").lower() in {c.lower() for _, _, c in SESSIONS}), ("600", True), "the button wears the same label: %r" % r["initial"])

    def test_unlocked_the_pane_follows_the_chats_switches_in_either_column_and_a_pick_lasts_until_the_next_switch(self):
        r = self._result()
        self.assertIn(r["initial"]["name"], set(NAMES.values()), "a chat column's active tab at boot (the column that reported last), from the kernel's frame on ready: %r" % r["initial"])
        self.assertEqual(r["initial"]["lock"], "false", "a fresh browser starts unlocked")
        self.assertTrue(r["follow"]["ok"], "a switch in the first column moved the pane: %r%s" % (r["follow"], self.why(r)))
        self.assertTrue(r["followBack"]["ok"], "and back: %r" % r["followBack"])
        self.assertEqual((r["pickUnlocked"]["ok"], r["pickUnlocked"]["lock"]), (True, "false"), "a pick shows its session and does NOT lock: %r" % r["pickUnlocked"])
        self.assertTrue(r["replaced"]["ok"], "a switch in the OTHER column replaced the pick (the follow continues): %r" % r["replaced"])
        self.assertEqual(r["replaced"]["rows"], [r["replaced"]["want"] + "-notes.md"], "the listing followed the session")

    def test_the_bars_buttons_are_built_once_so_a_repaint_keeps_the_focused_button_and_its_identity(self):
        # in place of the artifacts.test.ts text pin on the refocus (the reviewers of PR 1925): the picker button focused, a switch repaints, the same node still has the focus
        r = self._result()
        self.assertEqual(r["focusKeep"], {"active": "art-pick", "sameNode": True}, "the focused picker button survives the repaint as the same node: %r" % r["focusKeep"])

    def test_a_same_signature_answer_after_a_transcript_move_touches_neither_the_body_nor_its_rows(self):
        # the reviewers of PR 1925 (D): every growth signal rebuilt the pane; a move that changes no artifact re-asks and the answer is a no-op
        r = self._result(); x = r["sameSig"]
        self.assertTrue(x["reanswered"], "the transcript move was signalled and answered (data-answers moved): %r" % x)
        self.assertTrue(x["sameBody"], "the body's node is the one from before the answer: %r" % x)
        self.assertEqual(x["rows"][:1], ["new-file.md"], "the rows read the same, newest first: %r" % x)

    def test_unlocking_keeps_the_shown_session_until_the_next_switch_which_the_pane_follows_again(self):
        r = self._result()
        self.assertEqual((r["unlocked"]["lock"], r["unlocked"]["name"]), ("false", "web"), "unlocked: nothing new yet, the shown session stays: %r" % r["unlocked"])
        self.assertEqual((r["unlockedFollows"]["ok"], r["unlockedFollows"]["name"]), (True, r["unlockedFollows"]["want"]), "the next switch moves the pane again: %r" % r["unlockedFollows"])

    def test_locked_a_switch_leaves_the_pane_and_a_pick_holds_with_the_lock_on_and_a_reload_keeps_both(self):
        r = self._result()
        self.assertEqual((r["lockedStay"]["lock"], r["lockedStay"]["name"]), ("true", r["lockedStay"]["want"]), "locked: a switch in the first column left the pane where it was: %r" % r["lockedStay"])
        self.assertEqual((r["lockedPick"]["ok"], r["lockedPick"]["lock"], r["lockedPick"]["name"]), (True, "true", "web"), "locked: a pick replaces the session, the lock stays on: %r" % r["lockedPick"])
        fr = r["reloaded"]["frames"]
        self.assertEqual(fr.count("listArtifacts"), 1, "the reloaded pane asks ONCE: the boot's listing, and the first open's re-arm re-sends the watch alone (the reviewers of PR 1925, J): %r" % r["reloaded"])
        self.assertIn(fr, (["watchArtifacts", "listArtifacts"], ["watchArtifacts", "listArtifacts", "watchArtifacts"]), "the boot's pair, then the re-arm's watch when the bundle heard the open: %r" % r["reloaded"])
        self.assertEqual((r["reloaded"]["lock"], r["reloaded"]["name"], r["reloaded"]["stored"]), ("true", "web", "1"), "a reload keeps the lock and the shown session: %r" % r["reloaded"])

    def test_the_watch_survives_a_socket_drop_and_redial_so_growth_still_lists(self):
        # round two, the medium: a fresh client on the kernel has no watch; the pane re-arms on the shim's reopen signal
        r = self._result()
        rc = r["reconnect"]
        self.assertTrue(rc["redialed"], "the pane's socket was dropped and the shim redialed it (a new open socket, romp:wsup fired): %r%s" % (rc, self.why(r)))
        self.assertTrue(rc["grewAfter"], "a Write appended after the redial lists with no click: the watch was re-armed on the reopen: %r" % rc)
        self.assertIn("after-redial.md", rc["rows"])

    def test_growth_lists_the_new_file_with_no_click_and_there_is_no_refresh_control(self):
        r = self._result()
        g = r["growth"]
        self.assertEqual(r["beforeGrowth"]["rows"], ["web-notes.md"], "before the growth: the one file%s" % self.why(r))
        self.assertTrue(g["grew"], "the appended Write's file listed itself (the kernel's signal, the pane's re-ask): %r%s" % (g, self.why(r)))
        self.assertEqual(g["rows"], ["new-file.md", "web-notes.md"], "newest first")
        self.assertFalse(g["refresh"], "no Refresh control anywhere on the page")


if __name__ == "__main__":
    unittest.main()
