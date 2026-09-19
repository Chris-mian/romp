"""The board view switch on the served feed page (plans/card-boards.md, phase four, section 8): a hermetic kernel over one
synthetic session in the notes-api demo world, the real /feed page served from a copy of the built bundle, driven by
Playwright. Roads: a card posted with a board the kernel has never seen (`romp card -b notes -c new`, here the /notice body)
makes the board exist on the next frame with the defaults; `romp board define notes` (here POST /board) gives it the shape
the notice plan names; the View menu grows a Board row for it; the switch shows the card under its own category and hides
the feed's cards; the pick survives a reload; a page opened with ?board=notes shows the board with the Board rows hidden;
a define dropping a category that still holds a card is refused naming it. Synthetic only (placeholder ids, invented text)."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from tests.dist_copy import copy_dist  # noqa: E402

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
EXT = os.path.join(ROOT, "vscode-extension")
sys.path.insert(0, HERE)
import test_ship_reship_served as _lab  # noqa: E402  the lab kernel's environment
from test_live_paused_window_browser import _free_port  # noqa: E402

SID = "11111111-2222-3333-4444-555555555555"
NOTES = {"id": "notes", "title": "Notes",
         "categories": [{"id": "new", "title": "New", "chip": "neutral"}, {"id": "kept", "title": "Kept", "chip": "working"}, {"id": "done", "title": "Done", "chip": "completed"}],
         "defaultCategory": "new", "rules": [{"when": {"needsYou": True}, "category": "new"}], "sort": {"key": "t", "dir": "desc"}, "subSorts": [],
         "groupBy": None, "order": [], "notify": ["new"], "needsYou": "new", "kinds": ["notice"]}

DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));
let browser;
try { browser = await chromium.launch(cfg.launch || {}); }
catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
const ctx = await browser.newContext({ viewport: { width: 1200, height: 800 } });
const page = await ctx.newPage();
const errors = []; page.on("pageerror", (e) => errors.push(String(e).slice(0, 300)));
await page.addInitScript(() => {
  window.__boards = [];
  const record = (m) => { if (m && m.type === "feed") window.__boards.push(m.boards ? Object.keys(m.boards) : null); };
  let fed = null;
  Object.defineProperty(window, "__rompFed", { configurable: true, get() { return fed; },
    set(v) { fed = v; if (v && typeof v.inbound === "function" && !v.__labWrapped) { const inb = v.inbound; v.__labWrapped = true; v.inbound = (h, m) => { record(m); return inb(h, m); }; } } });
  window.addEventListener("message", (e) => { if (!fed) record(e.data); });
});
const hdr = { "X-Romp-Token": cfg.token };
const post = async (body) => (await (await page.request.post(cfg.notice, { data: body, headers: hdr })).json());
const board = async (body) => (await (await page.request.post(cfg.board, { data: body, headers: hdr })).json());
const sel = (id) => '[data-key="a:' + id + '"]';
const facts = () => page.evaluate(() => {
  const cols = document.getElementById("feed-cols");
  const q = (s) => Array.from(document.querySelectorAll(s));
  return { board: cols ? cols.dataset.board : null, lists: q("#feed-cols .feed-col-list").map((l) => l.id),
           heads: q("#feed-cols .feed-col-name").map((h) => h.textContent), cards: q("#feed-cols [data-key^='a:']").map((c) => [c.dataset.key, c.parentElement.id]),
           title: (document.getElementById("feed-viewbtn") || {}).title || "" };
});
const menu = async () => {
  await page.click("#feed-viewbtn");
  await page.waitForSelector(".feed-viewmenu .ctx-item", { timeout: 10000 });
  return page.evaluate(() => Array.from(document.querySelectorAll(".feed-viewmenu .ctx-item")).map((r) => ({ text: r.textContent, role: r.getAttribute("role"), checked: r.getAttribute("aria-checked"), board: r.dataset.board || null })));
};
await page.goto(cfg.feed);
await page.waitForFunction(() => (window.__boards || []).length >= 1, null, { timeout: 60000 });
// (1) a card onto a board the kernel has never seen: created on first use with the defaults, on the next frame
const r1 = await post({ id: cfg.sid, key: "standup", title: "Remember the standup moved", body: "to half past ten", producer: "cli", board: "notes", category: "new" });
const id1 = "notice:" + cfg.sid + ":standup:" + (r1.notice || {}).rev;
await page.waitForSelector(sel(id1), { state: "attached", timeout: 60000 }).catch(() => {});
await page.waitForFunction(() => (window.__boards || []).some((b) => b && b.includes("notes")), null, { timeout: 30000 }).catch(() => {});
const firstUse = { post: r1, facts: await facts(), framesWithNotes: (await page.evaluate(() => (window.__boards || []).filter((b) => b && b.includes("notes")).length)) };
// (2) the definition the notice plan names, through the door; the frame carries it; the View menu grows the Board rows
const defined = await board(cfg.notes);
await page.waitForTimeout(1500);
const rows = await menu();
const beforePick = await facts();
// (3) the switch: the notes board's columns, the card under new, the feed's cards off the board
await page.locator(".feed-viewmenu .ctx-item[data-board='notes']").click();
await page.waitForSelector(".feed-viewmenu", { state: "detached", timeout: 10000 });
await page.waitForFunction(() => { const c = document.getElementById("feed-cols"); return !!c && c.dataset.board === "notes"; }, null, { timeout: 10000 });
const onNotes = await facts();
const viewState = await page.evaluate(() => JSON.parse(localStorage.getItem("romp:feedview") || "{}").board || "");
// (3b) fold the board's first column (the caret is stacked-only in CSS: click it through the DOM); the fold is keyed notes:new
await page.evaluate(() => { const f = document.querySelector("#feed-cols .feed-col.col-new .fcol-fold"); if (f) f.click(); });
await page.waitForTimeout(300);
const folded = await page.evaluate(() => ({ collapsed: !!document.querySelector("#feed-cols .feed-col.col-new.col-collapsed"),
  cols: (JSON.parse(localStorage.getItem("romp:feedview") || "{}").cols || []), chipTitle: (document.querySelector("#feed-cols .feed-col.col-new .feed-col-name") || {}).getAttribute ? document.querySelector("#feed-cols .feed-col.col-new .feed-col-name").getAttribute("title") : null,
  chipStatic: !!document.querySelector("#feed-cols .feed-col.col-new .feed-col-name.fcol-static") }));
// (4) the pick survives a reload
await page.reload();
await page.waitForFunction(() => { const c = document.getElementById("feed-cols"); return !!c && c.dataset.board === "notes" && document.querySelector("#col-new-list [data-key]"); }, null, { timeout: 60000 }).catch(() => {});
const afterReload = await facts();
const foldAfterReload = await page.evaluate(() => !!document.querySelector("#feed-cols .feed-col.col-new.col-collapsed"));
await page.evaluate(() => { const f = document.querySelector("#feed-cols .feed-col.col-new .fcol-fold"); if (f) f.click(); });   // unfold for the roads below
// (5) back to the feed through the menu: the feed's three columns
const rows2 = await menu();
await page.locator(".feed-viewmenu .ctx-item[data-board='feed']").click();
await page.waitForFunction(() => { const c = document.getElementById("feed-cols"); return !!c && c.dataset.board === "feed"; }, null, { timeout: 10000 });
const backOnFeed = await facts();
// (6) ?board=notes: the board at load, the Board rows hidden
const page2 = await ctx.newPage();
await page2.goto(cfg.feed + "&board=notes");
await page2.waitForFunction(() => { const c = document.getElementById("feed-cols"); return !!c && c.dataset.board === "notes" && document.querySelector("#col-new-list [data-key]"); }, null, { timeout: 60000 }).catch(() => {});
const byQuery = await page2.evaluate(() => { const cols = document.getElementById("feed-cols"); return { board: cols ? cols.dataset.board : null, lists: Array.from(document.querySelectorAll("#feed-cols .feed-col-list")).map((l) => l.id) }; });
await page2.click("#feed-viewbtn");
await page2.waitForSelector(".feed-viewmenu .ctx-item", { timeout: 10000 });
const queryRows = await page2.evaluate(() => Array.from(document.querySelectorAll(".feed-viewmenu .ctx-item")).map((r) => r.getAttribute("role")));
// (7) a define dropping the category that holds the card is refused naming it
const dropped = await board({ ...JSON.parse(JSON.stringify(cfg.notes)), categories: cfg.notes.categories.filter((c) => c.id !== "new"), defaultCategory: "kept", rules: [], notify: [], needsYou: null });
process.stdout.write("RESULT:" + JSON.stringify({ firstUse, defined, rows, beforePick, onNotes, viewState, folded, afterReload, foldAfterReload, rows2, backOnFeed, byQuery, queryRows, dropped, errors }) + "\n");
await browser.close();
"""


class BoardViewServed(unittest.TestCase):
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
        cls.lab = tempfile.mkdtemp(prefix="board-view-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            cls._skip("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
        dist = os.path.join(cls.lab, "dist")
        copy_dist(os.path.join(EXT, "dist"), dist)
        cls.state = os.path.join(cls.lab, "xdg", "romp")
        cwd = os.path.join(cls.lab, "notes-api")
        for d in ("names", "sdk", "states"):
            os.makedirs(os.path.join(cls.state, d), exist_ok=True)
        os.makedirs(cwd, exist_ok=True)
        Path(cls.state, "session-hosts").write_text("off\n")
        claude = os.path.join(cls.lab, "claude")
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        Path(cls.state, "names", SID).write_text("web\t%s\t#1EA1EB\t#ffffff\n" % cwd)
        Path(cls.state, "sdk", SID + ".json").write_text(json.dumps(
            {"sid": SID, "name": "web", "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": SID, "alive": False,
             "model": "claude-fable-5-1", "liveModel": "Fable 5.1"}))
        t0 = int(time.time()) - 3600
        iso = lambda t: time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t))
        recs = [{"type": "user", "uuid": "u1", "parentUuid": None, "timestamp": iso(t0), "sessionId": SID,
                 "message": {"role": "user", "content": "a question about the notes api"}},
                {"type": "assistant", "uuid": "a1", "parentUuid": "u1", "timestamp": iso(t0 + 2), "sessionId": SID,
                 "message": {"role": "assistant", "model": "claude-fable-5-1", "stop_reason": "end_turn",
                             "content": [{"type": "text", "text": "the notes api keeps its shape."}]}}]
        Path(proj, SID + ".jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
        cls.port = _free_port()
        cls.token = "testtok-boards"
        env = _lab.kernel_env(cls.lab, claude, dist, cls.port, cls.token)
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
            cfg = os.path.join(self.lab, "boards.json")
            base = "http://127.0.0.1:%d" % self.port
            with open(cfg, "w") as f:
                json.dump({"feed": base + "/feed?token=" + self.token, "notice": base + "/notice", "board": base + "/board", "token": self.token, "sid": SID, "notes": NOTES}, f)
            driver = os.path.join(self.lab, "boards.mjs")
            Path(driver).write_text(DRIVER)
            p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=400,
                               env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
            if "browser-launch-failed" in p.stderr:
                self._skip("no playwright browser on this box")
            line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
            if not line:
                type(self)._fail = "the driver produced no RESULT (stderr: %s; kernel: %s)" % (p.stderr[-2000:], open(self.klog).read()[-1500:])
                self.fail(type(self)._fail)
            type(self)._r = json.loads(line[len("RESULT:"):])
        return self._r

    def test_a_card_onto_an_unseen_board_creates_it_with_the_defaults_and_the_frame_carries_it(self):
        r = self._result()
        self.assertEqual(r["errors"], [], "no page error")
        fu = r["firstUse"]
        self.assertTrue(fu["post"].get("ok"), fu["post"])
        self.assertEqual((fu["post"]["notice"]["board"], fu["post"]["notice"]["category"], fu["post"]["notice"].get("created")), ("notes", "new", "board"))
        self.assertGreaterEqual(fu["framesWithNotes"], 1, "the frame carries the new board's definition on the next push")
        self.assertEqual(fu["facts"]["board"], "feed", "the feed still shows until the user picks the board")

    def test_the_view_menu_grows_a_board_row_and_the_switch_shows_the_card_under_its_own_category_with_the_feed_off(self):
        r = self._result()
        self.assertIsNone(r["defined"].get("error"), r["defined"])
        rows = r["rows"]
        self.assertEqual([x["role"] for x in rows[:4]], ["menuitem", "menuitemcheckbox", "menuitemcheckbox", "menuitemcheckbox"], "the four view rows first")
        radios = [x for x in rows if x["role"] == "menuitemradio"]
        self.assertEqual([(x["board"], x["checked"], x["text"]) for x in radios], [("feed", "true", "Board: Feed"), ("notes", "false", "Board: Notes")])
        on = r["onNotes"]
        self.assertEqual(on["board"], "notes")
        self.assertEqual(on["lists"], ["col-new-list", "col-kept-list", "col-done-list"], "the board's columns in its order")
        self.assertEqual(on["heads"], ["New", "Kept", "Done"])
        cols = dict(on["cards"])
        self.assertIn("col-new-list", cols.values(), "the card sits under its category: %r" % on["cards"])
        self.assertTrue(all(c.startswith("col-") and c in ("col-new-list", "col-kept-list", "col-done-list") for c in cols.values()), "no feed card on the board: %r" % on["cards"])
        self.assertEqual(r["viewState"], "notes", "the pick is the feed's own view state")
        self.assertIn("showing the Notes board", on["title"])

    def test_the_pick_survives_a_reload_and_the_feed_comes_back_through_the_menu(self):
        r = self._result()
        self.assertEqual(r["afterReload"]["board"], "notes", "the pick survives a reload: %r" % r["afterReload"])
        self.assertEqual(r["afterReload"]["lists"], ["col-new-list", "col-kept-list", "col-done-list"])
        radios = [x for x in r["rows2"] if x["role"] == "menuitemradio"]
        self.assertEqual([(x["board"], x["checked"]) for x in radios], [("feed", "false"), ("notes", "true")])
        back = r["backOnFeed"]
        self.assertEqual(back["board"], "feed"); self.assertEqual(back["lists"], ["col-asks-list", "col-needsInput-list", "col-completed-list"])
        self.assertNotIn("board", back["title"])

    def test_a_fold_on_the_boards_column_is_keyed_per_board_and_survives_a_reload_and_its_chips_have_no_drag_affordance(self):
        # the 1886 read, medium 2 (a data board's fold was dropped by the view state's feed-only gate on a reload) and medium 3 (a
        # data board's chip promised a drag that stored nothing)
        r = self._result()
        f = r["folded"]
        self.assertTrue(f["collapsed"], "the column folds: %r" % f)
        self.assertIn("notes:new", f["cols"], "the fold is the board's own key in the view state: %r" % f["cols"])
        self.assertIsNone(f["chipTitle"], "no drag title on a data board's chip"); self.assertTrue(f["chipStatic"], "the chip is static")
        self.assertTrue(r["foldAfterReload"], "the fold survives a reload")

    def test_a_board_query_selects_the_board_at_load_with_the_board_rows_hidden(self):
        r = self._result()
        self.assertEqual(r["byQuery"]["board"], "notes", r["byQuery"])
        self.assertEqual(r["byQuery"]["lists"], ["col-new-list", "col-kept-list", "col-done-list"])
        self.assertNotIn("menuitemradio", r["queryRows"], "the page's pick is the page's: no Board rows")

    def test_a_define_dropping_a_category_that_holds_a_card_is_refused_naming_it(self):
        r = self._result()
        self.assertFalse(r["dropped"].get("ok"), r["dropped"])
        self.assertRegex(r["dropped"].get("error") or "", r"drops category 'new', which still holds 1 standing card")


if __name__ == "__main__":
    unittest.main()
