#!/usr/bin/env python3
"""A verdict filed after the nudge's evidence supersedes the nudge (the user 2026-07-29).

The audited incident, all fixtures SYNTHETIC: a card sat blocked on a question ("open the PR for the
notes-api branch, or hold it?"). The user answered in the thread; the unblocker ruled the question
answered and lifted the block. Five seconds later the stall nudge fired anyway — its arm predated the
answer — and its response turn was cut by a kernel restart. The failed-nudge evaluator then scored
that cut turn as "the response didn't resolve this" and filed a needs-you block OVER the unblock,
presenting the already-answered decision brief. The user re-answered a question they had answered
five minutes earlier.

The discipline, at both ends of the race: a verdict FILED (`at`; ev_t for legacy rows) after the
evidence the nudge machinery is acting on means the judges have already ruled on a newer world, so
the machinery stands down —
- fire time: _nudge_fire_list drops a goal whose diary gained a verdict after the ARM turn, even if
  the goal reads plain 'working' in the fresh store (the freshly-unblocked case above);
- eval time: _mark_nudge_failed retires the record as `moot` (no failed chip, no block) when a
  non-nudge verdict was filed after the RESPONSE turn.
A moot record keeps the anti-loop gate (lastTurnId pins the arm), and a genuinely still-stalled goal
re-arms on the next GENUINE ended turn, judged against the post-verdict world.
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
km = SourceFileLoader("romp_kernel_nudgemoot", os.path.join(BIN, "romp-kernel")).load_module()

SID = "11111111-2222-3333-4444-555555555555"
G1 = SID + ":g1"
NOW = 1781100000
ARM_T = NOW - 600                # the ended turn the stall was armed on
RESP_T = NOW - 120               # the nudge-response turn the evaluator scores


def _node(nid, text, **kw):
    d = {"id": nid, "text": text, "parentId": None, "nodeComplete": False,
         "blocked": False, "cleared": False, "trail": [], "t": NOW - 3600, "mt": NOW - 3600, "log": []}
    d.update(kw)
    return d


def _store(nodes, status=None):
    return {"rompUuid": SID, "seq": len(nodes), "lastNode": G1, "nodes": nodes, "placements": {},
            "status": status if status is not None else {n: "working" for n in nodes}}


class FireListArmOrdering(unittest.TestCase):
    """_nudge_fire_list's arm_t guard: the stall inference is stale once the judges filed anything newer."""

    def test_a_verdict_filed_after_the_arm_drops_the_fire(self):
        # the audited shape: unblocked moments ago → plain 'working' in the fresh store, but the
        # unblock's filing postdates the arm — the "it looks stalled" read predates the answer
        log = [{"ev_t": ARM_T, "src": "planner", "kind": "block", "why": "open the PR, or hold it?", "at": ARM_T + 5},
               {"ev_t": ARM_T, "src": "unblocker", "kind": "unblock", "why": "answered in the thread", "at": ARM_T + 300}]
        fresh = _store({G1: _node(G1, "ship the notes-api", log=log)})
        self.assertEqual(km._nudge_fire_list(fresh, [(G1, 1, False)], arm_t=ARM_T), [],
                         "the judges ruled after the arm — the status check would ask about a moved story")

    def test_old_history_before_the_arm_still_fires(self):
        log = [{"ev_t": ARM_T - 900, "src": "planner", "kind": "block", "why": "?", "at": ARM_T - 890},
               {"ev_t": ARM_T - 800, "src": "unblocker", "kind": "unblock", "why": "answered", "at": ARM_T - 790}]
        fresh = _store({G1: _node(G1, "ship the notes-api", log=log)})
        self.assertEqual([f[0] for f in km._nudge_fire_list(fresh, [(G1, 1, False)], arm_t=ARM_T)], [G1],
                         "a diary that predates the arm is exactly the stalled case — the nudge stands")

    def test_a_legacy_row_without_at_falls_back_to_ev_t(self):
        log = [{"ev_t": ARM_T + 60, "src": "closer", "kind": "block", "why": "?"}]   # no `at` (older writer)
        fresh = _store({G1: _node(G1, "ship the notes-api", log=log)})
        self.assertEqual(km._nudge_fire_list(fresh, [(G1, 1, False)], arm_t=ARM_T), [])

    def test_no_arm_t_keeps_the_old_contract(self):
        log = [{"ev_t": ARM_T + 60, "src": "unblocker", "kind": "unblock", "why": "answered", "at": ARM_T + 70}]
        fresh = _store({G1: _node(G1, "ship the notes-api", log=log)})
        self.assertEqual([f[0] for f in km._nudge_fire_list(fresh, [(G1, 1, False)])], [G1],
                         "callers that pass no arm turn get the pre-guard behavior unchanged")


class NudgeFailedMootWhenSuperseded(unittest.TestCase):
    """_mark_nudge_failed retires (moot) instead of blocking when the diary moved past the response."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        td = Path(self.td.name)
        # patch the KERNEL's own jd instance (km imports its own copy; a separately-loaded jd is a
        # different module object and the kernel would keep reading the live state dirs)
        self._saved = (km.jd.STATE, km.jd.GOALDIR, km._session_awaiting, km._path_of)
        km.jd.STATE = td
        km.jd.GOALDIR = td / "goals"
        km.jd.GOALDIR.mkdir(parents=True)
        km._autonudge_cache.clear()
        km._session_awaiting = lambda sid, path, idle, stamp=False: None
        km._path_of = lambda sid, now=None: "/nonexistent"
        (td / "auto-nudge.json").write_text(json.dumps(
            {"enabled": True, "nudged": {G1: {"count": 1, "lastTurnId": "t1", "at": RESP_T - 5}}}))

    def tearDown(self):
        km.jd.STATE, km.jd.GOALDIR, km._session_awaiting, km._path_of = self._saved
        km._autonudge_cache.clear()
        self.td.cleanup()

    def _write_store(self, log):
        (km.jd.GOALDIR / (SID + ".json")).write_text(json.dumps(
            _store({G1: _node(G1, "ship the notes-api", log=log)})))

    def test_a_later_unblock_retires_the_record_instead_of_blocking(self):
        # the audited shape: the unblocker ruled "answered" AFTER the response turn the evaluator
        # is scoring — filing "the response didn't resolve this" would contradict the diary and
        # resurface the answered brief
        self._write_store([{"ev_t": RESP_T - 60, "src": "planner", "kind": "block", "why": "?", "at": RESP_T - 50},
                           {"ev_t": RESP_T - 10, "src": "unblocker", "kind": "unblock",
                            "why": "answered in the thread", "at": RESP_T + 30}])
        self.assertEqual(km._mark_nudge_failed(G1, ev_t=RESP_T), "moot")
        store = km.jd.load_goals(SID)
        self.assertFalse(store["nodes"][G1]["blocked"],
                         "no procedural block over a diary that says the question was answered")
        rec = km._auto_nudge_data()["nudged"][G1]
        self.assertFalse(rec.get("failed"), "no 'nudge failed' chip either — the ask was superseded, not ignored")
        self.assertTrue(rec.get("moot"), "the episode is retired durably — the anti-loop arm stays pinned")

    def test_a_diary_that_did_not_move_still_blocks(self):
        self._write_store([{"ev_t": RESP_T - 300, "src": "planner", "kind": "block", "why": "?", "at": RESP_T - 290},
                           {"ev_t": RESP_T - 200, "src": "unblocker", "kind": "unblock", "why": "answered",
                            "at": RESP_T - 190}])
        self.assertEqual(km._mark_nudge_failed(G1, ev_t=RESP_T), "failed")
        store = km.jd.load_goals(SID)
        self.assertTrue(store["nodes"][G1]["blocked"], "the genuine failed-nudge → block behavior stands")
        self.assertTrue(km._auto_nudge_data()["nudged"][G1].get("failed"))

    def test_a_nudge_row_after_the_response_does_not_moot(self):
        # only REAL judges supersede; the machinery's own rows never gag its own escalation
        self._write_store([{"ev_t": RESP_T + 5, "src": "nudge", "kind": "block",
                            "why": "procedural", "at": RESP_T + 10}])
        self.assertEqual(km._mark_nudge_failed(G1, ev_t=RESP_T), "failed")

    def test_a_moot_record_is_settled_and_never_reevaluated(self):
        self._write_store([{"ev_t": RESP_T - 10, "src": "unblocker", "kind": "unblock",
                            "why": "answered", "at": RESP_T + 30}])
        self.assertEqual(km._mark_nudge_failed(G1, ev_t=RESP_T), "moot")
        self.assertIsNone(km._mark_nudge_failed(G1, ev_t=RESP_T),
                          "a settled (moot) episode is skipped exactly like a failed one")
        store = km.jd.load_goals(SID)
        self.assertFalse(store["nodes"][G1]["blocked"])


if __name__ == "__main__":
    unittest.main()
