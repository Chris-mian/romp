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
        (pdir / (SID + ".jsonl")).write_text("\n".join(json.dumps(r) for r in records) + "\n")
        names = td / "names"
        names.mkdir()
        (names / SID).write_text("testsess\t%s\t#abcdef\n" % str(cdir))
        saved = (jd.NAMES, jd.PROJECTS, jd.CAPDIR, jd.PCACHE, jd.caption_llm)
        jd.NAMES, jd.PROJECTS = names, proj
        jd.CAPDIR, jd.PCACHE = td / "captions", td / "pcache"
        jd.caption_llm = lambda text: "stub caption"

        def restore():
            (jd.NAMES, jd.PROJECTS, jd.CAPDIR, jd.PCACHE, jd.caption_llm) = saved
        return restore

    def test_pass_writes_both_grains_then_dedups(self):
        records = [uline(T0, "fix the flicker", "u1", ps="typed"),
                   aline(T0 + 30, "Fixed the flicker.", "a1", "u1", stop="end_turn")]
        with tempfile.TemporaryDirectory() as td:
            restore = self._fleet(td, records)
            try:
                # recent activity: set now near the transcript's time so the WINDOW includes it
                now = T0 + 120
                n1 = jd.run_once(now=now)
                recs = [json.loads(l) for l in (jd.CAPDIR / (SID + ".jsonl")).read_text().splitlines()]
                grains = sorted(r["grain"] for r in recs)
                self.assertEqual(grains, ["segment", "turn"], "single-segment turn writes both grains from one call")
                self.assertTrue(all(r["caption"] == "stub caption" for r in recs))
                self.assertEqual(n1, 2, "two records from one model call")
                # second pass: everything already captioned -> nothing written (id dedup)
                n2 = jd.run_once(now=now)
                self.assertEqual(n2, 0, "idempotent: a captioned unit is never re-captioned")
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
