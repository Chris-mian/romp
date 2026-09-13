#!/usr/bin/env python3
"""T323 stage 4a (2026-09-11): the assembly checkpoint. A document per leaf transcript records everything before the
cut (the turn holding the last compaction boundary) as identities and record locations, never bodies, plus the
carried emit state and the pre-cut graph facts; a fresh process verifies it, rebuilds the pre-cut turns as lazy atoms,
reads the leaf from the cut's byte offset only, parses that tail through a seeded adapter and proves the prefix by a
hash of its ids. Pinned here over every golden scenario that holds a compaction: the restored tree, hydrated, equals
the whole parse's byte for byte (turn ids, segment ids, atom uuids and bodies); folds after the restore keep equal;
a compaction landing after the document demotes to a whole parse; a rewrite under the cut's guard, a wrong version, a
moved session and a corrupt document each fall back loudly, counted; a body read before hydration is loud; the bytes
the restore reads are the document, the cut's guard and the tail. Synthetic transcripts only (the golden builders)."""
import json
import os
import time
import shutil
import tempfile
import unittest
from pathlib import Path
from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
em = load_source("romp_event_model", os.path.join(BIN, "romp-event-model"))
import sys
sys.path.insert(0, HERE)
import test_event_model_golden as G   # noqa: E402  the synthetic scenario builders

SID = G.SID
NOW = G.NOW
COMPACTING = [n for n in G.SINGLE_FILE if any(r.get("subtype") == "compact_boundary" for r in G.SINGLE_FILE[n][0]())]


def _last_uuid(recs):
    return next((r["uuid"] for r in reversed(recs) if r.get("uuid")), None)


def compacting_variant(recs, tag):
    """A golden scenario's records followed by a compaction (the CLI's shape: the boundary anchored on the last record, its
    summary child, the conversation chaining on) and two more turns: the original scenario becomes the pre-cut part, so its
    every atom kind (forks, rewinds, clears, absorbed attachments, skill atoms, command output, postal authors) is restored
    from the document and compared with the whole parse."""
    t1 = max((em.parse_z(r.get("timestamp")) or 0) for r in recs if r.get("timestamp")) + 600
    b, sm = "b_%s" % tag, "s_%s" % tag
    more = [G.compact_line(t1, b, _last_uuid(recs)),
            G.compact_summary_line(t1 + 1, sm, b),
            G.uline(t1 + 10, "after the compaction, what remains?", "u_%s_1" % tag, sm),
            G.aline(t1 + 20, "the cap and the retry budget remain", "a_%s_1" % tag, "u_%s_1" % tag, stop="end_turn"),
            G.uline(t1 + 30, "then close them out", "u_%s_2" % tag, "a_%s_1" % tag),
            G.aline(t1 + 40, "closing both", "a_%s_2" % tag, "u_%s_2" % tag, stop="end_turn")]
    return list(recs) + more


def _doc(path):
    """The leaf's assembly document, decoded (stored gzipped)."""
    import gzip
    return json.loads(gzip.decompress(em._asm_ckpt_file(path).read_bytes()))


def _write_doc(path, d):
    import gzip
    em._asm_ckpt_file(path).write_bytes(gzip.compress(json.dumps(d).encode("utf-8")))


def _strip(tree):
    """A tree as JSON compares it: lazy scalars dropped once hydrated (the whole parse never carries them); a restored
    tree's pre-cut turns are built into plain turns first (em.plain_tree, T323 stage 4c)."""
    t = json.loads(json.dumps(em.plain_tree(tree), default=lambda o: "<unserializable>"))
    t.pop("cutTurn", None)                                  # where the lazy atoms ended: a restored tree's own fact (stage 4b)
    for turn in t["turns"]:
        for a in turn["atoms"]:
            a.pop("lazy", None)
    return t


class Harness(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.ck = self.td / "checkpoints"
        em.set_checkpoint_dir(lambda: self.ck)
        self.states, self.sent = None, []                       # what parse() hands the parser until write() sets them
        self._trees = {}                                         # path → the tree parse() last returned (doc() writes with it)
        self.fresh()
        em._ASM_CKPT_STATS.update(written=0, restored=0, fallbacks={}, skipped={}, hydratedBytes=0, hydratedAtoms=0, hydratedBy={})

    def tearDown(self):
        em.set_checkpoint_dir(None)
        shutil.rmtree(self.td, ignore_errors=True)

    def fresh(self):
        """A kernel restart's in-memory side: every reader entry, assembly entry, hydrated body and pending restore gone."""
        with em._JSONL_CACHE_LOCK:
            em._JSONL_CACHE.clear()
        with em._ASM_LOCK:
            em._ASM_CACHE.clear()
        em._TRAILING_CACHE.clear()
        with em._ASM_CKPT_LOCK:
            em._HYDRATED.clear(); em._HYDRATED_BYTES[0] = 0
        em._LAZY_FILES.clear()
        with em._READ_BYTES_LOCK:
            em._READ_BYTES.clear()

    def write(self, name, records, states=None, sent=None):
        d = self.td / name                                      # a directory per scenario: no stale document at a reused path
        d.mkdir(exist_ok=True)
        p = d / (SID + ".jsonl")
        p.write_text("".join(json.dumps(r) + "\n" for r in records))
        self.states = G.IDLE_STATES if name == "idle_atom" else states
        self.sent = sent or []
        return str(p)

    def parse(self, path, modes=None):
        tree = em.parse_session(path, rompuuid=SID, name="impl", dir="/TESTDIR", candidate_files=[path],
                                states=self.states, postal_log=self.sent, now=NOW, asm_mode_out=modes)
        self._trees[path] = tree
        return tree

    def doc(self, path):
        """The leaf's document, written from its whole entry with the tree the last parse() of that path returned (the kernel
        hands the store's live tree, which gives the document its turns section: T323 stage 4c). A test that parsed the
        path through em.parse_session itself gets a document with no turns section (the atoms-only form)."""
        return em.asm_checkpoint_write(path, SID, tree=self._trees.get(path))

    def cold(self, path):
        self.fresh()
        saved = em._CKPT_DIR_FN
        em._CKPT_DIR_FN = None
        try:
            return _strip(self.parse(path))
        finally:
            em._CKPT_DIR_FN = saved

    def restored(self, path):
        """A fresh process parsing with the document in place: the tree hydrated, its mode, and the lazy count; the bytes
        the leaf cost BEFORE hydration are kept in self.read_before."""
        self.fresh()
        modes = []
        tree = self.parse(path, modes)
        self.read_before = em.read_bytes_report().get(path, 0)
        n_lazy = sum(1 for t in tree["turns"] for a in t["atoms"] if a.get("lazy") is not None)
        em.hydrate(tree, SID)
        return _strip(tree), modes, n_lazy

    @staticmethod
    def after(records, dt):
        """A time past every stamp in `records` by `dt` seconds (an append must not regress the fold's timestamp gate)."""
        return max(em.parse_z(r.get("timestamp")) or 0 for r in records if r.get("timestamp")) + dt


_KM = []


def kernel_module():
    """The kernel (and through it the judge, km.jd) loaded ONCE for this module: the judge module is one object for the
    whole test process, so a second load_source of it re-executes it under every test that already holds it."""
    if not _KM:
        os.environ.setdefault("ROMP_KERNEL_NO_OPEN", "1")
        _KM.append(load_source("romp_kernel_t323s4a", os.path.join(BIN, "romp-kernel")))
    return _KM[0]


class RestoredEqualsWhole(Harness):
    def test_every_compacting_golden_scenario_restores_identical(self):
        self.assertTrue(COMPACTING, "the golden set holds compaction scenarios")
        for name in COMPACTING:
            with self.subTest(scenario=name):
                records, sent = G.SINGLE_FILE[name]
                path = self.write(name, records(), sent=sent)
                whole = self.cold(path)
                self.fresh()
                self.parse(path)                                        # the whole parse the writer works from
                self.assertTrue(self.doc(path), "a document is written: %s" % em.asm_checkpoint_stats())
                doc = _doc(path)
                self.assertGreater(len(doc["atoms"]), 0, "the cut leaves atoms before it")
                got, modes, n_lazy = self.restored(path)
                self.assertEqual(modes, ["restore"], "the assembly came from the document: %s" % em.asm_checkpoint_stats())
                self.assertGreater(n_lazy, 0, "the pre-cut atoms were lazy before hydration")
                self.assertEqual(got, whole, "restored and hydrated equals the whole parse")
                self.assertEqual(em.asm_checkpoint_stats()["fallbacks"], {})
                size = os.path.getsize(path)
                self.assertLess(self.read_before, size, "the leaf was not read whole before hydration: %d of %d bytes" % (self.read_before, size))

    def test_every_golden_scenario_made_to_compact_restores_identical(self):
        """Review find (F): only the three natively compacting scenarios were restored. Every single-file golden scenario
        gets a compaction appended, so its atoms (forks, rewinds, a /clear, absorbed attachments, skill atoms, command
        output, postal authors, eclipsed and broken chains) are the pre-cut part restored from a document."""
        restored, skipped = [], {}
        for name in G.SINGLE_FILE:
            with self.subTest(scenario=name):
                records, sent = G.SINGLE_FILE[name]
                recs = compacting_variant(records(), name[:6])
                path = self.write("variant-" + name, recs, sent=sent)
                whole = self.cold(path)
                self.fresh(); self.parse(path)
                em._ASM_CKPT_STATS["skipped"] = {}
                wrote = self.doc(path)
                if not wrote:
                    skipped[name] = dict(em.asm_checkpoint_stats()["skipped"])
                    continue
                got, modes, n_lazy = self.restored(path)
                self.assertEqual(modes, ["restore"], name)
                self.assertGreater(n_lazy, 0)
                self.assertEqual(got, whole, "restored and hydrated equals the whole parse: %s" % name)
                self.assertEqual(em.asm_checkpoint_stats()["fallbacks"], {})
                restored.append(name)
        self.assertEqual(sorted(restored), ["author_kinds", "broken_chain_kept", "clear_breaks_lineage", "compaction_atom",
                                            "compaction_broken_stitch", "eclipsed_branch_kept", "idle_atom", "manual_compact_detached",
                                            "multi_input_absorbed", "popall", "queued_new_turn", "retry_superseded", "rewind_off_path",
                                            "slash_command_turn"], "every single-file golden scenario, made to compact, writes and restores")
        self.assertEqual(skipped, {}, "none is unsplittable")

    def test_a_two_file_lineage_made_to_compact_restores_identical(self):
        """The resume-lineage scenario (two files, a recorded resume fork) with a compaction in the leaf: the prior file is
        wholly before the cut, witnessed by its stat and never read at restore."""
        d = self.td / "lineage"; d.mkdir()
        pa, pb = d / (G.FSID_A + ".jsonl"), d / (G.FSID_B + ".jsonl")
        recs_b = compacting_variant(G.scenario_resume_lineage_fileB(), "lin")
        pa.write_text("".join(json.dumps(r) + "\n" for r in G.scenario_resume_lineage_fileA()))
        pb.write_text("".join(json.dumps(r) + "\n" for r in recs_b))
        states = getattr(G, "RESUME_STATES", None)
        cands = [str(pa), str(pb)]

        def parse(modes=None):
            return em.parse_session(str(pb), rompuuid=SID, name="impl", dir="/TESTDIR", candidate_files=cands, states=states,
                                    postal_log=[], now=NOW, asm_mode_out=modes)
        self.fresh(); saved = em._CKPT_DIR_FN; em._CKPT_DIR_FN = None
        try:
            whole = _strip(parse())
        finally:
            em._CKPT_DIR_FN = saved
        self.fresh(); parse()
        self.assertTrue(self.doc(str(pb)), em.asm_checkpoint_stats())
        doc = _doc(str(pb))
        self.assertIn(G.FSID_A, doc["files"])
        self.fresh(); modes = []
        tree = parse(modes)
        self.assertEqual(modes, ["restore"])
        self.assertTrue(doc["files"][G.FSID_A].get("skip"), "the prior file is wholly before the cut")
        self.assertEqual(em.read_bytes_report().get(str(pa), 0), 0, "a prior file wholly before the cut is never read at restore: %s" % em.read_bytes_report())
        em.hydrate(tree, SID)                                   # hydration reads its atoms' records, in the prior file too
        self.assertGreater(em.read_bytes_report().get(str(pa), 0), 0, "hydration seeks into the prior file for its atoms")
        self.assertEqual(_strip(tree), whole)
        os.utime(pa, (NOW, NOW))                                # the prior file's stat moves: the lineage witness fails
        self.fresh(); modes = []
        tree = parse(modes)
        self.assertEqual(modes, ["full"])
        self.assertIn("lineage", em.asm_checkpoint_stats()["fallbacks"])

    def test_appends_after_the_restore_fold_and_stay_equal(self):
        records, _ = G.SINGLE_FILE["compaction_atom"]
        recs = records()
        path = self.write("compaction_atom", recs)
        self.fresh(); self.parse(path); self.assertTrue(self.doc(path))
        got, modes, _ = self.restored(path)
        last = recs[-1]
        t1 = self.after(recs, 100)
        more = [G.uline(t1, "and then the cap", "u_more", last.get("uuid")),
                G.aline(t1 + 10, "two minutes, as before", "a_more", "u_more", stop="end_turn")]
        with open(path, "a") as f:
            for r in more:
                f.write(json.dumps(r) + "\n")
        modes = []
        tree = self.parse(path, modes)
        em.hydrate(tree, SID)
        self.assertEqual(modes, ["fold"], "the appended records folded onto the restored entry")
        self.assertEqual(_strip(tree), self.cold(path))

    def test_a_compaction_after_the_document_demotes_to_a_whole_parse(self):
        records, _ = G.SINGLE_FILE["compaction_atom"]
        recs = records()
        path = self.write("compaction_atom", recs)
        self.fresh(); self.parse(path); self.assertTrue(self.doc(path))
        self.restored(path)
        last = recs[-1]
        t1 = self.after(recs, 100)
        b = G.compact_line(t1, "b_new", last.get("uuid"))
        with open(path, "a") as f:
            f.write(json.dumps(b) + "\n")
            f.write(json.dumps(G.compact_summary_line(t1 + 1, "s_new", "b_new")) + "\n")
        modes = []
        tree = self.parse(path, modes)
        self.assertEqual(modes, ["full"], "a new boundary in the tail demotes to a whole parse, as before")
        self.assertEqual(_strip(tree), self.cold(path))


class Fallbacks(Harness):
    def _armed(self, tag):
        records, _ = G.SINGLE_FILE["compaction_atom"]
        path = self.write("compaction_atom-" + tag, records())
        self.fresh(); self.parse(path); self.assertTrue(self.doc(path))
        return path

    def test_each_reason_falls_back_to_a_whole_parse_and_is_counted(self):
        for reason, spoil in (
            ("version", lambda p: _write_doc(p, dict(_doc(p), av=99))),
            ("session", lambda p: _write_doc(p, dict(_doc(p), rompuuid="other"))),
            ("corrupt", lambda p: em._asm_ckpt_file(p).write_bytes(b"{nope")),
            ("guard", lambda p: self._rewrite_prefix(p)),
            ("identity", lambda p: self._spoil_identity(p)),
            ("shrunk", lambda p: self._shrink(p)),
            ("rewrite", lambda p: self._same_size_new_mtime(p)),
            ("inputs", lambda p: _write_doc(p, dict(_doc(p), cands=["/elsewhere/other.jsonl"]))),
            ("restore", lambda p: _write_doc(p, dict(_doc(p), records=[["bad"]]))),
        ):
            with self.subTest(reason=reason):
                path = self._armed(reason)
                em._ASM_CKPT_STATS["fallbacks"] = {}
                spoil(path)
                whole = self.cold(path)
                got, modes, _ = self.restored(path)
                self.assertEqual(modes, ["full"], reason)
                self.assertEqual(em.asm_checkpoint_stats()["fallbacks"], {reason: 1}, reason)
                self.assertEqual(got, whole)
                self.assertFalse(em._asm_ckpt_file(path).exists(), "the document that did not verify is gone")

    def _rewrite_prefix(self, path):
        """A rewrite under the cut's guard: the last pre-cut line changed and the file grown past its recorded size, so
        the size check passes and the guard bytes are what catch it."""
        lines = open(path).read().splitlines(keepends=True)
        doc = _doc(path)
        pre_n = doc["files"][SID]["cut"][1]
        r = json.loads(lines[pre_n - 1]); r["message"] = {"role": r["message"].get("role", "user"), "content": "REWRITTEN under the guard " + "x" * 400}
        lines[pre_n - 1] = json.dumps(r) + "\n"                 # longer than before, so the size check passes and the guard decides
        lines.append(json.dumps(G.uline(self.after([json.loads(x) for x in lines], 100), "appended after the rewrite", "u_rw", None)) + "\n")
        with open(path, "w") as f:
            f.writelines(lines)

    def _shrink(self, path):
        cut_off = _doc(path)["files"][SID]["cut"][0]              # the file ends before the recorded cut: a shrink
        data = open(path, "rb").read()
        open(path, "wb").write(data[:max(0, cut_off - 1)])

    def _same_size_new_mtime(self, path):
        data = open(path, "rb").read()
        open(path, "wb").write(data)
        os.utime(path, (NOW + 7, NOW + 7))

    def test_the_write_valves_are_counted(self):
        """Review find (K): a document past the cap is not written; a tree whose chronological order the cut cannot split
        (a pre-cut record stamped after the tail) is not written; both counted, and the session parses whole."""
        records, _ = G.SINGLE_FILE["compaction_atom"]
        path = self.write("valves", records())
        self.fresh(); self.parse(path)
        saved = em._ASM_CKPT_CAP
        em._ASM_CKPT_CAP = 10
        try:
            self.assertFalse(self.doc(path))
        finally:
            em._ASM_CKPT_CAP = saved
        self.assertEqual(em.asm_checkpoint_stats()["skipped"].get("oversize"), 1)
        self.assertFalse(em._asm_ckpt_file(path).exists())
        recs = records()
        first = recs[0]; first["timestamp"] = em.datetime.fromtimestamp(G.T0 + 10 ** 6, em.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z") if hasattr(em, "timezone") else "2099-01-01T00:00:00.000Z"
        path2 = self.write("valves-order", recs)
        self.fresh(); self.parse(path2)
        em._ASM_CKPT_STATS["skipped"] = {}
        wrote = self.doc(path2)
        self.assertFalse(wrote, "a pre-cut record stamped after every tail record cannot be split off")
        self.assertEqual(em.asm_checkpoint_stats()["skipped"], {"unsplittable": 1})

    def _spoil_identity(self, path):
        _write_doc(path, dict(_doc(path), identity="0" * 40))


class SkillLoadCarry(Harness):
    def test_a_pre_cut_skill_load_is_reported_from_a_restored_tree(self):
        """The harness's own skill load (T333: a bare-named <skill-format> wrapper the emit skips, reported as skillLoads for
        the judges' anchor stamp) before the cut rides the document's carry: the restored tree reports it as the whole
        parse does, with no body read."""
        skill = "notes-review"
        wrapper = ("<command-message>%s</command-message>\n<command-name>%s</command-name>\n"
                   "<skill-format>true</skill-format>" % (skill, skill))
        t0 = NOW - 7200
        recs = [G.uline(t0, "Add retries to the notes-api client", "u1", None),
                dict(G.uline(t0 + 1, wrapper, "u2", "u1"), isMeta=True),
                dict(G.uline(t0 + 1, "# Notes review reference\n\nHow to review notes.", "u3", "u2"), isMeta=True),
                G.aline(t0 + 60, "Adding the retry loop to the client.", "a1", "u3", stop="tool_use"),
                G.aline(t0 + 400, "Wrote the retry loop with a test.", "a2", "a1", stop="end_turn")]
        path = self.write("skill-load", compacting_variant(recs, "skl"))
        whole = self.cold(path)
        self.assertEqual(whole["skillLoads"], {"u2": skill}, "the whole parse reports the wrapper")
        self.fresh(); self.parse(path); self.assertTrue(self.doc(path), em.asm_checkpoint_stats())
        self.fresh(); modes = []
        tree = self.parse(path, modes)
        self.assertEqual(modes, ["restore"])
        self.assertEqual(tree["skillLoads"], {"u2": skill}, "restored from the carry, before any hydration")
        em.hydrate(tree, SID)
        self.assertEqual(_strip(tree), whole)


class WriteValves(Harness):
    def _whole(self, name="valve"):
        records, sent = G.SINGLE_FILE["compaction_atom"]
        path = self.write(name, records(), sent=sent)
        self.fresh(); self.parse(path)
        em._ASM_CKPT_STATS["skipped"] = {}
        return path

    def test_a_reconstruction_that_would_not_reproduce_the_ids_writes_nothing(self):
        """Review find (E): the identity is the whole parse's; a document whose lazy reconstruction would not reproduce
        it is not written, counted. Driven by answering the reconstruction's hash differently from the whole's."""
        path = self._whole()
        real, calls = em._pre_tree_identity, []
        def identity(atoms, rompuuid):
            calls.append(len(atoms))
            h = real(atoms, rompuuid)
            return h if len(calls) == 1 else "0" * len(h)          # the whole's hash, then a reconstruction that differs
        em._pre_tree_identity = identity
        try:
            self.assertFalse(self.doc(path))
        finally:
            em._pre_tree_identity = real
        self.assertEqual(len(calls), 2, "the whole parse's tree and the reconstruction were both hashed")
        self.assertEqual(em.asm_checkpoint_stats()["skipped"], {"reconstruction": 1})
        self.assertFalse(em._asm_ckpt_file(path).exists(), "no document")
        self.assertEqual(em.asm_checkpoint_stats()["skipped"], {"reconstruction": 1})
        em._ASM_CKPT_STATS["skipped"] = {}
        self.assertFalse(self.doc(path), "the failure is memoized for this entry and cut")
        self.assertEqual(em.asm_checkpoint_stats()["skipped"], {"reconstruction": 1}, "counted again, nothing rebuilt")
        self.assertEqual(em._ASM_CACHE[next(iter(em._ASM_CACHE))].get("docSkip", (None, None))[1], "reconstruction")

    def test_a_transient_failure_is_not_memoized_against_the_cut(self):
        """Review find (third round): a stat, offsets or write failure is a blip, not a property of the cut; memoizing it left
        the session without a document until its next compaction. It is counted and tried again at the next settle."""
        path = self._whole("blip")
        real = em._entry_offsets_gen
        em._entry_offsets_gen = lambda fp: (None, None)              # a record landing between the parse and the offsets (the
        try:                                                        #  writer's one entry read, T396)
            self.assertFalse(self.doc(path))
        finally:
            em._entry_offsets_gen = real
        self.assertEqual(em.asm_checkpoint_stats()["skipped"], {"offsets": 1})
        self.assertIsNone(em._ASM_CACHE[next(iter(em._ASM_CACHE))].get("docSkip"), "not memoized")
        self.assertTrue(self.doc(path), "the next settle writes")

    def test_a_whole_entry_writes_its_document_once(self):
        """Review find (H): a fold appends after the cut and changes nothing before it, so the settles after the first
        write skip the build (`written`), until the entry is replaced."""
        path = self._whole("once")
        self.assertTrue(self.doc(path))
        st = em._asm_ckpt_file(path).stat()
        self.assertFalse(self.doc(path))
        self.assertEqual(em.asm_checkpoint_stats()["skipped"], {"written": 1})
        self.assertEqual(em._asm_ckpt_file(path).stat().st_mtime_ns, st.st_mtime_ns, "the document was not rewritten")
        em._asm_ckpt_file(path).unlink()
        self.assertTrue(self.doc(path), "a missing document is written again from the same entry")


class PlannerOverRestored(Harness):
    """T377 (2026-09-12): the judges' planner computed every ended segment's unit text before any consumer checked placement,
    and every consumer skips placed units or reads keys only; over a restored tree that hydrated every pre-cut body from disk,
    1.06 GB per boot on the devbox (96 percent of the lazy index's atoms, in the judges' first pass). A unit the store already
    places is yielded with no text and nothing read; the rest read their text after the placement check, as before."""

    @classmethod
    def setUpClass(cls):
        cls.km = kernel_module(); cls.jd = cls.km.jd

    def _scalars(self, units):
        return [(u[0], u[1], u[2], u[4], u[5], u[6]) for u in units]     # id, phase, time, human, followup, trigger

    def test_placed_units_are_yielded_without_text_and_nothing_is_hydrated(self):
        jd = self.jd
        records, sent = G.SINGLE_FILE["compaction_atom"]
        path = self.write("planner", records(), sent=sent)
        self.fresh(); whole = self.parse(path); self.assertTrue(self.doc(path))
        empty = {"placements": {}, "nodes": {}, "seq": 0}
        ref = jd.plan_units(whole, empty)                              # the whole parse's units: the reference, text included
        self.assertTrue(ref and any(u[3] for u in ref), "the fixture yields units with text")
        placed = {"placements": {jd._unit_key(u[0], u[1]): "n1" for u in ref}, "nodes": {"n1": {"id": "n1"}}, "seq": 1}
        self.fresh(); modes = []; tree = self.parse(path, modes); self.assertEqual(modes, ["restore"])
        em._ASM_CKPT_STATS.update(hydratedAtoms=0, hydratedBytes=0, hydratedBy={})
        got = jd.plan_units(tree, placed)
        self.assertEqual(self._scalars(got), self._scalars(ref), "the same units, keys, times and scalars as the whole parse's")
        self.assertTrue(all(u[3] is None and u[7] is None for u in got), "a placed unit carries no text and no quote: %r" % [(u[3], u[7]) for u in got][:3])
        self.assertTrue(any(u[7] for u in ref), "the reference carries quotes")
        st = em.asm_checkpoint_stats()
        nseg = sum(len(em.segments(t)) for t in tree["turns"])
        self.assertFalse(any(k.startswith(("_unit_text", "_prompt_text")) for k in st["hydratedBy"]), "no unit text read: %s" % st["hydratedBy"])
        self.assertLessEqual(st["hydratedAtoms"], nseg, "at most the trigger atom's text per segment (the shape checks, as before): %s" % st)

    def test_unplaced_units_read_their_text_as_before(self):
        jd = self.jd
        records, sent = G.SINGLE_FILE["compaction_atom"]
        path = self.write("planner2", records(), sent=sent)
        self.fresh(); whole = self.parse(path); self.assertTrue(self.doc(path))
        empty = {"placements": {}, "nodes": {}, "seq": 0}
        ref = jd.plan_units(whole, empty)
        self.fresh(); tree = self.parse(path)                          # restored: what a full hydration of the tree costs
        em._ASM_CKPT_STATS.update(hydratedAtoms=0, hydratedBytes=0, hydratedBy={})
        em.hydrate(tree, SID); full = em.asm_checkpoint_stats()["hydratedBytes"]
        self.fresh(); tree = self.parse(path)
        em._ASM_CKPT_STATS.update(hydratedAtoms=0, hydratedBytes=0, hydratedBy={})
        got = jd.plan_units(tree, empty)
        self.assertEqual(got, ref, "unplaced: byte-identical to the whole parse's units, text included")
        st = em.asm_checkpoint_stats()
        self.assertEqual(st["hydratedBytes"], full, "unplaced units read what they always did: every pre-cut body of the units")
        self.assertTrue(any(k.startswith("_unit_text") for k in st["hydratedBy"]), "%s" % st["hydratedBy"])
class ConvergeAssembly(Harness):
    """T376 (2026-09-12): an idle session never settles, so its leaf never had an assembly document and the parse read it whole
    at every boot (31 of 60 leaves on the devbox, about 2.5 GB, the boot's remaining cost). The converge pass writes the
    document for a quiescent leaf from the whole assembly entry the boot's own parse built: no read of records (a stat per
    file and the cut's guard), charged to the cycle's byte budget, once; the next process restores it and reads the tail."""

    @classmethod
    def setUpClass(cls):
        cls.km = kernel_module()

    def setUp(self):
        super().setUp()
        em._ASM_CKPT_STATS["converge"] = {"writes": 0, "bytes": 0, "deferred": 0, "candidates": 0, "skipped": {}}
        with em._CKPT_LOCK:
            for k in em._CKPT_STATS["converge"]:                   # the fold half's counters too: the tests assert absolutes
                em._CKPT_STATS["converge"][k] = 0
        self.km._ASM_CONVERGE_DONE.clear(); self.km._ASM_CONVERGE_BLIP.clear(); self.km._ASM_CONVERGE_NOENTRY.clear()
        for name, val in (("CKPT_CONVERGE_MS", 150.0), ("CKPT_CONVERGE_BYTES", em._CKPT_CYCLE_CAP_DEFAULT), ("ASM_CONVERGE", True)):
            saved = getattr(self.km, name); setattr(self.km, name, val); self.addCleanup(setattr, self.km, name, saved)

    def idle_leaf(self, name="idle", scenario="compaction_atom", age=600):
        """A leaf idle past the reader's quiescence window, with no assembly document, parsed once by this process (the boot's
        read: a whole entry), registered as the only session."""
        import time
        records, sent = G.SINGLE_FILE[scenario]
        path = self.write(name, records(), sent=sent)
        old = time.time() - age; os.utime(path, (old, old))
        self.fresh(); self.parse(path)
        rows = [{"sid": SID, "path": path}]
        saved = self.km._sessions; self.km._sessions = lambda now, **kw: rows
        self.addCleanup(setattr, self.km, "_sessions", saved)
        self.assertFalse(em._asm_ckpt_file(path).exists())
        return path

    def cycle(self, now):
        self.km._begin_checkpoint_cycle()
        return self.km._converge_checkpoints(now)

    def test_the_pass_writes_an_idle_leafs_document_from_the_boots_parse_and_the_next_boot_reads_a_tail(self):
        path = self.idle_leaf()
        size = os.path.getsize(path); read0 = em.read_bytes_report().get(path, 0)
        self.cycle(NOW + 600)
        self.assertTrue(em._asm_ckpt_file(path).exists(), "written from the entry in hand")
        self.assertLess(em.read_bytes_report().get(path, 0) - read0, 512, "no read of records: the cut's guard alone")
        cv = em.asm_checkpoint_stats()["converge"]
        self.assertEqual((cv["writes"], cv["deferred"], cv["candidates"]), (1, 0, 1), "%s" % cv); self.assertGreater(cv["bytes"], 0)
        st = em._asm_ckpt_file(path).stat().st_mtime_ns
        self.cycle(NOW + 601); self.cycle(NOW + 602)
        cv = em.asm_checkpoint_stats()["converge"]
        self.assertEqual((cv["writes"], cv["candidates"]), (1, 1), "once: the document stands, the leaf is done: %s" % cv)
        self.assertEqual(em._asm_ckpt_file(path).stat().st_mtime_ns, st)
        whole = self.cold(path)
        tree, modes, n_lazy = self.restored(path)
        self.assertEqual(modes, ["restore"]); self.assertGreater(n_lazy, 0)
        self.assertLess(self.read_before, size, "the next boot reads the tail, not the whole leaf: %d of %d bytes" % (self.read_before, size))
        self.assertEqual(tree, whole)

    def test_the_dirty_leaf_boot_shape_writes_the_fold_document_and_the_assembly_document_in_one_pass(self):
        """Round one, medium: the ordinary boot shape is a dirty idle leaf (the judges' pass read it whole, its fold document lacks
        the pairing) with no assembly document. The fold half of the pass healed and primed it and its held quiescence drop
        POPPED the record entry; the assembly step then found the assembly entry but no record entry (_entry_offsets_gen (None, None)), a
        skipped write, retried once, abandoned. The assembly write now runs while the record entry is resident, inside the same
        hold, and the held drop is paid after it: one pop, both documents from the one read, and the next boot restores both."""
        path = self.idle_leaf("both")
        km = self.km; jd = km.jd
        size = os.path.getsize(path)
        jd._bg_scan(path)                                             # the boot's whole read by a fold: dirty, whole-resident
        self.assertTrue(em.entry_whole_resident(path))
        self.assertIn(path, em.checkpoint_converge_candidates(), "a fold candidate too")
        read0 = em.read_bytes_report().get(path, 0)
        self.cycle(NOW + 600)
        cv = em.checkpoint_stats()["converge"]; av = em.asm_checkpoint_stats()["converge"]
        self.assertEqual((cv["viaDrop"], cv["dropWrites"]), (1, 1), "the fold document, written at the held drop: %s" % cv)
        self.assertEqual((av["writes"], av["skipped"]), (1, {}), "the assembly document, written from the same read: %s" % av)
        self.assertTrue(em._asm_ckpt_file(path).exists())
        self.assertLess(em.read_bytes_report().get(path, 0) - read0, 1024, "no read of records for either")
        with em._JSONL_CACHE_LOCK:
            self.assertIsNone(em._JSONL_CACHE.get(path), "one pop, after both writes")
        self.fresh(); em.set_checkpoint_dir(lambda: self.ck)
        for c in list(em._FOLD_REG.values()): c.clear()
        before = em.checkpoint_stats()["restoredFolds"].get("bgJudge", 0)
        modes = []; self.parse(path, modes); self.assertEqual(modes, ["restore"], "the assembly document restores")
        jd._bg_scan(path)
        self.assertEqual(em.checkpoint_stats()["restoredFolds"].get("bgJudge", 0), before + 1, "the fold document restores")
        self.assertLess(em.read_bytes_report().get(path, 0), size, "the next boot reads the tail")

    def test_a_leaf_older_than_the_discover_window_is_written_from_the_boots_parse(self):
        """T382: the step walked _sessions(now), the discover window's rows (48 hours), so an idle leaf older than that was never a
        candidate although the boot had parsed it (19 of the 25 boundary leaves without a document on the devbox, 20 to 714
        hours old). The candidates come from the assembly cache's whole unrestored entries, the parses the boot actually did,
        each with its sid and flag; every other guard stands."""
        path = self.idle_leaf("aged")
        self.km._sessions = lambda now, **kw: []                       # no row in the window: the session is too old for discover
        read0 = em.read_bytes_report().get(path, 0)
        self.cycle(NOW + 600)
        self.assertTrue(em._asm_ckpt_file(path).exists(), "written from the parse in the cache, whatever the session's age")
        av = em.asm_checkpoint_stats()["converge"]
        self.assertEqual((av["writes"], av["candidates"], av["deferred"]), (1, 1, 0), "%s" % av)
        self.assertLess(em.read_bytes_report().get(path, 0) - read0, 512, "no read of records")
        self.cycle(NOW + 601); self.cycle(NOW + 602)
        self.assertEqual(em.asm_checkpoint_stats()["converge"]["writes"], 1, "once")
        tree, modes, n_lazy = self.restored(path)
        self.assertEqual(modes, ["restore"])

    def _parse_as(self, path, human):
        return em.parse_session(path, rompuuid=SID, name="impl", dir="/TESTDIR", candidate_files=[path], states=self.states,
                                postal_log=self.sent, now=NOW, sdk_human=human)

    def test_the_document_is_written_under_the_display_parses_flag_whichever_entry_the_cache_yields_first(self):
        """T382 review, medium: with two whole entries for one leaf (the judges' flag and the display's differ until the owner
        provider is wired), the step wrote under whichever entry the LRU order yielded first; under the wrong flag the display's
        next boot took a session fallback, deleted the document and read the leaf whole. The entry whose flag is the display
        parse's is chosen, in either order."""
        for order in ((False, True), (True, False)):
            with self.subTest(order=order):
                path = self.idle_leaf("flag%d%d" % order)
                self.fresh(); em.set_checkpoint_dir(lambda: self.ck)
                for c in list(em._FOLD_REG.values()): c.clear()
                self.km._ASM_CONVERGE_DONE.clear(); self.km._ASM_CONVERGE_NOENTRY.clear()
                for human in order:
                    self._parse_as(path, human)                        # two whole entries, the display's flag (False) first or second
                self.cycle(NOW + 600)
                self.assertTrue(em._asm_ckpt_file(path).exists())
                self.assertFalse(_doc(path)["sdkHuman"], "written under the display parse's flag")
                tree, modes, n_lazy = self.restored(path)
                self.assertEqual(modes, ["restore"], "the display's next boot restores it: %s" % em.asm_checkpoint_stats()["fallbacks"])

    def test_a_leaf_parsed_only_under_the_other_flag_is_skipped_and_counted(self):
        path = self.idle_leaf("otherflag")
        self.fresh(); em.set_checkpoint_dir(lambda: self.ck)
        for c in list(em._FOLD_REG.values()): c.clear()
        self.km._ASM_CONVERGE_DONE.clear(); self.km._ASM_CONVERGE_NOENTRY.clear()
        self._parse_as(path, True)                                     # the judges' flag alone: a document the display would unlink
        for k in range(2):
            self.cycle(NOW + 600 + k)
        self.assertFalse(em._asm_ckpt_file(path).exists(), "no document the reader would delete")
        av = em.asm_checkpoint_stats()["converge"]
        self.assertEqual((av["writes"], av["skipped"].get("flagMismatch")), (0, 1), "skipped once, counted: %s" % av)

    def test_a_write_over_the_cycles_budget_is_deferred_to_the_next(self):
        path = self.idle_leaf("budget")
        self.km.CKPT_CONVERGE_BYTES = 1
        self.cycle(NOW + 600)
        self.assertFalse(em._asm_ckpt_file(path).exists())
        self.assertEqual(em.asm_checkpoint_stats()["converge"]["deferred"], 1)
        self.km.CKPT_CONVERGE_BYTES = em._CKPT_CYCLE_CAP_DEFAULT
        self.cycle(NOW + 601)
        self.assertTrue(em._asm_ckpt_file(path).exists())
        self.assertEqual(em.asm_checkpoint_stats()["converge"]["writes"], 1)

    def test_a_zero_byte_budget_turns_the_step_off_rather_than_deferring_forever(self):
        """Round one, low 2: with ROMP_CKPT_CONVERGE_MB=0 every attempt was deferred and candidates and deferred grew each cycle."""
        path = self.idle_leaf("zero")
        self.km.CKPT_CONVERGE_BYTES = 0
        for k in range(3):
            self.cycle(NOW + 600 + k)
        cv = em.asm_checkpoint_stats()["converge"]
        self.assertEqual((cv["candidates"], cv["deferred"], cv["writes"]), (0, 0, 0), "off, as the drop write is: %s" % cv)
        self.assertFalse(em._asm_ckpt_file(path).exists())

    def test_a_blip_is_tried_twice_then_done_and_the_writer_names_its_caller_once_per_leaf(self):
        """Round two, low 3: the writer returns its reason (a blip, here the record entry gone before the offsets are read,
        versus a property of the cut), the pass tries a blip twice for one file state and then leaves it, and the writer's blip
        line names its caller and is said once per leaf and reason."""
        path = self.idle_leaf("blip"); km = self.km
        with em._JSONL_CACHE_LOCK:
            em._JSONL_CACHE.pop(path, None)                        # the record entry gone: the writer has no offsets (a blip)
        import io
        err = io.StringIO(); saved = sys.stderr; sys.stderr = err
        try:
            reasons = []
            self.assertFalse(em.asm_checkpoint_write(path, SID, False, reason_out=reasons, who="converge pass"))
            self.assertFalse(em.asm_checkpoint_write(path, SID, False, reason_out=reasons, who="converge pass"))
        finally:
            sys.stderr = saved
        self.assertEqual(reasons, ["offsets", "offsets"], "the writer's own reason, per attempt")
        lines = [l for l in err.getvalue().splitlines() if "not written by the converge pass" in l]
        self.assertEqual(len(lines), 1, "the blip line names its caller and is said once per leaf: %r" % err.getvalue())
        # the pass: the blip's two tries, then done for this file state (the record entry must be resident for a write)
        st = km._stat_key_ns(path)
        self.assertFalse(km._converge_assembly_leaf(path, SID, time.monotonic()))
        self.assertEqual(km._ASM_CONVERGE_NOENTRY.get(path), st, "no record entry: nothing to write from, counted once, no try spent")
        with em._JSONL_CACHE_LOCK:                                 # the record entry back, but the offsets torn away at the write
            pass
        self.fresh(); em.set_checkpoint_dir(lambda: self.ck); self.parse(path)   # a whole record entry again
        real = em._entry_offsets_gen; em._entry_offsets_gen = lambda p: (None, None)   # the writer's one entry read (T396)
        self.addCleanup(setattr, em, "_entry_offsets_gen", real)
        self.assertFalse(km._converge_assembly_leaf(path, SID, time.monotonic()))
        self.assertEqual(km._ASM_CONVERGE_BLIP.get(path), st, "a blip: the first try spent, not done")
        self.assertFalse(km._converge_assembly_leaf(path, SID, time.monotonic()))
        self.assertEqual(km._ASM_CONVERGE_DONE.get(path), st, "the second try spent: done for this file state")
        self.assertEqual(em.asm_checkpoint_stats()["converge"]["skipped"].get("offsets"), 2)

    def test_the_done_tables_release_their_oldest_past_the_bound(self):
        """Round two, low 3: past the bound the oldest entry is released, never the table cleared."""
        table = {"k%d" % i: i for i in range(4100)}
        self.km._release_oldest(table)
        self.assertEqual(len(table), 4096); self.assertNotIn("k0", table); self.assertIn("k4099", table); self.assertNotIn("k3", table)

    def test_a_leaf_without_a_boundary_is_looked_at_once(self):
        path = self.idle_leaf("plain", scenario=next(n for n in G.SINGLE_FILE if n not in COMPACTING))
        for k in range(3):
            self.cycle(NOW + 600 + k)
        cv = em.asm_checkpoint_stats()["converge"]
        self.assertFalse(em._asm_ckpt_file(path).exists())
        self.assertEqual((cv["candidates"], cv["skipped"].get("noBoundary"), cv["writes"]), (1, 1, 0), "no cut, no document, said once: %s" % cv)

    def test_off_writes_nothing_and_a_live_leaf_is_left_to_the_settle(self):
        path = self.idle_leaf("off")
        self.km.ASM_CONVERGE = False
        self.cycle(NOW + 600)
        self.assertFalse(em._asm_ckpt_file(path).exists()); self.assertEqual(em.asm_checkpoint_stats()["converge"]["candidates"], 0)
        self.km.ASM_CONVERGE = True
        live = self.idle_leaf("live", age=0)                       # fresh: the settle's writer covers it
        self.cycle(NOW + 601)
        self.assertFalse(em._asm_ckpt_file(live).exists()); self.assertEqual(em.asm_checkpoint_stats()["converge"]["candidates"], 0)
        self.assertIn("converge", self.km._PERF_STATS.snapshot()["asmCheckpoint"], "the counters ride /perf")


class HydrationAttribution(Harness):
    def test_a_shared_text_reader_is_attributed_with_its_caller(self):
        """T377: the boot's 1.06 GB of hydration read as `_unit_text`, the judges' shared text reader, which every walker calls;
        the bytes are attributed to the reader AND its caller, so the counter names the walker."""
        records, sent = G.SINGLE_FILE["compaction_atom"]
        path = self.write("attr", records(), sent=sent)
        self.fresh(); self.parse(path); self.assertTrue(self.doc(path))
        tree, _, n_lazy = self.fresh(), None, None
        modes = []; tree = self.parse(path, modes); self.assertEqual(modes, ["restore"])
        atoms = [a for t in tree["turns"] for a in t["atoms"]]
        em._ASM_CKPT_STATS.update(hydratedAtoms=0, hydratedBytes=0, hydratedBy={})
        def _unit_text(atoms):                                  # a stand-in for the judges' reader, registered like it
            return em.hydrate(atoms)
        em.register_hydrate_text_reader(_unit_text); self.addCleanup(em.unregister_hydrate_text_reader, _unit_text)
        def some_walker():
            return _unit_text(atoms)
        some_walker()
        by = em.asm_checkpoint_stats()["hydratedBy"]
        self.assertEqual(list(by), ["_unit_text<-some_walker"], "%s" % by)
        self.assertEqual(em.hydrate(atoms), 0, "hydrated already: nothing counted twice")
        self.fresh(); tree = self.parse(path); atoms = [a for t in tree["turns"] for a in t["atoms"]]
        em._ASM_CKPT_STATS.update(hydratedAtoms=0, hydratedBytes=0, hydratedBy={})
        def _atom_text(atoms):                                  # a reader reached through another shared reader (round one, low 3)
            return em.hydrate(atoms)
        def _prompt_text(atoms):
            return _atom_text(atoms)
        em.register_hydrate_text_reader(_atom_text, _prompt_text)
        self.addCleanup(em.unregister_hydrate_text_reader, _atom_text, _prompt_text)
        def other_walker():
            return _prompt_text(atoms)
        other_walker()
        self.assertEqual(list(em.asm_checkpoint_stats()["hydratedBy"]), ["_atom_text<-other_walker"], "the first caller outside the shared readers")

    def test_the_shared_readers_are_matched_by_code_object_not_by_name(self):
        """Round three, low 2: the shared text readers were matched by NAME, so a local function named like one was consumed as
        the reader (the whole-read passthrough already matches by code object for the same reason). The real readers are
        registered where they are defined; a same-named local function is a walker, and the stand-ins the attribution tests use
        register themselves."""
        records, sent = G.SINGLE_FILE["compaction_atom"]
        path = self.write("byobj", records(), sent=sent)
        self.fresh(); self.parse(path); self.assertTrue(self.doc(path))
        self.fresh(); modes = []; tree = self.parse(path, modes); self.assertEqual(modes, ["restore"])
        atoms = [a for t in tree["turns"] for a in t["atoms"]]
        em._ASM_CKPT_STATS.update(hydratedAtoms=0, hydratedBytes=0, hydratedBy={})
        def _atom_user_texts(a):                                # a walker that merely shares a shared reader's name
            return em.hydrate([a])
        def unrelated_walker():
            return [_atom_user_texts(a) for a in atoms]
        unrelated_walker()
        by = em.asm_checkpoint_stats()["hydratedBy"]
        self.assertEqual(list(by), ["_atom_user_texts"], "a same-named local function is the caller, not a shared reader: %s" % by)
        km = kernel_module()
        self.assertTrue(em.hydrate_text_reader_registered(km._atom_user_texts), "the kernel's reader is registered")
        self.assertTrue(all(em.hydrate_text_reader_registered(f) for f in (km.jd._unit_text, km.jd._prompt_text, km.jd._atom_text)),
                        "the judges' three readers are registered")

    def test_a_walk_from_inside_a_generator_expression_names_the_enclosing_function(self):
        """The 1e60c712 head went red on Python 3.10 and 3.11: a list comprehension there runs in its own frame (inlined from
        3.12 on, PEP 709), and the attribution named `<listcomp>`. A generator expression keeps its own frame on every version,
        so the first pin is red everywhere at that head; the comprehension pin is red on 3.10 and 3.11 and green above."""
        records, sent = G.SINGLE_FILE["compaction_atom"]
        path = self.write("scopes", records(), sent=sent)
        self.fresh(); self.parse(path); self.assertTrue(self.doc(path))
        def restored_atoms():
            self.fresh(); modes = []; tree = self.parse(path, modes); self.assertEqual(modes, ["restore"])
            em._ASM_CKPT_STATS.update(hydratedAtoms=0, hydratedBytes=0, hydratedBy={})
            return [a for t in tree["turns"] for a in t["atoms"]]
        atoms = restored_atoms()
        def genexpr_walker():
            return sum(em.hydrate([a]) for a in atoms)
        genexpr_walker()
        self.assertEqual(list(em.asm_checkpoint_stats()["hydratedBy"]), ["genexpr_walker"], "%s" % em.asm_checkpoint_stats()["hydratedBy"])

    def test_a_shared_reader_reached_from_a_list_comprehension_names_the_walker_around_it(self):
        """The comprehension case alone: red on Python 3.10 and 3.11 at 1e60c712 (`<listcomp>` has its own frame there), green
        from 3.12 on, where PEP 709 inlines it."""
        records, sent = G.SINGLE_FILE["compaction_atom"]
        path = self.write("listcomp", records(), sent=sent)
        self.fresh(); self.parse(path); self.assertTrue(self.doc(path))
        self.fresh(); modes = []; tree = self.parse(path, modes); self.assertEqual(modes, ["restore"])
        em._ASM_CKPT_STATS.update(hydratedAtoms=0, hydratedBytes=0, hydratedBy={})
        atoms = [a for t in tree["turns"] for a in t["atoms"]]
        def _atom_user_texts(a):                                # a stand-in shared reader reached from a comprehension inside a walker
            return em.hydrate([a])
        em.register_hydrate_text_reader(_atom_user_texts); self.addCleanup(em.unregister_hydrate_text_reader, _atom_user_texts)
        def listcomp_walker():
            return [_atom_user_texts(a) for a in atoms]
        listcomp_walker()
        self.assertEqual(list(em.asm_checkpoint_stats()["hydratedBy"]), ["_atom_user_texts<-listcomp_walker"], "%s" % em.asm_checkpoint_stats()["hydratedBy"])


class ReadersOverRestoredHydrateOnlyWhatTheyNeed(Harness):
    """T384 (2026-09-12): after the planner stopped hydrating every pre-cut body, the next walkers paid for the same bodies (the
    first T377 boot: _seg_prompt 723 MB, _seg_of_tool_uses 155 MB, _atom_user_texts 78 MB of 966). Each reads what it needs:
    the segment-prompt reader hydrates the one trigger atom, the tool-uses reader takes the ids from the lazy markers' scalars
    with no hydration, and the echo set reads no user text when no echo can land (an infinite floor). Per-reader bytes over a
    restored tree, on both builds."""

    @classmethod
    def setUpClass(cls):
        cls.km = kernel_module()

    def _restored(self, name):
        records, sent = G.SINGLE_FILE["compaction_atom"]
        path = self.write(name, records(), sent=sent)
        self.fresh(); self.parse(path); self.assertTrue(self.doc(path))
        self.fresh(); modes = []; tree = self.parse(path, modes); self.assertEqual(modes, ["restore"])
        em._ASM_CKPT_STATS.update(hydratedAtoms=0, hydratedBytes=0, hydratedBy={})
        return path, tree

    def test_the_segment_prompt_reader_hydrates_the_trigger_atom_alone(self):
        path, tree = self._restored("segprompt")
        segs = [seg for t in tree["turns"] for seg in em.segments(t)]
        pre = [seg for seg in segs if any(a.get("lazy") is not None for a in seg["atoms"])]
        self.assertTrue(pre, "pre-cut segments in play")
        prompts = [self.km._seg_prompt(seg) for seg in segs]
        st = em.asm_checkpoint_stats()
        self.assertLessEqual(st["hydratedAtoms"], len(pre), "one atom per pre-cut segment, the trigger: %s" % st)
        self.fresh(); whole = self.parse(path)
        self.assertEqual(prompts, [self.km._seg_prompt(seg) for t in whole["turns"] for seg in em.segments(t)], "the same prompts as the whole parse")

    def test_the_tool_uses_reader_takes_the_ids_from_the_markers_scalars(self):
        path, tree = self._restored("tooluses")
        whole_ids = {b.get("id") for t in self.cold(path)["turns"] for a in t["atoms"] if a.get("type") == "assistant"
                     for b in ((a.get("message") or {}).get("content") or []) if isinstance(b, dict) and b.get("type") == "tool_use"}
        self.assertTrue(whole_ids, "the fixture has tool calls")
        self.fresh(); modes = []; tree = self.parse(path, modes); self.assertEqual(modes, ["restore"])
        em._ASM_CKPT_STATS.update(hydratedAtoms=0, hydratedBytes=0, hydratedBy={})
        found = self.km._seg_of_tool_uses(tree, {"placements": {}, "nodes": {}, "seq": 0}, list(whole_ids))
        self.assertEqual(set(found), whole_ids, "every id resolved to its segment")
        self.assertEqual(em.asm_checkpoint_stats()["hydratedAtoms"], 0, "from the scalars, no body read: %s" % em.asm_checkpoint_stats()["hydratedBy"])

    def test_the_comments_frames_landing_walk_reads_no_user_text_below_the_oldest_echos_send(self):
        """The comments frame read every user atom of a thread's whole parse to test whether a live echo had landed (78 MB on
        the first T377 boot); a text lands at or after its send, so the atoms below the oldest echo's send are never read."""
        path, tree = self._restored("echoland")
        pre_users = [a for t in tree["turns"] for a in t["atoms"] if a.get("type") == "user" and a.get("lazy") is not None]
        self.assertTrue(pre_users, "pre-cut user atoms in play")
        newest = max(float(a.get("t") or 0) for t in tree["turns"] for a in t["atoms"] if a.get("t"))
        live = [{"_echo_text": "a typed-ahead line", "t": newest + 5}]   # an echo sent after every recorded atom
        rows = self.km._echo_landing_atoms(tree["turns"], live)
        self.assertEqual(rows, [], "no atom at or after the send: nothing to compare, nothing read")
        self.assertEqual(em.asm_checkpoint_stats()["hydratedAtoms"], 0, "%s" % em.asm_checkpoint_stats()["hydratedBy"])
        self.assertEqual(self.km._echo_landing_atoms(tree["turns"], []), [], "no live echo: no walk")
        live = [{"_echo_text": "an early line", "t": 0}]                 # an echo older than everything: every user atom is a candidate
        rows = self.km._echo_landing_atoms(tree["turns"], live)
        self.assertEqual(len(rows), sum(1 for t in tree["turns"] for a in t["atoms"] if a.get("type") == "user"))
        self.assertGreaterEqual(em.asm_checkpoint_stats()["hydratedAtoms"], len(pre_users), "below the floor they are read, as before")

    def test_a_marker_without_tool_use_scalars_is_an_answer_with_no_tool_call_and_hydrates_nothing(self):
        """Round two, medium: the writer records `tu` only when an atom has tool calls, so a marker without it is the common
        prose-only answer (the version gate and the source pin make any other marker shape unreachable). The reader takes it as
        an empty set: no body read (a fallback read here hydrated every prose-only answer the walk met). The tree holds a
        prose-only marker BESIDE a marker carrying calls before the cut, the production shape, so one tree pins both (round
        three, low 1: the earlier scenario had no tool call at all and compared two empty sets)."""
        records, sent = G.SINGLE_FILE["eclipsed_branch_kept"]          # tool calls and prose-only answers, then a compaction after
        path = self.write("notu-both", compacting_variant(records(), "notu"), sent=sent)   #  them: the whole scenario is pre-cut
        self.fresh(); self.parse(path); self.assertTrue(self.doc(path))
        whole_ids = {b.get("id") for t in self.cold(path)["turns"] for a in t["atoms"] if a.get("type") == "assistant"
                     for b in ((a.get("message") or {}).get("content") or []) if isinstance(b, dict) and b.get("type") == "tool_use"}
        self.assertTrue(whole_ids, "the fixture has tool calls")
        self.fresh(); modes = []; tree = self.parse(path, modes); self.assertEqual(modes, ["restore"])
        pre = [a for t in tree["turns"] for a in t["atoms"] if a.get("type") == "assistant" and a.get("lazy") is not None]
        with_calls = [a for a in pre if "tu" in a["lazy"]]; prose = [a for a in pre if "tu" not in a["lazy"]]
        self.assertTrue(with_calls and prose, "both shapes before the cut: %d with calls, %d prose-only" % (len(with_calls), len(prose)))
        em._ASM_CKPT_STATS.update(hydratedAtoms=0, hydratedBytes=0, hydratedBy={})
        found = self.km._seg_of_tool_uses(tree, {"placements": {}, "nodes": {}, "seq": 0}, list(whole_ids) + ["toolu_not_anywhere"])
        self.assertEqual(set(found), whole_ids, "the calls resolved from the scalars; the missing id resolves to nothing")
        self.assertEqual(em.asm_checkpoint_stats()["hydratedAtoms"], 0, "no prose-only answer read: %s" % em.asm_checkpoint_stats()["hydratedBy"])

    def test_the_comments_frame_itself_reads_no_user_text_for_an_echo_above_the_cut(self):
        """Round two, low 1: the pin on the call site. The frame is run over the thread's restored parse with a live echo sent
        after every recorded atom; hydratedBy carries no user-texts row (the frame's inline walk hydrated every pre-cut user
        atom before)."""
        km = self.km
        path, tree = self._restored("frame")
        newest = max(float(a.get("t") or 0) for t in tree["turns"] for a in t["atoms"] if a.get("t"))
        echo = {"_echo_text": "a typed-ahead line", "t": newest + 5, "uuid": "echo-1"}
        class FakeBackend:
            def session_state(self, tsid): return "working"
            def live_atoms(self, tsid): return [echo]
            def pending_queued(self, tsid): return []
            def launch_error(self, tsid): return None
        comments = self.td / "comments.json"; comments.write_text("{}")
        saved = {n: getattr(km, n) for n in ("_comments_path", "_load_comments_cached", "_sdk", "_thread_messages", "_thread_events",
                                              "_thread_reg", "_thread_turn_read", "_thread_owes_first_reply", "_agent_landed_after")}
        try:
            km._comments_path = lambda sid: comments
            km._load_comments_cached = lambda sid: {"threads": [{"sid": "thread-1", "status": "open", "createdT": 1}]}
            km._sdk = lambda: FakeBackend()
            km._thread_messages = lambda *a, **k: []
            km._thread_events = lambda *a, **k: []
            km._thread_reg = lambda tsid: {}
            km._thread_turn_read = lambda *a, **k: (False, False, tree["turns"])
            km._thread_owes_first_reply = lambda *a, **k: False
            km._agent_landed_after = lambda *a, **k: False
            em._ASM_CKPT_STATS.update(hydratedAtoms=0, hydratedBytes=0, hydratedBy={})
            frame = km._comments_frame(SID)
        finally:
            for n, v in saved.items():
                setattr(km, n, v)
        self.assertIsNotNone(frame, "the frame was built")
        by = em.asm_checkpoint_stats()["hydratedBy"]
        self.assertFalse(any(k.startswith("_atom_user_texts") for k in by), "the frame read no user text: %s" % by)

    def test_the_user_texts_reader_is_attributed_with_its_caller(self):
        """Round two, low 2: one row, _atom_user_texts, stood for both the frame's walk and the echo set's loop; the rows name
        the caller (T377's mechanism)."""
        km = self.km
        path, tree = self._restored("rows")
        em._ASM_CKPT_STATS.update(hydratedAtoms=0, hydratedBytes=0, hydratedBy={})
        km._echo_landing_atoms(tree["turns"], [{"_echo_text": "an early line", "t": 0}])
        km._merge_sets_memo.clear(); km._merge_tx_sets(tree, SID + "-rows", 0.0)
        by = em.asm_checkpoint_stats()["hydratedBy"]
        self.assertIn("_atom_user_texts<-_echo_landing_atoms", by, "%s" % by)
        self.assertIn("_atom_user_texts<-_merge_tx_sets", by, "%s" % by)
        self.assertNotIn("_atom_user_texts", by, "no bare row: %s" % by)

    def test_the_floor_and_the_held_filter_share_one_holdable_echo_predicate(self):
        """Round three, low 3: the four clauses (a text key, not a command, not dropped, not landed) were spelled out twice; one
        predicate serves both, the held filter adding its two dependent clauses, so a clause added to one side cannot recreate
        round two's low 4."""
        import inspect
        km = self.km
        self.assertTrue(km._echo_holdable({"_echo_text": "a line"}))
        for bad in ({"_echo_text": "a line", "command": True}, {"_echo_text": "a line", "dropped": True},
                    {"_echo_text": "a line", "_landed": True}, {"_echo_text": ""}, {}):
            self.assertFalse(km._echo_holdable(bad), "%r" % bad)
        self.assertIn("_echo_holdable(", inspect.getsource(km._echo_floor))
        self.assertIn("_echo_floor(", inspect.getsource(km._echo_landing_atoms))
        frame = inspect.getsource(km._comments_frame)
        self.assertIn("_echo_holdable(", frame)
        self.assertNotIn('not a.get("dropped") and not a.get("_landed")', frame, "the clauses live in the predicate alone")

    def _merge_with_live(self, name, live):
        """_merge_live_atoms over a restored tree with a stubbed owning backend holding `live`: the merged rows and the
        by-text mapping prune_live received (the two consumers of the transcript-side text sets beside the landing set)."""
        km = self.km
        path, tree = self._restored(name)
        got = {}
        class _Backend:
            def live_atoms(self, sid):
                return [dict(a) for a in live]
            def prune_live(self, sid, tx_uuids, tx_user_texts=(), human_floor=0):
                got["texts"] = tx_user_texts
        saved = km.Sessions.__dict__["backend_for"]
        km.Sessions.backend_for = staticmethod(lambda sid: _Backend())
        self.addCleanup(lambda: setattr(km.Sessions, "backend_for", saved))
        km._merge_sets_memo.clear()
        merged = km._merge_live_atoms(tree, SID + "-" + name)
        rows = [a.get("_echo_text") for t in merged["turns"] for a in (t.get("atoms") or []) if a.get("_echo_text")]
        return path, tree, rows, got.get("texts")

    def _pre_cut_user_text(self, path, tree):
        """A user text of a pre-cut turn (one the restored tree holds as a marker), read from the cold parse."""
        pre_uuids = {a.get("uuid") for t in tree["turns"] for a in t["atoms"] if a.get("lazy") is not None}
        for t in self.cold(path)["turns"]:
            for a in t["atoms"]:
                if a.get("uuid") in pre_uuids and a.get("type") == "user":
                    for txt in self.km._atom_user_texts(a):
                        if txt:
                            return txt
        self.fail("the fixture has a pre-cut user text")

    def test_a_dropped_echo_whose_text_landed_before_the_cut_is_hidden_and_pruned(self):
        """Follow-up round one, M3: the landing set's floor was narrowed to the holdable echoes, but the text sets it floors are
        also prune_live's by-text retirement input and the chat's echo dedupe input, which must cover EVERY live echo with a
        text. A dropped echo whose text landed in a pre-cut turn: at the floor over every echo the chat hides it and prune
        would retire it; under the holdable floor (None with no holdable echo; above the cut with one in the tail) it is
        painted as a permanent never-delivered row beside the message that did land, and prune never retires it, the by-text
        prune being an already-dropped echo's only automatic exit (_mark_dropped_echoes skips it at boot)."""
        km = self.km
        for tag, tail in (("alone", []), ("withtail", [{"_echo_text": "a fresh pending line", "t": 4102444800.0, "uuid": "echo-tail"}])):
            with self.subTest(tag):
                path, tree = self._restored("m3-" + tag)
                dropped_text = self._pre_cut_user_text(path, tree)
                dropped = {"_echo_text": dropped_text, "t": 0, "dropped": True, "uuid": "echo-dropped-" + tag}
                path, tree, rows, texts = self._merge_with_live("m3-" + tag, [dropped] + tail)
                self.assertNotIn(dropped_text, rows, "the dropped echo whose text landed is hidden: rows %r" % rows)
                self.assertIsNotNone(texts, "prune_live ran")
                self.assertTrue(km._echo_landed_in(dropped_text, texts), "prune's by-text input covers the landed text")
                if tail:
                    self.assertIn("a fresh pending line", rows, "the pending echo still paints")

    def test_the_echo_landing_set_reads_no_text_below_the_oldest_echo(self):
        """The saving that stands: the landing set reads pre-cut user texts from the oldest live echo's send up, dropped or
        not; with every echo newer than the cut, no pre-cut body is hydrated."""
        km = self.km
        path, tree = self._restored("setfloor")
        newest = max(float(a.get("t") or 0) for t in tree["turns"] for a in t["atoms"] if a.get("t"))
        live = [{"_echo_text": "a new dropped line", "t": newest + 1, "dropped": True}, {"_echo_text": "a new line", "t": newest + 5}]
        km._merge_sets_memo.clear()
        km._merge_tx_sets(tree, SID + "-setfloor", min(float(e["t"]) for e in live))
        self.assertEqual(em.asm_checkpoint_stats()["hydratedAtoms"], 0, "%s" % em.asm_checkpoint_stats()["hydratedBy"])

    def test_a_dropped_echo_below_the_cut_does_not_sink_the_landing_floor(self):
        """Round two, low 4: the floor was the min over every live echo with a text, but the frame holds only echoes that are not
        commands, not dropped and not landed, and a dropped one is never popped by the backend's prune; one dropped send older
        than the compaction sank the floor and every user atom above it was read on each frame."""
        path, tree = self._restored("dropped")
        newest = max(float(a.get("t") or 0) for t in tree["turns"] for a in t["atoms"] if a.get("t"))
        live = [{"_echo_text": "an old dropped line", "t": 0, "dropped": True}, {"_echo_text": "a new line", "t": newest + 5}]
        rows = self.km._echo_landing_atoms(tree["turns"], live)
        self.assertEqual(rows, [], "the dropped echo does not set the floor: %r" % rows)
        self.assertEqual(em.asm_checkpoint_stats()["hydratedAtoms"], 0, "%s" % em.asm_checkpoint_stats()["hydratedBy"])

    def test_a_whole_read_through_the_parse_family_names_the_walker(self):
        """Review, low 1: every parse goes through parsed_session, so its whole read was one row for every walker; the counter
        walks past the parse family to the first caller beyond it."""
        jd = self.km.jd
        records, sent = G.SINGLE_FILE["compaction_atom"]
        path = self.write("walker", records(), sent=sent)
        self.fresh(); jd._PARSE_CACHE.clear(); jd._CHAIN_MEMO.clear()
        with em._JSONL_CACHE_LOCK:
            em._RECORD_CACHE_STATS["wholeReads"] = {}
        def some_boot_walker():
            return jd.parsed_session(SID, [path], NOW)
        some_boot_walker()
        keys = list(em.record_cache_stats()["wholeReads"])
        self.assertTrue(any(k.endswith("<-some_boot_walker") for k in keys), "the walker, not the parse family: %s" % keys)
        self.assertFalse(any(k.split("<-")[-1] in ("parsed_session", "parse_session", "parse_cached", "_parse_store") for k in keys), "%s" % keys)
        # round two, low 3: the family is matched by code object, never by name: a local helper named like one is a walker
        self.fresh(); jd._PARSE_CACHE.clear(); jd._CHAIN_MEMO.clear()
        with em._JSONL_CACHE_LOCK:
            em._RECORD_CACHE_STATS["wholeReads"] = {}
        def _parse():
            return jd.parsed_session(SID, [path], NOW)
        def outer_walker():
            return _parse()
        outer_walker()
        keys = list(em.record_cache_stats()["wholeReads"])
        self.assertTrue(any(k.endswith("<-_parse") for k in keys), "a local helper named _parse is a walker, not the family: %s" % keys)

class KernelOverRestored(Harness):
    """The kernel's and the judges' body readers over a restored tree: every consumer the audit named hydrates what it
    reads, so the same answers come from the restored tree as from the whole parse, with no LazyBodyRead."""

    @classmethod
    def setUpClass(cls):
        cls.km = kernel_module()
        cls.jd = cls.km.jd

    def answers(self, tree):
        km, jd = self.km, self.jd
        segs = [seg for t in tree["turns"] for seg in em.segments(t)]
        store = {"placements": {}, "nodes": {}, "seq": 0}
        return {
            "anchors": [km._seg_anchors(seg["atoms"]) for seg in segs],
            "jumps": [km._seg_jump(seg["atoms"]) for seg in segs],
            "prompts": [km._seg_prompt(seg) for seg in segs],
            "lastText": [km._seg_last_text(seg["atoms"]) for seg in segs],
            "prose": [km._atom_prose_chars(a) for t in tree["turns"] for a in t["atoms"]],
            "userTexts": [km._atom_user_texts(a) for t in tree["turns"] for a in t["atoms"] if a.get("type") == "user"],
            "progress": km._open_turn_progress(tree["turns"]),
            "tasks": km._fold_tasks(tree),
            "landed": [km._turn_landed(t) for t in tree["turns"]],
            "units": [(u[0], u[1]) for u in jd.plan_units(tree, store)],
            "unitText": [jd._unit_text(seg["atoms"]) for seg in segs],
            "asstWork": [jd._has_asst_work(seg["atoms"]) for seg in segs],
            "mids": [km._seg_mids(seg) for seg in segs],                       # T358: the stored ids, or the markers'
            "humanFloor": km._human_turn_floor(tree),
            "txSets": (lambda s_: (s_[0], s_[1], s_[4]))(km._merge_tx_sets(tree, SID + "-" + str(id(tree)))),
            "bgHold": jd._awaiting_bg_hold(SID, "", tree, store, now=NOW),
        }

    def test_kernel_and_judge_readers_answer_the_same_over_the_restored_tree(self):
        for name in COMPACTING:
            with self.subTest(scenario=name):
                records, sent = G.SINGLE_FILE[name]
                path = self.write(name, records(), sent=sent)
                self.fresh()
                whole = self.parse(path)
                cold = json.loads(json.dumps(self.answers(whole), default=str))
                self.assertTrue(self.doc(path))
                self.fresh()
                modes = []
                tree = self.parse(path, modes)
                self.assertEqual(modes, ["restore"])
                self.assertTrue(any(a.get("lazy") is not None for t in tree["turns"] for a in t["atoms"]), "lazy atoms in play")
                got = json.loads(json.dumps(self.answers(tree), default=str))   # every reader hydrated what it needed
                self.assertEqual(got, cold)
                self.assertGreater(em.asm_checkpoint_stats()["hydratedAtoms"], 0, "the readers hydrated on demand")


class EventModelReaders(Harness):
    """Review find (C): the seam split and the declared plan read bodies inside the event model itself."""

    def _restored_with_doc(self):
        records, _ = G.SINGLE_FILE["compaction_atom"]
        recs = compacting_variant(records(), "seam")
        path = self.write("em-readers", recs)
        self.fresh(); whole = self.parse(path); self.doc(path)
        self.fresh(); tree = self.parse(path)
        self.assertTrue(any(a.get("lazy") is not None for t in tree["turns"] for a in t["atoms"]))
        return whole, tree

    def test_a_seam_split_inside_a_pre_cut_segment_hydrates(self):
        whole, tree = self._restored_with_doc()
        for w_turn, r_turn in zip(whole["turns"], tree["turns"]):
            for w_seg, r_seg in zip(em.segments(w_turn), em.segments(r_turn)):
                if len(w_seg["atoms"]) < 2:
                    continue
                t_split = w_seg["atoms"][0]["t"]
                r_split = em.split_segment(r_seg, t_split)            # reads the tail's bodies: hydrates, never raises
                w_split = em.split_segment(w_seg, t_split)
                if r_split is None or w_split is None:
                    self.assertEqual(r_split, w_split)
                    continue
                for part in r_split:
                    em.hydrate(part["atoms"], SID)
                self.assertEqual(_strip({"turns": [dict(r_split[0]), dict(r_split[1])]}), _strip({"turns": [dict(w_split[0]), dict(w_split[1])]}),
                                 "the seam split reads the same bodies")

    def test_the_declared_plan_over_a_restored_tree_hydrates(self):
        whole, tree = self._restored_with_doc()
        em._ASM_CKPT_STATS.update(hydratedAtoms=0, hydratedBytes=0, hydratedBy={})
        self.assertEqual(em.declared_plan(tree), em.declared_plan(whole))
        self.assertEqual(em.declared_plan(tree), [], "this scenario declares no plan")
        self.assertEqual((em.asm_checkpoint_stats()["hydratedAtoms"], em.asm_checkpoint_stats()["hydratedBy"]), (0, {}),
                         "review find (1): a session with no plan hydrates nothing for the planner's fold (it asked for the whole tree)")

    def test_the_declared_plan_hydrates_only_the_task_call_and_its_result(self):
        t0 = NOW - 7200
        recs = [G.uline(t0, "plan the retry work", "u1", None),
                G.aline(t0 + 10, "", "a1", "u1", tools=("TaskCreate",), stop="tool_use"),
                G.trline(t0 + 11, "tu_a1_0", "r1", "a1", content="Task #7 created"),
                G.aline(t0 + 20, "the plan is filed", "a2", "r1", stop="end_turn"),
                G.uline(t0 + 100, "now do it", "u2", "a2"),
                G.aline(t0 + 130, "done with the first step", "a3", "u2", stop="end_turn")]
        path = self.write("plan", compacting_variant(recs, "pln"))
        self.fresh(); whole = self.parse(path); plan = em.declared_plan(whole)
        self.assertEqual([t["key"] for t in plan], ["7"], "the whole parse folds the declared step")
        self.assertTrue(self.doc(path), em.asm_checkpoint_stats())
        self.fresh(); modes = []
        tree = self.parse(path, modes); self.assertEqual(modes, ["restore"])
        em._ASM_CKPT_STATS.update(hydratedAtoms=0, hydratedBytes=0, hydratedBy={})
        self.assertEqual(em.declared_plan(tree), plan)
        st = em.asm_checkpoint_stats()
        self.assertEqual(st["hydratedAtoms"], 2, "the TaskCreate call and its result, nothing else: %s" % st["hydratedBy"])
        self.assertEqual(sorted(st["hydratedBy"]), ["declared_plan"])
        self.assertEqual(sorted(a["uuid"] for a in em.plan_atoms(tree)), ["a1", "r1"])


class ConcurrentHydration(Harness):
    def test_two_threads_hydrating_the_same_atoms_read_each_record_once(self):
        """CI find (2026-09-11): the judges' unit text and the frame's markdown hydrate the same restored atoms at a boot
        from two threads; both missed the memo and both read (7806 reads for 7800 atoms). The file's read stripe is held
        across a group and the memo re-checked under it, so each record is read once whoever asks first."""
        import threading
        records, sent = G.SINGLE_FILE["compaction_atom"]
        path = self.write("threads", records(), sent=sent)
        self.fresh(); self.parse(path); self.assertTrue(self.doc(path))
        self.fresh(); modes = []
        tree = self.parse(path, modes); self.assertEqual(modes, ["restore"])
        lazy = [a for t in tree["turns"] for a in t["atoms"] if a.get("lazy") is not None]
        self.assertGreater(len(lazy), 0)
        copies = [[dict(a, lazy=dict(a["lazy"])) for a in lazy] for _ in range(4)]   # each thread its own atom dicts, same uuids
        em._ASM_CKPT_STATS.update(hydratedAtoms=0, hydratedBytes=0, hydratedBy={})
        gate, errors = threading.Barrier(4), []
        def run(atoms):
            try:
                gate.wait(5); em.hydrate(atoms, SID, by="thread")
            except Exception as e:                                # noqa: BLE001
                errors.append(e)
        ts = [threading.Thread(target=run, args=(c,)) for c in copies]
        for t in ts:
            t.start()
        for t in ts:
            t.join(10)
        self.assertEqual(errors, [])
        self.assertEqual(em.asm_checkpoint_stats()["hydratedAtoms"], len(lazy), "one read per record across four threads")
        for c in copies:
            self.assertEqual([a["message"] for a in c], [a["message"] for a in copies[0]], "every thread holds the same bodies")


class ClearedSessionDocument(Harness):
    def test_the_per_file_rewound_walk_leaves_a_lineage_document_standing(self):
        """Review find (B): the one-file walk asked for the leaf's document with the leaf alone as its inputs, so a
        /cleared session's document (its inputs name the anchor too) counted an inputs fallback and was unlinked on
        every reconcile pass. The walk asks quietly and the document stands."""
        jd = kernel_module().jd                                # the judge through the module's one kernel load
        d = self.td / "cleared"; d.mkdir()
        anchor = d / (SID + ".jsonl")
        leaf_sid = "77777777-2222-4333-8444-000000000777"
        leaf = d / (leaf_sid + ".jsonl")
        anchor.write_text("".join(json.dumps(r) + "\n" for r in G.SINGLE_FILE["queued_new_turn"][0]()))
        recs = compacting_variant(G.SINGLE_FILE["compaction_atom"][0](), "clr")
        leaf.write_text("".join(json.dumps(r) + "\n" for r in recs))
        cands = [str(leaf), str(anchor)]
        self.fresh()
        em.parse_session(str(leaf), rompuuid=SID, candidate_files=cands, states=None, postal_log=[], now=NOW)
        self.assertTrue(self.doc(str(leaf)), em.asm_checkpoint_stats())
        em._ASM_CKPT_STATS["fallbacks"] = {}
        saved = jd._sdk_owned
        jd._sdk_owned = lambda fsid: False
        try:
            rewound, fails = jd._per_file_rewound(SID, cands)     # the judges' walk itself, over the leaf and the anchor
        finally:
            jd._sdk_owned = saved
        self.assertIsInstance(rewound, set); self.assertEqual(fails, 0)
        self.assertEqual(em.asm_checkpoint_stats()["fallbacks"], {}, "a quiet ask: no fallback counted")
        self.assertTrue(em._asm_ckpt_file(str(leaf)).exists(), "the display's document stands")
        self.fresh(); modes = []
        em.parse_session(str(leaf), rompuuid=SID, candidate_files=cands, states=None, postal_log=[], now=NOW, asm_mode_out=modes)
        self.assertEqual(modes, ["restore"], "and the next parse restores from it")


class LazyBodies(Harness):
    def test_a_body_read_before_hydration_is_loud_and_hydration_counts(self):
        records, _ = G.SINGLE_FILE["compaction_atom"]
        path = self.write("compaction_atom", records())
        self.fresh(); self.parse(path); self.assertTrue(self.doc(path))
        self.fresh()
        tree = self.parse(path)
        lazy = [a for t in tree["turns"] for a in t["atoms"] if a.get("lazy") is not None]
        self.assertTrue(lazy)
        with self.assertRaises(em.LazyBodyRead):
            em._text_of(em._content(lazy[0]["message"]))
        with self.assertRaises((em.LazyBodyRead, TypeError)):      # whichever the encoder trips first, a lazy body never
            json.dumps(tree)                                       #  leaves as an empty message
        n = em.hydrate(lazy, SID)
        self.assertEqual(n, len(lazy))
        st = em.asm_checkpoint_stats()
        self.assertEqual(st["hydratedAtoms"], len([a for a in lazy]), "one read per lazy atom")
        self.assertGreater(st["hydratedBytes"], 0)
        self.assertEqual(em.hydrate(lazy, SID), 0, "nothing left to hydrate")
        json.dumps(tree)


if __name__ == "__main__":
    unittest.main()
