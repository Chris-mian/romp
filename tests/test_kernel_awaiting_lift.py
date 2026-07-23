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

    def _seed(self, why="waiting on two dispatched investigations; will act when they return"):
        nd = {"id": self.gid, "text": "a goal", "parentId": None, "nodeComplete": False,
              "blocked": False, "cleared": False, "trail": [], "t": BORN, "mt": BORN,
              "awaitingWhy": why, "awaitingAt": STAMP,
              "log": [{"ev_t": STAMP, "src": "closer", "kind": "awaiting", "why": why, "at": STAMP}]}
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
