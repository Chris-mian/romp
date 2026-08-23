#!/usr/bin/env python3
"""A DORMANT session's stamped-awaiting Working card converts to a procedural block (the user
2026-08-22): the CLI died while a judged wait still stood, so nothing that could answer it is
running — yet a live awaiting stamp exempted the card from the whole ladder (wake, nudge, staller)
and it sat "paused" in Working forever (two live cards measured at 79 hours). The conversion is
event-triggered (the death transition; a boot catch-up sweep), once per stamp episode, stands down
for restart cuts (the resume machinery owns those), and its why is a recognized procedural block.
SYNTHETIC fixtures only (placeholder UUIDs, invented text)."""
import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")

# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
SourceFileLoader("romp_event_model", os.path.join(BIN, "romp-event-model")).load_module()
jd = SourceFileLoader("romp_judge", os.path.join(BIN, "romp-judge")).load_module()
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "test-token-DO-NOT-USE")
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()

STAMP_T = 1781100000
_N = [0]


def _fresh_sid():
    """A distinct sid per test: the goals-store cache is mtime-keyed, and same-second reseeds of one
    sid would hand a later test the previous test's mutated store object."""
    _N[0] += 1
    return "11111111-2222-3333-4444-5555555555%02d" % _N[0]


SID = ""
GID = ""


def _seed_store(awaiting=True):
    store = jd.load_goals(SID)
    nd = {"id": GID, "text": "delegate the batch and report", "parentId": None,
          "nodeComplete": False, "blocked": False, "cleared": False, "t": STAMP_T - 100,
          "mt": STAMP_T, "trail": [], "doneWhy": "",
          "log": [{"ev_t": STAMP_T, "src": "closer", "kind": "awaiting",
                   "why": "both workers' report-backs", "at": STAMP_T}]}
    if awaiting:
        nd["awaitingWhy"] = "both workers' report-backs"
        nd["awaitingAt"] = STAMP_T
        nd["awaitingKind"] = "peer"
    store["nodes"][GID] = jd.GuardedNode(nd)
    store["status"] = {GID: "working"}
    jd.save_goals(SID, store)
    return store


def _write_state(state, t):
    d = jd.STATE / "states"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / (SID + ".jsonl"), "w") as f:
        f.write(json.dumps({"state": state, "t": t}) + "\n")


class DeadWaitBlock(unittest.TestCase):
    def setUp(self):
        global SID, GID
        SID = _fresh_sid()
        GID = SID + ":g1"
        km._PREV_ALIVE = None
        self.nudged = {}

    def tearDown(self):
        for d in (jd.GOALDIR, jd.STATE / "states"):
            for f in d.glob("*"):
                f.unlink()
        p = jd.STATE / "auto-nudge.json"
        if p.exists():
            p.unlink()

    def test_dormant_stamped_card_converts_to_a_recognized_procedural_block(self):
        _seed_store()
        _write_state("idle", STAMP_T + 50)
        fired = km._dead_wait_block(SID, GID, STAMP_T, "both workers' report-backs", self.nudged, STAMP_T + 900)
        self.assertTrue(fired)
        store = jd.load_goals(SID)
        nd = store["nodes"][GID]
        self.assertTrue(nd.get("blocked"), "the card lands in the terminal the ladder promises: blocked")
        self.assertTrue(str(nd.get("blockWhy") or "").startswith(jd.DEAD_WAIT_WHY_PREFIX))
        self.assertIn("both workers' report-backs", nd.get("blockWhy") or "",
                      "the brief names WHAT died with the session")
        self.assertTrue(jd.procedural_block_why(nd.get("blockWhy")),
                        "a dead wait is romp bookkeeping — the briefer must not invent a decision")
        # the evidence time is the newest recorded event (the settle), never wall-clock now
        blk = [e for e in nd.get("log", []) if e.get("kind") == "block"][-1]
        self.assertEqual(blk.get("ev_t"), STAMP_T + 50)

    def test_an_open_turn_last_state_stands_down_for_the_resume_machinery(self):
        _seed_store()
        _write_state("working", STAMP_T + 50)   # a restart CUT — the resume nudge owns this card
        self.assertFalse(km._dead_wait_block(SID, GID, STAMP_T, "w", self.nudged, STAMP_T + 900))
        self.assertFalse(jd.load_goals(SID)["nodes"][GID].get("blocked"))

    def test_once_per_stamp_episode_and_a_new_anchor_rearms(self):
        _seed_store()
        _write_state("idle", STAMP_T + 50)
        self.assertTrue(km._dead_wait_block(SID, GID, STAMP_T, "w", self.nudged, STAMP_T + 900))
        self.assertFalse(km._dead_wait_block(SID, GID, STAMP_T, "w", self.nudged, STAMP_T + 950),
                         "same episode never converts twice")
        # a genuinely NEW stamp episode (newer anchor) re-arms — but the fresh-store guard still
        # refuses while the card sits blocked, so no double-block either
        self.assertFalse(km._dead_wait_block(SID, GID, STAMP_T + 100, "w", self.nudged, STAMP_T + 990))

    def test_a_lifted_stamp_or_resolved_card_stands_down(self):
        _seed_store(awaiting=False)             # no live stamp on the fresh read
        _write_state("idle", STAMP_T + 50)
        self.assertFalse(km._dead_wait_block(SID, GID, STAMP_T, "w", self.nudged, STAMP_T + 900))

    def test_boot_catchup_sweep_converts_dormant_stores_and_spares_alive_ones(self):
        _seed_store()
        _write_state("idle", STAMP_T + 50)
        km._PREV_ALIVE = None                   # first tick after boot
        km._dead_wait_sweep(set(), self.nudged, STAMP_T + 900)
        self.assertTrue(jd.load_goals(SID)["nodes"][GID].get("blocked"), "boot catch-up found the dead wait")
        # …and an ALIVE session is never swept: reseed and list it as alive
        self.tearDown(); self.setUp()
        _seed_store()
        _write_state("idle", STAMP_T + 50)
        km._PREV_ALIVE = None
        km._dead_wait_sweep({SID}, self.nudged, STAMP_T + 900)
        self.assertFalse(jd.load_goals(SID)["nodes"][GID].get("blocked"))

    def test_a_post_stamp_peer_ack_does_not_hide_the_wait_from_the_sweep(self):
        # the 100-hour survivors (2026-08-23): a worker's "starting now" mail seconds after the stamp
        # made the peer-answered supersede read the wait as met, so the sweep stood down forever while
        # the chip kept showing awaiting. The sweep reads the RAW stamp: a dormant owner can't process
        # an answer anyway, so a recorded wait on a Working card converts regardless.
        _seed_store()
        _write_state("idle", STAMP_T + 50)
        saved = km._peer_answered_at
        km._peer_answered_at = lambda sid: STAMP_T + 110   # an ack landed just after the stamp
        try:
            km._PREV_ALIVE = None
            km._dead_wait_sweep(set(), self.nudged, STAMP_T + 900)
        finally:
            km._peer_answered_at = saved
        self.assertTrue(jd.load_goals(SID)["nodes"][GID].get("blocked"),
                        "the supersede must not hide a dormant owner's wait from the sweep")

    def test_death_transition_triggers_between_ticks(self):
        _seed_store()
        _write_state("idle", STAMP_T + 50)
        km._PREV_ALIVE = {SID}                  # was alive last tick…
        km._dead_wait_sweep(set(), self.nudged, STAMP_T + 900)   # …gone this tick: the death event
        self.assertTrue(jd.load_goals(SID)["nodes"][GID].get("blocked"))

    def test_the_block_writer_settles_the_brief_inline(self):
        # "Stuck on Distilling" (the user 2026-08-23): a dead store falls out of discover's 48h window,
        # so no distill pass ever writes its brief — the card asked for one forever. The procedural why
        # IS the decision; the writer settles blockSummary/briefedMt itself.
        _seed_store()
        _write_state("idle", STAMP_T + 50)
        km._PREV_ALIVE = None
        km._dead_wait_sweep(set(), self.nudged, STAMP_T + 900)
        nd = jd.load_goals(SID)["nodes"][GID]
        self.assertTrue(nd.get("blocked"))
        self.assertEqual(nd.get("blockSummary"), nd.get("blockWhy"),
                         "the brief settles at the writer — never left for a pass that will not come")
        self.assertIsNotNone(nd.get("briefedMt"))

    def test_the_sweep_heals_a_pre_existing_briefless_procedural_block(self):
        # Blocks written before the writers settled briefs inline: blocked, procedural why, no brief.
        _seed_store()
        st = jd.load_goals(SID)
        nd = st["nodes"][GID]
        jd.record_verdict(st, nd, "nudge", "block", STAMP_T + 100,
                          why=jd.dead_wait_block_why("the full test suite it kicked off"))
        jd.rollup_status(st, False)
        jd.save_goals(SID, st)
        self.assertIsNone(jd.load_goals(SID)["nodes"][GID].get("blockSummary"))
        _write_state("idle", STAMP_T + 50)
        km._PREV_ALIVE = None
        km._dead_wait_sweep(set(), self.nudged, STAMP_T + 900)
        nd = jd.load_goals(SID)["nodes"][GID]
        self.assertTrue((nd.get("blockSummary") or "").startswith(jd.DEAD_WAIT_WHY_PREFIX),
                        "the repair settles the stuck card's brief from its own why")

    def test_a_genuine_block_why_is_never_repaired_over(self):
        # The repair takes PROCEDURAL whys only: a genuine decision brief stays the briefer's job.
        _seed_store()
        st = jd.load_goals(SID)
        nd = st["nodes"][GID]
        jd.record_verdict(st, nd, "closer", "block", STAMP_T + 100,
                          why="pick a database: sqlite or postgres?")
        jd.rollup_status(st, False)
        jd.save_goals(SID, st)
        _write_state("idle", STAMP_T + 50)
        km._PREV_ALIVE = None
        km._dead_wait_sweep(set(), self.nudged, STAMP_T + 900)
        self.assertIsNone(jd.load_goals(SID)["nodes"][GID].get("blockSummary"),
                          "a substantive ask keeps waiting for the real briefer")

    def test_wake_goal_routes_its_dormant_branch_here(self):
        src = open(os.path.join(BIN, "romp-kernel")).read()
        self.assertIn("return _dead_wait_block(sid, gid, at, why, nudged, now)", src)
        self.assertIn("_dead_wait_sweep(alive_ids, nudged, now)", src)


if __name__ == "__main__":
    unittest.main()
