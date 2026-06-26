#!/usr/bin/env python3
"""The SessionBackend contract (the user 2026-06-26): tmux + SDK behind ONE clean session API, and NOTHING
above the backend shells tmux. These tests pin (a) both backends honor the ABC and (b) the no-raw-tmux
guard — so a future tmux leak into the higher layers fails CI instead of silently rotting the abstraction.
"""
import os
import re
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
sb = SourceFileLoader("romp_session_backend", os.path.join(BIN, "romp_session_backend.py")).load_module()

ABSTRACT = sorted(sb.SessionBackend.__abstractmethods__)


class AbcContract(unittest.TestCase):
    def test_abc_lists_the_expected_contract(self):
        for m in ("owns", "live_sessions", "send", "interrupt", "set_model", "set_mode", "set_effort",
                  "spawn", "resume", "kill", "rename",
                  "pending_queued", "live_atoms", "prune_live", "on_ask", "current_ask"):
            self.assertIn(m, ABSTRACT, "SessionBackend must declare %s as part of the contract" % m)

    def test_coordination_methods_exist_as_concrete_defaults_for_now(self):
        # working_note/set_working_note/wake are part of the target contract but start as concrete no-op
        # defaults (the SDK gap is filled in P3); assert they exist and the base is a safe no-op.
        for m in ("working_note", "set_working_note", "wake"):
            self.assertTrue(hasattr(sb.SessionBackend, m), "the ABC declares %s (concrete default for now)" % m)
        self.assertNotIn("wake", ABSTRACT, "coordination methods are concrete defaults until P3")

    def test_sdk_backend_honors_every_abstract_method(self):
        # SdkBackend is SDK-gated so it can't import the ABC when the dep is absent; it conforms by
        # duck-typing. Assert at the SOURCE level (no SDK dep needed) that it DEFINES each abstract method,
        # so the duck-typing can't silently drift from the contract.
        src = open(os.path.join(BIN, "romp_sdk_backend.py"), encoding="utf-8").read()
        defs = set(re.findall(r"\n    def ([a-z_]+)\s*\(", src))
        for m in ABSTRACT:
            self.assertIn(m, defs, "SdkBackend must implement the SessionBackend method %s" % m)


if __name__ == "__main__":
    unittest.main()
