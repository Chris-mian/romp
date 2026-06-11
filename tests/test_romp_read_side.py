#!/usr/bin/env python3
"""Read-side unit tests for the romp surfaces: the asks fold + origin detection
in scripts/romp-feed and the registry readers in scripts/romp-pipeline.

Run:  python3 tests/test_romp_read_side.py

Born from the 2026-06-09 incident day — every test here encodes either a
failure mode that reached production (see requests/corrections.jsonl in the
state dir) or a fold-semantics rule from REQUESTS.md that a future edit could
silently break. The model-judgment layer (ask splitting, REQ, LINK/DONE) is
deliberately NOT tested here: that layer is covered by the decision-log +
corrections replay on the pipeline side.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "bin")
sys.path.insert(0, SCRIPTS)                      # romp_colormap import inside the scripts

feed = SourceFileLoader("romp_feed_t", os.path.join(SCRIPTS, "romp-feed")).load_module()
pipe = SourceFileLoader("romp_pipeline_t", os.path.join(SCRIPTS, "romp-pipeline")).load_module()
feed.C.on = False                                # plain text: tests assert on substrings


def jl(*objs):
    return "".join(json.dumps(o) + "\n" for o in objs)


class RegistryFixture(unittest.TestCase):
    """Temp state dir wired into both modules; each test writes its own files."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="romp-test-")
        self.reqs = os.path.join(self.dir, "requests")
        self.summ = os.path.join(self.dir, "summaries")
        self.names = os.path.join(self.dir, "names")
        for d in (self.reqs, self.summ, self.names):
            os.makedirs(d)
        self._saved = (feed.REQS, feed.SUMM, feed.NAMES, pipe.REQS)
        feed.REQS, feed.SUMM, feed.NAMES = self.reqs, self.summ, self.names
        pipe.REQS = self.reqs

    def tearDown(self):
        feed.REQS, feed.SUMM, feed.NAMES, pipe.REQS = self._saved
        shutil.rmtree(self.dir, ignore_errors=True)

    def write(self, fname, content):
        with open(os.path.join(self.reqs if fname.endswith("jsonl") and not fname.startswith("s:")
                               else self.reqs, fname), "w") as f:
            f.write(content)

    def write_summary(self, sid, content):
        with open(os.path.join(self.summ, sid + ".jsonl"), "w") as f:
            f.write(content)


AGENTS = {"s1": {"name": "alpha", "dir": "", "rgb": None}}


class TestAsksFold(RegistryFixture):
    """ask_items() — the read-time fold rules from REQUESTS.md."""

    def test_amend_last_wins(self):
        self.write("nodes.jsonl", jl(
            {"kind": "ask", "id": "s1:100:aa#0", "sid": "s1", "turn_id": "s1:100:aa", "t": 100, "text": "original"},
            {"kind": "amend", "id": "s1:100:aa#0", "turn_id": "s1:200:bb", "t": 200, "text": "amended once"},
            {"kind": "amend", "id": "s1:100:aa#0", "turn_id": "s1:300:cc", "t": 300, "text": "amended twice"},
        ))
        items = feed.ask_items(AGENTS)
        self.assertEqual(len(items), 1)
        self.assertIn("amended twice", items[0]["did"])

    def test_cleared_ask_dropped(self):
        self.write("nodes.jsonl", jl(
            {"kind": "ask", "id": "s1:100:aa#0", "sid": "s1", "turn_id": "s1:100:aa", "t": 100, "text": "keep"},
            {"kind": "ask", "id": "s1:100:aa#1", "sid": "s1", "turn_id": "s1:100:aa", "t": 100, "text": "drop"},
        ))
        with open(os.path.join(self.reqs, "cleared.jsonl"), "w") as f:
            f.write(jl({"id": "s1:100:aa#1", "t": 500}))
        items = feed.ask_items(AGENTS)
        self.assertEqual([1 for i in items if "drop" in i["did"]], [])
        self.assertEqual(len(items), 1)

    def test_parents_walk_multi_hop_rollup(self):
        # a DONE on a handoff-of-a-handoff rolls all the way up: the whole
        # delegated chain ends DONE, so the root ask completes (leaf-path
        # accounting — nothing need ever be filed directly on the ask)
        self.write("nodes.jsonl", jl(
            {"kind": "ask", "id": "s1:100:aa#0", "sid": "s1", "turn_id": "s1:100:aa", "t": 100, "text": "root ask"},
            {"kind": "internal", "id": "m1", "from_sid": "s1", "to_sid": "s2", "t": 110, "text": "hop1"},
            {"kind": "parents", "id": "m1", "parent_ids": ["s1:100:aa#0"], "t": 110},
            {"kind": "internal", "id": "m2", "from_sid": "s2", "to_sid": "s3", "t": 120, "text": "hop2"},
            {"kind": "parents", "id": "m2", "parent_ids": ["m1"], "t": 120},
        ))
        with open(os.path.join(self.reqs, "links.jsonl"), "w") as f:
            f.write(jl({"kind": "link", "reply_id": "s3:130:dd", "request_ids": ["m2"], "relevance": "DONE", "sid": "s3", "t": 130}))
        items = feed.ask_items(AGENTS)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["column"], "completed")
        self.assertEqual(items[0]["t"], 130)     # link bumps last-activity

    def test_multi_root_parents_plural(self):
        # one handoff serving TWO asks: a DONE on it completes BOTH roots
        self.write("nodes.jsonl", jl(
            {"kind": "ask", "id": "a#0", "sid": "s1", "turn_id": "s1:100:aa", "t": 100, "text": "ask one"},
            {"kind": "ask", "id": "a#1", "sid": "s1", "turn_id": "s1:100:aa", "t": 100, "text": "ask two"},
            {"kind": "internal", "id": "m1", "from_sid": "s1", "to_sid": "s2", "t": 110, "text": "serves both"},
            {"kind": "parents", "id": "m1", "parent_ids": ["a#0", "a#1"], "t": 110},
        ))
        with open(os.path.join(self.reqs, "links.jsonl"), "w") as f:
            f.write(jl({"kind": "link", "reply_id": "s2:120:ee", "request_ids": ["m1"], "relevance": "DONE", "sid": "s2", "t": 120}))
        items = feed.ask_items(AGENTS)
        self.assertEqual(len(items), 2)
        self.assertTrue(all(i["column"] == "completed" for i in items))

    def test_parents_cycle_terminates(self):
        # malformed cycle in parent edges must not hang the fold
        self.write("nodes.jsonl", jl(
            {"kind": "ask", "id": "a#0", "sid": "s1", "turn_id": "s1:100:aa", "t": 100, "text": "root"},
            {"kind": "internal", "id": "m1", "from_sid": "s1", "to_sid": "s2", "t": 110, "text": "x"},
            {"kind": "internal", "id": "m2", "from_sid": "s2", "to_sid": "s1", "t": 111, "text": "y"},
            {"kind": "parents", "id": "m1", "parent_ids": ["m2"], "t": 110},
            {"kind": "parents", "id": "m2", "parent_ids": ["m1"], "t": 111},
        ))
        with open(os.path.join(self.reqs, "links.jsonl"), "w") as f:
            f.write(jl({"kind": "link", "reply_id": "r", "request_ids": ["m1"], "relevance": "DONE", "sid": "s2", "t": 120}))
        items = feed.ask_items(AGENTS)          # cycle reaches no root: tally lands nowhere
        self.assertEqual(len(items), 1)
        self.assertNotIn("1 done", items[0]["did"])

    def test_unanswered_decision_routes_needs_input(self):
        # an open question (no later the user turn in that session) → needs_input
        self.write("nodes.jsonl", jl(
            {"kind": "ask", "id": "a#0", "sid": "s1", "turn_id": "s1:100:aa", "t": 100, "text": "root"}))
        with open(os.path.join(self.reqs, "links.jsonl"), "w") as f:
            f.write(jl({"kind": "link", "reply_id": "r", "request_ids": ["a#0"], "relevance": "DECISION", "sid": "s1", "t": 120}))
        items = feed.ask_items(AGENTS)
        self.assertEqual(items[0]["column"], "needs_input")
        self.assertIn("needs you — alpha", items[0]["did"])

    # ---- DAG path accounting (the user's status model, 2026-06-09) ----

    def test_answered_decision_crossed_off(self):
        # The user's next typed turn in the asking session ANSWERS the question:
        # the ask reverts to open/in-flight, not needs_input — kills the
        # forever-"1 needs you" counter bug.
        self.write("nodes.jsonl", jl(
            {"kind": "ask", "id": "a#0", "sid": "s1", "turn_id": "s1:100:aa", "t": 100, "text": "root"}))
        with open(os.path.join(self.reqs, "links.jsonl"), "w") as f:
            f.write(jl({"kind": "link", "reply_id": "r", "request_ids": ["a#0"], "relevance": "DECISION", "sid": "s1", "t": 120}))
        self.write_summary("s1", jl(
            {"kind": "request", "id": "s1:200:bb", "t": 205, "text": "my answer"}))
        items = feed.ask_items(AGENTS)
        self.assertEqual(items[0]["column"], "asks")
        self.assertNotIn("needs you", items[0]["did"])

    def test_all_paths_done_completes(self):
        # every node (root + handoff) terminal-DONE → completed
        self.write("nodes.jsonl", jl(
            {"kind": "ask", "id": "a#0", "sid": "s1", "turn_id": "s1:100:aa", "t": 100, "text": "root"},
            {"kind": "internal", "id": "m1", "from_sid": "s1", "to_sid": "s2", "t": 110, "text": "hop"},
            {"kind": "parents", "id": "m1", "parent_ids": ["a#0"], "t": 110},
        ))
        with open(os.path.join(self.reqs, "links.jsonl"), "w") as f:
            f.write(jl(
                {"kind": "link", "reply_id": "r1", "request_ids": ["m1"], "relevance": "DONE", "sid": "s2", "t": 120},
                {"kind": "link", "reply_id": "r2", "request_ids": ["a#0"], "relevance": "DONE", "sid": "s1", "t": 130}))
        items = feed.ask_items(AGENTS)
        self.assertEqual(items[0]["column"], "completed")
        self.assertIn("all done", items[0]["did"])

    def test_open_branch_holds_ask_open_with_drop_point(self):
        # root DONE but the handoff never got a terminal reply: NOT completed —
        # the drop point names the session that owes the user a completion/question
        self.write("nodes.jsonl", jl(
            {"kind": "ask", "id": "a#0", "sid": "s1", "turn_id": "s1:100:aa", "t": 100, "text": "root"},
            {"kind": "internal", "id": "m1", "from_sid": "s1", "to_sid": "s2", "t": 110, "text": "hop"},
            {"kind": "parents", "id": "m1", "parent_ids": ["a#0"], "t": 110},
        ))
        with open(os.path.join(self.reqs, "links.jsonl"), "w") as f:
            f.write(jl({"kind": "link", "reply_id": "r2", "request_ids": ["a#0"], "relevance": "DONE", "sid": "s1", "t": 130}))
        agents = dict(AGENTS, s2={"name": "beta", "dir": "", "rgb": None})
        items = feed.ask_items(agents)
        self.assertEqual(items[0]["column"], "asks")
        self.assertIn("waiting on beta", items[0]["did"])

    def test_later_work_reopens_a_done_node(self):
        # newest link wins per node: DETAILS after a DONE = work continued
        self.write("nodes.jsonl", jl(
            {"kind": "ask", "id": "a#0", "sid": "s1", "turn_id": "s1:100:aa", "t": 100, "text": "root"}))
        with open(os.path.join(self.reqs, "links.jsonl"), "w") as f:
            f.write(jl(
                {"kind": "link", "reply_id": "r1", "request_ids": ["a#0"], "relevance": "DONE", "sid": "s1", "t": 120},
                {"kind": "link", "reply_id": "r2", "request_ids": ["a#0"], "relevance": "DETAILS", "sid": "s1", "t": 130}))
        items = feed.ask_items(AGENTS)
        self.assertEqual(items[0]["column"], "asks")

    # ---- clear vs late-work race (resurrection rule) ----

    def test_post_clear_question_resurrects(self):
        # a question ARRIVING after the clear must never be invisible: the
        # card resurrects into needs_input
        self.write("nodes.jsonl", jl(
            {"kind": "ask", "id": "a#0", "sid": "s1", "turn_id": "s1:100:aa", "t": 100, "text": "root"}))
        with open(os.path.join(self.reqs, "cleared.jsonl"), "w") as f:
            f.write(jl({"id": "a#0", "t": 200}))
        with open(os.path.join(self.reqs, "links.jsonl"), "w") as f:
            f.write(jl({"kind": "link", "reply_id": "r", "request_ids": ["a#0"], "relevance": "DECISION", "sid": "s1", "t": 300}))
        items = feed.ask_items(AGENTS)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["column"], "needs_input")
        self.assertIn("reopened after clear", items[0]["did"])

    def test_clearing_a_seen_question_sticks(self):
        # The user cleared WHILE the question was showing → deliberate dismissal;
        # a pre-clear question never resurrects
        self.write("nodes.jsonl", jl(
            {"kind": "ask", "id": "a#0", "sid": "s1", "turn_id": "s1:100:aa", "t": 100, "text": "root"}))
        with open(os.path.join(self.reqs, "links.jsonl"), "w") as f:
            f.write(jl({"kind": "link", "reply_id": "r", "request_ids": ["a#0"], "relevance": "DECISION", "sid": "s1", "t": 120}))
        with open(os.path.join(self.reqs, "cleared.jsonl"), "w") as f:
            f.write(jl({"id": "a#0", "t": 200}))
        self.assertEqual(feed.ask_items(AGENTS), [])

    def test_reclear_covers_the_resurrecting_question(self):
        # resurrect (question t=300 > clear t=200), the user clears AGAIN (t=400):
        # re-clears append; the newest clear wins and re-hides the card
        self.write("nodes.jsonl", jl(
            {"kind": "ask", "id": "a#0", "sid": "s1", "turn_id": "s1:100:aa", "t": 100, "text": "root"}))
        with open(os.path.join(self.reqs, "links.jsonl"), "w") as f:
            f.write(jl({"kind": "link", "reply_id": "r", "request_ids": ["a#0"], "relevance": "DECISION", "sid": "s1", "t": 300}))
        with open(os.path.join(self.reqs, "cleared.jsonl"), "w") as f:
            f.write(jl({"id": "a#0", "t": 200}, {"id": "a#0", "t": 400}))
        self.assertEqual(feed.ask_items(AGENTS), [])

    def test_answering_a_resurrected_question_rehides(self):
        # The user ANSWERS the post-clear question instead of re-clearing: the
        # crossoff closes it, so the cleared card sinks back out of view
        self.write("nodes.jsonl", jl(
            {"kind": "ask", "id": "a#0", "sid": "s1", "turn_id": "s1:100:aa", "t": 100, "text": "root"}))
        with open(os.path.join(self.reqs, "links.jsonl"), "w") as f:
            f.write(jl({"kind": "link", "reply_id": "r", "request_ids": ["a#0"], "relevance": "DECISION", "sid": "s1", "t": 300}))
        with open(os.path.join(self.reqs, "cleared.jsonl"), "w") as f:
            f.write(jl({"id": "a#0", "t": 200}))
        self.write_summary("s1", jl(
            {"kind": "request", "id": "s1:350:bb", "t": 355, "text": "my answer"}))
        self.assertEqual(feed.ask_items(AGENTS), [])

    def test_post_clear_done_does_not_resurrect(self):
        # late DONE/DETAILS on a cleared ask stay silent — only a question
        # warrants resurrection (a completion you retired isn't your problem)
        self.write("nodes.jsonl", jl(
            {"kind": "ask", "id": "a#0", "sid": "s1", "turn_id": "s1:100:aa", "t": 100, "text": "root"}))
        with open(os.path.join(self.reqs, "cleared.jsonl"), "w") as f:
            f.write(jl({"id": "a#0", "t": 200}))
        with open(os.path.join(self.reqs, "links.jsonl"), "w") as f:
            f.write(jl({"kind": "link", "reply_id": "r", "request_ids": ["a#0"], "relevance": "DONE", "sid": "s1", "t": 300}))
        self.assertEqual(feed.ask_items(AGENTS), [])

    # ---- leaf-path accounting (the user's ruling 2026-06-10: an ask is judged
    # by where its paths END; intermediate restatements are transparent) ----

    def test_delegated_chain_completes_through_restatements(self):
        # the stuck-card shape from the live registry: a restatement (DETAILS)
        # sits directly on the ask and on the mid-chain handoff, but the leaf
        # ends DONE — the path ended in done, so the ask completes. Under the
        # old every-node rule this card hung in ASKS forever.
        self.write("nodes.jsonl", jl(
            {"kind": "ask", "id": "a#0", "sid": "s1", "turn_id": "s1:100:aa", "t": 100, "text": "root"},
            {"kind": "internal", "id": "m1", "from_sid": "s1", "to_sid": "s2", "t": 110, "text": "hop1"},
            {"kind": "parents", "id": "m1", "parent_ids": ["a#0"], "t": 110},
            {"kind": "internal", "id": "m2", "from_sid": "s2", "to_sid": "s3", "t": 120, "text": "hop2"},
            {"kind": "parents", "id": "m2", "parent_ids": ["m1"], "t": 120},
        ))
        with open(os.path.join(self.reqs, "links.jsonl"), "w") as f:
            f.write(jl(
                {"kind": "link", "reply_id": "r0", "request_ids": ["a#0"], "relevance": "DETAILS", "sid": "s1", "t": 105},
                {"kind": "link", "reply_id": "r1", "request_ids": ["m1"], "relevance": "DETAILS", "sid": "s2", "t": 115},
                {"kind": "link", "reply_id": "r2", "request_ids": ["m2"], "relevance": "DONE", "sid": "s3", "t": 130}))
        items = feed.ask_items(AGENTS)
        self.assertEqual(items[0]["column"], "completed")

    def test_drop_point_is_the_open_leaf_not_intermediates(self):
        # only the LEAF where the path actually ended owes the user a terminal;
        # the open intermediate hop is transparent (its work continued down)
        self.write("nodes.jsonl", jl(
            {"kind": "ask", "id": "a#0", "sid": "s1", "turn_id": "s1:100:aa", "t": 100, "text": "root"},
            {"kind": "internal", "id": "m1", "from_sid": "s1", "to_sid": "s2", "t": 110, "text": "hop1"},
            {"kind": "parents", "id": "m1", "parent_ids": ["a#0"], "t": 110},
            {"kind": "internal", "id": "m2", "from_sid": "s2", "to_sid": "s3", "t": 120, "text": "hop2"},
            {"kind": "parents", "id": "m2", "parent_ids": ["m1"], "t": 120},
        ))
        agents = dict(AGENTS, s2={"name": "beta", "dir": "", "rgb": None},
                      s3={"name": "gamma", "dir": "", "rgb": None})
        items = feed.ask_items(agents)
        self.assertEqual(items[0]["column"], "asks")
        self.assertIn("waiting on gamma", items[0]["did"])
        self.assertNotIn("waiting on beta", items[0]["did"])

    def test_correction_done_closes_stale_leaf(self):
        # The user adjudicates: a leaf whose last word was a mid-work progress
        # note gets a corrections.jsonl DONE — the card completes, and the
        # row doubles as the linker's training label
        self.write("nodes.jsonl", jl(
            {"kind": "ask", "id": "a#0", "sid": "s1", "turn_id": "s1:100:aa", "t": 100, "text": "root"},
            {"kind": "internal", "id": "m1", "from_sid": "s1", "to_sid": "s2", "t": 110, "text": "hop"},
            {"kind": "parents", "id": "m1", "parent_ids": ["a#0"], "t": 110},
        ))
        with open(os.path.join(self.reqs, "links.jsonl"), "w") as f:
            f.write(jl(
                {"kind": "link", "reply_id": "r1", "request_ids": ["m1"], "relevance": "DONE", "sid": "s2", "t": 120},
                {"kind": "link", "reply_id": "r2", "request_ids": ["m1"], "relevance": "DETAILS", "sid": "s2", "t": 130}))
        with open(os.path.join(self.reqs, "corrections.jsonl"), "w") as f:
            f.write(jl({"t": 400, "by_sid": "feed-panel", "kind": "link", "decision_ref": "r2",
                        "should_have": {"request_ids": ["m1"], "relevance": "DONE"},
                        "note": "marked done by the user"}))
        items = feed.ask_items(AGENTS)
        self.assertEqual(items[0]["column"], "completed")

    # ---- needs-input taxonomy (the user's ruling 2026-06-10: actions and ideas
    # route to needs_input, not just blocked questions) ----

    def test_action_routes_needs_input_and_survives_typed_turn(self):
        # 'reload VS Code to pick this up' — the user typing in the session does
        # NOT cross it off (he may have typed without acting)
        self.write("nodes.jsonl", jl(
            {"kind": "ask", "id": "a#0", "sid": "s1", "turn_id": "s1:100:aa", "t": 100, "text": "root"}))
        with open(os.path.join(self.reqs, "links.jsonl"), "w") as f:
            f.write(jl({"kind": "link", "reply_id": "r", "request_ids": ["a#0"], "relevance": "ACTION", "sid": "s1", "t": 120}))
        self.write_summary("s1", jl(
            {"kind": "request", "id": "s1:200:bb", "t": 205, "text": "typed but did not reload"}))
        items = feed.ask_items(AGENTS)
        self.assertEqual(items[0]["column"], "needs_input")

    def test_action_closed_by_did_it_correction(self):
        # the "Done — I did it" click writes a DONE correction; newest-wins closes
        self.write("nodes.jsonl", jl(
            {"kind": "ask", "id": "a#0", "sid": "s1", "turn_id": "s1:100:aa", "t": 100, "text": "root"}))
        with open(os.path.join(self.reqs, "links.jsonl"), "w") as f:
            f.write(jl({"kind": "link", "reply_id": "r", "request_ids": ["a#0"], "relevance": "ACTION", "sid": "s1", "t": 120}))
        with open(os.path.join(self.reqs, "corrections.jsonl"), "w") as f:
            f.write(jl({"t": 400, "by_sid": "feed-panel", "kind": "link", "decision_ref": "r",
                        "should_have": {"request_ids": ["a#0"], "relevance": "DONE"}, "note": "did it"}))
        items = feed.ask_items(AGENTS)
        self.assertEqual(items[0]["column"], "completed")

    def test_idea_crossed_off_by_typed_turn(self):
        # a suggestion behaves like a question: the user's next typed turn in that
        # session is his reaction — the card drops back to in-flight
        self.write("nodes.jsonl", jl(
            {"kind": "ask", "id": "a#0", "sid": "s1", "turn_id": "s1:100:aa", "t": 100, "text": "root"}))
        with open(os.path.join(self.reqs, "links.jsonl"), "w") as f:
            f.write(jl({"kind": "link", "reply_id": "r", "request_ids": ["a#0"], "relevance": "IDEA", "sid": "s1", "t": 120}))
        items = feed.ask_items(AGENTS)
        self.assertEqual(items[0]["column"], "needs_input")
        self.write_summary("s1", jl(
            {"kind": "request", "id": "s1:200:bb", "t": 205, "text": "my reaction"}))
        items = feed.ask_items(AGENTS)
        self.assertEqual(items[0]["column"], "asks")

    def test_correction_is_a_reverdict_not_new_activity(self):
        # a correction closes the node (column flips) but must not bump the
        # card's recency — the work happened at the ORIGINAL report's time
        self.write("nodes.jsonl", jl(
            {"kind": "ask", "id": "a#0", "sid": "s1", "turn_id": "s1:100:aa", "t": 100, "text": "root"}))
        with open(os.path.join(self.reqs, "links.jsonl"), "w") as f:
            f.write(jl({"kind": "link", "reply_id": "r", "request_ids": ["a#0"], "relevance": "DETAILS", "sid": "s1", "t": 120}))
        with open(os.path.join(self.reqs, "corrections.jsonl"), "w") as f:
            f.write(jl({"t": 9999, "by_sid": "rejudge", "kind": "link", "decision_ref": "r",
                        "should_have": {"request_ids": ["a#0"], "relevance": "DONE"}, "note": "re-judged"}))
        items = feed.ask_items(AGENTS)
        self.assertEqual(items[0]["column"], "completed")
        self.assertEqual(items[0]["t"], 120)      # original report's time, not 9999

    def test_question_beats_done_for_column(self):
        # any open question routes the CARD to needs_input even when other
        # branches are done
        self.write("nodes.jsonl", jl(
            {"kind": "ask", "id": "a#0", "sid": "s1", "turn_id": "s1:100:aa", "t": 100, "text": "root"},
            {"kind": "internal", "id": "m1", "from_sid": "s1", "to_sid": "s2", "t": 110, "text": "hop"},
            {"kind": "parents", "id": "m1", "parent_ids": ["a#0"], "t": 110},
        ))
        with open(os.path.join(self.reqs, "links.jsonl"), "w") as f:
            f.write(jl(
                {"kind": "link", "reply_id": "r1", "request_ids": ["a#0"], "relevance": "DONE", "sid": "s1", "t": 120},
                {"kind": "link", "reply_id": "r2", "request_ids": ["m1"], "relevance": "DECISION", "sid": "s2", "t": 130}))
        items = feed.ask_items(AGENTS)
        self.assertEqual(items[0]["column"], "needs_input")

    def test_missing_registry_dir_is_empty_not_error(self):
        shutil.rmtree(self.reqs)
        self.assertEqual(feed.ask_items(AGENTS), [])

    def test_junk_lines_ignored(self):
        with open(os.path.join(self.reqs, "nodes.jsonl"), "w") as f:
            f.write('{"kind": "ask", "id": "a#0", "sid": "s1", "turn_id": "t", "t": 100, "text": "good"}\n')
            f.write("NOT JSON AT ALL\n{truncated\n\n")
        items = feed.ask_items(AGENTS)
        self.assertEqual(len(items), 1)

    def test_asks_are_user_origin(self):
        self.write("nodes.jsonl", jl(
            {"kind": "ask", "id": "a#0", "sid": "s1", "turn_id": "t", "t": 100, "text": "x"}))
        self.assertEqual(feed.ask_items(AGENTS)[0]["origin"], "user")

    # ── questions answered through channels that type nothing ───────────────

    def test_decision_crossed_when_session_moves_on(self):
        # INCIDENT 2026-06-10 (db_timeline): agent asked "should I implement
        # the fix?", the user approved via a dialog (no typed turn), session
        # resumed working — card sat in AWAITING while visibly busy. A newer
        # filed reply from the SAME session proves the question was resolved.
        self.write("nodes.jsonl", jl(
            {"kind": "ask", "id": "a#0", "sid": "s1", "turn_id": "s1:100:aa", "t": 100, "text": "fix the bug"},
            {"kind": "ask", "id": "b#0", "sid": "s1", "turn_id": "s1:90:zz", "t": 90, "text": "other work"}))
        with open(os.path.join(self.reqs, "links.jsonl"), "w") as f:
            f.write(jl(
                {"kind": "link", "reply_id": "r1", "request_ids": ["a#0"], "relevance": "DECISION", "sid": "s1", "t": 130},
                {"kind": "link", "reply_id": "r2", "request_ids": ["b#0"], "relevance": "DETAILS", "sid": "s1", "t": 140}))
        items = feed.ask_items(AGENTS)
        cols = {i["did"].split(None, 1)[1].split("  ")[0]: i["column"] for i in items}
        self.assertEqual(cols["fix the bug"], "asks")     # question moot → back in flight, NOT awaiting

    def test_decision_not_crossed_by_other_sessions_reply(self):
        # a different session filing work says nothing about THIS question
        self.write("nodes.jsonl", jl(
            {"kind": "ask", "id": "a#0", "sid": "s1", "turn_id": "s1:100:aa", "t": 100, "text": "fix the bug"}))
        with open(os.path.join(self.reqs, "links.jsonl"), "w") as f:
            f.write(jl(
                {"kind": "link", "reply_id": "r1", "request_ids": ["a#0"], "relevance": "DECISION", "sid": "s1", "t": 130},
                {"kind": "link", "reply_id": "r2", "request_ids": ["a#0"], "relevance": "DETAILS", "sid": "s2", "t": 125}))
        items = feed.ask_items(AGENTS)
        self.assertEqual(items[0]["column"], "needs_input")

    def test_action_survives_session_moving_on(self):
        # ACTION is the user's out-of-chat to-do — agent activity proves
        # nothing about it, so newer filed work from the same session (on
        # ANOTHER node — newest-on-node still rules within one node) must NOT
        # cross an action off the way it crosses a decision off
        self.write("nodes.jsonl", jl(
            {"kind": "ask", "id": "a#0", "sid": "s1", "turn_id": "s1:100:aa", "t": 100, "text": "reload the window"},
            {"kind": "ask", "id": "b#0", "sid": "s1", "turn_id": "s1:90:zz", "t": 90, "text": "other work"}))
        with open(os.path.join(self.reqs, "links.jsonl"), "w") as f:
            f.write(jl(
                {"kind": "link", "reply_id": "r1", "request_ids": ["a#0"], "relevance": "ACTION", "sid": "s1", "t": 130},
                {"kind": "link", "reply_id": "r2", "request_ids": ["b#0"], "relevance": "DETAILS", "sid": "s1", "t": 140}))
        items = feed.ask_items(AGENTS)
        bytext = {("reload" if "reload" in i["did"] else "other"): i["column"] for i in items}
        self.assertEqual(bytext["reload"], "needs_input")

    # ── follow-ups (followups.jsonl): reopen a completed card to ASKS ────────

    def _completed_root(self):
        """A root ask completed by a DONE link at t=120."""
        self.write("nodes.jsonl", jl(
            {"kind": "ask", "id": "a#0", "sid": "s1", "turn_id": "s1:100:aa", "t": 100, "text": "root"}))
        with open(os.path.join(self.reqs, "links.jsonl"), "w") as f:
            f.write(jl({"kind": "link", "reply_id": "r1", "request_ids": ["a#0"],
                        "relevance": "DONE", "sid": "s1", "t": 120}))

    def test_followup_reopens_completed_to_asks(self):
        # the deterministic record alone moves the card back — no bookkeeper
        # involvement, no gap where a sent follow-up shows as still completed
        self._completed_root()
        with open(os.path.join(self.reqs, "followups.jsonl"), "w") as f:
            f.write(jl({"id": "a#0", "sid": "s1", "t": 200, "text": "one more thing"}))
        items = feed.ask_items(AGENTS)
        self.assertEqual(items[0]["column"], "asks")
        self.assertEqual(items[0]["t"], 200)      # fresh follow-up bumps the card

    def test_followup_retired_by_minted_child_then_leafpath_owns_it(self):
        # bookkeeper filed the delivered turn as a CHILD of the root: the record
        # retires; the open child leaf keeps the card in ASKS, its DONE completes
        self._completed_root()
        with open(os.path.join(self.reqs, "followups.jsonl"), "w") as f:
            f.write(jl({"id": "a#0", "sid": "s1", "t": 200, "text": "one more thing"}))
        with open(os.path.join(self.reqs, "nodes.jsonl"), "a") as f:
            f.write(jl(
                {"kind": "ask", "id": "fu#0", "sid": "s1", "turn_id": "s1:210:bb", "t": 210, "text": "one more thing"},
                {"kind": "parents", "id": "fu#0", "parent_ids": ["a#0"], "t": 210}))
        items = feed.ask_items(AGENTS)
        self.assertEqual(len(items), 1)           # the child is NOT its own card
        self.assertIn("root", items[0]["did"])    # title stays the root's
        self.assertEqual(items[0]["column"], "asks")
        with open(os.path.join(self.reqs, "links.jsonl"), "a") as f:
            f.write(jl({"kind": "link", "reply_id": "r2", "request_ids": ["fu#0"],
                        "relevance": "DONE", "sid": "s1", "t": 300}))
        self.assertEqual(feed.ask_items(AGENTS)[0]["column"], "completed")

    def test_followup_retired_by_newer_verdict_on_root(self):
        # the answering reply was filed DONE on the ROOT itself (no child node):
        # any verdict newer than the follow-up retires the record
        self._completed_root()
        with open(os.path.join(self.reqs, "followups.jsonl"), "w") as f:
            f.write(jl({"id": "a#0", "sid": "s1", "t": 200, "text": "one more thing"}))
        with open(os.path.join(self.reqs, "links.jsonl"), "a") as f:
            f.write(jl({"kind": "link", "reply_id": "r2", "request_ids": ["a#0"],
                        "relevance": "DONE", "sid": "s1", "t": 300}))
        self.assertEqual(feed.ask_items(AGENTS)[0]["column"], "completed")

    def test_followup_resurrects_a_cleared_card(self):
        # following up on a card the user already cleared must bring it back —
        # a sent follow-up may never be invisible (same rule as post-clear questions)
        self._completed_root()
        with open(os.path.join(self.reqs, "cleared.jsonl"), "w") as f:
            f.write(jl({"id": "a#0", "t": 150}))
        with open(os.path.join(self.reqs, "followups.jsonl"), "w") as f:
            f.write(jl({"id": "a#0", "sid": "s1", "t": 200, "text": "one more thing"}))
        items = feed.ask_items(AGENTS)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["column"], "asks")


class TestOriginDetection(RegistryFixture):
    """feed_items() — user-vs-agent origin via same-id request lines.
    INCIDENT: peer-prompted turns once carried request lines (banner-gate bug);
    going forward absence-of-request-line == agent-prompted is the contract."""

    def test_same_id_request_means_user_and_exact_ask(self):
        self.write_summary("s1", jl(
            {"id": "s1:50:xx", "t": 50, "kind": "request", "text": "older unrelated ask"},
            {"id": "s1:100:aa", "t": 100, "kind": "request", "text": "the exact ask"},
            {"id": "s1:100:aa", "t": 105, "kind": "reply", "text": "did the thing", "relevance": "DONE"},
        ))
        items = feed.feed_items(AGENTS)
        self.assertEqual(items[0]["origin"], "user")
        self.assertEqual(items[0]["ask"], "the exact ask")   # same-id beats most-recent-preceding

    def test_no_request_line_means_agent(self):
        self.write_summary("s1", jl(
            {"id": "s1:100:aa", "t": 105, "kind": "reply", "text": "peer-prompted work", "relevance": "DETAILS"}))
        self.assertEqual(feed.feed_items(AGENTS)[0]["origin"], "agent")

    def test_default_filter_hides_agent_and_counts(self):
        self.write_summary("s1", jl(
            {"id": "s1:100:aa", "t": 100, "kind": "request", "text": "ask"},
            {"id": "s1:100:aa", "t": 105, "kind": "reply", "text": "user work"},
            {"id": "s1:200:bb", "t": 205, "kind": "reply", "text": "agent work"},
        ))
        class A:  # minimal args
            agent = None; live = False; today = False; since = None
            chrono = False; n = 0; all = False; asks = False
        items, hidden = feed.select(feed.feed_items(AGENTS), A, now=1000)
        self.assertEqual([i["did"] for i in items], ["user work"])
        self.assertEqual(hidden, 1)
        A.all = True
        items, hidden = feed.select(feed.feed_items(AGENTS), A, now=1000)
        self.assertEqual(len(items), 2)
        self.assertEqual(hidden, 0)


class TestPipelineReaders(RegistryFixture):
    """read_registry() in romp-pipeline — counts that drive the status table."""

    def test_links_open_asks_and_capture_counts(self):
        self.write("nodes.jsonl", jl(
            {"kind": "ask", "id": "a#0", "sid": "s1", "turn_id": "T1", "t": 100, "text": "x"},
            {"kind": "ask", "id": "a#1", "sid": "s1", "turn_id": "T1", "t": 100, "text": "y"},
            {"kind": "amend", "id": "a#0", "turn_id": "T2", "t": 200, "text": "z"},
        ))
        with open(os.path.join(self.reqs, "links.jsonl"), "w") as f:
            f.write(jl({"kind": "link", "reply_id": "R1", "request_ids": ["a#0", "a#1"], "relevance": "DONE", "sid": "s1", "t": 120}))
        with open(os.path.join(self.reqs, "cleared.jsonl"), "w") as f:
            f.write(jl({"id": "a#1", "t": 500}))
        links, open_asks, by_turn = pipe.read_registry()
        self.assertEqual(links["R1"], 2)         # one reply served two requests
        self.assertEqual(open_asks, 1)           # a#1 cleared
        self.assertEqual(by_turn["T1"], 2)       # split: two asks from one turn
        self.assertEqual(by_turn["T2"], 1)       # amend counts as capture activity


if __name__ == "__main__":
    unittest.main(verbosity=2)
