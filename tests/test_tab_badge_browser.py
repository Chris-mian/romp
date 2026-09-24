#!/usr/bin/env python3
"""THE TAB STATE BADGE (plans/tab-state-badge.md; the user 2026-09-21, the numbered dot chosen 2026-09-21 evening) on the
served chat page and the phone picker, in BOTH themes, driven by Playwright over a hermetic kernel. Badge mode is the
per-browser `tabStateBadge` setting. It is the DEFAULT since 2026-09-23, so the desktop strip context runs UNSEEDED (the served default, pinned here); the ring context seeds false and the phone context seeds true, before the page loads. Three synthetic notes-api sessions
sit in the Needs-you state with 1, 3 and 12 needs-you cards (that many blocked root goals), and one idle control with none.

What it reads, computed by the real page, never inferred from source:
  * BADGE MODE: each needs-you tab wears the top-right magenta dot carrying its black count (1, 3, 12), NOT the magenta
    ring; the 12 dot is a wider pill than the 1 dot, and every dot's rect sits inside its tab's rect at the top-right; the
    idle control wears no dot; the dot's background is the Needs-you token in each theme.
  * NOTHING MOVED: a needs-you tab's width and its label's left edge are the same with the badge off and on (the absolute
    dot joins no flow).
  * RING MODE (badge off, a chosen-off browser, byte-identical to the pre-badge strip): the same needs-you tab wears the dashed magenta ring in the token
    and NO dot.
  * THE PHONE (a coarse-pointer context): under badge mode the current-session chip (#mcur) and a needs-you row (.mrow)
    each wear the .m-badge dot with the count, and the row does NOT wear the .ask dashed treatment (the ring gave way).

Red at the base (a tree with no badge code): no dot, no count, no .m-badge: the badge-mode legs fail. TAB_BADGE_DIST=<dir>
serves another tree's UI bundle. Skips LOUDLY without the extension deps or a Playwright browser (CI sets
ROMP_SERVED_TESTS_REQUIRE=1 and installs both, so a skip there is a failure). Synthetic throughout: placeholder sids,
TESTHOST, invented goal text."""
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
import test_ship_reship_served as _lab  # noqa: E402  the lab kernel's environment

# the four synthetic sessions: three in the Needs-you state with 1/3/12 cards, one idle control with none
SESS = [("one", 1), ("few", 3), ("many", 12), ("calm", 0), ("over", 120)]
SIDS = {n: "%s-1111-2222-3333-444444444444" % (chr(ord("a") + i) * 8) for i, (n, _) in enumerate(SESS)}
PALETTE = {"one": ("#9cd2ff", "#0c1a2e"), "few": ("#1EA1EB", "#ffffff"), "many": ("#54B204", "#ffffff"), "calm": ("#c98cff", "#1a0c2e"), "over": ("#e08020", "#1a0c00")}
TOKEN = {"dark": "rgb(217, 70, 239)", "light": "rgb(162, 28, 175)"}   # --st-needs-bg: #d946ef and #a21caf
AMBER = {"dark": "rgb(230, 126, 34)", "light": "rgb(156, 74, 12)"}   # --st-retrying-bg: #e67e22 and #9C4A0C, the retrying left dot


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def blocked_store(sid, k, t0):
    """A goal store with k blocked ROOT goals, each its own needs-you card (one card per root, _entry_cards). Each carries
    a diary `block` event so the boot rollup re-derives the blocked flag from the log (else it clears before the first
    frame, as the colour lab's note records)."""
    nodes, status = {}, {}
    for i in range(k):
        gid = "%s:g%d" % (sid, i)
        nodes[gid] = {"id": gid, "text": "pick the option for fixture group %d" % i, "parentId": None,
                      "nodeComplete": False, "blocked": True, "blockWhy": "which option for group %d?" % i,
                      "cleared": False, "trail": [], "t": t0,
                      "log": [{"ev_t": t0 + 60, "src": "planner", "kind": "block", "why": "asked which option for group %d" % i, "at": t0 + 60}]}
        status[gid] = "blocked"
    last = "%s:g%d" % (sid, k - 1)
    return {"rompUuid": sid, "seq": k + 1, "lastNode": last, "closedTurns": [], "nodes": nodes, "placements": {}, "status": status}


DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));
let browser;
try { browser = await chromium.launch(); } catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
const errors = [];
const out = { badge: {}, ring: {}, moved: {}, phone: {}, gearDemo: {} };
const BADGE = () => localStorage.setItem("romp:settings", JSON.stringify({ tabStateBadge: true }));
const RING = () => localStorage.setItem("romp:settings", JSON.stringify({ tabStateBadge: false }));
const setTheme = (p, t) => p.evaluate((t) => document.body.classList.toggle("theme-light", t === "light"), t);
const themes = ["dark", "light"];
const rect = (r) => ({ top: r.top, right: r.right, bottom: r.bottom, left: r.left, width: r.width, height: r.height });

// ── the desktop strip at the DEFAULT (no seed): the badge is ON by default since 2026-09-23, so the served strip's
//    default path is pinned here (before the flip this context showed the ring and the .tab-badge wait below would red) ──
const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
const page = await ctx.newPage(); page.on("pageerror", (e) => errors.push("desktop: " + String(e).slice(0, 200)));
await page.goto(cfg.chat);
await page.waitForSelector('#tabs .tab[data-id="' + cfg.one + '"] .tab-badge', { timeout: 60000 }).catch(async () => {
  errors.push("badge: no dot on the needs-you tab: " + (await page.evaluate(() => Array.from(document.querySelectorAll("#tabs .tab[data-id]")).map((t) => t.dataset.id.slice(0, 8) + ":" + t.className).join(" | "))));
});
await page.waitForTimeout(400);
await page.waitForFunction((id) => { const b = document.querySelector('#tabs .tab[data-id="' + id + '"] .tab-badge'); return !!b && b.textContent === "99+"; }, cfg.over, { timeout: 60000 }).catch(() => errors.push("badge: the over-99 desktop tab never showed 99+"));
const readBadge = (p) => p.evaluate((ids) => {
  const one = (id) => {
    const t = document.querySelector('#tabs .tab[data-id="' + id + '"]'); if (!t) return null;
    const b = t.querySelector(".tab-badge"); const tr = t.getBoundingClientRect();
    const lbl = t.querySelector(".tab-label, .tab-name, .tab-title");
    const R = (e) => { const r = e.getBoundingClientRect(); return { top: r.top, right: r.right, bottom: r.bottom, left: r.left, width: r.width, height: r.height }; };
    return { cls: t.className, tab: R(t), labelLeft: lbl ? lbl.getBoundingClientRect().left : null,
             badge: b ? { text: b.textContent, label: b.getAttribute("aria-label"), rect: R(b), bg: getComputedStyle(b).backgroundColor, color: getComputedStyle(b).color,
                          radius: getComputedStyle(b).borderRadius } : null };
  };
  const o = {}; for (const [k, id] of Object.entries(ids)) o[k] = one(id); return o;
}, cfg.ids);
for (const t of themes) { await setTheme(page, t); await page.waitForTimeout(150); out.badge[t] = await readBadge(page); }
// (item 10, the second contributor on PR 2017; the shape cue, 2026-09-23) a probe: a bare `.tab-dot retrying` span is a
// HOLLOW amber ring, so its computed FILL is transparent and the amber rides the inset box-shadow (the outline): the
// left-dot amber and its distinct shape are exercised without seeding a hard-to-mint retrying session.
out.retryProbe = {};
for (const t of themes) { await setTheme(page, t); await page.waitForTimeout(100);
  out.retryProbe[t] = await page.evaluate(() => { const p = document.createElement("span"); p.className = "tab-dot retrying"; document.body.appendChild(p); const cs = getComputedStyle(p); const r = { bg: cs.backgroundColor, shadow: cs.boxShadow }; p.remove(); return r; }); }

// ── (the user 2026-09-23, who wanted the badge a pixel lower and further from the edge) the count badge's inset from the
//    tab's TOP and RIGHT edges, read in DENSE chrome too (a body class, dense-chrome.ts applyDenseChrome), so the dense
//    1px inset (restored 2026-09-24) is pinned beside the normal 3px. The desktop context carries no keycap, so this is the clean corner
//    geometry; the class is pure CSS, toggled on the open page, then restored before the geometry reads below. ──
out.badgeDense = {};
for (const t of themes) { await setTheme(page, t); await page.evaluate(() => document.body.classList.add("dense-chrome")); await page.waitForTimeout(150); out.badgeDense[t] = await readBadge(page); }
await page.evaluate(() => document.body.classList.remove("dense-chrome"));

const geomEval = (id) => { const t = document.querySelector('#tabs .tab[data-id="' + id + '"]'); const lbl = t.querySelector(".tab-label, .tab-name, .tab-title"); return { w: t.getBoundingClientRect().width, labelLeft: lbl ? lbl.getBoundingClientRect().left : null }; };
await setTheme(page, "dark"); await page.waitForTimeout(120);
const geomOn = await page.evaluate(geomEval, cfg.one);

// ── RING mode (badge off), a chosen-off browser (byte-identical to the pre-badge strip): a SEPARATE context with its own localStorage, so no reload can
//    fight the init script. Same viewport and sessions, so the tab layout is comparable for "nothing moved". ──
const ctxOff = await browser.newContext({ viewport: { width: 1400, height: 900 } });
await ctxOff.addInitScript(RING);   // explicit false: a chosen-off browser keeps ring mode under the badge default (since 2026-09-23)
const off = await ctxOff.newPage(); off.on("pageerror", (e) => errors.push("ring: " + String(e).slice(0, 200)));
await off.goto(cfg.chat);
await off.waitForFunction((id) => { const t = document.querySelector('#tabs .tab[data-id="' + id + '"]'); return !!t && t.classList.contains("ring-waiting-on-you"); }, cfg.one, { timeout: 60000 }).catch(async () => {
  errors.push("ring: no magenta ring on the needs-you tab with the badge off: " + (await off.evaluate((id) => { const t = document.querySelector('#tabs .tab[data-id="' + id + '"]'); return t ? t.className : "no tab"; }, cfg.one)));
});
await off.waitForTimeout(300);
await setTheme(off, "dark"); await off.waitForTimeout(120);
const geomOff = await off.evaluate(geomEval, cfg.one);
out.moved = { on: geomOn, off: geomOff };
for (const t of themes) { await setTheme(off, t); await off.waitForTimeout(150);
  out.ring[t] = await off.evaluate((id) => { const tab = document.querySelector('#tabs .tab[data-id="' + id + '"]'); const cs = getComputedStyle(tab);
    return { cls: tab.className, badge: !!tab.querySelector(".tab-badge"), outlineColor: cs.outlineColor, outlineStyle: cs.outlineStyle }; }, cfg.one); }

// ── (the user 2026-09-23) THE KEYCAP + BADGE OVERLAP: a tab showing BOTH the hot-key keycap (.tab-key, a right-end
//    in-flow flex item) AND a non-empty count badge (.tab-badge, absolute at the top-right corner) must not let the
//    badge overpaint the keycap. Its own context seeds a hot key on the 1-, 12- and 120-card needs-you sessions
//    (romp:tabkeys names the sid so tabHotkey looks it up; romp:keys carries the chord override effectiveChord reads)
//    plus badge mode, and reads the keycap and badge rects in both themes and both chromes (normal + dense-chrome). ──
out.hotkey = { normal: {}, dense: {} };
const HKIDS = [cfg.one, cfg.many, cfg.over, cfg.calm];   // + the idle `calm` tab: a keycap tab with NO count, for the no-count-side padding (the keycap-width fix)
const hkCtx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
await hkCtx.addInitScript((ids) => {
  try {
    localStorage.setItem("romp:settings", JSON.stringify({ tabStateBadge: true }));
    localStorage.setItem("romp:tabkeys", JSON.stringify(Object.fromEntries(ids.map((id) => [id, true]))));
    localStorage.setItem("romp:keys", JSON.stringify(Object.fromEntries(ids.map((id, i) => ["session.hotkey." + id, "Ctrl+Shift+" + (i + 1)]))));
  } catch (e) {}
}, HKIDS);
const hk = await hkCtx.newPage(); hk.on("pageerror", (e) => errors.push("hotkey: " + String(e).slice(0, 200)));
await hk.goto(cfg.chat);
await hk.waitForSelector('#tabs .tab[data-id="' + cfg.one + '"] .tab-badge:not(:empty)', { timeout: 60000 }).catch(() => errors.push("hotkey: the needs-you tab never took a count badge"));
await hk.waitForSelector('#tabs .tab[data-id="' + cfg.one + '"] .tab-key', { timeout: 60000 }).catch(async () => {
  errors.push("hotkey: no keycap on the needs-you tab (romp:tabkeys/romp:keys seeded): " + (await hk.evaluate((id) => { const t = document.querySelector('#tabs .tab[data-id="' + id + '"]'); return t ? (t.className + " kids=" + Array.from(t.children).map((c) => c.className).join(",")) : "no tab"; }, cfg.one)));
});
const readHK = (ids) => hk.evaluate((ids) => {
  const R = (e) => { if (!e) return null; const r = e.getBoundingClientRect(); return { top: r.top, right: r.right, bottom: r.bottom, left: r.left, width: r.width, height: r.height }; };
  const one = (id) => {
    const t = document.querySelector('#tabs .tab[data-id="' + id + '"]'); if (!t) return null;
    const key = t.querySelector(".tab-key"); const badge = t.querySelector(".tab-badge"); const close = t.querySelector(".tab-close");
    return { tab: R(t), key: R(key), keyText: key ? key.textContent : null, badge: R(badge), badgeText: badge ? badge.textContent : null,
             close: R(close), padRight: getComputedStyle(t).paddingRight };
  };
  const o = {}; for (const id of ids) o[id] = one(id); return o;
}, ids);
for (const t of themes) {
  await setTheme(hk, t);
  await hk.evaluate(() => document.body.classList.remove("dense-chrome")); await hk.waitForTimeout(150);
  out.hotkey.normal[t] = await readHK(HKIDS);
  await hk.evaluate(() => document.body.classList.add("dense-chrome")); await hk.waitForTimeout(150);
  out.hotkey.dense[t] = await readHK(HKIDS);
}
await hkCtx.close();

// ── the phone (a coarse-pointer context, its own localStorage seeded to badge mode) ──
const phoneCtx = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true, deviceScaleFactor: 3 });
await phoneCtx.addInitScript(BADGE);
const phone = await phoneCtx.newPage(); phone.on("pageerror", (e) => errors.push("phone: " + String(e).slice(0, 200)));
await phone.goto(cfg.chat);
// the picker scrapes the (hidden) desktop strip; open the list and pick a needs-you session so #mcur is one too
await phone.waitForFunction((id) => { const t = document.querySelector('#tabs .tab[data-id="' + id + '"]'); return !!t && !!t.querySelector(".tab-badge"); }, cfg.one, { timeout: 60000 }).catch(() => errors.push("phone: the desktop needs-you tab never took a badge"));
await phone.tap("#mcur");
await phone.waitForSelector("#mlist.open", { timeout: 10000 }).catch(() => errors.push("phone: the picker never opened"));
await phone.waitForFunction((id) => !!document.querySelector('#mlist .mrow[data-id="' + id + '"] .m-badge'), cfg.few, { timeout: 10000 }).catch(() => errors.push("phone: a needs-you row never took the .m-badge"));
await phone.waitForFunction((id) => !!document.querySelector('#mlist .mrow[data-id="' + id + '"] .m-badge'), cfg.over, { timeout: 10000 }).catch(() => errors.push("phone: the over-99 row never took the .m-badge"));
await phone.tap('#mlist .mrow[data-id="' + cfg.few + '"]');   // make a needs-you session the current one
await phone.waitForFunction(() => { const c = document.getElementById("mcur"); return !!c && !!c.querySelector(".m-badge"); }, null, { timeout: 10000 }).catch(() => errors.push("phone: #mcur never took the .m-badge after picking a needs-you session"));
await phone.tap("#mcur");
await phone.waitForSelector("#mlist.open", { timeout: 10000 }).catch(() => {});
for (const t of themes) {
  await setTheme(phone, t); await phone.waitForTimeout(200);
  out.phone[t] = await phone.evaluate((ids) => {
    const cur = document.getElementById("mcur"); const cb = cur ? cur.querySelector(".m-badge") : null;
    const row = document.querySelector('#mlist .mrow[data-id="' + ids.few + '"]'); const rb = row ? row.querySelector(".m-badge") : null;
    const rowOne = document.querySelector('#mlist .mrow[data-id="' + ids.one + '"]'); const rbOne = rowOne ? rowOne.querySelector(".m-badge") : null;
    const rowOver = document.querySelector('#mlist .mrow[data-id="' + ids.over + '"]'); const rbOver = rowOver ? rowOver.querySelector(".m-badge") : null;
    const R = (e) => { if (!e) return null; const r = e.getBoundingClientRect(); return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width }; };
    const cv = cur ? cur.querySelector(".cv") : null; const mclose = row ? row.querySelector(".mclose") : null;   // item 2: the chevron and the close must sit to the RIGHT of the pill, never under it
    return { curBadge: cb ? cb.textContent : null, curBg: cb ? getComputedStyle(cb).backgroundColor : null, curAsk: !!cur && cur.classList.contains("ask"),
             curRole: cb ? cb.getAttribute("role") : null, curLabel: cb ? cb.getAttribute("aria-label") : null,
             rowBadge: rb ? rb.textContent : null, rowBg: rb ? getComputedStyle(rb).backgroundColor : null, rowAsk: !!row && row.classList.contains("ask"),
             rowRole: rb ? rb.getAttribute("role") : null, rowLabel: rb ? rb.getAttribute("aria-label") : null,
             oneRowBadge: rbOne ? rbOne.textContent : null, oneRowLabel: rbOne ? rbOne.getAttribute("aria-label") : null,
             overRowBadge: rbOver ? rbOver.textContent : null, overRowLabel: rbOver ? rbOver.getAttribute("aria-label") : null,
             curPill: R(cb), curChevron: R(cv), rowPill: R(rb), rowClose: R(mclose) };
  }, cfg.ids);
  // (PR 2080 review HIGH) the phone's retrying leading dot is the same HOLLOW amber ring as the desktop: a bare
  // `.wd retrying` injected into #mcur (where the mobile picker CSS scopes it) computes a transparent fill and the amber
  // on the inset box-shadow, so form not colour tells it from the filled working/awaiting dots on the phone too.
  out.phoneRetryProbe = out.phoneRetryProbe || {};
  out.phoneRetryProbe[t] = await phone.evaluate(() => {
    const cur = document.getElementById("mcur"); if (!cur) return null;
    const w = document.createElement("span"); w.className = "wd retrying"; cur.appendChild(w);
    const cs = getComputedStyle(w); const r = { bg: cs.backgroundColor, shadow: cs.boxShadow }; w.remove(); return r;
  });
}
// ── (round-one MEDIUM + LOW 2) the GEAR PREVIEW and its own switch on the dashboard's settings page. openGear opens
//    the gear from the strip's glyph at the Tab strip section over a seeded store and reads, in both themes: the three
//    ring demos' computed styles (the demos, run through applyTabBadgeMode when the badge is on, must render the badge
//    vocabulary the strip does; the gear's hosts load feed.css + gear.css, never styles.css, so a rule missing there
//    leaves the demo unstyled) and the state-badge switch (#rs-statebadge). Two opens: a store that NEVER chose (empty:
//    the badge is the DEFAULT, so the demos paint the badge and the switch reads ON) and a stored false (the switch
//    reads OFF). The switch reflects `!== false`, the same guard the strip reads.
async function openGear(seed) {
  const gctx = await browser.newContext({ viewport: { width: 1200, height: 900 } });
  await gctx.addInitScript((v) => { try { localStorage.setItem("romp:settings", JSON.stringify(v)); } catch (e) {} }, seed);
  const d = await gctx.newPage(); d.on("pageerror", (e) => errors.push("gear: " + String(e).slice(0, 200)));
  await d.goto(cfg.url);
  await d.waitForSelector("#rail-gear", { timeout: 20000 }).catch(() => errors.push("gear: the dashboard never painted its rail"));
  let gchat = d.frames().find((f) => f.url().includes("/chat"));
  for (let i = 0; i < 100 && !gchat; i++) { await d.waitForTimeout(100); gchat = d.frames().find((f) => f.url().includes("/chat")); }
  if (!gchat) { errors.push("gear: no chat frame on the dashboard"); await gctx.close(); return {}; }
  await gchat.waitForSelector("#tabs .tab-strip-end .tab-widgets-gear", { timeout: 30000 }).catch(() => errors.push("gear: the strip never grew its gear glyph"));
  await gchat.click("#tabs .tab-strip-end .tab-widgets-gear");
  await d.waitForFunction(() => document.body.classList.contains("settings-open"), null, { timeout: 20000 }).catch(() => errors.push("gear: the settings never opened from the glyph"));
  let gset = d.frames().find((f) => f.url().includes("/settings"));
  for (let i = 0; i < 50 && !gset; i++) { await d.waitForTimeout(100); gset = d.frames().find((f) => f.url().includes("/settings")); }
  if (!gset) { errors.push("gear: no settings frame opened from the glyph"); await gctx.close(); return {}; }
  await gset.waitForSelector("#rsettings:not([hidden])", { timeout: 15000 }).catch(() => {});
  await gset.waitForSelector('#rs-rings .rs-widget[data-widget="ring-waiting-on-you"] .rs-widget-demo .tab', { timeout: 15000 }).catch(() => errors.push("gear: the ring demos never rendered"));
  const readGear = () => gset.evaluate(() => {
    const probe = document.createElement("span"); document.body.appendChild(probe);
    const tokens = {};
    for (const [k, expr] of [["needs", "var(--st-needs-bg, #d946ef)"], ["retrying", "var(--st-retrying-bg, #e67e22)"], ["awaiting", "var(--st-awaiting-bg, #c0392b)"]]) { probe.style.color = expr; tokens[k] = getComputedStyle(probe).color; }
    probe.remove();
    const R = (e) => { const r = e.getBoundingClientRect(); return { top: r.top, right: r.right, bottom: r.bottom, left: r.left, width: r.width, height: r.height }; };
    const rows = {};
    for (const r of document.querySelectorAll("#rs-rings .rs-widget[data-widget]")) {
      const demo = r.querySelector(".rs-widget-demo .tab"); if (!demo) continue;
      const cs = getComputedStyle(demo); const badge = demo.querySelector(".tab-badge"); const dot = demo.querySelector(".tab-dot.retrying"); const key = demo.querySelector(".tab-key");
      rows[r.dataset.widget] = { cls: demo.className, tab: R(demo), outlineStyle: cs.outlineStyle, outlineColor: cs.outlineColor, key: key ? R(key) : null,
        badge: badge ? { bg: getComputedStyle(badge).backgroundColor, position: getComputedStyle(badge).position, rect: R(badge), text: badge.textContent } : null,
        dot: dot ? { bg: getComputedStyle(dot).backgroundColor, shadow: getComputedStyle(dot).boxShadow, visibility: getComputedStyle(dot).visibility } : null };
    }
    const tsb = document.getElementById("rs-statebadge");   // the badge's OWN switch (a checkbox styled as a slider): its checked state must track the setting the strip reads
    return { tokens, rows, sw: tsb ? { checked: !!tsb.checked } : null };
  });
  const byTheme = {};
  for (const t of themes) { await setTheme(gset, t); await setTheme(d, t); await d.waitForTimeout(200); byTheme[t] = await readGear(); }
  await gctx.close();
  return byTheme;
}
out.gearDemo = await openGear({});                            // never chose: the badge is the default (demos + switch ON)
out.gearSwitchOff = await openGear({ tabStateBadge: false }); // a chosen off: the switch reads OFF
// ── (M) the count moves LIVE without a reload (plans/tab-state-badge.md, test 7): a needs-you card added climbs the
//    number, a card cleared drops it, on the OPEN badge-mode page, no reload. The count keys its own chat-signature
//    component and its own compare-and-wake, so a store change reaches the tab even when the membership set is unchanged.
await setTheme(page, "dark"); await page.waitForTimeout(150);
const liveBadge = () => page.evaluate((id) => { const b = document.querySelector('#tabs .tab[data-id="' + id + '"] .tab-badge'); return b ? b.textContent : null; }, cfg.one);
out.live = { start: await liveBadge() };
fs.writeFileSync(cfg.oneGoalPath, cfg.oneStore2);   // a SECOND blocked root goal -> count 1 to 2
await page.waitForFunction((id) => { const b = document.querySelector('#tabs .tab[data-id="' + id + '"] .tab-badge'); return !!b && b.textContent === "2"; }, cfg.one, { timeout: 40000 }).catch(() => errors.push("live: the badge never climbed to 2 after a card was added (no reload)"));
out.live.added = await liveBadge();
fs.writeFileSync(cfg.oneGoalPath, cfg.oneStore1);   // clear it -> count 2 to 1
await page.waitForFunction((id) => { const b = document.querySelector('#tabs .tab[data-id="' + id + '"] .tab-badge'); return !!b && b.textContent === "1"; }, cfg.one, { timeout: 40000 }).catch(() => errors.push("live: the badge never dropped back to 1 after the card cleared"));
out.live.cleared = await liveBadge();

// ── the keycap-widen GATE (the keycap-width fix 2026-09-24, T262g): the reserve sits on the keycap ALONE under a
//    strip-level class (#tabs.badge-keycap-room) the strip carries ONLY in badge mode with the Needs-you widget on. So a
//    keycap tab's right padding is the reserved 21px (17px dense) in badge mode WHETHER OR NOT a count shows (the idle
//    `calm` keycap tab equals the counted `one`), and the bare 7px (5px dense) in ring mode AND with the Needs-you widget
//    off (no reserved room, the pre-badge strip). `calm` (no count) in badge mode is the red-first case: 7px/5px at the
//    base, where the reserve was gated on the non-empty badge, so a keycap tab's width flipped as a count appeared. ──
out.gate = {};
const readPad = (p, id) => p.evaluate((id) => { const t = document.querySelector('#tabs .tab[data-id="' + id + '"]'); const bar = document.getElementById("tabs");
  return { pad: t ? getComputedStyle(t).paddingRight : null, room: bar ? bar.classList.contains("badge-keycap-room") : null,
           key: !!(t && t.querySelector(".tab-key")), badge: !!(t && t.querySelector(".tab-badge:not(:empty)")) }; }, id);
const GATE_TABKEYS = JSON.stringify({ [cfg.one]: true, [cfg.calm]: true });
const GATE_KEYS = JSON.stringify({ ["session.hotkey." + cfg.one]: "Ctrl+Shift+1", ["session.hotkey." + cfg.calm]: "Ctrl+Shift+2" });
for (const [label, sset] of [["badge", { tabStateBadge: true }], ["ring", { tabStateBadge: false }], ["widgetOff", { tabStateBadge: true, tabWidgets: { on: { "ring-waiting-on-you": false } } }]]) {
  const gc = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  await gc.addInitScript((a) => { try {
    localStorage.setItem("romp:settings", JSON.stringify(a.sset));
    localStorage.setItem("romp:tabkeys", a.tabkeys);
    localStorage.setItem("romp:keys", a.keys);
  } catch (e) {} }, { sset, tabkeys: GATE_TABKEYS, keys: GATE_KEYS });
  const gp = await gc.newPage(); gp.on("pageerror", (e) => errors.push("gate/" + label + ": " + String(e).slice(0, 200)));
  await gp.goto(cfg.chat);
  await gp.waitForSelector('#tabs .tab[data-id="' + cfg.calm + '"] .tab-key', { timeout: 60000 }).catch(() => errors.push("gate/" + label + ": no keycap on the idle tab"));
  out.gate[label] = {};
  for (const t of themes) { await setTheme(gp, t);
    await gp.evaluate(() => document.body.classList.remove("dense-chrome")); await gp.waitForTimeout(120);
    out.gate[label][t] = { normal: { one: await readPad(gp, cfg.one), calm: await readPad(gp, cfg.calm) } };
    await gp.evaluate(() => document.body.classList.add("dense-chrome")); await gp.waitForTimeout(120);
    out.gate[label][t].dense = { one: await readPad(gp, cfg.one), calm: await readPad(gp, cfg.calm) };
  }
  await gc.close();
}

// ── nothing moves when a keycap tab's count flips (the keycap-width fix 2026-09-24, T262g): at a narrow, wrapping
//    viewport a keycap tab in badge mode keeps its width AND #tabbar's height when its Needs-you count clears, because the
//    reserve is on the keycap, not the count. RED at this PR's base, where the reserve was gated on the non-empty badge,
//    so the tab's width flipped (21px->7px) as the count cleared and the strip's row count flapped. Own context: badge
//    default + a hot key on `one`; read (tab width, strip height) with the count, clear the count (an empty goal store),
//    read again; restore the store (this is the LAST context, so the default page's live legs above are untouched). ──
out.wrapFlip = {};
const wrapCtx = await browser.newContext({ viewport: { width: 360, height: 900 } });
await wrapCtx.addInitScript((s) => { try {
  localStorage.setItem("romp:tabkeys", s.tabkeys);
  localStorage.setItem("romp:keys", s.keys);
} catch (e) {} }, { tabkeys: JSON.stringify({ [cfg.one]: true }), keys: JSON.stringify({ ["session.hotkey." + cfg.one]: "Ctrl+Shift+1" }) });   // no tabStateBadge seed: the badge is the default
const wp = await wrapCtx.newPage(); wp.on("pageerror", (e) => errors.push("wrap: " + String(e).slice(0, 200)));
await wp.goto(cfg.chat);
await wp.waitForSelector('#tabs .tab[data-id="' + cfg.one + '"] .tab-key', { timeout: 60000 }).catch(() => errors.push("wrap: no keycap on the badge-mode tab"));
await wp.waitForSelector('#tabs .tab[data-id="' + cfg.one + '"] .tab-badge:not(:empty)', { timeout: 60000 }).catch(() => errors.push("wrap: the keycap tab never took a count badge"));
const readWrap = (id) => wp.evaluate((id) => { const t = document.querySelector('#tabs .tab[data-id="' + id + '"]'); const bar = document.getElementById("tabbar");
  return { w: t ? t.getBoundingClientRect().width : null, pad: t ? getComputedStyle(t).paddingRight : null, barH: bar ? bar.getBoundingClientRect().height : null,
           hasBadge: !!(t && t.querySelector(".tab-badge:not(:empty)")) }; }, id);
await setTheme(wp, "dark"); await wp.waitForTimeout(200);
out.wrapFlip.withCount = await readWrap(cfg.one);
fs.writeFileSync(cfg.oneGoalPath, cfg.oneStore0);   // clear the needs-you card -> count 0, the badge goes
await wp.waitForFunction((id) => { const t = document.querySelector('#tabs .tab[data-id="' + id + '"]'); return !!t && !t.querySelector(".tab-badge:not(:empty)"); }, cfg.one, { timeout: 40000 }).catch(() => errors.push("wrap: the badge never cleared after the card was removed"));
await wp.waitForTimeout(200);
out.wrapFlip.noCount = await readWrap(cfg.one);
fs.writeFileSync(cfg.oneGoalPath, cfg.oneStore1);   // restore
await wrapCtx.close();

process.stdout.write("RESULT:" + JSON.stringify({ ...out, errors }) + "\n");
await browser.close();
"""


class TabBadgeServed(unittest.TestCase):
    maxDiff = None

    @classmethod
    def _skip(cls, why):
        if os.environ.get("ROMP_SERVED_TESTS_REQUIRE") == "1":
            raise AssertionError("ROMP_SERVED_TESTS_REQUIRE=1 but the served lab could not run: " + why)
        raise unittest.SkipTest(why)

    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(os.path.join(EXT, "node_modules", "playwright")):
            cls._skip("extension deps absent (npm ci not run here): the served guard needs them")
        cls.lab = tempfile.mkdtemp(prefix="tab-badge-")
        before = os.environ.get("TAB_BADGE_DIST", "")
        if before:
            src = before
        else:
            b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
            if b.returncode != 0:
                cls._skip("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
            src = os.path.join(EXT, "dist")
        dist = os.path.join(cls.lab, "dist")
        copy_dist(src, dist)
        state = os.path.join(cls.lab, "xdg", "romp")
        claude = os.path.join(cls.lab, "claude")
        cwd = os.path.join(cls.lab, "notes-api")
        for d in ("names", "sdk", "states", "goals"):
            os.makedirs(os.path.join(state, d), exist_ok=True)
        Path(state, "session-hosts").write_text("off\n")   # this lab mints its own state root: no session host (repo rule)
        os.makedirs(cwd, exist_ok=True)
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        t0 = int(time.time()) - 3600
        cls.t0 = t0
        for name, k in SESS:
            sid = SIDS[name]
            bg, fg = PALETTE[name]
            Path(state, "names", sid).write_text("%s\t%s\t%s\t%s\n" % (name, cwd, bg, fg))
            Path(state, "sdk", sid + ".json").write_text(json.dumps(
                {"sid": sid, "name": name, "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": sid, "alive": True,
                 "model": "claude-opus-5", "liveModel": "Opus 5"}))
            Path(state, "states", sid + ".jsonl").write_text(json.dumps({"t": t0 + 70, "state": "idle"}) + "\n")
            recs = [{"type": "user", "timestamp": iso(t0), "uuid": "u1", "parentUuid": None, "promptSource": "typed", "sessionId": sid,
                     "message": {"role": "user", "content": "what does the %s session do in notes-api?" % name}},
                    {"type": "assistant", "timestamp": iso(t0 + 5), "uuid": "a1", "parentUuid": "u1", "sessionId": sid,
                     "message": {"role": "assistant", "model": "claude-opus-5", "stop_reason": "end_turn",
                                 "content": [{"type": "text", "text": "It keeps the %s side of the notes-api tidy." % name}]}}]
            Path(proj, sid + ".jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
            if k:
                Path(state, "goals", sid + ".json").write_text(json.dumps(blocked_store(sid, k, t0)))
        # no tag lens narrowing: one flat row of tabs
        Path(state, "timeline-views.json").write_text(json.dumps({"active": "all", "actives": {"chat": {"none": True}}, "tags": []}))
        Path(state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 10}, "seven_day": {"pct": 10}}))
        cls.port, cls.token = _free_port(), "testtok-tabbadge"
        env = _lab.kernel_env(cls.lab, claude, dist, cls.port, cls.token, ROMP_HOST_NAME="TESTHOST")
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
        cls._r = None

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "kernel", None):
            cls.kernel.kill()
            cls.kernel.wait()
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

    def _result(self):
        if getattr(type(self), "_fail", None):
            self.fail(type(self)._fail)
        if self._r is None:
            cfg = os.path.join(self.lab, "cfg.json")
            base = "http://127.0.0.1:%d" % self.port
            ids = {name: SIDS[name] for name, _ in SESS}
            with open(cfg, "w") as f:
                json.dump({"chat": base + "/chat?token=" + self.token, "url": base + "/?token=" + self.token, "token": self.token,
                           "one": SIDS["one"], "few": SIDS["few"], "many": SIDS["many"], "calm": SIDS["calm"], "over": SIDS["over"], "ids": ids,
                           "oneGoalPath": os.path.join(self.lab, "xdg", "romp", "goals", SIDS["one"] + ".json"),
                           "oneStore0": json.dumps({"rompUuid": SIDS["one"], "seq": 1, "lastNode": None, "closedTurns": [], "nodes": {}, "placements": {}, "status": {}}),
                           "oneStore1": json.dumps(blocked_store(SIDS["one"], 1, self.t0)),
                           "oneStore2": json.dumps(blocked_store(SIDS["one"], 2, self.t0))}, f)
            driver = os.path.join(self.lab, "driver.mjs")
            Path(driver).write_text(DRIVER)
            p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=400,
                               env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
            if p.returncode == 3 or "browser-launch-failed" in p.stderr:
                self._skip("no playwright browser on this box")
            line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
            if not line:
                type(self)._fail = "the driver produced no RESULT (stderr: %s; kernel: %s)" % (p.stderr[-2000:], open(self.klog).read()[-1500:])
                self.fail(type(self)._fail)
            type(self)._r = json.loads(line[len("RESULT:"):])
            if os.environ.get("TAB_BADGE_DUMP"):
                Path(os.environ["TAB_BADGE_DUMP"]).write_text(json.dumps(type(self)._r, indent=1) + "\n")
        return self._r

    def test_the_needs_you_dot_carries_the_black_count_in_the_token_at_1_3_and_12_and_the_control_wears_none(self):
        r = self._result()
        self.assertEqual(r["errors"], [], "no page error and every wait resolved")
        for t in ("dark", "light"):
            b = r["badge"][t]
            for name, count in (("one", "1"), ("few", "3"), ("many", "12")):
                d = b[name]["badge"]
                self.assertIsNotNone(d, "%s/%s: the needs-you tab wears the top-right dot" % (t, name))
                self.assertEqual(d["text"], count, "%s/%s: the dot carries its black count" % (t, name))
                self.assertEqual(d["bg"], TOKEN[t], "%s/%s: the dot is the Needs-you magenta token: %r" % (t, name, d))
                want = "rgb(0, 0, 0)" if t == "dark" else "rgb(255, 255, 255)"   # 9px bold TEXT: black clears 4.5:1 on the dark magenta; the light theme inks white (--st-needs-fg) where black is short (plans/tab-state-badge.md)
                self.assertEqual(d["color"], want, "%s/%s: the digit ink (black on dark, white on light): %r" % (t, name, d))
                self.assertNotIn("ring-waiting-on-you", b[name]["cls"].split(), "%s/%s: the magenta ring gave way to the dot" % (t, name))
            self.assertIsNone(b["calm"]["badge"], "%s: the idle control wears no dot" % t)

    def test_the_two_digit_count_widens_the_dot_into_a_pill_and_every_dot_stays_inside_its_tab_at_the_top_right(self):
        r = self._result()
        for t in ("dark", "light"):
            b = r["badge"][t]
            one, many = b["one"]["badge"], b["many"]["badge"]
            self.assertGreater(many["rect"]["width"], one["rect"]["width"] + 1, "%s: the 12 dot is a wider pill than the 1 dot: %r vs %r" % (t, many["rect"], one["rect"]))
            for name in ("one", "few", "many"):
                d, tab = b[name]["badge"]["rect"], b[name]["tab"]
                self.assertGreaterEqual(d["left"], tab["left"] - 0.5, "%s/%s: the dot's left is inside the tab" % (t, name))
                self.assertLessEqual(d["right"], tab["right"] + 0.5, "%s/%s: the dot's right is inside the tab" % (t, name))
                self.assertGreaterEqual(d["top"], tab["top"] - 0.5, "%s/%s: the dot is at/below the tab's top edge (contained, not above it)" % (t, name))
                self.assertLessEqual(d["bottom"], tab["bottom"] + 0.5, "%s/%s: the dot's bottom is inside the tab" % (t, name))
                self.assertGreater(tab["right"] - d["right"], -0.5, "%s/%s: the dot rides the RIGHT side of the tab" % (t, name))

    def test_nothing_moves_when_the_badge_flips_on_the_tab_width_and_the_label_edge_are_unchanged(self):
        r = self._result()
        on, off = r["moved"]["on"], r["moved"]["off"]
        self.assertAlmostEqual(on["w"], off["w"], delta=0.5, msg="the needs-you tab's width is the same with the badge off and on: %r vs %r" % (off, on))
        if on["labelLeft"] is not None and off["labelLeft"] is not None:
            self.assertAlmostEqual(on["labelLeft"], off["labelLeft"], delta=0.5, msg="the label's left edge did not move: %r vs %r" % (off, on))

    def test_ring_mode_badge_off_wears_the_dashed_magenta_ring_and_no_dot_byte_identical_to_the_pre_badge_strip(self):
        r = self._result()
        for t in ("dark", "light"):
            s = r["ring"][t]
            self.assertIn("ring-waiting-on-you", s["cls"].split(), "%s: with the badge off the needs-you tab wears the magenta ring: %r" % (t, s))
            self.assertEqual((s["outlineStyle"], s["outlineColor"]), ("dashed", TOKEN[t]), "%s: the ring is dashed in the token: %r" % (t, s))
            self.assertFalse(s["badge"], "%s: and there is NO dot in ring mode (badge off, byte-identical to the pre-badge strip)" % t)

    def test_the_phone_chip_and_a_needs_you_row_wear_the_count_dot_and_the_dashed_ask_treatment_gives_way(self):
        r = self._result()
        for t in ("dark", "light"):
            p = r["phone"][t]
            self.assertEqual(p["rowBadge"], "3", "%s: a needs-you row wears the .m-badge with its count: %r" % (t, p))
            self.assertEqual(p["rowBg"], TOKEN[t], "%s: the row's dot is the Needs-you token: %r" % (t, p))
            self.assertFalse(p["rowAsk"], "%s: the row's dashed .ask treatment gave way to the dot" % t)
            self.assertEqual(p["curBadge"], "3", "%s: the current-session chip wears the .m-badge with its count: %r" % (t, p))
            self.assertEqual(p["curBg"], TOKEN[t], "%s: the chip's dot is the Needs-you token: %r" % (t, p))
            self.assertFalse(p["curAsk"], "%s: the chip's dashed .ask border gave way to the dot" % t)
            self.assertEqual(p["curRole"], "img", "%s: the chip's dot is an image to a screen reader" % t)
            self.assertEqual(p["rowRole"], "img", "%s: the row's dot is an image" % t)
            self.assertEqual(p["curLabel"], "3 things need you", "%s: the chip dot's aria-label carries the full phrase: %r" % (t, p))
            self.assertEqual(p["rowLabel"], "3 things need you", "%s: the row dot's aria-label carries the full phrase: %r" % (t, p))
            self.assertEqual(p["oneRowBadge"], "1", "%s: a one-card session's row shows the count 1: %r" % (t, p))
            self.assertEqual(p["oneRowLabel"], "1 thing needs you", "%s: ...and its aria-label is the SINGULAR phrase (the arm no test executed before): %r" % (t, p))
            # item 2 (the second contributor, PR 2017): the pill RESERVES room, so the chevron and the close x sit to its
            # RIGHT, never stacked over it; their x-ranges are disjoint from the pill's (red at the merge, where it was absolute).
            self.assertIsNotNone(p["curChevron"], "%s: the chip has a chevron" % t)
            self.assertLessEqual(p["curPill"]["right"], p["curChevron"]["left"] + 0.5, "%s: the chip's count pill is left of the chevron, not over it: %r" % (t, p))
            self.assertIsNotNone(p["rowClose"], "%s: the row has a close x" % t)
            self.assertLessEqual(p["rowPill"]["right"], p["rowClose"]["left"] + 0.5, "%s: the row's count pill is left of the close x, not over it: %r" % (t, p))

    def test_above_99_the_phone_announces_the_exact_count_not_the_capped_text_equal_to_the_desktop(self):
        # item 1 (PR 2023 review): the phone scrapes the desktop dot's aria-label (uncapped), not its capped textContent,
        # so a session with more than 99 cards announces the exact number on the phone, equal to the desktop label, even
        # though both visible dots read "99+".
        r = self._result()
        for t in ("dark", "light"):
            desk = r["badge"][t]["over"]["badge"]
            self.assertEqual(desk["text"], "99+", "%s: the desktop dot's visible text caps at 99+: %r" % (t, desk))
            self.assertEqual(desk["label"], "120 things need you", "%s: ...but its aria-label carries the exact count: %r" % (t, desk))
            p = r["phone"][t]
            self.assertEqual(p["overRowBadge"], "99+", "%s: the phone row's visible dot caps at 99+ too: %r" % (t, p))
            self.assertEqual(p["overRowLabel"], "120 things need you", "%s: ...and its aria-label is the EXACT count, never '99+ things need you': %r" % (t, p))
            self.assertEqual(p["overRowLabel"], desk["label"], "%s: the phone and desktop labels are equal (the phone reads the desktop's): %r vs %r" % (t, p["overRowLabel"], desk["label"]))


    def test_the_count_moves_live_when_a_needs_you_card_is_added_and_cleared_without_a_reload(self):
        r = self._result()
        self.assertEqual(r["errors"], [], "no page error and every live wait resolved")
        live = r["live"]
        self.assertEqual(live["start"], "1", "the needs-you tab starts at one card")
        # this leg SHOWS only that the number moves on the open page with no reload; it cannot tell the chat-signature
        # component from the compare-and-wake. Those two mechanisms are pinned separately in test_kernel.py
        # (test_the_needs_you_count_wakes_the_pusher_on_a_count_only_change, the wake) and test_chat_build_sig_inputs.py
        # (test_the_needs_you_count_keys_the_signature_so_a_stale_badge_never_survives_a_judge_pass, the signature differential).
        self.assertEqual(live["added"], "2", "a second needs-you card climbs the number to 2 on the open page, no reload")
        self.assertEqual(live["cleared"], "1", "clearing the card drops the number back to 1, live, no reload")

    def test_the_retrying_left_dot_paints_the_amber_token(self):
        r = self._result()
        for t in ("dark", "light"):
            probe = r["retryProbe"][t]
            self.assertIn(probe["bg"], ("rgba(0, 0, 0, 0)", "transparent"), "%s: the retrying left dot is HOLLOW (a transparent fill), not a filled disc: %r" % (t, probe))
            self.assertIn(AMBER[t], probe["shadow"], "%s: the amber rides the inset outline (the ring shape): %r" % (t, probe))
            self.assertIn("inset", probe["shadow"], "%s: the outline is inset (a hollow ring, a distinct shape from the filled working/awaiting dots): %r" % (t, probe))

    def test_the_gear_preview_renders_the_badge_vocabulary_in_badge_mode_in_both_themes(self):
        # ROUND ONE MEDIUM (PR 2065): the gear's ring-section demos, run through applyTabBadgeMode when the badge is on,
        # must PAINT the badge vocabulary the strip paints, on the dashboard's own settings page. The gear's hosts load
        # feed.css + gear.css, never the chat's styles.css, so this reds at the first commit's head (the .tab-badge span
        # was an unstyled static span sitting in the flow, the retrying dot the working gold from the base .tab-dot rule)
        # until gear.css carries the .tab-badge and .tab-dot.retrying fallbacks. The gear.js source pin
        # (settings-previews.test.ts test 5) proves the demo BRANCH runs; it cannot see a missing CSS rule. This can.
        r = self._result()
        self.assertEqual(r["errors"], [], "the gear opened at the Tab strip section and every ring demo rendered")
        gd = r["gearDemo"]
        for t in ("dark", "light"):
            rows = gd[t]["rows"]; tok = gd[t]["tokens"]
            # Needs you (ring-waiting-on-you): the magenta ring gives way to the top-right dot in the needs token
            nu = rows.get("ring-waiting-on-you")
            self.assertIsNotNone(nu, "%s: the Needs-you demo row rendered a tab" % t)
            self.assertIsNotNone(nu["badge"], "%s: the Needs-you demo wears a .tab-badge (the ring dropped for the dot)" % t)
            self.assertEqual(nu["badge"]["position"], "absolute", "%s: the demo badge is positioned, not an unstyled static span: %r" % (t, nu["badge"]))
            self.assertEqual(nu["badge"]["bg"], tok["needs"], "%s: the demo badge's background is the needs token: %r" % (t, nu["badge"]))
            self.assertEqual(nu["badge"]["text"], "2", "%s: the Needs-you demo carries the count 2, so the preview draws the NUMBERED dot (the :not(:empty) rules live, not the bare older-kernel dot): %r" % (t, nu["badge"]))
            self.assertGreaterEqual(nu["badge"]["rect"]["width"], 14, "%s: the numbered dot is at least the 14px the :not(:empty) rule sizes it: %r" % (t, nu["badge"]))
            self.assertEqual(nu["outlineStyle"], "none", "%s: the Needs-you demo dropped its ring for the dot: %r" % (t, nu))
            self.assertAlmostEqual(nu["badge"]["rect"]["top"] - nu["tab"]["top"], 3.0, delta=0.6, msg="%s: the demo badge sits a 3px inset from the tab's TOP (no border on the demo tab): %r" % (t, nu))
            self.assertAlmostEqual(nu["tab"]["right"] - nu["badge"]["rect"]["right"], 3.0, delta=0.6, msg="%s: the demo badge sits a 3px inset from the tab's RIGHT (guards gear.css's 3px offset against a 2px revert): %r" % (t, nu))
            # (the keycap-width fix 2026-09-24) the demo carries the hot-key keycap AND, in badge mode, the count of 2, so
            # the gear.css keycap-widen twin must reserve the badge box: the keycap sits LEFT of the badge, not under it.
            # RED at the base and at 60fffcbfb (the demo has no twin), where the count badge overpaints the keycap.
            self.assertIsNotNone(nu["key"], "%s: the Needs-you demo carries the hot-key keycap" % t)
            self.assertLessEqual(nu["key"]["right"], nu["badge"]["rect"]["left"] + 0.5, "%s: the demo keycap sits left of the badge box, not under it (the gear twin reserves the room): key.right=%.1f badge.left=%.1f" % (t, nu["key"]["right"], nu["badge"]["rect"]["left"]))
            # Retrying (ring-retrying): the amber ring gives way to the amber LEFT status dot
            rt = rows.get("ring-retrying")
            self.assertIsNotNone(rt, "%s: the Retrying demo row rendered a tab" % t)
            self.assertIsNotNone(rt["dot"], "%s: the Retrying demo re-inks a .tab-dot.retrying slot" % t)
            self.assertIn(rt["dot"]["bg"], ("rgba(0, 0, 0, 0)", "transparent"), "%s: the retrying demo dot is HOLLOW (a transparent fill), the strip's shape cue mirrored: %r" % (t, rt["dot"]))
            self.assertIn(tok["retrying"], rt["dot"]["shadow"], "%s: the amber rides the demo dot's inset outline, not the working gold: %r" % (t, rt["dot"]))
            self.assertIn("inset", rt["dot"]["shadow"], "%s: the demo retrying dot is a hollow ring (a distinct shape): %r" % (t, rt["dot"]))
            self.assertEqual(rt["dot"]["visibility"], "visible", "%s: the retrying demo dot is visible: %r" % (t, rt["dot"]))
            # Blocked (ring-needs-you): the badge does not touch this ring, so it STAYS dashed in the awaiting token
            bl = rows.get("ring-needs-you")
            self.assertIsNotNone(bl, "%s: the Blocked demo row rendered a tab" % t)
            self.assertEqual(bl["outlineStyle"], "dashed", "%s: Blocked keeps its dashed ring under the badge: %r" % (t, bl))
            self.assertEqual(bl["outlineColor"], tok["awaiting"], "%s: the Blocked demo ring is the awaiting token: %r" % (t, bl))

    def test_the_gear_state_badge_switch_reflects_the_setting_the_strip_reads(self):
        # ROUND ONE LOW 2 (PR 2065): the gear's state-badge switch (#rs-statebadge) reflects the setting `!== false`, the
        # same guard the strip reads, so a store that NEVER chose shows the switch ON (the badge is the default) and a
        # stored false shows it OFF. A revert to `=== true` would leave the switch OFF while the strip paints the badge,
        # and nothing else in the suite catches that. Both themes.
        r = self._result()
        self.assertEqual(r["errors"], [], "the gear opened for both the never-chose and the chosen-off stores")
        for t in ("dark", "light"):
            on = r["gearDemo"][t]["sw"]; off = r["gearSwitchOff"][t]["sw"]
            self.assertIsNotNone(on, "%s: the state-badge switch is present in the gear" % t)
            self.assertTrue(on["checked"], "%s: a store that never chose shows the switch ON (the badge is the default): %r" % (t, on))
            self.assertIsNotNone(off, "%s: the state-badge switch is present in the gear (chosen off)" % t)
            self.assertFalse(off["checked"], "%s: a stored false shows the switch OFF: %r" % (t, off))

    def test_the_phone_retrying_dot_is_the_hollow_amber_ring_too(self):
        # PR 2080 review HIGH: the phone's retrying leading dot (#mcur .wd.retrying / .mrow .workdot.retrying in the
        # kernel's mobile CSS) was a FILLED amber disc, told from the filled working gold and awaiting green by colour
        # alone on the default path. It is now the same HOLLOW amber ring as the desktop: a transparent fill and the
        # amber on the inset outline, a distinct shape.
        r = self._result()
        for t in ("dark", "light"):
            p = r["phoneRetryProbe"][t]
            self.assertIsNotNone(p, "%s: the phone retry probe rendered in #mcur" % t)
            self.assertIn(p["bg"], ("rgba(0, 0, 0, 0)", "transparent"), "%s: the phone retrying dot is HOLLOW (a transparent fill): %r" % (t, p))
            self.assertIn(AMBER[t], p["shadow"], "%s: the amber rides the inset outline on the phone: %r" % (t, p))
            self.assertIn("inset", p["shadow"], "%s: the phone retrying dot is a hollow ring (a distinct shape): %r" % (t, p))

    def test_the_count_badge_sits_a_3px_inset_from_the_tab_top_and_right_2px_in_dense_chrome(self):
        # (the user 2026-09-23, who wanted the badge a pixel lower and further from the edge in NORMAL chrome; DENSE back
        # to 1px 2026-09-24, restoring PR 2023's measured reason that the hover-lifted close glyph overpaints less of the
        # digits) the dot sits a 3px inset from the tab's TOP and RIGHT edges in normal chrome, 1px in dense-chrome.
        # Measured as the gap from the tab's border-box edge to the badge's, which the tab's own 1px border adds one to
        # (4px normal, 2px dense). RED at this PR's base, where dense was 2px and the dense gaps read 3px. Both themes.
        r = self._result()
        self.assertEqual(r["errors"], [], "the badge geometry was read in normal and dense chrome")
        for t in ("dark", "light"):
            for name in ("one", "few", "many"):
                b = r["badge"][t][name]; d, tab = b["badge"]["rect"], b["tab"]
                self.assertAlmostEqual(tab["right"] - d["right"], 4.0, delta=0.6, msg="%s/%s: the badge sits a 3px inset from the tab's right (1px border + 3px): %r" % (t, name, b["badge"]["rect"]))
                self.assertAlmostEqual(d["top"] - tab["top"], 4.0, delta=0.6, msg="%s/%s: the badge sits a 3px inset from the tab's top (1px border + 3px): %r" % (t, name, b["badge"]["rect"]))
            for name in ("one", "many"):
                b = r["badgeDense"][t][name]; d, tab = b["badge"]["rect"], b["tab"]
                self.assertAlmostEqual(tab["right"] - d["right"], 2.0, delta=0.6, msg="%s/%s dense: the badge sits a 1px inset from the tab's right (1px border + 1px): %r" % (t, name, b["badge"]["rect"]))
                self.assertAlmostEqual(d["top"] - tab["top"], 2.0, delta=0.6, msg="%s/%s dense: the badge sits a 1px inset from the tab's top (1px border + 1px): %r" % (t, name, b["badge"]["rect"]))

    def test_a_bound_hotkey_keycap_stays_left_of_the_badge_box_and_the_content_run_clears_it(self):
        # (the user 2026-09-23, who wanted the tab widened when the keycap shows) a tab carrying BOTH the hot-key keycap
        # (.tab-key) and a non-empty count badge reserves the badge's box at the right, so the whole in-flow run (the
        # keycap and the rightmost ✕) sits LEFT of the badge instead of under it, in both themes AND both chromes.
        # WITHOUT the widen (no reserved room): the 99+ badge overpaints the keycap by about 6px (9px dense) and the
        # min-width badge overpaints the ✕ by about 10px, measured at the NEW offsets (3px normal, 1px dense); at the older
        # offsets those overpaints were about 5px (8px dense) and 9px (8px dense). The keycap and badge overlap vertically,
        # so the left-of check IS the no-intersection test. Sizing the room off the badge's min-width box, a wider count's ✕
        # may still ride under the wide badge (the accepted close-over-badge overlap), but the keycap clears every count.
        # (Green at this PR's base and head: the widen is present here; the keycap-width fix keeps it, gated on the strip.)
        r = self._result()
        self.assertEqual(r["errors"], [], "no page error and the keycap rendered on the needs-you tab")
        ids = {name: SIDS[name] for name in ("one", "many", "over")}
        for chrome in ("normal", "dense"):
            for t in ("dark", "light"):
                leg = r["hotkey"][chrome][t]
                for name in ("one", "many", "over"):
                    e = leg[ids[name]]
                    self.assertIsNotNone(e, "%s/%s/%s: the tab is present" % (chrome, t, name))
                    self.assertIsNotNone(e["key"], "%s/%s/%s: the hot-key keycap rendered (romp:tabkeys + romp:keys seeded): %r" % (chrome, t, name, e))
                    self.assertTrue(e["keyText"], "%s/%s/%s: the keycap carries the chord glyphs: %r" % (chrome, t, name, e))
                    self.assertLessEqual(e["key"]["right"], e["badge"]["left"] + 0.5,
                                         "%s/%s/%s: the keycap sits left of the badge box, not under it: key.right=%.1f badge.left=%.1f (badge=%r)" % (chrome, t, name, e["key"]["right"], e["badge"]["left"], e["badgeText"]))
                one = leg[ids["one"]]
                self.assertIsNotNone(one["close"], "%s/%s: the tab has a ✕ close glyph" % (chrome, t))
                self.assertLessEqual(one["close"]["right"], one["badge"]["left"] + 0.5,
                                     "%s/%s: the ✕ (rightmost in flow) clears the min-width badge box, so the tab widened to reserve it: close.right=%.1f badge.left=%.1f padRight=%s" % (chrome, t, one["close"]["right"], one["badge"]["left"], one["padRight"]))

    def test_the_keycap_reserve_is_gated_on_badge_mode_and_the_widget_not_the_count(self):
        # (the keycap-width fix 2026-09-24, T262g: a tab's width must not change with its state) the room for the top-right
        # badge is reserved on the keycap ALONE, under a strip-level class (#tabs.badge-keycap-room) the strip carries only
        # in badge mode with the Needs-you widget on. So a keycap tab's right padding is the reserved 21px (17px dense) in
        # badge mode whether or not a count shows (the idle `calm` keycap tab equals the counted `one`, so width is constant
        # across the count), and the bare 7px (5px dense) in ring mode and with the Needs-you widget off. RED at this PR's
        # base, where the reserve was gated on the non-empty badge: the idle keycap tab read 7px (5px dense) in badge mode,
        # so its width flipped as a count appeared or cleared. Deleting the dense widen rule also reds here (the normal
        # rule's specificity would win, giving 21px in dense chrome instead of 17px).
        r = self._result()
        self.assertEqual(r["errors"], [], "no page error and the keycap rendered under each gate config")
        for t in ("dark", "light"):
            for chrome, want in (("normal", "21px"), ("dense", "17px")):
                g = r["gate"]["badge"][t][chrome]
                self.assertTrue(g["calm"]["room"], "%s/%s: the strip carries badge-keycap-room in badge mode" % (t, chrome))
                self.assertTrue(g["calm"]["key"], "%s/%s: the idle tab has a keycap (romp:tabkeys/romp:keys seeded)" % (t, chrome))
                self.assertFalse(g["calm"]["badge"], "%s/%s: the idle tab has NO count badge" % (t, chrome))
                self.assertEqual(g["calm"]["pad"], want, "%s/%s: the IDLE keycap tab reserves the room in badge mode with no count: %r" % (t, chrome, g["calm"]))
                self.assertEqual(g["one"]["pad"], want, "%s/%s: the COUNTED keycap tab reserves the SAME room, so width is constant across the count: %r" % (t, chrome, g["one"]))
            for label in ("ring", "widgetOff"):
                for chrome, want in (("normal", "7px"), ("dense", "5px")):
                    g = r["gate"][label][t][chrome]
                    self.assertFalse(g["calm"]["room"], "%s/%s/%s: the strip does NOT carry badge-keycap-room (no reserved room)" % (label, t, chrome))
                    self.assertEqual(g["calm"]["pad"], want, "%s/%s/%s: a keycap tab reads the bare padding, the pre-badge strip's reference: %r" % (label, t, chrome, g["calm"]))

    def test_nothing_moves_when_a_keycap_tabs_count_flips_at_a_wrap_boundary(self):
        # (the keycap-width fix 2026-09-24, T262g: a tab's width must not change with its state) at a narrow, wrapping
        # viewport a keycap tab in badge mode keeps its width AND the strip's (#tabbar) height when its Needs-you count
        # clears, because the reserve is on the keycap, not the count. RED at this PR's base, where the reserve was gated
        # on the non-empty badge, so the tab's width flipped (21px -> 7px) as the count cleared and the strip's rows flapped.
        r = self._result()
        self.assertEqual(r["errors"], [], "no page error and the count flip resolved")
        w = r["wrapFlip"]
        self.assertTrue(w["withCount"]["hasBadge"], "the keycap tab starts with a count badge: %r" % w["withCount"])
        self.assertFalse(w["noCount"]["hasBadge"], "…and the badge cleared when the card was removed: %r" % w["noCount"])
        self.assertEqual(w["withCount"]["pad"], w["noCount"]["pad"], "the keycap tab's right padding is unchanged across the count flip: %r vs %r" % (w["withCount"], w["noCount"]))
        self.assertAlmostEqual(w["withCount"]["w"], w["noCount"]["w"], delta=0.5, msg="the keycap tab's width is unchanged across the count flip (T262g): %r vs %r" % (w["withCount"], w["noCount"]))
        self.assertAlmostEqual(w["withCount"]["barH"], w["noCount"]["barH"], delta=0.5, msg="the strip's height is unchanged, so the transcript does not slide under the reader: %r vs %r" % (w["withCount"], w["noCount"]))


if __name__ == "__main__":
    unittest.main()
