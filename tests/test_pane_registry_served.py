#!/usr/bin/env python3
"""The pane registry on the REAL dashboard (plans/panes-as-data.md, phase one, section 7's served leg). A hermetic kernel
starts with three data panes on disk: a state-root pane (pane:notes, a page under STATE/panes/notes/ that loads shim.js and
theme.css from /pane/notes/), a URL pane (a page a second, foreign origin serves: protocol none) and an experimental
route pane. A Chromium driver opens the dashboard and reads:
  1. the rail carries the shipped five then the data panes, the experimental one hidden until the gear asks; the body
     wears po-notes and po-docs and the attribute the inline scripts read;
  2. the notes pane is a shown column loading /pane/notes/: its page has the shim (window.__rompReload), the theme, and
     hears the pane-set broadcast naming it;
  3. the URL pane is a sandboxed iframe with its URL as given (no ?v=, no token), marked protocol none; the forged
     toggleFleet, notify and reveal it posts on load change nothing, and it is told nothing (its beacons say so);
  4. the gear's Panes section has a row per data pane, the experimental one off; turning it on brings the pane on screen;
  5. a define at the kernel while the page is open: the pane-set revision on the next keepalive stands the reload OFFER
     with the panes' wording, the page does not reload on its own, and the Reload click shows the new pane.
Runs when ROMP_SERVED_TESTS_REQUIRE=1 (CI); skips where no Chromium is installed. Synthetic fixtures only."""
import http.server
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

from tests.dist_copy import copy_dist

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
EXT = os.path.join(ROOT, "vscode-extension")
SID = "11111111-2222-4333-8444-000000000301"

import sys
sys.path.insert(0, HERE)
import test_ship_reship_served as _lab   # noqa: E402  the lab kernel's environment (the module, not its classes)

REQUIRE = os.environ.get("ROMP_SERVED_TESTS_REQUIRE") == "1"


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _transcript(cwd, pairs):
    out, parent, t = [], None, 1_700_000_000
    for i in range(pairs):
        u = "11111111-2222-4333-8444-0000000c%04x" % i
        a = "11111111-2222-4333-8444-0000000d%04x" % i
        ts = lambda k: time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t + i * 60 + k))
        out.append({"type": "user", "uuid": u, "parentUuid": parent, "timestamp": ts(0), "sessionId": SID, "cwd": cwd,
                    "message": {"role": "user", "content": "please keep the notes index fresh (part %d)" % (i + 1)}})
        out.append({"type": "assistant", "uuid": a, "parentUuid": u, "timestamp": ts(5), "sessionId": SID, "cwd": cwd,
                    "message": {"id": "msg_lab_%04d" % i, "type": "message", "role": "assistant", "model": "claude-sonnet-5",
                                "content": [{"type": "text", "text": "Note %d refreshed." % (i + 1)}], "stop_reason": "end_turn"}})
        parent = a
    return "\n".join(json.dumps(r) for r in out) + "\n"


NOTES_PAGE = """<!doctype html><html><head><meta charset=utf-8><link rel=stylesheet href=theme.css><script src=shim.js></script></head>
<body><h1 id=t>Notes</h1><div id=empty data-pane-empty style="height:260px"></div><iframe id=inner src=inner.html></iframe><script>
window.__labMsgs=[];window.addEventListener('message',function(e){window.__labMsgs.push(e.data);});
</script></body></html>"""

# a frame NESTED inside the notes pane (same origin as the shell, served from the pane's own directory): it forges the
# shell's messages to the top window; the check rules on the immediate frame, so a nested frame is not a pane and nothing acts
INNER_PAGE = """<!doctype html><html><body><script>
try{top.postMessage({romp:'toggleFleet',to:'fleet'},'*');top.postMessage({romp:'notify',kind:'error',text:'forged from a nested frame'},'*');
top.postMessage({romp:'openKeys'},'*');top.postMessage({romp:'hotkeyConfigure',sid:'11111111-2222-4333-8444-000000000301',name:'nested'},'*');}catch(e){}
</script></body></html>"""

# the URL pane's page, served by a SECOND origin: on load it forges three shell messages, and it beacons every message it
# receives back to its own server (an image load needs no CORS), so the test can read that it was told nothing
DOCS_PAGE = """<!doctype html><html><head><meta charset=utf-8></head><body><h1>Docs</h1><script>
try{parent.postMessage({romp:'toggleFleet',to:'fleet'},'*');parent.postMessage({romp:'notify',kind:'error',text:'forged from the docs pane'},'*');parent.postMessage({romp:'reveal',pane:'fleet'},'*');
parent.postMessage({romp:'openKeys'},'*');parent.postMessage({romp:'hotkeyConfigure',sid:'11111111-2222-4333-8444-000000000301',name:'forged'},'*');}catch(e){}
window.addEventListener('message',function(e){var i=new Image();i.src='/beacon?m='+encodeURIComponent(JSON.stringify(e.data)).slice(0,300);});
</script></body></html>"""


class _DocsServer(http.server.BaseHTTPRequestHandler):
    beacons = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/beacon"):
            _DocsServer.beacons.append(self.path)
            self.send_response(204); self.end_headers(); return
        body = DOCS_PAGE.encode()
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)


DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));
let browser;
try { browser = await chromium.launch(); }
catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
const page = await browser.newPage({ viewport: { width: 1500, height: 900 } });
const out = {};
const die = async (why) => { fs.writeSync(1, "RESULT:" + JSON.stringify({ ...out, died: why }) + "\n"); await browser.close(); process.exit(0); };
const rail = () => page.evaluate(() => Array.from(document.querySelectorAll(".rail-btn[data-pane]")).map((b) => ({ pane: b.getAttribute("data-pane"), text: b.textContent, hidden: b.hidden, on: b.classList.contains("on") })));
const body = () => page.evaluate(() => ({ cls: document.body.className.split(/\s+/).filter((c) => /^po-/.test(c)).sort(), attr: JSON.parse(document.body.getAttribute("data-panes") || "null") }));
const banner = () => page.evaluate(() => { const b = document.getElementById("rstale"); if (!b) return null;
  return { shown: b.classList.contains("show"), offer: b.classList.contains("offer"), text: b.querySelector(".rs-msg").textContent, reload: document.getElementById("rstale-reload").textContent }; }).catch(() => null);
const waitOffer = (ms) => page.waitForFunction(() => { const b = document.getElementById("rstale"); return !!b && b.classList.contains("show") && b.classList.contains("offer"); }, null, { timeout: ms }).then(() => true).catch(() => false);
const frameEnding = async (suffix) => { let fr = null; for (let i = 0; i < 150 && !fr; i++) { fr = page.frames().find((f) => f.url().split("?")[0].endsWith(suffix)); if (!fr) await page.waitForTimeout(100); } return fr; };

// ---- 1. the landing ----
await page.goto(cfg.url);
await page.waitForSelector(".rail-btn[data-pane=notes]", { timeout: 20000 }).catch(async () => { await die("no notes rail button"); });
await page.waitForTimeout(500);
out.rail = await rail();
out.body = await body();

// ---- 2. the state-root pane ----
const nf = await frameEnding("/pane/notes/");
if (!nf) await die("no /pane/notes/ frame");
await nf.waitForFunction(() => !!window.__rompReload, null, { timeout: 15000 }).catch(() => {});
out.notesHeard = await nf.waitForFunction(() => (window.__labMsgs || []).some((m) => m && m.romp === "panes"), null, { timeout: 15000 }).then(() => true).catch(() => false);
out.notesPage = await nf.evaluate(() => ({ title: (document.getElementById("t") || {}).textContent, shim: typeof window.__rompReload,
  theme: Array.from(document.styleSheets).some((s) => (s.href || "").endsWith("/pane/notes/theme.css")),
  on: (((window.__labMsgs || []).filter((m) => m && m.romp === "panes").slice(-1)[0]) || {}).on || null }));
out.notesRect = await page.evaluate(() => { const r = document.getElementById("notes-pane").getBoundingClientRect(); const c = document.getElementById("chat-pane").getBoundingClientRect();
  return { w: Math.round(r.width), h: Math.round(r.height), rightOfChat: r.left >= c.right, gutter: getComputedStyle(document.getElementById("gv-notes")).display }; });
out.notesSrc = await page.evaluate(() => document.getElementById("f-notes").getAttribute("src"));

// ---- 3. the URL pane ----
out.docs = await page.evaluate(() => { const f = document.getElementById("f-docs"); return { src: f.getAttribute("src"), sandbox: f.getAttribute("sandbox"), proto: f.getAttribute("data-protocol"), shown: document.body.classList.contains("po-docs"), w: Math.round(f.getBoundingClientRect().width) }; });
await page.waitForTimeout(2500);   // the docs page's and the nested frame's forged posts on load, and any broadcast the docs page would beacon
out.nestedLoaded = await nf.evaluate(() => { const f = document.getElementById("inner"); return !!(f && f.contentDocument && f.contentDocument.readyState === "complete"); }).catch(() => false);
out.afterForged = await page.evaluate(() => ({ fleet: document.body.classList.contains("po-fleet"),
  keysOpen: (() => { const b = document.getElementById("rkeys-back"); return !!b && !b.hidden; })(),   // the shortcuts modal (palette-main openKeys / hotkeyConfigure)
  tabKeys: localStorage.getItem("romp:tabkeys"),                                                     // a forged hotkeyConfigure would have remembered the chosen sid here
  notices: (() => { try { return JSON.parse(localStorage.getItem("romp:notices") || "[]").map((n) => n.text); } catch (e) { return []; } })() }));

if (cfg.shot) await page.screenshot({ path: cfg.shot });   // a picture for a reviewer (ROMP_LAB_SHOT names the file; unset in CI)

// ---- 4. the gear's rows ----
await page.evaluate(() => window.__rompOpenSettings && window.__rompOpenSettings());
let gf = null;
for (let i = 0; i < 150 && !gf; i++) { for (const f of page.frames()) { if (await f.$("#rs-pane-notes").catch(() => null)) { gf = f; break; } } if (!gf) await page.waitForTimeout(100); }
if (!gf) await die("no settings frame with the registry rows");
out.gear = await gf.evaluate(() => Array.from(document.querySelectorAll("#rs-panes-data input")).map((i) => ({ id: i.id, checked: i.checked, label: i.parentNode.querySelector("b").textContent })));
await gf.evaluate(() => { for (const id of ["rs-pane-lab", "rs-pane-artifacts"]) { const i = document.getElementById(id); i.checked = true; i.dispatchEvent(new Event("change", { bubbles: true })); } });
out.labAfterGear = await page.waitForFunction(() => { const b = document.querySelector(".rail-btn[data-pane=lab]"); return !!b && !b.hidden && document.body.classList.contains("po-lab"); }, null, { timeout: 10000 }).then(() => true).catch(() => false);
out.labSrc = await page.evaluate(() => document.getElementById("f-lab").getAttribute("src"));
out.artifactsAfterGear = await page.evaluate(() => { const b = document.querySelector(".rail-btn[data-pane=artifacts]"); const f = document.getElementById("f-artifacts");
  return { hidden: !!b && b.hidden, on: document.body.classList.contains("po-artifacts"), src: f ? f.getAttribute("src") : "absent" }; });
out.settingsPanes = await page.evaluate(() => { try { return JSON.parse(localStorage.getItem("romp:settings") || "{}").panes || null; } catch (e) { return null; } });
// ---- 4b. a HAND row flipped keeps the registry keys (the 1919 read, still standing at 1922: the hand rows' handler rewrote the set from
// three keys, so flipping Sessions, the Outline or the Feed dropped every registry key: the Artifacts control hid and its column
// closed while its row read checked, and a data pane's stored false came back on) ----
await gf.evaluate(() => { const i = document.getElementById("rs-pane-notes"); i.checked = false; i.dispatchEvent(new Event("change", { bubbles: true })); });   // a data pane hidden by its row: stored false
await page.waitForFunction(() => document.querySelector(".rail-btn[data-pane=notes]").hidden, null, { timeout: 5000 }).catch(() => {});
await gf.evaluate(() => { const i = document.getElementById("rs-pane-feed"); i.checked = false; i.dispatchEvent(new Event("change", { bubbles: true })); });   // a HAND row flipped
await page.waitForFunction(() => document.querySelector(".rail-btn[data-pane=feed]").hidden, null, { timeout: 5000 }).catch(() => {});
await page.waitForTimeout(300);
out.afterFeedFlip = await page.evaluate(() => ({ panes: (() => { try { return JSON.parse(localStorage.getItem("romp:settings") || "{}").panes || null; } catch (e) { return null; } })(),
  feedHidden: document.querySelector(".rail-btn[data-pane=feed]").hidden, notesHidden: document.querySelector(".rail-btn[data-pane=notes]").hidden,
  artifactsHidden: document.querySelector(".rail-btn[data-pane=artifacts]").hidden, labOn: document.body.classList.contains("po-lab"), notesOn: document.body.classList.contains("po-notes") }));
await gf.evaluate(() => { for (const id of ["rs-pane-feed", "rs-pane-notes"]) { const i = document.getElementById(id); i.checked = true; i.dispatchEvent(new Event("change", { bubbles: true })); } });   // both back
await page.waitForFunction(() => !document.querySelector(".rail-btn[data-pane=notes]").hidden && !document.querySelector(".rail-btn[data-pane=feed]").hidden, null, { timeout: 5000 }).catch(() => {});

// ---- 5. a define while the page is open ----
await page.evaluate(() => { window.__probe = 1; });
const res = await fetch(cfg.api + "/pane", { method: "POST", headers: { "Content-Type": "application/json", "X-Romp-Token": cfg.token },
  body: JSON.stringify({ id: "later", title: "Later", source: "/feed", on: true }) });
out.define = await res.json();
out.offerShown = await waitOffer(15000);           // one keepalive (ROMP_WS_KEEPALIVE=2) carries the moved revision
out.banner = await banner();
await page.waitForTimeout(4500);                   // two more keepalives: a self-reload would have fired by now
out.probeAlive = await page.evaluate(() => window.__probe === 1);
out.laterBeforeReload = await page.evaluate(() => !!document.querySelector(".rail-btn[data-pane=later]"));
await page.click("#rstale-reload");
out.reloaded = await page.waitForFunction(() => window.__probe !== 1, null, { timeout: 15000 }).then(() => true).catch(() => false);
await page.waitForSelector(".rail-btn[data-pane=later]", { timeout: 20000 }).catch(() => {});
await page.waitForTimeout(500);
out.afterReload = { later: !!(await page.$(".rail-btn[data-pane=later]")), body: await body(), banner: await banner() };

// ---- 6. the docking kit reads the list (plans/panes-as-data.md section 4): a data pane is a tree leaf with a ring, drops into a half-zone ----
const frame = () => page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r(1)))));
await page.evaluate(() => { const s = JSON.parse(localStorage.getItem("romp:settings") || "{}"); s.paneDocking = true; s.panes = Object.assign({}, s.panes || {}, { artifacts: true }); localStorage.setItem("romp:settings", JSON.stringify(s)); });   // the kit on; the Artifacts pane enabled in the gear (step 4 clicked its row; said here, not relied on)
await page.reload();
await page.waitForSelector(".rail-btn[data-pane=notes]", { timeout: 20000 }).catch(async () => { await die("no notes rail button after the kit's reload"); });
out.kitOn = await page.waitForFunction(() => !!(window.__rompPaneDock && window.__rompPaneDock.on() && window.__rompPaneDock.layout()), null, { timeout: 15000 }).then(() => true).catch(() => false);
if (!out.kitOn) await die("the docking kit did not come on");
await frame();
const leavesOf = () => page.evaluate(() => { const lay = window.__rompPaneDock.layout(); const lv = (n) => n.pane ? [n.pane] : n.kids.flatMap(lv); return lay ? lv(lay.tree) : []; });
const rectsOf = () => page.evaluate(() => Object.fromEntries(window.__rompPaneDock.rects().map((r) => { const el = document.getElementById(r.pane); const f = el && el.querySelector(":scope > iframe"); const b = f ? f.getBoundingClientRect() : null;
  return [r.pane, Object.assign({}, r.rect, { frame: b ? { x: b.left, y: b.top, w: b.width, h: b.height } : null })]; })));
out.kitLeaves = await leavesOf();
out.kitRects = await rectsOf();
out.kitTitleRail = await page.evaluate(() => Array.from(document.querySelectorAll(".rail-btn[data-pane]")).map((b) => [b.getAttribute("data-pane"), b.textContent]));
// the notes page's own empty surface: a press there forwards to the shell and arms exactly the ring's press (the detector honours data-pane-empty)
const nf2 = await frameEnding("/pane/notes/");
if (!nf2) await die("no notes frame after the kit's reload");
out.kitInjected = await nf2.waitForFunction(() => document.body.classList.contains("pane-docking") && !!window.__rompPaneGrab, null, { timeout: 15000 }).then(() => true).catch(() => false);
const nOrigin = await page.evaluate(() => { const f = document.getElementById("f-notes"); const b = f.getBoundingClientRect(); return { x: b.left + f.clientLeft, y: b.top + f.clientTop }; });
const spot = await nf2.evaluate(() => { const e = document.getElementById("empty"); const r = e.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2, under: (document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2) || {}).id || "" }; });
out.kitSpot = spot;
await page.mouse.move(nOrigin.x + spot.x, nOrigin.y + spot.y); await frame();
out.kitHover = await nf2.evaluate(() => ({ cls: document.body.className, cursor: getComputedStyle(document.body).cursor }));
await page.mouse.down(); await frame();
out.kitPressed = await page.evaluate(() => ({ pressed: window.__rompPaneDock.pressed(), dragging: window.__rompPaneDock.dragging() }));
await page.keyboard.press("Escape"); await frame(); await page.mouse.up(); await frame();
// a REAL drag from the notes pane's ring into the feed's left half: the layout changes, notes docks left of the feed
const before = await rectsOf();
const nr = before["notes-pane"], fr2 = before["feed-pane"];
if (!nr || !fr2) await die("notes or feed is not a leaf: " + JSON.stringify(Object.keys(before)));
const x0 = nr.x + 3, y0 = nr.y + nr.h / 2;   // the ring: the pane element's left padding
await page.mouse.move(x0, y0); await page.mouse.down(); await frame();
await page.mouse.move(x0 + 14, y0 + 14, { steps: 3 }); await frame();
out.kitArmed = await page.evaluate(() => window.__rompPaneDock.dragging());
await page.mouse.move(fr2.x + fr2.w * 0.2, fr2.y + fr2.h / 2, { steps: 8 }); await frame();
out.kitZone = await page.evaluate(() => window.__rompPaneDock.zone());
out.kitOutline = await page.evaluate(() => { const o = document.getElementById("pd-outline"); return o ? { on: o.classList.contains("on"), text: o.textContent } : null; });
await page.mouse.up(); await frame();
out.kitAfterDrop = { leaves: await leavesOf(), rects: await rectsOf(), layout: await page.evaluate(() => localStorage.getItem("romp-layout")) };
if (cfg.shot) await page.screenshot({ path: cfg.shot.replace(/\.png$/, "-kit.png") });   // the kit on, the data pane docked left of the feed
// the Artifacts pane (a shipped pane the kit's old lists never named) toggled on is a leaf too
await page.evaluate(() => window.__rompPaneToggle("artifacts", true)); await frame(); await frame();
out.kitArtifacts = { leaves: await leavesOf(), rect: (await rectsOf())["artifacts-pane"] || null };

// ---- 7. a PHONE (the mobile layout: one pane at a time, the bottom tabs): a data pane's tab shows its page, loaded once by the tap ----
const mctx = await browser.newContext({ viewport: { width: 420, height: 860 }, hasTouch: true, isMobile: true });
// the pane's desktop flag OFF in this browser (a rail toggle from an earlier desktop visit): on a phone the pane shows by its TAB alone,
// so its iframe must load from the tap, never from the desktop flag (the 1922 read: a tab tapped showed a blank pane)
await mctx.addInitScript(() => { if (window.top !== window) return; try { localStorage.setItem("romp-panes", JSON.stringify({ notes: false })); } catch (e) {} });   // the top document only: an init script runs in every same-origin frame too, and would re-seed after the shell's own writes
const mp = await mctx.newPage();
const notesRequests = [];
mp.on("request", (rq) => { if (/\/pane\/notes\/(\?|$)/.test(rq.url())) notesRequests.push(rq.url()); });
await mp.goto(cfg.url);
await mp.waitForSelector("#mtabs button[data-pane=notes]", { timeout: 20000 }).catch(async () => { await die("no notes tab on the phone"); });
await mp.waitForTimeout(800);
out.phoneBefore = await mp.evaluate(() => ({ mobile: !!(window.__rompMobileOn && window.__rompMobileOn()), tab: document.body.getAttribute("data-tab"),
  notesSrc: document.getElementById("f-notes").getAttribute("src"), tabs: Array.from(document.querySelectorAll("#mtabs button[data-pane]")).filter((b) => !b.hidden).map((b) => b.getAttribute("data-pane")) }));
await mp.click("#mtabs button[data-pane=notes]");
out.phoneLoaded = await mp.waitForFunction(() => { const f = document.getElementById("f-notes"); return f && f.getAttribute("src") === "/pane/notes/" && f.classList.contains("m-on"); }, null, { timeout: 10000 }).then(() => true).catch(() => false);
const mnf = await (async () => { for (let i = 0; i < 100; i++) { const f = mp.frames().find((fr) => fr.url().split("?")[0].endsWith("/pane/notes/")); if (f) return f; await mp.waitForTimeout(100); } return null; })();
if (mnf) await mnf.waitForFunction(() => !!document.getElementById("t") && !!window.__rompReload, null, { timeout: 15000 }).catch(() => {});   // the page's document and its shim, not the navigation's blank
out.phonePage = mnf ? await mnf.evaluate(() => ({ title: (document.getElementById("t") || {}).textContent || null, shim: typeof window.__rompReload })).catch(() => null) : null;
out.phoneAfterTap = await mp.evaluate(() => ({ tab: document.body.getAttribute("data-tab"), notesSrc: document.getElementById("f-notes").getAttribute("src"),
  visible: (() => { const r = document.getElementById("f-notes").getBoundingClientRect(); return r.width > 100 && r.height > 100; })() }));
await mp.click("#mtabs button[data-pane=chat]"); await mp.waitForTimeout(300);
await mp.click("#mtabs button[data-pane=notes]"); await mp.waitForTimeout(600);
out.phoneRequests = notesRequests.length;
await mctx.close();

// ---- 8. a PHONE at 390 by 844 with NOTHING stored: a generic pane loads by its TAB alone (the 1922 read: the gear's row tap loaded the
// tabless Artifacts page into a hidden 0x0 frame, and a reload loaded it again from the persisted rail flag) ----
const artRequests = [];
const pctx = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
const pp = await pctx.newPage();
pp.on("request", (rq) => { if (/\/artifacts(\?|$)/.test(rq.url())) artRequests.push(rq.url()); });
await pp.goto(cfg.url);
await pp.waitForSelector("#mtabs button[data-pane=chat]", { timeout: 20000 }).catch(async () => { await die("no phone tab bar at 390"); });
await pp.waitForTimeout(800);
await pp.evaluate(() => window.__rompOpenSettings && window.__rompOpenSettings());
let pgf = null;
for (let i = 0; i < 150 && !pgf; i++) { for (const f of pp.frames()) { if (await f.$("#rs-pane-artifacts").catch(() => null)) { pgf = f; break; } } if (!pgf) await pp.waitForTimeout(100); }
if (!pgf) await die("no settings frame on the phone");
await pgf.evaluate(() => { const i = document.getElementById("rs-pane-artifacts"); i.checked = true; i.dispatchEvent(new Event("change", { bubbles: true })); });
await pp.waitForTimeout(800);
out.phoneRowTap = await pp.evaluate(() => ({ src: document.getElementById("f-artifacts").getAttribute("src"), tab: document.body.getAttribute("data-tab"), on: document.body.classList.contains("po-artifacts"),
  panes: (() => { try { return JSON.parse(localStorage.getItem("romp:settings") || "{}").panes || null; } catch (e) { return null; } })(), requests: 0 }));
out.phoneRowTap.requests = artRequests.length;
await pctx.close();
// both flags stored and the tab remembered: a boot loads nothing and lands on the chat (the fallback for a pane with no tab)
const qctx = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
await qctx.addInitScript(() => { if (window.top !== window) return; try { localStorage.setItem("romp:settings", JSON.stringify({ panes: { artifacts: true } })); localStorage.setItem("romp-panes", JSON.stringify({ artifacts: true, notes: true })); localStorage.setItem("romp-mobile-tab", "artifacts"); } catch (e) {} });   // the top document only (an iframe's load would re-seed the remembered tab after the shell repaired it)
const qp = await qctx.newPage();
const bootRequests = [];
qp.on("request", (rq) => { if (/\/artifacts(\?|$)|\/pane\/notes\/(\?|$)/.test(rq.url())) bootRequests.push(rq.url()); });
await qp.goto(cfg.url);
await qp.waitForSelector("#mtabs button[data-pane=chat]", { timeout: 20000 }).catch(async () => { await die("no phone tab bar at 390 (second boot)"); });
await qp.waitForTimeout(1000);
out.phoneBoot = await qp.evaluate(() => ({ artSrc: document.getElementById("f-artifacts").getAttribute("src"), notesSrc: document.getElementById("f-notes").getAttribute("src"), tab: document.body.getAttribute("data-tab"),
  artOn: document.body.classList.contains("po-artifacts"), chatShown: document.getElementById("f-chat").classList.contains("m-on"), remembered: localStorage.getItem("romp-mobile-tab") }));
out.phoneBoot.requests = bootRequests.slice();
// the notes tab tapped: its page loads then, once
await qp.click("#mtabs button[data-pane=notes]"); await qp.waitForTimeout(800);
out.phoneNotesTap = { notesSrc: await qp.evaluate(() => document.getElementById("f-notes").getAttribute("src")), requests: bootRequests.slice() };
await qctx.close();
fs.writeSync(1, "RESULT:" + JSON.stringify(out) + "\n");
await browser.close();
process.exit(0);
"""


class ServedPaneRegistry(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(os.path.join(EXT, "node_modules", "playwright")):
            if REQUIRE:
                raise AssertionError("ROMP_SERVED_TESTS_REQUIRE=1 but the extension deps are absent")
            raise unittest.SkipTest("extension deps absent (npm ci not run here): the served leg needs them")
        cls.lab = tempfile.mkdtemp(prefix="pane-registry-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            raise unittest.SkipTest("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
        dist = os.path.join(cls.lab, "dist")
        copy_dist(os.path.join(EXT, "dist"), dist)
        state = os.path.join(cls.lab, "xdg", "romp")
        cwd = os.path.join(cls.lab, "proj")
        os.makedirs(os.path.join(state, "names"), exist_ok=True)
        os.makedirs(os.path.join(state, "sdk"), exist_ok=True)
        os.makedirs(cwd, exist_ok=True)
        Path(state, "session-hosts").write_text("off\n")
        Path(state, "names", SID).write_text("web\t%s\t\t\n" % cwd)
        Path(state, "sdk", SID + ".json").write_text(json.dumps(
            {"sid": SID, "name": "web", "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": SID, "alive": True}))
        Path(state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 100}, "seven_day": {"pct": 10}}))
        claude = os.path.join(cls.lab, "claude")
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        Path(proj, SID + ".jsonl").write_text(_transcript(cwd, 4))
        # the second origin: the URL pane's page
        cls.docs = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _DocsServer)
        cls.docs_port = cls.docs.server_address[1]
        threading.Thread(target=cls.docs.serve_forever, daemon=True).start()
        cls.docs_url = "http://127.0.0.1:%d/docs/" % cls.docs_port
        # the registry on disk before the kernel starts: the files the define door would write
        panes = Path(state, "panes"); (panes / "notes").mkdir(parents=True)
        (panes / "notes.json").write_text(json.dumps({"id": "notes", "title": "Notes", "source": "pane:notes", "on": True, "experimental": False, "protocol": "romp"}))
        (panes / "docs.json").write_text(json.dumps({"id": "docs", "title": "Docs", "source": cls.docs_url, "on": True, "experimental": False, "protocol": "none"}))
        (panes / "lab.json").write_text(json.dumps({"id": "lab", "title": "Lab", "source": "/feed", "on": False, "experimental": True, "protocol": "romp"}))
        (panes / "notes" / "index.html").write_text(NOTES_PAGE)
        (panes / "notes" / "inner.html").write_text(INNER_PAGE)
        cls.port = _free_port()
        cls.token = "testtok-paneregistry"
        cls.env = _lab.kernel_env(cls.lab, claude, dist, cls.port, cls.token,
                                  ROMP_WS_KEEPALIVE="2")                       # the pv rides the keepalive: keep the wait short
        cls.klog = os.path.join(cls.lab, "kernel.log")
        cls.kernel = subprocess.Popen([os.path.join(BIN, "romp-kernel")], stdout=open(cls.klog, "w"), stderr=subprocess.STDOUT, env=cls.env)
        for _ in range(120):
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/healthz" % cls.port, timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        else:
            cls.kernel.kill()
            raise unittest.SkipTest("hermetic kernel never served /healthz here")

    @classmethod
    def tearDownClass(cls):
        k = getattr(cls, "kernel", None)
        if k:
            try:
                os.kill(k.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            k.wait()
        d = getattr(cls, "docs", None)
        if d:
            d.shutdown()
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

    _res = None

    def _drive(self):
        cfg = os.path.join(self.lab, "cfg.json")
        with open(cfg, "w") as f:
            json.dump({"url": "http://127.0.0.1:%d/?token=%s" % (self.port, self.token), "api": "http://127.0.0.1:%d" % self.port, "token": self.token,
                       "shot": os.environ.get("ROMP_LAB_SHOT") or ""}, f)
        driver = os.path.join(self.lab, "driver.mjs")
        with open(driver, "w") as f:
            f.write(DRIVER)
        try:
            p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=300,
                               env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
        except subprocess.TimeoutExpired as e:
            so = e.stdout if isinstance(e.stdout, str) else (e.stdout or b"").decode()
            self.fail("driver timed out; partial output:\n%s" % so[-3000:])
        if p.returncode == 3:
            if REQUIRE:
                self.fail("ROMP_SERVED_TESTS_REQUIRE=1 but no Chromium launched: " + p.stderr[-500:])
            raise unittest.SkipTest("no playwright browser on this box: the served leg needs one")
        self.assertEqual(p.returncode, 0, "driver failed:\n" + p.stdout[-3000:] + p.stderr[-3000:])
        line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
        self.assertIsNotNone(line, "driver printed no result:\n" + p.stdout[-3000:])
        r = json.loads(line[len("RESULT:"):])
        self.assertNotIn("died", r, "driver aborted early: %r" % r)
        return r

    def _result(self):
        # one drive per class (the driver runs every leg in one browser session); a failure, a skip or a launch error is cached
        # and re-raised by every test, so the record is measured once and each leg's verdict stands on its own
        cls = type(self)
        if cls._res is None:
            try:
                cls._res = ("ok", self._drive())
            except Exception as e:
                cls._res = ("err", e)
        kind, val = cls._res
        if kind == "err":
            raise val
        return val

    def test_data_panes_render_dock_and_speak_the_protocol_a_url_pane_is_sandboxed_and_mute_and_a_define_offers_a_reload(self):
        r = self._result()
        # 1. the landing
        self.assertEqual([b["pane"] for b in r["rail"]], ["chat", "timeline", "fleet", "feed", "files", "artifacts", "docs", "lab", "notes"], r["rail"])
        by = {b["pane"]: b for b in r["rail"]}
        self.assertEqual((by["notes"]["text"], by["notes"]["hidden"], by["notes"]["on"]), ("Notes", False, True))
        self.assertEqual((by["docs"]["hidden"], by["docs"]["on"]), (False, True))
        self.assertTrue(by["lab"]["hidden"], "experimental: not in this dashboard until the gear asks: %r" % by["lab"])
        self.assertTrue(by["artifacts"]["hidden"], "the Artifacts record is experimental too (plans/panes-as-data.md phase three): hidden until the gear asks: %r" % by["artifacts"])
        # the forged messages (the URL pane's on load; a same-origin frame nested in the notes pane's): read FIRST, so a red
        # names the door that opened (the 1919 read: the shortcuts modal opened in recording mode on a forged row)
        self.assertFalse(r["afterForged"]["keysOpen"], "a forged openKeys or hotkeyConfigure must not open the shortcuts modal: %r" % r["afterForged"])
        self.assertIsNone(r["afterForged"]["tabKeys"], "a forged hotkeyConfigure must not remember a session the foreign page chose: %r" % r["afterForged"]["tabKeys"])
        self.assertTrue(r["nestedLoaded"], "the nested frame inside the notes pane loaded and posted: %r" % r.get("nestedLoaded"))
        self.assertFalse(r["afterForged"]["fleet"], "a forged toggleFleet (the URL pane's, the nested frame's) must not open the Outline")
        self.assertFalse(any("forged" in t for t in r["afterForged"]["notices"]), "a forged notify must not reach the notification center: %r" % r["afterForged"])
        self.assertEqual(r["body"]["cls"], ["po-chat", "po-docs", "po-feed", "po-notes", "po-timeline"], r["body"])
        self.assertEqual([(a["id"], a["protocol"], a["experimental"], a["on"], a["builtin"]) for a in r["body"]["attr"]],
                         [("artifacts", "romp", True, False, True), ("docs", "none", False, True, False), ("lab", "romp", True, False, False), ("notes", "romp", False, True, False)],
                         "the shipped record the generic build renders, then the data panes by id")
        # 2. the state-root pane: a shown column loading its page, which has the shim and the theme and hears the broadcast
        self.assertEqual(r["notesSrc"], "/pane/notes/")
        self.assertEqual((r["notesPage"]["title"], r["notesPage"]["shim"], r["notesPage"]["theme"]), ("Notes", "object", True), r["notesPage"])
        self.assertTrue(r["notesHeard"], "the pane-set broadcast reaches a protocol pane: %r" % r["notesPage"])
        self.assertEqual(r["notesPage"]["on"].get("notes"), True, r["notesPage"]["on"])
        self.assertNotIn("lab", r["notesPage"]["on"], "the experimental pane is not in this dashboard's set")
        self.assertGreater(r["notesRect"]["w"], 60, r["notesRect"]); self.assertGreater(r["notesRect"]["h"], 100)
        self.assertTrue(r["notesRect"]["rightOfChat"], "a column after the chat: %r" % r["notesRect"])
        self.assertNotEqual(r["notesRect"]["gutter"], "none", "its gutter shows between two shown columns")
        # 3. the URL pane: sandboxed, the URL as given, protocol none; its forged messages change nothing; it is told nothing
        self.assertEqual(r["docs"], {"src": self.docs_url, "sandbox": "allow-scripts allow-forms allow-popups", "proto": "none", "shown": True, "w": r["docs"]["w"]})
        self.assertGreater(r["docs"]["w"], 60)
        told = [b for b in _DocsServer.beacons if "panes" in b]
        self.assertEqual(told, [], "the URL pane is outside the protocol: no broadcast reaches it")
        # 4. the gear's rows
        self.assertEqual(r["gear"], [{"id": "rs-pane-artifacts", "checked": False, "label": "Artifacts"}, {"id": "rs-pane-docs", "checked": True, "label": "Docs"},
                                     {"id": "rs-pane-lab", "checked": False, "label": "Lab"}, {"id": "rs-pane-notes", "checked": True, "label": "Notes"}],
                         "the generic rows: the shipped Artifacts record (off by default, experimental) and the data panes")
        self.assertTrue(r["labAfterGear"], "the gear's row brings the experimental pane into the dashboard and on screen: %r" % {k: r[k] for k in ("labAfterGear", "labSrc", "settingsPanes")})
        self.assertEqual(r["labSrc"], "/feed", "loaded when shown")
        self.assertEqual((r["settingsPanes"] or {}).get("lab"), True, "saved under its own id in the pane set")
        self.assertEqual(r["artifactsAfterGear"], {"hidden": False, "on": True, "src": "/artifacts"},
                         "the Artifacts row turned on: the rail button shows and the pane comes on screen (the live reconcile), and only then does its iframe load: %r" % r["artifactsAfterGear"])
        # 5. a define while the page is open: the offer with the panes' wording, no self-reload, the Reload click shows it
        self.assertEqual(r["define"].get("ok"), True, r["define"])
        self.assertTrue(r["offerShown"], "the moved pane-set revision on the keepalive stands the offer: %r" % r.get("banner"))
        self.assertEqual(r["banner"], {"shown": True, "offer": True, "text": "The set of panes changed. Reload to see it.", "reload": "Reload"})
        self.assertTrue(r["probeAlive"], "an offer, never a self-reload")
        self.assertFalse(r["laterBeforeReload"], "the open page is not rewritten under the reader")
        self.assertTrue(r["reloaded"], "the Reload click reloads")
        self.assertTrue(r["afterReload"]["later"], "the fresh page carries the new pane: %r" % r["afterReload"])
        self.assertIn("po-later", r["afterReload"]["body"]["cls"], "on: true, on screen")
        self.assertFalse((r["afterReload"]["banner"] or {}).get("shown"), "nothing to say on the current page")
        # 6. the docking kit reads the list: a data pane toggled on is a tree leaf with a ring (the phase-one 0x0 fact closes)
        self.assertTrue(r["kitOn"])
        lv = r["kitLeaves"]
        self.assertIn("notes-pane", lv, "the notes pane is a leaf: %r" % lv); self.assertIn("docs-pane", lv, "the URL pane is a leaf too (only the ring, no detector)"); self.assertIn("later-pane", lv)
        self.assertEqual(lv.index("feed-pane") < lv.index("docs-pane") < lv.index("later-pane") < lv.index("notes-pane"), True, "the row's order, the rail's: %r" % lv)
        for pid in ("notes-pane", "docs-pane"):
            rc = r["kitRects"][pid]
            self.assertGreater(rc["w"], 60, "%s has a rectangle: %r" % (pid, rc)); self.assertGreater(rc["h"], 100)
            self.assertEqual((round(rc["frame"]["x"] - rc["x"]), round(rc["frame"]["y"] - rc["y"])), (6, 6), "the iframe sits inside the 6 px ring: %r" % rc)
        self.assertIn(["notes", "Notes"], r["kitTitleRail"])
        self.assertTrue(r["kitInjected"], "the detector is injected into the protocol pane's page and the kit's class is on its body")
        self.assertEqual(r["kitSpot"]["under"], "empty", "the press lands on the page's declared empty surface: %r" % r["kitSpot"])
        self.assertIn("pd-grab-hover", r["kitHover"]["cls"], "the open hand over the declared surface: %r" % r["kitHover"]); self.assertEqual(r["kitHover"]["cursor"], "grab")
        self.assertTrue(r["kitPressed"]["pressed"], "a press on the page's declared empty surface arms the shell's press (data-pane-empty honoured for any app): %r" % r["kitPressed"])
        self.assertTrue(r["kitArmed"], "the ring's press lifts the pane after the slop")
        self.assertEqual(r["kitZone"], {"target": "feed-pane", "edge": "left"}, "the feed's left half-zone: %r" % r["kitZone"])
        self.assertEqual(r["kitOutline"], {"on": True, "text": "Notes"}, "the live outline names the pane by its record's title: %r" % r["kitOutline"])
        after = r["kitAfterDrop"]["leaves"]
        self.assertLess(after.index("notes-pane"), after.index("feed-pane"), "dropped into the feed's left half: notes docks left of the feed: %r" % after)
        self.assertLess(r["kitAfterDrop"]["rects"]["notes-pane"]["x"], r["kitAfterDrop"]["rects"]["feed-pane"]["x"])
        self.assertIn("notes-pane", r["kitAfterDrop"]["layout"] or "", "the layout store holds the data pane's leaf")
        self.assertIn("artifacts-pane", r["kitArtifacts"]["leaves"], "the Artifacts pane toggled on is a leaf too: %r" % r["kitArtifacts"]["leaves"])
        # 7. the phone: a data pane's tab shows its page, loaded once by the tap (the 1922 read: the tab showed a blank pane)
        pb = r["phoneBefore"]
        self.assertTrue(pb["mobile"], "the phone layout: %r" % pb); self.assertEqual(pb["tab"], "chat")
        self.assertIsNone(pb["notesSrc"], "the pane's desktop flag is off in this browser: nothing loaded before the tap, the iframe waits for its tab")
        self.assertIn("notes", pb["tabs"]); self.assertNotIn("lab", pb["tabs"], "an experimental pane has no tab")
        self.assertTrue(r["phoneLoaded"], "the tap loads the pane's page and shows it: %r" % r.get("phoneAfterTap"))
        self.assertEqual(r["phoneAfterTap"]["tab"], "notes"); self.assertTrue(r["phoneAfterTap"]["visible"], "the pane fills the phone's screen: %r" % r["phoneAfterTap"])
        self.assertEqual((r["phonePage"] or {}).get("title"), "Notes", "the page is up, its shim with it: %r" % r["phonePage"])
        self.assertEqual(r["phoneRequests"], 1, "the page is requested once, however many times its tab is tapped: %r" % r["phoneRequests"])
        self.assertGreater((r["kitArtifacts"]["rect"] or {"w": 0})["w"], 60, "the Artifacts leaf has a rectangle: %r; after the drop: %r" % (r["kitArtifacts"], r["kitAfterDrop"]["rects"]))

    def test_a_hand_row_flipped_in_the_gear_keeps_the_registry_keys(self):
        r = self._result()
        # 4b. a hand row flipped keeps the registry keys (the 1919 read): the Feed off leaves the Artifacts control and the hidden Notes pane as they were
        f = r["afterFeedFlip"]
        self.assertEqual({k: f["panes"].get(k) for k in ("feed", "artifacts", "lab", "notes")}, {"feed": False, "artifacts": True, "lab": True, "notes": False}, "the whole set survives the hand row's flip: %r" % f["panes"])
        self.assertTrue(f["feedHidden"], "the Feed's button hidden by its row")
        self.assertFalse(f["artifactsHidden"], "the Artifacts control stays (its key survived)"); self.assertTrue(f["labOn"], "the Lab pane stays on screen")
        self.assertTrue(f["notesHidden"], "the Notes pane stays hidden (its stored false survived)"); self.assertFalse(f["notesOn"])

    def test_on_a_phone_a_generic_pane_loads_by_its_tab_alone_never_by_the_desktop_flag(self):
        r = self._result()
        # 8. the phone at 390 by 844 (the 1922 read): the gear's row tap enables the tabless Artifacts pane and loads NOTHING; a boot with both
        # flags stored and the tab remembered loads nothing and lands on the chat; a tabbed pane's tap loads its page, once
        pt = r["phoneRowTap"]
        self.assertEqual((pt["panes"] or {}).get("artifacts"), True, "the row enabled the pane: %r" % pt)
        self.assertIsNone(pt["src"], "no src: a pane with no tab is never loaded on a phone: %r" % pt); self.assertEqual(pt["requests"], 0, "and nothing requested")
        self.assertEqual(pt["tab"], "chat")
        pb2 = r["phoneBoot"]
        self.assertEqual((pb2["artSrc"], pb2["notesSrc"], pb2["tab"], pb2["chatShown"]), (None, None, "chat", True), "a boot with both flags stored and artifacts remembered: nothing loaded, the chat shown: %r" % pb2)
        self.assertEqual(pb2["requests"], [], "no page requested at boot: %r" % pb2["requests"])
        self.assertEqual(pb2["remembered"], "chat", "the remembered tab is repaired to the chat")
        self.assertEqual(r["phoneNotesTap"]["notesSrc"], "/pane/notes/", "the notes tab tapped loads its page")
        self.assertEqual(len(r["phoneNotesTap"]["requests"]), 1, "once: %r" % r["phoneNotesTap"]["requests"])


class TheBuiltBundles(unittest.TestCase):
    """The BUILT shell bundles read the shell's source check (plans/panes-as-data.md section 5): the palette and the docking kit. This
    module runs in CI's browser job with the extension built, where tests/test_pane_registry.py's source-level census cannot (the 1919
    read: its bundle leg skipped in every pytest cell, so its pass was invisible)."""

    def test_the_built_palette_and_docking_bundles_read_the_shells_check(self):
        dist = os.path.join(EXT, "dist")
        names = ["palette-main", "panedock-main"]
        if not all(os.path.exists(os.path.join(dist, n + ".js")) for n in names):
            if not os.path.isdir(os.path.join(EXT, "node_modules")):
                if REQUIRE:
                    raise AssertionError("ROMP_SERVED_TESTS_REQUIRE=1 but the extension deps are absent")
                raise unittest.SkipTest("extension deps absent (npm ci not run here): the built bundles cannot be read")
            b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
            self.assertEqual(b.returncode, 0, b.stderr[-500:])
        for n in names:
            self.assertIn("__rompPaneSourceOk", open(os.path.join(dist, n + ".js")).read(), "the built %s bundle reads the shell's check" % n)


if __name__ == "__main__":
    unittest.main()
