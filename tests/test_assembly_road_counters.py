#!/usr/bin/env python3
"""T398 (2026-09-12): a boot parsed two documented live leaves whole with no fallback counted, and nothing on GET /perf named the
road the parse took. The assembly's road counters (serve, fold, restore, full with its reason, bypass, the g:<reason> demotions)
ride asmCheckpoint.parse and the boot-health row, beside asmCheckpoint.removed, the document files removed per reason."""
import json
import os
import sys
import unittest
HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
from test_asm_checkpoint import em, G, SID, NOW, Harness, kernel_module, _strip   # noqa: E402


class AssemblyRoadCounters(Harness):
    def setUp(self):
        super().setUp()
        kernel_module()                                   # the kernel's first load refreshes the event model's globals: load it
        #                                                   before any counter is read, so the row and the test see one dict

    def _reset(self):
        for k in list(em._ASM_STATS):
            em._ASM_STATS[k] = 0

    def _boot_row_parse(self):
        """The boot-health row's `parse` as the kernel writes it, over THIS test's event model (the kernel module holds its own
        instance; the row reads whichever `em` the kernel names)."""
        km = kernel_module()
        saved = (km._append_restart_cut, km._BOOT_HEALTH_DONE[0], km.em); rows = []
        km._append_restart_cut = lambda row: rows.append(row); km._BOOT_HEALTH_DONE[0] = False; km.em = em
        try:
            km._boot_health_first_cycle(1.0)
        finally:
            km._append_restart_cut, km._BOOT_HEALTH_DONE[0], km.em = saved
        self.assertEqual(len(rows), 1)
        return rows[0]["parse"]

    def test_the_roads_ride_the_perf_block_with_the_full_parses_reason(self):
        records, sent = G.SINGLE_FILE["compaction_atom"]
        path = self.write("roads", records(), sent=sent)
        self.fresh(); self._reset()
        self.parse(path)                                                  # no document yet: a full parse, its reason named
        parse = em.asm_checkpoint_stats()["parse"]
        self.assertEqual(parse.get("full:noDocument"), 1, "%s" % parse)
        self.assertEqual(parse["full"], 1)
        self.assertTrue(self.doc(path))
        self.fresh(); self._reset()
        self.parse(path)                                                  # the document restores
        parse = em.asm_checkpoint_stats()["parse"]
        self.assertEqual(parse.get("restore"), 1, "%s" % parse)
        self.parse(path)                                                  # the same tree served from the entry
        self.assertEqual(em.asm_checkpoint_stats()["parse"]["serve"], 1)
        for k in ("serve", "fold", "full", "bypass", "fallback"):
            self.assertIn(k, parse)

    def test_a_from_zero_read_that_replaces_the_leafs_entry_demotes_and_is_counted_as_such(self):
        """The cascade shape under study: an assembly entry stands, a whole reader replaces the leaf's record entry under a new
        generation, and the next parse's gates demote the entry to a FULL parse that consults no document and counted nothing
        anyone could see; now `g:rewrite` and `full:demoted` name it."""
        records, sent = G.SINGLE_FILE["compaction_atom"]
        path = self.write("demote", records(), sent=sent)
        self.fresh(); self.parse(path); self.assertTrue(self.doc(path))
        self.fresh(); self.parse(path); self._reset()                     # the entry stands, restored from the document
        with em._JSONL_CACHE_LOCK:
            em._JSONL_CACHE.pop(path, None)
        em._read_jsonl_entry(path, tail_ok=False)                          # a from-zero read: a fresh generation
        self.parse(path)
        parse = em.asm_checkpoint_stats()["parse"]
        self.assertEqual(parse.get("g:rewrite"), 1, "%s" % parse)
        self.assertEqual(parse.get("restore:afterDemote"), 1, "the demoted entry falls to the restore road (T402): %s" % parse)
        self.assertEqual(parse.get("full:demoted", 0), 0, "%s" % parse)
        row = self._boot_row_parse()
        self.assertEqual((row.get("g:rewrite"), row.get("restore:afterDemote")), (1, 1), "the boot row's values: %r" % row)

    def test_a_refused_standing_document_is_booked_as_refused_not_as_none(self):
        """Round one, medium: the restore's refusal unlinked the document before _assemble decided the reason by a stat, so a
        corrupt standing document was booked full:noDocument and a boot whose documents were all refused read as a boot that
        had none. The refusal is recorded per path before the unlink and the parse books full:refused from it."""
        records, sent = G.SINGLE_FILE["compaction_atom"]
        path = self.write("removed", records(), sent=sent)
        self.fresh(); self.parse(path); self.assertTrue(self.doc(path))
        em._asm_ckpt_file(path).write_bytes(b"not a document")
        em._ASM_CKPT_STATS["removed"] = {}
        self.fresh(); self._reset(); self.parse(path)
        st = em.asm_checkpoint_stats()
        self.assertEqual(st["removed"], {"fallback:corrupt": 1}, "%s" % st["removed"])
        self.assertFalse(em._asm_ckpt_file(path).exists())
        self.assertEqual((st["parse"].get("full:refused"), st["parse"].get("full:noDocument", 0)), (1, 0),
                         "a document that stood and did not verify: refused, not none: %s" % st["parse"])
        self.assertEqual(self._boot_row_parse().get("full:refused"), 1, "the boot row carries it")

    def test_the_boot_health_row_carries_the_parses_roads(self):
        km = kernel_module()
        saved = (km._append_restart_cut, km._BOOT_HEALTH_DONE[0])
        rows = []
        km._append_restart_cut = lambda row: rows.append(row)
        km._BOOT_HEALTH_DONE[0] = False
        try:
            km._boot_health_first_cycle(1.0)
        finally:
            km._append_restart_cut, km._BOOT_HEALTH_DONE[0] = saved
        self.assertEqual(len(rows), 1)
        self.assertIsInstance(rows[0].get("parse"), dict, "%r" % rows[0])
        for k in ("serve", "fold", "restore", "full", "bypass", "fallback"):
            self.assertIn(k, rows[0]["parse"], "seeded keys: a row without one means zero: %r" % rows[0]["parse"])
        self.assertEqual(rows[0]["parse"], em.asm_checkpoint_stats()["parse"], "the row is the perf block's parse, values and all")

    def test_a_document_write_clears_the_refusal_slot(self):
        """Follow-up, low 1: a refusal recorded by one parse was never cleared at a document write and the restore road returned
        before the pop, so after a fresh document was written a later parse with NO document standing booked full:refused."""
        records, sent = G.SINGLE_FILE["compaction_atom"]
        path = self.write("slot", records(), sent=sent)
        self.fresh(); self.parse(path); self.assertTrue(self.doc(path))
        em._asm_ckpt_file(path).write_bytes(b"not a document")
        self.fresh(); self._reset(); self.parse(path)
        self.assertEqual(em.asm_checkpoint_stats()["parse"].get("full:refused"), 1)
        em._asm_ckpt_note(path, "corrupt")                                  # a JUDGE read's refusal, recorded in the slot
        self.assertTrue(self.doc(path), "a fresh document written")          # the write clears the slot
        self.fresh(); modes = []; self.parse(path, modes); self.assertEqual(modes, ["restore"])   # the restore road: no pop
        cp = em._asm_ckpt_file(path); cp.unlink(); cp.with_name(cp.name + ".meta").unlink(missing_ok=True)
        self.fresh(); self._reset(); self.parse(path)
        parse = em.asm_checkpoint_stats()["parse"]
        self.assertEqual((parse.get("full:noDocument"), parse.get("full:refused", 0)), (1, 0), "no document standing: noDocument: %s" % parse)

    def test_every_road_counter_write_goes_through_the_locked_helper(self):
        """Follow-up, low 3: the lock covered two of ten writes; every increment goes through _asm_stat under _ASM_CKPT_LOCK."""
        import inspect, re
        src = inspect.getsource(em)
        bare = [l.strip() for l in src.splitlines() if "_ASM_STATS[" in l and ("+=" in l or "= _ASM_STATS.get(" in l)
                and "(key, 0) + n" not in l]                                # the helper's own line
        self.assertEqual(bare, [], "bare writes: %r" % bare)
        self.assertGreaterEqual(len(re.findall(r"_asm_stat\(", src)), 10)
        self.assertIn("with _ASM_CKPT_LOCK:", inspect.getsource(em._asm_stat))

    def test_the_boot_sweep_counts_the_documents_it_removes(self):
        """Follow-up, low 6: `removed["sweep"]` had no test."""
        records, sent = G.SINGLE_FILE["compaction_atom"]
        path = self.write("swept", records(), sent=sent)
        self.fresh(); self.parse(path); self.assertTrue(self.doc(path))
        em._ASM_CKPT_STATS["removed"] = {}
        os.unlink(path)                                                     # the transcript vanishes: the sweep removes its document
        em.checkpoint_sweep()
        self.assertEqual(em.asm_checkpoint_stats()["removed"], {"sweep": 1})
        self.assertFalse(em._asm_ckpt_file(path).exists())

    SIBLING = "cccccccc-0000-0000-0000-000000000000"

    def _five_shape_file(self, name, resume=False):
        """Three turns, an attached compaction, two turns: the document's pre-cut records u1 a1 u2 a2 u3 a3 (the spine tip a3).
        With `resume`, a sibling file beside the leaf holds x1 x2 and u1 parents x2 (a two-file lineage)."""
        t0 = NOW
        recs = [G.uline(t0, "first ask", "u1", "x2" if resume else None), G.aline(t0 + 10, "first reply", "a1", "u1", stop="end_turn"),
                G.uline(t0 + 20, "second ask", "u2", "a1"), G.aline(t0 + 30, "second reply", "a2", "u2", stop="end_turn"),
                G.uline(t0 + 40, "third ask", "u3", "a2"), G.aline(t0 + 50, "third reply", "a3", "u3", stop="end_turn"),
                G.compact_line(t0 + 600, "b1", "a3"), G.compact_summary_line(t0 + 601, "s1", "b1"),
                G.uline(t0 + 610, "after the compaction", "u4", "s1"), G.aline(t0 + 620, "fourth reply", "a4", "u4", stop="end_turn"),
                G.uline(t0 + 630, "then more", "u5", "a4"), G.aline(t0 + 640, "fifth reply", "a5", "u5", stop="end_turn")]
        path = self.write(name, recs)
        if resume:
            sib = os.path.join(os.path.dirname(path), self.SIBLING + ".jsonl")
            with open(sib, "w") as fh:
                for r in [G.uline(t0 - 100, "sibling parent ask", "x1"), G.aline(t0 - 80, "sibling reply", "x2", "x1", stop="end_turn")]:
                    fh.write(json.dumps(r) + "\n")
            return path, t0, sib
        return path, t0

    def _parse_lineage(self, path, cands, modes=None):
        tree = em.parse_session(path, rompuuid=SID, name="impl", dir="/TESTDIR", candidate_files=list(cands),
                                states=None, postal_log=[], now=NOW, asm_mode_out=modes)
        self._trees[path] = tree
        return tree

    def _cold(self, path, cands=None):
        self.fresh(); saved = em._CKPT_DIR_FN; em._CKPT_DIR_FN = None
        try:
            return _strip(self._parse_lineage(path, cands or [path]))
        finally:
            em._CKPT_DIR_FN = saved

    def _append(self, path, recs):
        with open(path, "a") as fh:
            for r in recs:
                fh.write(json.dumps(r) + "\n")

    def _served(self, path, cands=None):
        """The tree the parse serves now, hydrated and stripped, with the parse counters."""
        with em._JSONL_CACHE_LOCK:
            em._RECORD_CACHE_STATS["wholeReads"] = {}
        tree = self._parse_lineage(path, cands or [path])
        em.hydrate(tree, SID)                                               # a restored tree's bodies, so the strip can read them
        return _strip(tree), em.asm_checkpoint_stats()["parse"], em.record_cache_stats()["wholeReads"]

    # The tail shapes (appended past the document's cut) and whether the tail chains onto the document: "restore" when every
    # parent-bearing record parents the pre-cut spine tip (a3) or a tail record, "whole" otherwise.
    SHAPES = {
        "a_rewind_pre_interior": (lambda t0: [G.uline(t0 + 700, "a rewind before the cut", "u_rw", "a1")], "whole"),
        "b_clear_fork": (lambda t0: [G.uline(t0 + 700, "a clear fork", "u_fork", None)], "whole"),
        "c_api_error_spur_at_opener": (lambda t0: [G.api_error_line(t0 + 700, "e1", "u5"), G.uline(t0 + 710, "after the spur", "u6", "e1")], "restore"),
        "d_rewind_post_cut": (lambda t0: [G.uline(t0 + 700, "a rewind after the cut", "u_rw2", "a4")], "restore"),
        "e_rewind_spine_tip": (lambda t0: [G.uline(t0 + 700, "a rewind onto the cut", "u_rw3", "a3")], "restore"),
        "f_two_step_rewind": (lambda t0: [G.uline(t0 + 700, "a rewind after the cut", "u_r1", "a4"), G.aline(t0 + 710, "its reply", "a_r1", "u_r1", stop="end_turn"),
                                          G.uline(t0 + 720, "then a rewind before the cut", "u_r2", "a2")], "whole"),
        "g_later_crossing": (lambda t0: [G.uline(t0 + 700, "chains on", "u6", "a5"), G.aline(t0 + 710, "reply", "a6", "u6", stop="end_turn"),
                                         G.uline(t0 + 720, "then crosses into the interior", "u7", "a1")], "whole"),
        "h_orphan_parent": (lambda t0: [G.uline(t0 + 700, "an orphan", "u_o", "00000000-no-such-record")], "whole"),
        "i_interior_api_error_alone": (lambda t0: [G.api_error_line(t0 + 700, "e2", "a1")], "whole"),
        "j_interior_api_error_with_reply": (lambda t0: [G.api_error_line(t0 + 700, "e2", "a1"), G.uline(t0 + 710, "after the spur", "u6", "e2")], "whole"),
        "k_stop_hook_summary_spur": (lambda t0: [G.stop_hook_line(t0 + 700, "sh1", "a2")], "whole"),
        "l_boundary_in_tail": (lambda t0: [G.compact_line(t0 + 700, "b2", "a5"), G.compact_summary_line(t0 + 701, "s2", "b2"),
                                           G.uline(t0 + 710, "after a second compaction", "u6", "s2")], "boundary"),
    }

    def _documented(self, name, resume=False):
        """A five-shape file with its document standing and its entry restored from it; the counters reset."""
        made = self._five_shape_file(name, resume=resume)
        path, cands = made[0], ([made[0], made[2]] if resume else [made[0]])
        self.fresh(); self._parse_lineage(path, cands); self.assertTrue(self.doc(path))
        self.fresh(); self._parse_lineage(path, cands); self._reset()          # the entry stands, restored from the document
        return made

    def _check(self, name, tree, parse, reads, road, path, cands=None, reason="descent", boot=False):
        if reason is not None:
            self.assertEqual(parse.get("g:" + reason), 1, "%s: the gates demoted the entry for %s: %s" % (name, reason, parse))
        if road == "restore":
            self.assertEqual(parse.get("restore"), 1, "%s: the restore road: %s" % (name, parse))
            self.assertEqual(parse.get("restore:afterDemote", 0), 0 if boot else 1, "%s: %s" % (name, parse))
            if not boot and reason != "rewrite":                          # a boot's parse primes the leaf's reader entry from zero
                self.assertEqual(reads, {}, "%s: no whole read" % name)   #  before the assembly (unchanged here); a rewrite IS a
                #                                                            from-zero read of the leaf
        elif road == "whole":
            self.assertEqual(parse.get("restore:chainRefused"), 1, "%s: the tail does not chain onto the document: %s" % (name, parse))
            self.assertEqual(parse.get("full:refused" if boot else "full:demoted"), 1, "%s: the whole parse: %s" % (name, parse))
        else:
            self.assertEqual(parse.get("full:demoted"), 1, "%s: a boundary in the tail parses whole: %s" % (name, parse))
        self.assertEqual(tree, self._cold(path, cands), "%s: the tree equals a cold whole parse" % name)

    def test_a_restore_over_a_document_stands_only_when_the_tail_chains_onto_it(self):
        """T402 rounds one and two: a restore over a document (after a descent demotion here) serves the document's pre-cut
        verdicts as they stand, so a tail that re-parents into the pre-cut interior, forks from a null root, anchors a system spur
        before the cut or names a parent no transcript holds must refuse to the whole parse, whatever the record's type; a tail
        whose every parent is the pre-cut spine tip or a tail record chains on. Twelve shapes, each against a cold whole parse."""
        for name, (tail, road) in self.SHAPES.items():
            with self.subTest(shape=name):
                path, t0 = self._documented("shape-" + name)
                self._append(path, tail(t0))
                em._read_jsonl_entry(path, tail_ok=True)                   # the entry grows; the gates see the delta
                tree, parse, reads = self._served(path)
                self._check(name, tree, parse, reads, road, path, reason="boundary" if road == "boundary" else "descent")

    def test_the_chain_rule_runs_for_a_rewrite_demotion_after_the_caches_own_eviction(self):
        """Round two, medium 1: the rule ran for descent only, and a plain LRU eviction of the leaf's record entry (the cache's byte
        budget) makes the next parse's reason g:rewrite, which reached the restore unguarded. The entry is evicted through the
        cache's own loop (a budget of one byte and a read of another file), never popped by hand."""
        for name in ("a_rewind_pre_interior", "b_clear_fork", "c_api_error_spur_at_opener"):
            with self.subTest(shape=name):
                tail, road = self.SHAPES[name]
                path, t0 = self._documented("evict-" + name)
                self._append(path, tail(t0))
                other = self.write("evict-other-" + name, [G.uline(t0, "another file", "o1")])
                saved = em._JSONL_CACHE_BUDGET_BYTES; em._JSONL_CACHE_BUDGET_BYTES = 1
                try:
                    em._read_jsonl_entry(other, tail_ok=False)             # the insert evicts the leaf's entry: the cache's own loop
                finally:
                    em._JSONL_CACHE_BUDGET_BYTES = saved
                with em._JSONL_CACHE_LOCK:
                    self.assertNotIn(path, em._JSONL_CACHE, "the leaf's record entry evicted")
                tree, parse, reads = self._served(path)
                self._check(name, tree, parse, reads, road, path, reason="rewrite")

    def test_a_nonleaf_demotion_is_refused_by_the_loads_lineage_witness_before_any_chain_rule(self):
        """Round two: the nonleaf demotion driven. A lineage file that grew (or was touched) demotes the entry as nonleaf; the
        document's own byte checks refuse it first (the skipped file's stat witness: fallbacks.lineage), and the parse is whole,
        equal to a cold parse. The rule's other nonleaf road, a lineage file's reader entry replaced under a new generation
        (the gates' line for a file with a cut of its own), is not reachable from these shapes: the writer skips every lineage
        file whose records all sort before the cut, which a resume parent's do, a fork of its own stamped after the compaction
        included (probed: pre 3 of 3, skip). The chain rule itself is one call inside _asm_restore, shared by every reason."""
        path, t0, sib = self._documented("nonleaf-grown", resume=True)
        self._append(sib, [G.uline(t0 - 60, "the sibling grows", "x3", "x2")])
        em._read_jsonl_entry(sib, tail_ok=True)
        fb0 = em.asm_checkpoint_stats()["fallbacks"].get("lineage", 0)
        tree, parse, reads = self._served(path, [path, sib])
        self.assertEqual((parse.get("g:nonleaf"), parse.get("full:demoted"), parse.get("restore:chainRefused", 0), parse.get("restore", 0)),
                         (1, 1, 0, 0), "%s" % parse)
        self.assertEqual(em.asm_checkpoint_stats()["fallbacks"].get("lineage", 0) - fb0, 1, "the load's lineage witness refused it")
        self.assertEqual(tree, self._cold(path, [path, sib]))

    def test_the_chain_rule_runs_for_the_boot_restore_too(self):
        """Round two, item A: with no assembly entry (every kernel boot, every eviction of the entry) the restore ran with no tail
        check, so a document standing over a rewound or forked tail restored as round one described at the next start. The one
        rule runs on every restore over a document; a refused boot restore falls to the whole parse and books restore:chainRefused."""
        for name in ("a_rewind_pre_interior", "b_clear_fork", "i_interior_api_error_alone", "c_api_error_spur_at_opener", "e_rewind_spine_tip"):
            with self.subTest(shape=name):
                tail, road = self.SHAPES[name]
                path, t0 = self._documented("boot-" + name)
                self._append(path, tail(t0))
                self.fresh(); self._reset()                                  # a boot: no entry, the document on disk
                tree, parse, reads = self._served(path)
                self._check(name, tree, parse, reads, road, path, reason=None, boot=True)

    def test_whole_reads_and_hydrations_are_counted_under_the_calling_threads_stage(self):
        """T401: the first instrumented boot said jobs.autoNudge read 162.8 MB, and the callers' rows could not say which caller
        inside that job read it. The kernel marks the thread's stage for each tick job and the push; the event model counts
        every whole read and hydration under (stage, caller) too, `none` outside the cycle."""
        km = kernel_module()
        records, sent = G.SINGLE_FILE["compaction_atom"]
        path = self.write("bystage", records(), sent=sent)
        self.fresh(); self.parse(path); self.assertTrue(self.doc(path))
        self.fresh()
        with em._JSONL_CACHE_LOCK:
            em._RECORD_CACHE_STATS["wholeReads"] = {}; em._RECORD_CACHE_STATS["wholeReadsByStage"] = {}
        em._ASM_CKPT_STATS["hydratedByStage"] = {}
        tree = km._job_stage("probe", lambda: self.parse(path))           # a restore inside a job: no whole read
        km._job_stage("probe", lambda: em.hydrate([a for t in tree["turns"] for a in t["atoms"] if a.get("lazy") is not None][:2], by="probeReader"))
        km._job_stage("probe", lambda: em._read_jsonl_entry(path, tail_ok=False))   # a whole read inside the job
        st = em.record_cache_stats()
        by_stage = st["wholeReadsByStage"]
        self.assertTrue(any(k.startswith("jobs.probe:upgrade<-") for k in by_stage), "the whole read under its job: %r" % by_stage)
        hb = em.asm_checkpoint_stats()["hydratedByStage"]
        self.assertTrue(any(k.startswith("jobs.probe:probeReader") for k in hb), "the hydration under its job: %r" % hb)
        with em._JSONL_CACHE_LOCK:
            em._JSONL_CACHE.pop(path, None)
        em._read_jsonl_entry(path, tail_ok=False)                          # outside any stage
        self.assertTrue(any(k.startswith("none:zero<-") for k in em.record_cache_stats()["wholeReadsByStage"]), "outside the cycle: none")
        self.assertIsNone(km._current_read_stage(), "the mark returns after the job")

    def test_the_push_mark_is_restored_on_every_exit_and_the_pushs_reads_count_under_push(self):
        """T401 round one, medium: _push set the thread's mark inline and restored it at its end, so a caught build failure returned
        before the restore and the pusher thread stayed marked `push` for the process's life, booking every later read outside a
        stage under push:. The mark is a decorator with a finally. And a read inside the push books push:<kind><-<caller>."""
        km = kernel_module()
        saved = (km._chat_tab_sessions, km._live_map, km.NAMES)
        def restore():
            km._chat_tab_sessions, km._live_map, km.NAMES = saved
        self.addCleanup(restore)
        km._live_map = lambda: {}; km.NAMES = {}
        def boom(now, live_map):
            raise RuntimeError("a synthetic build failure")
        km._chat_tab_sessions = boom
        import io
        err = io.StringIO(); saved_err = sys.stderr; sys.stderr = err
        try:
            km._push([{"app": "chat", "wid": "lab", "send": lambda *a, **k: None, "alive": True, "dedup": {}}], live_map={})
        except Exception:
            pass
        finally:
            sys.stderr = saved_err
        self.assertIsNone(km._current_read_stage(), "the mark is restored after a build failure (the leak)")
        # a read inside the push books push:<kind><-<caller>
        records, sent = G.SINGLE_FILE["compaction_atom"]
        path = self.write("pushread", records(), sent=sent)
        self.fresh()
        with em._JSONL_CACHE_LOCK:
            em._RECORD_CACHE_STATS["wholeReadsByStage"] = {}
        km._chat_tab_sessions = lambda now, live_map: (em._read_jsonl_entry(path, tail_ok=False), [])[1]   # a whole read inside the push
        try:
            km._push([{"app": "chat", "wid": "lab", "send": lambda *a, **k: None, "alive": True, "dedup": {}}], live_map={})
        except Exception:
            pass
        rows = em.record_cache_stats()["wholeReadsByStage"]
        self.assertTrue(any(k.startswith("push:zero<-") for k in rows), "the push's read under its mark: %r" % rows)
        self.assertIsNone(km._current_read_stage())
        self.assertTrue(hasattr(km._push, "__wrapped__"), "the push carries the stage decorator (set at entry, restored in a finally)")

if __name__ == "__main__":
    unittest.main()
