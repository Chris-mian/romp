#!/usr/bin/env python3
"""GET /sessions is served from the cycle's snapshot (plans/sessions-route-from-the-cycle.md): the pusher's cycle builds the
listing once when its exact key moved (the live rows, the names snapshot, the working-notes store, the registry revision, the
compacting bits) and every request serves the kept JSON; a request before the first cycle builds once and is served from the
kept listing by the next; ?threads=1 rides its own key. The postal bus reads this route for its roster (list_agents, the
send's liveness check), so a session's start, rename and death reach the roster within one cycle, and the rows keep the
fields the bus reads. Hermetic: a temp state root, two synthetic sessions on disk, the live map stubbed."""
import http.client
import inspect
import json
import os
import re
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from romp_load import load_source
HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "test-token-DO-NOT-USE")
km = load_source("romp_kernel_sessions_listing", os.path.join(BIN, "romp-kernel"))
jd = km.jd
sb = load_source("romp_sdk_backend", os.path.join(BIN, "romp_sdk_backend.py"))   # the module name the kernel reads the revision through
NOW = 1781100000
SID = "11111111-2222-3333-4444-555555555555"
SID2 = "11111111-2222-3333-4444-565656565656"
BUS_FIELDS = {"id", "name", "state", "dir", "bg", "fg", "lastSid", "compacting", "working", "backend"}   # what the postal bus's
#                                                                                                          roster and the picker read


class _Listing(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        td = Path(self.td.name)
        self.saved = (jd.NAMES, jd.PROJECTS, jd.GOALDIR, jd.STATE, km.NAMES, km.WORKING_DIR, km.Sessions.live, km._sdk)
        names = td / "names"; names.mkdir()
        proj = td / "projects"; proj.mkdir()
        jd.NAMES, jd.PROJECTS = names, proj
        jd.GOALDIR = td / "goals"; jd.GOALDIR.mkdir()
        jd.STATE = td
        km.NAMES = names
        km.WORKING_DIR = td / "working"; km.WORKING_DIR.mkdir()
        km._sdk = lambda: None
        cdir = td / "work"; cdir.mkdir()
        self.cdir = cdir
        pdir = proj / jd.re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(str(cdir)))
        pdir.mkdir(parents=True)
        self.pdir, self.names = pdir, names
        rec = {"type": "user", "timestamp": "2026-06-11T00:00:00.000Z", "uuid": "u1", "parentUuid": None, "promptSource": "typed",
               "message": {"role": "user", "content": "hello there"}}
        for sid, name in ((SID, "web"), (SID2, "api")):
            (pdir / (sid + ".jsonl")).write_text(json.dumps(rec) + "\n")
            (names / sid).write_text("%s\t%s\t#abcdef\n" % (name, str(cdir)))
        meta = {"state": "waiting", "since": NOW - 5, "model": "", "effort": "", "context": None, "compactPct": None,
                "color": None, "mode": "", "backend": "sdk"}
        self.row = {SID: dict(meta), SID2: dict(meta)}
        km.Sessions.live = lambda: dict(self.row)
        self._reset()
        with km._clients_lock:
            self.saved_clients = list(km._clients); km._clients[:] = []

    def _reset(self):
        getattr(km, "_SESSIONS_LISTING", {}).update({"key": None, "rows": None, "json": None, "threads": None, "threadsKey": None,
                                                     "built": 0, "served": 0, "requestBuilt": 0, "missBy": {}})   # absent at the base

    def tearDown(self):
        (jd.NAMES, jd.PROJECTS, jd.GOALDIR, jd.STATE, km.NAMES, km.WORKING_DIR, km.Sessions.live, km._sdk) = self.saved
        with km._clients_lock:
            km._clients[:] = self.saved_clients
        self._reset()
        for slot in ("snapshot", "sessions", "paths", "names", "files_stat", "files_dirty"):
            setattr(km._live_scope, slot, None)
        self.td.cleanup()

    def _cycle(self):
        km._pusher_cycle()

    def _body(self, threads=False):
        serve = getattr(km, "_sessions_listing_serve", None)
        if serve is None:                                            # the base: the route builds per request
            return km._session_rows() + (km._thread_rows() if threads else [])
        return json.loads(serve(threads=threads))

    def _stats(self):
        L = getattr(km, "_SESSIONS_LISTING", {})
        return {k: L.get(k, 0) for k in ("built", "served", "requestBuilt")}, dict(L.get("missBy", {}))

    def _count_builds(self, builds):
        """A seam on the row builder: the cycle's (_session_rows_from) on the head, the request's (_session_rows) at the base."""
        name = "_session_rows_from" if hasattr(km, "_session_rows_from") else "_session_rows"
        real = getattr(km, name)
        setattr(km, name, (lambda live_map: (builds.append(1), real(live_map))[1]) if name == "_session_rows_from"
                else (lambda: (builds.append(1), real())[1]))
        return name, real


class OneListingPerChange(_Listing):
    def test_two_cycles_with_nothing_moved_build_once_and_serve_equal_bodies(self):
        builds = []
        name, real = self._count_builds(builds)
        try:
            self._cycle(); self._cycle(); self._cycle()
            a, b = self._body(), self._body()
        finally:
            setattr(km, name, real)
        self.assertEqual(len(builds), 1, "one build across three quiet cycles (the base built per request, never per cycle)")
        self.assertEqual(a, b)
        self.assertEqual({r["id"] for r in a}, {SID, SID2})
        st, miss = self._stats()
        self.assertEqual((st["built"], st["served"], st["requestBuilt"]), (1, 2, 0))
        self.assertEqual(miss, {"first": 1})
        for r in a:
            self.assertTrue(BUS_FIELDS <= set(r), "the fields the bus reads stand: %r" % sorted(r))

    def test_each_key_input_moving_rebuilds_once_and_the_served_row_carries_the_change(self):
        self._cycle()
        self.row[SID]["state"] = "working"                                           # a state change (the live row)
        self._cycle()
        self.assertEqual(next(r for r in self._body() if r["id"] == SID)["state"], "working")
        (self.names / SID).write_text("web-two\t%s\t#abcdef\n" % str(self.cdir))     # a rename (the names snapshot)
        self._cycle()
        self.assertEqual(next(r for r in self._body() if r["id"] == SID)["name"], "web-two")
        (km.WORKING_DIR / SID2).write_text("editing the listing")                    # a working note (the notes store)
        self._cycle()
        self.assertEqual(next(r for r in self._body() if r["id"] == SID2)["working"], "editing the listing")
        sb.write_reg(str(jd.STATE), SID, {"sid": SID, "alive": True, "lastSid": SID2})   # a registry write (lastSid rides it)
        self._cycle()
        st, miss = self._stats()
        self.assertEqual(st["built"], 5, "one build per moved input: %r" % (miss,))
        self.assertEqual(set(miss), {"first", "rows", "names", "notes", "registry"}, "each miss names its input: %r" % miss)
        self._cycle()
        self.assertEqual(self._stats()[0]["built"], 5, "and a quiet cycle builds nothing")

    def test_a_start_a_rename_and_a_death_reach_the_roster_within_one_cycle(self):
        """The postal bus's roster (list_agents, the send's liveness check) reads this route: a session that started is
        listed after one cycle, a renamed one carries its name, a dead one is gone (absence reads as death downstream)."""
        del self.row[SID2]
        self._cycle()
        self.assertEqual({r["id"] for r in self._body()}, {SID})
        self.row[SID2] = dict(self.row[SID])                                          # the start
        self._cycle()
        self.assertEqual({r["id"] for r in self._body()}, {SID, SID2})
        del self.row[SID]                                                             # the death
        self._cycle()
        self.assertEqual({r["id"] for r in self._body()}, {SID2})

    def test_a_request_before_the_first_cycle_builds_once_and_is_served_from_the_kept_listing_by_the_next(self):
        builds = []
        name, real = self._count_builds(builds)
        try:
            a = self._body(); b = self._body()
            self.assertEqual(len(builds), 1, "one build, from the registry (no cycle yet), served to both requests (the base built twice)")
            self._cycle()
            self.assertEqual(len(builds), 2, "the first cycle rebuilds under its key from its snapshot")
            self.assertEqual(self._body(), a)
        finally:
            setattr(km, name, real)
        st, _ = self._stats()
        self.assertEqual((st["requestBuilt"], st["built"]), (1, 1))

    def test_the_route_serves_the_kept_json_and_threads_ride_their_own_key(self):
        self._cycle()
        srv = ThreadingHTTPServer(("127.0.0.1", 0), km.Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            def get(path):
                c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
                c.request("GET", path, headers={"X-Romp-Token": km.TOKEN})
                resp = c.getresponse(); body = resp.read().decode(); c.close()
                return resp.status, body
            status, body = get("/sessions")
            self.assertEqual(status, 200)
            self.assertEqual(body, getattr(km, "_SESSIONS_LISTING", {}).get("json"), "the kept JSON, byte for byte (the base keeps none)")
            self.assertEqual({r["id"] for r in json.loads(body)}, {SID, SID2})
            status, body = get("/sessions?threads=1")
            self.assertEqual(status, 200)
            rows = json.loads(body)
            self.assertIsInstance(rows, list)
            self.assertEqual({r["id"] for r in rows}, {SID, SID2}, "no thread sessions: the same rows")
        finally:
            srv.shutdown(); srv.server_close()

    def test_the_registry_revision_moves_on_the_one_write_path_and_every_writer_goes_through_it(self):
        src = inspect.getsource(sb)
        self.assertIn("REG_REV[0] += 1", inspect.getsource(sb.write_reg), "the write path bumps the revision (the base has none)")
        rev = getattr(sb, "reg_rev", lambda: 0)
        rev0 = rev()
        sb.write_reg(str(jd.STATE), SID2, {"sid": SID2, "alive": True})
        self.assertEqual(rev(), rev0 + 1)
        writers = [m.start() for m in re.finditer(r"\bwrite_reg\(", src)]
        self.assertGreaterEqual(len(writers), 10, "the registry's writers all call write_reg")
        for m in re.finditer(r"_reg_path\([^)]*\)", src):
            tail = src[m.end():m.end() + 200]
            self.assertNotRegex(tail, r"\.write_text\(|os\.replace\(|\.unlink\(",
                                "a registration file written or removed outside write_reg at offset %d" % m.start())


if __name__ == "__main__":
    unittest.main()
