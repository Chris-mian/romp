#!/usr/bin/env python3
"""T397 (2026-09-12): a boot's first pusher cycle took 59 s against 25 to 33 s all day, and /perf kept only cumulative stage
totals and a ring of whole-cycle durations, so nothing named the stage. The pusher keeps each cycle's stage split (wall, the
reader's bytes, the hydrated bytes), the boot's first for the process under `pusher.firstCycle`, the last cycles in a ring
sized as a fraction of memory under `pusher.stageRing`, and the restart ledger's boot-health row carries the first split."""
import inspect
import io
import os
import sys
import threading
import time
import unittest
from unittest import mock
HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
from test_asm_checkpoint import em, kernel_module   # noqa: E402


JOB_NAME_RE = r"_job_stage\(['\"](\w+)['\"]"   # a wrapped tick job's name, either quote style


class StageSplitUnit(unittest.TestCase):
    def setUp(self):
        self.km = kernel_module()

    def test_the_ring_is_a_fraction_of_memory_never_a_literal(self):
        km = self.km
        self.assertEqual(km._stage_ring_len(64 * 1024 ** 3), 256, "one cycle per 256 MiB: a 64 GB box keeps 256 (about 10 KB an entry)")
        self.assertEqual(km._stage_ring_len(8 * 1024 ** 3), 32)
        self.assertEqual(km._stage_ring_len(4 * 1024 ** 3), 16, "the floor")
        self.assertEqual(km._stage_ring_len(0), 16)
        self.assertGreaterEqual(km._stage_ring_len(), 16, "the machine's reading")
        # round one, low 5: resolved ONCE into a module slot, with an override
        saved = km._STAGE_RING_LEN[0]
        self.addCleanup(lambda: km._STAGE_RING_LEN.__setitem__(0, saved))
        km._STAGE_RING_LEN[0] = None
        with mock.patch.dict(os.environ, {"ROMP_PERF_STAGE_RING": "40"}):
            self.assertEqual(km._stage_ring_len(), 40, "the override names the length")
        with mock.patch.dict(os.environ, {"ROMP_PERF_STAGE_RING": "9000"}):
            self.assertEqual(km._stage_ring_len(), 40, "resolved once: a later environment does not move it")
        km._STAGE_RING_LEN[0] = None
        with mock.patch.dict(os.environ, {"ROMP_PERF_STAGE_RING": "nonsense"}):
            self.assertGreaterEqual(km._stage_ring_len(), 16, "a bad override falls to the memory fraction")

    def test_the_first_cycle_is_kept_and_every_cycle_rides_the_ring(self):
        km = self.km
        ps = km._PerfStats()
        ps.cycle_begin()
        ps.stage("push.chat", 0.010); ps.stage("push", 0.010); ps.stage("jobs", 0.005)
        ps.cycle(0.020)
        ps.cycle_begin()
        ps.stage("jobs", 0.001)
        ps.cycle(0.002)
        snap = ps.snapshot()["pusher"]
        first = snap["firstCycle"]
        self.assertEqual(first["s"], 0.02)
        self.assertEqual(sorted(first["stages"]), ["jobs", "push", "push.chat"])
        self.assertAlmostEqual(first["stages"]["push.chat"]["ms"], 10.0)
        self.assertEqual(set(first["stages"]["jobs"]), {"ms", "bytes", "hydrated"})
        self.assertEqual(len(snap["stageRing"]), 2, "both cycles in the ring")
        self.assertEqual(snap["stageRing"][1]["stages"], {"jobs": {"ms": 1.0, "bytes": 0, "hydrated": 0}})
        self.assertEqual(snap["stageRingMax"], km._stage_ring_len())
        self.assertEqual(snap["stageRingLen"], 2)
        fresh = km._PerfStats().snapshot()
        self.assertIsNone(fresh["pusher"]["firstCycle"], "no cycle yet: no split")
        self.assertEqual(fresh["pusher"]["splitFailed"], 0, "seeded at zero: a row without it means zero, not an older kernel")
        self.assertEqual(fresh["stages_ms"]["prelude"], 0.0, "every stage listed at zero: %r" % sorted(fresh["stages_ms"])[:6])
        self.assertIn("jobs.interruptBlock", fresh["stages_ms"])
        import re
        named = set(re.findall(JOB_NAME_RE, inspect.getsource(km._pusher_cycle_jobs)))
        self.assertEqual(re.findall(JOB_NAME_RE, "_job_stage('a', x); _job_stage(\"b\", y)"), ["a", "b"], "both quote styles (low D)")
        self.assertEqual(named, set(km._PerfStats.JOBS), "the JOBS tuple is the census of the wrapped tick jobs: a new job goes red here")
        self.assertEqual(len(km._PerfStats.JOBS), len(set(km._PerfStats.JOBS)), "no name twice")

    def test_a_stages_bytes_are_the_readers_bytes_since_the_previous_boundary(self):
        km = self.km
        ps = km._PerfStats()
        ps.cycle_begin()
        em._count_read("/lab/a.jsonl", 1000)                 # a read during the jobs before the push
        ps.stage_boundary()                                  # the push begins: those bytes are the jobs'
        em._count_read("/lab/b.jsonl", 250)                  # a read during the chat build
        ps.stage("push.chat", 0.001)
        ps.stage("push", 0.001)
        em._count_read("/lab/c.jsonl", 50)                   # a read during the jobs after the push
        ps.stage("jobs", 0.001)
        ps.cycle(0.003)
        st = ps.snapshot()["pusher"]["firstCycle"]["stages"]
        self.assertEqual(st["push.chat"]["bytes"], 250)
        self.assertEqual(st["push"]["bytes"], 250, "the container carries its sub-stages' bytes")
        self.assertEqual(st["jobs.other"]["bytes"], 1050, "the jobs' glue before and after the push, a sub-stage of jobs")
        self.assertEqual(st["jobs"]["bytes"], 1050, "the container carries its sub-stages' bytes")

    def test_the_split_is_the_pusher_threads_alone(self):
        """Round one, medium: a dashboard's connect push runs _push on the HTTP handler thread through the same stage calls; its
        whole build landed in the pusher cycle's split (a 5 ms cycle reporting a 20 s push.chat), in firstCycle and in the
        boot-health row. The split records the thread that opened the cycle alone; the cumulative totals take every thread."""
        km = self.km
        ps = km._PerfStats()
        ps.cycle_begin()
        ps.stage("push.chat", 0.005); ps.stage("push", 0.005)
        def connect_push():
            ps.stage_boundary(); ps.stage("push.chat", 20.0); ps.stage("push", 20.0)
        th = threading.Thread(target=connect_push); th.start(); th.join()
        ps.stage("jobs", 0.001)
        ps.cycle(0.006)
        first = ps.snapshot()["pusher"]["firstCycle"]
        self.assertEqual(first["stages"]["push.chat"]["ms"], 5.0, "the pusher's own push.chat, not the connect's 20 s")
        self.assertLessEqual(sum(v["ms"] for k, v in first["stages"].items() if k in ("jobs", "push")), first["s"] * 1000.0 + 0.5,
                             "the stages fit the cycle's wall with a second thread pushing mid-cycle")
        self.assertAlmostEqual(ps.snapshot()["stages_ms"]["push.chat"], 20005.0, "the totals took both")

    def test_a_push_in_the_gap_between_cycles_lands_in_no_cycle(self):
        """A connect push between two cycles (on any thread) is not the next cycle's: cycle_begin empties the split."""
        km = self.km
        ps = km._PerfStats()
        ps.cycle_begin(); ps.stage("jobs", 0.001); ps.cycle(0.002)
        ps.stage("push.chat", 9.0); ps.stage("push", 9.0)      # in the gap, on the pusher's own thread even
        ps.cycle_begin(); ps.stage("jobs", 0.002); ps.cycle(0.002)
        ring = ps.snapshot()["pusher"]["stageRing"]
        self.assertEqual(sorted(ring[1]["stages"]), ["jobs"], "the gap's push is in no cycle: %r" % ring[1])

    def test_a_stages_bytes_are_the_pusher_threads_own(self):
        """Round one, low 2: another thread's reads in the window (the judges' first pass, a boot warm) are not the pusher's."""
        km = self.km
        ps = km._PerfStats()
        ps.cycle_begin(); ps.stage_boundary()
        def other_reader():
            em._count_read("/lab/judge.jsonl", 5000)
        th = threading.Thread(target=other_reader); th.start(); th.join()
        em._count_read("/lab/mine.jsonl", 70)
        ps.stage("push.chat", 0.001); ps.stage("push", 0.001); ps.stage("jobs", 0.001); ps.cycle(0.003)
        st = ps.snapshot()["pusher"]["firstCycle"]["stages"]
        self.assertEqual(st["push.chat"]["bytes"], 70, "the pusher thread's own read alone: %r" % st)

    def test_the_boundary_sits_at_the_pushs_entry_before_the_cards_first_path(self):
        """Round one, low 1: on the boot's first cycle the cards-first feed closed push.feedFirst before the boundary, absorbing
        the pre-push jobs' bytes; the boundary is the first thing _push does."""
        src = inspect.getsource(self.km._push)
        self.assertLess(src.index("_PERF_STATS.stage_boundary()"), src.index("_feed_first(now, live_map, targets, connect)"))
        self.assertEqual(src.count("_PERF_STATS.stage_boundary()"), 1)

    def test_a_plain_snapshot_carries_the_newest_splits_and_the_ring_on_request(self):
        """Round one, low 3: the whole ring is up to a few MB of JSON on every GET /perf; a plain snapshot carries the newest
        16 (the ring's floor) and the ring's length, `ring_all` the whole ring, and ms rounded to one decimal."""
        km = self.km
        ps = km._PerfStats()
        for i in range(20):
            ps.cycle_begin(); ps.stage("jobs", 0.0012345); ps.cycle(0.002)
        plain = ps.snapshot()["pusher"]; whole = ps.snapshot(ring_all=True)["pusher"]
        self.assertEqual(len(plain["stageRing"]), km._PerfStats.STAGE_RING_SERVED)
        self.assertEqual((plain["stageRingLen"], len(whole["stageRing"])), (20, 20))
        self.assertEqual(plain["stageRing"][-1]["stages"]["jobs"]["ms"], 1.2, "one decimal")
        src = inspect.getsource(km)
        self.assertIn('_PERF_STATS.snapshot(ring_all=(q.get("ring") or [""])[0] == "all")', src, "GET /perf?ring=all serves the ring")

    def test_the_override_is_clamped_and_the_split_never_ends_the_pusher(self):
        """Round two, low 2: an override above the fraction passed the positive check and deque(maxlen=) raised inside cycle(),
        which runs in the pusher's finally and is caught nowhere, so a diagnostic knob ended the pusher thread for the
        process's life. The override is clamped to the fraction, and the split's bookkeeping never raises (counted)."""
        km = self.km
        saved = km._STAGE_RING_LEN[0]
        self.addCleanup(lambda: km._STAGE_RING_LEN.__setitem__(0, saved))
        km._STAGE_RING_LEN[0] = None
        with mock.patch.dict(os.environ, {"ROMP_PERF_STAGE_RING": str(2 ** 63 - 1)}):
            self.assertEqual(km._stage_ring_len(), km._stage_ring_len(km._mem_total_bytes()), "clamped to the fraction")
        ps = km._PerfStats()
        real = km._stage_ring_len
        km._stage_ring_len = lambda mem_total=None: 2 ** 70                 # a length the deque refuses
        self.addCleanup(setattr, km, "_stage_ring_len", real)
        ps.cycle_begin(); ps.stage("jobs", 0.001)
        ps.cycle(0.002)                                                    # no raise
        self.assertEqual(ps.snapshot()["pusher"].get("splitFailed"), 1)

    def test_every_tick_job_is_a_sub_stage_and_the_report_total_is_the_counter(self):
        """T398: the first live split said jobs 25 s with 224 MB read and nothing finer; every tick job closes its own
        `jobs.<job>` stage, the container carries their sum. Round two, low 1: the report's total is the running counter."""
        km = self.km
        ps = km._PerfStats()
        ps.cycle_begin()
        em._count_read("/lab/tick.jsonl", 300)
        ps.stage("jobs.interruptBlock", 0.004)
        ps.stage("jobs.autoNudge", 0.001)
        ps.stage("jobs", 0.006)
        ps.cycle(0.007)
        st = ps.snapshot()["pusher"]["firstCycle"]["stages"]
        self.assertEqual(st["jobs.interruptBlock"]["bytes"], 300)
        self.assertEqual(st["jobs"]["bytes"], 300, "the container carries its sub-stages' bytes")
        self.assertIn("_job_stage('interruptBlock', lambda: _interrupt_block_tick(now, live_map))", inspect.getsource(km._pusher_cycle_jobs))
        rep = em.read_bytes_report()
        self.assertEqual(rep["total"], em.read_bytes_total())
        self.assertGreaterEqual(rep["total"], sum(v for k, v in rep.items() if k != "total"))


class LabBootFirstCycle(unittest.TestCase):
    """A lab boot whose first cycle runs at least two stages: the real pusher cycle with every tick job a no-op and the push a
    short sleep, over a hermetic kernel module; the split names both stages, and the boot-health row carries it."""
    JOBS = ("_judge_tick", "_nudge_tick", "_reconcile_tick")

    def setUp(self):
        self.km = km = kernel_module()
        self.saved = (km.NAMES, km._live_map, km._push_all, km._append_restart_cut, km._BOOT_HEALTH_DONE[0])
        km.NAMES = {}
        km._live_map = lambda: {}
        self.rows = []
        km._append_restart_cut = lambda row: self.rows.append(row)
        km._BOOT_HEALTH_DONE[0] = False
        km._PERF_STATS.reset()
        self.saved_sampler = dict(km._FIRST_CYCLE_SAMPLER)               # the sampler's slot, restored after (round two, low 5)
        km._FIRST_CYCLE_SAMPLER.update({"started": False, "stop": threading.Event(), "rows": [], "thread": None, "failed": 0})

    def tearDown(self):
        km = self.km
        km.NAMES, km._live_map, km._push_all, km._append_restart_cut, km._BOOT_HEALTH_DONE[0] = self.saved
        km._FIRST_CYCLE_SAMPLER.clear(); km._FIRST_CYCLE_SAMPLER.update(self.saved_sampler)
        km._PERF_STATS.reset()

    def test_the_boot_row_carries_the_pushers_stack_samples_from_the_first_cycle_only(self):
        """T401 (3): two live reads of a slow first cycle were missed because the /perf stack sample could not be taken in time.
        The pusher's stack is sampled once a second during the boot's first cycle by a daemon thread that ends with it, and the
        samples ride the boot-health row as firstCycleStacks (seconds into the cycle, the stage mark, the innermost frames); a
        later cycle adds nothing and writes no row."""
        km = self.km
        km._push_all = km._stage_marked("push")(lambda live_map=None: time.sleep(2.3))   # marked as the real push is
        with km._clients_lock:                                             # a client, so the cycle pushes (the sleep above)
            km._clients.append({"app": "feed", "wid": "lab", "send": lambda *a, **k: None, "alive": True})
        self.addCleanup(lambda: [km._clients.remove(c) for c in list(km._clients) if c.get("wid") == "lab"])
        km._pusher_cycle()
        self.assertEqual(len(self.rows), 1, "one boot-health row")
        samples = self.rows[0].get("firstCycleStacks")
        self.assertIsInstance(samples, list, "the row carries the samples: %r" % sorted(self.rows[0]))
        self.assertGreaterEqual(len(samples), 2, "one a second through a 2.3 s cycle: %r" % samples)
        self.assertLessEqual(len(samples), km.FIRST_CYCLE_SAMPLES_MAX)
        for row in samples:
            self.assertEqual(set(row), {"t", "stage", "frames"}, row)
            self.assertTrue(all(isinstance(f, str) and " (" in f and f.endswith(")") for f in row["frames"]), row["frames"])
            self.assertLessEqual(len(row["frames"]), km.FIRST_CYCLE_SAMPLE_FRAMES)
        self.assertIn("push", [row["stage"] for row in samples], "a sample taken during the push carries the pusher's stage mark")
        waited = [row for row in samples if row["frames"] and "test_first_cycle_stage_split.py" in row["frames"][-1]]
        self.assertTrue(waited, "the innermost Python frame names where the cycle waited (the stubbed push; time.sleep itself is C): %r"
                        % [row["frames"][-1:] for row in samples])
        self.assertTrue(any("_pusher_cycle" in f for f in waited[0]["frames"]), "walked from the cycle: %r" % waited[0]["frames"])
        self.assertFalse(any(t.name == "first-cycle-sampler" for t in threading.enumerate()), "the sampler ended with the cycle")
        n = len(km._FIRST_CYCLE_SAMPLER["rows"])
        km._push_all = lambda live_map=None: time.sleep(1.2)
        km._pusher_cycle()
        self.assertEqual(len(self.rows), 1, "a later cycle writes no row")
        self.assertEqual(len(km._FIRST_CYCLE_SAMPLER["rows"]), n, "and adds no sample")
        self.assertFalse(any(t.name == "first-cycle-sampler" for t in threading.enumerate()))

    def _marked_push(self, seconds):
        km = self.km
        km._push_all = km._stage_marked("push")(lambda live_map=None: time.sleep(seconds))
        with km._clients_lock:
            km._clients.append({"app": "feed", "wid": "lab", "send": lambda *a, **k: None, "alive": True})
        self.addCleanup(lambda: [km._clients.remove(c) for c in list(km._clients) if c.get("wid") == "lab"])

    def test_a_sampler_thread_that_cannot_start_leaves_the_cycle_and_the_row_intact(self):
        """Round two, MEDIUM: the sampler's start was an unguarded statement in the cycle's prologue, before the cycle's try,
        and the pusher loop has no watchdog, so a start that raised (no thread slot at boot) would have ended the pusher for
        the process's life: no push, no tick job, no boot-health row. The start degrades to no samples with one stderr line,
        the thread is stored only once started, and the cycle completes and writes its row."""
        km = self.km
        self._marked_push(0.05)
        err = io.StringIO()
        with mock.patch.object(threading.Thread, "start", side_effect=RuntimeError("can't start new thread")), \
             mock.patch.object(sys, "stderr", err):
            km._pusher_cycle()                                                 # must not raise
        self.assertEqual(len(self.rows), 1, "the boot-health row was written")
        self.assertEqual(self.rows[0].get("firstCycleStacks"), [], "with no samples")
        self.assertIn("first-cycle sampler: not started", err.getvalue())
        self.assertIsNone(km._FIRST_CYCLE_SAMPLER["thread"], "nothing unstarted is stored, so the stop joined nothing")
        km._pusher_cycle()                                                     # the pusher goes on
        self.assertEqual(len(self.rows), 1)

    def test_a_failed_frame_walk_is_counted_and_sampling_goes_on(self):
        """Round two, low 4: one transient exception in the walk ended sampling for the boot, and a short list read as a fast
        cycle. The failure is counted (firstCycleStacksFailed on the row) and the next second samples again."""
        km = self.km
        self._marked_push(2.3)
        real = km._first_cycle_sample; calls = []
        def flaky(tid, t0):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("frame gone")
            return real(tid, t0)
        with mock.patch.object(km, "_first_cycle_sample", flaky):
            km._pusher_cycle()
        row = self.rows[0]
        self.assertEqual(row.get("firstCycleStacksFailed"), 1, sorted(row))
        self.assertGreaterEqual(len(row["firstCycleStacks"]), 1, "sampling went on after the failure: %r" % calls)

    def test_failed_walks_fill_the_cap_too(self):
        """1588 follow-up, low 4: a failed walk consumed an interval but not a cap slot, so an all-failing sampler woke every
        interval for the whole cycle instead of retiring with the cap."""
        km = self.km
        self._marked_push(1.5)
        calls = []
        def failing(tid, t0):
            calls.append(1); raise RuntimeError("frame gone")
        with mock.patch.object(km, "_first_cycle_sample", failing), mock.patch.object(km, "FIRST_CYCLE_SAMPLE_S", 0.1), \
             mock.patch.object(km, "FIRST_CYCLE_SAMPLES_MAX", 3):
            km._pusher_cycle()
        self.assertEqual(len(calls), 3, "three failed walks filled the cap and the sampler retired: %r" % calls)
        self.assertEqual(self.rows[0].get("firstCycleStacksFailed"), 3)
        self.assertEqual(self.rows[0]["firstCycleStacks"], [])

    def test_a_cycle_that_raises_is_counted_and_the_pusher_loop_goes_on(self):
        """The standing gap: _pusher called _pusher_cycle bare, and _live_map, the scopes' close and the boot row sit outside
        the cycle's try, so one raise there ended the pusher for the process's life, silently. The loop catches the cycle's
        raise, counts it under pusher.cycleFailed, says it once per exception kind, and goes on to the next cycle."""
        km = self.km
        import io
        n = [0]
        def cycle():
            n[0] += 1
            if n[0] <= 2:
                raise RuntimeError("no thread slot")
            km._LOOPS_STOP.set()
        err = io.StringIO()
        saved_stop = km._LOOPS_STOP.is_set()
        with mock.patch.object(km, "_pusher_cycle", cycle), mock.patch.object(km, "_PUSHER_FAILED_SAID", {}), \
             mock.patch.object(km.sys, "stderr", err), mock.patch.dict(km._PERF_STATS.pusher, {"cycleFailed": 0}):
            try:
                km._pusher()
                self.assertEqual(n[0], 3, "two raising cycles were skipped and the third ran")
                self.assertEqual(km._PERF_STATS.pusher["cycleFailed"], 2)
            finally:
                if not saved_stop:
                    km._LOOPS_STOP.clear()
        self.assertEqual(err.getvalue().count("pusher: a cycle raised RuntimeError"), 1, "said once per kind: %r" % err.getvalue())
        self.assertIn("cycleFailed", km._PERF_STATS.snapshot()["pusher"])

    def test_a_failing_cycle_that_woke_the_pusher_itself_retries_at_a_pace(self):
        """Round two, medium 2: the failure path fell through to the same wake wait as success, and that wait returns at once
        while the wake flag stands; tick jobs set it on the pusher's own thread during the cycle, so a cycle that set the
        flag then raised retried half a million times a second (a whole core). The guard clears the wake and paces the retry
        at the backstop, doubling to five seconds until a clean cycle; the counter goes through _PERF_STATS' locked method."""
        km = self.km
        n = [0]
        def cycle():
            n[0] += 1
            km._pusher_wake.set()                                          # a tick job's writer woke the pusher...
            raise RuntimeError("broken stderr")                            # ...and then the cycle raised
        saved_stop = km._LOOPS_STOP.is_set(); km._LOOPS_STOP.clear()
        timer = threading.Timer(1.0, km._LOOPS_STOP.set); timer.start()
        t0 = time.thread_time()
        try:
            with mock.patch.object(km, "_pusher_cycle", cycle), mock.patch.object(km, "_PUSHER_FAILED_SAID", {}), \
                 mock.patch.object(km.sys, "stderr", io.StringIO()), mock.patch.dict(km._PERF_STATS.pusher, {"cycleFailed": 0}):
                km._pusher()
                cpu = time.thread_time() - t0
                self.assertLess(n[0], 10, "the retries are paced, not spun: %d cycles in a second" % n[0])
                self.assertLess(cpu, 0.2, "and cost no core: %.3f s of thread CPU" % cpu)
                self.assertEqual(km._PERF_STATS.pusher["cycleFailed"], n[0])
        finally:
            timer.cancel()
            if saved_stop: km._LOOPS_STOP.set()
            else: km._LOOPS_STOP.clear()
        self.assertTrue(callable(getattr(km._PERF_STATS, "cycle_failed", None)), "the counter has a locked method like wake and cycle")
        self.assertEqual(km.PUSHER_FAIL_BACKOFF_S[-1], 5.0)

    def test_the_interval_widens_after_the_dense_samples(self):
        """Round two, low 3: sixty one-second samples kept the first minute and dropped the rest, so an 84 s cycle never showed
        where it ended; after FIRST_CYCLE_SAMPLE_DENSE samples the interval is FIRST_CYCLE_SAMPLE_WIDE_S, and the cap covers
        three minutes."""
        km = self.km
        self._marked_push(1.4)
        with mock.patch.object(km, "FIRST_CYCLE_SAMPLE_S", 0.2), mock.patch.object(km, "FIRST_CYCLE_SAMPLE_DENSE", 2, create=True), \
             mock.patch.object(km, "FIRST_CYCLE_SAMPLE_WIDE_S", 0.5, create=True):   # create=True: at a base without the widening the
            #                                                                            red is the GAP, not an AttributeError (1588 low 3)
            km._pusher_cycle()
        ts = [row["t"] for row in self.rows[0]["firstCycleStacks"]]
        self.assertGreaterEqual(len(ts), 3, ts)
        self.assertLess(ts[1] - ts[0], 0.45, "dense at first: %r" % ts)
        self.assertGreaterEqual(ts[2] - ts[1], 0.45, "then wide: %r" % ts)
        self.assertEqual(km.FIRST_CYCLE_SAMPLE_DENSE * km.FIRST_CYCLE_SAMPLE_S
                         + (km.FIRST_CYCLE_SAMPLES_MAX - km.FIRST_CYCLE_SAMPLE_DENSE) * km.FIRST_CYCLE_SAMPLE_WIDE_S, 180.0,
                         "the cap covers three minutes")

    def test_the_boots_first_cycle_names_its_stages(self):
        km = self.km
        km._push_all = lambda live_map=None: time.sleep(0.005)
        t0 = time.monotonic()
        km._pusher_cycle_jobs(int(time.time()), {}, True)
        dt = time.monotonic() - t0
        km._PERF_STATS.cycle(dt)
        km._boot_health_first_cycle(dt)
        snap = km._PERF_STATS.snapshot()["pusher"]
        first = snap["firstCycle"]
        self.assertIsNotNone(first, "the first cycle's split is kept")
        self.assertTrue({"jobs", "push"} <= set(first["stages"]), "both stages named: %r" % sorted(first["stages"]))
        self.assertTrue(any(k.startswith("jobs.") for k in first["stages"]), "the tick jobs as sub-stages: %r" % sorted(first["stages"]))
        self.assertGreaterEqual(first["stages"]["push"]["ms"], 5.0)
        self.assertLessEqual(sum(v["ms"] for k, v in first["stages"].items() if k in ("jobs", "push")), first["s"] * 1000.0 + 5.0,
                             "the stages fit the cycle's wall")
        self.assertEqual(len(self.rows), 1, "one boot-health row")
        self.assertEqual(sorted(self.rows[0]["stages"]), sorted(first["stages"]), "the row carries the split")
        self.assertEqual(self.rows[0]["firstCycleS"], round(dt, 2))


    def test_a_whole_pusher_cycle_names_its_prelude_and_the_stages_sum_to_the_wall(self):
        """Round two, low 3: cycle_begin was the jobs' first statement, so the liveness snapshot and the names before it had
        no bucket and the stages under-summed the cycle. The cycle opens at the top of _pusher_cycle and the prelude is a
        stage, so prelude + jobs + push fit the wall."""
        km = self.km
        km._push_all = lambda live_map=None: time.sleep(0.003)
        with km._clients_lock:                                             # a client, so the cycle pushes (any_client)
            km._clients.append({"app": "feed", "wid": "lab", "send": lambda *a, **k: None, "alive": True})
        self.addCleanup(lambda: [km._clients.remove(c) for c in list(km._clients) if c.get("wid") == "lab"])
        km._pusher_cycle()
        first = km._PERF_STATS.snapshot()["pusher"]["firstCycle"]
        self.assertIsNotNone(first)
        st = first["stages"]
        self.assertIn("prelude", st, "%r" % sorted(st))
        self.assertGreaterEqual(st["push"]["ms"], 3.0, "the push ran (a client was connected): %r" % sorted(st))
        top = sum(v["ms"] for k, v in st.items() if k in ("prelude", "jobs", "push"))
        self.assertLessEqual(top, first["s"] * 1000.0 + 2.0, "the top stages fit the wall: %r vs %r" % (top, first["s"]))
        self.assertGreaterEqual(top, first["s"] * 1000.0 * 0.8, "and account for most of it: %r vs %r" % (top, first["s"]))


if __name__ == "__main__":
    unittest.main()
