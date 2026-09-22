#!/usr/bin/env python3
"""A composer send must show its bubble, and keep showing it, until its landing replaces it (the user 2026-09-22:
pressing Enter often produced no bubble in the transcript on the deployed build; a reload brought the message back).

The lab drives the real /chat page against a hermetic kernel whose one session is MID-TURN (the transcript ends inside
a tool call), so a real send reaches the kernel and is queued there, and measures after every checkpoint whether the
SENT TEXT is on the page in a visible element. Variants, each looped: a plain send; a rapid double send; a send while
scrolled up; a send right after the socket dropped and the page redialled with the skeleton diet; a send pressed DURING
the redial; and a reload after a send. The kernel's copy, the page's own bubble and the landed atom are all acceptable
carriers of the text; what is not acceptable is a checkpoint at which no visible element carries it. SYNTHETIC fixtures
only; skips loudly without the extension deps or a Playwright browser.
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
import test_ship_reship_served as _lab   # noqa: E402  the lab kernel's environment (the module, not its classes)

SID = "aaaaaaaa-1111-2222-3333-444444444444"
ROUNDS = int(os.environ.get("SEND_BUBBLE_ROUNDS", "6"))


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
const page = await browser.newPage({ viewport: { width: 1000, height: 600 } });
page.on("console", (m) => { if (m.type() === "error") fs.appendFileSync(cfg.consoleLog, m.text() + "\n"); });
page.on("pageerror", (e) => fs.appendFileSync(cfg.consoleLog, "pageerror: " + e + "\n"));
const armPage = async () => {
  await page.goto(cfg.chat);
  await page.waitForSelector("#tabs .tab, #tabs [data-sid]", { timeout: 20000 });
  await page.waitForSelector(".turn.turn-user", { timeout: 20000 });
  await page.waitForTimeout(600);
  await page.evaluate(() => {
    window.__frames = 0; window.__sockets = []; window.__sent = [];
    window.addEventListener("message", (e) => { const m = e.data; if (m && (m.type === "session" || m.type === "update" || m.type === "chatTail")) window.__frames++; });
    const origSend = WebSocket.prototype.send;
    WebSocket.prototype.send = function (d) {
      try { const m = JSON.parse(d); if (m && m.type === "sendMessage") window.__sent.push({ text: m.text, qid: m.qid, t: Date.now() }); } catch (e) {}
      if (!window.__sockets.includes(this)) window.__sockets.push(this);
      return origSend.call(this, d);
    };
  });
};
await armPage();
const painted = () => page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 0)))));
// the measure: is the text on the page in a visible element? (our bubble, the kernel's copy, or the landed atom)
const measure = (text) => page.evaluate((t) => {
  const content = document.getElementById("content");
  const turns = Array.from(document.querySelectorAll("#content .turn"));
  const carriers = turns.filter((el) => (el.textContent || "").includes(t));
  const visible = carriers.filter((el) => el.getClientRects().length > 0 && getComputedStyle(el).display !== "none" && getComputedStyle(el).visibility !== "hidden");
  const tail = turns.slice(-4).map((el) => el.className);
  return { visible: visible.length, carriers: carriers.map((el) => el.className), tail, frames: window.__frames,
           sh: content ? content.scrollHeight : 0, st: content ? content.scrollTop : 0, ch: content ? content.clientHeight : 0,
           skeleton: !!document.querySelector(".tab.skeleton, [data-skeleton]"), composer: (document.getElementById("composer-input") || {}).value || "" };
}, text);
const waitFrames = async (n, ms) => { const b = await page.evaluate(() => window.__frames); try { await page.waitForFunction((b, n) => window.__frames >= b + n, b, n, { timeout: ms }); } catch (e) {} };
const send = async (text) => { await page.fill("#composer-input", text); await page.press("#composer-input", "Enter"); };
let stepN = 0; let parent = cfg.parent; const t0 = cfg.t0;
const iso = (x) => new Date(x * 1000).toISOString().replace(/\.\d{3}Z$/, ".000Z");
const step = () => {
  const i = stepN++;
  const t = t0 + 200 + i;
  let r;
  if (i % 2 === 0) { r = { type: "assistant", timestamp: iso(t), uuid: "s" + i, parentUuid: parent, sessionId: cfg.sid,
      message: { role: "assistant", model: "claude-fable-5-1", stop_reason: "tool_use", content: [{ type: "tool_use", id: "tu_s" + i, name: "Bash", input: { command: "true # step " + i } }] } }; }
  else { r = { type: "user", timestamp: iso(t), uuid: "s" + i, parentUuid: parent, sessionId: cfg.sid,
      message: { role: "user", content: [{ type: "tool_result", tool_use_id: "tu_s" + (i - 1), content: "ok" }] } }; }
  parent = "s" + i;
  fs.appendFileSync(cfg.transcript, JSON.stringify(r) + "\n");
};
const checks = [];   // every checkpoint: { variant, round, at, ...measure }
const check = async (variant, round, at, text) => { await painted(); const m = await measure(text); checks.push({ variant, round, at, text, ...m }); return m; };
const settle = async (variant, round, text, pushes) => {
  for (let k = 0; k < pushes; k++) { const b = await page.evaluate(() => window.__frames); step(); try { await page.waitForFunction((b) => window.__frames > b, b, { timeout: 4000 }); } catch (e) {} await check(variant, round, "push" + k, text); }
};
let n = 0;
const fresh = (tag) => `please ${tag} the notes-api search index, round ${++n}`;
// A. plain send into the mid-turn session
for (let r = 0; r < cfg.rounds; r++) {
  const text = fresh("rebuild");
  await send(text);
  await check("plain", r, "press", text);
  await page.waitForTimeout(300); await check("plain", r, "300ms", text);
  await waitFrames(1, 3000); await check("plain", r, "frame", text);
  await settle("plain", r, text, 3);
}
// B. rapid double send
for (let r = 0; r < cfg.rounds; r++) {
  const a = fresh("tighten"), b = fresh("document");
  await page.fill("#composer-input", a); await page.press("#composer-input", "Enter");
  await page.fill("#composer-input", b); await page.press("#composer-input", "Enter");
  await check("double-a", r, "press", a); await check("double-b", r, "press", b);
  await waitFrames(1, 3000); await check("double-a", r, "frame", a); await check("double-b", r, "frame", b);
  await settle("double-b", r, b, 2);
}
// C. send while scrolled up
for (let r = 0; r < cfg.rounds; r++) {
  const text = fresh("profile");
  await page.evaluate(() => { const c = document.getElementById("content"); c.scrollTop = Math.max(0, c.scrollHeight - c.clientHeight - 900); });
  await page.waitForTimeout(200);
  await send(text);
  await check("scrolled-up", r, "press", text);
  await waitFrames(1, 3000); await check("scrolled-up", r, "frame", text);
  await page.evaluate(() => { const c = document.getElementById("content"); c.scrollTop = c.scrollHeight; });
  await settle("scrolled-up", r, text, 2);
}
// D. a redial: close every socket the page holds; the shim redials with the skeleton diet; send once the frame lands
for (let r = 0; r < cfg.rounds; r++) {
  const text = fresh("index");
  const before = await page.evaluate(() => window.__frames);
  await page.evaluate(() => { for (const ws of window.__sockets) { try { ws.close(); } catch (e) {} } });
  try { await page.waitForFunction((b) => window.__frames > b, before, { timeout: 8000 }); } catch (e) {}
  await page.waitForTimeout(400);
  await send(text);
  await check("after-redial", r, "press", text);
  await waitFrames(1, 3000); await check("after-redial", r, "frame", text);
  await settle("after-redial", r, text, 2);
}
// E. a send pressed DURING the redial (the socket just closed, no frame yet)
for (let r = 0; r < cfg.rounds; r++) {
  const text = fresh("compact");
  await page.evaluate(() => { for (const ws of window.__sockets) { try { ws.close(); } catch (e) {} } });
  await send(text);
  await check("mid-redial", r, "press", text);
  await waitFrames(1, 8000); await check("mid-redial", r, "frame", text);
  await page.waitForTimeout(800); await check("mid-redial", r, "later", text);
  await settle("mid-redial", r, text, 2);
}
// F. a reload after a send: the kernel's copy carries the text
{
  const text = fresh("verify");
  await send(text);
  await check("reload", 0, "press", text);
  await waitFrames(1, 3000);
  await armPage();
  await check("reload", 0, "reloaded", text);
}
const sent = await page.evaluate(() => window.__sent.length);
fs.writeSync(1, "RESULT:" + JSON.stringify({ checks, sent }) + "\n");
await browser.close();
process.exit(0);
"""


class ServedSendBubbleVisible(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(os.path.join(EXT, "node_modules", "playwright")):
            raise unittest.SkipTest("extension deps absent (npm ci not run here) — the served guard needs them")
        cls.lab = tempfile.mkdtemp(prefix="send-bubble-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            raise unittest.SkipTest("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
        dist = os.path.join(cls.lab, "dist")
        copy_dist(os.path.join(EXT, "dist"), dist)
        cls.state = os.path.join(cls.lab, "xdg", "romp")
        cwd = os.path.join(cls.lab, "proj")
        for d in ("names", "sdk", "states"):
            os.makedirs(os.path.join(cls.state, d), exist_ok=True)
        Path(cls.state, "session-hosts").write_text("off\n")   # a test that mints its own state root pins the hosts off (CLAUDE.md)
        os.makedirs(cwd, exist_ok=True)
        Path(cls.state, "names", SID).write_text("web\t%s\t\t\n" % cwd)
        Path(cls.state, "sdk", SID + ".json").write_text(json.dumps(
            {"sid": SID, "name": "web", "cwd": cwd, "mode": "auto", "effort": "high",
             "lastSid": SID, "alive": True, "model": "claude-fable-5-1", "liveModel": "Fable 5.1"}))
        Path(cls.state, "usage.json").write_text(json.dumps({"five_hour": {"pct": 10}, "seven_day": {"pct": 10}}))
        claude = os.path.join(cls.lab, "claude")
        proj = os.path.join(claude, "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd)))
        os.makedirs(proj, exist_ok=True)
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
            {"type": "assistant", "timestamp": iso(t0 + 52), "uuid": "a3", "parentUuid": "tr1", "sessionId": SID,
             "message": {"role": "assistant", "model": "claude-fable-5-1", "stop_reason": "tool_use",
                         "content": [{"type": "tool_use", "id": "tu_a3_0", "name": "Bash", "input": {"command": "uv run pytest -q tests/test_search.py"}}]}},
        ]
        cls.transcript = os.path.join(proj, SID + ".jsonl")
        Path(cls.transcript).write_text("".join(json.dumps(r) + "\n" for r in recs))
        cls.port = _free_port()
        cls.token = "testtok-sendbubble"
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

    def test_the_sent_text_is_visible_at_every_checkpoint(self):
        cfg = os.path.join(self.lab, "cfg.json")
        console_log = os.path.join(self.lab, "console.log")
        Path(console_log).write_text("")
        with open(cfg, "w") as f:
            json.dump({"chat": "http://127.0.0.1:%d/chat?token=%s" % (self.port, self.token),
                       "transcript": self.transcript, "sid": SID, "t0": self.t0, "parent": "a3", "rounds": ROUNDS,
                       "consoleLog": console_log}, f)
        driver = os.path.join(self.lab, "driver.mjs")
        with open(driver, "w") as f:
            f.write(DRIVER)
        p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=900,
                           env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
        if p.returncode == 3:
            raise unittest.SkipTest("no playwright browser on this box — the served guard needs one (CI installs none)")
        self.assertEqual(p.returncode, 0, "driver failed:\n" + p.stdout[-3000:] + p.stderr[-3000:] + "\nkernel:\n" + open(self.klog).read()[-2500:])
        line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
        self.assertIsNotNone(line, "driver printed no result:\n" + p.stdout[-3000:])
        r = json.loads(line[len("RESULT:"):])
        checks = r["checks"]
        misses = [c for c in checks if c["visible"] == 0]
        print("SEND-BUBBLE: %d checkpoints, %d misses, %d sends reached the socket" % (len(checks), len(misses), r["sent"]))
        for c in misses[:40]:
            print("  MISS", json.dumps({k: c[k] for k in ("variant", "round", "at", "carriers", "tail", "sh", "st", "ch", "composer")}))
        console = open(console_log).read()
        self.assertEqual(console.strip(), "", "the page logged errors:\n" + console[-2000:])
        self.assertEqual(misses, [], "every checkpoint after a send shows the sent text in a visible element; misses above")


if __name__ == "__main__":
    unittest.main()
