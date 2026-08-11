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
    """G1 — the incident. rollup_status pins a top at 'working' off any tracked item whose agentTask MIRROR
    says "open"; the mirror is stale when the LIVE store has since FINISHED that item. That one case — the
    card may already be done — is the ONLY thing this gate defers on. Open work is real work: a card both
    sides still call open is legitimately working, and a session that stopped with open work is exactly the
    stall the nudge must fire on (the user 2026-07-23, reversing the earlier over-broad open-work gates)."""

    def test_a_stale_mirror_defers_the_nudge(self):
        self._write_tasks([("11", "completed")])            # the live store says DONE
        st = _store(agentTask={"key": "11", "status": "open", "raw": "in_progress"})   # mirror says open
        self.assertTrue(km._plan_sync_pending(SID, st["nodes"]))
        self.assertIn("to-do sync", km._revivers_pending(SID, st, _turns(), GID))

    def test_a_mirror_that_says_done_never_defers(self):
        # a mirror whose status is not "open" cannot pin a false 'working' (rollup_status keys off open),
        # so a disagreement in the store-open direction is not this gate's concern — the card isn't working
        # because of it.
        self._write_tasks([("11", "in_progress")])
        st = _store(agentTask={"key": "11", "status": "done", "raw": "completed"})
        self.assertFalse(km._plan_sync_pending(SID, st["nodes"]))

    def test_an_agreeing_mirror_does_not_defer(self):
        self._write_tasks([("11", "in_progress")])
        st = _store(agentTask={"key": "11", "status": "open", "raw": "in_progress"})
        self.assertFalse(km._plan_sync_pending(SID, st["nodes"]))
        self.assertEqual(km._revivers_pending(SID, st, _turns(), GID), "",
                         "an up-to-date mirror leaves the nudge free to fire")

    def test_a_finer_status_move_within_open_does_not_defer(self):
        # both sides still 'open' (pending vs in_progress): the card is LEGITIMATELY working, so the nudge
        # must be free to fire even though the finer status has not synced. Open work is not a stale-working.
        self._write_tasks([("11", "in_progress")])
        st = _store(agentTask={"key": "11", "status": "open", "raw": "pending"})
        self.assertFalse(km._plan_sync_pending(SID, st["nodes"]))

    def test_a_live_item_romp_tracks_no_node_for_does_not_defer(self):
        # an untracked live item is new work the planner has not minted a node for yet — it cannot make the
        # card falsely 'working' (rollup keys off tracked mirrors), and gating on "romp has no node yet"
        # reads pending FOREVER on any item the planner won't mint. A stalled session with open work must
        # still nudge (and, unresolved, escalate to blocked) — the whole point of the last resort.
        self._write_tasks([("11", "pending")])
        self.assertFalse(km._plan_sync_pending(SID, _store()["nodes"]))
        self.assertEqual(km._revivers_pending(SID, _store(), _turns(), GID), "")

    def test_completed_and_open_untracked_items_alike_do_not_defer(self):
        # the 2026-07-23 wedge and its generalization: NEITHER a finished untracked to-do (history, never
        # re-minted) NOR an open untracked one (new work) is a stale-working signal. Counting either pinned
        # the gate True forever, so an idle session that had ever declared a to-do was never nudged and never
        # surfaced as stalled (no spinner either, since no pass runs on an idle session).
        self._write_tasks([("1", "completed"), ("2", "completed"), ("3", "pending")])
        self.assertFalse(km._plan_sync_pending(SID, _store()["nodes"]))

    def test_idle_session_with_finished_todos_and_agreeing_mirror_is_free_to_nudge(self):
        # the real-world shape: many completed untracked to-dos plus the still-open ones tracked by mirrors
        # that AGREE with the live store. Nothing is actually out of sync, so the nudge must be free to fire.
        self._write_tasks([("1", "completed"), ("2", "completed"), ("3", "completed"),
                           ("12", "in_progress"), ("13", "pending"), ("14", "pending")])
        nodes = {}
        for k, raw in (("12", "in_progress"), ("13", "pending"), ("14", "pending")):
            nid = SID + ":n" + k
            nodes[nid] = {"id": nid, "parentId": None, "t": T0, "mt": T0, "text": "step " + k,
                          "log": [], "agentTask": {"key": k, "status": "open", "raw": raw}}
        self.assertFalse(km._plan_sync_pending(SID, nodes))
        store = {"rompUuid": SID, "seq": 1, "nodes": nodes, "placements": {},
                 "status": {nid: "working" for nid in nodes}}
        self.assertEqual(km._revivers_pending(SID, store, _turns(), SID + ":n12"), "",
                         "an idle session working on open to-dos must be free to nudge")

    def test_stale_mirror_beside_open_work_still_defers(self):
        # the gate stays sharp for the case it exists for: even amid legitimately-open work, ONE tracked
        # mirror that says open while the live store finished that item means a card may be done → defer.
        self._write_tasks([("11", "in_progress"), ("12", "completed")])
        nodes = {}
        for k, mstatus, raw in (("11", "open", "in_progress"), ("12", "open", "in_progress")):
            nid = SID + ":n" + k
            nodes[nid] = {"id": nid, "parentId": None, "t": T0, "mt": T0, "text": "step " + k,
                          "log": [], "agentTask": {"key": k, "status": mstatus, "raw": raw}}
        self.assertTrue(km._plan_sync_pending(SID, nodes))       # n12's mirror is stale-open over a done item

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

    def test_a_judge_call_for_this_session_defers(self):
        jd.active_runs = lambda: [{"judge": "closer", "fsid": SID, "sent": 1.0}]
        self.assertEqual(km._revivers_pending(SID, _store(), _turns(), GID), jd.WHY_JUDGING)

    def test_another_sessions_judge_call_does_not_defer(self):
        # SESSION-SCOPED (2026-07-25): another session's judging cannot revive THIS card, so it must not
        # hold this card's nudge — the old any-run-anywhere form starved nudges fleet-wide.
        jd.active_runs = lambda: [{"judge": "closer",
                                   "fsid": "99999999-8888-7777-6666-555555555555", "sent": 1.0}]
        self.assertEqual(km._revivers_pending(SID, _store(), _turns(), GID), "")

    def test_the_global_pass_snapshot_does_not_defer(self):
        # The producer opens a pass (and its feed snapshot) every ~3s for the WHOLE fleet — that is the
        # cadence of the kernel, not a reviver for this card. Deferring on it let two adjacent gate ticks
        # land inside two DIFFERENT routine passes and mint a false "stalled" card (2026-07-25).
        km._goals_snap[0] = {}
        self.assertEqual(km._revivers_pending(SID, _store(), _turns(), GID), "")

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
        self.assertFalse(km._nudge_deferred_ok(GID, "the agent's to-do sync is due", NOW, SID))
        # the record carries WHY it deferred, not just when (2026-07-23) — the stall note is grounded in
        # it — and WHOSE session it is (2026-07-25), so the stall readers can live-verify a frozen claim
        self.assertEqual(self._d["deferred"][GID],
                         {"at": NOW, "why": "the agent's to-do sync is due", "seen": 1, "sid": SID},
                         "the first deferral is stamped with its reason and session")

    def test_a_legacy_bare_int_deferral_still_backstops(self):
        # A live state file written before the record grew a reason still holds bare epoch ints; reading one
        # must keep working (and never crash the tick), it just has no why to tell the card about.
        self._d["deferred"] = {GID: NOW}
        self.assertFalse(km._nudge_deferred_ok(GID, "the agent's to-do sync is due", NOW + 5),
                         "an int record is read as a deferral that started at that time")
        self.assertTrue(km._nudge_deferred_ok(GID, "the agent's to-do sync is due",
                                              NOW + km.NUDGE_DEFER_BACKSTOP_SECS + 1),
                        "…and its backstop still fires")

    def test_a_deferral_past_the_backstop_fires_anyway(self):
        km._nudge_deferred_ok(GID, "the agent's to-do sync is due", NOW)
        self.assertTrue(km._nudge_deferred_ok(GID, "the agent's to-do sync is due",
                                              NOW + km.NUDGE_DEFER_BACKSTOP_SECS + 1),
                        "a wedged reviver defers the nudge but can never LOSE it")

    def test_the_reviver_clearing_forgets_the_deferral(self):
        km._nudge_deferred_ok(GID, "the agent's to-do sync is due", NOW)
        self.assertTrue(km._nudge_deferred_ok(GID, "", NOW + 5))
        self.assertNotIn(GID, self._d.get("deferred") or {})


class StalledGoals(Base):
    """The user 2026-07-23: a card romp is HOLDING must be able to say why. The nudge gate already knows;
    it just wasn't writing it down, so a working card sat silent while nothing moved it."""

    def setUp(self):
        super().setUp()
        self._saved_data, self._saved_write = km._auto_nudge_data, km._write_auto_nudge
        self._d = {"nudged": {}}
        km._auto_nudge_data = lambda: self._d
        km._write_auto_nudge = lambda d: self._d.update(d)

    def tearDown(self):
        km._auto_nudge_data, km._write_auto_nudge = self._saved_data, self._saved_write
        super().tearDown()

    def test_one_deferral_is_not_yet_a_stall(self):
        # Most reasons are momentary and clear on the next run. Calling one a stall would light every card.
        km._nudge_deferred_ok(GID, "the agent's to-do sync is due", NOW, SID)
        self.assertEqual(km._stalled_goals(), {}, "a reason seen ONCE is churn, not a wedge")

    def test_the_same_reason_twice_is_a_stall(self):
        km._nudge_deferred_ok(GID, "the agent's to-do sync is due", NOW)
        km._nudge_deferred_ok(GID, "the agent's to-do sync is due", NOW + 30)
        self.assertEqual(km._stalled_goals(),
                         {GID: {"why": "the agent's to-do sync is due", "since": NOW}},
                         "a reason that survived the next gate run is a wedge, dated from when it started")

    def test_a_reason_that_changes_restarts_the_count_but_not_the_clock(self):
        km._nudge_deferred_ok(GID, "the card is already complete and merely unsettled", NOW, SID)
        km._nudge_deferred_ok(GID, "the agent's to-do sync is due", NOW + 30, SID)
        self.assertEqual(km._stalled_goals(), {}, "bouncing between reasons is not wedged on either one")
        km._nudge_deferred_ok(GID, "the agent's to-do sync is due", NOW + 60, SID)
        self.assertEqual(km._stalled_goals()[GID]["since"], NOW,
                         "…but the card HAS been stuck since the first deferral, so the clock is kept")

    def test_the_reviver_clearing_ends_the_stall(self):
        km._nudge_deferred_ok(GID, "the agent's to-do sync is due", NOW)
        km._nudge_deferred_ok(GID, "the agent's to-do sync is due", NOW + 30)
        self.assertTrue(km._stalled_goals())
        km._nudge_deferred_ok(GID, "", NOW + 60)
        self.assertEqual(km._stalled_goals(), {},
                         "the stall ends on the reviver running — nobody has to erase the note")

    def test_a_long_wedge_stops_rewriting_the_record(self):
        km._nudge_deferred_ok(GID, "the agent's to-do sync is due", NOW)
        writes = []
        km._write_auto_nudge = lambda d: (writes.append(1), self._d.update(d))
        for i in range(6):
            km._nudge_deferred_ok(GID, "the agent's to-do sync is due", NOW + 30 * (i + 1))
        self.assertEqual(len(writes), 1,
                         "the run count stops at the threshold — a wedge is not a file write per tick")

    def test_a_judging_hold_defers_the_nudge_but_never_presents_as_a_stall(self):
        # The user 2026-07-31 (superseding the 2026-07-25 live-verify): a goal held because romp's own
        # review is mid-flight is a goal romp is WORKING — the Analyzing… swirl carries that story
        # (spin-caption.ts, tip naming the hold), and a yellow chip there drew the eye to a state nobody
        # needs to act on. The GATE half is untouched: the deferral still holds the nudge (backstop and
        # all); only the presentation is gone, however live the call.
        self.assertFalse(km._nudge_deferred_ok(GID, jd.WHY_JUDGING, NOW, SID),
                         "the hold itself is real — the nudge stays deferred")
        km._nudge_deferred_ok(GID, jd.WHY_JUDGING, NOW + 30, SID)
        jd.active_runs = lambda: [{"judge": "closer", "fsid": SID, "sent": 1.0}]
        self.assertEqual(km._stalled_goals(), {},
                         "romp reviewing is romp working — never a stall chip, even mid-flight")

    def test_a_legacy_global_pass_record_is_never_presented(self):
        # pre-2026-07-25 records carried the global "a judge pass is mid-flight" and named no session —
        # unverifiable, and minted by the pass cadence rather than a wedge, so they are dropped on read
        # (they still pop normally on the next gate walk). This is what heals the stale-card epidemic.
        self._d["deferred"] = {GID: {"at": NOW, "why": "a judge pass is mid-flight", "seen": 2}}
        jd.active_runs = lambda: [{"judge": "closer", "fsid": SID, "sent": 1.0}]
        self.assertEqual(km._stalled_goals(), {})

    def test_a_paused_tiers_record_shows_only_while_paused(self):
        km._retry_paused_on = lambda: True
        km._nudge_deferred_ok(GID, "the judge tiers are paused (nothing could revive it)", NOW, SID)
        km._nudge_deferred_ok(GID, "the judge tiers are paused (nothing could revive it)", NOW + 30, SID)
        self.assertIn(GID, km._stalled_goals())
        km._retry_paused_on = lambda: False
        self.assertEqual(km._stalled_goals(), {},
                         "tiers resumed while the record was frozen → the claim no longer stands")

    def test_the_stands_predicate_is_shared_with_the_judge_reader(self):
        # stalled_facts (judge side, feeds the staller and the distill due-anchor) filters through the SAME
        # jd.stall_why_stands, so the two stall surfaces can never disagree about which reasons present.
        jd.active_runs = lambda: [{"judge": "closer", "fsid": SID, "sent": 1.0}]
        self.assertFalse(jd.stall_why_stands(jd.WHY_JUDGING, SID),
                         "a judging hold is romp working, never presented — even with the call live")
        self.assertFalse(jd.stall_why_stands("a judge pass is mid-flight", None),
                         "the legacy global form is screened the same way")
        self.assertTrue(jd.stall_why_stands("the agent's to-do sync is due", None),
                        "store-backed reasons pass through — their own passes reconcile them")


class StampEvidenceTime(unittest.TestCase):
    """The stamp's block must claim the RESPONSE turn's time, not wall clock — else it structurally
    outranks the user's own reply floor and a reply can NEVER void a nudge block."""

    def test_the_stamp_passes_an_evidence_time_through(self):
        import inspect
        src = inspect.getsource(km._mark_nudge_failed)
        self.assertIn("def _mark_nudge_failed(gid, ev_t=None, wake=False):", src)
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
