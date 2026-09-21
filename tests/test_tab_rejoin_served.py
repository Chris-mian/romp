#!/usr/bin/env python3
"""A TAB DRAGGED OUT, THE CHATS HIDDEN AND SHOWN, THE TAB DRAGGED BACK: the page stays usable (the user 2026-09-21, who
dragged one chat tab out of the strip into its own column, pressed the rail's chat button to hide every chat, pressed it
again, dragged the separated tab back into the strip, and found the page stuck: no tab could be selected and the wrong
cursor stayed on).

The road, in code: the docking kit's transparent hit areas take the drop of a tab on the first chat's strip (they sit above
the shipped split script's own zones), and the join closes the emptied source column INSIDE the drop handler. The source
page's dragend, the one event that told both the kit and the split script to take their zones down, dies with its frame.
The kit had already removed its areas at the drop; the split script's zones (`.col-drop`, inset 0 over every chat pane but
the source) stayed mounted over the first chat, so every click on its strip landed on a zone and the pointer wore the
zone's arrow. The fix ends an in-flight tab drag when its source column closes, on both sides.

One hermetic kernel with two synthetic sessions (the notes-api world: web, api), Chromium on the shell page with the kit on,
REAL pointer events for both drags and a real click on the rail button. Asserted after the drag back: a click on a tab in
the first strip selects it; the element under the strip is the chat's own iframe (no drop zone of either engine remains,
the drop rectangles are off); the shell body carries no drag, resize or grab class and no hand or resize cursor; the kit
holds no drag. Also pinned (the user's decision, 2026-09-21): the drop preview square shows no text in its centre, neither
the pane's title over a landing half nor the "joins" word over a strip.

A second context runs the same two drags with no hide and show between them, recorded beside the first (the same defect,
whatever the rail did in between).

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
SID_WEB = "11111111-2222-4333-8444-0000000000e1"
SID_API = "11111111-2222-4333-8444-0000000000e2"
DRAG_CLASSES = ("pd-drag", "pd-resize", "pd-resize-x", "pd-resize-y", "pd-alt", "drag", "dragh", "pd-grab-hover")


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
    if (localStorage.getItem("__tr_seeded")) return;
    localStorage.setItem("__tr_seeded", "1");
    localStorage.setItem("romp-panes", JSON.stringify(__PANES__));
    localStorage.setItem("romp-pane-grow", JSON.stringify({ chat: 60, fleet: 34, feed: 40, files: 40 }));
    localStorage.removeItem("romp-layout");
    localStorage.setItem("romp:settings", JSON.stringify({ paneDocking: true, panes: { timeline: true, fleet: true, feed: true } }));
  } catch (e) {}
}).toString().replace("__PANES__", JSON.stringify(PANES));

const frame = (page) => page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r(1)))));
const rectsOf = (page) => page.evaluate(() => Object.fromEntries((window.__rompPaneDock ? window.__rompPaneDock.rects() : []).map((r) => [r.pane, r.rect])));
const leavesOf = (page) => page.evaluate(() => { const lay = window.__rompPaneDock && window.__rompPaneDock.layout(); const lv = (n) => n.pane ? [n.pane] : n.kids.flatMap(lv); return lay ? lv(lay.tree) : []; });
const parkedOf = (page) => page.evaluate(() => { const lay = window.__rompPaneDock && window.__rompPaneDock.layout(); return lay ? lay.parked : null; });
const outlineRead = (page) => page.evaluate(() => { const o = document.getElementById("pd-outline"); if (!o) return null; const r = o.getBoundingClientRect();
  return { on: o.classList.contains("on"), free: o.classList.contains("free"), refused: o.classList.contains("refused"), text: o.textContent, x: r.left, y: r.top, w: r.width, h: r.height }; });
// the tab's centre in SHELL viewport px (the frame's offset added), once it is draggable and laid out
const tabCentre = (page, fid, sid) => page.waitForFunction((a) => { const f = document.getElementById(a.fid); let d = null; try { d = f && f.contentDocument; } catch (e) { d = null; }
  const el = d && d.querySelector('#tabs .tab[data-id="' + a.sid + '"]'); if (!el || !el.draggable) return null; const r = el.getBoundingClientRect(); if (!(r.width > 0 && r.height > 0)) return null;
  const fr = f.getBoundingClientRect(); return { x: fr.left + f.clientLeft + r.left + r.width / 2, y: fr.top + f.clientTop + r.top + r.height / 2 }; }, { fid, sid }, { timeout: 30000 }).then((h) => h.jsonValue()).catch(() => null);
// a REAL HTML5 drag of a tab: the press, a few moves past the browser's threshold; the page's dragstart posts tabDrag to the shell, heard here
const startNativeDrag = async (page, pt) => {
  await page.evaluate(() => { window.__labTabDrag = null; if (!window.__labTabDragWired) { window.__labTabDragWired = true; window.addEventListener("message", (e) => { if (e && e.data && e.data.romp === "tabDrag") window.__labTabDrag = e.data; }); } });
  await page.mouse.move(pt.x, pt.y); await page.mouse.down();
  for (const st of [[2, 0], [6, 2], [12, 6], [20, 12], [30, 20]]) await page.mouse.move(pt.x + st[0], pt.y + st[1]);
  return await page.waitForFunction(() => !!(window.__labTabDrag && window.__labTabDrag.on), null, { timeout: 15000 }).then(() => true).catch(() => false);
};
const tabIn = (page, fid, sid) => page.evaluate((a) => { const f = document.getElementById(a.fid); let d = null; try { d = f && f.contentDocument; } catch (e) { d = null; } return !!(d && d.querySelector('#tabs .tab[data-id="' + a.sid + '"]')); }, { fid, sid });
const activeIn = (page, fid) => page.evaluate((id) => { const f = document.getElementById(id); let d = null; try { d = f && f.contentDocument; } catch (e) { d = null; } const t = d && d.querySelector("#tabs .tab.active[data-id]"); return t ? t.getAttribute("data-id") : null; }, fid);
// what the page is like at a point of the shell: the element under it (a zone of either engine, or the chat's iframe) and its cursor
const under = (page, pt) => page.evaluate((p) => { const el = document.elementFromPoint(p.x, p.y); return el ? { tag: el.tagName, id: el.id || "", cls: String(el.className || ""), cursor: getComputedStyle(el).cursor } : null; }, pt);
const state = async (page, chatPt) => ({
  zones: await page.evaluate(() => ({ kit: document.querySelectorAll(".pd-tabzone").length, split: document.querySelectorAll(".col-drop").length, ghostOn: !!(document.getElementById("col-ghost") && document.getElementById("col-ghost").classList.contains("on")), outlineOn: !!(document.getElementById("pd-outline") && document.getElementById("pd-outline").classList.contains("on")) })),
  body: await page.evaluate(() => ({ cls: document.body.className, cursor: getComputedStyle(document.body).cursor })),
  dragging: await page.evaluate(() => !!(window.__rompPaneDock && window.__rompPaneDock.dragging())),
  underStrip: chatPt ? await under(page, chatPt) : null,
});

async function run(withHideShow) {
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  await ctx.addInitScript("(" + seed + ")()");
  const page = await ctx.newPage();
  const o = { withHideShow, errors: [] };
  page.on("pageerror", (e) => o.errors.push(String(e && e.stack || e).slice(0, 300)));
  await page.goto(cfg.url);
  o.ready = await page.waitForFunction(() => { const pd = window.__rompPaneDock; if (!pd || !pd.on()) return false; const r = pd.rects(); if (r.length < 4) return false;
    const f = document.getElementById("f-chat"); const d = f && f.contentDocument; return !!(d && d.getElementById("tabbar") && d.querySelectorAll("#tabs .tab[data-id]").length >= 2); }, null, { timeout: 60000 }).then(() => true).catch(() => false);
  if (!o.ready) { o.absent = true; await ctx.close(); return o; }
  await page.waitForFunction(() => !!(window.__rompPaneDock.layout() && localStorage.getItem("romp-layout") && document.querySelectorAll(".pd-div").length >= 1), null, { timeout: 20000 }).catch(() => {});
  await frame(page);
  o.rects0 = await rectsOf(page); o.leaves0 = await leavesOf(page);
  // (1) the api tab dragged out of the first strip into the feed's bottom half: its own column pane there
  const pt = await tabCentre(page, "f-chat", cfg.api);
  o.out = { tab: pt };
  if (pt) {
    o.out.started = await startNativeDrag(page, pt);
    o.out.zones = await page.waitForFunction(() => document.querySelectorAll(".pd-tabzone").length >= 3, null, { timeout: 10000 }).then(() => true).catch(() => false);
    const feed = (await rectsOf(page))["feed-pane"];
    await page.mouse.move(feed.x + feed.w / 2, feed.y + feed.h * 0.85, { steps: 10 }); await frame(page);
    o.out.outline = await outlineRead(page);   // the drop preview over the feed's bottom half
    await page.mouse.up(); await frame(page);
    o.out.landed = await page.waitForFunction(() => { const el = document.getElementById("chat-pane-2"); const lay = window.__rompPaneDock.layout(); const lv = (n) => n.pane ? [n.pane] : n.kids.flatMap(lv); return !!(el && lay && lv(lay.tree).includes("chat-pane-2")); }, null, { timeout: 20000 }).then(() => true).catch(() => false);
    o.out.moved = await page.waitForFunction((sid) => { const f = document.getElementById("f-chat-2"); let d = null; try { d = f && f.contentDocument; } catch (e) { d = null; } const g = document.getElementById("f-chat"); let d0 = null; try { d0 = g && g.contentDocument; } catch (e) { d0 = null; }
      return !!(d && d.querySelector('#tabs .tab[data-id="' + sid + '"]') && d0 && !d0.querySelector('#tabs .tab[data-id="' + sid + '"]')); }, cfg.api, { timeout: 30000 }).then(() => true).catch(() => false);
    await page.waitForFunction(() => document.querySelectorAll(".pd-tabzone, .col-drop").length === 0, null, { timeout: 10000 }).catch(() => {});
    await frame(page);
    o.out.after = await state(page, null);
    o.out.rects = await rectsOf(page); o.out.leaves = await leavesOf(page);
  }
  // (2) the rail's chat button: every chat hidden, then shown again (a real click on the button, twice)
  if (withHideShow && o.out.moved) {
    const btn = page.locator('.rail-btn[data-pane="chat"]');
    await btn.click();
    o.hidden = { off: await page.waitForFunction(() => { const lay = window.__rompPaneDock.layout(); const lv = (n) => n.pane ? [n.pane] : n.kids.flatMap(lv); return !document.body.classList.contains("po-chat") && !!lay && !lv(lay.tree).some((p) => p === "chat-pane" || /^chat-pane-\d+$/.test(p)); }, null, { timeout: 20000 }).then(() => true).catch(() => false) };
    await frame(page);
    o.hidden.leaves = await leavesOf(page); o.hidden.parked = await parkedOf(page); o.hidden.rects = await rectsOf(page); o.hidden.bodyCls = await page.evaluate(() => document.body.className);
    await btn.click();
    o.shown = { on: await page.waitForFunction(() => { const lay = window.__rompPaneDock.layout(); const lv = (n) => n.pane ? [n.pane] : n.kids.flatMap(lv); const el = document.getElementById("chat-pane-2");
      return document.body.classList.contains("po-chat") && !!lay && lv(lay.tree).includes("chat-pane") && lv(lay.tree).includes("chat-pane-2") && !!el && el.getBoundingClientRect().width > 100; }, null, { timeout: 20000 }).then(() => true).catch(() => false) };
    await frame(page); await frame(page);
    o.shown.leaves = await leavesOf(page); o.shown.parked = await parkedOf(page); o.shown.rects = await rectsOf(page);
  }
  // (3) the separated tab dragged back onto the first chat's strip (its empty run, right of the tabs)
  const pt2 = await tabCentre(page, "f-chat-2", cfg.api);
  o.back = { tab: pt2 };
  if (pt2) {
    o.back.started = await startNativeDrag(page, pt2);
    const chat = (await rectsOf(page))["chat-pane"];
    const stripPt = { x: chat.x + chat.w * 0.7, y: chat.y + cfg.ring + 12 };
    await page.mouse.move(stripPt.x, stripPt.y, { steps: 10 }); await frame(page);
    o.back.outline = await outlineRead(page);   // the drop preview over the strip
    o.back.duringZones = await page.evaluate(() => ({ kit: document.querySelectorAll(".pd-tabzone").length, split: document.querySelectorAll(".col-drop").length }));
    await page.mouse.up(); await frame(page);
    o.back.rejoined = await page.waitForFunction((sid) => { const g = document.getElementById("f-chat"); let d0 = null; try { d0 = g && g.contentDocument; } catch (e) { d0 = null; } const lay = window.__rompPaneDock.layout(); const lv = (n) => n.pane ? [n.pane] : n.kids.flatMap(lv);
      return !!(d0 && d0.querySelector('#tabs .tab[data-id="' + sid + '"]') && !document.getElementById("chat-pane-2") && lay && !lv(lay.tree).includes("chat-pane-2")); }, cfg.api, { timeout: 30000 }).then(() => true).catch(() => false);
    await frame(page); await frame(page);
    // the page after the join: what is under the strip, the zones of both engines, the body, the kit; then a click on the
    // tab that is NOT active must select it
    const chatNow = (await rectsOf(page))["chat-pane"];
    o.back.after = await state(page, { x: chatNow.x + chatNow.w * 0.7, y: chatNow.y + cfg.ring + 12 });
    o.back.leaves = await leavesOf(page); o.back.parked = await parkedOf(page); o.back.rects = await rectsOf(page);
    const active0 = await activeIn(page, "f-chat");
    const want = active0 === cfg.web ? cfg.api : cfg.web;
    const tp = await tabCentre(page, "f-chat", want);
    o.back.select = { active0, want, tab: tp };
    if (tp) {
      o.back.select.underTab = await under(page, tp);
      await page.mouse.click(tp.x, tp.y); await frame(page); await frame(page);
      o.back.select.active1 = await page.waitForFunction((a) => { const f = document.getElementById("f-chat"); let d = null; try { d = f && f.contentDocument; } catch (e) { d = null; } const t = d && d.querySelector("#tabs .tab.active[data-id]"); return t && t.getAttribute("data-id") === a ? a : false; }, want, { timeout: 5000 }).then((h) => h.jsonValue()).catch(async () => await activeIn(page, "f-chat"));
    }
    // the strip's own cursor, read in the chat document (the open hand over its empty run while the kit is on)
    o.back.stripCursor = await page.evaluate(() => { const f = document.getElementById("f-chat"); let d = null; try { d = f && f.contentDocument; } catch (e) { d = null; } const tb = d && d.getElementById("tabbar"); return tb ? getComputedStyle(tb).cursor : null; });
    if (cfg.shots) { fs.mkdirSync(cfg.shots, { recursive: true }); await page.screenshot({ path: cfg.shots + "/tab-rejoin-" + (withHideShow ? "hideshow" : "plain") + ".png" }); }
  }
  await ctx.close();
  return o;
}
out.hideShow = await run(true);
out.plain = await run(false);
fs.writeSync(1, "RESULT:" + JSON.stringify(out) + "\n");
await browser.close();
process.exit(0);
"""


class ServedTabRejoin(unittest.TestCase):
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
        cls.lab = tempfile.mkdtemp(prefix="tab-rejoin-")
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
        cls.port, cls.token = _free_port(), "testtok-tabrejoin"
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
        p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=420, env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
        if p.returncode == 3:
            if REQUIRE:
                raise AssertionError("ROMP_SERVED_TESTS_REQUIRE=1 but no Chromium launched: " + p.stderr[-500:])
            raise unittest.SkipTest("no playwright browser on this box: the served leg needs one")
        assert p.returncode == 0, "driver failed:\n" + p.stdout[-3000:] + p.stderr[-3000:]
        line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
        assert line, "driver printed no result:\n" + p.stdout[-3000:] + p.stderr[-2000:]
        cls.r = json.loads(line[len("RESULT:"):])
        for k in ("hideShow", "plain"):
            o = cls.r.get(k) or {}
            print("TAB-REJOIN %s: leaves before the hide %r, after the show %r, after the join %r; after the join %r" % (
                k, (o.get("out") or {}).get("leaves"), (o.get("shown") or {}).get("leaves"), (o.get("back") or {}).get("leaves"), (o.get("back") or {}).get("after")), file=sys.stderr)

    @classmethod
    def tearDownClass(cls):
        for pr in getattr(cls, "procs", []):
            try:
                pr.kill(); pr.wait()
            except Exception:
                pass
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

    def _sequence(self, key):
        """The run's steps all happened (the preconditions of every claim below): the kit on, the tab out into its own
        column, the chats hidden and shown when the run does that, the tab back in the first strip with the column gone."""
        o = self.r[key]
        self.assertFalse(o.get("absent"), "the kit came on with the panes and the two tabs: %r" % o)
        self.assertEqual(o["errors"], [], "no page error: %r" % o["errors"])
        t = o["out"]
        self.assertTrue(t.get("tab"), "the api tab was found, draggable, in the first strip")
        self.assertTrue(t["started"], "the real drag out started (the page posted tabDrag on)")
        self.assertTrue(t["landed"] and t["moved"], "the tab became its own column pane under the feed and left the first strip: %r" % t.get("leaves"))
        self.assertEqual(t["after"]["zones"], {"kit": 0, "split": 0, "ghostOn": False, "outlineOn": False}, "the drop into a zone leaves no zone behind: %r" % t["after"])
        if o["withHideShow"]:
            self.assertTrue(o["hidden"]["off"], "the rail button hid every chat pane: %r" % o["hidden"])
            self.assertTrue(o["shown"]["on"], "and the second press brought both chat panes back: %r" % o["shown"])
        b = o["back"]
        self.assertTrue(b.get("tab"), "the api tab was found in the column's strip for the drag back")
        self.assertTrue(b["started"], "the real drag back started")
        self.assertTrue(b["rejoined"], "the tab is back in the first strip and the emptied column is gone from the page and the tree: %r" % b.get("leaves"))
        return o

    def _usable(self, o):
        b = o["back"]
        a = b["after"]
        self.assertTrue(b["select"].get("tab"), "the other tab was found in the first strip: %r" % b["select"])
        self.assertEqual(b["select"]["active1"], b["select"]["want"], "a click on a tab in the first strip selects it after the join (the page is not stuck): %r" % b["select"])
        u = a["underStrip"]
        self.assertTrue(u and u["tag"] == "IFRAME" and u["id"] == "f-chat", "the element under the first strip is the chat's own iframe, no drop zone of either engine over it: %r" % u)
        self.assertEqual(a["zones"], {"kit": 0, "split": 0, "ghostOn": False, "outlineOn": False}, "no hit area or drop zone remains and the drop rectangles are off after the join: %r" % a["zones"])
        cls = set(a["body"]["cls"].split())
        self.assertFalse(cls & set(DRAG_CLASSES), "the shell body carries no drag, resize or grab class: %r" % a["body"])
        self.assertNotIn(a["body"]["cursor"], ("grab", "grabbing", "col-resize", "row-resize", "move", "copy"), "and no hand or resize cursor: %r" % a["body"])
        self.assertFalse(a["dragging"], "the kit holds no drag")
        self.assertEqual(b["stripCursor"], "grab", "the strip's empty run wears the kit's open hand again, its own cursor: %r" % b["stripCursor"])

    def test_1_after_the_tab_is_dragged_out_the_chats_hidden_and_shown_and_the_tab_dragged_back_a_tab_is_selectable_and_no_drag_state_remains(self):
        o = self._sequence("hideShow")
        self._usable(o)

    def test_2_the_same_two_drags_with_no_hide_and_show_between_them_leave_the_page_usable_too(self):
        o = self._sequence("plain")
        self._usable(o)

    def test_3_the_drop_preview_square_carries_no_text_over_a_landing_half_nor_over_a_strip(self):
        # the user's decision (2026-09-21): the light-blue square says where the tab lands by its place alone; the pane's title
        # and the "joins" word leave its centre (a refused drop keeps its one line: a thin ring alone cannot say why)
        o = self._sequence("hideShow")
        ol = o["out"]["outline"]
        self.assertTrue(ol and ol["on"] and not ol["free"] and not ol["refused"], "the square shows over the feed's bottom half during the drag out: %r" % ol)
        self.assertEqual(ol["text"], "", "and carries no text: %r" % ol)
        bs = o["back"]["outline"]
        self.assertTrue(bs and bs["on"] and not bs["refused"], "the square shows over the first strip during the drag back: %r" % bs)
        self.assertEqual(bs["text"], "", "and carries no text there either: %r" % bs)


if __name__ == "__main__":
    unittest.main()
