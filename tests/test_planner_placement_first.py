#!/usr/bin/env python3
"""T377 (2026-09-12): the planner decides a unit's placement before it reads the unit's text, and its consumer trusts the same
verdict. Two review findings pinned here: the placement verdict's one volatile input, the episode floor, is taken ONCE per pass
and handed to both the planner and its consumer (a /clear landing mid-pass raised the floor between them, and a unit the
planner had yielded as placed reached the model with no text); and the placement lookup is an index built once per planner
call, not a walk of every recorded key per segment (the nudge gate's derivation grew twelve-fold). Synthetic transcripts."""
import json
import os
import tempfile
import unittest
from pathlib import Path
import sys
HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
from test_judge_apierror_no_fabricated_done import jd, uline, aline, NOW, iso   # noqa: E402  the consumer harness
SID = "7a377000-2222-4333-8444-000000000377"   # this module's PRIVATE synthetic sid (CLAUDE.md's goal-store rule: load_goals replays the
#                                                 per-sid override journal and node ids collide across modules under the shared placeholder)


class _PrivateSid(unittest.TestCase):
    def tearDown(self):
        try:
            (jd._overrides_dir() / (SID + ".jsonl")).unlink()          # this sid's override journal, never left for another module
        except FileNotFoundError:
            pass


def _records(n):
    recs, prev, t = [], None, NOW - 4000
    for i in range(n):
        u, a = "u%03d" % i, "a%03d" % i
        recs.append(uline(t, "please handle item number %d for the notes api" % i, u, prev))
        recs.append(aline(t + 10, "handled item %d" % i, a, u))
        prev, t = a, t + 60
    return recs


class FloorTakenOncePerPass(_PrivateSid):
    def test_a_floor_rising_after_the_planner_returns_never_sends_a_unit_without_text_to_the_model(self):
        calls = []
        with tempfile.TemporaryDirectory() as td:
            td = Path(td); tpath = td / (SID + ".jsonl")
            tpath.write_text("\n".join(json.dumps(r) for r in _records(2)) + "\n")
            saved = (jd.GOALDIR, jd.PCACHE, jd.plan_llm, jd.opener_llm, jd._group_store, jd.episode_floor)
            jd.GOALDIR, jd.PCACHE = td / "goals", td / "pcache"
            def fake(text, *a, **k):
                calls.append(text); return '{"ops":[]}'
            jd.plan_llm = jd.opener_llm = fake
            jd._group_store = lambda *a, **k: None
            try:
                jd._PARSE_CACHE.clear(); jd._CHAIN_MEMO.clear()
                session = jd.parsed_session(SID, [str(tpath)], NOW)
                units = jd.plan_units(session, {"placements": {}, "nodes": {}, "seq": 0})
                self.assertTrue(units)
                store = jd.load_goals(SID)
                for u in units:                                        # every unit recorded under a DRIFTED key (the same text hash,
                    key = jd._unit_key(u[0], u[1])                     #  an earlier t): a fuzzy hit while the episode floor is low
                    parts = key.split(":"); parts[-2] = str(float(parts[-2]) - 100)
                    store["placements"][":".join(parts)] = None
                store["placementsV"] = jd.PLACEMENTS_V                 # no migration pass: the planner is called once
                jd.save_goals(SID, store)
                last_t = max(u[2] for u in units)
                state = {"after": False}
                real_plan_units = jd.plan_units
                def planned(*a, **k):                                  # the floor rises the moment the planner returns: the /clear
                    out = real_plan_units(*a, **k); state["after"] = True; return out   #  landing mid-pass
                jd.plan_units = planned
                jd.episode_floor = lambda sid: (last_t - 50) if state["after"] else 0   # between the drifted key's t and the unit's
                jd._plan_session(SID, str(tpath), NOW)                 #  own: not retired, but its recorded twin no longer dedups it
            finally:
                jd.plan_units = real_plan_units
                (jd.GOALDIR, jd.PCACHE, jd.plan_llm, jd.opener_llm, jd._group_store, jd.episode_floor) = saved
        self.assertEqual(calls, [], "under the pass's one floor the drifted twins still dedup every unit: nothing planned, no None "
                                    "to the model (the base sent [None])")

    def test_a_unit_yielded_as_placed_but_planned_reads_its_text_and_quote_lazily(self):
        """The backstop: when the consumer's own verdict disagrees with the planner's (here forced), the unit is planned with its
        text read then, and the node it mints carries the trigger's verbatim quote (review, low 4)."""
        calls = []
        with tempfile.TemporaryDirectory() as td:
            td = Path(td); tpath = td / (SID + ".jsonl")
            tpath.write_text("\n".join(json.dumps(r) for r in _records(1)) + "\n")
            saved = (jd.GOALDIR, jd.PCACHE, jd.plan_llm, jd.opener_llm, jd._group_store, jd._placed_key)
            jd.GOALDIR, jd.PCACHE = td / "goals", td / "pcache"
            def fake(text, *a, **k):
                calls.append(text); return '{"ops":[{"why":"the ask","do":"mint","text":"Handle item zero"}]}'
            jd.plan_llm = jd.opener_llm = fake
            jd._group_store = lambda *a, **k: None
            try:
                jd._PARSE_CACHE.clear(); jd._CHAIN_MEMO.clear()
                session = jd.parsed_session(SID, [str(tpath)], NOW)
                units = jd.plan_units(session, {"placements": {}, "nodes": {}, "seq": 0})
                work = [u for u in units if u[1] == "work"]; self.assertEqual(len(work), 1)
                store = jd.load_goals(SID)
                store["placements"][jd._unit_key(work[0][0], "work")] = None      # placed for the planner's read...
                store["placementsV"] = jd.PLACEMENTS_V
                jd.save_goals(SID, store)
                real_placed = jd._placed_key
                state = {"after": False}
                real_plan_units = jd.plan_units
                def planned(*a, **k):
                    out = real_plan_units(*a, **k); state["after"] = True; return out
                jd.plan_units = planned
                jd._placed_key = lambda placements, key, live=None, **kw: (False if state["after"] else real_placed(placements, key, live, **kw))
                jd._plan_session(SID, str(tpath), NOW)                 # ...and unplaced for the consumer's: the backstop reads
                store = jd.load_goals(SID)                             # read while the goal directory is still the test's
            finally:
                jd.plan_units = real_plan_units
                (jd.GOALDIR, jd.PCACHE, jd.plan_llm, jd.opener_llm, jd._group_store, jd._placed_key) = saved
        self.assertEqual(len(calls), 1); self.assertTrue(isinstance(calls[0], str) and "item number 0" in calls[0], "%r" % calls)
        quotes = [n.get("quote") for n in store["nodes"].values() if isinstance(n, dict)]
        self.assertTrue(quotes and all(q for q in quotes), "the minted node carries the trigger's verbatim quote: %r" % quotes)


class HousekeepingNoteAlone(_PrivateSid):
    def test_a_note_segment_with_an_empty_work_text_and_a_placed_prompt_yields_no_work_unit(self):
        """Review, low 3: a kernel-notice or clear-wrap segment whose prompt key is placed and whose work text is empty yielded a
        WORK unit carrying the housekeeping note alone, unplaced and plannable. An empty work text drops the unit, note or not."""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td); tpath = td / (SID + ".jsonl")
            tpath.write_text("\n".join(json.dumps(r) for r in _records(1)) + "\n")
            jd._PARSE_CACHE.clear(); jd._CHAIN_MEMO.clear()
            session = jd.parsed_session(SID, [str(tpath)], NOW)
            seg_id = jd.plan_units(session, {"placements": {}, "nodes": {}, "seq": 0})[0][0]
            store = {"placements": {jd._unit_key(seg_id, "prompt"): None}, "nodes": {}, "seq": 0}
            saved = (jd._seam_text, jd._work_note)
            jd._seam_text = lambda seg: ""                             # the segment's own text empty...
            jd._work_note = lambda seg: "Note: this stretch was triggered by an automated romp notice.\n\n"   # ...under a note
            try:
                units = jd.plan_units(session, store)
            finally:
                jd._seam_text, jd._work_note = saved
        self.assertEqual([u for u in units if u[1] == "work"], [], "no work unit of a note alone: %r" % units)

    def test_the_lazy_text_for_a_work_unit_is_assembled_once(self):
        """Review, low 5: unit_text_for assembled the work text up to three times."""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td); tpath = td / (SID + ".jsonl")
            tpath.write_text("\n".join(json.dumps(r) for r in _records(1)) + "\n")
            jd._PARSE_CACHE.clear(); jd._CHAIN_MEMO.clear()
            session = jd.parsed_session(SID, [str(tpath)], NOW)
            seg = jd._segs(session["turns"][0], None)[0]
            count = [0]; real = jd._seam_text
            def counting(s):
                count[0] += 1; return real(s)
            jd._seam_text = counting
            try:
                text = jd.unit_text_for(seg, "work")
            finally:
                jd._seam_text = real
        self.assertTrue(text); self.assertEqual(count[0], 1, "assembled once: %d" % count[0])


class PlacementLookupIsAnIndex(_PrivateSid):
    def test_the_lookup_cost_is_a_build_once_index_not_a_walk_per_segment(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td); tpath = td / (SID + ".jsonl")
            n = 60
            tpath.write_text("\n".join(json.dumps(r) for r in _records(n)) + "\n")
            jd._PARSE_CACHE.clear(); jd._CHAIN_MEMO.clear()
            session = jd.parsed_session(SID, [str(tpath)], NOW)
            placements = {"%s:%d:%08x" % (SID, NOW - 90000 + i, i): None for i in range(2300)}   # 2,300 recorded keys, none ours
            store = {"placements": placements, "nodes": {}, "seq": 0}
            count = [0]; real = jd._seg_key
            def counting(k):
                count[0] += 1; return real(k)
            jd._seg_key = counting
            try:
                units = jd.plan_units(session, store)
            finally:
                jd._seg_key = real
            self.assertGreaterEqual(len(units), n)
            self.assertLessEqual(count[0], len(placements) + 12 * n,
                                 "one normalization per recorded key and a handful per segment, not a walk per segment: %d" % count[0])


if __name__ == "__main__":
    unittest.main()
