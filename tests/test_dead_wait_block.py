#!/usr/bin/env python3
"""A DORMANT session's stamped-awaiting Working card converts to a procedural block (the user
2026-08-22): the CLI died while a judged wait still stood, so nothing that could answer it is
running — yet a live awaiting stamp exempted the card from the whole ladder (wake, nudge, staller)
and it sat "paused" in Working forever (two live cards measured at 79 hours). The conversion is
event-triggered (the death transition; a boot catch-up sweep), once per stamp episode, stands down
for restart cuts (the resume machinery owns those), and its why is a recognized procedural block.
SYNTHETIC fixtures only (placeholder UUIDs, invented text)."""
import contextlib
import inspect
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")

# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
load_source("romp_event_model", os.path.join(BIN, "romp-event-model"))
jd = load_source("romp_judge", os.path.join(BIN, "romp-judge"))
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "test-token-DO-NOT-USE")
km = load_source("romp_kernel", os.path.join(BIN, "romp-kernel"))

STAMP_T = 1781100000
_N = [0]


def _fresh_sid():
    """A distinct sid per test: the goals-store cache is mtime-keyed, and same-second reseeds of one
    sid would hand a later test the previous test's mutated store object."""
    _N[0] += 1
    return "%08d-aaaa-4bbb-8ccc-dddddddddddd" % _N[0]      # never the shared 11111111-2222-... placeholder, at any count


SID = ""
GID = ""


class _FakeCodex:
    """The Codex backend as the corroborator reads it: a registry of sids, each still owned (alive) or
    marked dead, or a registry the backend could not read."""
    def __init__(self, rows=None, unreadable=False):
        self.rows = dict(rows or {})            # sid → alive
        self._registry_unreadable = unreadable

    def _session(self, sid):
        return self.rows.get(sid) if sid in self.rows else None   # a row (truthy or not) vs no row

    def owns(self, sid):
        return bool(self.rows.get(sid))


OTHER_SID = "11111111-2222-3333-4444-777777777777"   # a bystander SDK session: the registry is never empty


def _register_name(sid, ended=True):
    """A names-registry entry — the launch record BOTH backends write at creation — plus the SDK reg an
    ENDED session keeps (the backend never unlinks a reg; the kill flips alive to False): the shape of a
    dead SDK sender. A names entry with NO reg is dead history only when nothing shows recent life while
    the registry holds no regs at all; with fresh states rows beside an empty registry it reads as a
    registry moved aside, on which the corroborator stands down (tests/test_sdk_registry_blind.py). A sid
    with no reg and no names entry exists only as a transcript, and no liveness owner here can answer
    for it. Tests that need another reg shape write it after this call. ended=False models a sid the SDK
    registry never held (a Codex session, or plain history) on a machine that still runs OTHER SDK
    sessions: no reg for the sid, a bystander's alive reg beside it, so the registry is not empty."""
    jd.NAMES.mkdir(parents=True, exist_ok=True)
    (jd.NAMES / sid).write_text("web\t~/notes-api\t#3355aa\t#ffffff\n")
    jd.SDKDIR.mkdir(parents=True, exist_ok=True)
    if ended:
        (jd.SDKDIR / (sid + ".json")).write_text(json.dumps({"sid": sid, "alive": False}))
    else:
        (jd.SDKDIR / (OTHER_SID + ".json")).write_text(json.dumps({"sid": OTHER_SID, "alive": True}))


def _seed_store(awaiting=True, named=True, ended=True):
    # named=True: the fixture models a romp-LAUNCHED session (the usual world), so the corroborator
    # is entitled to settle it; named=False models a transcript-derived one (no launch record).
    if named:
        _register_name(SID, ended=ended)
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


class _HermeticDeadWait(unittest.TestCase):
    def setUp(self):
        global SID, GID
        SID = _fresh_sid()
        GID = SID + ":g1"
        km._PREV_ALIVE = None
        self.nudged = {}
        # hermetic liveness: the corroboration the sweep does before converting reads the Codex
        # backend's records; a readable registry that knows none of these sids is the
        # corroborated-dead world these tests were written in (a named sid with no record anywhere
        # is dead history). Never the real module, which would bind to this box's Codex state.
        self.codex = _FakeCodex()
        self._saved_codex = km._codex
        km._codex = lambda: self.codex

    def tearDown(self):
        km._codex = self._saved_codex
        for d in (jd.GOALDIR, jd.STATE / "states", jd.SDKDIR, jd.STATE / "gone", jd.NAMES, jd._overrides_dir()):   # the blocks journals too
            if d.is_dir():
                for f in d.glob("*"):
                    f.unlink()
        p = jd.STATE / "auto-nudge.json"
        if p.exists():
            p.unlink()


class DeadWaitBlock(_HermeticDeadWait):
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

    def test_the_sweep_reads_through_the_shared_view_and_loads_a_private_store_only_to_write(self):
        """Boot follow-up (2026-09-13): the sweep loaded a private goal store per candidate (load_goals with its journal replay,
        9 of the 13 autoNudge stack samples of the measurement boot), and the block writer loaded a second. The read path
        takes the walk's shared read-only view; a mutable load happens only to heal or to block, and the reads are counted
        under memos.deadWait."""
        _seed_store()
        _write_state("idle", STAMP_T + 50)
        km._PREV_ALIVE = None
        loads = []; shared = []
        real_load, real_shared = jd.load_goals, jd.load_goals_shared_or_fault
        jd.load_goals = lambda sid: (loads.append(sid), real_load(sid))[1]
        jd.load_goals_shared_or_fault = lambda sid: (shared.append(sid), real_shared(sid))[1]
        before = dict(km._DEAD_WAIT_STATS)
        try:
            km._dead_wait_sweep(set(), self.nudged, STAMP_T + 900)
        finally:
            jd.load_goals, jd.load_goals_shared_or_fault = real_load, real_shared
        self.assertTrue(jd.load_goals(SID)["nodes"][GID].get("blocked"), "the dead wait still converts")
        self.assertEqual(shared.count(SID), 1, "one shared read-only view for the candidate: %r" % shared)
        self.assertEqual(loads.count(SID), 1, "one private load, the block writer's own: %r" % loads)
        d = {k: km._DEAD_WAIT_STATS[k] - before.get(k, 0) for k in km._DEAD_WAIT_STATS}
        self.assertEqual((d["candidates"], d["sharedLoads"], d["mutableLoads"], d["blocks"]), (1, 1, 1, 1), "the writer's load counts: %r" % d)

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

    def _count_loads(self):
        loads, shared = [], []
        real_load, real_shared = jd.load_goals, jd.load_goals_shared_or_fault
        jd.load_goals = lambda sid: (loads.append(sid), real_load(sid))[1]
        jd.load_goals_shared_or_fault = lambda sid: (shared.append(sid), real_shared(sid))[1]
        self.addCleanup(lambda: setattr(jd, "load_goals", real_load))
        self.addCleanup(lambda: setattr(jd, "load_goals_shared_or_fault", real_shared))
        return loads, shared

    def test_the_alive_sessions_stores_are_read_through_the_shared_view_once_per_pass(self):
        """Round two, medium 1: the pass's dominant read was untouched: for every candidate, every ALIVE session's store was
        loaded privately (C times A loads, reported as zero). The peer-death arm reads only; it takes the shared view, one read
        per store per pass, and every mutable load the pass makes counts."""
        _seed_store()
        _write_state("idle", STAMP_T + 50)
        alive = set()
        for i in range(3):                                                  # three alive sessions with stores of their own
            a = _fresh_sid(); alive.add(a)
            (jd.SDKDIR / (a + ".json")).write_text(json.dumps({"sid": a, "alive": True}))
            jd.save_goals(a, jd.load_goals(a))
        km._PREV_ALIVE = None
        loads, shared = self._count_loads()
        before = dict(km._DEAD_WAIT_STATS)
        km._dead_wait_sweep(alive, self.nudged, STAMP_T + 900)
        pass_loads, pass_shared = list(loads), list(shared)                 # the pass's own reads, before this test reads anything
        d = {k: km._DEAD_WAIT_STATS[k] - before.get(k, 0) for k in km._DEAD_WAIT_STATS}
        self.assertTrue(jd.load_goals(SID)["nodes"][GID].get("blocked"))
        self.assertEqual([x for x in pass_loads if x in alive], [], "no private load of an alive session's store: %r" % pass_loads)
        self.assertEqual(sorted(x for x in pass_shared if x in alive), sorted(alive), "each alive store read once through the view")
        self.assertEqual((d["sharedLoads"], d["mutableLoads"], d["blocks"]), (4, 1, 1), "1 candidate + 3 alive shared; the writer's load: %r" % d)
        self.assertEqual(len(pass_loads), d["mutableLoads"], "every private load the pass made is counted: %r" % pass_loads)

    def test_the_heal_stands_down_when_a_peer_settled_the_brief_between_the_two_reads(self):
        """Round two, medium 2: to_heal was decided from the frozen view and the write landed on nodes from a later mutable load
        with no re-check, so a peer writer that settled the brief in between (a judge tier thread's save_goals) was clobbered.
        The heal re-tests the fresh node: still blocked, still briefless, still a procedural block."""
        _seed_store()
        st = jd.load_goals(SID); nd = st["nodes"][GID]
        jd.record_verdict(st, nd, "nudge", "block", STAMP_T + 100, why=jd.dead_wait_block_why("the full test suite it kicked off"))
        jd.rollup_status(st, False); jd.save_goals(SID, st)
        self.assertIsNone(jd.load_goals(SID)["nodes"][GID].get("blockSummary"))
        _write_state("idle", STAMP_T + 50)
        km._PREV_ALIVE = None
        real_load = jd.load_goals
        def peer_settles_then_load(sid):                                    # the peer's write lands between the view and the heal's load
            if sid == SID:
                st2 = real_load(sid); st2["nodes"][GID]["blockSummary"] = "the peer's genuine brief"; st2["nodes"][GID]["briefParts"] = ["p"]
                jd.save_goals(sid, st2)
            return real_load(sid)
        jd.load_goals = peer_settles_then_load
        before = dict(km._DEAD_WAIT_STATS)
        try:
            km._dead_wait_sweep(set(), self.nudged, STAMP_T + 900)
        finally:
            jd.load_goals = real_load
        self.assertEqual(jd.load_goals(SID)["nodes"][GID].get("blockSummary"), "the peer's genuine brief", "the peer's brief survives")
        self.assertEqual(km._DEAD_WAIT_STATS["healed"] - before["healed"], 0, "nothing healed, nothing saved over the peer")

    def test_blocks_counts_a_block_written_not_a_writer_called(self):
        """Round two, low 1: `blocks` counted writer calls at one site; a dormant candidate whose last state is working (the
        writer stands down for the resume machinery) counted one with nothing blocked."""
        _seed_store()
        _write_state("working", STAMP_T + 50)                              # a cut mid-turn: the writer stands down
        km._PREV_ALIVE = None
        before = dict(km._DEAD_WAIT_STATS)
        km._dead_wait_sweep(set(), self.nudged, STAMP_T + 900)
        self.assertFalse(jd.load_goals(SID)["nodes"][GID].get("blocked"))
        d = {k: km._DEAD_WAIT_STATS[k] - before.get(k, 0) for k in km._DEAD_WAIT_STATS}
        self.assertEqual((d["blocks"], d["mutableLoads"]), (0, 0), "the writer stood down before its load; no block written: %r" % d)

    def test_a_view_the_sweep_cannot_read_stands_the_candidate_down_re_armed_and_the_next_pass_places_the_block(self):
        """Round two, lows 2 and 3: the fault road. _or_fault catches OSError alone, so a malformed journal row (a ValueError)
        escaped to the per-candidate except and spent the death transition silently; any failure of the view is a fault:
        counted, the candidate re-armed, and the next pass with the store readable places the block."""
        _seed_store()
        _write_state("idle", STAMP_T + 50)
        km._PREV_ALIVE = None
        real_shared = jd.load_goals_shared_or_fault
        before = dict(km._DEAD_WAIT_STATS)
        for fault in (ValueError("malformed journal row"), None):
            jd.load_goals_shared_or_fault = (lambda sid, f=fault: (_ for _ in ()).throw(f)) if isinstance(fault, ValueError) else real_shared
            try:
                km._dead_wait_sweep(set(), self.nudged, STAMP_T + 900)
            finally:
                jd.load_goals_shared_or_fault = real_shared
            if fault is not None:
                self.assertFalse(jd.load_goals(SID)["nodes"][GID].get("blocked"), "nothing filed on a fault")
                self.assertIn(SID, km._PREV_ALIVE, "re-armed: the transition is not spent")
                self.assertEqual(km._DEAD_WAIT_STATS["loadFaults"] - before["loadFaults"], 1)
        self.assertTrue(jd.load_goals(SID)["nodes"][GID].get("blocked"), "the next pass placed the block")
        jd.load_goals_shared_or_fault = lambda sid: (None, OSError("EIO"))
        _seed_store(); _write_state("idle", STAMP_T + 50); km._PREV_ALIVE = None
        try:
            km._dead_wait_sweep(set(), self.nudged, STAMP_T + 900)
        finally:
            jd.load_goals_shared_or_fault = real_shared
        self.assertEqual(km._DEAD_WAIT_STATS["loadFaults"] - before["loadFaults"], 2, "an OSError fault counts the same")

    def test_blocks_and_loads_are_counted_inside_the_writers_wherever_called(self):
        """Round three, medium 1: the wake goal's dormant-owner branch is a fourth _dead_wait_block caller; its load bumped
        mutableLoads while its block went uncounted, since blocks was bumped at the sweep's three sites only. Both counters
        live inside the writers, so they mean what the writer did wherever it is called."""
        _seed_store()
        _write_state("idle", STAMP_T + 50)
        before = dict(km._DEAD_WAIT_STATS)
        self.assertTrue(km._dead_wait_block(SID, GID, STAMP_T, "both workers' report-backs", self.nudged, STAMP_T + 900),
                        "the writer called directly (the wake goal's dormant branch) writes the block")
        d = {k: km._DEAD_WAIT_STATS[k] - before.get(k, 0) for k in km._DEAD_WAIT_STATS}
        self.assertEqual((d["mutableLoads"], d["blocks"], d["passes"]), (1, 1, 0), "its load and its block, no pass: %r" % d)
        src = inspect.getsource(km._dead_wait_sweep)
        self.assertNotIn('_DEAD_WAIT_STATS["blocks"]', src, "the sweep bumps no block count of its own")

    def test_a_non_oserror_view_fault_is_said_once_per_episode_and_an_alive_view_fault_re_arms_the_candidate(self):
        """Round three, medium 2: a ValueError out of the view (a malformed journal row) was swallowed with no stderr where the base
        printed a traceback, and on an alive session's store it lost that peer's conversion for the transition. It is named on
        stderr once per episode through the pass's collapse, and an alive store the view cannot read re-arms the candidate."""
        _seed_store()
        _write_state("idle", STAMP_T + 50)
        alive = _fresh_sid(); (jd.SDKDIR / (alive + ".json")).write_text(json.dumps({"sid": alive, "alive": True}))
        jd.save_goals(alive, jd.load_goals(alive))
        real_shared = jd.load_goals_shared_or_fault
        def faulty(sid, target):
            def f(x):
                if x == target:
                    raise ValueError("journal row: t is not a number")
                return real_shared(x)
            return f
        err = io.StringIO()
        km._PREV_ALIVE = None
        jd.load_goals_shared_or_fault = faulty(SID, SID)                     # the candidate's own view raises
        try:
            with redirect_stderr(err):
                km._dead_wait_sweep({alive}, self.nudged, STAMP_T + 900)
                km._dead_wait_sweep({alive}, self.nudged, STAMP_T + 901)    # the same episode: not said again
        finally:
            jd.load_goals_shared_or_fault = real_shared
        self.assertEqual(err.getvalue().count("the goal-store view raised"), 1, "said once per episode: %r" % err.getvalue())
        self.assertIn("ValueError", err.getvalue())
        self.assertIn(SID, km._PREV_ALIVE, "re-armed")
        self.assertFalse(jd.load_goals(SID)["nodes"][GID].get("blocked"))
        km._PREV_ALIVE = None
        jd.load_goals_shared_or_fault = faulty(SID, alive)                   # the ALIVE session's view raises
        try:
            with redirect_stderr(io.StringIO()):
                km._dead_wait_sweep({alive}, self.nudged, STAMP_T + 902)
        finally:
            jd.load_goals_shared_or_fault = real_shared
        self.assertIn(SID, km._PREV_ALIVE, "an alive store the view cannot read re-arms the candidate: the peer conversion waits for the next pass")
        with redirect_stderr(io.StringIO()):
            km._dead_wait_sweep({alive}, self.nudged, STAMP_T + 903)        # healed: the next pass converts
        self.assertTrue(jd.load_goals(SID)["nodes"][GID].get("blocked"))

    def test_a_view_that_degrades_to_a_private_load_is_counted_as_a_fallback_and_another_threads_load_is_not(self):
        """Round three, low 2, and round four's medium: the shared view falls back to load_goals internally (an absent store file,
        an unreadable journal, unparseable bytes, the cache off); those loads counted under sharedLoads only, so /perf could
        claim the saving with the cache off. sharedFallback counts them by the OBJECT the view returned (a plain store where
        the frozen one is due), never by a delta over the process-global load count, which another thread's private load
        moved: 200 warm views under a burst of load_goals on another thread counted 166 degrades where none happened."""
        _seed_store()
        _write_state("idle", STAMP_T + 50)
        alive = _fresh_sid(); (jd.SDKDIR / (alive + ".json")).write_text(json.dumps({"sid": alive, "alive": True}))   # no store FILE
        km._PREV_ALIVE = None
        before = dict(km._DEAD_WAIT_STATS)
        km._dead_wait_sweep({alive}, self.nudged, STAMP_T + 900)
        d = {k: km._DEAD_WAIT_STATS[k] - before.get(k, 0) for k in km._DEAD_WAIT_STATS}
        self.assertEqual(d["sharedFallback"], 1, "the alive store without a file fell back to a private load: %r" % d)
        other = _fresh_sid(); jd.save_goals(other, jd.load_goals(other))    # a readable, cached store for the warm views
        import threading
        stop = threading.Event()
        def burst():                                                      # another thread's private loads, the WS handler's shape
            while not stop.is_set():
                jd.load_goals(SID)
        th = threading.Thread(target=burst, daemon=True); th.start()
        try:
            before = dict(km._DEAD_WAIT_STATS)
            for _ in range(200):
                store, fault = km._dead_wait_shared_view(other)
                self.assertIsNone(fault); self.assertIsInstance(store, jd.FrozenStore)
        finally:
            stop.set(); th.join(5)
        d = {k: km._DEAD_WAIT_STATS[k] - before.get(k, 0) for k in km._DEAD_WAIT_STATS}
        self.assertEqual((d["sharedLoads"], d["sharedFallback"]), (200, 0), "200 warm views, no degrade, whatever another thread loaded: %r" % d)

    def test_a_fault_whose_text_changes_on_the_same_store_is_a_new_episode(self):
        """Round four, low 2: the episode compared the SET of sids, so a different ValueError on the same store was never re-said,
        where the OSError episode table treats a different text as a new episode; the pairs (sid, text) are compared."""
        _seed_store()
        _write_state("idle", STAMP_T + 50)
        real_shared = jd.load_goals_shared_or_fault
        err = io.StringIO()
        km._PREV_ALIVE = None
        try:
            for text in ("journal row: t is not a number", "journal row: t is not a number", "journal row: gid missing"):
                jd.load_goals_shared_or_fault = (lambda sid, tx=text: (_ for _ in ()).throw(ValueError(tx)))
                with redirect_stderr(err):
                    km._dead_wait_sweep(set(), self.nudged, STAMP_T + 900)
        finally:
            jd.load_goals_shared_or_fault = real_shared
        self.assertEqual(err.getvalue().count("the goal-store view raised"), 2, "said for the first text and again for the new text, not for the repeat: %r" % err.getvalue())

    def test_the_heal_takes_one_mutable_load_and_counts(self):
        """The brief repair is a write: it takes a private load only when a briefless procedural block stands, and counts it."""
        _seed_store()
        st = jd.load_goals(SID)
        nd = st["nodes"][GID]
        jd.record_verdict(st, nd, "nudge", "block", STAMP_T + 100, why=jd.dead_wait_block_why("the full test suite it kicked off"))
        jd.rollup_status(st, False)
        jd.save_goals(SID, st)
        self.assertIsNone(jd.load_goals(SID)["nodes"][GID].get("blockSummary"))
        _write_state("idle", STAMP_T + 50)
        km._PREV_ALIVE = None
        loads = []
        real_load = jd.load_goals
        jd.load_goals = lambda sid: (loads.append(sid), real_load(sid))[1]
        before = dict(km._DEAD_WAIT_STATS)
        try:
            km._dead_wait_sweep(set(), self.nudged, STAMP_T + 900)
        finally:
            jd.load_goals = real_load
        d = {k: km._DEAD_WAIT_STATS[k] - before.get(k, 0) for k in km._DEAD_WAIT_STATS}
        self.assertEqual((d["healed"], d["mutableLoads"]), (1, 1), "the heal's one private load: %r" % d)
        self.assertEqual(loads.count(SID), 1, "one private load for the heal (the status scan read the shared view): %r" % loads)
        self.assertTrue((jd.load_goals(SID)["nodes"][GID].get("blockSummary") or "").startswith(jd.DEAD_WAIT_WHY_PREFIX))

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


class DeadWaitCorroboration(_HermeticDeadWait):
    """The sweep's trigger — absence from a RAW liveness listing — inherits every collapse that
    listing has (a backend's read that failed and is stood down on; a swallowed SDK live-merge
    exception does the same to the merged half), and the block it files is irreversible bookkeeping
    on the user's board with nothing to lift it when the listing returns. So absence alone NEVER
    files: the death is corroborated with the liveness OWNER first (the SDK reg's alive bit / a
    standing death record / the Codex registry's dead mark / a names entry no record answers for),
    and an unconfirmable candidate stands down for the cycle with its transition kept armed — the
    doctrine _death_sweep_tick and _death_boot_pass follow."""

    def _blocked(self):
        return bool(jd.load_goals(SID)["nodes"][GID].get("blocked"))

    def test_a_raw_listing_collapse_alone_never_files(self):
        _seed_store(ended=False)
        _write_state("idle", STAMP_T + 50)
        self.codex.rows[SID] = True               # the OWNER answers alive — the raw listing blinked
        km._PREV_ALIVE = {SID}
        km._dead_wait_sweep(set(), self.nudged, STAMP_T + 900)   # empty alive set: the collapse shape
        self.assertFalse(self._blocked(), "an owner-corroborated ALIVE session must never convert")
        self.assertIn(SID, km._PREV_ALIVE, "the death transition stays armed for a genuine later death")

    def test_a_blind_codex_registry_stands_down_and_the_next_tick_retries(self):
        _seed_store(ended=False)
        _write_state("idle", STAMP_T + 50)
        self.codex._registry_unreadable = True    # the Codex records cannot be read — a Codex sid and dead history look alike
        km._PREV_ALIVE = {SID}
        km._dead_wait_sweep(set(), self.nudged, STAMP_T + 900)
        self.assertFalse(self._blocked(), "unconfirmed is never dead — nothing files")
        self.assertIn(SID, km._PREV_ALIVE, "the candidate is kept, not spent")
        self.codex._registry_unreadable = False   # the registry reads again and marks the sid dead: the owner's answer…
        self.codex.rows[SID] = False
        km._dead_wait_sweep(set(), self.nudged, STAMP_T + 950)
        self.assertTrue(self._blocked(), "…and the retried tick converts")

    def test_the_codex_registrys_dead_mark_is_the_answer_for_a_codex_sid(self):
        _seed_store(ended=False)
        _write_state("idle", STAMP_T + 50)
        self.codex.rows[SID] = True               # a row the backend still owns
        self.assertIs(km._dead_wait_corroborated(SID), False, "owned: alive, never converts")
        self.codex.rows[SID] = False              # the registry's dead mark
        self.assertIs(km._dead_wait_corroborated(SID), True, "the owner's durable dead mark corroborates")

    def test_sdk_reg_alive_bit_outranks_the_merged_maps_absence(self):
        _seed_store()
        _write_state("idle", STAMP_T + 50)
        jd.SDKDIR.mkdir(parents=True, exist_ok=True)
        (jd.SDKDIR / (SID + ".json")).write_text(json.dumps({"alive": True}))
        km._PREV_ALIVE = {SID}
        km._dead_wait_sweep(set(), self.nudged, STAMP_T + 900)   # the swallowed SDK-merge shape
        self.assertFalse(self._blocked(),
                         "alive:True is live/revivable/crash-looped — the resume contract owns it")
        (jd.SDKDIR / (SID + ".json")).write_text(json.dumps({"alive": False}))
        km._dead_wait_sweep(set(), self.nudged, STAMP_T + 950)
        self.assertTrue(self._blocked(), "alive:False is the owner's durable answer — it converts")

    def test_a_standing_death_record_corroborates_without_a_probe(self):
        _seed_store()
        _write_state("idle", STAMP_T + 50)
        gone = jd.STATE / "gone"
        gone.mkdir(parents=True, exist_ok=True)
        (gone / (SID + ".json")).write_text(json.dumps({"t": STAMP_T + 60, "by": "gone"}))
        self.codex._registry_unreadable = True    # even with the Codex records unreadable…
        km._PREV_ALIVE = {SID}
        km._dead_wait_sweep(set(), self.nudged, STAMP_T + 900)
        self.assertTrue(self._blocked(), "…a death a corroborated writer already stamped answers")

    def test_wake_goal_dormant_branch_stands_down_for_transcript_derived_sessions(self):
        # a transcript-derived session (no reg, no names entry: launched by neither backend) reaches
        # _wake_goal absent from the merged map — no owner here can answer for it, so nothing may file
        _seed_store(named=False)                  # transcript-derived: no launch record
        _write_state("idle", STAMP_T + 50)
        store = jd.load_goals(SID)
        fired = km._wake_goal(SID, GID, (STAMP_T, "w"), self.nudged, [], store,
                              STAMP_T + 900, {}, {})
        self.assertFalse(fired)
        self.assertFalse(self._blocked(), "a reg-less file-derived session has no owner to ask")
        # …but a genuinely ENDED SDK session still converts on the same box: the reg answers
        jd.SDKDIR.mkdir(parents=True, exist_ok=True)
        (jd.SDKDIR / (SID + ".json")).write_text(json.dumps({"alive": False}))
        fired = km._wake_goal(SID, GID, (STAMP_T, "w"), self.nudged, [], store,
                              STAMP_T + 950, {}, {})
        self.assertTrue(fired)
        self.assertTrue(self._blocked())

    def test_clean_backend_records_cannot_settle_a_sid_no_backend_launched(self):
        # AUTHORITY FOLLOWS OWNERSHIP: a transcript-derived session (no reg, no names entry —
        # launched by neither backend) drops out of the alive set, arming its death transition.
        # Every backend's records read clean and know nothing of it — and that silence is not an
        # answer: a readable, EMPTY Codex registry never ran this sid, so letting it answer as the
        # liveness owner would be a false conversion of a live session's card. The records settle
        # only sids a backend could have run; this one stands down.
        _seed_store(named=False)                  # transcript-derived: no launch record
        _write_state("idle", STAMP_T + 50)
        self.assertIsNone(km._dead_wait_corroborated(SID),
                          "the records settle only sids a backend could have run")
        km._PREV_ALIVE = {SID}
        km._dead_wait_sweep(set(), self.nudged, STAMP_T + 900)
        self.assertFalse(self._blocked(), "a sid no backend ran must not convert on a clean registry's word")
        self.assertIn(SID, km._PREV_ALIVE, "stood down and kept armed, never spent")
        # …while the SAME sid WITH a launch record is the owner's to settle: it converts
        _register_name(SID)
        km._dead_wait_sweep(set(), self.nudged, STAMP_T + 950)
        self.assertTrue(self._blocked())


class DeadWaitStandDownLogging(_HermeticDeadWait):
    """Wedge-time log ergonomics: a stand-down is LOUD (the fail-loudly rule — a silent one wedges
    a candidate forever with no trace to act on) but collapsed to ONE line per sweep pass
    (_death_sweep_tick's idiom) — the per-candidate line multiplies by the candidate count under
    exactly the wedge it reports (a 20-session listing collapse would log every candidate every
    tick at the pusher cadence)."""

    def _blocked(self):
        return bool(jd.load_goals(SID)["nodes"][GID].get("blocked"))

    def test_a_blind_codex_registry_logs_one_line_per_pass_not_per_candidate(self):
        sid2 = _fresh_sid()
        _register_name(SID, ended=False)
        _register_name(sid2, ended=False)
        self.codex._registry_unreadable = True    # the Codex records cannot be read, shared by the whole pass
        km._PREV_ALIVE = {SID, sid2}
        buf = io.StringIO()
        with redirect_stderr(buf):
            km._dead_wait_sweep(set(), {}, STAMP_T + 900)
        lines = [ln for ln in buf.getvalue().splitlines() if "dead-wait" in ln and "Codex" in ln]
        self.assertEqual(len(lines), 1, "one line per pass, not per candidate: %r" % lines)
        self.assertIn("2 candidate(s) stood down this pass", lines[0])
        self.assertEqual({SID, sid2} & km._PREV_ALIVE, {SID, sid2}, "both kept armed")

    def test_a_single_probe_codex_blind_stand_down_names_the_sid(self):
        _register_name(SID, ended=False)
        self.codex._registry_unreadable = True
        buf = io.StringIO()
        with redirect_stderr(buf):
            self.assertIsNone(km._dead_wait_corroborated(SID))
        out = buf.getvalue()
        self.assertIn(SID, out, "the single-probe stand-down names the sid (fail-loudly rule)")
        self.assertIn("Codex registry", out)

    def test_unreadable_reg_stand_down_is_loud_and_per_pass_deduped(self):
        sid2 = _fresh_sid()
        jd.SDKDIR.mkdir(parents=True, exist_ok=True)
        (jd.SDKDIR / (SID + ".json")).write_text("{not json")     # an unreadable owner reg
        (jd.SDKDIR / (sid2 + ".json")).write_text("{not json")
        km._PREV_ALIVE = {SID, sid2}
        buf = io.StringIO()
        with redirect_stderr(buf):
            km._dead_wait_sweep(set(), {}, STAMP_T + 900)
        lines = [ln for ln in buf.getvalue().splitlines()
                 if "dead-wait" in ln and "unreadable" in ln]
        self.assertEqual(len(lines), 1,
                         "silent forever is a wedge with no trace; per-candidate is a flood: %r" % lines)
        self.assertIn("2 candidate(s) stood down this pass", lines[0])
        self.assertEqual({SID, sid2} & km._PREV_ALIVE, {SID, sid2}, "both kept armed")

    def test_single_probe_callers_still_name_the_sid(self):
        # _wake_goal's dormant branch corroborates ONE sid per call — there its line IS the pass,
        # and naming the sid is what makes the trace actionable
        jd.SDKDIR.mkdir(parents=True, exist_ok=True)
        (jd.SDKDIR / (SID + ".json")).write_text("{not json")
        buf = io.StringIO()
        with redirect_stderr(buf):
            self.assertIsNone(km._dead_wait_corroborated(SID))
        out = buf.getvalue()
        self.assertIn(SID, out, "the unreadable-reg stand-down must be loud (fail-loudly rule)")
        self.assertIn("unreadable", out)


class DeadWaitOneObserver(_HermeticDeadWait):
    """The death transition has ONE observer. _dead_wait_sweep's prev-swap (_PREV_ALIVE) is a
    lock-free read-modify-write, safe only because exactly one caller — the pusher's periodic
    tick — ever runs it. setAutoNudge's WS handler also fires _auto_nudge_tick (to re-arm nudging
    immediately on turn-on); racing the pusher, its swap could spend a death transition
    mid-pass without corroboration, losing the re-arm until the boot catch-up. So the
    WS-triggered tick SKIPS the sweep (run_dead_wait=False): its purpose is nudge re-arming,
    and the pusher re-runs the sweep on its own cadence anyway."""

    def _blocked(self):
        return bool(jd.load_goals(SID)["nodes"][GID].get("blocked"))

    @contextlib.contextmanager
    def _tick_stubs(self):
        """Stub the tick's OTHER legs (session walk, peer-wait graph, debt sweep, wake outcomes)
        so a tick-level call exercises only the sweep — the leg under test — hermetically."""
        saved = {nm: getattr(km, nm) for nm in
                 ("_alive_sessions", "_wait_for_graph", "_debt_backstop_tick",
                  "_awaiting_wake_outcomes")}
        km._alive_sessions = lambda now, live_map: []
        km._wait_for_graph = lambda now, alive_sids: {}
        km._debt_backstop_tick = lambda now: None
        km._awaiting_wake_outcomes = lambda now: False
        try:
            yield
        finally:
            for nm, fn in saved.items():
                setattr(km, nm, fn)

    def test_ws_shaped_tick_skips_the_sweep_and_the_pusher_shape_runs_it(self):
        _seed_store()
        _write_state("idle", STAMP_T + 50)
        km._PREV_ALIVE = {SID}                    # a pending death transition
        with self._tick_stubs():
            km._auto_nudge_tick(STAMP_T + 900, {}, run_dead_wait=False)   # setAutoNudge's tick
            self.assertEqual(km._PREV_ALIVE, {SID},
                             "the WS-triggered tick must not observe (or spend) the transition")
            self.assertFalse(self._blocked())
            km._auto_nudge_tick(STAMP_T + 950, {})                        # the pusher's tick
        self.assertTrue(self._blocked(), "the one observer still converts, on its own cadence")

    def test_a_mid_pass_ws_tick_leaves_the_transition_alone(self):
        # the racing interleave, deterministically: the pusher is MID-PASS (inside a candidate's
        # corroboration) when the WS handler's tick fires. The transition set must be exactly
        # what the pusher's pass installed — untouched by the nested tick. What holds it today is
        # the single-flight guard: the pusher's pass holds _AUTO_NUDGE_TICK_LOCK (a plain Lock), so
        # the nested tick returns at its try-acquire before run_dead_wait is even read. The
        # run_dead_wait=False sweep skip is pinned by the sequential sibling above, not by this test.
        _seed_store()
        _write_state("idle", STAMP_T + 50)
        km._PREV_ALIVE = {SID}
        real = km._dead_wait_corroborated
        seen = {}

        def hooked(sid, stats=None, now=None):
            if "ran" not in seen:
                seen["ran"] = True
                before = set(km._PREV_ALIVE)
                km._auto_nudge_tick(STAMP_T + 901, {}, run_dead_wait=False)   # WS fires mid-pass: returns at the lock
                seen["moved"] = set(km._PREV_ALIVE) != before
            return real(sid, stats=stats, now=now)

        km._dead_wait_corroborated = hooked
        try:
            with self._tick_stubs():
                km._auto_nudge_tick(STAMP_T + 900, {})                        # the pusher's tick
        finally:
            km._dead_wait_corroborated = real
        self.assertTrue(seen.get("ran"), "the pusher's pass reached its corroboration")
        self.assertFalse(seen.get("moved"), "the nested WS tick swapped the transition mid-pass")
        self.assertTrue(self._blocked(), "the pusher's own pass still completed its conversion")

    def test_the_setautonudge_call_site_skips_the_sweep(self):
        # the ownership rule holds at every WS call site (setAutoNudge and setCompactSuggest),
        # pinned the way test_wake_goal_routes_its_dormant_branch_here pins its wiring. Each arm is
        # sliced out and checked on its own: a whole-source substring match stayed green while the
        # setAutoNudge arm's tick was missing, satisfied by setCompactSuggest's line (#846 inserted
        # the new arm between the setter and its tick, re-parenting the tick). Both arms tick
        # through the one wrap, _ws_act_now_tick (the #943 review), which holds the one WS-shaped
        # call — so the sweep skip is pinned there, and no arm may call the tick around the wrap.
        src = inspect.getsource(km.Handler._dispatch_ws)
        arm_a = src[src.index('"setAutoNudge"'):src.index('"setCompactSuggest"')]
        arm_c = src[src.index('"setCompactSuggest"'):src.index('"setUpdateMode"')]
        self.assertIn("_ws_act_now_tick()", arm_a, "setAutoNudge's own arm re-ticks, through the wrap")
        self.assertIn("_ws_act_now_tick()", arm_c, "setCompactSuggest's arm re-ticks, through the wrap")
        self.assertNotIn("_auto_nudge_tick(", src, "no WS call site ticks around the wrap")
        wrap = inspect.getsource(km._ws_act_now_tick)
        self.assertIn("_auto_nudge_tick(int(time.time()), _live_map(), run_dead_wait=False)", wrap,
                      "the WS-shaped tick skips the one-observer sweep")
        self.assertIn("except Exception", wrap, "…and a failure in it is logged, not a socket failure")


if __name__ == "__main__":
    unittest.main()
