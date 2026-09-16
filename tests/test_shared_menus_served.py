#!/usr/bin/env python3
"""The shared menu builder tidy (v0.16.0): the chat's tab menu, the feed's card menu and the file browser's row menu open through
ui/webview/ctx-menu.ts, the builder the Sessions pane's menu introduced, instead of each building its card, placement and
dismissal by hand with no keyboard reach. One served check per surface, on the dashboard page (the shell with its chat and feed
panes) over a hermetic kernel with synthetic sessions (the notes-api world: web, api, tests, registered SDK records with closed
transcripts, so nothing is ever spawned) and a project folder holding one file and one directory for the browser to list:
  1. the chat tab menu: a right-click on web's tab opens the card in the menu role, its rows in the menu-item role and reachable
     (Rename first, Tags among them, Browse files last); the card holds the focus and ArrowDown moves it to the first row; Enter
     on Rename closes the card and opens the strip's inline rename, Escape ends it; the card takes the focus from the tab the
     right-click's press focused and Escape hands it back to that tab; the Tags row's click opens its flyout inside the card
     without closing it, and a press outside closes both;
  2. the feed card menu: a synthetic card on the feed (the page's own frame path); a right-click opens the card in the menu role
     with the bell row (its drawn icon) and Browse files; ArrowDown focuses the first row; Escape closes; ArrowDown twice and
     Enter pick Browse files and the file browser opens over the feed with the folder's rows;
  3. the file browser's row menu: a right-click on the file's row opens #fb-ctx in the menu role with Copy path, Download and Open
     folder window (its sub-line); ArrowDown focuses the first row; Escape closes the menu and leaves the browser up (the topmost
     layer peels first); the directory's row offers no Download; a second Escape closes the browser.
Red first per road at the tidy's base, where each menu opened without the role and without the keys. Skips loudly without the
extension deps or a browser.
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
from pathlib import Path

from tests.dist_copy import copy_dist

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
EXT = os.path.join(ROOT, "vscode-extension")
sys.path.insert(0, HERE)
import test_ship_reship_served as _lab   # noqa: E402  the lab kernel's environment (the module, not its classes)

SID_WEB = "aaaaaaaa-6000-2222-3333-777777777777"
SID_API = "aaaaaaaa-6000-2222-3333-888888888888"
SID_TESTS = "aaaaaaaa-6000-2222-3333-999999999999"
CARD = "aaaaaaaa-6000-2222-3333-000000000c01"


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _transcript(sid, tag, cwd, pairs):
    out, parent, t = [], None, 1_700_000_000
    for i in range(pairs):
        u = "11111111-2222-4333-8444-%02x00006a%04x" % (tag, i)
        a = "11111111-2222-4333-8444-%02x00006b%04x" % (tag, i)
        ts = lambda k: time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t + i * 60 + k))
        out.append({"type": "user", "uuid": u, "parentUuid": parent, "timestamp": ts(0), "sessionId": sid, "cwd": cwd,
                    "message": {"role": "user", "content": "please keep going with the notes-api search module (part %d)" % (i + 1)}})
        out.append({"type": "assistant", "uuid": a, "parentUuid": u, "timestamp": ts(5), "sessionId": sid, "cwd": cwd,
                    "message": {"id": "msg_lab_%d_%04d" % (tag, i), "type": "message", "role": "assistant", "model": "claude-sonnet-5",
                                "content": [{"type": "text", "text": "Note %d. The ranking pass reads its weights from the config now." % (i + 1)}],
                                "stop_reason": "end_turn"}})
        parent = a
    return "\n".join(json.dumps(r) for r in out) + "\n"


DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));
let browser;
try { browser = await chromium.launch(); } catch (e) { fs.writeSync(2, "no browser: " + e + "\n"); process.exit(3); }
const out = { roads: {}, errors: [] };
const finish = async () => { fs.writeFileSync(cfg.out, JSON.stringify(out)); await browser.close(); process.exit(0); };
const die = async (why) => { out.died = why; await finish(); };
process.on("unhandledRejection", async (e) => { await die("unhandled: " + String(e).split("\n")[0]); });
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
page.on("pageerror", (e) => out.errors.push(String(e)));
const T = 20000;
const waitFn = async (fn, arg, why) => page.waitForFunction(fn, arg, { timeout: T }).catch(async (e) => { await die(why + " (" + String(e).split("\n")[0] + ")"); });
const frameOf = async (fid) => (await page.$("#" + fid)).contentFrame();
// the open menu in a pane's document: the card's role and id, its own rows (a flyout's are a nested card's), their roles,
// reach, icons and sub-lines, where the focus sits, how many flyouts are open
const menuState = (fid, sel) => page.evaluate(([fid, sel]) => {
  const d = document.getElementById(fid).contentDocument;
  const m = d.querySelector(sel || ".ctx-menu");
  if (!m) return { open: false };
  const rows = Array.from(m.children).filter((c) => c.classList.contains("ctx-item"));
  const a = d.activeElement;
  return { open: true, role: m.getAttribute("role"), id: m.id || "",
    rows: rows.map((r) => (r.querySelector(".ctx-item-label") || r).textContent.trim()),
    roles: rows.map((r) => r.getAttribute("role")), reach: rows.every((r) => r.hasAttribute("tabindex")),
    icons: rows.map((r) => !!r.querySelector(".ctx-icon")),
    subs: rows.map((r) => { const s = r.querySelector(".ctx-item-sub"); return s ? s.textContent : null; }),
    focus: a === m ? "menu" : rows.indexOf(a) >= 0 ? rows.indexOf(a) : (a ? (a.id || a.tagName) : null),
    flyouts: m.querySelectorAll(".ctx-sub").length };
}, [fid, sel || null]);
const activeIn = (fid) => page.evaluate((fid) => { const d = document.getElementById(fid).contentDocument; const a = d.activeElement; return !a ? null : a.classList.contains("tab") && a.dataset.id ? "tab:" + a.dataset.id : (a.id || a.tagName); }, fid);
// a synthetic frame on a pane's window: the page's own frame path (a MessageEvent, what the socket shim dispatches)
const deliver = (fid, m) => page.evaluate(([fid, m]) => new Promise((res) => { const w = document.getElementById(fid).contentWindow; w.dispatchEvent(new w.MessageEvent("message", { data: m })); w.requestAnimationFrame(() => res(null)); }), [fid, m]);
// a right-click that misses its row (the base has the row but the claim reads red on the role) is recorded, never fatal
const rightClick = async (fid, sel) => { const fr = await frameOf(fid); return fr.locator(sel).first().click({ button: "right", timeout: 5000 }).then(() => true).catch(() => false); };

// ---- load: the chat's tabs, the feed pane switched on ----
await page.goto(cfg.url);
await waitFn((sid) => { const d = document.getElementById("f-chat") && document.getElementById("f-chat").contentDocument; return !!(d && d.querySelector('#tabs .tab[data-id="' + sid + '"]')); }, cfg.web, "web's tab never appeared");
await page.evaluate(() => { if (window.__rompPaneToggle) window.__rompPaneToggle("feed", true); });
await waitFn(() => { const d = document.getElementById("f-feed") && document.getElementById("f-feed").contentDocument; return !!(d && d.getElementById("feed-list")); }, null, "the feed pane never came up");
const chat = await frameOf("f-chat");
const tabSel = '#tabs .tab[data-id="' + cfg.web + '"]';
// 1. the chat tab menu
await chat.locator("#composer-input").click();   // the composer holds the focus first: the return road reads where it goes back to
out.roads.composerFocused = await activeIn("f-chat");
await rightClick("f-chat", tabSel);
await page.waitForTimeout(80);
out.roads.tabMenu = await menuState("f-chat");
await page.keyboard.press("ArrowDown");
out.roads.tabMenuArrow = await menuState("f-chat");
await page.keyboard.press("Enter");   // Rename: the strip's inline input
await page.waitForTimeout(80);
out.roads.tabRename = { menu: (await menuState("f-chat")).open, input: await page.evaluate((sel) => { const d = document.getElementById("f-chat").contentDocument; const i = d.querySelector(sel + " .tab-rename"); return i ? { value: i.value, focused: d.activeElement === i } : null; }, tabSel) };
await page.keyboard.press("Escape");
await page.waitForTimeout(80);
out.roads.tabRenameGone = !(await page.evaluate((sel) => !!document.getElementById("f-chat").contentDocument.querySelector(sel + " .tab-rename"), tabSel));
// …the focus return: the right-click's press focused the tab (a focusable strip item), the card took the focus, and Escape
// hands it back to the tab, the opener
await chat.locator("#composer-input").click();
await rightClick("f-chat", tabSel);
await page.waitForTimeout(80);
const opened = await menuState("f-chat");
await page.keyboard.press("Escape");
await page.waitForTimeout(80);
out.roads.tabEscape = { opened: opened.open, held: opened.focus, menu: (await menuState("f-chat")).open, active: await activeIn("f-chat") };
// …the Tags row keeps the card open and opens its flyout inside it; a press outside (the composer) closes both
await rightClick("f-chat", tabSel);
await page.waitForTimeout(80);
await chat.locator(".ctx-menu > .ctx-item", { hasText: "Tags" }).first().click({ timeout: 2500 }).catch(() => null);
await page.waitForTimeout(150);
out.roads.tabTags = await menuState("f-chat");
await chat.locator("#composer-input").click();
await page.waitForTimeout(80);
out.roads.tabOutside = await menuState("f-chat");
// 2. the feed card menu: one synthetic working card for web
const now = Math.floor(Date.now() / 1000);
await deliver("f-feed", { type: "feed", asks: [{ itemId: cfg.card, sid: cfg.web, name: "web", color: { bg: "#3a86ff", fg: "#ffffff" }, text: "notes-api: draft the search index",
  t: now - 60, live: true, turnId: "turn-c01", trgb: [30, 161, 235], column: "working", tree: [] }],
  sessions: [{ sid: cfg.web, name: "web" }, { sid: cfg.api, name: "api" }, { sid: cfg.tests, name: "tests" }], order: [cfg.web, cfg.api, cfg.tests] });
const cardSel = '#feed-cols [data-key="a:' + cfg.card + '"]';
out.roads.cardShown = await page.waitForFunction((sel) => !!document.getElementById("f-feed").contentDocument.querySelector(sel), cardSel, { timeout: 10000 }).then(() => true).catch(() => false);
await rightClick("f-feed", cardSel);
await page.waitForTimeout(80);
out.roads.cardMenu = await menuState("f-feed");
await page.keyboard.press("ArrowDown");
out.roads.cardMenuArrow = await menuState("f-feed");
await page.keyboard.press("Escape");
await page.waitForTimeout(80);
out.roads.cardEscape = await menuState("f-feed");
await rightClick("f-feed", cardSel);
await page.waitForTimeout(80);
await page.keyboard.press("ArrowDown"); await page.keyboard.press("ArrowDown");   // Browse files
await page.keyboard.press("Enter");
const browserUp = await page.waitForFunction(() => !!document.getElementById("f-feed").contentDocument.querySelector("#romp-filebrowse #fb-list .fb-row[data-act]"), null, { timeout: 10000 }).then(() => true).catch(() => false);
out.roads.browserOpened = { up: browserUp, menu: (await menuState("f-feed")).open,
  rows: await page.evaluate(() => Array.from(document.getElementById("f-feed").contentDocument.querySelectorAll("#fb-list .fb-row[data-act]")).map((r) => [r.dataset.act, (r.querySelector(".fb-name") || r).textContent.trim()])) };
// 3. the file browser's row menu, over the feed
await rightClick("f-feed", '#fb-list .fb-row[data-act="file"]');
await page.waitForTimeout(80);
out.roads.rowMenu = await menuState("f-feed", "#fb-ctx");
await page.keyboard.press("ArrowDown");
out.roads.rowMenuArrow = await menuState("f-feed", "#fb-ctx");
await page.keyboard.press("Escape");
await page.waitForTimeout(80);
out.roads.rowEscape = { menu: (await menuState("f-feed", "#fb-ctx")).open, browserUp: await page.evaluate(() => !!document.getElementById("f-feed").contentDocument.getElementById("romp-filebrowse")) };
await rightClick("f-feed", '#fb-list .fb-row[data-act="dir"]');
await page.waitForTimeout(80);
out.roads.dirMenu = await menuState("f-feed", "#fb-ctx");
await page.keyboard.press("Escape");
await page.waitForTimeout(80);
await page.keyboard.press("Escape");   // no menu now: the browser itself
await page.waitForTimeout(150);
out.roads.browserClosed = !(await page.evaluate(() => !!document.getElementById("f-feed").contentDocument.getElementById("romp-filebrowse")));
await finish();
"""


class SharedMenusServed(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(os.path.join(EXT, "node_modules", "playwright")):
            raise unittest.SkipTest("extension deps absent (npm ci not run here): the served leg needs them")
        cls.lab = tempfile.mkdtemp(prefix="sharedmenus-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            raise unittest.SkipTest("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
        dist = os.path.join(cls.lab, "dist")
        copy_dist(os.path.join(EXT, "dist"), dist)
        state = os.path.join(cls.lab, "xdg", "romp")
        cwd = os.path.join(cls.lab, "proj")
        for d in ("names", "sdk", "goals"):
            os.makedirs(os.path.join(state, d), exist_ok=True)
        os.makedirs(os.path.join(cwd, "notes"), exist_ok=True)
        Path(cwd, "README.md").write_text("# notes-api\n\nthe search module's notes\n")
        Path(cwd, "notes", "index.md").write_text("the remote index\n")
        with open(os.path.join(state, "session-hosts"), "w") as fh:   # a lab root of its own pins the hosts OFF (CLAUDE.md 2026-09-11)
            fh.write("off\n")
        claude = os.path.join(cls.lab, "claude")
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        for sid, name, tag in [(SID_WEB, "web", 1), (SID_API, "api", 2), (SID_TESTS, "tests", 3)]:
            Path(state, "names", sid).write_text("%s\t%s\t\t\n" % (name, cwd))
            Path(state, "sdk", sid + ".json").write_text(json.dumps(
                {"sid": sid, "name": name, "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": sid, "alive": True}))
            Path(proj, sid + ".jsonl").write_text(_transcript(sid, tag, cwd, 6))
        Path(state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 100}, "seven_day": {"pct": 10}}))   # park sends
        cls.port = _free_port()
        cls.token = "testtok-sharedmenus"
        env = _lab.kernel_env(cls.lab, claude, dist, cls.port, cls.token)
        cls.klog = os.path.join(cls.lab, "kernel.log")
        cls.kernel = subprocess.Popen([os.path.join(BIN, "romp-kernel")], stdout=open(cls.klog, "w"), stderr=subprocess.STDOUT, env=env)
        import urllib.request
        for _ in range(120):
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/healthz" % cls.port, timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        else:
            cls.kernel.kill()
            raise unittest.SkipTest("hermetic kernel never served /healthz here")
        cls.result, cls.driver_error = None, None
        cls._drive()

    @classmethod
    def _drive(cls):
        cfg = os.path.join(cls.lab, "cfg.json")
        res = os.path.join(cls.lab, "result.json")
        with open(cfg, "w") as f:
            json.dump({"url": "http://127.0.0.1:%d/?token=%s" % (cls.port, cls.token), "out": res,
                       "web": SID_WEB, "api": SID_API, "tests": SID_TESTS, "card": CARD}, f)
        driver = os.path.join(cls.lab, "driver.mjs")
        with open(driver, "w") as f:
            f.write(DRIVER)
        try:
            p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=300,
                               env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
        except subprocess.TimeoutExpired as e:
            so = e.stdout if isinstance(e.stdout, str) else (e.stdout or b"").decode()
            cls.driver_error = "driver timed out; partial output:\n%s" % so
            return
        if p.returncode == 3:
            raise unittest.SkipTest("no playwright browser on this box: the served leg needs one (CI installs none)")
        if p.returncode != 0 or not os.path.exists(res):
            cls.driver_error = "driver failed:\n" + p.stdout[-3000:] + p.stderr[-3000:]
            return
        with open(res) as f:
            r = json.load(f)
        keep = os.environ.get("ROMP_SHAREDMENUS_RESULT")
        if keep:
            shutil.copy(res, keep)
        if "died" in r:
            cls.driver_error = "driver aborted early: %s\n%s" % (r["died"], json.dumps(r, indent=1)[-3000:])
            return
        cls.result = r

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "kernel", None):
            cls.kernel.kill()
            cls.kernel.wait()
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

    def setUp(self):
        if self.driver_error:
            self.fail(self.driver_error)

    def test_0_the_pages_threw_nothing(self):
        self.assertEqual(self.result.get("errors"), [], "the pages threw nothing: %r" % self.result.get("errors"))

    def test_1_the_chat_tab_menu_opens_through_the_builder(self):
        r = self.result["roads"]
        self.assertEqual(r["composerFocused"], "composer-input", "the composer held the focus first")
        m = r["tabMenu"]
        self.assertTrue(m["open"], "the tab menu opened: %r" % m)
        self.assertEqual((m["role"], set(m["roles"]), m["reach"], m["focus"]), ("menu", {"menuitem"}, True, "menu"),
                         "the card in the menu role holding the focus, every row a reachable menu item: %r" % m)
        self.assertEqual((m["rows"][0], m["rows"][-1]), ("Rename", "Browse files"), "Rename first, Browse files last: %r" % m["rows"])
        self.assertIn("Tags", m["rows"], "the hand-built Tags row sits among the builder's rows: %r" % m["rows"])
        self.assertEqual(r["tabMenuArrow"]["focus"], 0, "ArrowDown moves the focus to the first row: %r" % r["tabMenuArrow"])
        self.assertEqual(r["tabRename"], {"menu": False, "input": {"value": "web", "focused": True}}, "Enter on Rename closes the card and opens the strip's inline rename: %r" % r["tabRename"])
        self.assertTrue(r["tabRenameGone"], "Escape ends the rename")
        self.assertEqual(r["tabEscape"], {"opened": True, "held": "menu", "menu": False, "active": "tab:" + SID_WEB},
                         "the card took the focus from the tab the press focused, and Escape hands it back to that tab: %r" % r["tabEscape"])
        self.assertEqual((r["tabTags"]["open"], r["tabTags"]["flyouts"]), (True, 1), "the Tags row keeps the card open and its flyout opens inside it: %r" % r["tabTags"])
        self.assertFalse(r["tabOutside"]["open"], "a press outside closes the card and its flyout: %r" % r["tabOutside"])

    def test_2_the_feed_card_menu_opens_through_the_builder(self):
        r = self.result["roads"]
        self.assertTrue(r["cardShown"], "the synthetic card rendered")
        m = r["cardMenu"]
        self.assertTrue(m["open"], "the card menu opened: %r" % m)
        self.assertEqual((m["role"], m["rows"], m["roles"], m["icons"][0], m["reach"], m["focus"]),
                         ("menu", ["Notify me", "Browse files"], ["menuitem", "menuitem"], True, True, "menu"),
                         "the card in the menu role: the bell row with its icon, then Browse files, reachable, the card holding the focus: %r" % m)
        self.assertEqual(r["cardMenuArrow"]["focus"], 0, "ArrowDown moves the focus to the bell row: %r" % r["cardMenuArrow"])
        self.assertFalse(r["cardEscape"]["open"], "Escape closes it")
        b = r["browserOpened"]
        self.assertEqual((b["up"], b["menu"]), (True, False), "ArrowDown twice and Enter pick Browse files: the browser is up, the card gone: %r" % b)
        self.assertIn(["file", "README.md"], b["rows"], "the folder's file listed: %r" % b["rows"])
        self.assertIn(["dir", "notes/"], b["rows"], "the folder's directory listed: %r" % b["rows"])

    def test_3_the_file_browsers_row_menu_opens_through_the_builder(self):
        r = self.result["roads"]
        m = r["rowMenu"]
        self.assertTrue(m["open"], "the row menu opened: %r" % m)
        self.assertEqual((m["id"], m["role"], m["rows"], m["subs"][2], m["reach"], m["focus"]),
                         ("fb-ctx", "menu", ["Copy path", "Download", "Open folder window"], "on the machine the session runs on", True, "menu"),
                         "#fb-ctx in the menu role with the three rows and the sub-line, reachable, holding the focus: %r" % m)
        self.assertEqual(r["rowMenuArrow"]["focus"], 0, "ArrowDown moves the focus to Copy path: %r" % r["rowMenuArrow"])
        self.assertEqual(r["rowEscape"], {"menu": False, "browserUp": True}, "Escape closes the menu and leaves the browser up: %r" % r["rowEscape"])
        self.assertEqual(r["dirMenu"]["rows"], ["Copy path", "Open folder window"], "a directory's row offers no Download: %r" % r["dirMenu"])
        self.assertTrue(r["browserClosed"], "the second Escape closes the browser")


if __name__ == "__main__":
    unittest.main()
