#!/usr/bin/env python3
"""T373 fold (the verifier of the rescind, 2026-09-12): the queued message's ✎ gives back exactly what went out. Two served
roads on a session mid-turn (the transcript ends inside a tool call, so a send parks): (1) a message composed with a quote
citation and two attachments, an image and a document, is sent, parks as a queued bubble, and the ✎ puts its words back
into the composer with the quote chip and the two attachment chips; (2) a message with an attachment is sent, the ✎ is
pressed, and the kernel's refusal (a cancelResult with ok false, injected in the kernel's own frame shape after the page's
cancel frame is dropped at the socket) puts the composer back as it was: no words, no chips. Red before this fold on the
first road (the record kept the images alone, so a document's path stayed in the text and no chips came back) and on the
second (the chips stayed armed on a refusal). SYNTHETIC fixtures only; skips loudly without the extension deps or a browser.
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
from datetime import datetime, timezone
from pathlib import Path

from tests.dist_copy import copy_dist

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
EXT = os.path.join(ROOT, "vscode-extension")
sys.path.insert(0, HERE)
import test_ship_reship as _lab   # noqa: E402  the lab kernel's environment (the module, not its classes: an
#                                   imported TestCase would be collected here a second time)

SID = "aaaaaaaa-1111-2222-3333-444444444444"
TEXT = "and also update the docstring"
TEXT2 = "then run the formatter"
SECONDS = float(os.environ.get("T262H_SECONDS", "60"))


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
const page = await browser.newPage({ viewport: { width: 1000, height: 700 } });
// the frames the page sends, and a switch that DROPS the cancel frame so a refusal can be staged in the kernel's shape
await page.addInitScript(() => {
  const send = WebSocket.prototype.send;
  window.__sent = []; window.__dropCancel = true;
  WebSocket.prototype.send = function (d) {
    try { const m = JSON.parse(d); if (m && m.type) { window.__sent.push(m); if (window.__dropCancel && m.type === "cancelQueued") return; } } catch (e) { /* not a frame */ }
    return send.call(this, d);
  };
});
await page.goto(cfg.chat);
await page.waitForSelector("#tabs .tab, #tabs [data-sid]", { timeout: 20000 });
await page.waitForSelector("#composer-input", { timeout: 20000 });
await page.waitForTimeout(600);
const composer = () => page.evaluate(() => ({
  text: document.getElementById("composer-input").value,
  chips: Array.from(document.querySelectorAll("#composer-chips .composer-chip-label")).map((n) => n.textContent),
  files: (document.getElementById("composer-files") ? Array.from(document.getElementById("composer-files").children).map((n) => n.textContent || n.getAttribute("title") || n.className) : []),
  bubbles: Array.from(document.querySelectorAll(".turn-queued:not(.turn-queued-hidden) .queued-bubble")).map((b) => (b.textContent || "").trim().slice(0, 120)),
  pencils: document.querySelectorAll(".turn-queued:not(.turn-queued-hidden) .queued-edit").length,
  crosses: document.querySelectorAll(".turn-queued:not(.turn-queued-hidden) .queued-x").length,
}));
const sentOf = (type) => page.evaluate((t) => window.__sent.filter((m) => m.type === t), type);
const clearBox = async () => {
  await page.evaluate(() => { const ta = document.getElementById("composer-input"); ta.value = ""; ta.dispatchEvent(new Event("input", { bubbles: true })); });
  // one control at a time, re-queried: each removal re-renders its strip, so the buttons gathered before it are detached
  await page.evaluate(() => { for (let i = 0; i < 16; i++) { const b = document.querySelector("#composer-chips .composer-chip-x, #composer-files button"); if (!b) break; b.click(); } });
  await page.waitForTimeout(300);
  return composer();
};
const bubbleWith = (t) => page.waitForFunction((x) => Array.from(document.querySelectorAll(".turn-queued:not(.turn-queued-hidden) .queued-bubble")).some((b) => (b.textContent || "").includes(x)), t, { timeout: 20000 });
const pressPencilOf = (t) => page.evaluate((x) => { const eds = Array.from(document.querySelectorAll(".turn-queued:not(.turn-queued-hidden) .queued-edit")); const ed = eds.find((e) => (e.closest(".queued-bubble").textContent || "").includes(x)); if (!ed) return null; const md = ed._qmd; ed.click(); return md; }, t);
// ROAD A (the refusal, on the fresh page): one attachment rides the send; the pencil pulls the message back and the user adds a
// file meanwhile; the kernel's refusal, staged in its own shape with the page's own cancel frame's id and body (the cancel
// itself dropped at the socket), takes back exactly what the pencil armed and leaves the user's addition
await page.evaluate((s) => window.postMessage({ romp: "adopt", sid: s.sid, state: { draft: "", citations: [], files: [s.pdf], staged: [] } }, "*"), cfg);
await page.waitForTimeout(300);
const seededA = await composer();
await page.fill("#composer-input", cfg.text2);
await page.press("#composer-input", "Enter");
await bubbleWith(cfg.text2); await page.waitForTimeout(400);
const parkedA = await composer();
const mdA = await pressPencilOf(cfg.text2);
await page.waitForTimeout(500);
const armedA = await composer();
await page.evaluate((s) => window.postMessage({ romp: "adopt", sid: s.sid, state: { draft: "", citations: [], files: [s.extra], staged: [] } }, "*"), cfg);
await page.waitForTimeout(300);
const addedA = await composer();
const lastCancel = await page.evaluate(() => { const c = window.__sent.filter((m) => m.type === "cancelQueued"); const l = c[c.length - 1]; return l ? { id: l.id, md: l.md } : null; });
await page.evaluate((f) => window.postMessage(f, "*"), { type: "cancelResult", ok: false, id: lastCancel ? lastCancel.id : cfg.sid, md: lastCancel ? lastCancel.md : mdA, text: "too late to cancel: the session already took this message" });
await page.waitForTimeout(600);
const afterA = await composer();
const missRows = await page.evaluate(() => window.__sent.filter((m) => m.type === "clientDiag" && m.what === "cancel-miss").map((m) => m.data));
const toast = await page.evaluate(() => Array.from(document.querySelectorAll(".warn-toast")).map((n) => (n.textContent || "").slice(0, 80)));
const clearedA = await clearBox();
// ROAD B: a quote citation and two attachments (an image and a document) ride the send; the pencil gives them all back
await page.evaluate((s) => window.postMessage({ romp: "adopt", sid: s.sid, state: { draft: "", citations: [{ title: "the retry curve", quote: "the retry curve" }], files: [s.png, s.pdf], staged: [] } }, "*"), cfg);
await page.waitForTimeout(300);
const seeded = await composer();
await page.fill("#composer-input", cfg.text1);
await page.press("#composer-input", "Enter");
await bubbleWith(cfg.text1); await page.waitForTimeout(400);
const queued1 = await composer();
const sent1 = (await sentOf("sendMessage")).filter((m) => (m.text || "").includes(cfg.text1));
const cancelsBefore1 = (await sentOf("cancelQueued")).length;
await pressPencilOf(cfg.text1);
await page.waitForTimeout(600);
const back1 = await composer();
const cancels1 = (await sentOf("cancelQueued")).length - cancelsBefore1;
const clearedB = await clearBox();
// ROAD C (round two's medium): a follow-up sent from a goal chip with an attachment parks; the page RELOADS, so the page's own
// record of the send is gone and the pencil has only the kernel's copy; the words, the goal chip and the attachment chip come back
await page.evaluate((s) => window.postMessage({ romp: "adopt", sid: s.sid, state: { draft: "", citations: [{ itemId: s.goalId, title: s.goalTitle }], files: [s.pdf], staged: [] } }, "*"), cfg);
await page.waitForTimeout(300);
const seededC = await composer();
await page.fill("#composer-input", cfg.text3);
await page.press("#composer-input", "Enter");
await bubbleWith(cfg.text3); await page.waitForTimeout(400);
const sentC = (await sentOf("askFollowUp")).map((m) => ({ itemId: m.itemId, text: m.text, paths: m.paths }));
await page.reload({ waitUntil: "load" });
await page.waitForSelector("#composer-input", { timeout: 20000 });
await bubbleWith(cfg.text3); await page.waitForTimeout(600);
const reloadedC = await composer();
const mdC = await pressPencilOf(cfg.text3);
await page.waitForTimeout(600);
const backC = await composer();
fs.writeSync(1, "RESULT:" + JSON.stringify({ seededA, parkedA, mdA, armedA, addedA, afterA, missRows, toast, clearedA, seeded, queued1, sent1: sent1.map((m) => ({ text: m.text, paths: m.paths })), back1, cancels1, clearedB, seededC, sentC, reloadedC, mdC, backC }) + "\n");
await browser.close();
process.exit(0);
"""


class QueuedLab(unittest.TestCase):
    """The boot: a hermetic kernel over a synthetic transcript that ends inside a running tool call, so every send the
    kernel receives waits behind the turn, and the real /chat page served from a copy of the built bundle. Subclassed by
    this module's tests and by the provisional-rows lab (T389, tests/test_provisional_rows_browser.py); no tests of its own."""
    maxDiff = None
    EXT = EXT

    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(os.path.join(EXT, "node_modules", "playwright")):
            raise unittest.SkipTest("extension deps absent (npm ci not run here) — the served guard needs them")
        cls.lab = tempfile.mkdtemp(prefix="queued-rescind-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            raise unittest.SkipTest("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
        dist = os.path.join(cls.lab, "dist")
        copy_dist(os.path.join(EXT, "dist"), dist)
        cls.state = os.path.join(cls.lab, "xdg", "romp")
        cwd = os.path.join(cls.lab, "proj")
        for d in ("names", "sdk", "states"):
            os.makedirs(os.path.join(cls.state, d), exist_ok=True)
        Path(cls.state, "session-hosts").write_text("off")     # a state root of our own: no real host for the session (the Testing rule)
        os.makedirs(cwd, exist_ok=True)
        Path(cls.state, "names", SID).write_text("web\t%s\t\t\n" % cwd)
        Path(cls.state, "sdk", SID + ".json").write_text(json.dumps(
            {"sid": SID, "name": "web", "cwd": cwd, "mode": "auto", "effort": "high",
             "lastSid": SID, "alive": True, "model": "claude-fable-5-1", "liveModel": "Fable 5.1"}))
        Path(cls.state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 10}, "seven_day": {"pct": 10}}))
        claude = os.path.join(cls.lab, "claude")
        # the kernel finds a session's transcript under Claude's project dir: EVERY non-alphanumeric char of the
        # realpath becomes '-' (jd._proj_dir). A slashes-only munge missed the '_' pytest's temp root can carry,
        # so the kernel found no transcript and drew an API-error turn instead (the batch-only flake, 2026-09-08).
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
        # a running turn: the reply is tall enough to overflow the pane, then a tool call whose result is in
        t0 = int(time.time()) - 900
        cls.t0 = t0
        recs = [
            {"type": "user", "timestamp": iso(t0), "uuid": "u1", "parentUuid": None, "promptSource": "sdk", "sessionId": SID,
             "message": {"role": "user", "content": "tighten the notes-api search"}},
            {"type": "assistant", "timestamp": iso(t0 + 10), "uuid": "a1", "parentUuid": "u1", "sessionId": SID,
             "message": {"role": "assistant", "model": "claude-fable-5-1", "stop_reason": "end_turn",
                         "content": [{"type": "text", "text": "\n\n".join("Paragraph %d of the reply." % i for i in range(14))}]}},
            {"type": "user", "timestamp": iso(t0 + 39), "uuid": "u2", "parentUuid": "a1", "promptSource": "sdk", "sessionId": SID,
             "message": {"role": "user", "content": "drop the unused import"}},
            {"type": "assistant", "timestamp": iso(t0 + 41), "uuid": "a2", "parentUuid": "u2", "sessionId": SID,
             "message": {"role": "assistant", "model": "claude-fable-5-1", "stop_reason": "tool_use",
                         "content": [{"type": "tool_use", "id": "tu_a2_0", "name": "Bash", "input": {"command": "uv run pytest -q"}}]}},
            {"type": "user", "timestamp": iso(t0 + 50), "uuid": "tr1", "parentUuid": "a2", "sessionId": SID,
             "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tu_a2_0", "content": "3 passed"}]}},
        ]
        cls.transcript = os.path.join(proj, SID + ".jsonl")
        Path(cls.transcript).write_text("".join(json.dumps(r) + "\n" for r in recs))
        # the steps the session runs while the send waits, and the splice the CLI writes when it takes it
        cls.steps = [
            {"type": "assistant", "timestamp": iso(t0 + 120), "uuid": "a3", "parentUuid": "tr1", "sessionId": SID,
             "message": {"role": "assistant", "model": "claude-fable-5-1", "stop_reason": "tool_use",
                         "content": [{"type": "tool_use", "id": "tu_a3_0", "name": "Bash", "input": {"command": "uv run pytest -q tests/test_search.py"}}]}},
            {"type": "user", "timestamp": iso(t0 + 121), "uuid": "tr2", "parentUuid": "a3", "sessionId": SID,
             "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tu_a3_0", "content": "5 passed"}]}},
            {"type": "assistant", "timestamp": iso(t0 + 122), "uuid": "a4", "parentUuid": "tr2", "sessionId": SID,
             "message": {"role": "assistant", "model": "claude-fable-5-1", "stop_reason": "tool_use",
                         "content": [{"type": "tool_use", "id": "tu_a4_0", "name": "Bash", "input": {"command": "git diff --stat"}}]}},
            {"type": "user", "timestamp": iso(t0 + 125), "uuid": "tr3", "parentUuid": "a4", "sessionId": SID,
             "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tu_a4_0", "content": "1 file changed"}]}},
        ]
        # sent at t0+55, taken at the t0+125 boundary (tr3, its file-order predecessor): 70 s later, so the landed
        # bubble's hover names the send time
        cls.landing = {"type": "attachment", "timestamp": iso(t0 + 55), "uuid": "att1", "parentUuid": "tr3", "isSidechain": False,
                       "sessionId": SID, "attachment": {"type": "queued_command", "prompt": TEXT}}
        cls.port = _free_port()
        cls.token = "testtok-rescind"
        env = _lab.kernel_env(cls.lab, claude, dist, cls.port, cls.token)
        cls.klog = os.path.join(cls.lab, "kernel.log")
        cls.kernel = subprocess.Popen([os.path.join(BIN, "romp-kernel")],
                                      stdout=open(cls.klog, "w"), stderr=subprocess.STDOUT, env=env)
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

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "kernel", None):
            cls.kernel.kill()
            cls.kernel.wait()
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)


class ServedQueuedRescind(QueuedLab):
    _r = None
    TEXT1, TEXT2, TEXT3 = "plot it again with the new bound", "and the report needs the new table", "and attach the report to that goal"

    def _paths(self):
        return os.path.join(self.lab, "proj", "plots", "retry.png"), os.path.join(self.lab, "proj", "docs", "report.pdf")

    def _extra(self):
        return os.path.join(self.lab, "proj", "notes", "todo.txt")

    def _result(self):
        """One driver run per class (both roads ride one page); each test reads its own road's measurements, so a
        head that fails one medium still reports the other."""
        cls = type(self)
        if cls._r is not None:
            return cls._r
        png, pdf = self._paths(); extra = self._extra()
        text1, text2, text3 = self.TEXT1, self.TEXT2, self.TEXT3
        os.makedirs(os.path.dirname(extra), exist_ok=True); Path(extra).write_text("- add the table\n")
        cfg = os.path.join(self.lab, "cfg.json")
        os.makedirs(os.path.dirname(png), exist_ok=True); os.makedirs(os.path.dirname(pdf), exist_ok=True)
        Path(png).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16); Path(pdf).write_bytes(b"%PDF-1.4\n%%EOF\n")
        with open(cfg, "w") as f:
            json.dump({"chat": "http://127.0.0.1:%d/chat?token=%s" % (self.port, self.token), "sid": SID, "png": png, "pdf": pdf, "extra": extra, "text1": text1, "text2": text2, "text3": text3,
                       "goalId": SID + ":g1", "goalTitle": "tighten the notes-api search"}, f)
        driver = os.path.join(self.lab, "driver.mjs")
        with open(driver, "w") as f:
            f.write(DRIVER)
        p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=300,
                           env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
        if p.returncode == 3:
            raise unittest.SkipTest("no playwright browser on this box — the served guard needs one (CI installs none)")
        self.assertEqual(p.returncode, 0, "driver failed:\n" + p.stdout[-3000:] + p.stderr[-3000:] + "\nkernel:\n" + open(self.klog).read()[-1500:])
        line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
        self.assertIsNotNone(line, "driver printed no result:\n" + p.stdout[-3000:])
        r = json.loads(line[len("RESULT:"):])
        print("RESULT:" + json.dumps(r), file=sys.stderr)
        cls._r = r
        return r

    def test_the_pencil_gives_back_the_words_the_quote_chip_and_both_attachment_chips(self):
        r = self._result(); png, pdf = self._paths(); text1 = self.TEXT1
        self.assertEqual((r["clearedA"]["text"], r["clearedA"]["chips"], r["clearedA"]["files"]), ("", [], []), "the box was cleared before this road: %r" % r["clearedA"])
        # the seed took: a quote chip and two attachment chips before the send
        self.assertEqual(r["seeded"]["chips"], ["the retry curve"]); self.assertEqual(len(r["seeded"]["files"]), 2, "two attachments seeded: %r" % r["seeded"])
        # the send carried the quote body, the trailing line of BOTH paths, and the attachment list on the frame
        self.assertEqual(len(r["sent1"]), 1, "one send with these words: %r" % r["sent1"])
        self.assertTrue(r["sent1"][0]["text"].startswith("Replying to this part of the conversation:"), "the quote rode ahead of the words: %r" % r["sent1"][0]["text"])
        self.assertTrue(r["sent1"][0]["text"].rstrip().endswith(png + " " + pdf), "the trailing line names both attachments: %r" % r["sent1"][0]["text"])
        self.assertEqual(r["sent1"][0].get("paths"), [png, pdf], "the frame carries the attachment list (medium 1)")
        self.assertEqual(r["queued1"]["text"], "", "the box emptied on send"); self.assertEqual(r["queued1"]["chips"], []); self.assertEqual(r["queued1"]["files"], [])
        self.assertGreaterEqual(r["queued1"]["pencils"], 1, "the parked message wears the pencil: %r" % r["queued1"]); self.assertEqual(r["queued1"]["crosses"], 0, "no cross on a message")
        # the pencil: the words alone in the box, the quote chip and the two attachment chips back, one cancel posted
        self.assertEqual(r["back1"]["text"], text1, "the typed words, without the quote section or the paths line: %r" % r["back1"])
        self.assertEqual(r["back1"]["chips"], ["the retry curve"], "the quote chip is back: %r" % r["back1"])
        self.assertEqual(len(r["back1"]["files"]), 2, "the image AND the document are chips again (medium 1): %r" % r["back1"])
        self.assertEqual(r["cancels1"], 1, "the rescind is the cancel: one frame")

    def test_a_refused_rescind_takes_back_only_what_the_pencil_armed_and_keeps_what_the_user_added_since(self):
        r = self._result(); text2 = self.TEXT2
        self.assertEqual(len(r["seededA"]["files"]), 1, "one attachment seeded: %r" % r["seededA"])
        self.assertEqual((r["parkedA"]["text"], r["parkedA"]["files"]), ("", []), "the box emptied on send: %r" % r["parkedA"])
        self.assertEqual(r["armedA"]["text"], text2, "the pencil armed the words: %r" % r["armedA"]); self.assertEqual(len(r["armedA"]["files"]), 1, "…and the attachment chip: %r" % r["armedA"])
        self.assertEqual(len(r["addedA"]["files"]), 2, "the user added a file after the pencil: %r" % r["addedA"])
        # the refusal: the words and the armed chip go; the file added since stays (round two, low 1)
        self.assertEqual((r["afterA"]["text"], r["afterA"]["chips"]), ("", []), "the refusal put the words back and took the armed chips: %r" % r["afterA"])
        self.assertEqual(len(r["afterA"]["files"]), 1, "exactly the user's own addition stays: %r" % r["afterA"]); self.assertIn("todo.txt", r["afterA"]["files"][0])
        self.assertEqual(len(r["missRows"]), 1, "the refusal reached the handler once: %r" % r["missRows"]); self.assertTrue(r["missRows"][0]["hadRestore"], "…and found the stash it stored (the NUL-byte key, fixed): %r" % r["missRows"])
        self.assertTrue(any("too late" in x for x in r["toast"]), "the refusal toasts: %r" % r["toast"])

    def test_a_follow_up_with_an_attachment_rescinds_after_a_reload_with_its_goal_chip_and_its_attachment_chip(self):
        # round two's medium: with the page's own record gone (a reload; another window is the same), the pencil has only the
        # kernel's copy, so the copy must carry the follow-up's attachment list exactly as a plain send's does
        r = self._result(); png, pdf = self._paths(); text3 = self.TEXT3
        self.assertEqual((r["clearedB"]["text"], r["clearedB"]["chips"], r["clearedB"]["files"]), ("", [], []), "the box was cleared before this road: %r" % r["clearedB"])
        self.assertEqual(r["seededC"]["chips"], ["tighten the notes-api search"], "the goal chip seeded: %r" % r["seededC"]); self.assertEqual(len(r["seededC"]["files"]), 1)
        self.assertEqual(len(r["sentC"]), 1, "one follow-up frame: %r" % r["sentC"])
        self.assertEqual(r["sentC"][0]["itemId"], SID + ":g1"); self.assertEqual(r["sentC"][0]["paths"], [pdf], "the follow-up frame carries the list")
        self.assertTrue(r["sentC"][0]["text"].rstrip().endswith(pdf), "…and the trailing line names it: %r" % r["sentC"][0]["text"])
        self.assertEqual((r["reloadedC"]["text"], r["reloadedC"]["files"]), ("", []), "after the reload the box is empty and the bubble is the kernel's: %r" % r["reloadedC"])
        self.assertEqual(r["backC"]["text"], text3, "the typed words alone, no raw paths line: %r" % r["backC"])
        self.assertEqual(len(r["backC"]["chips"]), 1, "the goal chip is back: %r" % r["backC"])
        self.assertEqual(len(r["backC"]["files"]), 1, "the attachment chip is back from the kernel's copy (the medium): %r" % r["backC"]); self.assertIn("report.pdf", r["backC"]["files"][0])

if __name__ == "__main__":
    unittest.main()
