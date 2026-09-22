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
import io
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
        # the owed-note globals, all of them, for every world (the second contributor's review, 2026-09-22): a past test's owing, settled ids,
        # memory-only mark or once-per-life read must not ride into this one
        km._rejournal_owed.clear(); km._owed_settled.clear(); km._owed_mem_only[0] = False
        getattr(km, "_owed_note_read", [False])[0] = False   # (tolerant of a kernel without the once-per-life read: the red-first run at the round's base)
        getattr(km, "_owed_read_fault", [""])[0] = ""        # the note read's episode memo (round fourteen)
        getattr(km, "_cleared_read_fault", [""])[0] = ""     # the clears-log read's episode memo (PR 2025)
        (jd.STATE / km.OWED_FILE).unlink(missing_ok=True)

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
        # (the owed globals reset in _World.setUp for every class: the second contributor's review found _owed_mem_only unreset here)

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
        self.assertTrue(any("the note's append refused" in r.get("note", "") for r in self._rows("owed-note")), "the append arm's durable record (the round-thirteen verifier): %r" % self._rows("owed-note"))

    def test_the_press_after_the_two_fault_undo_with_the_log_still_refusing_names_what_the_feed_restored(self):
        """The double-fault window's other side (the manager's read of round three): owed ids present, a later clear landed, then
        Undo with the log refusing again. The re-journal-first write refuses, and the refusal must name the newest clear (the batch
        the feed restored optimistically on the click) plus the owed ids, under an account for its own case, so the feed reverts the
        phantom; before this the function returned before its batch was filled and the frame named nothing."""
        self._dispatch({"type": "askClearMany", "itemIds": [A + ":g1", B + ":g1"]})
        orig = km._mark_nodes_cleared

        def flag_step_under_fault(ids, value, **kw):
            with _fault_on(self.b_file):
                return orig(ids, value, **kw)
        with mock.patch.object(km, "_mark_nodes_cleared", flag_step_under_fault), _nth_append_faults(jd.STATE / "cleared.jsonl", 2):
            self._dispatch({"type": "undoClear"})           # the two-fault shape: A back, B owed
        self.assertEqual(km._rejournal_owed, {B + ":g1": None})
        self._dispatch({"type": "askClear", "itemId": A + ":g1"})   # a later clear lands: the newest batch, the one the feed's Undo would restore
        with _append_faults(jd.STATE / "cleared.jsonl"):
            sent = self._dispatch({"type": "undoClear"})    # the re-journal-first write refuses again
        errs = [m for m in sent if m.get("type") == "err"]
        self.assertEqual([m["title"] for m in errs], ["That undo did not land"])
        self.assertIn("Nothing changed", errs[0]["text"], "the account for its own case: nothing new was marked undone this press")
        self.assertNotIn("were marked undone", errs[0]["text"], "not the first fault's words")
        self.assertNotIn("ok", errs[0], "a refusal carries no `ok`")
        self.assertEqual((errs[0]["op"], sorted(errs[0]["itemIds"])), ("undoClear", sorted([A + ":g1", B + ":g1"])),
                         "the newest clear the feed restored on the click, plus the owed card")
        self.assertTrue(self._flag(A, A + ":g1"), "the last clear stands")
        self.assertTrue(self._flag(B, B + ":g1"), "the owed card stays hidden")
        self.assertEqual(km._rejournal_owed, {B + ":g1": None}, "still owed")
        sent = self._dispatch({"type": "undoClear"})        # writable again: the owed card first, then the newest clear on the press after
        errs = [m for m in sent if m.get("type") == "err"]
        self.assertEqual([m["title"] for m in errs], ["Undo brought back earlier cards first"], "the reorder is told (the third review): %r" % errs)
        self.assertEqual(errs[0]["itemIds"], [A + ":g1"], "naming the batch the feed restored on the click, not restored this press")
        self.assertIn("press Undo again for it", errs[0]["text"])
        self.assertIs(errs[0].get("ok"), True, "information, not a refusal: the feed shows the dialog and files no bell entry (the round-four verifier)")
        self.assertFalse(self._flag(B, B + ":g1"), "the owed card comes back ahead of the last clear (the reorder the dialog names)")
        self.assertTrue(self._flag(A, A + ":g1"), "the last clear stands")
        sent = self._dispatch({"type": "undoClear"})
        self.assertEqual([m for m in sent if m.get("type") == "err"], [])
        self.assertFalse(self._flag(A, A + ":g1"), "the press after brings the last clear back")

    def test_a_partial_undo_or_clear_names_only_the_faulting_sessions_ids_and_the_landed_card_stays(self):
        """The third executed review's high: every account's frame carried the whole batch, so the feed reverted cards whose act
        had landed. A partial undo (one store faulting at its flag step) names that session's card alone, and the restored card is on
        the board; a partial clear (one store faulting at its save) names that session's card alone."""
        self._dispatch({"type": "askClearMany", "itemIds": [A + ":g1", B + ":g1"]})
        orig = km._mark_nodes_cleared

        def flag_step_under_fault(ids, value, **kw):
            with _fault_on(self.b_file):
                return orig(ids, value, **kw)
        with mock.patch.object(km, "_mark_nodes_cleared", flag_step_under_fault):
            sent = self._dispatch({"type": "undoClear"})
        errs = [m for m in sent if m.get("type") == "err"]
        self.assertEqual([(m["title"], m["itemIds"]) for m in errs], [("That undo did not land for api", [B + ":g1"])],
                         "the faulting session's frame names its own card alone")
        self.assertFalse(self._flag(A, A + ":g1")); self.assertIn(A + ":g1", self._feed_rows(A), "the landed card is on the board")
        # a partial clear: B's store refuses its save; the ledger rows landed for both
        self._dispatch({"type": "undoClear"})               # B back too (its re-journal kept it owed)
        with _fault_on(self.b_file):
            sent = self._dispatch({"type": "askClearMany", "itemIds": [A + ":g1", B + ":g1"]})
        errs = [m for m in sent if m.get("type") == "err"]
        self.assertEqual([(m["title"], m["itemIds"], m["sid"], m["op"]) for m in errs], [("That clear did not fully land for api", [], B, "askClearMany")],
                         "the clear's per-session account names NO card: the ledger took the clear, nothing is undelivered (the round-three verifier); the frame keeps the session for the latches")
        self.assertTrue(self._flag(A, A + ":g1"), "A's clear landed in full")
        self.assertIn(B + ":g1", km._cleared_ids(), "B's card is off the board too: the ledger row landed")

    def test_the_owed_notes_faults_are_said_and_a_stale_row_is_not_re_journaled(self):
        """The third review's low: the note's truncate passed on OSError, so every later Undo re-journaled the stale id; its read
        passed on every OSError, so an unreadable note read as nothing owed. Both have an account now, and the settled ids are not
        owed again while the rewrite is refused."""
        self._dispatch({"type": "askClearMany", "itemIds": [A + ":g1", B + ":g1"]})
        orig = km._mark_nodes_cleared

        def flag_step_under_fault(ids, value, **kw):
            with _fault_on(self.b_file):
                return orig(ids, value, **kw)
        with mock.patch.object(km, "_mark_nodes_cleared", flag_step_under_fault), _nth_append_faults(jd.STATE / "cleared.jsonl", 2):
            self._dispatch({"type": "undoClear"})           # B owed, on disk
        owed_file = jd.STATE / km.OWED_FILE
        orig_write = Path.write_text

        def refusing_write(p, *a, **kw):
            if p.name.startswith(owed_file.name) and p.name != owed_file.name:   # the atomic temp alone: a plain write on the final name goes through, so the atomic switch is guarded (the round-thirteen verifier)
                raise OSError(errno.EROFS, "Read-only file system", str(p))
            return orig_write(p, *a, **kw)
        with mock.patch.object(Path, "write_text", refusing_write):
            sent = self._dispatch({"type": "undoClear"})    # the re-journal lands; the note's rewrite refuses
        titles = [m["title"] for m in sent if m.get("type") == "err"]
        self.assertIn("romp could not update its note of earlier owed cards", titles, "the refused rewrite has an account: %r" % titles)
        self.assertTrue(any("the note's rewrite refused" in r.get("note", "") for r in self._rows("owed-note")), "the rewrite arm's durable record (the round-thirteen verifier): %r" % self._rows("owed-note"))
        self.assertFalse(self._flag(B, B + ":g1"), "B came back")
        self.assertIn(B + ":g1", [json.loads(l)["id"] for l in owed_file.read_text().splitlines() if l.strip()], "the stale row is still on disk")
        with mock.patch.object(Path, "write_text", refusing_write):
            self._dispatch({"type": "askClear", "itemId": A + ":g1"})
            sent = self._dispatch({"type": "undoClear"})    # the note still carries the settled id and its QUIET rewrite refuses again: said (round thirteen: its return was discarded)
        self.assertIn("romp could not update its note of earlier owed cards", [m["title"] for m in sent if m.get("type") == "err"], "the quiet rewrite's refusal has the owed-write account: %r" % sent)
        self.assertFalse(self._flag(A, A + ":g1"), "and the undo went ahead")
        self._dispatch({"type": "askClear", "itemId": A + ":g1"})   # the last clear
        sent = self._dispatch({"type": "undoClear"})
        self.assertEqual([m for m in sent if m.get("type") == "err"], [], "no stale re-journal: the settled id is not owed again")
        self.assertFalse(self._flag(A, A + ":g1"), "the next Undo restores the last clear, not the stale id")
        self.assertEqual(owed_file.read_text(), "", "and the note is rewritten once the file writes")
        # an unreadable note: said, and the undo goes ahead
        self._dispatch({"type": "askClear", "itemId": A + ":g1"})
        owed_file.write_text("")
        orig_read = Path.read_text

        def refusing_read(p, *a, **kw):
            if p == owed_file:
                raise OSError(errno.EACCES, "Permission denied", str(p))
            return orig_read(p, *a, **kw)
        with mock.patch.object(Path, "read_text", refusing_read):
            sent = self._dispatch({"type": "undoClear"})
        titles = [m["title"] for m in sent if m.get("type") == "err"]
        self.assertEqual(titles, ["romp could not read its note of earlier owed cards"], "an unreadable note is said, a missing one is not")
        self.assertFalse(self._flag(A, A + ":g1"), "and the undo went ahead")

    def _two_fault_undo_leaves_b_owed(self):
        """Two cards cleared in one batch, then Undo with B's store faulting at its flag step and the log refusing the re-journal: A back,
        B owed (in memory and in the note beside the log). Returns the faulting flag step for a later press."""
        self._dispatch({"type": "askClearMany", "itemIds": [A + ":g1", B + ":g1"]})
        orig = km._mark_nodes_cleared

        def flag_step_under_fault(ids, value, **kw):
            with _fault_on(self.b_file):
                return orig(ids, value, **kw)
        with mock.patch.object(km, "_mark_nodes_cleared", flag_step_under_fault), _nth_append_faults(jd.STATE / "cleared.jsonl", 2):
            self._dispatch({"type": "undoClear"})
        self.assertEqual(km._rejournal_owed, {B + ":g1": None})
        return flag_step_under_fault

    def test_the_reorder_account_is_filed_after_the_owed_batchs_flag_step_and_says_whether_they_came_back(self):
        """The fourth review's first low: filed when the re-journal landed, the reorder frame said "brought back" while the owed store was
        refusing, and both frames read cleared. Filed after the flag step, its words say the owed cards did not come back, beside the owed
        store's own account; with the store writable at that press the words say they did. Either way it is information (`ok`)."""
        under_fault = self._two_fault_undo_leaves_b_owed()
        self._dispatch({"type": "askClear", "itemId": A + ":g1"})   # the last clear: what the feed's Undo restores on the click
        with mock.patch.object(km, "_mark_nodes_cleared", under_fault):
            sent = self._dispatch({"type": "undoClear"})    # the re-journal lands; B's store refuses its flag step again
        errs = [m for m in sent if m.get("type") == "err"]
        self.assertEqual([m["title"] for m in errs], ["That undo did not land for api", "Undo went to earlier cards first"],
                         "the owed store's account, then the reorder worded for what happened: %r" % errs)
        self.assertEqual((errs[1]["itemIds"], errs[1].get("ok"), "ok" in errs[0]), ([A + ":g1"], True, False))
        self.assertNotIn("brought them back", errs[1]["text"], "no restore is claimed while the owed store refuses")
        self.assertIn("Once that session's goals file can be read and written again, one Undo brings them back and the next the last clear.", errs[1]["text"], "the words name the condition, not a press count (the sixth executed review; the round-eight verifier)")
        self.assertEqual(errs[1]["owedIds"], [B + ":g1"], "and the frame names the owed ids: the feed holds an entry for them above the last clear's")
        self.assertTrue(self._flag(B, B + ":g1"), "B still hidden"); self.assertTrue(self._flag(A, A + ":g1"), "the last clear stands")
        sent = self._dispatch({"type": "undoClear"})        # B's store writable: its re-journal row is the newest batch, so it comes back, quietly
        self.assertEqual([m for m in sent if m.get("type") == "err"], [])
        self.assertFalse(self._flag(B, B + ":g1")); self.assertTrue(self._flag(A, A + ":g1"))
        sent = self._dispatch({"type": "undoClear"})        # the press after that: the last clear, as the frame said
        self.assertEqual([m for m in sent if m.get("type") == "err"], []); self.assertFalse(self._flag(A, A + ":g1"))
        self._two_fault_undo_leaves_b_owed()                # the same shape with B's store writable at the re-journal-first press
        self._dispatch({"type": "askClear", "itemId": A + ":g1"})
        sent = self._dispatch({"type": "undoClear"})
        errs = [m for m in sent if m.get("type") == "err"]
        self.assertEqual([(m["title"], m["itemIds"], m.get("ok")) for m in errs], [("Undo brought back earlier cards first", [A + ":g1"], True)], "%r" % errs)
        self.assertNotIn("owedIds", errs[0], "the owed cards came back: nothing stands above the last clear's entry")
        self.assertFalse(self._flag(B, B + ":g1"), "the owed card came back"); self.assertTrue(self._flag(A, A + ":g1"), "the last clear stands")

    def test_the_reorder_is_filed_when_the_undo_rows_refuse_after_the_re_journal_landed_and_names_the_owed_ids(self):
        """The sixth executed review's second low: the reorder frame's undo-rows-refused exit had no test. Owed B, A cleared, then Undo with
        the log taking the re-journal-first rows and refusing the undo rows: the ledger's account first (nothing restored), then the reorder,
        worded for what happens next (B's re-journal is the newest batch: the next Undo is B's, the last clear the press after), naming A as
        not restored and B as owed. The presses after do as the frame says, quietly."""
        self._two_fault_undo_leaves_b_owed()
        self._dispatch({"type": "askClear", "itemId": A + ":g1"})
        with _nth_append_faults(jd.STATE / "cleared.jsonl", 2):
            sent = self._dispatch({"type": "undoClear"})    # append 1: the re-journal-first rows land; append 2: the undo rows refused
        errs = [m for m in sent if m.get("type") == "err"]
        self.assertEqual([m["title"] for m in errs], ["That undo did not land", "Undo went to earlier cards first"], "%r" % errs)
        self.assertEqual((errs[1]["itemIds"], errs[1].get("ok"), errs[1]["owedIds"]), ([A + ":g1"], True, [B + ":g1"]))
        self.assertIn("one Undo brings them back and the next the last clear", errs[1]["text"])
        self.assertTrue(self._flag(A, A + ":g1") and self._flag(B, B + ":g1"), "nothing restored this press")
        sent = self._dispatch({"type": "undoClear"})        # the next Undo: B, quietly
        self.assertEqual([m for m in sent if m.get("type") == "err"], []); self.assertFalse(self._flag(B, B + ":g1")); self.assertTrue(self._flag(A, A + ":g1"))
        sent = self._dispatch({"type": "undoClear"})        # the press after: the last clear
        self.assertEqual([m for m in sent if m.get("type") == "err"], []); self.assertFalse(self._flag(A, A + ":g1"))

    def test_the_owed_write_account_claims_nothing_about_the_restore_when_the_owed_store_refuses_too(self):
        """The sixth executed review's first low: filed at the rewrite, before the flag step, the account said "The owed cards came back", and
        with the owed store refusing on the same press three frames contradicted each other. It says what it knows: the undo went ahead and
        the note could not be rewritten; the store's account and the reorder frame say the rest."""
        under_fault = self._two_fault_undo_leaves_b_owed()
        self._dispatch({"type": "askClear", "itemId": A + ":g1"})
        owed_file = jd.STATE / km.OWED_FILE
        orig_write = Path.write_text

        def refusing_write(p, *a, **kw):
            if p.name.startswith(owed_file.name) and p.name != owed_file.name:   # the atomic temp alone: a plain write on the final name goes through, so the atomic switch is guarded (the round-thirteen verifier)
                raise OSError(errno.EROFS, "Read-only file system", str(p))
            return orig_write(p, *a, **kw)
        with mock.patch.object(Path, "write_text", refusing_write), mock.patch.object(km, "_mark_nodes_cleared", under_fault):
            sent = self._dispatch({"type": "undoClear"})    # the re-journal lands; the note's rewrite refuses; B's store refuses its flag step
        errs = [m for m in sent if m.get("type") == "err"]
        self.assertEqual([m["title"] for m in errs], ["romp could not update its note of earlier owed cards", "That undo did not land for api", "Undo went to earlier cards first"], "%r" % errs)
        self.assertNotIn("came back", errs[0]["text"], "no restore is claimed by the note's account")
        self.assertIn("could not rewrite the note", errs[0]["text"])
        self.assertTrue(self._flag(B, B + ":g1"), "B still flag-cleared, as the other two frames say")

    def _two_card_store_for_a(self):
        """A's store with a second goal (A:g2): a card to clear last while A:g1 and B:g1 are owed."""
        st = _store(A, "the faulting session's goal"); g2 = A + ":g2"
        st["nodes"][g2] = dict(st["nodes"][A + ":g1"], id=g2, text="the faulting session's second goal"); st["status"][g2] = "working"
        st["seq"] = 2; st["lastNode"] = g2
        self._write(A, st)

    def _both_owed(self):
        """A:g1 and B:g1 cleared in one batch, then Undo with both stores refusing their flag step and the log refusing the re-journal: both owed."""
        self._dispatch({"type": "askClearMany", "itemIds": [A + ":g1", B + ":g1"]})
        orig = km._mark_nodes_cleared

        def both_stores_fault(ids, value, **kw):
            with _fault_on(self.a_file), _fault_on(self.b_file):
                return orig(ids, value, **kw)
        with mock.patch.object(km, "_mark_nodes_cleared", both_stores_fault), _nth_append_faults(jd.STATE / "cleared.jsonl", 2):
            self._dispatch({"type": "undoClear"})
        self.assertEqual(set(km._rejournal_owed), {A + ":g1", B + ":g1"})
        return orig

    def test_the_reorder_names_both_owed_cards_left_in_two_batches_and_counts_no_presses(self):
        """The seventh executed review's first low: "one more Undo" assumed the owed ids that did not come back hold one stamp. Two owed
        sessions faulting differently (A skipped at the archive read keeps the re-journal-first stamp; B's flag step re-journals at a fresh
        one) sit in two batches: the frame names both as not back and says they take more than one Undo, and its stack reads B, A, then the
        last clear."""
        self._two_card_store_for_a()
        orig = self._both_owed()
        self._dispatch({"type": "askClear", "itemId": A + ":g2"})   # the last clear
        km._compact_goal_store(A)                          # the sweep archived A's cleared tops, so the archive restore reads A's store (and faults)
        orig_ra = km._restore_goal_archive

        def archive_read_faults_for_a(ids):
            with _fault_on(self.a_file):
                return orig_ra(ids)

        def b_flag_step_faults(ids, value, **kw):
            with _fault_on(self.b_file):
                return orig(ids, value, **kw)
        with mock.patch.object(km, "_restore_goal_archive", archive_read_faults_for_a), mock.patch.object(km, "_mark_nodes_cleared", b_flag_step_faults):
            sent = self._dispatch({"type": "undoClear"})
        errs = [m for m in sent if m.get("type") == "err"]
        ro = next(m for m in errs if m["title"] == "Undo went to earlier cards first")
        self.assertEqual(sorted(ro["owedIds"]), sorted([A + ":g1", B + ":g1"]), "both did not come back: %r" % errs)
        self.assertIn("more than one Undo", ro["text"]); self.assertNotIn("one Undo brings them back", ro["text"])
        self.assertEqual(ro["itemIds"], [A + ":g2"])
        self.assertEqual(ro["batches"], [[B + ":g1"], [A + ":g1"], [A + ":g2"]], "the kernel's stack rides the frame: B at a fresh stamp, A at the re-journal-first's, the last clear")
        self.assertEqual(ro["owedBatch"], [], "nothing owed in memory once the re-journal landed")

    def test_the_reorder_names_only_the_owed_card_that_did_not_come_back(self):
        """The seventh executed review's first low, the other half: the frame named owed ids that came back this press. With A back and B's
        flag step refusing, it names B alone, and counts the one press."""
        self._two_card_store_for_a()
        orig = self._both_owed()
        self._dispatch({"type": "askClear", "itemId": A + ":g2"})

        def b_flag_step_faults(ids, value, **kw):
            with _fault_on(self.b_file):
                return orig(ids, value, **kw)
        with mock.patch.object(km, "_mark_nodes_cleared", b_flag_step_faults):
            sent = self._dispatch({"type": "undoClear"})
        errs = [m for m in sent if m.get("type") == "err"]
        ro = next(m for m in errs if m["title"] == "Undo went to earlier cards first")
        self.assertEqual(ro["owedIds"], [B + ":g1"], "A came back: not named: %r" % errs)
        self.assertIn("one Undo brings them back and the next the last clear", ro["text"])
        self.assertFalse(self._flag(A, A + ":g1"), "A is back"); self.assertTrue(self._flag(B, B + ":g1"), "B is not")
        self.assertEqual(ro["batches"], [[B + ":g1"], [A + ":g2"]])

    def test_the_stack_on_the_wire_carries_the_newest_twenty_batches_and_the_count_before_the_bound(self):
        """The eighth executed review's low and the ninth's medium: every account carried every cleared id (a live log: 2245 stamps, about 129 KB
        a frame), and a bound alone left the feed reading absence as "not cleared". The frame carries the newest twenty log batches and the
        count before the bound, so the feed knows what was left out; the unbounded read still holds every batch."""
        st = _store(A, "the faulting session's goal")
        for n in range(2, 23):
            g = A + ":g%d" % n
            st["nodes"][g] = dict(st["nodes"][A + ":g1"], id=g, text="goal %d" % n); st["status"][g] = "working"
        st["seq"] = 22; st["lastNode"] = A + ":g22"
        self._write(A, st)
        for n in range(1, 22):                              # twenty-one single clears: twenty-one stamps
            self._dispatch({"type": "askClear", "itemId": A + ":g%d" % n})
        with _append_faults(jd.STATE / "cleared.jsonl"):
            sent = self._dispatch({"type": "undoClear"})    # a refused undo: one account, the stack on it
        errs = [m for m in sent if m.get("type") == "err"]
        self.assertEqual(len(errs), 1, "%r" % errs)
        self.assertEqual((len(errs[0]["batches"]), errs[0]["batchesTotal"]), (20, 21), "twenty on the wire, twenty-one held: %r" % errs[0].get("batchesTotal"))
        self.assertEqual((errs[0]["batches"][0], errs[0]["batches"][-1]), ([A + ":g21"], [A + ":g2"]), "the newest first; the oldest, g1, left out")
        self.assertEqual(km._ledger_batches(limit=None)[0][-1], [A + ":g1"], "the unbounded read holds all twenty-one")
        self.assertEqual(km._ledger_batches()[2], 21, "and says how many there are")

    def test_an_undo_of_an_archived_card_on_a_read_only_root_answers_the_socket_and_the_next_undo_restores(self):
        """The second contributor's review (2026-09-22): _restore_goal_archive's journal append and archive save, and the flag helper's journal
        appends, raised through the dispatcher on a read-only root and the receive loop dropped the client. Each files its account instead;
        with the root writable again the next Undo restores the card cleanly."""
        self._dispatch({"type": "askClear", "itemId": A + ":g1"})
        km._compact_goal_store(A)                          # the sweep archived the cleared top
        orig = jd.append_restore

        def refusing_append(*a, **kw):
            raise OSError(errno.EROFS, "Read-only file system", str(jd.GOALDIR / "overrides"))
        with mock.patch.object(jd, "append_restore", refusing_append):
            sent = self._dispatch({"type": "undoClear"})    # the restore journal refuses: an account, the socket kept
        errs = [m for m in sent if m.get("type") == "err"]
        self.assertEqual([m["title"] for m in errs], ["That undo did not land for web"], "%r" % errs)
        self.assertIn("Read-only", errs[0]["text"])
        self.assertNotIn(A + ":g1", jd.load_goals(A)["nodes"], "the card stays archived: nothing moved before the refusal")
        sent = self._dispatch({"type": "undoClear"})        # writable again: the next Undo restores cleanly
        self.assertEqual([m for m in sent if m.get("type") == "err"], [])
        self.assertFalse(self._flag(A, A + ":g1")); self.assertIn(A + ":g1", self._feed_rows(A))
        # the flag helper's journal append refusing at a clear: its account, the save skipped, the socket kept
        orig_clear = jd.append_clear

        def refusing_clear(*a, **kw):
            raise OSError(errno.EROFS, "Read-only file system", str(jd.GOALDIR / "overrides"))
        with mock.patch.object(jd, "append_clear", refusing_clear):
            sent = self._dispatch({"type": "askClear", "itemId": A + ":g1"})
        errs = [m for m in sent if m.get("type") == "err"]
        self.assertEqual([m["title"] for m in errs], ["That clear did not fully land for web"], "%r" % errs)
        self.assertFalse(self._flag(A, A + ":g1"), "the flag's save was skipped: the journal did not take the row")

    def test_the_undo_button_shows_while_a_card_is_owed_and_after_a_restart_before_the_first_undo(self):
        """The second contributor's review (2026-09-22): canUndoClear and the dismissed count read the clears log alone, so after a two-fault
        undo (a card owed in memory and in the note, none in the log) the button hid exactly when the dialogs said to press it, and after a
        restart until the first Undo read the note. Both PAYLOADS (build_feed and the off frame) read the log's ids and the owed ids; the note
        is read once per kernel life, and while it is unreadable ONE judge-errors row per episode is filed (the thirteenth executed review:
        the helper alone was pinned, so the two payload lines reverted to the log's count stayed green; one row per call filled the errors
        file at twice the build rate). Red against that mutant, and against the per-call rows; the helper is this branch's, so the round's
        base has no button to hide, only a missing name."""
        self._two_fault_undo_leaves_b_owed()
        self.assertEqual(km._cleared_ids(), {}, "the log holds nothing: the owing is in memory and the note")

        def payloads():
            feed = km.build_feed(NOW, self.live); off = km._feed_off_frame(NOW, self.live)
            return (feed["canUndoClear"], feed["dismissedCount"], off["canUndoClear"], off["dismissedCount"])
        self.assertEqual(payloads(), (True, 1, True, 1), "both payloads show the button while a card is owed (before: false and 0, the log alone)")
        km._rejournal_owed.clear(); km._owed_settled.clear(); km._owed_note_read[0] = False   # a restart: memory empty, the note on disk
        self.assertEqual(payloads(), (True, 1, True, 1), "the note is read for the button before any Undo (before: hidden until the first Undo)")
        self.assertTrue(km._owed_note_read[0], "read once per life")
        # a present, unreadable note: said ONCE per episode, and the read stays armed
        km._rejournal_owed.clear(); km._owed_note_read[0] = False
        owed_file = jd.STATE / km.OWED_FILE
        orig_read = Path.read_text

        def refusing_read(p, *a, **kw):
            if p == owed_file:
                raise OSError(errno.EACCES, "Permission denied", str(p))
            return orig_read(p, *a, **kw)
        rows0 = len(self._rows("owed-note"))
        with mock.patch.object(Path, "read_text", refusing_read):
            self.assertEqual(payloads(), (False, 0, False, 0), "the log alone while the note cannot be read")
            self.assertEqual(km._undo_stack_ids(), set())
        self.assertFalse(km._owed_note_read[0], "armed until a read lands")
        self.assertEqual(len(self._rows("owed-note")) - rows0, 1, "four reads of the standing fault (two per build, one per off frame, one direct), one judge-errors row (before: one per read): %r" % self._rows("owed-note"))
        self.assertIn("Permission denied", self._rows("owed-note")[-1]["note"])
        self.assertEqual(payloads(), (True, 1, True, 1), "readable again: the read lands and the button is back")
        with mock.patch.object(Path, "read_text", refusing_read):
            km._rejournal_owed.clear(); km._owed_note_read[0] = False
            self.assertEqual(km._undo_stack_ids(), set())
        self.assertEqual(len(self._rows("owed-note")) - rows0, 2, "a read that landed in between makes the next refusal a new episode: a second row")
        # an UNDO's read landing ends the episode too (the round-fourteen verifier's low: it left the memo standing, so a same-fault re-break before the next build filed nothing)
        self._dispatch({"type": "askClear", "itemId": A + ":g1"}); self._dispatch({"type": "undoClear"})   # the Undo goes to the owed card first (the reorder); its note read lands
        with mock.patch.object(Path, "read_text", refusing_read):
            km._rejournal_owed.clear(); km._owed_note_read[0] = False
            km._undo_stack_ids()
        self.assertEqual(len(self._rows("owed-note")) - rows0, 3, "the same fault after the Undo's landed read is a new episode: a third row")
        self._dispatch({"type": "undoClear"})              # the last clear back too, so the log is empty again for the corrupt-note case
        # an ABSENT note read by an Undo ends the episode too (the first contributor's note on PR 2014: the reset sat after the try, so the
        # missing-note arm returned before it and the identical fault filed nothing)
        with mock.patch.object(Path, "read_text", refusing_read):
            km._rejournal_owed.clear(); km._owed_note_read[0] = False
            km._undo_stack_ids()                                                              # a fourth row: a new episode after the landed read above
        self.assertEqual(len(self._rows("owed-note")) - rows0, 4)
        owed_file.unlink(missing_ok=True)
        self._dispatch({"type": "askClear", "itemId": A + ":g1"}); self._dispatch({"type": "undoClear"})   # the Undo's read finds no note: a landed read
        with mock.patch.object(Path, "read_text", refusing_read):
            km._rejournal_owed.clear(); km._owed_note_read[0] = False
            owed_file.write_text("")                                                          # present again, unreadable
            km._undo_stack_ids()
        self.assertEqual(len(self._rows("owed-note")) - rows0, 5, "the same fault after an absent-note read is a new episode (before: the missing-note arm left the memo standing)")
        # a note whose bytes are not text (the thirteenth executed review: a ValueError raised through every builder, nothing filed)
        km._rejournal_owed.clear(); km._owed_note_read[0] = False; km._owed_read_fault[0] = ""
        owed_file.write_bytes(b"\xff\xfe\x00 not text")
        self.assertEqual(payloads(), (False, 0, False, 0), "a corrupt note: the builders proceed on the log alone, nothing raises")
        self.assertEqual(len(self._rows("owed-note")) - rows0, 6, "and it is filed once")
        self.assertIn("codec", self._rows("owed-note")[-1]["note"])
        sent = self._dispatch({"type": "undoClear"})
        self.assertIn("romp could not read its note of earlier owed cards", [m.get("title") for m in sent if m.get("type") == "err"], "an Undo over a corrupt note says so on its frame: %r" % sent)

    def test_every_undo_account_carries_the_kernels_build_floor_and_a_landed_undo_sends_the_ack(self):
        """Round fifteen (the round-thirteen verifier's ruling): the feed judges a restore by a payload built after the kernel PROCESSED the
        undo, which every undo account names as a build floor: the counter as it stood then (claimed before a build's read, so a build past
        it read the store after every earlier clear applied and the undo's batch restored). A landed undo, with nothing else to say, sends an
        ack alone; the refusal and reorder frames carry the floor and no ack rides beside them; both payloads say this kernel accounts so."""
        self._dispatch({"type": "askClear", "itemId": A + ":g1"})
        sent = self._dispatch({"type": "undoClear"})
        acks = [m for m in sent if m.get("type") == "undoAck"]
        self.assertEqual([(m["op"], m["buildId"]) for m in acks], [("undoClear", km._feed_build_id[0])], "one ack, the build counter as it stood when the undo was processed: %r" % sent)
        self.assertEqual([m for m in sent if m.get("type") == "err"], [], "and no account beside it")
        self.assertGreater(km._next_feed_build_id(), acks[0]["buildId"], "a build claimed after the undo (the pusher claims the id before its read) is past the floor")
        self.assertIs(km.build_feed(NOW, self.live)["undoAck"], True); self.assertIs(km._feed_off_frame(NOW, self.live)["undoAck"], True)
        under_fault = self._two_fault_undo_leaves_b_owed()
        self._dispatch({"type": "askClear", "itemId": A + ":g1"})
        with mock.patch.object(km, "_mark_nodes_cleared", under_fault):
            sent = self._dispatch({"type": "undoClear"})    # the owed store's refusal and the reorder: two accounts, one floor
        errs = [m for m in sent if m.get("type") == "err"]
        self.assertEqual([m["title"] for m in errs], ["That undo did not land for api", "Undo went to earlier cards first"])
        self.assertEqual([m.get("buildId") for m in errs], [km._feed_build_id[0]] * 2, "the refusal and the reorder frames carry the floor: %r" % errs)
        self.assertEqual([m for m in sent if m.get("type") == "undoAck"], [], "no ack beside an account")
        sent = self._dispatch({"type": "askClear", "itemId": A + ":g2"})
        self.assertEqual([m for m in sent if m.get("type") in ("undoAck", "err")], [], "a clear that lands sends nothing: the floor is an undo's")

    def test_an_undo_account_marks_the_clients_floor_pending_so_the_rebuild_past_it_goes_and_echoes_the_undos_sequence(self):
        """The first contributor's post-merge review of PR 1967 (M1, M2) and round two of PR 2018's verifier. M1: a build claimed at or below
        the floor whose clears snapshot followed the restore lists the card, which the pane refuses, while the rebuild past the floor carries
        the same dedup signature (buildId is volatile) and would not go until the 60 s repost; a slot pop at the account could land between
        the in-flight build's claim and its send, which then refilled the slot. While the undo's floor is unanswered the client's feed frames
        carry their build id in the signature, so the in-flight build and the rebuild never share one; the mark clears once a build past the
        floor has gone. M2: the feed's per-undo sequence rides the request and comes back on the ack and on every undo account frame."""
        sent = []

        def client_of(**extra):
            return dict({"app": "feed", "alive": True, "send": lambda s: sent.append(json.loads(s)), "sent": {}}, **extra)

        def push(c, bid):                                 # the pusher's road: one build to this client, identical content every time
            p = {"type": "feed", "buildId": bid, "asks": [{"itemId": A + ":g1", "sid": A}], "now": NOW}; s_ = json.dumps(p)
            n0 = len(sent); km._send_slot(c, "feed", p, s_, km._dedup_sig(p, s_)); return len(sent) > n0
        for road, c in (("legacy", client_of()), ("delta", client_of(delta=True))):
            self.assertTrue(push(c, 3), road + ": the first frame goes")
            self.assertFalse(push(c, 4), road + ": an identical-content build is deduped (buildId is volatile)")
            km._gesture_store_refusal(c, "undo", {}, ids=[], op="undoClear", seq=7)
            floor = km._feed_build_id[0]
            self.assertEqual([(m["op"], m["seq"], m["buildId"]) for m in sent if m.get("type") == "undoAck"][-1:], [("undoClear", 7, floor)], road + ": the ack echoes the sequence and the floor: %r" % sent[-1:])
            # THE RACE (round two of PR 2018's verifier): the in-flight build, claimed at the floor before the account and sent after it,
            # refills the slot; the rebuild past the floor carries the same content and must still go (False at 583ab08b)
            self.assertTrue(push(c, floor), road + ": the in-flight build at the floor goes")
            self.assertTrue(push(c, floor + 1), road + ": the rebuild past the floor goes though its content is the in-flight build's (before: deduped until the repost)")
            self.assertNotIn("floorPending", c, road + ": a build past the floor sent, the mark clears")
            plain = {"type": "feed", "buildId": 0, "asks": [{"itemId": A + ":g1", "sid": A}], "now": NOW}
            self.assertEqual(c["sent"][("feed",)][0], km._dedup_sig(plain, json.dumps(plain)), road + ": the slot holds the plain signature again once the mark clears (a mutant clearing it without the slot reset sends one frame more)")
            # the mark itself (the post-merge note on PR 2018): equal to the floor after the account and after the at-floor push; a refusal's account
            # sets it too and leaves it standing until a build past ITS floor has gone
            km._gesture_store_refusal(c, "undo", {}, ids=[], op="undoClear", seq=10); floor2 = km._feed_build_id[0]
            self.assertEqual(c.get("floorPending"), floor2, road + ": the mark equals the floor after the account")
            self.assertTrue(push(c, floor2)); self.assertEqual(c.get("floorPending"), floor2, road + ": and after the at-floor push")
            km._next_feed_build_id()                                                          # a build claimed between the accounts: the refusal's floor is its own (the post-merge review of PR 2021)
            km._gesture_store_refusal(c, "undo", {km.LEDGER_KEY: {"fault": "the log refused", "ids": [A + ":g1"]}}, ids=[A + ":g1"], op="undoClear", seq=11); floor3 = km._feed_build_id[0]
            self.assertGreater(floor3, floor2, road + ": the build between the accounts moved the floor")
            self.assertEqual(c.get("floorPending"), floor3, road + ": a refusal's account sets the mark to its own floor (a mutant skipping the mark on the refused path leaves floor2 here; one popping it after the err frame leaves none)")
            self.assertTrue(push(c, floor3 + 1)); self.assertNotIn("floorPending", c)
            if road == "delta":
                self.assertTrue(push(c, floor3 + 2), "delta: one whole frame re-bases the stream")
            self.assertFalse(push(c, floor3 + 3 if road == "delta" else floor3 + 2), road + ": the dedup stands again")
        sent.clear()
        client = client_of()
        km._gesture_store_refusal(client, "clear", {}, ids=[A + ":g1"], op="askClear", seq=8)
        self.assertEqual(sent, [], "a clear's account carries no floor and no ack: the sequence is an undo's"); self.assertNotIn("floorPending", client)
        km._gesture_store_refusal(client, "undo", {km.LEDGER_KEY: {"fault": "the log refused", "ids": [A + ":g1"]}}, ids=[A + ":g1"], op="undoClear", seq=9)
        errs = [m for m in sent if m.get("type") == "err"]
        self.assertEqual([(m["op"], m.get("seq"), "buildId" in m) for m in errs], [("undoClear", 9, True)], "the refusal's frame echoes the sequence beside the floor: %r" % errs)
        self.assertEqual([m for m in sent if m.get("type") == "undoAck"], [], "no ack beside an account")
        # the arm passes the request's sequence through, an int alone
        sent = self._dispatch({"type": "askClear", "itemId": A + ":g1"}); sent = self._dispatch({"type": "undoClear", "seq": 11})
        self.assertEqual([m.get("seq") for m in sent if m.get("type") == "undoAck"], [11])
        sent = self._dispatch({"type": "askClear", "itemId": A + ":g1"}); sent = self._dispatch({"type": "undoClear", "seq": True})
        self.assertEqual([("seq" in m) for m in sent if m.get("type") == "undoAck"], [False], "a sequence that is not a number is not echoed")

    def test_every_clears_log_refusal_files_a_judge_errors_row(self):
        """The second contributor's post-merge review (2026-09-22): the four clears-log refusal arms (a clear's rows, an undo's rows, the
        flag-step re-journal, the re-journal-first rows) reached the pressing socket and nothing followed, while the note helpers' arms
        record theirs. Each files one judge-errors row (clears-log) and a stderr line."""
        rows = lambda: len(self._rows("clears-log"))
        n0 = rows()
        stderr = []

        @contextlib.contextmanager
        def captured():                                      # the stderr half of the convention (the second contributor's post-merge note on PR 2018: unpinned before)
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                yield
            stderr.append([l for l in buf.getvalue().splitlines() if l.startswith("clears log: ")])
        with captured(), _nth_append_faults(jd.STATE / "cleared.jsonl", 1):
            self._dispatch({"type": "askClear", "itemId": A + ":g1"})                # the clear rows refused
        self.assertEqual(rows() - n0, 1, "the clear rows' refusal files: %r" % self._rows("clears-log"))
        self._dispatch({"type": "askClear", "itemId": A + ":g1"})
        with captured(), _nth_append_faults(jd.STATE / "cleared.jsonl", 1):
            self._dispatch({"type": "undoClear"})                                     # the undo rows refused
        self.assertEqual(rows() - n0, 2, "the undo rows' refusal files")
        self._dispatch({"type": "undoClear"})                                         # A back
        with captured():
            self._two_fault_undo_leaves_b_owed()                                       # the flag-step re-journal refused: B owed
        self.assertEqual(rows() - n0, 3, "the flag-step re-journal's refusal files")
        with captured(), _nth_append_faults(jd.STATE / "cleared.jsonl", 1):
            self._dispatch({"type": "undoClear"})                                     # the owed id's re-journal-first rows refused
        self.assertEqual(rows() - n0, 4, "the re-journal-first refusal files")
        self.assertEqual([r["note"].split(" refused")[0] for r in self._rows("clears-log")[-4:]],
                         ["clears log: the clear rows", "clears log: the undo rows", "clears log: the flag-step re-journal", "clears log: the re-journal-first rows"])
        self.assertEqual([len(x) for x in stderr], [1, 1, 1, 1], "one stderr line per refusal: %r" % stderr)
        # the sixth writer: the mute's clear rows, under the flag setter's own bare except (the second contributor's post-merge note on PR 2018)
        self._dispatch({"type": "undoClear"})                                         # B back, A's clear undone: tops to mute
        with captured(), _nth_append_faults(jd.STATE / "cleared.jsonl", 1):
            km._set_session_flag(A, "hideFromFeed", True)
        self.assertEqual(rows() - n0, 5, "the mute's refusal files a row too"); self.assertEqual(len(stderr[-1]), 1)
        self.assertIn("the mute's clear rows", self._rows("clears-log")[-1]["note"])
        self.assertFalse(self._flag(A, A + ":g1"), "the refused mute sealed nothing: the raise at its site skips the node flags (the second contributor's post-merge review of PR 2021: with it deleted a refused mute sealed every open top and the module stayed green)")
        # the row names the session and its tops, the stderr line the session's first eight characters (the review's low: the two new writers'
        # rows named neither, so the card modal's warnings join never showed them); the four gesture arms' rows stay session-less, as before
        mute_row = self._rows("clears-log")[-1]
        self.assertEqual(mute_row["fsid"], A, "the mute's row names the session: %r" % mute_row); self.assertIn(A + ":g1", mute_row.get("goal") or [], "and its tops")
        self.assertIn("(session %s)" % A[:8], stderr[-1][0], "the stderr line names the session too: %r" % stderr[-1])
        self.assertEqual([r["fsid"] for r in self._rows("clears-log")[-5:-1]], ["", "", "", ""], "the gesture arms' rows name no session, as before")
        km._set_session_flag(A, "hideFromFeed", False)

    def test_a_present_clears_log_that_cannot_be_read_is_said_once_per_episode_and_on_the_undos_account(self):
        """The second contributor's post-merge note on PR 2018 made an undecodable clears log read as the empty uncached set (a raise before);
        the first contributor's post-merge review of PR 2021: that read, and the older OSError arm, said nothing anywhere while the note reader
        files a stderr line, a judge-errors row and an account for the same bytes. An ABSENT log stays silent; a present log that cannot be
        read, or whose bytes are not text, files ONE stderr line and ONE judge-errors row per fault episode (ended by a landed read or an absent
        log), and an Undo over it names the fault on its account, with the floor and the sequence, where a bare ack went."""
        log = jd.STATE / "cleared.jsonl"
        rows = lambda: [r for r in self._rows("cleared-unreadable") if "the read" in r.get("note", "")]   # the read's kind: the judge reader's, for the same file (the round-one verifier of PR 2025)

        @contextlib.contextmanager
        def captured(lines):
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                yield
            lines.extend(l for l in buf.getvalue().splitlines() if l.startswith("clears log: the read"))
        # non-text bytes: said once, on the socket too
        log.write_bytes(b"\xff\xfe\x00 not text\n"); km._CLEARED_MEMO["slot"] = None; getattr(km, "_cleared_read_fault", [""])[0] = ""   # (tolerant of the base without the memo: the red lands on the account below)
        lines = []
        with captured(lines):
            sent = self._dispatch({"type": "undoClear", "seq": 5})
        errs = [m for m in sent if m.get("type") == "err"]
        self.assertEqual([(m["title"], m.get("seq"), "buildId" in m) for m in errs], [("romp could not read its record of cleared cards", 5, True)], "the undo's account names the fault, with the floor and the sequence (before: a bare ack): %r" % sent)
        self.assertIn("codec", errs[0]["text"]); self.assertEqual([m for m in sent if m.get("type") == "undoAck"], [], "no bare ack beside it")
        self.assertEqual({"batches", "owedBatch", "batchesTotal"} & set(errs[0]), set(), "the read-fault account ships NO stack: an empty one from the faulted read emptied the feed's stack and released its suppressions (the round-one verifier of PR 2025): %r" % errs[0])
        # the sibling: a refused CLEAR over the unreadable log ships no stack either (the base sent an empty one)
        with _nth_append_faults(log, 1):
            km._CLEARED_MEMO["slot"] = None
            sent2 = self._dispatch({"type": "askClear", "itemId": A + ":g1"})
        errs2 = [m for m in sent2 if m.get("type") == "err"]
        self.assertEqual(len(errs2), 1, "the clear's refusal: %r" % sent2); self.assertEqual({"batches", "owedBatch", "batchesTotal"} & set(errs2[0]), set(), "no stack while the log cannot be read")
        self.assertEqual(len(rows()), 1, "one judge-errors row for the read: %r" % rows()); self.assertEqual(len(lines), 1, "one stderr line: %r" % lines)
        with captured(lines):
            km._CLEARED_MEMO["slot"] = None; km._cleared_ids(); km._undo_stack_ids()
        self.assertEqual((len(rows()), len(lines)), (1, 1), "the standing fault files nothing more: one row and one line per episode")
        # a landed read ends the episode; the same fault after it files again
        log.write_text(""); km._CLEARED_MEMO["slot"] = None; self.assertEqual(km._cleared_ids(), {}); self.assertEqual(getattr(km, "_cleared_read_fault", [""])[0], "")
        log.write_bytes(b"\xff\xfe\x00 not text\n"); km._CLEARED_MEMO["slot"] = None
        with captured(lines):
            km._cleared_ids()
        self.assertEqual((len(rows()), len(lines)), (2, 2), "a new episode after the landed read")
        # an unreadable log (a permission bit): the same shape, its own copy
        log.write_text(""); km._CLEARED_MEMO["slot"] = None; km._cleared_ids()
        orig_read = Path.read_text

        def refusing_read(p, *a, **kw):
            if p == log:
                raise OSError(errno.EACCES, "Permission denied", str(p))
            return orig_read(p, *a, **kw)
        with mock.patch.object(Path, "read_text", refusing_read), captured(lines):
            km._CLEARED_MEMO["slot"] = None
            sent = self._dispatch({"type": "undoClear", "seq": 6})
            km._CLEARED_MEMO["slot"] = None; km._cleared_ids()
        self.assertEqual([(m["title"], m.get("seq")) for m in sent if m.get("type") == "err"], [("romp could not read its record of cleared cards", 6)])
        self.assertIn("Permission denied", rows()[-1]["note"]); self.assertEqual((len(rows()), len(lines)), (3, 3), "one row and one line for the unreadable log's episode")
        # an absent log: nothing cleared, said nowhere, and it ends the episode
        log.unlink(); km._CLEARED_MEMO["slot"] = None
        with captured(lines):
            self.assertEqual(km._cleared_ids(), {})
        self.assertEqual((len(rows()), len(lines)), (3, 3), "an absent log is a real state: no row, no line"); self.assertEqual(getattr(km, "_cleared_read_fault", [""])[0], "")
        log.write_bytes(b"\xff\xfe\x00 not text\n"); km._CLEARED_MEMO["slot"] = None
        with captured(lines):
            km._cleared_ids()
        self.assertEqual((len(rows()), len(lines)), (4, 4), "the same bytes after an absent read are a new episode")
        log.write_text(""); km._CLEARED_MEMO["slot"] = None; km._cleared_ids()
        self.assertEqual({r["err"] for r in self._rows() if "the read" in r.get("note", "")}, {"cleared-unreadable"}, "the read's rows file under the kind the judge's own reader uses for this file, one kind per meaning (the round-one verifier of PR 2025)")

    def test_the_undos_account_describes_its_own_read_not_a_flag_another_read_may_have_moved(self):
        """The round-one verifier of PR 2025: the fault travelled as a module flag read two statements after the undo's read, so a pusher
        read landing in the window lost the account and one faulting there filed a false one. The undo takes the set and the fault in one
        statement; a flag that says otherwise does not speak for it."""
        two = hasattr(km, "_cleared_ids_read")                                          # (the base has the set-only reader alone: its red lands on the account below)
        getattr(km, "_cleared_read_fault", [""])[0] = ""                                # the flag says nothing faulted
        with mock.patch.object(km, "_cleared_ids_read" if two else "_cleared_ids", (lambda: ({}, "the read refused (stand-in)")) if two else (lambda: {})):
            sent = self._dispatch({"type": "undoClear", "seq": 7})
        self.assertEqual([m["title"] for m in sent if m.get("type") == "err"], ["romp could not read its record of cleared cards"], "the account follows the undo's own read (before: the flag, which said nothing): %r" % sent)
        getattr(km, "_cleared_read_fault", [""])[0] = "a stale fault another read left"  # the flag says a fault stands
        with mock.patch.object(km, "_cleared_ids_read" if two else "_cleared_ids", (lambda: ({}, "")) if two else (lambda: {})):
            sent = self._dispatch({"type": "undoClear", "seq": 8})
        self.assertEqual([m for m in sent if m.get("type") == "err"], [], "and a stale flag files no false account: the undo's own read landed")
        getattr(km, "_cleared_read_fault", [""])[0] = ""

    def test_a_clears_log_row_that_is_not_an_object_or_whose_id_is_not_a_string_is_skipped_by_the_kernels_reader(self):
        """The second contributor's post-merge review of PR 2021: the id lookup ran on whatever the parse returned, so a `[]` row raised
        AttributeError out of the read (an undo, a build). Such a row, and one whose id is not a string, are skipped per row like a row that
        is not JSON; the rows beside them load."""
        log = jd.STATE / "cleared.jsonl"
        log.write_text("[]\n" + json.dumps({"id": 5, "t": 1, "op": "clear"}) + "\n" + json.dumps({"id": A + ":g1", "t": 2, "op": "clear"}) + "\n"
                       + json.dumps({"id": {"k": "v"}, "t": 3, "op": "clear"}) + "\n" + json.dumps({"id": "", "t": 4, "op": "clear"}) + "\n")
        km._CLEARED_MEMO["slot"] = None
        try:
            got = km._cleared_ids()
        except AttributeError as e:
            self.fail("the reader raised on a row that is not an object: %r" % e)
        self.assertEqual(got, {A + ":g1": 2}, "the array row, the non-string ids and the empty id are skipped, the row beside them loads")
        self.assertEqual(km._undo_stack_ids(), {A + ":g1"}, "the stack helper reads the same")

    def test_a_standing_undecodable_clears_log_is_read_once_per_file_state_and_the_served_state_names_its_fault(self):
        """The second contributor's post-merge review of PR 2021: the fault arm returned before the memo, a permanent miss, so a standing
        undecodable log was re-read on every call (every build, every walk). Bytes that are not text are a function of the file, so the stat
        is an exact key: the empty set is served with its fault while the file stands, an Undo over the served state still names the fault,
        and the note stays once per episode (round two's shape). The OSError road stays uncached: a permission bit lifts with the stat unmoved."""
        log = jd.STATE / "cleared.jsonl"
        log.write_bytes(b"\xff\xfe\x00 not text\n"); km._CLEARED_MEMO["slot"] = None; km._cleared_read_fault[0] = ""
        orig_read, reads = Path.read_text, []

        def counting(p, *a, **kw):
            if p == log:
                reads.append(1)
            return orig_read(p, *a, **kw)
        with mock.patch.object(Path, "read_text", counting), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(km._cleared_ids(), {}); self.assertEqual(km._cleared_ids(), {}); km._undo_stack_ids()
            self.assertEqual(len(reads), 1, "the undecodable log is read once per file state (before: on every call)")
            sent = self._dispatch({"type": "undoClear", "seq": 10})
            self.assertEqual(len(reads), 1, "the undo's read is served too")
        self.assertEqual([m["title"] for m in sent if m.get("type") == "err"], ["romp could not read its record of cleared cards"], "the served state names its fault on the undo's account: %r" % sent)
        self.assertEqual(len([r for r in self._rows("cleared-unreadable") if "the read" in r["note"]]), 1, "one row for the episode: the served reads file nothing")
        log.write_bytes(b"\xff\xfe\x00 not text either\n")              # a new file state: read once more
        with mock.patch.object(Path, "read_text", counting), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(km._cleared_ids(), {}); self.assertEqual(km._cleared_ids(), {})
        self.assertEqual(len(reads), 2, "a moved stat is read again, once")
        log.write_text(""); km._CLEARED_MEMO["slot"] = None; km._cleared_ids()   # a landed read ends the episode

        def refusing(p, *a, **kw):
            if p == log:
                reads.append(1)
                raise OSError(errno.EACCES, "Permission denied", str(p))
            return orig_read(p, *a, **kw)
        with mock.patch.object(Path, "read_text", refusing), contextlib.redirect_stderr(io.StringIO()):
            km._CLEARED_MEMO["slot"] = None
            km._cleared_ids(); km._cleared_ids()
        self.assertEqual(len(reads), 4, "an unreadable log is read on every call: the fault can lift with the stat unmoved")
        log.write_text(""); km._CLEARED_MEMO["slot"] = None; km._cleared_ids()

    def test_the_accounts_stack_gate_reads_its_own_ledger_reads_fault_not_a_flag_a_landed_read_may_have_cleared(self):
        """The round-two verifier of PR 2025: the clear road's stack gate read the module flag AFTER the ledger read, the window round one
        named for the undo: a landed read on another thread between the two cleared the flag, and the refused clear's frame carried the
        faulted read's EMPTY stack. The gate reads the ledger read's own fault, returned beside the stack."""
        log = jd.STATE / "cleared.jsonl"
        log.write_bytes(b"\xff\xfe\x00 not text\n"); km._CLEARED_MEMO["slot"] = None; km._cleared_read_fault[0] = ""
        real = km._ledger_batches

        def landing_between(*a, **kw):
            out = real(*a, **kw)                                      # the account's ledger read, over the undecodable log
            km._cleared_read_fault[0] = ""                            # an injected landed read on another thread, before the gate
            return out
        with mock.patch.object(km, "_ledger_batches", landing_between), _nth_append_faults(log, 1), contextlib.redirect_stderr(io.StringIO()):
            km._CLEARED_MEMO["slot"] = None
            sent = self._dispatch({"type": "askClear", "itemId": A + ":g1"})
        errs = [m for m in sent if m.get("type") == "err"]
        self.assertEqual(len(errs), 1, "the clear's refusal: %r" % sent)
        self.assertEqual({"batches", "owedBatch", "batchesTotal"} & set(errs[0]), set(), "no stack: the gate reads the ledger read's own fault (before: the flag, cleared by the injected read, attached the empty stack): %r" % errs[0])
        log.write_text(""); km._CLEARED_MEMO["slot"] = None; km._cleared_ids()

    def test_the_read_fault_account_ships_no_stack_even_when_the_log_reads_again_before_the_frame_is_built(self):
        """The round-two verifier of PR 2025: the read-key guard was held by a source regex alone (with it gone, the gate below kept the
        Python pins green). The undo's own read faulted; the log reads again before the account is built, so the account's ledger read lands
        and no fault gates the stack: the read-fault account still ships none, since the read it answers for found nothing to stand on."""
        log = jd.STATE / "cleared.jsonl"
        log.write_text(""); km._CLEARED_MEMO["slot"] = None; km._cleared_read_fault[0] = ""
        real, calls = km._cleared_ids_read, [0]

        def first_faults(*a, **kw):
            calls[0] += 1
            if calls[0] == 1:
                return {}, "the undo's read refused (stand-in)"       # the undo's own read
            return real(*a, **kw)                                      # the log reads again: every later read lands
        with mock.patch.object(km, "_cleared_ids_read", first_faults):
            sent = self._dispatch({"type": "undoClear", "seq": 11})
        errs = [m for m in sent if m.get("type") == "err"]
        self.assertEqual([m["title"] for m in errs], ["romp could not read its record of cleared cards"], "the undo's own read faulted: %r" % sent)
        self.assertEqual({"batches", "owedBatch", "batchesTotal"} & set(errs[0]), set(), "no stack on the read-fault account though the ledger read behind the frame landed (with the key guard gone, that landed read's stack rode it)")
        self.assertEqual(real(), ({}, ""), "premise: the log reads again, so a ledger read behind the frame would land (under the guard the read-fault-only account runs none)")

    def test_an_undo_over_an_unreadable_log_with_a_card_owed_touches_nothing_and_files_the_account(self):
        """The first contributor's round-one comment on PR 2025 (pre-existing): the re-journal-first block ran before the undo's own read, so
        over a log it could not read the press appended the owed row after the garbage, emptied the owing, rewrote the note and then filed the
        read-fault account whose words say nothing was touched; a truncation repair then left that card flag-cleared with no row and no note,
        unreachable by Undo. The undo's own read comes first: on a fault the account is filed and nothing is touched; the press after the
        repair re-journals the owed row first and restores the card."""
        self._two_fault_undo_leaves_b_owed()                                 # B owed, in memory and in the note beside the log
        log, note = jd.STATE / "cleared.jsonl", jd.STATE / km.OWED_FILE
        prefix = b"\xff\xfe\x00 not text\n"
        log.write_bytes(prefix + log.read_bytes()); km._CLEARED_MEMO["slot"] = None; km._cleared_read_fault[0] = ""
        before_log, before_note, before_owed = log.read_bytes(), note.read_bytes(), dict(km._rejournal_owed)
        with contextlib.redirect_stderr(io.StringIO()):
            sent = self._dispatch({"type": "undoClear", "seq": 12})
        self.assertEqual([m["title"] for m in sent if m.get("type") == "err"], ["romp could not read its record of cleared cards"], "the read-fault account, alone: %r" % sent)
        self.assertEqual([m for m in sent if m.get("type") == "undoAck" or m.get("ok")], [], "no ack and no reorder frame beside it")
        self.assertEqual(log.read_bytes(), before_log, "no row appended behind the bytes the undo could not read (before: the owed row went in after the garbage)")
        self.assertEqual(km._rejournal_owed, before_owed, "the owing stands in memory (before: emptied)"); self.assertEqual(note.read_bytes(), before_note, "and the note is unchanged (before: rewritten)")
        self.assertTrue(self._flag(B, B + ":g1"), "the owed card stays as it was")
        log.write_bytes(before_log[len(prefix):]); km._CLEARED_MEMO["slot"] = None   # the repair: the log reads again
        sent = self._dispatch({"type": "undoClear", "seq": 13})
        self.assertEqual(km._rejournal_owed, {}, "the press that could read the log re-journals the owed row first and consumes the owing: %r" % sent)
        self.assertFalse(self._flag(B, B + ":g1"), "and the owed card is back")

    def test_the_two_new_judge_errors_kinds_are_documented(self):
        """The second contributor's post-merge note on PR 2018: `clears-log` and `owed-note` were in neither kind list; the round-one verifier
        of PR 2025: the sentences must name each kind's writer and shape, the kernel's read filing under `cleared-unreadable` per episode."""
        doc = (Path(km.__file__).resolve().parent.parent / "docs" / "judges.md").read_text()
        ds = jd._log_judge_error.__doc__
        flat = doc.replace("\n  ", " ")
        self.assertRegex(flat, r"clears-log: a write to the clears log refused \(a clear's or an undo's rows, the mute's, the episode boundary's\), one row per refusal", "the write kind's sentence")
        self.assertRegex(flat, r"cleared-unreadable is filed by the kernel's own reader of the clears log as well[^.]{0,300}one row per fault episode", "the read kind's sentence names the kernel's reader and the episode")
        self.assertRegex(flat, r"owed-note: the note of owed cards beside the log could not be written or read")
        self.assertRegex(ds, r'"clears-log" \(a clears-log write refused')
        self.assertRegex(ds.replace("\n", " "), r'"cleared-unreadable" is also the kernel\'s own reader\'s\s+kind for the clears log[^)]*one row per fault episode')
        self.assertIn('"owed-note"', ds)
        # the note helper's and the refusal sender's own docstrings (the round-two verifier of PR 2025: the helper's sentence was pinned by nothing)
        self.assertRegex(km._clears_log_fault_note.__doc__.replace("\n", " "), r"the kernel's own READ of the log files under `cleared-unreadable`,\s+the kind the judge's side-file reader files for the same file, one row per fault episode", "the helper names the read as the kind's second writer")
        self.assertIn("`cleared-unreadable` for the read-fault account's read of it", km._gesture_store_refusal.__doc__, "the sender names the read-fault account's kind")

    def test_a_clears_account_after_a_restart_carries_the_owing_the_note_holds(self):
        """The second contributor's post-merge review (2026-09-22): the restart-owing load on a non-undo account was pinned by no behaviour
        (a `pass` left the module green). After a restart (memory empty, the note on disk) a clear the log refuses carries the owed id
        in its account's stack."""
        self._two_fault_undo_leaves_b_owed()
        km._rejournal_owed.clear(); km._owed_settled.clear(); km._owed_note_read[0] = False   # a restart
        with _nth_append_faults(jd.STATE / "cleared.jsonl", 1):
            sent = self._dispatch({"type": "askClear", "itemId": A + ":g1"})
        errs = [m for m in sent if m.get("type") == "err"]
        self.assertEqual([m["owedBatch"] for m in errs], [[B + ":g1"]], "the account's stack carries the owing the note holds (before: empty until the first Undo read it): %r" % errs)

    def test_a_note_row_that_is_not_json_is_skipped_and_the_others_load(self):
        """The second contributor's post-merge review (2026-09-22): the note read's row guard was pinned by no behaviour. A row that is not
        JSON is skipped; the id beside it loads; nothing raises."""
        (jd.STATE / km.OWED_FILE).write_text("{not json\n" + json.dumps({"id": B + ":g1"}) + "\n")
        km._rejournal_owed.clear(); km._owed_note_read[0] = False; km._owed_read_fault[0] = ""
        self.assertEqual(km._undo_stack_ids(), {B + ":g1"}, "the garbage row is skipped, the id beside it loads")
        self.assertTrue(km._owed_note_read[0], "and the read counts as landed")

    def test_the_off_frame_over_an_undecodable_clears_log_ships_zero_counts(self):
        """The thirteenth executed review (2026-09-22): the off frame's guarded clears-log read was dead code once the stack helper replaced it,
        and _cleared_ids catches OSError alone, so with tracking off a clears log whose bytes are not text raised UnicodeDecodeError out of
        the frame (the carry shipped zero counts). The ids are computed inside the guard again."""
        (jd.STATE / "cleared.jsonl").write_bytes(b"\xff\xfe\x00 not text\n")
        f = km._feed_off_frame(NOW, self.live)
        self.assertEqual((f["off"], f["dismissedCount"], f["canUndoClear"]), (True, 0, False), "zero counts, no raise")

    def test_the_one_stamp_reorder_clause_names_the_store_by_its_kind(self):
        """The thirteenth executed review (2026-09-22): the clause derived its subject as a goals file for an owed NOTICE id, whose own account
        names the notice archive. The subject comes from the store keys: a notice archive against a goals file, several stores as such."""
        def words(owed, extra=None):
            sent = []
            client = {"app": "feed", "alive": True, "send": lambda s: sent.append(json.loads(s))}
            skipped = {km.LEDGER_REORDER_KEY: {"fault": "", "ids": [A + ":g2"], "landed": False, "owed": owed, "stamps": 1}}
            skipped.update(extra or {})
            km._gesture_store_refusal(client, "undo", skipped, ids=[A + ":g2"], op="undoClear")
            return next(m["text"] for m in sent if m.get("title") == "Undo went to earlier cards first")
        self.assertIn("Once that session's notice archive can be read and written again, one Undo brings them back", words(["notice:%s:k:1" % B]))
        self.assertIn("Once that session's goals file can be read and written again", words([B + ":g1"]))
        self.assertIn("Once those stores can be read and written again", words([B + ":g1", "notice:%s:k:1" % B]), "a goals file and a notice archive of one session are two stores")
        self.assertIn("Once the clears log can be read and written again", words([B + ":g1"], {km.LEDGER_REJOURNAL_AGAIN_KEY: {"fault": "x", "ids": [B + ":g1"]}}))

    def test_a_refused_continue_from_the_chat_box_answers_that_socket_with_the_held_shape(self):
        """The second contributor's review (2026-09-22): the askFollowUp arm's ack reached feed clients alone, so a chat socket that pressed
        Continue heard nothing and its row stayed latched. The pressing socket, when its app is not the feed, hears the held shape: the
        words went out, the reopen did not land, the why as the error; a goal gone has its own words."""
        sent = []
        client = {"app": "chat", "alive": True, "send": lambda s: sent.append(json.loads(s))}
        orig = jd.optimistic_followup

        def refusing(*a, **kw):
            raise OSError(errno.EROFS, "Read-only file system", str(self.a_file))
        with mock.patch.object(jd, "optimistic_followup", refusing), mock.patch.object(km, "_send_or_park", lambda *a, **kw: object()):
            km.Handler._dispatch_ws(object.__new__(km.Handler), {"type": "askFollowUp", "itemId": A + ":g1", "sid": A, "cont": True}, client)
        done = [m for m in sent if m.get("type") == "noticeActionDone"]
        self.assertEqual([(m["itemId"], m["ok"], m["held"]) for m in done], [(A + ":g1", True, True)], "the held shape to the socket that pressed: %r" % sent)
        self.assertIn("Read-only", done[0]["error"])
        sent.clear()
        with mock.patch.object(jd, "optimistic_followup", lambda *a, **kw: False), mock.patch.object(km, "_send_or_park", lambda *a, **kw: object()):
            km.Handler._dispatch_ws(object.__new__(km.Handler), {"type": "askFollowUp", "itemId": A + ":g9", "sid": A, "cont": True}, client)
        done = [m for m in sent if m.get("type") == "noticeActionDone"]
        self.assertEqual(len(done), 1); self.assertIn("no longer on the board", done[0]["error"], "the goal-gone case has its own words: %r" % done)
        sent.clear()
        feed = {"app": "feed", "alive": True, "send": lambda s: sent.append(json.loads(s))}
        with mock.patch.object(jd, "optimistic_followup", refusing), mock.patch.object(km, "_send_or_park", lambda *a, **kw: object()):
            km.Handler._dispatch_ws(object.__new__(km.Handler), {"type": "askFollowUp", "itemId": A + ":g1", "sid": A, "cont": True}, feed)
        self.assertEqual([m for m in sent if m.get("type") == "noticeActionDone"], [], "a feed client hears the ack it always did, not the box's shape")

    def test_a_stale_note_across_a_restart_does_not_name_a_card_this_press_restores(self):
        """The fourth review's second low: the note's rewrite refused (its stale row stays), a restart, the card re-cleared, Undo: the
        re-journal-first step named the newest batch as not restored, and that batch IS the owed card, which this press restores, so the
        feed parked a live card. A re-journaled id is left out of the batch the frame names."""
        self._two_fault_undo_leaves_b_owed()
        owed_file = jd.STATE / km.OWED_FILE
        orig_write = Path.write_text

        def refusing_write(p, *a, **kw):
            if p.name.startswith(owed_file.name) and p.name != owed_file.name:   # the atomic temp alone: a plain write on the final name goes through, so the atomic switch is guarded (the round-thirteen verifier)
                raise OSError(errno.EROFS, "Read-only file system", str(p))
            return orig_write(p, *a, **kw)
        with mock.patch.object(Path, "write_text", refusing_write):
            self._dispatch({"type": "undoClear"})           # B comes back; the note's rewrite refuses: the stale row stays on disk
        self.assertFalse(self._flag(B, B + ":g1"))
        km._rejournal_owed.clear(); km._owed_settled.clear()   # a restart: memory empty, the stale note on disk
        self._dispatch({"type": "askClear", "itemId": B + ":g1"})   # B re-cleared: the newest batch
        sent = self._dispatch({"type": "undoClear"})
        self.assertEqual([m for m in sent if m.get("type") == "err"], [], "the owed id is the newest batch too: restored this press, nothing named as parked")
        self.assertFalse(self._flag(B, B + ":g1"), "B is back")

    def test_an_unreadable_note_is_left_as_it_is_when_the_re_journal_lands(self):
        """The fourth review's third low: after an unreadable note a landed re-journal rewrote the note with a literal empty list, wiping rows
        memory never read (X on disk, the read refused: the note ended empty and X stayed flag-cleared with no ledger row). Nothing is
        rewritten after a refused read; the rows stay for the next read that lands, the settled id kept out of it."""
        self._two_fault_undo_leaves_b_owed()
        owed_file = jd.STATE / km.OWED_FILE
        X = "11111111-2222-3333-4444-999999999999:g7"       # a row an earlier life of the kernel owed: on disk, never in this memory
        owed_file.write_text(json.dumps({"id": X}) + "\n" + json.dumps({"id": B + ":g1"}) + "\n")
        orig_read = Path.read_text

        def refusing_read(p, *a, **kw):
            if p == owed_file:
                raise OSError(errno.EACCES, "Permission denied", str(p))
            return orig_read(p, *a, **kw)
        with mock.patch.object(Path, "read_text", refusing_read):
            sent = self._dispatch({"type": "undoClear"})    # memory owes B; the note cannot be read; the re-journal lands and B comes back
        self.assertEqual([m["title"] for m in sent if m.get("type") == "err"], ["romp could not read its note of earlier owed cards"])
        self.assertFalse(self._flag(B, B + ":g1"), "B came back")
        rows = [json.loads(l)["id"] for l in owed_file.read_text().splitlines() if l.strip()]
        self.assertEqual(rows, [X, B + ":g1"], "the note is not rewritten after a refused read: the unread row survives (before: an empty note)")
        self.assertEqual(km._owed_settled, {B + ":g1"}, "and B's stale row is kept out of the next read that lands")

    def test_a_peers_owing_between_the_notes_read_and_its_rewrite_waits_and_is_kept(self):
        """The fourth review's fourth low, the round-four verifier's medium: the lock covered each call, not the section, and the rewrite
        wrote a literal empty list, so a peer socket's persist between the read and the rewrite was truncated off disk (a restart then owed
        nothing and that card stayed flag-cleared with no ledger row). One lock spans the section, so the peer's persist waits for the
        rewrite, and the rewrite writes what is still owed."""
        import threading
        self._two_fault_undo_leaves_b_owed()
        owed_file = jd.STATE / km.OWED_FILE
        X = "11111111-2222-3333-4444-999999999999:g7"

        def peer():                                       # another socket's undo owing a new card: the note (the helper takes the lock), then memory
            km._owed_persist([X])
            km._rejournal_owed[X] = None
        t = threading.Thread(target=peer, daemon=True)
        orig_ids = km._cleared_ids
        seen = []

        def hooked(*a, **kw):                             # inside the section (the read done, the rewrite ahead): the peer arrives
            if not seen:
                seen.append(1)
                t.start(); t.join(0.4)
                seen.append(t.is_alive())
            return orig_ids(*a, **kw)
        with mock.patch.object(km, "_cleared_ids", hooked):
            sent = self._dispatch({"type": "undoClear"})
        t.join(5)
        self.assertEqual(seen, [1, True], "the peer's persist waited: one lock spans the read-modify-write (before: it landed between them)")
        self.assertFalse(t.is_alive())
        self.assertEqual([m for m in sent if m.get("type") == "err"], [])
        self.assertFalse(self._flag(B, B + ":g1"), "B came back")
        rows = [json.loads(l)["id"] for l in owed_file.read_text().splitlines() if l.strip()]
        self.assertEqual(rows, [X], "the peer's row is on disk after the rewrite (before: truncated off)")
        self.assertEqual(km._rejournal_owed, {X: None}, "and owed in memory")
        km._rejournal_owed.clear()

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


class UndoStackSequences(_World):
    """Round eight of PR 1967: the feed's Undo stack and the kernel's batches, equal by ENUMERATION rather than by the case a reviewer
    happens to try (rounds four to seven each found one stack residue). Two cards (A's and B's), the presses a page can make (Clear on a
    card, Clear all, Undo), and at each press the owed store (B's) landing or refusing at the flag step and the clears log landing,
    refusing every append, or refusing from the second append on (the shape that first leaves a card owed). Every kernel state reachable
    within DEPTH presses is expanded once; each transition records the frames the socket heard (the fields the feed reads), the cards
    visible after, and the kernel's stack after (_ledger_batches: the owed ids first, then the log's batches by stamp, newest first).
    tests/fixtures/undo-stack-transitions.json holds the table, and ui/webview/feed-render-incremental.test.ts replays every transition
    against the built feed, asserting after every press that the feed's stack (top first) equals the kernel's and that the board shows
    exactly the visible cards. This test regenerates the table and fails when the committed one differs (ROMP_WRITE_FIXTURES=1 rewrites
    it), so a kernel change that moves a frame or a batch is seen on both sides. Synthetic throughout: the placeholder sids, no paths."""
    DEPTH = 5
    ACTIONS = ("clearA", "clearB", "clearAll", "undo")
    STORE = ("lands", "refuses")
    LOG = ("lands", "refuses", "refuses2")
    FRAME_KEYS = ("type", "op", "ok", "sid", "itemId", "itemIds", "owedIds", "batches", "owedBatch", "batchesTotal", "title")

    def setUp(self):                                      # the acts class's world (its sessions, live map and app sink), without its tests
        super().setUp()
        sessions = [{"sid": A, "name": "web", "path": "/nonexistent/%s.jsonl" % A, "anchor": 0, "mtime": 0},
                    {"sid": B, "name": "api", "path": "/nonexistent/%s.jsonl" % B, "anchor": 0, "mtime": 0}]
        self.live = {A: _TM(), B: _TM()}
        self.app = []
        for p in (mock.patch.object(km, "_alive_sessions", lambda now, live_map: list(sessions)),
                  mock.patch.object(km, "_warm_fleet_bg", lambda now: None),
                  mock.patch.object(km, "_live_map", lambda: dict(self.live)),
                  mock.patch.object(km, "_send_to_app", lambda app, m: self.app.append((app, m))),
                  mock.patch.object(km, "_name_of", lambda sid: {A: "web", B: "api"}.get(sid)),
                  mock.patch.object(km.Sessions, "backend_for", staticmethod(lambda sid: mock.MagicMock()))):
            p.start()
            self.addCleanup(p.stop)
        km._rejournal_owed.clear(); km._owed_settled.clear(); km._owed_mem_only[0] = False
        getattr(km, "_owed_note_read", [False])[0] = False; getattr(km, "_owed_read_fault", [""])[0] = ""

    _dispatch = ActsUnderAFailedWrite._dispatch
    _flag = ActsUnderAFailedWrite._flag

    def _fresh(self):
        _World.tearDown(self); _World.setUp(self)           # a new state root with the two stores; the class's patches stay
        km._rejournal_owed.clear(); km._owed_settled.clear(); km._owed_mem_only[0] = False
        getattr(km, "_owed_note_read", [False])[0] = False; getattr(km, "_owed_read_fault", [""])[0] = ""

    def _visible(self):
        cur = km._cleared_ids()
        return [i for i in (A + ":g1", B + ":g1") if i not in cur and not self._flag(i.rsplit(":", 1)[0], i)]

    def _state_key(self):
        batches, owed, _total, _fault = km._ledger_batches()
        p = jd.STATE / km.OWED_FILE
        note = [json.loads(l)["id"] for l in p.read_text().splitlines() if l.strip()] if p.exists() else []
        return json.dumps({"batches": batches, "owed": owed, "flags": [i for i in (A + ":g1", B + ":g1") if self._flag(i.rsplit(":", 1)[0], i)],
                           "settled": sorted(km._owed_settled), "note": note, "memOnly": km._owed_mem_only[0]}, sort_keys=True)

    def _allowed(self, action, visible):
        return {"clearA": A + ":g1" in visible, "clearB": B + ":g1" in visible, "clearAll": bool(visible), "undo": True}[action]

    def _press(self, action, store, log):
        msg = {"clearA": {"type": "askClear", "itemId": A + ":g1"}, "clearB": {"type": "askClear", "itemId": B + ":g1"},
               "clearAll": {"type": "clearAll"}, "undo": {"type": "undoClear"}}[action]
        orig = km._mark_nodes_cleared

        def flag_step_under_fault(ids, value, **kw):
            with _fault_on(self.b_file):
                return orig(ids, value, **kw)
        with contextlib.ExitStack() as st:
            if store == "refuses":
                st.enter_context(mock.patch.object(km, "_mark_nodes_cleared", flag_step_under_fault))
            if log == "refuses":
                st.enter_context(_append_faults(jd.STATE / "cleared.jsonl"))
            elif log == "refuses2":
                st.enter_context(_nth_append_faults(jd.STATE / "cleared.jsonl", 2))
            sent = self._dispatch(msg)
        frames = []
        for m in sent:
            if m.get("type") not in ("err", "undoAck"):   # the accounts, the landed undo's ack among them (round fifteen); the build floor itself stays out of the table (the counter is process-global)
                continue
            f = {k: m[k] for k in self.FRAME_KEYS if k in m}
            f["text"] = "(the account's words: not part of the table)"   # the feed's err road needs a text; the words carry a fault copy
            frames.append(f)
        return frames

    def test_the_feeds_stack_equals_the_kernels_batches_after_every_press_by_enumeration(self):
        start = self._state_key()
        states = {start: {"witness": [], "batches": km._ledger_batches()[0], "visible": self._visible()}}
        transitions, frontier = [], [start]
        for _depth in range(self.DEPTH):
            grown = []
            for key in frontier:
                witness, visible = states[key]["witness"], states[key]["visible"]
                for action in self.ACTIONS:
                    if not self._allowed(action, visible):
                        continue
                    for store in self.STORE:
                        for log in self.LOG:
                            self._fresh()
                            for a, s, l in witness:
                                self._press(a, s, l)
                            self.assertEqual(self._state_key(), key, "the witness reaches its state again: presses are deterministic")
                            frames = self._press(action, store, log)
                            after = self._state_key()
                            t = {"from": key, "input": [action, store, log], "frames": frames, "after": km._ledger_batches()[0],
                                 "visible": self._visible(), "to": after}
                            transitions.append(t)
                            if after not in states:
                                states[after] = {"witness": witness + [[action, store, log]], "batches": t["after"], "visible": t["visible"]}
                                grown.append(after)
            frontier = grown
        self.assertGreater(len(states), 10, "an enumeration over more than a handful of states")
        table = {"cards": {"A": A + ":g1", "B": B + ":g1"}, "sids": {"A": A, "B": B}, "depth": self.DEPTH, "start": start,
                 "states": states, "transitions": transitions}
        lines = ["{", '"cards": %s,' % json.dumps(table["cards"]), '"sids": %s,' % json.dumps(table["sids"]), '"depth": %d,' % self.DEPTH,
                 '"start": %s,' % json.dumps(start), '"states": {']
        keys = list(states)
        for i, k in enumerate(keys):
            lines.append("%s: %s%s" % (json.dumps(k), json.dumps(states[k], sort_keys=True), "," if i < len(keys) - 1 else ""))
        lines += ["},", '"transitions": [']
        for i, t in enumerate(transitions):
            lines.append(json.dumps(t, sort_keys=True) + ("," if i < len(transitions) - 1 else ""))
        lines += ["]", "}"]
        text = "\n".join(lines) + "\n"
        path = Path(__file__).resolve().parent / "fixtures" / "undo-stack-transitions.json"
        if os.environ.get("ROMP_WRITE_FIXTURES") == "1":
            path.write_text(text)
        self.assertTrue(path.exists(), "the table is committed beside the tests (ROMP_WRITE_FIXTURES=1 writes it)")
        self.assertEqual(json.loads(path.read_text()), json.loads(text), "the committed table is what the kernel does now (ROMP_WRITE_FIXTURES=1 rewrites it)")


if __name__ == "__main__":
    unittest.main()
