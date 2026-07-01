#!/usr/bin/env python3
"""A SLASH-COMMAND turn must NOT spawn a provisional placeholder card (the user 2026-06-29). The planner
SKIPS command segments (they never become goals), so they never get a `placement` — meaning a command-triggered
placeholder would hang forever (the JLD `/usage` case: a /usage with no output left an "analyzing usage" card
that never resolved). _provisional_card now drops command segments. Synthetic transcript only — placeholder
UUIDs, hostname TESTHOST, no real data.
"""
import json
import os
import tempfile
import time
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
km = SourceFileLoader("romp_kernel_provcmd", os.path.join(BIN, "romp-kernel")).load_module()

SID = "11111111-2222-3333-4444-555555555555"


def _iso(ep):
    import datetime
    return datetime.datetime.fromtimestamp(ep, tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


class ProvisionalCommand(unittest.TestCase):
    def _session(self, recs):
        td = tempfile.mkdtemp()
        p = os.path.join(td, SID + ".jsonl")
        open(p, "w").write("\n".join(json.dumps(r) for r in recs) + "\n")
        return {"path": p, "sid": SID, "name": "JLD"}

    def test_command_turn_gets_no_provisional_placeholder(self):
        now = int(time.time())
        # a bare /usage command (no output, no model work) — exactly JLD's stuck case
        s = self._session([{"type": "user", "timestamp": _iso(now - 5), "uuid": "c1", "parentUuid": None,
                            "message": {"role": "user", "content": "<command-name>/usage</command-name>"}}])
        card = km._provisional_card(s, "JLD", {"bg": "#fff", "fg": "#000"}, SID, True, now, store={})
        self.assertIsNone(card, "a slash-command turn never warrants a provisional placeholder")

    def test_a_real_prompt_still_gets_a_placeholder(self):
        now = int(time.time())
        # a genuine human prompt the planner hasn't placed yet → the placeholder SHOULD appear (control)
        s = self._session([{"type": "user", "timestamp": _iso(now - 5), "uuid": "u1", "parentUuid": None,
                            "promptSource": "typed",
                            "message": {"role": "user", "content": "Please refactor the auth module"}}])
        card = km._provisional_card(s, "JLD", {"bg": "#fff", "fg": "#000"}, SID, True, now, store={})
        self.assertIsNotNone(card, "a real unplaced human prompt still surfaces a placeholder")

    def test_a_followup_gets_no_provisional_placeholder(self):
        # a follow-up (carries the romp-goal-id marker) files UNDER its already-reopened target goal, so a
        # separate provisional card would just FLASH then vanish. No placeholder (the user 2026-07-01).
        now = int(time.time())
        body = "does the context look right?\n\n<!-- romp-goal-id: %s:g7 -->" % SID
        s = self._session([{"type": "user", "timestamp": _iso(now - 5), "uuid": "u1", "parentUuid": None,
                            "promptSource": "typed",
                            "message": {"role": "user", "content": body}}])
        card = km._provisional_card(s, "JLD", {"bg": "#fff", "fg": "#000"}, SID, True, now, store={})
        self.assertIsNone(card, "a follow-up reopens its target goal — no separate provisional flash")


if __name__ == "__main__":
    unittest.main()
