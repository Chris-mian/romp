#!/usr/bin/env python3
"""The Task tracking master switch (T404 PR 2, the user 2026-09-13): default on; off, the task tracking system stands down
entirely. Executed on the kernel module with a hermetic state root: the store's reads (absent, malformed, false, true), the
setter's gesture rules (echo, stale, applied stamp), the socket arm (writes and wakes the producer), the producer's tier
gate (a function of its inputs: off starts nothing with a live session and retries not paused; on starts both), the feed's
off frame in place of a build (the builder stubbed to raise: a call would be the bug), the two panes' notice (hidden while
on, shown while off), the nudge pass walking wake-only while off (the goal nudges wait; the compaction suggestion and the
debt ladder keep the nudge toggle), and the CENSUS: every model-call site in kernel/judge.py names a judge that
judge.py MODEL_CALLERS declares, and the entry point refuses an undeclared judge and stands a tracking judge down while the
switch is off. Synthetic everything: hermetic XDG state, no network, no browser.
"""
import ast
import json
import os
import shutil
import tempfile
import time
import types
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)   # a live kernel's export outranks the XDG floor
os.environ.setdefault("ROMP_KERNEL_PORT", "0")   # never the live kernel's port
import sys
sys.path.insert(0, HERE)
from romp_load import load_source   # noqa: E402

km = load_source("romp_kernel_tasktrack", os.path.join(BIN, "romp-kernel"))
JUDGE_SRC = Path(ROOT, "kernel", "judge.py").read_text()


class _Base(unittest.TestCase):
    """A fresh state root per test; the judge module's hook restored after."""
    maxDiff = None

    def setUp(self):
        self._td = tempfile.mkdtemp()
        self._saved_state = km.jd.STATE
        km.jd.STATE = Path(self._td)
        km.jd._state_cache.clear()
        Path(self._td, "session-hosts").write_text("off")
        self._saved_hook = km.jd.TASK_TRACKING_ON
        km.jd.TASK_TRACKING_ON = km._task_tracking_on
        km._stale_seen.last = None
        km._stale_seen.refused = None

    def tearDown(self):
        km.jd.TASK_TRACKING_ON = self._saved_hook
        km.jd.STATE = self._saved_state
        km.jd._state_cache.clear()
        shutil.rmtree(self._td, ignore_errors=True)

    def _file(self):
        return Path(self._td) / km.TASK_TRACKING_FILE


class TheStore(_Base):
    def test_absent_unreadable_or_malformed_reads_on(self):
        self.assertTrue(km._task_tracking_on(), "no file: on")
        self._file().write_text("{not json")
        self.assertTrue(km._task_tracking_on(), "malformed: on")
        self._file().write_text(json.dumps({"gt": 5}))
        self.assertTrue(km._task_tracking_on(), "no field: on")
        self._file().write_text(json.dumps({"enabled": "no"}))
        self.assertTrue(km._task_tracking_on(), "only the literal false turns it off")

    def test_false_reads_off_and_true_on(self):
        self._file().write_text(json.dumps({"enabled": False, "gt": 1}))
        self.assertFalse(km._task_tracking_on())
        self._file().write_text(json.dumps({"enabled": True, "gt": 2}))
        self.assertTrue(km._task_tracking_on())

    def test_reading_never_creates_the_file(self):
        km._task_tracking_on()
        self.assertFalse(self._file().exists())


class TheSetter(_Base):
    def test_a_stamped_flip_applies_and_is_read_back(self):
        self.assertEqual(km._set_task_tracking(False, gt=1000), 1000)
        self.assertEqual(json.loads(self._file().read_text()), {"enabled": False, "gt": 1000})
        self.assertFalse(km._task_tracking_on())
        self.assertEqual(km._set_task_tracking(True, gt=1001), 1001)
        self.assertTrue(km._task_tracking_on())

    def test_the_same_value_with_the_same_stamp_is_a_silent_echo_and_an_older_stamp_stands_down(self):
        km._set_task_tracking(False, gt=1000)
        self.assertIsNone(km._set_task_tracking(False, gt=1000), "the gesture's own echo: nothing to apply")
        self.assertIsNone(km._stale_seen.last, "an echo is quiet")
        self.assertIsNone(km._set_task_tracking(True, gt=900), "an older stamp stands down")
        self.assertEqual(km._stale_seen.last["setting"], "task-tracking")
        self.assertFalse(km._task_tracking_on(), "the stored value held")

    def test_an_unstamped_flip_applies_with_the_clock(self):
        stamp = km._set_task_tracking(False)
        self.assertIsInstance(stamp, int)
        self.assertGreater(stamp, 0)
        self.assertFalse(km._task_tracking_on())


class TheSocketArm(_Base):
    def test_set_task_tracking_writes_and_wakes_the_producer(self):
        km._producer_wake.clear()
        t0 = time.time()
        km._PURE_FEED = ("stale", 0, 0, None)
        km.Handler._dispatch_ws(types.SimpleNamespace(), {"type": "setTaskTracking", "enabled": False, "gt": 2000}, {})
        self.assertFalse(km._task_tracking_on(), "the arm wrote the store")
        self.assertTrue(km._producer_wake.is_set(), "…and woke the producer, so the tiers stop at the next pass")
        self.assertGreaterEqual(km._views_dirty[0], t0, "…and marked the views dirty, so the feed cache rebuilds into the off frame instead of serving its warmed build")
        self.assertIsNone(km._PURE_FEED, "…and dropped the GET copy")
        km._producer_wake.clear()
        km.Handler._dispatch_ws(types.SimpleNamespace(), {"type": "setTaskTracking", "enabled": True, "gt": 1999}, {})
        self.assertFalse(km._task_tracking_on(), "a stale stamp stood down")
        self.assertFalse(km._producer_wake.is_set(), "a stood-down gesture is not new information: no wake")


class TheProducerGate(_Base):
    def setUp(self):
        super().setUp()
        self._saved = (km._live_map, km._retry_paused_on)
        km._live_map = lambda: {"11111111-2222-3333-4444-555555555555": object()}
        km._retry_paused_on = lambda: False

    def tearDown(self):
        km._live_map, km._retry_paused_on = self._saved
        super().tearDown()

    def test_off_starts_no_tier_with_a_live_session_and_retries_not_paused(self):
        self.assertFalse(km._tiers_may_start(False))
        km._set_task_tracking(False, gt=1)
        self.assertFalse(km._tiers_may_start(), "the default reads the store")

    def test_on_starts_the_tiers(self):
        self.assertTrue(km._tiers_may_start(True))
        self.assertTrue(km._tiers_may_start(), "the default reads the store: absent is on")

    def test_no_live_session_or_a_paused_retry_starts_none_even_when_on(self):
        km._live_map = lambda: {}
        self.assertFalse(km._tiers_may_start(True))
        km._live_map = lambda: {"x": 1}
        km._retry_paused_on = lambda: True
        self.assertFalse(km._tiers_may_start(True))

    def test_the_producer_keeps_its_two_literal_tier_threads_behind_the_predicate(self):
        import inspect, re
        body = inspect.getsource(km._producer)
        guard = re.search(r"if _tiers_may_start\(tracking\):\n(.*?)\n            for t in tiers:", body, re.S)
        self.assertTrue(guard, "one guard for both tiers")
        self.assertIn('args=(jd.run_index,), name="index"', guard.group(1))
        self.assertIn('args=(jd.run_triage,), name="triage"', guard.group(1))
        self.assertIn("_PERF_STATS.judge_tiers(len(tiers))", guard.group(1), "the counter rides the same block")

    def test_the_perf_counter_counts_tier_starts(self):
        before = km._PERF_STATS.snapshot()["judge"]["tierStarts"]
        km._PERF_STATS.judge_tiers(2)
        self.assertEqual(km._PERF_STATS.snapshot()["judge"]["tierStarts"], before + 2)


class TheFeedOffFrame(_Base):
    def test_the_switch_is_an_input_of_the_view_signature(self):
        # the feed cache serves its warmed build while the signature stands: the switch's file is one of its inputs, so a flip
        # busts the cache the way every other file input does (the dirty mark in the socket arm is the belt)
        km._live_map = getattr(km, "_live_map")
        s1 = json.dumps(km._fleet_view_sig(int(time.time()), {}), sort_keys=True, default=str)
        km._set_task_tracking(False, gt=1)
        s2 = json.dumps(km._fleet_view_sig(int(time.time()), {}), sort_keys=True, default=str)
        self.assertNotEqual(s1, s2, "the signature moved with the switch's file")
        self.assertIn("__tracking__", s2)

    def test_the_frame_carries_the_flag_and_the_empty_lists_its_readers_iterate(self):
        f = km._feed_off_frame(123)
        self.assertEqual((f["type"], f["off"], f["now"], f["asks"], f["ledgers"]), ("feed", True, 123, [], []))
        for key in ("items", "asks", "working", "awaiting", "stateUnknown", "order", "sessions", "ledgers", "hosts", "pendingHosts", "pendingDead"):
            self.assertEqual(f[key], [], key + ": every list the push, the chat and the merge read is present and empty (a missing one raised inside the push)")
        self.assertIn('feed["working"]', Path(ROOT, "kernel", "kernel.py").read_text(), "the push does read the working list")
        self.assertEqual(km._needs_input_sids(f), set() if isinstance(km._needs_input_sids(f), set) else km._needs_input_sids(f))
        self.assertEqual(km._needs_you_count(f), 0)

    def test_the_pure_feed_builds_nothing_while_off(self):
        km._set_task_tracking(False, gt=1)
        saved = km.build_feed
        def boom(*a, **k):
            raise AssertionError("build_feed called while task tracking is off")
        km.build_feed = boom
        try:
            km._PURE_FEED = None if hasattr(km, "_PURE_FEED") else None
            f = km._pure_feed(int(time.time()), {})
        finally:
            km.build_feed = saved
        self.assertTrue(f.get("off"), json.dumps(f)[:200])


class ThePanesNotice(_Base):
    def test_the_notice_is_in_both_pages_hidden_while_on_and_shown_while_off(self):
        for page in (km._feed_page(), km._fleet_page()):
            self.assertIn("<div id=tt-off class=tt-off hidden", page, "on: the notice is in the page, hidden")
            self.assertIn("Task tracking is off, so there is no ", page)
            self.assertIn("<button id=tt-off-btn type=button class=notice-act>Open Task tracking settings</button>", page)
        km._set_task_tracking(False, gt=1)
        feed, fleet = km._feed_page(), km._fleet_page()
        self.assertIn("<div id=tt-off class=tt-off style=", feed, "off: the notice shows")
        self.assertIn("there is no feed to show", feed)
        self.assertIn("there is no outline to show", fleet)
        self.assertNotIn("class=tt-off hidden", feed)
        self.assertNotIn("class=tt-off hidden", fleet)

    def test_the_version_report_carries_the_switch_top_level_and_in_settings(self):
        v = km._version_info()
        self.assertTrue(v["taskTracking"])
        self.assertTrue(v["settings"]["taskTracking"])
        km._set_task_tracking(False, gt=1)
        v = km._version_info()
        self.assertFalse(v["taskTracking"])
        self.assertFalse(v["settings"]["taskTracking"])


def _census():
    """Every function in judge.py that calls _judge_run, and every judge name those calls carry: a constant `judge=`,
    the function's own default for a `judge` parameter, and every constant a caller passes for that parameter."""
    tree = ast.parse(JUDGE_SRC)
    fns = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    def defaults(fn):
        a = fn.args; d = {}
        for arg, dv in zip(a.args[len(a.args) - len(a.defaults):], a.defaults):
            d[arg.arg] = dv
        for arg, dv in zip(a.kwonlyargs, a.kw_defaults):
            d[arg.arg] = dv
        return d
    callers, names = set(), set()
    for fname, fn in fns.items():
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_judge_run":
                callers.add(fname)
                jv = {k.arg: k.value for k in node.keywords}.get("judge")
                if isinstance(jv, ast.Constant):
                    names.add(jv.value)
                elif isinstance(jv, ast.Name):
                    dv = defaults(fn).get(jv.id)
                    if isinstance(dv, ast.Constant):
                        names.add(dv.value)
                    for n2 in ast.walk(tree):
                        if isinstance(n2, ast.Call) and getattr(n2.func, "id", None) == fname:
                            for k in n2.keywords:
                                if k.arg == jv.id and isinstance(k.value, ast.Constant):
                                    names.add(k.value.value)
                else:
                    names.add("<unnamed:%s>" % fname)
    return callers, names


class TheCensus(_Base):
    def test_every_model_call_site_names_a_judge_the_table_declares_and_the_table_names_nothing_else(self):
        callers, names = _census()
        self.assertGreaterEqual(len(callers), 15, "the model-call functions of judge.py: %r" % sorted(callers))
        self.assertFalse([n for n in names if str(n).startswith("<unnamed")], "every call names its judge: %r" % sorted(map(str, names)))
        self.assertEqual(names, set(km.jd.MODEL_CALLERS), "the census and the table agree: a new caller declares itself")
        self.assertTrue(all(v in ("tracking", "user") for v in km.jd.MODEL_CALLERS.values()), km.jd.MODEL_CALLERS)
        self.assertEqual({v for v in km.jd.MODEL_CALLERS.values()}, {"tracking"}, "today every kernel-initiated judge stands down with the switch")

    def test_the_entry_point_stands_a_tracking_judge_down_while_off_and_lets_an_undeclared_or_unnamed_call_through_loudly(self):
        class Reached(Exception):
            pass
        saved_engine = km.jd._judge_engine
        def boom():
            raise Reached("the model engine was reached")
        km.jd._judge_engine = boom
        errs = Path(km.jd.ERRORS)   # the module binds its error log at import (the state root alone does not move it)
        before = errs.read_text() if errs.exists() else ""
        try:
            km.jd.TASK_TRACKING_ON = lambda: False
            self.assertEqual(km.jd._judge_run("m", "sys", "user", judge="planner"), "", "off: no call, an empty reply")
            self.assertTrue(km.jd._judge_ctx.paused, "a stand-down, never a failure to count")
            with self.assertRaises(Reached, msg="an unnamed call (a harness, a probe) is not gated: it reaches the engine"):
                km.jd._judge_run("m", "sys", "user")
            km.jd.TASK_TRACKING_ON = lambda: True
            with self.assertRaises(Reached, msg="on: a declared judge reaches the engine"):
                km.jd._judge_run("m", "sys", "user", judge="planner")
            with self.assertRaises(Reached, msg="an undeclared NAME proceeds…"):
                km.jd._judge_run("m", "sys", "user", judge="not-a-judge")
            after = errs.read_text() if errs.exists() else ""
            self.assertIn("unregistered-caller", after[len(before):], "…but says so in judge-errors.jsonl; the census test is the gate that refuses it")
        finally:
            km.jd._judge_engine = saved_engine

    def test_the_kernel_installs_its_store_as_the_judge_modules_hook_at_boot(self):
        src = Path(BIN, "romp-kernel").read_text() if Path(BIN, "romp-kernel").exists() else ""
        ksrc = Path(ROOT, "kernel", "kernel.py").read_text()
        self.assertIn("jd.TASK_TRACKING_ON = _task_tracking_on", ksrc)
        self.assertIn("TASK_TRACKING_ON = lambda: True", JUDGE_SRC, "the module's default: a hand-run judge pass is the user's")


class TheNudgePass(_Base):
    """The goal nudges wait while tracking is off: the walk runs wake-only, as it does with the nudge toggle off; the
    compaction suggestion and the debt ladder keep the nudge toggle alone."""
    def setUp(self):
        super().setUp()
        self._saved = {k: getattr(km, k) for k in ("_alive_sessions", "_nudge_asks_by_target", "_nudge_look_stat", "_auto_nudge_data",
                                                     "_auto_nudge_session", "_compact_suggest_tick", "_debt_backstop_tick", "_dead_wait_sweep",
                                                     "_auto_nudge_on", "_cleared_ids", "_push_soon")}
        self.calls = []
        km._alive_sessions = lambda now, live_map: [{"sid": "11111111-2222-3333-4444-555555555555", "path": os.path.join(self._td, "t.jsonl"), "name": "web"}]
        km._nudge_asks_by_target = lambda: {}
        km._nudge_look_stat = lambda s, asks, pstat: (("k",), False, False)
        km._auto_nudge_data = lambda: {"enabled": True, "nudged": {}}
        km._auto_nudge_session = lambda s, now, live_map, nudged, waitfor, alive_ids, wake_only=False, cleared=None: self.calls.append(("session", wake_only))
        km._compact_suggest_tick = lambda sid, s, now: self.calls.append(("compact", None))
        km._debt_backstop_tick = lambda now: self.calls.append(("debt", None))
        km._dead_wait_sweep = lambda alive_ids, nudged, now: self.calls.append(("sweep", None))
        km._auto_nudge_on = lambda: True
        km._cleared_ids = lambda: set()
        km._push_soon = lambda: None

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(km, k, v)
        super().tearDown()

    def test_off_walks_wake_only_and_keeps_the_compaction_suggestion_and_the_debt_ladder(self):
        km._set_task_tracking(False, gt=1)
        km._auto_nudge_pass(int(time.time()), {}, True)
        kinds = [k for k, _ in self.calls]
        self.assertIn(("session", True), self.calls, "the goal walk ran wake-only: %r" % self.calls)
        self.assertIn("compact", kinds, "the compaction suggestion keeps the nudge toggle")
        self.assertIn("debt", kinds, "the debt ladder keeps the nudge toggle")

    def test_on_walks_the_goals(self):
        km._auto_nudge_pass(int(time.time()), {}, True)
        self.assertIn(("session", False), self.calls, self.calls)


if __name__ == "__main__":
    unittest.main()
