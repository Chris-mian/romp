#!/usr/bin/env python3
"""THE SETTINGS CARD'S PREVIEWS BESIDE THE REAL LINE (T415 part two, the user 2026-09-14, through romp_feature-review), on the served
dashboard: a hermetic kernel serves three synthetic notes-api sessions (web, api and tests, TESTHOST, Opus 5 at high, auto) whose
persisted context fills are 20, 62 and 95 percent; the chat frame's line above the composer shows each one's controls and battery
as the active tab changes, and the Chat tab's Tab widgets and Status line sections (reached through the shell's relay) show their
previews. (3) The demo tab in the Tab widgets preview and in every row reads the placeholder session_name (the user's copy) in its
identity colour, as a real tab reads its name. (4) The word Preview is a title above each preview box, never inside it. (5) The status line preview draws its
mode, model and effort badges and its battery through the line's own renderer over a demo status (Opus 5 at high, 62 percent):
the same classes, the same tints as the real line for the same values (the model and effort labels' colours and the battery's
fill at 62 percent equal the api session's, in the dark theme and the light), the battery coloured by its percentage (the three
sessions' fills are three colours), nothing opening on a click and no tooltip.

SETTINGS_PREVIEWS_SHOTS=<prefix> writes <prefix>-line-<pct>-<theme>.png, <prefix>-<section>-<theme>.png and a composite
<prefix>-beside-<theme>.png of the three real lines over the preview; SETTINGS_PREVIEWS_DUMP=<path> writes the whole
measurement. Skips LOUDLY without the extension deps or a Playwright browser (CI sets ROMP_SERVED_TESTS_REQUIRE=1 and installs
both, so a skip there is a failure). Synthetic throughout: placeholder sids, TESTHOST, invented text.
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
import test_ship_reship as _lab   # noqa: E402  the lab kernel's environment

NAMES = ["web", "api", "tests"]
CTX = {"web": 20, "api": 62, "tests": 95}   # the persisted context fill each session shows (the sdk registry's liveCtx)
SIDS = {n: "%s-1111-2222-3333-444444444444" % (chr(ord("a") + i) * 8) for i, n in enumerate(NAMES)}
PALETTE = [("#9cd2ff", "#0c1a2e"), ("#1EA1EB", "#ffffff"), ("#54B204", "#ffffff")]   # one identity colour per session
BRANCH = "search-module"


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
const out = { errors: [], notFound: [] };   // errors: page errors and console errors other than a resource load; notFound: the 404s by url (a load failure's console text names no url)
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
const page = await ctx.newPage();
page.on("pageerror", (e) => out.errors.push("pageerror: " + String(e)));
page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) out.errors.push("console: " + m.text()); });
page.on("response", (r) => { if (r.status() === 404) out.notFound.push(r.url().replace(/^https?:\/\/[^/]+/, "")); });
await page.goto(cfg.url);
await page.waitForSelector("#rail-gear", { timeout: 20000 });
let chatF = page.frames().find((f) => f.url().includes("/chat"));
for (let i = 0; i < 100 && !chatF; i++) { await page.waitForTimeout(100); chatF = page.frames().find((f) => f.url().includes("/chat")); }
if (!chatF) { console.error("no chat frame"); process.exit(1); }
await chatF.waitForFunction((n) => document.querySelectorAll("#tabs .tab[data-id]").length >= n, cfg.count, { timeout: 30000 });
// the real line: the badges (kind, text, computed colour) and the battery (size, fill, colour, text)
const readLine = (f) => f.evaluate(() => {
  const sl = document.getElementById("statusline"); const meta = sl && sl.querySelector("#spinner-meta"); const bar = sl && sl.querySelector("#ctx-bar");
  const btns = meta ? Array.from(meta.querySelectorAll(".meta-btn")).map((b) => { const l = b.querySelector(".meta-label"); return { kind: b.dataset.kind, text: l ? l.textContent : "", color: l ? getComputedStyle(l).color : null }; }) : null;
  const fill = bar ? bar.querySelector(".ctx-fill") : null, txt = bar ? bar.querySelector(".ctx-text") : null;
  return { btns, bar: bar ? { display: getComputedStyle(bar).display, w: Math.round(bar.getBoundingClientRect().width), h: Math.round(bar.getBoundingClientRect().height), fillW: fill ? fill.style.width : null,
                              fillBg: fill ? getComputedStyle(fill).backgroundColor : null, text: txt ? txt.textContent : null } : null };
});
// the theme the PRODUCT's way (round three): the store's theme key ("classic", "yatharth", "yatharth-light") and the same-document signal in the
// shell page; every frame applies it through applyTheme on the storage event (theme.ts: chat-theme-yatharth for both yatharth themes,
// theme-light for yatharth-light only). Never a body class toggled by hand, a combination the product cannot produce.
const THEMES = { dark: "classic", yatharth: "yatharth", light: "yatharth-light" };
const setTheme = async (frames, theme) => {
  await page.evaluate((name) => { const s = JSON.parse(localStorage.getItem("romp:settings") || "{}"); s.theme = name; localStorage.setItem("romp:settings", JSON.stringify(s)); window.dispatchEvent(new Event("romp:settings")); }, THEMES[theme]);
  for (const f of frames) await f.evaluate(() => window.dispatchEvent(new Event("romp:settings"))).catch(() => {});   // the same-document signal in each frame too (a frame may miss a storage event it raised itself)
  await page.waitForTimeout(600);
};
// the colormap the PRODUCT's way: the card's own picker (cmPick saves the store and posts setColormap to the kernel, which colours the
// line from its persisted map); the line's fill is awaited, since the kernel recolours on its next push
const setColormap = async (setF, name, fillBefore) => {
  await page.evaluate(() => window.__rompOpenSettings("general", "appearance"));   // the picker is the General tab's Appearance section
  await setF.waitForSelector("#rs-cmap-btn", { state: "visible", timeout: 10000 });
  await setF.click("#rs-cmap-btn"); await setF.waitForTimeout(150);
  await setF.click('#rs-cmap-list [data-cmap="' + name + '"]');
  await chatF.waitForFunction((was) => { const f = document.querySelector("#statusline #ctx-bar .ctx-fill"); return f && getComputedStyle(f).backgroundColor !== was; }, fillBefore, { timeout: 15000 });
  await page.evaluate(() => window.__rompOpenSettings("chat", "statusline"));   // back to the Status line section, where the preview is read
  await setF.waitForSelector("#rs-swidgets .rs-widget", { state: "visible", timeout: 10000 });
  await page.waitForTimeout(500);
};
const lineClip = async () => {
  const box = await chatF.evaluate(() => { const b = document.getElementById("statusline").getBoundingClientRect(); return { top: b.top, height: b.height }; });
  const fr = await page.evaluate(() => { const f = document.getElementById("f-chat").getBoundingClientRect(); return { x: f.left, y: f.top, w: f.width }; });
  return { x: fr.x, y: fr.y + box.top - 8, width: Math.min(fr.w, 1100), height: box.height + 16 };
};
const clips = { dark: {}, yatharth: {}, light: {} };
out.lines = { dark: {}, yatharth: {}, light: {} };
for (const theme of ["dark", "yatharth", "light"]) {
  out.bodyClasses = out.bodyClasses || {}; 
  await setTheme([page, chatF], theme);
  for (const name of cfg.names) {
    await chatF.click('#tabs .tab[data-id="' + cfg.sids[name] + '"]');
    await chatF.waitForSelector("#statusline .sl-right #spinner-meta", { timeout: 20000 });
    await chatF.waitForFunction((pct) => { const t = document.querySelector("#statusline #ctx-bar .ctx-text"); return t && t.textContent === pct + "%"; }, cfg.ctx[name], { timeout: 10000 }).catch(() => {});
    await page.waitForTimeout(400);
    out.lines[theme][name] = await readLine(chatF);
    if (cfg.shots) { const c = await lineClip(); clips[theme][name] = await page.screenshot({ clip: c }); fs.writeFileSync(cfg.shots + "-line-" + cfg.ctx[name] + "-" + theme + ".png", clips[theme][name]); }
  }
  out.bodyClasses[theme] = { chat: await chatF.evaluate(() => document.body.className) };
}
await setTheme([page, chatF], "dark");
await chatF.click('#tabs .tab[data-id="' + cfg.sids.api + '"]'); await page.waitForTimeout(300);
// the settings on the Status line section, through the shell's relay
await page.evaluate(() => window.__rompOpenSettings("chat", "statusline"));
await page.waitForFunction(() => document.body.classList.contains("settings-open"), null, { timeout: 20000 }).catch(() => {});
let setF = page.frames().find((f) => f.url().includes("/settings"));
for (let i = 0; i < 50 && !setF; i++) { await page.waitForTimeout(100); setF = page.frames().find((f) => f.url().includes("/settings")); }
if (!setF) { console.error("no settings frame"); process.exit(1); }
await setF.waitForSelector("#rs-swidgets .rs-widget", { timeout: 15000 });
await setF.waitForSelector('#rsettings .rs-card[data-section-landed="statusline"]', { timeout: 10000 }).catch(() => {});
await setF.evaluate(() => (document.fonts && document.fonts.ready) || null).catch(() => {});
// the previews: each section's title and box, the demo tabs, the status preview's badges and battery
const readPreviews = (f) => f.evaluate(() => {
  const sec = (host) => { const h = document.querySelector(host); const title = h.nextElementSibling; const okTitle = !!(title && title.classList.contains("rs-preview-title"));
    const box = okTitle ? title.nextElementSibling : title; const okBox = !!(box && box.classList.contains("rs-preview"));
    return { title: okTitle ? { text: title.textContent, bottom: title.getBoundingClientRect().bottom } : null,
             box: okBox ? { top: box.getBoundingClientRect().top, text: box.textContent, hasLabel: !!box.querySelector(".rs-preview-label") } : null,
             body: okBox ? box.querySelector(".rs-preview-body").firstElementChild : null }; };
  const tabOf = (el) => el ? { cls: el.className, chipBg: el.style.getPropertyValue("--chip-bg"), label: (() => { const l = el.querySelector(".tab-label"); return l ? { text: l.textContent, color: getComputedStyle(l).color, weight: getComputedStyle(l).fontWeight } : null; })() } : null;
  const tabSec = sec("#rs-widgets"), stSec = sec("#rs-swidgets");
  const rowDemos = Array.from(document.querySelectorAll("#rs-widgets .rs-widget:not(.rs-divider) .rs-widget-demo")).map((d) => { const t = tabOf(d.firstElementChild);
    if (t) { const c = d.getBoundingClientRect(), r = d.firstElementChild.getBoundingClientRect(); t.fits = r.left >= c.left - 0.5 && r.right <= c.right + 0.5; t.cellW = Math.round(c.width); t.tabW = Math.round(r.width); } return t; });
  const line = stSec.body; const meta = line ? line.querySelector(".spinner-meta") : null; const bar = line ? line.querySelector(".ctx-bar") : null;
  const btns = meta ? Array.from(meta.querySelectorAll(".meta-btn")).map((b) => { const l = b.querySelector(".meta-label"); return { kind: b.dataset.kind, text: l ? l.textContent : "", color: l ? getComputedStyle(l).color : null, cursor: getComputedStyle(b).cursor, tip: b._tipText || null, title: b.title || "", top: Math.round(b.getBoundingClientRect().top) }; }) : null;
  const fill = bar ? bar.querySelector(".ctx-fill") : null, txt = bar ? bar.querySelector(".ctx-text") : null;
  return { tab: { title: tabSec.title, box: tabSec.box, preview: tabOf(tabSec.body), rowDemos },
           status: { title: stSec.title, box: stSec.box, lineCls: line ? line.className : null, btns, copies: line ? line.querySelectorAll(".rs-sl-ctl, .rs-sl-batt").length : null,
                     bar: bar ? { display: getComputedStyle(bar).display, w: Math.round(bar.getBoundingClientRect().width), h: Math.round(bar.getBoundingClientRect().height), fillW: fill ? fill.style.width : null,
                                  fillBg: fill ? getComputedStyle(fill).backgroundColor : null, text: txt ? txt.textContent : null, cursor: getComputedStyle(bar).cursor, id: bar.id, title: bar.title || "",
                                  right: Math.round(bar.getBoundingClientRect().right), top: Math.round(bar.getBoundingClientRect().top) } : null,
                     boxRight: stSec.body ? Math.round(stSec.body.parentNode.parentNode.getBoundingClientRect().right) : null,
                     chipTop: line && line.querySelector(".rs-sl-chip") ? Math.round(line.querySelector(".rs-sl-chip").getBoundingClientRect().top) : null,
                     lineRoom: line ? line.clientWidth : null, lineDemand: line ? Math.round(Array.from(line.children).reduce((a, c) => a + c.getBoundingClientRect().width, 0) + 10 * (line.children.length - 1)) : null,
                     lineParts: line ? Array.from(line.children).map((c) => c.className.split(" ")[0] + ":" + Math.round(c.getBoundingClientRect().width)) : null,
                     rightParts: line && line.querySelector(".rs-sl-right") ? Array.from(line.querySelector(".rs-sl-right").children).map((c) => c.className.split(" ")[0] + ":" + Math.round(c.getBoundingClientRect().width)) : null,
                     font: line ? getComputedStyle(line).fontFamily.slice(0, 40) + " " + getComputedStyle(line).fontSize : null,
                     rightOrder: line && line.querySelector(".rs-sl-right") ? Array.from(line.querySelector(".rs-sl-right").children).map((c) => c.className) : null } };
});
out.previews = { dark: null, yatharth: null, light: null };
const previewClips = {};
for (const theme of ["dark", "yatharth", "light"]) {
  await setTheme([page, chatF, setF], theme);
  await page.mouse.move(5, 5); await page.waitForTimeout(400);
  out.bodyClasses[theme].settings = await setF.evaluate(() => document.body.className);
  out.previews[theme] = await readPreviews(setF);
  if (cfg.shots) {
    for (const section of ["tabwidgets", "statusline"]) {
      const c = await setF.evaluate((section) => { const head = document.querySelector('#rsettings .rs-sec[data-section="' + section + '"]'); head.scrollIntoView({ block: "start" });
        const host = document.getElementById(section === "tabwidgets" ? "rs-widgets" : "rs-swidgets"); let end = host.nextElementSibling; if (end && end.nextElementSibling && end.nextElementSibling.classList.contains("rs-preview")) end = end.nextElementSibling;
        const card = document.querySelector("#rsettings .rs-card").getBoundingClientRect(), a = head.getBoundingClientRect(), b = end.getBoundingClientRect();
        return { x: card.left, y: Math.max(0, a.top - 6), width: card.width, height: Math.min(window.innerHeight, b.bottom + 10) - Math.max(0, a.top - 6), pv: { x: b.left, y: b.top, width: b.width, height: b.height } }; }, section);
      await page.waitForTimeout(250);
      await page.screenshot({ path: cfg.shots + "-" + section + "-" + theme + ".png", clip: { x: c.x, y: c.y, width: c.width, height: c.height } });
      if (section === "statusline") previewClips[theme] = await page.screenshot({ clip: c.pv });
    }
  }
}
// the viridis map (round three, low a): the kernel rounds half to even, so the preview's arithmetic must too; the 62 percent fill on viridis is a tie
await setTheme([page, chatF, setF], "dark");
const auroraFill = (await readLine(chatF)).bar.fillBg;
await setColormap(setF, "viridis", auroraFill);
out.viridis = { preview: await readPreviews(setF), line: await readLine(chatF) };
await setColormap(setF, "aurora", out.viridis.line.bar.fillBg);
// the storage-only repaint (round four, low a): another frame's store write reaches the card as a StorageEvent with no body class change;
// the preview's fill must follow the store's colormap on that signal alone (the store is written and read back here, the kernel untouched)
out.storageProbe = await setF.evaluate(async () => {
  const fill = () => { const f = document.querySelector("#rs-swidgets ~ .rs-preview .ctx-fill"); return f ? getComputedStyle(f).backgroundColor : null; };
  const write = (name) => { const s = JSON.parse(localStorage.getItem("romp:settings") || "{}"); const was = s.colormap; s.colormap = name; localStorage.setItem("romp:settings", JSON.stringify(s)); return was; };
  const before = fill(), cls = document.body.className;
  const was = write("viridis"); window.dispatchEvent(new StorageEvent("storage", { key: "romp:settings" }));
  await new Promise((r) => setTimeout(r, 200));
  const after = fill(), clsAfter = document.body.className;
  write(was || "aurora"); window.dispatchEvent(new StorageEvent("storage", { key: "romp:settings" }));
  await new Promise((r) => setTimeout(r, 200));
  return { before, after, restored: fill(), bodyClassUnchanged: cls === clsAfter };
});
// a narrow card (round three, low e; round four, low b: the geometry as measured): the line wraps twice on the way down, at about 500 px
// the battery under the badges (the cluster's own wrap), from 470 down the whole cluster below the widgets with the battery beside the badges
const rowsOf = () => setF.evaluate(() => {
  const line = document.querySelector("#rs-swidgets ~ .rs-preview .rs-sl"); if (!line) return null; const top = (el) => el ? Math.round(el.getBoundingClientRect().top) : null;
  return { chip: top(line.querySelector(".rs-sl-chip")), dir: top(line.querySelector(".status-dir")), badge: top(line.querySelector(".meta-btn")), bar: top(line.querySelector(".ctx-bar")),
           barRight: Math.round(line.querySelector(".ctx-bar").getBoundingClientRect().right), boxRight: Math.round(line.parentNode.parentNode.getBoundingClientRect().right), room: line.clientWidth };
});
out.narrowRows = {};
for (const w of [500, 430, 380]) { await page.setViewportSize({ width: w, height: 900 }); await page.waitForTimeout(700); out.narrowRows[w] = await rowsOf(); }
await page.setViewportSize({ width: 430, height: 900 }); await page.waitForTimeout(700);
out.narrow = await readPreviews(setF);
await page.setViewportSize({ width: 1440, height: 900 }); await page.waitForTimeout(500);
// the composite: the three real lines over the preview, one image per theme (the settings frame covers the chat, so the two never share a viewport)
if (cfg.shots) {
  const comp = await ctx.newPage();
  for (const theme of ["dark", "yatharth", "light"]) {
    const img = (buf, cap) => '<figure style="margin:0 0 10px"><figcaption style="font:12px sans-serif;color:#888;margin:0 0 3px">' + cap + '</figcaption><img style="display:block;max-width:100%" src="data:image/png;base64,' + buf.toString("base64") + '"></figure>';
    const html = '<body style="margin:12px;background:' + (theme === "light" ? "#f4efe6" : "#1a1a1b") + ';width:1120px">'
      + cfg.names.map((n) => img(clips[theme][n], "the real line, session " + n + " at " + cfg.ctx[n] + " percent")).join("") + img(previewClips[theme], "the settings card's status line preview (Opus 5 at high, 62 percent)") + "</body>";
    await comp.setContent(html); await comp.waitForTimeout(300);
    await comp.screenshot({ path: cfg.shots + "-beside-" + theme + ".png", fullPage: true });
  }
  await comp.close();
}
fs.writeFileSync(cfg.out, JSON.stringify(out));
console.log("RESULT: ok");
await browser.close();
process.exit(0);
"""


class ServedSettingsPreviews(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        try:
            cls._boot()
            cls._run()
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def _boot(cls):
        if not os.path.isdir(os.path.join(EXT, "node_modules", "playwright")):
            raise unittest.SkipTest("extension deps absent (npm ci not run here): the served guard needs them")
        probe = subprocess.run(["node", "-e", "const p=require(process.argv[1]);process.stdout.write(p.chromium.executablePath())",
                                os.path.join(EXT, "node_modules", "playwright")], capture_output=True, text=True)
        if probe.returncode != 0 or not os.path.exists(probe.stdout.strip()):
            raise unittest.SkipTest("no playwright browser on this box: the served guard needs one (CI installs none)")
        cls.lab = tempfile.mkdtemp(prefix="settings-previews-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            raise unittest.SkipTest("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
        dist = os.path.join(cls.lab, "dist")
        copy_dist(os.path.join(EXT, "dist"), dist)
        state = os.path.join(cls.lab, "xdg", "romp")
        claude = os.path.join(cls.lab, "claude")
        cwd = os.path.join(cls.lab, "notes-api")
        for d in ("names", "sdk", "states"):
            os.makedirs(os.path.join(state, d), exist_ok=True)
        Path(state, "session-hosts").write_text("off\n")   # a lab root writes its own session-hosts off (the conftest rule)
        os.makedirs(cwd, exist_ok=True)
        cls.cwd = cwd
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        t0 = int(time.time()) - 900
        for i, name in enumerate(NAMES):
            sid = SIDS[name]
            bg, fg = PALETTE[i]
            Path(state, "names", sid).write_text("%s\t%s\t%s\t%s\n" % (name, cwd, bg, fg))
            Path(state, "sdk", sid + ".json").write_text(json.dumps(
                {"sid": sid, "name": name, "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": sid, "alive": True,
                 "model": "claude-opus-5", "liveModel": "Opus 5", "liveCtx": CTX[name]}))
            # the records carry the branch the way Claude Code stamps it, so the session's top-level gitBranch is known
            recs = [{"type": "user", "timestamp": iso(t0 + i), "uuid": "u1", "parentUuid": None, "promptSource": "typed", "sessionId": sid, "cwd": cwd, "gitBranch": BRANCH,
                     "message": {"role": "user", "content": "what does the %s session do in notes-api?" % name}},
                    {"type": "assistant", "timestamp": iso(t0 + i + 5), "uuid": "a1", "parentUuid": "u1", "sessionId": sid, "cwd": cwd, "gitBranch": BRANCH,
                     "message": {"role": "assistant", "model": "claude-opus-5", "stop_reason": "end_turn",
                                 "content": [{"type": "text", "text": "It keeps the %s side of the notes-api tidy." % name}]}}]
            Path(proj, sid + ".jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
        Path(state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 10}, "seven_day": {"pct": 10}}))
        cls.port, cls.token = _free_port(), "testtok-previews"
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
    def _run(cls):
        cfg = os.path.join(cls.lab, "cfg.json")
        outp = os.path.join(cls.lab, "out.json")
        with open(cfg, "w") as f:
            json.dump({"url": "http://127.0.0.1:%d/?token=%s" % (cls.port, cls.token), "count": len(NAMES), "out": outp, "names": NAMES, "sids": SIDS, "ctx": CTX,
                       "shots": os.environ.get("SETTINGS_PREVIEWS_SHOTS", "")}, f)
        driver = os.path.join(cls.lab, "driver.mjs")
        with open(driver, "w") as f:
            f.write(DRIVER)
        p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=420,
                           env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
        if p.returncode == 3:
            raise unittest.SkipTest("no playwright browser on this box: the served guard needs one")
        if p.returncode != 0:
            raise AssertionError("driver failed:\n" + p.stdout[-3000:] + p.stderr[-3000:] + "\nkernel:\n" + open(cls.klog).read()[-1500:])
        cls.out = json.load(open(outp))
        dump = os.environ.get("SETTINGS_PREVIEWS_DUMP")
        if dump:
            with open(dump, "w") as f:
                json.dump(cls.out, f, indent=1)

    @classmethod
    def tearDownClass(cls):
        k = getattr(cls, "kernel", None)
        if k:
            k.kill(); k.wait()
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

    def _p(self, theme="dark"):
        return self.out["previews"][theme]

    def test_the_preview_caption_is_a_title_above_the_box_in_both_sections_never_inside(self):
        p = self._p()
        for name in ("tab", "status"):
            s = p[name]; t = "\n  " + name + "=" + json.dumps({k: s[k] for k in ("title", "box")})
            self.assertIsNotNone(s["title"], name + ": a title right under the rows" + t)
            self.assertEqual(s["title"]["text"], "Preview", t)
            self.assertIsNotNone(s["box"], name + ": the box under the title" + t)
            self.assertLessEqual(s["title"]["bottom"], s["box"]["top"] + 0.5, name + ": the title ABOVE the box" + t)
            self.assertNotIn("Preview", s["box"]["text"], name + ": the word never inside the previewed thing" + t)
            self.assertFalse(s["box"]["hasLabel"], t)

    def test_the_demo_tab_reads_the_placeholder_session_name_in_its_identity_colour_in_the_preview_and_every_row(self):
        p = self._p()["tab"]; t = "\n  " + json.dumps({"preview": p["preview"], "rows": p["rowDemos"]})
        tabs = [p["preview"]] + [r for r in p["rowDemos"] if r is not None]
        self.assertGreaterEqual(len(tabs), 3, "the preview and the rows' demo tabs" + t)
        for tab in tabs:
            self.assertIn("colored", tab["cls"].split(), "the tab wears the identity colour class" + t)
            self.assertEqual(tab["chipBg"], "#9cd2ff", "the demo record's colour as the tab's --chip-bg" + t)
            self.assertEqual(tab["label"]["text"], "session_name", "the placeholder session_name (the user's copy), from the demo record" + t)
            self.assertEqual(tab["label"]["color"], "rgb(156, 210, 255)", "the label painted in it, as a real tab's is" + t)
            self.assertEqual(tab["label"]["weight"], "600", t)
        for tab in p["rowDemos"]:
            if tab is not None:
                self.assertTrue(tab["fits"], "the row's demo tab fits its cell (the placeholder is wider than the old name; a spill covered the grip)" + t)

    def test_the_status_line_preview_draws_the_controls_and_the_battery_through_the_lines_renderer_inert(self):
        s = self._p()["status"]; t = "\n  " + json.dumps(s)
        self.assertIsNotNone(s["btns"], "the badges are the line's .spinner-meta with .meta-btn children" + t)
        self.assertEqual([(b["kind"], b["text"]) for b in s["btns"]], [("mode", "Auto"), ("model", "Opus 5"), ("effort", "high")], "mode, model, effort, the line's order and words" + t)
        self.assertEqual(s["copies"], 0, "no words or boxed number standing in" + t)
        self.assertIsNotNone(s["bar"], "the battery is the line's .ctx-bar" + t)
        self.assertEqual((s["bar"]["text"], s["bar"]["fillW"]), ("62%", "62%"), "filled to its percentage, the number inside" + t)
        self.assertEqual(s["bar"]["id"], "", "no id on a preview: the chat's in-place refresh looks its own up by id" + t)
        self.assertEqual(s["rightOrder"][-2:], ["spinner-meta", "ctx-bar"], "the controls then the battery close the right cluster, as on the line" + t)
        for b in s["btns"]:
            self.assertEqual((b["cursor"], b["tip"], b["title"]), ("default", None, ""), b["kind"] + ": inert, no pointer, no tooltip" + t)
        self.assertEqual(s["bar"]["cursor"], "default", "the battery too" + t)
        self.assertEqual(s["bar"]["title"], "", "an inert battery carries no click-to-compact tooltip (round three, low b)" + t)
        self.assertEqual(len({b["top"] for b in s["btns"]}), 1, "the three badges share one row in the card's width: the preview never wraps a badge under another" + t)
        self.assertLessEqual(s["bar"]["right"], s["boxRight"] - 8, "the battery ends inside the box, never clipped by its border (the line wraps its cluster below when the card is too narrow)" + t)
        for theme in ("dark", "light"):
            p = self._p(theme)["status"]; tt = "\n  " + theme + ": room %s demand %s parts %s" % (p["lineRoom"], p["lineDemand"], p["lineParts"])
            self.assertLessEqual(abs(p["chipTop"] - p["bar"]["top"]), 8, theme + ": the whole line holds one row at the card's width, the chip and the battery level" + tt)
            self.assertLessEqual(p["lineDemand"], p["lineRoom"] - 8, theme + ": with room to spare" + tt)

    def test_the_preview_matches_the_real_line_for_the_same_values_and_the_battery_colours_by_percentage(self):
        bc = self.out["bodyClasses"]; tb = "\n  " + json.dumps(bc)
        self.assertNotIn("chat-theme-yatharth", bc["dark"]["chat"], "classic: the body bare" + tb)
        self.assertIn("chat-theme-yatharth", bc["yatharth"]["chat"], "yatharth: the theme class, no light" + tb); self.assertNotIn("theme-light", bc["yatharth"]["chat"], tb)
        self.assertIn("chat-theme-yatharth theme-light", " ".join(sorted(bc["light"]["chat"].split(), key=lambda c: c != "chat-theme-yatharth")), "yatharth-light: both classes, the product's only light theme" + tb)
        self.assertIn("chat-theme-yatharth", bc["light"]["settings"], "the settings page carries the theme class too (settings-page.ts applyTheme)" + tb)
        for theme in ("dark", "yatharth", "light"):
            s = self._p(theme)["status"]; api = self.out["lines"][theme]["api"]; t = "\n  " + theme + " preview=" + json.dumps(s) + "\n  api line=" + json.dumps(api)
            self.assertIsNotNone(s["btns"], t); self.assertIsNotNone(api["btns"], "the real line at 62 percent" + t)
            real = {b["kind"]: b for b in api["btns"]}
            for b in s["btns"]:
                self.assertEqual(b["text"], real[b["kind"]]["text"], b["kind"] + ": the same word" + t)
                self.assertEqual(b["color"], real[b["kind"]]["color"], b["kind"] + ": the same tint (classic: the kernel's rank on the selected colormap; yatharth: the tone; yatharth-light: the tone re-encoded readable, as the line's is)" + t)
            self.assertEqual((s["bar"]["fillBg"], s["bar"]["text"], s["bar"]["w"], s["bar"]["h"]), (api["bar"]["fillBg"], api["bar"]["text"], api["bar"]["w"], api["bar"]["h"]), "the battery: the same fill colour, number and box" + t)
            fills = {n: self.out["lines"][theme][n]["bar"]["fillBg"] for n in ("web", "api", "tests")}
            self.assertEqual(len(set(fills.values())), 3, "three percentages, three colours on the real line: the fill is coloured by its percentage\n  " + json.dumps(fills))
            self.assertEqual([self.out["lines"][theme][n]["bar"]["text"] for n in ("web", "api", "tests")], ["20%", "62%", "95%"], theme)
        self.assertEqual(self.out["errors"], [], "no page errors")

    def test_on_viridis_the_preview_fill_equals_the_kernels_rounding_at_the_tie(self):
        v = self.out["viridis"]; t = "\n  preview=" + json.dumps(v["preview"]["status"]["bar"]) + "\n  line=" + json.dumps(v["line"]["bar"])
        self.assertEqual(v["preview"]["status"]["bar"]["fillBg"], v["line"]["bar"]["fillBg"], "viridis at 62 percent is a rounding tie (172.5): the preview rounds half to even as the kernel does (round three, low a)" + t)
        self.assertEqual(v["line"]["bar"]["fillBg"], "rgb(44, 172, 128)", "the kernel's value" + t)
        for b in v["preview"]["status"]["btns"]:
            self.assertEqual(b["color"], {x["kind"]: x for x in v["line"]["btns"]}[b["kind"]]["color"], b["kind"] + " on viridis" + t)

    def test_a_narrow_card_wraps_the_cluster_below_the_chip_the_battery_under_the_badges_at_500_and_beside_them_from_470_down(self):
        rows = self.out["narrowRows"]; t = "\n  " + json.dumps(rows)
        for w in ("500", "430", "380"):
            r = rows[w]
            self.assertLessEqual(r["barRight"], r["boxRight"] - 8, w + " px: the battery ends inside the box (round three low e: at 430 px it sat 101 px outside the card)" + t)
            self.assertGreater(r["dir"], r["chip"] + 10, w + " px: the right cluster (the widgets, the badges, the battery) drops below the state chip as one block" + t)
        r = rows["500"]
        self.assertLessEqual(abs(r["badge"] - r["dir"]), 8, "500 px: the badges beside the widgets" + t)
        self.assertGreater(r["bar"], r["badge"] + 10, "500 px: the battery alone on the row under the badges (the cluster's own wrap)" + t)
        for w in ("430", "380"):
            r = rows[w]
            self.assertGreater(r["badge"], r["dir"] + 10, w + " px: the widgets take a row of their own" + t)
            self.assertLessEqual(abs(r["bar"] - r["badge"]), 8, w + " px: the badges and the battery share the row below them" + t)
        n = self.out["narrow"]["status"]
        self.assertEqual(len({b["top"] for b in n["btns"]}), 1, "the badges still share one row at 430 px\n  " + json.dumps(n["btns"]))

    def test_a_store_write_from_another_frame_repaints_the_preview_on_the_storage_event_alone(self):
        p = self.out["storageProbe"]; t = "\n  " + json.dumps(p)
        self.assertTrue(p["bodyClassUnchanged"], "no body class change along the probe: the storage signal alone is under test" + t)
        self.assertEqual(p["before"], "rgb(14, 164, 226)", "aurora's 62 percent before" + t)
        self.assertEqual(p["after"], "rgb(44, 172, 128)", "viridis's 62 percent after the StorageEvent: the card repainted its previews on the storage signal (round four, low a)" + t)
        self.assertEqual(p["restored"], p["before"], "and back on the restoring signal" + t)
        self.assertEqual([u for u in self.out["notFound"] if "/dist/" in u], [], "every file of ours the pages ask for is served: " + json.dumps(self.out["notFound"]))


if __name__ == "__main__":
    unittest.main()
