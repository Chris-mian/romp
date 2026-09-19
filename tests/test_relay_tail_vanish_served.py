"""The vanishing-intervening-messages bug (the user's top priority, 2026-09-18): a session read long and scrolled
back drops the turns between the reader's read point and the live tail on ONE frame. The user's shape: an assistant
message "1 hour ago" then directly "now", with an hour of turns between them gone from the render though they are on
disk. It surfaced on REMOTE sessions over the federation relay (the sessions one reads long and scrolls back into),
but the defect is entirely page-side (the 2026-09-19 investigation: federation.ts copies the frame whole); the relay is only
the amplifier, so this lab drives a relayed session through the relay's own inbound door.

The loss needs a frame the page cannot safely place onto the regions it holds, and the branch that receives one
APPLIES it instead of refusing it. Four such shapes, one per guard, each injected here through the window twin of
window.__rompFed.inbound (a re-windowed full frame or a delta the kernel really sends, one field varied):
  taillo_low        (guard 3, render.ts upsert): a proto-2 full frame whose tailLo lies at/below a held history
                    run's hi while its events do not re-carry that run -> the merge drops the run / concatenates
                    across the hole (the reported "1 hour ago" directly above "now").
  no_taillo         (guard 2, upsert): a proto-2 full frame with no numeric tailLo -> the merge is skipped and the
                    frame's window replaces every held run.
  not_proto2        (guard 2, upsert): a full frame that is not proto 2 for a session the page holds as proto 2 ->
                    same collapse.
  anchor_in_history (guard 1, chatTail): a delta whose afterUuid resolves inside a HISTORY run, not the tail run ->
                    s.events truncates there and every row between that run and the tail is dropped.

The invariant each asserts: the resident region store does not SHRINK across the frame (no held run is discarded),
the parked read point stays, and its neighbours stay. Red at main; green once each site refuses a frame it cannot
place and asks for one it can. Synthetic only (placeholder uuids, hostname TESTHOST, invented text). Reuses the
two-kernel relay harness of test_federated_history_scroll_served.
"""
import json
import os
import re
import subprocess
import sys
import time
import unittest
import urllib.request

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
EXT = os.path.join(ROOT, "vscode-extension")
BIN = os.path.join(ROOT, "bin")
sys.path.insert(0, HERE)
import test_federated_history_scroll_served as _fed   # noqa: E402  reuse _kernel/_transcript/_free_port/HOST
from tests.dist_copy import copy_dist   # noqa: E402

SID_R = "11111111-2222-4333-8444-000000000d01"   # the watched remote session
HOST = _fed.HOST
REMOTE = HOST + ":" + SID_R
WID = "vanishlab"
PAIRS = 600   # ~1200 events; the tail holds the last ~125 turns, so a middle read point stays far from it
MID_TURN = 200   # the read point: a middle turn far from BOTH the head and the resident tail (~turn 475+), so a gap persists to the tail
SCENARIOS = ["taillo_low", "no_taillo", "not_proto2", "anchor_in_history"]


DRIVER = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
const require = createRequire(process.env.EXT_PKG);
const { chromium } = require("playwright");
const cfg = JSON.parse(fs.readFileSync(process.env.CFG, "utf8"));
let browser;
try { browser = await chromium.launch(cfg.launch || {}); }
catch (e) { console.error("browser-launch-failed: " + e); process.exit(3); }
const context = await browser.newContext({ viewport: { width: 1200, height: 800 } });
const page = await context.newPage();
const out = { died: null, scenarios: {} };
page.on("pageerror", () => {});
await page.addInitScript((rid) => {
  try { localStorage.setItem("romp-vscode-state-chat", JSON.stringify({ activeId: rid })); } catch (e) {}
}, cfg.remote);

const snapshot = async () => page.evaluate((c) => {
  const rs = (window.__rompRegions && window.__rompRegions()) || [];
  const runs = rs.filter((r) => r.kind === "run");
  const dom = Array.from(document.querySelectorAll("#content .turn[data-uuid]")).map((t) => t.getAttribute("data-uuid"));
  const readRun = rs.find((r) => r.kind === "run" && r.hi != null && r.lo > 0) || null;
  return {
    regions: rs, storeCount: runs.reduce((n, r) => n + (r.n || 0), 0),
    hasGap: rs.some((r) => r.kind === "gap" && r.lo > 0),
    readPresent: dom.includes(c.readUuid), readRunLo: readRun ? readRun.lo : 0, readRunLast: readRun ? readRun.last : null,
    neighbors: c.neighbors.filter((u) => dom.includes(u)), domLen: dom.length,
  };
}, { readUuid: cfg.readUuid, neighbors: cfg.neighbors });

const park = async () => {
  await page.goto(cfg.chat);
  await page.waitForSelector("#content .turn[data-uuid]", { timeout: 40000 });
  await page.waitForTimeout(1200);
  // LAND on a middle turn (a deep link): the shell posts a focus to the read-point uuid; the page opens a window
  // around it, leaving a gap between that read-point run and the resident tail run (the user's scrolled-back shape).
  await page.evaluate((f) => window.postMessage(f, "*"), { type: "focus", id: cfg.remote, anchor: cfg.readUuid });
  await page.waitForFunction((u) => !!document.querySelector('#content .turn[data-uuid="' + u + '"]'), cfg.readUuid, { timeout: 40000 }).catch(() => {});
  await page.waitForTimeout(1800);
};

const inject = async (name, before) => {
  const base = { id: cfg.remote, ev: cfg.frameEvents, nm: cfg.sessionName, lo: before.readRunLo, anchor: before.readRunLast, delta: cfg.deltaEvents };
  await page.evaluate((a) => {
    const st = { state: "idle", sinceEpoch: null };
    if (a.name === "taillo_low") window.postMessage({ type: "session", id: a.id, proto: 2, events: a.ev, tailLo: a.lo, headKnown: false, name: a.nm, status: st }, "*");
    else if (a.name === "no_taillo") window.postMessage({ type: "session", id: a.id, proto: 2, events: a.ev, headKnown: false, name: a.nm, status: st }, "*");
    else if (a.name === "not_proto2") window.postMessage({ type: "session", id: a.id, events: a.ev, name: a.nm, status: st }, "*");
    else if (a.name === "anchor_in_history") window.postMessage({ type: "chatTail", id: a.id, afterUuid: a.anchor, events: a.delta }, "*");
  }, { ...base, name });
  await page.waitForTimeout(2500);
};

try {
  for (const name of cfg.scenarios) {
    await park();
    const before = await snapshot();
    await inject(name, before);
    const after = await snapshot();
    out.scenarios[name] = { before, after };
  }
} catch (e) { out.died = String(e).slice(0, 500); }
console.log("RESULT:" + JSON.stringify(out));
await browser.close();
"""


class RelayVanishGuards(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.procs = []
        try:
            cls._boot()
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def _boot(cls):
        if not os.path.isdir(os.path.join(EXT, "node_modules", "playwright")):
            raise unittest.SkipTest("extension deps absent (npm ci not run here), the served lab needs them")
        probe = subprocess.run(["node", "-e", "const p=require(process.argv[1]);process.stdout.write(p.chromium.executablePath())",
                                os.path.join(EXT, "node_modules", "playwright")], capture_output=True, text=True)
        if probe.returncode != 0 or not os.path.exists(probe.stdout.strip()):
            raise unittest.SkipTest("no playwright browser on this box, the served lab needs one (CI installs none)")
        import tempfile
        cls.lab = tempfile.mkdtemp(prefix="relay-vanish-guards-")
        b = subprocess.run(["node", "esbuild.js"], cwd=EXT, capture_output=True, text=True)
        if b.returncode != 0:
            raise unittest.SkipTest("esbuild failed here: " + (b.stderr or b.stdout)[-200:])
        copy_dist(os.path.join(EXT, "dist"), os.path.join(cls.lab, "dist"))
        cls.rport, cls.rtoken = _fed._free_port(), "testtok-vanish-remote"
        cls.hport, cls.htoken = _fed._free_port(), "testtok-vanish-hub"
        rp, cls.rlog = _fed._kernel(cls.lab, "testhost", cls.rport, cls.rtoken, [(SID_R, "api", "api", PAIRS)])
        cls.procs.append(rp)
        hp, cls.hlog = _fed._kernel(cls.lab, "hub", cls.hport, cls.htoken, [])
        cls.procs.append(hp)
        body = json.dumps({"host": HOST, "kernelPort": cls.rport, "busPort": _fed._free_port(), "token": cls.rtoken}).encode()
        req = urllib.request.Request("http://127.0.0.1:%d/checkin?token=%s" % (cls.hport, cls.htoken), data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            if not json.loads(resp.read().decode()).get("ok"):
                raise unittest.SkipTest("the hub refused the check-in")
        for _ in range(60):
            try:
                with urllib.request.urlopen("http://127.0.0.1:%d/tunnels?token=%s" % (cls.hport, cls.htoken), timeout=3) as r2:
                    rows = json.loads(r2.read().decode()).get("tunnels") or []
            except Exception:
                rows = []
            row = next((t for t in rows if t.get("host") == HOST), None)
            if row and row.get("status") == "up" and row.get("hasToken"):
                break
            time.sleep(0.5)
        else:
            raise unittest.SkipTest("the hub never reported the checked-in peer up")
        cwd = os.path.join(cls.lab, "testhost", "proj")
        cls.result, cls.driver_error = None, None
        cls._drive(cwd)

    @classmethod
    def _tail_pairs(cls, cwd):
        """The re-windowed full frame's events: only the live tail's last three turns (what a full push carries once a
        session passes WIRE_TAIL). Their uuids are the transcript's real tail turns, so the frame shares keys with the
        resident tail run (a re-send, not a /clear fork)."""
        evs = []
        for i in range(PAIRS - 3, PAIRS):
            t0 = 1_700_000_000 + i * 600
            evs.append({"type": "user", "uuid": "api-u%03d" % i, "parentUuid": "api-a%03d" % (i - 1), "sessionId": SID_R,
                        "cwd": cwd, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t0)),
                        "promptSource": "typed", "message": {"role": "user", "content": "turn %d: what changed?" % i}})
            evs.append({"type": "assistant", "uuid": "api-a%03d" % i, "parentUuid": "api-u%03d" % i, "sessionId": SID_R,
                        "cwd": cwd, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t0 + 60)),
                        "message": {"role": "assistant", "model": "claude-opus-5", "stop_reason": "end_turn",
                                    "content": [{"type": "text", "text": "turn %d: the ranking pass is updated" % i}]}})
        return evs

    @classmethod
    def _delta_pairs(cls, cwd):
        """A short tail delta of brand-new turns (fresh uuids), for the chatTail scenario."""
        t0 = 1_700_000_000 + (PAIRS + 5) * 600
        return [
            {"type": "user", "uuid": "delta-user-0001", "parentUuid": "api-a%03d" % (PAIRS - 1), "sessionId": SID_R,
             "cwd": cwd, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t0)), "promptSource": "typed",
             "message": {"role": "user", "content": "one more: paste the latest numbers"}},
            {"type": "assistant", "uuid": "delta-asst-0001", "parentUuid": "delta-user-0001", "sessionId": SID_R,
             "cwd": cwd, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t0 + 60)),
             "message": {"role": "assistant", "model": "claude-opus-5", "stop_reason": "end_turn",
                         "content": [{"type": "text", "text": "done: the numbers are in"}]}},
        ]

    @classmethod
    def _drive(cls, cwd):
        read_uuid = "api-u%03d" % MID_TURN
        neighbors = ["api-u%03d" % (MID_TURN - 1), "api-a%03d" % (MID_TURN - 1), "api-a%03d" % MID_TURN,
                     "api-u%03d" % (MID_TURN + 1), "api-a%03d" % (MID_TURN + 1)]
        cfg = os.path.join(cls.lab, "cfg.json")
        with open(cfg, "w") as f:
            json.dump({"chat": "http://127.0.0.1:%d/chat?skeleton=1&wid=%s&token=%s" % (cls.hport, WID, cls.htoken),
                       "remote": REMOTE, "readUuid": read_uuid, "neighbors": neighbors, "sessionName": "api",
                       "scenarios": SCENARIOS, "frameEvents": cls._tail_pairs(cwd), "deltaEvents": cls._delta_pairs(cwd)}, f)
        driver = os.path.join(cls.lab, "driver.mjs")
        with open(driver, "w") as f:
            f.write(DRIVER)
        try:
            p = subprocess.run(["node", driver], capture_output=True, text=True, timeout=400,
                               env=dict(os.environ, EXT_PKG=os.path.join(EXT, "package.json"), CFG=cfg))
        except subprocess.TimeoutExpired as e:
            cls.driver_error = "driver timed out; partial:\n%s" % ((e.stdout if isinstance(e.stdout, str) else (e.stdout or b"").decode()))
            return
        if p.returncode == 3:
            raise unittest.SkipTest("no playwright browser on this box (CI installs none)")
        if p.returncode != 0:
            cls.driver_error = "driver failed:\n" + p.stdout[-3000:] + p.stderr[-3000:]
            return
        line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT:")), None)
        if line is None:
            cls.driver_error = "driver printed no result:\n" + p.stdout[-3000:] + p.stderr[-3000:]
            return
        cls.result = json.loads(line[len("RESULT:"):])

    @classmethod
    def tearDownClass(cls):
        for p in getattr(cls, "procs", []):
            try:
                p.kill(); p.wait()
            except Exception:
                pass
        import shutil
        shutil.rmtree(getattr(cls, "lab", ""), ignore_errors=True)

    def _scenario(self, name):
        if getattr(type(self), "driver_error", None):
            self.fail(type(self).driver_error)
        if getattr(type(self), "result", None) is None:
            raise unittest.SkipTest("the driver produced no result")
        sc = (type(self).result.get("scenarios") or {}).get(name)
        if sc is None:
            self.fail("the driver ran no %r scenario: %r" % (name, type(self).result))
        return sc["before"], sc["after"]

    def _assert_scenario(self, name, expect_read_drop):
        before, after = self._scenario(name)
        # the scenario must be the user's shape: the read point rendered mid-thread with a real hole to the tail
        self.assertTrue(before.get("readPresent"), "[%s] the read point rendered mid-thread: %r" % (name, before.get("regions")))
        self.assertTrue(before.get("hasGap"), "[%s] a hole lay between the read point and the tail: %r" % (name, before.get("regions")))
        # the invariant: the frame the page cannot place must NOT shrink the resident store (no held run discarded)
        self.assertGreaterEqual(after.get("storeCount", 0), before.get("storeCount", 0),
                                "[%s] the resident store SHRANK across the frame (a held run vanished, the user's bug): before=%d after=%d regions after=%r"
                                % (name, before.get("storeCount", 0), after.get("storeCount", 0), after.get("regions")))
        # …and the parked read point and its neighbours stay
        self.assertTrue(after.get("readPresent"),
                        "[%s] the parked read point VANISHED from the DOM (the user's bug): regions after=%r" % (name, after.get("regions")))
        self.assertEqual(after.get("neighbors"), before.get("neighbors"),
                         "[%s] the read point's neighbours dropped: before=%r after=%r" % (name, before.get("neighbors"), after.get("neighbors")))

    def test_guard3_taillo_below_a_held_run_never_drops_the_read_point(self):
        self._assert_scenario("taillo_low", expect_read_drop=True)

    def test_guard2_full_frame_without_a_taillo_keeps_the_held_runs(self):
        self._assert_scenario("no_taillo", expect_read_drop=True)

    def test_guard2_non_proto2_full_frame_keeps_the_held_runs(self):
        self._assert_scenario("not_proto2", expect_read_drop=True)

    def test_guard1_a_delta_anchored_in_a_history_run_drops_nothing(self):
        self._assert_scenario("anchor_in_history", expect_read_drop=False)


if __name__ == "__main__":
    unittest.main()
