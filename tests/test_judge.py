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

    def test_tools_used_carries_key_args(self):
        """simplify's enrichment: TOOLS USED shows the key arg per tool (file path / Bash
        description), never the payload — no full scripts, diffs, or tool outputs."""
        big = "echo " + "X" * 5000                      # a huge bash script must NOT be dumped
        atoms = [
            {"type": "user", "author": "human",
             "message": {"content": [{"type": "text", "text": "do the thing"}]}},
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Edit",
                 "input": {"file_path": "/work/romp/bin/romp-judge"}},
                {"type": "tool_use", "name": "Bash",
                 "input": {"description": "run the test suite", "command": big}},
                {"type": "tool_use", "name": "Read",
                 "input": {"file_path": "/work/romp/chat-view/src/webview/feed.ts"}},
            ]}},
        ]
        txt = jd._unit_text(atoms)
        self.assertIn("Edit(bin/romp-judge)", txt, "file tools show the path (last 2 components)")
        self.assertIn("Read(webview/feed.ts)", txt)
        self.assertIn("Bash(run the test suite)", txt, "Bash shows its description")
        self.assertNotIn("X" * 200, txt, "the full bash script is never dumped")
        self.assertIn("USER ASKED: do the thing", txt)

    def test_tools_used_bash_falls_back_to_command_head(self):
        """No description on a Bash → the command head (capped at 60) stands in, never the script."""
        cmd = "git rebase --onto main feature~3 feature && make all && ./deploy.sh prod extra extra"
        atoms = [{"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Bash", "input": {"command": cmd}}]}}]
        txt = jd._unit_text(atoms)
        self.assertIn("Bash(git rebase", txt, "no description → the command head stands in")
        arg = txt.split("Bash(", 1)[1].split(")", 1)[0]
        self.assertLessEqual(len(arg), 60, "the command head is capped at 60 chars")

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

    def test_shape_passthrough_and_trim(self):
        self.assertEqual(jd._shape("hello", 10, 10), "hello", "fits within head+tail → unchanged")
        big = "A" * 50 + "MID" + "Z" * 50
        out = jd._shape(big, 20, 20)
        self.assertIn(" […] ", out, "oversized → head+tail with the elision marker")
        self.assertTrue(out.startswith("A" * 20), "the opening (head) is kept")
        self.assertTrue(out.endswith("Z" * 20), "the trailing end (tail) is kept")
        self.assertNotIn("MID", out, "the middle is dropped")

    def test_unit_text_shapes_a_long_assistant_reply(self):
        # > head+tail (2500+5500=8000) → keep the opening framing AND the trailing ask, drop the middle
        text = "HEAD_START " + "a" * 3000 + " MIDDLE_DROP " + "b" * 6000 + " TAIL_END"
        s = build_session([uline(T0, "q", "u1", ps="typed"),
                           aline(T0 + 30, text, "a1", "u1", stop="end_turn")])
        out = jd._unit_text(s["turns"][0]["atoms"])
        self.assertIn(" […] ", out, "an assistant reply over 8000 chars is trimmed with the marker")
        self.assertIn("HEAD_START", out); self.assertIn("TAIL_END", out)
        self.assertNotIn("MIDDLE_DROP", out, "the middle is dropped; head + tail survive")

    def test_unit_text_full_passthrough_when_short(self):
        text = "SHORT_ANSWER " + "c" * 500
        s = build_session([uline(T0, "q", "u1", ps="typed"),
                           aline(T0 + 30, text, "a1", "u1", stop="end_turn")])
        out = jd._unit_text(s["turns"][0]["atoms"])
        self.assertNotIn(" […] ", out, "under the limit → full passthrough, no marker")
        self.assertIn("SHORT_ANSWER", out); self.assertIn("c" * 500, out)


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

    def test_parse_caption_reads_json_field(self):
        # the captioner now emits {"caption": "..."}; _parse_caption extracts + cleans the field
        self.assertEqual(jd._parse_caption('{"caption": "Fixed the feed flicker"}'), "Fixed the feed flicker")
        self.assertEqual(jd._parse_caption('noise {"caption": "Tinted cards by recency"} more'),
                         "Tinted cards by recency", "the JSON object is isolated from surrounding prose")
        self.assertEqual(jd._parse_caption('{"caption": ""}'), "", "empty field (no finished work) -> no caption")
        self.assertEqual(jd._parse_caption("not json at all"), "", "a non-JSON reply -> no caption")
        self.assertEqual(jd._parse_caption('{"caption": "How can I help?"}'), "",
                         "the anti-chat guard still applies to the field value")


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
                r1 = jd.run_index(now=now)
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
                r2 = jd.run_index(now=now)
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
                jd.run_index(now=now, fairness=2, budget=100)
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
                jd.run_index(now=now)
                self.assertEqual(json.loads((jd.ARCHDIR / (SID + ".json")).read_text())["turns"], 1)
                # the session gains a second ended turn (rewrite the transcript; mtime/size change
                # invalidates the units cache, so the new turn is captioned, then re-archived)
                self._tpath.write_text("\n".join(json.dumps(r) for r in [
                    uline(T0, "first ask", "u1", ps="typed"),
                    aline(T0 + 30, "first reply", "a1", "u1", stop="end_turn"),
                    uline(T0 + 100, "second ask", "u2", "a1", ps="typed"),
                    aline(T0 + 130, "second reply", "a2", "u2", stop="end_turn")]) + "\n")
                jd.run_index(now=now)
                self.assertEqual(json.loads((jd.ARCHDIR / (SID + ".json")).read_text())["turns"], 2,
                                 "archive refreshes when the session gains a turn")
            finally:
                restore()


class ArchiveParse(unittest.TestCase):
    def test_parses_headline_and_abstract(self):
        out = '{"headline": "Rebuilding the romp event model", "abstract": "Built the parser and its tests. Validated it against the corpus."}'
        rec = jd._parse_archive(out)
        self.assertEqual(rec["headline"], "Rebuilding the romp event model")
        self.assertTrue(rec["abstract"].startswith("Built the parser"))
        self.assertIn("corpus", rec["abstract"])

    def test_tolerates_surrounding_prose(self):
        out = 'Here is the summary:\n{"headline": "Tuning the captioner", "abstract": "Pulled the word target down. Killed the comma-splice tail."}'
        rec = jd._parse_archive(out)
        self.assertEqual(rec["headline"], "Tuning the captioner")
        self.assertIn("Pulled the word target down. Killed the comma-splice tail.", rec["abstract"])

    def test_missing_field_is_failed_capture(self):
        self.assertIsNone(jd._parse_archive('{"headline": "only a headline, no abstract"}'))
        self.assertIsNone(jd._parse_archive("just some prose with no JSON"))
        self.assertIsNone(jd._parse_archive(""))


class PlanParse(unittest.TestCase):
    def test_mint_sub_and_amend_dropped(self):
        self.assertEqual(jd._parse_plan('{"ops":[{"why":"new ask","do":"mint","text":"Rebuild the parser"}]}', 3),
                         [{"do": "mint", "why": "new ask", "text": "Rebuild the parser"}])
        ops = jd._parse_plan('{"ops":[{"why":"step","do":"sub","under":2,"text":"added a test"},'
                             '{"why":"owed a call","do":"block","ref":1}]}', 3)
        self.assertEqual([o["do"] for o in ops], ["sub", "block"])
        self.assertEqual((ops[0]["under"], ops[1]["ref"]), (2, 1))
        # amend was cut (the user 2026-06-17): a lone amend op now parses to nothing
        self.assertIsNone(jd._parse_plan('{"ops":[{"why":"redef","do":"amend","goal":1,"text":"x"}]}', 3),
                          "amend is no longer a planner op")

    def test_out_of_range_sub_falls_back_to_mint(self):
        ops = jd._parse_plan('{"ops":[{"why":"x","do":"sub","under":9,"text":"orphan step"}]}', 3)  # only 3 open
        self.assertEqual(ops[0]["do"], "mint", "an invalid sub ref still places the work, never orphan")

    def test_bad_refs_dropped_and_garbage_none(self):
        self.assertIsNone(jd._parse_plan('{"ops":[{"why":"x","do":"done","goal":9}]}', 3),
                          "a done with only an out-of-range goal -> dropped -> no usable op")
        self.assertIsNone(jd._parse_plan("i cannot help with that", 3), "non-JSON -> None")
        self.assertIsNone(jd._parse_plan('{"ops":[]}', 3), "empty ops -> None")

    def test_multi_op_finish_one_start_another(self):
        ops = jd._parse_plan('{"ops":[{"why":"finished it","do":"done","goal":1},'
                             '{"why":"new ask","do":"mint","text":"start Y"}]}', 2)
        self.assertEqual([o["do"] for o in ops], ["done", "mint"], "a segment can finish one goal AND start another")

    def test_skip_verdict(self):
        self.assertEqual(jd._parse_plan('{"ops":[{"why":"just an ack","do":"skip"}]}', 3),
                         [{"do": "skip", "why": "just an ack"}])

    def test_tolerates_fences_and_prose(self):
        raw = 'Sure:\n```json\n{"ops":[{"why":"x","do":"mint","text":"a goal"}]}\n```'
        self.assertEqual(jd._parse_plan(raw, 3)[0]["do"], "mint", "strips ``` fences + surrounding prose")

    def test_trailing_prose_with_braces_still_parses(self):
        # The planner/closer parse-storm (the user 2026-06-18): a valid reply followed by a trailing aside
        # that itself contains a brace (a path, a goal ref, a code snippet). The old greedy first-brace→
        # last-brace match swallowed the aside and failed json.loads → None → unbounded retry storm.
        raw = '{"ops":[{"why":"new ask","do":"mint","text":"Rebuild it"}]} note: filed under {the parser goal}'
        self.assertEqual(jd._parse_plan(raw, 3),
                         [{"do": "mint", "why": "new ask", "text": "Rebuild it"}],
                         "trailing prose with a brace no longer breaks the parse")
        # the same hazard inside a fenced reply with a trailing path
        raw2 = '```json\n{"ops":[{"why":"x","do":"skip"}]}\n```\nsee ~/.local/state/romp/{goals}'
        self.assertEqual(jd._parse_plan(raw2, 3), [{"do": "skip", "why": "x"}],
                         "fence + trailing brace-bearing path still parses")

    def test_first_valid_object_wins_over_later_junk(self):
        # raw_decode stops at the first complete object; a malformed brace-blob after it is ignored.
        raw = '{"ops":[{"why":"y","do":"mint","text":"A"}]}{not json {at all}}'
        self.assertEqual(jd._parse_plan(raw, 3)[0]["text"], "A")


class PlanParseStorm(unittest.TestCase):
    """A planner reply that never parses must not retry forever (the user 2026-06-18). After
    PLAN_PARSE_RETRIES fails on ONE segment the planner stops retrying it — a human message is
    hard-placed (never lost), a non-user segment dropped — so one un-parseable reply can't storm the
    error log or burn a Sonnet call every pass forever."""

    def _run(self, records, llm):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            tpath = td / (SID + ".jsonl")
            tpath.write_text("\n".join(json.dumps(r) for r in records) + "\n")
            saved = (jd.GOALDIR, jd.PCACHE, jd.plan_llm, jd._group_store)
            jd.GOALDIR, jd.PCACHE = td / "goals", td / "pcache"
            jd.plan_llm = llm
            jd._group_store = lambda *a, **k: None     # don't fire the real grouper model after a placement
            try:
                placed = [jd._plan_session(SID, str(tpath), NOW) for _ in range(jd.PLAN_PARSE_RETRIES)]
                store = jd.load_goals(SID)
            finally:
                (jd.GOALDIR, jd.PCACHE, jd.plan_llm, jd._group_store) = saved
            return placed, store

    def test_human_message_lands_after_retries(self):
        records = [uline(T0, "please fix the flaky test", "u1", ps="typed"),
                   aline(T0 + 30, "On it.", "a1", "u1", stop="end_turn")]
        placed, store = self._run(records, lambda *a, **k: "i cannot help with that")   # never parses
        self.assertEqual(placed, [0] * (jd.PLAN_PARSE_RETRIES - 1) + [1],
                         "no placement until retries are exhausted, then ONE hard placement")
        tops = [nd for nd in store["nodes"].values() if nd["parentId"] is None]
        self.assertEqual(len(tops), 1, "the user message is hard-placed as a goal, never lost to a parse failure")
        self.assertEqual(store.get("parseFails", {}), {}, "the per-segment fail counter is cleared once resolved")

    def test_parsing_reply_places_normally_without_storm(self):
        # control: a reply that parses on the first try places immediately and records no parse-fails
        records = [uline(T0, "add a setting", "u1", ps="typed"),
                   aline(T0 + 30, "Added.", "a1", "u1", stop="end_turn")]
        placed, store = self._run(records, lambda *a, **k: '{"ops":[{"why":"new ask","do":"mint","text":"Add a setting"}]}')
        self.assertEqual(placed[0], 1, "a parseable reply places on the first pass")
        self.assertEqual(store.get("parseFails", {}), {}, "no parse-fail bookkeeping on the happy path")


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
        jd.apply_plan(s, "seg1", T0, [{"do": "mint", "why": "x", "text": "Goal A"}], [])
        jd.apply_plan(s, "seg2", T0 + 10, [{"do": "sub", "why": "x", "under": 1, "text": "step 1"}], jd.open_menu(s))
        sub = [n for n in s["nodes"].values() if n["parentId"] is not None]
        self.assertEqual(len(sub), 1)
        self.assertEqual(s["placements"]["seg2"], sub[0]["id"])
        self.assertEqual(s["nodes"][sub[0]["parentId"]]["text"], "Goal A", "sub files under the minted goal")

    def test_done_and_block_persist_their_reasons(self):
        s = _store()
        jd.apply_plan(s, "seg1", T0, [{"do": "mint", "why": "new ask", "text": "G"},
                                      {"do": "block", "why": "needs the user's go-ahead", "ref": 1}], [])
        nid = s["placements"]["seg1"]
        self.assertTrue(s["nodes"][nid]["blocked"])
        self.assertEqual(s["nodes"][nid]["blockWhy"], "needs the user's go-ahead", "block reason persisted")
        self.assertEqual(s["nodes"][nid]["why"], "new ask", "creation rationale persisted (for the modal tooltip)")
        jd.apply_plan(s, "seg2", T0 + 10, [{"do": "done", "why": "shipped it", "goal": 1}], jd.open_menu(s))
        self.assertTrue(s["nodes"][nid]["nodeComplete"])
        self.assertFalse(s["nodes"][nid]["blocked"], "completing a node clears its soft block")
        self.assertEqual(s["nodes"][nid]["doneWhy"], "shipped it", "done reason persisted")

    def test_done_only_segment_is_marked_processed(self):
        s = _store()
        jd.apply_plan(s, "seg1", T0, [{"do": "mint", "why": "x", "text": "G"}], [])
        jd.apply_plan(s, "seg2", T0 + 10, [{"do": "done", "why": "finished", "goal": 1}], jd.open_menu(s))
        self.assertIn("seg2", s["placements"], "a done-only segment still records a placements key (idempotent)")

    def test_mt_tracks_last_modified_t_stays_create(self):
        s = _store()
        jd.apply_plan(s, "s1", T0, [{"do": "mint", "why": "x", "text": "G"}], [])
        nid = s["placements"]["s1"]
        self.assertEqual((s["nodes"][nid]["t"], s["nodes"][nid]["mt"]), (T0, T0), "create sets t and mt")
        jd.apply_plan(s, "s2", T0 + 50, [{"do": "block", "why": "owed", "goal": 1}], jd.open_menu(s))
        self.assertEqual(s["nodes"][nid]["mt"], T0 + 50, "a block bumps mt")
        jd.apply_plan(s, "s3", T0 + 90, [{"do": "done", "why": "shipped", "goal": 1}], jd.open_menu(s))
        self.assertEqual(s["nodes"][nid]["mt"], T0 + 90, "a done bumps mt")
        self.assertEqual(s["nodes"][nid]["t"], T0, "t stays the create time — feed/ledger reading t are unaffected")

    def test_open_menu_seals_completed_subtrees(self):
        # A completed subtree is SEALED (the user 2026-06-16): an OPEN child of a done top is NOT in the
        # menu, so the planner can't sub/amend into it — new related work mints a new top instead.
        s = _store()
        jd.apply_plan(s, "s1", T0, [{"do": "mint", "why": "x", "text": "done top"}], [])
        jd.apply_plan(s, "s2", T0 + 10, [{"do": "sub", "why": "x", "under": 1, "text": "open child"}], jd.open_menu(s))
        self.assertEqual({nd["text"] for nd in jd.open_menu(s)}, {"done top", "open child"}, "both open before completion")
        menu = jd.open_menu(s)
        top_i = next(i for i, nd in enumerate(menu, 1) if nd["text"] == "done top")
        jd.apply_plan(s, "s3", T0 + 20, [{"do": "done", "why": "shipped", "goal": top_i}], menu)
        self.assertFalse(s["nodes"][s["placements"]["s2"]]["nodeComplete"], "the child is still open in the store")
        self.assertEqual(jd.open_menu(s), [], "the completed top AND its still-open child are sealed out of the menu")


class PlanRef(unittest.TestCase):
    """A done/block op targets a node CREATED earlier in the SAME reply via "ref" (1-based among this
    reply's mints/subs) — the multi-op replacement for the old DONE-self, composing with goal-indexed ops."""

    def test_mint_born_complete_via_ref(self):
        s = _store()
        jd.apply_plan(s, "s1", T0, [{"do": "mint", "why": "x", "text": "small task"},
                                    {"do": "done", "why": "done in one go", "ref": 1}], [])
        self.assertTrue(s["nodes"][s["placements"]["s1"]]["nodeComplete"],
                        "mint + done ref → the new top is born complete")

    def test_sub_step_ref_completes_only_the_step(self):
        s = _store()
        jd.apply_plan(s, "s1", T0, [{"do": "mint", "why": "x", "text": "G"}], [])
        jd.apply_plan(s, "s2", T0 + 10, [{"do": "sub", "why": "x", "under": 1, "text": "step"},
                                         {"do": "done", "why": "x", "ref": 1}], jd.open_menu(s))
        step = next(nd for nd in s["nodes"].values() if nd["parentId"] is not None)
        self.assertTrue(step["nodeComplete"], "sub + done ref → the step is complete")
        self.assertFalse(s["nodes"][s["placements"]["s1"]]["nodeComplete"], "the parent goal is NOT completed")

    def test_done_goal_clears_subtree_blocks(self):
        s = _store()
        jd.apply_plan(s, "s1", T0, [{"do": "mint", "why": "x", "text": "G"}], [])
        jd.apply_plan(s, "s2", T0 + 10, [{"do": "sub", "why": "x", "under": 1, "text": "sub"},
                                         {"do": "block", "why": "owed", "ref": 1}], jd.open_menu(s))
        sub = next(nd for nd in s["nodes"].values() if nd["parentId"] is not None)
        self.assertTrue(sub["blocked"])
        menu = jd.open_menu(s)
        gn = next(i for i, nd in enumerate(menu, 1) if nd["text"] == "G")
        jd.apply_plan(s, "s3", T0 + 20, [{"do": "done", "why": "x", "goal": gn}], menu)
        self.assertTrue(s["nodes"][s["placements"]["s1"]]["nodeComplete"], "done G → G complete")
        self.assertFalse(sub["blocked"], "completing G clears its subtree blocks")

    def test_ref_and_goal_compose_in_one_reply(self):
        s = _store()
        jd.apply_plan(s, "s1", T0, [{"do": "mint", "why": "x", "text": "G1"}], [])
        menu = jd.open_menu(s)                                   # [G1]
        jd.apply_plan(s, "s2", T0 + 10, [{"do": "mint", "why": "x", "text": "G2"},
                                         {"do": "done", "why": "x", "goal": 1},
                                         {"do": "done", "why": "x", "ref": 1}], menu)
        self.assertTrue(s["nodes"][s["placements"]["s1"]]["nodeComplete"], "done goal 1 completes G1")
        self.assertTrue(s["nodes"][s["placements"]["s2"]]["nodeComplete"], "done ref 1 completes the new G2")


class PlanSubRef(unittest.TestCase):
    """The planner no longer GROUPS (that moved to the grouper judge, 2026-06-17). It keeps `sub` with
    "ref" so a segment can mint an umbrella and file its own new work under it in the SAME reply."""

    def test_parse_drops_group_keeps_sub_ref(self):
        # a `group` op from the planner is now dropped (only-op → None; the planner doesn't reshape)
        self.assertIsNone(jd._parse_plan('{"ops":[{"why":"x","do":"group","goal":2,"under":1}]}', 3),
                          "the planner no longer emits group")
        ops = jd._parse_plan('{"ops":[{"why":"x","do":"mint","text":"keep"},'
                             '{"why":"x","do":"group","goal":1,"under":2}]}', 3)
        self.assertEqual(ops, [{"do": "mint", "why": "x", "text": "keep"}], "a group op is stripped, the mint stays")
        self.assertEqual(jd._parse_plan('{"ops":[{"why":"x","do":"sub","ref":1,"text":"step"}]}', 0),
                         [{"do": "sub", "why": "x", "ref": 1, "text": "step"}], "sub still accepts a ref parent")

    def test_sub_ref_files_new_work_under_a_fresh_umbrella(self):
        s = _store()
        jd.apply_plan(s, "s1", T0, [{"do": "mint", "why": "x", "text": "Umbrella"},
                                    {"do": "sub", "why": "x", "ref": 1, "text": "new step"}], [])
        um = next(nd for nd in s["nodes"].values() if nd["text"] == "Umbrella")
        step = next(nd for nd in s["nodes"].values() if nd["text"] == "new step")
        self.assertEqual(step["parentId"], um["id"], "sub ref files the new step under the just-minted umbrella")
        self.assertIsNone(um["parentId"], "the umbrella is the top")


class Grouper(unittest.TestCase):
    """The grouper judge (the user 2026-06-17): a separate pass after the planner that reshapes a
    session's OPEN top goals into coherent trees — relinking one top under another, or minting a fresh
    higher-level umbrella and nesting tops under it. Event-gated per session (groupedSig) so a stable
    board is never re-grouped."""

    def _two_tops(self):
        s = _store()
        jd.apply_plan(s, "s1", T0, [{"do": "mint", "why": "x", "text": "Goal A"}], [])
        jd.apply_plan(s, "s2", T0 + 10, [{"do": "mint", "why": "x", "text": "Goal B"}], jd.open_menu(s))
        return s, s["placements"]["s1"], s["placements"]["s2"]

    # ── parse ──
    def test_parse_mint_group_and_empty(self):
        self.assertEqual(jd._parse_group('{"ops":[{"why":"x","do":"group","goal":2,"under":1}]}', 3),
                         [{"do": "group", "why": "x", "goal": 2, "under": 1}])
        ops = jd._parse_group('{"ops":[{"why":"u","do":"mint","text":"Umbrella"},'
                              '{"why":"x","do":"group","goal":1,"ref":1}]}', 2)
        self.assertEqual(ops[0], {"do": "mint", "why": "u", "text": "Umbrella"})
        self.assertEqual(ops[1], {"do": "group", "why": "x", "goal": 1, "ref": 1}, "group via a same-reply ref")
        self.assertEqual(jd._parse_group('{"ops":[{"why":"x","do":"group","goal":1,"under":1}]}', 3), [],
                         "self-group (goal == under) is dropped")
        self.assertEqual(jd._parse_group('{"ops":[]}', 3), [], "empty ops is valid: nothing to group")
        self.assertIsNone(jd._parse_group("not json", 3), "unusable JSON → None (retry)")

    # ── apply ──
    def test_relinks_a_top_under_another(self):
        s, a, b = self._two_tops()
        tops = jd._group_tops(s)                                  # [A, B] oldest-first
        ai = next(i for i, nd in enumerate(tops, 1) if nd["id"] == a)
        bi = next(i for i, nd in enumerate(tops, 1) if nd["id"] == b)
        n = jd.apply_group(s, tops, [{"do": "group", "why": "both serve X", "goal": bi, "under": ai}], T0 + 20)
        self.assertEqual(n, 1, "one relink applied")
        self.assertEqual(s["nodes"][b]["parentId"], a, "B is relinked under A (its subtree moves with it)")
        self.assertIsNone(s["nodes"][a]["parentId"], "A stays a top")

    def test_two_tops_under_a_fresh_umbrella_with_anchor_backfill(self):
        s, a, b = self._two_tops()
        s["nodes"][a]["trail"] = ["s1"]                           # A has a real anchor seg; B has none
        tops = jd._group_tops(s)
        ai = next(i for i, nd in enumerate(tops, 1) if nd["id"] == a)
        bi = next(i for i, nd in enumerate(tops, 1) if nd["id"] == b)
        jd.apply_group(s, tops, [{"do": "mint", "why": "both serve X", "text": "Umbrella X"},
                                 {"do": "group", "why": "x", "goal": ai, "ref": 1},
                                 {"do": "group", "why": "x", "goal": bi, "ref": 1}], T0 + 20)
        um = next(nd for nd in s["nodes"].values() if nd["text"] == "Umbrella X")
        self.assertEqual(s["nodes"][a]["parentId"], um["id"], "A grouped under the fresh umbrella")
        self.assertEqual(s["nodes"][b]["parentId"], um["id"], "B grouped under the fresh umbrella")
        self.assertIsNone(um["parentId"], "the umbrella is the new top")
        self.assertTrue(um.get("umbrella"), "a minted umbrella is tagged")
        self.assertEqual(um["trail"], ["s1"], "umbrella inherits its earliest grouped child's anchor seg")

    def test_refuses_a_cycle(self):
        s = _store()
        jd.apply_plan(s, "s1", T0, [{"do": "mint", "why": "x", "text": "Parent"}], [])
        jd.apply_plan(s, "s2", T0 + 10, [{"do": "sub", "why": "x", "under": 1, "text": "Child"}], jd.open_menu(s))
        parent, child = s["placements"]["s1"], s["placements"]["s2"]
        tops = [s["nodes"][parent], s["nodes"][child]]            # force Child into the candidate list to exercise the guard
        n = jd.apply_group(s, tops, [{"do": "group", "why": "x", "goal": 1, "under": 2}], T0 + 20)
        self.assertEqual(n, 0, "the cyclic relink is refused")
        self.assertIsNone(s["nodes"][parent]["parentId"], "grouping Parent under its own Child is refused (no cycle)")
        self.assertEqual(s["nodes"][child]["parentId"], parent, "Child stays under Parent")

    def test_relink_clamps_at_max_depth(self):
        s = _store()
        jd.apply_plan(s, "s0", T0, [{"do": "mint", "why": "x", "text": "A"}], [])
        for i in range(1, jd.MAX_DEPTH + 1):                     # chain A -> step1 -> ... down to MAX_DEPTH
            menu = jd.open_menu(s)
            last = max(s["nodes"].values(), key=lambda nd: nd["t"])
            n = next(j for j, nd in enumerate(menu, 1) if nd["id"] == last["id"])
            jd.apply_plan(s, "s%d" % i, T0 + i, [{"do": "sub", "why": "x", "under": n, "text": "step %d" % i}], menu)
        jd.apply_plan(s, "sb", T0 + 50, [{"do": "mint", "why": "x", "text": "B"}], jd.open_menu(s))
        deepest = max(s["nodes"].values(), key=lambda nd: jd._depth(s["nodes"], nd["id"]))
        b = s["placements"]["sb"]
        tops = [deepest, s["nodes"][b]]                          # group B under the deepest node
        jd.apply_group(s, tops, [{"do": "group", "why": "x", "goal": 2, "under": 1}], T0 + 60)
        self.assertLessEqual(jd._depth(s["nodes"], b), jd.MAX_DEPTH, "B's relink is clamped to MAX_DEPTH")

    # ── the session pass: event-gated by the open-top set ──
    def _setup(self, store, records):
        td = Path(tempfile.mkdtemp())
        cdir = td / "launchdir"; cdir.mkdir()
        proj = td / "projects"
        pdir = proj / jd.re.sub(r"[/.]", "-", os.path.realpath(str(cdir)))
        pdir.mkdir(parents=True)
        (pdir / (SID + ".jsonl")).write_text("\n".join(json.dumps(r) for r in records) + "\n")
        names = td / "names"; names.mkdir()
        (names / SID).write_text("testsess\t%s\t#abcdef\n" % str(cdir))
        self._saved = (jd.NAMES, jd.PROJECTS, jd.GOALDIR, jd.group_llm)
        jd.NAMES, jd.PROJECTS, jd.GOALDIR = names, proj, td / "goals"
        jd.save_goals(SID, store)
        return str(pdir / (SID + ".jsonl"))

    def tearDown(self):
        if hasattr(self, "_saved"):
            (jd.NAMES, jd.PROJECTS, jd.GOALDIR, jd.group_llm) = self._saved

    def test_session_runs_once_then_gates_until_top_set_changes(self):
        store, a, b = self._two_tops()
        records = [uline(T0, "task one", "u1", ps="typed"),
                   aline(T0 + 10, "did one", "a1", "u1", stop="end_turn")]
        self._setup(store, records)
        calls = []

        def fake_group(menu):
            calls.append(menu)
            return '{"ops":[{"why":"both serve X","do":"group","goal":2,"under":1}]}'   # B under A
        jd.group_llm = fake_group
        now = T0 + 5000
        jd.run_group(now=now)
        st = jd.load_goals(SID)
        self.assertEqual(st["nodes"][b]["parentId"], a, "B nested under A")
        self.assertEqual(len(calls), 1, "the grouper called the model once")
        self.assertTrue(st.get("groupedSig"), "groupedSig recorded")
        jd.run_group(now=now)
        self.assertEqual(len(calls), 1, "unchanged open-top set → the model is NOT called again (event-gated)")
        # a NEW top appears → the open-top set changes → the grouper re-runs
        st = jd.load_goals(SID)
        jd.apply_plan(st, "s3", T0 + 200, [{"do": "mint", "why": "x", "text": "Goal C"}], jd.open_menu(st))
        jd.save_goals(SID, st)
        jd.run_group(now=now)
        self.assertEqual(len(calls), 2, "a newly minted top re-triggers the grouper")

    def test_single_top_records_sig_without_calling_model(self):
        store = _store()
        jd.apply_plan(store, "s1", T0, [{"do": "mint", "why": "x", "text": "Solo"}], [])
        records = [uline(T0, "task", "u1", ps="typed"), aline(T0 + 10, "did", "a1", "u1", stop="end_turn")]
        self._setup(store, records)
        calls = []
        jd.group_llm = lambda menu: calls.append(menu) or '{"ops":[]}'
        jd.run_group(now=T0 + 5000)
        self.assertEqual(len(calls), 0, "fewer than two tops → nothing to group, model not called")
        self.assertIsNotNone(jd.load_goals(SID).get("groupedSig"), "the (single-top) set is still recorded")

    def test_prompt_carries_the_grouping_steer(self):
        for phrase in ('"do":"group"', '"do":"mint"', "RELINK open top", "umbrella",
                       "AGGRESSIVE about grouping", "look-alike wording"):
            self.assertIn(phrase, jd.GROUP_SYS, phrase)
        self.assertNotIn("genuine", jd.GROUP_SYS.lower(), "the grouper prompt avoids 'genuine' too")

    def test_prompt_allows_doing_nothing(self):
        # the user 2026-06-17: the grouper may do nothing on its turn if nothing fits — make it explicit.
        self.assertIn("DOING NOTHING IS A VALID", jd.GROUP_SYS)
        self.assertIn('{"ops": []}', jd.GROUP_SYS, "the empty-ops escape hatch is spelled out")
        # and an empty op list is honored end-to-end: no relinks, nothing minted
        s, a, b = self._two_tops()
        tops = jd._group_tops(s)
        before = {nid: nd.get("parentId") for nid, nd in s["nodes"].items()}
        n = jd.apply_group(s, tops, jd._parse_group('{"ops":[]}', len(tops)), T0 + 20)
        self.assertEqual(n, 0, "empty ops → zero relinks")
        self.assertEqual({nid: nd.get("parentId") for nid, nd in s["nodes"].items()}, before, "tree unchanged")

    def test_planner_groups_inline_after_each_placement(self):
        # the user 2026-06-17: the grouper runs after EVERY planner step, so run_plan alone (no separate
        # run_group pass) nests the 2nd minted top under the 1st.
        records = [uline(T0, "one", "u1", ps="typed"),
                   aline(T0 + 10, "", "a1", "u1", tools=("Bash",), stop="end_turn"),
                   uline(T0 + 100, "two", "u2", "a1", ps="typed"),
                   aline(T0 + 110, "", "a2", "u2", tools=("Bash",), stop="end_turn")]
        td = Path(tempfile.mkdtemp())
        cdir = td / "launchdir"; cdir.mkdir()
        proj = td / "projects"
        pdir = proj / jd.re.sub(r"[/.]", "-", os.path.realpath(str(cdir)))
        pdir.mkdir(parents=True)
        (pdir / (SID + ".jsonl")).write_text("\n".join(json.dumps(r) for r in records) + "\n")
        names = td / "names"; names.mkdir()
        (names / SID).write_text("testsess\t%s\t#abcdef\n" % str(cdir))
        saved = (jd.NAMES, jd.PROJECTS, jd.GOALDIR, jd.plan_llm, jd.group_llm)
        jd.NAMES, jd.PROJECTS, jd.GOALDIR = names, proj, td / "goals"
        jd._PARSE_CACHE.clear()
        gcalls = []
        try:
            jd.plan_llm = (lambda text, menu, human=False:
                           '{"ops":[{"why":"x","do":"mint","text":"%s"}]}' % ("A" if "one" in text else "B"))

            def fake_group(menu):
                gcalls.append(menu)
                return '{"ops":[{"why":"both serve X","do":"group","goal":2,"under":1}]}'   # B under A
            jd.group_llm = fake_group
            jd.run_plan(now=T0 + 5000)
            st = jd.load_goals(SID)
            tops = [nd for nd in st["nodes"].values() if nd["parentId"] is None]
            self.assertEqual(len(tops), 1, "2nd top grouped under the 1st INLINE — no separate run_group needed")
            self.assertGreaterEqual(len(gcalls), 1, "the planner invoked the grouper after a placement")
        finally:
            (jd.NAMES, jd.PROJECTS, jd.GOALDIR, jd.plan_llm, jd.group_llm) = saved
            jd._PARSE_CACHE.clear()


class PlanRollup(unittest.TestCase):
    def _mint(self, s, seg, t, text):
        jd.apply_plan(s, seg, t, [{"do": "mint", "why": "x", "text": text}], jd.open_menu(s))

    def _done(self, s, seg, t, n):
        jd.apply_plan(s, seg, t, [{"do": "done", "why": "x", "goal": n}], jd.open_menu(s))

    def test_nonfocus_complete_goal_completes_focus_held_open(self):
        s = _store()
        self._mint(s, "s1", T0, "G1")
        self._done(s, "s2", T0 + 10, 1)                          # complete G1 (done-only, focus unchanged)
        self._mint(s, "s3", T0 + 20, "G2")                       # G2 is now the active focus
        g1, g2 = s["placements"]["s1"], s["placements"]["s3"]
        jd.rollup_status(s, session_closed=False)
        self.assertEqual(s["status"][g1], "completed", "complete AND no longer the focus -> completed")
        self.assertEqual(s["status"][g2], "working")

    def test_focus_complete_goal_held_until_session_closed(self):
        s = _store()
        self._mint(s, "s1", T0, "G")
        self._done(s, "s2", T0 + 10, 1)                          # G complete, still the only/active focus
        gid = s["placements"]["s1"]
        jd.rollup_status(s, session_closed=False)
        self.assertEqual(s["status"][gid], "working", "complete but still the active focus -> held open (no flicker)")
        jd.rollup_status(s, session_closed=True)
        self.assertEqual(s["status"][gid], "completed", "session closed -> the focus goal may complete")

    def test_blocked_beats_completed(self):
        s = _store()
        self._mint(s, "s1", T0, "G")
        jd.apply_plan(s, "s2", T0 + 10, [{"do": "sub", "why": "x", "under": 1, "text": "needs a decision"},
                                         {"do": "block", "why": "owed a decision", "ref": 1}], jd.open_menu(s))
        gid = s["placements"]["s1"]
        jd.rollup_status(s, session_closed=True)
        self.assertEqual(s["status"][gid], "blocked", "a blocked descendant beats completion")

    def test_top_done_with_open_step_completes_when_settled(self):
        """The real-fleet pattern: the planner DONEs the TOP goal (the segment discharged the whole ask)
        but a trailing step was never DONE'd. The old whole-subtree rule held this working forever; the
        top-done rule completes it once settled."""
        s = _store()
        self._mint(s, "s1", T0, "G1")                                            # top goal
        jd.apply_plan(s, "s2", T0 + 10, [{"do": "sub", "why": "x", "under": 1, "text": "a step"}],
                      jd.open_menu(s))                                            # step under G1, never DONE'd
        self._done(s, "s3", T0 + 20, 1)                                          # DONE the TOP goal #1
        self._mint(s, "s4", T0 + 30, "G2")                                       # G2 now the focus → G1 settled
        g1, step = s["placements"]["s1"], s["placements"]["s2"]
        self.assertTrue(s["nodes"][g1]["nodeComplete"])
        self.assertFalse(s["nodes"][step]["nodeComplete"], "the trailing step is still open")
        jd.rollup_status(s, session_closed=False)
        self.assertEqual(s["status"][g1], "completed",
                         "top-done + settled completes even with a trailing open step")

    def test_top_done_with_open_blocked_step_not_stuck(self):
        """The stuck-'blocked' bug (the user, 2026-06-15): the negative sweep
        completes the TOP (clearing only the top's own block) but a trailing step is left open AND
        blocked. A completed (sub)tree has no outstanding work, so the stale descendant block must
        not keep the finished goal rolling up to 'blocked'."""
        s = _store()
        g = _mknode(s, "G", complete=True)                 # top discharged (e.g. by the sweep)
        step = _mknode(s, "a step", parent=g["id"])        # trailing step: still open...
        step["blocked"] = True                             # ...and carrying a stale block
        s["lastNode"] = g["id"]
        jd.rollup_status(s, session_closed=True)            # settled
        self.assertEqual(s["status"][g["id"]], "completed",
                         "top-done goal completes despite a trailing open+blocked step")


class Courier(unittest.TestCase):
    def test_seg_peer_extracts_sender_and_msgid(self):
        seg = {"trigger": "u1", "atoms": [{"uuid": "u1", "type": "user", "author": {"peer": "SENDERSID"},
               "message": {"content": [{"type": "text", "text": "ASK: do X\nromp-msg-id: abc.123"}]}}]}
        self.assertEqual(jd._seg_peer(seg), ("SENDERSID", "abc.123"))
        human = {"trigger": "u2", "atoms": [{"uuid": "u2", "type": "user", "author": "human",
                 "message": {"content": [{"type": "text", "text": "hi"}]}}]}
        self.assertIsNone(jd._seg_peer(human), "a human prompt is not a peer segment")

    def test_seg_human_detects_human_opener(self):
        human = {"trigger": "u1", "atoms": [{"uuid": "u1", "type": "user", "author": "human",
                 "message": {"content": [{"type": "text", "text": "hi"}]}}]}
        self.assertTrue(jd._seg_human(human), "a human prompt is a user message")
        for auth in ("sdk", "system", {"peer": "SENDERSID"}):
            seg = {"trigger": "u2", "atoms": [{"uuid": "u2", "type": "user", "author": auth,
                   "message": {"content": [{"type": "text", "text": "x"}]}}]}
            self.assertFalse(jd._seg_human(seg), "%r is not a user message" % (auth,))

    def test_parse_courier(self):
        self.assertEqual(jd._parse_courier('{"verdict": "delegating", "goal": 2, "text": "fix the build"}', 3),
                         {"delegating": True, "n": 2, "text": "fix the build"})
        self.assertFalse(jd._parse_courier('{"verdict": "coordinating", "goal": 0, "text": ""}', 3)["delegating"])
        self.assertIsNone(jd._parse_courier("garbage", 3))
        self.assertIsNone(jd._parse_courier('{"verdict": "delegating", "goal": 9, "text": "x"}', 3)["n"],
                          "out-of-range sender goal -> no link")
        self.assertIsNone(jd._parse_courier('{"verdict": "delegating", "goal": 0, "text": "x"}', 3)["n"],
                          "goal 0 (no linkage) -> None")

    def test_log_judge_error_appends(self):
        # Swallowed judge-call failures are recorded to ERRORS (judge-errors.jsonl) for romp -j to surface.
        import tempfile, shutil, json as _json
        from pathlib import Path
        d = Path(tempfile.mkdtemp()); saved = jd.ERRORS
        try:
            jd.ERRORS = d / "judge-errors.jsonl"
            jd._log_judge_error("planner", "sid1", "parse")
            jd._log_judge_error("courier", "sid2", "call")
            recs = [_json.loads(l) for l in jd.ERRORS.read_text().splitlines()]
            self.assertEqual([r["tier"] for r in recs], ["planner", "courier"])
            self.assertEqual(recs[0]["err"], "parse")
            self.assertEqual(recs[1]["fsid"], "sid2")
            self.assertIsInstance(recs[0]["t"], int)
        finally:
            jd.ERRORS = saved
            shutil.rmtree(d, ignore_errors=True)

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
            jd.plan_llm = lambda text, menu, human=False: ('{"ops":[{"why":"x","do":"mint","text":"Goal one"}]}'
                                                           if "no open goals" in menu
                                                           else '{"ops":[{"why":"x","do":"sub","under":1,"text":"a step"}]}')
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


class PlanSkip(unittest.TestCase):
    """skip is now gated on authorship: a NON-user no-work segment (sdk/system/auto) is recorded
    processed but creates no node; a segment carrying a real USER message can NEVER be skipped — if the
    model returns skip anyway, the hard guard coerces it onto the board (mint when the board is empty,
    else a step under the most recent open goal). Event-based: keys on the trigger atom's author."""

    def _run(self, records):
        td = Path(tempfile.mkdtemp())
        cdir = td / "launchdir"; cdir.mkdir()
        proj = td / "projects"
        pdir = proj / jd.re.sub(r"[/.]", "-", os.path.realpath(str(cdir)))
        pdir.mkdir(parents=True)
        (pdir / (SID + ".jsonl")).write_text("\n".join(json.dumps(r) for r in records) + "\n")
        names = td / "names"; names.mkdir()
        (names / SID).write_text("testsess\t%s\t#abcdef\n" % str(cdir))
        self._saved = (jd.NAMES, jd.PROJECTS, jd.GOALDIR, jd.plan_llm)
        jd.NAMES, jd.PROJECTS, jd.GOALDIR = names, proj, td / "goals"
        return td

    def tearDown(self):
        if hasattr(self, "_saved"):
            (jd.NAMES, jd.PROJECTS, jd.GOALDIR, jd.plan_llm) = self._saved

    def test_nonuser_skip_recorded_but_user_skip_is_coerced(self):
        # sdk-opened no-work segment → the model SKIPs and it stays skipped (no node); a HUMAN no-work
        # ack → the model SKIPs but the hard guard places it anyway (board empty → mint).
        records = [uline(T0, "auto kickoff", "u0", ps="sdk"),                 # sdk → skip allowed
                   aline(T0 + 10, "noted", "a0", "u0", stop="end_turn"),
                   uline(T0 + 100, "just an ack", "u1", "a0", ps="typed"),    # human ack → MUST be placed
                   aline(T0 + 110, "ok", "a1", "u1", stop="end_turn")]
        self._run(records)
        calls = []

        def fake_plan(text, menu, human=False):
            calls.append((text, human))
            return '{"ops":[{"why":"nothing to do","do":"skip"}]}'           # model tries to skip BOTH
        jd.plan_llm = fake_plan
        now = T0 + 5000
        jd.run_plan(now=now)
        store = jd.load_goals(SID)
        self.assertEqual(len(store["nodes"]), 1, "only the human segment landed; the sdk skip created nothing")
        node = next(iter(store["nodes"].values()))
        self.assertIsNone(node["parentId"], "board was empty → coerced to a new top goal")
        self.assertIn("ack", node["text"], "the coerced label comes from the user's message")
        self.assertIn(None, store["placements"].values(), "the sdk SKIP is recorded as None (no node)")
        # the planner saw human=True for the user segment and human=False for the sdk one
        self.assertEqual(sorted(h for _, h in calls), [False, True])
        n_calls = len(calls)
        jd.run_plan(now=now)                                              # 2nd pass
        self.assertEqual(len(calls), n_calls, "both segments are idempotent — neither is re-judged")

    def test_user_skip_coerced_subs_under_the_active_goal(self):
        # a human tool-work segment mints a top; a later human ack the model tries to skip is coerced
        # to a STEP under that goal (the most recent open node), not a second top.
        records = [uline(T0, "do it", "u1", ps="typed"),
                   aline(T0 + 10, "", "a1", "u1", tools=("Bash",), stop="end_turn"),   # tool work → real placement
                   uline(T0 + 100, "thanks", "u2", "a1", ps="typed"),                  # human ack → coerced sub
                   aline(T0 + 110, "yw", "a2", "u2", stop="end_turn")]
        self._run(records)

        def fake_plan(text, menu, human=False):
            return ('{"ops":[{"why":"x","do":"mint","text":"the task"}]}' if "TOOLS USED" in text
                    else '{"ops":[{"why":"bare thanks","do":"skip"}]}')
        jd.plan_llm = fake_plan
        jd.run_plan(now=T0 + 5000)
        store = jd.load_goals(SID)
        tops = [nd for nd in store["nodes"].values() if nd["parentId"] is None]
        subs = [nd for nd in store["nodes"].values() if nd["parentId"] is not None]
        self.assertEqual(len(tops), 1, "the ack did NOT mint a second top")
        self.assertEqual(len(subs), 1, "the ack was coerced to a step under the active goal")
        self.assertEqual(subs[0]["parentId"], tops[0]["id"])


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
        jd.apply_plan(s, "s0", T0, [{"do": "mint", "why": "x", "text": "G"}], [])
        for i in range(1, 6):
            menu = jd.open_menu(s)
            last = max(s["nodes"].values(), key=lambda nd: nd["t"])           # newest node
            n = next(j for j, nd in enumerate(menu, 1) if nd["id"] == last["id"])
            jd.apply_plan(s, "s%d" % i, T0 + i, [{"do": "sub", "why": "x", "under": n, "text": "step %d" % i}], menu)
        depths = [self._depth_of(s, nid) for nid in s["nodes"]]
        self.assertLessEqual(max(depths), jd.MAX_DEPTH, "the tree stays shallow; steps don't chain")

    def test_unblock_newest_wins(self):
        s = _store()
        jd.apply_plan(s, "s1", T0, [{"do": "mint", "why": "x", "text": "G"}], [])
        jd.apply_plan(s, "s2", T0 + 10, [{"do": "sub", "why": "x", "under": 1, "text": "needs a decision"},
                                         {"do": "block", "why": "owed", "ref": 1}], jd.open_menu(s))
        self.assertTrue(any(nd["blocked"] for nd in s["nodes"].values()), "blocked after the block op")
        # later non-block work ON THAT BRANCH (under the blocked node) clears the stale block — the user
        # answered and work resumed there (surgical newest-wins; a sibling branch is left alone, below).
        menu = jd.open_menu(s)
        nb = next(i for i, nd in enumerate(menu, 1) if nd["text"] == "needs a decision")
        jd.apply_plan(s, "s3", T0 + 20, [{"do": "sub", "why": "x", "under": nb, "text": "did the next thing"}], menu)
        self.assertFalse(any(nd["blocked"] for nd in s["nodes"].values()), "newer work on the branch un-blocks it")

    def test_topic_placement_prompt_and_menu_cap(self):
        # the recency-bias fix: the prompt tells the model to scan the WHOLE list + file by topic, and the
        # menu cap is wide enough that an old topic-matching goal doesn't scroll off.
        self.assertIn("SCAN THE WHOLE", jd.PLAN_SYS)
        self.assertIn("never default to the most recent", jd.PLAN_SYS)
        self.assertIn("mint only when NO open goal matches", jd.PLAN_SYS)
        self.assertGreaterEqual(jd.open_menu.__defaults__[0], 20, "menu cap covers old goals (≥20)")

    def test_user_message_must_be_placed_never_skipped(self):
        # a segment carrying a real user message can't be skipped: the prompt forbids it and plan_llm
        # flags the segment with a <note> when human.
        self.assertIn("NEVER skip", jd.PLAN_SYS)
        self.assertIn("REAL USER MESSAGE", jd.PLAN_SYS)
        # human=True appends the note; human=False (the default) does not
        import unittest.mock as mock
        with mock.patch.object(jd, "_judge_run", return_value="{}") as m:
            jd.plan_llm("seg", "menu", human=True)
            self.assertIn("MUST be placed", m.call_args.args[2])
            jd.plan_llm("seg", "menu")
            self.assertNotIn("MUST be placed", m.call_args.args[2])

    def test_max_depth_is_4_and_stated_in_the_prompt(self):
        self.assertEqual(jd.MAX_DEPTH, 4, "planning hierarchy capped at 4 (the user, 2026-06-16)")
        self.assertIn("%d levels deep" % jd.MAX_DEPTH, jd.PLAN_SYS,
                      "the depth budget is embedded in the planner prompt, kept in sync with MAX_DEPTH")

    def test_why_messages_get_concise_writing_guidance(self):
        # The user's planner "why" is shown on the feed cards (why / blockWhy / doneWhy), so the prompt
        # carries distilled concise-writing rules (the user 2026-06-16, from the JLD method): real reason
        # first, concrete verbs, cut filler, no em dashes, confidence calibration.
        for phrase in ("Write each \"why\" plainly", "the real reason first", "concrete verbs",
                       "Cut filler", "no em dashes", "say it once"):
            self.assertIn(phrase, jd.PLAN_SYS, phrase)
        # the planner no longer polices stock AI words (the user 2026-06-16: that anti-AI-tell steer
        # isn't useful here); the general plain-writing advice above stays
        self.assertNotIn("delve", jd.PLAN_SYS)
        self.assertNotIn("stock AI words", jd.PLAN_SYS)
        # the courier's handoff label gets the same plain-words steer
        self.assertIn("plain concrete words", jd.COURIER_SYS)
        # the closer now writes a doneWhy per completed goal (JSON done list), with the same writing guidance
        self.assertIn('"done"', jd.CLOSER_SYS, "the closer emits a JSON done list with a reason per goal")
        for phrase in ("Write each \"why\" plainly", "no em dashes", "say it once"):
            self.assertIn(phrase, jd.CLOSER_SYS, phrase)

    def test_whys_are_user_vantage_and_blocks_read_as_questions(self):
        # the user 2026-06-17: whys speak to the user (no self-narration), and a block reads as the
        # question/ask itself rather than "Assistant asked …".
        self.assertIn("from the USER's vantage", jd.PLAN_SYS)
        self.assertIn("Drop self-narration", jd.PLAN_SYS)
        self.assertIn("PHRASE the \"why\" as the QUESTION OR ASK", jd.PLAN_SYS)
        self.assertIn("from the USER's vantage", jd.CLOSER_SYS, "the closer's doneWhy gets the same steer")

    def test_why_cap_raised_to_300(self):
        long = "word " * 100                                   # ~500 chars after normalization
        ops = jd._parse_plan('{"ops":[{"why":"%s","do":"mint","text":"G"}]}' % long.strip(), 1)
        self.assertEqual(len(ops[0]["why"]), 300, "planner why capped at 300 (was 200)")
        done = jd._parse_close('{"done":[{"goal":1,"why":"%s"}]}' % long.strip(), 1)["done"]
        self.assertEqual(len(done[1]), 300, "closer doneWhy capped at 300 (was 200)")

    def test_planner_eager_done_and_no_grouping(self):
        # the user 2026-06-17: the planner biases toward marking goals done EAGERLY, and (split out the
        # same day) NO LONGER groups — grouping moved to the grouper judge. Guard against a revert.
        self.assertIn("Mark done EAGERLY", jd.PLAN_SYS)
        for gone in ('"do":"group"', "RELINK", "GROUPING (be aggressive)", "regroup tops"):
            self.assertNotIn(gone, jd.PLAN_SYS, "%s should have moved to the grouper" % gone)
        self.assertIn("do NOT reorganize the board", jd.PLAN_SYS, "the planner is told the grouper handles nesting")

    def test_sub_files_under_the_old_topic_goal_not_the_newest(self):
        # mechanics: a SUB targeting an OLD goal lands there, not the newer one — the planner can reach
        # any menu index, so the topic clause's older-goal choice is honored end-to-end.
        s = _store()
        jd.apply_plan(s, "old", T0, [{"do": "mint", "why": "x", "text": "the OLD topic"}], [])
        jd.apply_plan(s, "new", T0 + 1000, [{"do": "mint", "why": "x", "text": "a NEWER topic"}], jd.open_menu(s))
        menu = jd.open_menu(s)                                    # oldest-first: [OLD, NEWER]
        self.assertEqual([nd["text"] for nd in menu], ["the OLD topic", "a NEWER topic"])
        old_idx = next(i for i, nd in enumerate(menu, 1) if nd["text"] == "the OLD topic")
        jd.apply_plan(s, "seg", T0 + 2000, [{"do": "sub", "why": "x", "under": old_idx, "text": "on the old topic"}],
                      menu)
        step = next(nd for nd in s["nodes"].values() if nd["parentId"] is not None)
        self.assertEqual(s["nodes"][step["parentId"]]["text"], "the OLD topic", "filed under the OLD goal")


class BlockCompletionCorrectness(unittest.TestCase):
    """simplify's block/completion-correctness handoff (2026-06-15, human-designed): the weighing BLOCK
    rule, surgical (branch-only) un-block, completion clearing descendant blocks, bottom-up rollup."""

    def _mint(self, s, seg, t, text):
        jd.apply_plan(s, seg, t, [{"do": "mint", "why": "x", "text": text}], jd.open_menu(s))

    def _sub(self, s, seg, t, parent_text, text, block=False):
        menu = jd.open_menu(s)
        n = next(i for i, nd in enumerate(menu, 1) if nd["text"] == parent_text)
        ops = [{"do": "sub", "why": "x", "under": n, "text": text}]
        if block:
            ops.append({"do": "block", "why": "owed", "ref": 1})
        jd.apply_plan(s, seg, t, ops, menu)

    def test_block_prompt_uses_the_weighing_rule(self):
        # #1: source-level guard that the validated weighing rule is in the planner prompt (the
        # behavioural A/B is simplify's; this locks the prompt against an accidental revert).
        for phrase in ("NEEDS THE USER", "is NOT blocking", "WEIGHING",
                       "the owed decision WINS"):
            self.assertIn(phrase, jd.PLAN_SYS, phrase)

    def test_block_prompt_excludes_non_user_deferrals(self):
        # the user 2026-06-16: work waiting on a PEER (handling it, or a reply to a message you sent) or
        # any non-user thing is NOT a user-owed decision, so it must NOT be labeled blocked. The block
        # trigger is qualified "from the user" so a peer's reply doesn't read as the blocking 'answer'.
        for phrase in ("answer FROM THE USER", "Waiting on anyone or anything OTHER than the user",
                       "another session is handling it", "PEER's reply to a message you sent",
                       "avoid a conflict", "only the human blocks"):
            self.assertIn(phrase, jd.PLAN_SYS, phrase)

    def test_answers_are_done_not_blocked(self):
        # the user 2026-06-17 (reversed the earlier block-the-answer rule): a fully-given explanation /
        # answer to a user question is DONE with the answer as its doneWhy — the feed tagline shows the
        # answer, so it no longer needs to sit in the needs-you/block column. Guard against a revert.
        self.assertIn("EXPLANATION or ANSWER", jd.PLAN_SYS)
        self.assertIn("the goal is DONE", jd.PLAN_SYS, "an answered question completes")
        self.assertIn("concise summary of the answer", jd.PLAN_SYS, "the answer rides in the done why")
        # the old block-the-answer mechanism is gone
        self.assertNotIn("ANSWERED THE USER", jd.PLAN_SYS, "answers are no longer routed to block")
        self.assertNotIn("if the ask was a QUESTION", jd.PLAN_SYS, "the done op no longer exempts questions")

    def test_answer_goal_completes_with_the_answer_as_donewhy(self):
        # mechanics: mint an answer-goal + done it via ref → it lands complete with the answer as doneWhy
        # (the inline reason the feed shows on the done card). No block needed.
        s = _store()
        jd.apply_plan(s, "qa", T0, [{"do": "mint", "why": "user asked how streaming works", "text": "Explained streaming tiers"},
                                    {"do": "done", "why": "Tier-1 delivers instantly; tier-2 batches every 20s", "ref": 1}], [])
        nid = s["placements"]["qa"]
        self.assertTrue(s["nodes"][nid]["nodeComplete"], "the answer-goal is DONE, not left open or blocked")
        self.assertFalse(s["nodes"][nid].get("blocked"), "and NOT parked in needs-you")
        self.assertEqual(s["nodes"][nid]["doneWhy"], "Tier-1 delivers instantly; tier-2 batches every 20s",
                         "the concise answer rides in doneWhy → shown on the done card's tagline")

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
        jd.apply_plan(s, "s3", T0 + 2, [{"do": "done", "why": "x", "goal": n}], menu)
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
    def test_done_list_with_reasons(self):
        self.assertEqual(jd._parse_close('{"done": [{"goal": 2, "why": "shipped it"}]}', 4),
                         {"done": {2: "shipped it"}, "block": {}})
        self.assertEqual(jd._parse_close(
            '{"done": [{"goal": 1, "why": "fixed the parser"}, {"goal": 3, "why": "wired the CLI flags"}]}', 4),
            {"done": {1: "fixed the parser", 3: "wired the CLI flags"}, "block": {}})
        self.assertEqual(jd._parse_close('noise {"done": [{"goal": 2, "why": "done"}]} more', 4),
                         {"done": {2: "done"}, "block": {}}, "the outermost JSON object is isolated from prose")

    def test_block_list_parsed_and_done_wins(self):
        # the user 2026-06-17: the closer can now BLOCK a touched top (needs the user), not just complete it
        self.assertEqual(jd._parse_close('{"done": [], "block": [{"goal": 2, "why": "Approve the migration?"}]}', 3),
                         {"done": {}, "block": {2: "Approve the migration?"}})
        self.assertEqual(jd._parse_close('{"done": [{"goal": 1, "why": "shipped"}], "block": [{"goal": 1, "why": "?"}]}', 3),
                         {"done": {1: "shipped"}, "block": {}}, "a goal in both -> done wins, dropped from block")
        self.assertEqual(jd._parse_close('{"done": [{"goal": 1, "why": "x"}]}', 3),
                         {"done": {1: "x"}, "block": {}}, "an absent block key is tolerated")

    def test_empty_done_completes_nothing(self):
        self.assertEqual(jd._parse_close('{"done": []}', 3), {"done": {}, "block": {}},
                         "empty done list -> empty maps (complete/block nothing)")

    def test_garbage_skips(self):
        self.assertIsNone(jd._parse_close("", 3), "empty output -> skip the turn")
        self.assertIsNone(jd._parse_close("i can't help with that", 3),
                          "no JSON object -> skip (complete nothing, the safe default)")
        self.assertIsNone(jd._parse_close('{"foo": 1}', 3),
                          "a JSON object with no done list -> skip (safe)")
        self.assertIsNone(jd._parse_close("1, 3", 3),
                          "the old numbers-only format is no longer accepted -> skip (safe)")

    def test_out_of_range_and_dupes_dropped(self):
        self.assertEqual(jd._parse_close('{"done": [{"goal": 1, "why": "a"}, {"goal": 9, "why": "b"}]}', 3),
                         {"done": {1: "a"}, "block": {}}, "out-of-range index is dropped")
        self.assertEqual(jd._parse_close('{"done": [{"goal": 9, "why": "b"}]}', 3), {"done": {}, "block": {}},
                         "only out-of-range -> empty (nothing in-range done)")
        self.assertEqual(jd._parse_close('{"done": [{"goal": 2, "why": "first"}, {"goal": 2, "why": "second"}]}', 3),
                         {"done": {2: "first"}, "block": {}}, "first reason wins for a duplicate index")
        self.assertEqual(jd._parse_close('{"done": ["junk", {"why": "no goal"}, {"goal": 2, "why": "ok"}]}', 3),
                         {"done": {2: "ok"}, "block": {}}, "malformed entries are skipped")

    def test_closer_prompt_offers_block(self):
        for phrase in ('"block"', "BLOCKED", "owed BY the user", "NEEDS THE USER"):
            self.assertIn(phrase, jd.CLOSER_SYS, phrase)

    def test_closer_prompt_prioritizes_top_level(self):
        # the user 2026-06-17: the closer is level-agnostic but prompted to prioritize top-level goals.
        self.assertIn("TOP-LEVEL goals are the most important", jd.CLOSER_SYS)
        self.assertIn("sub-goal", jd.CLOSER_SYS, "it also resolves finished sub-goals")


class SweepApply(unittest.TestCase):
    def test_completes_listed_dones_with_reason_and_provenance(self):
        s = _store()
        g1, g2, g3 = _mknode(s, "G1"), _mknode(s, "G2"), _mknode(s, "G3")
        newly = jd.apply_close(s, [g1, g2, g3], {"done": {1: "shipped G1", 3: "shipped G3"}, "block": {}}, t=T0 + 50)
        self.assertEqual(set(newly), {g1["id"], g3["id"]}, "the listed-done goals (1, 3) are completed")
        self.assertTrue(g1["nodeComplete"] and g3["nodeComplete"])
        self.assertFalse(g2["nodeComplete"], "a goal not listed stays open")
        self.assertEqual(g1["doneWhy"], "shipped G1", "the closer's reason is persisted as doneWhy")
        self.assertEqual(g1["mt"], T0 + 50, "the close bumps mt so the done node deep-links to the turn")
        self.assertTrue(g1.get("negComplete"), "closer-completed nodes are tagged for the A/B sample")

    def test_blocks_listed_goals_with_the_question_as_blockwhy(self):
        # the user 2026-06-17: the closer can BLOCK a touched top (needs-you), recording the question.
        s = _store()
        g1, g2 = _mknode(s, "G1"), _mknode(s, "G2")
        newly = jd.apply_close(s, [g1, g2], {"done": {1: "shipped"}, "block": {2: "Approve the rename?"}}, t=T0 + 50)
        self.assertEqual(newly, [g1["id"]], "block does NOT count as a completion")
        self.assertTrue(g2["blocked"], "the blocked goal is marked needs-you")
        self.assertEqual(g2["blockWhy"], "Approve the rename?", "the question rides in blockWhy")
        self.assertFalse(g2["nodeComplete"], "a blocked goal is not completed")
        self.assertTrue(g2["negBlock"], "a closer-set block is tagged negBlock (vs a planner block) for attribution")

    def test_empty_completes_and_blocks_nothing(self):
        s = _store()
        g1, g2 = _mknode(s, "G1"), _mknode(s, "G2")
        self.assertEqual(jd.apply_close(s, [g1, g2], {"done": {}, "block": {}}), [], "'none' -> nothing")

    def test_already_complete_not_recounted(self):
        s = _store()
        g1 = _mknode(s, "G1", complete=True)
        self.assertEqual(jd.apply_close(s, [g1], {"done": {1: "x"}, "block": {}}), [], "an already-complete node isn't re-completed")

    def test_closer_anchors_resolved_top_to_the_turns_recap(self):
        # the user 2026-06-17: a top the closer resolves at turn-end deep-links to the turn's FINAL segment
        # (the recap), not whatever intermediate segment its trail pointed at. trail[-1] = the recap.
        records = [uline(T0, "do the thing", "u1", ps="typed"),
                   aline(T0 + 20, "all done — summary here", "a1", "u1", stop="end_turn")]
        session = build_session(records)
        turn = session["turns"][0]
        recap = em.segments(turn)[-1]["id"]
        s = _store()
        g = _mknode(s, "The thing", t=T0)
        g["trail"] = ["older-intermediate-seg"]              # the pre-close (intermediate) anchor
        s["placements"] = {em.segments(turn)[0]["id"]: g["id"]}   # so _turn_menu sees the turn touched g
        saved = jd.closer_llm
        try:
            jd.closer_llm = lambda tt, mt: '{"done": [{"goal": 1, "why": "done"}], "block": []}'
            newly = jd._close_turn(s, turn)
        finally:
            jd.closer_llm = saved
        self.assertEqual(newly, [g["id"]], "the top was completed")
        self.assertEqual(s["nodes"][g["id"]]["trail"][-1], recap, "the done card now anchors to the turn's recap")
        self.assertNotEqual(s["nodes"][g["id"]]["trail"][-1], "older-intermediate-seg", "moved off the intermediate seg")


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

    def test_scoped_to_open_touched_goals_at_every_level(self):
        turn, segs = self._two_seg_turn()
        self.assertEqual(len(segs), 2, "the absorbed turn has two segments")
        s = _store()
        g1 = _mknode(s, "G1")
        g2 = _mknode(s, "G2"); sub2 = _mknode(s, "step of G2", parent=g2["id"])
        _mknode(s, "G3 untouched")                                 # a dormant goal no segment touched
        s["placements"][segs[0]["id"]] = g1["id"]
        s["placements"][segs[1]["id"]] = sub2["id"]               # placed deep, under a step of G2
        ids = {nd["id"] for nd in jd._turn_menu(turn, s)}
        self.assertEqual(ids, {g1["id"], sub2["id"], g2["id"]},
                         "level-agnostic: the touched sub2 AND its top g2 (and g1) are candidates; G3 (untouched) excluded")

    def test_completed_top_is_not_a_candidate(self):
        turn, segs = self._two_seg_turn()
        s = _store()
        g1 = _mknode(s, "G1", complete=True)
        g2 = _mknode(s, "G2")
        s["placements"][segs[0]["id"]] = g1["id"]
        s["placements"][segs[1]["id"]] = g2["id"]
        self.assertEqual([nd["id"] for nd in jd._turn_menu(turn, s)], [g2["id"]],
                         "an already-completed top is no longer a sweep candidate")

    def test_touched_node_and_its_ancestors_deduped(self):
        turn, segs = self._two_seg_turn()
        s = _store()
        g = _mknode(s, "G"); sub = _mknode(s, "step", parent=g["id"])
        s["placements"][segs[0]["id"]] = g["id"]
        s["placements"][segs[1]["id"]] = sub["id"]
        self.assertEqual({nd["id"] for nd in jd._turn_menu(turn, s)}, {g["id"], sub["id"]},
                         "the touched sub AND its top are both candidates, each once (deduped)")


class SweepTurn(unittest.TestCase):
    def setUp(self):
        self._llm = jd.closer_llm
        self.s = build_session([uline(T0, "do X", "u1", ps="typed"),
                                aline(T0 + 20, "did X", "a1", "u1", stop="end_turn")])
        self.turn = self.s["turns"][0]
        self.seg = em.segments(self.turn)[0]

    def tearDown(self):
        jd.closer_llm = self._llm

    def test_completes_the_touched_top(self):
        store = _store(); g1 = _mknode(store, "Do X")
        store["placements"][self.seg["id"]] = g1["id"]
        jd.closer_llm = lambda tt, mt: '{"done": [{"goal": 1, "why": "finished X"}]}'
        self.assertEqual(jd._close_turn(store, self.turn), [g1["id"]])
        self.assertTrue(store["nodes"][g1["id"]]["nodeComplete"])
        self.assertEqual(store["nodes"][g1["id"]]["doneWhy"], "finished X",
                         "the closer's reason becomes the node's doneWhy")
        self.assertEqual(store["nodes"][g1["id"]]["mt"], self.turn["t"],
                         "mt is bumped to the turn time so the done node deep-links to where it resolved")

    def test_llm_failure_completes_nothing(self):
        store = _store(); g1 = _mknode(store, "Do X")
        store["placements"][self.seg["id"]] = g1["id"]
        jd.closer_llm = lambda tt, mt: ""                          # -> _parse_close None -> retry, complete nothing
        self.assertIsNone(jd._close_turn(store, self.turn))
        self.assertFalse(store["nodes"][g1["id"]]["nodeComplete"], "an LLM failure must not complete a goal")

    def test_no_touched_goal_is_a_noop_without_calling_the_llm(self):
        jd.closer_llm = lambda tt, mt: (_ for _ in ()).throw(AssertionError("LLM must not run on an empty menu"))
        self.assertEqual(jd._close_turn(_store(), self.turn), [], "a turn that placed nothing -> no-op")


class SweepSession(unittest.TestCase):
    """End-to-end on a sandboxed fleet: the planner (positive-only, never DONE'ing) leaves tops
    working; the negative sweep completes the ones it's told are no longer outstanding, while the
    settled gate and per-turn idempotency compose unchanged."""

    def setUp(self):
        self._saved = (jd.NAMES, jd.PROJECTS, jd.GOALDIR, jd.plan_llm, jd.closer_llm, jd.group_llm)
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
        jd.plan_llm = lambda text, menu, human=False: '{"ops":[{"why":"x","do":"mint","text":"Goal"}]}'
        jd.group_llm = lambda menu: '{"ops":[]}'   # planner now groups inline; keep the sweep's tops un-nested
        self.now = T0 + 5000

    def tearDown(self):
        (jd.NAMES, jd.PROJECTS, jd.GOALDIR, jd.plan_llm, jd.closer_llm, jd.group_llm) = self._saved
        self._td.cleanup()

    def test_completes_and_settles_finished_tops_on_turn_end(self):
        jd.run_plan(now=self.now)
        store = jd.load_goals(SID)
        tops = sorted((nd for nd in store["nodes"].values() if nd["parentId"] is None), key=lambda nd: nd["t"])
        self.assertEqual(len(tops), 2)
        self.assertTrue(all(not nd["nodeComplete"] for nd in tops), "positive-only DONE'd nothing")
        self.assertTrue(all(store["status"][nd["id"]] == "working" for nd in tops), "both working before the sweep")
        jd.closer_llm = lambda tt, mt: '{"done": [{"goal": 1, "why": "done"}]}'   # each turn's single touched top reported done
        n = jd.run_close(now=self.now)
        store = jd.load_goals(SID)
        g1, g2 = tops[0]["id"], tops[1]["id"]
        self.assertTrue(store["nodes"][g1]["nodeComplete"] and store["nodes"][g2]["nodeComplete"],
                        "the sweep marked both touched tops nodeComplete")
        self.assertEqual(store["status"][g1], "completed", "the earlier top settles (not the focus) -> completed")
        self.assertEqual(store["status"][g2], "completed",
                         "the focus top ALSO finalizes — the last turn ENDED, so it's settled (the user 2026-06-17)")
        self.assertEqual(n, 2, "two nodes completed by the sweep")

    def test_dormant_goal_untouched_and_idempotent(self):
        seed = jd.load_goals(SID)
        g0 = _mknode(seed, "Dormant goal from another topic", t=T0 - 1000)
        jd.save_goals(SID, seed)
        jd.run_plan(now=self.now)
        jd.closer_llm = lambda tt, mt: '{"done": [{"goal": 1, "why": "done"}]}'
        jd.run_close(now=self.now)
        store = jd.load_goals(SID)
        self.assertFalse(store["nodes"][g0["id"]]["nodeComplete"],
                         "a goal no turn touched is never completed by the sweep (the false-positive guard)")
        jd.closer_llm = lambda tt, mt: (_ for _ in ()).throw(AssertionError("an idempotent pass must not call the LLM"))
        self.assertEqual(jd.run_close(now=self.now), 0, "every turn already swept -> re-running completes nothing")


class CloserKeyMigration(unittest.TestCase):
    """The closer's per-session 'already processed' set survives the sweep->close rename: it reads the
    new `closedTurns` key but falls back to the pre-rename `sweptTurns` so live stores don't re-run."""

    def test_reads_pre_rename_sweptturns(self):
        self.assertEqual(jd._closed_turns({"closedTurns": ["t2"]}), {"t2"})
        self.assertEqual(jd._closed_turns({"sweptTurns": ["t1"]}), {"t1"},
                         "the pre-rename sweptTurns key is still honored")
        self.assertEqual(jd._closed_turns({"closedTurns": ["t2"], "sweptTurns": ["t1"]}), {"t2"},
                         "the new key wins when both are present")
        self.assertEqual(jd._closed_turns({}), set())


class JudgeSystemPrompt(unittest.TestCase):
    """Every judge call is ISOLATED to its own prompt: --system-prompt REPLACES Claude Code's base
    prompt, --exclude-dynamic-system-prompt-sections drops the per-machine blocks, and --safe-mode
    drops auto-discovered CLAUDE.md/memory. (Measured: 8334 -> ~165 input tokens.)"""

    def test_replaces_not_appends_cc_prompt(self):
        cmd = jd._judge_cmd("some-model", "SYSTEM_PROMPT_BODY")
        self.assertIn("--system-prompt", cmd, "the judge REPLACES Claude Code's prompt")
        self.assertNotIn("--append-system-prompt", cmd, "no longer appended onto the CC base prompt")
        self.assertIn("--exclude-dynamic-system-prompt-sections", cmd,
                      "per-machine env / git / date blocks are dropped")
        self.assertIn("--safe-mode", cmd, "auto-discovered CLAUDE.md / memory / hooks are dropped")
        self.assertEqual(cmd[cmd.index("--system-prompt") + 1], "SYSTEM_PROMPT_BODY",
                         "the judge's prompt follows the --system-prompt flag")
        self.assertEqual(cmd[cmd.index("--output-format") + 1], "json",
                         "JSON envelope (for per-call usage logging)")


class JudgeOutputFormat(unittest.TestCase):
    """All five judges speak ONE output shape: a single JSON object, parsed by the shared _json_obj
    (the user 2026-06-16). Guards the consistency against any judge drifting back to a bespoke format."""

    def test_every_judge_prompt_requests_a_json_object(self):
        for name, sysp in [("captioner", jd.CAPTION_SYS), ("archiver", jd.ARCHIVE_SYS),
                           ("planner", jd.PLAN_SYS), ("closer", jd.CLOSER_SYS), ("courier", jd.COURIER_SYS)]:
            self.assertIn("JSON object", sysp, "%s must request a single JSON object" % name)

    def test_json_obj_isolates_the_outermost_object(self):
        self.assertEqual(jd._json_obj('```json\n{"a": 1}\n```'), {"a": 1}, "code fences are tolerated")
        self.assertEqual(jd._json_obj('prose {"a": 1, "b": [2]} trailing'), {"a": 1, "b": [2]},
                         "the outermost object is isolated from surrounding prose")
        self.assertIsNone(jd._json_obj("no json here"))
        self.assertIsNone(jd._json_obj("[1, 2, 3]"), "a top-level array is not an object")
        self.assertIsNone(jd._json_obj(""))


class ModelTiers(unittest.TestCase):
    """The Haiku cost lever (judge.md §Two run tiers): captioner + archiver run on the cheap INDEX
    model (Haiku); planner + courier + closer on the TRIAGE model (Sonnet)."""

    def test_index_vs_triage_split(self):
        self.assertIn("haiku", jd.INDEX_MODEL, "index tier is Haiku")
        self.assertEqual(jd.TRIAGE_MODEL, "claude-sonnet-4-6", "triage tier is Sonnet")
        self.assertNotEqual(jd.INDEX_MODEL, jd.TRIAGE_MODEL)
        calls, saved = [], jd._judge_run
        jd._judge_run = lambda model, sysp, user, effort=None, judge=None: (calls.append((model, sysp)) or "")
        try:
            jd.caption_llm("x"); jd.archive_llm("x"); jd.plan_llm("x", "y")
            jd.courier_llm("x", "y"); jd.closer_llm("x", "y")
        finally:
            jd._judge_run = saved
        by_sys = {sysp: m for (m, sysp) in calls}
        self.assertEqual(by_sys[jd.CAPTION_SYS], jd.INDEX_MODEL, "captioner → index (Haiku)")
        self.assertEqual(by_sys[jd.ARCHIVE_SYS], jd.INDEX_MODEL, "archiver → index (Haiku)")
        self.assertEqual(by_sys[jd.PLAN_SYS], jd.TRIAGE_MODEL, "planner → triage (Sonnet)")
        self.assertEqual(by_sys[jd.COURIER_SYS], jd.TRIAGE_MODEL, "courier → triage (Sonnet)")
        self.assertEqual(by_sys[jd.CLOSER_SYS], jd.TRIAGE_MODEL, "closer → triage (Sonnet)")

    def test_plan_llm_model_and_effort_override(self):
        """plan_llm takes model + effort overrides (for the classification A/B); default is triage, no effort."""
        seen, saved = {}, jd._judge_run
        jd._judge_run = lambda model, sysp, user, effort=None, judge=None: (seen.update(model=model, effort=effort) or "")
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


class SettledGateStates(unittest.TestCase):
    """The rollup's settled gate finalizes a completed focus goal once the session is NOT mid-turn — the
    last turn ENDED (end_turn) or is idle-terminated (the user 2026-06-17: the old idle-only signal was
    unreliable, so completions hung at working until the next prompt). parsed_session passes
    states/<fsid>.jsonl so a real idle transition still settles an unfinished turn (handed off by `bugs`),
    and the states file's (mtime,size) is folded into the parse-cache key so an idle-only change re-parses."""

    def _setup(self, records):
        td = Path(tempfile.mkdtemp())
        path = td / (SID + ".jsonl")
        path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
        statesdir = td / "states"; statesdir.mkdir()
        self._saved = (jd.STATESDIR, dict(jd._PARSE_CACHE))
        jd.STATESDIR = statesdir
        jd._PARSE_CACHE.clear()
        return str(path), statesdir

    def tearDown(self):
        if hasattr(self, "_saved"):
            jd.STATESDIR = self._saved[0]
            jd._PARSE_CACHE.clear(); jd._PARSE_CACHE.update(self._saved[1])

    def test_ended_turn_is_settled_without_idle(self):
        # the fix: an ended turn (assistant handed back the floor) is settled immediately — no idle needed.
        records = [uline(T0, "do it", "u1", ps="typed"), aline(T0 + 10, "done", "a1", "u1", stop="end_turn")]
        path, _ = self._setup(records)
        self.assertTrue(jd._session_closed(jd.parsed_session(SID, [path], T0 + 5000)),
                        "end_turn → settled (no waiting on an idle signal that may never be written)")

    def test_open_turn_not_settled_until_idle(self):
        # a turn still in progress (no end_turn) is NOT settled — until a real idle transition lands.
        records = [uline(T0, "do it", "u1", ps="typed"), aline(T0 + 10, "still going", "a1", "u1", stop=None)]
        path, statesdir = self._setup(records)
        now = T0 + 5000
        self.assertFalse(jd._session_closed(jd.parsed_session(SID, [path], now)),
                         "mid-turn (assistant still streaming) → not settled (no flicker)")
        (statesdir / (SID + ".jsonl")).write_text(json.dumps({"t": T0 + 60, "state": "idle"}) + "\n")
        self.assertTrue(jd._session_closed(jd.parsed_session(SID, [path], now)),
                        "an idle transition still settles an unfinished turn (abandoned / laptop closed)")

    def test_idle_append_busts_cache_despite_unchanged_transcript(self):
        records = [uline(T0, "x", "u1", ps="typed"), aline(T0 + 10, "y", "a1", "u1", stop=None)]   # open, not ended
        path, statesdir = self._setup(records)
        (statesdir / (SID + ".jsonl")).write_text(json.dumps({"t": T0 + 5, "state": "working"}) + "\n")
        now = T0 + 5000
        self.assertFalse(jd._session_closed(jd.parsed_session(SID, [path], now)))
        with open(statesdir / (SID + ".jsonl"), "a") as fh:           # transcript untouched; states grows
            fh.write(json.dumps({"t": T0 + 60, "state": "idle"}) + "\n")
        self.assertTrue(jd._session_closed(jd.parsed_session(SID, [path], now)),
                        "states-file growth busts the cache → re-parse picks up the idle transition")

    def test_focus_complete_goal_settles_when_the_turn_ends(self):
        # end-to-end: a discharged TOP that is the active focus finalizes the moment its turn ends — no
        # new prompt, no idle. While the turn is still open it's held working (no flicker).
        open_recs = [uline(T0, "ship it", "u1", ps="typed"), aline(T0 + 10, "shipping", "a1", "u1", stop=None)]
        path, _ = self._setup(open_recs)
        now = T0 + 5000
        s = _store()
        g = _mknode(s, "Ship the release", t=T0); g["nodeComplete"] = True
        s["lastNode"] = g["id"]                                       # the completed goal is the active focus
        jd.rollup_status(s, jd._session_closed(jd.parsed_session(SID, [path], now)))
        self.assertEqual(s["status"][g["id"]], "working", "still mid-turn → held working (no flicker)")
        # the assistant finishes the turn (end_turn) → settled → completed, with no prompt and no idle
        Path(path).write_text("\n".join(json.dumps(r) for r in
                              [uline(T0, "ship it", "u1", ps="typed"),
                               aline(T0 + 10, "shipped", "a1", "u1", stop="end_turn")]) + "\n")
        jd._PARSE_CACHE.clear()
        jd.rollup_status(s, jd._session_closed(jd.parsed_session(SID, [path], now)))
        self.assertEqual(s["status"][g["id"]], "completed", "turn ended → focus goal finalizes (no prompt, no idle)")


class FollowUp(unittest.TestCase):
    """Follow-up handling (the user 2026-06-17): a "follow up on this card" UI action composes a chat
    prompt carrying `<!-- romp-goal-id: <id> -->`. The planner reopens that exact goal (the sole exception
    to the sealed-completed-subtree rule) and FORCES the new work as a step UNDER it; the closer/settled
    gate re-completes it. No event-model change — the judge parses the marker from the prompt text."""

    def test_seg_followup_extracts_marker(self):
        gid = SID + ":g3"
        seg = {"trigger": "u1", "atoms": [{"uuid": "u1", "type": "user", "author": "human",
               "message": {"content": [{"type": "text", "text": "more please <!-- romp-goal-id: %s -->" % gid}]}}]}
        self.assertEqual(jd._seg_followup(seg), gid)
        plain = {"trigger": "u2", "atoms": [{"uuid": "u2", "type": "user", "author": "human",
                 "message": {"content": [{"type": "text", "text": "no marker here"}]}}]}
        self.assertIsNone(jd._seg_followup(plain), "no marker → not a follow-up")

    def _setup(self, records, store):
        td = Path(tempfile.mkdtemp())
        cdir = td / "launchdir"; cdir.mkdir()
        proj = td / "projects"
        pdir = proj / jd.re.sub(r"[/.]", "-", os.path.realpath(str(cdir)))
        pdir.mkdir(parents=True)
        (pdir / (SID + ".jsonl")).write_text("\n".join(json.dumps(r) for r in records) + "\n")
        names = td / "names"; names.mkdir()
        (names / SID).write_text("testsess\t%s\t#abcdef\n" % str(cdir))
        self._saved = (jd.NAMES, jd.PROJECTS, jd.GOALDIR, jd.plan_llm, jd.group_llm)
        jd.NAMES, jd.PROJECTS, jd.GOALDIR = names, proj, td / "goals"
        jd._PARSE_CACHE.clear()
        jd.save_goals(SID, store)

    def tearDown(self):
        if hasattr(self, "_saved"):
            (jd.NAMES, jd.PROJECTS, jd.GOALDIR, jd.plan_llm, jd.group_llm) = self._saved
            jd._PARSE_CACHE.clear()

    def _completed_top(self, gid, blocked=False):
        return {"rompUuid": SID, "seq": 1, "status": {gid: "blocked" if blocked else "completed"},
                "placements": {"s0": gid},
                "nodes": {gid: {"id": gid, "text": "Ship the release", "parentId": None,
                                "nodeComplete": not blocked, "blocked": blocked, "cleared": False,
                                "trail": ["s0"], "t": T0 - 100, "mt": T0 - 100, "doneWhy": "shipped"}}}

    def test_followup_reopens_completed_goal_and_forces_sub_under_it(self):
        gid = SID + ":g1"
        records = [uline(T0, "actually also handle the edge case <!-- romp-goal-id: %s -->" % gid, "u1", ps="typed"),
                   aline(T0 + 10, "handled it", "a1", "u1", stop="end_turn")]
        self._setup(records, self._completed_top(gid))
        # the planner describes the work; the parent is forced to the tagged goal regardless of "under"
        jd.plan_llm = lambda text, menu, human=False: '{"ops":[{"why":"covered the edge case","do":"mint","text":"edge case handled"}]}'
        jd.run_plan(now=T0 + 5000)
        st = jd.load_goals(SID)
        self.assertFalse(st["nodes"][gid]["nodeComplete"], "the tagged goal was reopened")
        subs = [nd for nd in st["nodes"].values() if nd["parentId"] == gid]
        self.assertEqual(len(subs), 1, "the follow-up work was filed UNDER the tagged goal (forced), not as a new top")
        self.assertEqual(subs[0]["text"], "edge case handled", "reuses the planner's description for the step")
        self.assertEqual(st["status"][gid], "working", "the reopened goal is working again")

    def test_followup_unblocks_a_blocked_goal(self):
        gid = SID + ":g1"
        records = [uline(T0, "here's my answer: yes <!-- romp-goal-id: %s -->" % gid, "u1", ps="typed"),
                   aline(T0 + 10, "proceeding", "a1", "u1", stop="end_turn")]
        self._setup(records, self._completed_top(gid, blocked=True))
        jd.plan_llm = lambda text, menu, human=False: '{"ops":[{"why":"answered, moving on","do":"sub","under":1,"text":"resumed after the answer"}]}'
        jd.run_plan(now=T0 + 5000)
        st = jd.load_goals(SID)
        self.assertFalse(st["nodes"][gid]["blocked"], "answering the follow-up unblocked the goal")
        self.assertEqual(len([nd for nd in st["nodes"].values() if nd["parentId"] == gid]), 1, "work filed under it")

    def test_followup_to_missing_goal_falls_back_to_normal_placement(self):
        records = [uline(T0, "brand new thing <!-- romp-goal-id: %s:g99 -->" % SID, "u1", ps="typed"),
                   aline(T0 + 10, "did it", "a1", "u1", stop="end_turn")]
        self._setup(records, {"rompUuid": SID, "seq": 0, "nodes": {}, "placements": {}, "status": {}})
        jd.plan_llm = lambda text, menu, human=False: '{"ops":[{"why":"new ask","do":"mint","text":"New thing"}]}'
        jd.run_plan(now=T0 + 5000)
        tops = [nd for nd in jd.load_goals(SID)["nodes"].values() if nd["parentId"] is None]
        self.assertEqual(len(tops), 1, "a stale follow-up id falls back to normal placement (minted a top)")

    def test_optimistic_followup_reopens_immediately_with_pending_flag(self):
        # the kernel calls this on Enter so the card shows WORKING + a chip before the judge pass runs.
        gid = SID + ":g1"
        td = Path(tempfile.mkdtemp()); saved = jd.GOALDIR; jd.GOALDIR = td / "goals"
        try:
            jd.save_goals(SID, {"rompUuid": SID, "seq": 1, "status": {gid: "completed"}, "placements": {},
                                "nodes": {gid: {"id": gid, "text": "Ship it", "parentId": None,
                                                "nodeComplete": True, "blocked": False, "cleared": False,
                                                "trail": ["s0"], "t": T0, "mt": T0, "doneWhy": "shipped"}}})
            self.assertTrue(jd.optimistic_followup(SID, gid), "reopened the card")
            st = jd.load_goals(SID)
            self.assertTrue(st["nodes"][gid]["followupPending"], "followupPending set (drives the chip)")
            self.assertFalse(st["nodes"][gid]["nodeComplete"], "reopened — nodeComplete cleared")
            self.assertEqual(st["status"][gid], "working", "rollup shows WORKING immediately, not completed")
            jd._reopen(st, gid)                         # the judge's OFFICIAL reopen supersedes the optimistic one
            self.assertNotIn("followupPending", st["nodes"][gid], "_reopen drops the optimistic flag")
            self.assertFalse(jd.optimistic_followup(SID, SID + ":g99"), "unknown goal → no-op (False)")
        finally:
            jd.GOALDIR = saved

    def test_optimistic_followup_on_a_blocked_sub_unblocks_its_top(self):
        # the per-sub follow-up (the user 2026-06-17): the feed posts the EXISTING askFollowUp with a SUB's
        # node id, so optimistic_followup reopens just that sub and unblocks its ANCESTOR chain → the TOP card
        # goes off-blocked at once, and the sub carries followupPending (the modal's per-node "Followed up"
        # chip). This is the backend contract the feed.ts per-sub action relies on — no kernel change.
        top, sub = SID + ":g1", SID + ":g2"
        td = Path(tempfile.mkdtemp()); saved = jd.GOALDIR; jd.GOALDIR = td / "goals"
        try:
            jd.save_goals(SID, {"rompUuid": SID, "seq": 2, "status": {top: "blocked"}, "placements": {},
                "nodes": {
                    top: {"id": top, "text": "Build it", "parentId": None, "nodeComplete": False,
                          "blocked": True, "cleared": False, "trail": ["s0"], "t": T0, "mt": T0},
                    sub: {"id": sub, "text": "decide the API shape", "parentId": top, "nodeComplete": False,
                          "blocked": True, "cleared": False, "trail": ["s1"], "t": T0, "mt": T0,
                          "blockWhy": "needs the user's call"}}})
            self.assertTrue(jd.optimistic_followup(SID, sub), "reopened the specific blocked sub")
            st = jd.load_goals(SID)
            self.assertTrue(st["nodes"][sub]["followupPending"], "the SUB carries followupPending (per-node chip)")
            self.assertFalse(st["nodes"][sub]["blocked"], "the followed-up sub is unblocked")
            self.assertFalse(st["nodes"][top]["blocked"], "unblocking the sub's ancestor chain clears the top's block")
            self.assertEqual(st["status"][top], "working", "the top card goes off-blocked → working immediately")
        finally:
            jd.GOALDIR = saved


class Distiller(unittest.TestCase):
    """The distiller (the user 2026-06-17): when a TOP completes, summarize the goal's full WORK history —
    its trail + subtree trails across all open→done cycles (DISCONTINUOUS; never the unrelated work
    between) — into node["summary"] for the card modal. Event-gated per goal (distilledMt vs mt)."""

    def _setup(self, records):
        td = Path(tempfile.mkdtemp())
        cdir = td / "launchdir"; cdir.mkdir()
        proj = td / "projects"
        pdir = proj / jd.re.sub(r"[/.]", "-", os.path.realpath(str(cdir)))
        pdir.mkdir(parents=True)
        path = pdir / (SID + ".jsonl")
        path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
        names = td / "names"; names.mkdir()
        (names / SID).write_text("testsess\t%s\t#abcdef\n" % str(cdir))
        self._saved = (jd.NAMES, jd.PROJECTS, jd.GOALDIR, jd.STATESDIR, jd.distill_llm)
        jd.NAMES, jd.PROJECTS, jd.GOALDIR, jd.STATESDIR = names, proj, td / "goals", td / "states"
        jd._PARSE_CACHE.clear()
        return str(path)

    def tearDown(self):
        if hasattr(self, "_saved"):
            (jd.NAMES, jd.PROJECTS, jd.GOALDIR, jd.STATESDIR, jd.distill_llm) = self._saved
            jd._PARSE_CACHE.clear()

    def test_distills_completed_top_from_its_discontinuous_trail(self):
        records = [uline(T0, "do part one", "u1", ps="typed"),
                   aline(T0 + 10, "did part one", "a1", "u1", stop="end_turn"),
                   uline(T0 + 100, "an unrelated other thing", "u2", "a1", ps="typed"),
                   aline(T0 + 110, "did the unrelated thing", "a2", "u2", stop="end_turn"),
                   uline(T0 + 200, "now finish part two", "u3", "a2", ps="typed"),
                   aline(T0 + 210, "finished part two", "a3", "u3", stop="end_turn")]
        path = self._setup(records)
        now = T0 + 5000
        session = jd.parsed_session(SID, [path], now)
        s1 = em.segments(session["turns"][0])[0]["id"]      # part one
        s3 = em.segments(session["turns"][2])[0]["id"]      # part two (turn 2 = unrelated work, NOT in the trail)
        gid = SID + ":g1"
        jd.save_goals(SID, {"rompUuid": SID, "seq": 1, "status": {gid: "completed"}, "placements": {},
                            "nodes": {gid: {"id": gid, "text": "Build the thing", "parentId": None,
                                            "nodeComplete": True, "blocked": False, "cleared": False,
                                            "trail": [s1, s3], "t": T0, "mt": T0 + 210}}})
        captured = {}

        def fake_distill(goal_text, work_text):
            captured["goal"], captured["work"] = goal_text, work_text
            return "Part one and part two delivered."
        jd.distill_llm = fake_distill
        self.assertEqual(jd.run_distill(now=now), 1, "the completed top is distilled")
        st = jd.load_goals(SID)
        self.assertEqual(st["nodes"][gid]["summary"], "Part one and part two delivered.")
        self.assertEqual(st["nodes"][gid]["distilledMt"], T0 + 210, "distilledMt records the completion it summarized")
        self.assertIn("part one", captured["work"])
        self.assertIn("part two", captured["work"])
        self.assertNotIn("unrelated", captured["work"], "only the goal's OWN trail segs, not the work between cycles")
        calls = []                                          # event-gated: re-running distills nothing
        jd.distill_llm = lambda g, w: (calls.append(1), "x")[1]
        self.assertEqual(jd.run_distill(now=now), 0)
        self.assertEqual(calls, [], "a goal already distilled at this mt is not re-distilled")

    def test_redistills_only_after_mt_advances(self):
        records = [uline(T0, "x", "u1", ps="typed"), aline(T0 + 10, "done", "a1", "u1", stop="end_turn")]
        path = self._setup(records)
        now = T0 + 5000
        s1 = em.segments(jd.parsed_session(SID, [path], now)["turns"][0])[0]["id"]
        gid = SID + ":g1"
        jd.save_goals(SID, {"rompUuid": SID, "seq": 1, "status": {gid: "completed"}, "placements": {},
                            "nodes": {gid: {"id": gid, "text": "G", "parentId": None, "nodeComplete": True,
                                            "blocked": False, "cleared": False, "trail": [s1], "t": T0,
                                            "mt": T0 + 10, "distilledMt": T0 + 10, "summary": "old"}}})
        jd.distill_llm = lambda g, w: "fresh"
        self.assertEqual(jd.run_distill(now=now), 0, "already distilled at this mt -> no-op")
        st = jd.load_goals(SID); st["nodes"][gid]["mt"] = T0 + 999; jd.save_goals(SID, st)   # reopened + re-completed
        self.assertEqual(jd.run_distill(now=now), 1, "mt advanced (re-completed) -> re-distill")
        self.assertEqual(jd.load_goals(SID)["nodes"][gid]["summary"], "fresh")

    def test_prompt_asks_for_artifact_or_summary(self):
        for phrase in ("concrete ARTIFACT", "copy", "discontinuous"):
            self.assertIn(phrase, jd.DISTILL_SYS, phrase)


class RunTriage(unittest.TestCase):
    """run_triage is the TRIAGE-tier sequence as one unit (so the kernel can run it parallel to the
    always-on index tier): plan → close → courier → group → distill, in that order."""

    def test_runs_the_sequence_in_order(self):
        calls = []
        saved = (jd.run_plan, jd.run_close, jd.run_courier, jd.run_group, jd.run_distill)
        jd.run_plan = lambda **k: (calls.append("plan"), 3)[1]
        jd.run_close = lambda **k: calls.append("close")
        jd.run_courier = lambda **k: calls.append("courier")
        jd.run_group = lambda **k: calls.append("group")
        jd.run_distill = lambda **k: calls.append("distill")
        try:
            placed = jd.run_triage(now=NOW)
        finally:
            (jd.run_plan, jd.run_close, jd.run_courier, jd.run_group, jd.run_distill) = saved
        self.assertEqual(placed, 3, "returns the planner's placement count")
        self.assertEqual(calls, ["plan", "close", "courier", "group", "distill"],
                         "plan → close → courier → group → distill (closer/grouper/distiller on by default)")


class JudgeUsageLog(unittest.TestCase):
    """Per-call token/cost logging (judge_ui 2026-06-17): _judge_run unwraps claude -p's JSON envelope to
    .result and appends one usage line to USAGE; fully defensive — an envelope without a result falls back
    to raw stdout and logs nothing, never breaking the call."""

    def test_unwraps_result_and_logs_usage(self):
        import unittest.mock as mock
        wrapper = json.dumps({"result": '{"ops":[]}',
                              "usage": {"input_tokens": 100, "output_tokens": 20,
                                        "cache_creation_input_tokens": 5, "cache_read_input_tokens": 50},
                              "duration_ms": 1234, "total_cost_usd": 0.0009})

        class _P:
            stdout = wrapper
        td = Path(tempfile.mkdtemp()); saved = jd.USAGE
        jd.USAGE = td / "judge-usage.jsonl"; jd._judge_ctx.fsid = "FSID-X"
        try:
            with mock.patch.object(jd.subprocess, "run", return_value=_P()):
                out = jd._judge_run(jd.TRIAGE_MODEL, "sys", "user", judge="planner")
        finally:
            jd.USAGE = saved; jd._judge_ctx.fsid = None
        self.assertEqual(out, '{"ops":[]}', "_judge_run returns the unwrapped .result text (callers unchanged)")
        rec = json.loads((td / "judge-usage.jsonl").read_text().strip())
        self.assertEqual((rec["judge"], rec["tier"], rec["fsid"]), ("planner", "triage", "FSID-X"))
        self.assertEqual((rec["in"], rec["out"], rec["cache_w"], rec["cache_r"]), (100, 20, 5, 50))
        self.assertEqual((rec["ms"], rec["cost"]), (1234, 0.0009))

    def test_unparseable_envelope_falls_back_to_raw_and_logs_nothing(self):
        import unittest.mock as mock

        class _P:
            stdout = '{"ops":[]}'                      # bare model JSON, not an envelope (no "result" key)
        td = Path(tempfile.mkdtemp()); saved = jd.USAGE
        jd.USAGE = td / "judge-usage.jsonl"
        try:
            with mock.patch.object(jd.subprocess, "run", return_value=_P()):
                out = jd._judge_run(jd.TRIAGE_MODEL, "s", "u", judge="planner")
        finally:
            jd.USAGE = saved
        self.assertEqual(out, '{"ops":[]}', "no envelope → raw stdout (defensive; callers' _json_obj still parses)")
        self.assertFalse((td / "judge-usage.jsonl").exists(), "nothing logged when there's no usage envelope")


if __name__ == "__main__":
    unittest.main(verbosity=2)
