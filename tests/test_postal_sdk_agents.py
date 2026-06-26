#!/usr/bin/env python3
"""SDK-backed (non-tmux) sessions must be VISIBLE + reachable to the Romp Postal Service (the user via ui,
2026-06-26). local_agents() enumerated ONLY tmux sessions, so an SDK session had no row → list_agents
omitted it and a send to it resolved the recipient as DEAD and PARKED instead of delivering, even though
the session was open. local_agents() now merges alive SDK registry entries (~/.local/state/romp/sdk/*.json).
Delivery is on-disk + tmux-free, so enumeration is the whole fix for the parking. Synthetic only —
placeholder UUIDs, hostname-free.
"""
import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()      # hermetic; constants resolve under here at import
pm = SourceFileLoader("romp_postal", os.path.join(BIN, "romp-postal")).load_module()

SID = "11111111-2222-3333-4444-555555555555"


class SdkAgentsVisibleToPostal(unittest.TestCase):
    def setUp(self):
        self._tmux = pm.tmux
        pm.tmux = lambda *a, **k: ""                    # no tmux sessions in the test → local_agents = SDK only
        pm.SDKDIR.mkdir(parents=True, exist_ok=True)
        pm.STATESDIR.mkdir(parents=True, exist_ok=True)
        self._reg = pm.SDKDIR / (SID + ".json")
        self._reg.write_text(json.dumps({"sid": SID, "name": "sdksess", "cwd": "/work/dir", "alive": True}))
        (pm.STATESDIR / (SID + ".jsonl")).write_text(json.dumps({"t": 1, "state": "waiting"}) + "\n")

    def tearDown(self):
        pm.tmux = self._tmux
        for p in (self._reg, pm.STATESDIR / (SID + ".jsonl")):
            try:
                p.unlink()
            except OSError:
                pass

    def test_alive_sdk_session_is_a_live_local_agent(self):
        a = {x["id"]: x for x in pm.local_agents()}.get(SID)
        self.assertIsNotNone(a, "an alive SDK-backed session must be a live postal agent (else sends park)")
        self.assertEqual(a["name"], "sdksess")
        self.assertEqual(a["dir"], "/work/dir")
        self.assertEqual(a["state"], "waiting")     # read from states/<sid>.jsonl
        self.assertFalse(a["remote"])

    def test_send_resolves_an_sdk_session_ALIVE_not_parked(self):
        sid, name, d, alive = pm._resolve_session("sdksess")
        self.assertEqual(sid, SID)
        self.assertTrue(alive, "a send to an open SDK session must resolve ALIVE (deliver), not dead (park)")

    def test_dead_sdk_session_is_not_a_live_agent(self):
        self._reg.write_text(json.dumps({"sid": SID, "name": "sdksess", "cwd": "/work/dir", "alive": False}))
        self.assertNotIn(SID, {x["id"] for x in pm.local_agents()})

    def test_same_id_in_both_sources_is_not_duplicated(self):
        pm.tmux = lambda *a, **k: "1|sdksess|%s|||working" % SID   # hypothetically also a tmux row
        ids = [x["id"] for x in pm.local_agents()]
        self.assertEqual(ids.count(SID), 1, "a session in both tmux + SDK sources must appear once")


if __name__ == "__main__":
    unittest.main()
