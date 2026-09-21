"""The chat page's NEEDS YOU BOX (plans/needs-you.md, phase three): a hermetic kernel over one synthetic live session in the
notes-api demo world, the real /chat page served from a copy of the built bundle, driven by Playwright, the feed pane closed.
The session's goal store holds three judge questions (diary block events in the fold's shape) and a fourth, working focus goal;
the transcript ends on an API error record only the user can clear (isApiErrorMessage, "prompt is too long"), so the fourth
card is a HARD STOP the kernel floors with a live-block object (state apiError) and the tab wears the red Blocked ring; a message
from a DIRECTED peer is held under STATE/postal/quarantine before boot and becomes a needs-you notice card at the first build.
The box lists the three questions (Reply, Continue, Clear) and the held message (Approve, Deny) under a "Needs you · 4" header,
wears the Needs you token on its edge, and lists no row for the hard stop. Clear
takes its row off the box with the next frame; Continue posts the card's own Continue wire and its row leaves once the kernel
files the reply; Reply points the composer at the card (the chip with the card's title) and the row leaves once the typed reply
is filed. The gear's Needs you box switch (a romp:settings save) hides the box and leaves the ring; back on, the box returns.
Synthetic only: placeholder ids, invented text, hostname TESTHOST."""
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

SID = "cccccccc-1111-2222-3333-444444444444"
MID = "aaaaaaaa-bbbb-cccc-dddd-000000000301"
TOKEN_RGB = "rgb(217, 70, 239)"          # --st-needs-bg, the dark theme (styles.css)
QUESTIONS = ["which database does the suite target?", "should the parser keep the legacy header?", "is the fixtures directory versioned?"]

DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));
let browser;
try { browser = await chromium.launch(); }
catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
const page = await browser.newPage({ viewport: { width: 1100, height: 760 } });
const errors = []; page.on("pageerror", (e) => errors.push(String(e).slice(0, 300)));
const out = { errors };
const rowSel = (id) => '#notices .ntc-row[data-item="' + id + '"]';
const readBox = () => page.evaluate(() => {
  const box = document.getElementById("notices"); const cs = box ? getComputedStyle(box) : null;
  const rows = box ? Array.from(box.querySelectorAll(".ntc-row")) : [];
  const tab = document.querySelector('#tabs .tab[data-id]');
  return { shown: !!box && box.style.display !== "none" && !!cs && cs.display !== "none", border: cs ? cs.borderTopColor : null, borderLeft: cs ? cs.borderLeftWidth : null,
           head: box ? ((box.querySelector(".ntc-head .ntc-label") || {}).textContent || null) : null,
           dot: box && box.querySelector(".ntc-head .ntc-dot") ? getComputedStyle(box.querySelector(".ntc-head .ntc-dot")).backgroundColor : null,
           rows: rows.map((r) => ({ id: r.getAttribute("data-item"), title: (r.querySelector(".ntc-title") || {}).textContent, body: (r.querySelector(".ntc-body") || {}).textContent,
                                   buttons: Array.from(r.querySelectorAll(".ntc-actions button")).map((b) => b.textContent), disabled: Array.from(r.querySelectorAll(".ntc-actions button")).map((b) => b.disabled) })),
           tabClasses: tab ? tab.className : null };
});
const waitRows = (n, ms) => page.waitForFunction((n) => document.querySelectorAll("#notices .ntc-row").length === n, n, { timeout: ms }).then(() => true).catch(() => false);
await page.goto(cfg.chat);
await page.waitForSelector("#tabs .tab", { timeout: 30000 }).catch(() => {});
// 1. the box: four rows (the three questions and the held message), the header, the token edge, no row for the hard stop, the red ring on the tab
out.fourRows = await waitRows(4, 60000);
out.first = await readBox();
// the hard stop as the feed pane shows it from the same kernel's pushed frame: the focus goal's card under Needs you with the on-you API error badge
const feed = await browser.newPage({ viewport: { width: 1400, height: 900 } });
await feed.goto(cfg.feed);
const g4Sel = '[data-key="a:' + cfg.g4 + '"]';
out.hardStop = await feed.waitForSelector(g4Sel, { state: "attached", timeout: 60000 }).then(() => feed.evaluate((sel) => { const c = document.querySelector(sel);
  const badge = c ? c.querySelector(".fask-api") : null; const badges = c ? Array.from(c.querySelectorAll("a, span")).map((x) => x.textContent || "").filter((t) => t.startsWith("⚠")) : [];
  return { col: c ? c.parentElement.id : null, badges }; }, g4Sel)).catch(() => ({ col: null, badges: [] }));
await feed.close();
// 2. Clear on the third question: the card's own askClear wire; the row leaves with the next frame
await page.click(rowSel(cfg.g3) + ' [data-act="ntc-clear"]');
out.clearLatched = await page.evaluate((s) => { const r = document.querySelector(s); return r ? Array.from(r.querySelectorAll("button")).every((b) => b.disabled) : null; }, rowSel(cfg.g3));
out.afterClear = { left: await page.waitForFunction((s) => !document.querySelector(s), rowSel(cfg.g3), { timeout: 60000 }).then(() => true).catch(() => false) };
out.afterClear.box = await readBox();
// 3. Continue on the second question: the card's Continue wire (askFollowUp with cont); the kernel files the reply and the card leaves Needs you
await page.click(rowSel(cfg.g2) + ' [data-act="ntc-cont"]');
out.contLatched = await page.evaluate((s) => { const r = document.querySelector(s); return r ? Array.from(r.querySelectorAll("button")).every((b) => b.disabled) : null; }, rowSel(cfg.g2));
out.afterCont = { left: await page.waitForFunction((s) => !document.querySelector(s), rowSel(cfg.g2), { timeout: 60000 }).then(() => true).catch(() => false) };
out.afterCont.box = await readBox();
// 4. Reply on the first question: the composer takes the card (the chip with its title); the typed reply is a follow-up on the card and the row leaves once filed
await page.click(rowSel(cfg.g1) + ' [data-act="ntc-reply"]');
out.chip = await page.waitForFunction(() => { const c = document.querySelector("#composer .composer-chip .composer-chip-label"); return c ? c.textContent : null; }, null, { timeout: 15000 }).then((h) => h.jsonValue()).catch(() => null);
out.rowStaysOnReply = await page.evaluate((s) => !!document.querySelector(s), rowSel(cfg.g1));
await page.fill("#composer-input", cfg.reply);
await page.press("#composer-input", "Enter");
out.afterReply = { left: await page.waitForFunction((s) => !document.querySelector(s), rowSel(cfg.g1), { timeout: 60000 }).then(() => true).catch(() => false) };
out.afterReply.box = await readBox();
// 5. the switch: a romp:settings save with the box off hides it and leaves the ring; back on, the box returns
const setBox = (on) => page.evaluate((on) => { const s = JSON.parse(localStorage.getItem("romp:settings") || "{}"); s.needsBox = on; localStorage.setItem("romp:settings", JSON.stringify(s)); window.dispatchEvent(new Event("romp:settings")); }, on);
await setBox(false);
out.off = { hidden: await page.waitForFunction(() => { const b = document.getElementById("notices"); return !!b && b.style.display === "none"; }, null, { timeout: 10000 }).then(() => true).catch(() => false) };
out.off.box = await readBox();
await setBox(true);
out.on = { shown: await page.waitForFunction(() => { const b = document.getElementById("notices"); return !!b && b.style.display !== "none" && b.querySelectorAll(".ntc-row").length >= 1; }, null, { timeout: 10000 }).then(() => true).catch(() => false) };
out.on.box = await readBox();
process.stdout.write("RESULT:" + JSON.stringify(out) + "\n");
await browser.close();
"""


def _block(t, why):
    return {"ev_t": t, "src": "planner", "kind": "block", "why": why, "at": t}


class NeedsYouBoxChatServed(unittest.TestCase):
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
        cls.lab = tempfile.mkdtemp(prefix="needs-you-box-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            cls._skip("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
        dist = os.path.join(cls.lab, "dist")
        copy_dist(os.path.join(EXT, "dist"), dist)
        state = os.path.join(cls.lab, "xdg", "romp")
        cwd = os.path.join(cls.lab, "notes-api")
        for d in ("names", "sdk", "states", "goals", os.path.join("postal", "quarantine")):
            os.makedirs(os.path.join(state, d), exist_ok=True)
        os.makedirs(cwd, exist_ok=True)
        Path(state, "session-hosts").write_text("off\n")
        claude = os.path.join(cls.lab, "claude")
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        Path(state, "names", SID).write_text("web\t%s\t#9cd2ff\t#0c1a2e\n" % cwd)
        Path(state, "sdk", SID + ".json").write_text(json.dumps(
            {"sid": SID, "name": "web", "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": SID, "alive": True,
             "model": "claude-opus-5", "liveModel": "Opus 5"}))
        t0 = int(time.time()) - 3600
        iso = lambda t: time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t))
        recs, parent = [], None
        for i in range(6):
            u, a = "u%d" % i, "a%d" % i
            recs.append({"type": "user", "uuid": u, "parentUuid": parent, "timestamp": iso(t0 + 10 * i), "sessionId": SID, "promptSource": "typed",
                         "message": {"role": "user", "content": "question %d about the notes api" % i}})
            recs.append({"type": "assistant", "uuid": a, "parentUuid": u, "timestamp": iso(t0 + 10 * i + 4), "sessionId": SID,
                         "message": {"role": "assistant", "model": "claude-opus-5", "stop_reason": "end_turn",
                                     "content": [{"type": "text", "text": "answer %d: the notes api keeps its shape." % i}]}})
            parent = a
        # the session is STOPPED on an API error only the user can clear (the transcript's last record, Claude Code's
        # isApiErrorMessage shape, "prompt is too long"): its focus goal (the store's lastNode) floors as a live block, the hard stop
        recs.append({"type": "user", "uuid": "u6", "parentUuid": parent, "timestamp": iso(t0 + 60), "sessionId": SID, "promptSource": "typed",
                     "message": {"role": "user", "content": "wire the fixtures directory into the integration suite"}})
        recs.append({"type": "assistant", "uuid": "e6", "parentUuid": "u6", "timestamp": iso(t0 + 62), "sessionId": SID, "isApiErrorMessage": True,
                     "apiErrorStatus": 400, "error": "invalid_request",
                     "message": {"role": "assistant", "content": [{"type": "text", "text": "API Error: 400 prompt is too long"}]}})
        Path(proj, SID + ".jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
        Path(state, "states", SID + ".jsonl").write_text(json.dumps({"t": t0 + 70, "state": "idle"}) + "\n")
        # three questions the judges filed (diary events in the fold's shape, so the rollup keeps the flags), and the working focus goal
        cls.g = [SID + ":g%d" % i for i in range(1, 5)]
        nodes, status = {}, {}
        for i, q in enumerate(QUESTIONS):
            g = cls.g[i]
            nodes[g] = {"id": g, "text": q, "parentId": None, "nodeComplete": False, "blocked": True, "blockWhy": q, "cleared": False, "trail": [],
                        "t": t0 + 100 + i, "log": [_block(t0 + 200 + i, "asked: " + q)]}
            status[g] = "blocked"
        g4 = cls.g[3]
        nodes[g4] = {"id": g4, "text": "wire the fixtures directory into the integration suite", "parentId": None, "nodeComplete": False, "blocked": False,
                     "cleared": False, "trail": [], "t": t0 + 300, "log": []}
        status[g4] = "working"
        Path(state, "goals", SID + ".json").write_text(json.dumps(
            {"rompUuid": SID, "seq": 5, "lastNode": g4, "closedTurns": [], "nodes": nodes, "placements": {}, "status": status}))
        # a message from a DIRECTED peer, held for the user's decision: a needs-you notice with Approve and Deny at the first build
        Path(state, "postal", "quarantine", MID + ".json").write_text(json.dumps(
            {"mid": MID, "to": "web", "toId": SID, "frm": "api", "frmId": "11111111-2222-3333-4444-666666666666",
             "body": "the README draft is ready for a look, could you check the parser section before the release?",
             "kind": "coordinate", "origin": "TESTHOST", "via": "peer", "at": int(time.time()) - 600}))
        cls.port = _free_port()
        cls.token = "testtok-needsbox"
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
            cfg = os.path.join(self.lab, "needsbox.json")
            base = "http://127.0.0.1:%d" % self.port
            with open(cfg, "w") as f:
                json.dump({"chat": base + "/chat?token=" + self.token, "feed": base + "/feed?token=" + self.token, "sid": SID, "g1": self.g[0], "g2": self.g[1], "g3": self.g[2], "g4": self.g[3],
                           "reply": "Postgres, the same as production"}, f)
            driver = os.path.join(self.lab, "needsbox.mjs")
            Path(driver).write_text(DRIVER)
            p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=600,
                               env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
            if "browser-launch-failed" in p.stderr:
                self._skip("no playwright browser on this box")
            line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
            if line is None:
                type(self)._fail = "the driver produced no RESULT (stderr: %s; kernel: %s)" % (p.stderr[-2000:], open(self.klog).read()[-1500:])
                self.fail(type(self)._fail)
            type(self)._r = json.loads(line[len("RESULT:"):])
        return self._r

    def _kernel_tail(self):
        try:
            return open(self.klog).read()[-1200:]
        except OSError:
            return ""

    def test_the_box_lists_the_questions_and_the_held_message_under_the_header_in_the_token_and_no_row_for_the_hard_stop(self):
        r = self._result()
        self.assertEqual(r["errors"], [], "no page error")
        self.assertTrue(r["fourRows"], "four rows within a minute: %r (kernel: %s)" % (r["first"], self._kernel_tail()))
        b = r["first"]
        self.assertTrue(b["shown"], "the box shows")
        self.assertEqual(b["head"], "Needs you · 4", "the header: the title with the count")
        self.assertEqual((b["border"], b["borderLeft"], b["dot"]), (TOKEN_RGB, "1px", TOKEN_RGB), "one thin edge and the dot in the Needs you token: %r" % b)
        ids = [x["id"] for x in b["rows"]]
        self.assertEqual(ids[:3], self.g[:3], "the three questions first, in the frame's order: %r" % ids)
        self.assertEqual(ids[3], "notice:%s:%s:1" % (SID, MID), "then the held message")
        self.assertNotIn(self.g[3], ids, "the hard stop (the focus goal under the on-you API error) has no row")
        hard = r["hardStop"]
        self.assertEqual(hard["col"], "col-needsInput-list", "the feed pane files the focus goal's card under Needs you from the same pushed frame: %r" % hard)
        self.assertTrue(any("Prompt too long" in t for t in hard["badges"]), "wearing the on-you API error badge, the hard stop the box leaves out: %r" % hard)
        self.assertTrue(any(x["id"] == self.g[0] for x in b["rows"]), "the questions are on the box while the hard stop is not")
        for row, q in zip(b["rows"][:3], QUESTIONS):
            self.assertEqual(row["title"], q, "the card's text is the row's title")
            self.assertEqual(row["buttons"], ["Reply", "Continue", "Clear"], "a live session's question: Reply, Continue, Clear")
            self.assertEqual(row["disabled"], [False, False, False])
        self.assertEqual(b["rows"][3]["buttons"], ["Approve", "Deny"], "the held message keeps its stored actions")
        self.assertIn("ring-needs-you", b["tabClasses"] or "", "the tab wears the red Blocked ring for the hard stop (it outranks the Needs you ring): %r" % b["tabClasses"])

    def test_clear_takes_its_row_off_the_box_with_the_next_frame(self):
        r = self._result()
        self.assertTrue(r["clearLatched"], "the row's buttons latch on the press")
        self.assertTrue(r["afterClear"]["left"], "the cleared question's row left: %r (kernel: %s)" % (r["afterClear"]["box"], self._kernel_tail()))
        self.assertEqual(r["afterClear"]["box"]["head"], "Needs you · 3")

    def test_continue_posts_the_cards_continue_and_its_row_leaves_once_the_kernel_files_the_reply(self):
        r = self._result()
        self.assertTrue(r["contLatched"], "the row's buttons latch on the press")
        self.assertTrue(r["afterCont"]["left"], "the continued question's row left: %r (kernel: %s)" % (r["afterCont"]["box"], self._kernel_tail()))
        self.assertEqual(r["afterCont"]["box"]["head"], "Needs you · 2")

    def test_reply_points_the_composer_at_the_card_and_the_typed_reply_takes_the_row_off(self):
        r = self._result()
        self.assertEqual(r["chip"], QUESTIONS[0], "the composer's chip names the card, as a feed card click that lands in the chat does")
        self.assertTrue(r["rowStaysOnReply"], "Reply alone leaves the row: the reply is not written yet")
        self.assertTrue(r["afterReply"]["left"], "the typed reply is a follow-up on the card and its row left: %r (kernel: %s)" % (r["afterReply"]["box"], self._kernel_tail()))
        self.assertEqual(r["afterReply"]["box"]["head"], "Needs you · 1", "the held message alone remains")

    def test_the_switch_hides_the_box_and_leaves_the_ring_and_back_on_the_box_returns(self):
        r = self._result()
        self.assertTrue(r["off"]["hidden"], "the box hides on the save: %r" % r["off"]["box"])
        self.assertIn("ring-needs-you", r["off"]["box"]["tabClasses"] or "", "the ring stays: the switch is the box's alone")
        self.assertTrue(r["on"]["shown"], "back on, the box returns with its rows: %r" % r["on"]["box"])


if __name__ == "__main__":
    unittest.main()
