#!/usr/bin/env python3
"""Lifecycle validation for the Road B freeze (issue #1735, kernel/gc_freeze.py).

The freeze keeps the loaded decoded heap out of the collector's walk, so the tests prove the
collector still behaves: the trigger logic folds a load in cheaply and reclaims a release with
an unfreeze; the env switch turns it off; an acyclic object frozen then dropped dies by
reference counting while a frozen CYCLE survives until a reclaim; re-folding a transcript across
a freeze forces no reread; the gc hook still counts the collections that do run; and a warm
collection after the freeze walks far fewer objects than the cold one. Every fixture is
synthetic. Real-collector tests unfreeze in tearDown so the freeze never leaks to another test.
"""
import gc
import json
import os
import sys
import tempfile
import unittest
import weakref
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
    """Records the collector calls a reconcile makes, in order, so the trigger logic is pinned
    without touching the real collector."""
    def __init__(self):
        self.calls = []
    def collect(self, *a):
        self.calls.append("collect")
    def freeze(self):
        self.calls.append("freeze")
    def unfreeze(self):
        self.calls.append("unfreeze")


class TriggerLogic(unittest.TestCase):
    def test_a_load_folds_in_a_cyclic_note_reclaims_and_the_backstop_bounds(self):
        fake = FakeGc()
        c = gf.GcFreeze(enabled=True, load_trees=8, backstop_foldins=2, gc=fake, clock=lambda: 0.0)
        # nothing loaded yet: not due; a first load makes the initial freeze due
        self.assertFalse(c.due(inserts=0, notes=0))
        self.assertTrue(c.due(inserts=3, notes=0), "the first freeze is due once something is loaded")
        self.assertEqual(c.reconcile(inserts=3, notes=0), "initial")
        self.assertEqual(fake.calls, ["collect", "freeze"], "the initial freeze collects then freezes, no unfreeze")
        # a small load is NOT material; a load past the threshold is a cheap fold-in (no unfreeze)
        self.assertFalse(c.due(inserts=3 + 7, notes=0), "under the threshold does not fire per parse")
        self.assertTrue(c.due(inserts=3 + 8, notes=0))
        fake.calls.clear()
        self.assertEqual(c.reconcile(inserts=3 + 8, notes=0), "load")
        self.assertEqual(fake.calls, ["collect", "freeze"], "a load fold-in walks only the unfrozen: no unfreeze")
        # a CYCLIC release note since the last reclaim needs the unfreeze reclaim; a moved pop counter would NOT (no notes)
        self.assertFalse(c.due(inserts=3 + 8, notes=0), "no new load and no note: not due (a record-cache pop moves no note)")
        self.assertTrue(c.due(inserts=3 + 8, notes=1))
        fake.calls.clear()
        self.assertEqual(c.reconcile(inserts=3 + 8, notes=1), "release")
        self.assertEqual(fake.calls, ["unfreeze", "collect", "freeze"], "a cyclic note reclaims: unfreeze, collect, re-freeze")
        # the backstop: after backstop_foldins load fold-ins since the last reclaim, a reclaim runs even with no new note
        base = 3 + 8
        self.assertEqual(c.reconcile(inserts=base + 8, notes=1), "load", "the intermediate reconciles are cheap load fold-ins")
        self.assertEqual(c.reconcile(inserts=base + 16, notes=1), "load")   # load fold-in 2 -> _foldins now at the backstop
        self.assertTrue(c.due(inserts=base + 16, notes=1), "the backstop makes a reconcile due even with no new load or note")
        self.assertEqual(c.reconcile(inserts=base + 16, notes=1), "backstop", "and it reconciles as a reclaim")
        self.assertGreaterEqual(c.reclaims, 2, "the cyclic note and the backstop each ran a reclaim")
        self.assertFalse(c.due(inserts=base + 16, notes=1), "the backstop reset _foldins: not due again until the next load or note")

    def test_the_initial_freeze_syncs_the_note_mark(self):
        # a release noted BEFORE the first freeze is taken by the initial collect; it must not drive a wasted reclaim next
        fake = FakeGc()
        c = gf.GcFreeze(enabled=True, load_trees=8, gc=fake, clock=lambda: 0.0)
        self.assertEqual(c.reconcile(inserts=3, notes=5), "initial", "the first freeze, with 5 releases already noted")
        self.assertEqual(fake.calls, ["collect", "freeze"], "the initial freeze collects and freezes, no unfreeze")
        self.assertFalse(c.due(inserts=3, notes=5), "the pre-freeze notes are synced: not due with no NEW note (no wasted reclaim next tick)")
        self.assertTrue(c.due(inserts=3, notes=6), "a genuinely new note after the freeze is due")

    def test_the_env_switch_turns_it_off(self):
        self.assertFalse(gf.enabled_from_env({"ROMP_GC_FREEZE": "off"}))
        self.assertFalse(gf.enabled_from_env({"ROMP_GC_FREEZE": "0"}))
        self.assertTrue(gf.enabled_from_env({}), "on by default")
        self.assertTrue(gf.enabled_from_env({"ROMP_GC_FREEZE": "on"}))
        fake = FakeGc()
        c = gf.GcFreeze(enabled=False, gc=fake)
        self.assertFalse(c.due(inserts=100, notes=5))
        self.assertIsNone(c.reconcile(inserts=100, notes=5))
        self.assertEqual(fake.calls, [], "a disabled controller never touches the collector")

    def test_the_load_threshold_parses_safely_and_floors_at_one(self):
        # the #1735 high: a bad ROMP_GC_FREEZE_LOAD_TREES must not kill the kernel at import; it falls back, named
        self.assertEqual(gf.load_trees_from_env({}), (gf.DEFAULT_LOAD_TREES, None), "absent: the default, no complaint")
        self.assertEqual(gf.load_trees_from_env({"ROMP_GC_FREEZE_LOAD_TREES": "  "}), (gf.DEFAULT_LOAD_TREES, None), "whitespace: the default")
        self.assertEqual(gf.load_trees_from_env({"ROMP_GC_FREEZE_LOAD_TREES": "abc"}), (gf.DEFAULT_LOAD_TREES, "abc"), "a bad value falls back and is named")
        self.assertEqual(gf.load_trees_from_env({"ROMP_GC_FREEZE_LOAD_TREES": "20"}), (20, None))
        self.assertEqual(gf.load_trees_from_env({"ROMP_GC_FREEZE_LOAD_TREES": "0"})[0], 1, "floored at 1: a 0 would make due() fire every idle cycle")
        self.assertEqual(gf.load_trees_from_env({"ROMP_GC_FREEZE_LOAD_TREES": "-5"})[0], 1, "a negative is floored at 1 too")
        self.assertEqual(gf.GcFreeze(load_trees=0).load_trees, 1, "the controller floors its threshold too")


class DoubleController:
    """Records the reconcile calls, so the pusher tick's guard and error handling are pinned without the collector."""
    def __init__(self, enabled=True, due=True, raise_reconcile=False):
        self.enabled = enabled
        self._due = due
        self._raise = raise_reconcile
        self.reconciled = []
    def due(self, inserts, notes):
        return self._due
    def reconcile(self, inserts, notes):
        self.reconciled.append((inserts, notes))
        if self._raise:
            raise RuntimeError("reconcile blew up")
        return "load"


class PusherTick(unittest.TestCase):
    """MEDIUM 1: the pusher wiring had no teeth (removing the call or the guard left the suite green). pusher_tick
    is the extracted seam the kernel calls; these pin its guard and its never-die error handling in-process."""
    def setUp(self):
        gf._NOTED_RELEASES[0] = 0
        self.addCleanup(lambda: gf._NOTED_RELEASES.__setitem__(0, 0))

    def _stats(self, inserts=10, released=0):
        return lambda: {"inserts": inserts, "released": released}   # `released` is a /perf stat; pusher_tick must NOT key on it

    def test_it_reconciles_only_on_an_idle_non_first_cycle(self):
        errs = []
        c = DoubleController()
        gf.pusher_tick(c, idle=True, first=False, stats_fn=self._stats(), on_error=errs.append)
        self.assertEqual(len(c.reconciled), 1, "an idle, non-first cycle reconciles")
        c = DoubleController()
        gf.pusher_tick(c, idle=True, first=True, stats_fn=self._stats(), on_error=errs.append)
        self.assertEqual(c.reconciled, [], "the boot's first cycle never reconciles")
        c = DoubleController()
        gf.pusher_tick(c, idle=False, first=False, stats_fn=self._stats(), on_error=errs.append)
        self.assertEqual(c.reconciled, [], "a busy cycle (marks or writes) never reconciles")
        c = DoubleController(enabled=False)
        gf.pusher_tick(c, idle=True, first=False, stats_fn=self._stats(), on_error=errs.append)
        self.assertEqual(c.reconciled, [], "a disabled controller never reconciles")
        self.assertEqual(errs, [], "no errors on the happy paths")

    def test_it_reads_inserts_and_the_noted_releases_never_the_pop_counter(self):
        c = DoubleController()
        gf.note_release(); gf.note_release()                      # two cyclic releases noted by their owners
        # `released` (the record cache's pop counter) is high but must NOT reach the controller: the reclaim is keyed on notes
        gf.pusher_tick(c, idle=True, first=False, stats_fn=self._stats(inserts=4, released=999), on_error=lambda e: None)
        self.assertEqual(c.reconciled, [(4, 2)], "the controller gets inserts and the NOTED releases, not the record cache's pop counter")

    def test_a_not_due_controller_is_not_reconciled(self):
        # teeth for the `if controller.due(...)` guard: a `if True:` mutant would reconcile a not-due controller
        c = DoubleController(due=False)
        gf.pusher_tick(c, idle=True, first=False, stats_fn=self._stats(), on_error=lambda e: None)
        self.assertEqual(c.reconciled, [], "an idle non-first cycle with a not-due controller runs no reconcile")

    def test_a_raising_stats_read_or_reconcile_is_handed_to_on_error_and_never_propagates(self):
        # a raising stats read
        errs = []
        def boom():
            raise RuntimeError("cache stats read failed")
        c = DoubleController()
        gf.pusher_tick(c, idle=True, first=False, stats_fn=boom, on_error=errs.append)   # must not raise
        self.assertEqual(len(errs), 1, "the failing read is counted once")
        self.assertEqual(c.reconciled, [], "and no reconcile ran")
        # a raising RECONCILE (teeth for reconcile staying inside the try): on_error once, nothing propagated
        errs2 = []
        c2 = DoubleController(raise_reconcile=True)
        gf.pusher_tick(c2, idle=True, first=False, stats_fn=self._stats(), on_error=errs2.append)   # must not raise
        self.assertEqual(len(errs2), 1, "the raising reconcile is caught and counted once")
        self.assertEqual(len(c2.reconciled), 1, "the reconcile was attempted")

    def test_the_kernels_tick_guards_and_counts_a_not_due_and_a_raising_reconcile(self):
        # the same guard and error handling mirrored through the kernel's own _gc_freeze_tick wrapper
        km = load_source("romp_kernel_gcf_tick", os.path.join(BIN, "romp-kernel"))
        saved_gf, saved_stats = km._GC_FREEZE, km.em.record_cache_stats
        saved_errs, saved_said = km._GC_FREEZE_ERRORS[0], km._GC_FREEZE_SAID[0]
        try:
            km.em.record_cache_stats = lambda: {"inserts": 3}
            nd = DoubleController(due=False)
            km._GC_FREEZE = nd
            km._gc_freeze_tick(True, False)
            self.assertEqual(nd.reconciled, [], "the kernel tick runs no reconcile when the controller is not due")
            km._GC_FREEZE_ERRORS[0] = 0; km._GC_FREEZE_SAID[0] = False
            rc = DoubleController(raise_reconcile=True)
            km._GC_FREEZE = rc
            km._gc_freeze_tick(True, False)   # must not raise
            self.assertEqual(km._GC_FREEZE_ERRORS[0], 1, "a raising reconcile is counted through the kernel wrapper")
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

    def test_acyclic_dies_by_refcount_under_the_freeze_a_cycle_waits_for_the_reclaim(self):
        c = gf.GcFreeze(enabled=True, load_trees=1, gc=gc)
        # an acyclic object frozen and then dropped is reclaimed at once by reference counting
        acyclic = Cyclic(); acyclic.other = None
        wa = weakref.ref(acyclic)
        c.reconcile(inserts=1, notes=0)              # initial freeze folds `acyclic` into the frozen set
        del acyclic
        self.assertIsNone(wa(), "an acyclic frozen object dies by refcount when its owner drops it, freeze or no freeze")
        # a reference cycle frozen and then dropped survives a LOAD fold-in and is reclaimed only by a NOTE-driven reclaim
        a = Cyclic(); b = Cyclic(); a.other = b; b.other = a
        wcyc = weakref.ref(a)
        c.reconcile(inserts=2, notes=0)              # a load fold-in that freezes the cycle
        del a, b
        c.reconcile(inserts=3, notes=0)              # another load fold-in (no note): does NOT unfreeze
        self.assertIsNotNone(wcyc(), "a frozen cycle survives a load fold-in: it is not walked")
        c.reconcile(inserts=3, notes=1)              # a cyclic-owner note: unfreeze, collect, re-freeze
        self.assertIsNone(wcyc(), "the frozen cycle is reclaimed once a note-driven reconcile unfreezes and collects")

    def test_the_kernels_gc_hook_still_counts_the_collections_a_reconcile_runs(self):
        km = load_source("romp_kernel_gcf_hook", os.path.join(BIN, "romp-kernel"))
        st = km._PerfStats()
        st.install_gc_hook()                          # the kernel's own gc.callbacks hook, on this test's collector
        try:
            before = st.gc[2][0]                      # generation-two collections counted so far
            c = gf.GcFreeze(enabled=True, load_trees=1, gc=gc)
            c.reconcile(inserts=1, notes=0)           # a freeze runs a collection
            c.reconcile(inserts=2, notes=1)           # a note reclaim runs one too
            self.assertGreater(st.gc[2][0], before, "the kernel's gc hook counted the full collections the reconciles ran")
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
        # cold: a heap of CYCLES, watched by a weakref oracle, frozen out of the walk
        heap = self._make_cycles(20000)
        watched = [weakref.ref(x) for x in heap[:50]]   # a comprehension: its `x` does not leak into this scope
        c = gf.GcFreeze(enabled=True, load_trees=1, gc=gc)
        c.reconcile(inserts=1, notes=0)              # freeze the cold cycles out of the walk
        del heap                                     # drop every external ref: only the freeze keeps the cycles now
        self._make_cycles(200)                       # a little new (unheld) garbage for the warm collection to walk
        gc.collect()
        self.assertTrue(all(w() is not None for w in watched),
                        "a warm full collection after the freeze does not walk the frozen cold cycles: they survive though nothing holds them")
        self.assertGreater(gc.get_freeze_count(), 20000, "the frozen count shows the cold cycles left the collector's walk")
        # only a note-driven reclaim (unfreeze) reclaims them
        c.reconcile(inserts=2, notes=1)
        self.assertTrue(all(w() is None for w in watched), "the reclaim unfroze and collected the now-unreferenced cold cycles")


def _uline(sid, t, text, uid, parent=None):
    from datetime import datetime, timezone
    iso = datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return {"type": "user", "timestamp": iso, "uuid": uid, "parentUuid": parent, "sessionId": sid,
            "cwd": "/home/TESTHOST/proj", "message": {"role": "user", "content": text}}


def _aline(sid, t, text, uid, parent):
    from datetime import datetime, timezone
    iso = datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return {"type": "assistant", "timestamp": iso, "uuid": uid, "parentUuid": parent, "sessionId": sid,
            "message": {"role": "assistant", "content": [{"type": "text", "text": text}], "stop_reason": "end_turn"}}


class NoRereadChurn(unittest.TestCase):
    def tearDown(self):
        gc.unfreeze()
        gc.collect()

    def test_freezing_forces_no_whole_transcript_reread(self):
        """A freeze must not make the reader re-read a transcript it already cached: the record
        cache's whole-read and insert counters do not move when the same file is folded again
        after a freeze."""
        em = load_source("romp_event_model_gcf", os.path.join(BIN, "romp-event-model"))
        sid = "11111111-2222-3333-4444-aaaaaaaaaa01"
        recs = [_uline(sid, 1_700_000_000, "ask", "u1"), _aline(sid, 1_700_000_030, "answer", "a1", "u1"),
                _uline(sid, 1_700_000_600, "again", "u2", "a1"), _aline(sid, 1_700_000_630, "ok", "a2", "u2")]
        d = tempfile.mkdtemp()
        p = os.path.join(d, sid + ".jsonl")
        Path(p).write_text("".join(json.dumps(r) + "\n" for r in recs))
        em.parse_session(p, rompuuid=sid)                 # first parse: a whole read fills the cache
        s1 = em.record_cache_stats()
        c = gf.GcFreeze(enabled=True, load_trees=1, gc=gc)
        c.reconcile(inserts=1, notes=0)                   # freeze the loaded records
        em.parse_session(p, rompuuid=sid)                 # re-parse the unchanged file
        s2 = em.record_cache_stats()
        self.assertEqual(s2["inserts"], s1["inserts"], "no new insert: the freeze did not evict the cached records")
        self.assertEqual(s2.get("wholeReads"), s1.get("wholeReads"), "no new whole read: the freeze forced no reread")

    def test_the_load_trigger_fires_off_the_real_record_cache_counter(self):
        """The kernel keys the reconcile on the record cache's real insert counter: parsing transcripts grows it,
        and once it grows past the threshold the controller is due and a reconcile freezes the loaded objects."""
        em = load_source("romp_event_model_gcf2", os.path.join(BIN, "romp-event-model"))
        d = tempfile.mkdtemp()
        base_ins = int(em.record_cache_stats().get("inserts") or 0)
        for i in range(10):
            sid = "11111111-2222-3333-4444-bbbbbbbb%04d" % i
            recs = [_uline(sid, 1_700_000_000, "ask", "u1"), _aline(sid, 1_700_000_030, "answer", "a1", "u1"),
                    _uline(sid, 1_700_000_600, "again", "u2", "a1"), _aline(sid, 1_700_000_630, "ok", "a2", "u2")]
            p = os.path.join(d, sid + ".jsonl")
            Path(p).write_text("".join(json.dumps(r) + "\n" for r in recs))
            em.parse_session(p, rompuuid=sid)
        st = em.record_cache_stats()
        inserts = int(st.get("inserts") or 0)
        self.assertGreaterEqual(inserts - base_ins, 8, "ten parses grew the cache's insert counter past the load threshold")
        c = gf.GcFreeze(enabled=True, load_trees=8, gc=gc)
        self.assertTrue(c.due(inserts, notes=0), "the load trigger reads the real insert counter and is due")
        frozen_before = gc.get_freeze_count()
        self.assertEqual(c.reconcile(inserts, notes=0), "initial")
        self.assertGreater(gc.get_freeze_count(), frozen_before, "the reconcile froze the loaded objects out of the collector's walk")


class RecordCacheReleaseIsAStat(unittest.TestCase):
    """The 2026-09-21 review's correction: the record cache's `released` counter is a /perf STATISTIC, not a
    reclaim trigger. Its pops release acyclic decoded json, freed by refcount, so a reclaim there would collect
    nothing. `released` moves on a re-read replacement and an OSError pop, but a moving `released` under re-reads
    drives NO reclaim: the reclaim is keyed on cyclic-owner notes and the backstop, never on the pop counter."""
    def setUp(self):
        gf._NOTED_RELEASES[0] = 0
        self.addCleanup(lambda: gf._NOTED_RELEASES.__setitem__(0, 0))

    def tearDown(self):
        gc.unfreeze()                                # this test's reconcile froze the heap; never leak the freeze to another test
        gc.collect()

    def test_released_moves_on_a_pop_but_re_reads_drive_no_reclaim(self):
        em = load_source("romp_event_model_rel", os.path.join(BIN, "romp-event-model"))
        d = tempfile.mkdtemp()
        sid = "11111111-2222-3333-4444-cccccccc0001"
        rows = [_uline(sid, 1_700_000_000, "ask", "u1"), _aline(sid, 1_700_000_030, "answer", "a1", "u1"),
                _uline(sid, 1_700_000_600, "again", "u2", "a1"), _aline(sid, 1_700_000_630, "ok", "a2", "u2")]
        p = os.path.join(d, sid + ".jsonl"); Path(p).write_text("".join(json.dumps(r) + "\n" for r in rows))
        em.parse_session(p, rompuuid=sid)
        rel0 = em.record_cache_stats()["released"]
        c = gf.GcFreeze(enabled=True, load_trees=1, gc=gc)
        c.reconcile(int(em.record_cache_stats()["inserts"]), gf.noted_releases())   # an initial freeze
        kinds = []
        for k in range(6):                                # six re-reads: append and re-parse, each REPLACES the cache entry
            rows += [_uline(sid, 1_700_001_000 + k * 100, "more %d" % k, "u%d" % (10 + k), "a2")]
            Path(p).write_text("".join(json.dumps(r) + "\n" for r in rows))
            em.parse_session(p, rompuuid=sid)
            st = em.record_cache_stats()
            kinds.append(gf.pusher_tick(c, idle=True, first=False, stats_fn=lambda st=st: st, on_error=lambda e: None))
        rel1 = em.record_cache_stats()["released"]
        self.assertGreater(rel1, rel0, "each re-read replacement popped the old entry: `released` moved (a /perf stat)")
        self.assertNotIn("release", kinds, "a moving `released` under re-reads drives NO release reclaim: %r" % kinds)
        self.assertNotIn("backstop", kinds, "and no backstop fired over six re-reads: %r" % kinds)
        self.assertEqual(c.reclaims, 0, "the whole run of re-reads ran zero reclaims (the design's near-zero): %r" % c.reclaims)


class SdkSessionNote(unittest.TestCase):
    """The note fires at the CYCLIC owner only. Executed on a REAL SdkSession over a stub backend: a session with a
    surviving `client` back-reference is cyclic (needs a collect); the session-end helper notes a release for it and
    not for one whose client was cleared. The plumbing reaches gcf.note_release; the kernel injects it at load."""
    def setUp(self):
        gf._NOTED_RELEASES[0] = 0
        self.addCleanup(lambda: gf._NOTED_RELEASES.__setitem__(0, 0))

    def _session(self, sbmod):
        import tempfile as _tf
        class StubBackend:
            state_dir = _tf.mkdtemp()
            def _update_reg(self, *a, **k): pass
            def _log(self, *a, **k): pass
        return sbmod.SdkSession(StubBackend(), {"sid": "11111111-2222-3333-4444-555555555555", "name": "web", "cwd": "/tmp"})

    def test_a_surviving_client_session_is_cyclic_and_the_helper_notes_it(self):
        sbmod = load_source("romp_sdk_backend_note", os.path.join(ROOT, "kernel", "sdk_backend.py"))
        spy = []
        sbmod.set_release_note(lambda: spy.append(1))
        self.addCleanup(lambda: sbmod.set_release_note(None))
        # the connect-raised cycle: a live client that refers back to the session (executed oracle on the real object)
        s = self._session(sbmod)
        class Client:
            pass
        client = Client(); client.session = s; s.client = client
        w = weakref.ref(s)
        gc.collect(); gc.disable()
        del s, client
        self.assertIsNotNone(w(), "a session with a live client that refers back is cyclic: it outlives the drop with the collector off")
        gc.enable(); gc.collect()
        self.assertIsNone(w(), "and only a collection reclaims it")
        # the helper notes a release for a session that still holds a client, and NOT for one whose client was cleared
        sbmod._note_session_release(self._session(sbmod))
        self.assertEqual(spy, [], "no note for a session with client None (the common exit, acyclic)")
        s2 = self._session(sbmod); s2.client = object()
        sbmod._note_session_release(s2)
        self.assertEqual(spy, [1], "a note for a session that ended with a live client (the cyclic path)")

    def test_the_kernel_injects_the_note_when_the_backend_loads(self):
        import inspect
        ksrc = inspect.getsource(load_source("romp_kernel_gcf_inject", os.path.join(BIN, "romp-kernel")))
        self.assertRegex(ksrc, r'sbmod = load_source\("romp_sdk_backend"[\s\S]{0,320}?sbmod\.set_release_note\(gcf\.note_release\)',
                         "the kernel wires the release note right after it loads the SDK backend")


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


class KernelGlue(unittest.TestCase):
    """The kernel's own glue: `_gc_freeze_tick(idle, first)` (the pusher calls it at the idle boundary) reconciles
    through pusher_tick and counts a raising cache read once, and `_pusher_cycle` calls it. The tick is exercised
    in-process on a controller double; the call site is a source pin so deleting it reddens."""
    def _km(self):
        return load_source("romp_kernel_gcf_glue", os.path.join(BIN, "romp-kernel"))

    def test_the_tick_reconciles_and_counts_a_raising_read_once(self):
        km = self._km()
        saved_gf, saved_stats = km._GC_FREEZE, km.em.record_cache_stats
        saved_errs, saved_said = km._GC_FREEZE_ERRORS[0], km._GC_FREEZE_SAID[0]

        class Double:
            enabled = True
            def __init__(self): self.reconciled = []
            def due(self, inserts, notes): return True
            def reconcile(self, inserts, notes): self.reconciled.append((inserts, notes)); return "load"
        d = Double()
        try:
            km._GC_FREEZE = d
            km.em.record_cache_stats = lambda: {"inserts": 3}
            km._gc_freeze_tick(True, False)
            self.assertEqual(len(d.reconciled), 1, "an idle non-first cycle reconciles through the tick")
            d.reconciled.clear()
            km._gc_freeze_tick(True, True)
            self.assertEqual(d.reconciled, [], "the boot's first cycle does not")
            # a raising cache read is counted once and never propagates
            km._GC_FREEZE_ERRORS[0] = 0; km._GC_FREEZE_SAID[0] = False
            def boom(): raise RuntimeError("stats read failed")
            km.em.record_cache_stats = boom
            km._gc_freeze_tick(True, False)   # must not raise
            km._gc_freeze_tick(True, False)
            self.assertEqual(km._GC_FREEZE_ERRORS[0], 2, "each raising read is counted")
            self.assertTrue(km._GC_FREEZE_SAID[0], "and it is said once")
        finally:
            km._GC_FREEZE = saved_gf
            km.em.record_cache_stats = saved_stats
            km._GC_FREEZE_ERRORS[0] = saved_errs; km._GC_FREEZE_SAID[0] = saved_said

    def test_the_pusher_cycle_calls_the_tick_at_the_idle_boundary(self):
        import inspect
        km = self._km()
        src = inspect.getsource(km._pusher_cycle)
        self.assertRegex(src, r"_gc_freeze_tick\(_cycle_idle, first\)",
                         "the pusher cycle calls the freeze tick with the cycle's idle flag and first-cycle flag")


if __name__ == "__main__":
    unittest.main()
