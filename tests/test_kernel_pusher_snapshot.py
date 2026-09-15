#!/usr/bin/env python3
"""The pusher cycle takes ONE liveness snapshot (the 2026-08-10 CPU fix).

Every _live_map() read asks both backends for their rows and sweeps the whole SDK reg registry.
The pusher's cycle used to take NINE of them — one inside _push plus one per tick job — at its
0.5s cadence, which profiling attributed as the kernel's single hottest thread (~50-90% of one
core sustained, three quarters of total process CPU). The jobs all take the map as a parameter
by design, so the fix is purely structural: one snapshot at cycle start, handed to everything.

SYNTHETIC fixtures only: placeholder UUIDs, invented names.
"""
import collections
import json
import os
import tempfile
import time
import unittest
from romp_load import load_source
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
load_source("romp_event_model", os.path.join(BIN, "romp-event-model"))
load_source("romp_judge", os.path.join(BIN, "romp-judge"))
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = load_source("romp_kernel_pushsnap", os.path.join(BIN, "romp-kernel"))
jd = km.jd

NOW = 1781100000
SID = "11111111-2222-3333-4444-555555555555"
SID2 = "11111111-2222-3333-4444-565656565656"   # a second session: the per-sid misses the discover memo removes


class _CycleFixture(unittest.TestCase):
    """The shared world for the cycle tests: a hermetic state root, two sessions on disk (transcripts,
    names, live rows), the kernel globals the tests replace saved and restored, and every scope slot
    cleared after each test. No tests of its own: the concrete classes below derive from it, so each
    test is collected once."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        td = Path(self.td.name)
        self.saved = (jd.NAMES, jd.PROJECTS, jd.CAPDIR, jd.ARCHDIR, jd.GOALDIR, jd.STATE,
                      km.NAMES, km.Sessions.live, km._sdk,
                      km._auto_nudge_tick, km._clear_done_working_notes,
                      km._turn_notify_tick, km._api_health_frame, km._api_health_push, km._lift_spent_awaiting)
        names = td / "names"; names.mkdir()
        proj = td / "projects"; proj.mkdir()
        jd.NAMES, jd.PROJECTS = names, proj
        jd.CAPDIR, jd.ARCHDIR, jd.GOALDIR = td / "captions", td / "archive", td / "goals"
        for d in (jd.CAPDIR, jd.ARCHDIR, jd.GOALDIR):
            d.mkdir()
        jd.STATE = td
        km.NAMES = names
        km._sdk = lambda: None
        # a real session on disk, so the push leg builds it and the DEEP helpers (the awaiting/bg-task
        # sources, the feed's per-session gates) actually run — the reads this fix removes hide there
        cdir = td / "work"; cdir.mkdir()
        pdir = proj / jd.re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(str(cdir)))
        pdir.mkdir(parents=True)
        rec = {"type": "user", "timestamp": "2026-06-11T00:00:00.000Z", "uuid": "u1",
               "parentUuid": None, "promptSource": "typed",
               "message": {"role": "user", "content": "hello there"}}
        self.paths = {}
        for sid, name in ((SID, "web"), (SID2, "api")):
            self.paths[sid] = str(pdir / (sid + ".jsonl"))
            (pdir / (sid + ".jsonl")).write_text(json.dumps(rec) + "\n")
            (names / sid).write_text("%s\t%s\t#abcdef\n" % (name, str(cdir)))
        meta = {"state": "waiting", "since": NOW - 5, "model": "", "effort": "", "context": None,
                "compactPct": None, "color": None, "mode": "", "backend": "sdk"}
        self.row = {SID: dict(meta), SID2: dict(meta)}
        self.saved_clients = list(km._clients)
        self._files_stat_reset()

    def _files_stat_reset(self):
        """The ten-file key's standing snapshot, dirty set and observers back to a boot's: no test inherits another's marks."""
        getattr(km, "_FILES_STAT_STANDING", {}).clear()
        getattr(km, "_FILES_STAT_DIRTY", {}).update({"sids": set(), "all": True})
        getattr(km, "_FILES_STAT_OBSERVED", {}).update({"postal": None, "rows": {}, "jdAll": None, "jdBy": {}})
        km._live_scope.files_dirty = None

    def tearDown(self):
        (jd.NAMES, jd.PROJECTS, jd.CAPDIR, jd.ARCHDIR, jd.GOALDIR, jd.STATE,
         km.NAMES, km.Sessions.live, km._sdk,
         km._auto_nudge_tick, km._clear_done_working_notes,
         km._turn_notify_tick, km._api_health_frame, km._api_health_push, km._lift_spent_awaiting) = self.saved
        with km._clients_lock:
            km._clients[:] = self.saved_clients
        # every scope slot, so a failing test cannot leak a cycle's memo into the next on this thread
        km._live_scope.snapshot = None
        km._live_scope.sessions = None
        km._live_scope.paths = None
        km._live_scope.names = None
        km._live_scope.files_stat = None
        self._files_stat_reset()
        km._compact_clicked.clear()
        self.td.cleanup()


class OneSnapshotPerCycle(_CycleFixture):
    """One liveness snapshot per cycle, handed to every job (the module docstring's fix)."""

    def test_one_cycle_reads_liveness_once_however_deep_the_call(self):
        # count REAL liveness reads (Sessions.live — the backends' rows + reg sweep), not the delegator:
        # inside the cycle's scope every _live_map() call, at any depth of the build stack,
        # must be served the cycle's one snapshot instead of taking a fresh read
        reads = []
        row = self.row
        km.Sessions.live = lambda: (reads.append(1), dict(row))[1]
        got = {}
        # bracket the pusher's job list: the FIRST and the LAST job after the push that take the map must both receive the
        # cycle's one map (the housekeeping jobs run on the jobs thread since 2026-09-13: see the twin below)
        km._turn_notify_tick = lambda now, live_map: got.setdefault("first", live_map)
        km._api_health_frame = lambda now, live_map: got.setdefault("last", live_map)
        km._api_health_push = lambda frame: None
        sent = []
        with km._clients_lock:   # a connected chat client, so the _push leg builds for real
            km._clients[:] = [{"app": "chat", "alive": True, "wid": "", "qbytes": 0,
                               "send": sent.append}]
        km._pusher_cycle()
        self.assertEqual(len(reads), 1, "one fork + one reg sweep per cycle — that IS the fix")
        self.assertIn(SID, got.get("first") or {}, "the jobs got the cycle's snapshot")
        self.assertIs(got.get("first"), got.get("last"))
        self.assertTrue(any('"type": "session"' in s or '"type":"session"' in s.replace(" ", "")
                            for s in sent), "the push leg really built the session")
        self.assertIsNone(km._live_scope.snapshot, "the scope ends with the cycle")
        # OUTSIDE a cycle the delegator reads fresh — a WS handler must never see a stale snapshot
        n = len(reads)
        km._live_map()
        self.assertEqual(len(reads), n + 1)

    def test_one_jobs_pass_reads_liveness_once_and_hands_it_to_every_job(self):
        """The jobs thread's twin (the housekeeping split, 2026-09-13): its pass takes ONE snapshot of its own, the first and
        the last housekeeping job receive that one map, and the scope ends with the pass."""
        reads = []
        row = self.row
        km.Sessions.live = lambda: (reads.append(1), dict(row))[1]
        got = {}
        km._lift_spent_awaiting = lambda now, live_map: got.setdefault("first", live_map)
        km._clear_done_working_notes = lambda now, live_map: got.setdefault("last", live_map)
        km._jobs_cycle()
        self.assertEqual(len(reads), 1, "one liveness read per jobs pass")
        self.assertIn(SID, got.get("first") or {}, "the jobs got the pass's snapshot")
        self.assertIs(got.get("first"), got.get("last"))
        self.assertIsNone(km._live_scope.snapshot, "the scope ends with the pass")
        self.assertIsNone(km._live_scope.sessions)

    def test_build_session_reuses_the_callers_snapshot(self):
        # build_session used to take a FRESH liveness read per session build (the bgTasks line) — on
        # the pusher's hottest path that was a liveness read + reg sweep per tab per push
        reads = []
        row = self.row
        km.Sessions.live = lambda: (reads.append(1), dict(row))[1]
        m = km.build_session(SID, NOW, dict(self.row))
        self.assertIsNotNone(m)
        self.assertEqual(reads, [], "a provided snapshot is enough — no fresh liveness reads")


class OneDiscoverPerCycle(_CycleFixture):
    """The cycle's discover rows are memoized on the scope, so the tick jobs' _alive_sessions calls, the
    _path_of misses under _compacting_now and the builders share ONE _sessions sweep per (window, forks)
    key — one fingerprint through _sessions — with or without a client. Fingerprints are attributed
    through _sessions, not counted globally: direct jd.discover callers exist (the wide walk, postal
    enrichment, analytics) and a global count is fixture-fragile."""

    def _cycle(self, client, cycle=None):
        cycle = cycle or km._pusher_cycle                 # or km._jobs_cycle: the housekeeping's pass (the split, 2026-09-13)
        depth, inside, outside, keys = [0], [], [], set()
        orig_sessions, orig_fp = km._sessions, jd._discover_fingerprint

        def sessions(now, window=None, forks=True):
            keys.add((jd.WINDOW if window is None else int(window), bool(forks)))
            depth[0] += 1
            try:
                return orig_sessions(now, window, forks)
            finally:
                depth[0] -= 1

        def fp(*a, **k):
            (inside if depth[0] else outside).append(1)
            return orig_fp(*a, **k)
        km._sessions, jd._discover_fingerprint = sessions, fp
        km.Sessions.live = lambda: dict(self.row)
        with km._clients_lock:
            km._clients[:] = [client] if client else []
        s0 = dict(km._sessions_scope_stats)
        try:
            cycle()
        finally:
            km._sessions, jd._discover_fingerprint = orig_sessions, orig_fp
        s1 = km._sessions_scope_stats
        return len(inside), keys, {k: s1[k] - s0[k] for k in s1}

    def test_one_sweep_per_key_per_cycle_without_a_client(self):
        fps, keys, d = self._cycle(None)
        self.assertEqual(d["miss"], len(keys), "one _sessions sweep per (window, forks) key")
        self.assertIn((jd.WINDOW, True), keys)
        self.assertEqual(fps, d["miss"], "…and one discover fingerprint per sweep")
        self.assertGreaterEqual(d["hit"], 1, "the pusher's own jobs and the _path_of misses were served from the memo")
        self.assertIsNone(km._live_scope.sessions, "the memo ends with the cycle")

    def test_one_sweep_per_key_per_jobs_pass(self):
        # the housekeeping jobs' twin (the split, 2026-09-13): the pass opens its own memo, one sweep per key, the jobs served
        fps, keys, d = self._cycle(None, cycle=km._jobs_cycle)
        self.assertEqual(d["miss"], len(keys), "one _sessions sweep per (window, forks) key")
        self.assertIn((jd.WINDOW, True), keys)
        self.assertEqual(fps, d["miss"])
        self.assertGreaterEqual(d["hit"], 5, "the tick jobs and the _path_of misses were served from the memo")
        self.assertIsNone(km._live_scope.sessions, "the memo ends with the pass")

    def test_one_sweep_per_key_per_cycle_with_a_chat_client(self):
        sent = []
        fps, keys, d = self._cycle({"app": "chat", "alive": True, "wid": "", "qbytes": 0, "send": sent.append})
        self.assertTrue(any('"type": "session"' in m for m in sent), "the push leg really built the sessions")
        self.assertEqual(d["miss"], len(keys))
        self.assertEqual(fps, d["miss"])
        self.assertGreaterEqual(d["hit"], 5)
        self.assertIsNone(km._live_scope.sessions)

    def test_outside_a_cycle_every_read_is_fresh(self):
        # the _live_map half of the idiom: a WS handler must never see a stale cycle's rows
        km._live_scope.sessions = None
        fps = []
        orig = jd._discover_fingerprint
        jd._discover_fingerprint = lambda *a, **k: fps.append(1) or orig(*a, **k)
        s0 = dict(km._sessions_scope_stats)
        try:
            km._sessions(int(time.time()))
            km._sessions(int(time.time()))
        finally:
            jd._discover_fingerprint = orig
        self.assertEqual(len(fps), 2, "no scope, no memo: two reads are two sweeps")
        self.assertEqual(dict(km._sessions_scope_stats), s0,
                         "…and no counter moved: the stats are bumped only under an open scope, which is why they need no lock")

    def test_a_hit_hands_out_a_copy_too(self):
        # the docstring says hit OR miss: a consumer that appends to the FIRST hit's list must not grow the memo either
        km._live_scope.sessions = {}
        try:
            now = int(time.time())
            km._sessions(now)                                   # the miss
            b = km._sessions(now)                               # the first hit
            b.append({"sid": "11111111-2222-3333-4444-999999999999"})
            c = km._sessions(now)
            self.assertIsNot(c, b)
            self.assertEqual(sorted(r["sid"] for r in c), sorted([SID, SID2]), "the mutation stayed with the hit's caller")
        finally:
            km._live_scope.sessions = None

    def test_an_empty_window_is_still_one_sweep_per_cycle(self):
        # an empty row list is a valid memo value: a kernel with no session in the window (and none live) must not
        # re-sweep on every read of the cycle
        old = time.time() - 3 * 86400
        for path in self.paths.values():
            os.utime(path, (old, old))
        self.row = {}
        fps, keys, d = self._cycle(None, cycle=km._jobs_cycle)   # the tick jobs' pass (the housekeeping split, 2026-09-13)
        self.assertEqual(d["miss"], len(keys), "one sweep per key, the empty result memoized")
        self.assertEqual(fps, d["miss"])
        self.assertGreaterEqual(d["hit"], 5, "the tick jobs were served the empty list from the memo")

    def test_the_key_is_normalized_like_discover(self):
        # the memo key is normalized the way discover normalizes its own: None, the default window and a float
        # spelling of it, with forks given as a truthy int, are one key (the docstring's promise; no in-cycle caller
        # passes an explicit window today)
        km._live_scope.sessions = {}
        try:
            s0 = dict(km._sessions_scope_stats)
            now = int(time.time())
            km._sessions(now)
            km._sessions(now, window=jd.WINDOW)
            km._sessions(now, window=float(jd.WINDOW), forks=1)
            d = {k: km._sessions_scope_stats[k] - s0[k] for k in s0}
            self.assertEqual((d["miss"], d["hit"]), (1, 2))
            self.assertEqual(list(km._live_scope.sessions), [(jd.WINDOW, True)])
        finally:
            km._live_scope.sessions = None

    def test_build_session_does_not_write_into_the_cycles_row(self):
        # the row dicts are shared read-only across the cycle; build_session's one write (path_override) goes to a copy,
        # or the override would leak into every later consumer of the cycle's rows
        km._live_scope.sessions = {}
        km.Sessions.live = lambda: dict(self.row)
        try:
            now = int(time.time())
            m = km.build_session(SID, now, live_map=self.row, path_override=self.paths[SID2])
            self.assertIsNotNone(m)
            row = next(r for r in km._sessions(now) if r["sid"] == SID)
            self.assertEqual(row["path"], self.paths[SID], "the override stayed with that build")
        finally:
            km._live_scope.sessions = None

    def test_a_read_hands_out_a_copy_of_the_cycles_rows(self):
        # the headless _alive_sessions fallback returns _sessions' list as its own; a consumer that
        # appends to it must not grow the cycle's shared list for every later reader
        km._live_scope.sessions = {}
        try:
            a = km._sessions(int(time.time()))
            self.assertEqual(sorted(r["sid"] for r in a), sorted([SID, SID2]))
            a.append({"sid": "11111111-2222-3333-4444-999999999999"})
            b = km._sessions(int(time.time()))
            self.assertIsNot(b, a)
            self.assertEqual(sorted(r["sid"] for r in b), sorted([SID, SID2]), "the mutation stayed with the caller")
            self.assertIs(b[0], km._sessions(int(time.time()))[0], "the row dicts themselves are shared")
        finally:
            km._live_scope.sessions = None

    def test_a_live_session_older_than_the_window_walks_wide_once(self):
        # a live sid idle longer than 48h is resolved by _alive_sessions' wide walk, which every
        # _alive_sessions call in the cycle repeated before the memo (a fingerprint each)
        old = time.time() - 3 * 86400
        os.utime(self.paths[SID2], (old, old))
        wide_calls = []
        orig = jd.discover

        def discover(now, window=None, forks=True):
            if window == jd.DEATH_BACKFILL_WINDOW:
                wide_calls.append(1)
            return orig(now, window, forks)
        jd.discover = discover
        got = {}
        km._clear_done_working_notes = lambda now, live_map: got.setdefault("alive", km._alive_sessions(now, live_map))
        try:
            fps, keys, d = self._cycle(None, cycle=km._jobs_cycle)   # the _alive_sessions callers are the housekeeping jobs
        finally:
            jd.discover = orig
        self.assertEqual(sorted(r["sid"] for r in got["alive"]), sorted([SID, SID2]),
                         "the old live session is still on every surface")
        self.assertEqual(len(wide_calls), 1, "one wide walk per cycle")
        self.assertEqual(d["wide_miss"], 1)
        self.assertGreaterEqual(d["wide_hit"], 5, "…served to every other _alive_sessions call")
        self.assertEqual(fps, d["miss"], "the 48h sweep still ran once")


class TickReadsTheRowsPath(_CycleFixture):
    """_interrupt_block_tick hands _compacting_now the row's own path and live meta. When the hoist landed it
    was also a behaviour change for a LIVE session idle longer than 48h: _path_of searched only the 48h set
    and answered None, so the gate read an empty parse, and an optimistic compact click could not be
    disproved by the session's own compact_boundary for the 180 s cap — the tick skipped the row that long.
    With the row's path the gate reads the cached parse, and the boundary (the event) retires the click.
    Since _session_row (the single-session resolver behind the fork/comment/rewind doors, 2026-09-14) the
    default _path_of read resolves that idle session through discover's wide walk too, so the two reads
    agree and the hoist is what it was always for: the saved per-row discover sweep."""

    def _boundary_transcript(self, offset=0):
        """SID2's transcript with a compact_boundary at now + offset (its mtime set idle longer than the caption
        window), parsed into the cache as the background warm leaves it. Returns (path, now)."""
        t = int(time.time())
        recs = [{"type": "user", "timestamp": "2026-06-11T00:00:00.000Z", "uuid": "u1", "parentUuid": None,
                 "promptSource": "typed", "message": {"role": "user", "content": "hello there"}},
                {"type": "assistant", "timestamp": "2026-06-11T00:00:05.000Z", "uuid": "a1", "parentUuid": "u1",
                 "message": {"role": "assistant", "content": [{"type": "text", "text": "hi"}],
                             "stop_reason": "end_turn"}},
                {"type": "system", "subtype": "compact_boundary", "uuid": "cb1", "parentUuid": None,
                 "logicalParentUuid": "a1", "isMeta": False,
                 "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t + offset)),
                 "compactMetadata": {"trigger": "manual", "preTokens": 1000, "postTokens": 100}}]
        path = self.paths[SID2]
        Path(path).write_text("\n".join(json.dumps(r) for r in recs) + "\n")
        old = time.time() - 3 * 86400
        os.utime(path, (old, old))                       # idle longer than the caption window
        km._parse_cache.clear()
        km._parse(path, SID2, int(time.time()))          # the cached parse holds the boundary, as the background warm leaves it
        return path, t

    def test_the_rows_path_lets_the_boundary_disprove_an_optimistic_click(self):
        path, t = self._boundary_transcript()
        km.Sessions.live = lambda: dict(self.row)
        km._compact_clicked[SID2] = t - 10               # the kernel sent /compact just before the boundary
        self.assertFalse(km._compacting_now(SID2), "the default read resolves the idle session's own transcript "
                                                  "(_path_of via _session_row's wide walk), so the boundary retires "
                                                  "the click here too; before _session_row the 48h search found no "
                                                  "transcript and the click stood unproven for the whole cap")
        km._compact_clicked[SID2] = t - 10
        self.assertFalse(km._compacting_now(SID2, tm=self.row[SID2], path=path),
                         "with the row's path the cached parse's boundary retires the click")
        self.assertNotIn(SID2, km._compact_clicked, "…on the event, not a timer")

    def test_the_tick_reads_the_rows_own_live_meta(self):
        # The tick hands _compacting_now the row's live meta beside its path, so the gate reads the CYCLE's `since`
        # (when the row's state began) rather than refetching liveness per row. Visible when the two diverge: a
        # boundary that landed after the row's state began but BEFORE the click does not retire the click by itself,
        # and it is the row's `since` that reads the compaction as over (a boundary since the state's start); a
        # refetched meta whose `since` postdates the boundary would keep the session reading as compacting, and the
        # tick would skip the row.
        path, t = self._boundary_transcript(offset=-20)        # the boundary 20 s ago
        fetched = {sid: dict(m) for sid, m in self.row.items()}
        fetched[SID2]["since"] = t + 3600                       # a fresh liveness read: a state that began after the boundary
        km.Sessions.live = lambda: dict(fetched)
        self.row[SID2]["since"] = NOW - 5                       # the cycle's row: its state began before the boundary
        km._compact_clicked[SID2] = t - 10                      # clicked after the boundary: the boundary alone leaves it standing
        seen = []
        saved = km._api_error
        km._api_error = lambda p: seen.append(p) or {"text": "overloaded"}   # truthy: the tick stops at this gate
        try:
            km._interrupt_block_tick(int(time.time()), self.row)
        finally:
            km._api_error = saved
        self.assertIn(path, seen, "with the row's own meta the gate read the compaction as over: the tick reached the next gate")
        self.assertIn(SID2, km._compact_clicked, "the click itself stands: no boundary followed it")

    def test_the_tick_no_longer_skips_the_old_live_session(self):
        path, t = self._boundary_transcript()
        km.Sessions.live = lambda: dict(self.row)
        km._compact_clicked[SID2] = t - 10
        seen = []
        saved = km._api_error
        km._api_error = lambda p: seen.append(p) or {"text": "overloaded"}   # truthy: the tick stops at this gate
        try:
            km._interrupt_block_tick(int(time.time()), self.row)
        finally:
            km._api_error = saved
        self.assertIn(path, seen, "the tick reached the row's next gate: the compacting gate read the real parse")
        self.assertNotIn(SID2, km._compact_clicked)


class LazyChatSerialization(unittest.TestCase):
    """The chat payload's full serialization is LAZY (round two of the 2026-08-10 CPU fix): steady
    state sends only chatTail suffixes, so eagerly json.dumps-ing the whole multi-MB active-tab
    payload every cycle — profiled as ~half the pusher's remaining busy samples — bought nothing.
    _send_chat materializes it only on the untrimmed full-send branch and hands it back for reuse."""

    def _client(self, caught_up_from=None, sid="s1", head_uuid="e0"):
        sent = []
        c = {"app": "chat", "alive": True, "send": lambda s: sent.append(s), "sent": {}}
        if caught_up_from is not None:
            c["echat"] = {sid: (head_uuid, caught_up_from)}
        return c, sent

    def _payload(self, sid="s1", n=5):
        return {"type": "session", "id": sid, "status": {"state": "working"},
                "events": [{"uuid": "e%d" % i, "kind": "user", "text": "m%d" % i} for i in range(n)]}

    def test_a_caught_up_client_gets_a_tail_and_no_full_serialization_happens(self):
        m = self._payload()
        c, sent = self._client(caught_up_from=0)
        out = km._send_chat(c, m, None, 3, False)
        self.assertIsNone(out, "no full send → the lazy serialization was never materialized")
        self.assertEqual(len(sent), 1)
        got = json.loads(sent[0])
        self.assertEqual((got["type"], got["from"]), ("chatTail", 3))

    def test_a_fresh_client_materializes_it_once_and_hands_it_back(self):
        m = self._payload()
        c, sent = self._client()                     # no echat state → the full-send branch
        out = km._send_chat(c, m, None, 3, False)
        self.assertIsInstance(out, str, "the full send materialized the serialization")
        self.assertEqual(json.loads(out)["id"], "s1")
        self.assertEqual(sent, [out], "the exact materialized bytes went to the client")
        # a second full-send client REUSES the returned serialization verbatim
        c2, sent2 = self._client()
        out2 = km._send_chat(c2, m, out, 3, False)
        self.assertIs(out2, out)

    def test_unchanged_feed_and_bars_reuse_their_wire_form_across_cycles(self):
        # Round three: with nothing changed, a cycle must not re-serialize the shared payloads at all —
        # measured on a quiet fleet, the per-cycle dumps were ~357KB (feed) + ~1.65MB (bars), ~4MB/s of
        # json.dumps discarded by the dedup. The wire caches key on the cached build's identity (+ a
        # deep-eq on the ledgers attach), so an unchanged second cycle serves the SAME tuple.
        base = OneSnapshotPerCycle("test_one_cycle_reads_liveness_once_however_deep_the_call")
        base.setUp()
        try:
            km.Sessions.live = lambda: dict(base.row)
            frames = []
            with km._clients_lock:
                km._clients[:] = [
                    {"app": "chat", "alive": True, "wid": "", "qbytes": 0, "send": lambda s: None},
                    {"app": "feed", "alive": True, "wid": "", "qbytes": 0, "send": frames.append},
                    {"app": "timeline", "alive": True, "wid": "", "qbytes": 0, "send": lambda s: None},
                ]
            km._feed_wire = km._bars_wire = None
            km._built_feed[:] = [None, None, 0.0, 0.0]
            km._built_timeline[:] = [None, None, 0.0, 0.0]
            km._pusher_cycle()
            w_feed, w_bars = km._feed_wire, km._bars_wire
            self.assertIsNotNone(w_feed, "the first cycle made the feed's wire form once")
            # the body is a lazy cell: this feed client announces no delta, so its whole frame went and the cell
            # holds the one whole encode of the build; the signature is the split's tuple
            self.assertIsInstance(w_feed[3], km._LazyWire)
            self.assertTrue(w_feed[3].materialized(), "a legacy client took the whole frame: serialized once")
            self.assertEqual(w_feed[4], km._parts_sig(w_feed[5]))
            n = len(frames)
            km._pusher_cycle()
            self.assertIs(km._feed_wire, w_feed, "unchanged feed → the SAME wire tuple, no re-dump")
            if w_bars is not None:   # bars need a warmed timeline build; when present, same contract
                self.assertIs(km._bars_wire, w_bars, "unchanged bars → the SAME wire tuple, no re-dump")
            self.assertEqual(len(frames), n, "…and the deduped client got nothing new")
        finally:
            base.tearDown()
            km._feed_wire = km._bars_wire = None
            km._built_feed[:] = [None, None, 0.0, 0.0]
            km._built_timeline[:] = [None, None, 0.0, 0.0]

    def test_send_client_honors_a_precomputed_dedup_sig(self):
        # feed/bars carry volatile keys, so _dedup_sig re-dumps the FILTERED payload per call — the
        # pusher now computes it once per cycle and passes it down. Prove the parameter is authoritative:
        # two payloads differing in a NON-volatile field but sharing a passed sig must dedup.
        sent = []
        c = {"app": "feed", "alive": True, "send": lambda s: sent.append(s)}
        m1 = {"type": "bars", "now": 1, "x": "a"}
        m2 = {"type": "bars", "now": 2, "x": "b"}    # x differs → a recomputed sig would NOT dedup
        km._send_client(c, ("t",), m1, pre=json.dumps(m1), sig="same")
        km._send_client(c, ("t",), m2, pre=json.dumps(m2), sig="same")
        self.assertEqual(len(sent), 1, "the passed sig, not a recomputation, drives the dedup")


class OneTenFileSnapshotPerPass(_CycleFixture):
    """plans/nudge-walk-events.md, the shared snapshot: the ten-file key every event-keyed tick job reads
    (_session_files_stat) is taken once per session per jobs pass and served to every later asker in that
    pass, so the lift, the walk and the interrupt tick read one view of a session's files and the pass pays
    ten stats per alive session, not ten per asker. memos.nudgeWalk.stats counts the stats paid."""
    def test_the_tick_jobs_share_one_ten_file_snapshot_per_pass(self):
        real, real_stat, asked, inside, stats = km._session_files_stat, os.stat, collections.Counter(), [0], [0]
        def counting(s):                     # the asks, and the stats the key itself pays while answering them
            asked[s["sid"]] += 1
            inside[0] += 1
            try:
                return real(s)
            finally:
                inside[0] -= 1
        def stat(*a, **k):
            if inside[0]:
                stats[0] += 1
            return real_stat(*a, **k)
        km._session_files_stat, os.stat = counting, stat
        try:
            before = km._NUDGE_WALK_STATS.get("stats")
            km.Sessions.live = lambda: dict(self.row)
            with km._clients_lock:
                km._clients[:] = []
            km._jobs_cycle()
            counted = (km._NUDGE_WALK_STATS.get("stats") or 0) - (before or 0)
        finally:
            km._session_files_stat, os.stat = real, real_stat
        self.assertGreaterEqual(min(asked[SID], asked[SID2]), 2,
                                "more than one tick job asks for each alive session's key in a pass: %r" % dict(asked))
        self.assertEqual(stats[0], 10 * len(self.row),
                         "ten stats per alive session per pass, whoever asks: %r asks, %d stats" % (dict(asked), stats[0]))
        self.assertEqual(counted, stats[0], "memos.nudgeWalk.stats counts the stats the key paid")

    def _pass(self):
        """One jobs cycle over the fixture's two live sessions: (the stats the ten-file key paid, the walk's parses, its gate
        hits), the stats counted through os.stat while the key answers."""
        real, real_stat, inside, stats = km._session_files_stat, os.stat, [0], [0]
        def counting(s):
            inside[0] += 1
            try:
                return real(s)
            finally:
                inside[0] -= 1
        def stat(*a, **k):
            if inside[0]:
                stats[0] += 1
            return real_stat(*a, **k)
        p0, h0 = km._NUDGE_WALK_STATS["parses"], km._NUDGE_WALK_STATS["skippedParses"]
        km._session_files_stat, os.stat = counting, stat
        try:
            km.Sessions.live = lambda: dict(self.row)
            with km._clients_lock:
                km._clients[:] = []
            km._jobs_cycle()
        finally:
            km._session_files_stat, os.stat = real, real_stat
        return stats[0], km._NUDGE_WALK_STATS["parses"] - p0, km._NUDGE_WALK_STATS["skippedParses"] - h0

    def test_a_quiet_pass_stats_nothing_and_parses_nothing(self):
        """plans/nudge-walk-events.md rule 2: with no event marked and the floor standing, the next pass serves every
        session's key from the standing snapshot (no stat) and the walk's gate skips every look."""
        first, _, _ = self._pass()
        self.assertEqual(first, 10 * len(self.row), "the boot's first pass stats every alive session")
        self._pass()                                            # the first pass's own writes (the ledger's never-seen rows) mark the second
        served0 = km._NUDGE_WALK_STATS.get("served")
        stats, parses, hits = self._pass()
        self.assertEqual(stats, 0, "a quiet pass pays no per-session stat")
        self.assertEqual(parses, 0, "and the walk parses nothing")
        self.assertEqual(hits, len(self.row), "every look is a gate hit on the standing key")
        self.assertEqual((km._NUDGE_WALK_STATS.get("served") or 0) - (served0 or 0), len(self.row), "memos.nudgeWalk.served counts them")

    def test_the_floor_re_stats_every_session_and_still_parses_nothing(self):
        self._pass(); self._pass()
        for v in getattr(km, "_FILES_STAT_STANDING", {}).values():
            v[1] -= getattr(km, "NUDGE_FLOOR_S", 30)          # the standing stats are older than the floor now
        stats, parses, hits = self._pass()
        self.assertEqual(stats, 10 * len(self.row), "the floor re-stats every session once")
        self.assertEqual((parses, hits), (0, len(self.row)), "nothing moved, so the fresh keys still hit the memo")
        self.assertEqual(self._pass()[0], 0, "and the pass after it is quiet again")

    def test_a_session_file_written_here_marks_that_session_alone(self):
        self._pass(); self._pass()
        jd.append_episode(SID, "h1", SID, NOW)                 # a keyed file of SID, written through the judge module's own writer
        stats, parses, hits = self._pass()
        self.assertEqual(stats, 10, "the marked session is statted, the other is served: %d stats" % stats)
        self.assertEqual((parses, hits), (1, len(self.row) - 1), "its moved key parses once; the other session's look hits")
        self.assertEqual(self._pass()[0], 0, "and the pass after it is quiet again")

    def test_a_judge_written_store_marks_every_session(self):
        self._pass(); self._pass()
        (jd.GOALDIR / (SID2 + ".json")).write_text(json.dumps({"rompUuid": SID2, "nodes": {}, "status": {}}))   # the judges' process
        self.assertTrue(km._bump_judge_gen_if_changed(), "the producer's observer sees the store move")           # publishing a store
        stats, parses, hits = self._pass()
        self.assertEqual(stats, 10 * len(self.row), "every session's key is statted after a judge write")
        self.assertEqual(self._pass()[0], 0, "and the pass after it is quiet again")

    def test_a_live_row_change_marks_its_session(self):
        self._pass(); self._pass()
        self.row[SID]["state"] = "working"                      # the backend's in-memory word on a turn's edge: no file of the key yet
        stats, parses, hits = self._pass()
        self.assertEqual(stats, 10, "the row that moved is statted, the other served: %d stats" % stats)
        self.assertEqual(self._pass()[0], 0, "and the pass after it is quiet again")

    def test_the_postal_log_moving_marks_every_session(self):
        self._pass(); self._pass()
        (jd.STATE / "timeline").mkdir(exist_ok=True)
        with (jd.STATE / "timeline" / "messages.jsonl").open("a") as fh:
            fh.write(json.dumps({"id": "m1", "t": NOW}) + "\n")   # another process's log: the prelude's own stat sees it move
        stats, parses, hits = self._pass()
        self.assertEqual(stats, 10 * len(self.row), "the shared log moved: every session is statted")
        self.assertEqual(self._pass()[0], 0, "and the pass after it is quiet again")

    def test_outside_a_pass_every_ask_stats(self):
        """A handler's own tick runs with no pass scope open: nothing is served stale from an earlier pass."""
        s = {"sid": SID, "path": self.paths[SID]}
        km._live_scope.files_stat = None
        before = km._NUDGE_WALK_STATS.get("stats")
        km._session_files_stat(s); km._session_files_stat(s)
        self.assertEqual((km._NUDGE_WALK_STATS.get("stats") or 0) - (before or 0), 20, "two asks, twenty stats, no memo")


if __name__ == "__main__":
    unittest.main()
