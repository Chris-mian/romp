#!/usr/bin/env python3
"""The modal's user "Resolve" override must survive the diary flip (found 2026-07-07): _resolve_node
wrote nodeComplete/blocked flags with NO diary event, so the rollup_status call inside the very same
function re-derived the flags from the (unchanged) log and REVERTED the user's own action — the resolve
was a silent no-op from the moment the log became the authority. It now records a user done verdict
first. XDG_STATE_HOME is pointed at a temp dir BEFORE the kernel loads. Synthetic fixtures only."""
import os
import tempfile
import time
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
_STATE_TMP = tempfile.mkdtemp()
os.environ["XDG_STATE_HOME"] = _STATE_TMP
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
kern = SourceFileLoader("romp_kernel_resolvenode", os.path.join(BIN, "romp-kernel")).load_module()
jd = kern.jd

SID = "11111111-2222-3333-4444-555555555555"
GID = SID + ":g1"
NOW = int(time.time())


class ResolveNode(unittest.TestCase):
    def test_user_resolve_is_evented_and_survives_the_rollup(self):
        store = {"rompUuid": SID, "seq": 1, "placements": {}, "status": {},
                 "nodes": {GID: {"id": GID, "text": "Ship the widget", "parentId": None,
                                 "nodeComplete": False, "blocked": True, "blockWhy": "pick a name",
                                 "cleared": False, "trail": [], "t": NOW - 600, "mt": NOW - 300}}}
        jd.rollup_status(store, False)
        jd.save_goals(SID, store)
        self.assertTrue(kern._resolve_node(SID, GID))

        st = jd.load_goals(SID)
        nd = st["nodes"][GID]
        self.assertTrue(nd["nodeComplete"], "the user's resolve holds through the in-call rollup")
        self.assertFalse(nd["blocked"])
        ev = [e for e in nd["log"] if e["kind"] == "done" and not e.get("synth")]
        self.assertEqual([e["src"] for e in ev], ["user"], "the resolve is a USER done verdict in the diary")
        jd.rollup_status(st, False)                    # and the NEXT pass cannot revert it either
        self.assertTrue(st["nodes"][GID]["nodeComplete"])


if __name__ == "__main__":
    unittest.main()
