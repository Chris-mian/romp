#!/usr/bin/env python3
"""Clearing a still-OPEN card sends its live session a ONE-round wrap-up directive (the user 2026-07-24).

The July-22 post-mortem this encodes (all fixtures SYNTHETIC): a card was cleared from the feed three
minutes after its build started; the only copy of the work was uncommitted worktree edits, which
evaporated with no signal. The user clears cards they distrust — some clears catch real work — so the
clear of a working/blocked card now tells the owning session ONCE: stop, park any unfinished work
where it won't be lost, and surface at most one final keep-or-discard decision. Like a file-delete
confirm, routed one time through the agent. The ask names no branch or commit (the user 2026-07-26):
not every session is coding in git.

The invariants:
- Only still-OPEN top goals notify (completed/settled tops, sub-goals, and stream items don't).
- A pure-delegation top notifies nobody (the peer's linked copy rides the same batch and notifies THAT
  session).
- ONE round only: the decision card the wrap-up reply mints carries clearWrap (judge apply_plan), and
  clearing a clearWrap card is terminal — no second message, no loop.
- The message carries romp-clear-wrap + romp-injected and NO romp-goal-id: a goal-id would make the
  follow-up judge reopen the cleared goal, the resurrection the clear must rule out.
- Dead sessions get nothing; a failed send never breaks the clear; the undo path sends nothing.
- It reads as the user's own short message. The session does not know romp is tracking it, so the prose
  carries none of romp's vocabulary (goal, card, board, clear) and none of its directive register.
"""
import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
km = SourceFileLoader("romp_kernel_clearwrap", os.path.join(BIN, "romp-kernel")).load_module()
jd = km.jd

SID = "11111111-2222-3333-4444-555555555555"
PEER = "66666666-7777-8888-9999-000000000000"
G_OPEN, G_DONE, G_SUB, G_WRAP, G_DELEG = (SID + ":g1", SID + ":g2", SID + ":g3",
                                          SID + ":g4", SID + ":g5")
NOW = 1781100000
T0 = NOW - 3600


def _node(nid, text, parent=None, **kw):
    d = {"id": nid, "text": text, "parentId": parent, "nodeComplete": False,
         "blocked": False, "cleared": False, "t": T0, "mt": T0, "log": []}
    d.update(kw)
    return d


def _nodes():
    return {G_OPEN: _node(G_OPEN, "Build the sticky timestamp", why="Prototype the floating stamp."),
            G_DONE: _node(G_DONE, "Ship the release", nodeComplete=True),
            G_SUB: _node(G_SUB, "A step inside", parent=G_OPEN),
            G_WRAP: _node(G_WRAP, "Parked WIP: keep or discard?", clearWrap=True),
            G_DELEG: _node(G_DELEG, "Peer is porting the client",
                           handoff={"peer": PEER, "msgId": "m1"})}


class ClearWrapTargets(unittest.TestCase):
    def setUp(self):
        self._orig_load = jd.load_goals
        nodes = _nodes()
        jd.load_goals = lambda sid: {"rompUuid": SID, "nodes": nodes, "placements": {}, "status": {}}

    def tearDown(self):
        jd.load_goals = self._orig_load

    def test_only_the_open_top_notifies(self):
        out = km._clear_wrap_targets([G_OPEN, G_DONE, G_SUB, G_WRAP, G_DELEG, SID + ":stream-item"])
        self.assertEqual(out, {SID: [G_OPEN]},
                         "done tops, sub-goals, wrap-decision cards, pure delegations and non-goal "
                         "items all skip; only the still-open own-work top gets the wrap-up")

    def test_a_blocked_top_is_open_too(self):
        # "cleared from working or blocked" (the user 2026-07-24): a blocked card holds an unanswered
        # ask — clearing it dismisses that ask, and the session should hear about it once.
        nodes = _nodes()
        nodes[G_OPEN]["blocked"] = True
        jd.load_goals = lambda sid: {"nodes": nodes}
        self.assertEqual(km._clear_wrap_targets([G_OPEN]), {SID: [G_OPEN]})

    def test_a_clearwrap_card_is_terminal(self):
        # the one-and-only-one-loop rule: clearing the wrap-up's own decision card must NOT trigger
        # another wrap-up — that would be the infinite confirm regress.
        self.assertEqual(km._clear_wrap_targets([G_WRAP]), {})

    def test_an_unreadable_store_notifies_nobody(self):
        def boom(sid):
            raise OSError("store unreadable")
        jd.load_goals = boom
        self.assertEqual(km._clear_wrap_targets([G_OPEN]), {})


class ClearWrapBody(unittest.TestCase):
    def test_single_goal_form(self):
        out = km._clear_wrap_body([G_OPEN], _nodes())
        self.assertIn("> Build the sticky timestamp", out)
        self.assertIn("> Prototype the floating stamp.", out, "the planner's why rides as context")
        # It reads as DONE, not as an abandonment order (the user 2026-07-29): a clear most often means
        # "acknowledged, I am finished with this", and the old "stop work, don't pick it back up" framing
        # made an ordinary acknowledgement sound like a rebuke.
        self.assertIn("I'm done with this one", out)
        self.assertIn("you can stop here", out)
        self.assertIn("save it somewhere it won't be lost", out,
                      "loss-proofing without naming git — not every session is coding (the user "
                      "2026-07-26); an agent in a repo still reads this as 'commit to a branch'")
        # …and it ASKS FOR NOTHING. A mandatory reply made every clear cost a second decision, which is
        # the loop this removes: silence is the expected answer.
        self.assertIn("No need to reply", out)
        self.assertNotIn("reply once", out)
        self.assertNotIn("Just the one reply", out)
        # the session keeps the discretion to speak up, on two grounds only
        self.assertIn("still needs a decision from me", out)
        self.assertIn("stopped you too early", out)

    def test_bundle_numbers_the_goals(self):
        nodes = _nodes()
        nodes[SID + ":g9"] = _node(SID + ":g9", "Write the migration guide")
        out = km._clear_wrap_body([G_OPEN, SID + ":g9"], nodes)
        self.assertIn("> 1. Build the sticky timestamp", out)
        self.assertIn("> 2. Write the migration guide", out)
        self.assertIn("I'm done with these", out)
        self.assertIn("you can stop here", out)
        self.assertIn("work in progress on any of them", out)
        self.assertIn("If one of them still needs a decision", out)

    def test_it_reads_as_a_human_ask_not_a_system_notice(self):
        # the user 2026-07-24: the session has no idea romp is tracking it, so the message must not
        # narrate the goal machinery at it ("the goal above was cleared off the board — a dismissal,
        # not a completion"). It is the person it works for asking for something, in their words.
        # Prose only: the marker tail is a hidden HTML comment and names romp on purpose.
        prose = km._clear_wrap_body([G_OPEN], _nodes()).split("<!--")[0].lower()
        for jargon in ("goal", "board", "card", "clear", "dismiss", "romp"):
            self.assertNotIn(jargon, prose,
                             "%r is romp's vocabulary, not the user's — the session doesn't know the "
                             "tracking system exists" % jargon)

    def test_it_stays_short(self):
        # succinctness is the point, not a nicety: a long directive reads as a system notice however
        # it is worded. The first draft ran ~110 words; hold the rewrite near half that.
        body = km._clear_wrap_body([G_OPEN], _nodes()).split("<!--")[0].split("\n\n", 1)[1]
        self.assertLess(len(body.split()), 75, "the ask fits in a short human message")

    def test_markers_wrap_but_never_goal_id(self):
        out = km._clear_wrap_body([G_OPEN], _nodes())
        self.assertIn("<!-- romp-injected -->", out, "gray romp bubble")
        self.assertIn("<!-- romp-clear-wrap -->", out, "the judge keys the wrap-up note off this")
        self.assertNotIn("romp-goal-id", out,
                         "a goal-id would reopen the cleared goal and file the reply under it — the "
                         "resurrection the clear must rule out")
        self.assertNotIn("romp-auto", out, "not an auto-nudge; no nudge logo, no nudge re-arm semantics")


class ClearWrapNotify(unittest.TestCase):
    """The glue: _clear_all → targets → live-only send; failures never break the clear."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.saved_state = jd.STATE
        jd.STATE = Path(self.td.name)
        self._orig = {n: getattr(km, n) for n in ("_tmux_sessions", "_sessions", "_mark_nodes_cleared")}
        self._orig_load = jd.load_goals
        self._orig_backend = km.Sessions.backend_for
        km._sessions = lambda now: []
        km._mark_nodes_cleared = lambda ids, v: None   # exercised by its own tests; here we test the notify
        nodes = _nodes()
        jd.load_goals = lambda sid: {"nodes": nodes}
        self.sent = []
        test = self

        class FakeBackend:
            def send(self, sid, body):
                test.sent.append((sid, body))
        km.Sessions.backend_for = staticmethod(lambda sid: FakeBackend())
        km._tmux_sessions = lambda: {SID: {"state": "waiting"}}

    def tearDown(self):
        for n, v in self._orig.items():
            setattr(km, n, v)
        jd.load_goals = self._orig_load
        km.Sessions.backend_for = self._orig_backend
        jd.STATE = self.saved_state
        self.td.cleanup()

    def test_clearing_an_open_card_sends_one_wrap_up(self):
        km._clear_all([G_OPEN])
        self.assertEqual(len(self.sent), 1)
        sid, body = self.sent[0]
        self.assertEqual(sid, SID)
        self.assertIn("<!-- romp-clear-wrap -->", body)

    def test_a_batch_clear_bundles_into_one_message(self):
        nodes = _nodes()
        nodes[SID + ":g9"] = _node(SID + ":g9", "Write the migration guide")
        jd.load_goals = lambda sid: {"nodes": nodes}
        km._clear_all([G_OPEN, SID + ":g9", G_DONE])
        self.assertEqual(len(self.sent), 1, "one session, one message — never one per card")
        self.assertIn("> 1.", self.sent[0][1])

    def test_clearing_a_done_card_sends_nothing(self):
        km._clear_all([G_DONE])
        self.assertEqual(self.sent, [])

    def test_clearing_the_decision_card_sends_nothing(self):
        km._clear_all([G_WRAP])
        self.assertEqual(self.sent, [], "one round only — the confirm card's clear is final")

    def test_a_dead_session_gets_nothing(self):
        km._tmux_sessions = lambda: {}
        km._clear_all([G_OPEN])
        self.assertEqual(self.sent, [], "no live CLI → no agent holding WIP to ask")

    def test_a_send_failure_never_breaks_the_clear(self):
        class Boom:
            def send(self, sid, body):
                raise RuntimeError("pane gone")
        km.Sessions.backend_for = staticmethod(lambda sid: Boom())
        km._clear_all([G_OPEN])                        # must not raise
        cleared = (jd.STATE / "cleared.jsonl").read_text()
        self.assertIn(G_OPEN, cleared, "the clear itself landed despite the notify failure")

    def test_undo_sends_nothing(self):
        km._clear_all([G_OPEN])
        self.sent.clear()
        km._undo_clear()
        self.assertEqual(self.sent, [], "an undo is the user re-raising the thread themselves")


class JudgeSide(unittest.TestCase):
    def _seg(self, text):
        return {"id": "s1", "t": T0, "trigger": "u1",
                "atoms": [{"uuid": "u1", "type": "user", "t": T0,
                           "message": {"content": [{"type": "text", "text": text}]}}]}

    def test_seg_clearwrap_keys_on_the_marker(self):
        self.assertTrue(jd._seg_clearwrap(self._seg("wrap up\n<!-- romp-clear-wrap -->")))
        self.assertFalse(jd._seg_clearwrap(self._seg("plain nudge\n<!-- romp-injected -->")))
        self.assertFalse(jd._seg_clearwrap({"id": "s0", "atoms": [], "trigger": None}))

    def test_apply_plan_stamps_clearwrap_on_minted_nodes(self):
        store = {"rompUuid": SID, "seq": 0, "nodes": {}, "placements": {}, "status": {}}
        jd.apply_plan(store, "seg1", T0, [{"do": "mint", "text": "Parked WIP: keep or discard?",
                                           "why": "draft committed to a branch"}], [], clear_wrap=True)
        nd = next(iter(store["nodes"].values()))
        self.assertTrue(nd.get("clearWrap"), "the decision card is marked terminal")
        store2 = {"rompUuid": SID, "seq": 0, "nodes": {}, "placements": {}, "status": {}}
        jd.apply_plan(store2, "seg1", T0, [{"do": "mint", "text": "ordinary goal", "why": "w"}], [])
        nd2 = next(iter(store2["nodes"].values()))
        self.assertNotIn("clearWrap", nd2, "ordinary mints stay lean — no stray flag")

    def test_plan_units_note_pin(self):
        import inspect
        src = inspect.getsource(jd.plan_units)
        self.assertIn("one-time wrap-up of goals the user just", src)
        self.assertIn("re-create or reopen the cleared goals themselves", src)
        # the DEFAULT is now to file nothing, matching a wrap-up that asks for no reply (2026-07-29):
        # a session that merely stops, or reports what it parked, must not mint anything
        self.assertIn("the DEFAULT is to **skip**", src)
        self.assertIn("or reports what", src)
        # …and a card is minted only when the session raises something that genuinely needs the user
        self.assertIn("**one** new top-level goal, blocked on the user", src)
        self.assertIn("an explicit question it is", src)
        self.assertIn("the dismissal looks premature", src)


if __name__ == "__main__":
    unittest.main()
