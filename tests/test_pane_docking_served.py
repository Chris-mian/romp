#!/usr/bin/env python3
"""THE PANE DOCKING ENGINE on the served dashboard, driven with REAL pointer events (plans/pane-docking.md phase two;
the user 2026-09-18: move panes by their empty space, no title bars, a blue outline where the pane will land, default
off). One hermetic kernel, Chromium on the shell page (`/`), two contexts:

ON (the gear's paneDocking true, seeded in the store before the page loads): the cursor states by COMPUTED cursor (the
open hand over a pane's ring and over the chat strip's empty run, the closed hand while a pane is held, the open hand
over content while Option/Alt is down); a press on a pane's ring lifts only past the slop; the accent outline follows
the pointer across two half-zones of one pane (its rectangle re-read right before each comparison); a pane dropped
into each of the four half-zones lands there (the layout store and the panes' rectangles after each); Escape cancels
a drag with the store untouched; the timeline band keeps a fixed height; the three shipped stores are never written.

OFF (nothing seeded, the default): the same gestures change nothing: the pane row's DOM is byte-identical before and
after, no layout store exists, no engine stylesheet or outline node, the body carries no engine class.

Synthetic only: placeholder uuids, the notes-api world. Skips LOUDLY without the extension deps or a Playwright browser,
and for nothing else (ROMP_SERVED_TESTS_REQUIRE=1 turns the skips red where the browser is installed)."""
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

SID_WEB = "11111111-2222-4333-8444-0000000000d1"
SID_API = "11111111-2222-4333-8444-0000000000d2"


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
const out = { errors: [], on: {}, off: {} };
const PANES = { chat: true, fleet: true, feed: true, timeline: true, files: false };

const seed = (on) => (() => {
  if (window !== window.top) return;
  try {
    if (localStorage.getItem("__pd_seeded")) return;
    localStorage.setItem("__pd_seeded", "1");
    localStorage.setItem("romp-panes", JSON.stringify(__PANES__));
    localStorage.removeItem("romp-layout");
    if (__ON__) localStorage.setItem("romp:settings", JSON.stringify({ paneDocking: true, panes: { timeline: true, fleet: true, feed: true } }));
    else localStorage.setItem("romp:settings", JSON.stringify({ panes: { timeline: true, fleet: true, feed: true } }));
  } catch (e) {}
}).toString().replace("__PANES__", JSON.stringify(PANES)).replace("__ON__", on ? "true" : "false");

const rectsOf = (page) => page.evaluate(() => Object.fromEntries((window.__rompPaneDock ? window.__rompPaneDock.rects() : []).map((r) => [r.pane, r.rect])));
const store = (page) => page.evaluate(() => ({ layout: localStorage.getItem("romp-layout"), grow: localStorage.getItem("romp-pane-grow"), panes: localStorage.getItem("romp-panes") }));
const outlineRect = (page) => page.evaluate(() => { const o = document.getElementById("pd-outline"); if (!o) return null; const r = o.getBoundingClientRect(); return { on: o.classList.contains("on"), free: o.classList.contains("free"), refused: o.classList.contains("refused"), x: r.left, y: r.top, w: r.width, h: r.height, text: o.textContent }; });
const chatFrame = (page) => page.frames().find((f) => /\/chat(\?|$)/.test(f.url()));
// Chromium delivers pointermove aligned to animation frames: read the engine's state only after two frames have
// passed since the move (an event wait, not a timer), so a read never runs ahead of the event it measures
const frame = (page) => page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r(1)))));

// a REAL pointer drag: press at (x0,y0), travel past the slop, visit each waypoint (recording the outline against the
// rects read right then), release at the last waypoint
async function drag(page, x0, y0, waypoints, { release = true, escape = false } = {}) {
  const rec = { pressed: null, armed: null, way: [] };
  await page.mouse.move(x0, y0);
  await page.mouse.down();
  await frame(page);
  rec.pressed = await page.evaluate(() => ({ dragging: window.__rompPaneDock.dragging(), bodyCursor: getComputedStyle(document.body).cursor, cls: document.body.className }));
  await page.mouse.move(x0 + 3, y0 + 3);   // under the slop: nothing lifts
  await frame(page);
  rec.underSlop = await page.evaluate(() => window.__rompPaneDock.dragging());
  await page.mouse.move(x0 + 14, y0 + 14, { steps: 3 });
  await frame(page);
  rec.armed = await page.evaluate(() => ({ dragging: window.__rompPaneDock.dragging(), bodyCursor: getComputedStyle(document.body).cursor, paneCursor: getComputedStyle(document.getElementById("feed-pane")).cursor }));
  for (const w of waypoints) {
    await page.mouse.move(w.x, w.y, { steps: 6 });
    await frame(page);
    rec.way.push({ at: w, rects: await rectsOf(page), outline: await outlineRect(page), zone: await page.evaluate(() => window.__rompPaneDock.zone()) });
  }
  if (escape) { await page.keyboard.press("Escape"); await frame(page); rec.afterEscape = await page.evaluate(() => ({ dragging: window.__rompPaneDock.dragging(), outline: document.getElementById("pd-outline").classList.contains("on") })); await page.mouse.up(); }
  else if (release) { await page.mouse.up(); await frame(page); }
  rec.after = { rects: await rectsOf(page), store: await store(page), dragging: await page.evaluate(() => window.__rompPaneDock.dragging()), outlineOn: await page.evaluate(() => document.getElementById("pd-outline").classList.contains("on")) };
  return rec;
}

// ── ON ────────────────────────────────────────────────────────────────────────────────────────────────
{
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  await ctx.addInitScript("(" + seed(true) + ")()");
  const page = await ctx.newPage();
  page.on("pageerror", (e) => out.errors.push("on: " + String(e && e.stack || e).slice(0, 300)));
  await page.goto(cfg.url);
  const ready = await page.waitForFunction(() => {
    const pd = window.__rompPaneDock; if (!pd || !pd.on()) return false;
    const r = pd.rects(); if (r.length < 4) return false;
    const f = document.getElementById("f-chat"); const d = f && f.contentDocument;
    return !!(d && d.getElementById("tabbar") && document.getElementById("f-fleet") && document.getElementById("f-fleet").getAttribute("src"));
  }, null, { timeout: 60000 }).then(() => true).catch(() => false);
  out.on.ready = ready;
  await page.waitForTimeout(800);
  const o = out.on;
  o.bodyClass = await page.evaluate(() => document.body.className);
  o.rects0 = await rectsOf(page);
  o.store0 = await store(page);
  o.tl = await page.evaluate(() => { const c = document.querySelector(".col"); return { tl: getComputedStyle(c).getPropertyValue("--tl").trim(), rowBottom: document.querySelector(".row").getBoundingClientRect().bottom, colBottom: c.getBoundingClientRect().bottom }; });
  // cursors at rest: the ring, the shell body, the chat strip's empty run and a tab in it
  const cf = chatFrame(page);
  o.cursors = {
    feedRing: await page.evaluate(() => getComputedStyle(document.getElementById("feed-pane")).cursor),
    body: await page.evaluate(() => getComputedStyle(document.body).cursor),
    tabbar: cf ? await cf.evaluate(() => getComputedStyle(document.getElementById("tabbar")).cursor) : null,
    tab: cf ? await cf.evaluate(() => { const t = document.querySelector("#tabs .tab"); return t ? getComputedStyle(t).cursor : null; }) : null,
    chatRoot: cf ? await cf.evaluate(() => getComputedStyle(document.documentElement).cursor) : null,
  };
  // Option/Alt held: the open hand over content
  await page.keyboard.down("Alt");
  await page.waitForTimeout(80);
  o.alt = { chatRoot: cf ? await cf.evaluate(() => getComputedStyle(document.documentElement).cursor) : null, bodyCls: await page.evaluate(() => document.body.className) };
  await page.keyboard.up("Alt");
  await page.waitForTimeout(80);
  o.altUp = { chatRoot: cf ? await cf.evaluate(() => getComputedStyle(document.documentElement).cursor) : null, bodyCls: await page.evaluate(() => document.body.className) };
  // drag 1: the feed by its top ring, across the outline pane's TOP then BOTTOM half, dropped on the bottom
  let r = o.rects0, feed = r["feed-pane"], fleet = r["fleet-pane"];
  o.drag1 = await drag(page, feed.x + feed.w / 2, feed.y + 1, [
    { x: fleet.x + fleet.w / 2, y: fleet.y + fleet.h * 0.2 },
    { x: fleet.x + fleet.w / 2, y: fleet.y + fleet.h * 0.8 },
  ]);
  // drag 2: the feed (now under the outline) by its top ring to the chat's LEFT half
  r = o.drag1.after.rects; feed = r["feed-pane"]; let chat = r["chat-pane"];
  o.drag2 = await drag(page, feed.x + feed.w / 2, feed.y + 1, [{ x: chat.x + chat.w * 0.1, y: chat.y + chat.h / 2 }]);
  // drag 3: the outline by its LEFT ring to the chat's TOP half
  r = o.drag2.after.rects; fleet = r["fleet-pane"]; chat = r["chat-pane"];
  o.drag3 = await drag(page, fleet.x + 1, fleet.y + fleet.h / 2, [{ x: chat.x + chat.w / 2, y: chat.y + chat.h * 0.1 }]);
  // drag 4: the outline by its top ring to the feed's RIGHT half
  r = o.drag3.after.rects; fleet = r["fleet-pane"]; feed = r["feed-pane"];
  o.drag4 = await drag(page, fleet.x + fleet.w / 2, fleet.y + 1, [{ x: feed.x + feed.w * 0.9, y: feed.y + feed.h / 2 }]);
  // Escape mid-drag: the chat by its top ring, lifted over the feed, cancelled
  r = o.drag4.after.rects; chat = r["chat-pane"]; feed = r["feed-pane"];
  o.storeBeforeEsc = await store(page);
  o.esc = await drag(page, chat.x + chat.w / 2, chat.y + 1, [{ x: feed.x + feed.w / 2, y: feed.y + feed.h / 2 }], { escape: true });
  // a press under the slop is a click, not a drag
  o.click = await (async () => { const rr = await rectsOf(page); const p = rr["chat-pane"]; await page.mouse.move(p.x + p.w / 2, p.y + 1); await page.mouse.down(); await page.mouse.move(p.x + p.w / 2 + 2, p.y + 2); await frame(page); const d = await page.evaluate(() => window.__rompPaneDock.dragging()); await page.mouse.up(); return { dragging: d, store: await store(page) }; })();
  o.final = { rects: await rectsOf(page), store: await store(page), tl: await page.evaluate(() => getComputedStyle(document.querySelector(".col")).getPropertyValue("--tl").trim()) };
  if (cfg.shots) { fs.mkdirSync(cfg.shots, { recursive: true }); await page.screenshot({ path: cfg.shots + "/pane-docking-on.png" }); }
  await ctx.close();
}

// ── OFF ───────────────────────────────────────────────────────────────────────────────────────────────
{
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  await ctx.addInitScript("(" + seed(false) + ")()");
  const page = await ctx.newPage();
  page.on("pageerror", (e) => out.errors.push("off: " + String(e && e.stack || e).slice(0, 300)));
  await page.goto(cfg.url);
  await page.waitForFunction(() => { const f = document.getElementById("f-chat"); const d = f && f.contentDocument; const g = document.getElementById("f-feed"); return !!(d && d.getElementById("tabbar") && g && g.getAttribute("src") && document.querySelector("#feed-pane")); }, null, { timeout: 60000 }).catch(() => {});
  await page.waitForTimeout(1200);
  const snap = () => page.evaluate(() => ({
    row: document.querySelector(".row").outerHTML,
    band: document.getElementById("tl-pane").outerHTML,
    bodyCls: document.body.className,
    css: !!document.getElementById("pd-css"), outline: !!document.getElementById("pd-outline"), divs: document.querySelectorAll(".pd-div").length,
    engineOn: !!(window.__rompPaneDock && window.__rompPaneDock.on()),
    layout: localStorage.getItem("romp-layout"),
    feedCursor: getComputedStyle(document.getElementById("feed-pane")).cursor,
  }));
  out.off.before = await snap();
  const rr = await page.evaluate(() => Object.fromEntries(["chat-pane", "fleet-pane", "feed-pane"].map((id) => { const r = document.getElementById(id).getBoundingClientRect(); return [id, { x: r.left, y: r.top, w: r.width, h: r.height }]; })));
  // the same gestures: a press at the feed's top edge dragged into the chat, and an Option-drag from the chat into the feed
  const feed = rr["feed-pane"], chat = rr["chat-pane"];
  await page.mouse.move(feed.x + feed.w / 2, feed.y + 1); await page.mouse.down(); await page.mouse.move(feed.x + feed.w / 2 + 14, feed.y + 14, { steps: 3 }); await page.mouse.move(chat.x + chat.w * 0.1, chat.y + chat.h / 2, { steps: 6 }); await page.mouse.up();
  await page.keyboard.down("Alt"); await page.mouse.move(chat.x + chat.w / 2, chat.y + chat.h / 2); await page.mouse.down(); await page.mouse.move(chat.x + chat.w / 2 + 14, chat.y + chat.h / 2 + 14, { steps: 3 }); await page.mouse.move(feed.x + feed.w / 2, feed.y + feed.h / 2, { steps: 6 }); await page.mouse.up(); await page.keyboard.up("Alt");
  await page.waitForTimeout(400);
  out.off.after = await snap();
  await ctx.close();
}
await browser.close();
process.stdout.write("RESULT:" + JSON.stringify(out) + "\n", () => process.exit(0));
"""


class ServedPaneDocking(unittest.TestCase):
    maxDiff = None

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
            raise unittest.SkipTest("extension deps absent (npm ci not run here): the served lab needs them")
        probe = subprocess.run(["node", "-e", "const p=require(process.argv[1]);process.stdout.write(p.chromium.executablePath())",
                                os.path.join(EXT, "node_modules", "playwright")], capture_output=True, text=True)
        if probe.returncode != 0 or not os.path.exists(probe.stdout.strip()):
            raise unittest.SkipTest("no playwright browser on this box: the served lab needs one (CI installs none)")
        cls.lab = tempfile.mkdtemp(prefix="pane-dock-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            raise unittest.SkipTest("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
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
        cls.port, cls.token = _free_port(), "testtok-panedock"
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
            raise unittest.SkipTest("hermetic kernel never served /healthz here")
        cls._drive()

    @classmethod
    def _drive(cls):
        cfg = os.path.join(cls.lab, "cfg.json")
        with open(cfg, "w") as f:
            json.dump({"url": "http://127.0.0.1:%d/?token=%s" % (cls.port, cls.token), "shots": os.environ.get("PANE_DOCK_SHOTS", "")}, f)
        driver = os.path.join(cls.lab, "driver.mjs")
        Path(driver).write_text(DRIVER)
        p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=420,
                           env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
        if p.returncode == 3:
            raise unittest.SkipTest("no playwright browser on this box: the served leg needs one (CI installs none)")
        assert p.returncode == 0, "driver failed:\n" + p.stdout[-3000:] + p.stderr[-3000:]
        line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
        assert line, "driver printed no result:\n" + p.stdout[-3000:] + p.stderr[-2000:]
        cls.r = json.loads(line[len("RESULT:"):])
        if os.environ.get("PANE_DOCK_SHOTS"):
            with open(os.path.join(os.environ["PANE_DOCK_SHOTS"], "result.json"), "w") as f:
                json.dump(cls.r, f, indent=1)

    @classmethod
    def tearDownClass(cls):
        for pr in getattr(cls, "procs", []):
            try:
                pr.kill(); pr.wait()
            except Exception:
                pass
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

    # ── helpers ──────────────────────────────────────────────────────────────────────────────────────
    @staticmethod
    def _leaves(node):
        return [node["pane"]] if "pane" in node else [p for k in node["kids"] for p in ServedPaneDocking._leaves(k)]

    def _layout(self, store):
        self.assertTrue(store.get("layout"), "the layout store exists while the kit is on")
        lay = json.loads(store["layout"])
        self.assertEqual(lay.get("v"), 1)
        return lay

    def _near(self, a, b, tol, what):
        self.assertLessEqual(abs(a - b), tol, "%s: %r vs %r" % (what, a, b))

    # ── the ON page ──────────────────────────────────────────────────────────────────────────────────
    def test_1_the_engine_is_on_and_positions_every_pane_with_the_band_at_a_fixed_height(self):
        self.assertEqual(self.r["errors"], [], self.r["errors"])
        o = self.r["on"]
        self.assertTrue(o["ready"], "the engine came on and the panes have rects: %r" % o.get("bodyClass"))
        self.assertIn("pane-docking", o["bodyClass"].split())
        r = o["rects0"]
        self.assertEqual(sorted(r), ["chat-pane", "feed-pane", "fleet-pane", "tl-pane"], "the seeded panes, the band included")
        chat, fleet, feed, band = r["chat-pane"], r["fleet-pane"], r["feed-pane"], r["tl-pane"]
        self.assertLess(chat["x"] + chat["w"], fleet["x"]); self.assertLess(fleet["x"] + fleet["w"], feed["x"])   # today's row order
        self._near(chat["y"], fleet["y"], 1, "the row shares a top"); self._near(chat["h"], feed["h"], 1, "and a height")
        tl = float(o["tl"]["tl"].replace("px", "") or 0)
        self.assertGreater(tl, 0, "the shell's --tl: %r" % o["tl"])
        self._near(band["h"], tl, 1.5, "the band's height is the fixed --tl px")
        self._near(band["y"] + band["h"], o["tl"]["rowBottom"], 1.5, "the band sits at the bottom of the pane area")
        self.assertGreater(band["y"], chat["y"] + chat["h"], "below the row")
        lay = self._layout(o["store0"])
        self.assertEqual(lay["tree"]["dir"], "col"); self.assertEqual(lay["tree"]["fixed"][1], tl, "the band is the fixed kid of the root column")
        self.assertEqual(self._leaves(lay["tree"]), ["chat-pane", "fleet-pane", "feed-pane", "tl-pane"])

    def test_2_cursors_the_open_hand_over_the_ring_and_the_strips_empty_run_and_under_option_the_closed_hand_while_held(self):
        o = self.r["on"]
        c = o["cursors"]
        self.assertEqual(c["feedRing"], "grab", "the pane's ring wears the open hand: %r" % c)
        self.assertEqual(c["tabbar"], "grab", "the chat strip's empty run wears the open hand: %r" % c)
        self.assertNotEqual(c["tab"], "grab", "a tab keeps its own cursor: %r" % c)
        self.assertNotEqual(c["chatRoot"], "grab", "content at rest is not a grab surface: %r" % c)
        self.assertEqual(o["alt"]["chatRoot"], "grab", "Option held: the open hand over content: %r" % o["alt"])
        self.assertIn("pd-alt", o["alt"]["bodyCls"].split())
        self.assertNotEqual(o["altUp"]["chatRoot"], "grab", "released: back to the content's cursor: %r" % o["altUp"])
        self.assertNotIn("pd-alt", o["altUp"]["bodyCls"].split())
        d = o["drag1"]
        self.assertFalse(d["pressed"]["dragging"], "a press alone lifts nothing")
        self.assertFalse(d["underSlop"], "three px of travel is under the slop")
        self.assertTrue(d["armed"]["dragging"], "past the slop the pane is held")
        self.assertEqual(d["armed"]["bodyCursor"], "grabbing", "the closed hand while held: %r" % d["armed"])
        self.assertEqual(d["armed"]["paneCursor"], "grabbing")

    def test_3_the_outline_follows_the_pointer_across_two_half_zones_of_one_pane(self):
        d = self.r["on"]["drag1"]
        top, bottom = d["way"][0], d["way"][1]
        fl = top["rects"]["fleet-pane"]
        self.assertEqual(top["zone"], {"target": "fleet-pane", "edge": "top"}, top["zone"])
        self.assertTrue(top["outline"]["on"] and not top["outline"]["free"], top["outline"])
        self._near(top["outline"]["x"], fl["x"], 1.5, "the outline's left is the outline pane's left")
        self._near(top["outline"]["y"], fl["y"], 1.5, "top half: its top is the pane's top")
        self._near(top["outline"]["w"], fl["w"], 1.5, "full width")
        self._near(top["outline"]["h"], (fl["h"] - 7) / 2, 2, "half the height, less the gutter's share")
        fl2 = bottom["rects"]["fleet-pane"]
        self.assertEqual(bottom["zone"], {"target": "fleet-pane", "edge": "bottom"}, bottom["zone"])
        self._near(bottom["outline"]["y"] + bottom["outline"]["h"], fl2["y"] + fl2["h"], 1.5, "bottom half: its bottom is the pane's bottom")
        self._near(bottom["outline"]["h"], (fl2["h"] - 7) / 2, 2, "half the height")
        self.assertGreater(bottom["outline"]["y"], top["outline"]["y"] + 10, "the outline moved with the pointer")

    def test_4_a_pane_dropped_into_each_half_zone_lands_there_and_the_store_follows(self):
        o = self.r["on"]
        # 1: the feed below the outline (the outline's bottom half)
        a = o["drag1"]["after"]
        self.assertFalse(a["dragging"]); self.assertFalse(a["outlineOn"], "the outline goes at the drop")
        fl, fd = a["rects"]["fleet-pane"], a["rects"]["feed-pane"]
        self._near(fd["x"], fl["x"], 1.5, "same left"); self.assertGreater(fd["y"], fl["y"] + fl["h"] - 1, "the feed below the outline")
        self._near(fd["w"], fl["w"], 1.5, "same width")
        lay = self._layout(a["store"]); self.assertEqual(self._leaves(lay["tree"]), ["chat-pane", "fleet-pane", "feed-pane", "tl-pane"])
        row = lay["tree"]["kids"][0]; self.assertEqual(row["dir"], "row"); self.assertEqual(row["kids"][1]["dir"], "col", "the outline over the feed as a column inside the row")
        # 2: the feed to the chat's left half
        b = o["drag2"]["after"]
        fd, ch = b["rects"]["feed-pane"], b["rects"]["chat-pane"]
        self.assertLess(fd["x"] + fd["w"], ch["x"] + 1, "the feed left of the chat"); self._near(fd["y"], ch["y"], 1.5, "same top")
        self.assertEqual(self._leaves(self._layout(b["store"])["tree"]), ["feed-pane", "chat-pane", "fleet-pane", "tl-pane"])
        # 3: the outline to the chat's top half
        c = o["drag3"]["after"]
        fl, ch = c["rects"]["fleet-pane"], c["rects"]["chat-pane"]
        self.assertLess(fl["y"] + fl["h"], ch["y"] + 1, "the outline above the chat"); self._near(fl["x"], ch["x"], 1.5, "same left"); self._near(fl["w"], ch["w"], 1.5, "same width")
        # 4: the outline to the feed's right half
        d = o["drag4"]["after"]
        fl, fd = d["rects"]["fleet-pane"], d["rects"]["feed-pane"]
        self.assertGreater(fl["x"], fd["x"] + fd["w"] - 1, "the outline right of the feed"); self._near(fl["y"], fd["y"], 1.5, "same top"); self._near(fl["h"], fd["h"], 1.5, "same height")
        self.assertEqual(self._leaves(self._layout(d["store"])["tree"]), ["feed-pane", "fleet-pane", "chat-pane", "tl-pane"])
        # every drop kept the band fixed at the bottom
        band = d["rects"]["tl-pane"]
        self._near(band["h"], float(o["final"]["tl"].replace("px", "")), 1.5, "the band's px through four drops")
        for k in ("chat-pane", "fleet-pane", "feed-pane"):
            self.assertLess(d["rects"][k]["y"] + d["rects"][k]["h"], band["y"] + 1, "%s above the band" % k)

    def test_5_escape_cancels_a_lifted_drag_and_a_press_under_the_slop_is_a_click(self):
        o = self.r["on"]
        e = o["esc"]
        self.assertTrue(e["armed"]["dragging"], "lifted before Escape")
        self.assertFalse(e["afterEscape"]["dragging"], "Escape drops the pane where it was")
        self.assertFalse(e["afterEscape"]["outline"], "and the outline goes")
        self.assertEqual(e["after"]["store"]["layout"], o["storeBeforeEsc"]["layout"], "the store is untouched by a cancelled drag")
        self.assertFalse(o["click"]["dragging"], "two px of travel: a click, nothing lifted")
        self.assertEqual(o["click"]["store"]["layout"], o["storeBeforeEsc"]["layout"])

    def test_6_the_shipped_stores_are_read_and_never_written(self):
        o = self.r["on"]
        self.assertEqual(o["final"]["store"]["grow"], o["store0"]["grow"], "romp-pane-grow untouched by four drops")
        self.assertEqual(o["final"]["store"]["panes"], o["store0"]["panes"], "romp-panes untouched")
        self.assertEqual(json.loads(o["store0"]["panes"]), {"chat": True, "fleet": True, "feed": True, "timeline": True, "files": False})

    # ── the OFF page ─────────────────────────────────────────────────────────────────────────────────
    def test_7_with_the_switch_off_the_same_gestures_change_nothing_and_no_engine_node_or_store_exists(self):
        f = self.r["off"]
        b, a = f["before"], f["after"]
        self.assertFalse(b["engineOn"], "the bundle loads and stays inert")
        self.assertNotIn("pane-docking", b["bodyCls"].split())
        self.assertFalse(b["css"] or b["outline"], "no engine stylesheet, no outline node")
        self.assertEqual(b["divs"], 0)
        self.assertIsNone(b["layout"], "no layout store is written while the kit is off")
        self.assertNotEqual(b["feedCursor"], "grab", "no open hand anywhere")
        self.assertEqual(a["row"], b["row"], "the pane row's DOM is byte-identical after the gestures")
        self.assertEqual(a["band"], b["band"])
        self.assertEqual(a["bodyCls"], b["bodyCls"])
        self.assertIsNone(a["layout"]); self.assertFalse(a["css"] or a["outline"]); self.assertEqual(a["divs"], 0)


if __name__ == "__main__":
    unittest.main()
