"""The held-mail card on the served feed page (plans/notice-cards.md, "Action kinds and the held-mail card", 2026-09-19): a
hermetic kernel over one synthetic session in the notes-api demo world, the real /feed page served from a copy of the built
bundle, driven by Playwright. A message from a DIRECTED peer held under STATE/postal/quarantine before boot becomes a NOTICE
card under the recipient at the first build (the kernel's backfill): title, producer, the route line and the message text,
Approve and Deny of the quarantine kind, under Blocked. The card modal shows the message text with the recipient's name as
the header, unstruck for a live session (the older card's header struck it through as a dead session's). Approve reaches the
kernel's noticeAction op and, with no postal bus in the lab, is refused with the bus's unreachable reason: the button re-arms
and the reason rides the toast, the card stays. Deny asks for the optional note first, on the document body, with two choices
and no Cancel; Deny without note posts the bare verdict and is refused the same way. Clear dismisses the card and leaves the
held file on disk (the decision is the bus's, never the pane's). The delivery road itself is unit-tested with the bus's act
stubbed (tests/test_kernel_trust.py HeldMailDecision, tests/test_notice_card_store.py ActionKinds). Synthetic only: placeholder
ids, invented text, hostname TESTHOST."""
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
MID = "aaaaaaaa-bbbb-cccc-dddd-000000000101"
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
const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
const errors = []; page.on("pageerror", (e) => errors.push(String(e).slice(0, 300)));
// the pane's frames, recorded at the federation manager's inbound; every noticeActionDone; every toast
await page.addInitScript(() => {
  window.__frames = 0; window.__nad = []; window.__toasts = [];
  document.addEventListener("DOMContentLoaded", () => new MutationObserver(() => { for (const t of document.querySelectorAll(".feed-toast")) { const x = t.textContent || ""; if (x && !window.__toasts.includes(x)) window.__toasts.push(x); } })
    .observe(document.documentElement, { childList: true, subtree: true, characterData: true }));
  const record = (m) => { if (!m) return; if (m.type === "feed" && Array.isArray(m.asks)) window.__frames++; if (m.type === "noticeActionDone") window.__nad.push(m); };
  let fed = null;
  Object.defineProperty(window, "__rompFed", { configurable: true, get() { return fed; },
    set(v) { fed = v; if (v && typeof v.inbound === "function" && !v.__labWrapped) { const inb = v.inbound; v.__labWrapped = true; v.inbound = (h, m) => { record(m); return inb(h, m); }; } } });
  window.addEventListener("message", (e) => { if (!fed) record(e.data); });
});
const id = "notice:" + cfg.sid + ":" + cfg.mid + ":1";
const sel = '[data-key="a:' + id + '"]';
const cardFacts = () => page.evaluate((s) => { const c = document.querySelector(s); if (!c) return null;
  const q = (x) => c.querySelector(x); const cs = getComputedStyle(c);
  return { col: c.parentElement && c.parentElement.id, vis: c.offsetHeight > 0 && cs.display !== "none", prod: (q(".fask-nprod") || {}).textContent || "",
    bodyText: (q(".fask-nbody") || {}).textContent || "", title: (q(".fcard-title") || {}).textContent || "",
    name: (q(".fname") || {}).textContent || "", live: c.classList.contains("live"), dead: c.classList.contains("dead"),
    actions: Array.from(c.querySelectorAll(".fask-nactions button")).map((b) => ({ label: b.textContent, disabled: b.disabled, vis: b.offsetHeight > 0 })),
    blockChip: (() => { const b = q(".fask-blocked, .fblocked"); return b ? getComputedStyle(b).display : null; })(),
    clearVisible: Array.from(c.querySelectorAll("button.fdismiss")).some((b) => /clear/i.test(b.textContent || "") && b.offsetHeight > 0) }; }, sel);
await page.goto(cfg.feed);
// (1) the card is on the board from the first build: the held file was written before boot
await page.waitForSelector(sel, { timeout: 60000 }).catch(() => {});
const first = await cardFacts();
// (2) the card modal: a click on the card's body (not a button) opens it after the double-click debounce; it shows the message
// text and the recipient's name as its header, which for a live session carries no struck-through (dead) mark
let modal = null;
if (first) {
  await page.click(sel + " .fask-nbody", { timeout: 5000 }).catch(() => {});
  await page.waitForSelector("#feed-modal .feed-modal-notice", { timeout: 15000 }).catch(() => {});
  modal = await page.evaluate(() => { const m = document.getElementById("feed-modal"); if (!m) return { open: false };
    const agent = document.getElementById("feed-modal-agent"); const nb = m.querySelector(".feed-modal-notice .fask-nbody");
    return { open: getComputedStyle(m).display !== "none", header: agent ? agent.textContent : null, headerDead: agent ? agent.classList.contains("dead") : null,
      headerDecoration: agent ? getComputedStyle(agent).textDecorationLine : null, bodyText: nb ? nb.textContent : null,
      struck: Array.from(m.querySelectorAll(".dead")).filter((e) => e.offsetHeight > 0).map((e) => e.textContent),
      actions: Array.from(m.querySelectorAll(".feed-modal-notice .fask-nactions button")).map((b) => b.textContent),
      follow: (() => { const f = document.getElementById("feed-modal-follow"); return f ? getComputedStyle(f).display : null; })() }; });
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => { const m = document.getElementById("feed-modal"); return !m || getComputedStyle(m).display === "none"; }, null, { timeout: 5000 }).catch(() => {});
}
// (3) Approve: the synchronous latch, then the kernel's answer (no bus in the lab: refused as unreachable), the re-arm, the toast
let approve = null;
if (first) {
  const nadBefore = await page.evaluate(() => (window.__nad || []).length);
  const latched = await page.evaluate((s) => { const c = document.querySelector(s); const b = c && Array.from(c.querySelectorAll(".fask-nactions button")).find((x) => x.textContent === "Approve");
    if (!b) throw new Error("no Approve button"); b.click();
    return { actions: Array.from(c.querySelectorAll(".fask-nactions button")).map((a) => ({ label: a.textContent, disabled: a.disabled })), dialog: !!document.getElementById("quar-dialog") }; }, sel);
  await page.waitForFunction(([i, n]) => (window.__nad || []).filter((m) => m.itemId === i).length > n, [id, nadBefore], { timeout: 40000 }).catch(() => {});
  const done = await page.evaluate((i) => (window.__nad || []).filter((m) => m.itemId === i), id);
  await page.waitForFunction((s) => { const b = document.querySelector(s + " .fask-nactions button"); return b && !b.disabled; }, sel, { timeout: 15000 }).catch(() => {});
  approve = { latched, done, after: await cardFacts(), toasts: await page.evaluate(() => (window.__toasts || []).slice()) };
}
// (4) Deny: the note prompt first, on the document body; Deny without note posts the bare verdict, refused the same way
let deny = null;
if (first) {
  const nadBefore = await page.evaluate(() => (window.__nad || []).length);
  await page.evaluate((s) => { const c = document.querySelector(s); const b = c && Array.from(c.querySelectorAll(".fask-nactions button")).find((x) => x.textContent === "Deny"); if (!b) throw new Error("no Deny button"); b.click(); }, sel);
  await page.waitForSelector("#quar-dialog", { timeout: 5000 }).catch(() => {});
  const prompt = await page.evaluate((s) => { const d = document.getElementById("quar-dialog"); if (!d) return null;
    const c = document.querySelector(s);
    return { onBody: d.parentElement === document.body, title: (d.querySelector(".pickdlg-title") || {}).textContent || "", buttons: Array.from(d.querySelectorAll("button")).map((b) => b.textContent),
      textarea: !!d.querySelector("textarea"), denyLatched: (Array.from(c.querySelectorAll(".fask-nactions button")).find((x) => /^Deny/.test(x.textContent)) || {}).disabled }; }, sel);
  // the backdrop first: no decision
  await page.mouse.click(4, 4);
  await page.waitForTimeout(200);
  const afterBackdrop = await page.evaluate((s) => ({ dialog: !!document.getElementById("quar-dialog"), nad: (window.__nad || []).length,
    denyLatched: (Array.from(document.querySelector(s).querySelectorAll(".fask-nactions button")).find((x) => /^Deny/.test(x.textContent)) || {}).disabled }), sel);
  await page.evaluate((s) => { const c = document.querySelector(s); Array.from(c.querySelectorAll(".fask-nactions button")).find((x) => x.textContent === "Deny").click(); }, sel);
  await page.waitForSelector("#quar-dialog", { timeout: 5000 }).catch(() => {});
  await page.evaluate(() => { const d = document.getElementById("quar-dialog"); const b = Array.from(d.querySelectorAll("button")).find((x) => x.textContent === "Deny without note"); b.click(); });
  await page.waitForFunction(([i, n]) => (window.__nad || []).filter((m) => m.itemId === i).length > n - 0 && (window.__nad || []).length > n, [id, nadBefore], { timeout: 40000 }).catch(() => {});
  const done = await page.evaluate((n) => (window.__nad || []).slice(n), nadBefore);
  await page.waitForFunction((s) => Array.from(document.querySelector(s).querySelectorAll(".fask-nactions button")).every((b) => !b.disabled), sel, { timeout: 15000 }).catch(() => {});
  deny = { prompt, afterBackdrop, done, after: await cardFacts(), dialogGone: !(await page.$("#quar-dialog")) };
}
// (5) Clear takes the card off the board; the held file is the bus's to decide, so it stays (read by the test on disk)
let cleared = null;
if (first) {
  const clicked = await page.evaluate((s) => { const c = document.querySelector(s); const b = Array.from(c.querySelectorAll("button.fdismiss")).find((x) => x.textContent === "Clear" && x.offsetHeight > 0);
    if (!b) return false; b.click(); return true; }, sel);   // the card's Clear by its label: the action buttons share the chrome class
  await page.waitForSelector(sel, { state: "detached", timeout: 15000 }).catch(() => {});
  cleared = { clicked, gone: !(await page.$(sel)) };
}
const frames = await page.evaluate(() => window.__frames || 0);
process.stdout.write("RESULT:" + JSON.stringify({ first, modal, approve, deny, cleared, frames, errors }) + "\n");
await browser.close();
"""


class HeldMailServed(unittest.TestCase):
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
        cls.lab = tempfile.mkdtemp(prefix="held-mail-")
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
        # the recipient reads LIVE (its record says so; the lab has no SDK, so nothing is spawned): the modal's header must not
        # strike its name through
        Path(cls.state, "sdk", SID + ".json").write_text(json.dumps(
            {"sid": SID, "name": "web", "cwd": cwd, "mode": "auto", "effort": "high", "lastSid": SID, "alive": True,
             "model": "claude-fable-5-1", "liveModel": "Fable 5.1"}))
        t0 = int(time.time()) - 3600
        iso = lambda t: time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t))
        recs = [{"type": "user", "uuid": "u1", "parentUuid": None, "timestamp": iso(t0), "sessionId": SID,
                 "message": {"role": "user", "content": "a question about the notes api"}},
                {"type": "assistant", "uuid": "a1", "parentUuid": "u1", "timestamp": iso(t0 + 2), "sessionId": SID,
                 "message": {"role": "assistant", "model": "claude-fable-5-1", "stop_reason": "end_turn",
                             "content": [{"type": "text", "text": "the notes api keeps its shape."}]}}]
        Path(proj, SID + ".jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
        # the held message, as the postal bus writes it (postal_service.py: the quarantine record of a DIRECTED peer's mail),
        # BEFORE the kernel boots: the first build's backfill posts its card
        cls.held = os.path.join(cls.state, "postal", "quarantine", MID + ".json")
        Path(cls.held).write_text(json.dumps(
            {"mid": MID, "to": "web", "toId": SID, "frm": "api", "frmId": "11111111-2222-3333-4444-666666666666", "body": TEXT,
             "kind": "coordinate", "origin": "TESTHOST", "via": "peer", "at": int(time.time()) - 600}))
        cls.port = _free_port()
        cls.token = "testtok-heldmail"
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
            cfg = os.path.join(self.lab, "heldmail.json")
            base = "http://127.0.0.1:%d" % self.port
            with open(cfg, "w") as f:
                json.dump({"feed": base + "/feed?token=" + self.token, "token": self.token, "sid": SID, "mid": MID}, f)
            driver = os.path.join(self.lab, "heldmail.mjs")
            Path(driver).write_text(DRIVER)
            p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=400,
                               env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
            if "browser-launch-failed" in p.stderr:
                self._skip("no playwright browser on this box")
            line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
            if line is None:
                type(self)._fail = "the driver produced no RESULT (stderr: %s; kernel: %s)" % (p.stderr[-2000:], open(self.klog).read()[-1500:])
                self.fail(type(self)._fail)
            type(self)._r = json.loads(line[len("RESULT:"):])
        print("HELDMAIL:", json.dumps(self._r), file=sys.stderr)
        return self._r

    def test_the_held_message_is_a_needs_you_notice_card_under_the_recipient_with_approve_and_deny(self):
        r = self._result()
        self.assertEqual(r["errors"], [], "no page error")
        c = r["first"]
        self.assertIsNotNone(c, "the card is on the board from the first build (kernel log tail: %s)" % open(self.klog).read()[-800:])
        self.assertEqual((c["col"], c["vis"], c["prod"]), ("col-needsInput-list", True, "via postal"))
        self.assertEqual(c["title"], "New message from api")
        self.assertEqual(c["name"], "web", "under the RECIPIENT session")
        self.assertIn("from TESTHOST:api to web, held because peer TESTHOST is DIRECTED", c["bodyText"], "the route line")
        self.assertIn(TEXT, c["bodyText"], "the message text is the body")
        self.assertEqual([(a["label"], a["disabled"]) for a in c["actions"]], [("Approve", False), ("Deny", False)], "two actions of the kind, no Edit")
        self.assertTrue(all(a["vis"] for a in c["actions"]))
        self.assertTrue(c["clearVisible"], "Clear as on every card")

    def test_the_modal_shows_the_message_text_under_the_recipients_name_unstruck_for_a_live_session(self):
        r = self._result()
        m = r["modal"]
        self.assertIsNotNone(m); self.assertTrue(m["open"], "the card modal opened on the body click")
        self.assertIn(TEXT, m["bodyText"] or "", "the modal's body is the message text")
        self.assertEqual(m["header"], "web", "the recipient's name heads the modal")
        self.assertTrue(r["first"]["live"], "the recipient's record says live: the card reads live")
        self.assertFalse(m["headerDead"], "…so the header is not struck through as a dead session's (the older card's fault)")
        self.assertEqual(m["struck"], [], "nothing in the modal is struck through")
        self.assertEqual(m["actions"], ["Approve", "Deny"], "the modal carries the same two actions")
        self.assertEqual(m["follow"], "none", "no session gesture on a notice card's modal")

    def test_approve_reaches_the_kernel_and_the_bus_unreachable_refusal_re_arms_the_button_with_the_reason_toasted(self):
        r = self._result()
        a = r["approve"]
        self.assertIsNotNone(a)
        self.assertEqual(a["latched"]["actions"], [{"label": "Approve…", "disabled": True}, {"label": "Deny", "disabled": True}], "both latch on the click; the one clicked says what it is doing")
        self.assertFalse(a["latched"]["dialog"], "an approve asks nothing")
        self.assertEqual(len(a["done"]), 1, "the kernel answered the gesture by the card's id: %r" % a["done"])
        self.assertFalse(a["done"][0]["ok"]); self.assertIn("postal bus unreachable", a["done"][0]["error"], "no bus in the lab: the act road's own refusal")
        self.assertEqual([(x["label"], x["disabled"]) for x in a["after"]["actions"]], [("Approve", False), ("Deny", False)], "re-armed on the kernel's answer")
        self.assertTrue(any("refused" in t and "postal bus unreachable" in t for t in a["toasts"]), "the reason rode the toast: %r" % a["toasts"])
        self.assertEqual(a["after"]["col"], "col-needsInput-list", "a refused decision leaves the card (the message is still held)")

    def test_deny_asks_for_the_optional_note_first_and_the_bare_deny_posts_the_verdict(self):
        r = self._result()
        d = r["deny"]
        self.assertIsNotNone(d); p = d["prompt"]
        self.assertIsNotNone(p, "the note prompt opened")
        self.assertTrue(p["onBody"], "on the document body, outside the re-rendered feed root")
        self.assertEqual(p["buttons"], ["Deny & send note", "Deny without note"], "two choices, no Cancel")
        self.assertTrue(p["textarea"]); self.assertIn("note", p["title"].lower())
        self.assertFalse(p["denyLatched"], "Deny latches on the decision, not on the prompt")
        self.assertEqual((d["afterBackdrop"]["dialog"], d["afterBackdrop"]["denyLatched"]), (False, False), "the backdrop closed the prompt with no decision")
        self.assertEqual(len(d["done"]), 1, "one answer for the bare deny: %r" % d["done"])
        self.assertFalse(d["done"][0]["ok"]); self.assertIn("postal bus unreachable", d["done"][0]["error"])
        self.assertTrue(d["dialogGone"]); self.assertEqual([x["disabled"] for x in d["after"]["actions"]], [False, False], "re-armed")

    def test_clear_dismisses_the_card_and_leaves_the_held_file_to_the_bus(self):
        r = self._result()
        self.assertTrue(r["cleared"]["clicked"], "the card's Clear button was found"); self.assertTrue(r["cleared"]["gone"], "Clear took the card off the board")
        self.assertTrue(os.path.exists(self.held), "the held file stays: a dismissal is not a decision")


if __name__ == "__main__":
    unittest.main()
