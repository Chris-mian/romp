#!/usr/bin/env python3
"""The auto-nudge is a LAST RESORT (the user 2026-07-22).

"Nudges should ALWAYS fire — never miss one, because a missed nudge means a card stalls in 'working' and
is never surfaced — but should ALWAYS wait until every other possibility for something to revive the card
is exhausted."

The incident this encodes: a card's 'working' status came from a STALE agent-to-do mirror (Claude Code's
live task store had moved on; rollup_status pins a top at 'working' off any tracked item whose mirror
still says "open"). The nudge read that stale 'working', fired, and then STAMPED a needs-you block on a
card the session went on to finish by itself minutes later with no user input.

Two halves are tested here: the reviver gate (defer while something else can still act) and the
backstop (a wedged reviver defers the nudge but can never LOSE it). All fixtures SYNTHETIC.
"""
import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel_nlr", os.path.join(BIN, "romp-kernel")).load_module()
jd = km.jd

SID = "11111111-2222-3333-4444-555555555555"
GID = SID + ":g1"
NOW = 1781100000
T0 = NOW - 3600


def _store(**nd):
    node = {"id": GID, "parentId": None, "t": T0, "mt": T0, "text": "a goal", "log": []}
    node.update(nd)
    return {"rompUuid": SID, "seq": 1, "nodes": {GID: node}, "placements": {}, "status": {GID: "working"}}


def _turns():
    return [{"id": "t1", "t": T0, "end": T0 + 10, "ended": True, "atoms": []}]


class Base(unittest.TestCase):
    def setUp(self):
        km._task_plan_cache.clear()
        self._saved_cfg = os.environ.get("CLAUDE_CONFIG_DIR")
        self.td = tempfile.TemporaryDirectory()
        os.environ["CLAUDE_CONFIG_DIR"] = self.td.name
        self._saved_pause = km._retry_paused_on
        self._saved_snap = km._goals_snap[0]
        self._saved_runs = jd.active_runs
        km._retry_paused_on = lambda: False
        km._goals_snap[0] = None
        jd.active_runs = lambda: ()

    def tearDown(self):
        km._retry_paused_on = self._saved_pause
        km._goals_snap[0] = self._saved_snap
        jd.active_runs = self._saved_runs
        if self._saved_cfg is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = self._saved_cfg
        km._task_plan_cache.clear()
        self.td.cleanup()

    def _write_tasks(self, items):
        d = Path(self.td.name) / "tasks" / SID
        d.mkdir(parents=True, exist_ok=True)
        for i, (key, status) in enumerate(items):
            (d / ("%s.json" % key)).write_text(json.dumps(
                {"id": key, "subject": "step %s" % key, "status": status}))


class PlanSyncGate(Base):
    """G1 — the incident. The nudge already READ the agent-to-do data (for message wording); now it gates."""

    def test_a_stale_mirror_defers_the_nudge(self):
        self._write_tasks([("11", "completed")])            # the live store says DONE
        st = _store(agentTask={"key": "11", "status": "open", "raw": "in_progress"})   # mirror says open
        self.assertTrue(km._plan_sync_pending(SID, st["nodes"]))
        self.assertIn("to-do sync", km._revivers_pending(SID, st, _turns(), GID))

    def test_an_agreeing_mirror_does_not_defer(self):
        self._write_tasks([("11", "in_progress")])
        st = _store(agentTask={"key": "11", "status": "open", "raw": "in_progress"})
        self.assertFalse(km._plan_sync_pending(SID, st["nodes"]))
        self.assertEqual(km._revivers_pending(SID, st, _turns(), GID), "",
                         "an up-to-date mirror leaves the nudge free to fire")

    def test_a_finer_status_move_also_defers(self):
        # both still 'open', but pending -> in_progress means the sync has not landed
        self._write_tasks([("11", "in_progress")])
        st = _store(agentTask={"key": "11", "status": "open", "raw": "pending"})
        self.assertTrue(km._plan_sync_pending(SID, st["nodes"]))

    def test_a_live_item_romp_tracks_no_node_for_defers(self):
        self._write_tasks([("11", "pending")])
        self.assertTrue(km._plan_sync_pending(SID, _store()["nodes"]))

    def test_no_declared_plan_is_not_pending(self):
        self.assertFalse(km._plan_sync_pending(SID, _store()["nodes"]),
                         "a session that never declared a to-do list has nothing to be stale")

    def test_an_unreadable_task_store_defers_rather_than_nudging(self):
        # the authority failing must never wave a nudge through (repo policy: be loud, never fold)
        d = Path(self.td.name) / "tasks" / SID
        d.mkdir(parents=True, exist_ok=True)
        os.chmod(d, 0o000)
        try:
            self.assertTrue(km._plan_sync_pending(SID, _store()["nodes"]))
        finally:
            os.chmod(d, 0o755)


class OtherReviverGates(Base):
    def test_paused_judges_defer(self):
        km._retry_paused_on = lambda: True
        self.assertIn("paused", km._revivers_pending(SID, _store(), _turns(), GID))

    def test_a_pass_in_flight_defers(self):
        km._goals_snap[0] = {}
        self.assertIn("mid-flight", km._revivers_pending(SID, _store(), _turns(), GID))

    def test_a_reply_being_judged_defers(self):
        st = _store(followupPending=True)
        self.assertIn("reply", km._revivers_pending(SID, st, _turns(), GID))

    def test_a_complete_but_unsettled_card_defers(self):
        st = _store(nodeComplete=True)
        self.assertIn("complete", km._revivers_pending(SID, st, _turns(), GID))

    def test_a_quiet_store_does_not_defer(self):
        # the guard against the WORSE bug: absent markers must never read as "pending" and suppress
        # the nudge forever on a young or quiet store.
        self.assertEqual(km._revivers_pending(SID, _store(), _turns(), GID), "")


class DeferBackstop(Base):
    """Never MISS a nudge: a reviver that never clears defers, but the backstop lets it through."""

    def setUp(self):
        super().setUp()
        self._saved_data, self._saved_write = km._auto_nudge_data, km._write_auto_nudge
        self._d = {"nudged": {}}
        km._auto_nudge_data = lambda: self._d
        km._write_auto_nudge = lambda d: self._d.update(d)

    def tearDown(self):
        km._auto_nudge_data, km._write_auto_nudge = self._saved_data, self._saved_write
        super().tearDown()

    def test_first_deferral_holds_the_nudge(self):
        self.assertFalse(km._nudge_deferred_ok(GID, "the agent's to-do sync is due", NOW))
        self.assertEqual(self._d["deferred"][GID], NOW, "the first deferral is stamped")

    def test_a_deferral_past_the_backstop_fires_anyway(self):
        km._nudge_deferred_ok(GID, "the agent's to-do sync is due", NOW)
        self.assertTrue(km._nudge_deferred_ok(GID, "the agent's to-do sync is due",
                                              NOW + km.NUDGE_DEFER_BACKSTOP_SECS + 1),
                        "a wedged reviver defers the nudge but can never LOSE it")

    def test_the_reviver_clearing_forgets_the_deferral(self):
        km._nudge_deferred_ok(GID, "the agent's to-do sync is due", NOW)
        self.assertTrue(km._nudge_deferred_ok(GID, "", NOW + 5))
        self.assertNotIn(GID, self._d.get("deferred") or {})


class StampEvidenceTime(unittest.TestCase):
    """The stamp's block must claim the RESPONSE turn's time, not wall clock — else it structurally
    outranks the user's own reply floor and a reply can NEVER void a nudge block."""

    def test_the_stamp_passes_an_evidence_time_through(self):
        import inspect
        src = inspect.getsource(km._mark_nudge_failed)
        self.assertIn("def _mark_nudge_failed(gid, ev_t=None):", src)
        self.assertIn("_ev = int(ev_t or now)", src)
        self.assertIn('jd.record_verdict(store, nd, "nudge", "block", _ev', src)
        self.assertIn('jd.append_block(sid, gid, "nudge", why, _ev)', src)

    def test_the_call_site_supplies_the_response_turn_time(self):
        import inspect
        src = inspect.getsource(km._auto_nudge_session)
        self.assertIn("_mark_nudge_failed(gid, ev_t=", src)
        self.assertIn("_sdefer = _revivers_pending(sid, store, turns, gid)", src)
        self.assertLess(src.index("_sdefer = _revivers_pending"), src.index("_mark_nudge_failed(gid, ev_t="),
                        "the stamp waits for every other reviver BEFORE it interrupts the user")


if __name__ == "__main__":
    unittest.main()
