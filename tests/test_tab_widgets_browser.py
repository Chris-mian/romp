#!/usr/bin/env python3
"""The tab-title WIDGETS and the settings panel in TABS (T379, the user 2026-09-12), on the served dashboard: a hermetic kernel
serves the landing with two synthetic notes-api sessions (web and api, idle, TESTHOST); the chat frame's strip carries the
widgets (the dot slot on every tab, the hot-key keycap on the tab whose hot key the tab hot-key store names) and the
tab-widgets gear glyph at the strip's right end; the glyph opens the settings frame on the Chat tab scrolled to its Tab
widgets section (through the shell's relay; the user's amendment 2026-09-12: no tab of their own), where each registered widget is a row with a live demo drawn by the strip's own render, a sliding switch and its
options; a switch or an option written there reaches the chat frame's strip live (the storage event) and the store's
tabCtx mirror; the last tab is remembered; the pills hide every other pane.

TAB_WIDGETS_DIST=<dir> serves another tree's UI bundle (the red run's before); TAB_WIDGETS_SHOTS=<prefix> writes
<prefix>-strip-<theme>.png and <prefix>-settings-<theme>.png; TAB_WIDGETS_DUMP=<path> writes the whole measurement. Skips LOUDLY
without the extension deps or a Playwright browser (CI sets ROMP_SERVED_TESTS_REQUIRE=1 and installs both, so a skip
there is a failure). Synthetic throughout: placeholder sids, TESTHOST, invented text.
"""
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
import test_ship_reship as _lab   # noqa: E402  the lab kernel's environment: a list of names, never a copy of the runner's

NAMES = ["web", "api"]
SIDS = {n: "%s-1111-2222-3333-444444444444" % (chr(ord("a") + i) * 8) for i, n in enumerate(NAMES)}
PALETTE = [("#9cd2ff", "#0c1a2e"), ("#1EA1EB", "#ffffff")]


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));
let browser;
try { browser = await chromium.launch(); }
catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
const ctx = await browser.newContext({ viewport: { width: 1200, height: 800 } });
// the tab hot-key store shape (the hot key widget reads it): web is in the set, its chord Ctrl+Shift+1
await ctx.addInitScript(([sid]) => {
  try { localStorage.setItem("romp:tabkeys", JSON.stringify({ [sid]: "web" })); localStorage.setItem("romp:keys", JSON.stringify({ ["session.hotkey." + sid]: "Ctrl+Shift+1" })); } catch (e) {}
}, [cfg.sidWeb]);
const page = await ctx.newPage();
await page.goto(cfg.url);
await page.waitForSelector("#rail-gear", { timeout: 20000 });
const chat = () => page.frames().find((f) => f.url().includes("/chat"));
await page.waitForFunction(() => true);
let chatF = chat();
for (let i = 0; i < 100 && !chatF; i++) { await page.waitForTimeout(100); chatF = chat(); }
if (!chatF) { console.error("no chat frame"); process.exit(1); }
await chatF.waitForSelector("#tabs .tab[data-id]", { timeout: 30000 });
await chatF.waitForFunction((n) => document.querySelectorAll("#tabs .tab[data-id]").length >= n, cfg.count, { timeout: 30000 });
await chatF.waitForTimeout(500);
const readStrip = () => chatF.evaluate(([sidWeb]) => {
  const rect = (e) => { const b = e.getBoundingClientRect(); return { left: b.left, right: b.right, top: b.top, bottom: b.bottom, w: b.width, h: b.height }; };
  const tabs = Array.from(document.querySelectorAll("#tabs .tab[data-id]")).map((t) => ({
    id: t.dataset.id, name: (t.querySelector(".tab-label") || {}).textContent || "",
    children: Array.from(t.children).map((c) => c.className),
    dot: (() => { const d = t.querySelector(".tab-dot"); if (!d) return null; const cs = getComputedStyle(d); return { cls: d.className, visibility: cs.visibility, opacity: cs.opacity, bg: cs.backgroundColor, w: d.getBoundingClientRect().width }; })(),
    key: (() => { const k = t.querySelector(".tab-key"); return k ? { text: k.textContent, title: k.title, w: k.getBoundingClientRect().width } : null; })(),
    ctx: !!t.querySelector(".tab-ctx"),
  }));
  const gear = document.querySelector("#tabs .tab-gearbox .tab-widgets-gear");   // T405: the gear in a box of its own at the strip's right
  const box = document.querySelector("#tabs .tab-gearbox");
  const s = JSON.parse(localStorage.getItem("romp:settings") || "{}");
  return { tabs, web: tabs.find((t) => t.id === sidWeb), gear: gear ? { title: gear.title, aria: gear.getAttribute("aria-label"), svg: !!gear.querySelector("svg"), rect: rect(gear), inBox: gear.parentElement === box, boxH: box.getBoundingClientRect().height } : null,
           store: { tabWidgets: s.tabWidgets || null, tabCtx: s.tabCtx || null } };
}, [cfg.sidWeb]);
const out = {};
out.strip0 = await readStrip();
// the glyph opens the settings frame on the Chat tab, scrolled to its Tab widgets section, through the shell
const settingsOpen = () => page.evaluate(() => document.body.classList.contains("settings-open"));
if (out.strip0.gear) {   // T405: the gear opens its menu; the "Tab widgets…" row is the T379 ask
  await chatF.click("#tabs .tab-gearbox .tab-widgets-gear");
  await chatF.waitForSelector('[data-rows-menu="1"]', { timeout: 5000 });
  out.menuRoles = await chatF.evaluate(() => Array.from(document.querySelectorAll('[data-rows-menu="1"] > div')).map((r) => [r.getAttribute("role"), r.hasAttribute("aria-checked")]));
  await chatF.click('[data-rows-menu="1"] [role="menuitem"]:nth-child(2)');   // the Tab widgets row is an ACTION (role menuitem, no checked state); a role drift fails here, on the selector that did not match
}
await page.waitForFunction(() => document.body.classList.contains("settings-open"), null, { timeout: 20000 }).catch(() => {});
out.shellOpen = await settingsOpen();
let setF = page.frames().find((f) => f.url().includes("/settings"));
for (let i = 0; i < 50 && !setF; i++) { await page.waitForTimeout(100); setF = page.frames().find((f) => f.url().includes("/settings")); }
if (!setF) {   // no settings frame opened (the red run's before: no glyph, no ask): every later reading is an honest empty, so each test fails on its own assertion
  const none = { open: false, pills: [], panes: [], rows: [], remembered: null, section: null };
  Object.assign(out, { panel0: none, afterCtxOff: { panel: none, strip: out.strip0 }, dotOpt: { present: false, picked: false, labels: [] }, afterGrey: { panel: none, strip: out.strip0 },
                       afterKeyOff: { strip: out.strip0 }, feedPane: none, pillBack: none, reask: none, afterEscape: { shellOpen: false, panel: none }, reopen: none, legacy: {}, tall: { open: null, reask: null } });
  fs.writeFileSync(cfg.out, JSON.stringify(out)); console.log("RESULT: ok"); await browser.close(); process.exit(0);
}
await setF.waitForSelector("#rsettings:not([hidden])", { timeout: 15000 }).catch(() => {});
await setF.evaluate(() => (document.fonts && document.fonts.ready) || null).catch(() => {});   // the layout the measurement reads is the settled one (a late web font moved the head on a slow runner)
// the landing's own mark, never a delay: the gear stamps the card when the section scroll lands (CI, 2026-09-13: a fixed wait read before it)
const landed = (frame) => frame.waitForSelector('#rsettings .rs-card[data-section-landed="tabwidgets"]', { timeout: 10000 }).then(() => true).catch(() => false);
out.landed0 = await landed(setF);
const readPanel = () => setF.evaluate(() => {
  const p = document.getElementById("rsettings");
  if (!p || p.hidden) return { open: false };
  const pills = Array.from(document.querySelectorAll("#rsettings .rs-tab")).map((b) => ({ tab: b.dataset.tab, text: b.textContent, on: b.classList.contains("on"), selected: b.getAttribute("aria-selected") }));
  const panes = Array.from(document.querySelectorAll("#rsettings .rs-pane")).map((pn) => ({ pane: pn.dataset.pane, hidden: pn.hidden, display: getComputedStyle(pn).display, rows: pn.querySelectorAll(".rs-row, .rs-widget").length }));
  const rows = Array.from(document.querySelectorAll("#rs-widgets .rs-widget")).map((r) => {
    const sw = r.querySelector(".rs-switch"); const cs = getComputedStyle(sw); const knob = getComputedStyle(sw, "::after");
    const demo = r.querySelector(".rs-widget-demo .tab"); const desc = r.querySelector(".rs-widget-name .rs-sub, .rs-widget-name span");
    return { id: r.dataset.widget, label: r.querySelector(".rs-widget-name b").textContent, desc: desc.textContent,
             swLeft: sw.getBoundingClientRect().left, descDisplay: getComputedStyle(desc).display,
             sw: { role: sw.getAttribute("role"), checked: sw.getAttribute("aria-checked"), on: sw.classList.contains("on"), w: sw.getBoundingClientRect().width, h: sw.getBoundingClientRect().height, radius: cs.borderRadius, knobLeft: knob.left, bg: cs.backgroundColor },
             demo: demo ? Array.from(demo.children).map((c) => ({ cls: c.className, text: c.textContent, title: c.title || "" })) : null,
             opts: Array.from(r.querySelectorAll(".rs-widget-opt")).map((o) => ({ key: o.dataset.opt, label: o.title, current: (o.querySelector("button") || {}).textContent || "" })) };
  });
  // the SECTION: the Tab widgets head against the card's box and scroll (the gear's ask scrolls the card so the head sits under the padding)
  const card = document.querySelector("#rsettings .rs-card"); const sec = document.querySelector('#rsettings .rs-sec[data-section="tabwidgets"]');
  const cr = card.getBoundingClientRect(); const sr = sec ? sec.getBoundingClientRect() : null;
  const section = sec ? { top: sr.top, cardTop: cr.top, cardBottom: cr.bottom, pad: parseFloat(getComputedStyle(card).paddingTop), scrollTop: card.scrollTop, overflow: card.scrollHeight - card.clientHeight,
                          inChat: !!sec.closest('.rs-pane[data-pane="chat"]'), paneHidden: sec.closest(".rs-pane").hidden,
                          room: parseFloat(getComputedStyle(sec.closest(".rs-pane")).paddingBottom) || 0, cardH: cr.height, viewportH: window.innerHeight } : null;
  return { open: true, pills, panes, rows, remembered: localStorage.getItem("romp:settingsTab"), section };
});
out.panel0 = await readPanel();
// the Context bar's switch off: the store's prefs and mirror, the chat's strip on the storage event
const flip = async (id) => { await setF.click('#rs-widgets .rs-widget[data-widget="' + id + '"] .rs-switch'); await setF.waitForTimeout(400); };
await flip("ctx");
out.afterCtxOff = { panel: await readPanel(), strip: await readStrip() };
await flip("ctx");
// the dot's option: a grey dot when idle (the tabs are idle here), through the house picker
out.dotOpt = await setF.evaluate(async () => {
  const wrap = document.querySelector('#rs-widgets .rs-widget[data-widget="dot"] .rs-widget-opt[data-opt="idle"]');
  if (!wrap) return { present: false };
  wrap.querySelector("button").click();
  await new Promise((r) => setTimeout(r, 100));
  const row = Array.from(wrap.querySelectorAll("[data-wopt-dot-idle]")).find((r) => r.getAttribute("data-wopt-dot-idle") === "grey");
  const labels = Array.from(wrap.querySelectorAll("[data-wopt-dot-idle]")).map((r) => r.textContent.replace(/\u2713/g, "").trim());   // the current row carries the house picker's check glyph
  if (row) row.click();
  await new Promise((r) => setTimeout(r, 400));
  return { present: true, labels, picked: !!row };
});
out.afterGrey = { panel: await readPanel(), strip: await readStrip() };
// the hot key widget off: the keycap leaves web's tab
await flip("hotkey");
out.afterKeyOff = { strip: await readStrip() };
await flip("hotkey");
// the pills: Feed hides Chat; Escape closes; the next open remembers the tab
await setF.click('#rsettings .rs-tab[data-tab="feed"]'); await setF.waitForTimeout(150);
out.feedPane = await readPanel();
// a pill round trip (Feed, then Chat by its pill): the Chat pane comes back at its top with no section room left behind
await setF.click('#rsettings .rs-tab[data-tab="chat"]'); await setF.waitForTimeout(150);
out.pillBack = await readPanel();
// an ask on an OPEN panel (through the shell's relay, the path the glyph's message takes; the lifted settings iframe covers the
// strip while the panel is open, so the glyph itself is not reachable by a pointer then): switches back to Chat and scrolls
await page.evaluate(() => window.__rompOpenSettings("chat", "tabwidgets")); out.landedReask = await landed(setF);
out.reask = await readPanel();
// the screenshots: the strip with the glyph and the Chat tab at its Tab widgets section, dark then light
const shot = async (theme) => {
  await page.evaluate((t) => document.body.classList.toggle("theme-light", t === "light"), theme);
  await chatF.evaluate((t) => document.body.classList.toggle("theme-light", t === "light"), theme);
  await setF.evaluate((t) => document.body.classList.toggle("theme-light", t === "light"), theme);
  await page.waitForTimeout(200);
  if (!cfg.shots) return;
  const card = await setF.evaluate(() => { const b = document.querySelector("#rsettings .rs-card").getBoundingClientRect(); return { x: b.left, y: b.top, width: b.width, height: b.height }; });   // the whole card: the scrolled Tab widgets section sits in its lower part
  const fr = await page.evaluate(() => { const f = document.getElementById("f-settings").getBoundingClientRect(); return { x: f.left, y: f.top }; });
  await page.screenshot({ path: cfg.shots + "-settings-" + theme + ".png", clip: { x: fr.x + card.x, y: fr.y + card.y, width: card.width, height: card.height } });
};
await shot("dark"); await shot("light");
await page.evaluate(() => document.body.classList.remove("theme-light")); await setF.evaluate(() => document.body.classList.remove("theme-light")); await chatF.evaluate(() => document.body.classList.remove("theme-light"));
await page.keyboard.press("Escape"); await page.waitForTimeout(300);
out.afterEscape = { shellOpen: await settingsOpen(), panel: await readPanel() };
// the strip shot with the panel closed
for (const theme of ["dark", "light"]) {
  await chatF.evaluate((t) => document.body.classList.toggle("theme-light", t === "light"), theme);
  await page.evaluate((t) => document.body.classList.toggle("theme-light", t === "light"), theme);
  await page.waitForTimeout(150);
  if (cfg.shots) {
    const bar = await chatF.evaluate(() => { const b = document.getElementById("tabbar").getBoundingClientRect(); return { x: 0, y: Math.max(0, b.top - 4), width: Math.min(window.innerWidth, 900), height: b.height + 8 }; });
    const fr = await page.evaluate(() => { const f = document.getElementById("f-chat").getBoundingClientRect(); return { x: f.left, y: f.top }; });
    await page.screenshot({ path: cfg.shots + "-strip-" + theme + ".png", clip: { x: fr.x + bar.x, y: fr.y + bar.y, width: bar.width, height: bar.height } });
  }
}
await chatF.evaluate(() => document.body.classList.remove("theme-light")); await page.evaluate(() => document.body.classList.remove("theme-light"));
// reopen from the rail's gear: the remembered tab (Chat) comes up
await page.click("#rail-gear");
await page.waitForFunction(() => document.body.classList.contains("settings-open"), null, { timeout: 10000 }).catch(() => {});
await setF.waitForTimeout(300);
out.reopen = await readPanel();
await page.close(); await ctx.close();
// LEGACY STORES (round one, HIGH): a browser from before the widgets holds tabCtx and no tabWidgets. The panel must read the
// context bar's row from tabCtx (always: on at Always; never: off), and a save of an UNRELATED setting (Compact transcript)
// must leave the store's tabWidgets absent and tabCtx as it was, the strip unchanged. One fresh context per mode.
out.legacy = {};
for (const mode of ["always", "never"]) {
  const c2 = await browser.newContext({ viewport: { width: 1200, height: 800 } });
  await c2.addInitScript(([m]) => { try { localStorage.setItem("romp:settings", JSON.stringify({ compact: true, tabCtx: m })); } catch (e) {} }, [mode]);
  const p2 = await c2.newPage();
  await p2.goto(cfg.url);
  await p2.waitForSelector("#rail-gear", { timeout: 20000 });
  let cf = p2.frames().find((f) => f.url().includes("/chat"));
  for (let i = 0; i < 100 && !cf; i++) { await p2.waitForTimeout(100); cf = p2.frames().find((f) => f.url().includes("/chat")); }
  await cf.waitForFunction((n) => document.querySelectorAll("#tabs .tab[data-id]").length >= n, cfg.count, { timeout: 30000 });
  await cf.waitForTimeout(400);
  const strip = () => cf.evaluate(() => { const s = JSON.parse(localStorage.getItem("romp:settings") || "{}");
    return { ctx: Array.from(document.querySelectorAll("#tabs .tab[data-id]")).map((t) => !!t.querySelector(".tab-ctx")), store: { tabWidgets: "tabWidgets" in s ? s.tabWidgets : "absent", tabCtx: s.tabCtx, compact: s.compact } }; });
  const before = await strip();
  // the shell's state before the ask is recorded (a lifted settings iframe would take the strip's pointer events); the ask
  // itself goes through the shell's own relay, the path the glyph's message takes, so this scene reads the panel whatever
  // the shell's pointer state is
  const shellBefore = await p2.evaluate(() => { const f = document.getElementById("f-settings"); return { cls: document.body.className, fSrc: f ? f.getAttribute("src") : null, fDisplay: f ? getComputedStyle(f).display : null }; });
  await p2.evaluate(() => window.__rompOpenSettings("chat", "tabwidgets"));
  await p2.waitForFunction(() => document.body.classList.contains("settings-open"), null, { timeout: 20000 }).catch(() => {});
  let sf = p2.frames().find((f) => f.url().includes("/settings"));
  for (let i = 0; i < 50 && !sf; i++) { await p2.waitForTimeout(100); sf = p2.frames().find((f) => f.url().includes("/settings")); }
  await sf.waitForSelector("#rsettings:not([hidden])", { timeout: 15000 }).catch(() => {});
  await sf.waitForTimeout(300);
  const row = () => sf.evaluate(() => { const r = document.querySelector('#rs-widgets .rs-widget[data-widget="ctx"]'); if (!r) return null;
    const sw = r.querySelector(".rs-switch"); const o = r.querySelector('.rs-widget-opt[data-opt="show"] button');
    return { checked: sw.getAttribute("aria-checked"), show: o ? o.textContent.replace(/\u25be/g, "").trim() : null }; });
  const panelBefore = await row();
  await sf.click("#rs-compact"); await sf.waitForTimeout(500);   // an unrelated setting's save
  out.legacy[mode] = { before, shellBefore, panelBefore, after: await strip(), panelAfter: await row() };
  await p2.close(); await c2.close();
}
// a TALL window (the follow-up's round one, MEDIUM): below its cap the card grows under any room added, so the head stopped
// short (152px off at 1200px); the room is sized to the cap now. The glyph's open and a re-ask, measured at 1200 by 1200.
{
  const c3 = await browser.newContext({ viewport: { width: 1200, height: 1200 } });
  const p3 = await c3.newPage(); await p3.goto(cfg.url); await p3.waitForSelector("#rail-gear", { timeout: 20000 });
  let cf3 = p3.frames().find((f) => f.url().includes("/chat"));
  for (let i = 0; i < 100 && !cf3; i++) { await p3.waitForTimeout(100); cf3 = p3.frames().find((f) => f.url().includes("/chat")); }
  await cf3.waitForFunction((n) => document.querySelectorAll("#tabs .tab[data-id]").length >= n, cfg.count, { timeout: 30000 });
  await p3.evaluate(() => window.__rompOpenSettings("chat", "tabwidgets"));
  await p3.waitForFunction(() => document.body.classList.contains("settings-open"), null, { timeout: 20000 }).catch(() => {});
  let sf3 = p3.frames().find((f) => f.url().includes("/settings"));
  for (let i = 0; i < 50 && !sf3; i++) { await p3.waitForTimeout(100); sf3 = p3.frames().find((f) => f.url().includes("/settings")); }
  await sf3.waitForSelector("#rsettings:not([hidden])", { timeout: 15000 }).catch(() => {});
  await sf3.evaluate(() => (document.fonts && document.fonts.ready) || null).catch(() => {});
  out.tallLanded = await landed(sf3);
  const readSec = () => sf3.evaluate(() => { const card = document.querySelector("#rsettings .rs-card"); const sec = document.querySelector('#rsettings .rs-sec[data-section="tabwidgets"]');
    if (!card || !sec) return null; const cr = card.getBoundingClientRect(), sr = sec.getBoundingClientRect();
    return { top: sr.top, cardTop: cr.top, cardBottom: cr.bottom, pad: parseFloat(getComputedStyle(card).paddingTop), scrollTop: card.scrollTop, overflow: card.scrollHeight - card.clientHeight,
             room: parseFloat(getComputedStyle(sec.closest(".rs-pane")).paddingBottom) || 0, cardH: cr.height, viewportH: window.innerHeight, inChat: true, paneHidden: sec.closest(".rs-pane").hidden }; });
  out.tall = { open: await readSec() };
  await p3.evaluate(() => window.__rompOpenSettings("chat", "tabwidgets")); out.tall.reaskLanded = await landed(sf3);
  out.tall.reask = await readSec();
  // the review's oracles (round two): the ask STANDS across the browser's own scrolls and re-lands on size changes; only the user's input ends it
  const clearMark = () => sf3.evaluate(() => { const c = document.querySelector("#rsettings .rs-card"); if (c) c.removeAttribute("data-section-landed"); });
  const landedSoon = (frame, ms) => frame.waitForSelector('#rsettings .rs-card[data-section-landed="tabwidgets"]', { timeout: ms }).then(() => true).catch(() => false);
  await clearMark(); await p3.setViewportSize({ width: 1200, height: 900 });    // SHORTER: the card shrinks to the new cap (Chrome's anchoring nudges the scroll)
  out.tall.shorter = { landed: await landedSoon(sf3, 10000), sec: await readSec() };
  await clearMark(); await p3.setViewportSize({ width: 1200, height: 1400 });   // TALLER: the card grows to the new cap and the browser clamps the scroll first
  out.tall.taller = { landed: await landedSoon(sf3, 10000), sec: await readSec() };
  const fr3 = await p3.evaluate(() => { const f = document.getElementById("f-settings").getBoundingClientRect(); return { x: f.left, y: f.top }; });
  const cr3 = await sf3.evaluate(() => { const r = document.querySelector("#rsettings .rs-card").getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; });
  await p3.mouse.move(fr3.x + cr3.x, fr3.y + cr3.y); await p3.mouse.wheel(0, -120); await sf3.waitForTimeout(250);   // a real WHEEL over the card: the user's scroll
  const afterWheel = await readSec();
  await clearMark(); await p3.setViewportSize({ width: 1200, height: 1500 });   // a growth after the user's scroll: no re-land, the ask ended
  out.tall.wheel = { afterWheel, landedAfterGrowth: await landedSoon(sf3, 2500), sec: await readSec() };
  // ROUND THREE: the keyboard road (MEDIUM), the ask's own echo (LOW 1), a lost release and a press on the padding (LOW 2)
  const r3 = {};
  // a re-ask's landing owes one scroll event, its echo, dispatched at the next frame: two frames let it pass before the road's
  // own input, so a head without the write ledger fails a road for the road's reason and not for LOW 1's
  const settled = () => sf3.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
  const reask = async () => { await clearMark(); await p3.evaluate(() => window.__rompOpenSettings("chat", "tabwidgets")); const l = await landed(sf3); await settled(); return l; };
  const settleScroll = () => sf3.evaluate(() => new Promise((res) => { const c = document.querySelector("#rsettings .rs-card"); let last = c.scrollTop, same = 0;
    const tick = () => { if (c.scrollTop === last) same++; else { same = 0; last = c.scrollTop; } if (same >= 3) res(); else requestAnimationFrame(tick); }; requestAnimationFrame(tick); }));
  // K: a click in the card (the section head), a pause past the input window on purpose (the key must stand on its own, not on the
  // click), PageUp: the key scrolls the card while its keydown targets BODY (the card has no tabindex); a size change after it must
  // land nothing and leave the card where the key put it
  r3.keyLanded = await reask();
  await clearMark(); await p3.setViewportSize({ width: 1200, height: 1450 });   // the ask stands before the key: a size change re-lands
  r3.keyStanding = await landedSoon(sf3, 10000); await settled();
  const headBox = await sf3.evaluate(() => { const r = document.querySelector('#rsettings .rs-pane:not([hidden]) .rs-sec[data-section="tabwidgets"]').getBoundingClientRect(); return { x: r.left + 20, y: r.top + r.height / 2 }; });
  await p3.mouse.click(fr3.x + headBox.x, fr3.y + headBox.y);
  await sf3.waitForTimeout(300);
  const beforeKey = await readSec();
  await p3.keyboard.press("PageUp");
  await sf3.waitForFunction((t) => document.querySelector("#rsettings .rs-card").scrollTop !== t, beforeKey.scrollTop, { timeout: 5000 }).catch(() => {});
  await settleScroll();
  const afterKey = await readSec();
  await clearMark(); await p3.setViewportSize({ width: 1200, height: 1420 });   // a size change after the user's key: nothing lands
  r3.key = { beforeKey, afterKey, landedAfterResize: await landedSoon(sf3, 2500), sec: await readSec() };
  // the three probes below drive the ask's own machinery from inside the page: a synthetic press, a size change of the card (its
  // observer re-lands), frames counted, never a clock, except the pauses past the 120 ms input window that the probes need
  const probe = (body) => sf3.evaluate(new Function("return (async () => {" + `
    const card = document.querySelector("#rsettings .rs-card"), label = document.querySelector('#rsettings .rs-pane:not([hidden]) .rs-sec[data-section="tabwidgets"]');
    const mark = () => card.getAttribute("data-section-landed");
    const frames = (n) => new Promise((r) => { const step = () => (--n <= 0 ? r() : requestAnimationFrame(step)); requestAnimationFrame(step); });
    const pastWindow = () => new Promise((r) => setTimeout(r, 200));
    const press = (target, x, y) => target.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, composed: true, clientX: x, clientY: y, pointerType: "mouse", isPrimary: true, button: 0, buttons: 1 }));
    const release = () => window.dispatchEvent(new PointerEvent("pointerup", { bubbles: true, pointerType: "mouse", isPrimary: true }));
    const nudge = async () => { card.scrollTop = 0; await frames(2); card.scrollTop = 20; await frames(2); };   // two scrolls of another origin: one alone could be paid to an echo debt (round four, LOW 1)
    const cycle = async () => { card.removeAttribute("data-section-landed"); card.style.maxHeight = "70vh"; await frames(4); const a = { mark: mark(), scrollTop: card.scrollTop };
      card.removeAttribute("data-section-landed"); card.style.maxHeight = ""; await frames(4); return { afterChange: a, restored: mark(), scrollTop: card.scrollTop }; };
  ` + body + "})();"));
  // E: the card moved by another origin (no input: the ask stands, the head off the top), then a press on the section's head and a
  // size change at once: the re-land's write moves the card back and its echo arrives inside the input window
  r3.echoLanded = await reask();
  r3.echo = await probe(`
    card.scrollTop = 0; await frames(2);
    const lr = label.getBoundingClientRect(); press(label, lr.left + 10, lr.top + lr.height / 2);
    const out = await cycle(); release(); return out;`);
  // B: a grab of the gutter, then the page's blur and visibility change with no release ever, a pause past the window, a scroll of
  // another origin, a size change: the hold must be gone, the ask standing
  r3.blurLanded = await reask();
  r3.blur = await probe(`
    const r = card.getBoundingClientRect(), gw = r.width - card.clientLeft * 2 - card.clientWidth;
    press(card, r.left + card.clientLeft + card.clientWidth + gw / 2, r.top + r.height / 2);
    window.dispatchEvent(new Event("blur")); document.dispatchEvent(new Event("visibilitychange"));
    await pastWindow(); await nudge();
    const out = await cycle(); return Object.assign({ gw }, out);`);
  // P: a press whose target is the card's own padding (inside the client box), a pause past the window, a scroll of another origin,
  // a size change: a press is no grab, so the ask stands
  r3.padLanded = await reask();
  r3.pad = await probe(`
    const r = card.getBoundingClientRect();
    press(card, r.left + card.clientLeft + 3, r.top + card.clientTop + 3);
    await pastWindow(); await nudge();
    const out = await cycle(); release(); return out;`);
  // ROUND FOUR. S: a landing's echo debt (MEDIUM 1): a re-land by a SHRINK of the card's cap (a shrink moves nothing before the landing
  // runs, so the landing's room drop and write back net to zero and the frame renders no move: the debt's shape; a growth clamps the
  // scroll first, a real move that pays any debt), then ONE scroll with the user's evidence (a wheel on the card and the scroll it
  // stands for, within the window): the ask must end on that first scroll, so the next size change, a further shrink that cannot
  // clamp the wheel's position, lands nothing and the card stays where the wheel put it. The cap is restored after the measurement.
  r3.debtLanded = await reask();
  r3.debt = await probe(`
    card.style.maxHeight = "70vh"; await frames(4); const relanded = mark(); await frames(2);
    card.dispatchEvent(new WheelEvent("wheel", { bubbles: true, deltaY: -120 })); card.scrollTop = card.scrollTop - 120; await frames(2);
    const afterWheel = { mark: mark(), scrollTop: card.scrollTop };
    card.removeAttribute("data-section-landed"); card.style.maxHeight = "60vh"; await frames(4);
    const out = { relanded, afterWheel, landedAfterChange: mark(), scrollTop: card.scrollTop, overflow: card.scrollHeight - card.clientHeight };
    card.style.maxHeight = ""; await frames(4); return out;`);
  // G: a press at the innermost content pixel column (LOW 2): measured from the border box it read as the gutter; no grab, the ask stands
  r3.edgeLanded = await reask();
  r3.edge = await probe(`
    const r = card.getBoundingClientRect();
    press(card, r.left + card.clientLeft + card.clientWidth - 1, r.top + r.height / 2);
    await pastWindow(); await nudge();
    const out = await cycle(); release(); return out;`);
  // C: the focus on a checkbox row in the landed view, then a real PageUp (MEDIUM 2): a checkbox consumes no Page key, so the card
  // scrolls; the key must count (a checkbox is no field), the ask end, and a size change after it land nothing
  r3.boxLanded = await reask();
  await clearMark(); await p3.setViewportSize({ width: 1200, height: 1450 }); r3.boxStanding = await landedSoon(sf3, 10000); await settled();
  await sf3.evaluate(() => document.getElementById("rs-striprows").focus({ preventScroll: true }));
  const beforeBoxKey = await readSec();
  await p3.keyboard.press("PageUp");
  await sf3.waitForFunction((t) => document.querySelector("#rsettings .rs-card").scrollTop !== t, beforeBoxKey.scrollTop, { timeout: 5000 }).catch(() => {});
  await settleScroll();
  const afterBoxKey = await readSec();
  await clearMark(); await p3.setViewportSize({ width: 1200, height: 1420 });
  r3.box = { active: await sf3.evaluate(() => { const a = document.activeElement; return a ? a.tagName + "#" + a.id + ":" + (a.getAttribute("type") || "") : null; }),
             beforeBoxKey, afterBoxKey, landedAfterResize: await landedSoon(sf3, 2500), sec: await readSec() };
  out.tall.r3 = r3;
  await p3.close(); await c3.close();
}
fs.writeFileSync(cfg.out, JSON.stringify(out));
await browser.close();
console.log("RESULT: ok");
"""


class ServedTabWidgets(unittest.TestCase):
    maxDiff = None
    result = None

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
            raise unittest.SkipTest("extension deps absent (npm ci not run here) — the served guard needs them")
        probe = subprocess.run(["node", "-e", "const p=require(process.argv[1]);process.stdout.write(p.chromium.executablePath())",
                                os.path.join(EXT, "node_modules", "playwright")], capture_output=True, text=True)
        if probe.returncode != 0 or not os.path.exists(probe.stdout.strip()):
            raise unittest.SkipTest("no playwright browser on this box — the served guard needs one (CI installs none)")
        cls.lab = tempfile.mkdtemp(prefix="tab-widgets-")
        before = os.environ.get("TAB_WIDGETS_DIST", "")
        if before:
            src = before
        else:
            b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
            if b.returncode != 0:
                raise unittest.SkipTest("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
            src = os.path.join(EXT, "dist")
        dist = os.path.join(cls.lab, "dist")
        copy_dist(src, dist)
        state = os.path.join(cls.lab, "xdg", "romp")
        claude = os.path.join(cls.lab, "claude")
        cwd = os.path.join(cls.lab, "notes-api")
        for d in ("names", "sdk", "states"):
            os.makedirs(os.path.join(state, d), exist_ok=True)
        Path(state, "session-hosts").write_text("off\n")   # a lab root writes its own session-hosts off (the conftest rule)
        os.makedirs(cwd, exist_ok=True)
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        t0 = int(time.time()) - 900
        for i, name in enumerate(NAMES):
            sid = SIDS[name]
            bg, fg = PALETTE[i]
            Path(state, "names", sid).write_text("%s\t%s\t%s\t%s\n" % (name, cwd, bg, fg))
            Path(state, "sdk", sid + ".json").write_text(json.dumps(
                {"sid": sid, "name": name, "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": sid, "alive": True,
                 "model": "claude-opus-5", "liveModel": "Opus 5",
                 **({"liveCtx": 62} if name == "web" else {})}))   # web carries a context percentage, so the context bar has something to show (round two, LOW 6)
            recs = [{"type": "user", "timestamp": iso(t0 + i), "uuid": "u1", "parentUuid": None, "promptSource": "typed", "sessionId": sid,
                     "message": {"role": "user", "content": "what does the %s session do in notes-api?" % name}},
                    {"type": "assistant", "timestamp": iso(t0 + i + 5), "uuid": "a1", "parentUuid": "u1", "sessionId": sid,
                     "message": {"role": "assistant", "model": "claude-opus-5", "stop_reason": "end_turn",
                                 "content": [{"type": "text", "text": "It keeps the %s side of the notes-api tidy." % name}]}}]
            Path(proj, sid + ".jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
        Path(state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 10}, "seven_day": {"pct": 10}}))
        cls.port, cls.token = _free_port(), "testtok-tabwidgets"
        env = _lab.kernel_env(cls.lab, claude, dist, cls.port, cls.token, ROMP_HOST_NAME="TESTHOST")
        cls.state = state
        cls.klog = os.path.join(cls.lab, "kernel.log")
        cls.kernel = subprocess.Popen([os.path.join(BIN, "romp-kernel")], stdout=open(cls.klog, "w"), stderr=subprocess.STDOUT, env=env)
        for _ in range(120):
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/healthz" % cls.port, timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        else:
            raise unittest.SkipTest("hermetic kernel never served /healthz here")

    @classmethod
    def tearDownClass(cls):
        k = getattr(cls, "kernel", None)
        if k:
            k.terminate()
            try:
                k.wait(timeout=10)
            except subprocess.TimeoutExpired:
                k.kill(); k.wait()
            time.sleep(0.5)
        lab = getattr(cls, "lab", "")
        shutil.rmtree(lab, ignore_errors=True)
        time.sleep(0.3)
        shutil.rmtree(lab, ignore_errors=True)

    @classmethod
    def _run(cls):
        if cls.result is not None:
            if isinstance(cls.result, BaseException):
                raise cls.result
            return cls.result
        try:
            cls.result = cls._drive()
        except BaseException as e:
            cls.result = e
            raise
        return cls.result

    @classmethod
    def _drive(cls):
        cfg = os.path.join(cls.lab, "cfg.json")
        out = os.path.join(cls.lab, "result.json")
        with open(cfg, "w") as f:
            json.dump({"url": "http://127.0.0.1:%d/?token=%s" % (cls.port, cls.token), "count": len(NAMES), "out": out, "sidWeb": SIDS["web"],
                       "shots": os.environ.get("TAB_WIDGETS_SHOTS", "")}, f)
        driver = os.path.join(cls.lab, "driver.mjs")
        with open(driver, "w") as f:
            f.write(DRIVER)
        p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=300,
                           env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
        if p.returncode == 3:
            raise unittest.SkipTest("no playwright browser on this box — the served guard needs one (CI installs none)")
        if p.returncode != 0:
            raise AssertionError("driver failed:\n" + p.stdout[-3000:] + p.stderr[-3000:] + "\nkernel:\n" + open(cls.klog).read()[-1500:])
        if not os.path.exists(out):
            raise AssertionError("driver printed no result:\n" + p.stdout[-3000:])
        result = json.loads(Path(out).read_text())
        if os.environ.get("TAB_WIDGETS_DUMP"):
            Path(os.environ["TAB_WIDGETS_DUMP"]).write_text(json.dumps(result, indent=1) + "\n")
        return result

    def test_the_strip_carries_the_widgets_and_the_gear_glyph_in_its_own_box_at_the_right(self):
        s = self._run()["strip0"]
        table = "\n  " + json.dumps(s)[:1200]
        self.assertEqual(len(s["tabs"]), 2, table)
        for t in s["tabs"]:
            self.assertIsNotNone(t["dot"], "every tab carries the dot slot (T262g)" + table)
            self.assertEqual(t["dot"]["visibility"], "hidden", "idle: the slot is laid out and hidden" + table)
            self.assertEqual(t["children"][0], t["dot"]["cls"], "the dot is the tab's first child (the before-the-name slot)" + table)
        web = s["web"]
        self.assertIsNotNone(web["key"], "web's hot key (the tab hot-key store) renders as a keycap" + table)
        self.assertEqual(web["key"]["text"], "⌃⇧1", table)
        self.assertGreater(web["key"]["w"], 10, table)
        self.assertTrue(web["ctx"], "web carries a context percentage (62): the bar shows from half full" + table)
        self.assertEqual(web["children"].index("tab-ctx"), web["children"].index("tab-label") + 1, "the bar follows the name" + table)
        self.assertEqual(web["children"].index("tab-key"), web["children"].index("tab-ctx") + 1, "the keycap follows the bar (registration order)" + table)
        api = next(t for t in s["tabs"] if t["name"].endswith("api"))
        self.assertIsNone(api["key"], "no hot key assigned: no keycap" + table)
        self.assertIsNotNone(s["gear"], "the glyph is in the strip (the chat sits in the shell, so a gear can be reached)" + table)
        self.assertEqual((s["gear"]["title"], s["gear"]["aria"], s["gear"]["svg"], s["gear"]["inBox"]), ("Tab strip: lock, widgets…", "Tab strip settings", False, True), "T405: the shell's glyph, a character, in the gear box" + table)
        self.assertLessEqual(s["gear"]["rect"]["h"], s["gear"]["boxH"] + 0.5, "it takes no extra height beyond its box (the tags box's floor)" + table)
        self.assertEqual(self._run().get("menuRoles"), [["menuitemcheckbox", True], ["menuitem", False]], "the lock row a switch, the widgets row an action (round two, low 2)" + table)

    def _assert_scrolled_to_the_section(self, p, table):
        # the section head sits inside the card's visible box, under its padding, unless the card ran out of scroll first
        sec = p["section"]
        table = "\n  section=" + json.dumps(sec) + table   # the numbers first: the panel's table is long and cut
        self.assertIsNotNone(sec, "the Tab widgets head carries the section anchor" + table)
        self.assertTrue(sec["inChat"] and not sec["paneHidden"], "the section is in the Chat pane, which is shown" + table)
        self.assertGreaterEqual(sec["top"], sec["cardTop"] - 0.5, "the head is not above the card's box" + table)
        self.assertLess(sec["top"], sec["cardBottom"], "the head is inside the card's box" + table)
        if sec["overflow"] > 0:
            self.assertGreater(sec["scrollTop"], 0, "the card scrolled" + table)
            # round two, LOW 1: the head sits under the card's padding, always: the pane gains room at its end for it
            self.assertLess(abs(sec["top"] - (sec["cardTop"] + sec["pad"])), 3, "the head sits under the card's padding" + table)

    def test_the_glyph_opens_the_settings_on_the_chat_tab_scrolled_to_the_tab_widgets_section_with_the_other_panes_hidden(self):
        r = self._run()
        self.assertTrue(r["shellOpen"], "the shell lifted the settings frame")
        p = r["panel0"]
        table = "\n  " + json.dumps(p)[:1500]
        self.assertTrue(p["open"], table)
        self.assertEqual([x["tab"] for x in p["pills"]], ["general", "chat", "feed", "sessions", "automation", "tasks", "debug"], "seven pills in the user's order (T400; T404: Automation, Appearance into General)" + table)
        self.assertEqual([x["text"] for x in p["pills"]], ["General", "Chat", "Feed", "Sessions", "Automation", "Task tracking", "Debug"], table)
        self.assertEqual([x["on"] for x in p["pills"]], [False, True, False, False, False, False, False], "the Chat pill is on" + table)
        self.assertEqual([x["selected"] for x in p["pills"]], ["false", "true", "false", "false", "false", "false", "false"], table)
        shown = [x for x in p["panes"] if x["display"] != "none"]
        self.assertEqual([x["pane"] for x in shown], ["chat"], "one pane painted" + table)
        self.assertTrue(all(x["rows"] > 0 for x in p["panes"]), "every pane holds rows" + table)
        self.assertEqual(p["remembered"], "chat", table)
        self.assertTrue(r["landed0"], "the gear marked the landing before the measurement (the lab waits for the event, never a delay)")
        self.assertTrue(r["landedReask"], "…and marked the re-ask's landing afresh (the earlier mark is cleared with the earlier ask)")
        self._assert_scrolled_to_the_section(p, table)

    def test_each_widget_row_shows_a_live_demo_drawn_by_the_strips_render_a_sliding_switch_and_its_options(self):
        p = self._run()["panel0"]
        self.assertTrue(p["open"], "the panel opened: " + json.dumps(p)[:300])
        rows = p["rows"]
        table = "\n  " + json.dumps(rows)[:2000]
        self.assertEqual([r["id"] for r in rows], ["dot", "ctx", "hotkey"], "registration order: the dot, the bar, the hot key" + table)
        self.assertEqual([r["label"] for r in rows], ["Status dot", "Context bar", "Hot key"], table)
        for r in rows:
            self.assertEqual((r["sw"]["role"], r["sw"]["checked"], r["sw"]["on"]), ("switch", "true", True), r["id"] + " is on by default" + table)
            self.assertEqual(r["sw"]["radius"], "999px", "the sliding toggle, a pill" + table)
            self.assertGreater(r["sw"]["w"], r["sw"]["h"], table)
            self.assertEqual(r["sw"]["knobLeft"], "18px", "on: the knob sits right" + table)
            self.assertTrue(r["desc"], "a one-line description" + table)
        dot, ctx, key = rows
        self.assertEqual([c["cls"] for c in dot["demo"]], ["tab-dot", "tab-label"], "the demo: a working session's gold dot before the name" + table)
        self.assertEqual(dot["demo"][0]["title"], "working — a turn is running right now", table)
        self.assertEqual([c["cls"] for c in ctx["demo"]], ["tab-label", "tab-ctx"], "the bar after the name" + table)
        self.assertEqual([c["cls"] for c in key["demo"]], ["tab-label", "tab-key"], table)
        self.assertEqual(key["demo"][1]["text"], "⌃⇧1", "the demo keycap" + table)
        self.assertEqual([[o["key"] for o in r["opts"]] for r in rows], [["idle"], ["show"], []], "the dot's idle option, the bar's show option, the hot key none" + table)
        self.assertEqual(dot["opts"][0]["current"].replace("▾", "").strip(), "Hide when idle", table)
        self.assertEqual(ctx["opts"][0]["current"].replace("▾", "").strip(), "From 50% full", table)
        # round one, LOW 2: one grid across the rows, so every switch starts at the same x; the description sits behind the hover popover
        self.assertEqual(len({round(r["swLeft"]) for r in rows}), 1, "the switches line up down the list" + table)
        self.assertEqual([r["descDisplay"] for r in rows], ["none"] * 3, "the descriptions are hover popovers at rest, the panel's idiom" + table)

    def test_a_store_from_before_the_widgets_reads_its_gauge_setting_and_an_unrelated_save_leaves_it_alone(self):
        # round one, HIGH: an injected default for tabWidgets won over tabCtx (the row read on at 50 percent whatever the user had
        # chosen) and a save of ANY setting wrote the empty prefs and rewrote the mirror
        lg = self._run()["legacy"]
        for mode, checked, show in (("always", "true", "Always"), ("never", "false", "From 50% full")):
            sc = lg.get(mode)
            table = "\n  " + json.dumps(sc)[:1500]
            self.assertIsNotNone(sc, "the legacy scene ran" + table)
            self.assertEqual(sc["before"]["store"], {"tabWidgets": "absent", "tabCtx": mode, "compact": True}, mode + ": the seeded store" + table)
            self.assertEqual((sc["panelBefore"]["checked"], sc["panelBefore"]["show"]), (checked, show), mode + ": the row reads the older setting" + table)
            self.assertEqual(sc["after"]["store"], {"tabWidgets": "absent", "tabCtx": mode, "compact": False}, mode + ": Compact saved; the widgets key still absent, the mirror untouched" + table)
            self.assertEqual(sc["after"]["ctx"], sc["before"]["ctx"], mode + ": the strip unchanged" + table)
            self.assertEqual(any(sc["before"]["ctx"]), mode == "always", mode + ": the seeded percentage shows exactly when the older setting says so (the assertion above is not vacuous)" + table)
            self.assertEqual(sc["panelAfter"], sc["panelBefore"], mode + ": the row unchanged" + table)

    def test_a_switch_writes_the_prefs_and_the_mirror_and_the_strip_follows_live(self):
        r = self._run()
        a = r["afterCtxOff"]
        self.assertTrue(a["panel"]["open"], "the panel opened: " + json.dumps(a["panel"])[:300])
        table = "\n  " + json.dumps(a["strip"]["store"]) + " " + json.dumps([x["sw"]["checked"] for x in a["panel"]["rows"]])
        self.assertEqual([x["sw"]["checked"] for x in a["panel"]["rows"]], ["true", "false", "true"], "the Context bar's switch is off" + table)
        self.assertEqual(a["strip"]["store"]["tabWidgets"]["on"], {"ctx": False}, "the store's prefs" + table)
        self.assertEqual(a["strip"]["store"]["tabCtx"], "never", "…and the older key mirrors it, for older readers" + table)
        self.assertFalse(a["strip"]["web"]["ctx"], "the bar left web's tab live" + table)
        k = r["afterKeyOff"]["strip"]
        self.assertIsNone(k["web"]["key"], "the hot key widget off: the keycap left web's tab, live, through the storage event: " + json.dumps(k["web"]))
        self.assertEqual(k["store"]["tabWidgets"]["on"], {"ctx": True, "hotkey": False}, "the bar's flag was written back on, the hot key's off: " + json.dumps(k["store"]))
        g = r["afterGrey"]
        self.assertTrue(r["dotOpt"]["present"] and r["dotOpt"]["picked"], json.dumps(r["dotOpt"]))
        self.assertEqual(r["dotOpt"]["labels"], ["Hide when idle", "Grey dot when idle"], "the option's two choices as a house picker")
        self.assertEqual(g["strip"]["store"]["tabWidgets"]["opts"], {"dot": {"idle": "grey"}}, json.dumps(g["strip"]["store"]))
        for t in g["strip"]["tabs"]:
            self.assertEqual(t["dot"]["cls"], "tab-dot idle", "the idle tabs wear the quiet grey dot now: " + json.dumps(t["dot"]))
            self.assertEqual(t["dot"]["visibility"], "visible", json.dumps(t["dot"]))
            self.assertLess(float(t["dot"]["opacity"]), 0.6, "quiet" + json.dumps(t["dot"]))
        self.assertEqual(g["panel"]["rows"][0]["demo"][0]["cls"], "tab-dot", "the demo is a working session: its dot stays gold whatever the idle option")
        self.assertEqual(g["panel"]["rows"][0]["opts"][0]["current"].replace("▾", "").strip(), "Grey dot when idle")

    def test_the_pills_switch_panes_escape_closes_and_the_next_open_remembers_the_tab(self):
        r = self._run()
        c = r["feedPane"]
        self.assertTrue(c["open"], "the panel opened: " + json.dumps(c)[:300])
        shown = [x["pane"] for x in c["panes"] if x["display"] != "none"]
        self.assertEqual(shown, ["feed"], json.dumps(c["panes"]))
        self.assertEqual(c["remembered"], "feed")
        self.assertTrue(c["section"]["paneHidden"], "the Tab widgets section is in the hidden Chat pane now")
        # the follow-up's round one, LOW 1: a pill round trip (Feed, then Chat by its pill) leaves no section room on the Chat pane
        pb = r["pillBack"]
        self.assertEqual([x["pane"] for x in pb["panes"] if x["display"] != "none"], ["chat"], json.dumps(pb["panes"]))
        self.assertEqual(pb["section"]["room"], 0, "the Chat pane comes back with no room left behind: " + json.dumps(pb["section"]))
        self.assertEqual(pb["section"]["scrollTop"], 0, "…at its top: " + json.dumps(pb["section"]))
        a = r["reask"]
        self.assertEqual([x["pane"] for x in a["panes"] if x["display"] != "none"], ["chat"], "the glyph on an open panel switches back to Chat: " + json.dumps(a["panes"]))
        self._assert_scrolled_to_the_section(a, "\n  " + json.dumps(a["section"]))
        self.assertFalse(r["afterEscape"]["shellOpen"], "Escape closed the settings (the shell's chain)")
        self.assertFalse(r["afterEscape"]["panel"]["open"])
        ro = r["reopen"]
        self.assertTrue(ro["open"], "the rail's gear reopened it")
        self.assertEqual([x["pane"] for x in ro["panes"] if x["display"] != "none"], ["chat"], "…on the remembered tab (Chat was picked last)")
        # round two, LOW 2 and 7: a plain open (no section) starts at the card's top, and the earlier ask's observer never fires again
        self.assertEqual(ro["section"]["scrollTop"], 0, "a plain open resets the card; no stale section scroll: " + json.dumps(ro["section"]))

    def test_a_tall_window_lands_the_head_under_the_padding_too(self):
        # the follow-up's round one, MEDIUM: below its cap the card grew under the room and the head stopped 152px short at a
        # 1200px window; the room is sized to the card's cap now, so the first open and a re-ask land the head at the top
        r = self._run(); t = r["tall"]
        self.assertTrue(r["tallLanded"] and t["reaskLanded"], "both landings marked: " + json.dumps([r["tallLanded"], t["reaskLanded"]]))
        for k in ("open", "reask"):
            sec = t[k]
            table = "\n  " + json.dumps(sec)
            self.assertIsNotNone(sec, k + ": the tall scene ran" + table)
            self.assertGreaterEqual(sec["viewportH"], 1200, table)
            self.assertLess(abs(sec["top"] - (sec["cardTop"] + sec["pad"])), 3, k + ": the head sits under the card's padding at 1200px" + table)

    def test_the_ask_stands_across_the_browsers_own_scrolls_and_ends_only_on_the_users_input(self):
        # round two, MEDIUM: a shorter window (Chrome's anchoring nudges the scroll after the settle) and a taller window (the browser
        # clamps the scroll before the resize observation) both re-land the head and re-room; a real wheel over the card ends the ask,
        # so a growth after it lands nothing
        t = self._run()["tall"]
        for k in ("shorter", "taller"):
            sc = t[k]; table = "\n  " + k + ": " + json.dumps(sc)
            self.assertTrue(sc["landed"], k + ": the ask re-landed after the resize" + table)
            self.assertLess(abs(sc["sec"]["top"] - (sc["sec"]["cardTop"] + sc["sec"]["pad"])), 3, k + ": the head under the padding again" + table)
            self.assertGreater(sc["sec"]["room"], 0, k + ": re-roomed" + table)
        self.assertLess(t["shorter"]["sec"]["viewportH"], t["taller"]["sec"]["viewportH"], json.dumps([t["shorter"]["sec"]["viewportH"], t["taller"]["sec"]["viewportH"]]))
        w = t["wheel"]; table = "\n  wheel: " + json.dumps(w)
        self.assertGreaterEqual(abs(w["afterWheel"]["top"] - (w["afterWheel"]["cardTop"] + w["afterWheel"]["pad"])), 3, "the wheel moved the head off the top" + table)
        self.assertFalse(w["landedAfterGrowth"], "the ask ended on the user's input: a growth after it lands nothing" + table)
        self.assertLessEqual(abs(w["sec"]["scrollTop"] - w["afterWheel"]["scrollTop"]), 1, "the card stays where the wheel put it (round four)" + table)

    def test_a_key_scroll_after_a_click_in_the_card_ends_the_ask(self):
        # round three, MEDIUM: the inputs were bound to the card, which has no tabindex, so PageUp after a click in it targeted BODY,
        # the ask stood, and the next size change threw the user's scroll away (the head 594 off after the key, 0.5 after the resize);
        # the inputs are read on the window now, a key counting when the card is the scroll focus
        r = self._run()["tall"]["r3"]; k = r["key"]; table = "\n  key: " + json.dumps(k)
        self.assertTrue(r["keyLanded"] and r["keyStanding"], "the ask landed and stood (a size change re-landed) before the key" + table)
        self.assertLess(k["afterKey"]["scrollTop"], k["beforeKey"]["scrollTop"], "PageUp scrolled the card" + table)
        self.assertFalse(k["landedAfterResize"], "a size change after the user's key lands nothing" + table)
        self.assertLessEqual(abs(k["sec"]["scrollTop"] - k["afterKey"]["scrollTop"]), 1, "the card stays where the key put it" + table)
        self.assertGreaterEqual(abs(k["sec"]["top"] - (k["sec"]["cardTop"] + k["sec"]["pad"])), 3, "the head stays off the top" + table)

    def test_the_asks_own_landing_echo_is_never_the_users_scroll(self):
        # round three, LOW 1: a press on a row within 120 ms of the ask's own re-land made its echo read as the user's scroll (the ask
        # died at 0 and 60 ms after an input); the ask's writes are marked and their one echo consumed
        r = self._run()["tall"]["r3"]; e = r["echo"]; table = "\n  echo: " + json.dumps(e)
        self.assertTrue(r["echoLanded"], table)
        self.assertEqual(e["afterChange"]["mark"], "tabwidgets", "the re-land's mark survives its own echo inside the input window" + table)
        self.assertEqual(e["restored"], "tabwidgets", "the ask stands: a second size change re-lands" + table)

    def test_a_lost_release_ends_with_the_pages_focus_or_visibility(self):
        # round three, LOW 2: a page put behind another mid-press gets neither pointerup nor pointercancel, and the hold made the next
        # scroll of any origin end the ask; blur and visibilitychange clear it
        r = self._run()["tall"]["r3"]; b = r["blur"]; table = "\n  blur: " + json.dumps(b)
        self.assertTrue(r["blurLanded"], table)
        # headless Chromium hides its scrollbars (the gutter measures 0 here, printed as gw), so the probe's press stands for the
        # gutter by its offsets: clientLeft + clientWidth + half the gutter, beyond the client box, which is all scrollerGrab reads
        self.assertEqual(b["afterChange"]["mark"], "tabwidgets", "the ask stands after the lost release: the size change re-lands" + table)
        self.assertEqual(b["restored"], "tabwidgets", table)

    def test_a_press_on_the_cards_padding_is_no_grab(self):
        # round three, LOW 2: the hold latched on any press whose target was the card (its padding), so an ordinary click on the
        # card's edge outlived the input window as a standing hold; only the gutter latches (landing-settle's scrollerGrab)
        r = self._run()["tall"]["r3"]; p = r["pad"]; table = "\n  pad: " + json.dumps(p)
        self.assertTrue(r["padLanded"], table)
        self.assertEqual(p["afterChange"]["mark"], "tabwidgets", "no hold from a press on the padding: the size change re-lands" + table)
        self.assertEqual(p["restored"], "tabwidgets", table)

    def test_a_landings_echo_is_the_frames_move_or_no_debt_at_all(self):
        # round four, MEDIUM 1: go() dropped the room to measure (the card clamped 594 to 0) and landed it back, and the ledger read the
        # clamped intermediate as a move: a debt no scroll event paid, so the user's first real scroll after every landing was eaten
        # (a wheel tick moved the card 594 to 474 with the ask standing, and the next size change re-landed it). The move is the
        # frame's now, and an unpaid debt is forgiven two frames on
        r = self._run()["tall"]["r3"]; d = r["debt"]; table = "\n  debt: " + json.dumps(d)
        self.assertTrue(r["debtLanded"], table)
        self.assertEqual(d["relanded"], "tabwidgets", "the size change re-landed before the wheel" + table)
        self.assertIsNone(d["afterWheel"]["mark"], "the first scroll with the user's evidence after a landing ends the ask" + table)
        self.assertIsNone(d["landedAfterChange"], "a size change after it lands nothing" + table)
        self.assertLessEqual(abs(d["scrollTop"] - d["afterWheel"]["scrollTop"]), 1, "the card stays where the wheel put it" + table)

    def test_a_key_after_the_focus_on_a_checkbox_row_ends_the_ask(self):
        # round four, MEDIUM 2: any INPUT counted as a field, so PageUp after a click on a checkbox row scrolled the card with no evidence
        # and the size change re-landed 594 over the user's 0; a field is an element that consumes the scroll keys
        r = self._run()["tall"]["r3"]; b = r["box"]; table = "\n  box: " + json.dumps(b)
        self.assertTrue(r["boxLanded"] and r["boxStanding"], "the ask landed and stood before the key" + table)
        self.assertEqual(b["active"], "INPUT#rs-striprows:checkbox", "the focus sits on the checkbox" + table)
        self.assertLess(b["afterBoxKey"]["scrollTop"], b["beforeBoxKey"]["scrollTop"], "PageUp scrolled the card" + table)
        self.assertFalse(b["landedAfterResize"], "a size change after the user's key lands nothing" + table)
        self.assertLessEqual(abs(b["sec"]["scrollTop"] - b["afterBoxKey"]["scrollTop"]), 1, "the card stays where the key put it" + table)

    def test_the_innermost_content_pixel_column_is_no_gutter_grab(self):
        # round four, LOW 2: the grab's offsets were measured from the border box against the padding box's clientWidth, so a press at
        # clientLeft + clientWidth - 1 read as the gutter; the offsets come from the padding box now
        r = self._run()["tall"]["r3"]; e = r["edge"]; table = "\n  edge: " + json.dumps(e)
        self.assertTrue(r["edgeLanded"], table)
        self.assertEqual(e["afterChange"]["mark"], "tabwidgets", "no hold from a press inside the client box: the size change re-lands" + table)
        self.assertEqual(e["restored"], "tabwidgets", table)


if __name__ == "__main__":
    unittest.main()
