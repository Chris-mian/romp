"""The chat page's approval box and the ask ring for a held message (plans/notice-cards.md, "Action kinds and the held-mail card",
2026-09-19): a hermetic kernel over one synthetic live session in the notes-api demo world, the real /chat page served from a
copy of the built bundle, driven by Playwright, the feed pane closed. A message from a DIRECTED peer held under
STATE/postal/quarantine before boot becomes a notice card at the first build (the kernel's backfill; the chat is a feed
audience, so the feed builds with no feed pane), and the chat page shows it in the #notices box above the background box with
Approve and Deny while the session's tab wears the ask ring. Approve reaches the kernel's noticeAction op and, with no postal
bus in the lab, is refused as unreachable: the buttons re-arm and the row says why. Deny opens the optional note inline with two
choices and a way back; Deny without note posts the bare verdict and is refused the same way. The decision itself is the bus's
success (unit-tested with the act stubbed), so the lab takes it the way the runner records it, an expire row in the notice
store: the row leaves the box and the ring leaves the tab within a frame. Every read of the reader's bottom holds at the box's
observer pass (the page's romp:box-below event, the load flake of 2026-09-19), and one scenario pins the follow-mode race that
flake uncovered: a write to the bottom whose scroll echo is dispatched after the box grew. Synthetic only: placeholder ids,
invented text, hostname TESTHOST."""
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
// the payload explains a failure (2026-09-20: test one went red once in a whole-suite run and the assertion was lost with the log):
// the browser's console errors, and every wait of the first leg timed and marked, so a timeout names itself rather than surfacing
// as a missing ring or a False read downstream
const consoleErrors = []; page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(String(m.text()).slice(0, 300)); });
const waits = {};
const timed = async (label, p) => { const t0 = Date.now(); const ok = await p.then(() => true).catch(() => false); waits[label] = { ok, ms: Date.now() - t0 }; return ok; };
// the bottom box's observer pass is an EVENT (render.ts, "romp:box-below": one per pass, with the height that pass acted on). The lab
// records the last pass per box before the page's scripts run, and a read of the bottom holds until the box's current height is the
// one the last pass reported (settled): the flake of 2026-09-19 (main red at bee556e8) read scrollTop between the box's growth and
// the pass that re-pins the reader. A box at its max height grows no further and passes no more, so the hold is on the height,
// never on "a pass came" (two rows reach the max on one font and not on another)
await page.addInitScript(() => { window.__labBoxBelow = {}; window.addEventListener("romp:box-below", (e) => { const d = e.detail;
  window.__labBoxBelow[d.id] = { n: ((window.__labBoxBelow[d.id] || {}).n || 0) + 1, height: d.height, repinned: d.repinned }; }); });
await page.goto(cfg.chat);
// the socket hold (the merge-guard lab's shim): an outbound frame whose type is in __hold is parked at the socket, not sent;
// __release sends the parked ones. The latch is a TRANSIENT (the kernel's refusal re-arms the row and says why), so it may not
// be asserted by timing: CI's runner had the answer back before the read (the manager's fix parcel, 2026-09-19). The click's
// request is held at the socket while the latch is read, then released, and the re-arm and the refusal line are read after it
await page.evaluate(() => { const orig = WebSocket.prototype.send; window.__hold = new Set(); window.__heldRaw = [];
  WebSocket.prototype.send = function (d) { window.__ws = this; try { const m = JSON.parse(d); if (m && m.type && window.__hold.has(m.type)) { window.__heldRaw.push(d); return; } } catch (e) {} return orig.call(this, d); };
  window.__release = () => { const ws = window.__ws; const held = window.__heldRaw; window.__heldRaw = []; for (const d of held) orig.call(ws, d); return held.length; }; });
const holdActions = () => page.evaluate(() => { window.__hold.add("noticeAction"); });
const releaseActions = () => page.evaluate(() => window.__release());
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
    pass: (window.__labBoxBelow || {}).notices || null, boxHeight: box ? box.getBoundingClientRect().height : null,
    tabClasses: tab ? Array.from(tab.classList) : null }; }, rowSel);
// settled: the approval box's content height (what the observer measures: the border box less borders and padding, 0 while hidden)
// is the height its last pass reported. False after fifteen seconds is a fact the assertions read, never a retry
const settledFn = () => { const b = document.getElementById("notices"); const rec = (window.__labBoxBelow || {}).notices; if (!b || !rec) return false;
  const cs = getComputedStyle(b); const r = b.getBoundingClientRect().height;
  const content = r > 0 ? r - parseFloat(cs.borderTopWidth) - parseFloat(cs.borderBottomWidth) - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom) : 0;
  return Math.abs(content - rec.height) < 0.02; };
const settled = () => page.waitForFunction(settledFn, null, { timeout: 15000 }).then(() => true).catch(() => false);
const atBottomNow = () => page.evaluate(() => { const c = document.getElementById("content"); return c ? (c.scrollHeight - c.scrollTop - c.clientHeight) < 2 : null; });
const lastPass = () => page.evaluate(() => (window.__labBoxBelow || {}).notices || null);
const hold = (mid, body) => fs.writeFileSync(cfg.qdir + "/" + mid + ".json", JSON.stringify({ mid, to: "web", toId: cfg.sid, frm: "api", frmId: "11111111-2222-3333-4444-666666666666",
  body, kind: "coordinate", origin: "TESTHOST", via: "peer", at: Math.floor(Date.now() / 1000) - 60 }));
const rowSelOf = (mid) => '#notices .ntc-row[data-item="notice:' + cfg.sid + ":" + mid + ':1"]';
// (1) the box and its row from the first frames; the ring trails the feed build by at most one frame
await timed("row", page.waitForFunction((s) => { const b = document.getElementById("notices"); return !!b && b.style.display !== "none" && !!document.querySelector(s); }, rowSel, { timeout: 90000 }));
const settled1 = await timed("settled", page.waitForFunction(settledFn, null, { timeout: 15000 }));   // the box appeared: the reader's re-pin is on the pass this holds at
await timed("ring", page.waitForFunction(() => { const tab = Array.from(document.querySelectorAll("#tabs .tab")).find((t) => ((t.querySelector(".tab-label") || t).textContent || "").trim() === "web"); return !!tab && Array.from(tab.classList).some((c) => c.startsWith("ring-")); }, null, { timeout: 60000 }));
const first = await facts(); first.settled = settled1; first.waits = Object.assign({}, waits);
first.geometry = await page.evaluate(() => { const c = document.getElementById("content"); const b = document.getElementById("notices"); return c ? { sh: c.scrollHeight, st: c.scrollTop, ch: c.clientHeight, box: b ? b.getBoundingClientRect().height : null } : null; });
// (1b) follow mode across a box's growth (2026-09-19, the second cause behind main's red): a write to the bottom owes one scroll event,
// its echo; the approval box growing before that event is dispatched put the reader a box's height above the NEW bottom at the echo's
// at-bottom read, and the record said scrolled-up, so the box's pass had nothing to re-pin. Deterministic here: the reader moves up
// (no write pending: a gesture, follow mode off), then in ONE task the jump button's write to the bottom and the Deny step's growth
// of the box (the note textarea under one row, which leaves room below the max height); the echo and the pass come in the next
// rendering update, the echo first. Then Back: the two actions again, the box back to one row's height
let race = null;
if (first.row) {
  await page.evaluate(() => { const c = document.getElementById("content"); c.scrollTop = c.scrollTop - 300; });
  await page.waitForFunction(() => { const j = document.getElementById("jump-bottom"); return !!j && !j.hidden; }, null, { timeout: 15000 }).catch(() => {});
  const before = await lastPass();
  await page.evaluate((s) => { document.getElementById("jump-bottom").click(); const r = document.querySelector(s); Array.from(r.querySelectorAll("button")).find((x) => x.textContent === "Deny").click(); }, rowSel);
  const settledRace = await settled();
  race = { settled: settledRace, before, pass: await lastPass(), atBottom: await atBottomNow(), boxHeight: await page.evaluate(() => document.getElementById("notices").getBoundingClientRect().height) };
  await page.evaluate((s) => { const r = document.querySelector(s); Array.from(r.querySelectorAll("button")).find((x) => x.textContent === "Back").click(); }, rowSel);
  race.backSettled = await settled(); race.back = await facts();
}
// (2) Approve PRESSED while a second hold lands (the review of PR 1890, medium 1): the frame that adds the second row must not
// destroy the pressed button; the release is a click: latched, posted, the kernel's refusal (no bus) re-arms with the reason
let approve = null;
if (first.row) {
  const btn = page.locator(rowSel + " button", { hasText: /^Approve$/ }).first();
  const bb = await btn.boundingBox();
  await page.evaluate((s) => { window.__pressed = Array.from(document.querySelector(s).querySelectorAll("button")).find((x) => x.textContent === "Approve"); }, rowSel);
  await page.mouse.move(bb.x + bb.width / 2, bb.y + bb.height / 2);
  await holdActions();
  await page.mouse.down();
  hold(cfg.mid2, "a second message, held while the first's Approve is pressed");
  await page.waitForSelector(rowSelOf(cfg.mid2), { timeout: 90000 }).catch(() => {});
  const settledMid = await settled();   // the second row grew the box under the press
  const midPress = await facts(); midPress.settled = settledMid;
  // the pressed button must be the SAME element after the frame (the old code replaced every row, so the press had nothing to
  // land on); the box grew upward with its new row, so the pointer follows the button to where it now sits before the release
  midPress.pressedSurvived = await page.evaluate((s) => { const r = document.querySelector(s); const b = r && Array.from(r.querySelectorAll("button")).find((x) => x.textContent === "Approve");
    return !!(window.__pressed && document.contains(window.__pressed) && b === window.__pressed); }, rowSel);
  const bb2 = await btn.boundingBox();
  await page.mouse.move(bb2.x + bb2.width / 2, bb2.y + bb2.height / 2);
  await page.mouse.up();
  const latched = await page.evaluate((s) => { const r = document.querySelector(s); return Array.from(r.querySelectorAll("button")).map((x) => ({ label: x.textContent, disabled: x.disabled })); }, rowSel);
  const held = await releaseActions();   // the request goes to the kernel now; its refusal (no bus) re-arms the row and says why
  await page.waitForFunction((s) => { const e = document.querySelector(s + " .ntc-err"); return e && e.style.display !== "none" && (e.textContent || "").length > 0; }, rowSel, { timeout: 40000 }).catch(() => {});
  approve = { midPress, latched, held, after: await facts() };
  // (2b) a THIRD hold lands: the first row's refusal line stays (its own actions did not change), the rows keep their order
  hold(cfg.mid3, "a third message, held after the refusal");
  await page.waitForSelector(rowSelOf(cfg.mid3), { timeout: 90000 }).catch(() => {});
  const settledThird = await settled();   // three rows: at the max height on one font, grown on another; the hold is the height, not a pass
  approve.afterThird = await facts(); approve.afterThird.settled = settledThird;
}
// (3) Deny: the inline note step, Back, then Deny without note: refused the same way
let deny = null;
if (first.row) {
  await page.evaluate((s) => { const r = document.querySelector(s); Array.from(r.querySelectorAll("button")).find((x) => x.textContent === "Deny").click(); }, rowSel);
  const settledNote = await settled();   // with three rows the box may already stand at its max height: settled either way
  const step = await facts(); step.settled = settledNote;
  await page.evaluate((s) => { const r = document.querySelector(s); Array.from(r.querySelectorAll("button")).find((x) => x.textContent === "Back").click(); }, rowSel);
  const back = await facts();
  await page.evaluate((s) => { const r = document.querySelector(s); Array.from(r.querySelectorAll("button")).find((x) => x.textContent === "Deny").click(); }, rowSel);
  await holdActions();
  await page.evaluate((s) => { const r = document.querySelector(s); const e = r.querySelector(".ntc-err"); e.textContent = ""; e.style.display = "none";
    Array.from(r.querySelectorAll("button")).find((x) => x.textContent === "Deny without note").click(); }, rowSel);
  const latched = await facts();
  const held = await releaseActions();
  await page.waitForFunction((s) => { const e = document.querySelector(s + " .ntc-err"); return e && e.style.display !== "none" && (e.textContent || "").length > 0; }, rowSel, { timeout: 40000 }).catch(() => {});
  deny = { step, back, latched, held, after: await facts() };
}
// (4) the decision, as the runner records a success: an expire row in the notice store; the row and the ring leave
let decided = null;
if (first.row) {
  for (const mid of [cfg.mid, cfg.mid2, cfg.mid3]) fs.appendFileSync(cfg.notices, JSON.stringify({ op: "expire", t: Math.floor(Date.now() / 1000), key: mid, rev: 1, sid: cfg.sid }) + "\n");
  await page.waitForFunction(() => !document.querySelector("#notices .ntc-row"), null, { timeout: 90000 }).catch(() => {});
  await page.waitForFunction(() => { const tab = Array.from(document.querySelectorAll("#tabs .tab")).find((t) => ((t.querySelector(".tab-label") || t).textContent || "").trim() === "web"); return !!tab && !Array.from(tab.classList).some((c) => c === "ring-waiting-on-you"); }, null, { timeout: 60000 }).catch(() => {});
  decided = await facts();
}
process.stdout.write("RESULT:" + JSON.stringify({ first, race, approve, deny, decided, errors, consoleErrors }) + "\n");
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
        f = r["first"]
        # every message of this leg carries the payload that explains it (2026-09-20): the timed waits, the console errors, the kernel log tail
        why = lambda: "waits: %r; console errors: %r; kernel log tail: %s" % (f.get("waits"), r.get("consoleErrors"), open(self.klog).read()[-800:])
        self.assertEqual(r["errors"], [], "no page error (%s)" % why())
        self.assertTrue(f["row"], "the row is in the box (%s)" % why())
        self.assertEqual((f["boxDisplay"], f["boxVisible"]), ("", True))
        self.assertTrue(f["aboveBg"], "the approval box sits above the background box")
        self.assertEqual(f["title"], "New message from api")
        self.assertIn(TEXT, f["body"], "the message text is the row's body")
        self.assertEqual(f["buttons"], [{"label": "Approve", "disabled": False}, {"label": "Deny", "disabled": False}], "two actions of the kind, no Edit")
        self.assertIsNotNone(f["tabClasses"], "the session's tab")
        self.assertIn("ring-waiting-on-you", f["tabClasses"], "the ask ring: a held message blocks the session until decided: %r (%s)" % (f["tabClasses"], why()))
        self.assertTrue(f["scrollable"], "the transcript scrolls (sixty turns), so the bottom is a real position")
        self.assertTrue(f["settled"], "the box's height is the one its last observer pass reported: the event the read holds at (pass: %r; %s)" % (f["pass"], why()))
        self.assertTrue(f["atBottom"], "the at-bottom reader stayed at the bottom when the box appeared (the box is a box below, low a), read settled (geometry: %r; pass: %r; %s)" % (f.get("geometry"), f["pass"], why()))

    def test_a_bottom_writes_echo_keeps_follow_mode_when_the_box_grows_before_it_is_dispatched(self):
        r = self._result()
        x = r["race"]
        self.assertIsNotNone(x)
        self.assertTrue(x["settled"], "the box settled after the note step opened under the jump (pass: %r)" % x["pass"])
        self.assertGreater(x["pass"]["height"], x["before"]["height"], "the note step grew the box, the scenario's premise: %r -> %r" % (x["before"], x["pass"]))
        self.assertTrue(x["atBottom"], "the jump's write to the bottom and the box's growth in one task: the write's echo keeps follow mode and the pass re-pins the reader to the new bottom (pass: %r)" % x["pass"])
        self.assertTrue(x["backSettled"]); self.assertEqual([b["label"] for b in x["back"]["buttons"]], ["Approve", "Deny"], "Back restores the two actions")

    def test_a_press_survives_a_hold_landing_mid_press_and_the_refusal_line_survives_the_next_hold(self):
        r = self._result()
        a = r["approve"]
        self.assertIsNotNone(a)
        self.assertEqual(len(a["midPress"]["rows"]), 2, "the second hold's row landed while Approve was pressed: %r" % a["midPress"]["rows"])
        self.assertTrue(a["midPress"]["pressedSurvived"], "the pressed button is the same element after the frame that added a row (reconciled in place, never replaced)")
        self.assertEqual(a["latched"], [{"label": "Approve…", "disabled": True}, {"label": "Deny", "disabled": True}], "the release was a click: latched (the review of PR 1890, medium 1); read with the request held at the socket, so the kernel's answer cannot beat the read")
        self.assertEqual(a["held"], 1, "exactly one request was held and released: the click's noticeAction")
        self.assertIn("Refused: postal bus unreachable", a["after"]["err"], "the kernel answered the click")
        t = a["afterThird"]
        self.assertEqual(len(t["rows"]), 3, "the third hold's row joined: %r" % t["rows"])
        self.assertEqual(t["rows"][0], "notice:%s:%s:1" % (SID, MID), "the first row kept its place")
        self.assertIn("Refused: postal bus unreachable", t["err"], "the first row's refusal line survived the frame that added a row")
        self.assertEqual(t["errShown"], "")
        self.assertTrue(t["settled"], "the box settled after the third row, at its max height or grown (pass: %r)" % t["pass"]); self.assertTrue(t["atBottom"], "still at the bottom with three rows, read settled")

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
        self.assertTrue(d["step"]["settled"], "the box settled after the note step (pass: %r)" % d["step"]["pass"]); self.assertTrue(d["step"]["atBottom"], "the note step grew or kept the box: the at-bottom reader stayed at the bottom (low a), read settled")
        self.assertEqual([b["label"] for b in d["back"]["buttons"]], ["Approve", "Deny"], "Back returns to the two actions"); self.assertEqual(d["back"]["note"], "none")
        self.assertTrue(all(b["disabled"] for b in d["latched"]["buttons"]), "latched on the decision (read with the request held at the socket): %r" % d["latched"]["buttons"])
        self.assertEqual(d["held"], 1, "exactly one request was held and released")
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
