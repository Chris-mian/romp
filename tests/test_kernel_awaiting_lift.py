#!/usr/bin/env python3
"""A goal's ⏳ awaiting stamp is RETIRED once the dispatches it was waiting on return (the user
2026-07-22).

The closer's own lift is bounded to the goals a turn actually WORKED ON (`touched`) — correct for goals
merely riding the menu, but it means a goal the session ABANDONS keeps its stamp forever. Live case: a goal
stamped "waiting on two dispatched investigations" at 12:26; both task-notifications landed by 12:31; the
session went idle at 12:32 and filed its later work under other goals, so no closer pass revisited it. Four
and a half hours later the card still claimed the wait with an empty task list behind it.

_lift_spent_awaiting keys on the EVENT, never a timer: the notification that answered each dispatch is in
the transcript and _scan_bg_tasks already pairs launches to results. It is SELF-SCOPING — it lifts only
when the goal itself dispatched background work by stamp time and all of it came back — so a stamp naming
a CI run, a scheduled check-back or a peer handoff owns no such dispatches, never matches, and keeps its
stamp (those remain the 6h backstop's job, the one case a timer is the only tool for).

SYNTHETIC fixtures only: placeholder UUIDs, invented task descriptions.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
km = SourceFileLoader("romp_kernel_awlift", os.path.join(BIN, "romp-kernel")).load_module()

SID = "11111111-2222-3333-4444-999999999999"
BORN, LAUNCH, STAMP, BACK = 100, 200, 300, 400      # goal minted / dispatched / stamped / result landed


def _iso(ep):
    import datetime
    return datetime.datetime.fromtimestamp(ep, tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _launch(tid, t):
    """An async Agent dispatch ack — the durable 'this work is now running' record."""
    return {"type": "user", "timestamp": _iso(t), "uuid": "u" + tid, "parentUuid": None,
            "toolUseResult": {"status": "async_launched", "description": "a dispatched investigation"},
            "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tid,
                                                     "content": "launched"}]}}


def _notification(tid, t):
    """The standalone <task-notification> user record that ENDS the wait (the dominant live shape)."""
    body = ("<task-notification>\n<task-id>%s</task-id>\n<tool-use-id>%s</tool-use-id>\n"
            "<status>completed</status>\n<summary>the investigation finished</summary>\n"
            "</task-notification>" % (tid, tid))
    return {"type": "user", "timestamp": _iso(t), "uuid": "n" + tid, "parentUuid": None,
            "message": {"role": "user", "content": body}}


class AwaitingLift(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        td = Path(self.td.name)
        self.saved = {k: getattr(km, k) for k in ("_alive_sessions", "_mark_views_dirty")}
        self.saved_jd = (km.jd.STATE, km.jd.GOALDIR)
        km.jd.STATE = td
        km.jd.GOALDIR = td / "goals"
        km.jd.GOALDIR.mkdir(parents=True)
        self.path = str(td / (SID + ".jsonl"))
        km._alive_sessions = lambda now, tmux: [{"sid": SID, "path": self.path}]
        km._mark_views_dirty = lambda *a, **k: None
        km._SESSION_STAMP_CACHE.clear()
        km._bgall_cache.clear()
        km._bgtasks_cache.clear()
        self.gid = SID + ":g1"

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(km, k, v)
        km.jd.STATE, km.jd.GOALDIR = self.saved_jd
        km._SESSION_STAMP_CACHE.clear(); km._bgall_cache.clear(); km._bgtasks_cache.clear()
        self.td.cleanup()

    def _transcript(self, recs):
        with open(self.path, "w") as f:
            for r in recs:
                f.write(json.dumps(r) + "\n")
        km._bgall_cache.clear(); km._bgtasks_cache.clear()

    def _seed(self, why="waiting on two dispatched investigations; will act when they return",
              born=BORN, anchor=STAMP, written=None):
        """`anchor` is awaitingAt (the audited turn's TRIGGER time); `written` is when the closer actually
        wrote the verdict (its `at`), which defaults to the anchor for the pre-2026-07-27 fixture shape."""
        nd = {"id": self.gid, "text": "a goal", "parentId": None, "nodeComplete": False,
              "blocked": False, "cleared": False, "trail": [], "t": born, "mt": born,
              "awaitingWhy": why, "awaitingAt": anchor,
              "log": [{"ev_t": anchor, "src": "closer", "kind": "awaiting", "why": why,
                       "at": anchor if written is None else written}]}
        (km.jd.GOALDIR / (SID + ".json")).write_text(json.dumps(
            {"rompUuid": SID, "seq": 1, "placements": {}, "status": {}, "nodes": {self.gid: nd}}))

    def _tick(self, now=BACK + 100):
        km._lift_spent_awaiting(now, {SID: {"state": ""}})

    def _stamp(self):
        nodes = json.loads((km.jd.GOALDIR / (SID + ".json")).read_text())["nodes"]
        return nodes[self.gid].get("awaitingWhy") or None

    # ---- the bug ----
    def test_both_dispatches_returned_lifts_the_stamp(self):
        self._transcript([_launch("t1", LAUNCH), _launch("t2", LAUNCH + 5),
                          _notification("t1", BACK), _notification("t2", BACK + 5)])
        self._seed()
        self.assertIsNotNone(self._stamp(), "precondition: the goal starts stamped")
        self._tick()
        self.assertIsNone(self._stamp(), "every dispatch came back → the wait is over")

    def test_one_still_running_keeps_the_stamp(self):
        self._transcript([_launch("t1", LAUNCH), _launch("t2", LAUNCH + 5),
                          _notification("t1", BACK)])          # t2 never reported
        self._seed()
        self._tick()
        self.assertIsNotNone(self._stamp(), "one dispatch is still out → still genuinely awaiting")

    # ---- self-scoping: the other awaiting flavors are untouched ----
    def test_a_wait_with_no_dispatches_of_its_own_is_untouched(self):
        # a CI run / scheduled check-back / peer handoff: nothing was dispatched, so nothing can be paired
        self._transcript([])
        self._seed(why="waiting on the release pipeline to go green, then will tag")
        self._tick()
        self.assertIsNotNone(self._stamp(), "no dispatches to evidence → the stamp is not ours to lift")

    def test_a_dispatch_launched_after_the_stamp_is_not_owned(self):
        # it cannot be what the stamp was explaining, so its return says nothing about that wait
        self._transcript([_launch("t9", STAMP + 50), _notification("t9", STAMP + 90)])
        self._seed()
        self._tick()
        self.assertIsNotNone(self._stamp(), "only dispatches at/before the stamp can retire it")

    def test_a_dispatch_from_before_the_goal_existed_is_not_owned(self):
        self._transcript([_launch("t0", BORN - 50), _notification("t0", BORN - 10)])
        self._seed()
        self._tick()
        self.assertIsNotNone(self._stamp(), "a task predating the goal is another goal's business")

    # ---- guards ----
    def test_a_dormant_session_is_skipped(self):
        # its tasks died with its CLI; the death notice is the truth there, never a lift
        self._transcript([_launch("t1", LAUNCH), _notification("t1", BACK)])
        self._seed()
        km._lift_spent_awaiting(BACK + 100, {})        # no live snapshot for the sid
        self.assertIsNotNone(self._stamp(), "a dormant session is never ruled on here")

    def test_an_unstamped_goal_is_left_alone(self):
        self._transcript([_launch("t1", LAUNCH), _notification("t1", BACK)])
        nd = {"id": self.gid, "text": "a goal", "parentId": None, "nodeComplete": False,
              "blocked": False, "cleared": False, "trail": [], "t": BORN, "mt": BORN}
        (km.jd.GOALDIR / (SID + ".json")).write_text(json.dumps(
            {"rompUuid": SID, "seq": 1, "placements": {}, "status": {}, "nodes": {self.gid: nd}}))
        self._tick()
        self.assertIsNone(self._stamp())

    def test_the_lift_is_recorded_in_the_verdict_log(self):
        self._transcript([_launch("t1", LAUNCH), _notification("t1", BACK)])
        self._seed()
        self._tick()
        log = json.loads((km.jd.GOALDIR / (SID + ".json")).read_text())["nodes"][self.gid]["log"]
        self.assertTrue(any(e.get("kind") == "awaiting" and e.get("lift") for e in log),
                        "the retraction is journalled like any other verdict, not a silent field wipe")

    # ---- ownership scoping (the user 2026-07-27): placement is authoritative when the judge has spoken ----
    def test_a_return_placed_under_another_card_never_lifts_this_stamp(self):
        # unrelated returns were lifting CI-wait stamps (one lifted the same minute it was re-asserted):
        # the bare time window claimed every task the session launched in [born, at]
        self._transcript([_launch("t1", LAUNCH), _notification("t1", BACK)])
        self._seed(why="waiting on the release pipeline to go green, then will tag")
        saved = km._bg_placed_tops
        km._bg_placed_tops = lambda sid, path, tids: {"t1": SID + ":gOTHER"}
        try:
            self._tick()
        finally:
            km._bg_placed_tops = saved
        self.assertIsNotNone(self._stamp(), "another card's dispatch can never retire this wait")

    def test_the_goals_own_placed_dispatch_still_lifts(self):
        self._transcript([_launch("t1", LAUNCH), _notification("t1", BACK)])
        self._seed()
        saved = km._bg_placed_tops
        km._bg_placed_tops = lambda sid, path, tids: {"t1": self.gid}
        try:
            self._tick()
        finally:
            km._bg_placed_tops = saved
        self.assertIsNone(self._stamp(), "the goal's own thread returned everything → the wait is over")

    def test_a_later_running_dispatch_on_the_same_thread_keeps_the_stamp(self):
        # placed under the same top AFTER the stamp: its flight keeps the wait honest, so no lift
        self._transcript([_launch("t1", LAUNCH), _notification("t1", BACK), _launch("t2", STAMP + 50)])
        self._seed()
        saved = km._bg_placed_tops
        km._bg_placed_tops = lambda sid, path, tids: {"t1": self.gid, "t2": self.gid}
        try:
            self._tick()
        finally:
            km._bg_placed_tops = saved
        self.assertIsNotNone(self._stamp(), "the thread's own newer dispatch is still out")

    # ---- rolled-up stamps (the user 2026-07-27): frozen invisible, so retire them on the record ----
    def test_a_rolled_up_stamp_is_lifted_and_only_once(self):
        # the roll-down froze a stamped node under a resolved ancestor — every reader skips rolledUp,
        # so the stamp could neither show nor retire. The sweep lifts it, diary-guarded against re-fire.
        self._transcript([])
        nd = {"id": self.gid, "text": "a goal", "parentId": None, "nodeComplete": True,
              "blocked": False, "cleared": False, "rolledUp": True, "trail": [], "t": BORN, "mt": BORN,
              "awaitingWhy": "a wait the roll-down froze", "awaitingAt": STAMP,
              "log": [{"ev_t": STAMP, "src": "closer", "kind": "awaiting",
                       "why": "a wait the roll-down froze", "at": STAMP}]}
        (km.jd.GOALDIR / (SID + ".json")).write_text(json.dumps(
            {"rompUuid": SID, "seq": 1, "placements": {}, "status": {}, "nodes": {self.gid: nd}}))
        self._tick()
        log = json.loads((km.jd.GOALDIR / (SID + ".json")).read_text())["nodes"][self.gid]["log"]
        self.assertEqual(len([e for e in log if e.get("kind") == "awaiting" and e.get("lift")]), 1,
                         "the frozen stamp is retired, on the record")
        self._tick()
        log2 = json.loads((km.jd.GOALDIR / (SID + ".json")).read_text())["nodes"][self.gid]["log"]
        self.assertEqual(len([e for e in log2 if e.get("kind") == "awaiting" and e.get("lift")]), 1,
                         "diary-guarded: the sweep never re-lifts")

    # ---- the collapsed window (the user 2026-07-27): mint and stamp in the SAME turn ----
    # awaitingAt is the audited turn's TRIGGER, but a turn dispatches partway through, always after it.
    # When that turn also MINTED the goal, born == awaitingAt and [born, awaitingAt] is a single instant:
    # the fallback matched nothing, so this whole path was dead for the goals it exists to serve. The
    # bound is the stamp's WRITE time, which is after every launch the closer could have audited.
    def test_a_same_turn_mint_and_stamp_still_owns_its_mid_turn_dispatch(self):
        self._transcript([_launch("t1", STAMP + 20), _notification("t1", STAMP + 60)])
        self._seed(born=STAMP, anchor=STAMP, written=STAMP + 90)   # one turn: trigger STAMP, closed later
        self.assertIsNotNone(self._stamp(), "precondition: the goal starts stamped")
        self._tick(now=STAMP + 200)
        self.assertIsNone(self._stamp(),
                          "the dispatch was launched inside the very turn the stamp explains → owned, "
                          "and it came back")

    def test_a_same_turn_dispatch_still_running_keeps_the_stamp(self):
        # the widened bound must not lift a wait that is genuinely still out
        self._transcript([_launch("t1", STAMP + 20)])              # never reported
        self._seed(born=STAMP, anchor=STAMP, written=STAMP + 90)
        self._tick(now=STAMP + 200)
        self.assertIsNotNone(self._stamp(), "its own dispatch is still in flight")

    def test_a_dispatch_after_the_stamp_was_written_is_still_not_owned(self):
        # the bound moved to the WRITE time, not to infinity: a launch the closer could not have seen
        # belongs to a later turn and says nothing about this wait
        self._transcript([_launch("t9", STAMP + 150), _notification("t9", STAMP + 180)])
        self._seed(born=STAMP, anchor=STAMP, written=STAMP + 90)
        self._tick(now=STAMP + 300)
        self.assertIsNotNone(self._stamp(), "launched after the stamp was written → a later turn's work")

    def test_written_at_prefers_the_newest_assertion_and_ignores_lifts(self):
        why = "waiting on a dispatched investigation"
        nd = {"awaitingAt": STAMP,
              "log": [{"ev_t": STAMP, "kind": "awaiting", "why": why, "at": STAMP + 10},
                      {"ev_t": STAMP, "kind": "awaiting", "why": why, "at": STAMP + 90},
                      {"ev_t": STAMP, "kind": "awaiting", "lift": True, "at": STAMP + 500},
                      {"ev_t": STAMP, "kind": "done", "at": STAMP + 900}]}
        self.assertEqual(km._stamp_written_at(nd), STAMP + 90,
                         "the newest ASSERTION bounds ownership; a lift retracts a wait, never asserts one")

    def test_written_at_floors_at_the_anchor_for_a_legacy_record(self):
        self.assertEqual(km._stamp_written_at({"awaitingAt": STAMP, "log": []}), STAMP,
                         "no journalled write time → the old anchor bound, unchanged")
        self.assertEqual(km._stamp_written_at({"awaitingAt": STAMP}), STAMP, "no log at all is safe")

    # ---- the lift's EVIDENCE time (the user 2026-08-06): the stamp's anchor, never wall-clock ----
    # The fold reads a node's diary in (ev_t, at) order, and a closer assert carries its audited TURN's
    # trigger — always older than the moment a lift fires. So a lift stamped `now` outranked every assert
    # the closer could still file on that segment, permanently: a session relaunched its watcher seconds
    # after a lift, the closer re-asserted the wait three times over the next two minutes, and the fold
    # discarded all three. The card sat in Working with no awaiting box and no spin (its session idle), its
    # live watcher demoted to a background-process chip, and its nudge exemption gone.
    def test_the_lift_is_stamped_at_the_anchor_not_wall_clock(self):
        self._transcript([_launch("t1", LAUNCH), _notification("t1", BACK)])
        self._seed()
        self._tick(now=BACK + 5000)
        log = json.loads((km.jd.GOALDIR / (SID + ".json")).read_text())["nodes"][self.gid]["log"]
        lift = [e for e in log if e.get("kind") == "awaiting" and e.get("lift")][0]
        self.assertEqual(lift["ev_t"], STAMP,
                         "the lift retracts the wait it LOOKED at, so it carries that stamp's anchor")
        self.assertNotEqual(lift["ev_t"], BACK + 5000, "never the tick's wall clock")

    def test_a_closer_reassert_filed_after_the_lift_restores_the_stamp(self):
        self._transcript([_launch("t1", LAUNCH), _notification("t1", BACK)])
        self._seed()
        self._tick()
        self.assertIsNone(self._stamp(), "precondition: the returned dispatch lifted the wait")
        # the session relaunches its watcher and the closer, auditing the SAME turn, says the wait is on
        store = json.loads((km.jd.GOALDIR / (SID + ".json")).read_text())
        nd = store["nodes"][self.gid]
        again = "the relaunched watcher on the two open PRs; it deploys once they merge"
        self.assertTrue(km.jd.record_verdict(store, nd, "closer", "awaiting", STAMP, why=again),
                        "the closer's re-assert is allowed to land")
        self.assertEqual(km.jd._fold_node(nd)["awaitingWhy"], again,
                         "the newest RULING wins: an assert filed after the lift puts the stamp back")
        self.assertEqual(km._goal_awaiting_stamp(store["nodes"], self.gid), again,
                         "so the card wears its awaiting box again, and keeps its nudge exemption")

    def test_the_lift_still_wins_when_nothing_is_filed_after_it(self):
        # the ordinary case is unchanged: nobody re-asserts, so the retraction stands
        self._transcript([_launch("t1", LAUNCH), _notification("t1", BACK)])
        self._seed(anchor=STAMP, written=STAMP + 10)
        self._tick()
        store = json.loads((km.jd.GOALDIR / (SID + ".json")).read_text())
        nd = store["nodes"][self.gid]
        self.assertIsNone(km.jd._fold_node(nd)["awaitingWhy"], "the wait is over and stays over")
        self.assertIsNone(km._goal_awaiting_stamp(store["nodes"], self.gid))

    def test_running_only_scan_still_hides_returned_tasks(self):
        # the want_all split must not change the existing running-only view
        self._transcript([_launch("t1", LAUNCH), _launch("t2", LAUNCH + 5), _notification("t1", BACK)])
        running = km._scan_bg_tasks(self.path)
        self.assertEqual([t["id"] for t in running], ["t2"])
        every = km._scan_bg_tasks(self.path, want_all=True)
        self.assertEqual(sorted(t["id"] for t in every), ["t1", "t2"])
        self.assertEqual({t["id"]: t["status"] for t in every}["t1"], "completed")


if __name__ == "__main__":
    unittest.main()
