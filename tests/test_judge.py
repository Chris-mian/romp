#!/usr/bin/env python3
"""Tests for bin/romp-judge (summarizer layer, increment 1: the captioner + engine).

The model call (caption_llm) is stubbed; everything else — unit selection, the
single-segment-turn caption reuse, the unit-text builder, the caption store + dedup,
and the engine pass (discovery / budget / fairness / write) — is tested deterministically.
All fixtures are SYNTHETIC (invented text, placeholder UUIDs, hostname TESTHOST).
"""
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
em = SourceFileLoader("romp_event_model", os.path.join(BIN, "romp-event-model")).load_module()
jd = SourceFileLoader("romp_judge", os.path.join(BIN, "romp-judge")).load_module()

NOW = 1781100000
SID = "11111111-2222-3333-4444-555555555555"
T0 = NOW - 3600


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def uline(t, text, uuid, parent=None, ps="typed"):
    r = {"type": "user", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent,
         "message": {"role": "user", "content": text}}
    if ps is not None:
        r["promptSource"] = ps
    return r


def aline(t, text, uuid, parent=None, tools=(), stop="end_turn"):
    content = [{"type": "text", "text": text}] if text else []
    for i, n in enumerate(tools):
        content.append({"type": "tool_use", "id": "tu_%s_%d" % (uuid, i), "name": n, "input": {}})
    return {"type": "assistant", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent,
            "message": {"role": "assistant", "content": content, "stop_reason": stop}}


def qop(t, op, content=None):
    return {"type": "queue-operation", "timestamp": iso(t), "operation": op, "content": content}


def attline(t, prompt, uuid, parent=None):
    return {"type": "attachment", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent,
            "attachment": {"type": "queued_command", "prompt": prompt}}


def build_session(records, now=NOW, rompuuid=SID):
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / (rompuuid + ".jsonl")
        p.write_text("\n".join(json.dumps(r) for r in records) + "\n")
        return em.parse_session(str(p), rompuuid=rompuuid, candidate_files=[str(p)], now=now)


# ───────────────────────── unit selection ─────────────────────────
class TaskSelection(unittest.TestCase):
    def test_single_segment_turn_mirrors_to_turn(self):
        """A single-segment ended turn = one model call writing BOTH a segment- and a
        turn-grain record (reuse), never a second call."""
        s = build_session([
            uline(T0, "fix the flicker", "u1", ps="typed"),
            aline(T0 + 30, "Fixed the flicker.", "a1", "u1", stop="end_turn"),
        ])
        tasks = jd._ready_tasks(s)
        self.assertEqual(len(tasks), 1, "single-segment turn = one caption call")
        grains = sorted(w["grain"] for w in tasks[0]["writes"])
        self.assertEqual(grains, ["segment", "turn"], "the one call writes both grains")

    def test_multi_segment_turn_gets_its_own_call(self):
        """An absorbed multi-input turn: one call per segment PLUS a distinct turn call."""
        s = build_session([
            uline(T0, "refactor the ledger", "u1", ps="typed"),
            aline(T0 + 20, "Reading ledger.", "a1", "u1", tools=("Read",), stop="tool_use"),
            qop(T0 + 40, "enqueue", "also rename the digest"),
            qop(T0 + 60, "remove"),
            attline(T0 + 60, "also rename the digest", "att1", "a1"),
            aline(T0 + 90, "Renamed the digest too.", "a2", "att1", stop="end_turn"),
        ])
        tasks = jd._ready_tasks(s)
        grains = [tuple(sorted(w["grain"] for w in t["writes"])) for t in tasks]
        self.assertEqual(grains.count(("segment",)), 2, "two segment-only calls")
        self.assertEqual(grains.count(("turn",)), 1, "one distinct turn call (>=2 segments)")
        self.assertNotIn(("segment", "turn"), grains, "no mirror when the turn has >1 segment")

    def test_open_final_turn_is_withheld(self):
        """The last segment+turn of an OPEN final turn (not ended, no idle) are not ready."""
        s = build_session([
            uline(T0, "first ask", "u1", ps="typed"),
            aline(T0 + 20, "first reply", "a1", "u1", stop="end_turn"),
            uline(T0 + 100, "second ask, still working", "u2", "a1", ps="typed"),
            aline(T0 + 120, "calling a tool", "a2", "u2", tools=("Bash",), stop="tool_use"),
        ])
        tasks = jd._ready_tasks(s)
        # turn 1 (ended, single segment) -> 1 task; turn 2 (open) -> withheld entirely
        self.assertEqual(len(tasks), 1)
        self.assertTrue(any(w["grain"] == "turn" for w in tasks[0]["writes"]))

    def test_idle_terminated_final_turn_is_ready(self):
        """An idle atom terminates the final turn, so its unit becomes ready."""
        states = [{"t": T0 + 40, "state": "working"}, {"t": T0 + 60, "state": "idle"},
                  {"t": T0 + 4000, "state": "working"}]
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / (SID + ".jsonl")
            p.write_text("\n".join(json.dumps(r) for r in [
                uline(T0, "investigate crash", "u1", ps="typed"),
                aline(T0 + 30, "Reproduced it.", "a1", "u1", tools=("Bash",), stop="tool_use"),
            ]) + "\n")
            s = em.parse_session(str(p), rompuuid=SID, candidate_files=[str(p)],
                                 states=states, now=T0 + 5000)
        tasks = jd._ready_tasks(s)
        self.assertTrue(tasks, "an idle-terminated turn is ready despite stop_reason=tool_use")


# ───────────────────────── unit text ─────────────────────────
class UnitText(unittest.TestCase):
    def test_builds_user_assistant_tools(self):
        s = build_session([
            uline(T0, "add a recency tint", "u1", ps="typed"),
            aline(T0 + 30, "Tinted cards by recency.", "a1", "u1", tools=("Read", "Edit"), stop="end_turn"),
        ])
        atoms = s["turns"][0]["atoms"]
        txt = jd._unit_text(atoms)
        self.assertIn("USER ASKED: add a recency tint", txt)
        self.assertIn("ASSISTANT SAID: Tinted cards by recency.", txt)
        self.assertIn("TOOLS USED: Read, Edit", txt)

    def test_tool_result_atoms_are_not_user_input(self):
        # a tool_result-only user atom (author None) must not become "USER ASKED"
        s = build_session([
            uline(T0, "do the thing", "u1", ps="typed"),
            aline(T0 + 10, "calling tool", "a1", "u1", tools=("Bash",), stop="tool_use"),
            {"type": "user", "timestamp": iso(T0 + 15), "uuid": "r1", "parentUuid": "a1",
             "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tu_a1_0",
                                                       "content": "output"}]}},
            aline(T0 + 20, "Done.", "a2", "r1", stop="end_turn"),
        ])
        txt = jd._unit_text(s["turns"][0]["atoms"])
        self.assertEqual(txt.count("USER ASKED:"), 1, "only the real prompt is user input")
        self.assertIn("do the thing", txt)


# ───────────────────────── caption cleaning ─────────────────────────
class CleanCaption(unittest.TestCase):
    def test_strips_and_caps(self):
        self.assertEqual(jd._clean_caption("  Fixed the auth null check.  "), "Fixed the auth null check")

    def test_rejects_questions_and_chat(self):
        self.assertEqual(jd._clean_caption("Do you want me to continue?"), "")
        self.assertEqual(jd._clean_caption("How can I help?"), "")
        self.assertEqual(jd._clean_caption("Let me know if you want more"), "")

    def test_rejects_degenerate(self):
        self.assertEqual(jd._clean_caption("..."), "")
        self.assertEqual(jd._clean_caption(""), "")

    def test_strips_tool_name_leak(self):
        # an agent-tool name leak is stripped; the accomplishment is kept
        self.assertEqual(jd._clean_caption("Explained the edit to a reviewer via reply tool"),
                         "Explained the edit to a reviewer")
        self.assertEqual(jd._clean_caption("Fixed the null check using the Edit tool"), "Fixed the null check")
        # legit work that isn't an agent-tool-usage clause is untouched
        self.assertEqual(jd._clean_caption("Built a small CLI tool"), "Built a small CLI tool")

    def test_rejects_meta_refusals(self):
        # the model narrating that it can't caption is a failed capture, not a caption
        self.assertEqual(jd._clean_caption("Nothing to summarize"), "")
        self.assertEqual(jd._clean_caption("Insufficient context to determine what happened"), "")
        self.assertEqual(jd._clean_caption("Unable to summarize the segment"), "")
        # but a real caption that merely contains a normal word is kept
        self.assertEqual(jd._clean_caption("Summarized the release notes"), "Summarized the release notes")


# ───────────────────────── caption store ─────────────────────────
class CaptionStore(unittest.TestCase):
    def test_append_and_dedup(self):
        with tempfile.TemporaryDirectory() as td:
            old = jd.CAPDIR
            jd.CAPDIR = Path(td)
            try:
                jd.append_caption(SID, "id1", "segment", T0, "Fixed it")
                jd.append_caption(SID, "id2", "turn", T0, "Shipped it")
                self.assertEqual(jd.captioned_ids(SID), {"id1", "id2"})
            finally:
                jd.CAPDIR = old


# ───────────────────────── the engine pass (fake fleet, stubbed model) ─────────────────────────
class EnginePass(unittest.TestCase):
    def _fleet(self, td, records):
        """Lay out a synthetic fleet: names/<sid> -> cdir, and the transcript under the munged
        project dir. Returns (state_dir, restore_fn) with judge globals pointed at it."""
        td = Path(td)
        cdir = td / "launchdir"
        cdir.mkdir()
        proj = td / "projects"
        munged = jd.re.sub(r"[/.]", "-", os.path.realpath(str(cdir)))
        pdir = proj / munged
        pdir.mkdir(parents=True)
        self._tpath = pdir / (SID + ".jsonl")
        self._tpath.write_text("\n".join(json.dumps(r) for r in records) + "\n")
        names = td / "names"
        names.mkdir()
        (names / SID).write_text("testsess\t%s\t#abcdef\n" % str(cdir))
        saved = (jd.NAMES, jd.PROJECTS, jd.CAPDIR, jd.ARCHDIR, jd.PCACHE, jd.caption_llm, jd.archive_llm)
        jd.NAMES, jd.PROJECTS = names, proj
        jd.CAPDIR, jd.ARCHDIR, jd.PCACHE = td / "captions", td / "archive", td / "pcache"
        jd.caption_llm = lambda text: "stub caption"
        jd.archive_llm = lambda log: {"headline": "stub headline", "abstract": "stub abstract"}

        def restore():
            (jd.NAMES, jd.PROJECTS, jd.CAPDIR, jd.ARCHDIR, jd.PCACHE, jd.caption_llm, jd.archive_llm) = saved
        return restore

    def test_pass_writes_both_grains_then_dedups(self):
        records = [uline(T0, "fix the flicker", "u1", ps="typed"),
                   aline(T0 + 30, "Fixed the flicker.", "a1", "u1", stop="end_turn")]
        with tempfile.TemporaryDirectory() as td:
            restore = self._fleet(td, records)
            try:
                # recent activity: set now near the transcript's time so the WINDOW includes it
                now = T0 + 120
                r1 = jd.run_once(now=now)
                recs = [json.loads(l) for l in (jd.CAPDIR / (SID + ".jsonl")).read_text().splitlines()]
                grains = sorted(r["grain"] for r in recs)
                self.assertEqual(grains, ["segment", "turn"], "single-segment turn writes both grains from one call")
                self.assertTrue(all(r["caption"] == "stub caption" for r in recs))
                self.assertEqual(r1["captions"], 2, "two records from one model call")
                # the archiver ran after captioning and wrote one session archive from the turn caption
                self.assertEqual(r1["archives"], 1)
                arch = json.loads((jd.ARCHDIR / (SID + ".json")).read_text())
                self.assertEqual(arch["headline"], "stub headline")
                self.assertEqual(arch["turns"], 1, "archive records the turn-caption count it was built from")
                # second pass: captions deduped AND the archive is unchanged (turn count same) -> no rework
                r2 = jd.run_once(now=now)
                self.assertEqual(r2["captions"], 0, "idempotent: a captioned unit is never re-captioned")
                self.assertEqual(r2["archives"], 0, "archive not rebuilt when the turn-caption count is unchanged")
            finally:
                restore()

    def test_fairness_cap_limits_per_session(self):
        # a session with several ended turns; fairness=2 caps calls from it this pass
        records = []
        prev = None
        for i in range(5):
            t = T0 + i * 200
            u = "u%d" % i
            records.append(uline(t, "ask number %d" % i, u, parent=prev, ps="typed"))
            a = "a%d" % i
            records.append(aline(t + 30, "did number %d" % i, a, u, stop="end_turn"))
            prev = a
        with tempfile.TemporaryDirectory() as td:
            restore = self._fleet(td, records)
            try:
                now = T0 + 5 * 200 + 120
                jd.run_once(now=now, fairness=2, budget=100)
                recs = [json.loads(l) for l in (jd.CAPDIR / (SID + ".jsonl")).read_text().splitlines()]
                # fairness caps CALLS at 2; each single-segment turn call writes 2 records
                calls = len({r["caption"] and r["id"].rsplit(":", 1)[0] for r in recs})  # distinct segment t's
                self.assertLessEqual(len(recs), 4, "fairness=2 -> at most 2 calls -> <=4 records")
                self.assertGreater(len(recs), 0)
            finally:
                restore()

    def test_archive_refreshes_when_session_gains_a_turn(self):
        """Event-based refresh: the archive rebuilds when the turn-caption count grows, never on a timer."""
        with tempfile.TemporaryDirectory() as td:
            restore = self._fleet(td, [uline(T0, "first ask", "u1", ps="typed"),
                                       aline(T0 + 30, "first reply", "a1", "u1", stop="end_turn")])
            try:
                now = T0 + 5000
                jd.run_once(now=now)
                self.assertEqual(json.loads((jd.ARCHDIR / (SID + ".json")).read_text())["turns"], 1)
                # the session gains a second ended turn (rewrite the transcript; mtime/size change
                # invalidates the units cache, so the new turn is captioned, then re-archived)
                self._tpath.write_text("\n".join(json.dumps(r) for r in [
                    uline(T0, "first ask", "u1", ps="typed"),
                    aline(T0 + 30, "first reply", "a1", "u1", stop="end_turn"),
                    uline(T0 + 100, "second ask", "u2", "a1", ps="typed"),
                    aline(T0 + 130, "second reply", "a2", "u2", stop="end_turn")]) + "\n")
                jd.run_once(now=now)
                self.assertEqual(json.loads((jd.ARCHDIR / (SID + ".json")).read_text())["turns"], 2,
                                 "archive refreshes when the session gains a turn")
            finally:
                restore()


class ArchiveParse(unittest.TestCase):
    def test_parses_headline_and_abstract(self):
        out = "HEADLINE: Rebuilding the romp event model\nABSTRACT: Built the parser and its tests. Validated it against the corpus."
        rec = jd._parse_archive(out)
        self.assertEqual(rec["headline"], "Rebuilding the romp event model")
        self.assertTrue(rec["abstract"].startswith("Built the parser"))
        self.assertIn("corpus", rec["abstract"])

    def test_multi_line_abstract_is_joined(self):
        out = "HEADLINE: Tuning the captioner\nABSTRACT: Pulled the word target down.\nKilled the comma-splice tail."
        rec = jd._parse_archive(out)
        self.assertIn("Pulled the word target down. Killed the comma-splice tail.", rec["abstract"])

    def test_missing_field_is_failed_capture(self):
        self.assertIsNone(jd._parse_archive("HEADLINE: only a headline, no abstract"))
        self.assertIsNone(jd._parse_archive("just some prose with no labels"))
        self.assertIsNone(jd._parse_archive(""))


class PlanParse(unittest.TestCase):
    def test_mint_sub_amend(self):
        self.assertEqual(jd._parse_goal_edit("MINT :: Rebuild the parser :: DONE none :: BLOCK no", 3)["op"], "MINT")
        e = jd._parse_goal_edit("SUB 2 :: added a test :: DONE 2 :: BLOCK yes", 3)
        self.assertEqual((e["op"], e["n"], e["done"], e["block"]), ("SUB", 2, 2, True))
        self.assertEqual(jd._parse_goal_edit("AMEND 1 :: new goal text :: DONE none :: BLOCK no", 3)["op"], "AMEND")

    def test_out_of_range_ref_falls_back_to_mint(self):
        e = jd._parse_goal_edit("SUB 9 :: orphan step :: DONE none :: BLOCK no", 3)  # only 3 open
        self.assertEqual(e["op"], "MINT", "an invalid ref must still place the segment, never orphan")

    def test_bad_done_dropped_and_garbage_none(self):
        self.assertIsNone(jd._parse_goal_edit("SUB 1 :: step :: DONE 9 :: BLOCK no", 3)["done"])
        self.assertIsNone(jd._parse_goal_edit("i cannot help with that", 3))


def _store():
    return {"rompUuid": SID, "seq": 0, "nodes": {}, "placements": {}, "status": {}}


class PlanApply(unittest.TestCase):
    def test_mint_then_sub_under_it(self):
        s = _store()
        jd.apply_goal_edit(s, "seg1", T0, {"op": "MINT", "n": None, "text": "Goal A", "done": None, "block": False}, [])
        jd.apply_goal_edit(s, "seg2", T0 + 10, {"op": "SUB", "n": 1, "text": "step 1", "done": None, "block": False},
                           jd.open_menu(s))
        sub = [n for n in s["nodes"].values() if n["parentId"] is not None]
        self.assertEqual(len(sub), 1)
        self.assertEqual(s["placements"]["seg2"], sub[0]["id"])
        self.assertEqual(s["nodes"][sub[0]["parentId"]]["text"], "Goal A", "sub files under the minted goal")

    def test_done_marks_complete_and_clears_block(self):
        s = _store()
        jd.apply_goal_edit(s, "seg1", T0, {"op": "MINT", "n": None, "text": "G", "done": None, "block": True}, [])
        nid = s["placements"]["seg1"]
        self.assertTrue(s["nodes"][nid]["blocked"])
        jd.apply_goal_edit(s, "seg2", T0 + 10, {"op": "AMEND", "n": 1, "text": "G", "done": 1, "block": False},
                           jd.open_menu(s))
        self.assertTrue(s["nodes"][nid]["nodeComplete"])
        self.assertFalse(s["nodes"][nid]["blocked"], "completing a node clears its soft block")


class PlanRollup(unittest.TestCase):
    def _mint(self, s, seg, t, text, done=None, block=False):
        jd.apply_goal_edit(s, seg, t, {"op": "MINT", "n": None, "text": text, "done": done, "block": block},
                           jd.open_menu(s))

    def test_nonfocus_complete_goal_completes_focus_held_open(self):
        s = _store()
        self._mint(s, "s1", T0, "G1")
        jd.apply_goal_edit(s, "s2", T0 + 10, {"op": "AMEND", "n": 1, "text": "G1", "done": 1, "block": False},
                           jd.open_menu(s))                       # complete G1
        self._mint(s, "s3", T0 + 20, "G2")                       # G2 is now the active focus
        g1, g2 = s["placements"]["s1"], s["placements"]["s3"]
        jd.rollup_status(s, session_closed=False)
        self.assertEqual(s["status"][g1], "completed", "complete AND no longer the focus -> completed")
        self.assertEqual(s["status"][g2], "working")

    def test_focus_complete_goal_held_until_session_closed(self):
        s = _store()
        self._mint(s, "s1", T0, "G")
        jd.apply_goal_edit(s, "s2", T0 + 10, {"op": "AMEND", "n": 1, "text": "G", "done": 1, "block": False},
                           jd.open_menu(s))                       # G complete, still the only/active focus
        gid = s["placements"]["s1"]
        jd.rollup_status(s, session_closed=False)
        self.assertEqual(s["status"][gid], "working", "complete but still the active focus -> held open (no flicker)")
        jd.rollup_status(s, session_closed=True)
        self.assertEqual(s["status"][gid], "completed", "session closed -> the focus goal may complete")

    def test_blocked_beats_completed(self):
        s = _store()
        self._mint(s, "s1", T0, "G")
        jd.apply_goal_edit(s, "s2", T0 + 10, {"op": "SUB", "n": 1, "text": "needs a decision", "done": None,
                                              "block": True}, jd.open_menu(s))   # blocked sub-node under G
        gid = s["placements"]["s1"]
        jd.rollup_status(s, session_closed=True)
        self.assertEqual(s["status"][gid], "blocked", "a blocked descendant beats completion")

    def test_top_done_with_open_step_completes_when_settled(self):
        """The real-fleet pattern (17/27 top-goals): the planner DONE's the TOP goal (the segment
        discharged the whole ask) but a trailing step was never DONE'd. The old whole-subtree rule
        held this working forever (0/27 ever reached all-leaves-complete); the top-done rule
        completes it once settled."""
        s = _store()
        self._mint(s, "s1", T0, "G1")                                            # top goal
        jd.apply_goal_edit(s, "s2", T0 + 10, {"op": "SUB", "n": 1, "text": "a step", "done": None,
                                              "block": False}, jd.open_menu(s))   # step under G1, never DONE'd
        jd.apply_goal_edit(s, "s3", T0 + 20, {"op": "AMEND", "n": 1, "text": "G1", "done": 1,
                                              "block": False}, jd.open_menu(s))   # DONE the TOP goal #1
        self._mint(s, "s4", T0 + 30, "G2")                                       # G2 now the focus → G1 settled
        g1, step = s["placements"]["s1"], s["placements"]["s2"]
        self.assertTrue(s["nodes"][g1]["nodeComplete"])
        self.assertFalse(s["nodes"][step]["nodeComplete"], "the trailing step is still open")
        jd.rollup_status(s, session_closed=False)
        self.assertEqual(s["status"][g1], "completed",
                         "top-done + settled completes even with a trailing open step")


class PlanPass(unittest.TestCase):
    def test_pass_accretes_menu_then_dedups(self):
        """Per-session sequential: segment 2's menu contains segment 1's minted goal (accretion);
        a second pass re-places nothing (dedup by segment id)."""
        records = [uline(T0, "first ask", "u1", ps="typed"),
                   aline(T0 + 30, "did first", "a1", "u1", stop="end_turn"),
                   uline(T0 + 100, "second ask", "u2", "a1", ps="typed"),
                   aline(T0 + 130, "did second", "a2", "u2", stop="end_turn")]
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            cdir = td / "launchdir"; cdir.mkdir()
            proj = td / "projects"
            pdir = proj / jd.re.sub(r"[/.]", "-", os.path.realpath(str(cdir)))
            pdir.mkdir(parents=True)
            (pdir / (SID + ".jsonl")).write_text("\n".join(json.dumps(r) for r in records) + "\n")
            names = td / "names"; names.mkdir()
            (names / SID).write_text("testsess\t%s\t#abcdef\n" % str(cdir))
            saved = (jd.NAMES, jd.PROJECTS, jd.GOALDIR, jd.plan_llm)
            jd.NAMES, jd.PROJECTS, jd.GOALDIR = names, proj, td / "goals"
            jd.plan_llm = lambda text, menu: ("MINT :: Goal one :: DONE none :: BLOCK no"
                                              if "no open goals" in menu else "SUB 1 :: a step :: DONE none :: BLOCK no")
            try:
                now = T0 + 5000
                n1 = jd.run_plan(now=now)
                self.assertEqual(n1, 2, "both segments placed")
                store = jd.load_goals(SID)
                tops = [nd for nd in store["nodes"].values() if nd["parentId"] is None]
                subs = [nd for nd in store["nodes"].values() if nd["parentId"] is not None]
                self.assertEqual(len(tops), 1, "second segment filed UNDER the first's goal (menu accreted)")
                self.assertEqual(len(subs), 1)
                n2 = jd.run_plan(now=now)
                self.assertEqual(n2, 0, "idempotent: placed segments are not re-placed")
            finally:
                (jd.NAMES, jd.PROJECTS, jd.GOALDIR, jd.plan_llm) = saved


class PlanTuning(unittest.TestCase):
    """The completion tuning (agreed at the planner checkpoint): flatten (cap depth so steps are
    siblings, not an ever-deepening chain) and un-block newest-wins."""

    def _depth_of(self, store, nid):
        d = 0
        while store["nodes"].get(nid, {}).get("parentId") is not None:
            nid = store["nodes"][nid]["parentId"]; d += 1
        return d

    def test_steps_do_not_chain_past_max_depth(self):
        s = _store()
        # mint G, then keep SUB-ing under the most-recently-created node (the old chaining bug)
        jd.apply_goal_edit(s, "s0", T0, {"op": "MINT", "n": None, "text": "G", "done": None, "block": False}, [])
        for i in range(1, 6):
            menu = jd.open_menu(s)
            last = max(s["nodes"].values(), key=lambda nd: nd["t"])           # newest node
            n = next(j for j, nd in enumerate(menu, 1) if nd["id"] == last["id"])
            jd.apply_goal_edit(s, "s%d" % i, T0 + i, {"op": "SUB", "n": n, "text": "step %d" % i,
                                                      "done": None, "block": False}, menu)
        depths = [self._depth_of(s, nid) for nid in s["nodes"]]
        self.assertLessEqual(max(depths), jd.MAX_DEPTH, "the tree stays shallow; steps don't chain")

    def test_unblock_newest_wins(self):
        s = _store()
        jd.apply_goal_edit(s, "s1", T0, {"op": "MINT", "n": None, "text": "G", "done": None, "block": False}, [])
        jd.apply_goal_edit(s, "s2", T0 + 10, {"op": "SUB", "n": 1, "text": "needs a decision",
                                              "done": None, "block": True}, jd.open_menu(s))
        self.assertTrue(any(nd["blocked"] for nd in s["nodes"].values()), "blocked after the BLOCK segment")
        # later non-block work under the goal clears the stale block (the user answered + work moved on)
        jd.apply_goal_edit(s, "s3", T0 + 20, {"op": "SUB", "n": 1, "text": "did the next thing",
                                              "done": None, "block": False}, jd.open_menu(s))
        self.assertFalse(any(nd["blocked"] for nd in s["nodes"].values()), "newer work un-blocks the goal")


if __name__ == "__main__":
    unittest.main(verbosity=2)
