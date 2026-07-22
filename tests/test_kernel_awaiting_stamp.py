#!/usr/bin/env python3
"""The JUDGE's durable awaiting stamp reaching the kernel (2026-07-22): the closer's `awaiting` verdict
(kernel/judge.py) lands awaitingWhy/awaitingAt on the goal node — store-backed, so it survives kernel
restarts, where the LIVE awaiting sources (in-memory subagents/bgTasks) go dark. Consumers here:

  * _goal_awaiting_stamp — the subtree scan both the feed floor and the nudge gates share;
  * _mark_nudge_failed — a stamped goal's nudge is never converted into a needs-you block (the
    restart-proof twin of the session-level awaiting re-check): this is exactly the false "stalled"
    a genuinely-waiting session showed after a kernel restart.

SYNTHETIC fixtures only (placeholder UUIDs, invented text)."""
import json
import tempfile
import time
import unittest
import os
from pathlib import Path
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel_awstamp", os.path.join(BIN, "romp-kernel")).load_module()

SID = "11111111-2222-3333-4444-999999999999"
NOW = int(time.time())


def _node(nid, parent=None, why=None, at=None, rolled=False):
    nd = {"id": nid, "text": "a goal", "parentId": parent, "nodeComplete": False,
          "blocked": False, "cleared": False, "trail": [], "t": 100, "mt": 100}
    if why:
        nd["awaitingWhy"], nd["awaitingAt"] = why, at or 100
        nd["log"] = [{"ev_t": at or 100, "src": "closer", "kind": "awaiting", "why": why, "at": 1}]
    if rolled:
        nd["rolledUp"] = True
    return nd


class GoalAwaitingStamp(unittest.TestCase):
    def test_finds_the_tops_own_stamp(self):
        nodes = {"g1": _node("g1", why="the sweep it launched; will analyze when done")}
        self.assertEqual(km._goal_awaiting_stamp(nodes, "g1"),
                         "the sweep it launched; will analyze when done")

    def test_freshest_descendant_stamp_wins(self):
        nodes = {"g1": _node("g1"),
                 "s1": _node("s1", parent="g1", why="the older wait", at=100),
                 "s2": _node("s2", parent="g1", why="the newer wait", at=200)}
        self.assertEqual(km._goal_awaiting_stamp(nodes, "g1"), "the newer wait")

    def test_rolled_up_cache_is_not_a_verdict(self):
        # a rolledUp node's flags are tree-derived display state the materialize pass skips — a stale
        # awaitingWhy could sit there forever, so the scan must never read it
        nodes = {"g1": _node("g1"), "s1": _node("s1", parent="g1", why="stale", rolled=True)}
        self.assertIsNone(km._goal_awaiting_stamp(nodes, "g1"))

    def test_none_without_a_stamp_and_other_tops_never_leak(self):
        nodes = {"g1": _node("g1"), "g2": _node("g2", why="someone else's wait")}
        self.assertIsNone(km._goal_awaiting_stamp(nodes, "g1"), "another top's stamp never floors this one")


class NudgeFailedRespectsTheStamp(unittest.TestCase):
    """_mark_nudge_failed re-checks awaiting AT THE WRITE. The live re-check already exists; the stamp
    re-check is its restart-proof twin — after a kernel restart the live sources read None while the
    store still says the goal waits on async work, and without this the fork-nudge floor manufactured
    a false needs-you 'stalled' card on a genuinely-waiting session."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        td = Path(self.td.name)
        self._saved = (km.jd.STATE, km.jd.GOALDIR, km._session_awaiting, km._path_of)
        km.jd.STATE = td
        km.jd.GOALDIR = td / "goals"
        km.jd.GOALDIR.mkdir(parents=True)
        km._autonudge_cache.clear()
        self.gid = SID + ":g1"
        km._session_awaiting = lambda sid, path, idle, stamp=False: None   # the LIVE sources are dark (post-restart)
        km._path_of = lambda sid, now=None: "/nonexistent"
        (td / "auto-nudge.json").write_text(json.dumps(
            {"enabled": True, "nudged": {self.gid: {"count": 1, "lastTurnId": "t1"}}}))

    def tearDown(self):
        km.jd.STATE, km.jd.GOALDIR, km._session_awaiting, km._path_of = self._saved
        km._autonudge_cache.clear()
        self.td.cleanup()

    def _seed(self, why=None):
        nd = _node(self.gid, why=why, at=200)
        nd["text"] = "run the long parameter sweep"
        (km.jd.GOALDIR / (SID + ".json")).write_text(json.dumps({
            "rompUuid": SID, "seq": 1, "lastNode": self.gid, "placements": {}, "status": {},
            "nodes": {self.gid: nd}}))

    def test_a_stamped_goal_never_gets_the_failure_block(self):
        self._seed(why="the sweep it dispatched; will file results when it lands")
        km._mark_nudge_failed(self.gid)
        store = km.jd.load_goals(SID)
        self.assertFalse(store["nodes"][self.gid]["blocked"],
                         "the judge says the goal awaits async work — a nudge is never converted to a block")
        self.assertFalse(km._auto_nudge_data()["nudged"][self.gid].get("failed"),
                         "the episode isn't failed either — it re-arms cleanly when the wait ends")

    def test_without_a_stamp_the_stall_block_stands(self):
        self._seed(why=None)
        km._mark_nudge_failed(self.gid)
        store = km.jd.load_goals(SID)
        self.assertTrue(store["nodes"][self.gid]["blocked"], "the existing stall→block behavior stands")
        self.assertTrue(km._auto_nudge_data()["nudged"][self.gid].get("failed"))


class SessionLevelStamp(unittest.TestCase):
    """Source 2 of _session_awaiting (2026-07-22): the durable stamp reaching the SESSION-scoped surfaces
    (rail chip / chat-view chip / timeline lane) via stamp=True, so a genuinely-awaiting session stays
    green/faded across a kernel restart where the live sources go dark. The FEED passes stamp=False (its own
    per-goal _goal_awaiting_stamp scoping) so one goal's stamp never floors its siblings."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        td = Path(self.td.name)
        self._saved = (km.jd.STATE, km.jd.GOALDIR, km._tmux_sessions, km._states_awaiting_overlay)
        km.jd.STATE = td
        km.jd.GOALDIR = td / "goals"
        km.jd.GOALDIR.mkdir(parents=True)
        km._SESSION_STAMP_CACHE.clear()
        km._states_awaiting_overlay = lambda sid: None
        # a LIVE snapshot with an EMPTY bg-task set (SDK-style): sources 0-1 find nothing and fall through to
        # the stamp; the present "bgTasks" key means source 0.75 (transcript pairing) is skipped as well
        km._tmux_sessions = lambda: {SID: {"state": "", "since": None, "subagents": [], "bgTasks": []}}

    def tearDown(self):
        km.jd.STATE, km.jd.GOALDIR, km._tmux_sessions, km._states_awaiting_overlay = self._saved
        km._SESSION_STAMP_CACHE.clear()
        self.td.cleanup()

    def _seed(self, *stamps):
        nodes = {nid: _node(nid, why=why, at=at) for nid, why, at in stamps}
        (km.jd.GOALDIR / (SID + ".json")).write_text(json.dumps({
            "rompUuid": SID, "seq": 1, "placements": {}, "status": {}, "nodes": nodes}))

    def test_session_stamp_takes_the_freshest_across_ALL_tops(self):
        # session-level, so it scans every goal (not one subtree like _goal_awaiting_stamp) for the newest
        self._seed(("g1", "the older wait, padded", 100), ("g2", "the newer wait", 300))
        self.assertEqual(km._session_stamp_cached(SID), "the newer wait")

    def test_stamp_true_lifts_a_live_session_whose_live_sources_are_dark(self):
        self._seed(("g1", "the watcher it armed; files the clip when it triggers", 200))
        self.assertEqual(km._session_awaiting(SID, "/p", True, stamp=True),
                         "the watcher it armed; files the clip when it triggers")

    def test_stamp_false_stays_none_so_the_feed_scopes_per_goal(self):
        # the crux: the feed calls stamp=False, so the session-level signal is None for a stamp-only session
        # and _await_ok can never floor a SIBLING working goal — only _goal_awaiting_stamp floors the one goal
        self._seed(("g1", "some async wait", 200))
        self.assertIsNone(km._session_awaiting(SID, "/p", True, stamp=False))

    def test_a_dormant_session_never_resurrects_off_a_stale_stamp(self):
        self._seed(("g1", "a wait whose CLI is gone", 200))
        km._tmux_sessions = lambda: {}          # SID not in the live set → live is None
        self.assertIsNone(km._session_awaiting(SID, "/p", True, stamp=True))

    def test_an_open_turn_is_working_not_awaiting_even_with_a_stamp(self):
        self._seed(("g1", "async wait", 200))
        self.assertIsNone(km._session_awaiting(SID, "/p", False, stamp=True), "idle=False short-circuits")

    def test_the_chip_reads_awaitingBg_for_a_stamp_only_live_session(self):
        # end to end: no live source, only the stamp → the shared _session_chip derivation still says awaiting
        self._seed(("g1", "the watcher it armed", 200))
        saved = (km._session_working, km._api_error, km._compacting, km._interrupting)
        km._session_working = lambda turns: False
        km._api_error = lambda path: None
        km._compacting = lambda *a, **k: False
        km._interrupting = lambda *a, **k: False
        try:
            chip = km._session_chip(SID, "/p", {"turns": []}, km._tmux_sessions()[SID], NOW)
        finally:
            km._session_working, km._api_error, km._compacting, km._interrupting = saved
        self.assertEqual(chip, "awaitingBg")

    def test_the_cache_invalidates_when_the_store_changes(self):
        self._seed(("g1", "first wait", 200))
        self.assertEqual(km._session_stamp_cached(SID), "first wait")
        self._seed(("g1", "second wait, a different length so size differs", 300))
        self.assertEqual(km._session_stamp_cached(SID), "second wait, a different length so size differs")


if __name__ == "__main__":
    unittest.main()
