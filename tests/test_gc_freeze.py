#!/usr/bin/env python3
"""Lifecycle validation for the Road B freeze (issue #1735, kernel/gc_freeze.py).

The freeze keeps the loaded decoded heap out of the collector's walk. WHEN to reclaim is MEASURED, not
guessed: every session-end pop registers a weakref to the session with the controller, and the idle
tick judges each by observation (dead ref died by refcount, no reclaim; a live ref whose worker thread
still runs is kept; a live ref whose thread finished is a surviving cycle to reclaim). These tests pin
that judgement's truth table on synthetic refs and a real SdkSession, that every session-end pop
registers the ended session, plus the load fold-in, the backstop, the safe knob parse, the env
switch, a weakref oracle over the freeze, and the pusher glue. Every fixture is synthetic. Real-collector
tests unfreeze in tearDown so the freeze never leaks to another test.
"""
import gc
import importlib.machinery
import json
import os
import sys
import tempfile
import threading
import time
import types
import unittest
import weakref
from datetime import datetime, timezone
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
GC_FREEZE = os.path.join(ROOT, "kernel", "gc_freeze.py")

sys.path.insert(0, os.path.join(ROOT, "tests"))
from romp_load import load_source   # brought in before the state preamble (the mkdtemp hook and TMPDIR redirect ride it)

# hermetic before any romp module load (never load romp modules against live state)
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)
os.makedirs(os.path.join(os.environ["XDG_STATE_HOME"], "romp"), exist_ok=True)
Path(os.environ["XDG_STATE_HOME"], "romp", "session-hosts").write_text("off")
os.environ["ROMP_POSTAL_CLIENT_ONLY"] = "1"

gf = load_source("romp_gc_freeze", GC_FREEZE)


class FakeGc:
    """Records the collector calls a reconcile makes, in order, so the tick logic is pinned without the collector."""
    def __init__(self):
        self.calls = []
    def collect(self, *a):
        self.calls.append("collect")
    def freeze(self):
        self.calls.append("freeze")
    def unfreeze(self):
        self.calls.append("unfreeze")


class TriggerLogic(unittest.TestCase):
    def test_the_load_fold_in_and_the_backstop(self):
        fake = FakeGc()
        c = gf.GcFreeze(enabled=True, load_trees=8, backstop_foldins=2, gc=fake, clock=lambda: 0.0)
        self.assertIsNone(c.tick(inserts=0), "nothing loaded yet: no freeze")
        self.assertEqual(c.tick(inserts=3), "initial", "the first load makes the initial freeze")
        self.assertEqual(fake.calls, ["collect", "freeze"], "the initial freeze collects then freezes, no unfreeze")
        self.assertIsNone(c.tick(inserts=3 + 7), "a load under the threshold does not fold in")
        fake.calls.clear()
        self.assertEqual(c.tick(inserts=3 + 8), "load", "a load past the threshold folds in cheaply")
        self.assertEqual(fake.calls, ["collect", "freeze"], "a load fold-in walks only the unfrozen: no unfreeze")
        self.assertIsNone(c.tick(inserts=3 + 8), "no new load and nothing ended: nothing due (a record-cache pop is not a trigger)")
        # the backstop: after backstop_foldins load fold-ins since the last reclaim, a reclaim runs anyway
        self.assertEqual(c.tick(inserts=3 + 16), "load")   # fold-in 2 -> _foldins at the backstop
        fake.calls.clear()
        self.assertEqual(c.tick(inserts=3 + 16), "backstop", "the backstop reclaims: unfreeze, collect, re-freeze")
        self.assertEqual(fake.calls, ["unfreeze", "collect", "freeze"])
        self.assertIsNone(c.tick(inserts=3 + 16), "the backstop reset _foldins: not due again until the next load or ended cycle")

    def test_a_pre_freeze_ended_ref_is_taken_by_the_initial_collect_not_a_wasted_reclaim(self):
        # a session ended BEFORE the first freeze: the initial collect takes any garbage; no separate reclaim
        fake = FakeGc()
        c = gf.GcFreeze(enabled=True, load_trees=8, gc=fake, clock=lambda: 0.0)
        dead = _Owner()
        c.note_ended(dead, thread=None)
        del dead                                     # the ref is now dead: acyclic, gone
        self.assertEqual(c.tick(inserts=3), "initial", "the first tick freezes; the pre-freeze ended ref is resolved, not reclaimed")
        self.assertEqual(fake.calls, ["collect", "freeze"], "no unfreeze: the initial collect already took any pre-freeze garbage")

    def test_the_env_switch_turns_it_off(self):
        self.assertFalse(gf.enabled_from_env({"ROMP_GC_FREEZE": "off"}))
        self.assertFalse(gf.enabled_from_env({"ROMP_GC_FREEZE": "0"}))
        self.assertTrue(gf.enabled_from_env({}), "on by default")
        self.assertTrue(gf.enabled_from_env({"ROMP_GC_FREEZE": "on"}))
        fake = FakeGc()
        c = gf.GcFreeze(enabled=False, gc=fake)
        self.assertIsNone(c.tick(inserts=100))
        self.assertEqual(fake.calls, [], "a disabled controller never touches the collector")

    def test_the_load_threshold_parses_safely_and_floors_at_one(self):
        self.assertEqual(gf.load_trees_from_env({}), (gf.DEFAULT_LOAD_TREES, None), "absent: the default, no complaint")
        self.assertEqual(gf.load_trees_from_env({"ROMP_GC_FREEZE_LOAD_TREES": "  "}), (gf.DEFAULT_LOAD_TREES, None), "whitespace: the default")
        self.assertEqual(gf.load_trees_from_env({"ROMP_GC_FREEZE_LOAD_TREES": "abc"}), (gf.DEFAULT_LOAD_TREES, "abc"), "a bad value falls back and is named")
        self.assertEqual(gf.load_trees_from_env({"ROMP_GC_FREEZE_LOAD_TREES": "20"}), (20, None))
        self.assertEqual(gf.load_trees_from_env({"ROMP_GC_FREEZE_LOAD_TREES": "0"})[0], 1, "floored at 1")
        self.assertEqual(gf.load_trees_from_env({"ROMP_GC_FREEZE_LOAD_TREES": "-5"})[0], 1, "a negative is floored at 1 too")
        self.assertEqual(gf.GcFreeze(load_trees=0).load_trees, 1, "the controller floors its threshold too")


class _FakeThread:
    def __init__(self, alive):
        self._alive = alive
    def is_alive(self):
        return self._alive


class _Owner:
    """A weakref-able stand-in for an ended session (SimpleNamespace is not weakref-able)."""


class EndedTruthTable(unittest.TestCase):
    """The measured judgement, the verifier's cases a to e (its probe drives real sessions; this pins the decision
    on synthetic weakref-able owners with a controllable worker thread, deterministically). resolve_ended returns
    whether a reclaim is owed, and a reclaim is NEVER owed for a dead ref."""
    def _controller(self):
        return gf.GcFreeze(enabled=True, gc=FakeGc(), clock=lambda: 0.0)

    def test_a_dead_ref_is_acyclic_and_owes_no_reclaim(self):     # (a) run to exit: died by refcount
        c = self._controller()
        s = _Owner()
        c.note_ended(s, thread=_FakeThread(alive=False))
        del s
        self.assertFalse(c.resolve_ended(), "a ref that died by refcount owes no reclaim (acyclic)")
        self.assertEqual(c._ended, [], "and it is dropped")

    def test_a_live_ref_with_a_finished_thread_is_cyclic_and_owes_a_reclaim(self):  # (b) client survives, (e) teardown raise
        c = self._controller()
        s = _Owner()
        c.note_ended(s, thread=_FakeThread(alive=False))
        self.assertTrue(c.resolve_ended(), "a ref still alive with its worker thread finished is a surviving cycle: reclaim")
        self.assertEqual(c._ended, [], "and it is dropped after the reclaim it owes")

    def test_a_live_ref_with_a_running_thread_is_kept_then_reclaimed_when_it_finishes(self):  # (c) kill mid-turn
        c = self._controller()
        s = _Owner()
        th = _FakeThread(alive=True)
        c.note_ended(s, thread=th)
        self.assertFalse(c.resolve_ended(), "a live ref whose thread still runs is not garbage yet: no reclaim")
        self.assertEqual(len(c._ended), 1, "it is kept for the next tick")
        th._alive = False                             # the thread finishes
        self.assertTrue(c.resolve_ended(), "now the thread is finished and the ref is alive: a surviving cycle, reclaim")
        self.assertEqual(c._ended, [], "and dropped")

    def test_the_tick_reclaims_a_real_cyclic_ended_session(self):
        # an executed oracle on a real SdkSession: a live client that refers back is a cycle; ended with a finished
        # thread, the tick reclaims it (unfreeze, collect, re-freeze)
        sbmod = load_source("romp_sdk_backend_ended", os.path.join(ROOT, "kernel", "sdk_backend.py"))
        class StubBackend:
            state_dir = tempfile.mkdtemp()
            def _update_reg(self, *a, **k): pass
            def _log(self, *a, **k): pass
        s = sbmod.SdkSession(StubBackend(), {"sid": "11111111-2222-3333-4444-555555555555", "name": "web", "cwd": "/tmp"})
        class Client: pass
        client = Client(); client.session = s; s.client = client   # the surviving-client cycle
        w = weakref.ref(s)
        fake = FakeGc()
        c = gf.GcFreeze(enabled=True, load_trees=1, gc=fake, clock=lambda: 0.0)
        c.tick(inserts=1)                             # an initial freeze so a reclaim is meaningful
        c.note_ended(s, thread=_FakeThread(alive=False))   # the session ended, its worker thread finished
        del s, client
        fake.calls.clear()
        self.assertEqual(c.tick(inserts=1), "release", "the tick observes the cyclic ended session and reclaims")
        self.assertEqual(fake.calls, ["unfreeze", "collect", "freeze"], "a reclaim unfreezes, collects, re-freezes")
        self.assertIsNotNone(w, "the weakref object outlives (the FakeGc does not actually collect)")


class DoubleController:
    """Records the tick calls, so the pusher tick's guard and error handling are pinned without the collector."""
    def __init__(self, enabled=True, raise_tick=False):
        self.enabled = enabled
        self._raise = raise_tick
        self.ticks = []
    def tick(self, inserts):
        self.ticks.append(inserts)
        if self._raise:
            raise RuntimeError("tick blew up")
        return "load"


class PusherTick(unittest.TestCase):
    """The pusher's idle-boundary seam, pinned in-process (the kernel's call site alone had no teeth)."""
    def _stats(self, inserts=10):
        return lambda: {"inserts": inserts}

    def test_it_ticks_only_on_an_idle_non_first_cycle(self):
        errs = []
        c = DoubleController()
        gf.pusher_tick(c, idle=True, first=False, stats_fn=self._stats(), on_error=errs.append)
        self.assertEqual(len(c.ticks), 1, "an idle, non-first cycle ticks")
        self.assertEqual(c.ticks, [10], "and reads the record cache's insert counter")
        for idle, first in ((True, True), (False, False)):
            c = DoubleController()
            gf.pusher_tick(c, idle=idle, first=first, stats_fn=self._stats(), on_error=errs.append)
            self.assertEqual(c.ticks, [], "the boot's first cycle and a busy cycle never tick: idle=%r first=%r" % (idle, first))
        c = DoubleController(enabled=False)
        gf.pusher_tick(c, idle=True, first=False, stats_fn=self._stats(), on_error=errs.append)
        self.assertEqual(c.ticks, [], "a disabled controller never ticks")
        self.assertEqual(errs, [], "no errors on the happy paths")

    def test_a_raising_stats_read_or_tick_is_handed_to_on_error_and_never_propagates(self):
        errs = []
        def boom():
            raise RuntimeError("cache stats read failed")
        gf.pusher_tick(DoubleController(), idle=True, first=False, stats_fn=boom, on_error=errs.append)   # must not raise
        self.assertEqual(len(errs), 1, "the failing read is counted once")
        errs2 = []
        c = DoubleController(raise_tick=True)
        gf.pusher_tick(c, idle=True, first=False, stats_fn=self._stats(), on_error=errs2.append)   # must not raise
        self.assertEqual(len(errs2), 1, "a raising tick is caught and counted once")
        self.assertEqual(len(c.ticks), 1, "the tick was attempted")

    def test_the_kernels_tick_wrapper_ticks_and_counts_a_raising_tick(self):
        km = load_source("romp_kernel_gcf_tick", os.path.join(BIN, "romp-kernel"))
        saved_gf, saved_stats = km._GC_FREEZE, km.em.record_cache_stats
        saved_errs, saved_said = km._GC_FREEZE_ERRORS[0], km._GC_FREEZE_SAID[0]
        try:
            km.em.record_cache_stats = lambda: {"inserts": 3}
            d = DoubleController()
            km._GC_FREEZE = d
            km._gc_freeze_tick(True, False)
            self.assertEqual(d.ticks, [3], "the kernel tick reads inserts and ticks on an idle non-first cycle")
            d.ticks.clear()
            km._gc_freeze_tick(True, True)
            self.assertEqual(d.ticks, [], "the boot's first cycle does not tick")
            km._GC_FREEZE_ERRORS[0] = 0; km._GC_FREEZE_SAID[0] = False
            km._GC_FREEZE = DoubleController(raise_tick=True)
            km._gc_freeze_tick(True, False)   # must not raise
            self.assertEqual(km._GC_FREEZE_ERRORS[0], 1, "a raising tick is counted through the kernel wrapper")
            self.assertTrue(km._GC_FREEZE_SAID[0], "and said once")
        finally:
            km._GC_FREEZE = saved_gf
            km.em.record_cache_stats = saved_stats
            km._GC_FREEZE_ERRORS[0] = saved_errs; km._GC_FREEZE_SAID[0] = saved_said


class Cyclic:
    """A weakref-able node so a reference cycle can be watched by a weakref oracle."""
    __slots__ = ("other", "__weakref__")


class RealCollector(unittest.TestCase):
    def tearDown(self):
        gc.unfreeze()                                # never leak a freeze to another test
        gc.collect()

    def test_acyclic_dies_by_refcount_a_cycle_reclaims_only_when_the_ended_tick_runs(self):
        c = gf.GcFreeze(enabled=True, load_trees=1, gc=gc)
        acyclic = Cyclic(); acyclic.other = None
        wa = weakref.ref(acyclic)
        c.tick(inserts=1)                            # initial freeze folds `acyclic` in
        del acyclic
        self.assertIsNone(wa(), "an acyclic frozen object dies by refcount when its owner drops it, freeze or no freeze")
        a = Cyclic(); b = Cyclic(); a.other = b; b.other = a
        wcyc = weakref.ref(a)
        c.tick(inserts=2)                            # a load fold-in that freezes the cycle
        c.note_ended(a, thread=_FakeThread(alive=False))   # the cycle's owner ended, its thread finished
        del a, b
        c.tick(inserts=2)                            # the tick observes the cyclic ended ref and reclaims
        self.assertIsNone(wcyc(), "the frozen cycle is reclaimed once the ended tick unfreezes and collects")

    def test_the_kernels_gc_hook_still_counts_the_collections_a_reconcile_runs(self):
        km = load_source("romp_kernel_gcf_hook", os.path.join(BIN, "romp-kernel"))
        st = km._PerfStats()
        st.install_gc_hook()
        try:
            before = st.gc[2][0]
            c = gf.GcFreeze(enabled=True, load_trees=1, gc=gc)
            c.tick(inserts=1)                        # a freeze runs a collection
            self.assertGreater(st.gc[2][0], before, "the kernel's gc hook counted the full collection the freeze ran")
        finally:
            st.remove_gc_hook()

    @staticmethod
    def _make_cycles(n):
        out = []
        for _ in range(n):
            a = Cyclic(); b = Cyclic(); a.other = b; b.other = a
            out.append(a)
        return out                                   # a function scope so no loop variable leaks a reference

    def test_a_warm_collection_after_the_freeze_leaves_the_frozen_cold_cycles_alone(self):
        heap = self._make_cycles(20000)
        watched = [weakref.ref(x) for x in heap[:50]]   # a comprehension: its `x` does not leak into this scope
        c = gf.GcFreeze(enabled=True, load_trees=1, gc=gc)
        c.tick(inserts=1)                            # freeze the cold cycles out of the walk
        del heap
        self._make_cycles(200)                       # a little new (unheld) garbage for the warm collection to walk
        gc.collect()
        self.assertTrue(all(w() is not None for w in watched),
                        "a warm full collection after the freeze does not walk the frozen cold cycles: they survive though nothing holds them")
        self.assertGreater(gc.get_freeze_count(), 20000, "the frozen count shows the cold cycles left the collector's walk")


def _iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _uline(sid, t, text, uid, parent=None):
    return {"type": "user", "timestamp": _iso(t), "uuid": uid, "parentUuid": parent, "sessionId": sid,
            "cwd": "/home/TESTHOST/proj", "message": {"role": "user", "content": text}}


def _aline(sid, t, text, uid, parent):
    return {"type": "assistant", "timestamp": _iso(t), "uuid": uid, "parentUuid": parent, "sessionId": sid,
            "message": {"role": "assistant", "content": [{"type": "text", "text": text}], "stop_reason": "end_turn"}}


class RecordCacheIsAStat(unittest.TestCase):
    """The record cache's `released` counter is a /perf STATISTIC, not a reclaim trigger: its pops release acyclic
    json, freed by refcount. `released` moves on a re-read replacement and an OSError pop, but re-reads (which grow
    inserts and released) drive only cheap load fold-ins, never a reclaim; and a freeze forces no reread."""
    def tearDown(self):
        gc.unfreeze()
        gc.collect()

    def _write(self, d, sid, rows):
        p = os.path.join(d, sid + ".jsonl")
        Path(p).write_text("".join(json.dumps(r) + "\n" for r in rows))
        return p

    def test_released_moves_on_a_pop_and_no_reread_across_a_freeze(self):
        em = load_source("romp_event_model_rel", os.path.join(BIN, "romp-event-model"))
        d = tempfile.mkdtemp()
        sid = "11111111-2222-3333-4444-cccccccc0001"
        rows = [_uline(sid, 1_700_000_000, "ask", "u1"), _aline(sid, 1_700_000_030, "answer", "a1", "u1"),
                _uline(sid, 1_700_000_600, "again", "u2", "a1"), _aline(sid, 1_700_000_630, "ok", "a2", "u2")]
        p = self._write(d, sid, rows)
        em.parse_session(p, rompuuid=sid)
        s1 = em.record_cache_stats()
        rel0 = s1["released"]
        c = gf.GcFreeze(enabled=True, load_trees=1, gc=gc)
        c.tick(int(s1["inserts"]))                   # an initial freeze
        kinds = []
        for k in range(6):                           # six re-reads: append and re-parse, each REPLACES the cache entry
            rows.append(_uline(sid, 1_700_001_000 + k * 100, "more %d" % k, "u%d" % (10 + k), "a2"))
            Path(p).write_text("".join(json.dumps(r) + "\n" for r in rows))
            em.parse_session(p, rompuuid=sid)
            kinds.append(gf.pusher_tick(c, idle=True, first=False, stats_fn=em.record_cache_stats, on_error=lambda e: None))
        s2 = em.record_cache_stats()
        self.assertGreater(s2["released"], rel0, "each re-read replacement popped the old entry: `released` moved (a /perf stat)")
        self.assertNotIn("release", kinds, "a moving `released` under re-reads drives NO reclaim: %r" % kinds)
        self.assertNotIn("backstop", kinds, "and no backstop fired over six re-reads: %r" % kinds)
        self.assertEqual(c.reclaims, 0, "zero reclaims across the run of re-reads (the design's near-zero): %r" % c.reclaims)


class KernelKnob(unittest.TestCase):
    """The kernel-side knob fallback, executed at import: a bad ROMP_GC_FREEZE_LOAD_TREES falls back to the default,
    counts an error and says one line; a 0 is floored to 1 with no error."""
    def _load_with(self, value, name):
        import contextlib, io
        saved = os.environ.get("ROMP_GC_FREEZE_LOAD_TREES")
        os.environ["ROMP_GC_FREEZE_LOAD_TREES"] = value
        err = io.StringIO()
        try:
            with contextlib.redirect_stderr(err):
                km = load_source(name, os.path.join(BIN, "romp-kernel"))
        finally:
            if saved is None:
                os.environ.pop("ROMP_GC_FREEZE_LOAD_TREES", None)
            else:
                os.environ["ROMP_GC_FREEZE_LOAD_TREES"] = saved
        return km, err.getvalue()

    def test_a_bad_knob_falls_back_and_is_said_a_zero_is_floored(self):
        km, err = self._load_with("abc", "romp_kernel_knob_abc")
        self.assertEqual(km._GC_FREEZE_LOAD_TREES, km.gcf.DEFAULT_LOAD_TREES, "abc falls back to the default")
        self.assertGreaterEqual(km._GC_FREEZE_ERRORS[0], 1, "the bad knob is counted under errors")
        self.assertIn("ROMP_GC_FREEZE_LOAD_TREES", err, "and said once on stderr: %r" % err)
        km0, err0 = self._load_with("0", "romp_kernel_knob_zero")
        self.assertEqual(km0._GC_FREEZE_LOAD_TREES, 1, "0 is floored to 1")
        self.assertEqual(km0._GC_FREEZE_ERRORS[0], 0, "a floored 0 is a valid int, no error")
        self.assertEqual(err0, "", "and nothing said for a valid, floored value")


class SessionEndPopsRegister(unittest.TestCase):
    """Every session-end pop registers the ended session with the controller (via _note_ended), so the controller
    measures its cyclicity at the idle tick. Executed: _note_ended reaches the injected note with the session and
    its worker thread. Pinned: exactly three call sites, so deleting a note at any pop (the mutant the verifier
    named) reddens; the truth table above pins the judgement each registered session then gets."""
    def test_the_helper_registers_and_the_three_pop_sites_call_it(self):
        import inspect
        import re as _re
        sbmod = load_source("romp_sdk_backend_pops", os.path.join(ROOT, "kernel", "sdk_backend.py"))
        seen = []
        sbmod.set_ended_note(lambda session, thread: seen.append((session, thread)))
        self.addCleanup(lambda: sbmod.set_ended_note(None))

        class StubBackend:
            state_dir = tempfile.mkdtemp()
            def _update_reg(self, *a, **k):
                pass
            def _log(self, *a, **k):
                pass
        s = sbmod.SdkSession(StubBackend(), {"sid": "11111111-2222-3333-4444-555555555555", "name": "web", "cwd": "/tmp"})
        sbmod._note_ended(s)
        self.assertEqual(len(seen), 1, "_note_ended registers the ended session with the injected note")
        self.assertIs(seen[0][0], s, "the session is passed through")
        self.assertIs(seen[0][1], s.thread, "and its worker thread, for the tick to read is_alive")
        # every session-end pop calls _note_ended: exactly three sites (deleting a call at any pop reddens)
        calls = len(_re.findall(r"\n[ \t]+_note_ended\(", inspect.getsource(sbmod)))
        self.assertEqual(calls, 3, "the three session-end pops (stop, kill, run-to-exit) each call _note_ended: %d" % calls)


class KernelGlue(unittest.TestCase):
    """The kernel wires the ended note at backend load and calls the tick at the pusher's idle boundary."""
    def test_the_pusher_cycle_calls_the_tick_and_the_kernel_wires_the_ended_note(self):
        import inspect
        km = load_source("romp_kernel_gcf_glue", os.path.join(BIN, "romp-kernel"))
        self.assertRegex(inspect.getsource(km._pusher_cycle), r"_gc_freeze_tick\(_cycle_idle, first\)",
                         "the pusher cycle calls the freeze tick with the cycle's idle flag and first-cycle flag")
        self.assertRegex(inspect.getsource(km), r'sbmod = load_source\("romp_sdk_backend"[\s\S]{0,320}?sbmod\.set_ended_note\(_GC_FREEZE\.note_ended\)',
                         "the kernel wires the controller's ended note when it loads the SDK backend")


if __name__ == "__main__":
    unittest.main()
