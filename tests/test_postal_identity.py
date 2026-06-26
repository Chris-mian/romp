#!/usr/bin/env python3
"""Postal must resolve THIS session's identity from CLAUDE_CODE_SESSION_ID (the harness's reliable
per-session fsid), NOT the tmux @romp-session-id var. The tmux var is wrong for an SDK (non-tmux) session
whose MCP is parented under a leftover tmux pane — the user 2026-06-24 hit this: an SDK session sitting in a
stale 'FRO' pane sent mail AS the isolated FRO session and was wrongly blocked as isolated, while the
timeline icon (keyed on the real fsid) correctly showed it un-isolated. Synthetic only — placeholder ids.
"""
import os
import unittest
from importlib.machinery import SourceFileLoader

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "bin")
pm = SourceFileLoader("romp_postal_id", os.path.join(BIN, "romp-postal-service")).load_module()

FSID = "11111111-2222-3333-4444-555555555555"


class SelfIdentity(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.get("CLAUDE_CODE_SESSION_ID")
        self._tmux = pm.tmux

    def tearDown(self):
        if self._env is None:
            os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
        else:
            os.environ["CLAUDE_CODE_SESSION_ID"] = self._env
        pm.tmux = self._tmux

    def test_my_id_prefers_the_env_over_the_tmux_var(self):
        os.environ["CLAUDE_CODE_SESSION_ID"] = FSID
        pm.tmux = lambda *a: "wrong-stale-pane-id"   # tmux would return a DIFFERENT session's id
        self.assertEqual(pm.my_id(), FSID)           # env wins → the real session, never the stale pane

    def test_my_id_falls_back_to_tmux_when_env_absent(self):
        os.environ.pop("CLAUDE_CODE_SESSION_ID", None)

        def fake_tmux(*a):
            if a[:2] == ("display-message", "-p"):
                return "somesess\n"
            if a and a[0] == "show":
                return "tmux-fallback-id\n"
            return ""
        pm.tmux = fake_tmux
        self.assertEqual(pm.my_id(), "tmux-fallback-id")

    def test_my_id_is_none_when_nothing_resolves(self):
        os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
        pm.tmux = lambda *a: ""                       # no tmux either
        self.assertIsNone(pm.my_id())


if __name__ == "__main__":
    unittest.main()
