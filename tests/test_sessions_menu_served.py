"""The Sessions pane's row menu (the user 2026-09-16): right-click a session's name in the Sessions panel to Rename or Delete it,
on the tab strip's own roads (plans/sessions-pane-session-menu.md).

The served dashboard page (the shell with its chat and Sessions panes) over a hermetic kernel with synthetic sessions (the
notes-api world: web, api, tests, registered SDK records with closed transcripts, so nothing is ever spawned) and a goal store
for api with one open top, so its row carries a tree. Roads, one browser run:
  1. a right-click on api's head opens the menu: two rows, Rename and Delete (danger), on the token card, in both themes;
  2. Rename: the inline input replaces the name; a new name and Enter post renameSession once, and the name propagates on the
     kernel's push to the row and to the chat strip's tab; a second edit ended by Escape posts nothing; a name the kernel
     refuses (a space in it) keeps the old name and brings the kernel's warning frame;
  3. Delete on the running session: the confirm carries the strip's title and names the open goal; Cancel posts nothing and
     the row stays; End session posts endSession then closeTab, the row leaves the pane and the tab leaves the strip;
  4. keyboard: Shift+F10 on the focused head opens the menu with its first row focused; ArrowDown and Enter pick Delete; Escape
     closes the confirm with nothing posted.
Red first per road at the merge base (no menu opens there). Skips loudly without the extension deps or a browser.
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
import test_ship_reship_served as _lab   # noqa: E402  the lab kernel's environment

SID_WEB = "aaaaaaaa-5000-2222-3333-777777777777"
SID_API = "aaaaaaaa-5000-2222-3333-888888888888"
SID_TESTS = "aaaaaaaa-5000-2222-3333-999999999999"
OPEN_TOP = "index the notes"


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _transcript(sid, tag, cwd, pairs):
    out, parent, t = [], None, 1_700_000_000
    for i in range(pairs):
        u = "11111111-2222-4333-8444-%02x00005a%04x" % (tag, i)
        a = "11111111-2222-4333-8444-%02x00005b%04x" % (tag, i)
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
// every frame: what the pane posts to its host, and the frames the socket brings it (the kernel's warning)
await page.addInitScript(() => {
  window.__posted = []; window.__frames = [];
  let real;
  Object.defineProperty(window, "acquireVsCodeApi", { configurable: true,
    get() { return function () { const api = real ? real() : {}; const post = api.postMessage ? api.postMessage.bind(api) : () => {};
      api.postMessage = (m) => { window.__posted.push(m); return post(m); }; return api; }; },
    set(fn) { real = fn; } });
  const wrapIn = (fn) => function (ev) { try { const m = JSON.parse(ev.data); if (m && m.type === "warn") window.__frames.push(m); } catch (e) {} return fn.call(this, ev); };
  const AEL = WebSocket.prototype.addEventListener;
  WebSocket.prototype.addEventListener = function (type, fn, opts) { return AEL.call(this, type, type === "message" && typeof fn === "function" ? wrapIn(fn) : fn, opts); };
  const desc = Object.getOwnPropertyDescriptor(WebSocket.prototype, "onmessage");
  Object.defineProperty(WebSocket.prototype, "onmessage", { configurable: true, get() { return desc.get.call(this); }, set(fn) { desc.set.call(this, typeof fn === "function" ? wrapIn(fn) : fn); } });
});
const T = 20000;
const waitFn = async (fn, arg, why) => page.waitForFunction(fn, arg, { timeout: T }).catch(async (e) => { await die(why + " (" + String(e).split("\n")[0] + ")"); });
const paneDoc = () => document.getElementById("f-fleet") && document.getElementById("f-fleet").contentDocument;
const paneFrame = async () => (await page.$("#f-fleet")).contentFrame();
const headSel = (sid) => '.fl-head[data-sid="' + sid + '"]';
const posted = (type) => page.evaluate((type) => (document.getElementById("f-fleet").contentWindow.__posted || []).filter((m) => m && m.type === type), type);
const clearPosted = () => page.evaluate(() => { const w = document.getElementById("f-fleet").contentWindow; w.__posted.length = 0; w.__frames.length = 0; });
const warns = () => page.evaluate(() => (document.getElementById("f-fleet").contentWindow.__frames || []).map((m) => m.text || ""));
const menuState = () => page.evaluate(() => {
  const d = document.getElementById("f-fleet").contentDocument;
  const m = d.querySelector(".ctx-menu.fl-sess-menu");
  if (!m) return { open: false };
  const probe = d.createElement("div"); probe.style.cssText = "position:fixed;left:-9999px;background:var(--menu-bg)"; d.body.appendChild(probe);
  const want = getComputedStyle(probe).backgroundColor; probe.remove();
  const rows = Array.from(m.querySelectorAll(".ctx-item"));
  return { open: true, rows: rows.map((r) => r.querySelector(".ctx-item-label").textContent), danger: rows.map((r) => r.classList.contains("ctx-item-danger")),
           bg: getComputedStyle(m).backgroundColor, want, role: m.getAttribute("role"), focusedRow: rows.indexOf(d.activeElement), light: d.body.classList.contains("theme-light") };
});
const confirmState = () => page.evaluate(() => {
  const d = document.getElementById("f-fleet").contentDocument;
  const c = d.getElementById("confirm");
  if (!c) return { open: false };
  return { open: true, title: c.querySelector(".confirm-title").textContent, detail: c.querySelector(".confirm-detail").textContent,
           buttons: Array.from(c.querySelectorAll(".confirm-btn")).map((b) => [b.textContent, b.classList.contains("danger")]) };
});
const rowName = (sid) => page.evaluate((sel) => { const d = document.getElementById("f-fleet").contentDocument; const n = d.querySelector(sel + " .fl-name"); return n ? n.textContent : null; }, headSel(sid));
const tabLabel = (sid) => page.evaluate((sid) => { const d = document.getElementById("f-chat").contentDocument; const t = d.querySelector('#tabs .tab[data-id="' + sid + '"] .tab-label'); return t ? t.textContent : null; }, sid);
const rightClick = async (sid) => { const fr = await paneFrame(); await fr.locator(headSel(sid) + " .fl-name").first().click({ button: "right" }); await page.waitForTimeout(80); };
// a row or a button that never appears (the merge base has no menu) is recorded as such, so each road reads red on its own
// claim there instead of the driver dying on the first missing row
const pickRow = async (label) => { const fr = await paneFrame(); const ok = await fr.locator(".ctx-menu.fl-sess-menu .ctx-item", { hasText: label }).first().click({ timeout: 2500 }).then(() => true).catch(() => false); await page.waitForTimeout(80); return ok; };
const pressButton = async (label) => { const fr = await paneFrame(); const ok = await fr.locator("#confirm .confirm-btn", { hasText: label }).first().click({ timeout: 2500 }).then(() => true).catch(() => false); await page.waitForTimeout(80); return ok; };
const setLight = (on) => page.evaluate((on) => { const d = document.getElementById("f-fleet").contentDocument; d.body.classList.toggle("theme-light", on); }, on);

// ---- load: the chat's tabs, the Sessions pane switched on, api's row with its tree ----
await page.goto(cfg.url);
await waitFn((sids) => { const d = document.getElementById("f-chat") && document.getElementById("f-chat").contentDocument; if (!d) return false; const ids = Array.from(d.querySelectorAll("#tabs .tab[data-id]")).map((t) => t.dataset.id); return sids.every((s) => ids.includes(s)); }, [cfg.web, cfg.api, cfg.tests], "the chat never showed the tabs");
await page.evaluate(() => { if (window.__rompPaneToggle) window.__rompPaneToggle("fleet", true); });
await waitFn(() => { const d = document.getElementById("f-fleet") && document.getElementById("f-fleet").contentDocument; return !!(d && d.getElementById("fleet-list")); }, null, "the Sessions pane never loaded");
await waitFn((sel) => { const d = document.getElementById("f-fleet").contentDocument; return !!d.querySelector(sel); }, headSel(cfg.api), "api's row never appeared");
out.rows = await page.evaluate(() => Array.from(document.getElementById("f-fleet").contentDocument.querySelectorAll(".fl-head[data-sid]")).map((h) => [h.dataset.sid, h.querySelector(".fl-name").textContent, h.tabIndex, h.getAttribute("role")]));
out.apiTree = await page.evaluate((sel) => { const d = document.getElementById("f-fleet").contentDocument; const sec = d.querySelector(sel).closest(".fl-session"); return Array.from(sec.querySelectorAll(".ledger-ttext")).map((t) => t.textContent); }, headSel(cfg.api));
// 1. the menu, both themes
await rightClick(cfg.api);
out.roads.menuDark = await menuState();
await page.keyboard.press("Escape"); await page.waitForTimeout(60);
out.roads.menuClosedByEscape = await menuState();
await setLight(true);
await rightClick(cfg.api);
out.roads.menuLight = await menuState();
await page.mouse.click(5, 5); await page.waitForTimeout(60);   // a press outside the card
out.roads.menuClosedByPress = await menuState();
await setLight(false);
// 2. Rename
await clearPosted();
await rightClick(cfg.api);
const renameOpened = await pickRow("Rename");
out.roads.renameInput = await page.evaluate((sel) => { const d = document.getElementById("f-fleet").contentDocument; const i = d.querySelector(sel + " .fl-rename"); return i ? { value: i.value, focused: d.activeElement === i, selected: i.selectionEnd - i.selectionStart } : null; }, headSel(cfg.api));
if (renameOpened) { await page.keyboard.type("api-search"); await page.keyboard.press("Enter"); }
await page.waitForTimeout(80);
out.roads.renamePosted = await posted("renameSession");
const propagated = await page.waitForFunction((sid) => {
  const pd = document.getElementById("f-fleet").contentDocument, cd = document.getElementById("f-chat").contentDocument;
  const n = pd.querySelector('.fl-head[data-sid="' + sid + '"] .fl-name'), t = cd.querySelector('#tabs .tab[data-id="' + sid + '"] .tab-label');
  return !!n && !!t && n.textContent === "api-search" && t.textContent === "api-search";
}, cfg.api, { timeout: 8000 }).then(() => true).catch(() => false);
out.roads.renamePropagated = { ok: propagated, row: await rowName(cfg.api), tab: await tabLabel(cfg.api) };
// …Escape leaves the name and posts nothing
await clearPosted();
await rightClick(cfg.api);
if (await pickRow("Rename")) { await page.keyboard.type("nope"); await page.keyboard.press("Escape"); }
await page.waitForTimeout(300);
out.roads.renameEscape = { posted: await posted("renameSession"), row: await rowName(cfg.api), inputLeft: await page.evaluate(() => !!document.getElementById("f-fleet").contentDocument.querySelector(".fl-rename")) };
// …a name the kernel refuses keeps the old one and the warning arrives
await clearPosted();
await rightClick(cfg.api);
if (await pickRow("Rename")) { await page.keyboard.type("bad name"); await page.keyboard.press("Enter"); }
await page.waitForFunction(() => (document.getElementById("f-fleet").contentWindow.__frames || []).length > 0, null, { timeout: 5000 }).catch(() => null);
await page.waitForTimeout(300);
out.roads.renameRefused = { posted: await posted("renameSession"), warns: await warns(), row: await rowName(cfg.api), tab: await tabLabel(cfg.api) };
// 3. Delete on the running session
await clearPosted();
await rightClick(cfg.api);
await pickRow("Delete");
out.roads.confirm = await confirmState();
await pressButton("Cancel");
await page.waitForTimeout(200);
out.roads.cancelled = { confirm: await confirmState(), posted: (await posted("endSession")).length + (await posted("closeTab")).length, row: await rowName(cfg.api) };
await rightClick(cfg.api);
await pickRow("Delete");
await pressButton("End session");
out.roads.endPosted = await page.evaluate(() => (document.getElementById("f-fleet").contentWindow.__posted || []).filter((m) => m && (m.type === "endSession" || m.type === "closeTab")).map((m) => [m.type, m.id]));
const gone = await page.waitForFunction((sid) => {
  const pd = document.getElementById("f-fleet").contentDocument, cd = document.getElementById("f-chat").contentDocument;
  return !pd.querySelector('.fl-head[data-sid="' + sid + '"]') && !cd.querySelector('#tabs .tab[data-id="' + sid + '"]');
}, cfg.api, { timeout: 10000 }).then(() => true).catch(() => false);
out.roads.ended = { gone, rows: await page.evaluate(() => Array.from(document.getElementById("f-fleet").contentDocument.querySelectorAll(".fl-head[data-sid]")).map((h) => h.dataset.sid)),
                    tabs: await page.evaluate(() => Array.from(document.getElementById("f-chat").contentDocument.querySelectorAll("#tabs .tab[data-id]")).map((t) => t.dataset.id)) };
// 4. keyboard, on web's row
await clearPosted();
await page.evaluate((sel) => { const d = document.getElementById("f-fleet").contentDocument; d.querySelector(sel).focus(); }, headSel(cfg.web));
const fr = await paneFrame();
await fr.locator(headSel(cfg.web)).press("Shift+F10");
await page.waitForTimeout(80);
out.roads.kbMenu = await menuState();
await page.keyboard.press("ArrowDown");
out.roads.kbMoved = await menuState();
if (out.roads.kbMoved.open) await page.keyboard.press("Enter");   // with no menu, Enter would open the session instead
await page.waitForTimeout(80);
out.roads.kbConfirm = await confirmState();
await page.keyboard.press("Escape");
await page.waitForTimeout(200);
out.roads.kbEscaped = { confirm: await confirmState(), posted: (await posted("endSession")).length, row: await rowName(cfg.web) };
await finish();
"""


class SessionsMenuServed(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(os.path.join(EXT, "node_modules", "playwright")):
            raise unittest.SkipTest("extension deps absent (npm ci not run here): the served leg needs them")
        cls.lab = tempfile.mkdtemp(prefix="sessmenu-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            raise unittest.SkipTest("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
        dist = os.path.join(cls.lab, "dist")
        copy_dist(os.path.join(EXT, "dist"), dist)
        state = os.path.join(cls.lab, "xdg", "romp")
        cwd = os.path.join(cls.lab, "proj")
        for d in ("names", "sdk", "goals"):
            os.makedirs(os.path.join(state, d), exist_ok=True)
        os.makedirs(cwd, exist_ok=True)
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
        # api's goal store: one open top, so its row carries a tree and the End confirm has a goal to name
        Path(state, "goals", SID_API + ".json").write_text(json.dumps(
            {"rompUuid": SID_API, "seq": 1, "placementsV": 1, "status": {}, "lastNode": "g1",
             "nodes": {"g1": {"text": OPEN_TOP, "t": 1781100000, "mt": 1781100000, "parentId": None}}}))
        Path(state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 100}, "seven_day": {"pct": 10}}))   # park sends
        cls.port = _free_port()
        cls.token = "testtok-sessmenu"
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
                       "web": SID_WEB, "api": SID_API, "tests": SID_TESTS}, f)
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
        keep = os.environ.get("ROMP_SESSMENU_RESULT")
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

    def test_0_the_page_threw_nothing_and_the_rows_are_focusable(self):
        r = self.result
        self.assertEqual(r.get("errors"), [], "the pages threw nothing: %r" % r.get("errors"))
        rows = {row[0]: row for row in r["rows"]}
        self.assertIn(SID_API, rows, "api's row is there: %r" % r["rows"])
        self.assertEqual((rows[SID_API][1], rows[SID_API][2], rows[SID_API][3]), ("api", 0, "button"), "the head is focusable with a button role: %r" % rows[SID_API])
        self.assertIn(OPEN_TOP, r["apiTree"], "api's tree shows the open top from its goal store: %r" % r["apiTree"])

    def test_1_a_right_click_on_the_row_opens_the_menu_on_the_token_card_in_both_themes(self):
        r = self.result["roads"]
        for key in ("menuDark", "menuLight"):
            m = r[key]
            self.assertTrue(m["open"], "%s: the menu opened: %r" % (key, m))
            self.assertEqual((m["rows"], m["danger"], m["role"]), (["Rename", "Delete"], [False, True], "menu"), "%s: two rows, Delete marked danger: %r" % (key, m))
            self.assertEqual(m["bg"], m["want"], "%s: the card's background is the theme's menu token: %r" % (key, m))
            self.assertNotIn(m["bg"], ("rgba(0, 0, 0, 0)", "transparent"), "%s: a painted card" % key)
        self.assertNotEqual(r["menuDark"]["bg"], r["menuLight"]["bg"], "the two themes resolve the token differently")
        self.assertFalse(r["menuClosedByEscape"]["open"], "Escape closes it")
        self.assertFalse(r["menuClosedByPress"]["open"], "a press outside closes it")

    def test_2_rename_edits_in_place_posts_the_strips_message_and_the_name_propagates(self):
        r = self.result["roads"]
        self.assertEqual(r["renameInput"], {"value": "api", "focused": True, "selected": 3}, "the inline input holds the name, focused and selected: %r" % r["renameInput"])
        self.assertEqual([(m["type"], m["id"], m["name"]) for m in r["renamePosted"]], [("renameSession", SID_API, "api-search")], "one renameSession post with the new name")
        self.assertEqual(r["renamePropagated"], {"ok": True, "row": "api-search", "tab": "api-search"}, "the kernel's push renames the row and the chat strip's tab: %r" % r["renamePropagated"])
        self.assertEqual((r["renameEscape"]["posted"], r["renameEscape"]["row"], r["renameEscape"]["inputLeft"]), ([], "api-search", False), "Escape posts nothing and leaves the name: %r" % r["renameEscape"])
        rf = r["renameRefused"]
        self.assertEqual([m["name"] for m in rf["posted"]], ["bad name"], "the refused name was posted once (the kernel decides): %r" % rf["posted"])
        self.assertTrue(rf["warns"] and any("letters, digits" in w for w in rf["warns"]), "the kernel's warning frame arrived: %r" % rf["warns"])
        self.assertEqual((rf["row"], rf["tab"]), ("api-search", "api-search"), "the old name stands everywhere: %r" % rf)

    def test_3_delete_asks_with_the_strips_confirm_naming_the_open_goal_then_ends_the_session_on_the_strips_two_messages(self):
        r = self.result["roads"]
        c = r["confirm"]
        self.assertTrue(c["open"], "the confirm opened: %r" % c)
        self.assertEqual(c["title"], "End “api-search”?", "the strip's title: %r" % c["title"])
        self.assertIn(OPEN_TOP, c["detail"], "the detail names the open goal: %r" % c["detail"])
        self.assertIn("revive", c["detail"], "…and says how the session comes back")
        self.assertEqual(c["buttons"], [["End session", True], ["Cancel", False]], "the strip's buttons, End session marked danger: %r" % c["buttons"])
        self.assertEqual((r["cancelled"]["confirm"]["open"], r["cancelled"]["posted"], r["cancelled"]["row"]), (False, 0, "api-search"), "Cancel closes the box, posts nothing, the row stays: %r" % r["cancelled"])
        self.assertEqual(r["endPosted"], [["endSession", SID_API], ["closeTab", SID_API]], "End session posts the strip's two messages in its order: %r" % r["endPosted"])
        e = r["ended"]
        self.assertTrue(e["gone"], "the row left the pane and the tab left the strip on the kernel's push: %r" % e)
        self.assertNotIn(SID_API, e["rows"]); self.assertNotIn(SID_API, e["tabs"])

    def test_4_the_keyboard_reaches_the_menu_and_the_confirm(self):
        r = self.result["roads"]
        self.assertEqual((r["kbMenu"]["open"], r["kbMenu"]["rows"], r["kbMenu"]["focusedRow"]), (True, ["Rename", "Delete"], 0), "Shift+F10 on the focused head opens the menu with Rename focused: %r" % r["kbMenu"])
        self.assertEqual(r["kbMoved"]["focusedRow"], 1, "ArrowDown moves to Delete: %r" % r["kbMoved"])
        self.assertTrue(r["kbConfirm"]["open"] and r["kbConfirm"]["title"].startswith("End “web”"), "Enter picks Delete and the confirm opens for web: %r" % r["kbConfirm"])
        self.assertEqual((r["kbEscaped"]["confirm"]["open"], r["kbEscaped"]["posted"], r["kbEscaped"]["row"]), (False, 0, "web"), "Escape closes the confirm with nothing posted: %r" % r["kbEscaped"])


if __name__ == "__main__":
    unittest.main()
