#!/usr/bin/env python3
"""THE TAB LOCK (T395, the user 2026-09-12; T405, the user 2026-09-13: the lock moved off the strip into the strip's gear) on
the served chat page and, for the Sessions pane, the landing: a hermetic kernel serves six synthetic notes-api sessions
(TESTHOST, one flat row of tabs, the chat lens narrowed to no tags). The strip's chrome (T405): a gear at the strip's
FARTHEST right in a box of the tags box's height, wearing the shell's own settings glyph (the rail's character, one
source); its menu holds "Lock the tabs in place", the toggle row with the button's two titles, and "Tab widgets…"; no lock
button anywhere in the strip; the tag control displays no chips (narrowed to no tags, it still wears the accent). A REAL
mouse drag (page.mouse down, a run of moves across the strip, up over the target) with the lock OFF moves the tab; the
lock row pressed, the same drag moves nothing, the tabs are not draggable, the row wears the ✓, the setting persists across
a reload; pressed again, the drag moves the tab once more. Round one: a keyboard press (Enter on the gear, Enter on the
row) keeps the focus on the row across the strip's rebuild, Escape hands it back to the gear; and the Sessions pane (the
landing's timeline, which shares the order) refuses a lane drag while locked, its lanes without the grab cursor and saying
why, and moves the lane once unlocked. The phone layout (a coarse pointer under 1024 px) hides the strip and its gear with it.

TAB_LOCK_DIST=<dir> serves another tree's UI bundle (the red run's before); TAB_LOCK_SHOTS=<prefix> writes
<prefix>-strip-<theme>.png (the strip with the gear's menu open); TAB_LOCK_DUMP=<path> writes the whole measurement. Skips LOUDLY without the extension deps or
a Playwright browser (CI sets ROMP_SERVED_TESTS_REQUIRE=1 and installs both, so a skip there is a failure). Synthetic
throughout: placeholder sids, TESTHOST, invented text.
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

NAMES = ["web", "api", "deploy", "tests", "docs", "auth"]
SIDS = {n: "%s-1111-2222-3333-444444444444" % (chr(ord("a") + i) * 8) for i, n in enumerate(NAMES)}
PALETTE = [("#9cd2ff", "#0c1a2e"), ("#1EA1EB", "#ffffff"), ("#54B204", "#ffffff"), ("#c98cff", "#1a0c2e"),
           ("#e5a50a", "#1a1200"), ("#4EC9B0", "#00201a")]


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
const ctx = await browser.newContext({ viewport: { width: 1400, height: 800 } });
const page = await ctx.newPage();   // the SHELL: the chat frame, the settings frame the gear opens, the timeline frame that shares the order
await page.addInitScript(() => {   // the gesture's log in every frame: every drag event, so a case that moved nothing says whether a drag ever began
  window.__log = [];
  for (const k of ["dragstart", "drop", "dragend"]) window.addEventListener(k, (e) => window.__log.push({ k, prevented: e.defaultPrevented }));
});
await page.goto(cfg.landing);
await page.waitForSelector("#rail-gear", { timeout: 20000 });
const frameOf = async (part) => { let f = page.frames().find((x) => x.url().includes(part)); for (let i = 0; i < 100 && !f; i++) { await page.waitForTimeout(100); f = page.frames().find((x) => x.url().includes(part)); } if (!f) { console.error("no " + part + " frame"); process.exit(1); } return f; };
let chatF = await frameOf("/chat");
const settle = async () => {
  await chatF.waitForFunction((n) => document.querySelectorAll("#tabs .tab[data-id]").length >= n, cfg.count, { timeout: 30000 });
  await chatF.waitForTimeout(600);
};
await settle();
const frameBox = (id) => page.evaluate((id) => { const f = document.getElementById(id).getBoundingClientRect(); return { x: f.left, y: f.top }; }, id);
// the strip: the tabs in DOM order with their rects, the right end and the gear's dress, the store
const layout = () => chatF.evaluate(() => {
  const bar = document.getElementById("tabs"); const b = bar.getBoundingClientRect();
  const r1 = (v) => Math.round(v * 10) / 10;
  const tabs = Array.from(bar.querySelectorAll(".tab[data-id]")).map((t) => { const r = t.getBoundingClientRect();
    return { id: t.dataset.id, name: (t.querySelector(".tab-label") || t).textContent.trim(), left: r1(r.left - b.left), top: r1(r.top - b.top), w: r1(r.width), h: r1(r.height), draggable: !!t.draggable }; });
  const end = bar.querySelector(".tab-strip-end");   // T412: one right-end wrapper, the tags button and the gear
  const btn = end && end.querySelector(".tab-widgets-gear");
  const probe = document.createElement("span"); probe.style.color = "var(--accent)"; document.body.appendChild(probe);
  const accent = getComputedStyle(probe).color; probe.remove();
  const pb = document.createElement("span"); pb.style.border = "1px solid var(--card-border)"; document.body.appendChild(pb);
  const cardBorder = getComputedStyle(pb).borderTopColor; pb.remove();
  const add = bar.querySelector(".tab-add"), tagBox = bar.querySelector(".tab-tagbox"), tagBtn = bar.querySelector(".tab-tagbox .tab-tagfilter");
  const tb = tagBtn ? { w: r1(tagBtn.getBoundingClientRect().width), h: r1(tagBtn.getBoundingClientRect().height), border: getComputedStyle(tagBtn).borderTopColor, radius: getComputedStyle(tagBtn).borderRadius } : null;
  let s = {}; try { s = JSON.parse(localStorage.getItem("romp:settings") || "{}") || {}; } catch (e) {}
  const gear = end && btn ? { present: true, last: bar.lastElementChild === end, prev: end.previousElementSibling ? end.previousElementSibling.className : null,
                       endH: r1(end.getBoundingClientRect().height), tagBoxH: tagBox ? r1(tagBox.getBoundingClientRect().height) : null, tagInEnd: !!tagBox && tagBox.parentElement === end,
                       rightGap: r1(b.right - btn.getBoundingClientRect().right), endRightGap: r1(b.right - end.getBoundingClientRect().right), text: btn.textContent, svg: !!btn.querySelector("svg"),
                       label: btn.getAttribute("aria-label"), title: btn.title, haspopup: btn.getAttribute("aria-haspopup"),
                       border: getComputedStyle(btn).borderTopColor, borderW: getComputedStyle(btn).borderTopWidth, borderStyle: getComputedStyle(btn).borderTopStyle, radius: getComputedStyle(btn).borderRadius,
                       color: getComputedStyle(btn).color, bg: getComputedStyle(btn).backgroundColor, fontSize: getComputedStyle(btn).fontSize, boxed: btn.parentElement !== end,
                       w: r1(btn.getBoundingClientRect().width), h: r1(btn.getBoundingClientRect().height),
                       tagRightOfAdd: tagBtn && add ? r1(tagBtn.getBoundingClientRect().left - add.getBoundingClientRect().right) : null,
                       tagToGear: tagBtn ? r1(btn.getBoundingClientRect().left - tagBtn.getBoundingClientRect().right) : null,
                       tagRightGap: tagBtn ? r1(b.right - tagBtn.getBoundingClientRect().right) : null, tagTag: tagBtn ? tagBtn.tagName : null }
                   : { present: false };
  const lock = { present: !!bar.querySelector(".tab-lock, .tab-lockbox"), menus: document.querySelectorAll("[data-rows-menu]").length };
  const chips = bar.querySelector(".tab-tagbox .tab-tagchips");
  const tagCtl = tagBtn ? { pressed: tagBtn.getAttribute("aria-pressed"), chipsInDom: !!chips, chipCount: chips ? chips.children.length : 0 } : null;
  const ms = document.getElementById("mtag-slot");
  return { bar: { left: b.left, top: b.top, right: b.right }, tabs, order: tabs.map((t) => t.id), gear, lock, tagBtn: tb, tagCtl, accent, cardBorder,
           mountChips: ms && ms.children[1] ? ms.children[1].childElementCount : null, mountPresent: !!ms, store: { tabsLocked: "tabsLocked" in s ? s.tabsLocked : "absent" } };
});
// drag the 3rd tab and release over the left part of the 1st (the reorder lab's gesture), in page coordinates through the frame's box
async function drag(label) {
  const pre = await layout(); const fb = await frameBox("f-chat");
  const src = pre.tabs[2], tgt = pre.tabs[0];
  const sx = fb.x + pre.bar.left + src.left + src.w / 2, sy = fb.y + pre.bar.top + src.top + src.h / 2;
  const tx = fb.x + pre.bar.left + tgt.left + tgt.w * 0.25, ty = fb.y + pre.bar.top + tgt.top + tgt.h / 2;
  await chatF.evaluate(() => { window.__log = []; });
  await page.mouse.move(sx, sy); await page.mouse.down();
  await page.mouse.move(sx + 4, sy + 1, { steps: 2 });
  await page.mouse.move(tx, ty, { steps: 16 });
  for (let i = 0; i < 3; i++) await page.mouse.move(tx, ty);
  await page.mouse.up();
  await page.waitForTimeout(500);
  await page.mouse.move(900, 600);
  const post = await layout();
  const log = await chatF.evaluate(() => window.__log);
  return { label, dragged: src.name, preOrder: pre.order.map((id) => pre.tabs.find((t) => t.id === id).name), postOrder: post.order.map((id) => post.tabs.find((t) => t.id === id).name),
           moved: pre.order.join() !== post.order.join(), landedFirst: post.order[0] === src.id, srcDraggable: src.draggable,
           ev: { dragstart: log.filter((e) => e.k === "dragstart").length, drop: log.filter((e) => e.k === "drop").length, dragend: log.filter((e) => e.k === "dragend").length } };
}
// THE GEAR'S JUMP (T415): one click on the strip's gear, the settings open on the Chat tab scrolled to the Tab strip head, the
// lock's checkbox row between that head and Tab widgets; no menu on the way. Read from the settings frame once the card shows.
const settingsOpen = () => page.evaluate(() => document.body.classList.contains("settings-open"));
const landing = (setF) => setF.evaluate(() => {
  const card = document.querySelector("#rsettings .rs-card"); const cr = card.getBoundingClientRect();
  const head = document.querySelector("[data-section=tabstrip]"), widgets = document.querySelector("[data-section=tabwidgets]");
  const hr = head ? head.getBoundingClientRect() : null, wr = widgets ? widgets.getBoundingClientRect() : null;
  const tl = document.getElementById("rs-tablock"), row = tl ? tl.closest("label") : null;
  const on = document.querySelector("#rsettings .rs-tab.on");
  return { tab: on ? on.dataset.tab : null, headPresent: !!head, headText: head ? head.textContent : null, headTop: hr ? Math.round((hr.top - cr.top) * 10) / 10 : null,
           cardPad: parseFloat(getComputedStyle(card).paddingTop), cardScrollTop: card.scrollTop, headAboveWidgets: hr && wr ? hr.top < wr.top : null,
           lockRow: row ? { present: true, checked: tl.checked, label: (row.querySelector("b") || {}).textContent || null, sub: (row.querySelector(".rs-sub") || {}).textContent || null,
                            betweenHeads: !!hr && !!wr && row.getBoundingClientRect().top > hr.top && row.getBoundingClientRect().top < wr.top } : { present: false } };
});
const openViaGear = async () => {
  await chatF.click("#tabs .tab-widgets-gear");
  const open = await page.waitForFunction(() => document.body.classList.contains("settings-open"), null, { timeout: 5000 }).then(() => true).catch(() => false);
  const menus = await chatF.evaluate(() => document.querySelectorAll("[data-rows-menu]").length);   // the base: a menu, no settings
  if (!open) { await page.keyboard.press("Escape"); await page.waitForTimeout(150); return { open: false, menus, land: null, setF: null }; }
  const setF = await frameOf("/settings");
  await setF.waitForSelector("#rsettings:not([hidden])", { timeout: 10000 }); await setF.waitForTimeout(500);   // the section ask settles
  return { open: true, menus, land: await landing(setF), setF };
};
const closeSettings = async () => { await page.evaluate(() => window.__rompOpenSettings()); await page.waitForFunction(() => !document.body.classList.contains("settings-open"), null, { timeout: 5000 }).catch(() => {}); await page.waitForTimeout(250); };
const press = async () => {   // the gear's jump, then the lock's switch
  const r = await openViaGear();
  if (!r.open || !r.land.lockRow.present) { if (r.open) await closeSettings(); return { open: r.open, menus: r.menus, land: r.land, toggled: false }; }
  await r.setF.click("#rs-tablock"); await r.setF.waitForTimeout(400);
  const after = await landing(r.setF);
  await closeSettings(); await chatF.waitForTimeout(300);
  return { open: true, menus: r.menus, land: r.land, toggled: true, after };
};
const out = { start: await layout() };
await chatF.evaluate(() => document.body.classList.add("theme-light")); await chatF.waitForTimeout(150);
out.light = await layout();
await chatF.evaluate(() => document.body.classList.remove("theme-light")); await chatF.waitForTimeout(150);
out.unlockedDrag = await drag("unlocked: the 3rd tab to the first slot");
out.pressed = await press();                              // the jump and the switch: locked
out.locked = await layout();
await page.reload(); await page.waitForSelector("#rail-gear", { timeout: 20000 }); chatF = await frameOf("/chat"); await settle();   // the setting is the browser's: a fresh page comes up locked
out.afterReload = await layout();
out.lockedDrag = await drag("locked: the same drag");
// a KEYBOARD press: Enter on the focused gear is its click and opens the settings; Escape (the shell's chain) closes them
await chatF.focus("#tabs .tab-widgets-gear"); await page.keyboard.press("Enter"); await page.waitForTimeout(500);
out.keyOpen = { settingsOpen: await settingsOpen() };
if (out.keyOpen.settingsOpen) { const sf = await frameOf("/settings"); await sf.waitForSelector("#rsettings:not([hidden])", { timeout: 10000 }).catch(() => {}); await sf.waitForTimeout(400); out.keyOpen.land = await landing(sf); }
else { await page.keyboard.press("Escape"); await page.waitForTimeout(150); }
await page.keyboard.press("Escape"); await page.waitForTimeout(400);
out.keyEscape = { settingsOpen: await settingsOpen() };
// THE SESSIONS PANE: the landing's timeline shares the order with the strip; its lane drag is held too
const tl = await frameOf("/timeline");
await tl.waitForFunction((names) => Array.from(document.querySelectorAll("svg text")).filter((t) => names.includes(t.textContent.trim())).length >= names.length, cfg.names, { timeout: 30000 });
await page.waitForTimeout(600);
const lanes = () => tl.evaluate((names) => {
  const labels = Array.from(document.querySelectorAll("svg text")).filter((t) => names.includes(t.textContent.trim()))
    .map((t) => { const r = t.getBoundingClientRect(); return { name: t.textContent.trim(), x: r.left + r.width / 2, y: r.top + r.height / 2 }; }).sort((a, b) => a.y - b.y);
  const rects = Array.from(document.querySelectorAll("svg rect"));
  return { labels, grabRects: rects.filter((q) => q.style.cursor === "grab").length, titles: Array.from(document.querySelectorAll("svg rect > title")).map((q) => q.textContent) };
}, cfg.names);
async function laneDrag(label) {
  const pre = await lanes(); const fb = await frameBox("f-timeline");
  if (pre.labels.length < 3) return { label, skipped: "lanes: " + pre.labels.length };
  const src = pre.labels[2], tgt = pre.labels[0];
  await page.mouse.move(fb.x + src.x, fb.y + src.y); await page.mouse.down();
  await page.mouse.move(fb.x + src.x, fb.y + src.y - 8, { steps: 3 });
  await page.mouse.move(fb.x + tgt.x, fb.y + tgt.y - 4, { steps: 12 });
  await page.mouse.up(); await page.waitForTimeout(900);
  const post = await lanes();
  return { label, dragged: src.name, preOrder: pre.labels.map((l) => l.name), postOrder: post.labels.map((l) => l.name),
           moved: pre.labels.map((l) => l.name).join() !== post.labels.map((l) => l.name).join(), grabRectsPre: pre.grabRects, titlesPre: pre.titles };
}
out.tlLocked = await laneDrag("locked: the 3rd lane to the top");
// the dress in both themes (T412: the strip's gear is the rail gear's twin), compact tabs, and the screenshots: the strip, and the card open at the Tab strip section
out.themes = {};
const railRead = () => page.evaluate(() => { const g = document.getElementById("rail-gear"), cs = getComputedStyle(g); return { color: cs.color, bg: cs.backgroundColor, fontSize: cs.fontSize, border: cs.borderTopWidth + " " + cs.borderTopStyle, radius: cs.borderRadius, h: g.getBoundingClientRect().height }; });
for (const theme of ["dark", "light"]) {
  await chatF.evaluate((t) => document.body.classList.toggle("theme-light", t === "light"), theme);
  await page.evaluate((t) => document.body.classList.toggle("theme-light", t === "light"), theme);
  await page.mouse.move(4, 4); await page.waitForTimeout(200);
  const restLay = await layout();
  await chatF.hover("#tabs .tab-widgets-gear"); await page.waitForTimeout(200);
  const hov = await chatF.evaluate(() => { const g = document.querySelector("#tabs .tab-widgets-gear"), cs = getComputedStyle(g); return { color: cs.color, bg: cs.backgroundColor, border: cs.borderTopWidth + " " + cs.borderTopStyle }; });
  await page.mouse.move(4, 4); await page.waitForTimeout(150);
  const railRest = await railRead();
  await page.hover("#rail-gear"); await page.waitForTimeout(200);
  const railHover = await railRead();
  await page.mouse.move(4, 4); await page.waitForTimeout(100);
  out.themes[theme] = restLay;
  out.themes[theme].rest = restLay.gear; out.themes[theme].hover = hov; out.themes[theme].railRest = railRest; out.themes[theme].railHover = railHover;
  await chatF.evaluate(() => document.body.classList.add("dense-chrome")); await chatF.waitForTimeout(150);
  out.themes[theme].dense = await chatF.evaluate(() => { const h = (el) => el ? el.getBoundingClientRect().height : null;
    return { tab: h(document.querySelector("#tabs .tab[data-id]")), gear: h(document.querySelector("#tabs .tab-widgets-gear")), end: h(document.querySelector("#tabs .tab-strip-end")),
             tagbox: h(document.querySelector("#tabs .tab-tagbox")), contentTop: document.getElementById("content") ? document.getElementById("content").getBoundingClientRect().top : null }; });
  const fb = await frameBox("f-chat");
  const clip = async (name) => { if (!cfg.shots) return; const b = await chatF.evaluate(() => { const r = document.getElementById("tabbar").getBoundingClientRect(); return { top: r.top, h: r.height }; });
    await page.screenshot({ path: cfg.shots + "-" + name + "-" + theme + ".png", clip: { x: fb.x, y: fb.y + Math.max(0, b.top - 4), width: 1400 - fb.x, height: b.h + 60 } }); };
  await clip("dense-strip");
  await chatF.evaluate(() => document.body.classList.remove("dense-chrome")); await chatF.waitForTimeout(100);
  await clip("strip");
  // the card open at the Tab strip section, through the gear
  const j = await openViaGear();
  if (j.open) {
    out.themes[theme].jump = j.land;
    if (cfg.shots) { const c = await j.setF.evaluate(() => { const r = document.querySelector("#rsettings .rs-card").getBoundingClientRect(); return { x: r.left, y: r.top, width: r.width, height: Math.min(r.height, 520) }; });
      await page.screenshot({ path: cfg.shots + "-settings-" + theme + ".png", clip: c }); }
    await closeSettings();
  } else out.themes[theme].jump = { open: false, menus: j.menus };
}
await chatF.evaluate(() => document.body.classList.remove("theme-light")); await page.evaluate(() => document.body.classList.remove("theme-light"));
// the phone layout (T161: a coarse pointer under 1024 px): the kernel's page hides the whole strip, the gear with it
const phoneCtx = await browser.newContext({ viewport: { width: 800, height: 900 }, hasTouch: true });
const phone = await phoneCtx.newPage(); await phone.goto(cfg.chat);
await phone.waitForFunction(() => document.querySelectorAll("#tabs .tab[data-id]").length > 0 || getComputedStyle(document.getElementById("tabs") || document.body).display === "none", null, { timeout: 30000 }).catch(() => {});
await phone.waitForTimeout(600);
out.phone = await phone.evaluate(() => { const tabs = document.getElementById("tabs"); const gear = document.querySelector("#tabs .tab-widgets-gear");
  const vis = (el) => !!el && el.getClientRects().length > 0 && getComputedStyle(el).display !== "none" && getComputedStyle(el).visibility !== "hidden";
  const ms = document.getElementById("mtag-slot");
  return { phoneLayout: window.matchMedia("(pointer:coarse) and (max-width:1024px)").matches, stripVisible: vis(tabs), gearVisible: vis(gear), mslot: !!ms,
           tagVisible: vis(document.querySelector("#tabs .tab-tagfilter")), endVisible: vis(document.querySelector("#tabs .tab-strip-end")),
           mslotChips: ms && ms.children[1] ? ms.children[1].childElementCount : null }; });
await phoneCtx.close();
out.pressedAgain = await press();                         // unlocked again
out.unlocked = await layout();
out.unlockedAgainDrag = await drag("unlocked again: the same drag");
out.tlUnlocked = await laneDrag("unlocked: the 3rd lane to the top");
fs.writeFileSync(cfg.out, JSON.stringify(out));
console.log("RESULT: ok");
await browser.close();
"""


class ServedTabLock(unittest.TestCase):
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
        cls.lab = tempfile.mkdtemp(prefix="tab-lock-")
        before = os.environ.get("TAB_LOCK_DIST", "")
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
        cwd = os.path.join(cls.lab, "proj")
        for d in ("names", "sdk", "states"):
            os.makedirs(os.path.join(state, d), exist_ok=True)
        Path(state, "session-hosts").write_text("off\n")   # this lab mints its own state root: no session host (repo rule)
        os.makedirs(cwd, exist_ok=True)
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        t0 = int(time.time()) - 900
        for i, name in enumerate(NAMES):
            sid = SIDS[name]
            bg, fg = PALETTE[i % len(PALETTE)]
            Path(state, "names", sid).write_text("%s\t%s\t%s\t%s\n" % (name, cwd, bg, fg))
            Path(state, "sdk", sid + ".json").write_text(json.dumps(
                {"sid": sid, "name": name, "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": sid, "alive": True,
                 "model": "claude-opus-5", "liveModel": "Opus 5"}))
            recs = [{"type": "user", "timestamp": iso(t0 + i), "uuid": "u1", "parentUuid": None, "promptSource": "typed", "sessionId": sid,
                     "message": {"role": "user", "content": "what does the %s session do in notes-api?" % name}},
                    {"type": "assistant", "timestamp": iso(t0 + i + 5), "uuid": "a1", "parentUuid": "u1", "sessionId": sid,
                     "message": {"role": "assistant", "model": "claude-opus-5", "stop_reason": "end_turn",
                                 "content": [{"type": "text", "text": "It keeps the %s side of the notes-api tidy." % name}]}}]
            Path(proj, sid + ".jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
        Path(state, "timeline-views.json").write_text(json.dumps({"active": "all", "actives": {"chat": {"none": True}}, "tags": []}))   # the chat lens narrowed to no tags (T405: the control shows no chips for it)
        Path(state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 10}, "seven_day": {"pct": 10}}))
        cls.port, cls.token = _free_port(), "testtok-tablock"
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
            raise unittest.SkipTest("hermetic kernel never served /healthz here")

    @classmethod
    def tearDownClass(cls):
        k = getattr(cls, "kernel", None)
        if k:
            k.kill(); k.wait()
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

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
            json.dump({"chat": "http://127.0.0.1:%d/chat?token=%s" % (cls.port, cls.token), "landing": "http://127.0.0.1:%d/?token=%s" % (cls.port, cls.token),
                       "count": len(NAMES), "names": NAMES, "out": out, "shots": os.environ.get("TAB_LOCK_SHOTS", "")}, f)
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
        if os.environ.get("TAB_LOCK_DUMP"):
            Path(os.environ["TAB_LOCK_DUMP"]).write_text(json.dumps(result, indent=1) + "\n")
        return result

    def test_the_gear_sits_last_at_the_strips_farthest_right_wearing_the_shells_glyph_with_no_menu_and_no_lock_button(self):
        # T405: the shell's settings glyph from one source at the strip's right; T412: a bare glyph dressed as the rail's; T415: no menu behind it
        r = self._run(); s = r["start"]
        table = "\n  " + json.dumps(s["gear"]) + "\n  " + json.dumps(s["lock"])
        self.assertTrue(s["gear"]["present"], "the strip carries the gear (the settings can be reached in the shell)" + table)
        self.assertTrue(s["gear"]["last"] and s["gear"]["endRightGap"] <= 2.0, "the right end is last and flush" + table)
        self.assertEqual(s["gear"]["text"], "\u26ed", "the shell's own gear glyph" + table); self.assertFalse(s["gear"]["svg"])
        self.assertEqual((s["gear"]["label"], s["gear"]["title"], s["gear"]["haspopup"]), ("Tab strip settings", "Tab strip settings", None), "a plain button to the settings: no popup role (T415)" + table)
        self.assertFalse(s["lock"]["present"], "no lock button in the strip (T405)" + table)
        self.assertEqual(s["lock"]["menus"], 0, "no rows menu on the page" + table)
        self.assertEqual((s["tagCtl"]["pressed"], s["tagCtl"]["chipCount"]), ("true", 0), "the lens is narrowed to no tags: the button wears the accent, no chip for the none pick (T405)" + json.dumps(s["tagCtl"]))
        for theme in ("dark", "light"):
            t = r["themes"][theme]; g = t["gear"]; tb = "\n  " + theme + "=" + json.dumps(g)
            self.assertFalse(g["boxed"], theme + ": no box around the gear" + tb)
            self.assertEqual((g["borderW"], g["borderStyle"]), ("0px", "none"), theme + ": no border" + tb)
            rr, rh, hv = t["railRest"], t["railHover"], t["hover"]; tr = "\n  rail rest=" + json.dumps(rr) + "\n  rail hover=" + json.dumps(rh) + "\n  gear hover=" + json.dumps(hv)
            self.assertEqual(g["fontSize"], rr["fontSize"], theme + ": the rail gear's glyph size" + tb + tr)
            self.assertEqual(t["rest"]["color"], rr["color"], theme + ": the rail gear's rest colour" + tb + tr)
            self.assertEqual((hv["color"], hv["bg"]), (rh["color"], rh["bg"]), theme + ": the rail gear's hover" + tr)
            d = t["dense"]; td = "\n  " + theme + " dense=" + json.dumps(d)
            self.assertLessEqual(abs(d["tab"] - 25), 0.6, theme + ": compact tabs are 25px" + td)
            self.assertLessEqual(d["gear"], d["tab"] + 0.01, theme + ": the gear inside the dense row" + td)
            self.assertLessEqual(abs(d["contentTop"] - 31), 0.6, theme + ": the transcript's top at 31px under compact tabs" + td)

    def test_the_gear_jumps_straight_to_the_settings_chat_tab_at_the_tab_strip_section_above_tab_widgets(self):
        r = self._run(); p = r["pressed"]; t = "\n  " + json.dumps(p)
        self.assertTrue(p["open"], "one click on the gear opened the settings (T415): no menu in between" + t)
        self.assertEqual(p["menus"], 0, "and no rows menu was drawn on the way" + t)
        L = p["land"]
        self.assertEqual(L["tab"], "chat", "the Chat tab" + t)
        self.assertEqual((L["headPresent"], L["headText"]), (True, "Tab strip"), "the strip's own section" + t)
        self.assertLessEqual(abs(L["headTop"] - L["cardPad"]), 2.0, "the card scrolled so the Tab strip head sits at its top, under the padding (the section ask)" + t)
        self.assertTrue(L["headAboveWidgets"], "the Tab strip section sits ABOVE Tab widgets" + t)
        self.assertEqual((L["lockRow"]["present"], L["lockRow"]["label"], L["lockRow"]["betweenHeads"]), (True, "Lock the tabs in place", True), "the lock is the section's row" + t)
        for theme in ("dark", "light"):
            j = r["themes"][theme]["jump"]; tj = "\n  " + theme + "=" + json.dumps(j)
            self.assertTrue(j.get("headPresent"), theme + ": the jump lands on the section in this theme too" + tj)
            self.assertLessEqual(abs(j["headTop"] - j["cardPad"]), 2.0, theme + ": at the card's top" + tj)

    def test_the_phone_layout_hides_the_strip_and_the_gear_with_it(self):
        p = self._run()["phone"]
        self.assertTrue(p["phoneLayout"], json.dumps(p))
        self.assertFalse(p["stripVisible"], "the phone page hides the whole strip (T161)" + json.dumps(p))
        self.assertFalse(p["gearVisible"], "so there is no gear to place" + json.dumps(p))
        self.assertFalse(p["tagVisible"] or p["endVisible"], "nor a tags button or the right-end wrapper: the strip's two right-end controls go with it (T412)" + json.dumps(p))

    def test_locked_the_drag_moves_nothing_and_unlocked_the_same_drag_moves_the_tab(self):
        r = self._run()
        u = r["unlockedDrag"]
        self.assertTrue(u["moved"] and u["landedFirst"], "unlocked: the real drag moved the 3rd tab to the first slot: " + json.dumps(u))
        self.assertTrue(u["srcDraggable"], "unlocked: the tab is draggable")
        self.assertTrue(r["pressed"]["toggled"] and r["pressed"]["after"]["lockRow"]["checked"], "the switch in the settings' Tab strip section locked the tabs: " + json.dumps(r["pressed"]))
        self.assertEqual(r["locked"]["store"]["tabsLocked"], True, "the setting is written: " + json.dumps(r["locked"]["store"]))
        self.assertEqual(r["afterReload"]["store"]["tabsLocked"], True, "and a fresh page comes up locked")
        l = r["lockedDrag"]
        self.assertFalse(l["moved"], "locked: the same drag moved nothing: " + json.dumps(l))
        self.assertFalse(l["srcDraggable"], "locked: the tabs are not draggable")
        self.assertEqual(l["ev"]["dragstart"], 0, "locked: no drag ever began: " + json.dumps(l["ev"]))
        self.assertTrue(r["pressedAgain"]["toggled"] and not r["pressedAgain"]["after"]["lockRow"]["checked"], "pressed again: unlocked: " + json.dumps(r["pressedAgain"]))
        self.assertEqual(r["unlocked"]["store"]["tabsLocked"], False)
        a = r["unlockedAgainDrag"]
        self.assertTrue(a["moved"] and a["landedFirst"], "unlocked again: the same drag moves the tab: " + json.dumps(a))

    def test_enter_on_the_focused_gear_opens_the_settings_and_escape_closes_them(self):
        r = self._run()
        self.assertTrue(r["keyOpen"]["settingsOpen"], "Enter on the gear is its click: the settings open" + json.dumps(r["keyOpen"]))
        self.assertEqual((r["keyOpen"]["land"]["tab"], r["keyOpen"]["land"]["headText"]), ("chat", "Tab strip"), "at the Tab strip section" + json.dumps(r["keyOpen"]))
        self.assertFalse(r["keyEscape"]["settingsOpen"], "Escape closes them by the shell's chain" + json.dumps(r["keyEscape"]))

    def test_the_sessions_pane_lane_drag_is_held_by_the_lock_and_moves_once_unlocked(self):
        r = self._run(); l = r["tlLocked"]; u = r["tlUnlocked"]
        if "skipped" in l or "skipped" in u:
            self.skipTest("the Sessions pane drew fewer than three lanes here: " + json.dumps([l, u]))
        self.assertFalse(l["moved"], "locked: the lane drag moves nothing: " + json.dumps(l))
        self.assertTrue(u["moved"], "unlocked: the same lane drag moves the lane: " + json.dumps(u))

    def test_the_lock_row_reads_its_state_in_the_settings(self):
        r = self._run()
        self.assertEqual(r["pressed"]["land"]["lockRow"]["checked"], False, "before the press the row reads unlocked: " + json.dumps(r["pressed"]["land"]["lockRow"]))
        self.assertEqual(r["pressed"]["after"]["lockRow"]["checked"], True, "after it, locked")
        self.assertEqual(r["pressedAgain"]["land"]["lockRow"]["checked"], True, "opened again while locked, the row reads locked")
        self.assertIn("drag", (r["pressed"]["land"]["lockRow"]["sub"] or "").lower(), "the row's line says what the lock holds: " + json.dumps(r["pressed"]["land"]["lockRow"]))


if __name__ == "__main__":
    unittest.main()
