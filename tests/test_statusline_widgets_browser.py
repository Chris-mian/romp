#!/usr/bin/env python3
"""The status line's WIDGETS and their settings section (T409, the user 2026-09-13), on the served dashboard: a hermetic kernel
serves the landing with two synthetic notes-api sessions (web and api, idle, TESTHOST, their transcripts stamped with the
branch search-module); the chat frame's line above the composer carries the widgets in their order (by default the folder
by name, then the branch, leading the right cluster before the controls; no session name, no host), the Chat tab's Status
line section (right after Tab widgets, reached through the shell's relay, the whole entry point: no gear on the line) lists
one row per widget with a live demo drawn by the line's own render, a sliding switch and the widget's options; a switch or
an option written there reaches the chat frame's line live (the storage event), and the store's two mirrors (showBranch,
showSessionBadge) follow; a store from before the widgets shows the branch whatever its showBranch says (the one-shot
migration: that key was the gear's injected default and is never read; the widget defaults apply, and the first save of
the prefs writes the key and the mirrors), an unrelated save leaves that store's keys as they were, and the branch row
switched off stays off in a page opened afresh in the same browser.

STATUSLINE_SHOTS=<prefix> writes <prefix>-line-<theme>.png and <prefix>-settings-<theme>.png; STATUSLINE_DUMP=<path> writes
the whole measurement. Skips LOUDLY without the extension deps or a Playwright browser (CI sets ROMP_SERVED_TESTS_REQUIRE=1
and installs both, so a skip there is a failure). Synthetic throughout: placeholder sids, TESTHOST, invented text.
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

NAMES = ["web", "api"]
SIDS = {n: "%s-1111-2222-3333-444444444444" % (chr(ord("a") + i) * 8) for i, n in enumerate(NAMES)}
PALETTE = [("#9cd2ff", "#0c1a2e"), ("#1EA1EB", "#ffffff")]
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
const out = {};
const openShell = async (ctx) => {
  const page = await ctx.newPage();
  await page.goto(cfg.url);
  await page.waitForSelector("#rail-gear", { timeout: 20000 });
  let chatF = page.frames().find((f) => f.url().includes("/chat"));
  for (let i = 0; i < 100 && !chatF; i++) { await page.waitForTimeout(100); chatF = page.frames().find((f) => f.url().includes("/chat")); }
  if (!chatF) { console.error("no chat frame"); process.exit(1); }
  await chatF.waitForFunction((n) => document.querySelectorAll("#tabs .tab[data-id]").length >= n, cfg.count, { timeout: 30000 });
  await chatF.click('#tabs .tab[data-id="' + cfg.sidWeb + '"]');
  await chatF.waitForSelector("#statusline .sl-right #spinner-meta", { timeout: 20000 });
  await chatF.waitForTimeout(400);
  return { page, chatF };
};
// the line: every child of #statusline and of its right cluster, in order, with the widgets' facts
const readLine = (chatF) => chatF.evaluate(() => {
  const sl = document.getElementById("statusline");
  const desc = (n) => ({ cls: n.className, text: n.textContent, title: n.title || "", act: n.dataset.act || null, cwd: n.dataset.cwd || null, id: n.dataset.id || null, bg: n.style.background || "" });
  const kids = Array.from(sl.children).map(desc);
  const right = sl.querySelector(".sl-right");
  const s = JSON.parse(localStorage.getItem("romp:settings") || "{}");
  return { kids, right: right ? Array.from(right.children).map(desc) : null,
           store: { statusWidgets: "statusWidgets" in s ? s.statusWidgets : "absent", showBranch: "showBranch" in s ? s.showBranch : "absent", showSessionBadge: "showSessionBadge" in s ? s.showSessionBadge : "absent" } };
});
const settingsFrame = async (page) => {
  await page.waitForFunction(() => document.body.classList.contains("settings-open"), null, { timeout: 20000 }).catch(() => {});
  let setF = page.frames().find((f) => f.url().includes("/settings"));
  for (let i = 0; i < 50 && !setF; i++) { await page.waitForTimeout(100); setF = page.frames().find((f) => f.url().includes("/settings")); }
  return setF;
};
const readPanel = (setF) => setF.evaluate(() => {
  const rows = Array.from(document.querySelectorAll("#rs-swidgets .rs-widget")).map((r) => {
    const sw = r.querySelector(".rs-switch"); const desc = r.querySelector(".rs-widget-name .rs-sub");
    const demo = r.querySelector(".rs-widget-demo").firstElementChild;
    return { id: r.dataset.widget, label: r.querySelector(".rs-widget-name b").textContent, desc: desc ? desc.textContent : "",
             sw: { role: sw.getAttribute("role"), checked: sw.getAttribute("aria-checked"), on: sw.classList.contains("on") }, off: r.classList.contains("rs-widget-off"),
             demo: demo ? { cls: demo.className, text: demo.textContent, hasSvg: !!demo.querySelector("svg") } : null,
             opts: Array.from(r.querySelectorAll(".rs-widget-opt")).map((o) => ({ key: o.dataset.opt, label: o.title, current: (o.querySelector("button") || {}).textContent || "" })) };
  });
  const card = document.querySelector("#rsettings .rs-card");
  const heads = Array.from(document.querySelectorAll('#rsettings .rs-pane[data-pane="chat"] .rs-sec')).map((h) => h.textContent);
  const tw = document.querySelector('#rsettings .rs-sec[data-section="tabwidgets"]'), sl = document.querySelector('#rsettings .rs-sec[data-section="statusline"]');
  return { rows, heads, landed: card ? card.getAttribute("data-section-landed") : null, order: tw && sl ? (tw.compareDocumentPosition(sl) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0 : null,
           gearOnLine: !!document.querySelector("#statusline .tab-widgets-gear"), legacyRows: !!document.querySelector("#rs-branch, #rs-badge") };
});
// ── the main context: the default line, the section, the switches and the option reaching the line live ──
const ctx = await browser.newContext({ viewport: { width: 1440, height: 800 }, deviceScaleFactor: 2 });
const { page, chatF } = await openShell(ctx);
out.line0 = await readLine(chatF);
out.chatGear = await chatF.evaluate(() => ({ onLine: !!document.querySelector("#statusline button.tab-widgets-gear, #statusline .rs-gear"),
  stripRows: (() => { const g = document.querySelector("#tabs .tab-strip-end .tab-widgets-gear"); return g ? g.title : null; })() }));
await page.evaluate(() => window.__rompOpenSettings("chat", "statusline"));
const setF = await settingsFrame(page);
if (!setF) { console.error("no settings frame"); process.exit(1); }
await setF.waitForSelector("#rs-swidgets .rs-widget", { timeout: 15000 });
await setF.waitForSelector('#rsettings .rs-card[data-section-landed="statusline"]', { timeout: 10000 }).catch(() => {});
await setF.evaluate(() => (document.fonts && document.fonts.ready) || null).catch(() => {});
out.panel0 = await readPanel(setF);
const flip = async (id) => { await setF.click('#rs-swidgets .rs-widget[data-widget="' + id + '"] .rs-switch'); await setF.waitForTimeout(400); };
await flip("branch");
out.branchOff = { line: await readLine(chatF), panel: await readPanel(setF) };
await flip("branch");
out.branchBack = { line: await readLine(chatF) };
await flip("name");
out.nameOn = { line: await readLine(chatF), panel: await readPanel(setF) };
await flip("name");
// the folder's option through the house picker: Full path, then back to Name only
const pick = async (value) => setF.evaluate(async (value) => {
  const wrap = document.querySelector('#rs-swidgets .rs-widget[data-widget="folder"] .rs-widget-opt[data-opt="show"]');
  if (!wrap) return { present: false };
  wrap.querySelector("button").click();
  await new Promise((r) => setTimeout(r, 100));
  const rows = Array.from(wrap.querySelectorAll("[data-swopt-folder-show]"));
  const labels = rows.map((r) => r.textContent.replace(/✓/g, "").trim());
  const row = rows.find((r) => r.getAttribute("data-swopt-folder-show") === value);
  if (row) row.click();
  await new Promise((r) => setTimeout(r, 400));
  return { present: true, labels, picked: !!row };
}, value);
out.pathPick = await pick("path");
out.pathOn = { line: await readLine(chatF), panel: await readPanel(setF) };
await pick("name");
out.pathBack = { line: await readLine(chatF) };
// screenshots: the line with the defaults, and the Chat tab at its Status line section, dark then light
const shot = async (theme) => {
  for (const f of [page, chatF, setF]) await f.evaluate((t) => document.body.classList.toggle("theme-light", t === "light"), theme).catch(() => {});
  await page.mouse.move(5, 5);   // the pointer off the rows: a row's hover popover would cover the row below it
  await page.waitForTimeout(600);
  if (!cfg.shots) return;
  const card = await setF.evaluate(() => { const b = document.querySelector("#rsettings .rs-card").getBoundingClientRect(); return { x: b.left, y: b.top, width: b.width, height: b.height }; });
  const fr = await page.evaluate(() => { const f = document.getElementById("f-settings").getBoundingClientRect(); return { x: f.left, y: f.top }; });
  await page.screenshot({ path: cfg.shots + "-settings-" + theme + ".png", clip: { x: fr.x + card.x, y: fr.y + card.y, width: card.width, height: card.height } });
};
await shot("dark"); await shot("light");
for (const f of [page, chatF, setF]) await f.evaluate(() => document.body.classList.remove("theme-light")).catch(() => {});
await page.keyboard.press("Escape"); await page.waitForTimeout(300);
for (const theme of ["dark", "light"]) {
  for (const f of [page, chatF]) await f.evaluate((t) => document.body.classList.toggle("theme-light", t === "light"), theme);
  await page.waitForTimeout(600);
  if (cfg.shots) {
    const box = await chatF.evaluate(() => { const b = document.getElementById("statusline").getBoundingClientRect(); return { top: b.top, height: b.height }; });
    const fr = await page.evaluate(() => { const f = document.getElementById("f-chat").getBoundingClientRect(); return { x: f.left, y: f.top, w: f.width }; });
    await page.screenshot({ path: cfg.shots + "-line-" + theme + ".png", clip: { x: fr.x, y: fr.y + box.top - 10, width: Math.min(fr.w, 1200), height: box.height + 20 } });
  }
}
await page.close(); await ctx.close();
// ── LEGACY STORES: a browser from before the widgets holds showBranch and no statusWidgets (the one-shot migration: the
// key was the gear's injected default, not a choice, so the branch shows whatever it says; the first widget save writes
// the prefs and the mirror, and a page opened afresh in the same browser reads that choice) ──
out.legacy = {};
for (const mode of ["off", "on", "absent"]) {
  const c2 = await browser.newContext({ viewport: { width: 1440, height: 800 } });
  // seeded ONCE per browser context: a later page (the reload leg below) keeps whatever the gear saved
  await c2.addInitScript(([m]) => { try { if (localStorage.getItem("romp:settings") !== null) return; const s = { compact: true }; if (m === "off") s.showBranch = false; if (m === "on") s.showBranch = true; localStorage.setItem("romp:settings", JSON.stringify(s)); } catch (e) {} }, [mode]);
  const { page: p2, chatF: cf } = await openShell(c2);
  const before = await readLine(cf);
  await p2.evaluate(() => window.__rompOpenSettings("chat", "statusline"));
  const sf = await settingsFrame(p2);
  await sf.waitForSelector("#rs-swidgets .rs-widget", { timeout: 15000 });
  await sf.waitForTimeout(300);
  const panelBefore = await readPanel(sf);
  await sf.click("#rs-compact"); await sf.waitForTimeout(500);   // an unrelated setting's save
  out.legacy[mode] = { before, panelBefore, after: await readLine(cf), panelAfter: await readPanel(sf) };
  if (mode === "off") {
    // the upgraded browser switches the branch off in the Status line section: the line drops it at once, and a page
    // opened afresh in the same context (the browser's next load) reads the choice from the prefs
    await sf.click('#rs-swidgets .rs-widget[data-widget="branch"] .rs-switch'); await sf.waitForTimeout(500);
    out.legacy.offSwitched = await readLine(cf);
    await p2.close();
    const { page: p3, chatF: cf3 } = await openShell(c2);
    out.legacy.offReloaded = await readLine(cf3);
    await p3.close();
  } else await p2.close();
  await c2.close();
}
fs.writeFileSync(cfg.out, JSON.stringify(out));
console.log("RESULT: ok");
await browser.close();
process.exit(0);
"""


class ServedStatusLineWidgets(unittest.TestCase):
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
        cls.lab = tempfile.mkdtemp(prefix="statusline-widgets-")
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
                 "model": "claude-opus-5", "liveModel": "Opus 5", "liveCtx": 62}))
            # the records carry the branch the way Claude Code stamps it, so the session's top-level gitBranch is known
            recs = [{"type": "user", "timestamp": iso(t0 + i), "uuid": "u1", "parentUuid": None, "promptSource": "typed", "sessionId": sid, "cwd": cwd, "gitBranch": BRANCH,
                     "message": {"role": "user", "content": "what does the %s session do in notes-api?" % name}},
                    {"type": "assistant", "timestamp": iso(t0 + i + 5), "uuid": "a1", "parentUuid": "u1", "sessionId": sid, "cwd": cwd, "gitBranch": BRANCH,
                     "message": {"role": "assistant", "model": "claude-opus-5", "stop_reason": "end_turn",
                                 "content": [{"type": "text", "text": "It keeps the %s side of the notes-api tidy." % name}]}}]
            Path(proj, sid + ".jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
        Path(state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 10}, "seven_day": {"pct": 10}}))
        cls.port, cls.token = _free_port(), "testtok-statusline"
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
            json.dump({"url": "http://127.0.0.1:%d/?token=%s" % (cls.port, cls.token), "count": len(NAMES), "out": outp, "sidWeb": SIDS["web"],
                       "shots": os.environ.get("STATUSLINE_SHOTS", "")}, f)
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
        dump = os.environ.get("STATUSLINE_DUMP")
        if dump:
            with open(dump, "w") as f:
                json.dump(cls.out, f, indent=1)

    @classmethod
    def tearDownClass(cls):
        k = getattr(cls, "kernel", None)
        if k:
            k.kill(); k.wait()
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

    def _right_classes(self, line):
        return [k["cls"] for k in line["right"]]

    def test_the_line_carries_the_defaults_in_order_the_folder_by_name_then_the_branch_leading_the_right_cluster(self):
        line = self.out["line0"]
        kids = [k["cls"] for k in line["kids"]]
        self.assertNotIn("chip chip-session", kids, "the session name is off by default (the user's ruling)")
        self.assertTrue(kids[0].startswith("chip"), "the state chip leads the line when no left widget is on: %r" % kids)
        right = line["right"]
        self.assertEqual([k["cls"] for k in right][:3], ["status-dir folder-link", "status-branch", "spinner-meta"], "folder, branch, then the controls: %r" % right)
        dir_ = right[0]
        self.assertEqual(dir_["text"], " notes-api", "the folder by name")
        self.assertEqual(dir_["cwd"], self.cwd); self.assertEqual(dir_["id"], SIDS["web"])
        self.assertEqual(dir_["act"], "browseFiles", "on the web a click browses the folder in the dashboard")
        self.assertTrue(dir_["title"].startswith(self.cwd), "the full path on hover: %r" % dir_["title"])
        self.assertEqual(right[1]["text"], "⎇ " + BRANCH, "the branch from the transcript's stamp")
        self.assertNotIn("status-host", " ".join(k["cls"] for k in right), "no host for a local session")
        self.assertEqual(line["store"]["statusWidgets"], "absent", "nothing written until the user changes a row")

    def test_no_gear_on_the_line_and_no_new_menu_row_the_settings_section_is_the_whole_entry_point(self):
        self.assertFalse(self.out["chatGear"]["onLine"], "the user's ruling: no gear icon on the line")
        self.assertFalse(self.out["panel0"]["gearOnLine"])
        self.assertEqual(self.out["chatGear"]["stripRows"], "Tab strip settings", "the strip's gear is a plain button to the settings (T415), no Status line row added: %r" % self.out["chatGear"])
        self.assertEqual(self.out["panel0"]["landed"], "statusline", "the relay's ask lands on the Status line section")
        self.assertTrue(self.out["panel0"]["order"], "the section follows Tab widgets")
        self.assertIn("Status line", self.out["panel0"]["heads"])
        self.assertFalse(self.out["panel0"]["legacyRows"], "the Show git branch and Show session badge checkboxes are gone")

    def test_each_row_shows_a_live_demo_drawn_by_the_lines_render_a_switch_at_its_default_and_its_options(self):
        rows = self.out["panel0"]["rows"]
        self.assertEqual([r["id"] for r in rows], ["name", "folder", "branch", "host"])
        self.assertEqual([r["label"] for r in rows], ["Session name", "Folder", "Git branch", "Host"])
        self.assertEqual([r["sw"]["checked"] for r in rows], ["false", "true", "true", "false"], "the user's defaults")
        self.assertTrue(all(r["sw"]["role"] == "switch" and r["desc"] for r in rows))
        by = {r["id"]: r for r in rows}
        self.assertEqual((by["folder"]["demo"]["cls"], by["folder"]["demo"]["text"], by["folder"]["demo"]["hasSvg"]), ("status-dir", " notes-api", True))
        self.assertEqual((by["branch"]["demo"]["cls"], by["branch"]["demo"]["text"]), ("status-branch", "⎇ search-module"))
        self.assertEqual((by["name"]["demo"]["cls"], by["name"]["demo"]["text"]), ("chip chip-session", "session_name"))   # the demo record's placeholder name (T415 part two)
        self.assertEqual((by["host"]["demo"]["cls"], by["host"]["demo"]["text"]), ("status-branch status-host", "@ TESTHOST"), "the demo record is a remote session")
        self.assertEqual([(o["key"], o["label"]) for o in by["folder"]["opts"]], [("show", "Show")])
        self.assertIn("Name only", by["folder"]["opts"][0]["current"])
        self.assertTrue(by["name"]["off"] and by["host"]["off"] and not by["folder"]["off"])

    def test_a_switch_writes_the_prefs_and_both_mirrors_and_the_line_follows_live(self):
        off = self.out["branchOff"]
        self.assertEqual(self._right_classes(off["line"])[:2], ["status-dir folder-link", "spinner-meta"], "the branch left the line at once")
        self.assertEqual(off["line"]["store"]["statusWidgets"]["on"], {"branch": False})
        self.assertEqual(off["line"]["store"]["showBranch"], False, "the mirror follows")
        self.assertEqual([r["sw"]["checked"] for r in off["panel"]["rows"]], ["false", "true", "false", "false"])
        self.assertEqual(self._right_classes(self.out["branchBack"]["line"])[:3], ["status-dir folder-link", "status-branch", "spinner-meta"])
        on = self.out["nameOn"]
        self.assertEqual(on["line"]["kids"][0]["cls"], "chip chip-session", "the name leads the line, before the state chip")
        self.assertEqual((on["line"]["kids"][0]["text"], on["line"]["kids"][0]["bg"]), ("web", "rgb(156, 210, 255)"), "on its identity colour")
        self.assertEqual(on["line"]["store"]["showSessionBadge"], True, "the mirror follows")

    def test_the_folders_full_path_option_reaches_the_line_and_back(self):
        self.assertEqual(self.out["pathPick"], {"present": True, "labels": ["Name only", "Full path"], "picked": True})
        r = self.out["pathOn"]["line"]["right"][0]
        self.assertEqual(r["cls"], "status-dir status-dir-full folder-link")
        self.assertEqual(r["text"], " " + self.cwd)
        self.assertEqual(self.out["pathOn"]["line"]["store"]["statusWidgets"]["opts"], {"folder": {"show": "path"}})
        self.assertEqual(self.out["pathBack"]["line"]["right"][0]["cls"], "status-dir folder-link")

    def test_a_store_from_before_the_widgets_shows_the_branch_whatever_its_key_says_and_an_unrelated_save_leaves_the_store_alone(self):
        # the one-shot migration (the user's call through the manager, 2026-09-13): the legacy key was the gear's injected
        # default, not a choice, so every pre-widgets store reads the widget defaults; a load writes nothing
        L = self.out["legacy"]
        for mode in ("off", "on", "absent"):
            self.assertIn("status-branch", " ".join(self._right_classes(L[mode]["before"])), "%s: the branch shows after the upgrade (the widget's default)" % mode)
            self.assertEqual([r["sw"]["checked"] for r in L[mode]["panelBefore"]["rows"] if r["id"] == "branch"], ["true"], "%s: the row reads the widget's default, never the legacy key" % mode)
        for mode, want in (("off", False), ("on", True), ("absent", "absent")):
            after = L[mode]["after"]["store"]
            self.assertEqual(after["statusWidgets"], "absent", "%s: an unrelated save writes no statusWidgets" % mode)
            self.assertEqual(after["showBranch"], want, "%s: showBranch as it was (a mirror only from the first widget save)" % mode)
            self.assertEqual(self._right_classes(L[mode]["after"]), self._right_classes(L[mode]["before"]), "%s: the line unchanged" % mode)

    def test_the_upgraded_browsers_row_switched_off_stays_off_across_a_reload(self):
        L = self.out["legacy"]
        sw = L["offSwitched"]
        self.assertNotIn("status-branch", " ".join(self._right_classes(sw)), "the switch off dropped the branch from the line at once")
        self.assertEqual((sw["store"]["statusWidgets"]["on"], sw["store"]["showBranch"]), ({"branch": False}, False), "the first widget save wrote the prefs and the mirror")
        rl = L["offReloaded"]
        self.assertNotIn("status-branch", " ".join(self._right_classes(rl)), "a page opened afresh reads the choice: the branch stays off")
        self.assertEqual((rl["store"]["statusWidgets"]["on"], rl["store"]["showBranch"]), ({"branch": False}, False))


if __name__ == "__main__":
    unittest.main()
