#!/usr/bin/env python3
"""A parallel tool batch parses and renders whole while its results arrive (2026-09-23).

When the model makes several tool calls in one message, the Claude CLI writes each call as its own assistant record
of that message (one message id, chained call to call) and parents each RESULT at the record carrying its own call
(the record's sourceToolAssistantUUID). The transcript is then a tree, not a line: while the results land, the leaf is
whichever result (or the hook attachment after it) was written last, and the leaf-to-root walk passes through only
that result's call. The other calls and results hung off the spine, and the parse filed them as a rewound branch.

What that showed: a full chat frame built after the first result carried only the first call; the second and third
came back only when their own results landed (the reproduction lab caught it in 12 of 12 runs), and once the batch
was over the results of every call but the last were missing, so those tool rows never showed their output.

The parse now keeps the batch: an off-spine record that continues a spine call's own message, or that answers one of
its calls, is part of the conversation, with everything the CLI chained under it, up to a message someone sent (that
keeps the verdict a branch leaving the spine takes). Pinned here at the event model (every stage of a batch, results
in and out of order, a single call unchanged, a real rewind still dropping, the membership sets), at the chat build
(a frame per stage) and over the assembly document (a restored build equals the whole one). Synthetic transcripts
only: the notes-api demo world, invented commands and placeholder ids."""
import json
import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from test_chat_pages import NOW, SID, Harness, _strip, em, jd, km   # noqa: E402  the chat build harness (hermetic state root)

T0 = NOW - 3000
MSG = "msg_ba7c_calls"                          # the model message that carries the three calls
PID = "11111111-2222-3333-4444-0000000ba7c1"    # the turn's promptId: the CLI stamps the prompt and every result with it


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def prompt(t, uid, parent, text):
    return {"type": "user", "uuid": uid, "parentUuid": parent, "timestamp": iso(t), "promptSource": "typed",
            "promptId": PID, "cwd": "/w/notes-api", "message": {"role": "user", "content": text}}


def call(t, uid, parent, call_id, command, msg=MSG):
    """One tool_use block, as its own assistant record of the model message `msg` (the CLI writes one per block)."""
    return {"type": "assistant", "uuid": uid, "parentUuid": parent, "timestamp": iso(t), "cwd": "/w/notes-api",
            "message": {"id": msg, "role": "assistant", "model": "claude-test-1", "stop_reason": "tool_use",
                        "content": [{"type": "tool_use", "id": call_id, "name": "Bash", "input": {"command": command}}]}}


def result(t, uid, call_uid, call_id, out):
    """A call's result, parented at the record carrying its own call (not at the previous record)."""
    return {"type": "user", "uuid": uid, "parentUuid": call_uid, "sourceToolAssistantUUID": call_uid, "promptId": PID,
            "timestamp": iso(t), "toolUseResult": {"stdout": out, "stderr": "", "interrupted": False},
            "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": call_id, "content": out}]}}


def hook(t, uid, parent):
    """The PostToolUse hook's attachment the CLI chains after a result: no atom, but it can be the leaf."""
    return {"type": "attachment", "uuid": uid, "parentUuid": parent, "timestamp": iso(t),
            "attachment": {"type": "hook_non_blocking_error", "hookEvent": "PostToolUse", "stderr": "", "exitCode": 1}}


def reply(t, uid, parent, text, msg="msg_ba7c_reply"):
    return {"type": "assistant", "uuid": uid, "parentUuid": parent, "timestamp": iso(t), "cwd": "/w/notes-api",
            "message": {"id": msg, "role": "assistant", "model": "claude-test-1", "stop_reason": "end_turn",
                        "content": [{"type": "text", "text": text}]}}


CALLS = [prompt(T0, "p1", None, "run the three notes-api checks at once, then summarize"),
         call(T0 + 5, "ca", "p1", "toolu_a", "uv run pytest -q tests/test_search.py"),
         call(T0 + 5, "cb", "ca", "toolu_b", "uv run pytest -q tests/test_notes.py"),
         call(T0 + 5, "cc", "cb", "toolu_c", "uv run ruff check notes_api")]
RES_A = [result(T0 + 15, "ra", "ca", "toolu_a", "search: 12 passed"), hook(T0 + 15, "ha", "ra")]
RES_B = [result(T0 + 17, "rb", "cb", "toolu_b", "notes: 30 passed"), hook(T0 + 17, "hb", "rb")]
RES_C = [result(T0 + 19, "rc", "cc", "toolu_c", "ruff: all checks passed"), hook(T0 + 19, "hc", "rc")]
REPLY = [reply(T0 + 25, "r1", "hc", "All three checks passed: search, notes and lint.")]


class _Batch(Harness):
    def setUp(self):
        super().setUp()
        (jd.STATE / "session-hosts").write_text("off\n")   # this state root is the test's own: no per-session host spawns

    def append(self, recs):
        with open(self.leaf, "a") as f:
            f.write("".join(json.dumps(r) + "\n" for r in recs))

    def parse(self):
        return em.parse_session(self.leaf, rompuuid=SID, name="web", dir="/w/notes-api", candidate_files=[self.leaf],
                                states=None, postal_log=[], now=NOW)

    def atoms(self, out=None):
        out = out or self.parse()
        return [a.get("uuid") for t in out["turns"] for a in t["atoms"]]

    def cold_atoms(self):
        self.fresh()
        return self.atoms()

    def membership(self):
        return em.chain_membership(self.leaf, candidate_files=[self.leaf], rompuuid=SID)


class EventModel(_Batch):
    def test_every_call_is_kept_at_every_stage_of_the_batch(self):
        stages = [(CALLS, ["p1", "ca", "cb", "cc"]),
                  (RES_A, ["p1", "ca", "cb", "cc", "ra"]),
                  (RES_B, ["p1", "ca", "cb", "cc", "ra", "rb"]),
                  (RES_C, ["p1", "ca", "cb", "cc", "ra", "rb", "rc"]),
                  (REPLY, ["p1", "ca", "cb", "cc", "ra", "rb", "rc", "r1"])]
        for recs, want in stages:
            self.append(recs)
            with self.subTest(leaf=recs[-1]["uuid"]):
                self.assertEqual(self.atoms(), want, "the calls in the order the model issued them, each result as it lands")
        self.assertEqual(self.cold_atoms(), stages[-1][1], "a cold parse of the finished batch agrees with the folded one")

    def test_the_folded_parse_equals_a_cold_parse_after_each_result(self):
        self.append(CALLS)
        self.parse()
        for recs in (RES_A, RES_B, RES_C, REPLY):
            self.append(recs)
            warm = self.atoms()
            self.assertEqual(self.cold_atoms(), warm, "warm == cold after %s" % recs[0]["uuid"])

    def test_results_landing_out_of_order_keep_every_call(self):
        self.append(CALLS)
        late_c = [result(T0 + 12, "rc", "cc", "toolu_c", "ruff: all checks passed"), hook(T0 + 12, "hc", "rc")]
        self.append(late_c)
        self.assertEqual(self.atoms(), ["p1", "ca", "cb", "cc", "rc"])
        self.append(RES_A)                                  # the leaf is now under the FIRST call: the others hang off it
        self.assertEqual(self.atoms(), ["p1", "ca", "cb", "cc", "rc", "ra"])
        self.append(RES_B + [reply(T0 + 25, "r1", "hb", "All three checks passed.")])
        self.assertEqual(self.atoms(), ["p1", "ca", "cb", "cc", "rc", "ra", "rb", "r1"])
        self.assertEqual(self.cold_atoms(), ["p1", "ca", "cb", "cc", "rc", "ra", "rb", "r1"])

    def test_the_membership_sets_hold_the_batch_as_kept_never_as_rewound(self):
        self.append(CALLS + RES_A)
        mem = self.membership()
        self.assertEqual(mem["rewind"], set(), "a call waiting on its result is not a rewound branch")
        self.assertTrue({"ca", "cb", "cc", "ra", "ha"} <= mem["kept"])
        self.append(RES_B + RES_C + REPLY)
        mem = self.membership()
        self.assertEqual(mem["rewind"], set(), "the earlier results are not rewound once the reply chains off the last")
        self.assertTrue({"ca", "cb", "cc", "ra", "ha", "rb", "hb", "rc", "hc", "r1"} <= mem["kept"])

    def test_a_single_tool_call_parses_as_before(self):
        self.append([prompt(T0, "p1", None, "run the search tests"),
                     call(T0 + 5, "c1", "p1", "toolu_1", "uv run pytest -q tests/test_search.py"),
                     result(T0 + 15, "r1res", "c1", "toolu_1", "search: 12 passed"), hook(T0 + 15, "h1", "r1res"),
                     reply(T0 + 20, "r1", "h1", "The search tests pass.")])
        self.assertEqual(self.atoms(), ["p1", "c1", "r1res", "r1"])
        mem = self.membership()
        self.assertEqual(mem["rewind"], set())

    def test_a_rewind_after_a_batch_still_drops_the_abandoned_exchange(self):
        # the user deleted their follow-up and asked something else: the new prompt re-parents at the batch's reply, and
        # the abandoned prompt and its reply stay dropped, batch or no batch
        self.append(CALLS + RES_A + RES_B + RES_C + REPLY + [
            prompt(T0 + 60, "u2", "r1", "and the export endpoint?"),
            reply(T0 + 70, "a2", "u2", "The export endpoint has no tests yet.", msg="msg_ba7c_a2"),
            prompt(T0 + 90, "u3", "r1", "actually, look at the search ranking first"),
            reply(T0 + 100, "a3", "u3", "Search ranking sorts by recency only.", msg="msg_ba7c_a3")])
        uuids = self.atoms()
        self.assertEqual(uuids, ["p1", "ca", "cb", "cc", "ra", "rb", "rc", "r1", "u3", "a3"])
        self.assertTrue({"u2", "a2"} <= self.membership()["rewind"])

    def test_a_prompt_hanging_under_a_batch_record_keeps_the_rewind_verdict(self):
        # the batch keep covers what the CLI chained under an off-spine call or result, never a message someone sent:
        # a prompt parented below a sibling result, off the leaf's path, stays a rewound branch
        self.append(CALLS + RES_A + RES_B + [prompt(T0 + 18, "px", "hb", "wait, skip the lint run"),
                                             reply(T0 + 18, "ax", "px", "Skipping lint.", msg="msg_ba7c_ax")]
                    + RES_C + REPLY)
        uuids = self.atoms()
        self.assertIn("rb", uuids, "the sibling result above the prompt is kept")
        self.assertNotIn("px", uuids)
        self.assertNotIn("ax", uuids)
        self.assertTrue({"px", "ax"} <= self.membership()["rewind"])


class ChatFrame(_Batch):
    def tools(self):
        self.fresh()
        m = km.build_session(SID, NOW, {}, floor=0)
        return [(e["uuid"], e.get("toolUseId"), e.get("output"), e.get("resultUuid"))
                for e in _strip(m["events"]) if e.get("kind") == "tool"]

    def test_a_full_frame_carries_every_call_in_order_with_results_filling_in(self):
        self.append(CALLS)
        pending = [("ca", "toolu_a", "", None), ("cb", "toolu_b", "", None), ("cc", "toolu_c", "", None)]
        self.assertEqual(self.tools(), pending, "before any result: three pending calls")
        self.append(RES_A)
        self.assertEqual(self.tools(), [("ca", "toolu_a", "search: 12 passed", "ra"),
                                        ("cb", "toolu_b", "", None), ("cc", "toolu_c", "", None)],
                         "after the first result: that call shows it, the other two stay pending")
        self.append(RES_B)
        self.assertEqual(self.tools(), [("ca", "toolu_a", "search: 12 passed", "ra"),
                                        ("cb", "toolu_b", "notes: 30 passed", "rb"), ("cc", "toolu_c", "", None)])
        self.append(RES_C + REPLY)
        self.assertEqual(self.tools(), [("ca", "toolu_a", "search: 12 passed", "ra"),
                                        ("cb", "toolu_b", "notes: 30 passed", "rb"),
                                        ("cc", "toolu_c", "ruff: all checks passed", "rc")],
                         "after every result: all three complete")

    def test_a_single_tool_call_renders_as_before(self):
        self.append([prompt(T0, "p1", None, "run the search tests"),
                     call(T0 + 5, "c1", "p1", "toolu_1", "uv run pytest -q tests/test_search.py")])
        self.assertEqual(self.tools(), [("c1", "toolu_1", "", None)])
        self.append([result(T0 + 15, "r1res", "c1", "toolu_1", "search: 12 passed"), hook(T0 + 15, "h1", "r1res"),
                     reply(T0 + 20, "r1", "h1", "The search tests pass.")])
        self.assertEqual(self.tools(), [("c1", "toolu_1", "search: 12 passed", "r1res")])


class AssemblyDocument(_Batch):
    def test_a_restored_build_equals_the_whole_one_with_every_batch_result(self):
        # twelve settled turns, each a batch of three calls whose results land in call order: the document's cut falls
        # before the last settled turn, so most batches are pre-cut rows (their verdicts stored) and one is in the tail
        recs, parent = [], None
        for k in range(12):
            t, s = T0 - 40000 + 600 * k, "t%d" % k
            ids = [("%sc%d" % (s, i), "toolu_%s_%d" % (s, i)) for i in range(3)]
            recs.append(prompt(t, s + "p", parent, "turn %d: run the three notes-api checks at once" % k))
            prev = s + "p"
            for i, (cu, cid) in enumerate(ids):
                recs.append(call(t + 5, cu, prev, cid, "uv run pytest -q tests/test_part%d.py" % i, msg="msg_%s" % s))
                prev = cu
            for i, (cu, cid) in enumerate(ids):
                recs += [result(t + 10 + i, s + "r%d" % i, cu, cid, "part %d of turn %d: ok" % (i, k)),
                         hook(t + 10 + i, s + "h%d" % i, s + "r%d" % i)]
            recs.append(reply(t + 20, s + "a", s + "h2", "Turn %d: all three checks passed." % k, msg="msg_%s_r" % s))
            parent = s + "a"
        self.write(recs)
        whole = self.whole()
        outs = {e["toolUseId"]: e.get("output") for e in whole if e.get("kind") == "tool"}
        self.assertEqual(len(outs), 36)
        self.assertTrue(all(outs.values()), "every call of every batch shows its result: %r" % [k for k, v in outs.items() if not v])
        self.document()
        m = self.restored()
        floor = m["floor"]
        self.assertGreater(floor, 0, "the restored build renders from the cut")
        tail = _strip(m["events"])
        self.assertEqual(self.pages(floor, 4) + tail, whole, "the pre-cut batches restore exactly as the whole parse keeps them")


if __name__ == "__main__":
    unittest.main()
