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


def _mknode(s, text, parent=None, t=T0, complete=False):
    """Add a goal node directly (bypassing the planner) — for the sweep unit tests."""
    s["seq"] = s.get("seq", 0) + 1
    nid = "%s:g%d" % (SID, s["seq"])
    nd = {"id": nid, "text": text, "parentId": parent, "nodeComplete": complete,
          "blocked": False, "cleared": False, "trail": [], "t": t}
    s["nodes"][nid] = nd
    return nd


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


class Courier(unittest.TestCase):
    def test_seg_peer_extracts_sender_and_msgid(self):
        seg = {"trigger": "u1", "atoms": [{"uuid": "u1", "type": "user", "author": {"peer": "SENDERSID"},
               "message": {"content": [{"type": "text", "text": "ASK: do X\nromp-msg-id: abc.123"}]}}]}
        self.assertEqual(jd._seg_peer(seg), ("SENDERSID", "abc.123"))
        human = {"trigger": "u2", "atoms": [{"uuid": "u2", "type": "user", "author": "human",
                 "message": {"content": [{"type": "text", "text": "hi"}]}}]}
        self.assertIsNone(jd._seg_peer(human), "a human prompt is not a peer segment")

    def test_parse_courier(self):
        self.assertEqual(jd._parse_courier("PROPAGATING 2 :: fix the build", 3),
                         {"propagating": True, "n": 2, "text": "fix the build"})
        self.assertFalse(jd._parse_courier("FYI ::", 3)["propagating"])
        self.assertIsNone(jd._parse_courier("garbage", 3))
        self.assertIsNone(jd._parse_courier("PROPAGATING 9 :: x", 3)["n"], "out-of-range sender goal -> no link")

    def test_apply_courier_plants_top_goal_with_origin_and_dedups(self):
        s = _store()
        origin = {"peer": "SENDER", "goalId": "SENDER:g1", "msgId": "m1"}
        nid = jd.apply_courier(s, "seg1", T0, "do the handoff", origin)
        self.assertIsNone(s["nodes"][nid]["parentId"], "handoff is a top-level goal in the recipient tree")
        self.assertEqual(s["nodes"][nid]["origin"], origin)
        n2 = jd.apply_courier(s, "seg2", T0 + 10, "again", {"peer": "SENDER", "goalId": None, "msgId": "m1"})
        self.assertEqual(n2, nid, "same msgId -> reuse the planted node (idempotent)")
        self.assertEqual(sum(1 for nd in s["nodes"].values() if nd.get("origin")), 1, "no duplicate handoff")


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
        # later non-block work ON THAT BRANCH (under the blocked node) clears the stale block — the user
        # answered and work resumed there (surgical newest-wins; a sibling branch is left alone, below).
        menu = jd.open_menu(s)
        nb = next(i for i, nd in enumerate(menu, 1) if nd["text"] == "needs a decision")
        jd.apply_goal_edit(s, "s3", T0 + 20, {"op": "SUB", "n": nb, "text": "did the next thing",
                                              "done": None, "block": False}, menu)
        self.assertFalse(any(nd["blocked"] for nd in s["nodes"].values()), "newer work on the branch un-blocks it")


class BlockCompletionCorrectness(unittest.TestCase):
    """simplify's block/completion-correctness handoff (2026-06-15, human-designed): the weighing BLOCK
    rule, surgical (branch-only) un-block, completion clearing descendant blocks, bottom-up rollup."""

    def _mint(self, s, seg, t, text):
        jd.apply_goal_edit(s, seg, t, {"op": "MINT", "n": None, "text": text, "done": None, "block": False},
                           jd.open_menu(s))

    def _sub(self, s, seg, t, parent_text, text, block=False):
        menu = jd.open_menu(s)
        n = next(i for i, nd in enumerate(menu, 1) if nd["text"] == parent_text)
        jd.apply_goal_edit(s, seg, t, {"op": "SUB", "n": n, "text": text, "done": None, "block": block}, menu)

    def test_block_prompt_uses_the_weighing_rule(self):
        # #1: source-level guard that the validated weighing rule is in the planner prompt (the
        # behavioural A/B is simplify's; this locks the prompt against an accidental revert).
        for phrase in ("WAITING ON THE USER", "answering or reporting is not", "WEIGHING",
                       "the owed decision WINS"):
            self.assertIn(phrase, jd.PLAN_SYS, phrase)

    def test_surgical_unblock_leaves_sibling_block(self):
        # #2: two blocked sibling sub-goals; non-block work on ONE branch clears only that branch.
        s = _store()
        self._mint(s, "s1", T0, "G")
        self._sub(s, "s2", T0 + 1, "G", "subA", block=True)
        self._sub(s, "s3", T0 + 2, "G", "subB", block=True)
        b0 = {nd["text"]: nd["blocked"] for nd in s["nodes"].values()}
        self.assertTrue(b0["subA"] and b0["subB"], "both siblings blocked")
        self._sub(s, "s4", T0 + 3, "subA", "did subA work", block=False)   # non-block work under subA
        byname = {nd["text"]: nd for nd in s["nodes"].values()}
        self.assertFalse(byname["subA"]["blocked"], "the worked branch un-blocks")
        self.assertTrue(byname["subB"]["blocked"], "the unrelated sibling stays blocked")

    def test_completion_clears_descendant_blocks(self):
        # #3: DONE'ing a node clears blocks across its WHOLE subtree (a checked-off goal's child blocks are moot).
        s = _store()
        self._mint(s, "s1", T0, "G")
        self._sub(s, "s2", T0 + 1, "G", "sub", block=True)
        sub = next(nd for nd in s["nodes"].values() if nd["text"] == "sub")
        self.assertTrue(sub["blocked"])
        menu = jd.open_menu(s)
        n = next(i for i, nd in enumerate(menu, 1) if nd["text"] == "G")
        jd.apply_goal_edit(s, "s3", T0 + 2, {"op": "AMEND", "n": n, "text": "G", "done": n, "block": False}, menu)
        self.assertFalse(sub["blocked"], "completing the parent clears the descendant's block")

    def test_bottom_up_completion_when_all_children_done(self):
        # #4: a top whose children are ALL complete rolls up complete even if the top was never DONE'd.
        s = _store()
        self._mint(s, "s1", T0, "G")
        self._sub(s, "s2", T0 + 1, "G", "c1")
        self._sub(s, "s3", T0 + 2, "G", "c2")
        g = s["placements"]["s1"]
        for c in [nd for nd in s["nodes"].values() if nd["parentId"] == g]:
            c["nodeComplete"] = True
        self.assertFalse(s["nodes"][g]["nodeComplete"], "the top itself was never DONE'd")
        self._mint(s, "s4", T0 + 3, "G2")                 # a newer top is the focus → G settles
        jd.rollup_status(s, session_closed=False)
        self.assertEqual(s["status"][g], "completed", "all children complete → the top rolls up complete")

    def test_childless_top_still_needs_its_own_done(self):
        # #4 guard: bottom-up must NOT complete a childless node that was never DONE'd.
        s = _store()
        self._mint(s, "s1", T0, "G")
        self._mint(s, "s2", T0 + 1, "G2")                 # settle G
        g = s["placements"]["s1"]
        jd.rollup_status(s, session_closed=False)
        self.assertEqual(s["status"][g], "working", "a childless, never-DONE'd top stays working")


# ───────────────────────── the negative turn-end sweep (HYBRID completion) ─────────────────────────
class SweepParse(unittest.TestCase):
    def test_outstanding_numbers(self):
        self.assertEqual(jd._parse_sweep("1, 3", 4), {1, 3})
        self.assertEqual(jd._parse_sweep("2", 4), {2})
        self.assertEqual(jd._parse_sweep("Goals 2 and 4 are still outstanding", 4), {2, 4},
                         "digits are extracted even with surrounding prose")

    def test_none_completes_all(self):
        self.assertEqual(jd._parse_sweep("none", 3), set(),
                         "explicit 'none outstanding' -> empty set (complete every candidate)")

    def test_garbage_skips(self):
        self.assertIsNone(jd._parse_sweep("", 3), "empty output -> skip the turn")
        self.assertIsNone(jd._parse_sweep("i can't help with that", 3),
                          "no numbers and no 'none' -> skip (complete nothing, the safe default)")

    def test_out_of_range_dropped(self):
        self.assertEqual(jd._parse_sweep("1, 9", 3), {1}, "out-of-range index is dropped")
        self.assertIsNone(jd._parse_sweep("9", 3), "only an out-of-range index -> nothing usable -> skip")


class SweepApply(unittest.TestCase):
    def test_completes_complement_and_tags_provenance(self):
        s = _store()
        g1, g2, g3 = _mknode(s, "G1"), _mknode(s, "G2"), _mknode(s, "G3")
        newly = jd.apply_sweep(s, [g1, g2, g3], {2})              # only #2 still outstanding
        self.assertEqual(set(newly), {g1["id"], g3["id"]}, "the complement (1, 3) is completed")
        self.assertTrue(g1["nodeComplete"] and g3["nodeComplete"])
        self.assertFalse(g2["nodeComplete"], "the outstanding goal stays open")
        self.assertTrue(g1.get("negComplete"), "sweep-completed nodes are tagged for the A/B sample")

    def test_none_outstanding_completes_all(self):
        s = _store()
        g1, g2 = _mknode(s, "G1"), _mknode(s, "G2")
        self.assertEqual(set(jd.apply_sweep(s, [g1, g2], set())), {g1["id"], g2["id"]})

    def test_already_complete_not_recounted(self):
        s = _store()
        g1 = _mknode(s, "G1", complete=True)
        self.assertEqual(jd.apply_sweep(s, [g1], set()), [], "an already-complete node isn't re-completed")


class SweepMenu(unittest.TestCase):
    def _two_seg_turn(self):
        s = build_session([
            uline(T0, "ask A", "u1", ps="typed"),
            aline(T0 + 20, "did A", "a1", "u1", tools=("Read",), stop="tool_use"),
            qop(T0 + 40, "enqueue", "ask B"),
            qop(T0 + 60, "remove"),
            attline(T0 + 60, "ask B", "att1", "a1"),
            aline(T0 + 90, "did B", "a2", "att1", stop="end_turn"),
        ])
        turn = s["turns"][0]
        return turn, em.segments(turn)

    def test_scoped_to_open_touched_top_ancestors(self):
        turn, segs = self._two_seg_turn()
        self.assertEqual(len(segs), 2, "the absorbed turn has two segments")
        s = _store()
        g1 = _mknode(s, "G1")
        g2 = _mknode(s, "G2"); sub2 = _mknode(s, "step of G2", parent=g2["id"])
        _mknode(s, "G3 untouched")                                 # a dormant goal no segment touched
        s["placements"][segs[0]["id"]] = g1["id"]
        s["placements"][segs[1]["id"]] = sub2["id"]               # placed deep, under a step of G2
        ids = {nd["id"] for nd in jd._turn_menu(turn, s)}
        self.assertEqual(ids, {g1["id"], g2["id"]},
                         "the menu is the OPEN top-ancestors the turn touched; G3 (untouched) is excluded")

    def test_completed_top_is_not_a_candidate(self):
        turn, segs = self._two_seg_turn()
        s = _store()
        g1 = _mknode(s, "G1", complete=True)
        g2 = _mknode(s, "G2")
        s["placements"][segs[0]["id"]] = g1["id"]
        s["placements"][segs[1]["id"]] = g2["id"]
        self.assertEqual([nd["id"] for nd in jd._turn_menu(turn, s)], [g2["id"]],
                         "an already-completed top is no longer a sweep candidate")

    def test_two_segments_one_top_deduped(self):
        turn, segs = self._two_seg_turn()
        s = _store()
        g = _mknode(s, "G"); sub = _mknode(s, "step", parent=g["id"])
        s["placements"][segs[0]["id"]] = g["id"]
        s["placements"][segs[1]["id"]] = sub["id"]
        self.assertEqual([nd["id"] for nd in jd._turn_menu(turn, s)], [g["id"]],
                         "two segments under one top -> the top appears once")


class SweepTurn(unittest.TestCase):
    def setUp(self):
        self._llm = jd.sweep_llm
        self.s = build_session([uline(T0, "do X", "u1", ps="typed"),
                                aline(T0 + 20, "did X", "a1", "u1", stop="end_turn")])
        self.turn = self.s["turns"][0]
        self.seg = em.segments(self.turn)[0]

    def tearDown(self):
        jd.sweep_llm = self._llm

    def test_completes_the_touched_top(self):
        store = _store(); g1 = _mknode(store, "Do X")
        store["placements"][self.seg["id"]] = g1["id"]
        jd.sweep_llm = lambda tt, mt: "none"
        self.assertEqual(jd._sweep_turn(store, self.turn), [g1["id"]])
        self.assertTrue(store["nodes"][g1["id"]]["nodeComplete"])

    def test_llm_failure_completes_nothing(self):
        store = _store(); g1 = _mknode(store, "Do X")
        store["placements"][self.seg["id"]] = g1["id"]
        jd.sweep_llm = lambda tt, mt: ""                          # -> _parse_sweep None -> retry, complete nothing
        self.assertIsNone(jd._sweep_turn(store, self.turn))
        self.assertFalse(store["nodes"][g1["id"]]["nodeComplete"], "an LLM failure must not complete a goal")

    def test_no_touched_goal_is_a_noop_without_calling_the_llm(self):
        jd.sweep_llm = lambda tt, mt: (_ for _ in ()).throw(AssertionError("LLM must not run on an empty menu"))
        self.assertEqual(jd._sweep_turn(_store(), self.turn), [], "a turn that placed nothing -> no-op")


class SweepSession(unittest.TestCase):
    """End-to-end on a sandboxed fleet: the planner (positive-only, never DONE'ing) leaves tops
    working; the negative sweep completes the ones it's told are no longer outstanding, while the
    settled gate and per-turn idempotency compose unchanged."""

    def setUp(self):
        self._saved = (jd.NAMES, jd.PROJECTS, jd.GOALDIR, jd.plan_llm, jd.sweep_llm)
        self._td = tempfile.TemporaryDirectory()
        td = Path(self._td.name)
        cdir = td / "launchdir"; cdir.mkdir()
        proj = td / "projects"
        pdir = proj / jd.re.sub(r"[/.]", "-", os.path.realpath(str(cdir)))
        pdir.mkdir(parents=True)
        records = [uline(T0, "task A", "u1", ps="typed"),
                   aline(T0 + 30, "did A", "a1", "u1", stop="end_turn"),
                   uline(T0 + 100, "task B", "u2", "a1", ps="typed"),
                   aline(T0 + 130, "did B", "a2", "u2", stop="end_turn")]
        (pdir / (SID + ".jsonl")).write_text("\n".join(json.dumps(r) for r in records) + "\n")
        names = td / "names"; names.mkdir()
        (names / SID).write_text("testsess\t%s\t#abcdef\n" % str(cdir))
        jd.NAMES, jd.PROJECTS, jd.GOALDIR = names, proj, td / "goals"
        # positive-only: always MINT a top, never DONE -> every top is left 'working'
        jd.plan_llm = lambda text, menu: "MINT :: Goal :: DONE none :: BLOCK no"
        self.now = T0 + 5000

    def tearDown(self):
        (jd.NAMES, jd.PROJECTS, jd.GOALDIR, jd.plan_llm, jd.sweep_llm) = self._saved
        self._td.cleanup()

    def test_completes_silently_finished_top_and_settled_still_gates(self):
        jd.run_plan(now=self.now)
        store = jd.load_goals(SID)
        tops = sorted((nd for nd in store["nodes"].values() if nd["parentId"] is None), key=lambda nd: nd["t"])
        self.assertEqual(len(tops), 2)
        self.assertTrue(all(not nd["nodeComplete"] for nd in tops), "positive-only DONE'd nothing")
        self.assertTrue(all(store["status"][nd["id"]] == "working" for nd in tops), "both working before the sweep")
        jd.sweep_llm = lambda tt, mt: "none"                     # nothing outstanding -> complete each touched top
        n = jd.run_sweep(now=self.now)
        store = jd.load_goals(SID)
        g1, g2 = tops[0]["id"], tops[1]["id"]
        self.assertTrue(store["nodes"][g1]["nodeComplete"] and store["nodes"][g2]["nodeComplete"],
                        "the sweep marked both touched tops nodeComplete")
        self.assertEqual(store["status"][g1], "completed", "the earlier top is settled (not the focus) -> completed")
        self.assertEqual(store["status"][g2], "working",
                         "the focus top is held working by the settled gate despite the sweep (no flicker)")
        self.assertEqual(n, 2, "two nodes completed by the sweep")

    def test_dormant_goal_untouched_and_idempotent(self):
        seed = jd.load_goals(SID)
        g0 = _mknode(seed, "Dormant goal from another topic", t=T0 - 1000)
        jd.save_goals(SID, seed)
        jd.run_plan(now=self.now)
        jd.sweep_llm = lambda tt, mt: "none"
        jd.run_sweep(now=self.now)
        store = jd.load_goals(SID)
        self.assertFalse(store["nodes"][g0["id"]]["nodeComplete"],
                         "a goal no turn touched is never completed by the sweep (the false-positive guard)")
        jd.sweep_llm = lambda tt, mt: (_ for _ in ()).throw(AssertionError("an idempotent pass must not call the LLM"))
        self.assertEqual(jd.run_sweep(now=self.now), 0, "every turn already swept -> re-running completes nothing")


class ModelTiers(unittest.TestCase):
    """The Haiku cost lever (judge.md §Two run tiers): captioner + archiver run on the cheap INDEX
    model (Haiku); planner + courier + negative-sweep on the TRIAGE model (Sonnet)."""

    def test_index_vs_triage_split(self):
        self.assertIn("haiku", jd.INDEX_MODEL, "index tier is Haiku")
        self.assertEqual(jd.TRIAGE_MODEL, "claude-sonnet-4-6", "triage tier is Sonnet")
        self.assertNotEqual(jd.INDEX_MODEL, jd.TRIAGE_MODEL)
        calls, saved = [], jd._judge_run
        jd._judge_run = lambda model, sysp, user, effort=None: (calls.append((model, sysp)) or "")
        try:
            jd.caption_llm("x"); jd.archive_llm("x"); jd.plan_llm("x", "y")
            jd.courier_llm("x", "y"); jd.sweep_llm("x", "y")
        finally:
            jd._judge_run = saved
        by_sys = {sysp: m for (m, sysp) in calls}
        self.assertEqual(by_sys[jd.CAPTION_SYS], jd.INDEX_MODEL, "captioner → index (Haiku)")
        self.assertEqual(by_sys[jd.ARCHIVE_SYS], jd.INDEX_MODEL, "archiver → index (Haiku)")
        self.assertEqual(by_sys[jd.PLAN_SYS], jd.TRIAGE_MODEL, "planner → triage (Sonnet)")
        self.assertEqual(by_sys[jd.COURIER_SYS], jd.TRIAGE_MODEL, "courier → triage (Sonnet)")
        self.assertEqual(by_sys[jd.SWEEP_SYS], jd.TRIAGE_MODEL, "negative sweep → triage (Sonnet)")

    def test_plan_llm_model_and_effort_override(self):
        """plan_llm takes model + effort overrides (for the classification A/B); default is triage, no effort."""
        seen, saved = {}, jd._judge_run
        jd._judge_run = lambda model, sysp, user, effort=None: (seen.update(model=model, effort=effort) or "")
        try:
            jd.plan_llm("seg", "menu")
            self.assertEqual((seen["model"], seen["effort"]), (jd.TRIAGE_MODEL, None), "default: triage, no thinking")
            jd.plan_llm("seg", "menu", model="claude-opus-4-8", effort="medium")
            self.assertEqual((seen["model"], seen["effort"]), ("claude-opus-4-8", "medium"), "overrides pass through")
        finally:
            jd._judge_run = saved


class ClassifyExperiment(unittest.TestCase):
    """The blocked/working classification A/B (measure-only) picks each goal's latest subtree segment
    to re-classify — for a blocked goal that's the blocking segment (newest-wins)."""

    def test_latest_subtree_segment_is_the_most_recent_across_the_subtree(self):
        s = _store()
        top = _mknode(s, "G", t=T0)
        sub = _mknode(s, "sub", parent=top["id"], t=T0 + 10)
        s["nodes"][top["id"]]["trail"] = ["sA"]
        s["nodes"][sub["id"]]["trail"] = ["sB", "sC"]
        nodes = s["nodes"]
        children = {}
        for x, nd in nodes.items():
            children.setdefault(nd.get("parentId"), []).append(x)
        seg_by_id = {"sA": {"id": "sA", "t": T0, "atoms": []},
                     "sB": {"id": "sB", "t": T0 + 5, "atoms": []},
                     "sC": {"id": "sC", "t": T0 + 20, "atoms": []}}
        seg = jd._latest_subtree_segment(top["id"], nodes, children, seg_by_id)
        self.assertEqual(seg["id"], "sC", "the most recent segment anywhere in the subtree")
        self.assertIsNone(jd._latest_subtree_segment(top["id"], nodes, children, {}),
                          "no resolvable segment → None")


if __name__ == "__main__":
    unittest.main(verbosity=2)
