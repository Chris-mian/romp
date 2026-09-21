#!/usr/bin/env python3
"""The VERTICAL chat split, LOCAL face (drag a tab to a pane's bottom edge; the chat vertical split, 2026-09-16).
A column splits into a top and a bottom pane: the top keeps the column's own session, the bottom holds the one
split off. This drives the split through __rompMoveTab(sid,'down') (the drag's mutation; PR2 drives the pointer)
and pins the model the design decided: a long session in EVERY pane fills to turn 0, ESPECIALLY the non-focused
one after a shell reload (the scroll-back wall lesson, #1754); the bottom pane dials /chat?col=N&skeleton=1 with
its own iid; the two panes are STACKED (same left, greater top) with a row-resize gutter between; and the split
persists across a reload as a cols entry with place:'below', parent and ratio under v:2.

One hermetic kernel. Both panes hold a documented (cut-floor) long session, so fill-to-turn-0 is a real
transition, not an already-short transcript. Synthetic only: placeholder uuids, hostname TESTHOST, the served
builder's invented text."""
import glob
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
from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
EXT = os.path.join(ROOT, "vscode-extension")
sys.path.insert(0, HERE)
import test_ship_reship_served as _lab                      # noqa: E402
from test_asm_checkpoint_served import transcript           # noqa: E402

os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)
_ST0 = Path(os.environ["XDG_STATE_HOME"]) / "romp"
_ST0.mkdir(parents=True, exist_ok=True)
(_ST0 / "session-hosts").write_text("off\n")

SID_TOP = "dddd1111-2222-4333-8444-000000000a01"    # stays in the top pane (the column's own session)
SID_BOT = "dddd1111-2222-4333-8444-000000000a02"    # split down into the bottom pane
COLOR = ("#64b5f6", "#0c1a2e")


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));   // {url, top, bot}
let browser;
try { browser = await chromium.launch(cfg.launch || {}); }
catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
const page = await browser.newPage({ viewport: { width: 1400, height: 820 } });
page.on("pageerror", () => {});
// clear the split store on the TOP frame only (a column iframe's load must not wipe it mid-flight), and record
// every frame's WebSocket dial URLs (the bottom pane's included) so we can read its skeleton=1 and its iid.
await page.addInitScript(() => {
  try { if (window === window.top && !localStorage.getItem("__vsplit_started")) { localStorage.removeItem("romp-chat-cols"); Object.keys(localStorage).filter((k) => k.indexOf("romp-vscode-state-chat") === 0).forEach((k) => localStorage.removeItem(k)); localStorage.setItem("__vsplit_started", "1"); } } catch (e) {}   // clear ONCE (first load); the reload must keep the split to test persistence
  try { window.__dials = []; const N = window.WebSocket; window.WebSocket = function (u, p) { try { window.__dials.push(String(u)); } catch (e) {} return p === undefined ? new N(u) : new N(u, p); }; window.WebSocket.prototype = N.prototype; } catch (e) {}
});
const out = { died: null };
const frameOf = async (fid) => { const h = await page.$("#" + fid); return h ? await h.contentFrame() : null; };
// the fill observable for one pane: scroll #content to the top twice, let the observer fire and the head page land,
// then read __rompRegions (a run region at lo 0 = filled to turn 0; a gap region at boot = a real head gap).
const colState = async (fid, sid) => {
  const fr = await frameOf(fid);
  if (!fr) return { missing: true };
  await fr.waitForFunction(() => document.querySelectorAll("#content .turn[data-uuid]").length >= 1, null, { timeout: 30000 }).catch(() => {});
  const boot = await fr.evaluate((id) => {
    const c = document.getElementById("content");
    const regions = (typeof window.__rompRegions === "function") ? window.__rompRegions(id) : null;
    return { active: (document.querySelector("#tabs .tab.active[data-id]") || {}).getAttribute ? document.querySelector("#tabs .tab.active[data-id]").getAttribute("data-id") : null,
             turns: document.querySelectorAll("#content .turn[data-uuid]").length,
             hasGapRegion: !!(regions && regions.some((r) => r.kind === "gap")), regions };
  }, sid);
  await fr.evaluate(() => { const c = document.getElementById("content"); if (c) { c.scrollTop = 0; c.dispatchEvent(new Event("scroll")); } });
  await page.waitForTimeout(300);
  await fr.evaluate(() => { const c = document.getElementById("content"); if (c) { c.scrollTop = 0; c.dispatchEvent(new Event("scroll")); } });
  await page.waitForTimeout(1800);
  const after = await fr.evaluate((id) => {
    const regions = (typeof window.__rompRegions === "function") ? window.__rompRegions(id) : null;
    return { turns: document.querySelectorAll("#content .turn[data-uuid]").length, regions };
  }, sid);
  return { boot, after };
};
// the dial URL a given frame opened (full url), from the WebSocket hook the initscript installed
const dialsOf = async (fid) => { const fr = await frameOf(fid); return fr ? await fr.evaluate(() => (window.__dials || []).slice()) : []; };
try {
  await page.goto(cfg.url);
  await page.waitForFunction((t) => { const f = document.getElementById("f-chat"); const d = f && f.contentDocument; return !!(d && d.querySelector('#tabs .tab[data-id="' + t + '"]')); }, cfg.top, { timeout: 40000 });
  // show the top session, then split the bottom one DOWN
  await frameOf("f-chat").then((fr) => fr && fr.locator('#tabs .tab[data-id="' + cfg.top + '"]').first().click().catch(() => {}));
  await page.waitForTimeout(400);
  out.topDialsBefore = await dialsOf("f-chat");   // the top frame's dial BEFORE the split, to prove it is not reloaded (LOW a)
  out.split = await page.evaluate((bot) => { const f = window.__rompMoveTab(bot, "down"); return { frameId: f && f.id, cols: localStorage.getItem("romp-chat-cols") }; }, cfg.bot);
  const botFid = out.split.frameId;
  out.botFid = botFid;
  await page.waitForFunction((fid) => !!document.getElementById(fid), botFid, { timeout: 20000 });
  await page.waitForTimeout(600);
  // GEOMETRY: the bottom pane is stacked UNDER the top (same left, greater top), and the gutter between is row-resize
  out.geom = await page.evaluate((fid) => {
    const top = document.getElementById("f-chat"), bot = document.getElementById(fid);
    const tr = top.getBoundingClientRect(), br = bot.getBoundingClientRect();
    const g = document.querySelector(".pane.split-v .gh-chat");
    return { sameLeft: Math.abs(tr.left - br.left) <= 2, belowTop: br.top > tr.top + tr.height / 2,
             widthClose: Math.abs(tr.width - br.width) <= 2, gutterCursor: g ? getComputedStyle(g).cursor : null,
             paneSplit: !!(top.closest(".pane") && top.closest(".pane").classList.contains("split-v")) };
  }, botFid);
  // DIAL: the bottom frame dialed /chat?col=<n>&skeleton=1 with an iid distinct from the top pane's
  out.topDials = await dialsOf("f-chat");
  out.botDials = await dialsOf(botFid);
  // LOW a: the top frame did NOT reload across the split (its dial list is unchanged, same iid)
  out.topDialsAfter = await dialsOf("f-chat");
  // LOW c: the per-half focus ring. The split focuses the new BOTTOM half; then focus the TOP half and re-check.
  await frameOf(botFid).then((fr) => fr && fr.locator('#tabs .tab[data-id="' + cfg.bot + '"]').first().click().catch(() => {}));
  await page.waitForTimeout(300);
  out.ringBottomFocused = await page.evaluate(() => { const p = document.getElementById("chat-pane"); return { top: p.classList.contains("focus-top"), bottom: p.classList.contains("focus-bottom") }; });
  await frameOf("f-chat").then((fr) => fr && fr.locator('#tabs .tab[data-id="' + cfg.top + '"]').first().click().catch(() => {}));
  await page.waitForTimeout(300);
  out.ringTopFocused = await page.evaluate(() => { const p = document.getElementById("chat-pane"); return { top: p.classList.contains("focus-top"), bottom: p.classList.contains("focus-bottom") }; });
  // HIGH: DRAG the gutter down; both halves must move and the persisted ratio must match the screen (a cursor is not a behaviour)
  const subId = "chat-sub-" + botFid.slice(7);
  const heights = () => page.evaluate((s) => { const t = document.getElementById("f-chat"), sub = document.getElementById(s); const cc = JSON.parse(localStorage.getItem("romp-chat-cols") || "{}"); const be = (cc.cols || []).find((c) => c.place === "below"); const th = t.getBoundingClientRect().height, sh = sub ? sub.getBoundingClientRect().height : null; return { topH: Math.round(th), subH: sh === null ? null : Math.round(sh), ratio: be ? be.ratio : null, onScreen: (th && sh) ? th / (th + sh) : null }; }, subId);
  out.beforeDrag = await heights();
  const gr = await page.evaluate(() => { const g = document.querySelector(".pane.split-v .gh-chat"); if (!g) return null; const r = g.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; });
  if (gr) { await page.mouse.move(gr.x, gr.y); await page.mouse.down(); await page.mouse.move(gr.x, gr.y + 140, { steps: 10 }); await page.mouse.up(); await page.waitForTimeout(400); }
  out.afterDrag = await heights();
  // FILL at creation (both panes): the bottom is focused now, the top is non-focused
  out.topFill = await colState("f-chat", cfg.top);
  out.botFill = await colState(botFid, cfg.bot);
  // RELOAD: the ring lands on one pane, both redial; the non-focused pane must still fill (the wall guard), and the split persists
  await page.reload();
  await page.waitForFunction((t) => { const f = document.getElementById("f-chat"); const d = f && f.contentDocument; return !!(d && d.querySelector('#tabs .tab[data-id="' + t + '"]')); }, cfg.top, { timeout: 40000 });
  await page.waitForTimeout(400);
  out.afterReload = await page.evaluate(() => { const cc = JSON.parse(localStorage.getItem("romp-chat-cols") || "{}"); const be = (cc.cols || []).find((c) => c.place === "below"); return { cols: localStorage.getItem("romp-chat-cols"), botExists: !!document.querySelector('iframe[id^="f-chat-"]'), botId: (document.querySelector(".pane.split-v .chat-sub iframe") || {}).id || null, belowRatio: be ? be.ratio : null }; });
  const botFid2 = out.afterReload.botId || botFid;
  await page.waitForFunction((fid) => !!document.getElementById(fid), botFid2, { timeout: 20000 });
  await page.waitForTimeout(500);
  out.topReloadFill = await colState("f-chat", cfg.top);
  out.botReloadFill = await colState(botFid2, cfg.bot);
  // LOW 1: the TOP half must shrink past the iframe's intrinsic ~150px min. Drag the gutter fully UP; gutterV clamps the
  // top to mn=min(80,sum*0.2), but .pane.split-v>iframe without min-height:0 floors it at the iframe's automatic minimum
  // (its ~150px default object height), sticking it ~70px above the drag. min-height:0 frees it to reach the clamp.
  const subIdUp = "chat-sub-" + botFid2.slice(7);
  const gu = await page.evaluate(() => { const g = document.querySelector(".pane.split-v .gh-chat"); if (!g) return null; const r = g.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; });
  if (gu) { await page.mouse.move(gu.x, gu.y); await page.mouse.down(); await page.mouse.move(gu.x, 8, { steps: 12 }); await page.mouse.up(); await page.waitForTimeout(400); }
  out.afterUp = await page.evaluate((s) => { const t = document.getElementById("f-chat"), sub = document.getElementById(s); return { topH: Math.round(t.getBoundingClientRect().height), subH: sub ? Math.round(sub.getBoundingClientRect().height) : null }; }, subIdUp);
} catch (e) {
  out.died = String(e).slice(0, 500);
}
process.stdout.write("RESULT:" + JSON.stringify(out) + "\n");
await browser.close();
"""


POINTER_DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));   // {url, top, bot, staleDrop, holdTimeline}
let browser;
try { browser = await chromium.launch(cfg.launch || {}); }
catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
const page = await browser.newPage({ viewport: { width: 1400, height: 820 } });
page.on("pageerror", () => {});
await page.addInitScript(() => {
  try { if (window === window.top && !localStorage.getItem("__vsplit_drag_started")) { localStorage.removeItem("romp-chat-cols"); Object.keys(localStorage).filter((k) => k.indexOf("romp-vscode-state-chat") === 0).forEach((k) => localStorage.removeItem(k)); localStorage.setItem("__vsplit_drag_started", "1"); } } catch (e) {}
});
const out = { died: null };
// A LATE timeline (cfg.holdTimeline): the band's document is held until the driver has the tab it drags, so the timeline's
// loader and then its bars land while the driver waits on the settle below, before the point it measures from, and the band
// moves from its loader height to its content height before the drag begins: the hold reproduces a slow runner's late
// timeline arrival (CI, 2026-09-18), not the missed drop (VSplitDragLateTimeline's docstring says why).
let releaseTimeline = () => {};
if (cfg.holdTimeline) {
  // out.timelineHeld witnesses the hold: the /timeline documents the route saw, and how many arrived while the hold was in
  // force. The shell requests /timeline at boot, before the chat strip the driver waits on can render, so the request precedes
  // the release by construction; a route that stopped matching would otherwise run the plain drag under the late-timeline
  // class's name.
  let released = false; const held = new Promise((r) => { releaseTimeline = () => { released = true; r(); }; });
  out.timelineHeld = { requests: 0, beforeRelease: 0 };
  await page.route((u) => u.pathname === "/timeline", async (route) => { out.timelineHeld.requests += 1; if (!released) out.timelineHeld.beforeRelease += 1; await held; await route.continue(); });
}
// The timeline band under the pane row auto-fits its content: --tl follows the timeline body's scrollHeight through a
// ResizeObserver (kernel.py's autosize: min(scrollHeight + 2, 70 vh)). While the timeline shows its loader the band is about
// 250 px; when its bars land it shrinks to the lanes and #chat-pane takes the difference (two lanes are 97 px; 686 minus 533
// is 153, which is 250 minus 97). A drag begun before that lands measures a bottom zone the collapse then moves out from
// under the pointer (CI 2026-09-18: the pane 533 px tall at the zone, 686 at the ghost, the ghost never on, the drop
// missed). The tracking loop below survives a shift during the drag; this wait keeps the shift from happening: it gates the
// drag's START on the event the pane's growth follows, never a delay. The loader laid out no more (it stays in the DOM at
// display:none, so client rects are the test), the plot laid out (the wrap's own svg, .romp-tl-wrap > svg: the view's corner
// bar holds icon svgs too), the band at its content height. A dashboard without the band (po-timeline off) waits for nothing
// and records skipped. A non-timeout error keeps its own text, as the tab wait's does below.
const settled = () => page.waitForFunction(() => {
  if (!document.body.classList.contains("po-timeline")) return { skipped: true };
  const tf = document.getElementById("f-timeline"); const d = tf && tf.contentDocument; if (!d || !d.body) return false;
  const ld = d.querySelector(".tl-loader"), svg = d.querySelector(".romp-tl-wrap > svg");
  if (!ld || ld.getClientRects().length || !svg || !svg.getClientRects().length) return false;
  const band = document.getElementById("tl-pane").getBoundingClientRect().height;
  const want = Math.min(d.body.scrollHeight + 2, Math.round(window.innerHeight * 0.7));
  return Math.abs(band - want) <= 1 ? { band: band, want: want } : false;
}, null, { timeout: 40000 }).then((h) => h.jsonValue()).catch(async (e) => {
  if (!(e && e.name === "TimeoutError")) throw e;
  // The generic waitForFunction timeout names no step, so the failure this wait exists to catch would read like every
  // other wait's. Name the step and say what the band looked like when the wait gave up.
  const seen = await page.evaluate(() => {
    const tf = document.getElementById("f-timeline"); const d = tf && tf.contentDocument;
    const ld = d && d.querySelector(".tl-loader"), svg = d && d.querySelector(".romp-tl-wrap > svg"), tl = document.getElementById("tl-pane");
    return { poTimeline: document.body.classList.contains("po-timeline"), band: tl ? Math.round(tl.getBoundingClientRect().height) : null,
             want: d && d.body ? Math.min(d.body.scrollHeight + 2, Math.round(window.innerHeight * 0.7)) : null,
             loader: ld ? (ld.getClientRects().length ? "shown" : "hidden") : "absent", plot: svg ? (svg.getClientRects().length ? "shown" : "hidden") : "absent" };
  }).catch(() => null);
  throw new Error("the timeline band never settled (loader hidden, plot shown, band at its content height) within 40 s; seen " + JSON.stringify(seen) + "; " + ((e && e.message) || e));
});
const frameOf = async (fid) => { const h = await page.$("#" + fid); return h ? await h.contentFrame() : null; };
const rectIn = async (fid, sel) => { const fr = await frameOf(fid); if (!fr) return null; const h = await fr.$(sel); if (!h) return null; const b = await h.boundingBox(); return b ? { x: b.x + b.width / 2, y: b.y + b.height / 2 } : null; };
// the fill observable for the bottom pane (the dragged session): scroll #content to the top twice, let the observer
// fire, read __rompRegions (a run region at lo 0 = filled to turn 0)
const filled = async (fid) => {
  const fr = await frameOf(fid); if (!fr) return { missing: true };
  await fr.waitForFunction(() => document.querySelectorAll("#content .turn[data-uuid]").length >= 1, null, { timeout: 30000 }).catch(() => {});
  // WAIT for the fill (a run region at lo 0), re-nudging #content to the top on each poll so a slow observer keeps
  // getting a scroll to act on; bounded and event-based, never a fixed sleep (a starved runner needs far longer than
  // a fixed pause, a fast one far less). A genuine miss falls through and reports filled:false with the last regions.
  await fr.waitForFunction((id) => {
    const c = document.getElementById("content"); if (c) { c.scrollTop = 0; c.dispatchEvent(new Event("scroll")); }
    const regions = (typeof window.__rompRegions === "function") ? window.__rompRegions(id) : null;
    return !!(regions && regions.some((r) => r.kind === "run" && r.lo === 0));
  }, cfg.bot, { timeout: 30000 }).catch(() => {});
  return await fr.evaluate((id) => { const regions = (typeof window.__rompRegions === "function") ? window.__rompRegions(id) : null; return { turns: document.querySelectorAll("#content .turn[data-uuid]").length, filled: !!(regions && regions.some((r) => r.kind === "run" && r.lo === 0)), regions }; }, cfg.bot);
};
try {
  await page.goto(cfg.url, { waitUntil: cfg.holdTimeline ? "domcontentloaded" : "load" });   // a held /timeline document holds the top document's load event too (as a slow /timeline response does on a slow runner); the waits below are event-based and need no load
  await page.waitForFunction((t) => { const f = document.getElementById("f-chat"); const d = f && f.contentDocument; return !!(d && d.querySelector('#tabs .tab[data-id="' + t + '"]')); }, cfg.top, { timeout: 40000 });
  // both sessions sit in column 1; show the top one
  await frameOf("f-chat").then((fr) => fr && fr.locator('#tabs .tab[data-id="' + cfg.top + '"]').first().click().catch(() => {}));
  // A REAL pointer drag of the bottom session's tab past the threshold: the page's dragstart mounts the shell's zones.
  // The tab is found AND measured in ONE in-page step (2026-09-18). The chat page rebuilds its strip from scratch on every
  // frame that changes its signature (a placeholder tab turning into a loaded one, a status change), so a Playwright
  // locator's two-step boundingBox (resolve a handle, then measure it) can measure a node the rebuild just replaced and
  // read null: the driver then died in milliseconds wearing a 40 s message, with the tab present, visible and draggable
  // at every instant. The page's JS is single-threaded, so an in-page find-and-measure cannot be interleaved with a
  // rebuild. The predicate wants the live node draggable (its manager up, not locked), laid out (a non-empty box; a slow
  // runner paints the strip late) and not visibility:hidden (Playwright's own visible test), and maps its centre through
  // the iframe's box (the pane's iframe is position:absolute at inset 0 with no border, under no transformed ancestor).
  // waitForFunction retries it every frame under the same 40 s bound, never a fixed sleep; a non-timeout error keeps its
  // own text, so the timeout is the only road to the throw below.
  let t = null;
  try {
    const h = await page.waitForFunction((b) => {
      const f = document.getElementById("f-chat"); const d = f && f.contentDocument; const el = d && d.querySelector('#tabs .tab[data-id="' + b + '"]');
      if (!el || !el.draggable) return null;
      const r = el.getBoundingClientRect(); if (!(r.width > 0 && r.height > 0) || d.defaultView.getComputedStyle(el).visibility === "hidden") return null;
      const fr = f.getBoundingClientRect(); return { x: fr.left + f.clientLeft + r.left + r.width / 2, y: fr.top + f.clientTop + r.top + r.height / 2 };
    }, cfg.bot, { timeout: 40000 });
    t = await h.jsonValue();
  } catch (e) { if (!(e && e.name === "TimeoutError")) throw e; }
  if (!t) throw new Error("no drag start: the bottom session's tab (data-id " + cfg.bot + ") never rendered as a visible, draggable box in f-chat's strip within 40s");
  releaseTimeline(); out.settled = await settled();   // the band at its content height BEFORE mouse.down: from here the pane rect holds through the drag
  out.pane = await page.evaluate(() => { const p = document.getElementById("chat-pane"); const r = p.getBoundingClientRect(); return { left: Math.round(r.left), top: Math.round(r.top), width: Math.round(r.width), height: Math.round(r.height) }; });
  // Hear the page's dragstart from the SHELL: the tab's dragstart posts {romp:'tabDrag', on:true} to the parent,
  // which is what makes the shell mount the zones (mountZones). Install the listener BEFORE the drag so none is missed.
  await page.evaluate(() => { window.__vsplitDragStarted = false; window.addEventListener("message", (e) => { if (e && e.data && e.data.romp === "tabDrag" && e.data.on) window.__vsplitDragStarted = true; }, false); });
  // Cross the native drag threshold in SEVERAL honoured pointer moves, yielding a paint between each so a starved
  // runner registers the gesture and fires dragstart; stop as soon as the shell has heard it. Never a fixed sleep.
  await page.mouse.move(t.x, t.y); await page.mouse.down();
  let dragStarted = false;
  for (const step of [[4, 1], [10, 3], [18, 6], [28, 9], [40, 12]]) {
    await page.mouse.move(t.x + step[0], t.y + step[1]);
    dragStarted = await page.evaluate(() => window.__vsplitDragStarted === true);
    if (dragStarted) break;
    await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
  }
  if (!dragStarted) dragStarted = await page.waitForFunction(() => window.__vsplitDragStarted === true, null, { timeout: 15000 }).then(() => true).catch(() => false);
  if (!dragStarted) throw new Error("no dragstart: the real pointer drag of the bottom tab (data-id " + cfg.bot + ") never fired the page's dragstart (no {romp:'tabDrag',on} reached the shell) across five stepped moves and a 15s wait; the drag threshold was not crossed under load");
  // dragstart fired, so the shell mounts the zones now; this road drives the bottom drop zone
  try {
    await page.waitForFunction(() => !!document.querySelector("#chat-pane > .col-drop.col-drop-bottom"), null, { timeout: 20000 });
  } catch (e) {
    if (e && e.name === "TimeoutError") throw new Error("no drop zone: dragstart fired but the shell did not mount #chat-pane > .col-drop.col-drop-bottom within 20s (mountZones ran late, or the pane lost its zone under load)");
    throw e;
  }
  // The bottom drop zone is anchored to the pane's BOTTOM (col-drop-bottom is position:absolute; bottom:0; height set
  // inline), so when the split's sessions load and GROW the pane (#chat-pane is flex:60 1 0; 533 -> 686 px in CI) the
  // zone rides DOWN. A pointer placed from a rect read BEFORE that growth ends up ABOVE the shifted zone, over the column
  // zone -- the ghost never lights and the drop lands as a column move, so the post-mouse.up wait for a place:'below'
  // entry times out (the four cases' shared death, 2026-09-19). The lab makes that growth DETERMINISTIC and then survives
  // it. No fixed sleeps: a rAF gates each layout read.
  const readZone = () => page.evaluate(() => { const z = document.querySelector("#chat-pane > .col-drop.col-drop-bottom"); if (!z) return null; const r = z.getBoundingClientRect(); const p = z.parentElement.getBoundingClientRect(); return { col: z.getAttribute("data-col"), top: Math.round(r.top), height: Math.round(r.height), x: r.left + r.width / 2, y: r.top + r.height / 2, paneTop: Math.round(p.top), paneHeight: Math.round(p.height) }; });
  const raf = () => page.evaluate(() => new Promise((res) => requestAnimationFrame(() => res(true))));
  const ghostRead = () => page.evaluate(() => { const g = document.getElementById("col-ghost"); const r = g.getBoundingClientRect(); const p = document.getElementById("chat-pane").getBoundingClientRect(); return { cls: g.className, text: g.textContent, left: Math.round(r.left), top: Math.round(r.top), width: Math.round(r.width), height: Math.round(r.height), paneTop: Math.round(p.top), paneHeight: Math.round(p.height), paneLeft: Math.round(p.left), paneWidth: Math.round(p.width) }; });
  // FORCE the shift the flake rides on: pin #chat-pane SHORT (the bottom zone rides to the short bottom), record where a
  // single-read drive would aim, then release the pin so the pane springs to its real height and the zone drops well
  // below that point -- the mid-drag growth made reliable, a style toggle, no sleep.
  await page.evaluate(() => { const p = document.getElementById("chat-pane"); if (p) { p.style.setProperty("align-self", "flex-start", "important"); p.style.setProperty("height", "360px", "important"); } });
  await raf();
  const zShort = await readZone();
  out.shiftFrom = zShort ? zShort.y : null;   // the pre-growth read point a stale drive would release at
  await page.evaluate(() => { const p = document.getElementById("chat-pane"); if (p) { p.style.removeProperty("align-self"); p.style.removeProperty("height"); } });
  await raf();
  out.shiftTo = ((await readZone()) || {}).y ?? null;   // the zone's live centre once the pane has grown
  if (cfg.staleDrop) {
    // the OLD single-read drive (for the red): aim at the pre-growth point. The zone has ridden below it, so the pointer
    // sits over the column zone; the ghost never lights and the drop is a column move -- the place:'below' wait times out.
    out.bottomZone = zShort;
    if (zShort) await page.mouse.move(zShort.x, zShort.y, { steps: 4 });
    out.ghost = await ghostRead();
    await page.mouse.up();
  } else {
    // the FIX: track the LIVE zone the way a user does -- read it, move onto it, and repeat until the pane stops growing
    // AND the ghost is lit, then release THERE (a final re-read guards a last reflow). rAF-paced, bounded.
    let bz = await readZone();
    for (let i = 0; i < 60 && bz; i++) {
      await page.mouse.move(bz.x, bz.y, { steps: 4 });
      const next = await readZone();
      const ghostOn = await page.evaluate(() => { const g = document.getElementById("col-ghost"); return !!g && g.classList.contains("on"); });
      if (next && next.paneHeight === bz.paneHeight && ghostOn) { bz = next; break; }   // the pane stopped growing and the ghost is lit over the live zone: settled
      bz = next; await raf();
    }
    out.bottomZone = bz;
    out.ghost = await ghostRead();
    const drop = (await readZone()) || bz;
    await page.mouse.move(drop.x, drop.y, { steps: 2 });
    await page.mouse.up();
  }
  await page.waitForFunction(() => { const cc = JSON.parse(localStorage.getItem("romp-chat-cols") || "{}"); return (cc.cols || []).some((c) => c.place === "below"); }, null, { timeout: 20000 });
  // wait for the bottom pane's iframe to be BUILT (event-based), not a fixed settle, so afterDrop reads its id under load
  await page.waitForFunction(() => !!document.querySelector(".pane.split-v .chat-sub iframe"), null, { timeout: 20000 }).catch(() => {});
  out.afterDrop = await page.evaluate(() => {
    const cc = JSON.parse(localStorage.getItem("romp-chat-cols") || "{}"); const be = (cc.cols || []).find((c) => c.place === "below");
    const g = document.getElementById("col-ghost"); const bot = document.querySelector(".pane.split-v .chat-sub iframe");
    return { cols: localStorage.getItem("romp-chat-cols"), parent: be ? be.parent : null, botId: bot ? bot.id : null,
             ghostCls: g.className, zones: document.querySelectorAll(".col-drop").length, paneSplit: !!(bot && bot.closest(".pane") && bot.closest(".pane").classList.contains("split-v")) };
  });
  const botFid = out.afterDrop.botId;
  if (botFid) { await page.waitForFunction((fid) => !!document.getElementById(fid), botFid, { timeout: 20000 }); out.botFill = await filled(botFid); }
} catch (e) { out.died = String(e).slice(0, 500); }
process.stdout.write("RESULT:" + JSON.stringify(out) + "\n");
await browser.close();
"""


class _VSplitLab(unittest.TestCase):
    """Shared boot for the vertical-split labs: one hermetic kernel, two cut-floor sessions, a browser driver whose
    text each subclass names in DRIVER_JS (VSplitLocal drives the mutation; VSplitDrag drives the pointer)."""
    maxDiff = None
    DRIVER_JS = None
    CFG_EXTRA = {}      # a subclass's driver switches, written into cfg.json beside url, top, bot and staleDrop
    _cache = None

    @classmethod
    def setUpClass(cls):
        try:
            cls._boot()
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def _boot(cls):
        if not os.path.isdir(os.path.join(EXT, "node_modules", "playwright")):
            raise unittest.SkipTest("extension deps absent")
        probe = subprocess.run(["node", "-e", "const p=require(process.argv[1]);process.stdout.write(p.chromium.executablePath())",
                                os.path.join(EXT, "node_modules", "playwright")], capture_output=True, text=True)
        if probe.returncode != 0 or not os.path.exists(probe.stdout.strip()):
            raise unittest.SkipTest("no playwright browser")
        cls.lab = tempfile.mkdtemp(prefix="chat-vsplit-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            raise unittest.SkipTest("esbuild failed: " + (b.stderr or b.stdout)[-200:])
        copy_dist(os.path.join(EXT, "dist"), os.path.join(cls.lab, "dist"))
        sub = os.path.join(cls.lab, "solo")
        state = os.path.join(sub, "xdg", "romp")
        claude = os.path.join(sub, "claude")
        cwd = os.path.join(sub, "proj")
        for d in ("names", "sdk", "states", "checkpoints"):
            os.makedirs(os.path.join(state, d), exist_ok=True)
        os.makedirs(cwd, exist_ok=True)
        Path(state, "session-hosts").write_text("off\n")
        Path(state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 10}, "seven_day": {"pct": 10}}))
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        now = int(time.time())
        for sid, sname, age in ((SID_TOP, "api", 86400), (SID_BOT, "web", 90000)):
            Path(state, "names", sid).write_text("%s\t%s\t%s\t%s\n" % (sname, cwd, COLOR[0], COLOR[1]))
            Path(state, "sdk", sid + ".json").write_text(json.dumps(
                {"sid": sid, "name": sname, "cwd": cwd, "mode": "auto", "effort": "high",
                 "lastSid": sid, "alive": True, "model": "claude-opus-5", "liveModel": "Opus 5"}))
            Path(proj, sid + ".jsonl").write_text("".join(json.dumps(r) + "\n" for r in transcript(now - age, turns=600, compact_every=150)))
        # seed a cut-floor (documented) checkpoint for BOTH sessions, so each pane has a real head gap to fill
        os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
        km = load_source("romp_kernel_vsplit_seed", os.path.join(BIN, "romp-kernel"))
        jd, em = km.jd, km.em
        saved_state = jd.STATE
        try:
            jd._rebind_state(Path(state))
            em.set_checkpoint_dir(lambda: jd.STATE / "checkpoints")
            saved = (km._sessions, km._live_map)
            cls.seed = {}
            try:
                for sid in (SID_TOP, SID_BOT):
                    leaf = os.path.join(proj, sid + ".jsonl")
                    row = {"sid": sid, "name": "s", "path": leaf, "mtime": now, "anchor": sid}
                    km._sessions = lambda now=None, _r=row, **kw: [_r]
                    km._live_map = lambda: {}
                    km.build_session(sid, now, {}, floor=0)
                    cls.seed[sid] = bool(em.asm_checkpoint_write(leaf, sid, sdk_human=True, tree=km._parse(leaf, sid, now)))
            finally:
                km._sessions, km._live_map = saved
            ckpts = [os.path.basename(f) for f in glob.glob(os.path.join(str(state), "checkpoints", "*.asm.json.gz"))]
            if not all(cls.seed.values()) or len(ckpts) < 2:
                raise unittest.SkipTest("could not seed cut-floor documents: %r ckpts=%r" % (cls.seed, ckpts))
        finally:
            em.set_checkpoint_dir(None)
            jd._rebind_state(saved_state)
        cls.port, cls.token = _free_port(), "testtok-vsplit"
        env = _lab.kernel_env(sub, claude, os.path.join(cls.lab, "dist"), cls.port, cls.token)
        cls.klog = os.path.join(cls.lab, "kernel.log")
        cls.kernel = subprocess.Popen([os.path.join(BIN, "romp-kernel")], stdout=open(cls.klog, "w"), stderr=subprocess.STDOUT, env=env)
        cls.procs = [cls.kernel]
        for _ in range(120):
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/healthz" % cls.port, timeout=1); break
            except Exception:
                time.sleep(0.5)
        else:
            cls.kernel.kill(); raise unittest.SkipTest("kernel never served /healthz")

    @classmethod
    def tearDownClass(cls):
        for p in getattr(cls, "procs", []):
            try:
                p.kill(); p.wait()
            except Exception:
                pass
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

    def _result(self):
        if type(self)._cache is None:
            cfg = os.path.join(self.lab, "cfg.json")
            with open(cfg, "w") as f:
                json.dump({"url": "http://127.0.0.1:%d/?token=%s" % (self.port, self.token),
                           "top": SID_TOP, "bot": SID_BOT,
                           "staleDrop": bool(os.environ.get("VSPLIT_STALE_DROP")),
                           **type(self).CFG_EXTRA}, f)
            driver = os.path.join(self.lab, "driver.mjs")
            Path(driver).write_text(type(self).DRIVER_JS)
            p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=420,
                               env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
            if "browser-launch-failed" in p.stderr:
                raise unittest.SkipTest("no playwright browser")
            line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
            self.assertIsNotNone(line, "no RESULT (stderr: %s)" % p.stderr[-1500:])
            type(self)._cache = json.loads(line[len("RESULT:"):])
        r = type(self)._cache
        print("VSPLIT %s" % json.dumps(r)[:2000], file=sys.stderr)
        self.assertIsNone(r.get("died"), "driver error: %s" % r.get("died"))
        return r

    @staticmethod
    def _filled(colfill):
        after = (colfill or {}).get("after") or {}
        return any(x.get("kind") == "run" and x.get("lo") == 0 for x in (after.get("regions") or []))


class VSplitLocal(_VSplitLab):
    """The split through __rompMoveTab(sid,'down') (the drag's mutation): the geometry, the dial, the fill on both
    faces, the gutter drag, the unreloaded top and the per-half ring."""
    DRIVER_JS = DRIVER
    _cache = None

    def test_1_split_stacks_the_bottom_pane_under_the_top_with_a_row_resize_gutter(self):
        g = self._result().get("geom") or {}
        self.assertTrue(g.get("paneSplit"), "the parent .pane is .split-v: %r" % g)
        self.assertTrue(g.get("sameLeft") and g.get("belowTop"), "the bottom pane is stacked UNDER the top (same left, greater top): %r" % g)
        self.assertEqual(g.get("gutterCursor"), "row-resize", "the between-panes gutter is row-resize, not col-resize: %r" % g)

    def test_2_the_bottom_pane_dials_col_skeleton_with_its_own_iid(self):
        r = self._result()
        bot = [u for u in (r.get("botDials") or []) if "/ws" in u]
        self.assertTrue(bot, "the bottom frame opened a /ws dial: %r" % r.get("botDials"))
        self.assertTrue(any("skeleton=1" in u for u in bot), "the bottom dial carries skeleton=1: %r" % bot)
        import re as _re
        def iid(us):
            for u in us:
                m = _re.search(r"[?&]iid=([^&]+)", u)
                if m:
                    return m.group(1)
            return None
        bi, ti = iid(bot), iid([u for u in (r.get("topDials") or []) if "/ws" in u])
        self.assertTrue(bi, "the bottom dial carries an iid: %r" % bot)
        self.assertNotEqual(bi, ti, "the bottom pane's iid is distinct from the top pane's: bot=%r top=%r" % (bi, ti))

    def test_3_both_panes_fill_to_turn_0_at_creation(self):
        r = self._result()
        self.assertTrue((r.get("topFill", {}).get("boot") or {}).get("hasGapRegion"), "the top pane boots with a head gap: %r" % r.get("topFill"))
        self.assertTrue(self._filled(r.get("topFill")), "the TOP pane fills to turn 0: %r" % r.get("topFill"))
        self.assertTrue(self._filled(r.get("botFill")), "the BOTTOM pane fills to turn 0: %r" % r.get("botFill"))

    def test_4_the_non_focused_pane_fills_after_a_reload_the_wall_guard(self):
        r = self._result()
        cols = r.get("afterReload", {}).get("cols") or ""
        self.assertIn('"place":"below"', cols, "the split persists as a place:'below' cols entry: %r" % cols)
        self.assertIn('"parent":1', cols, "the bottom pane records its parent column (1): %r" % cols)
        self.assertTrue(self._filled(r.get("topReloadFill")), "the top pane fills to turn 0 after a reload: %r" % r.get("topReloadFill"))
        self.assertTrue(self._filled(r.get("botReloadFill")), "the NON-FOCUSED bottom pane fills to turn 0 after a reload (the wall guard): %r" % r.get("botReloadFill"))

    def test_5_dragging_the_gutter_moves_both_halves_and_persists_the_ratio(self):
        r = self._result()
        b, a = r.get("beforeDrag") or {}, r.get("afterDrag") or {}
        self.assertIsNotNone(a.get("subH"), "the bottom .chat-sub is a real element with a height: %r" % a)
        # dragging the gutter DOWN grows the top and shrinks the bottom; the HIGH bug wired flex to the absolute iframe
        # (inert), so the .chat-sub kept its creation flex and a drag collapsed it
        self.assertGreater(a.get("topH", 0), b.get("topH", 0) + 20, "the TOP half grew when the gutter was dragged down: before=%r after=%r" % (b, a))
        self.assertLess(a.get("subH", 1e9), b.get("subH", 0) - 20, "the BOTTOM half shrank, not collapsed: before=%r after=%r" % (b, a))
        self.assertGreater(a.get("subH", 0), 40, "the bottom half did not collapse to a sliver: after=%r" % a)
        self.assertAlmostEqual(a.get("ratio") or 0, a.get("onScreen") or 0, delta=0.05,
                               msg="the persisted ratio matches the on-screen top fraction: after=%r" % a)
        self.assertAlmostEqual((r.get("afterReload") or {}).get("belowRatio") or 0, a.get("ratio") or 0, delta=0.03,
                               msg="a reload restores the dragged ratio: reload=%r drag=%r" % (r.get("afterReload"), a))

    def test_6_the_top_iframe_is_not_reloaded_across_the_split(self):
        import re as _re
        r = self._result()
        def iid(us):
            for u in (us or []):
                if "/ws" not in u:
                    continue
                m = _re.search(r"[?&]iid=([^&]+)", u)
                if m:
                    return m.group(1)
            return None
        before, after = iid(r.get("topDialsBefore")), iid(r.get("topDialsAfter"))
        self.assertTrue(before, "the top frame dialed before the split: %r" % r.get("topDialsBefore"))
        self.assertEqual(before, after, "the top frame keeps its iid across the split (kept in place, not reparented or reloaded): before=%r after=%r" % (before, after))

    def test_7_the_focused_half_of_a_split_column_shows_its_own_ring(self):
        r = self._result()
        bot, top = r.get("ringBottomFocused") or {}, r.get("ringTopFocused") or {}
        self.assertTrue(bot.get("bottom") and not bot.get("top"), "clicking the BOTTOM half rings it alone (.focus-bottom): %r" % bot)
        self.assertTrue(top.get("top") and not top.get("bottom"), "clicking the TOP half moves the ring to it (.focus-top): %r" % top)

    def test_8_the_top_half_shrinks_past_the_iframes_intrinsic_min_when_dragged_fully_up(self):
        # LOW 1: without min-height:0 on .pane.split-v>iframe the top iframe floors at its ~150px automatic minimum (its
        # default object height), so a full-up drag (clamped to ~80px) leaves it ~70px too tall; the one declaration frees
        # it. Threshold 120 cleanly separates the pre-fix ~150px from the post-fix ~80px (robust to the 150-vs-154 border).
        a = self._result().get("afterUp") or {}
        self.assertIsNotNone(a.get("topH"), "the top half has a measured height after the up-drag: %r" % a)
        self.assertLess(a.get("topH", 10 ** 9), 120,
                        "the TOP half shrank past the iframe's ~150px intrinsic floor toward the ~80px drag clamp: %r" % a)


class VSplitDrag(_VSplitLab):
    """PR2: a REAL pointer drag of a tab to a pane's BOTTOM edge produces the split. The page's dragstart mounts the
    shell's zones; the split-down zone is a band at the pane's bottom; the ghost shows the pane's bottom half with the
    dragged session's name; the drop splits the column top and bottom and the new bottom pane fills to turn 0."""
    DRIVER_JS = POINTER_DRIVER
    _cache = None

    def test_0_the_layout_stood_still_through_the_drag(self):
        """The drag begins only once the timeline band has settled (its loader hidden, its height its content's), so the
        pane rect measured before the drag is the rect the zone, the ghost and the drop see. CI 2026-09-18: the band collapsed
        from its loader to two lanes mid-drag, the pane went 533 to 686, the ghost never turned on and the drop missed."""
        r = self._result()
        st = r.get("settled") or {}
        self.assertTrue(st.get("skipped") or abs(st.get("band", -99) - st.get("want", 99)) <= 1,
                        "the timeline band at its content height before the drag: %r" % st)
        heights = ((r.get("pane") or {}).get("height"), (r.get("bottomZone") or {}).get("paneHeight"), (r.get("ghost") or {}).get("paneHeight"))
        self.assertEqual(len(set(heights)), 1, "one pane height before the drag, at the zone and at the ghost: %r" % (heights,))

    def test_1_a_drag_to_the_bottom_edge_mounts_a_split_down_band_at_the_pane_bottom(self):
        r = self._result()
        bz = r.get("bottomZone") or {}
        self.assertEqual(bz.get("col"), "", "the first column's split-down zone carries data-col=''")
        # measured against the pane rect AT ZONE TIME (the layout settles as the sessions load, so a pre-drag rect drifts)
        self.assertGreater(bz.get("top", 0), bz["paneTop"] + bz["paneHeight"] / 2,
                           "the zone is a band in the pane's lower half: %r" % bz)

    def test_2_the_ghost_shows_the_panes_bottom_half_with_no_text(self):
        r = self._result()
        g = r.get("ghost") or {}
        self.assertIn("on", g.get("cls", "").split(), "the rectangle showed over the bottom zone: %r" % g)
        self.assertEqual(g.get("text"), "", "no text in the square (the dragged session's name left it, the user 2026-09-21): %r" % g)
        # the ghost is the pane's BOTTOM half, measured against the pane rect AT GHOST TIME
        self.assertAlmostEqual(g.get("top"), round(g["paneTop"] + g["paneHeight"] / 2), delta=2,
                               msg="the ghost's top is the pane's midline: %r" % g)
        self.assertAlmostEqual(g.get("height"), round(g["paneHeight"] / 2), delta=2, msg="half the pane's height: %r" % g)
        self.assertAlmostEqual(g.get("left"), g["paneLeft"], delta=2, msg="the pane's left edge: %r" % g)
        self.assertAlmostEqual(g.get("width"), g["paneWidth"], delta=2, msg="the full pane width: %r" % g)

    def test_3_the_drop_splits_the_column_into_a_bottom_pane_and_clears_the_zones(self):
        r = self._result()
        d = r.get("afterDrop") or {}
        self.assertEqual(d.get("parent"), 1, "a place:'below' entry keyed on parent 1: %r" % d.get("cols"))
        self.assertTrue(d.get("botId"), "the bottom pane iframe mounted: %r" % d)
        self.assertTrue(d.get("paneSplit"), "the parent .pane became .split-v: %r" % d)
        self.assertEqual(d.get("zones"), 0, "every drag zone unmounted at the drop: %r" % d)
        self.assertNotIn("on", d.get("ghostCls", "").split(), "the rectangle hidden at the drop: %r" % d.get("ghostCls"))

    def test_4_the_dragged_down_session_fills_its_bottom_pane_to_turn_0(self):
        r = self._result()
        self.assertTrue((r.get("botFill") or {}).get("filled"),
                        "the dragged-down session's bottom pane fills to turn 0 (the wall lesson): %r" % r.get("botFill"))

    def test_5_the_drop_survives_the_mid_drag_pane_growth_that_rides_the_zone_down(self):
        # The regression's shape, forced deterministically: the driver pins the pane short, notes where a single-read
        # drive would aim (shiftFrom), then lets the pane spring to its real height so the bottom-anchored zone rides down
        # (shiftTo). The zone moving well below the read point is what makes a stale release miss; the drive must track it.
        r = self._result()
        sf, st = r.get("shiftFrom"), r.get("shiftTo")
        self.assertIsNotNone(sf); self.assertIsNotNone(st)
        self.assertGreater(st - sf, 50, "the forced growth rode the bottom zone DOWN past the read point (else the red is vacuous): from=%r to=%r" % (sf, st))
        bz = r.get("bottomZone") or {}
        self.assertGreater(sf, 0)
        self.assertLess(sf, bz.get("top", 0), "the pre-growth read point now sits ABOVE the grown zone, so a stale release would miss it (the bug); the live-tracking drive lands anyway: read=%r grownZoneTop=%r" % (sf, bz.get("top")))
        # and, tracking the live zone, the drop DID land below (the driver would have died on the place:'below' wait otherwise)
        self.assertIn('"place":"below"', (r.get("afterDrop") or {}).get("cols") or "", "the drop landed below despite the shift: %r" % (r.get("afterDrop") or {}).get("cols"))


class VSplitDragLateTimeline(VSplitDrag):
    """The same drag with the timeline's document held until the tab is ready, so the band's loader and then its bars land
    while the driver waits: the settle wait is a real wait here (the band moves from its loader height to its content height
    before the drag begins), where VSplitDrag's timeline has usually settled before the driver looks. It does not reproduce
    the 2026-09-18 CI shape (the band collapsing mid-drag, the pane 533 px at the zone and 686 at the ghost, the drop
    missed): on a fast machine the drop lands with or without the wait. test_0 pins the witness and the equal heights against
    the late loader, test_6 that the hold engaged; VSplitDragBarsHeldPastTheZone is the case that fails without the wait."""
    CFG_EXTRA = {"holdTimeline": True}
    _cache = None

    def test_6_the_timeline_document_was_held_while_the_driver_waited_for_the_tab(self):
        """The hold engaged: the route saw the /timeline document, and saw it while the hold was in force, so the band's
        loader and bars landed late by construction. Without this the class would run the plain drag under its own name if
        the route stopped matching (a moved path, the switch never reaching the driver)."""
        h = self._result().get("timelineHeld") or {}
        self.assertTrue(h.get("requests"), "the route saw the /timeline document: %r" % (h,))
        self.assertTrue(h.get("beforeRelease"), "the document was requested while the hold was in force: %r" % (h,))


BARS_HOLD_JS = r"""
// The timeline's BARS held on the wire: every frame from the first {type:"bars"} full (or a bars delta) on the app=timeline
// socket queues until releaseBars(), which the driver calls right after it has measured the drop zone. So the bars can land
// only AFTER that measure, and what the band does before it is the timeline's own: with no bars it keeps its loader, and its
// loader backstop (ui/romp-timeline-view.js, 12 s) draws the lanes without them. The drain is registered once, when the
// socket opens, and every frame after the release passes straight through, so out.barsHold.held is the queue depth AT the
// release (every queued frame is still queued then) and out.barsHold.late counts the bars frames that arrived after it.
// Which road ran depends on the kernel's speed: a kernel with the bars ready before the measure has them queued (held), one
// that builds them longer than the driver's lead sends them after the release (late), and the bars land after the measure
// on either road, which is the premise the case asserts through the plot (BARS_RELEASE_JS). sockets 0 means the route
// matched no timeline socket and the hold was never in the path.
let releaseBars = () => {}; const barsHeld = new Promise((r) => { releaseBars = r; });
out.barsHold = { sockets: 0, held: 0, late: 0 };
const isBars = (m) => { if (typeof m !== "string") return false; try { const j = JSON.parse(m); return !!j && (j.type === "bars" || (j.type === "delta" && j.slot === "bars")); } catch (e) { return false; } };
await page.routeWebSocket((u) => /[?&]app=timeline(&|$)/.test(String(u)), (ws) => {
  out.barsHold.sockets += 1;
  const server = ws.connectToServer(); let held = false, released = false; const q = [];
  ws.onMessage((m) => server.send(m));
  ws.onClose(() => { try { server.close(); } catch (e) {} });
  server.onClose(() => { try { ws.close(); } catch (e) {} });
  barsHeld.then(() => { released = true; while (q.length) ws.send(q.shift()); });
  server.onMessage((m) => {
    if (released) { if (isBars(m)) out.barsHold.late += 1; ws.send(m); return; }
    if (!held && isBars(m)) held = true;
    if (!held) { ws.send(m); return; }
    q.push(m); out.barsHold.held += 1;
  });
});
"""

BARS_RELEASE_JS = r"""
    // The bars land now, after the zone was measured and the tracking loop above has settled on it. First wait for the bars
    // to reach the plot: draw() rebuilds the wrap's svg when they land, and until then it holds no bars (empty under the
    // loader, the bare lanes after the backstop), so the svg gaining elements is a witness that reads neither the loader's
    // display nor the band's height. A settle predicate that passed early would otherwise pass this case too, the ghost read
    // before the bars landed, against the same rect the zone saw. Then wait for the band's settle event (loader hidden, plot
    // shown, band at its content height), never a delay, so whatever the bars do to the layout is done before the ghost is
    // read: a band that had settled before the measure passes at once and the drag goes on unchanged; a band still at its
    // loader height collapses here, the pane grows, and the zone pinned to its bottom has moved between the zone read and the
    // ghost read (the re-read before mouse.up still lands the drop, so the pane heights are the finding).
    const plotMarks = () => page.evaluate(() => { const tf = document.getElementById("f-timeline"); const d = tf && tf.contentDocument; const svg = d && d.querySelector(".romp-tl-wrap > svg"); return svg ? svg.querySelectorAll("*").length : -1; });
    const marksBefore = await plotMarks();
    releaseBars();
    await page.waitForFunction((n) => {
      if (!document.body.classList.contains("po-timeline")) return true;
      const tf = document.getElementById("f-timeline"); const d = tf && tf.contentDocument; const svg = d && d.querySelector(".romp-tl-wrap > svg");
      return !!svg && svg.querySelectorAll("*").length > n;
    }, marksBefore, { timeout: 40000 }).catch((e) => {
      if (!(e && e.name === "TimeoutError")) throw e;
      throw new Error("the bars did not reach the plot after the release (the wrap's svg gained no element over " + marksBefore + ") within 40 s; barsHold " + JSON.stringify(out.barsHold)
        + (out.barsHold.held ? "" : " (nothing was queued before the release: the bars landed before the zone measure, or the hold matched no frame)") + "; " + ((e && e.message) || e));
    });
    out.afterBars = await settled();
    out.afterBars.plotMarks = { before: marksBefore, after: await plotMarks() };
    out.afterBars.paneHeight = await page.evaluate(() => Math.round(document.getElementById("chat-pane").getBoundingClientRect().height));
"""


def _bars_held_past_the_zone(driver):
    """POINTER_DRIVER with the bars hold installed before the page loads and released right after the zone measure. Each
    insertion point must match exactly once, so a driver rewrite that moves either line fails here, loudly, not in the drag."""
    hold_at, release_at = "const out = { died: null };", "out.bottomZone = bz;"
    assert driver.count(hold_at) == 1 and driver.count(release_at) == 1, "the bars-hold insertion points changed"
    return driver.replace(hold_at, hold_at + BARS_HOLD_JS, 1).replace(release_at, release_at + BARS_RELEASE_JS, 1)


class VSplitDragBarsHeldPastTheZone(VSplitDrag):
    """The same drag with the timeline's bars held on the wire until the driver has measured the drop zone, so they can land
    only after that measure. Before it, the band is the timeline's alone: a loader until the bars, then the lanes when the
    view's loader backstop gives up waiting for them. A driver that waits for the band to settle before the drag measures
    after that draw, at the lanes' height, and the bars landing mid-drag change nothing. A driver that starts the drag without
    waiting measures the loader-height pane; the bars then collapse the band, the pane grows and the zone pinned to its bottom
    moves out from under the pointer (CI 2026-09-18: 533 at the zone, 686 at the ghost, the ghost never on, the drop missed).
    The live-tracking drive re-reads the zone before it releases, so here the drop lands either way and the pane heights are
    the finding. The order of events is fixed with and without the wait, whatever the machine's speed: the release is keyed
    on the measure and the drag on the settle. After the release the driver waits for the bars to reach the plot before the
    settle wait, a witness that reads neither the loader's display nor the band's height, so a settle predicate that passes
    early (at the loader-height band) is red here too: the ghost is read only after the bars landed.

    Three couplings, all to the view's loader backstop (ui/romp-timeline-view.js, 12 s), which is the only cause that can
    settle the band while the bars are held. CEILING: the green side needs the backstop shorter than the settle wait plus the
    driver's lead to it; past that the band never settles and the wait names the step when it gives up, a loud red. FLOOR:
    the RED side needs the backstop to fire after a driver without the wait reaches its zone measure. On a runner slow enough
    to invert that, the band collapses before the measure, the run without the wait passes, and the reproduction stops
    discriminating while never giving a false red with it. HEIGHT: the green side needs the released bars to add no height
    (no judge band, the same lane set), true of this lab's fixtures because the svg's height follows lanes and judging rather
    than turns; a fixture that changes it is a loud red with and without the wait rather than a silent pass."""
    DRIVER_JS = _bars_held_past_the_zone(POINTER_DRIVER)
    _cache = None

    def _raw(self):
        """The driver's result whether or not it died: a driver that died on a later wait still recorded the geometry,
        which is the finding."""
        try:
            self._result()
        except AssertionError:
            if type(self)._cache is None:
                raise
        return type(self)._cache

    def test_6_the_bars_were_held_and_the_drop_landed_where_the_zone_was_measured(self):
        r = self._raw()
        hold, bz, g, d = r.get("barsHold") or {}, r.get("bottomZone") or {}, r.get("ghost") or {}, r.get("afterDrop") or {}
        marks = (r.get("afterBars") or {}).get("plotMarks") or {}
        self.assertTrue(hold.get("sockets") and marks.get("after", -1) > marks.get("before", 10 ** 9),
                        "the bars landed AFTER the zone measure: the hold matched the timeline socket, and the plot gained the "
                        "bars' marks after the release (held frames were released there; late ones arrived after it): "
                        "barsHold=%r plotMarks=%r died=%r" % (hold, marks, r.get("died")))
        self.assertEqual(bz.get("paneHeight"), g.get("paneHeight"),
                         "the pane rect held from the zone to the ghost: %r at the zone, %r at the ghost; after the bars landed %r; "
                         "the ghost's class %r" % (bz.get("paneHeight"), g.get("paneHeight"), r.get("afterBars"), g.get("cls")))
        self.assertEqual(d.get("parent"), 1,
                         "the drop split the column (a place:'below' entry keyed on parent 1): died=%r afterDrop=%r" % (r.get("died"), d))


if __name__ == "__main__":
    unittest.main()
