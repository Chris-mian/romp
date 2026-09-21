#!/usr/bin/env python3
"""One session's UNREADABLE goals file is loud for that session and invisible to the others.

load_goals raises on a read fault (EACCES, EIO, a directory at the path) instead of fabricating an
empty store. Inside the judge passes that raise reaches the per-session pass wrapper; everywhere else
it used to reach nothing: the feed builder's session loop, the timeline, the chat ledger, the kernel's
ticks and the index tier read every store with no per-session catch, all under the pusher's single
outer try. One faulting file made the pusher log a line and send NOTHING to ANY client, every cycle,
for as long as the fault lasted. jd.load_goals_or_fault is the boundary: `(store, None)` or
`(None, exc)`, one `store-unreadable` judge-errors row per fault EPISODE (a successful read ends the
episode), and never an empty store. run_courier and run_propagate get the per-session `pass-crash`
catch the other passes already have, and a user gesture a fault made us skip answers the socket that
made it.

SYNTHETIC fixtures only: private synthetic sids, the notes-api demo world (`web` / `api` / `tests`),
message ids stamped TESTHOST; the per-sid override journals are cleaned in tearDown."""
import contextlib
import errno
import itertools
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from romp_load import load_source
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
km = load_source("romp_kernel_storefault", os.path.join(BIN, "romp-kernel"))
jd = km.jd

A = "9c0d1e2f-3a4b-4c5d-8e6f-0a1b2c3d4e5f"      # the session whose store FAULTS
B = "9c0d1e2f-3a4b-4c5d-8e6f-0a1b2c3d4e60"      # a healthy peer
P = "9c0d1e2f-3a4b-4c5d-8e6f-0a1b2c3d4e61"      # a third session, the peer a walk or a link reaches
NOW = 1781300000
T0 = NOW - 3600
MID1 = "1781296400.000001_1.TESTHOST"
MID2 = "1781296400.000002_1.TESTHOST"


def _iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _uline(t, text, uuid, parent=None, ps="typed"):
    return {"type": "user", "timestamp": _iso(t), "uuid": uuid, "parentUuid": parent,
            "promptSource": ps, "message": {"role": "user", "content": text}}


def _aline(t, text, uuid, parent, stop="end_turn"):
    return {"type": "assistant", "timestamp": _iso(t), "uuid": uuid, "parentUuid": parent,
            "message": {"role": "assistant", "content": [{"type": "text", "text": text}],
                        "stop_reason": stop}}


def _peer_body(mid, text):
    return "DELEGATE: %s\n<!-- romp-msg-id: %s -->\n<!-- romp-msg-kind: delegate -->" % (text, mid)


def _TM():
    """One live session row, every key the feed and timeline builders read."""
    return {"state": "ready", "color": "#888888", "since": NOW - 60, "model": "", "effort": "",
            "context": None, "backend": "sdk"}


def _store(sid, text, **node):
    """A one-goal store in the judge's own shape; `node` overrides the goal's fields."""
    gid = sid + ":g1"
    nd = {"id": gid, "parentId": None, "t": T0, "mt": T0, "text": text, "nodeComplete": False,
          "blocked": False, "cleared": False, "trail": [], "log": []}
    nd.update(node)
    return {"rompUuid": sid, "seq": 1, "rev": 1, "placementsV": jd.PLACEMENTS_V, "placements": {},
            "nodes": {gid: nd}, "status": {gid: "completed" if nd.get("nodeComplete") else "working"},
            "lastNode": gid}


@contextlib.contextmanager
def _fault_on(path):
    """Every reader of `path` raises EIO; every other read is untouched. Path.read_text is the load path's
    reader; the save path's memoized readers (_disk_entry, _disk_rev) open a descriptor of their own and
    read from it (_disk_read), so os.open faults for the path as well."""
    orig_read_text, orig_open = Path.read_text, os.open

    def faulting(p, *a, **kw):
        if p == path:
            raise OSError(errno.EIO, "Input/output error", str(p))
        return orig_read_text(p, *a, **kw)

    def faulting_open(p, *a, **kw):
        if os.fspath(p) == str(path):
            raise OSError(errno.EIO, "Input/output error", str(path))
        return orig_open(p, *a, **kw)
    with mock.patch.object(Path, "read_text", faulting), mock.patch.object(os, "open", faulting_open):
        yield


class _World(unittest.TestCase):
    def setUp(self):
        self._saved = jd.STATE
        self.td = tempfile.TemporaryDirectory()
        jd._rebind_state(Path(self.td.name))
        jd.GOALDIR.mkdir(parents=True)
        jd.NAMES.mkdir(parents=True)
        self.a_file = jd.GOALDIR / (A + ".json")
        self.b_file = jd.GOALDIR / (B + ".json")
        self._write(A, _store(A, "the faulting session's goal"))
        self._write(B, _store(B, "the healthy session's goal"))
        km._parse_cache.clear()
        jd._PARSE_CACHE.clear(); jd._CHAIN_MEMO.clear()

    def tearDown(self):
        for sid in (A, B, P):
            (jd._overrides_dir() / (sid + ".jsonl")).unlink(missing_ok=True)
        jd._rebind_state(self._saved)
        for sid in (A, B, P):
            (jd._overrides_dir() / (sid + ".jsonl")).unlink(missing_ok=True)
        self.td.cleanup()

    def _write(self, sid, store):
        (jd.GOALDIR / (sid + ".json")).write_text(json.dumps(store))

    def _transcript(self, sid, recs):
        p = Path(self.td.name) / (sid + ".jsonl")
        p.write_text("\n".join(json.dumps(r) for r in recs) + "\n")
        km._parse_cache.clear()
        jd._PARSE_CACHE.clear(); jd._CHAIN_MEMO.clear()
        return str(p)

    def _rows(self, err=None):
        if not jd.ERRORS.exists():
            return []
        rows = [json.loads(l) for l in jd.ERRORS.read_text().splitlines()]
        return [r for r in rows if err is None or r["err"] == err]


class FeedBoundary(_World):
    def setUp(self):
        super().setUp()
        # B's card wears a delegation-origin badge pointing at A's goal: the badge's liveness is read
        # from A's store, so the PEER read in build_feed's card loop is exercised too
        self._write(B, _store(B, "the healthy session's goal", origin={"peer": A, "goalId": A + ":g1"}))
        self.sessions = [{"sid": A, "name": "web", "path": "/nonexistent/%s.jsonl" % A, "anchor": 0, "mtime": 0},
                         {"sid": B, "name": "api", "path": "/nonexistent/%s.jsonl" % B, "anchor": 0, "mtime": 0}]
        for p in (mock.patch.object(km, "_alive_sessions", lambda now, live_map: list(self.sessions)),
                  mock.patch.object(km, "_warm_fleet_bg", lambda now: None)):
            p.start()
            self.addCleanup(p.stop)
        self.live = {A: _TM(), B: _TM()}

    def _asks(self):
        return {a["itemId"]: a for a in km.build_feed(NOW, self.live)["asks"]}

    def test_one_faulting_store_costs_that_session_only_and_files_one_row_per_episode(self):
        with _fault_on(self.a_file):
            cards = self._asks()
            self.assertIn(B + ":g1", cards, "the healthy session's card is on the board")
            self.assertNotIn(A + ":g1", cards, "nothing goal-derived is shown for the session that faulted")
            self.assertFalse(cards[B + ":g1"]["origin"]["live"],
                             "a badge whose sender's store faults reads absorbed, and the build goes on")
            rows = self._rows("store-unreadable")
            self.assertEqual([(r["fsid"], r["judge"]) for r in rows], [(A, "romp")],
                             "exactly one row, for the faulting session, on the judge-errors surface")
            self.assertIn("Input/output error", rows[0]["note"], "the note carries the fault itself")
            self._asks()
            self.assertEqual(len(self._rows("store-unreadable")), 1, "a repeat of the same fault files nothing new")
        cards = self._asks()                         # the fault cleared: A reads again → its episode ends
        self.assertIn(A + ":g1", cards)
        self.assertTrue(cards[B + ":g1"]["origin"]["live"], "the badge reads the sender's open goal again")
        self.assertEqual(len(self._rows("store-unreadable")), 1, "a healthy build files nothing")
        with _fault_on(self.a_file):
            self._asks()
        self.assertEqual(len(self._rows("store-unreadable")), 2,
                         "a fault after a successful read is a NEW episode and files again")

    def test_the_faulting_stores_file_is_never_written(self):
        before = self.a_file.read_bytes()
        with _fault_on(self.a_file):
            self._asks()
        self.assertEqual(self.a_file.read_bytes(), before, "the build never publishes over a store it could not read")

    def test_the_provisional_card_is_not_inferred_from_a_store_that_faulted(self):
        """'The planner has not placed this prompt yet' is read off PLACEMENTS. With the store unreadable
        that is not knowledge, so the placeholder that would surface on a healthy store must not."""
        self._write(A, _store(A, "the faulting session's goal", nodeComplete=True))   # no working card fronts it
        tpath = self._transcript(A, [_uline(NOW - 500, "start the next piece", "u1"),
                                     _aline(NOW - 480, "Done.", "a1", "u1")])
        self.sessions[0]["path"] = tpath
        km._parse(tpath, A, NOW)                     # warm: build_feed reads the parse cache only
        self.assertIn("provisional:" + A, self._asks(),
                      "premise: on a healthy store the unplaced prompt surfaces a provisional card")
        with _fault_on(self.a_file):
            ids = set(self._asks())
        self.assertNotIn("provisional:" + A, ids, "not inferred from placements we could not read")
        self.assertEqual([i for i in ids if A in i], [], "nothing at all is shown for the faulting session")
        self.assertIn("provisional:" + A, self._asks(), "and it is back once the store reads again")

    def test_the_timeline_frame_ships_with_one_lane_faulting(self):
        km._BARS_COMPLAINED.clear()
        with _fault_on(self.a_file):
            tl = km.build_timeline(NOW, self.live, with_bars=False)
            self.assertIsNotNone(tl, "the frame ships")
            lanes = {s["id"] for s in tl.get("sessions") or []} if isinstance(tl, dict) else set()
            self.assertIn(B, lanes, "the healthy lane is there")
            self.assertEqual(len(self._rows("store-unreadable")), 1, "one row for the faulting lane")
        self.assertTrue(str(km._BARS_COMPLAINED.get((A, "goals"), "")).startswith("OSError"),
                        "and the lane says why it renders without goal data, like every other bars stage")

    def test_the_chat_tab_builds_with_its_store_faulting(self):
        tpath = self._transcript(A, [_uline(NOW - 500, "start the next piece", "u1"),
                                     _aline(NOW - 480, "Done.", "a1", "u1")])
        sess = [{"sid": A, "name": "web", "anchor": None, "path": tpath, "mtime": NOW}]
        with mock.patch.object(km, "_sessions", lambda now, window=None, forks=True: list(sess)):
            healthy = km.build_session(A, NOW, self.live)
            self.assertTrue(healthy and healthy["ledger"]["tree"], "premise: the tab's ledger tree shows the goal")
            with _fault_on(self.a_file):
                m = km.build_session(A, NOW, self.live)
        self.assertIsNotNone(m, "the tab builds")
        self.assertEqual(m["id"], A)
        self.assertEqual(m["ledger"]["tree"], [], "with no goal-derived content")
        self.assertEqual([r["fsid"] for r in self._rows("store-unreadable")], [A])


class PushBoundary(_World):
    def test_one_faulting_store_does_not_stop_the_push(self):
        """The pusher's outer try used to catch the raise and return before sending to ANY client."""
        sessions = [{"sid": A, "name": "web", "path": "/nonexistent/%s.jsonl" % A, "anchor": 0, "mtime": 0},
                    {"sid": B, "name": "api", "path": "/nonexistent/%s.jsonl" % B, "anchor": 0, "mtime": 0}]
        live = {A: _TM(), B: _TM()}
        sent = []
        with mock.patch.object(km, "_alive_sessions", lambda now, tm: list(sessions)), \
                mock.patch.object(km, "_warm_fleet_bg", lambda now: None), \
                mock.patch.object(km, "_live_map", lambda: dict(live)), \
                mock.patch.object(km, "_chat_tab_sessions", lambda now, tm: []), \
                mock.patch.object(km, "_send_client", lambda c, key, msg, pre=None, sig=None: sent.append((key, msg))), \
                _fault_on(self.a_file):
            km._push([{"app": "feed", "alive": True}], live_map=live)
        keys = [k[0] for k, _ in sent]
        self.assertIn("feed", keys, "a feed payload reached the client despite one session's fault: %r" % keys)
        payload = next(m for k, m in sent if k[0] == "feed")
        body = payload if isinstance(payload, dict) else json.loads(payload)
        data = body.get("data") or body.get("feed") or body
        cards = {a["itemId"] for a in (data.get("asks") or [])}
        self.assertIn(B + ":g1", cards, "and it carries the healthy session's card")
        self.assertEqual([r["fsid"] for r in self._rows("store-unreadable")], [A])


class InterruptLiftBoundary(_World):
    """The interrupt tick's LIFT: on a store fault the intrBlocked marker must be KEPT, so the next
    healthy tick lifts romp's own block; erasing it would leave the card in Needs-you wearing a block
    no tick ever looks at again."""
    CUT_T = NOW - 1800
    RESUME_T = NOW - 600

    def setUp(self):
        super().setUp()
        self.tpath = self._transcript(A, [_uline(NOW - 3600, "wire up the reconnect banner", "u1"),
                                          _aline(NOW - 3580, "on it", "a1", "u1", "tool_use"),
                                          _uline(self.CUT_T, "[Request interrupted by user]", "u2", "a1")])
        st = _store(A, "Ship the reconnect banner")
        st["closedTurns"] = []
        self._write(A, st)
        km._write_auto_nudge({"enabled": True, "nudged": {}, "intrBlocked": {}})
        for p in (mock.patch.object(km, "_alive_sessions", lambda now, live_map: [{"sid": A, "path": self.tpath}]),
                  mock.patch.object(km, "_push_all", lambda *a, **k: None),
                  mock.patch.object(jd, "CLOSER_ON", False)):
            p.start()
            self.addCleanup(p.stop)
        km._downtime[:] = []
        km._autonudge_cache.clear()
        km._pending_ops.clear()
        self.live = {A: dict(_TM(), state="idle")}

    def _reengage(self):
        with open(self.tpath, "a") as f:
            f.write(json.dumps(_uline(self.RESUME_T, "use the staging host for now", "u3", "u2")) + "\n")
            f.write(json.dumps(_aline(self.RESUME_T + 40, "done", "a2", "u3")) + "\n")
        km._parse_cache.clear()
        jd._PARSE_CACHE.clear(); jd._CHAIN_MEMO.clear()

    def test_a_fault_at_the_reengage_tick_keeps_the_marker_so_the_next_tick_lifts(self):
        gid = A + ":g1"
        km._interrupt_block_tick(NOW, self.live)
        self.assertEqual(km._intr_blocked(A), gid, "premise: the stop blocked the focus goal and marked it")
        self.assertEqual(jd.load_goals(A)["status"][gid], "blocked")
        self._reengage()
        before = self.a_file.read_bytes()
        with _fault_on(self.a_file):
            km._interrupt_block_tick(NOW, self.live)
        self.assertEqual(self.a_file.read_bytes(), before, "nothing was written to a store we could not read")
        self.assertEqual(km._intr_blocked(A), gid, "the marker is KEPT: the lift is owed, not spent")
        km._interrupt_block_tick(NOW, self.live)  # the fault cleared
        self.assertEqual(jd.load_goals(A)["status"][gid], "working", "the next healthy tick lifts the block")
        self.assertIsNone(km._intr_blocked(A), "and spends the marker")

    def test_a_fault_at_the_stop_tick_records_no_block_and_the_next_healthy_tick_does(self):
        """The BLOCK half of the tick meets the fault too: a genuine stop whose store cannot be read records
        nothing, writes nothing and marks nothing (a marker with no block behind it would be a claim with no
        evidence), files the session's one `store-unreadable` row, and the next healthy tick blocks the focus
        goal as if the fault had never been. A bare load_goals here raised out of the whole tick, which has
        no per-session catch around this write (review find, 2026-09-08)."""
        gid = A + ":g1"
        before = self.a_file.read_bytes()
        with _fault_on(self.a_file):
            km._interrupt_block_tick(NOW, self.live)
        self.assertIsNone(km._intr_blocked(A), "no marker: nothing was blocked")
        self.assertEqual(self.a_file.read_bytes(), before, "nothing was written to a store we could not read")
        self.assertEqual([r["fsid"] for r in self._rows("store-unreadable")], [A], "and the fault is filed once")
        km._interrupt_block_tick(NOW, self.live)          # the fault cleared
        self.assertEqual(km._intr_blocked(A), gid, "the next healthy tick blocks the focus goal and marks it")
        self.assertEqual(jd.load_goals(A)["status"][gid], "blocked")

    def _append(self, recs):
        with open(self.tpath, "a") as f:
            for r in recs:
                f.write(json.dumps(r) + "\n")
        km._parse_cache.clear()
        jd._PARSE_CACHE.clear(); jd._CHAIN_MEMO.clear()

    def test_a_second_stop_during_the_fault_keeps_the_marker_so_the_block_is_still_lifted_after(self):
        """The kept-marker promise has to survive the block branch too: a SECOND genuine stop while the
        fault persists asks _intr_block_stands whether the marked block still holds its card, and a store
        it cannot read is not evidence that it fell. Reading a fault as 'no longer stands' popped the
        marker, the re-block failed through the same fault, and romp's own block outlived every tick."""
        gid = A + ":g1"
        km._interrupt_block_tick(NOW, self.live)
        self.assertEqual(km._intr_blocked(A), gid, "premise: the stop blocked the focus goal and marked it")
        self._reengage()
        before = self.a_file.read_bytes()
        with _fault_on(self.a_file):
            km._interrupt_block_tick(NOW, self.live)          # re-engaged under the fault: the lift is owed
            self.assertEqual(km._intr_blocked(A), gid, "kept (the lift's half of the promise)")
            self._append([_uline(self.RESUME_T + 100, "and the prod host after", "u4", "a2"),
                          _aline(self.RESUME_T + 120, "on it", "a3", "u4", "tool_use"),
                          _uline(self.RESUME_T + 200, "[Request interrupted by user]", "u5", "a3")])
            km._interrupt_block_tick(NOW, self.live)          # a second stop, still under the fault
            self.assertEqual(km._intr_blocked(A), gid, "still kept: an unreadable store is not evidence the block fell")
        self.assertEqual(self.a_file.read_bytes(), before, "nothing was written through the fault")
        km._interrupt_block_tick(NOW, self.live)              # the fault cleared, the stop still stands
        self.assertEqual(km._intr_blocked(A), gid, "the marked block holds its card, so the marker holds")
        self.assertEqual(jd.load_goals(A)["status"][gid], "blocked")
        self._append([_uline(self.RESUME_T + 300, "keep going with staging", "u6", "u5"),
                      _aline(self.RESUME_T + 340, "done", "a4", "u6")])
        km._interrupt_block_tick(NOW, self.live)              # re-engaged, readable: the lift lands
        self.assertEqual(jd.load_goals(A)["status"][gid], "working", "romp's own block is lifted")
        self.assertIsNone(km._intr_blocked(A), "and the marker is spent")


class NudgeTickBoundary(_World):
    """The auto-nudge tick's per-session slice reads the store once every session-level gate has passed:
    a fault there fires nothing, stamps nothing and files the session's one row. A bare load_goals raised
    out of the slice into the tick's per-session catch: one stderr line per tick, no row, and every nudge
    module still passed (review find, 2026-09-08)."""

    def setUp(self):
        super().setUp()
        uid = "11111111-2222-3333-4444-555555555555"
        turns = [{"id": "t1", "t": NOW - 600, "end": NOW - 540, "ended": True, "trigger": {"uuid": uid},
                  "atoms": [{"uuid": uid, "type": "user", "author": "human", "t": NOW - 600}]}]
        self.sent = []
        test = self

        class FakeBackend:
            def send(self, sid, body):
                test.sent.append((sid, body))
        for p in (mock.patch.object(km, "_session_flag", lambda sid, flag: False),
                  mock.patch.object(km, "_compacting_now", lambda sid: False),
                  mock.patch.object(km, "_api_error", lambda path: None),
                  mock.patch.object(km, "_session_working", lambda turns: False),
                  mock.patch.object(km, "_interrupt_suppresses_nudge", lambda turns, sid="", **k: False),
                  mock.patch.object(km, "_backend_queued", lambda sid: False),
                  mock.patch.object(km, "_backend_rewind_pending", lambda sid: False),
                  mock.patch.object(km, "_last_state", lambda sid: ("", 0)),
                  mock.patch.object(km, "_session_awaiting", lambda *a, **k: False),
                  # the first gate AFTER the read, held shut: a healthy slice stops right there, so the one
                  # question here (does the read stay inside the boundary?) has one answer either way
                  mock.patch.object(km, "_closer_settled", lambda *a: False),
                  mock.patch.object(km, "_pending_ops", {}),
                  mock.patch.object(jd, "parsed_session", lambda sid, paths, now: {"turns": turns}),
                  mock.patch.object(km.Sessions, "backend_for", staticmethod(lambda sid: FakeBackend()))):
            p.start()
            self.addCleanup(p.stop)
        km._autonudge_cache.clear()

    def _slice(self):
        return km._auto_nudge_session({"sid": A, "path": "/nonexistent/%s.jsonl" % A}, NOW, {}, {}, {})

    def test_a_faulting_store_fires_nothing_and_files_one_row(self):
        self.assertEqual(self._slice(), "closer-unsettled", "premise: every gate before the read passes; the read runs")
        before = self.a_file.read_bytes()
        with _fault_on(self.a_file):
            self.assertIsNone(self._slice(), "the fault stands the slice down")
        self.assertEqual(self.sent, [], "nothing was sent to the session")
        self.assertEqual(self.a_file.read_bytes(), before, "nothing was written to a store we could not read")
        self.assertEqual([r["fsid"] for r in self._rows("store-unreadable")], [A], "and the fault is filed once")
        self.assertEqual(self._slice(), "closer-unsettled", "the next tick reads again")


class TriagePassBoundary(_World):
    """run_courier and run_propagate walk every session with the same per-session catch the other passes
    have: the faulting session files a `pass-crash` row and the pass goes on to the next session."""

    def setUp(self):
        super().setUp()
        self.paths = {}
        for sid, text in ((A, "start the faulting session's work"), (B, "start the healthy session's work"),
                          (P, "start the peer's work")):
            self.paths[sid] = self._transcript(sid, [_uline(T0, text, "u-" + sid[-2:])])
        self._discover([A, B])
        self.msgs = Path(self.td.name) / "messages.jsonl"
        p = mock.patch.object(jd, "MESSAGES", self.msgs)
        p.start()
        self.addCleanup(p.stop)
        self.seen = []
        orig = jd.load_goals

        def recording(fsid):
            self.seen.append(fsid)
            return orig(fsid)
        p = mock.patch.object(jd, "load_goals", recording)
        p.start()
        self.addCleanup(p.stop)

    def _discover(self, sids):
        names = {A: "web", B: "api", P: "tests"}
        discovered = [(sid, self.paths[sid], None, names[sid]) for sid in sids]
        p = mock.patch.object(jd, "discover", lambda now, window=None, forks=True: list(discovered))
        p.start()
        self.addCleanup(p.stop)

    def _messages(self, rows):
        self.msgs.write_text("\n".join(json.dumps(r) for r in rows) + "\n")

    def _sent(self, mid, sender, to, body):
        return {"t": T0, "ev": "sent", "id": mid, "from": "web", "from_id": sender, "to_id": to,
                "kind": "delegate", "body": body}

    def _crashes(self, judge):
        return sorted((r["fsid"], r["note"].split(":")[0]) for r in self._rows("pass-crash") if r["judge"] == judge)

    def test_run_courier_continues_past_a_faulting_session(self):
        o_view = jd.load_goals_shared                 # the courier's scan reads the shared view (2026-09-09): record
        view = lambda fsid: (self.seen.append(fsid), o_view(fsid))[1]   # its reads beside the writer's
        with _fault_on(self.a_file), mock.patch.object(jd, "load_goals_shared", view):
            jd.run_courier(now=NOW)
        self.assertIn(B, self.seen, "the pass reached the healthy session after the fault")
        rows = self._rows("pass-crash")
        self.assertEqual([(r["judge"], r["fsid"]) for r in rows], [("courier", A)],
                         "one pass-crash row, for the faulting session, from the courier")
        self.assertIn("Input/output error", rows[0]["note"])

    def test_run_courier_files_a_faulting_sender_and_moves_on_to_the_next_message(self):
        """Three of the courier's reads name another session: a relayed message's sender, a pending
        message's recipient (read again when its turn comes), and a pending message's sender. Each
        faults here — P outright, A only from its second read — and each files its own row."""
        body_a, body_b = _peer_body(MID1, "the first piece"), _peer_body(MID2, "the second piece")
        self.paths[A] = self._transcript(A, [_uline(T0, body_a, "m1", ps="sdk"), _aline(T0 + 60, "On it.", "a1", "m1")])
        self.paths[B] = self._transcript(B, [_uline(T0 + 5, body_b, "m2", ps="sdk"), _aline(T0 + 65, "On it.", "a2", "m2")])
        self._discover([A, B, P])
        self._messages([self._sent(MID1, P, A, body_a), self._sent(MID2, P, B, body_b),
                        dict(self._sent("1781296400.000003_1.TESTHOST", P, "peer:remote-api", "DELEGATE: relayed"),
                             toName="remote-api", t=T0 + 1)])
        calls, orig = {}, jd.load_goals

        def faulting(fsid):
            calls[fsid] = calls.get(fsid, 0) + 1
            if fsid == P or (fsid == A and calls[fsid] >= 2):
                raise OSError(errno.EIO, "Input/output error", str(jd.GOALDIR / (fsid + ".json")))
            return orig(fsid)
        with mock.patch.object(jd, "load_goals", faulting), \
                mock.patch.object(jd, "load_goals_shared", faulting):
            jd.run_courier(now=NOW)
        self.assertEqual(self._crashes("courier"),
                         sorted([(P, "store"), (P, "sender store"), (A, "store"), (B, "sender %s store" % P[:8])]),
                         "P's own walk, the relayed sender, the re-read recipient and the pending sender each file a row")
        self.assertGreaterEqual(calls.get(B, 0), 2, "the healthy recipient was read in both arms: the pass went on")
        self.assertNotIn(A + ":g2", jd.load_goals(A).get("nodes", {}), "nothing was planted off a faulting sender")

    def test_run_courier_skips_a_message_whose_root_walk_hits_a_faulting_peer(self):
        """The sender is healthy; the link's chain hops to a PEER whose store faults. The message is
        skipped this pass (retried next), never treated as 'unrooted', which would mint a recipient top."""
        body = _peer_body(MID1, "the first piece")
        self.paths[B] = self._transcript(B, [_uline(T0, body, "m1", ps="sdk"), _aline(T0 + 60, "On it.", "a1", "m1")])
        self._discover([A, B, P])
        self._messages([self._sent(MID1, A, B, body)])
        self._write(A, _store(A, "the sender's open ask", origin={"peer": P, "goalId": P + ":g1"}))
        self._write(P, _store(P, "the peer's goal"))
        calls, orig = {}, jd.load_goals

        def faulting(fsid):                          # P reads fine in the session loop; its store faults when the
            calls[fsid] = calls.get(fsid, 0) + 1     # root walk hops to it
            if fsid == P and calls[fsid] >= 2:
                raise OSError(errno.EIO, "Input/output error", str(jd.GOALDIR / (fsid + ".json")))
            return orig(fsid)
        with mock.patch.object(jd, "courier_llm",
                               lambda text, menu, declared=None: '{"verdict": "delegating", "goal": 1, "text": "the first piece"}'), \
                mock.patch.object(jd, "load_goals", faulting), \
                mock.patch.object(jd, "load_goals_shared", faulting):
            jd.run_courier(now=NOW)
        self.assertEqual(self._crashes("courier"), [(B, "root walk")], "the one arm that tripped, attributed to the recipient")
        self.assertGreaterEqual(calls.get(P, 0), 2, "premise: the walk did hop to the peer")
        b = jd.load_goals(B)
        self.assertEqual(list(b["nodes"]), [B + ":g1"], "no recipient top was minted off an unresolved walk")
        self.assertEqual(b["placements"], {}, "the message stays pending for the next pass")

    def test_run_propagate_continues_past_a_faulting_session(self):
        with _fault_on(self.a_file):
            jd.run_propagate(now=NOW)
        self.assertEqual(self.seen.count(B), 1, "the healthy session is read once per pass, shared by both arms")
        self.assertGreaterEqual(self.seen.count(A), 2,
                                "both arms of the pass reached the faulting session (a read that raised is not kept)")
        rows = self._rows("pass-crash")
        self.assertTrue(rows, "the faulting session's rows are filed")
        self.assertEqual({(r["judge"], r["fsid"]) for r in rows}, {("propagate", A)},
                         "every row is the faulting session's, from the propagate pass")

    def test_run_propagate_leaves_a_faulting_senders_tracker_for_the_next_pass(self):
        # B finished a goal it was handed by A; checking A's tracker off needs A's store, which faults
        self._write(B, _store(B, "the delegated piece", nodeComplete=True, origin={"peer": A, "goalId": A + ":g1"}))
        with _fault_on(self.a_file):
            jd.run_propagate(now=NOW)
        crashes = self._crashes("propagate")
        self.assertIn((B, "sender %s store" % A[:8]), crashes, "the recipient's row names the sender it could not read")
        self.assertIn(B, self.seen)

    def test_run_propagate_joins_a_faulting_recipient_to_nothing_and_writes_no_tracker(self):
        # A's tracker waits on B; the reply sweep asks B's store whether the card was dismissed
        self._write(A, _store(A, "the handed-off piece", handoff={"peer": B, "msgId": MID1, "t": T0}))
        before = self.a_file.read_bytes()
        with _fault_on(self.b_file):
            jd.run_propagate(now=NOW)
        self.assertEqual([r["fsid"] for r in self._rows("store-unreadable")], [B],
                         "the recipient lookup goes through the boundary: one row for B")
        self.assertEqual(self.a_file.read_bytes(), before, "A's tracker stays open, unwritten")

    def test_the_index_tier_captions_the_healthy_session_when_one_store_faults(self):
        with _fault_on(self.a_file):
            self.assertEqual(jd.tasks_for(A, self.paths[A], [self.paths[A]], NOW), [],
                             "no caption tasks are derived from a store that could not be read")
            self.assertTrue(jd.tasks_for(B, self.paths[B], [self.paths[B]], NOW),
                            "the healthy session's tasks are unaffected")
        self.assertEqual([r["fsid"] for r in self._rows("store-unreadable")], [A])


class GestureRefusal(_World):
    """A user gesture a fault made us skip must reach the socket that made it: an undo whose session
    cannot be read appends its journal row, but the card does not come back, and before this nothing on
    screen said why."""

    def setUp(self):
        super().setUp()
        sessions = [{"sid": A, "name": "web", "path": "/nonexistent/%s.jsonl" % A, "anchor": 0, "mtime": 0},
                    {"sid": B, "name": "api", "path": "/nonexistent/%s.jsonl" % B, "anchor": 0, "mtime": 0}]
        self.live = {A: _TM(), B: _TM()}
        for p in (mock.patch.object(km, "_alive_sessions", lambda now, live_map: list(sessions)),
                  mock.patch.object(km, "_warm_fleet_bg", lambda now: None),
                  mock.patch.object(km, "_live_map", lambda: dict(self.live))):   # the handler's own build
            p.start()
            self.addCleanup(p.stop)

    def _dispatch(self, msg):
        sent = []
        client = {"app": "feed", "alive": True, "send": lambda s: sent.append(json.loads(s))}
        km.Handler._dispatch_ws(object.__new__(km.Handler), msg, client)
        return sent

    def _feed_rows(self, sid):
        """What the board shows for `sid` right now: {card itemId: card}."""
        return {a["itemId"]: a for a in km.build_feed(NOW, self.live)["asks"] if a["itemId"].startswith(sid)}

    def test_an_undo_clear_the_fault_skipped_answers_the_socket_that_asked(self):
        gid = A + ":g1"
        jd.GOALARCHDIR.mkdir(parents=True, exist_ok=True)   # the cleared card was compacted to the archive
        arch = _store(A, "the cleared card", cleared=True)
        (jd.GOALARCHDIR / (A + ".json")).write_text(json.dumps({"rompUuid": A, "nodes": arch["nodes"],
                                                                 "status": {gid: "cleared"}}))
        (jd.STATE / "cleared.jsonl").write_text(json.dumps({"id": gid, "t": NOW - 10, "op": "clear"}) + "\n")
        before = self.a_file.read_bytes()
        with _fault_on(self.a_file):
            sent = self._dispatch({"type": "undoClear"})
        errs = [m for m in sent if m.get("type") == "err"]
        self.assertEqual([m.get("sid") for m in errs], [A], "one refusal, for the session the undo could not reach")
        self.assertIn("undo", errs[0]["title"])
        self.assertIn("Input/output error", errs[0]["text"], "and it says why")
        self.assertIn("not restored", errs[0]["text"], "and what did not happen")
        self.assertIn("press Undo again", errs[0]["text"], "and the one true remedy: the next Undo retries these ids")
        self.assertNotIn("copy", errs[0], "`copy` is the USER'S undelivered text by contract; romp's prose never rides it")
        self.assertEqual(self.a_file.read_bytes(), before, "nothing was written to the store")
        self.assertIn(gid, json.loads((jd.GOALARCHDIR / (A + ".json")).read_text())["nodes"],
                      "the archive still holds the card for a later undo")

    def test_the_refusal_names_the_goals_file_relative_to_the_state_root(self):
        """The dialog's copy of the fault says goals/<sid>.json, never the absolute path under the home
        directory: an absolute state path has no business in a pane (the rule _oserror_text already states
        for the frames it serves), and a federated dashboard shows the pane on another machine's screen.
        The errno text and the file name stay, so the user still learns what refused and which session's
        store. The judge-errors row keeps the whole path, which is diagnostic there."""
        self._compacted(A, NOW - 10)
        with _fault_on(self.a_file):
            sent = self._dispatch({"type": "undoClear"})
        errs = [m for m in sent if m.get("type") == "err"]
        self.assertEqual([m.get("sid") for m in errs], [A])
        self.assertNotIn(self.td.name, errs[0]["text"], "the state root is not shown")
        self.assertIn("goals/%s.json" % A, errs[0]["text"], "the file is still named, relative to the state root")
        self.assertIn("Input/output error", errs[0]["text"], "and so is the fault")
        self.assertIn(str(self.a_file), self._rows("store-unreadable")[0]["note"],
                      "the judge-errors row keeps the whole path: it is diagnostic there")

    def test_the_fault_copy_keeps_the_errno_text_and_the_file_name(self):
        """The copy is str(fault) with the state root taken out of EVERY path it names: a failed publish's
        rename names two, the temp file and its destination. A fault with no text at all reads as its type."""
        fault = OSError(errno.EIO, "Input/output error", str(self.a_file))
        self.assertEqual(km._store_fault_copy(fault), "[Errno 5] Input/output error: 'goals/%s.json'" % A)
        tmp = jd.GOALDIR / (A + ".json.tmp.1.2.3")
        fault = OSError(errno.ENOENT, "No such file or directory", str(tmp), None, str(self.a_file))
        self.assertEqual(km._store_fault_copy(fault),
                         "[Errno 2] No such file or directory: 'goals/%s.json.tmp.1.2.3' -> 'goals/%s.json'" % (A, A),
                         "the root leaves both paths, not only the first")
        self.assertEqual(km._store_fault_copy(ValueError()), "ValueError")

    def test_a_sub_goal_drop_the_fault_skipped_answers_with_its_own_account(self):
        """The modal's Drop is sub-task-only, and a sub-goal row renders from the node FLAG alone
        (cleared.jsonl hides TOP cards only) — the very write the fault refused. So the whole-card
        account ("off the board") would be false here: nothing changed, the row is as it was, try again."""
        gid, sub = A + ":g1", A + ":g2"
        st = _store(A, "the parent goal")
        st["nodes"][sub] = dict(st["nodes"][gid], id=sub, parentId=gid, text="the sub-goal to drop")
        st["status"][sub] = "working"
        self._write(A, st)
        row = lambda: next(r for r in self._feed_rows(A)[gid]["tree"] if r["id"] == sub)
        self.assertFalse(row()["cleared"], "premise: the sub row renders un-cleared")
        before = self.a_file.read_bytes()
        with _fault_on(self.a_file):
            sent = self._dispatch({"type": "nodeOverride", "sid": A, "nodeId": sub, "op": "clear"})
        errs = [m for m in sent if m.get("type") == "err"]
        self.assertEqual([m.get("sid") for m in errs], [A])
        self.assertIn("sub-goal was not cleared", errs[0]["title"])
        self.assertIn("Input/output error", errs[0]["text"], "it says why")
        self.assertNotIn(self.td.name, errs[0]["text"], "the file is named relative to the state root")
        self.assertIn("nothing changed there", errs[0]["text"], "what happened: nothing")
        self.assertIn("Try it again", errs[0]["text"], "the true remedy: a retry appends a fresh row and sets the flag")
        self.assertNotIn("copy", errs[0])
        self.assertEqual(self.a_file.read_bytes(), before, "the flag was not written")
        self.assertIn(gid, self._feed_rows(A), "the card stays on the board")
        self.assertFalse(row()["cleared"], "and the sub row still renders un-cleared, as the dialog says")
        sent = self._dispatch({"type": "nodeOverride", "sid": A, "nodeId": sub, "op": "clear"})   # the retry, readable
        self.assertEqual([m for m in sent if m.get("type") == "err"], [], "nothing to refuse")
        self.assertTrue(row()["cleared"], "the retry sets the flag: the row renders cleared")
        self.assertIn(gid, self._feed_rows(A), "the card itself was never cleared")

    def test_a_clear_all_answers_once_per_session_and_reads_true_for_several_cards(self):
        """Clear-all across two cards of one session whose store faults at the flag step (a fault before
        the build would keep A's cards out of the batch itself): ONE refusal for the session, worded for
        any number of cards, and true — the cards are off the board (their cleared.jsonl rows landed), the
        durable flag is not. Through the real dispatcher, which also pins that Clear-all clears at all:
        the handler indexed `items`, a payload key build_feed no longer emits, and raised before
        _clear_all ran — so Clear-all cleared nothing and only a stderr line knew."""
        gid, g3 = A + ":g1", A + ":g3"
        st = _store(A, "the first card")
        st["nodes"][g3] = dict(st["nodes"][gid], id=g3, text="the second card")
        st["status"][g3] = "working"
        self._write(A, st)
        self.assertEqual(set(self._feed_rows(A)), {gid, g3}, "premise: two cards of one session")
        before, orig = self.a_file.read_bytes(), km._mark_nodes_cleared

        def flag_step_under_fault(ids, value, **kw):
            with _fault_on(self.a_file):
                return orig(ids, value, **kw)
        with mock.patch.object(km, "_mark_nodes_cleared", flag_step_under_fault):
            sent = self._dispatch({"type": "clearAll"})
        errs = [m for m in sent if m.get("type") == "err"]
        self.assertEqual([m.get("sid") for m in errs], [A], "one refusal per session, not per card")
        self.assertIn("What you cleared there is off the board", errs[0]["text"], "plural-safe: any number of cards")
        self._assert_clear_refusal(errs[0], before)
        self.assertIn(g3, km._cleared_ids())
        self.assertEqual(self._feed_rows(A), {}, "both cards are off the board, as it says")
        self.assertTrue(jd.load_goals(B)["nodes"][B + ":g1"]["cleared"], "the other session's clear landed in full")

    def _assert_clear_refusal(self, err, before):
        """The whole-card clear dialog says exactly what happened: the card is off the board (its
        cleared.jsonl row landed) but the durable flag was not written into a goals file romp could not read,
        named as goals/<sid>.json, never by its absolute path."""
        self.assertIn("Input/output error", err["text"], "it says why")
        self.assertNotIn(self.td.name, err["text"], "the file is named relative to the state root")
        self.assertIn("goals/%s.json" % A, err["text"])
        self.assertIn("off the board", err["text"], "what did happen")
        self.assertIn("not written", err["text"], "what did not")
        self.assertNotIn("copy", err, "`copy` is the USER'S undelivered text by contract; romp's prose never rides it")
        self.assertIn(A + ":g1", km._cleared_ids(), "the view-level clear holds, as the dialog says")
        self.assertEqual(self.a_file.read_bytes(), before, "and nothing was written to the store, as it says")

    def test_a_card_clear_the_fault_skipped_answers_the_socket_that_asked(self):
        """The per-card Clear (askClear) is the same gesture as Clear-all; it answers the socket on the
        same condition, with the same account."""
        before = self.a_file.read_bytes()
        with _fault_on(self.a_file):
            sent = self._dispatch({"type": "askClear", "itemId": A + ":g1"})
        errs = [m for m in sent if m.get("type") == "err"]
        self.assertEqual([m.get("sid") for m in errs], [A], "one refusal, for the card's session")
        self.assertIn("clear", errs[0]["title"])
        self._assert_clear_refusal(errs[0], before)

    def _compacted(self, sid, t):
        """`sid`'s only card, cleared at `t` and already swept into the archive (the live store holds
        no node for it), the shape a later Undo must reach into."""
        gid = sid + ":g1"
        jd.GOALARCHDIR.mkdir(parents=True, exist_ok=True)
        arch = _store(sid, "the cleared card", cleared=True)
        (jd.GOALARCHDIR / (sid + ".json")).write_text(json.dumps({"rompUuid": sid, "nodes": arch["nodes"],
                                                                   "status": {gid: "cleared"}}))
        live = _store(sid, "unused")
        live["nodes"], live["status"], live["lastNode"] = {}, {}, None
        self._write(sid, live)
        with (jd.STATE / "cleared.jsonl").open("a") as f:
            f.write(json.dumps({"id": gid, "t": t, "op": "clear"}) + "\n")

    def _undo_rows(self):
        return [json.loads(l)["id"] for l in (jd.STATE / "cleared.jsonl").read_text().splitlines()
                if json.loads(l).get("op") == "undo"]

    def test_an_undo_the_fault_skipped_is_retried_by_the_next_undo(self):
        """One Clear-all batch across two sessions; A's store faults at Undo. B's card comes back and
        its undo row is journaled; A's ids are NOT journaled as undone, so they stay the newest batch —
        the next Undo, once the file reads, restores exactly them. (Journaling every id first consumed
        the batch: a second Undo found nothing and A's card stayed in the archive for good.)"""
        for sid in (A, B):
            self._compacted(sid, NOW - 10)
        before = self.a_file.read_bytes()
        with _fault_on(self.a_file):
            sent = self._dispatch({"type": "undoClear"})
        self.assertEqual([m.get("sid") for m in sent if m.get("type") == "err"], [A])
        self.assertEqual(self._undo_rows(), [B + ":g1"], "only the ids whose restore RAN are journaled as undone")
        self.assertEqual(km._cleared_ids(), {A + ":g1": NOW - 10}, "A's ids remain the newest cleared batch")
        b = jd.load_goals(B)
        self.assertFalse(b["nodes"][B + ":g1"]["cleared"], "B's card is back and un-cleared")
        self.assertEqual(json.loads((jd.GOALARCHDIR / (B + ".json")).read_text())["nodes"], {})
        self.assertEqual(self.a_file.read_bytes(), before, "A's store was not written")
        self.assertIn(A + ":g1", json.loads((jd.GOALARCHDIR / (A + ".json")).read_text())["nodes"],
                      "A's archive still holds the card")
        sent = self._dispatch({"type": "undoClear"})     # the fault cleared; the user presses Undo again
        self.assertEqual([m for m in sent if m.get("type") == "err"], [], "nothing to refuse this time")
        a = jd.load_goals(A)
        self.assertIn(A + ":g1", a["nodes"], "A's card is restored into the live store")
        self.assertFalse(a["nodes"][A + ":g1"]["cleared"])
        self.assertEqual(json.loads((jd.GOALARCHDIR / (A + ".json")).read_text())["nodes"], {})
        self.assertEqual(self._undo_rows(), [B + ":g1", A + ":g1"], "and now A's undo row is journaled")
        self.assertEqual(km._cleared_ids(), {}, "the batch is fully undone")

    def _uncompacted(self, sid, t):
        """`sid`'s only card, cleared at `t` but not yet swept: the node sits flag-cleared in the LIVE
        store and the archive holds nothing, so the restore step has no store read to fault on."""
        st = _store(sid, "the cleared card", cleared=True)
        st["status"][sid + ":g1"] = "cleared"
        self._write(sid, st)
        with (jd.STATE / "cleared.jsonl").open("a") as f:
            f.write(json.dumps({"id": sid + ":g1", "t": t, "op": "clear"}) + "\n")

    def test_an_undo_of_an_uncompacted_card_whose_store_faults_stays_owed(self):
        """Nothing archived means the restore step cannot skip the session; the flag step is the first
        read to meet the fault, AFTER the undo row landed. Those ids are re-journaled as cleared, so the
        batch stays owed and the next Undo restores exactly them (journaled-and-consumed before)."""
        for sid in (A, B):
            self._uncompacted(sid, NOW - 10)
        before = self.a_file.read_bytes()
        with _fault_on(self.a_file):
            sent = self._dispatch({"type": "undoClear"})
        self.assertEqual([m.get("sid") for m in sent if m.get("type") == "err"], [A])
        self.assertIn(A + ":g1", km._cleared_ids(), "A's card is still owed its undo")
        self.assertNotIn(B + ":g1", km._cleared_ids())
        self.assertFalse(jd.load_goals(B)["nodes"][B + ":g1"]["cleared"], "B's card is back")
        self.assertEqual(self.a_file.read_bytes(), before, "A's store was not written")
        self.assertEqual(self._feed_rows(A), {}, "A's card stays hidden, as the dialog says")
        sent = self._dispatch({"type": "undoClear"})     # the fault cleared; Undo again
        self.assertEqual([m for m in sent if m.get("type") == "err"], [])
        self.assertFalse(jd.load_goals(A)["nodes"][A + ":g1"]["cleared"], "the next Undo un-clears A's card")
        self.assertEqual(km._cleared_ids(), {})
        self.assertIn(A + ":g1", self._feed_rows(A), "and it is back on the board")

    def test_a_fault_that_first_appears_at_the_flag_step_leaves_the_undo_owed(self):
        """The store read fine for the restore and faults at the flag step: the node is back in the
        live store but flag-cleared, which the board hides exactly like the clear did, and no modal op
        can reach a hidden card. With its undo row already journaled the batch would be consumed; the
        re-journaled clear keeps it owed, and the next Undo un-clears it."""
        for sid in (A, B):
            self._compacted(sid, NOW - 10)
        orig = km._mark_nodes_cleared

        def flag_step_under_fault(ids, value, **kw):
            with _fault_on(self.a_file):
                return orig(ids, value, **kw)
        with mock.patch.object(km, "_mark_nodes_cleared", flag_step_under_fault):
            sent = self._dispatch({"type": "undoClear"})
        self.assertEqual([m.get("sid") for m in sent if m.get("type") == "err"], [A])
        a = jd.load_goals(A)
        self.assertIn(A + ":g1", a["nodes"], "the restore ran: the node is back in the live store...")
        self.assertTrue(a["nodes"][A + ":g1"]["cleared"], "...still flag-cleared (the flag step could not run)")
        self.assertIn(A + ":g1", km._cleared_ids(), "so the id is re-journaled as cleared: the batch stays owed")
        self.assertEqual(self._feed_rows(A), {}, "the card is hidden, as the dialog says")
        self.assertFalse(jd.load_goals(B)["nodes"][B + ":g1"]["cleared"], "B's undo landed in full")
        sent = self._dispatch({"type": "undoClear"})     # readable again
        self.assertEqual([m for m in sent if m.get("type") == "err"], [])
        self.assertFalse(jd.load_goals(A)["nodes"][A + ":g1"]["cleared"], "the next Undo un-clears it")
        self.assertEqual(km._cleared_ids(), {})
        self.assertIn(A + ":g1", self._feed_rows(A))

    def test_a_re_journaled_batch_shares_one_timestamp_so_the_next_undo_restores_all_of_it(self):
        """Two cards of one session cleared in ONE batch, undone while the store faults at the flag step: the
        re-journaled clear rows must carry one shared `t`, because a batch IS its exact timestamp (_cleared_ids
        and _undo_clear key on equality; _clear_all stamps one `t` before its loop for that reason). Stamped
        per row, the two cards split into two one-card batches and each further Undo brought back one card,
        against the promise that the next Undo restores exactly them (review find, 2026-09-08). time.time is
        a counter for the faulting undo, so two stamps taken in one loop can never happen to coincide."""
        gid, g3 = A + ":g1", A + ":g3"
        st = _store(A, "the first card", cleared=True)
        st["nodes"][g3] = dict(st["nodes"][gid], id=g3, text="the second card")
        st["status"] = {gid: "cleared", g3: "cleared"}
        self._write(A, st)
        with (jd.STATE / "cleared.jsonl").open("a") as f:
            for iid in (gid, g3):
                f.write(json.dumps({"id": iid, "t": NOW - 10, "op": "clear"}) + "\n")
        self.assertEqual(set(km._cleared_ids()), {gid, g3}, "premise: one two-card batch")
        with _fault_on(self.a_file), mock.patch.object(km.time, "time", side_effect=itertools.count(NOW)):
            sent = self._dispatch({"type": "undoClear"})
        self.assertEqual([m.get("sid") for m in sent if m.get("type") == "err"], [A])
        cur = km._cleared_ids()
        self.assertEqual(set(cur), {gid, g3}, "both ids are re-journaled as cleared: owed")
        self.assertEqual(len(set(cur.values())), 1, "and they share ONE timestamp: still one batch")
        sent = self._dispatch({"type": "undoClear"})     # the fault cleared; Undo ONCE
        self.assertEqual([m for m in sent if m.get("type") == "err"], [])
        self.assertEqual(km._cleared_ids(), {}, "one Undo restores the whole batch")
        a = jd.load_goals(A)
        self.assertFalse(a["nodes"][gid]["cleared"])
        self.assertFalse(a["nodes"][g3]["cleared"])
        self.assertEqual(set(self._feed_rows(A)), {gid, g3}, "both cards are back on the board")

    def test_a_fault_at_the_save_step_of_a_clear_answers_the_socket_instead_of_dropping_it(self):
        """The store reads at the flag step and faults at its SAVE (save_goals' own strict reads: the file
        went unreadable between the load and the publish). That raise left _clear_all and the dispatcher
        unhandled, and the receive loop re-raises any OSError to the outer handler, which swallows it and
        marks the client dead: the dashboard disconnected without a word. The save now sits behind the
        same boundary as the load: the dispatch RETURNS (so the loop goes on reading this socket), the
        socket hears the same account, and the fault is filed once (review find, 2026-09-08)."""
        before, orig = self.a_file.read_bytes(), jd.save_goals

        def save_under_fault(fsid, store):
            with _fault_on(self.a_file):
                return orig(fsid, store)
        with mock.patch.object(jd, "save_goals", save_under_fault):
            sent = self._dispatch({"type": "askClear", "itemId": A + ":g1"})   # raised OSError before
        errs = [m for m in sent if m.get("type") == "err"]
        self.assertEqual([m.get("sid") for m in errs], [A], "one refusal, for the card's session")
        self.assertIn("clear", errs[0]["title"])
        self._assert_clear_refusal(errs[0], before)
        self.assertEqual([r["fsid"] for r in self._rows("store-unwritable")], [A], "filed once, like a load fault")

    def test_a_publish_that_fails_at_the_undo_answers_and_leaves_the_ids_owed(self):
        """The other save-step shape: the file reads fine and the PUBLISH itself fails (the temp cannot be
        written: a full disk, a directory gone read-only). The undo's restore reached the store and could not
        publish it, so nothing is journaled as undone, the archive keeps the card, the socket hears why, and
        the next Undo, once the publish lands, restores it."""
        for sid in (A, B):
            self._compacted(sid, NOW - 10)
        before, orig = self.a_file.read_bytes(), jd._publish_tmp

        def unwritable_for_a(dirpath, fsid):
            p = orig(dirpath, fsid)
            return Path(self.td.name) / "gone" / p.name if fsid == A and dirpath == jd.GOALDIR else p
        with mock.patch.object(jd, "_publish_tmp", unwritable_for_a):
            sent = self._dispatch({"type": "undoClear"})   # raised FileNotFoundError before
        errs = [m for m in sent if m.get("type") == "err"]
        self.assertEqual([m.get("sid") for m in errs], [A])
        self.assertIn("undo", errs[0]["title"])
        self.assertIn("No such file or directory", errs[0]["text"], "it says why: the publish that failed")
        self.assertNotIn(self.td.name, errs[0]["text"], "the temp it could not write is named relative to the root")
        self.assertIn("not restored", errs[0]["text"])
        self.assertEqual(self._undo_rows(), [B + ":g1"], "only the id whose publish LANDED is journaled as undone")
        self.assertEqual(km._cleared_ids(), {A + ":g1": NOW - 10}, "A's ids remain the newest cleared batch")
        self.assertEqual(self.a_file.read_bytes(), before, "A's store was not written")
        self.assertIn(A + ":g1", json.loads((jd.GOALARCHDIR / (A + ".json")).read_text())["nodes"],
                      "A's archive still holds the card")
        self.assertEqual([r["fsid"] for r in self._rows("store-unwritable")], [A])
        sent = self._dispatch({"type": "undoClear"})     # the publish lands again; Undo
        self.assertEqual([m for m in sent if m.get("type") == "err"], [])
        self.assertIn(A + ":g1", jd.load_goals(A)["nodes"], "A's card is restored")
        self.assertEqual(km._cleared_ids(), {})

    def test_a_gesture_that_reaches_every_session_says_nothing(self):
        (jd.STATE / "cleared.jsonl").write_text(json.dumps({"id": B + ":g1", "t": NOW - 10, "op": "clear"}) + "\n")
        sent = self._dispatch({"type": "undoClear"})
        self.assertEqual([m for m in sent if m.get("type") == "err"], [], "no refusal without a skipped session")


@contextlib.contextmanager
def _nth_append_faults(path, nth):
    """The `nth` APPEND to `path` raises EROFS; the others land. The undo's second clears-log append is its re-journal."""
    orig_open = Path.open
    seen = [0]

    def faulting(p, mode="r", *a, **kw):
        if p == path and "a" in mode:
            seen[0] += 1
            if seen[0] == nth:
                raise OSError(errno.EROFS, "Read-only file system", str(path))
        return orig_open(p, mode, *a, **kw)
    with mock.patch.object(Path, "open", faulting):
        yield


@contextlib.contextmanager
def _append_faults(path):
    """Every APPEND to `path` raises EROFS with the absolute path in its text (a read-only state root); every other open is
    untouched, so the stores still read and the clears log still reads."""
    orig_open = Path.open

    def faulting(p, mode="r", *a, **kw):
        if p == path and "a" in mode:
            raise OSError(errno.EROFS, "Read-only file system", str(path))
        return orig_open(p, mode, *a, **kw)
    with mock.patch.object(Path, "open", faulting):
        yield


class ActsUnderAFailedWrite(_World):
    """The acts a Needs you row offers (Clear, Continue, a typed reply, the modal's Drop and Done, Retry now, a billing pick,
    a notice card's button) when the state write behind them REFUSES (a read-only root): the socket that asked hears it and
    lives, every frame names the file and never the state root, and a delivery that happened is never answered as a failure
    (the second executed review of PR 1935, carried into phase three). Before this a raise out of any of these reached the
    receive loop's OSError arm, which is for the socket's own failures, and every pane's connection was torn down."""

    def setUp(self):
        super().setUp()
        sessions = [{"sid": A, "name": "web", "path": "/nonexistent/%s.jsonl" % A, "anchor": 0, "mtime": 0},
                    {"sid": B, "name": "api", "path": "/nonexistent/%s.jsonl" % B, "anchor": 0, "mtime": 0}]
        self.live = {A: _TM(), B: _TM()}
        self.app = []                                     # what the kernel broadcast to an app (the result frames, the ack)
        for p in (mock.patch.object(km, "_alive_sessions", lambda now, live_map: list(sessions)),
                  mock.patch.object(km, "_warm_fleet_bg", lambda now: None),
                  mock.patch.object(km, "_live_map", lambda: dict(self.live)),
                  mock.patch.object(km, "_send_to_app", lambda app, m: self.app.append((app, m))),
                  mock.patch.object(km, "_name_of", lambda sid: {A: "web", B: "api"}.get(sid)),   # ours: the drive arms run
                  mock.patch.object(km.Sessions, "backend_for", staticmethod(lambda sid: mock.MagicMock()))):
            p.start()
            self.addCleanup(p.stop)
        getattr(km, "_rejournal_owed", {}).clear()       # a past test's owed re-journal must not ride into this one
        (jd.STATE / getattr(km, "OWED_FILE", "cleared-owed.jsonl")).unlink(missing_ok=True)

    def _dispatch(self, msg):
        sent = []
        client = {"app": "feed", "alive": True, "send": lambda s: sent.append(json.loads(s))}
        km.Handler._dispatch_ws(object.__new__(km.Handler), msg, client)
        return sent

    def _flag(self, sid, nid):
        return bool(jd.load_goals(sid)["nodes"][nid].get("cleared"))

    def _drops(self):
        return [m for app, m in self.app if app == "chat" and m.get("type") == "dropCitation"]

    # ── the clears log (Clear, Clear on a header, Clear all, Drop, Undo) ──────────────────────────────────────────────
    def test_a_clear_whose_ledger_write_refuses_answers_the_socket_and_changes_nothing(self):
        gid = A + ":g1"
        with _append_faults(jd.STATE / "cleared.jsonl"):
            sent = self._dispatch({"type": "askClear", "itemId": gid})   # raised OSError out of the handler before this
        errs = [m for m in sent if m.get("type") == "err"]
        self.assertEqual(len(errs), 1, "one refusal on the socket that asked")
        self.assertEqual(errs[0]["title"], "That clear did not land")
        self.assertIn("clears log", errs[0]["text"])
        self.assertIn("Read-only file system", errs[0]["text"], "and it says why")
        self.assertIn("nothing was cleared", errs[0]["text"], "and what did not happen")
        self.assertNotIn(str(jd.STATE), errs[0]["text"], "the dialog names no state root")
        self.assertFalse((jd.STATE / "cleared.jsonl").exists(), "no row landed")
        self.assertFalse(self._flag(A, gid), "no node was flagged: the clear did not happen at all")
        # the frame names the REQUEST (the second review of PR 1967): the feed releases the click's suppression of that card and repaints
        # it, the chat re-arms the row's buttons; and the composer's citation stays, since nothing was cleared
        self.assertEqual((errs[0]["op"], errs[0]["itemId"], errs[0]["itemIds"]), ("askClear", gid, [gid]))
        self.assertEqual(self._drops(), [], "no dropCitation after a refused clear")
        sent = self._dispatch({"type": "askClear", "itemId": gid})   # the retry, once the log writes again
        self.assertEqual([m for m in sent if m.get("type") == "err"], [])
        self.assertTrue(self._flag(A, gid))
        self.assertIn(gid, km._cleared_ids())
        self.assertEqual([d["itemId"] for d in self._drops()], [gid], "the landed clear drops the citation, once")

    def test_a_clear_all_and_a_sub_goal_drop_answer_the_same_way(self):
        with _append_faults(jd.STATE / "cleared.jsonl"):
            many = self._dispatch({"type": "askClearMany", "itemIds": [A + ":g1", B + ":g1"]})
            drop = self._dispatch({"type": "nodeOverride", "sid": A, "nodeId": A + ":g1", "op": "clear"})
        self.assertEqual([m["title"] for m in many if m.get("type") == "err"], ["That clear did not land"],
                         "one dialog for the whole batch: the log is one file")
        self.assertEqual([m["title"] for m in drop if m.get("type") == "err"], ["That sub-goal was not cleared"])
        self.assertIn("the row is as it was", [m for m in drop if m.get("type") == "err"][0]["text"])
        self.assertFalse((jd.STATE / "cleared.jsonl").exists())
        self.assertFalse(self._flag(A, A + ":g1") or self._flag(B, B + ":g1"))
        m_err = [m for m in many if m.get("type") == "err"][0]; d_err = [m for m in drop if m.get("type") == "err"][0]
        self.assertEqual((m_err["op"], m_err["itemIds"]), ("askClearMany", [A + ":g1", B + ":g1"]), "the batch's ids ride the refusal")
        self.assertEqual((d_err["op"], d_err["itemIds"]), ("nodeOverride", [A + ":g1"]))
        self.assertEqual(self._drops(), [], "no dropCitation after either refused clear")

    def test_a_clear_all_whose_ledger_write_refuses_names_the_batch_and_keeps_every_citation(self):
        """The fourth clear arm (the third review of PR 1967: left out of the three's fix): the refusal names the request and the
        whole batch, and dropCitationsAll is not sent, since nothing was cleared."""
        with _append_faults(jd.STATE / "cleared.jsonl"):
            sent = self._dispatch({"type": "clearAll"})
        errs = [m for m in sent if m.get("type") == "err"]
        self.assertEqual([m["title"] for m in errs], ["That clear did not land"])
        self.assertEqual(errs[0]["op"], "clearAll")
        self.assertEqual(sorted(errs[0]["itemIds"]), sorted([A + ":g1", B + ":g1"]), "the whole board's batch rides the refusal")
        self.assertEqual([m for app, m in self.app if m.get("type") == "dropCitationsAll"], [], "every composer chip stays")
        self.assertFalse(self._flag(A, A + ":g1") or self._flag(B, B + ":g1"))
        sent = self._dispatch({"type": "clearAll"})         # the retry lands: one dropCitationsAll
        self.assertEqual([m for m in sent if m.get("type") == "err"], [])
        self.assertEqual(len([m for app, m in self.app if m.get("type") == "dropCitationsAll"]), 1)

    def test_an_undo_refusal_names_the_batch_it_reached_for(self):
        """The feed restores the batch optimistically on the click; a refusal must name it so the restore is reverted (the third
        review of PR 1967)."""
        self._dispatch({"type": "askClearMany", "itemIds": [A + ":g1", B + ":g1"]})
        with _append_faults(jd.STATE / "cleared.jsonl"):
            sent = self._dispatch({"type": "undoClear"})
        errs = [m for m in sent if m.get("type") == "err"]
        self.assertEqual([m["title"] for m in errs], ["That undo did not land"])
        self.assertEqual((errs[0]["op"], sorted(errs[0]["itemIds"])), ("undoClear", sorted([A + ":g1", B + ":g1"])))

    def test_the_owed_re_journal_survives_a_restart_beside_the_log_and_the_dialog_states_the_limit_when_that_refuses_too(self):
        """The two-fault shape, then the kernel's memory emptied (a restart): the owed ids are read back from the file beside the
        log and re-journaled first, so the next Undo still brings the card back (the third review of PR 1967: a module dict alone
        dropped the owing silently). When the file refuses too, the dialog says the owing lives in memory alone."""
        self._dispatch({"type": "askClearMany", "itemIds": [A + ":g1", B + ":g1"]})
        orig = km._mark_nodes_cleared

        def flag_step_under_fault(ids, value, **kw):
            with _fault_on(self.b_file):
                return orig(ids, value, **kw)
        with mock.patch.object(km, "_mark_nodes_cleared", flag_step_under_fault), _nth_append_faults(jd.STATE / "cleared.jsonl", 2):
            sent = self._dispatch({"type": "undoClear"})
        rj = next(m for m in sent if m.get("type") == "err" and m["title"] == "That undo did not fully land")
        self.assertIn("saved a note of them beside its records, so a restart keeps it", rj["text"])
        self.assertIn("ahead of the last clear", rj["text"], "the reorder is named")
        owed = [json.loads(l)["id"] for l in (jd.STATE / km.OWED_FILE).read_text().splitlines() if l.strip()]
        self.assertEqual(owed, [B + ":g1"], "the owing is on disk")
        km._rejournal_owed.clear()                          # the restart: memory empty, the file not
        sent = self._dispatch({"type": "undoClear"})
        self.assertEqual([m for m in sent if m.get("type") == "err"], [])
        self.assertFalse(self._flag(B, B + ":g1"), "the next Undo after the restart brings B back")
        self.assertEqual((jd.STATE / km.OWED_FILE).read_text(), "", "and the owing is settled")
        # the file beside the log refusing too: the limit, stated
        self._dispatch({"type": "askClearMany", "itemIds": [A + ":g1", B + ":g1"]})
        with mock.patch.object(km, "_mark_nodes_cleared", flag_step_under_fault), _nth_append_faults(jd.STATE / "cleared.jsonl", 2), \
             _append_faults(jd.STATE / km.OWED_FILE):
            sent = self._dispatch({"type": "undoClear"})
        rj = next(m for m in sent if m.get("type") == "err" and m["title"] == "That undo did not fully land")
        self.assertIn("only this running romp remembers", rj["text"])
        self.assertIn("a restart before it can write again loses that", rj["text"], "the limit is stated where the promise is made")
        self.assertEqual(km._rejournal_owed, {B + ":g1": None})

    def test_an_undo_whose_re_journal_refuses_says_so_and_the_next_undo_re_journals_first(self):
        """Two cards cleared in one batch; the undo's rows land, one store faults at its flag step, and the clears log refuses the
        re-journal that keeps that card owed: the card reads undone with its flag standing, which no later Undo reaches by the
        ledger alone. The refusal has its own account (LEDGER_KEY's says nothing was recorded, false here), the ids are owed in
        memory, and the next Undo writes the re-journal FIRST and restores the card in the same gesture."""
        self._dispatch({"type": "askClearMany", "itemIds": [A + ":g1", B + ":g1"]})
        self.assertTrue(self._flag(A, A + ":g1") and self._flag(B, B + ":g1"))
        orig = km._mark_nodes_cleared

        def flag_step_under_fault(ids, value, **kw):
            with _fault_on(self.b_file):
                return orig(ids, value, **kw)
        with mock.patch.object(km, "_mark_nodes_cleared", flag_step_under_fault), _nth_append_faults(jd.STATE / "cleared.jsonl", 2):
            sent = self._dispatch({"type": "undoClear"})    # append 1: the undo rows land; append 2: the re-journal refused
        errs = [m for m in sent if m.get("type") == "err"]
        self.assertEqual(sorted(m["title"] for m in errs), ["That undo did not fully land", "That undo did not land for api"],
                         "the store's own account and the re-journal's, apart: %r" % errs)
        rj = next(m for m in errs if m["title"] == "That undo did not fully land")
        self.assertIn("Press Undo again once romp can write and they come back, ahead of the last clear", rj["text"], "the remedy is the next Undo, which writes the re-journal first, and the reorder is named")
        self.assertNotIn("was not recorded", rj["text"], "the undo rows DID land: LEDGER_KEY's wording would be false")
        self.assertFalse(self._flag(A, A + ":g1"), "A's undo landed in full")
        self.assertTrue(self._flag(B, B + ":g1"), "B sits flag-cleared: the flag step could not run")
        self.assertEqual(km._cleared_ids(), {}, "and the ledger reads B as undone: the ledger alone reaches it no more")
        self.assertEqual(self._feed_rows(B), {}, "hidden, as the dialog says")
        sent = self._dispatch({"type": "undoClear"})        # writable again: the re-journal goes first, then the restore
        self.assertEqual([m for m in sent if m.get("type") == "err"], [])
        self.assertFalse(self._flag(B, B + ":g1"), "the next Undo brings B back")
        self.assertEqual(km._cleared_ids(), {})
        self.assertIn(B + ":g1", self._feed_rows(B))
        self.assertEqual(km._rejournal_owed, {}, "nothing owed once the re-journal landed")

    def _feed_rows(self, sid):
        return {a["itemId"]: a for a in km.build_feed(NOW, self.live)["asks"] if a["itemId"].startswith(sid)}

    def test_an_undo_whose_ledger_write_refuses_stays_owed_and_the_next_undo_restores(self):
        gid = A + ":g1"
        self._dispatch({"type": "askClear", "itemId": gid})              # a clear that landed
        self.assertTrue(self._flag(A, gid))
        with _append_faults(jd.STATE / "cleared.jsonl"):
            sent = self._dispatch({"type": "undoClear"})
        errs = [m for m in sent if m.get("type") == "err"]
        self.assertEqual([m["title"] for m in errs], ["That undo did not land"])
        self.assertIn("press Undo again", errs[0]["text"], "the one true remedy")
        self.assertNotIn(str(jd.STATE), errs[0]["text"])
        self.assertTrue(self._flag(A, gid), "still hidden: nothing was journaled")
        self.assertIn(gid, km._cleared_ids(), "the batch stays the newest, so the next Undo retries exactly it")
        sent = self._dispatch({"type": "undoClear"})
        self.assertEqual([m for m in sent if m.get("type") == "err"], [])
        self.assertFalse(self._flag(A, gid), "restored")
        self.assertEqual(km._cleared_ids(), {})

    # ── the result frames name no state root ──────────────────────────────────────────────────────────────────────────
    def test_a_resolve_a_redistill_and_a_notice_action_that_raise_name_no_state_root(self):
        boom = OSError(errno.EROFS, "Read-only file system", str(self.a_file))

        def raiser(*a, **k):
            raise boom
        with mock.patch.object(km, "_resolve_node", raiser):
            self._dispatch({"type": "nodeOverride", "sid": A, "nodeId": A + ":g1", "op": "resolve"})
        with mock.patch.object(jd, "append_override", raiser):
            self._dispatch({"type": "redistill", "sid": A, "itemId": A + ":g1"})
        with mock.patch.object(km, "_notice_action", raiser):
            sent = self._dispatch({"type": "noticeAction", "itemId": "notice:%s:k:1" % A, "kind": "send", "body": {}})
        frames = [m for app, m in self.app if m.get("type") in ("nodeOverrideResult", "redistillResult")]
        done = [m for m in sent if m.get("type") == "noticeActionDone"]
        self.assertEqual([m["type"] for m in frames], ["nodeOverrideResult", "redistillResult"])
        self.assertEqual(len(done), 1)
        for m in frames + done:
            self.assertFalse(m["ok"])
            self.assertIn("Read-only file system", m["error"], "the errno text stays")
            self.assertIn("goals/" + A + ".json", m["error"], "and the file, relative to the state root")
            self.assertNotIn(str(jd.STATE), m["error"], "a frame a federated pane may show names no state root")
        self.assertNotIn("held", done[0], "a refusal is not a held delivery: the key rides only an answer whose delivery landed and whose dismissal refused")
        # a delivery whose dismissal refused: ok, with the card held (the pane keeps it and leaves the button spent)
        with mock.patch.object(km, "_notice_action", lambda *a, **k: (True, "the card could not be dismissed (x)")):
            sent = self._dispatch({"type": "noticeAction", "itemId": "notice:%s:k:1" % A, "kind": "send", "body": {}})
        done = [m for m in sent if m.get("type") == "noticeActionDone"]
        self.assertEqual((done[0]["ok"], done[0]["held"]), (True, True))

    # ── Continue, a typed reply, the modal's Check status; a billing pick; Retry now ───────────────────────────────────
    def test_a_reply_whose_send_write_refuses_is_refused_on_the_frame_the_arm_has(self):
        boom = OSError(errno.EROFS, "Read-only file system", str(jd.STATE / "pending-ops" / (A + ".json")))
        with mock.patch.object(km, "_send_or_park", mock.Mock(side_effect=boom)):
            sent = self._dispatch({"type": "askFollowUp", "itemId": A + ":g1", "text": "and the fix?"})
        errs = [m for m in sent if m.get("type") == "err"]
        self.assertEqual(len(errs), 1, "the refusal dialog the arm already had, not a torn socket")
        self.assertEqual((errs[0]["op"], errs[0]["itemId"]), ("askFollowUp", A + ":g1"), "the card's own latch releases")
        self.assertIn("could not write its state", errs[0]["text"])
        self.assertIn("pending-ops/" + A + ".json", errs[0]["text"])
        self.assertNotIn(str(jd.STATE), errs[0]["text"])
        self.assertEqual(errs[0]["copy"], "and the fix?", "the typed text rides back")
        self.assertIn("saved verbatim in undelivered.jsonl", errs[0]["text"], "the append landed, so the dialog may say so")
        self.assertTrue((jd.STATE / "undelivered.jsonl").exists())
        self.assertEqual([m for app, m in self.app if m.get("type") == "cardMoveAck"], [], "no move was predicted, none is answered")
        # the undelivered append refusing too (the whole root read-only): the dialog says so and names the Copy button as the one record
        with mock.patch.object(km, "_send_or_park", mock.Mock(side_effect=boom)), _append_faults(jd.STATE / "undelivered.jsonl"):
            sent = self._dispatch({"type": "askFollowUp", "itemId": A + ":g1", "text": "still here?"})
        errs = [m for m in sent if m.get("type") == "err"]
        self.assertEqual(len(errs), 1)
        self.assertIn("could not write undelivered.jsonl either", errs[0]["text"])
        self.assertNotIn("saved verbatim", errs[0]["text"], "no claim of a file that was not written")
        self.assertNotIn(str(jd.STATE), errs[0]["text"])
        self.assertEqual(errs[0]["copy"], "still here?", "the copy is the record")

    def test_a_reply_whose_reopen_write_refuses_acks_with_the_cause_instead_of_calling_the_card_gone(self):
        boom = OSError(errno.EROFS, "Read-only file system", str(self.a_file))
        with mock.patch.object(km, "_send_or_park", lambda *a, **k: True), \
             mock.patch.object(jd, "optimistic_followup", mock.Mock(side_effect=boom)):
            sent = self._dispatch({"type": "askFollowUp", "itemId": A + ":g1", "cont": True})
        acks = [m for app, m in self.app if m.get("type") == "cardMoveAck"]
        self.assertEqual(len(acks), 1)
        self.assertFalse(acks[0]["ok"])
        self.assertIn("goals/" + A + ".json", acks[0]["why"], "the cause rides the ack")
        self.assertNotIn(str(jd.STATE), acks[0]["why"])
        self.assertEqual([m for m in sent if m.get("type") == "err"], [], "the words went out: no refusal dialog")

    def test_a_billing_pick_and_a_manual_retry_whose_write_refuses_are_said_on_their_frames(self):
        boom = OSError(errno.EROFS, "Read-only file system", str(jd.STATE / "pending-ops" / (A + ".json")))
        with mock.patch.object(km, "_set_auth_or_park", mock.Mock(side_effect=boom)):
            sent = self._dispatch({"type": "setAuth", "id": A, "value": "login"})
        warns = [m for m in sent if m.get("type") == "warn"]
        self.assertEqual(len(warns), 1)
        self.assertIn("could not write its state", warns[0]["text"])
        self.assertNotIn(str(jd.STATE), warns[0]["text"])
        with mock.patch.object(km, "_fire_api_retry", mock.Mock(side_effect=boom)):
            sent = self._dispatch({"type": "apiRetry", "id": A, "manual": True})
        refused = [m for m in sent if m.get("type") == "retryRefused"]
        self.assertEqual(len(refused), 1, "the manual Retry hears it on the frame that releases its latch")
        self.assertEqual(refused[0]["sid"], A)
        self.assertIn("could not write its state", refused[0]["text"])
        self.assertNotIn(str(jd.STATE), refused[0]["text"])


if __name__ == "__main__":
    unittest.main()
