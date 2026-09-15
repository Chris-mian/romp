#!/usr/bin/env python3
"""A chat column opened on a HOST-PREFIXED tab stands (the user 2026-09-14): the SERVED leg.

The user dragged a session's tab to the chat's right edge on a federated dashboard (a remote host attached, so its
sessions ride `host:<uuid>`). The column opened, then folded itself ~250 ms later and the tab snapped back. Their
console instrument recorded the chain: the drop landed and the store held the column; the new column's frame
connected and posted hostsPending naming the tab's host (its handshake with that host not finished); the column
posted colEmpty; the shell removed the pane and the store reverted. The new column's page had heard the LOCAL
kernel's strip — which lists this kernel's sessions and nothing of the remote's — armed tabOrderSeen on it, found its
one member in neither the merged order nor the live set (both still local-only), and called the column empty. A
loopback board with bare ids never showed it: there the only host IS the one that reported.

The rule now (render.ts hostsSeen, chat-columns.ts columnEmptiness): a column judges a member absent only once the
member's host has reported on this socket; until then the verdict is "unknown" and nothing is said. This lab runs
the user's board: a HUB kernel with a local session and a second hermetic kernel checked in as host TESTHOST (the
mobile handshake, no ssh — the tests/test_file_preview_remote_served.py shape) owning one session, which the hub's
dashboard shows as TESTHOST:<sid>. A headless browser opens the hub's dashboard and ONE driver run walks the story:
  1. the remote tab is dragged from column 1 into the edge zone. The new column's relay frames from TESTHOST are
     HELD at the wire from the drop (playwright's routeWebSocket) until its LOCAL socket has delivered the kernel's
     first strip and a beat has passed — the window the user's timeline shows, held open rather than raced. In it the
     column stands, no colEmpty is posted, the store still lists the member (before the fix: colEmpty, pane gone,
     store reverted). Released, TESTHOST's strip lands, the column lists its member, and it still stands five
     seconds on: the frame attached, the store unchanged, no colEmpty ever posted;
  2. the real fold still works: the member's ✕ in column 2 (End session) empties the column at once — one colEmpty
     from column 2 naming the member as gone AND crossed, the pane removed, the store back to no columns. TESTHOST's
     frames to the column are held again for this step, so the verdict read is the page's own and not the far kernel's
     confirm of the close racing it over loopback (ackClosingTabs clears the cross the moment the kernel's strip agrees).
Skips LOUDLY when the extension deps or a playwright browser are absent (CI installs none). Synthetic only:
placeholder sids, host TESTHOST, invented notes-api prompt text, no real session data."""
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
from pathlib import Path

from tests.dist_copy import copy_dist

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
EXT = os.path.join(ROOT, "vscode-extension")
sys.path.insert(0, HERE)
import test_ship_reship as _lab   # noqa: E402  the lab kernel's environment (the module, not its classes)

SID_A = "11111111-2222-4333-8444-000000000601"   # "web": the hub's own session, column 1's
SID_R = "11111111-2222-4333-8444-000000000602"   # "api" on TESTHOST: the session the drag opens a column on
HOST = "TESTHOST"
REMOTE = HOST + ":" + SID_R                       # …as the hub's dashboard carries it (federation.ts prefixId)
CLOSE_ACK_MS_LAB = 1500   # render.ts CLOSE_ACK_MS for the lab (the romp:closeAckMs knob)
HOLD_MS = 5000            # how long the column must stand after its host's strip has landed


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _transcript(sid, tag, cwd, pairs):
    """`pairs` CLOSED user/assistant turns for `sid` (an OPEN turn would invite the boot reconcile to resume it)."""
    out, parent, t = [], None, 1_700_000_000
    filler = ["The ranking pass reads its weights from the notes-api config now.",
              "Tokenizer edge cases (hyphens, quotes) are covered by the new fixture set.",
              "Index rebuild time is dominated by the stemmer; caching its table halves it."]
    for i in range(pairs):
        u, a = "%s-u%02d" % (tag, i), "%s-a%02d" % (tag, i)
        out.append({"type": "user", "uuid": u, "parentUuid": parent, "sessionId": sid, "cwd": cwd, "timestamp": "2024-01-01T00:%02d:00Z" % (i % 60),
                    "promptSource": "typed", "message": {"role": "user", "content": "turn %d: what changed in the notes-api search?" % i}})
        out.append({"type": "assistant", "uuid": a, "parentUuid": u, "sessionId": sid, "cwd": cwd, "timestamp": "2024-01-01T00:%02d:30Z" % (i % 60),
                    "message": {"role": "assistant", "model": "claude-opus-5", "stop_reason": "end_turn",
                                "content": [{"type": "text", "text": filler[i % len(filler)]}]}})
        parent = a
    return "".join(json.dumps(r) + "\n" for r in out)


def _kernel(lab, name, port, token, sessions):
    """Boot one hermetic kernel: its own state root and dist, and `sessions` [(sid, name, tag)] with closed-turn transcripts."""
    state = os.path.join(lab, name, "xdg", "romp")
    claude = os.path.join(lab, name, "claude")
    cwd = os.path.join(lab, name, "proj")
    for d in ("names", "sdk", "states"):
        os.makedirs(os.path.join(state, d), exist_ok=True)
    os.makedirs(cwd, exist_ok=True)
    Path(state, "session-hosts").write_text("off\n")   # a lab root writes its own hosts off (the conftest rule)
    Path(state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 100}, "seven_day": {"pct": 10}}))   # park sends
    proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
    os.makedirs(proj, exist_ok=True)
    for sid, sname, tag in sessions:
        Path(state, "names", sid).write_text("%s\t%s\t\t\n" % (sname, cwd))
        Path(state, "sdk", sid + ".json").write_text(json.dumps(
            {"sid": sid, "name": sname, "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": sid, "alive": True}))
        Path(proj, sid + ".jsonl").write_text(_transcript(sid, tag, cwd, 6))
    env = _lab.kernel_env(os.path.join(lab, name), claude, os.path.join(lab, "dist"), port, token, ROMP_HOST_NAME=name.upper())
    log = os.path.join(lab, name + "-kernel.log")
    proc = subprocess.Popen([os.path.join(BIN, "romp-kernel")], stdout=open(log, "w"), stderr=subprocess.STDOUT, env=env)
    for _ in range(120):
        try:
            urllib.request.urlopen("http://127.0.0.1:%d/healthz" % port, timeout=1)
            return proc, log
        except Exception:
            time.sleep(0.5)
    proc.kill(); proc.wait()
    raise unittest.SkipTest("hermetic kernel %s never served /healthz here" % name)


DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));
let browser;
try { browser = await chromium.launch(); }
catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
const out = { t0: Date.now() };
const T = 15000;
// THE WIRE. Column 2's LOCAL socket (/chat?col=2 → its ws carries col=2): the first tabOrder frame the kernel sends it is
// the event the story keys on (the page arms tabOrderSeen on it). The RELAY sockets to TESTHOST (/remote/TESTHOST/ws, no
// col in the url — every column's looks alike): one opened while the hold is armed is the new column's, and its frames
// from the far kernel are HELD until the driver releases them, so the window between the local strip and the remote's
// stays open for as long as the step needs, never raced (tests/test_chat_split_served.py step 11's technique).
let col2StripResolve = null; const col2Strip = new Promise((r) => { col2StripResolve = r; });
await page.routeWebSocket((u) => /[?&]col=2(?:&|$)/.test(u.href) && !/\/remote\//.test(u.pathname), (ws) => {
  const server = ws.connectToServer();
  ws.onMessage((m) => server.send(m));
  server.onMessage((m) => { try { const f = JSON.parse(m); if (f && f.type === "tabOrder" && col2StripResolve) { col2StripResolve(Date.now()); col2StripResolve = null; } } catch (e) { /* a non-JSON frame */ } ws.send(m); });
  server.onClose(() => ws.close()); ws.onClose(() => server.close());
});
let holdRemote = false; const heldRemote = [];   // [{ws, frames}] the relay sockets opened under the hold
await page.routeWebSocket((u) => /\/remote\//.test(u.pathname), (ws) => {
  const server = ws.connectToServer();
  const held = holdRemote ? { ws, frames: [], open: true } : null;
  if (held) heldRemote.push(held);
  ws.onMessage((m) => server.send(m));
  server.onMessage((m) => { if (held && held.open) held.frames.push(m); else ws.send(m); });
  server.onClose(() => ws.close()); ws.onClose(() => server.close());
});
const releaseRemote = () => { holdRemote = false; let n = 0; for (const h of heldRemote) { h.open = false; for (const m of h.frames.splice(0)) { n++; try { h.ws.send(m); } catch (e) { /* the column closed under the hold */ } } } return n; };
const rearmRemote = () => { let n = 0; for (const h of heldRemote) { h.open = true; n++; } return n; };   // the same sockets held again (column 1's, opened before the hold, are never in the list)
// The shell's log (the top document): the split's colEmpty traffic with its source frame, each pane's hostsPending post,
// and every write of romp-chat-cols, stamped. And the lab's knob: the close backstop at 1.5 s.
await page.addInitScript((ackMs) => {
  if (window !== window.top) return;
  try { localStorage.setItem("romp:closeAckMs", String(ackMs)); } catch (e) { /* */ }
  window.__shellLog = [];
  window.addEventListener("message", (e) => {
    const m = e && e.data; if (!m || typeof m !== "object") return;
    if (m.romp !== "colEmpty" && m.romp !== "hostsPending") return;
    let src = null; try { const f = window.__rompFrameOfWin && window.__rompFrameOfWin(e.source); src = f ? f.id : null; } catch (err) { /* */ }
    window.__shellLog.push({ t: Date.now(), romp: m.romp, src, gone: m.gone, crossed: m.crossed, hosts: m.hosts, app: m.app });
  }, true);
  const setItem = Storage.prototype.setItem;
  Storage.prototype.setItem = function (k, v) { if (k === "romp-chat-cols") window.__shellLog.push({ t: Date.now(), store: v }); return setItem.call(this, k, v); };
}, cfg.ackMs);
const die = async (why) => {
  out.ms = Date.now() - out.t0;
  try { out.logAtDeath = await page.evaluate(() => (window.__shellLog || []).slice(-20)); } catch (e) { /* */ }
  fs.writeSync(1, "RESULT:" + JSON.stringify({ ...out, died: why }) + "\n");
  await browser.close();
  process.exit(0);
};
const waitFn = async (fn, arg, why) => page.waitForFunction(fn, arg, { timeout: T }).catch(async (e) => { await die(why + " (" + String(e).split("\n")[0] + ")"); });
const tabsOf = ([fid]) => { const f = document.getElementById(fid); const d = f && f.contentDocument; return d ? Array.from(d.querySelectorAll("#tabs .tab[data-id]")).map((t) => t.dataset.id) : null; };
const waitTabs = (fid, sids) => waitFn(([fid, sids]) => { const f = document.getElementById(fid); const d = f && f.contentDocument; if (!d) return false;
  const ids = Array.from(d.querySelectorAll("#tabs .tab[data-id]")).map((t) => t.dataset.id); return sids.every((s) => ids.includes(s)); }, [fid, sids], fid + " never showed tabs " + sids.join(","));
const waitActive = (fid, sid) => waitFn(([fid, sid]) => { const f = document.getElementById(fid); const d = f && f.contentDocument;
  const t = d && d.querySelector("#tabs .tab.active[data-id]"); return !!t && t.dataset.id === sid; }, [fid, sid], fid + " never activated " + sid);
const tabsIn = (fid) => page.evaluate(tabsOf, [fid]);
const activeIn = (fid) => page.evaluate((fid) => { const f = document.getElementById(fid); const d = f && f.contentDocument; const t = d && d.querySelector("#tabs .tab.active[data-id]"); return t ? t.dataset.id : null; }, fid);
const listsIn = (fid, sid, timeout) => page.waitForFunction(([fid, sid]) => { const f = document.getElementById(fid); const d = f && f.contentDocument; return !!d && Array.from(d.querySelectorAll("#tabs .tab[data-id]")).some((t) => t.dataset.id === sid); }, [fid, sid], { timeout }).then(() => true).catch(() => false);
const shell = () => page.evaluate(() => ({ frameIds: window.__rompChatFrameIds(), cols: localStorage.getItem("romp-chat-cols"), sets: window.__rompChatSets() }));
const shellLog = () => page.evaluate(() => window.__shellLog.slice());
const toastsIn = (fid) => page.evaluate((fid) => { const f = document.getElementById(fid); const d = f && f.contentDocument; return d ? Array.from(d.querySelectorAll(".warn-toast-msg")).map((e) => e.textContent) : null; }, fid);
const rectIn = (fid, sel) => page.evaluate(([fid, sel]) => { const f = document.getElementById(fid); const fr = f.getBoundingClientRect(); const el = f.contentDocument.querySelector(sel);
  if (!el) return null; const r = el.getBoundingClientRect(); return { x: fr.left + r.left, y: fr.top + r.top, w: r.width, h: r.height }; }, [fid, sel]);
const clickTab = async (fid, sid) => { const fr = await (await page.$("#" + fid)).contentFrame(); await fr.locator('#tabs .tab[data-id="' + sid + '"]').first().click(); };
// a real pointer drag (tests/test_chat_split_served.py step 9): down on the tab, past the threshold, over the edge zone, up
const dragStart = async (fid, sid) => {
  const t = await rectIn(fid, '#tabs .tab[data-id="' + sid + '"]');
  if (!t) await die("no tab for " + sid + " in " + fid);
  await page.mouse.move(t.x + t.w / 2, t.y + t.h / 2);
  await page.mouse.down();
  await page.mouse.move(t.x + t.w / 2 + 24, t.y + t.h / 2 + 6, { steps: 4 });
};

await page.goto(cfg.url, { waitUntil: "domcontentloaded" });
await waitFn(() => !document.getElementById("romp-boot"), null, "boot splash never cleared");
// column 1 shows the hub's own session and TESTHOST's under its prefix (the remote's strip has landed in column 1)
await waitTabs("f-chat", [cfg.sidA, cfg.remote]);
if ((await activeIn("f-chat")) !== cfg.sidA) { await clickTab("f-chat", cfg.sidA); await waitActive("f-chat", cfg.sidA); }
out.col1Before = await tabsIn("f-chat");
await page.evaluate(() => { window.__shellLog = []; });

// ---- 1. the drag: TESTHOST's tab into the edge; the new column's remote frames held from the drop ----
holdRemote = true;
await dragStart("f-chat", cfg.remote);
await waitFn(() => !!document.querySelector(".col-drop.col-drop-edge"), null, "the edge zone never mounted for the remote tab's drag");
const edge = await page.evaluate(() => { const z = document.querySelector(".col-drop.col-drop-edge"); const r = z.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; });
await page.mouse.move(edge.x, edge.y, { steps: 8 });
await waitFn(() => document.getElementById("col-ghost").classList.contains("on"), null, "the rectangle never showed over the edge zone");
const tDrop = Date.now();
await page.mouse.up();
out.s1 = { storeAtDrop: await page.evaluate(() => localStorage.getItem("romp-chat-cols")) };
out.s1.opened = await page.waitForFunction(() => !!document.getElementById("f-chat-2"), null, { timeout: T }).then(() => true).catch(() => false);
// the window: the column's LOCAL strip has landed (its tabOrderSeen armed) while TESTHOST's frames to it are still held
out.s1.localStripMs = await Promise.race([col2Strip.then((t) => t - tDrop), new Promise((r) => setTimeout(() => r(null), T))]);
await page.evaluate(() => new Promise((r) => setTimeout(r, 400)));   // the page's render, the shell's colEmpty hop and its store write: one bounded beat
out.s1.remoteHeld = heldRemote.map((h) => h.frames.length);
out.s1.inWindow = { frames: (await shell()).frameIds, cols: await page.evaluate(() => localStorage.getItem("romp-chat-cols")), log: await shellLog(), col2Tabs: await tabsIn("f-chat-2") };
out.s1.released = releaseRemote();
// TESTHOST's strip lands in the column: it lists its member…
out.s1.col2Lists = await listsIn("f-chat-2", cfg.remote, T);
const tListed = Date.now();
// …and stands five seconds on (the user's fold came ~250 ms after the drop). The wall clock, not the timer, is the floor
// the lab asserts: a Node timer can fire before Date.now() agrees the delay has passed (main's run of 2026-09-15 read
// 4999 against 5000), so after the timer, re-arm for whatever the clock still owes, until the hold is covered.
await page.waitForTimeout(cfg.holdMs);
while (Date.now() - tListed < cfg.holdMs) await page.waitForTimeout(Math.max(1, cfg.holdMs - (Date.now() - tListed)));   // bounded by the remainder: a few ms at most
out.s1.heldMs = Date.now() - tListed;
out.s1.after = { ...(await shell()), col1Tabs: await tabsIn("f-chat"), col2Tabs: await tabsIn("f-chat-2"), col2Active: await activeIn("f-chat-2"), col1Active: await activeIn("f-chat"), log: await shellLog(),
                 pane2: await page.evaluate(() => !!document.getElementById("chat-pane-2")) };

// ---- 2. the real fold: the member's ✕ in column 2 (End session) empties it at once ----
let reopened = true;
if (!(await page.$("#f-chat-2"))) {   // step 1 lost the column (the defect): this step stands on its own, so a column on the remote tab is opened again
  await page.evaluate((sid) => window.__rompMoveTab(sid, "new"), cfg.remote);
  reopened = await listsIn("f-chat-2", cfg.remote, T) && !!(await page.$("#f-chat-2"));   // …which the same defect folds too
}
await page.evaluate(() => { window.__shellLog = []; });
out.s2 = { reopened };
if (reopened) {
// TESTHOST's frames to the column are held again for the cross: the page's OWN verdict is what this step reads (colEmpty with the
// member crossed). Over loopback the far kernel's confirm of the close (its `closed` frame, its strip omitting the member) can
// reach the column before the page's deferred render, and ackClosingTabs clears the cross the moment the kernel agrees — the
// post then says crossed [] (right: nothing is left to hold back), which is the kernel's fold, not the cross's. One run in three.
out.s2.rearmed = rearmRemote();
const f2 = await (await page.$("#f-chat-2")).contentFrame();
const tCross = Date.now();
// the tab's ✕ (a delegated data-act="close" on the strip): a live session's cross opens the End confirm; "End session" posts
// endSession + closeTab and drops the tab locally — the user's own cross, the emptiness the shell holds back for
out.s2.crossed = await f2.evaluate((sid) => { const x = document.querySelector('#tabs .tab[data-id="' + sid + '"] .tab-close'); if (!x) return false; x.click(); return true; }, cfg.remote);
out.s2.confirm = await f2.waitForFunction(() => !!document.querySelector("#confirm .confirm-btn"), null, { timeout: T }).then(() => true).catch(() => false);
out.s2.confirmTitle = await f2.evaluate(() => { const t = document.querySelector("#confirm .confirm-title"); return t ? t.textContent : null; });
out.s2.ended = await f2.evaluate(() => { const b = Array.from(document.querySelectorAll("#confirm .confirm-btn")).find((e) => /End session/.test(e.textContent || "")); if (!b) return false; b.click(); return true; });
out.s2.paneGone = await page.waitForFunction(() => !document.getElementById("chat-pane-2") && !document.getElementById("f-chat-2"), null, { timeout: T }).then(() => true).catch(() => false);
out.s2.msToFold = Date.now() - tCross;
out.s2.after = await shell();
out.s2.log = await shellLog();
out.s2.heldDuringCross = heldRemote.map((h) => h.frames.length);
releaseRemote();
const left = tCross + cfg.ackMs + 800 - Date.now(); if (left > 0) await page.waitForTimeout(left);
out.s2.col1Tabs = await tabsIn("f-chat"); out.s2.toasts1 = await toastsIn("f-chat");
} else { out.s2.log = await shellLog(); out.s2.after = await shell(); }
out.ms = Date.now() - out.t0;
fs.writeSync(1, "RESULT:" + JSON.stringify(out) + "\n");
await browser.close();
process.exit(0);
"""


class ServedChatSplitHostPrefix(unittest.TestCase):
    """Two kernels (a hub and a checked-in TESTHOST), one page, one driver run in setUpClass; each method asserts one step."""
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.procs = []
        try:
            cls._boot()
        except BaseException:          # a skip OR a failure: never leave a kernel or a lab behind
            cls.tearDownClass()
            raise

    @classmethod
    def _boot(cls):
        if not os.path.isdir(os.path.join(EXT, "node_modules", "playwright")):
            raise unittest.SkipTest("extension deps absent (npm ci not run here) — the served lab needs them")
        probe = subprocess.run(["node", "-e", "const p=require(process.argv[1]);process.stdout.write(p.chromium.executablePath())",
                                os.path.join(EXT, "node_modules", "playwright")], capture_output=True, text=True)
        if probe.returncode != 0 or not os.path.exists(probe.stdout.strip()):
            raise unittest.SkipTest("no playwright browser on this box — the served lab needs one (CI installs none)")
        cls.lab = tempfile.mkdtemp(prefix="chat-split-host-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            raise unittest.SkipTest("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
        copy_dist(os.path.join(EXT, "dist"), os.path.join(cls.lab, "dist"))   # skips a concurrent build's staging files (tests/dist_copy.py)
        # the REMOTE kernel owns the session the drag opens a column on; the HUB owns column 1's and shows the remote's through the relay
        cls.rport, cls.rtoken = _free_port(), "testtok-remote-split"
        cls.hport, cls.htoken = _free_port(), "testtok-hub-split"
        rp, cls.rlog = _kernel(cls.lab, "testhost", cls.rport, cls.rtoken, [(SID_R, "api", 2)])
        cls.procs.append(rp)
        hp, cls.hlog = _kernel(cls.lab, "hub", cls.hport, cls.htoken, [(SID_A, "web", 1)])
        cls.procs.append(hp)
        body = json.dumps({"host": HOST, "kernelPort": cls.rport, "busPort": _free_port(), "token": cls.rtoken}).encode()
        req = urllib.request.Request("http://127.0.0.1:%d/checkin?token=%s" % (cls.hport, cls.htoken), data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            ans = json.loads(resp.read().decode())
        if not ans.get("ok"):
            raise unittest.SkipTest("the hub refused the check-in: %r" % ans)
        rows = []
        for _ in range(60):   # the hub's supervisor probes the peer and reports it up; the browser dials only then
            try:
                with urllib.request.urlopen("http://127.0.0.1:%d/tunnels?token=%s" % (cls.hport, cls.htoken), timeout=3) as r2:
                    rows = json.loads(r2.read().decode()).get("tunnels") or []
            except Exception:
                rows = []
            row = next((t for t in rows if t.get("host") == HOST), None)
            if row and row.get("status") == "up" and row.get("hasToken"):
                break
            time.sleep(0.5)
        else:
            raise unittest.SkipTest("the hub never reported the checked-in peer up: %r" % (rows,))
        cls.result, cls.driver_error = None, None
        cls._drive()

    @classmethod
    def _drive(cls):
        cfg = os.path.join(cls.lab, "cfg.json")
        with open(cfg, "w") as f:
            json.dump({"url": "http://127.0.0.1:%d/?token=%s" % (cls.hport, cls.htoken), "sidA": SID_A, "remote": REMOTE,
                       "ackMs": CLOSE_ACK_MS_LAB, "holdMs": HOLD_MS}, f)
        driver = os.path.join(cls.lab, "driver.mjs")
        with open(driver, "w") as f:
            f.write(DRIVER)
        try:
            p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=240,
                               env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
        except subprocess.TimeoutExpired as e:
            so = e.stdout if isinstance(e.stdout, str) else (e.stdout or b"").decode()
            cls.driver_error = "driver timed out; partial output:\n%s" % so
            return
        if p.returncode == 3:
            raise unittest.SkipTest("no playwright browser on this box — the served leg needs one (CI installs none)")
        if p.returncode != 0:
            cls.driver_error = "driver failed:\n" + p.stdout[-3000:] + p.stderr[-3000:]
            return
        line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
        if line is None:
            cls.driver_error = "driver printed no result:\n" + p.stdout[-3000:] + p.stderr[-3000:]
            return
        r = json.loads(line[len("RESULT:"):])
        if "died" in r:
            cls.driver_error = "driver aborted early: %s\n%s" % (r["died"], json.dumps(r, indent=1)[-3000:])
            return
        cls.result = r

    @classmethod
    def tearDownClass(cls):
        for p in getattr(cls, "procs", []):
            try:
                p.kill(); p.wait()
            except Exception:
                pass
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

    def _r(self):
        if self.driver_error:
            tail = ""
            for name in ("hlog", "rlog"):
                try:
                    with open(getattr(self, name)) as fh:
                        tail += "\n%s tail:\n%s" % (name, fh.read()[-1500:])
                except (OSError, AttributeError):
                    pass
            self.fail(self.driver_error + tail)
        return self.result

    def test_1_a_remote_hosts_tab_dragged_into_the_edge_opens_a_column_that_stands_through_the_local_strip_and_after_its_host_reports(self):
        r = self._r()
        s = r["s1"]
        self.assertIn(REMOTE, r["col1Before"], "the story starts with the remote session on column 1's strip under its host prefix: %r" % r["col1Before"])
        self.assertTrue(s["opened"], "the drop opened a second column: %r" % s)
        self.assertEqual(json.loads(s["storeAtDrop"]), {"v": 2, "cols": [{"n": 2, "ids": [REMOTE]}]}, "the store holds the column on the remote session at the drop")
        self.assertIsNotNone(s["localStripMs"], "column 2's local socket delivered the kernel's first strip inside the window: %r" % s)
        # THE WINDOW (the user's timeline): the local strip has landed, the remote's frames are held at the wire. Before the fix the
        # column posted colEmpty here, the shell removed the pane and the store reverted to no columns.
        w = s["inWindow"]
        self.assertEqual([e for e in w["log"] if e.get("romp") == "colEmpty"], [], "a column whose member's host has not reported says nothing about emptiness: %r" % w["log"])
        self.assertEqual(w["frames"], ["f-chat", "f-chat-2"], "the column stands through the window: %r" % w)
        self.assertEqual(json.loads(w["cols"]), {"v": 2, "cols": [{"n": 2, "ids": [REMOTE]}]}, "…and the store still lists its member: %r" % w)
        self.assertTrue(any(n > 0 for n in s["remoteHeld"]), "the hold was real — the new column's relay frames from TESTHOST were held: %r" % s["remoteHeld"])
        # released: the host's strip lands, the column lists its member and stands five seconds on
        self.assertTrue(s["col2Lists"], "column 2 lists the remote session once its host's strip lands: %r" % s)
        self.assertGreaterEqual(s["heldMs"], HOLD_MS, "the driver held the column for the whole hold by the wall clock: %r" % s["heldMs"])
        a = s["after"]
        self.assertTrue(a["pane2"], "#chat-pane-2 is still attached %d ms after the member was listed: %r" % (s["heldMs"], a))
        self.assertEqual(a["frameIds"], ["f-chat", "f-chat-2"])
        self.assertEqual(json.loads(a["cols"]), {"v": 2, "cols": [{"n": 2, "ids": [REMOTE]}]})
        self.assertEqual(a["col2Tabs"], [REMOTE], "column 2 shows the remote session alone: %r" % a)
        self.assertNotIn(REMOTE, a["col1Tabs"], "…and column 1 no longer lists it: %r" % a)
        self.assertEqual(a["col2Active"], REMOTE)
        self.assertEqual([e for e in a["log"] if e.get("romp") == "colEmpty"], [], "no colEmpty was ever posted for the column: %r" % a["log"])

    def test_2_the_members_cross_in_the_new_column_still_empties_and_folds_it(self):
        r = self._r()
        s = r["s2"]
        self.assertTrue(s["reopened"], "a column on the remote tab stands long enough to be crossed: %r" % s)
        self.assertGreaterEqual(s["rearmed"], 1, "the column's relay socket was held for the cross, so the verdict read is the page's own: %r" % s)
        self.assertTrue(s["crossed"], "the remote tab's ✕ was clicked in column 2: %r" % s)
        self.assertTrue(s["confirm"], "a live session's ✕ opens the End confirm: %r" % s)
        self.assertIn("api", s["confirmTitle"] or "", "the confirm names the session: %r" % s)
        self.assertTrue(s["ended"], "…and End session was chosen")
        self.assertTrue(s["paneGone"], "the emptied column folded (%r ms): %r" % (s["msToFold"], s))
        self.assertEqual(json.loads(s["after"]["cols"]), {"v": 2, "cols": []}, "the store is back to no columns: %r" % s["after"])
        self.assertEqual(s["after"]["frameIds"], ["f-chat"])
        posts = [e for e in s["log"] if e.get("romp") == "colEmpty"]
        self.assertEqual([(e["src"], e["gone"], e["crossed"]) for e in posts], [("f-chat-2", [REMOTE], [REMOTE])],
                         "one colEmpty, from column 2, naming the member gone AND crossed (the shell holds it back in column 1): %r" % s["log"])


if __name__ == "__main__":
    unittest.main()
