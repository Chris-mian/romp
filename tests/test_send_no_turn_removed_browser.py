#!/usr/bin/env python3
"""NO SEND MAY TAKE AN ALREADY-LANDED TURN OFF THE PAGE, not even for one painted frame (the user 2026-09-23:
on most sends the previous agent message disappeared and came back — a flash, self-healing, and the transient
cousin of the message that vanished for good on 2026-09-22, PR 2050).

The measure is the PAINT, not the end state. A tail re-render legitimately takes nodes out and puts them back
inside one task, which no eye can see; what the user saw is a turn missing from a frame the browser actually
painted. So the lab samples the landed turns at every requestAnimationFrame — the callback runs immediately
before the paint, so the set it reads is the set that frame shows — and a watched turn that leaves one sample
and returns in a later one is a flash, recorded with both frame numbers. A MutationObserver runs beside it and
records every removal of a watched turn from #content with whether the node was back by the end of the same
task, so a legitimate re-render reads apart from a loss.

Watched: the last landed turns resident at the press (their uuids), which stay inside the tail window, so a
virtualization slide is never mistaken for a loss. Transient keys are not landed turns and are excluded
(optimistic:, held:, echo:, echo-, cmd:).

Variants, each looped: a send into an idle session; a send while the previous turn is still streaming (the
transcript grows under the press); a rapid double send; a long composed body; and the injected pair — the two
whole-session builds a send used to race, delivered newest-then-oldest through the pane's own message channel
(the T262i idiom). `quote` sends the same `sendMessage` frame as `plain` with a composed body (render.ts
routeUserMessage), so the long-body round covers it; `followup` differs only in the kernel entry point it posts to.

Last, a POSITIVE CONTROL: the same older list with its watermark stripped, which nothing refuses, then the base
back. The sampler must convict THAT — the watched turns leaving a painted frame and returning a few frames later,
by uuid — or a green run above would only mean the instrument was blind.

SYNTHETIC fixtures only; skips loudly without the extension deps or a Playwright browser.
"""
import json
import os
import re
import shutil
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
import test_ship_reship_served as _lab                     # noqa: E402  the lab kernel's environment
from test_send_bubble_visible_browser import _free_port, _kernel, _kernel_tail, _seed_records, SID   # noqa: E402

ROUNDS = int(os.environ.get("SEND_FLASH_ROUNDS", "2"))     # two rounds of each variant fits CI's per-test cap
LOCAL_SETUP_S = 60
DRIVER_TIMEOUT_S = 420

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
await page.addInitScript(() => {
  window.__frames = 0; window.__sockets = []; window.__sent = []; window.__last = null; window.__diag = [];
  window.addEventListener("message", (e) => { const m = e.data; if (!m || typeof m.type !== "string") return;
    if (m.type === "session" || m.type === "update" || m.type === "chatTail") { window.__frames++;
      if (m.type === "session" && Array.isArray(m.events)) window.__last = m; } });
  const origSend = WebSocket.prototype.send;
  WebSocket.prototype.send = function (d) {
    try { const m = JSON.parse(d);
          if (m && m.type === "sendMessage") window.__sent.push({ qid: m.qid });
          if (m && m.type === "clientDiag" && m.surface === "chat" && /^frame-/.test(m.what || "")) window.__diag.push({ what: m.what }); } catch (e) {}
    if (!window.__sockets.includes(this)) window.__sockets.push(this);
    return origSend.call(this, d);
  };
});
// ── the watcher: a per-PAINT sample of the landed turns, plus the mutation record beside it ──
const installWatcher = () => page.evaluate(() => {
  const content = document.getElementById("content");
  const TRANSIENT = /^(optimistic:|held:|echo:|echo-|cmd:)/;   // never landed turns (frame-guard.ts TRANSIENT_KEY_PREFIXES + the page's own)
  const landed = () => {
    const out = [];
    for (const el of content.querySelectorAll(".turn[data-uuid]")) {
      const u = el.dataset.uuid;
      if (!u || TRANSIENT.test(u)) continue;
      if (el.getClientRects().length === 0) continue;         // a hidden echo paints nothing
      out.push(u);
    }
    return out;
  };
  const w = { paints: 0, prev: new Set(), watch: new Set(), left: [], back: [], mut: [], stopped: false, landed };
  window.__watch = w;
  w.mo = new MutationObserver((recs) => {
    for (const r of recs) for (const n of r.removedNodes) {
      if (!(n instanceof Element) || !n.matches || !n.matches(".turn[data-uuid]")) continue;
      const u = n.dataset.uuid;
      if (!u || TRANSIENT.test(u) || !w.watch.has(u)) continue;
      // back inside the SAME task = a tail re-render, which no paint can fall inside; still recorded, apart
      w.mut.push({ uuid: u.slice(-12), sameTask: !!content.querySelector('[data-uuid="' + CSS.escape(u) + '"]') });
    }
  });
  w.mo.observe(content, { childList: true, subtree: true });
  const tick = () => {
    if (w.stopped) return;
    w.paints++;
    const now = new Set(landed());
    for (const u of w.prev) if (w.watch.has(u) && !now.has(u)) w.left.push({ uuid: u.slice(-12), paint: w.paints });
    for (const u of now) if (w.watch.has(u) && !w.prev.has(u)) w.back.push({ uuid: u.slice(-12), paint: w.paints });
    w.prev = now;
    requestAnimationFrame(tick);
  };
  w.prev = new Set(landed());
  requestAnimationFrame(tick);
});
// arm the watch on the last `n` landed turns resident right now (inside the tail window, so no slide counts)
let frameAtPress = 0;   // window.__frames at the press: `observe` records how many frames the round added, so a round the kernel never answered reads 0
const watchTailFull = async (n) => {
  frameAtPress = await page.evaluate(() => window.__frames);
  return page.evaluate((k) => {
    const w = window.__watch;
    const all = w.landed();
    w.watch = new Set(all.slice(-k));
    w.prev = new Set(all);
    w.left.length = 0; w.back.length = 0; w.mut.length = 0;
    return all.slice(-k);                                 // in view order: the last is the newest landed turn
  }, n);
};
const watchTail = async (n) => (await watchTailFull(n)).map((u) => u.slice(-12));
const readWatch = () => page.evaluate(() => ({ paints: window.__watch.paints, left: window.__watch.left.slice(),
                                               back: window.__watch.back.slice(), mut: window.__watch.mut.slice(),
                                               present: window.__watch.landed().map((u) => u.slice(-12)) }));
const armPage = async () => {
  await page.goto(cfg.chat);
  await page.waitForSelector("#tabs .tab, #tabs [data-sid]", { timeout: 20000 });
  if (cfg.remote) {
    const remoteTab = page.locator("#tabs .tab", { hasText: cfg.remote }).first();
    await remoteTab.waitFor({ timeout: 45000 });
    await remoteTab.click();
  }
  await page.waitForSelector(".turn.turn-user", { timeout: 20000 });
  await page.waitForTimeout(600);
};
await armPage();
await installWatcher();
const painted = () => page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 0)))));
let lastSeen = 0, waits = 0, waitTimeouts = 0;
const snap = async () => { lastSeen = await page.evaluate(() => window.__frames); };
const waitFrames = async (n, ms) => { waits++; try { await page.waitForFunction(({ b, n }) => window.__frames >= b + n, { b: lastSeen, n }, { timeout: ms }); } catch (e) { waitTimeouts++; } await snap(); };
const send = async (text) => { await snap(); await page.fill("#composer-input", text); await page.press("#composer-input", "Enter"); };
let stepN = 0; let parent = cfg.parent; const t0 = cfg.t0;
const iso = (x) => new Date(x * 1000).toISOString().replace(/\.\d{3}Z$/, ".000Z");
const step = () => {   // one more record on the transcript: the reply going on under the press
  const i = stepN++;
  const t = t0 + 200 + i;
  const r = i % 2 === 0
    ? { type: "assistant", timestamp: iso(t), uuid: "s" + i, parentUuid: parent, sessionId: cfg.sid,
        message: { role: "assistant", model: "claude-fable-5-1", stop_reason: "tool_use", content: [{ type: "tool_use", id: "tu_s" + i, name: "Bash", input: { command: "true # step " + i } }] } }
    : { type: "user", timestamp: iso(t), uuid: "s" + i, parentUuid: parent, sessionId: cfg.sid,
        message: { role: "user", content: [{ type: "tool_result", tool_use_id: "tu_s" + (i - 1), content: "ok" }] } };
  parent = "s" + i;
  fs.appendFileSync(cfg.transcript, JSON.stringify(r) + "\n");
};
const rounds = [];   // one record per round: what was watched, the frames the round added, what left a painted frame, what came back
const observe = async (variant, round, watched) => {
  const r = await readWatch();
  const cur = await page.evaluate(() => window.__frames);
  rounds.push({ variant, round, watched, frames: cur - frameAtPress, paints: r.paints, left: r.left, back: r.back,
                mut: r.mut, missing: watched.filter((u) => !r.present.includes(u)) });
};
let n = 0;
const fresh = (tag) => `please ${tag} the notes-api search index, round ${++n}`;
const on = (v) => !cfg.variants || cfg.variants.includes(v);
// A. a send into a session sitting idle: nothing else is moving, so any removal is the send's own
for (let r = 0; on("A") && r < cfg.rounds; r++) {
  const watched = await watchTail(8);
  await send(fresh("rebuild"));
  await waitFrames(1, 4000); await painted();
  await page.waitForTimeout(500); await painted();
  await observe("idle", r, watched);
}
// B. a send while the previous turn is still streaming: records land under the press
for (let r = 0; on("B") && r < cfg.rounds; r++) {
  const watched = await watchTail(8);
  await snap(); step(); step();
  await send(fresh("profile"));
  step();
  await waitFrames(2, 6000); await painted();
  step();
  await waitFrames(1, 5000); await painted();
  await observe("streaming", r, watched);
}
// C. two presses in a row, the second before the first's frame lands
for (let r = 0; on("C") && r < cfg.rounds; r++) {
  const watched = await watchTail(8);
  await page.fill("#composer-input", fresh("tighten")); await page.press("#composer-input", "Enter");
  await page.fill("#composer-input", fresh("document")); await page.press("#composer-input", "Enter");
  await waitFrames(2, 6000); await painted();
  await page.waitForTimeout(500); await painted();
  await observe("double", r, watched);
}
// D. a long composed body, the shape the quote route posts (routeUserMessage: the same sendMessage frame)
for (let r = 0; on("D") && r < cfg.rounds; r++) {
  const watched = await watchTail(8);
  const quoted = ["> the notes-api search index is rebuilt on every write", ">", "can we batch that?", ""].join("\n");
  await send(quoted + fresh("batch"));
  await waitFrames(1, 4000); await painted();
  await page.waitForTimeout(400); await painted();
  await observe("quote-body", r, watched);
}
// E. the injected pair: the two whole-session builds a send used to race (66486701's targeted push beside the
// pusher cycle), delivered NEWEST then OLDEST through the pane's own message channel. With one builder no such
// pair exists; PR 2050's watermark guard is the backstop, and either way no watched turn may leave a paint.
const injected = {};
if (on("E")) {
  await page.evaluate(() => { window.__last = null; for (const ws of window.__sockets) { try { ws.close(); } catch (e) {} } });
  try { await page.waitForFunction(() => !!window.__last, null, { timeout: 10000 }); } catch (e) {}
  await page.waitForTimeout(400);
  const base = await page.evaluate(() => window.__last);
  injected.baseOk = !!(base && base.wm && Array.isArray(base.wm.tx) && base.wm.leaf);
  if (injected.baseOk) {
    const full = await watchTailFull(8);
    const watched = full.map((u) => u.slice(-12));
    // the older reader's list: the last landed turns its parse had not reached, dropped by uuid (its live tail
    // still carried the echo and the streamed reply, which is why it read as newer on that axis alone)
    injected.dropped = full.slice(-3).map((u) => u.slice(-12));
    const bump = (wm, dSize, dLive) => ({ leaf: wm.leaf, tx: wm.tx.map((r, i) => (i === 0 ? [r[0] + (dSize > 0 ? 1 : 0), r[1] + dSize] : r)), live: (typeof wm.live === "number" ? wm.live : 0) + dLive });
    const olderEvents = await page.evaluate(({ evs, drop }) => evs.filter((e) => !drop.includes(e && e.uuid)),
                                            { evs: base.events, drop: full.slice(-3) });
    const newer = { ...base, wm: bump(base.wm, 400, 1) };
    const older = { ...base, events: olderEvents, wm: bump(base.wm, 0, 3) };
    const inject = (f) => page.evaluate((x) => { window.postMessage(x, "*"); }, f);
    await inject(newer); await painted();
    await inject(older); await painted();
    await page.waitForTimeout(300); await painted();
    injected.diag = await page.evaluate(() => window.__diag.slice());
    await observe("injected-older-frame", 0, watched);
    // F. the POSITIVE CONTROL: the same older list with NO watermark, which nothing refuses, then the base back.
    // This is the flash itself, staged — and the instrument must convict it, or a green run above says nothing.
    const bare = { ...older }; delete bare.wm;
    const w2 = await watchTail(8);
    await inject(bare); await painted(); await page.waitForTimeout(120); await painted();
    await inject({ ...base, wm: bump(base.wm, 800, 2) }); await painted(); await page.waitForTimeout(200); await painted();
    await observe("control-unguarded-older-frame", 0, w2);
  }
}
await page.evaluate(() => { window.__watch.stopped = true; window.__watch.mo.disconnect(); });
const sent = await page.evaluate(() => window.__sent.length);
fs.writeFileSync(cfg.out, JSON.stringify({ rounds, sent, injected, waits, waitTimeouts }));
fs.writeSync(1, "RESULT-FILE:" + cfg.out + "\n");
await browser.close();
process.exit(0);
"""


class NoLandedTurnLeavesAPaintedFrame(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(os.path.join(EXT, "node_modules", "playwright")):
            raise unittest.SkipTest("extension deps absent (npm ci not run here) — the served guard needs them")
        cls.lab = tempfile.mkdtemp(prefix="send-flash-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            raise unittest.SkipTest("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
        copy_dist(os.path.join(EXT, "dist"), os.path.join(cls.lab, "dist"))
        cls.t0 = int(time.time()) - 900
        cls.port, cls.token = _free_port(), "testtok-sendflash"
        cls.proc, cls.klog, cls.transcript = _kernel(cls.lab, "one", cls.port, cls.token, records=_seed_records(cls.t0))

    @classmethod
    def tearDownClass(cls):
        p = getattr(cls, "proc", None)
        if p:
            p.kill(); p.wait()
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

    def test_no_send_takes_a_landed_turn_out_of_a_painted_frame(self):
        cfg = os.path.join(self.lab, "cfg.json")
        console_log = os.path.join(self.lab, "console.log")
        Path(console_log).write_text("")
        with open(cfg, "w") as f:
            json.dump({"chat": "http://127.0.0.1:%d/chat?token=%s" % (self.port, self.token),
                       "transcript": self.transcript, "sid": SID, "t0": self.t0, "parent": "a3", "rounds": ROUNDS,
                       "consoleLog": console_log, "variants": None, "remote": None,
                       "out": os.path.join(self.lab, "result.json")}, f)
        driver = os.path.join(self.lab, "driver.mjs")
        with open(driver, "w") as f:
            f.write(DRIVER)
        try:
            p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=DRIVER_TIMEOUT_S,
                               env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
        except subprocess.TimeoutExpired as e:
            out = e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
            self.fail("the driver ran past its %d s budget; its output so far:\n%s\n%s"
                      % (DRIVER_TIMEOUT_S, out[-3000:], _kernel_tail(("kernel", self.klog))))
        if p.returncode == 3:
            raise unittest.SkipTest("no playwright browser on this box — the served guard needs one")
        self.assertEqual(p.returncode, 0, "driver failed:\n" + p.stdout[-3000:] + p.stderr[-3000:]
                         + "\nkernel:\n" + open(self.klog).read()[-2500:])
        line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT-FILE:")), None)
        self.assertIsNotNone(line, "driver printed no result:\n" + p.stdout[-3000:])
        with open(line[len("RESULT-FILE:"):]) as f:
            r = json.load(f)
        rounds = r["rounds"]
        print("SEND-FLASH: %d rounds, %d sends reached the socket, %d of %d frame waits ran out"
              % (len(rounds), r["sent"], r["waitTimeouts"], r["waits"]))
        for x in rounds:
            print("  %-22s round %d: %d frames, %d paints, watched %d, left %r, back %r, same-task removals %d"
                  % (x["variant"], x["round"], x["frames"], x["paints"], len(x["watched"]), x["left"], x["back"],
                     sum(1 for m in x["mut"] if m["sameTask"])))
        console = open(console_log).read()
        self.assertEqual(console.strip(), "", "the page logged errors:\n" + console[-2000:])
        inj = r["injected"]
        self.assertTrue(inj.get("baseOk"), "the kernel's real frame carries a watermark: %r" % (inj,))
        # ROUNDS rounds of each of A to D, then the injected pair (E and its control), which run once the watermark is in hand
        self.assertEqual(len(rounds), 4 * ROUNDS + 2, "every variant ran: %r" % [x["variant"] for x in rounds])
        self.assertGreater(min(x["paints"] for x in rounds), 0, "the per-paint sampler ran: %r" % rounds)
        # The real rounds are not vacuous (review, 2026-09-23): waitFrames swallows its timeout into a counter, so a kernel
        # that refused every send or never delivered a frame would have left every real round green. Five presses per
        # round (A one, B one, C two, D one), each a sendMessage frame on the socket; and every real round added at least
        # one frame from the kernel since its press. The wait timeouts stay a printed figure: they flake under CI load.
        self.assertEqual(r["sent"], 5 * ROUNDS, "every press posted a sendMessage frame: %d of %d" % (r["sent"], 5 * ROUNDS))
        # The POSITIVE CONTROL first: the flash, staged (an older list no guard refuses, then the base back).
        # The instrument must convict it, or the invariant below is green for saying nothing.
        ctrl = [x for x in rounds if x["variant"] == "control-unguarded-older-frame"]
        self.assertEqual(len(ctrl), 1, "the control ran: %r" % [x["variant"] for x in rounds])
        gone = {u["uuid"] for u in ctrl[0]["left"]}
        self.assertTrue(gone, "the sampler caught landed turns leaving a painted frame under an unguarded older list")
        self.assertTrue(gone & {u["uuid"] for u in ctrl[0]["back"]},
                        "…and coming back: the flash the user reported, recorded in both directions: %r" % ctrl[0])
        self.assertTrue(gone & set(inj["dropped"]), "…and they are the turns that list left out: %r vs %r"
                        % (sorted(gone), inj["dropped"]))
        self.assertEqual(ctrl[0]["missing"], [], "the control heals, as the user's flash did")
        # THE INVARIANT: on a real send, a watched turn never leaves a frame the browser painted
        real = [x for x in rounds if x["variant"] != "control-unguarded-older-frame"]
        flashed = [{k: x[k] for k in ("variant", "round", "left", "back", "mut")} for x in real if x["left"]]
        self.assertEqual(flashed, [], "a landed turn left a painted frame after a send (the flash):\n%s"
                         % json.dumps(flashed, indent=2))
        # …and none of them is simply gone at the end either
        lost = [{k: x[k] for k in ("variant", "round", "missing")} for x in real if x["missing"]]
        self.assertEqual(lost, [], "a landed turn was gone from the page after a send:\n%s" % json.dumps(lost, indent=2))
        self.assertEqual([x["variant"] for x in real if x["frames"] == 0], [],
                         "every real send round saw at least one new frame from the kernel")
        self.assertIn("frame-stale", [d["what"] for d in inj.get("diag") or []],
                      "the older build is refused by the page's backstop and said so: %r" % (inj.get("diag"),))


class DriverBudget(unittest.TestCase):
    """The driver's budget sits under the per-test ceiling CI's served-page step gives pytest, less this class's
    setup (the esbuild run and a healthz boot loop). Needs no browser."""

    def test_the_budget_sits_under_the_ci_cap_less_the_setup(self):
        text = open(os.path.join(ROOT, ".github", "workflows", "ci.yml")).read()
        at = text.find('ROMP_SERVED_TESTS_REQUIRE: "1"')
        self.assertGreater(at, 0, "ci.yml names the served-page step by its ROMP_SERVED_TESTS_REQUIRE env")
        m = re.search(r"--timeout=(\d+)", text[at:])
        self.assertIsNotNone(m, "the served-page step runs pytest under --timeout")
        self.assertLess(DRIVER_TIMEOUT_S + LOCAL_SETUP_S, int(m.group(1)))

    def test_the_driver_run_reads_the_budget(self):
        src = open(os.path.realpath(__file__)).read()
        self.assertIn("timeout=DRIVER_TIMEOUT_S", src, "the run reads the constant, never a literal")
        self.assertIn("except subprocess.TimeoutExpired", src, "a budget overrun reports with the kernel's tail")


if __name__ == "__main__":
    unittest.main()
