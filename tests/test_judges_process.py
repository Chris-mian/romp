#!/usr/bin/env python3
"""Stage three of the process split (plans/judges-process.md), the kernel's side: with STATE/judges-process `on` the producer
sends one `pass` line per wake to a long-lived `romp-judge --serve` child and feeds its `done` line to /perf's judge block, its
own bookkeeping standing around the request in the loop's order (the goals snapshot opened before, closed after; the generation
bumped only when a store moved); a child that exits mid-pass, hangs past the hard bound, answers a malformed line or speaks a
protocol version this kernel does not know costs a lost pass, never a silent accept, and comes back on the next wake; with the
switch off (the default) the in-process tiers run and no child starts; tracking off sends no request. The child is a stand-in
script answering the protocol romp_metrics's child speaks, through ROMP_JUDGE_SERVE_CMD."""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
from test_asm_checkpoint import kernel_module   # noqa: E402  the hermetic kernel over a temp state root

SID = "11111111-2222-3333-4444-777777777777"
FAKE = r'''
import json, os, sys, time
mode = os.environ.get("FAKE_MODE", "")
log = os.environ.get("FAKE_LOG", "")
store = os.environ.get("FAKE_STORE", "")
sys.stdout.write(json.dumps({"op": "ready", "pid": os.getpid(), "judgeVersion": "fake",
                             "protocolVersion": int(os.environ.get("FAKE_PROTO", "1"))}) + "\n")
sys.stdout.flush()
while True:
    line = sys.stdin.readline()
    if not line:
        break
    req = json.loads(line)
    if req.get("op") == "quit":
        break
    if log:
        with open(log, "a") as f:
            f.write(line)
    seq = req["seq"]
    if mode == "exit-on-2" and seq == 2:
        sys.exit(3)
    if mode == "hang-on-2" and seq == 2:
        time.sleep(30)
    if mode == "garbage-on-2" and seq == 2:
        sys.stdout.write("romp-judge: not a protocol line\n"); sys.stdout.flush()
        continue
    if store:
        with open(store, "w") as f:
            f.write(json.dumps({"rompUuid": os.path.basename(store)[:-5], "seq": seq, "closedTurns": [], "nodes": {}, "placements": {}, "status": {}}))
    sys.stdout.write(json.dumps({"op": "done", "seq": seq, "wallMs": 12.5, "tierStarts": 2 if req.get("tracking") else 0,
                                 "tierCpuMs": 3.0, "workerCpuMs": 4.0, "failures": None,
                                 "recordCache": {"entries": 1}, "asmCheckpoint": {"restore": 1}}) + "\n")
    sys.stdout.flush()
'''


class _Child(unittest.TestCase):
    def setUp(self):
        self.km = km = kernel_module()
        self.jd = km.jd
        self.td = tempfile.mkdtemp()
        self.script = os.path.join(self.td, "fake-judge.py")
        Path(self.script).write_text(FAKE)
        self.log = os.path.join(self.td, "requests.jsonl")
        self.env_saved = {k: os.environ.get(k) for k in ("ROMP_JUDGE_SERVE_CMD", "FAKE_MODE", "FAKE_LOG", "FAKE_STORE", "FAKE_PROTO")}
        os.environ["ROMP_JUDGE_SERVE_CMD"] = "%s %s" % (sys.executable, self.script)
        os.environ["FAKE_LOG"] = self.log
        for k in ("FAKE_MODE", "FAKE_STORE", "FAKE_PROTO"):
            os.environ.pop(k, None)
        self.saved = (km._wait_boot_attached, km._live_map, km._retry_paused_on, km._sdk, km._task_tracking_on,
                      getattr(km, "JUDGE_CHILD_PASS_HARD_S", None), self.jd.run_index, self.jd.run_triage)
        km._wait_boot_attached = lambda: True
        km._live_map = lambda: {SID: {"state": "waiting", "since": 1}}
        km._retry_paused_on = lambda: False
        km._sdk = lambda: None
        if hasattr(km, "_PRODUCER_ONE_PASS"):
            km._PRODUCER_ONE_PASS[0] = True
        if hasattr(km, "_JUDGE_CHILD"):
            km._JUDGE_CHILD.__init__()                    # a fresh child slot: no process, seq 0, never started
        self._reset_judge_counters()
        self.switch = self.jd.STATE / getattr(km, "JUDGES_PROCESS_FILE", "judges-process")
        self.jd.GOALDIR.mkdir(parents=True, exist_ok=True)

    def _reset_judge_counters(self):
        with self.km._PERF_STATS.lock:
            self.km._PERF_STATS.judge.update({"passes": 0, "tierStarts": 0})
            for k, v in (("passesLost", 0), ("childRestarts", 0), ("cpu_ms_child_workers", 0.0), ("child", None)):
                if k in self.km._PERF_STATS.judge:
                    self.km._PERF_STATS.judge[k] = v

    def tearDown(self):
        km = self.km
        if hasattr(km, "_JUDGE_CHILD"):
            km._JUDGE_CHILD.stop()
        if hasattr(km, "_PRODUCER_ONE_PASS"):
            km._PRODUCER_ONE_PASS[0] = False
        (km._wait_boot_attached, km._live_map, km._retry_paused_on, km._sdk, km._task_tracking_on,
         km.JUDGE_CHILD_PASS_HARD_S, self.jd.run_index, self.jd.run_triage) = self.saved
        for k, v in self.env_saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        try:
            self.switch.unlink()
        except OSError:
            pass
        for p in (self.jd.GOALDIR / (SID + ".json"),):
            try:
                p.unlink()
            except OSError:
                pass

    def _on(self):
        self.switch.write_text("on\n")

    def _pass(self):
        """One producer pass. The head's loop returns after a pass on the test sentinel; a kernel without it (the base) is
        driven on a thread and stopped after its first pass, so every test here is red at the base on its assertion."""
        km = self.km
        if hasattr(km, "_PRODUCER_ONE_PASS"):
            km._producer()
            return
        import threading
        passes0 = km._PERF_STATS.judge["passes"]
        t = threading.Thread(target=km._producer, daemon=True)
        t.start()
        deadline = time.monotonic() + 20
        while km._PERF_STATS.judge["passes"] == passes0 and time.monotonic() < deadline:   # loop-ok: a bounded wait on the pass counter
            time.sleep(0.02)
        km._LOOPS_STOP.set(); km._producer_wake.set()
        t.join(10)
        km._LOOPS_STOP.clear()

    def _requests(self):
        try:
            return [json.loads(l) for l in Path(self.log).read_text().splitlines() if l.strip()]
        except OSError:
            return []

    def _judge(self):
        return self.km._PERF_STATS.snapshot()["judge"]


class ChildRoad(_Child):
    def test_one_pass_through_the_child_feeds_perf_and_keeps_the_kernels_bookkeeping_in_order(self):
        km = self.km
        self._on()
        os.environ["FAKE_STORE"] = str(self.jd.GOALDIR / (SID + ".json"))   # the child's judges write a store during the pass
        order = []
        child = getattr(km, "_JUDGE_CHILD", None)         # absent at the base: the order then never shows a pass, the red below
        real_begin, real_end, real_pass = km._begin_goals_pass, km._end_goals_pass, getattr(child, "pass_", None)
        km._begin_goals_pass = lambda: (order.append("begin"), real_begin())[1]
        km._end_goals_pass = lambda: (order.append("end"), real_end())[1]
        if child is not None:
            child.pass_ = lambda now, tracking=True: (order.append("pass"), real_pass(now, tracking))[1]
        called = []
        self.jd.run_index = lambda: called.append("index")
        self.jd.run_triage = lambda: called.append("triage")
        gen0 = km._judge_gen[0]
        try:
            self._pass()
        finally:
            km._begin_goals_pass, km._end_goals_pass = real_begin, real_end
            if child is not None:
                child.pass_ = real_pass
        reqs = self._requests()
        self.assertEqual(len(reqs), 1, "one pass line per wake: %r" % reqs)
        self.assertEqual((reqs[0]["op"], reqs[0]["seq"], reqs[0]["tracking"]), ("pass", 1, True))
        self.assertAlmostEqual(reqs[0]["now"], time.time(), delta=30)
        self.assertEqual(called, [], "no in-process tier ran")
        self.assertEqual(order[:3], ["begin", "pass", "end"], "the goals snapshot opens before the request and closes after it: %r" % order)
        self.assertEqual(km._judge_gen[0], gen0 + 1, "the generation bumped once: the child's store write, seen after its done")
        j = self._judge()
        self.assertEqual((j["passes"], j["tierStarts"], j.get("passesLost"), j.get("childRestarts")), (1, 2, 0, 0))
        self.assertEqual(j.get("cpu_ms_child_workers"), 4.0)
        self.assertEqual((j.get("child") or {}).get("seq"), 1)
        self.assertEqual((j.get("child") or {}).get("pid"), getattr(getattr(km, "_JUDGE_CHILD", None), "pid", None))
        self.assertEqual((j.get("child") or {}).get("recordCache"), {"entries": 1})

    def test_a_pass_with_no_store_moved_bumps_no_generation(self):
        km = self.km
        self._on()
        self._pass()                                      # anchors the fingerprint (the first pass)
        gen0 = km._judge_gen[0]
        self._pass()
        self.assertEqual(km._judge_gen[0], gen0, "nothing moved: the views keep their signature")
        self.assertEqual(len(self._requests()), 2, "and the one child served both passes")
        self.assertEqual(self._judge()["childRestarts"], 0)

    def test_the_default_runs_the_tiers_in_process_and_starts_no_child(self):
        km = self.km
        called = []
        self.jd.run_index = lambda: called.append("index")
        self.jd.run_triage = lambda: called.append("triage")
        self._pass()
        self.assertEqual(sorted(called), ["index", "triage"], "the in-process tiers ran")
        self.assertIsNone(getattr(km, "_JUDGE_CHILD", None) and km._JUDGE_CHILD.proc, "no child started")
        self.assertEqual(self._requests(), [])
        self.assertEqual(self._judge()["tierStarts"], 2)

    def test_tracking_off_sends_no_request_and_starts_no_child(self):
        km = self.km
        self._on()
        km._task_tracking_on = lambda: False
        self._pass()
        self.assertEqual(self._requests(), [])
        self.assertIsNone(getattr(km, "_JUDGE_CHILD", None) and km._JUDGE_CHILD.proc)
        self.assertEqual(self._judge()["tierStarts"], 0)


class FailureRoads(_Child):
    def test_a_child_that_exits_mid_pass_loses_the_pass_and_comes_back_on_the_next_wake(self):
        km = self.km
        self._on()
        os.environ["FAKE_MODE"] = "exit-on-2"
        self._pass(); self._pass()
        j = self._judge()
        self.assertEqual((j["passes"], j.get("passesLost"), j.get("childRestarts")), (2, 1, 0), "the second pass is lost: %r" % j)
        self.assertIsNone(getattr(getattr(km, "_JUDGE_CHILD", None), "proc", None), "the dead child is cleared")
        self._pass()
        j = self._judge()
        self.assertEqual((j["passes"], j.get("passesLost"), j.get("childRestarts")), (3, 1, 1), "the third wake restarts it and is served")
        self.assertEqual([r["seq"] for r in self._requests()], [1, 2, 3])

    def test_a_child_silent_past_the_hard_bound_is_killed_and_the_pass_lost(self):
        km = self.km
        self._on()
        os.environ["FAKE_MODE"] = "hang-on-2"
        km.JUDGE_CHILD_PASS_HARD_S = 1.5
        self._pass()
        t0 = time.monotonic(); self._pass(); dt = time.monotonic() - t0
        j = self._judge()
        self.assertEqual((j.get("passesLost"), j.get("childRestarts")), (1, 0))
        self.assertIsNone(getattr(getattr(km, "_JUDGE_CHILD", None), "proc", None), "killed")
        self.assertLess(dt, 10, "the pass ended at the bound, not at the child's leisure")
        self._pass()
        self.assertEqual((self._judge().get("passesLost"), self._judge().get("childRestarts")), (1, 1))

    def test_a_malformed_done_is_a_lost_pass_never_an_accept(self):
        km = self.km
        self._on()
        os.environ["FAKE_MODE"] = "garbage-on-2"
        self._pass()
        child_before = self._judge().get("child")
        self._pass()
        j = self._judge()
        self.assertEqual(j.get("passesLost"), 1)
        self.assertEqual(j.get("child"), child_before, "nothing of the garbage line landed on the block")
        self.assertEqual(j["tierStarts"], 2, "no tier start counted for the lost pass")

    def test_a_protocol_version_this_kernel_does_not_speak_is_refused(self):
        km = self.km
        self._on()
        os.environ["FAKE_PROTO"] = "2"
        self._pass()
        j = self._judge()
        self.assertEqual((j["passes"], j.get("passesLost"), j["tierStarts"]), (1, 1, 0), "refused: the pass is lost, nothing accepted")
        self.assertIsNone(getattr(getattr(km, "_JUDGE_CHILD", None), "proc", None), "and the child is not kept")
        self.assertEqual(self._requests(), [], "no request reached it")


if __name__ == "__main__":
    unittest.main()
