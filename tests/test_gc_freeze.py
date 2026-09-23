#!/usr/bin/env python3
"""Lifecycle validation for the Road B freeze (issue #1735, kernel/gc_freeze.py).

The freeze keeps the loaded decoded heap out of the collector's walk. WHEN to reclaim is MEASURED, not
guessed: every session-end pop registers a weakref to the session with the controller, and the idle
tick judges each by observation (dead ref died by refcount, no reclaim; a live ref whose worker thread
still runs is kept; a live ref whose thread finished is a surviving cycle to reclaim, or a ref a live root keeps, which reads the same, costs one reclaim and is counted a survivor). These tests pin
that judgement's truth table on synthetic refs and a real SdkSession, that every session-end pop
registers the ended session, plus the load fold-in, the backstop, the safe knob parse, the env
switch, a weakref oracle over the freeze, and the pusher glue. Every fixture is synthetic. Real-collector
tests unfreeze in tearDown so the freeze never leaks to another test.
"""
import gc
import json
import os
import sys
import tempfile
import threading
import time
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
        # PR 1999 review: a RELEASE resets the fold-in counter too (not only a backstop). After a release, the next backstop
        # needs a FULL backstop_foldins loads; guarding the reset on kind=="backstop" alone would fire the backstop a load early.
        ins = 3 + 24
        self.assertEqual(c.tick(inserts=ins), "load", "one load fold-in since the backstop (_foldins -> 1)")
        owner = _Owner()                                          # held in a local: alive with a finished worker -> owed (the FakeGc collect is a no-op)
        fin = _FakeThread(alive=False)   # a local, so the weakref resolves and is_alive() False is what decides (review PR 2042 low)
        c.note_ended(owner, thread=fin)
        self.assertEqual(c.tick(inserts=ins), "release", "the owed cyclic ref reclaims and resets _foldins")
        ins += 8; self.assertEqual(c.tick(inserts=ins), "load", "fold-in 1 since the release")
        ins += 8; self.assertEqual(c.tick(inserts=ins), "load", "fold-in 2 since the release: still a load, not an early backstop")
        self.assertEqual(c.tick(inserts=ins), "backstop", "now the backstop fires: a full backstop_foldins loads since the release")

    def test_a_pre_freeze_ended_ref_is_taken_by_the_initial_collect_not_a_wasted_reclaim(self):
        # a session ended BEFORE the first freeze: the initial collect takes any garbage; no separate reclaim. Both a dead
        # ref and a LIVE ref (with a finished worker, both kept in locals) are registered before the first tick, so the pin
        # fails if the release branch is moved ahead of the initial-freeze check (the live ref would then drive an unfreeze).
        fake = FakeGc()
        c = gf.GcFreeze(enabled=True, load_trees=8, gc=fake, clock=lambda: 0.0)
        dead = _Owner()
        c.note_ended(dead, thread=None)
        del dead                                     # the ref is now dead: acyclic, gone
        live = _Owner(); fin = _FakeThread(alive=False)   # a LIVE pre-freeze ref with a finished worker, both in locals
        c.note_ended(live, thread=fin)
        self.assertEqual(c.tick(inserts=3), "initial", "the first tick freezes; the pre-freeze ended refs are judged then, not a separate reclaim")
        self.assertEqual(fake.calls, ["collect", "freeze"], "no unfreeze: the initial collect already took any pre-freeze garbage")
        self.assertEqual(c._ended, [], "the pre-freeze refs are consumed by the initial judgement, never carried")
        self.assertIsNone(c.tick(inserts=3), "a second tick with nothing new is None: the pre-freeze refs did not linger into a reclaim")

    def test_the_env_switch_turns_it_off(self):
        self.assertFalse(gf.enabled_from_env({"ROMP_GC_FREEZE": "off"}))
        self.assertFalse(gf.enabled_from_env({"ROMP_GC_FREEZE": "0"}))
        self.assertTrue(gf.enabled_from_env({}), "on by default")
        self.assertTrue(gf.enabled_from_env({"ROMP_GC_FREEZE": "on"}))
        fake = FakeGc()
        c = gf.GcFreeze(enabled=False, gc=fake)
        self.assertIsNone(c.tick(inserts=100))
        self.assertEqual(fake.calls, [], "a disabled controller never touches the collector")
        fin = _FakeThread(alive=False)   # a local, so the weakref resolves and is_alive() False is what decides (review PR 2042 low)
        c.note_ended(_Owner(), thread=fin)   # PR 1999 review: note_ended early-returns when disabled
        self.assertEqual(c._ended, [], "a disabled controller registers no ended session (else it would leak a pair per end for the process life)")

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
        fin = _FakeThread(alive=False)   # a local, so the weakref resolves and is_alive() False is what decides (review PR 2042 low)
        c.note_ended(s, thread=fin)
        del s
        self.assertFalse(c.resolve_ended(), "a ref that died by refcount owes no reclaim (acyclic)")
        self.assertEqual(c._ended, [], "and it is dropped")

    def test_a_live_ref_with_a_finished_thread_is_cyclic_and_owes_a_reclaim(self):  # (b) client survives, (e) teardown raise
        c = self._controller()
        s = _Owner()
        fin = _FakeThread(alive=False)                # a local, so tref() resolves and is_alive() False is what decides (not a dead tref)
        c.note_ended(s, thread=fin)
        self.assertTrue(c.resolve_ended(), "a ref still alive with its worker thread finished is a surviving cycle: reclaim")
        self.assertEqual(c._ended, [], "and it is dropped after the reclaim it owes")

    def test_a_sid_less_owed_root_yields_one_empty_string_by_equality(self):
        """PR 2042 review (attribution): a sid-less owed root gathers one empty string into last_release_sids, so assert by
        EQUALITY, never truthiness (a truthiness check would pass a bug that gathered nothing; [''] is truthy but wrong)."""
        c = self._controller()
        s = _Owner()                                  # no `.sid`
        fin = _FakeThread(alive=False)
        c.note_ended(s, thread=fin)
        self.assertTrue(c.resolve_ended())
        self.assertEqual(c.last_release_sids, [""], "one owed root with no sid: exactly one empty string, by equality: %r" % c.last_release_sids)

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
        # thread, the STAGED release runs (collect with the freeze in place, then unfreeze + collect, then re-freeze).
        # The session's own never-started worker Thread would keep it alive by its `_target`, so the CLIENT cycle would
        # be redundant; rebind s.thread to a finished stand-in before the registration so the client cycle is the sole
        # keeper (review PR 1999 tests). Under gc.disable() so a young-generation collect cannot take it before the read.
        sbmod = load_source("romp_sdk_backend_ended", os.path.join(ROOT, "kernel", "sdk_backend.py"))
        class StubBackend:
            state_dir = tempfile.mkdtemp()
            def _update_reg(self, *a, **k): pass
            def _log(self, *a, **k): pass
        gc.disable()
        self.addCleanup(gc.enable)
        s = sbmod.SdkSession(StubBackend(), {"sid": "11111111-2222-3333-4444-555555555555", "name": "web", "cwd": "/tmp"})
        s.thread = _FakeThread(alive=False)           # a finished stand-in, holding nothing: the client cycle alone keeps s alive
        class Client: pass
        client = Client(); client.session = s; s.client = client   # the surviving-client cycle
        w = weakref.ref(s)
        fake = FakeGc()
        c = gf.GcFreeze(enabled=True, load_trees=1, gc=fake, clock=lambda: 0.0)
        c.tick(inserts=1)                             # an initial freeze so a reclaim is meaningful
        c.note_ended(s, thread=s.thread)              # the session ended, its worker thread finished
        del s, client
        fake.calls.clear()
        self.assertEqual(c.tick(inserts=1), "release", "the tick observes the cyclic ended session and reclaims")
        self.assertEqual(fake.calls, ["collect", "unfreeze", "collect", "freeze"],
                         "the staged release: a cheap collect with the freeze in place, then unfreeze + collect (a survivor under the no-op fake), then re-freeze")
        self.assertIsNotNone(w(), "the cyclic session stays alive under the FakeGc (its collect is a no-op): this pins the reconcile KIND, not the collection")


class EndedLockConcurrency(unittest.TestCase):
    """LOW 1, the concurrency fix, pinned DETERMINISTICALLY (no wall-clock, no statistical race). resolve_ended sets
    self._ended = keep and judges the OLD list under _ended_lock, so a note_ended landing on another thread mid-judgement
    blocks and lands in the NEW list, never in the old one the judgement is consuming. A stub worker thread whose is_alive()
    pauses the judgement mid-flight while the lock is held; a second registration then lands only AFTER the judgement
    returns, unjudged in the live list, and is judged at the NEXT tick. At affd9abf there is no lock: resolve_ended iterates
    self._ended live and rebinds after the loop, so a registration landing mid-judgement is consumed by the index-based loop
    and the rebind drops it (this test reds there by copy-aside; the red is quoted in the PR body)."""

    class _Gate:
        """A stand-in worker thread: is_alive() signals it has paused the judgement, then blocks until released, then reads
        as still running (so the paused owner is KEPT, never itself a reclaim)."""
        def __init__(self, entered, release):
            self._entered, self._release = entered, release
            self.released = None                          # set True when the gate was released, False on a pathological timeout (PR 1999 round-four low)
        def is_alive(self):
            self._entered.set()
            self.released = self._release.wait(30)        # a generous bound; the test asserts it was RELEASED, not a vacuous timeout
            return True

    def test_resolve_ended_holds_the_lock_so_a_concurrent_registration_is_never_dropped(self):
        c = gf.GcFreeze(enabled=True, gc=FakeGc(), clock=lambda: 0.0)
        entered, release, at_lock = threading.Event(), threading.Event(), threading.Event()
        self.addCleanup(release.set)                              # PR 1999 round-four low: a failed pre-release assertion must still free R, not park it to the bound
        o1, o2 = _Owner(), _Owner()
        gate = self._Gate(entered, release)                       # a strong ref: the controller keeps only a weakref to the thread
        fin = _FakeThread(alive=False)                            # P2's finished worker thread (a strong ref, likewise)
        c.note_ended(o1, thread=gate)                             # P1: its is_alive pauses the judgement mid-flight
        box = {}
        R = threading.Thread(target=lambda: box.__setitem__("reclaim1", c.resolve_ended()), daemon=True)
        R.start()
        self.assertTrue(entered.wait(10), "the judgement reached P1 and paused mid-flight")
        # a second session ends WHILE the judgement is mid-flight; its worker thread has finished, so were it judged in this
        # pass it would owe a reclaim and leave the live list. It must not be: the lock holds the old list steady.
        lock = getattr(c, "_ended_lock", None)
        if lock is not None:                                       # the head: note_ended blocks on the lock; spy it to know it arrived
            real = lock                                            # R already holds the real lock (acquired before this swap); the spy sees only B's acquire
            class _SpyLock:
                def acquire(self, *a, **k):
                    at_lock.set()                                  # the concurrent note_ended has reached the lock (and will block: R holds it)
                    return real.acquire(*a, **k)
                def release(self): return real.release()
                def __enter__(self): self.acquire(); return self
                def __exit__(self, *a): self.release()
            c._ended_lock = _SpyLock()
            B = threading.Thread(target=lambda: c.note_ended(o2, thread=fin), daemon=True)
            B.start()
            self.assertTrue(at_lock.wait(10), "the concurrent note_ended reached the lock while the judgement held it")
            release.set()
            R.join(10); B.join(10)
        else:                                                      # affd9abf: no lock; the append lands unguarded, mid-loop, on this thread
            c.note_ended(o2, thread=fin)
            release.set()
            R.join(10)
        self.assertFalse(box["reclaim1"], "the judgement returned before the append landed: it judged only P1 (kept), never the "
                                          "mid-flight registration (at affd9abf the live loop consumed it and returned a reclaim)")
        self.assertTrue(any(sref() is o2 for sref, _ in c._ended), "the mid-judgement registration sits in the live list, never dropped")
        # judged at the NEXT tick: P2 is alive with a finished thread, so it owes a reclaim then and is dropped
        self.assertTrue(c.resolve_ended(), "the next tick judges the kept registration: a surviving cycle owes its reclaim")
        self.assertFalse(any(sref() is o2 for sref, _ in c._ended), "and P2 is dropped after the reclaim it owes")
        self.assertTrue(gate.released, "the gate was RELEASED mid-flight, not a vacuous 30 s timeout (PR 1999 round-four low)")


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

    def test_the_kernel_wrapper_writes_one_line_per_release_naming_the_session_none_per_load(self):
        """PR 1999 review (attribution 6): a release means a session ended with a surviving cycle and a full-heap pause;
        the kernel wrapper writes one stderr line per release naming the resolved sid(s) off last_release_sids, and none
        on a load tick."""
        import contextlib, io
        km = load_source("romp_kernel_gcf_rel", os.path.join(BIN, "romp-kernel"))
        saved_gf, saved_stats = km._GC_FREEZE, km.em.record_cache_stats

        class _RelController:
            def __init__(self, kind, survivors=0, kept=None):
                self.enabled = True; self._kind = kind
                self.last_release_sids = ["deadbeef"]; self.last_ms = 1.2
                self.last_release_survivors = survivors; self.last_kept_sids = kept or []
            def tick(self, inserts):
                return self._kind
        def _line(controller):
            km._GC_FREEZE = controller
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                km._gc_freeze_tick(True, False)
            return err.getvalue()
        try:
            km.em.record_cache_stats = lambda: {"inserts": 3}
            # a real reclaim (nothing survived): the line reads "reclaimed" and names the owed sid
            out = _line(_RelController("release", survivors=0))
            self.assertEqual(out.count("\n"), 1, "exactly one line per release: %r" % out)
            self.assertIn("deadbeef", out, "the release line names the ended session: %r" % out)
            self.assertIn("reclaimed", out)
            # PR 2042 review: the LIVE-ROOT case (a survivor) freed nothing: the line names the KEPT sids as kept by a live
            # root, never "reclaimed" (the base wrote "reclaimed a surviving cycle" for this case too)
            out2 = _line(_RelController("release", survivors=1, kept=["cafef00d"]))
            self.assertEqual(out2.count("\n"), 1, "exactly one line for the kept case: %r" % out2)
            self.assertIn("cafef00d", out2, "the kept case names the kept sid: %r" % out2)
            self.assertIn("live root", out2, "the kept case says kept by a live root: %r" % out2)
            self.assertNotIn("reclaimed", out2, "the kept case freed nothing: never 'reclaimed': %r" % out2)
            # a load tick writes no release line
            self.assertEqual(_line(_RelController("load")), "", "a load tick writes no release line")
        finally:
            km._GC_FREEZE = saved_gf
            km.em.record_cache_stats = saved_stats


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
        fin = _FakeThread(alive=False)   # a local, so the weakref resolves and is_alive() False is what decides (review PR 2042 low)
        c.note_ended(a, thread=fin)   # the cycle's owner ended, its thread finished
        del a, b
        c.tick(inserts=2)                            # the tick observes the cyclic ended ref and reclaims
        self.assertIsNone(wcyc(), "the frozen cycle is reclaimed once the ended tick unfreezes and collects")

    def test_a_live_root_ref_is_a_survivor_counted_once_then_dropped(self):
        """PR 1999 review (behaviour 4): a ref judged a surviving cycle (alive, worker finished) that a live ROOT, not a
        cycle, keeps is not freed by the reclaim; it is counted a survivor on /perf (a wasted pause) and dropped, never
        re-registered, so a strong root costs exactly ONE reclaim. A genuine frozen cycle is freed: no survivor."""
        gc.disable(); self.addCleanup(gc.enable)
        c = gf.GcFreeze(enabled=True, load_trees=1, gc=gc)
        c.tick(inserts=1)                            # initial freeze
        root = _Owner(); root.sid = "abcdef12-3456-7890-abcd-ef1234567890"   # a synthetic sid so the release names it (review PR 2042 low)
        fin = _FakeThread(alive=False)   # a local, so the weakref resolves and is_alive() False is what decides (review PR 2042 low)
        c.note_ended(root, thread=fin)
        self.assertEqual(c.tick(inserts=1), "release", "a live ref with a finished worker is judged a surviving cycle: a release runs")
        # the REAL resolve_ended gathered the owed sid onto last_release_sids (its first 8 chars): deleting the gather reds this
        self.assertEqual(c.last_release_sids, ["abcdef12"], "the release names the owed session by its sid's first 8 chars: %r" % c.last_release_sids)
        # PR 2042 review (attribution): the /perf VALUE carries it, and the live-root case reads lastReleaseSurvivors 1
        self.assertEqual(c.perf()["lastReleaseSids"], ["abcdef12"], "/perf carries the owed sid value: %r" % c.perf()["lastReleaseSids"])
        self.assertEqual(c.perf()["lastReleaseSurvivors"], 1, "the live-root release freed nothing: one survivor on /perf")
        self.assertEqual(c.survivors, 1, "the live root kept it through the reclaim: one survivor counted")
        self.assertIsNone(c.tick(inserts=1), "the survivor was dropped, never re-registered: no second reclaim owed")
        self.assertEqual(c.perf()["lastReleaseSids"], [], "the next tick owed nothing, so lastReleaseSids is cleared: %r" % c.perf()["lastReleaseSids"])
        self.assertEqual(c.survivors, 1, "and not double-counted")
        before = c.survivors
        a = Cyclic(); b = Cyclic(); a.other = b; b.other = a
        wcyc = weakref.ref(a)
        c.tick(inserts=2)                            # fold the cycle in (freeze it)
        fin = _FakeThread(alive=False)   # a local, so the weakref resolves and is_alive() False is what decides (review PR 2042 low)
        c.note_ended(a, thread=fin); del a, b
        c.tick(inserts=2)                            # a real reclaim
        self.assertIsNone(wcyc(), "the genuine cycle is freed")
        self.assertEqual(c.survivors, before, "a freed cycle adds no survivor")

    def test_a_release_the_cheap_collect_takes_whole_counts_as_a_load(self):
        """PR 1999 review (behaviour 5): the release is staged. A cyclic ended session on a cycle allocated SINCE the last
        freeze (no load pass between spawn and end) is UNFROZEN, so the cheap collect with the freeze in place takes it
        whole; it counts as a LOAD pass, not a reclaim, so the backstop bound does not stretch and no full-heap pause runs."""
        gc.disable(); self.addCleanup(gc.enable)
        c = gf.GcFreeze(enabled=True, load_trees=1, gc=gc)
        c.tick(inserts=1)                            # initial freeze
        reclaims0, foldins0 = c.reclaims, c._foldins
        a = Cyclic(); b = Cyclic(); a.other = b; b.other = a   # allocated AFTER the freeze: unfrozen
        wcyc = weakref.ref(a)
        fin = _FakeThread(alive=False)   # a local, so the weakref resolves and is_alive() False is what decides (review PR 2042 low)
        c.note_ended(a, thread=fin); del a, b
        self.assertEqual(c.tick(inserts=1), "load", "the cheap collect took the released cycle whole: counted as a load pass")
        self.assertEqual(c.reclaims, reclaims0, "no full-heap reclaim ran: the backstop bound is not stretched")
        self.assertGreater(c._foldins, foldins0, "the cheap release folded in like a load")
        self.assertIsNone(wcyc(), "the cheap collect freed the unfrozen cycle")
        self.assertEqual(c.survivors, 0, "nothing survived: no wasted pause")

    def test_a_frozen_member_of_the_released_cycle_forces_the_full_walk(self):
        """PR 2042 review (item 1), the condition pair: the cheap stage takes the cycle only when EVERY member postdates the
        last freeze. A released cycle with a FROZEN member (one folded in by an earlier load pass) is not taken by the cheap
        collect: the release must unfreeze and walk the frozen heap (a reclaim). A young cycle that merely KEEPS an unrelated
        object alive is still all-young, so it is the load case above."""
        gc.disable(); self.addCleanup(gc.enable)
        c = gf.GcFreeze(enabled=True, load_trees=1, gc=gc)
        c.tick(inserts=1)                            # initial freeze
        old = Cyclic(); old.other = None             # allocated after the initial freeze; fold it in so it is FROZEN:
        c.tick(inserts=2)                            # a load fold-in freezes `old`
        self.assertGreater(gc.get_freeze_count(), 0, "old is frozen")
        reclaims0 = c.reclaims
        young = Cyclic(); young.other = old; old.other = young   # the released cycle young<->old: `old` is a FROZEN member
        wy = weakref.ref(young)
        fin = _FakeThread(alive=False)
        c.note_ended(young, thread=fin); del young, old
        self.assertEqual(c.tick(inserts=2), "release", "a frozen member holds the cycle out of the cheap walk: the release unfreezes and reclaims")
        self.assertEqual(c.reclaims, reclaims0 + 1, "a full-heap reclaim ran")
        self.assertIsNone(wy(), "the unfreeze-and-collect freed the cycle with the frozen member")
        self.assertEqual(c.survivors, 0, "the cycle was garbage: no live-root survivor")

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

    def test_freezing_forces_no_whole_transcript_reread(self):
        # a freeze must not make the reader re-read a file it already cached: re-parsing the UNCHANGED file after a
        # freeze moves neither `inserts` nor `wholeReads` (restored from the shipped NoRereadChurn, ported to tick)
        em = load_source("romp_event_model_reread", os.path.join(BIN, "romp-event-model"))
        d = tempfile.mkdtemp()
        sid = "11111111-2222-3333-4444-cccccccc0002"
        rows = [_uline(sid, 1_700_000_000, "ask", "u1"), _aline(sid, 1_700_000_030, "answer", "a1", "u1"),
                _uline(sid, 1_700_000_600, "again", "u2", "a1"), _aline(sid, 1_700_000_630, "ok", "a2", "u2")]
        p = self._write(d, sid, rows)
        em.parse_session(p, rompuuid=sid)
        s1 = em.record_cache_stats()
        c = gf.GcFreeze(enabled=True, load_trees=1, gc=gc)
        c.tick(int(s1["inserts"]))                   # freeze the loaded records
        em.parse_session(p, rompuuid=sid)            # re-parse the unchanged file
        s2 = em.record_cache_stats()
        self.assertEqual(s2["inserts"], s1["inserts"], "no new insert: the freeze did not evict the cached records")
        self.assertEqual(s2.get("wholeReads"), s1.get("wholeReads"), "no new whole read: the freeze forced no reread")

    def test_the_load_fold_in_fires_off_the_real_insert_counter(self):
        # ten real parses grow the record cache's insert counter past the threshold; the tick folds them in and the
        # frozen count rises (restored from the shipped NoRereadChurn, ported to tick)
        em = load_source("romp_event_model_loadctr", os.path.join(BIN, "romp-event-model"))
        d = tempfile.mkdtemp()
        c = gf.GcFreeze(enabled=True, load_trees=8, gc=gc)

        def parse(i):
            sid = "11111111-2222-3333-4444-bbbbbbbb%04d" % i
            rows = [_uline(sid, 1_700_000_000, "ask", "u1"), _aline(sid, 1_700_000_030, "answer", "a1", "u1"),
                    _uline(sid, 1_700_000_600, "again", "u2", "a1"), _aline(sid, 1_700_000_630, "ok", "a2", "u2")]
            em.parse_session(self._write(d, sid, rows), rompuuid=sid)
            return int(em.record_cache_stats()["inserts"])
        parse(0)
        self.assertEqual(c.tick(int(em.record_cache_stats()["inserts"])), "initial", "the first parse makes the initial freeze")
        for i in range(1, 11):                       # ten more real parses grow the real insert counter past the threshold
            inserts = parse(i)
        frozen_before = gc.get_freeze_count()
        self.assertEqual(c.tick(inserts), "load", "the tick reads the REAL insert counter grown past the threshold and folds the load in")
        self.assertGreater(gc.get_freeze_count(), frozen_before, "the fold-in froze the newly loaded objects out of the collector's walk")


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


def _install_fake_sdk():
    """The verifier's fake claude_agent_sdk: a client that stalls after the init frame, so a real SdkBackend
    connects and runs a session thread without the real CLI. Installed in sys.modules before sdk_backend loads."""
    import asyncio
    import importlib.machinery as _mach
    import types as _types

    class _StandIn(_types.ModuleType):
        def __getattr__(self, name):
            if name.startswith("__"):
                raise AttributeError(name)
            cls = type(name, (), {"__init__": lambda self, *a, **k: self.__dict__.update(k)})
            setattr(self, name, cls)
            return cls

    class SystemMessage:
        def __init__(self, subtype, data=None):
            self.subtype = subtype
            self.data = data or {}

    class FakeClient:
        def __init__(self, options=None, transport=None):
            self.options = options
            self._q = asyncio.Queue()
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def query(self, prompt, session_id="default"):
            async for turn in prompt:
                await self._q.put(turn)
        async def interrupt(self):
            pass
        async def get_context_usage(self):
            return {"percentage": 2, "model": "claude-x"}
        async def get_server_info(self):
            return {}
        async def receive_messages(self):
            await self._q.get()
            yield SystemMessage("init", {"session_id": getattr(self.options, "session_id", None) or "fsid",
                                         "model": "claude-x", "permissionMode": "acceptEdits"})
            while True:
                await asyncio.sleep(3600)

    m = _StandIn("claude_agent_sdk")
    m.__spec__ = _mach.ModuleSpec("claude_agent_sdk", None)
    m.__file__ = "<test stand-in>"
    m.ClaudeAgentOptions = type("ClaudeAgentOptions", (), {"__init__": lambda self, **kw: self.__dict__.update(kw)})
    m.ClaudeSDKClient = FakeClient
    m.SystemMessage = SystemMessage
    m.AssistantMessage = type("AssistantMessage", (), {"__init__": lambda self, content=None, model=None: self.__dict__.update(content=content or [], model=model)})
    m.ResultMessage = type("ResultMessage", (), {"__init__": lambda self, **k: self.__dict__.update(k)})
    m.TextBlock = type("TextBlock", (), {"__init__": lambda self, text="": self.__dict__.update(text=text)})
    had = "claude_agent_sdk" in sys.modules
    prior = sys.modules.get("claude_agent_sdk")
    sys.modules["claude_agent_sdk"] = m
    def restore():                                   # never leave the stand-in in sys.modules: on a box where the real package
        if had:                                      # imports (the kernel's sdkvenv on sys.path), it would shadow it for every later module
            sys.modules["claude_agent_sdk"] = prior
        else:
            sys.modules.pop("claude_agent_sdk", None)
    return restore


class FakeSdkRestore(unittest.TestCase):
    """PR 1999 round-four low: _install_fake_sdk's restore must put back whatever `claude_agent_sdk` was in sys.modules (a
    real package on a box with the sdkvenv on the path), or leave it absent when there was none. Seed a marker and check it
    comes back; then check the absent case pops the stand-in."""
    def test_the_restore_puts_back_the_prior_module_or_leaves_it_absent(self):
        import types as _types
        saved = sys.modules.get("claude_agent_sdk")
        self.addCleanup(lambda: sys.modules.__setitem__("claude_agent_sdk", saved) if saved is not None else sys.modules.pop("claude_agent_sdk", None))
        marker = _types.ModuleType("claude_agent_sdk"); marker.MARKER = object()
        sys.modules["claude_agent_sdk"] = marker
        restore = _install_fake_sdk()
        self.assertIsNot(sys.modules.get("claude_agent_sdk"), marker, "the stand-in replaced the prior module while installed")
        restore()
        self.assertIs(sys.modules.get("claude_agent_sdk"), marker, "the restore put the prior module back")
        # the absent case: no prior module, so the restore pops the stand-in
        sys.modules.pop("claude_agent_sdk", None)
        restore2 = _install_fake_sdk()
        self.assertIn("claude_agent_sdk", sys.modules, "the stand-in is installed")
        restore2()
        self.assertNotIn("claude_agent_sdk", sys.modules, "the restore pops the stand-in when there was no prior module")


class SessionEndPopsRegister(unittest.TestCase):
    """Executed: a real SdkBackend driven to each of its three session-end pops (run-to-exit, kill, conserve-close)
    through the fake SDK registers the ended session with the controller. A spy sees one registration per pop, with
    the session and its worker thread; the run-to-exit registers though its `client` is already None, so re-adding
    a `client is not None` guard at a pop (the round-one defect) would drop it and redden here."""
    @classmethod
    def setUpClass(cls):
        cls.addClassCleanup(_install_fake_sdk())     # install the stand-in and register its restore (pop it, or put back any real package)
        cls.addClassCleanup(lambda: sys.modules.pop("romp_sdk_backend_pops", None))
        cls.sb = load_source("romp_sdk_backend_pops", os.path.join(ROOT, "kernel", "sdk_backend.py"))

    def _backend(self, tag):
        d = tempfile.mkdtemp(prefix="gcf-pops-" + tag + "-")
        open(os.path.join(d, "session-hosts"), "w").write("off")
        return self.sb.SdkBackend(d, "/bin/true", lambda *a, **k: None), d

    def _wait(self, pred, timeout=15.0):
        end = time.time() + timeout
        while time.time() < end:
            if pred():
                return True
            time.sleep(0.02)
        return False

    def _connected(self, tag, name):
        be, d = self._backend(tag)
        sid = be.spawn(name, d)
        self.assertTrue(be.connect(sid), "connect refused")
        self.assertTrue(self._wait(lambda: be.sessions.get(sid) and be.sessions[sid].client is not None), "never connected")
        return be, d, sid

    def test_each_of_the_three_session_end_pops_registers_the_ended_session(self):
        """Executed teeth (review PR 1999): a REAL GcFreeze over the fake collector is the ended note (never a strong list,
        which would leak every ended session and pass a note that leaks). Each of the three pops registers EXACTLY once with
        the session and its worker thread (read off c._ended's weakrefs), ahead of the drop; and the run-to-exit end, the
        common case, DIES BY REFERENCE COUNTING once its strong refs are dropped and its worker joined, so the judgement owes
        no reclaim. Under gc.disable() so a young-generation collect cannot take the ref before the read."""
        c = gf.GcFreeze(enabled=True, gc=FakeGc(), clock=lambda: 0.0)
        self.sb.set_ended_note(c.note_ended)
        self.addCleanup(lambda: self.sb.set_ended_note(None))
        gc.disable(); self.addCleanup(gc.enable)
        # run to exit through _on_session_gone: shutdown ends the loop, its own thread pops with client cleared
        be, d, sid = self._connected("exit", "web")
        s = be.sessions[sid]; th = s.thread
        n = len(c._ended)
        s.shutdown()
        self.assertTrue(self._wait(lambda: not th.is_alive()), "the session thread never finished")
        self.assertTrue(self._wait(lambda: len(c._ended) == n + 1), "_on_session_gone registered EXACTLY one ended session: %d" % (len(c._ended) - n))
        sref, tref = c._ended[-1]
        self.assertIs(sref(), s, "the session is registered (read off the weakref while still held)")
        self.assertIs(tref(), th, "with its worker thread")
        self.assertIsNone(s.client, "run-to-exit clears client, yet the pop still registered (a client guard here would drop it)")
        # the common end dies by REFERENCE COUNTING: join the worker (clears its _target), drop every strong local, then the
        # weakref is dead and the judgement owes no reclaim (never a wasted full pause for the ordinary exit)
        th.join(10)
        del s, th
        owed = c.resolve_ended()
        self.assertIsNone(sref(), "the run-to-exit session died by reference counting once its refs dropped: acyclic")
        self.assertEqual(owed, [], "the common end owes NO reclaim (it was not a surviving cycle): %r" % owed)
        # kill (mid-turn). PR 2042 review item 7: WAIT for the worker (the gone hook registers from its finally), THEN
        # assert the count directly, so a broken `if popped:` guard that lets the gone hook register a SECOND time (count
        # n+2) reds; the earlier poll-until-n+1 passed as soon as it hit n+1, before the worker's gone hook could add one.
        be2, d2, sid2 = self._connected("kill", "api")
        s2 = be2.sessions[sid2]; th2 = s2.thread
        n = len(c._ended)
        be2.kill(sid2)
        self.assertTrue(self._wait(lambda: not th2.is_alive()), "the kill worker never finished")
        self.assertTrue(self._wait(lambda: len(c._ended) > n), "kill registered the ended session")
        self.assertEqual(len(c._ended), n + 1, "kill registered EXACTLY once, even after the worker's gone hook ran: %d" % (len(c._ended) - n))
        sref2, tref2 = c._ended[-1]
        self.assertIs(sref2(), s2, "kill registered the session"); self.assertIs(tref2(), th2, "with its worker thread")
        # item 8 mirror: the killed session dies by refcount and owes no reclaim (a pop that stashed it would leak it, unseen)
        del s2, th2
        owed2 = c.resolve_ended()
        self.assertIsNone(sref2(), "the killed session died by reference counting: acyclic, not stashed")
        self.assertEqual(owed2, [], "the killed session owes no reclaim: %r" % owed2)
        # conserve-close (the stop pop): same wait-then-assert and dead-ref mirror
        be3, d3, sid3 = self._connected("close", "tests")
        self.assertTrue(self._wait(lambda: be3.conserve_idle(sid3), 8.0), "never conserve-idle")
        s3 = be3.sessions[sid3]; th3 = s3.thread
        n = len(c._ended)
        be3.conserve_close(sid3)
        self.assertTrue(self._wait(lambda: not th3.is_alive()), "the conserve-close worker never finished")
        self.assertTrue(self._wait(lambda: len(c._ended) > n), "conserve_close registered the ended session")
        self.assertEqual(len(c._ended), n + 1, "conserve_close registered EXACTLY once, even after the worker's gone hook ran: %d" % (len(c._ended) - n))
        sref3, tref3 = c._ended[-1]
        self.assertIs(sref3(), s3, "conserve_close registered the session"); self.assertIs(tref3(), th3, "with its worker thread")
        del s3, th3
        owed3 = c.resolve_ended()
        self.assertIsNone(sref3(), "the conserve-closed session died by reference counting: acyclic, not stashed")
        self.assertEqual(owed3, [], "the conserve-closed session owes no reclaim: %r" % owed3)


class KernelGlue(unittest.TestCase):
    """The kernel wires the ended note at backend load and calls the tick at the pusher's idle boundary."""
    def test_the_pusher_cycle_calls_the_tick_and_the_kernel_wires_the_ended_note(self):
        import inspect
        km = load_source("romp_kernel_gcf_glue", os.path.join(BIN, "romp-kernel"))
        self.assertRegex(inspect.getsource(km._pusher_cycle), r"_gc_freeze_tick\(_cycle_idle, first\)",
                         "the pusher cycle calls the freeze tick with the cycle's idle flag and first-cycle flag")
        # the regex reds a guard-name typo; the SDK-load function itself is executed in
        # test_the_kernel_sdk_load_wires_the_ended_note_executed, which reds the three unreachable-call mutants the text misses.
        self.assertRegex(inspect.getsource(km), r'hasattr\(sbmod, "set_ended_note"\)[\s\S]{0,240}?sbmod\.set_ended_note\(_GC_FREEZE\.note_ended\)',
                         "the kernel guards and wires the ended note on the same literal name (executed by the glue test below)")
        sbmod = load_source("romp_sdk_backend_wire", os.path.join(ROOT, "kernel", "sdk_backend.py"))
        self.assertTrue(hasattr(sbmod, "set_ended_note"), "the real backend exposes the exact name the kernel's hasattr guards on")
        self.addCleanup(lambda: sbmod.set_ended_note(None))
        sbmod.set_ended_note(km._GC_FREEZE.note_ended)
        self.assertEqual(sbmod._ENDED_NOTE[0], km._GC_FREEZE.note_ended,
                         "the backend's own setter wires the note (==, a bound method mints anew per read); the kernel's call of it is executed below")

    def test_the_kernel_sdk_load_wires_the_ended_note_executed(self):
        """PR 2042 review (item 2): the ended-note wiring is pinned by EXECUTING the kernel's SDK-load function, not only the
        regex plus a call of the backend's own setter. Stub the kernel copy's load_source to a namespace whose backend is a
        plain recorder (not a mock, which answers hasattr True for a misspelt guard name), whose startup_auth_env returns {}
        (kernel.py reads it unguarded, so assert no problems) and whose set_ended_note records; save and restore the kernel
        names and jd wires as _sdk_locked_for_real does; run _sdk_locked; the recorded note equals the controller's
        note_ended. Three mutants that keep the source text but make the call unreachable red this."""
        import io, types
        from contextlib import redirect_stderr
        km = load_source("romp_kernel_gcf_glue_exec", os.path.join(BIN, "romp-kernel"))
        noted = []
        class _Recorder:
            def __init__(self, *a, **k):
                self.args = (a, k)
        fake = types.SimpleNamespace(SdkBackend=_Recorder, startup_auth_env=lambda *a, **k: {},
                                     set_ended_note=lambda fn: noted.append(fn))
        names = ("_sdk_backend", "load_source", "_sdk_import_notice", "_ensure_sdk_on_path", "_model_catalog_boot",
                 "_claude_bin", "_mark_boot", "_sdk_problem")
        saved = {n: getattr(km, n) for n in names}
        wires = ("_LOGIN_AUTH_ENV_FN", "_USAGE_REFRESH_FN", "_DEFAULT_AUTH_FN", "_DEFAULT_LOGIN_FN", "_API_HEALTH_NOTE_FN")
        saved_jd = {w: getattr(km.jd, w) for w in wires}
        problems = []
        try:
            km._sdk_backend = None
            km.load_source = lambda name, path: fake
            km._sdk_import_notice = lambda: True
            km._ensure_sdk_on_path = lambda: True
            km._model_catalog_boot = lambda _async=True: False
            km._claude_bin = lambda: "/bin/true"
            km._mark_boot = lambda *a, **k: None
            km._sdk_problem = problems.append
            err = io.StringIO()
            with redirect_stderr(err):
                km._sdk_locked()
        finally:
            for n in names:
                setattr(km, n, saved[n])
            for w in wires:
                setattr(km.jd, w, saved_jd[w])
        self.assertEqual(noted, [km._GC_FREEZE.note_ended], "the executed SDK-load wired the controller's note_ended (by equality): %r" % noted)
        self.assertEqual(problems, [], "the auth-env hook returned an empty problems list")

    def test_every_session_end_pop_is_paired_with_an_ended_note(self):
        """A source census beside the driven test: every `self.sessions.pop(` site in the SDK backend (a session end, in
        `kill`, `conserve_close` and the `_on_session_gone` hook) is followed within a few lines by a `_note_ended(` CALL,
        so a FUTURE fourth pop that forgets the note reds here. The driven test (SessionEndPopsRegister) proves the three
        that exist fire; this guards the ones not yet written. Comments are stripped and the `def _note_ended` line skipped,
        so a comment naming the call or the definition itself never pairs a pop (review PR 1999 tests). LIMIT (PR 1999
        round-four low): the census matches the single-line literal `self.sessions.pop(`; a pop split across physical lines
        (an argument on the next line) would not be found. The three pops today are each one line, and a new pop kept to one
        line is caught; a future multi-line pop would need this literal widened."""
        raw = Path(ROOT, "kernel", "sdk_backend.py").read_text().splitlines()
        code = [ln.split("#", 1)[0] for ln in raw]      # strip line comments so a comment naming the call does not pair a pop
        code = ["" if ln.lstrip().startswith("def _note_ended") else ln for ln in code]   # the def line is not a call
        pops = [i for i, ln in enumerate(code) if "self.sessions.pop(" in ln]
        self.assertEqual(len(pops), 3, "the SDK backend has exactly the three session-end pops (kill, conserve_close, _on_session_gone): %d" % len(pops))
        for i in pops:
            window = "\n".join(code[i:i + 5])           # the pop's line and the next four, comments stripped
            self.assertIn("_note_ended(", window,
                          "the session-end pop at line %d (a kill, conserve_close or _on_session_gone) is not paired with a "
                          "_note_ended call within four lines: %r" % (i + 1, "\n".join(raw[i:i + 5])))


if __name__ == "__main__":
    unittest.main()
