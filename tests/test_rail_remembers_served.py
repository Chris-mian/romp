#!/usr/bin/env python3
"""THE RAIL REMEMBERS THE ARRANGEMENT (plans/pane-buttons-with-many-chats.md section 6; the user 2026-09-21: a hide remembers
the arrangement and a show restores it, as a rule for every rail button; nothing changes on the phone). One hermetic kernel
with two synthetic sessions (the notes-api world: web, api), Chromium on the shell page with the docking kit on, REAL pointer
events for every drag and real clicks on the rail's buttons.

The road, in code: the kit parks a hidden pane (its leaf leaves the tree) and used to re-open it at its DEFAULT dock (a chat
column right of the last chat, the feed right of the outline), so a pane the user had moved came back somewhere else. The
layout now keeps a remembered tree beside `parked` while anything is parked, and a returning pane goes back beside the
neighbour it had, with the share it had; what the user did meanwhile stands.

Driven here, each read against the arrangement recorded right before its hide:
  - the FEED moved under the chat, hidden and shown from the rail: back under the chat;
  - the OUTLINE moved beside the chat, hidden and shown: back where it was;
  - a chat COLUMN made by dragging a tab out (under the outline), every chat hidden by the chat button and shown: the column
    back under the outline and the first chat where it was;
  - the column CLOSED while hidden: the chat comes back where it was, the column's every record gone (tree, parked, memory);
  - the OUTLINE TOGGLED while the chat was hidden: the chat comes back above the feed as remembered, then the outline beside it;
  - the RE-JOIN rule: a tab dragged out and back onto the first strip closes its column and leaves no record of it;
  - the PHONE: at 390 px the kit stays off and the tab bar shows one pane at a time; no layout store is written.

Runs when ROMP_SERVED_TESTS_REQUIRE=1 (CI); skips loudly where the extension deps or a Playwright browser are absent."""
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
import test_ship_reship_served as _lab   # noqa: E402  the lab kernel's environment

REQUIRE = os.environ.get("ROMP_SERVED_TESTS_REQUIRE") == "1"
RING = 6
SID_WEB = "11111111-2222-4333-8444-0000000000f1"
SID_API = "11111111-2222-4333-8444-0000000000f2"


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _turns(sid, tag, t0, n):
    out, parent = [], None
    for k in range(n):
        u, a = "%s-u%02d" % (tag, k), "%s-a%02d" % (tag, k)
        t = t0 + 300 * k
        out.append({"type": "user", "timestamp": _iso(t), "uuid": u, "parentUuid": parent, "sessionId": sid, "promptSource": "typed",
                    "message": {"role": "user", "content": "turn %d: tidy the notes-api search ranking" % k}})
        out.append({"type": "assistant", "timestamp": _iso(t + 60), "uuid": a, "parentUuid": u, "sessionId": sid,
                    "message": {"role": "assistant", "model": "claude-opus-5", "stop_reason": "end_turn",
                                "content": [{"type": "text", "text": "The ranking weights now come from the config file."}]}})
        parent = a
    return out


DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));
let browser;
try { browser = await chromium.launch(); }
catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
const out = { errors: [] };
const PANES = { chat: true, fleet: true, feed: true, timeline: true, files: false };
const seed = (() => {
  if (window !== window.top) return;
  try {
    if (localStorage.getItem("__rr_seeded")) return;
    localStorage.setItem("__rr_seeded", "1");
    localStorage.setItem("romp-panes", JSON.stringify(__PANES__));
    localStorage.setItem("romp-pane-grow", JSON.stringify({ chat: 60, fleet: 34, feed: 40, files: 40 }));
    localStorage.removeItem("romp-layout");
    localStorage.setItem("romp:settings", JSON.stringify({ paneDocking: true, panes: { timeline: true, fleet: true, feed: true } }));
  } catch (e) {}
}).toString().replace("__PANES__", JSON.stringify(PANES));

const frame = (page) => page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r(1)))));
const rectsOf = (page) => page.evaluate(() => Object.fromEntries((window.__rompPaneDock ? window.__rompPaneDock.rects() : []).map((r) => [r.pane, r.rect])));
const leavesOf = (page) => page.evaluate(() => { const lay = window.__rompPaneDock && window.__rompPaneDock.layout(); const lv = (n) => n.pane ? [n.pane] : n.kids.flatMap(lv); return lay ? lv(lay.tree) : []; });
const shapeOf = (page) => page.evaluate(() => { const lay = window.__rompPaneDock && window.__rompPaneDock.layout(); const sh = (n) => n.pane ? n.pane : n.dir + "[" + n.kids.map(sh).join(",") + "]"; return lay ? sh(lay.tree) : null; });
const stored = (page) => page.evaluate(() => { const s = localStorage.getItem("romp-layout"); let p = null; try { p = JSON.parse(s); } catch (e) { p = null; } return { raw: s, parsed: p }; });
const snap = async (page) => ({ leaves: await leavesOf(page), shape: await shapeOf(page), rects: await rectsOf(page), stored: await stored(page) });
const waitLeaves = (page, pred) => page.waitForFunction((src) => { const lay = window.__rompPaneDock && window.__rompPaneDock.layout(); if (!lay) return false; const lv = (n) => n.pane ? [n.pane] : n.kids.flatMap(lv); const ls = lv(lay.tree); const f = new Function("ls", "return " + src); return !!f(ls); }, pred, { timeout: 20000 }).then(() => true).catch(() => false);
// a REAL pointer drag of a pane by its ring (the docking kit's own): press at (x0,y0), past the slop, to the waypoint, release
async function dragPane(page, x0, y0, wp) {
  await page.mouse.move(x0, y0); await page.mouse.down(); await frame(page);
  await page.mouse.move(x0 + 14, y0 + 14, { steps: 3 }); await frame(page);
  const armed = await page.evaluate(() => !!(window.__rompPaneDock && window.__rompPaneDock.dragging()));
  await page.mouse.move(wp.x, wp.y, { steps: 8 }); await frame(page);
  const zone = await page.evaluate(() => (window.__rompPaneDock && window.__rompPaneDock.zone ? window.__rompPaneDock.zone() : null));
  await page.mouse.up(); await frame(page); await frame(page);
  return { armed, zone };
}
const tabCentre = (page, fid, sid) => page.waitForFunction((a) => { const f = document.getElementById(a.fid); let d = null; try { d = f && f.contentDocument; } catch (e) { d = null; }
  const el = d && d.querySelector('#tabs .tab[data-id="' + a.sid + '"]'); if (!el || !el.draggable) return null; const r = el.getBoundingClientRect(); if (!(r.width > 0 && r.height > 0)) return null;
  const fr = f.getBoundingClientRect(); return { x: fr.left + f.clientLeft + r.left + r.width / 2, y: fr.top + f.clientTop + r.top + r.height / 2 }; }, { fid, sid }, { timeout: 30000 }).then((h) => h.jsonValue()).catch(() => null);
const startNativeDrag = async (page, pt) => {
  await page.evaluate(() => { window.__labTabDrag = null; if (!window.__labTabDragWired) { window.__labTabDragWired = true; window.addEventListener("message", (e) => { if (e && e.data && e.data.romp === "tabDrag") window.__labTabDrag = e.data; }); } });
  await page.mouse.move(pt.x, pt.y); await page.mouse.down();
  for (const st of [[2, 0], [6, 2], [12, 6], [20, 12], [30, 20]]) await page.mouse.move(pt.x + st[0], pt.y + st[1]);
  return await page.waitForFunction(() => !!(window.__labTabDrag && window.__labTabDrag.on), null, { timeout: 15000 }).then(() => true).catch(() => false);
};
// a tab dragged out of the first strip into the bottom half of `targetPane`: its own column pane there (chat-pane-2)
async function tabOut(page, targetPane) {
  const pt = await tabCentre(page, "f-chat", cfg.api); if (!pt) return { tab: null };
  const started = await startNativeDrag(page, pt);
  await page.waitForFunction(() => document.querySelectorAll(".pd-tabzone").length >= 2, null, { timeout: 10000 }).catch(() => {});
  const t = (await rectsOf(page))[targetPane];
  await page.mouse.move(t.x + t.w / 2, t.y + t.h * 0.85, { steps: 10 }); await frame(page);
  await page.mouse.up(); await frame(page);
  const landed = await waitLeaves(page, 'ls.includes("chat-pane-2")');
  const moved = await page.waitForFunction((sid) => { const f = document.getElementById("f-chat-2"); let d = null; try { d = f && f.contentDocument; } catch (e) { d = null; } return !!(d && d.querySelector('#tabs .tab[data-id="' + sid + '"]')); }, cfg.api, { timeout: 30000 }).then(() => true).catch(() => false);
  await page.waitForFunction(() => document.querySelectorAll(".pd-tabzone, .col-drop").length === 0, null, { timeout: 10000 }).catch(() => {});
  await frame(page);
  return { tab: pt, started, landed, moved };
}
const rail = async (page, key) => { await page.locator('.rail-btn[data-pane="' + key + '"]').click(); await frame(page); };
const chatLeaf = (p) => p === "chat-pane" || /^chat-pane-\d+$/.test(p);

async function desktop() {
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  await ctx.addInitScript("(" + seed + ")()");
  const page = await ctx.newPage();
  const o = { errors: [] };
  page.on("pageerror", (e) => o.errors.push(String(e && e.stack || e).slice(0, 300)));
  await page.goto(cfg.url);
  o.ready = await page.waitForFunction(() => { const pd = window.__rompPaneDock; if (!pd || !pd.on()) return false; const r = pd.rects(); if (r.length < 4) return false;
    const f = document.getElementById("f-chat"); const d = f && f.contentDocument; return !!(d && d.getElementById("tabbar") && d.querySelectorAll("#tabs .tab[data-id]").length >= 2); }, null, { timeout: 60000 }).then(() => true).catch(() => false);
  if (!o.ready) { o.absent = true; await ctx.close(); return o; }
  await page.waitForFunction(() => !!(window.__rompPaneDock.layout() && localStorage.getItem("romp-layout") && document.querySelectorAll(".pd-div").length >= 1), null, { timeout: 20000 }).catch(() => {});
  await frame(page);
  o.seed = await snap(page);
  // (1) the FEED moved under the chat, hidden and shown from the rail
  {
    const r = await rectsOf(page); const chat = r["chat-pane"], feed = r["feed-pane"];
    const drag = await dragPane(page, feed.x + feed.w / 2, feed.y + 1, { x: chat.x + chat.w / 2, y: chat.y + chat.h * 0.85 });
    const before = await snap(page);
    await rail(page, "feed"); const off = await waitLeaves(page, '!ls.includes("feed-pane")'); await frame(page);
    const hidden = await snap(page);
    await rail(page, "feed"); const on = await waitLeaves(page, 'ls.includes("feed-pane")'); await frame(page); await frame(page);
    o.feed = { drag, before, off, hidden, on, after: await snap(page) };
  }
  // (2) the OUTLINE moved to the chat's left half (beside the chat, inside the chat column), hidden and shown
  {
    const r = await rectsOf(page); const chat = r["chat-pane"], fl = r["fleet-pane"];
    const drag = await dragPane(page, fl.x + fl.w / 2, fl.y + 1, { x: chat.x + chat.w * 0.15, y: chat.y + chat.h / 2 });
    const before = await snap(page);
    await rail(page, "fleet"); const off = await waitLeaves(page, '!ls.includes("fleet-pane")'); await frame(page);
    const hidden = await snap(page);
    await rail(page, "fleet"); const on = await waitLeaves(page, 'ls.includes("fleet-pane")'); await frame(page); await frame(page);
    o.outline = { drag, before, off, hidden, on, after: await snap(page) };
  }
  // (3) a chat COLUMN under the outline (a tab dragged out into the outline's bottom half), every chat hidden by the chat button, shown
  {
    const out1 = await tabOut(page, "fleet-pane");
    const before = await snap(page);
    await rail(page, "chat"); const off = await waitLeaves(page, '!ls.some((p) => p === "chat-pane" || /^chat-pane-\\d+$/.test(p))'); await frame(page);
    const hidden = await snap(page);
    await rail(page, "chat"); const on = await waitLeaves(page, 'ls.includes("chat-pane") && ls.includes("chat-pane-2")');
    await page.waitForFunction(() => { const el = document.getElementById("chat-pane-2"); return !!el && el.getBoundingClientRect().width > 60; }, null, { timeout: 20000 }).catch(() => {});
    await frame(page); await frame(page);
    o.column = { out: out1, before, off, hidden, on, after: await snap(page) };
  }
  // (4) the column CLOSED while every chat is hidden: the chat comes back where it was, with no record of the column
  {
    const before = await snap(page);
    await rail(page, "chat"); const off = await waitLeaves(page, '!ls.some((p) => p === "chat-pane" || /^chat-pane-\\d+$/.test(p))'); await frame(page);
    await page.evaluate(() => { if (window.__rompCloseSplit) window.__rompCloseSplit(2); });
    const gone = await page.waitForFunction(() => { const lay = window.__rompPaneDock.layout(); return !document.getElementById("chat-pane-2") && !!lay && !lay.parked.includes("chat-pane-2"); }, null, { timeout: 20000 }).then(() => true).catch(() => false);
    await frame(page);
    const hidden = await snap(page);
    await rail(page, "chat"); const on = await waitLeaves(page, 'ls.includes("chat-pane")'); await frame(page); await frame(page);
    o.closedHidden = { before, off, gone, hidden, on, after: await snap(page) };
  }
  // (5) the OUTLINE TOGGLED while the chat is hidden: the chat back above the feed as remembered, then the outline beside it
  {
    const before = await snap(page);
    await rail(page, "chat"); const chatOff = await waitLeaves(page, '!ls.includes("chat-pane")'); await frame(page);
    await rail(page, "fleet"); const fleetOff = await waitLeaves(page, '!ls.includes("fleet-pane")'); await frame(page);
    const bothHidden = await snap(page);
    await rail(page, "chat"); const chatOn = await waitLeaves(page, 'ls.includes("chat-pane")'); await frame(page); await frame(page);
    const chatBack = await snap(page);
    await rail(page, "fleet"); const fleetOn = await waitLeaves(page, 'ls.includes("fleet-pane")'); await frame(page); await frame(page);
    o.toggledHidden = { before, chatOff, fleetOff, bothHidden, chatOn, chatBack, fleetOn, after: await snap(page) };
  }
  // (6) the RE-JOIN rule: a tab out again (under the outline), then back onto the first strip: the column closes, no record stays
  {
    const before = await snap(page);
    const out2 = await tabOut(page, "fleet-pane");
    const withColumn = await snap(page);
    const pt = await tabCentre(page, "f-chat-2", cfg.api);
    let back = { tab: pt };
    if (pt) {
      back.started = await startNativeDrag(page, pt);
      const chat = (await rectsOf(page))["chat-pane"];
      await page.mouse.move(chat.x + chat.w * 0.7, chat.y + cfg.ring + 12, { steps: 10 }); await frame(page);
      await page.mouse.up(); await frame(page);
      back.rejoined = await page.waitForFunction((sid) => { const g = document.getElementById("f-chat"); let d0 = null; try { d0 = g && g.contentDocument; } catch (e) { d0 = null; } const lay = window.__rompPaneDock.layout(); const lv = (n) => n.pane ? [n.pane] : n.kids.flatMap(lv);
        return !!(d0 && d0.querySelector('#tabs .tab[data-id="' + sid + '"]') && !document.getElementById("chat-pane-2") && lay && !lv(lay.tree).includes("chat-pane-2")); }, cfg.api, { timeout: 30000 }).then(() => true).catch(() => false);
      await frame(page); await frame(page);
    }
    o.rejoin = { before, out: out2, withColumn, back, after: await snap(page), zones: await page.evaluate(() => document.querySelectorAll(".pd-tabzone, .col-drop").length) };
  }
  if (cfg.shots) { fs.mkdirSync(cfg.shots, { recursive: true }); await page.screenshot({ path: cfg.shots + "/rail-remembers-desktop.png" }); }
  await ctx.close();
  return o;
}

async function phone() {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  await ctx.addInitScript("(" + seed + ")()");
  const page = await ctx.newPage();
  const o = { errors: [] };
  page.on("pageerror", (e) => o.errors.push(String(e && e.stack || e).slice(0, 300)));
  await page.goto(cfg.url);
  await page.waitForFunction(() => !!(document.getElementById("mtabs") && document.getElementById("f-chat")), null, { timeout: 60000 }).catch(() => {});
  await page.waitForTimeout(800);
  const read = () => page.evaluate(() => ({ mobile: !!(window.__rompMobileOn && window.__rompMobileOn()), kitOn: !!(window.__rompPaneDock && window.__rompPaneDock.on()), bodyKit: document.body.classList.contains("pane-docking"), tab: document.body.getAttribute("data-tab"), layout: localStorage.getItem("romp-layout"),
    visible: ["chat-pane", "fleet-pane", "feed-pane", "tl-pane"].filter((id) => { const el = document.getElementById(id); if (!el) return false; const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(el).display !== "none"; }) }));
  o.boot = await read();
  const tap = async (key) => { const b = page.locator('#mtabs button[data-pane="' + key + '"]'); if (await b.count()) { await b.first().click(); await page.waitForTimeout(300); } return await read(); };
  o.feedTab = await tap("feed");
  o.chatTab = await tap("chat");
  await ctx.close();
  return o;
}
out.desktop = await desktop();
out.phone = await phone();
fs.writeSync(1, "RESULT:" + JSON.stringify(out) + "\n");
await browser.close();
process.exit(0);
"""


class ServedRailRemembers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.procs = []
        try:
            cls._boot()
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def _boot(cls):
        if not os.path.isdir(os.path.join(EXT, "node_modules", "playwright")):
            if REQUIRE:
                raise AssertionError("ROMP_SERVED_TESTS_REQUIRE=1 but the extension deps are absent")
            raise unittest.SkipTest("extension deps absent (npm ci not run here): the served lab needs them")
        cls.lab = tempfile.mkdtemp(prefix="rail-remembers-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        assert b.returncode == 0, "esbuild failed: " + (b.stderr or b.stdout)[-400:]
        copy_dist(os.path.join(EXT, "dist"), os.path.join(cls.lab, "dist"))
        sub = os.path.join(cls.lab, "hub")
        state = os.path.join(sub, "xdg", "romp")
        claude = os.path.join(sub, "claude")
        cwd = os.path.join(sub, "proj")
        for d in ("names", "sdk", "states"):
            os.makedirs(os.path.join(state, d), exist_ok=True)
        os.makedirs(cwd, exist_ok=True)
        Path(state, "session-hosts").write_text("off\n")   # a lab root writes its own hosts off (the conftest rule)
        Path(state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 10}, "seven_day": {"pct": 10}}))
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        now = int(time.time())
        for sid, sname, tag in ((SID_WEB, "web", "w"), (SID_API, "api", "a")):
            Path(state, "names", sid).write_text("%s\t%s\t\t\n" % (sname, cwd))
            Path(state, "sdk", sid + ".json").write_text(json.dumps(
                {"sid": sid, "name": sname, "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": sid, "alive": True,
                 "model": "claude-opus-5", "liveModel": "Opus 5"}))
            Path(proj, sid + ".jsonl").write_text("".join(json.dumps(r) + "\n" for r in _turns(sid, tag, now - 3000, 4)))
        cls.port, cls.token = _free_port(), "testtok-railremembers"
        env = _lab.kernel_env(sub, claude, os.path.join(cls.lab, "dist"), cls.port, cls.token)
        cls.klog = os.path.join(cls.lab, "kernel.log")
        proc = subprocess.Popen([os.path.join(BIN, "romp-kernel")], stdout=open(cls.klog, "a"), stderr=subprocess.STDOUT, env=env)
        cls.procs.append(proc)
        for _ in range(120):
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/healthz" % cls.port, timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        else:
            raise AssertionError("hermetic kernel never served /healthz here")
        cls._drive()

    @classmethod
    def _drive(cls):
        cfg = os.path.join(cls.lab, "cfg.json")
        with open(cfg, "w") as f:
            json.dump({"url": "http://127.0.0.1:%d/?token=%s" % (cls.port, cls.token), "api": SID_API, "web": SID_WEB, "ring": RING, "shots": os.environ.get("ROMP_LAB_SHOT") or ""}, f)
        driver = os.path.join(cls.lab, "driver.mjs")
        Path(driver).write_text(DRIVER)
        p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=480, env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
        if p.returncode == 3:
            if REQUIRE:
                raise AssertionError("ROMP_SERVED_TESTS_REQUIRE=1 but no Chromium launched: " + p.stderr[-500:])
            raise unittest.SkipTest("no playwright browser on this box: the served leg needs one")
        assert p.returncode == 0, "driver failed:\n" + p.stdout[-3000:] + p.stderr[-3000:]
        line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
        assert line, "driver printed no result:\n" + p.stdout[-3000:] + p.stderr[-2000:]
        cls.r = json.loads(line[len("RESULT:"):])
        d = cls.r.get("desktop") or {}
        for k in ("feed", "outline", "column", "closedHidden", "toggledHidden", "rejoin"):
            s = d.get(k) or {}
            print("RAIL-REMEMBERS %s: before %r after %r" % (k, (s.get("before") or {}).get("shape"), (s.get("after") or {}).get("shape")), file=sys.stderr)

    @classmethod
    def tearDownClass(cls):
        for pr in getattr(cls, "procs", []):
            try:
                pr.kill(); pr.wait()
            except Exception:
                pass
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

    # ── helpers ─────────────────────────────────────────────────────────────────────────────────────────
    def _desktop(self):
        d = self.r["desktop"]
        self.assertFalse(d.get("absent"), "the kit came on with the panes and the two tabs: %r" % d)
        self.assertEqual(d["errors"], [], "no page error: %r" % d["errors"])
        return d

    def _same_arrangement(self, before, after, what, tol=2.0):
        self.assertEqual(after["leaves"], before["leaves"], "%s: the same panes in the same order: %r vs %r" % (what, after["leaves"], before["leaves"]))
        self.assertEqual(after["shape"], before["shape"], "%s: the same tree shape: %r vs %r" % (what, after["shape"], before["shape"]))
        for pane, r0 in before["rects"].items():
            r1 = after["rects"].get(pane)
            self.assertIsNotNone(r1, "%s: %s has a rectangle after" % (what, pane))
            for k in ("x", "y", "w", "h"):
                self.assertLessEqual(abs(r1[k] - r0[k]), tol, "%s: %s.%s back where it was: %r vs %r" % (what, pane, k, r1, r0))

    def _memory(self, snap):
        return (snap["stored"]["parsed"] or {}).get("remembered")

    def _no_record(self, snap, pane, what):
        raw = snap["stored"]["raw"] or ""
        self.assertNotIn(pane, raw, "%s: the layout store (tree, parked, memory) holds no record of %s: %r" % (what, pane, raw))
        self.assertNotIn(pane, snap["leaves"])

    # ── the tests ─────────────────────────────────────────────────────────────────────────────────────────
    def test_1_the_feed_moved_under_the_chat_comes_back_under_the_chat_after_the_rail_hides_and_shows_it(self):
        d = self._desktop()
        f = d["feed"]
        self.assertTrue(f["drag"]["armed"], "the ring press lifted the feed")
        self.assertIn("col[chat-pane,feed-pane]", f["before"]["shape"], "the feed docked under the chat: %r" % f["before"]["shape"])
        self.assertTrue(f["off"] and f["on"], "the rail hid and showed the feed: %r" % {k: f[k] for k in ("off", "on")})
        self.assertNotIn("feed-pane", f["hidden"]["leaves"])
        m = self._memory(f["hidden"])
        self.assertTrue(m and "feed-pane" in json.dumps(m), "the store remembers the arrangement while the feed is parked: %r" % f["hidden"]["stored"]["raw"])
        self._same_arrangement(f["before"], f["after"], "the feed shown again (its default dock is right of the outline)")
        self.assertIsNone(self._memory(f["after"]), "nothing parked: nothing remembered")

    def test_2_the_outline_moved_beside_the_chat_comes_back_where_it_was(self):
        d = self._desktop()
        o = d["outline"]
        self.assertTrue(o["drag"]["armed"], "the ring press lifted the outline")
        self.assertIn("row[fleet-pane,chat-pane]", o["before"]["shape"], "the outline beside the chat, inside the chat column: %r" % o["before"]["shape"])
        self.assertTrue(o["off"] and o["on"])
        self._same_arrangement(o["before"], o["after"], "the outline shown again (its default dock is right of the last chat)")
        self.assertIsNone(self._memory(o["after"]))

    def test_3_a_chat_column_under_the_outline_and_the_first_chat_come_back_where_they_were_after_the_chat_button_hides_and_shows_every_chat(self):
        d = self._desktop()
        c = d["column"]
        self.assertTrue(c["out"].get("tab") and c["out"]["started"] and c["out"]["landed"] and c["out"]["moved"], "the tab became its own column under the outline: %r" % c["out"])
        self.assertIn("col[fleet-pane,chat-pane-2]", c["before"]["shape"], "the column under the outline: %r" % c["before"]["shape"])
        self.assertTrue(c["off"], "the chat button parked every chat pane: %r" % c["hidden"]["leaves"])
        self.assertFalse(any(p == "chat-pane" or p.startswith("chat-pane-") for p in c["hidden"]["leaves"]))
        self.assertEqual(sorted(c["hidden"]["stored"]["parsed"]["parked"]), ["chat-pane", "chat-pane-2"])
        self.assertTrue(c["on"], "the second press brought both back")
        self._same_arrangement(c["before"], c["after"], "every chat shown again (the default docks would put the chat at the left and the column right of it)")

    def test_4_a_column_closed_while_every_chat_is_hidden_leaves_no_record_and_the_chat_comes_back_where_it_was(self):
        d = self._desktop()
        c = d["closedHidden"]
        self.assertTrue(c["off"] and c["gone"] and c["on"], "hidden, the column closed, shown: %r" % {k: c[k] for k in ("off", "gone", "on")})
        self._no_record(c["hidden"], "chat-pane-2", "while hidden, after the close")
        self._no_record(c["after"], "chat-pane-2", "after the show")
        want = dict(c["before"])
        want_leaves = [p for p in c["before"]["leaves"] if p != "chat-pane-2"]
        self.assertEqual(c["after"]["leaves"], want_leaves, "the chat back where it was, the column gone (the default dock would put the chat at the left): %r vs %r" % (c["after"]["leaves"], want_leaves))
        self.assertEqual(c["after"]["shape"], c["before"]["shape"].replace("col[fleet-pane,chat-pane-2]", "fleet-pane"), "the column's slot collapsed onto the outline: %r" % c["after"]["shape"])
        self.assertIsNone(self._memory(c["after"]))

    def test_5_the_outline_toggled_while_the_chat_is_hidden_the_chat_comes_back_above_the_feed_then_the_outline_beside_it(self):
        d = self._desktop()
        t = d["toggledHidden"]
        self.assertTrue(t["chatOff"] and t["fleetOff"] and t["chatOn"] and t["fleetOn"], "%r" % {k: t[k] for k in ("chatOff", "fleetOff", "chatOn", "fleetOn")})
        self.assertEqual(t["bothHidden"]["leaves"], ["feed-pane", "tl-pane"], "the feed alone over the band while both are hidden")
        self.assertEqual(t["chatBack"]["shape"], "col[col[chat-pane,feed-pane],tl-pane]", "the chat back ABOVE the feed, as remembered (its default dock is a row, left of the feed): %r" % t["chatBack"]["shape"])
        self._same_arrangement(t["before"], t["after"], "the outline shown again beside the chat")
        self.assertIsNone(self._memory(t["after"]))

    def test_6_a_tab_dragged_out_and_back_onto_the_first_strip_closes_its_column_and_leaves_no_record_of_it(self):
        d = self._desktop()
        r = d["rejoin"]
        self.assertTrue(r["out"].get("tab") and r["out"]["landed"] and r["out"]["moved"], "the column opened again: %r" % r["out"])
        self.assertIn("chat-pane-2", r["withColumn"]["leaves"])
        self.assertTrue(r["back"].get("tab") and r["back"]["started"] and r["back"]["rejoined"], "the tab back in the first strip and the column gone: %r" % r["back"])
        self._no_record(r["after"], "chat-pane-2", "after the re-join")
        self._same_arrangement(r["before"], r["after"], "the arrangement before the tab went out")
        self.assertEqual(r["zones"], 0, "no drop zone of either engine remains")

    def test_7_the_phone_is_unchanged_the_kit_stays_off_the_tab_bar_shows_one_pane_and_no_layout_store_is_written(self):
        p = self.r["phone"]
        self.assertEqual(p["errors"], [], p["errors"])
        for k in ("boot", "feedTab", "chatTab"):
            s = p[k]
            self.assertTrue(s["mobile"], "%s: the phone layout is on: %r" % (k, s))
            self.assertFalse(s["kitOn"] or s["bodyKit"], "%s: the kit stays off on the phone: %r" % (k, s))
            self.assertIsNone(s["layout"], "%s: no layout store is written on the phone: %r" % (k, s["layout"]))
            self.assertLessEqual(len(s["visible"]), 1, "%s: one pane at a time: %r" % (k, s["visible"]))
        self.assertEqual(p["feedTab"]["tab"], "feed"); self.assertEqual(p["chatTab"]["tab"], "chat")


if __name__ == "__main__":
    unittest.main()
