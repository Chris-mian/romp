#!/usr/bin/env python3
"""Live divider resizing on the REAL dashboard (plans/pane-docking.md section 12, the user 2026-09-20): every divider drag
renders the panes it affects at their new sizes continuously, one layout per animation frame, with no provisional line.
A hermetic kernel serves the dashboard with two synthetic sessions; a Chromium driver drives REAL pointer events over the
four divider drags the dashboard has and reads, for each:
  - mid-drag, at three sample points, the two panes' widths (or heights) equal the pointer's split within a pixel;
  - the release persists the drag's store ONCE (a Storage.setItem count on the key), never per frame;
  - Escape restores the pre-drag sizes live and writes nothing;
  - the iframes keep their content across the drag (a probe set in each frame survives: no reload);
  - a far drag stops at the pair's real minimum (120 px) with the edge at the pointer up to it (the kit's clamp holds against
    the geometry at the PRESS, never against the tree the drag rewrote the frame before);
  - the chat's reader survives the reflow: one at the true bottom stays within 2 px of it at three samples through a narrowing
    drag (the transcript wraps longer and the view grows under them); one scrolled up keeps the line they read where it was
    ON SCREEN within a pixel (the browser's scroll anchoring holds their turn while the transcript above it re-wraps; the
    chat's own strip compensation holds it when the tab strip wraps to another row as the pane narrows);
  - Escape is heard from a keyboard inside a pane (the chat's composer focused), and a release with no frame between it and
    the last move lands that position itself with one store write;
  - under the kit, a pane toggled mid-drag ends the drag committed and the store parses, matches the screen and survives a
    reload; the band re-sized by the shell's autosize under a column drag keeps its height through the drag's frames and
    reaches the store once; the band's own edge writes the store once at release and nothing on Escape; the divider's cursor
    holds over the panes for the drag.
The four: (1) the shipped column gutters (kit off), (2) the sessions band's height divider (kit off), (3) the chat's vertical
split divider (kit off, a session moved down), (4) the docking kit's dividers (kit on: a divider between columns and one
between rows). The lab also measures the cost the design names: frames per second from the shell's requestAnimationFrame
timestamps during a drag across the row with every pane on, and the browser's long-animation-frame entries over that span
(reported in the RESULT), and pins the longest animation-frame callback the shell runs over the drag, the one cost that does not
move with the CPU quota. Runs when ROMP_SERVED_TESTS_REQUIRE=1 (CI); skips where no Chromium
is installed. Synthetic fixtures only."""
import json
import os
import re
import shutil
import signal
import socket
import subprocess
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
TOP = "11111111-2222-4333-8444-000000000401"     # web
BOT = "11111111-2222-4333-8444-000000000402"     # api

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


def _transcript(sid, cwd, pairs, tag):
    out, parent, t = [], None, 1_700_000_000
    filler = ["The ranking pass reads its weights from the notes-api config now.",
              "Tokenizer edge cases (hyphens, quotes) are covered by the new fixture set.",
              "Index rebuild time is dominated by the stemmer; caching its table halves it.",
              "The pagination cursor survives a re-sort because it encodes the sort key too."]
    for i in range(pairs):
        u = "11111111-2222-4333-8444-00000%s%04x" % (tag, i)
        a = "11111111-2222-4333-8444-00000%s%04x" % (tag + "f", i)
        ts = lambda k: time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t + i * 60 + k))
        out.append({"type": "user", "uuid": u, "parentUuid": parent, "timestamp": ts(0), "sessionId": sid, "cwd": cwd,
                    "message": {"role": "user", "content": "please keep going with the search module notes (part %d)" % (i + 1)}})
        body = "\n\n".join(["Note %d." % (i + 1)] + [filler[(i + k) % len(filler)] for k in range(3)])
        out.append({"type": "assistant", "uuid": a, "parentUuid": u, "timestamp": ts(5), "sessionId": sid, "cwd": cwd,
                    "message": {"id": "msg_lab_%s_%04d" % (tag, i), "type": "message", "role": "assistant", "model": "claude-sonnet-5",
                                "content": [{"type": "text", "text": body}], "stop_reason": "end_turn"}})
        parent = a
    return "\n".join(json.dumps(r) for r in out) + "\n"


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
const die = async (why) => { fs.writeSync(1, "RESULT:" + JSON.stringify({ ...out, died: why }) + "\n"); await browser.close(); process.exit(0); };
// Chromium delivers pointer moves aligned to animation frames and the shell applies a divider's position at the next frame: read
// geometry only after two frames have passed since the move (an event wait, not a timer)
const frame = (page) => page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r(1)))));
const rect = (page, sel) => page.evaluate((s) => { const el = document.querySelector(s); if (!el) return null; const r = el.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height, right: r.right, bottom: r.bottom }; }, sel);
// the shell's stores: every localStorage write counted by key (the release writes once, a frame never)
const instrument = async (page) => page.evaluate(() => {
  const w = window; w.__writes = {}; const set = Storage.prototype.setItem;
  Storage.prototype.setItem = function (k, v) { w.__writes[k] = (w.__writes[k] || 0) + 1; return set.call(this, k, v); };
  w.__frames = []; w.__framesOn = false;
  // the page's own frame callbacks TIMED: the shell's frame helpers read window.requestAnimationFrame at call time, so every callback
  // they arm runs through this wrapper; the longest one over a drag is the cost that is load-independent (a busy frame in the gutter's
  // apply() is 80 ms whatever the CPU quota; a starved CPU stretches the drag over more frames but each callback stays a few ms)
  const raf0 = w.requestAnimationFrame.bind(w); w.__cbMax = 0; w.__cbN = 0; w.__cbLong = 0;
  w.requestAnimationFrame = (cb) => raf0((t) => { const s = performance.now(); try { return cb(t); } finally { const d = performance.now() - s; w.__cbN++; if (d > w.__cbMax) w.__cbMax = d; if (d > 40) w.__cbLong++; } });
  const loop = (t) => { if (w.__framesOn) w.__frames.push(t); raf0(loop); }; raf0(loop);
  w.__loaf = []; try { new PerformanceObserver((l) => { for (const e of l.getEntries()) w.__loaf.push({ t: e.startTime, d: e.duration }); }).observe({ type: "long-animation-frame", buffered: false }); } catch (e) { w.__loafErr = String(e); }
  return true;
});
const writes = (page) => page.evaluate(() => Object.assign({}, window.__writes));
const probeSet = (fr) => fr.evaluate(() => { window.__probe = 1; return 1; }).catch(() => false);
const probeAlive = (fr) => fr.evaluate(() => window.__probe === 1).catch(() => false);
const frameOfPath = (page, re) => page.frames().find((f) => re.test(f.url()));

// ── (A) the kit OFF: the shipped column gutters, the band's height divider, the chat's vertical split ─────────────────────────
const ctxA = await browser.newContext({ viewport: { width: 1500, height: 900 } });
const page = await ctxA.newPage();
page.on("pageerror", (e) => out.errors.push("A: " + String(e).slice(0, 200)));
await page.addInitScript(() => { try { const s = JSON.parse(localStorage.getItem("romp:settings") || "{}"); s.showFilesControl = true; localStorage.setItem("romp:settings", JSON.stringify(s)); } catch (e) {} });
await page.goto(cfg.url);
await page.waitForSelector("#f-chat", { timeout: 30000 }).catch(async () => { await die("no chat frame"); });
await page.waitForFunction(() => Array.from(document.querySelectorAll("iframe")).some((f) => (f.getAttribute("src") || "").startsWith("/chat")), null, { timeout: 20000 });
await page.evaluate(() => { window.__rompPaneToggle("fleet", true); window.__rompPaneToggle("files", true); });   // every pane on: chat, Outline, feed, Files, the band
await page.waitForTimeout(1200);
await instrument(page);
const chatFr = frameOfPath(page, /\/chat(\?|$)/), feedFr = frameOfPath(page, /\/feed(\?|$)/);
if (!chatFr || !feedFr) await die("chat or feed frame missing");
await chatFr.waitForFunction(() => document.querySelectorAll("#content .turn").length > 10, null, { timeout: 30000 }).catch(() => {});
await probeSet(chatFr); await probeSet(feedFr);
out.panesOn = await page.evaluate(() => document.body.className.split(/\s+/).filter((c) => /^po-/.test(c)).sort());

// a divider drag with three sample points: press at the divider, move past the slop to each sample, read the pair after two frames
async function dragH(gutterSel, leftSel, rightSel, samples, { release = true, escape = false, key = null } = {}) {
  const g = await rect(page, gutterSel); if (!g) return { error: "no gutter " + gutterSel };
  const L0 = await rect(page, leftSel), R0 = await rect(page, rightSel);
  const w0 = await writes(page);
  const x0 = g.x + g.w / 2, y0 = g.y + g.h / 2;
  await page.mouse.move(x0, y0); await page.mouse.down(); await frame(page);
  const rec = { before: { L: L0, R: R0 }, points: [] };
  for (const dx of samples) {
    await page.mouse.move(x0 + dx, y0, { steps: 4 }); await frame(page);
    const L = await rect(page, leftSel), R = await rect(page, rightSel);
    rec.points.push({ dx, pointerX: x0 + dx, L: { x: L.x, w: L.w, right: L.right }, R: { x: R.x, w: R.w }, sum: L.w + R.w,
      ghost: await page.evaluate(() => { const gh = document.getElementById("gv-ghost"); return gh ? getComputedStyle(gh).display : "absent"; }) });
  }
  if (escape) { await page.keyboard.press("Escape"); await frame(page); }
  else if (release) { await page.mouse.up(); await frame(page); }
  const wAfter = await writes(page);
  rec.after = { L: await rect(page, leftSel), R: await rect(page, rightSel), writes: key ? (wAfter[key] || 0) - (w0[key] || 0) : null, allWrites: wAfter };
  if (escape) { await page.mouse.up(); await frame(page); rec.afterUp = { L: await rect(page, leftSel), R: await rect(page, rightSel), writes: key ? ((await writes(page))[key] || 0) - (w0[key] || 0) : null }; }
  return rec;
}
// the chat's reader through a drag: the transcript's scroller (#content), its distance from the bottom, its height and width
const recordScrollWrites = () => chatFr.evaluate(() => { const c = document.getElementById("content"); const d = Object.getOwnPropertyDescriptor(Element.prototype, "scrollTop");
  window.__stw = []; if (c.__stwHooked) return true; c.__stwHooked = true;
  Object.defineProperty(c, "scrollTop", { configurable: true, get() { return d.get.call(this); },
    set(v) { window.__stw.push({ to: v, from: d.get.call(this), by: String(new Error().stack || "").split("\n").slice(2, 5).map((l) => l.trim().replace(/\(.*\//, "(").slice(0, 60)) }); d.set.call(this, v); } });
  return true; });
const readerAt = () => chatFr.evaluate(() => { const c = document.getElementById("content"); const a = document.querySelector(".turn[data-lab-anchor]");
  return { dist: c.scrollHeight - c.scrollTop - c.clientHeight, top: c.scrollTop, sh: c.scrollHeight, ch: c.clientHeight, w: c.clientWidth, turns: c.querySelectorAll(".turn").length,
    anchor: a ? Math.round((a.getBoundingClientRect().top - c.getBoundingClientRect().top) * 100) / 100 : null, screen: a ? Math.round(a.getBoundingClientRect().top * 100) / 100 : null,
    ctop: Math.round(c.getBoundingClientRect().top * 100) / 100, strip: (() => { const tb = document.getElementById("tabbar"); return tb ? Math.round(tb.getBoundingClientRect().height * 100) / 100 : 0; })(),
    writes: (window.__stw || []).splice(0) }; });
// a drag on the chat | Outline gutter reading the chat's reader at every sample (a narrowing drag: the pointer moves left)
async function dragReader(samples, place) {
  await chatFr.evaluate(() => document.querySelectorAll(".turn[data-lab-anchor]").forEach((n) => n.removeAttribute("data-lab-anchor")));
  if (place === "bottom") await chatFr.evaluate(() => { const c = document.getElementById("content"); c.scrollTop = c.scrollHeight; });
  else {
    // scrolled up: the turn a third of the way down the transcript with its top a pixel above the scroller's top, so the turn
    // before it is wholly out of view and the browser's scroll anchor is this turn's first line (the browser holds the top of
    // the first visible node: with the previous turn's last block a sliver in view, that block's own re-wrap would push every
    // line under it down the screen); a screen or more of transcript above re-wraps, and the reader is well above the bottom
    await chatFr.evaluate(() => { const c = document.getElementById("content");
      const turns = Array.from(c.querySelectorAll(".turn")).filter((n) => n.getBoundingClientRect().height > 0);   // the laid-out turns (a turn folded away has no box)
      const t = turns[Math.floor(turns.length / 3)];
      t.setAttribute("data-lab-anchor", "1"); c.scrollTop += t.getBoundingClientRect().top - c.getBoundingClientRect().top + 1; });
  }
  await frame(page); await frame(page); await recordScrollWrites();
  const g = await rect(page, "#gv-a"); const x0 = g.x + g.w / 2, y0 = g.y + g.h / 2;
  const rec = { place, before: await readerAt(), chatW0: (await rect(page, "#chat-pane")).w, points: [] };
  await page.mouse.move(x0, y0); await page.mouse.down(); await frame(page);
  for (const dx of samples) { await page.mouse.move(x0 + dx, y0, { steps: 4 }); await frame(page); await frame(page); rec.points.push({ dx, reader: await readerAt(), chatW: (await rect(page, "#chat-pane")).w }); }
  await page.keyboard.press("Escape"); await frame(page); await page.mouse.up(); await frame(page); await frame(page);
  rec.after = await readerAt();
  return rec;
}
out.readerBottom = await dragReader([-120, -240, -340], "bottom");
out.readerUp = await dragReader([-120, -240, -340], "up");
// (1) the shipped chat | Outline gutter (gv-a, both shown)
out.gutter = await dragH("#gv-a", "#chat-pane", "#fleet-pane", [-120, -60, 80], { key: "romp-pane-grow" });
out.gutterEscape = await dragH("#gv-a", "#chat-pane", "#fleet-pane", [-90, 60], { escape: true, key: "romp-pane-grow" });
out.probesAfterGutter = { chat: await probeAlive(chatFr), feed: await probeAlive(feedFr) };
// (1c) Escape from a keyboard INSIDE a pane: the chat's composer focused, the divider pressed (the press keeps the keyboard where
// it was), Escape heard by the drag's listener on the pane document; the keyboard handed back to the shell after (focus is sticky)
const focusComposer = (fr) => fr.evaluate(() => { const t = document.querySelector("#composer textarea") || document.querySelector("textarea"); if (t) t.focus(); return { tag: document.activeElement && document.activeElement.tagName, id: document.activeElement && document.activeElement.id }; });
const keyboardBack = (pg) => pg.evaluate(() => { const a = document.activeElement; if (a && a.tagName === "IFRAME") a.blur(); return document.activeElement ? document.activeElement.tagName : null; });
out.composerFocus = await focusComposer(chatFr);
out.topActiveDuringComposer = await page.evaluate(() => document.activeElement && document.activeElement.id);
out.gutterEscapeComposer = await dragH("#gv-a", "#chat-pane", "#fleet-pane", [-90, 60], { escape: true, key: "romp-pane-grow" });
out.keyboardBack = await keyboardBack(page);
// (1d) a move and a release with NO frame between them: the release lands the position under the pointer itself, one store write
async function sameTaskH(gutterSel, leftSel, key, dx) {
  const g = await rect(page, gutterSel); const L0 = await rect(page, leftSel); const w0 = await writes(page);
  const x0 = g.x + g.w / 2, y0 = g.y + g.h / 2;
  await page.mouse.move(x0, y0); await page.mouse.down(); await frame(page);
  await page.mouse.move(x0 + dx, y0); await page.mouse.up();
  await frame(page); await frame(page);
  return { before: L0.w, after: (await rect(page, leftSel)).w, dx, writes: ((await writes(page))[key] || 0) - (w0[key] || 0) };
}
out.gutterSameTask = await sameTaskH("#gv-a", "#chat-pane", "romp-pane-grow", -70);

// (2) the band's height divider (#gh, --tl): the pointer's distance from the column's bottom is the band's height (clamped to its content)
async function dragBand(dys, { escape = false } = {}) {
  const g = await rect(page, "#gh"); if (!g) return { error: "no band gutter" };
  const col = await rect(page, ".col");
  const tl0 = await page.evaluate(() => getComputedStyle(document.querySelector(".col")).getPropertyValue("--tl"));
  const band0 = await rect(page, "#tl-pane");
  const w0 = await writes(page);
  const x0 = g.x + g.w / 2, y0 = g.y + g.h / 2;
  await page.mouse.move(x0, y0); await page.mouse.down(); await frame(page);
  const rec = { tl0, band0: { h: band0.h }, points: [] };
  for (const dy of dys) {
    await page.mouse.move(x0, y0 + dy, { steps: 4 }); await frame(page);
    const b = await rect(page, "#tl-pane");
    rec.points.push({ dy, pointerY: y0 + dy, wanted: col.bottom - (y0 + dy), bandH: b.h, tl: await page.evaluate(() => document.querySelector(".col").style.getPropertyValue("--tl")) });
  }
  if (escape) { await page.keyboard.press("Escape"); await frame(page); await page.mouse.up(); await frame(page); }
  else { await page.mouse.up(); await frame(page); }
  rec.after = { bandH: (await rect(page, "#tl-pane")).h, tl: await page.evaluate(() => document.querySelector(".col").style.getPropertyValue("--tl")), writes: Object.entries(await writes(page)).filter(([k, n]) => (n || 0) !== (w0[k] || 0)).map(([k]) => k) };
  return rec;
}
out.band = await dragBand([50, 65, 58]);          // down: the band shrinks (its content caps growth and 48 px floors it, so the samples sit between)
out.bandEscape = await dragBand([55, 70], { escape: true });

// (3) the chat's vertical split: a session moved DOWN makes a bottom pane and a row-resize gutter between the two frames
out.split = await page.evaluate((bot) => { const f = window.__rompMoveTab(bot, "down"); return { frameId: f && f.id }; }, cfg.bot);
await page.waitForSelector(".pane.split-v .gh-chat", { timeout: 15000 }).catch(async () => { await die("no vertical split gutter"); });
await page.waitForTimeout(800);
async function dragV(gutterSel, topSel, botSel, dys, { escape = false } = {}) {
  const g = await rect(page, gutterSel); if (!g) return { error: "no gutter " + gutterSel };
  const T0 = await rect(page, topSel), B0 = await rect(page, botSel);
  const w0 = await writes(page);
  const x0 = g.x + g.w / 2, y0 = g.y + g.h / 2;
  await page.mouse.move(x0, y0); await page.mouse.down(); await frame(page);
  const flexes = () => page.evaluate(({ a, b }) => ({ T: document.querySelector(a).style.flex, B: document.querySelector(b).style.flex }), { a: topSel, b: botSel });
  const rec = { before: { T: { y: T0.y, h: T0.h }, B: { y: B0.y, h: B0.h }, flex: await flexes() }, points: [] };
  for (const dy of dys) {
    await page.mouse.move(x0, y0 + dy, { steps: 4 }); await frame(page);
    const T = await rect(page, topSel), B = await rect(page, botSel);
    rec.points.push({ dy, pointerY: y0 + dy, T: { y: T.y, h: T.h, bottom: T.bottom }, B: { y: B.y, h: B.h }, sum: T.h + B.h });
  }
  if (escape) { await page.keyboard.press("Escape"); await frame(page); await page.mouse.up(); await frame(page); }
  else { await page.mouse.up(); await frame(page); }
  const wAfter = await writes(page);
  rec.after = { T: await rect(page, topSel), B: await rect(page, botSel), writes: (wAfter["romp-chat-cols"] || 0) - (w0["romp-chat-cols"] || 0), flex: await flexes() };
  return rec;
}
const subSel = ".pane.split-v .chat-sub";
out.vsplit = await dragV(".pane.split-v .gh-chat", "#f-chat", subSel, [-80, 60, -30]);
out.vsplitEscape = await dragV(".pane.split-v .gh-chat", "#f-chat", subSel, [70, -50], { escape: true });
out.probesAfterAll = { chat: await probeAlive(chatFr), feed: await probeAlive(feedFr) };

// (5) the cost: a drag across the row on the chat | Outline gutter with every pane on, frames sampled from requestAnimationFrame
{
  const g = await rect(page, "#gv-a");
  const x0 = g.x + g.w / 2, y0 = g.y + g.h / 2;
  const cdp = await ctxA.newCDPSession(page); await cdp.send("Performance.enable");
  const metric = async (name) => { const r = await cdp.send("Performance.getMetrics"); const e = (r.metrics || []).find((x) => x.name === name); return e ? e.value : null; };
  const layouts0 = await metric("LayoutCount"), styles0 = await metric("RecalcStyleCount");
  await page.evaluate(() => { window.__frames = []; window.__loaf = []; window.__framesOn = true; window.__cbMax = 0; window.__cbN = 0; window.__cbLong = 0; });
  const t0 = Date.now();
  await page.mouse.move(x0, y0); await page.mouse.down();
  await page.mouse.move(x0 - 320, y0, { steps: 24 }); await page.mouse.move(x0 + 320, y0, { steps: 48 }); await page.mouse.move(x0, y0, { steps: 24 });
  await page.mouse.up(); await frame(page);
  const ms = Date.now() - t0;
  const m = await page.evaluate(() => { const f = window.__frames; window.__framesOn = false; const span = f.length > 1 ? f[f.length - 1] - f[0] : 0; const gaps = []; for (let i = 1; i < f.length; i++) gaps.push(f[i] - f[i - 1]);
    return { frames: f.length, spanMs: Math.round(span), fps: span > 0 ? Math.round((f.length - 1) * 1000 / span) : null, maxGapMs: Math.round(Math.max(0, ...gaps)), loaf: window.__loaf.length, loafMaxMs: Math.round(Math.max(0, ...window.__loaf.map((e) => e.d))), loafErr: window.__loafErr || null,
      cbMaxMs: Math.round(window.__cbMax * 10) / 10, cbCount: window.__cbN, cbLong: window.__cbLong }; });
  const layouts1 = await metric("LayoutCount"), styles1 = await metric("RecalcStyleCount");
  out.cost = Object.assign({ dragMs: ms, panes: out.panesOn, layouts: layouts1 !== null && layouts0 !== null ? layouts1 - layouts0 : null, styleRecalcs: styles1 !== null && styles0 !== null ? styles1 - styles0 : null }, m);
  if (cfg.shots) { await page.mouse.move(x0, y0); await page.mouse.down(); await page.mouse.move(x0 - 200, y0, { steps: 12 }); await frame(page); await page.screenshot({ path: cfg.shots + "-mid.png" }); await page.mouse.up(); await frame(page); await page.screenshot({ path: cfg.shots + "-after.png" }); }
}
await ctxA.close();

// ── (B) the kit ON: a divider between columns and one between rows ───────────────────────────────────────────────────────────
const ctxB = await browser.newContext({ viewport: { width: 1500, height: 900 } });
const pb = await ctxB.newPage();
pb.on("pageerror", (e) => out.errors.push("B: " + String(e).slice(0, 200)));
await pb.addInitScript(() => { try { const s = JSON.parse(localStorage.getItem("romp:settings") || "{}"); s.paneDocking = true; s.showFilesControl = true; localStorage.setItem("romp:settings", JSON.stringify(s)); } catch (e) {} });
await pb.goto(cfg.url);
await pb.waitForFunction(() => !!(window.__rompPaneDock && window.__rompPaneDock.on() && document.querySelectorAll(".pd-div").length >= 1), null, { timeout: 20000 }).catch(async () => { await die("the kit did not come on"); });
await pb.waitForTimeout(800);
await pb.evaluate(() => { window.__rompPaneToggle("fleet", true); window.__rompPaneToggle("files", true); });   // every pane on: the row holds four columns, so dividers between columns survive the dock below
await pb.waitForTimeout(800);
await instrument(pb);
const rectsOf = () => pb.evaluate(() => Object.fromEntries(window.__rompPaneDock.rects().map((r) => [r.pane, r.rect])));
const layoutStr = () => pb.evaluate(() => JSON.stringify(window.__rompPaneDock.layout()));
const divs = () => pb.evaluate(() => Array.from(document.querySelectorAll(".pd-div")).map((d) => { const r = d.getBoundingClientRect(); return { dir: d.getAttribute("data-dir"), x: r.left, y: r.top, w: r.width, h: r.height }; }));
out.kitDivs = await divs();
out.kitGhost = await pb.evaluate(() => !!document.getElementById("pd-ghost"));
const chatFrB = frameOfPath(pb, /\/chat(\?|$)/), tlFrB = frameOfPath(pb, /\/timeline(\?|$)/);
const layoutOf = () => pb.evaluate(() => window.__rompPaneDock.layout());
const storedLayout = () => pb.evaluate(() => { const s = localStorage.getItem("romp-layout"); try { return { raw: s, parsed: JSON.parse(s) }; } catch (e) { return { raw: s, parsed: null, error: String(e) }; } });
const tlOf = () => pb.evaluate(() => document.querySelector(".col").style.getPropertyValue("--tl"));
const cursorOver = (id) => pb.evaluate((i) => { const el = document.getElementById(i); return el ? getComputedStyle(el).cursor : null; }, id);
const kitWrites = async (w0) => ((await writes(pb))["romp-layout"] || 0) - (w0["romp-layout"] || 0);
// the pair at a divider: for a vertical divider (dir row) the leaf ending at its left and the leaf starting at its right; for a
// horizontal one (dir col) the leaf above and the leaf below, at the divider's centre
const pairAt = (d, rs) => { const es = Object.entries(rs); const x0 = d.x + d.w / 2, y0 = d.y + d.h / 2;
  if (d.dir === "row") { const L = es.find(([, r]) => Math.abs(r.x + r.w - d.x) <= 8 && r.y <= y0 && r.y + r.h >= y0), R = es.find(([, r]) => Math.abs(r.x - (d.x + d.w)) <= 8 && r.y <= y0 && r.y + r.h >= y0); return { L: L && L[0], R: R && R[0] }; }
  const T = es.find(([, r]) => Math.abs(r.y + r.h - d.y) <= 8 && r.x <= x0 && r.x + r.w >= x0), B = es.find(([, r]) => Math.abs(r.y - (d.y + d.h)) <= 8 && r.x <= x0 && r.x + r.w >= x0); return { L: T && T[0], R: B && B[0] }; };
// the divider between the chat and the feed (a row-dir divider is vertical, between columns): the leaves on either side by rect
async function dragKit(dir, samples, { escape = false } = {}) {
  const ds = (await divs()).filter((d) => d.dir === dir); if (!ds.length) return { error: "no " + dir + " divider" };
  const d = ds[0]; const before = await rectsOf(); const lay0 = await layoutStr(); const w0 = await writes(pb);
  const x0 = d.x + d.w / 2, y0 = d.y + d.h / 2;
  const p = pairAt(d, before); if (!p.L || !p.R) return { error: "no pair at the divider", div: d, rects: before };
  const cursorBefore = await cursorOver(p.L);   // off a drag: the grab hand
  await pb.mouse.move(x0, y0); await pb.mouse.down(); await frame(pb);
  const rec = { dir, pair: p, before: { L: before[p.L], R: before[p.R] }, points: [], cursorBefore };
  for (const dd of samples) {
    if (dir === "row") await pb.mouse.move(x0 + dd, y0, { steps: 4 }); else await pb.mouse.move(x0, y0 + dd, { steps: 4 });
    await frame(pb);
    const rs = await rectsOf(); const L = rs[p.L], R = rs[p.R];
    rec.points.push({ d: dd, pointer: dir === "row" ? x0 + dd : y0 + dd, L: L, R: R, edge: dir === "row" ? L.x + L.w : L.y + L.h, sum: dir === "row" ? L.w + R.w : L.h + R.h, cursor: await cursorOver(p.L) });
  }
  if (escape) { await pb.keyboard.press("Escape"); await frame(pb); await pb.mouse.up(); await frame(pb); }
  else { await pb.mouse.up(); await frame(pb); }
  const rs = await rectsOf(); const wAfter = await writes(pb);
  rec.after = { L: rs[p.L], R: rs[p.R], writes: (wAfter["romp-layout"] || 0) - (w0["romp-layout"] || 0), layoutRestored: (await layoutStr()) === lay0, cursor: await cursorOver(p.L) };
  return rec;
}
// a move and a release with NO frame between them on a kit divider: the release lands the position itself, one store write
async function sameTaskKit(dir, dd) {
  const d = (await divs()).filter((x) => x.dir === dir)[0]; if (!d) return { error: "no " + dir + " divider", divs: await divs(), rects: await rectsOf(), layout: await layoutOf() };
  const before = await rectsOf(); const p = pairAt(d, before); if (!p.L || !p.R) return { error: "no pair", div: d, rects: before }; const w0 = await writes(pb);
  const x0 = d.x + d.w / 2, y0 = d.y + d.h / 2;
  await pb.mouse.move(x0, y0); await pb.mouse.down(); await frame(pb);
  if (dir === "row") await pb.mouse.move(x0 + dd, y0); else await pb.mouse.move(x0, y0 + dd);
  await pb.mouse.up(); await frame(pb); await frame(pb);
  const rs = await rectsOf();
  return { dir, dd, pair: p, before: before[p.L], after: rs[p.L], writes: await kitWrites(w0) };
}
// a pane toggled UNDER a kit drag (the rail's toggle: a leaf gone or a leaf new): the drag ends at its last position, committed;
// the store parses and matches the screen; a release or an Escape after it changes nothing; the pane put back after
async function toggleMidDrag(dir, dd, paneKey, { escape = false, show = false } = {}) {
  if (show) { await pb.evaluate((k) => window.__rompPaneToggle(k, false), paneKey); await frame(pb); await frame(pb); }
  const d = (await divs()).filter((x) => x.dir === dir)[0]; if (!d) return { error: "no " + dir + " divider", divs: await divs(), rects: await rectsOf(), layout: await layoutOf() };
  const before = await rectsOf(); const p = pairAt(d, before); if (!p.L || !p.R) return { error: "no pair", div: d, rects: before }; const w0 = await writes(pb);
  const x0 = d.x + d.w / 2, y0 = d.y + d.h / 2;
  await pb.mouse.move(x0, y0); await pb.mouse.down(); await frame(pb);
  await pb.mouse.move(x0 + dd, y0, { steps: 4 }); await frame(pb); await frame(pb);
  const mid = { rects: await rectsOf(), writes: await kitWrites(w0) };
  await pb.evaluate(({ k, on }) => window.__rompPaneToggle(k, on), { k: paneKey, on: show });
  await frame(pb); await frame(pb);
  const afterToggle = { rects: await rectsOf(), layout: await layoutOf(), stored: await storedLayout(), writes: await kitWrites(w0), pressed: await pb.evaluate(() => document.body.classList.contains("pd-resize")) };
  await pb.mouse.move(x0 + dd - 40, y0, { steps: 2 }); await frame(pb); await frame(pb);   // more travel under the held pointer: the drag is over
  const afterMore = { rects: await rectsOf(), writes: await kitWrites(w0) };
  if (escape) { await pb.keyboard.press("Escape"); await frame(pb); }
  await pb.mouse.up(); await frame(pb); await frame(pb);
  const afterUp = { rects: await rectsOf(), layout: await layoutOf(), stored: await storedLayout(), writes: await kitWrites(w0) };
  await pb.evaluate(({ k, on }) => window.__rompPaneToggle(k, on), { k: paneKey, on: !show }); await frame(pb); await frame(pb);   // the pane back as it was
  return { dir, dd, paneKey, show, escape, pair: p, before, mid, afterToggle, afterMore, afterUp, restored: { rects: await rectsOf(), layout: await layoutOf() } };
}
// the band RE-SIZED under a column drag (the shell's autosize follows the band's content, with no gesture on the band): the
// drag's next frames keep the new height, the release or Escape keeps it, the store gets it once
async function bandGrowMidDrag({ escape = false, dir = "row", far = false } = {}) {
  const d = (await divs()).filter((x) => x.dir === dir)[0]; if (!d) return { error: "no " + dir + " divider", divs: await divs(), rects: await rectsOf() };
  const before = await rectsOf(); const p = pairAt(d, before); if (!p.L || !p.R) return { error: "no pair", div: d, rects: before }; const w0 = await writes(pb);
  const x0 = d.x + d.w / 2, y0 = d.y + d.h / 2;
  const mv = async (dd, steps = 4) => { if (dir === "row") await pb.mouse.move(x0 + dd, y0, { steps }); else await pb.mouse.move(x0, y0 + dd, { steps }); };
  const edgeOf = (rs) => (dir === "row" ? rs[p.L].x + rs[p.L].w : rs[p.L].y + rs[p.L].h);
  const tl0 = await tlOf(); const band0 = (await rect(pb, "#tl-pane")).h;
  await pb.mouse.move(x0, y0); await pb.mouse.down(); await frame(pb);
  await mv(-60); await frame(pb); await frame(pb);
  const mid = { rects: await rectsOf(), tl: await tlOf(), edge: edgeOf(await rectsOf()), pointer: (dir === "row" ? x0 : y0) - 60 };
  // the tracer BEFORE the growth (the sixth review: a tracer registered by a second round trip after the growth could start after the
  // reconcile's armed frame had already corrected the edge, and pass on the very defect it was cut for): registered on the page and
  // left running, it samples the pair's edge from the DOM and the height variable on EVERY animation frame until told to stop, so its
  // first frame precedes the growth and no frame between is missed (the fifth review: a frame armed by the reconcile landed one paint
  // late, so the pre-growth ratios painted for one frame)
  await pb.evaluate(({ L, isRow }) => { const w = window; w.__labTrace = []; w.__labTraceOn = true;
    const step = () => { const el = document.getElementById(L); const r = el.getBoundingClientRect(); w.__labTrace.push({ edge: isRow ? r.right : r.bottom, tl: document.querySelector(".col").style.getPropertyValue("--tl") }); if (w.__labTraceOn) requestAnimationFrame(step); };
    requestAnimationFrame(step); }, { L: p.L, isRow: dir === "row" });
  await tlFrB.evaluate(() => { const g = document.createElement("div"); g.id = "lab-grow"; g.style.height = "150px"; document.body.appendChild(g); });
  await pb.waitForFunction((t) => document.querySelector(".col").style.getPropertyValue("--tl") !== t, tl0, { timeout: 5000 }).catch(() => {});
  await frame(pb); await frame(pb);
  const trace = await pb.evaluate(() => { window.__labTraceOn = false; return window.__labTrace.slice(); });
  const grown = { trace, tl: await tlOf(), band: (await rect(pb, "#tl-pane")).h, rects: await rectsOf(), edge: edgeOf(await rectsOf()), pointer: (dir === "row" ? x0 : y0) - 60, writes: await kitWrites(w0) };   // no move since the growth: the edge re-applied against the re-read geometry
  await mv(-100); await frame(pb); await frame(pb);   // another frame of the drag
  const later = { tl: await tlOf(), band: (await rect(pb, "#tl-pane")).h, rects: await rectsOf(), edge: edgeOf(await rectsOf()), pointer: (dir === "row" ? x0 : y0) - 100, writes: await kitWrites(w0) };
  let farPoint = null;
  if (far) { await mv(900, 6); await frame(pb); await frame(pb); const rs = await rectsOf(); farPoint = { rects: rs, edge: edgeOf(rs), pointer: (dir === "row" ? x0 : y0) + 900 }; }
  if (escape) { await pb.keyboard.press("Escape"); await frame(pb); }
  await pb.mouse.up(); await frame(pb); await frame(pb);
  const after = { tl: await tlOf(), band: (await rect(pb, "#tl-pane")).h, rects: await rectsOf(), edge: edgeOf(await rectsOf()), stored: await storedLayout(), writes: await kitWrites(w0), farPoint };
  await tlFrB.evaluate(() => { const g = document.getElementById("lab-grow"); if (g) g.remove(); });
  await pb.waitForFunction((t) => document.querySelector(".col").style.getPropertyValue("--tl") === t, tl0, { timeout: 5000 }).catch(() => {});
  await frame(pb); await frame(pb);
  return { escape, dir, far, pair: p, tl0, band0, mid, grown, later, after, back: { tl: await tlOf(), band: (await rect(pb, "#tl-pane")).h } };
}
// the kit's BAND edge (the col-dir divider whose bottom meets the band's top): the band's height follows the pointer's distance
// from its bottom, live per frame; the store is written once at release, never per frame, and nothing on Escape
async function dragBandKit(dys, { escape = false } = {}) {
  const band = await rect(pb, "#tl-pane"); if (!band) return { error: "no band" };
  const ds = (await divs()).filter((d) => d.dir === "col" && Math.abs(d.y + d.h - band.y) <= 8); if (!ds.length) return { error: "no band divider", divs: await divs(), band };
  const d = ds[0]; const x0 = d.x + d.w / 2, y0 = d.y + d.h / 2; const w0 = await writes(pb);
  const tl0 = await tlOf();
  await pb.mouse.move(x0, y0); await pb.mouse.down(); await frame(pb);
  const rec = { tl0, band0: band.h, bottom: band.bottom, points: [], cursor: await cursorOver("chat-pane") };
  for (const dy of dys) {
    await pb.mouse.move(x0, y0 + dy, { steps: 4 }); await frame(pb); await frame(pb);
    rec.points.push({ dy, pointerY: y0 + dy, wanted: band.bottom - (y0 + dy), tl: await tlOf(), band: (await rect(pb, "#tl-pane")).h, writes: await kitWrites(w0) });
  }
  if (escape) { await pb.keyboard.press("Escape"); await frame(pb); await pb.mouse.up(); await frame(pb); await frame(pb); }
  else { await pb.mouse.up(); await frame(pb); await frame(pb); }
  rec.after = { tl: await tlOf(), band: (await rect(pb, "#tl-pane")).h, writes: await kitWrites(w0), stored: await storedLayout(), cursor: await cursorOver("chat-pane") };
  return rec;
}
out.kitRow = await dragKit("row", [-100, -50, 70]);
out.kitRowEscape = await dragKit("row", [-80, 60], { escape: true });
out.kitRowFar = await dragKit("row", [1200, -1200], { escape: true });   // past the clamp both ways: the right pane, then the left, at the minimum
// a divider between rows: dock the feed into the chat's bottom half by its ring (the docking kit's own drag), then drag that divider
{
  const rs = await rectsOf(); const feed = rs["feed-pane"], chat = rs["chat-pane"];
  if (feed && chat) {
    await pb.mouse.move(feed.x + 3, feed.y + feed.h / 2); await pb.mouse.down(); await frame(pb);
    await pb.mouse.move(feed.x + 20, feed.y + feed.h / 2 + 20, { steps: 3 }); await frame(pb);
    await pb.mouse.move(chat.x + chat.w / 2, chat.y + chat.h * 0.85, { steps: 10 }); await frame(pb);
    await pb.mouse.up(); await frame(pb); await pb.waitForTimeout(400);
  }
  out.kitDivsAfterDock = await divs();
}
out.kitCol = await dragKit("col", [-60, 40, -20]);
out.kitColEscape = await dragKit("col", [50, -40], { escape: true });
out.kitColFar = await dragKit("col", [900, -900], { escape: true });
// the new legs: the same-task release, Escape from the chat's composer (the kit's keydown wiring on the pane document), a pane
// hidden and one shown under the drag (a release and an Escape each), the band grown under a column drag, the band's own edge
out.kitSameTask = await sameTaskKit("row", 60);
out.kitComposerFocus = chatFrB ? await focusComposer(chatFrB) : null;
out.kitTopActive = await pb.evaluate(() => document.activeElement && document.activeElement.id);
out.kitEscapeFromPane = await dragKit("row", [-70, 50], { escape: true });
out.kitKeyboardBack = await keyboardBack(pb);
out.kitToggleHideRelease = await toggleMidDrag("row", -60, "files");
out.kitToggleHideEscape = await toggleMidDrag("row", -60, "files", { escape: true });
out.kitToggleShowRelease = await toggleMidDrag("row", -60, "files", { show: true });
out.kitBandGrowRelease = tlFrB ? await bandGrowMidDrag() : { error: "no timeline frame" };
out.kitBandGrowEscape = tlFrB ? await bandGrowMidDrag({ escape: true }) : { error: "no timeline frame" };
// the divider between STACKED panes (the chat over the docked feed, under the band's split): the band's growth moves its avail, its rect
// and the pair, so the drag's edge must be re-read (round four): the edge at the pointer with no move, the far drag at the minimum
out.kitBandGrowStacked = tlFrB ? await bandGrowMidDrag({ dir: "col", far: true }) : { error: "no timeline frame" };
out.kitBand = await dragBandKit([-40, -20, 30]);
out.kitBandEscape = await dragBandKit([-30, 20], { escape: true });
// a reload restores the persisted layout: the rects before and after, and the stored string against the layout after
{
  const before = await rectsOf(); const storedBefore = await storedLayout();
  await pb.reload();
  await pb.waitForFunction(() => !!(window.__rompPaneDock && window.__rompPaneDock.on() && document.querySelectorAll(".pd-div").length >= 1), null, { timeout: 20000 }).catch(() => {});
  await pb.waitForTimeout(800); await frame(pb); await frame(pb);
  out.kitReload = { before, after: await rectsOf(), storedBefore: storedBefore.raw, layoutAfter: await layoutOf(), storedAfter: (await storedLayout()).raw };
}
await ctxB.close();
fs.writeSync(1, "RESULT:" + JSON.stringify(out) + "\n");
await browser.close();
process.exit(0);
"""


def _leaves(node):
    return [p for k in node["kids"] for p in _leaves(k)] if "kids" in node else [node["pane"]]


def _split_holding(node, a, b):
    """The split whose direct kids hold leaves `a` and `b` in adjacent positions (the dragged pair's split), or None."""
    if "kids" not in node:
        return None
    ls = [_leaves(k) for k in node["kids"]]
    for i in range(len(ls) - 1):
        if a in ls[i] and b in ls[i + 1] and len(ls[i]) == 1 and len(ls[i + 1]) == 1:
            return node
    for k in node["kids"]:
        r = _split_holding(k, a, b)
        if r is not None:
            return r
    return None


def _fixed_px(node, pane):
    if "kids" not in node:
        return None
    for i, k in enumerate(node["kids"]):
        if "kids" not in k and k.get("pane") == pane:
            return (node.get("fixed") or [None] * len(node["kids"]))[i]
    for k in node["kids"]:
        v = _fixed_px(k, pane)
        if v is not None:
            return v
    return None


def _px(tl):
    return float(str(tl).replace("px", "") or 0)


def _overlaps(rects):
    out, items = [], sorted(rects.items())
    for i, (a, ra) in enumerate(items):
        for b, rb in items[i + 1:]:
            if ra["x"] < rb["x"] + rb["w"] - 1 and rb["x"] < ra["x"] + ra["w"] - 1 and ra["y"] < rb["y"] + rb["h"] - 1 and rb["y"] < ra["y"] + ra["h"] - 1:
                out.append((a, b))
    return out


class ServedLiveDividers(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(os.path.join(EXT, "node_modules", "playwright")):
            if REQUIRE:
                raise AssertionError("ROMP_SERVED_TESTS_REQUIRE=1 but the extension deps are absent")
            raise unittest.SkipTest("extension deps absent (npm ci not run here): the served leg needs them")
        cls.lab = tempfile.mkdtemp(prefix="live-dividers-")
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
        for sid, name in ((TOP, "web"), (BOT, "api")):
            Path(state, "names", sid).write_text("%s\t%s\t\t\n" % (name, cwd))
            Path(state, "sdk", sid + ".json").write_text(json.dumps({"sid": sid, "name": name, "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": sid, "alive": True}))
        Path(state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 100}, "seven_day": {"pct": 10}}))   # park sends
        claude = os.path.join(cls.lab, "claude")
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        Path(proj, TOP + ".jsonl").write_text(_transcript(TOP, cwd, 40, "a"))   # long: the chat's relayout is the cost the design measures
        Path(proj, BOT + ".jsonl").write_text(_transcript(BOT, cwd, 6, "b"))
        cls.port = _free_port()
        cls.token = "testtok-livedividers"
        cls.env = _lab.kernel_env(cls.lab, claude, dist, cls.port, cls.token)
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
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

    def _drive(self):
        cfg = os.path.join(self.lab, "cfg.json")
        with open(cfg, "w") as f:
            json.dump({"url": "http://127.0.0.1:%d/?token=%s" % (self.port, self.token), "bot": BOT, "shots": os.environ.get("ROMP_LAB_SHOT") or ""}, f)
        driver = os.path.join(self.lab, "driver.mjs")
        with open(driver, "w") as f:
            f.write(DRIVER)
        try:
            p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=300, env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
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
        self.assertNotIn("died", r, "driver aborted early: %r" % {k: r[k] for k in ("died", "errors") if k in r})
        print("LIVE-DIVIDERS COST:", json.dumps(r.get("cost")), file=sys.stderr)
        summary = os.environ.get("GITHUB_STEP_SUMMARY")   # CI's job summary shows a passing test's numbers; pytest's capture hides the print
        if summary:
            with open(summary, "a") as f:
                f.write("LIVE-DIVIDERS COST: %s\n\n" % json.dumps(r.get("cost")))
        return r

    def _within(self, a, b, tol, msg):
        self.assertLessEqual(abs(a - b), tol, "%s: %r vs %r" % (msg, a, b))

    _res = None

    def _result(self):
        # one drive per class (the driver runs every leg in one browser session); a driver failure or a skip is cached and
        # re-raised by every test, so the record is measured once and each leg's verdict stands on its own
        cls = type(self)
        if cls._res is None:
            try:
                cls._res = ("ok", self._drive())
            except Exception as e:   # a failure, a skip, a launch error: each cached and re-raised by every test
                cls._res = ("err", e)
        kind, val = cls._res
        if kind == "err":
            raise val
        return val

    def test_the_shipped_dividers_resize_live_persist_once_restore_on_escape_keep_the_panes_content_and_the_cost_is_measured(self):
        # the shipped column gutter, the band's height divider, the chat's vertical split (kit off), the probes, the cost
        r = self._result()
        self.assertEqual(r["errors"], [], "no page error")
        self.assertEqual(r["panesOn"], ["po-chat", "po-feed", "po-files", "po-fleet", "po-timeline"], "every pane on for the drags")
        # (1) the shipped column gutter: mid-drag the left pane's right edge follows the pointer (less the gutter's half), the pair's sum holds
        g = r["gutter"]
        self.assertNotIn("error", g, g)
        for pt in g["points"]:
            self._within(pt["L"]["right"] + 3.5, pt["pointerX"], 1.5, "mid-drag the divider (the left pane's right edge plus half the 7 px gutter) sits at the pointer")
            self._within(pt["sum"], g["points"][0]["sum"], 1.5, "the pair trades width, the sum holds")
            self.assertEqual(pt["ghost"], "absent", "no provisional line")
        self._within(g["after"]["L"]["w"], g["points"][-1]["L"]["w"], 1.0, "the release changes nothing on screen: what was seen is what was got")
        self.assertEqual(g["after"]["writes"], 1, "the grow store is written once, at release: %r" % g["after"]["allWrites"])
        e = r["gutterEscape"]
        self.assertGreater(abs(e["points"][0]["L"]["w"] - e["before"]["L"]["w"]), 20, "the drag moved the pair before Escape")
        self._within(e["after"]["L"]["w"], e["before"]["L"]["w"], 1.0, "Escape restores the pre-drag widths live")
        self.assertEqual(e["after"]["writes"], 0, "and writes nothing"); self._within(e["afterUp"]["L"]["w"], e["before"]["L"]["w"], 1.0, "the release after Escape changes nothing")
        self.assertEqual(r["probesAfterGutter"], {"chat": True, "feed": True}, "the iframes keep their content: no reload")
        # (2) the band's height divider: the band's height is the pointer's distance from the column's bottom, live; nothing persisted
        b = r["band"]
        self.assertNotIn("error", b, b)
        tls = [float(str(pt["tl"]).replace("px", "") or 0) for pt in b["points"]]
        for pt, tl in zip(b["points"], tls):
            self._within(tl, pt["wanted"], 4.0, "mid-drag the band's --tl is the pointer's distance from the column's bottom, within the 7 px gutter's half")
            self._within(pt["bandH"], tl, 1.0, "and the band's element is that height")
        for pt, tl in list(zip(b["points"], tls))[1:]:
            self._within(tl - tls[0], -(pt["dy"] - b["points"][0]["dy"]), 1.0, "the band follows the pointer's travel exactly: a pixel moved is a pixel of height")
        self._within(b["after"]["bandH"], b["points"][-1]["bandH"], 1.5, "the release changes nothing on screen")
        self.assertEqual([k for k in b["after"]["writes"] if k in ("romp-pane-grow", "romp-layout", "romp-chat-cols")], [], "the band's height persists nothing, as before (no pane store written)")
        be = r["bandEscape"]
        self._within(be["after"]["bandH"], be["band0"]["h"], 1.5, "Escape restores the band's height")
        # (3) the chat's vertical split: the top frame's bottom follows the pointer, the ratio is written once at release
        v = r["vsplit"]
        self.assertNotIn("error", v, v)
        for pt in v["points"]:
            self._within(pt["T"]["bottom"] + 3.5, pt["pointerY"], 1.5, "mid-drag the split's divider sits at the pointer")
            self._within(pt["sum"], v["points"][0]["sum"], 1.5, "the two halves trade height")
        self._within(v["after"]["T"]["h"], v["points"][-1]["T"]["h"], 1.0, "the release changes nothing on screen")
        self.assertEqual(v["after"]["writes"], 1, "romp-chat-cols is written once, at release")
        ve = r["vsplitEscape"]
        self._within(ve["after"]["T"]["h"], ve["before"]["T"]["h"], 1.0, "Escape restores the split's heights: %r" % {"before": ve["before"], "after": ve["after"], "points": ve["points"]})
        self.assertEqual(ve["after"]["writes"], 0)
        self.assertEqual(r["probesAfterAll"], {"chat": True, "feed": True}, "the iframes keep their content through every drag")
        # (5) the cost, measured and BOUNDED on the page's own work per frame, as a COUNT: how many of the animation-frame callbacks
        # the shell ran over the drag took longer than 40 ms (the verifier's read: a frame-rate pin is wall-clock and reds under a
        # half-core quota with nothing wrong; the layout count over CDP rises under load too, since a starved CPU stretches the drag
        # over more frames; and a cgroup quota can throttle the process inside ONE callback, so the longest callback alone is not
        # load-independent either: 74 ms once in two loaded runs). An 80 ms busy loop in the gutter's apply() makes EVERY applied
        # frame's callback long; a starved CPU makes at most a few. The frame rate, the long-frame count, the layout and style-recalc
        # counts and the longest callback are reported beside it, present but not pinned
        c = r["cost"]
        self.assertGreater(c["frames"], 10, "frames were sampled during the drag: %r" % c)
        self.assertGreater(c["cbCount"], 10, "the shell's frame callbacks were timed: %r" % c)
        self.assertIsNotNone(c["fps"]); self.assertIsNotNone(c["loaf"]); self.assertIsNotNone(c["cbMaxMs"])
        self.assertIsNotNone(c["layouts"], "the shell's layouts over the drag were counted (CDP Performance metrics): %r" % c)
        self.assertLessEqual(c["cbLong"], 10, "at most ten of the shell's animation-frame callbacks over the drag run longer than 40 ms (a busy frame in the gutter's apply makes every one long; a starved CPU a few): %r" % c)

    def test_escape_from_a_keyboard_inside_a_pane_and_a_release_with_no_frame_between_on_the_shipped_gutter(self):
        # the drag listens on every same-origin pane document (dragKeys): with the chat's composer focused the top document's
        # active element is the chat frame and the pane hears the Escape; the release with no frame between it and the move lands
        # the position itself and writes the store once (the same-frame case of tests/test_pane_gutter_drag.py, on the real page)
        r = self._result()
        self.assertEqual(r["composerFocus"]["tag"], "TEXTAREA", "the keyboard is in the chat's composer: %r" % r["composerFocus"])
        self.assertEqual(r["topActiveDuringComposer"], "f-chat", "the top document's active element is the chat frame")
        e = r["gutterEscapeComposer"]
        self.assertNotIn("error", e, e)
        self.assertGreater(abs(e["points"][0]["L"]["w"] - e["before"]["L"]["w"]), 20, "the drag moved the pair before Escape")
        self._within(e["after"]["L"]["w"], e["before"]["L"]["w"], 1.0, "Escape from the composer restores the pre-drag widths: %r" % e["after"])
        self.assertEqual(e["after"]["writes"], 0, "and writes nothing")
        self.assertEqual(r["keyboardBack"], "BODY", "the keyboard handed back to the shell for the legs after")
        st = r["gutterSameTask"]
        self._within(st["after"], st["before"] + st["dx"], 1.5, "a release with no frame between lands the position under the pointer: %r" % st)
        self.assertEqual(st["writes"], 1, "one store write: %r" % st)

    def test_the_chats_reader_survives_the_reflow_at_the_bottom_and_scrolled_up(self):
        # the chat's reader through a narrowing drag on the chat | Outline gutter: at the true bottom, and scrolled up
        r = self._result()
        # (1b) the chat's reader through a narrowing drag (the 1927 read: the transcript wraps longer, the view grows, and the browser
        # keeps scrollTop, so a reader at the true bottom was left above it): the reflow rule (followReflow, scroll-keep.ts) keeps
        # them at the bottom at every sample; a scrolled-up reader keeps the line they read where it was on screen (the browser's
        # scroll anchoring holds their turn, the chat's strip compensation holds it when the tab strip wraps to another row)
        rb = r["readerBottom"]
        self.assertLessEqual(rb["before"]["dist"], 2, "the reader starts at the true bottom: %r" % rb["before"])
        self.assertGreater(rb["points"][-1]["reader"]["sh"], rb["before"]["sh"] + 40, "the narrowing drag grew the view (the lines wrapped longer): %r" % [pt["reader"]["sh"] for pt in rb["points"]])
        widths = [pt["chatW"] for pt in rb["points"]]
        self.assertEqual(widths, sorted(widths, reverse=True), "each sample narrows the chat further: %r" % widths)
        self.assertLess(widths[0], rb["chatW0"] - 100, "the first sample already 120 px narrower than before the press")
        for pt in rb["points"]:
            self.assertLessEqual(pt["reader"]["dist"], 2, "mid-drag, at %d px, the bottom reader is within 2 px of the bottom: %r" % (pt["dx"], pt["reader"]))
        self.assertLessEqual(rb["after"]["dist"], 2, "and after Escape's restore")
        ru = r["readerUp"]
        self.assertIsNotNone(ru["before"]["anchor"], "the anchor turn was found")
        self.assertGreater(ru["before"]["dist"], 200, "the reader is scrolled up: %r" % ru["before"])
        self.assertGreater(ru["before"]["top"], 300, "with a screen or more of transcript above them to re-wrap: %r" % ru["before"])
        for pt in ru["points"]:
            self.assertIsNotNone(pt["reader"]["screen"], "the anchor turn is on the page mid-drag")
            self._within(pt["reader"]["screen"], ru["before"]["screen"], 1.0, "a scrolled-up reader keeps the line they read where it was on screen, within a pixel, at %d px: %r" % (pt["dx"], ru))
        self._within(ru["after"]["screen"], ru["before"]["screen"], 1.0, "and after Escape's restore")
        # the writes the chat made to their position are its strip compensation only (the tab strip wrapping to another row moves
        # the scroller down by that row, and the chat scrolls by the same amount so the line stays put on screen); the transcript
        # re-wrapping above them is the browser's scroll anchoring, no write
        moved = sum(w["to"] - w["from"] for pt in ru["points"] for w in pt["reader"]["writes"])
        self._within(moved, ru["points"][-1]["reader"]["ctop"] - ru["before"]["ctop"], 1.5, "every write the chat made to a scrolled-up reader's position is its strip compensation: the sum is the scroller's own move down the page")

    def test_the_kits_dividers_between_columns_and_rows_resize_live_persist_once_and_restore_on_escape(self):
        # the docking kit on: no landing line; the divider between columns and, after docking the feed under the chat, between rows
        r = self._result()
        # (4) the docking kit: no ghost element; the divider between columns and the one between rows resize their pair live
        self.assertFalse(r["kitGhost"], "the kit's landing line is gone")
        k = r["kitRow"]
        self.assertNotIn("error", k, k)
        for pt in k["points"]:
            self._within(pt["edge"] + 3.5, pt["pointer"], 1.5, "mid-drag the kit's column divider sits at the pointer")
            self._within(pt["sum"], k["points"][0]["sum"], 1.5, "the pair trades width")
        self.assertEqual(k["after"]["writes"], 1, "romp-layout is written once, at release")
        ke = r["kitRowEscape"]
        self.assertTrue(ke["after"]["layoutRestored"], "Escape restores the pre-drag layout: %r" % ke["after"])
        self.assertEqual(ke["after"]["writes"], 0)
        kc = r["kitCol"]
        self.assertNotIn("error", kc, "a divider between rows after docking the feed under the chat: %r" % {k2: kc.get(k2) for k2 in ("error", "div")})
        for pt in kc["points"]:
            self._within(pt["edge"] + 3.5, pt["pointer"], 1.5, "mid-drag the kit's row divider sits at the pointer")
            self._within(pt["sum"], kc["points"][0]["sum"], 1.5, "the pair trades height")
        self.assertEqual(kc["after"]["writes"], 1)
        self.assertTrue(r["kitColEscape"]["after"]["layoutRestored"])

    def test_the_kits_divider_keeps_its_cursor_over_the_panes_escape_from_a_pane_document_restores_and_a_frameless_release_lands(self):
        r = self._result()
        k = r["kitRow"]
        self.assertEqual(k["cursorBefore"], "grab", "off a drag the pane's cursor is the grab hand")
        for pt in k["points"]:
            self.assertEqual(pt["cursor"], "col-resize", "mid-drag on a divider between columns the pane under the pointer shows col-resize: %r" % pt["cursor"])
        self.assertEqual(k["after"]["cursor"], "grab", "and the hand comes back at the release")
        kc = r["kitCol"]
        for pt in kc["points"]:
            self.assertEqual(pt["cursor"], "row-resize", "between rows, row-resize")
        st = r["kitSameTask"]
        self._within(st["after"]["w"], st["before"]["w"] + st["dd"], 1.5, "a release with no frame between lands the position: %r" % st)
        self.assertEqual(st["writes"], 1, "one store write")
        self.assertEqual((r["kitComposerFocus"] or {}).get("tag"), "TEXTAREA", "the keyboard in the kit page's chat composer")
        self.assertEqual(r["kitTopActive"], "f-chat")
        ke = r["kitEscapeFromPane"]
        self.assertNotIn("error", ke, ke)
        self.assertTrue(ke["after"]["layoutRestored"], "Escape heard by the kit's keydown wiring on the pane document restores the layout: %r" % ke["after"])
        self.assertEqual(ke["after"]["writes"], 0)
        self.assertEqual(r["kitKeyboardBack"], "BODY")

    def test_a_pane_toggled_under_a_kit_drag_ends_the_drag_committed_and_the_store_parses_and_matches_the_screen(self):
        r = self._result()
        for name in ("kitToggleHideRelease", "kitToggleHideEscape", "kitToggleShowRelease"):
            t = r[name]
            self.assertNotIn("error", t, t)
            at = t["afterToggle"]
            self.assertIsNotNone(at["stored"]["parsed"], "%s: the store parses after the toggle: %r" % (name, at["stored"]))
            on_screen = sorted(at["rects"].keys()); in_store = sorted(_leaves(at["stored"]["parsed"]["tree"])); in_layout = sorted(_leaves(at["layout"]["tree"]))
            self.assertEqual(in_store, on_screen, "%s: the store's leaves are the panes on screen" % name)
            self.assertEqual(in_layout, on_screen)
            self.assertEqual("files-pane" in on_screen, t["show"], "%s: the toggled pane is %s" % (name, "shown" if t["show"] else "gone"))
            self.assertEqual(_overlaps(at["rects"]), [], "%s: no two panes overlap after the toggle" % name)
            self.assertNotIn("files-pane", at["stored"]["parsed"].get("parked", []) if t["show"] else [], "a shown pane is not parked")
            if not t["show"]:
                self.assertIn("files-pane", at["stored"]["parsed"].get("parked", []), "a hidden pane is parked, once")
            self.assertFalse(at["pressed"], "%s: the drag ended at the toggle (new information under the held pointer)" % name)
            self.assertEqual(at["writes"], 1, "%s: ONE store write at the toggle: the drag lands without writing and the reconcile writes the corrected layout (round four: the commit's write of the press-tree layout was a second, stale write): %r" % (name, at["writes"]))
            # the drag's last position landed: a pane HIDDEN gives its room to every remaining kid in proportion, so the dragged pair keeps
            # its SHARE; a pane SHOWN docks at the right end and splits the last leaf's share in half (splitAt), so the dragged pair's
            # left pane keeps its width less its part of the one new gutter
            L, R = t["pair"]["L"], t["pair"]["R"]
            if t["show"]:
                self._within(at["rects"][L]["w"], t["mid"]["rects"][L]["w"], 8.0, "%s: the drag's last position landed (the left pane's width, less the new gutter's share): mid %r after %r" % (name, t["mid"]["rects"], at["rects"]))
            else:
                share = lambda rs: rs[L]["w"] / (rs[L]["w"] + rs[R]["w"])
                self._within(share(at["rects"]), share(t["mid"]["rects"]), 0.01, "%s: the drag's last position landed (the pair's share held through the close): mid %r after %r" % (name, t["mid"]["rects"], at["rects"]))
            self.assertEqual(t["afterMore"]["rects"], at["rects"], "%s: more travel under the held pointer moves nothing" % name)
            self.assertEqual(t["afterUp"]["rects"], at["rects"], "%s: the release (or Escape) after changes nothing" % name)
            self.assertEqual(t["afterUp"]["writes"], 1, "%s: and writes nothing more" % name)
            self.assertEqual(t["afterUp"]["stored"]["raw"], at["stored"]["raw"])
            self.assertEqual(sorted(t["restored"]["rects"].keys()), sorted(t["before"].keys()), "%s: the pane put back" % name)
        # a reload restores the persisted layout: the same panes, the columns at their widths (the band's height is content-sized by the
        # shell's autosize at boot, so a band left at a dragged height comes back at its content's, and the rows above follow it)
        rl = r["kitReload"]
        self.assertEqual(sorted(rl["after"].keys()), sorted(rl["before"].keys()), "a reload shows the same panes: %r" % rl)
        for k2, v in rl["before"].items():
            for side in ("x", "w"):
                self._within(rl["after"][k2][side], v[side], 1.5, "a reload restores %s's %s" % (k2, side))
        self.assertEqual(sorted(_leaves(rl["layoutAfter"]["tree"])), sorted(_leaves(json.loads(rl["storedBefore"])["tree"])), "the layout after the reload holds the leaves the store held before it")

    def test_the_band_resized_under_a_column_drag_keeps_its_height_through_the_drag_and_reaches_the_store_once(self):
        r = self._result()
        for name in ("kitBandGrowRelease", "kitBandGrowEscape"):
            b = r[name]
            self.assertNotIn("error", b, b)
            self.assertNotEqual(b["grown"]["tl"], b["tl0"], "%s: the shell's autosize wrote the band's height under the drag: %r" % (name, b["grown"]["tl"]))
            grown_px = _px(b["grown"]["tl"])
            self._within(b["grown"]["band"], grown_px, 1.5, "%s: the band shows the new height mid-drag" % name)
            self._within(b["later"]["band"], grown_px, 1.5, "%s: the drag's next frame keeps it (the press tree carried the px): %r" % (name, b["later"]))
            L = b["pair"]["L"]
            self._within(b["later"]["rects"][L]["x"] + b["later"]["rects"][L]["w"] + 3.5, b["later"]["pointer"], 1.5, "%s: and the edge is still at the pointer" % name)
            self.assertEqual(b["grown"]["writes"], 0, "%s: no store write from the reconcile under the drag" % name)
            self._within(b["after"]["band"], grown_px, 1.5, "%s: the release or Escape keeps the band's height (the drag never touched it)" % name)
            self.assertEqual(b["after"]["tl"], b["grown"]["tl"], "%s: the height variable untouched" % name)
            self.assertEqual(b["after"]["writes"], 1, "%s: one store write, at the end: %r" % (name, b["after"]["writes"]))
            self._within(_fixed_px(b["after"]["stored"]["parsed"]["tree"], "tl-pane"), grown_px, 1.5, "%s: the store carries the new band px" % name)
            self._within(b["back"]["band"], b["band0"], 1.5, "%s: the content shrunk back, the band follows" % name)

    def test_a_divider_between_stacked_panes_under_the_band_re_reads_its_edge_when_the_band_grows(self):
        # round four: the reconcile's carry left the drag's avail, rect, pair sizes and press origin as recorded at the press, so under
        # the band's split a divider between stacked panes clamped, resized and persisted against a geometry that was gone (the edge 87 px
        # behind the pointer with no move, the far drag leaving the bottom pane at 96 px under the 120 minimum, the store holding it)
        r = self._result()
        b = r["kitBandGrowStacked"]
        self.assertNotIn("error", b, b)
        self.assertEqual(b["dir"], "col")
        self.assertNotEqual(b["grown"]["tl"], b["tl0"], "the band grew under the drag: %r" % b["grown"]["tl"])
        self._within(b["mid"]["edge"] + 3.5, b["mid"]["pointer"], 1.5, "before the growth the edge sits at the pointer")
        self._within(b["grown"]["edge"] + 3.5, b["grown"]["pointer"], 1.5, "after the growth, with NO move, the edge is back at the pointer (the re-read geometry re-applied): %r" % {k: b["grown"][k] for k in ("edge", "pointer", "tl")})
        self.assertGreaterEqual(len(b["grown"]["trace"]), 3, "the edge traced on every animation frame around the growth")
        self.assertEqual(b["grown"]["trace"][0]["tl"], b["tl0"], "the trace begins BEFORE the growth (the sixth review: a tracer that starts after the reconcile's frame sees only corrected frames): %r" % b["grown"]["trace"])
        self.assertTrue(any(t["tl"] != b["tl0"] for t in b["grown"]["trace"]), "and spans the band's growth: %r" % b["grown"]["trace"])
        for k, t in enumerate(b["grown"]["trace"]):
            self._within(t["edge"] + 3.5, b["grown"]["pointer"], 1.5, "frame %d of the trace: the edge never leaves the pointer, not for one painted frame (the fifth review: 64 px off for a frame): %r" % (k, b["grown"]["trace"]))
        self._within(b["later"]["edge"] + 3.5, b["later"]["pointer"], 1.5, "and follows the next move: %r" % {k: b["later"][k] for k in ("edge", "pointer")})
        fp = b["after"]["farPoint"]
        self.assertIsNotNone(fp)
        R = b["pair"]["R"]
        self._within(fp["rects"][R]["h"], 120.0, 1.5, "the far drag stops with the bottom pane at the real minimum, 120 px (the stale press values left it at 96): %r" % fp["rects"][R])
        self._within(b["after"]["rects"][R]["h"], 120.0, 1.5, "the release keeps it")
        tree = b["after"]["stored"]["parsed"]["tree"]
        L = b["pair"]["L"]
        pair_split = _split_holding(tree, L, R)
        self.assertIsNotNone(pair_split, "the store holds the pair's split: %r" % tree)
        i = _leaves(pair_split["kids"][0]) == [L] and 0 or [k for k, kid in enumerate(pair_split["kids"]) if L in _leaves(kid)][0]
        rl, rr = pair_split["ratios"][i], pair_split["ratios"][i + 1]
        avail = b["after"]["rects"][L]["h"] + b["after"]["rects"][R]["h"]
        self._within(rr * avail, 120.0, 1.5, "the store's ratios match the screen: the bottom pane's share is 120 px of the pair: %r" % pair_split["ratios"])
        self.assertEqual(b["after"]["writes"], 1, "one store write, at the release")

    def test_the_kits_band_edge_resizes_live_persists_once_at_release_and_nothing_on_escape(self):
        r = self._result()
        b = r["kitBand"]
        self.assertNotIn("error", b, b)
        self.assertEqual(b["cursor"], "row-resize", "the band's edge shows row-resize over the panes")
        for pt in b["points"]:
            tl = _px(pt["tl"])
            self._within(tl, pt["wanted"], 4.0, "mid-drag the band's height is the pointer's distance from its bottom, within the gutter's half: %r" % pt)
            self._within(pt["band"], tl, 1.5, "and the band's element is that height")
            self.assertEqual(pt["writes"], 0, "no store write per frame: %r" % pt)
        self._within(b["after"]["band"], b["points"][-1]["band"], 1.5, "the release changes nothing on screen")
        self.assertEqual(b["after"]["writes"], 1, "the store is written once, at release")
        self._within(_fixed_px(b["after"]["stored"]["parsed"]["tree"], "tl-pane"), _px(b["after"]["tl"]), 1.5, "the store's band px is the height variable's")
        self.assertEqual(b["after"]["cursor"], "grab")
        be = r["kitBandEscape"]
        self.assertNotIn("error", be, be)
        self.assertGreater(abs(be["points"][0]["band"] - be["band0"]), 15, "the drag moved the band before Escape")
        self.assertEqual(be["after"]["tl"], be["tl0"], "Escape restores the height variable")
        self._within(be["after"]["band"], be["band0"], 1.5, "and the band's height")
        self.assertEqual(be["after"]["writes"], 0, "and writes nothing: %r" % be["after"]["writes"])

    def test_a_far_drag_on_the_kits_dividers_stops_at_the_panes_minimum_with_the_edge_at_the_clamp(self):
        # the kit's clamp against the press geometry: the pushed pane at 120 px both ways on each divider, the edge stopped there
        r = self._result()
        # (4b) the far drags: the kit's clamp holds against the geometry at the PRESS (the 1927 read: against the tree the drag
        # rewrote every frame, the window shrank each frame and the edge stopped at half its range); the pane the pointer pushes
        # sits at the real minimum, 120 px, and the edge stops there
        kf = r["kitRowFar"]
        self.assertNotIn("error", kf, kf)
        far_r, far_l = kf["points"]
        self._within(far_r["R"]["w"], 120.0, 1.5, "far right on the column divider: the right pane at the minimum, 120 px: %r" % far_r)
        self._within(far_r["sum"], kf["points"][0]["sum"], 1.5, "the pair trades width at the clamp too")
        self.assertLess(far_r["edge"], far_r["pointer"] - 100, "the edge stopped at the clamp, short of the pointer")
        self._within(far_l["L"]["w"], 120.0, 1.5, "far left: the left pane at the minimum, 120 px: %r" % far_l)
        self.assertTrue(kf["after"]["layoutRestored"], "Escape restores the layout after the far drags")
        kcf = r["kitColFar"]
        self.assertNotIn("error", kcf, kcf)
        far_d, far_u = kcf["points"]
        self._within(far_d["R"]["h"], 120.0, 1.5, "far down on the row divider: the bottom pane at the minimum, 120 px: %r" % far_d)
        self.assertLess(far_d["edge"], far_d["pointer"] - 100, "the edge stopped at the clamp")
        self._within(far_u["L"]["h"], 120.0, 1.5, "far up: the top pane at the minimum: %r" % far_u)
        self.assertTrue(kcf["after"]["layoutRestored"])

if __name__ == "__main__":
    unittest.main()
