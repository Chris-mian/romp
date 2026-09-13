#!/usr/bin/env python3
"""T394 round one (2026-09-12): the chat's background box words the judge's verdict on a tracked task (kept running, not
waited on) only where the judge gave it. The kernel ships that verdict as launch ids, bgServiceIds, from _bg_split's
services (the closer audited past the launch without a wait), in every turn state, beside awaitingTaskIds (a wait's rows).
Synthetic fixtures only."""
import inspect
import os
import tempfile
import unittest
from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")

# Hermetic state BEFORE the loads — they resolve their state root at import time.
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)
os.makedirs(os.path.join(os.environ["XDG_STATE_HOME"], "romp"), exist_ok=True)
with open(os.path.join(os.environ["XDG_STATE_HOME"], "romp", "session-hosts"), "w") as _f:
    _f.write("off")   # a state root of our own: no real host for any session (the Testing rule)
load_source("romp_event_model", os.path.join(BIN, "romp-event-model"))
load_source("romp_judge", os.path.join(BIN, "romp-judge"))
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = load_source("romp_kernel_bgsvc", os.path.join(BIN, "romp-kernel"))

SID = "aaaaaaaa-1111-2222-3333-444444444444"
TASKS = [{"tid": "tu_cmd_1", "type": "shell", "desc": "Build the docs site"},
         {"tid": "tu_svc_1", "type": "shell", "desc": "Serve the docs preview"},
         {"tid": "tu_agent_1", "type": "agent", "desc": "Map the parser"},
         {"tid": "", "type": "shell", "desc": "a launch not yet placed"}]


class BgServiceIds(unittest.TestCase):
    def setUp(self):
        self._split, self._norm = km._bg_split, km._bg_live_norm
        km._bg_live_norm = lambda sid, path: list(TASKS)
        # the judge's split: the awaited launches and the services, as _bg_split answers it
        km._bg_split = lambda sid, path, tasks: ([t for t in tasks if t["tid"] in ("tu_cmd_1", "tu_agent_1", "")],
                                                 [t for t in tasks if t["tid"] == "tu_svc_1"])

    def tearDown(self):
        km._bg_split, km._bg_live_norm = self._split, self._norm

    def test_the_services_launch_ids_are_the_judges_furniture_verdict_and_nothing_else(self):
        self.assertEqual(km._bg_service_ids(SID, "/synthetic/path.jsonl"), ["tu_svc_1"])
        self.assertEqual(km._awaiting_task_ids(SID, "/synthetic/path.jsonl"), ["tu_cmd_1", "tu_agent_1"], "the awaited half, unchanged; an unplaced launch has no id")

    def test_the_status_ships_the_ids_in_every_turn_state(self):
        src = inspect.getsource(km.build_session)
        self.assertIn('"bgServiceIds": _bg_service_ids(sid, sess["path"], live_map),', src, "shipped unconditionally, beside the awaited ids, over the build's own liveness snapshot")
        self.assertIn('"awaitingTaskIds": (_awaiting_task_ids(sid, sess["path"]) if awaiting_why else []),', src, "the awaited ids still ride a wait only")


if __name__ == "__main__":
    unittest.main()
