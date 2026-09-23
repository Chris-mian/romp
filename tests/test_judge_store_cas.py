#!/usr/bin/env python3
"""Optimistic concurrency on the goal store (the user 2026-07-22).

Writers are concurrent and uncoordinated: every judge pass holds its store across a minutes-long model
call, while the kernel's nudge tick stamps blocks on its own thread. save_goals used to rename blindly, so
last-writer-wins silently ERASED the other's events — a card the nudge had just blocked flashed back to
'working' for one push before the next load healed it from the override journal.

save_goals now compares the revision it loaded at against the one on disk and REBASES (union of verdict
logs) instead of clobbering. The store is an append-only event log, so two writers appending different
events never really conflicted: the right answer is both sets. All fixtures SYNTHETIC.
"""
import contextlib
import errno
import json
import os
import tempfile
import unittest
from unittest import mock
from romp_load import load_source
from pathlib import Path

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "bin")
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
jd = load_source("romp_judge", os.path.join(BIN, "romp-judge"))

SID = "11111111-2222-3333-4444-555555555555"
NOW = 1781100000
T0 = NOW - 3600


class StoreCas(unittest.TestCase):
    def setUp(self):
        self._saved = jd.STATE
        self.td = tempfile.TemporaryDirectory()
        jd._rebind_state(Path(self.td.name))

    def tearDown(self):
        jd._rebind_state(self._saved)
        self.td.cleanup()

    def _nid(self, n):
        return "%s:g%d" % (SID, n)

    def _seed(self):
        """One working top goal, published."""
        s = {"rompUuid": SID, "seq": 0, "placementsV": jd.PLACEMENTS_V, "nodes": {},
             "placements": {}, "status": {}}
        jd.apply_plan(s, "s1", T0, [{"do": "mint", "why": "x", "text": "A goal"}], [])
        jd.rollup_status(s, session_closed=False)
        jd.save_goals(SID, s)

    def test_rev_advances_on_every_publish(self):
        self._seed()
        r1 = jd._disk_rev(SID)
        self.assertGreater(r1, 0, "a published store carries a revision")
        s = jd.load_goals(SID)
        # A REAL change: since 2026-07-22 a save whose content matches disk is not a publish at all and
        # leaves `rev` where it is (see tests/test_judge_store_noop_publish.py). `rev` counts publications.
        jd.record_verdict(s, s["nodes"][self._nid(1)], "romp", "block", T0 + 30, why="needs a decision")
        jd.rollup_status(s, session_closed=False)
        jd.save_goals(SID, s)
        self.assertGreater(jd._disk_rev(SID), r1, "each publish advances the revision")

    def test_load_stamps_a_base_rev_that_is_never_serialized(self):
        self._seed()
        s = jd.load_goals(SID)
        self.assertIn("_baseRev", s, "the loaded revision is remembered for the CAS")
        jd.save_goals(SID, s)
        self.assertNotIn("_baseRev", json.loads((jd.GOALDIR / (SID + ".json")).read_text()),
                         "the transient base revision is never written to disk")

    @staticmethod
    @contextlib.contextmanager
    def _reads_raise(target):
        """Inside the block, every Path.read_text of `target` raises OSError (the EMFILE/EIO shape a
        busy kernel meets); other paths read normally."""
        real = Path.read_text
        def boom(p, *a, **k):
            if p == target:
                raise OSError(errno.EMFILE, "synthetic: too many open files")
            return real(p, *a, **k)
        Path.read_text = boom
        try:
            yield
        finally:
            Path.read_text = real

    def test_a_store_loaded_without_its_unreadable_journal_is_marked_and_the_mark_is_never_serialized(self):
        # A store FILE that exists and cannot be read raises (ReadFaultCas), and an unparseable one is
        # quarantined aside and legitimately fresh, so the one load that answers with less than the files
        # hold is a parsed store whose override JOURNAL exists and could not be read: _replay_overrides
        # returns it without the user's rows. A reader that caches "what the files hold" by their identity
        # (the kernel's awaiting-lift gate) must tell that answer from a complete one, so it carries a
        # transient `_unread` mark beside `_baseRev`: popped before a publish and outside the content hash.
        self.assertNotIn("_unread", jd.load_goals(SID), "no file: an empty store IS the truth")
        self._seed()
        self.assertNotIn("_unread", jd.load_goals(SID), "a parsed store with no journal is what the files say")
        jd.append_override(SID, self._nid(1), "resolve", T0 + 60)
        with self._reads_raise(jd._overrides_dir() / (SID + ".jsonl")):
            s = jd.load_goals(SID)
        self.assertIn(self._nid(1), s["nodes"], "the store itself was read")
        self.assertEqual(s.get("_unread"), "journal", "...but the journal was not: the user's gestures are missing")
        self.assertFalse(s["nodes"][self._nid(1)].get("nodeComplete"), "the journaled resolve is not in this view")
        self.assertEqual(s["_baseRev"], jd._disk_rev(SID), "the CAS base is the parsed store's, as before")
        self.assertNotIn("_unread", json.loads(jd._store_content(s)), "not store content")
        s["nodes"][self._nid(1)]["text"] = "A goal, retitled"
        jd.save_goals(SID, s)
        gp = jd.GOALDIR / (SID + ".json")
        self.assertNotIn("_unread", json.loads(gp.read_text()), "the mark is never written to disk")
        final = jd.load_goals(SID)
        self.assertNotIn("_unread", final, "a journal that exists and reads leaves no mark")
        nd = final["nodes"][self._nid(1)]
        self.assertEqual(nd["text"], "A goal, retitled")
        self.assertTrue(nd.get("nodeComplete"), "the journal replays on the next load: the publish lost nothing durable")

    def test_a_stale_pass_no_longer_erases_a_concurrent_block(self):
        # THE BUG: pass A loads, goes off to its model call; the nudge tick blocks the card and publishes;
        # pass A then saves its pre-block snapshot and wipes the block -> the card flashes back to working.
        self._seed()
        gid = self._nid(1)
        a = jd.load_goals(SID)                       # pass A's snapshot (pre-block)
        nudge = jd.load_goals(SID)                   # the nudge tick, on its own thread
        jd.record_verdict(nudge, nudge["nodes"][gid], "nudge", "block", T0 + 100, why="owed")
        jd.rollup_status(nudge, session_closed=False)
        jd.save_goals(SID, nudge)                    # the block is published
        self.assertEqual(jd.load_goals(SID)["status"][gid], "blocked", "premise: the block landed")
        jd.save_goals(SID, a)                        # pass A publishes its STALE snapshot
        healed = jd.load_goals(SID)
        self.assertTrue(any(e.get("kind") == "block" for e in healed["nodes"][gid].get("log") or []),
                        "the concurrent block survives the stale pass's save")
        self.assertEqual(healed["status"][gid], "blocked",
                         "and the rolled-up status still reads blocked - no working flicker")

    def test_both_writers_events_survive_a_rebase(self):
        # two passes append DIFFERENT events; the store is an event log, so the answer is BOTH
        self._seed()
        gid = self._nid(1)
        a, b = jd.load_goals(SID), jd.load_goals(SID)
        jd.record_verdict(a, a["nodes"][gid], "planner", "block", T0 + 50, why="a's block")
        jd.record_verdict(b, b["nodes"][gid], "closer", "done", T0 + 60, why="b's done")
        jd.save_goals(SID, a)
        jd.save_goals(SID, b)                        # b rebases onto a instead of clobbering
        log = jd.load_goals(SID)["nodes"][gid].get("log") or []
        kinds = {(e.get("src"), e.get("kind")) for e in log}
        self.assertIn(("planner", "block"), kinds, "the first writer's event survives")
        self.assertIn(("closer", "done"), kinds, "the second writer's event is there too")

    def test_a_stale_pass_no_longer_erases_a_fresh_takeaway(self):
        # "Stuck on Distilling" (the user 2026-08-23): distill-family fields are STATE, not log rows,
        # so the event fold never carried them — a pass holding a pre-distill snapshot across its model
        # call erased the freshly-published summary on save, the card flipped back to "Distilling…",
        # and the distiller re-ran, oscillating for as long as writers overlapped.
        self._seed()
        gid = self._nid(1)
        a = jd.load_goals(SID)                       # pass A's snapshot (pre-distill)
        d = jd.load_goals(SID)                       # the distiller
        d["nodes"][gid]["summary"] = "Shipped the exporter end to end."
        d["nodes"][gid]["distilledMt"] = T0 + 500
        d["nodes"][gid]["blockSummary"] = "Decide: keep or drop the legacy path."
        d["nodes"][gid]["briefedMt"] = T0 + 500
        jd.save_goals(SID, d)
        jd.record_verdict(a, a["nodes"][gid], "planner", "unblock", T0 + 600, why="a's own event")
        jd.save_goals(SID, a)                        # the stale pass publishes; must rebase, not clobber
        nd = jd.load_goals(SID)["nodes"][gid]
        self.assertEqual(nd.get("summary"), "Shipped the exporter end to end.",
                         "the takeaway survives a stale writer's save")
        self.assertEqual(nd.get("distilledMt"), T0 + 500)
        self.assertEqual(nd.get("blockSummary"), "Decide: keep or drop the legacy path.")

    def test_the_newer_distill_episode_wins_and_a_deliberate_reopen_is_kept(self):
        self._seed()
        gid = self._nid(1)
        # disk holds an OLD episode; our snapshot re-distilled a NEWER one → ours stands
        d0 = jd.load_goals(SID)
        d0["nodes"][gid]["summary"] = "old episode"
        d0["nodes"][gid]["distilledMt"] = T0 + 100
        jd.save_goals(SID, d0)
        mine = jd.load_goals(SID)
        stale = jd.load_goals(SID)
        mine["nodes"][gid]["summary"] = "new episode"
        mine["nodes"][gid]["distilledMt"] = T0 + 200
        jd.save_goals(SID, stale)                    # move the rev so mine must rebase
        jd.save_goals(SID, mine)
        self.assertEqual(jd.load_goals(SID)["nodes"][gid].get("summary"), "new episode")
        # the blocked path's deliberate ""→None re-open keeps its OLD briefedMt on purpose: an equal
        # disk stamp must not resurrect the "" it nulled
        b0 = jd.load_goals(SID)
        b0["nodes"][gid]["blockSummary"] = ""
        b0["nodes"][gid]["briefedMt"] = T0 + 300
        jd.save_goals(SID, b0)
        reopener = jd.load_goals(SID)
        mover = jd.load_goals(SID)
        reopener["nodes"][gid]["blockSummary"] = None
        jd.save_goals(SID, mover)                    # rev moves; the re-opener must rebase
        jd.save_goals(SID, reopener)
        self.assertIsNone(jd.load_goals(SID)["nodes"][gid].get("blockSummary"),
                          "an equal disk stamp keeps the re-opener's pending state")

    def test_a_node_minted_by_the_other_writer_is_adopted(self):
        self._seed()
        a = jd.load_goals(SID)                       # snapshot before the other writer mints
        b = jd.load_goals(SID)
        jd.apply_plan(b, "s2", T0 + 20, [{"do": "mint", "why": "x", "text": "Their new goal"}],
                      jd.open_menu(b))
        jd.save_goals(SID, b)
        jd.save_goals(SID, a)                        # a must not delete a goal it never saw
        nodes = jd.load_goals(SID)["nodes"]
        self.assertIn(self._nid(2), nodes, "the other writer's minted node survives the stale save")
        self.assertIn(self._nid(1), nodes)

    def test_an_in_place_rewrite_that_leaves_rev_alone_is_a_publication_the_holders_save_rebases_onto(self):
        """The CI red of 2026-09-23 on the box lab: its driver edits the store IN PLACE (a node added, `seq` bumped, `rev` untouched, the
        shape of a hand edit too), and a judge pass whose store predates the edit saved after it. The CAS compared revisions alone, saw the
        file's revision where it loaded it, and published the pass's store over the edit: the new node gone, the driver's seq reverted, the
        card never built. The CAS now compares the identity of the file the base was read from as well, so the rewrite reads as a
        publication and the save rebases onto it: the minted node survives, the holder's own event lands beside it."""
        self._seed()
        holder = jd.load_goals(SID)                  # the pass's private copy, loaded before the edit
        path = jd.GOALDIR / (SID + ".json")
        st = json.loads(path.read_text())           # the editor: read, mutate, seq bumped, rev untouched, written in place
        g9 = self._nid(9)
        st["nodes"][g9] = {"id": g9, "text": "Their in-place goal", "parentId": None, "nodeComplete": False, "blocked": True, "blockWhy": "q",
                           "cleared": False, "trail": [], "t": T0 + 30, "log": [{"ev_t": T0 + 30, "src": "planner", "kind": "block", "why": "asked: q", "at": T0 + 30}]}
        st["status"][g9] = "blocked"; st["seq"] = (st.get("seq") or 0) + 1
        path.write_text(json.dumps(st))
        jd.record_verdict(holder, holder["nodes"][self._nid(1)], "unblocker", "note", T0 + 40, why="the pass ends with a save")
        jd.save_goals(SID, holder)
        after = json.loads(path.read_text())
        self.assertIn(g9, after["nodes"], "the in-place edit's node survives the holder's save (before: published over, the revision unmoved)")
        self.assertEqual(after["nodes"][g9].get("blockSummary"), None); self.assertEqual(after["status"].get(g9), "blocked")
        self.assertTrue(any(e.get("why") == "the pass ends with a save" for e in after["nodes"][self._nid(1)]["log"]), "and the holder's own event landed beside it")
        self.assertNotIn("_baseIdent", after, "the identity base is transient, never serialized")
        self.assertNotIn("_baseIdent", json.loads(path.read_text()).keys())
        # the holder's next save is uncontended: the identity re-stamped after the publish is the file's, so no second rebase
        jd.record_verdict(holder, holder["nodes"][self._nid(1)], "unblocker", "note", T0 + 50, why="a second event")
        with mock.patch.object(jd, "_rebase_onto_disk", side_effect=AssertionError("no rebase owed")) as rb:
            jd.save_goals(SID, holder)
        self.assertEqual(rb.call_count, 0, "an uncontended second save rebases nothing (the identity written is the identity read back)")

    def test_a_store_whose_identity_base_came_through_a_json_round_trip_saves_without_a_rebase(self):
        """The round-one lane red of PR 2064: the identity base is a tuple, and a store that went through json.loads(json.dumps(...)) holds it
        as a list; a list never equals a tuple, so compared as loaded every save from such a store would rebase forever. The compare is in
        tuples on both sides."""
        self._seed()
        s = jd.load_goals(SID)
        s2 = json.loads(json.dumps(s))               # the round trip: _baseRev stays an int, _baseIdent becomes a list
        self.assertIsInstance(s2["_baseIdent"], list, "premise: the round trip turned the tuple into a list")
        jd.record_verdict(s2, s2["nodes"][self._nid(1)], "unblocker", "note", T0 + 40, why="an event to publish")
        with mock.patch.object(jd, "_rebase_onto_disk", side_effect=AssertionError("no rebase owed")) as rb:
            jd.save_goals(SID, s2)
        self.assertEqual(rb.call_count, 0, "an uncontended save from the round-tripped store rebases nothing (before: the list never equalled the tuple)")
        self.assertTrue(any(e.get("why") == "an event to publish" for e in json.loads((jd.GOALDIR / (SID + ".json")).read_text())["nodes"][self._nid(1)]["log"]), "and it published")

    def test_the_shared_view_carries_the_identity_base_the_writer_loader_carries(self):
        """The round-one lane red of PR 2064: load_goals carried _baseIdent and load_goals_shared did not, so the two views disagreed. The
        shared view stamps the identity of the bytes it read, so the views agree by construction, and a fresh store names its absent file."""
        self._seed()
        shared, writer = jd.load_goals_shared(SID), jd.load_goals(SID)
        self.assertEqual(shared["_baseIdent"], writer["_baseIdent"], "one identity for one file: %r %r" % (shared["_baseIdent"], writer["_baseIdent"]))
        self.assertIsNotNone(writer["_baseIdent"]); self.assertEqual(len(writer["_baseIdent"]), 3, "inode, mtime_ns, size")
        fresh = jd.load_goals("99999999-8888-7777-6666-555555555555")
        self.assertIn("_baseIdent", fresh); self.assertIsNone(fresh["_baseIdent"], "no file at the load: None, set explicitly")

    def test_an_uncontended_first_save_after_a_load_rebases_zero_times(self):
        """The round-one verifier of PR 2064: nothing held the load's recorded identity to the file's. A load whose identity base were None
        (or the wrong file's, as the quarantine-decline retry's was) would rebase on every first save, correctly but for nothing, and every
        CAS test stayed green. The identity the load records IS the file's: an uncontended first save compares equal and rebases zero times."""
        self._seed()
        s = jd.load_goals(SID)
        self.assertIsNotNone(s["_baseIdent"], "premise: a file was read")
        jd.record_verdict(s, s["nodes"][self._nid(1)], "unblocker", "note", T0 + 40, why="the first event after the load")
        real = jd._rebase_onto_disk
        calls = []

        def counting(fsid, store):
            calls.append(fsid); return real(fsid, store)
        with mock.patch.object(jd, "_rebase_onto_disk", counting):
            jd.save_goals(SID, s)
        self.assertEqual(calls, [], "the identity recorded at the load is the file's own: no rebase on an uncontended first save (a None or a stale identity would rebase here)")
        after = json.loads((jd.GOALDIR / (SID + ".json")).read_text())
        self.assertTrue(any(e.get("why") == "the first event after the load" for e in after["nodes"][self._nid(1)]["log"]), "and it published")

    def test_the_identity_recorded_after_a_quarantine_decline_is_the_file_that_was_read(self):
        """The round-one verifier of PR 2064: the reader's quarantine-decline retry recursed without the identity list, so the outer list kept
        the unparseable file's identity and the load stamped it as the base while the bytes came from the new file; the next save rebased
        spuriously. The retry hands the list on, and the base is the identity of the file whose bytes the load returned."""
        self._seed()
        path = jd.GOALDIR / (SID + ".json")
        good = path.read_bytes()
        path.write_bytes(b"{ torn")                  # unparseable bytes at the load's first read
        real_q = jd._quarantine_store

        def declining(p, reason, st):                # the quarantine declines: the file changed under the reader (a peer published)
            path.write_bytes(good)
            return None
        with mock.patch.object(jd, "_quarantine_store", declining):
            s = jd.load_goals(SID)
        st = path.stat()
        self.assertEqual(tuple(s["_baseIdent"]), (st.st_ino, st.st_mtime_ns, st.st_size), "the base is the good file's identity, not the torn file's (before: the torn file's, a size of 6)")
        jd.record_verdict(s, s["nodes"][self._nid(1)], "unblocker", "note", T0 + 40, why="after the decline")
        with mock.patch.object(jd, "_rebase_onto_disk", side_effect=AssertionError("no rebase owed")) as rb:
            jd.save_goals(SID, s)
        self.assertEqual(rb.call_count, 0, "and the save after it rebases nothing")

    def test_a_file_created_after_a_fresh_load_is_a_publication_too(self):
        """No file at the load (a fresh store, base 0, no identity); an editor creates one without a revision before the first save. On the
        revision alone (0 against 0) the save published the fresh store over it; the file's presence is the moved identity."""
        holder = jd.load_goals(SID)                  # absent: the fresh store
        path = jd.GOALDIR / (SID + ".json"); path.parent.mkdir(parents=True, exist_ok=True)
        g7 = self._nid(7)                            # an id the pass's mint (g1) cannot collide with
        path.write_text(json.dumps({"rompUuid": SID, "seq": 1, "nodes": {g7: {"id": g7, "text": "Created outside", "parentId": None, "nodeComplete": False,
                                                                                 "blocked": False, "cleared": False, "trail": [], "t": T0, "log": []}},
                                    "placements": {}, "status": {g7: "working"}}))
        jd.apply_plan(holder, "s1", T0 + 10, [{"do": "mint", "why": "x", "text": "The pass's goal"}], [])
        jd.save_goals(SID, holder)
        after = json.loads(path.read_text())
        self.assertIn(g7, after["nodes"], "the node the editor created survives the fresh store's first save (before: 0 against 0 passed the CAS)")
        self.assertEqual(sorted(after["nodes"]), sorted([self._nid(1), g7]), "both writers' nodes: %r" % sorted(after["nodes"]))

    def test_a_field_the_other_writer_changed_is_carried_onto_a_stale_save(self):
        """The manager's ruling of 2026-09-23 on the box lab's long-brief miss: two writers hold one node; the second changes a plain field
        (a brief edited without its family's stamp) and publishes; the first, holding the older base, adds a node and saves. The rebase
        adopted the new node but kept the first writer's copy of the field, so the second's edit was published over (live: a brief edited
        in place lost to a judge pass's save). The load records a digest per field as the file held it, and the rebase carries every field
        the other writer moved where this writer did not."""
        self._seed()
        g1 = self._nid(1)
        a = jd.load_goals(SID)                       # the pass's copy, loaded before the edit
        b = jd.load_goals(SID)                       # the editor: a field changed, no family stamp
        b["nodes"][g1]["parentId"] = "the parent the editor set"   # a plain field (a brief is a FAMILY field: its own pin below)
        jd.save_goals(SID, b)
        jd.apply_plan(a, "s2", T0 + 20, [{"do": "mint", "why": "x", "text": "The pass's new goal"}], jd.open_menu(a))
        jd.save_goals(SID, a)                        # a's base is behind: the rebase folds b's publish in
        after = jd.load_goals(SID)
        self.assertEqual(after["nodes"][g1].get("parentId"), "the parent the editor set", "the field the other writer changed rides the stale save (before: the holder's copy won and the edit was lost)")
        self.assertIn(self._nid(2), after["nodes"], "and the new node is there, as before")

    def test_where_both_writers_changed_one_field_the_incoming_writers_change_wins(self):
        """The per-field rule's tie: both moved the same field since the base; the writer publishing now keeps its own change (said in the
        design line), and the fields only the other moved still carry."""
        self._seed()
        g1 = self._nid(1)
        a = jd.load_goals(SID); b = jd.load_goals(SID)
        b["nodes"][g1]["text"] = "theirs"; b["nodes"][g1]["parentId"] = "their parent"
        jd.save_goals(SID, b)
        a["nodes"][g1]["text"] = "ours"
        jd.record_verdict(a, a["nodes"][g1], "unblocker", "note", T0 + 40, why="an event of ours")
        jd.save_goals(SID, a)
        after = jd.load_goals(SID)["nodes"][g1]
        self.assertEqual(after.get("text"), "ours", "both moved text: the incoming writer's change wins")
        self.assertEqual(after.get("parentId"), "their parent", "the field only they moved is carried beside it")

    def test_a_field_the_other_writer_removed_goes_on_a_stale_save(self):
        self._seed()
        g1 = self._nid(1)
        a = jd.load_goals(SID); b = jd.load_goals(SID)
        b["nodes"][g1]["label"] = "a label to remove later"; jd.save_goals(SID, b)
        a2 = jd.load_goals(SID)                      # a fresh holder at the revision with the label
        b2 = jd.load_goals(SID); b2["nodes"][g1].pop("label", None); jd.save_goals(SID, b2)   # the other writer removes it
        jd.record_verdict(a2, a2["nodes"][g1], "unblocker", "note", T0 + 50, why="ours"); jd.save_goals(SID, a2)
        self.assertNotIn("label", jd.load_goals(SID)["nodes"][g1], "the removal the other writer made rides the stale save")

    def test_the_field_base_is_the_bytes_the_load_read_found_by_identity_and_moves_with_each_publish(self):
        """No digest, no copy at a load or a save: the base is the bytes the load read, found by the identity the load stamped in the
        raw-parse memo's history of the last few versions, only when a rebase runs. After a publish the holder stands on what it wrote,
        so a later move by the other writer is carried on the next save."""
        self._seed()
        g1 = self._nid(1)
        a = jd.load_goals(SID)
        self.assertNotIn("_baseFields", a, "no field digests on the loaded store (the round-one verifier: 200 ms a load, 4.7 MB retained)")
        self.assertIsNotNone(a["_baseIdent"])
        jd.record_verdict(a, a["nodes"][g1], "unblocker", "note", T0 + 40, why="one"); jd.save_goals(SID, a)
        raw = json.loads((jd.GOALDIR / (SID + ".json")).read_text())
        self.assertNotIn("_baseIdent", raw, "transient, never serialized"); self.assertIn("_baseIdent", a, "re-stamped on the holder after the publish")
        b = jd.load_goals(SID); b["nodes"][g1]["parentId"] = "later parent"; jd.save_goals(SID, b)   # the other writer moves a plain field after our publish
        jd.record_verdict(a, a["nodes"][g1], "unblocker", "note", T0 + 60, why="two"); jd.save_goals(SID, a)
        self.assertEqual(jd.load_goals(SID)["nodes"][g1].get("parentId"), "later parent", "the re-stamped base sees the move after our publish and carries it")
        shared, writer = jd.load_goals_shared(SID), jd.load_goals(SID)
        self.assertEqual(json.dumps(shared), json.dumps(writer), "the shared view and the writer loader still agree key for key")

    def test_a_second_rebase_iteration_stands_on_the_first_iterations_disk(self):
        """The round-one verifier: the field base was the load's for every iteration of the CAS loop, so when a third writer published
        between the first rebase's re-check and the retry, the second iteration read the values the first had carried as this holder's
        own moves and published them over the newer ones. The identity the rebase reads moves to the version it rebased onto, and the
        next iteration compares against that."""
        self._seed()
        g1 = self._nid(1)
        a = jd.load_goals(SID)
        b = jd.load_goals(SID); b["nodes"][g1]["parentId"] = "V1"; jd.save_goals(SID, b)   # the first other writer
        real = jd._rebase_onto_disk
        calls = []

        def rebase_then_third(fsid, store):
            real(fsid, store)
            calls.append(1)
            if len(calls) == 1:                      # between the first rebase and the loop's re-check: a third writer publishes V2
                c = jd.load_goals(SID); c["nodes"][g1]["parentId"] = "V2"; jd.save_goals(SID, c)
        jd.record_verdict(a, a["nodes"][g1], "unblocker", "note", T0 + 40, why="ours")
        with mock.patch.object(jd, "_rebase_onto_disk", rebase_then_third):
            jd.save_goals(SID, a)
        self.assertEqual(len(calls), 2, "premise: two rebase iterations")
        self.assertEqual(jd.load_goals(SID)["nodes"][g1].get("parentId"), "V2", "the second iteration carries the third writer's V2 (before: V1, carried in the first, was published over V2)")

    def test_a_family_field_is_left_to_the_family_merge_and_an_in_place_edit_stamps_its_family(self):
        """The round-one verifier: the carry copied a family's stamp and fields one by one, so the family merge never fired and a holder who
        edited one family field published one episode's line with another's parts. Every family-managed key is excluded from the carry
        and the family merge adopts a family as a unit by its stamp: an in-place brief edit without the stamp is not carried; with its
        family stamped newer it is adopted, parts and all."""
        self._seed()
        g1 = self._nid(1)
        a = jd.load_goals(SID); a["nodes"][g1]["briefedMt"] = 1000; a["nodes"][g1]["blockSummary"] = "the pass's brief"; a["nodes"][g1]["briefParts"] = ["p1"]; jd.save_goals(SID, a)
        holder = jd.load_goals(SID)                  # stands on the stamped brief
        path = jd.GOALDIR / (SID + ".json")
        st = json.loads(path.read_text()); st["nodes"][g1]["blockSummary"] = "edited without a stamp"; st["rev"] += 1; path.write_text(json.dumps(st))
        jd.record_verdict(holder, holder["nodes"][g1], "unblocker", "note", T0 + 40, why="ours"); jd.save_goals(SID, holder)
        self.assertEqual(json.loads(path.read_text())["nodes"][g1].get("blockSummary"), "the pass's brief", "a family field edited without its stamp is the family merge's call: equal stamps keep the holder's")
        holder2 = jd.load_goals(SID)
        st = json.loads(path.read_text()); st["nodes"][g1]["blockSummary"] = "edited and stamped"; st["nodes"][g1]["briefParts"] = ["e1", "e2"]; st["nodes"][g1]["briefedMt"] = 2000; st["rev"] += 1; path.write_text(json.dumps(st))
        jd.record_verdict(holder2, holder2["nodes"][g1], "unblocker", "note", T0 + 50, why="ours again"); jd.save_goals(SID, holder2)
        after = json.loads(path.read_text())["nodes"][g1]
        self.assertEqual((after.get("blockSummary"), after.get("briefParts"), after.get("briefedMt")), ("edited and stamped", ["e1", "e2"], 2000), "the stamped family is adopted as a unit")

    def test_a_diary_owned_key_the_other_writer_wrote_is_not_carried(self):
        """The rollup re-derives the protected keys after the rebase, which hid this: with the rollup held still, a diary-owned key the other
        writer wrote directly (a why without its landing event) is not the carry's to copy."""
        self._seed()
        g1 = self._nid(1)
        holder = jd.load_goals(SID)
        path = jd.GOALDIR / (SID + ".json")
        st = json.loads(path.read_text()); st["nodes"][g1]["blockWhy"] = "a why written by hand"; st["rev"] += 1; path.write_text(json.dumps(st))
        jd.record_verdict(holder, holder["nodes"][g1], "unblocker", "note", T0 + 40, why="ours")
        with mock.patch.object(jd, "rollup_status", lambda store, session_closed=False, **kw: None):
            jd.save_goals(SID, holder)
        self.assertNotEqual(json.loads(path.read_text())["nodes"][g1].get("blockWhy"), "a why written by hand", "a diary-owned key is not carried (the log is its source)")

    def test_a_base_that_rolled_out_of_the_raw_history_carries_nothing_and_says_so(self):
        """The history keeps the last few versions per path; a holder that outlived them (more publishes meanwhile than it keeps) rebases as
        before the rule, carrying no plain field, and the goals counters count the miss."""
        self._seed()
        g1 = self._nid(1)
        holder = jd.load_goals(SID)
        for i in range(jd._RAW_HISTORY_KEEP + 2):    # loop-ok: bounded by the history's depth
            w = jd.load_goals(SID); w["nodes"][g1]["parentId"] = "V%d" % i; jd.save_goals(SID, w)
        before = dict(jd._GOAL_IO) if hasattr(jd, "_GOAL_IO") else None
        jd.record_verdict(holder, holder["nodes"][g1], "unblocker", "note", T0 + 40, why="ours"); jd.save_goals(SID, holder)
        after = json.loads((jd.GOALDIR / (SID + ".json")).read_text())["nodes"][g1]
        self.assertIsNone(after.get("parentId"), "the base rolled out: nothing carried, the holder's field stands (as before the rule)")
        if before is not None:
            self.assertEqual(jd._GOAL_IO.get("carryNoBase", 0) - before.get("carryNoBase", 0), 1, "and the counter says the base was gone")

    def test_an_in_place_editor_that_changes_a_field_is_carried_too(self):
        """The box lab's own shape: the file rewritten in place with rev and seq bumped, a brief changed WITH its family stamped (briefedMt, as
        the lab's driver and every kernel writer of a brief do) and a plain field changed, while a holder's base predates it."""
        self._seed()
        g1 = self._nid(1)
        holder = jd.load_goals(SID)
        path = jd.GOALDIR / (SID + ".json"); st = json.loads(path.read_text())
        st["nodes"][g1]["blockSummary"] = "the editor's long brief"; st["nodes"][g1]["briefedMt"] = 5000; st["nodes"][g1]["parentId"] = "the editor's parent"
        st["seq"] = (st.get("seq") or 0) + 1; st["rev"] = (st.get("rev") or 0) + 1
        path.write_text(json.dumps(st))
        jd.record_verdict(holder, holder["nodes"][g1], "unblocker", "note", T0 + 40, why="the pass ends with a save"); jd.save_goals(SID, holder)
        after = json.loads(path.read_text())["nodes"][g1]
        self.assertEqual((after.get("blockSummary"), after.get("parentId")), ("the editor's long brief", "the editor's parent"), "the in-place edit survives the holder's save: the stamped family through the family merge, the plain field through the carry (before: the holder's copy won on both)")

    def test_rebase_folds_a_duplicate_verdict_instead_of_doubling_it(self):
        # verdict identity is (ev_t, src, kind) - the same triple _replay_overrides dedups on
        self._seed()
        gid = self._nid(1)
        a, b = jd.load_goals(SID), jd.load_goals(SID)
        jd.record_verdict(a, a["nodes"][gid], "nudge", "block", T0 + 100, why="owed")
        jd.record_verdict(b, b["nodes"][gid], "nudge", "block", T0 + 100, why="owed")
        jd.save_goals(SID, a)
        jd.save_goals(SID, b)
        log = jd.load_goals(SID)["nodes"][gid].get("log") or []
        blocks = [e for e in log if e.get("kind") == "block" and int(e.get("ev_t") or 0) == T0 + 100]
        self.assertEqual(len(blocks), 1, "the same verdict from both writers folds to one entry")

    def test_a_second_save_of_the_same_store_still_rebases(self):
        # One holder saving the SAME store twice (the planner saves its store several times per pass;
        # the distiller saves after titling and again after distilling): the first publish popped the
        # base and nothing restored it, so every later save of the object took the unconditional branch
        # and wrote over whatever a concurrent writer published in between (review 2026-09-06).
        self._seed()
        gid = self._nid(1)
        s = jd.load_goals(SID)
        jd.record_verdict(s, s["nodes"][gid], "planner", "done", T0 + 30, why="shipped")
        jd.save_goals(SID, s)                        # our first publish
        other = jd.load_goals(SID)                   # a kernel-side writer, between our two saves
        jd.apply_plan(other, "s2", T0 + 40, [{"do": "mint", "why": "x", "text": "Their new goal"}],
                      jd.open_menu(other))
        jd.save_goals(SID, other)
        s["nodes"][gid]["summary"] = "Shipped the exporter end to end."   # our second change, SAME object
        s["nodes"][gid]["distilledMt"] = T0 + 500
        jd.save_goals(SID, s)                        # must rebase onto their publish, not clobber it
        after = jd.load_goals(SID)
        self.assertIn(self._nid(2), after["nodes"], "the other writer's node survives our second save")
        self.assertEqual(after["nodes"][gid].get("summary"), "Shipped the exporter end to end.",
                         "and our second change landed too")
        self.assertNotIn("_baseRev", json.loads((jd.GOALDIR / (SID + ".json")).read_text()),
                         "the re-stamped base is still never written to disk")

    def test_a_second_uncontended_save_of_the_same_object_does_not_rebase(self):
        # the re-stamp is exact: the base after a publish is the revision that publish wrote, so a second
        # save with nobody else publishing in between finds disk == base and never rebases (a stale
        # re-stamp would rebase every second save; no re-stamp would leave the object base-less)
        self._seed()
        gid = self._nid(1)
        s = jd.load_goals(SID)
        jd.record_verdict(s, s["nodes"][gid], "planner", "done", T0 + 30, why="shipped")
        jd.save_goals(SID, s)                        # our first publish
        r1 = jd._disk_rev(SID)
        s["nodes"][gid]["summary"] = "Shipped the exporter end to end."   # our second change, SAME object
        calls, real = [], jd._rebase_onto_disk

        def spy(fsid, store):
            calls.append(fsid)
            return real(fsid, store)
        jd._rebase_onto_disk = spy
        try:
            jd.save_goals(SID, s)
        finally:
            jd._rebase_onto_disk = real
        self.assertEqual(calls, [], "nobody else published: the base is the revision the first save wrote")
        self.assertEqual(jd._disk_rev(SID), r1 + 1)
        self.assertEqual(s.get("_baseRev"), r1 + 1, "and the object now carries that revision as its base")

    def test_an_uncontended_save_does_not_rebase(self):
        self._seed()
        gid = self._nid(1)
        s = jd.load_goals(SID)
        jd.record_verdict(s, s["nodes"][gid], "planner", "done", T0 + 30, why="shipped")
        jd.save_goals(SID, s)                        # nobody else wrote → straight publish
        self.assertTrue(jd.load_goals(SID)["nodes"][gid].get("nodeComplete"))


class ReadFaultCas(unittest.TestCase):
    """The CAS can never publish over a file it could not READ.

    Before this, every reader in the save path answered a read failure with the ABSENT-file value:
    load_goals returned a fresh store at base 0, _disk_rev read 0, _matches_disk read "no match" and
    _rebase_onto_disk had "nothing to rebase onto". So on an EIO, an EACCES or a corrupt file, save_goals
    found base 0 == disk 0 and published the empty store over the user's goals. Now a read fault raises
    from every one of those readers and the file on disk is left byte for byte as it was.

    Mints goals, so it uses a PRIVATE synthetic sid (CLAUDE.md, 2026-08-24) and cleans that sid's override
    journal in tearDown."""
    FSID = "7b2c3d4e-5f60-4182-93a4-b5c6d7e8f901"

    def setUp(self):
        self._saved = jd.STATE
        self.td = tempfile.TemporaryDirectory()
        jd._rebind_state(Path(self.td.name))

    def tearDown(self):
        (jd._overrides_dir() / (self.FSID + ".jsonl")).unlink(missing_ok=True)
        jd._rebind_state(self._saved)
        (jd._overrides_dir() / (self.FSID + ".jsonl")).unlink(missing_ok=True)
        self.td.cleanup()

    def _file(self):
        return jd.GOALDIR / (self.FSID + ".json")

    def _gid(self):
        return "%s:g1" % self.FSID

    def _seed(self):
        s = {"rompUuid": self.FSID, "seq": 0, "placementsV": jd.PLACEMENTS_V, "nodes": {},
             "placements": {}, "status": {}}
        jd.apply_plan(s, "s1", T0, [{"do": "mint", "why": "x", "text": "A goal"}], [])
        jd.rollup_status(s, session_closed=False)
        jd.save_goals(self.FSID, s)

    @contextlib.contextmanager
    def _eio_on_the_store(self):
        """Every reader of THIS store's path raises EIO; every other read is untouched. Path.read_text is the
        load path's reader; the save path's memoized readers (_disk_entry, _disk_rev) open a descriptor of
        their own and read from it (_disk_read), so os.open faults for the path as well."""
        target, orig_read_text, orig_open = self._file(), Path.read_text, os.open

        def faulting(path, *a, **kw):
            if path == target:
                raise OSError(errno.EIO, "Input/output error", str(path))
            return orig_read_text(path, *a, **kw)

        def faulting_open(path, *a, **kw):
            if os.fspath(path) == str(target):
                raise OSError(errno.EIO, "Input/output error", str(target))
            return orig_open(path, *a, **kw)
        with mock.patch.object(Path, "read_text", faulting), mock.patch.object(os, "open", faulting_open):
            yield

    def test_a_read_fault_raises_from_load_instead_of_reading_as_an_empty_store(self):
        self._seed()
        with self._eio_on_the_store():
            with self.assertRaises(OSError) as cm:
                jd.load_goals(self.FSID)
        self.assertEqual(cm.exception.errno, errno.EIO, "the fault itself, not a fresh store")
        self.assertEqual(len(self._sidecars()), 0, "a FAULT is not corruption: nothing is moved aside")

    def test_a_read_fault_at_save_publishes_nothing_and_the_file_is_untouched(self):
        self._seed()
        before = self._file().read_bytes()
        s = jd.load_goals(self.FSID)                 # a snapshot taken while the disk was healthy...
        jd.record_verdict(s, s["nodes"][self._gid()], "planner", "done", T0 + 30, why="shipped")
        with self._eio_on_the_store():               # ...then the store becomes unreadable
            with self.assertRaises(OSError):
                jd.save_goals(self.FSID, s)
        self.assertEqual(self._file().read_bytes(), before,
                         "the publish did not go ahead over bytes it failed to compare against")

    def test_a_raise_inside_the_cas_loop_keeps_the_object_cas_protected(self):
        # the window save_goals' docstring left documented on 2026-09-06 (the base popped before the CAS loop,
        # re-stamped only after the rename, so a raise between the two left the object base-less and its next
        # save unconditional) is closed (review find, 2026-09-08): when the publish did not happen the object
        # keeps the base it was loaded at, so the holder's retry is CAS-protected too. The read-fault cases
        # above raise inside _matches_disk, BEFORE the pop; here the revision read inside the loop fails, then
        # the rename itself, and then a retry meets a concurrent publish
        self._seed()
        before = self._file().read_bytes()
        s = jd.load_goals(self.FSID)
        base = s["_baseRev"]
        jd.record_verdict(s, s["nodes"][self._gid()], "planner", "done", T0 + 30, why="shipped")
        real = jd._disk_rev_ident                    # the loop's revision read (the revision and the file's identity since 2026-09-23)

        def faulting(fsid):
            raise OSError(errno.EIO, "Input/output error", fsid)
        jd._disk_rev_ident = faulting
        try:
            with self.assertRaises(OSError):
                jd.save_goals(self.FSID, s)
        finally:
            jd._disk_rev_ident = real
        self.assertEqual(s.get("_baseRev"), base, "a raise inside the loop: the object keeps the base it was loaded at")
        self.assertEqual(self._file().read_bytes(), before, "nothing was published")

        def no_rename(path, target):
            raise OSError(errno.EIO, "Input/output error", str(target))
        with mock.patch.object(Path, "rename", no_rename):
            with self.assertRaises(OSError):
                jd.save_goals(self.FSID, s)
        self.assertEqual(s.get("_baseRev"), base, "a raise at the rename: the base is restored too")
        self.assertEqual(self._file().read_bytes(), before, "nothing was published")
        other = jd.load_goals(self.FSID)             # a concurrent writer publishes between the failure and the retry
        jd.apply_plan(other, "s2", T0 + 40, [{"do": "mint", "why": "x", "text": "Their new goal"}],
                      jd.open_menu(other))
        jd.save_goals(self.FSID, other)
        jd.save_goals(self.FSID, s)                  # the retry: CAS-protected, so it rebases instead of stomping
        after = jd.load_goals(self.FSID)
        self.assertIn("%s:g2" % self.FSID, after["nodes"], "the other writer's node survives the retried save")
        kinds = {(e.get("src"), e.get("kind")) for e in after["nodes"][self._gid()].get("log") or []}
        self.assertIn(("planner", "done"), kinds, "and our verdict landed")
        self.assertEqual(s.get("_baseRev"), after["rev"], "the retry re-stamped the written revision as the base")

    def test_a_file_corrupted_after_load_is_not_overwritten_by_the_save(self):
        """The save path never quarantines (that is load's job, after the evidence is preserved): a store
        that turned unparseable underneath a held snapshot makes the save raise, and the bytes stay put for
        the next load to move aside."""
        self._seed()
        s = jd.load_goals(self.FSID)
        jd.record_verdict(s, s["nodes"][self._gid()], "planner", "done", T0 + 30, why="shipped")
        self._file().write_text("{not json")
        with self.assertRaises(ValueError):
            jd.save_goals(self.FSID, s)
        self.assertEqual(self._file().read_text(), "{not json", "the save wrote nothing")
        self.assertEqual(len(self._sidecars()), 0, "and moved nothing: the save path only reads")
        fresh = jd.load_goals(self.FSID)             # the next load is the one that quarantines
        self.assertEqual(len(self._sidecars()), 1)
        jd.save_goals(self.FSID, fresh)
        self.assertEqual(json.loads(self._file().read_text())["rompUuid"], self.FSID)

    def test_disk_rev_reads_zero_only_for_an_absent_file(self):
        self.assertEqual(jd._disk_rev(self.FSID), 0, "absent → 0, a create")
        self._seed()
        self.assertGreater(jd._disk_rev(self.FSID), 0)
        with self._eio_on_the_store():
            with self.assertRaises(OSError):
                jd._disk_rev(self.FSID)
        self._file().write_text("{not json")
        with self.assertRaises(ValueError):
            jd._disk_rev(self.FSID)

    def test_a_fresh_store_is_not_published_over_a_non_object_file(self):
        """A top-level JSON value that is not an object is neither a store nor an absent file: a fresh store
        (base 0, minted while the path was empty) is not published over it, and a gesture's boundary answers
        the fault instead of None."""
        s = jd.load_goals(self.FSID)                 # absent: a fresh store at base 0
        jd.apply_plan(s, "s1", T0, [{"do": "mint", "why": "x", "text": "A goal"}], [])
        jd.GOALDIR.mkdir(parents=True, exist_ok=True)
        self._file().write_bytes(b"[]")              # meanwhile the path holds a JSON array
        with self.assertRaises(ValueError):
            jd.save_goals(self.FSID, s)
        self.assertEqual(self._file().read_bytes(), b"[]", "nothing was published over bytes that are not a store")
        self.assertIsInstance(jd.save_goals_or_fault(self.FSID, s), ValueError,
                              "the gesture boundary answers the fault, not None")
        self.assertEqual(self._file().read_bytes(), b"[]")

    def test_matches_disk_and_rebase_raise_on_a_fault_or_a_corrupt_file(self):
        """Each reader in the save path on its own: a version of either that swallowed the read and answered
        'no match' / 'nothing to rebase onto' would let save_goals go ahead and passed every other test."""
        self._seed()
        s = jd.load_goals(self.FSID)
        self.assertTrue(jd._matches_disk(self.FSID, s), "premise: a healthy read matches")
        with self._eio_on_the_store():
            self.assertRaises(OSError, jd._matches_disk, self.FSID, s)
            self.assertRaises(OSError, jd._rebase_onto_disk, self.FSID, s)
        self._file().write_text("{not json")
        self.assertRaises(ValueError, jd._matches_disk, self.FSID, s)
        self.assertRaises(ValueError, jd._rebase_onto_disk, self.FSID, s)
        self.assertEqual(self._file().read_text(), "{not json", "neither reader touched the file")

    def _sidecars(self):
        return sorted(jd.GOALDIR.glob(self.FSID + ".json.corrupt-*"))


if __name__ == "__main__":
    unittest.main()
