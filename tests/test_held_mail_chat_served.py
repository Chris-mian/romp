"""The chat page's approval box and the ask ring for a held message (plans/notice-cards.md, "Action kinds and the held-mail card",
2026-09-19): a hermetic kernel over one synthetic live session in the notes-api demo world, the real /chat page served from a
copy of the built bundle, driven by Playwright, the feed pane closed. A message from a DIRECTED peer held under
STATE/postal/quarantine before boot becomes a notice card at the first build (the kernel's backfill; the chat is a feed
audience, so the feed builds with no feed pane), and the chat page shows it in the #notices box above the background box with
Approve and Deny while the session's tab wears the ask ring. Approve reaches the kernel's noticeAction op and, with no postal
bus in the lab, is refused as unreachable: the buttons re-arm and the row says why. Deny opens the optional note inline with two
choices and a way back; Deny without note posts the bare verdict and is refused the same way. The decision itself is the bus's
success (unit-tested with the act stubbed), so the lab takes it the way the runner records it, an expire row in the notice
store: the row leaves the box and the ring leaves the tab within a frame. Synthetic only: placeholder ids, invented text,
hostname TESTHOST."""
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
MID = "aaaaaaaa-bbbb-cccc-dddd-000000000102"
MID2 = "aaaaaaaa-bbbb-cccc-dddd-000000000103"    # lands while Approve is pressed (the review of PR 1890, medium 1)
MID3 = "aaaaaaaa-bbbb-cccc-dddd-000000000104"    # lands after the refusal: the row's refusal line must stay
TEXT = "the README draft is ready for a look, could you check the parser section before the release?"

DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));
let browser;
try { browser = await chromium.launch(cfg.launch || {}); }
catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
const page = await browser.newPage({ viewport: { width: 1100, height: 760 } });
const errors = []; page.on("pageerror", (e) => errors.push(String(e).slice(0, 300)));
await page.goto(cfg.chat);
await page.waitForSelector("#tabs .tab", { timeout: 30000 }).catch(() => {});
const id = "notice:" + cfg.sid + ":" + cfg.mid + ":1";
const rowSel = '#notices .ntc-row[data-item="' + id + '"]';
const boxShown = () => page.evaluate((s) => { const b = document.getElementById("notices"); return !!b && b.style.display !== "none" && !!document.querySelector(s); }, rowSel);
const facts = () => page.evaluate((s) => { const box = document.getElementById("notices"); const r = document.querySelector(s);
  const tab = Array.from(document.querySelectorAll("#tabs .tab")).find((t) => ((t.querySelector(".tab-label") || t).textContent || "").trim() === "web");
  return { boxDisplay: box ? box.style.display : null, boxVisible: !!box && box.offsetHeight > 0, row: !!r,
    title: r ? (r.querySelector(".ntc-title") || {}).textContent : null, body: r ? (r.querySelector(".ntc-body") || {}).textContent : null,
    buttons: r ? Array.from(r.querySelectorAll("button")).map((b) => ({ label: b.textContent, disabled: b.disabled })) : null,
    note: r ? (r.querySelector(".ntc-note") || {}).style?.display : null, err: r ? ((r.querySelector(".ntc-err") || {}).textContent || "") : null,
    errShown: r ? (r.querySelector(".ntc-err") || {}).style?.display : null,
    aboveBg: (() => { const bg = document.getElementById("bg-tasks"); return !!(box && bg && box.compareDocumentPosition(bg) & Node.DOCUMENT_POSITION_FOLLOWING); })(),
    rows: box ? Array.from(box.querySelectorAll(".ntc-row")).map((x) => x.getAttribute("data-item")) : [],
    atBottom: (() => { const c = document.getElementById("content"); return c ? (c.scrollHeight - c.scrollTop - c.clientHeight) < 2 : null; })(),
    scrollable: (() => { const c = document.getElementById("content"); return c ? c.scrollHeight > c.clientHeight + 40 : null; })(),
    tabClasses: tab ? Array.from(tab.classList) : null }; }, rowSel);
const hold = (mid, body) => fs.writeFileSync(cfg.qdir + "/" + mid + ".json", JSON.stringify({ mid, to: "web", toId: cfg.sid, frm: "api", frmId: "11111111-2222-3333-4444-666666666666",
  body, kind: "coordinate", origin: "TESTHOST", via: "peer", at: Math.floor(Date.now() / 1000) - 60 }));
const rowSelOf = (mid) => '#notices .ntc-row[data-item="notice:' + cfg.sid + ":" + mid + ':1"]';
// (1) the box and its row from the first frames; the ring trails the feed build by at most one frame
await page.waitForFunction((s) => { const b = document.getElementById("notices"); return !!b && b.style.display !== "none" && !!document.querySelector(s); }, rowSel, { timeout: 90000 }).catch(() => {});
await page.waitForFunction(() => { const tab = Array.from(document.querySelectorAll("#tabs .tab")).find((t) => ((t.querySelector(".tab-label") || t).textContent || "").trim() === "web"); return !!tab && Array.from(tab.classList).some((c) => c.startsWith("ring-")); }, null, { timeout: 60000 }).catch(() => {});
const first = await facts();
// (2) Approve PRESSED while a second hold lands (the review of PR 1890, medium 1): the frame that adds the second row must not
// destroy the pressed button; the release is a click: latched, posted, the kernel's refusal (no bus) re-arms with the reason
let approve = null;
if (first.row) {
  const btn = page.locator(rowSel + " button", { hasText: /^Approve$/ }).first();
  const bb = await btn.boundingBox();
  await page.evaluate((s) => { window.__pressed = Array.from(document.querySelector(s).querySelectorAll("button")).find((x) => x.textContent === "Approve"); }, rowSel);
  await page.mouse.move(bb.x + bb.width / 2, bb.y + bb.height / 2);
  await page.mouse.down();
  hold(cfg.mid2, "a second message, held while the first's Approve is pressed");
  await page.waitForSelector(rowSelOf(cfg.mid2), { timeout: 90000 }).catch(() => {});
  const midPress = await facts();
  // the pressed button must be the SAME element after the frame (the old code replaced every row, so the press had nothing to
  // land on); the box grew upward with its new row, so the pointer follows the button to where it now sits before the release
  midPress.pressedSurvived = await page.evaluate((s) => { const r = document.querySelector(s); const b = r && Array.from(r.querySelectorAll("button")).find((x) => x.textContent === "Approve");
    return !!(window.__pressed && document.contains(window.__pressed) && b === window.__pressed); }, rowSel);
  const bb2 = await btn.boundingBox();
  await page.mouse.move(bb2.x + bb2.width / 2, bb2.y + bb2.height / 2);
  await page.mouse.up();
  const latched = await page.evaluate((s) => { const r = document.querySelector(s); return Array.from(r.querySelectorAll("button")).map((x) => ({ label: x.textContent, disabled: x.disabled })); }, rowSel);
  await page.waitForFunction((s) => { const e = document.querySelector(s + " .ntc-err"); return e && e.style.display !== "none" && (e.textContent || "").length > 0; }, rowSel, { timeout: 40000 }).catch(() => {});
  approve = { midPress, latched, after: await facts() };
  // (2b) a THIRD hold lands: the first row's refusal line stays (its own actions did not change), the rows keep their order
  hold(cfg.mid3, "a third message, held after the refusal");
  await page.waitForSelector(rowSelOf(cfg.mid3), { timeout: 90000 }).catch(() => {});
  approve.afterThird = await facts();
}
// (3) Deny: the inline note step, Back, then Deny without note: refused the same way
let deny = null;
if (first.row) {
  await page.evaluate((s) => { const r = document.querySelector(s); Array.from(r.querySelectorAll("button")).find((x) => x.textContent === "Deny").click(); }, rowSel);
  const step = await facts();
  step.atBottomAfterNote = (await facts()).atBottom;
  await page.evaluate((s) => { const r = document.querySelector(s); Array.from(r.querySelectorAll("button")).find((x) => x.textContent === "Back").click(); }, rowSel);
  const back = await facts();
  await page.evaluate((s) => { const r = document.querySelector(s); Array.from(r.querySelectorAll("button")).find((x) => x.textContent === "Deny").click(); }, rowSel);
  await page.evaluate((s) => { const r = document.querySelector(s); const e = r.querySelector(".ntc-err"); e.textContent = ""; e.style.display = "none";
    Array.from(r.querySelectorAll("button")).find((x) => x.textContent === "Deny without note").click(); }, rowSel);
  const latched = await facts();
  await page.waitForFunction((s) => { const e = document.querySelector(s + " .ntc-err"); return e && e.style.display !== "none" && (e.textContent || "").length > 0; }, rowSel, { timeout: 40000 }).catch(() => {});
  deny = { step, back, latched, after: await facts() };
}
// (4) the decision, as the runner records a success: an expire row in the notice store; the row and the ring leave
let decided = null;
if (first.row) {
  for (const mid of [cfg.mid, cfg.mid2, cfg.mid3]) fs.appendFileSync(cfg.notices, JSON.stringify({ op: "expire", t: Math.floor(Date.now() / 1000), key: mid, rev: 1, sid: cfg.sid }) + "\n");
  await page.waitForFunction(() => !document.querySelector("#notices .ntc-row"), null, { timeout: 90000 }).catch(() => {});
  await page.waitForFunction(() => { const tab = Array.from(document.querySelectorAll("#tabs .tab")).find((t) => ((t.querySelector(".tab-label") || t).textContent || "").trim() === "web"); return !!tab && !Array.from(tab.classList).some((c) => c === "ring-waiting-on-you"); }, null, { timeout: 60000 }).catch(() => {});
  decided = await facts();
}
process.stdout.write("RESULT:" + JSON.stringify({ first, approve, deny, decided, errors }) + "\n");
await browser.close();
"""


class HeldMailChatServed(unittest.TestCase):
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
        cls.lab = tempfile.mkdtemp(prefix="held-mail-chat-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            cls._skip("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
        dist = os.path.join(cls.lab, "dist")
        copy_dist(os.path.join(EXT, "dist"), dist)
        cls.state = os.path.join(cls.lab, "xdg", "romp")
        cwd = os.path.join(cls.lab, "notes-api")
        for d in ("names", "sdk", "states", os.path.join("postal", "quarantine")):
            os.makedirs(os.path.join(cls.state, d), exist_ok=True)
        os.makedirs(cwd, exist_ok=True)
        Path(cls.state, "session-hosts").write_text("off\n")
        claude = os.path.join(cls.lab, "claude")
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        Path(cls.state, "names", SID).write_text("web\t%s\t#1EA1EB\t#ffffff\n" % cwd)
        Path(cls.state, "sdk", SID + ".json").write_text(json.dumps(
            {"sid": SID, "name": "web", "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": SID, "alive": True,
             "model": "claude-fable-5-1", "liveModel": "Fable 5.1"}))
        t0 = int(time.time()) - 3600
        iso = lambda t: time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t))
        # sixty closed turns: the transcript scrolls, so "at the bottom" is a real position the boxes below could push (low a)
        recs, parent = [], None
        for i in range(60):
            u, a = "u%d" % i, "a%d" % i
            recs.append({"type": "user", "uuid": u, "parentUuid": parent, "timestamp": iso(t0 + 4 * i), "sessionId": SID,
                         "message": {"role": "user", "content": "question %d about the notes api" % i}})
            recs.append({"type": "assistant", "uuid": a, "parentUuid": u, "timestamp": iso(t0 + 4 * i + 2), "sessionId": SID,
                         "message": {"role": "assistant", "model": "claude-fable-5-1", "stop_reason": "end_turn",
                                     "content": [{"type": "text", "text": "answer %d: the notes api keeps its shape." % i}]}})
            parent = a
        Path(proj, SID + ".jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
        cls.held = os.path.join(cls.state, "postal", "quarantine", MID + ".json")
        Path(cls.held).write_text(json.dumps(
            {"mid": MID, "to": "web", "toId": SID, "frm": "api", "frmId": "11111111-2222-3333-4444-666666666666", "body": TEXT,
             "kind": "coordinate", "origin": "TESTHOST", "via": "peer", "at": int(time.time()) - 600}))
        cls.notices = os.path.join(cls.state, "notices", SID + ".jsonl")
        cls.qdir = os.path.join(cls.state, "postal", "quarantine")
        cls.port = _free_port()
        cls.token = "testtok-heldchat"
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
            cfg = os.path.join(self.lab, "heldchat.json")
            base = "http://127.0.0.1:%d" % self.port
            with open(cfg, "w") as f:
                json.dump({"chat": base + "/chat?token=" + self.token, "token": self.token, "sid": SID, "mid": MID, "mid2": MID2, "mid3": MID3,
                           "notices": self.notices, "qdir": self.qdir, "text": TEXT}, f)
            driver = os.path.join(self.lab, "heldchat.mjs")
            Path(driver).write_text(DRIVER)
            p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=500,
                               env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
            if "browser-launch-failed" in p.stderr:
                self._skip("no playwright browser on this box")
            line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
            if line is None:
                type(self)._fail = "the driver produced no RESULT (stderr: %s; kernel: %s)" % (p.stderr[-2000:], open(self.klog).read()[-1500:])
                self.fail(type(self)._fail)
            type(self)._r = json.loads(line[len("RESULT:"):])
        print("HELDCHAT:", json.dumps(self._r), file=sys.stderr)
        return self._r

    def test_the_held_message_shows_in_the_approval_box_above_the_background_box_and_the_tab_wears_the_ask_ring(self):
        r = self._result()
        self.assertEqual(r["errors"], [], "no page error")
        f = r["first"]
        self.assertTrue(f["row"], "the row is in the box (kernel log tail: %s)" % open(self.klog).read()[-800:])
        self.assertEqual((f["boxDisplay"], f["boxVisible"]), ("", True))
        self.assertTrue(f["aboveBg"], "the approval box sits above the background box")
        self.assertEqual(f["title"], "New message from api")
        self.assertIn(TEXT, f["body"], "the message text is the row's body")
        self.assertEqual(f["buttons"], [{"label": "Approve", "disabled": False}, {"label": "Deny", "disabled": False}], "two actions of the kind, no Edit")
        self.assertIsNotNone(f["tabClasses"], "the session's tab")
        self.assertIn("ring-waiting-on-you", f["tabClasses"], "the ask ring: a held message blocks the session until decided: %r" % f["tabClasses"])
        self.assertTrue(f["scrollable"], "the transcript scrolls (sixty turns), so the bottom is a real position")
        self.assertTrue(f["atBottom"], "the at-bottom reader stayed at the bottom when the box appeared (the box is a box below, low a)")

    def test_a_press_survives_a_hold_landing_mid_press_and_the_refusal_line_survives_the_next_hold(self):
        r = self._result()
        a = r["approve"]
        self.assertIsNotNone(a)
        self.assertEqual(len(a["midPress"]["rows"]), 2, "the second hold's row landed while Approve was pressed: %r" % a["midPress"]["rows"])
        self.assertTrue(a["midPress"]["pressedSurvived"], "the pressed button is the same element after the frame that added a row (reconciled in place, never replaced)")
        self.assertEqual(a["latched"], [{"label": "Approve…", "disabled": True}, {"label": "Deny", "disabled": True}], "the release was a click: latched (the review of PR 1890, medium 1)")
        self.assertIn("Refused: postal bus unreachable", a["after"]["err"], "the kernel answered the click")
        t = a["afterThird"]
        self.assertEqual(len(t["rows"]), 3, "the third hold's row joined: %r" % t["rows"])
        self.assertEqual(t["rows"][0], "notice:%s:%s:1" % (SID, MID), "the first row kept its place")
        self.assertIn("Refused: postal bus unreachable", t["err"], "the first row's refusal line survived the frame that added a row")
        self.assertEqual(t["errShown"], "")
        self.assertTrue(t["atBottom"], "still at the bottom with three rows")

    def test_approve_reaches_the_kernel_and_the_refusal_re_arms_the_row_saying_why(self):
        r = self._result()
        a = r["approve"]
        self.assertIsNotNone(a)
        self.assertEqual(a["latched"], [{"label": "Approve…", "disabled": True}, {"label": "Deny", "disabled": True}], "both latch; the one clicked says what it is doing")
        self.assertEqual(a["after"]["errShown"], "", "the reason shows in the row")
        self.assertIn("Refused: postal bus unreachable", a["after"]["err"], "no bus in the lab: the act road's own refusal")
        self.assertEqual(a["after"]["buttons"], [{"label": "Approve", "disabled": False}, {"label": "Deny", "disabled": False}], "re-armed on the kernel's answer")

    def test_deny_opens_the_note_inline_with_two_choices_and_a_way_back_and_the_bare_deny_posts_the_verdict(self):
        r = self._result()
        d = r["deny"]
        self.assertIsNotNone(d)
        self.assertEqual([b["label"] for b in d["step"]["buttons"]], ["Deny & send note", "Deny without note", "Back"])
        self.assertEqual(d["step"]["note"], "", "the note textarea shows")
        self.assertTrue(d["step"]["atBottomAfterNote"], "the note step grew the box: the at-bottom reader stayed at the bottom (low a)")
        self.assertEqual([b["label"] for b in d["back"]["buttons"]], ["Approve", "Deny"], "Back returns to the two actions"); self.assertEqual(d["back"]["note"], "none")
        self.assertTrue(all(b["disabled"] for b in d["latched"]["buttons"]), "latched on the decision: %r" % d["latched"]["buttons"])
        self.assertIn("Refused: postal bus unreachable", d["after"]["err"])
        self.assertTrue(all(not b["disabled"] for b in d["after"]["buttons"]), "re-armed")

    def test_the_decision_takes_the_row_off_the_box_and_the_ring_off_the_tab(self):
        r = self._result()
        d = r["decided"]
        self.assertIsNotNone(d)
        self.assertFalse(d["row"], "the row left with the frame that dropped it"); self.assertEqual(d["rows"], [], "all three decided")
        self.assertEqual(d["boxDisplay"], "none", "no row: the box hides")
        self.assertNotIn("ring-waiting-on-you", d["tabClasses"] or [], "the ask ring left with the decision: %r" % d["tabClasses"])


if __name__ == "__main__":
    unittest.main()
