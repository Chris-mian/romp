#!/usr/bin/env python3
"""find_sessions / revive_session are USER-INITIATED (the user 2026-06-25): a session shouldn't go
spelunking through the user's session history or wake a dead session on its own initiative — those
tools reach OUTSIDE the live fleet, so recruiting/reviving past work is the user's call. The prompt
surfaces (MCP server instructions, the two tool descriptions, and SKILL.md) must carry that guard;
in-fleet coordination (list_agents / send_message) stays unrestricted. No real session data here.
"""
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
SKILL = os.path.join(ROOT, "claude", "skills", "romp-postal", "SKILL.md")

os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()      # hermetic; constants resolve under here at import
pm = SourceFileLoader("romp_postal", os.path.join(BIN, "romp-postal-service")).load_module()


def _tool_desc(name):
    for t in pm.MCP_TOOLS:
        if t["name"] == name:
            return t["description"]
    raise AssertionError(f"no MCP tool named {name}")


class NoAutonomousRevive(unittest.TestCase):
    def test_server_instructions_warn_against_self_directed_recruiting(self):
        ins = pm.MCP_INSTRUCTIONS.lower()
        self.assertIn("find_sessions", ins)
        self.assertIn("revive_session", ins)
        # the restraint: only when the user asks; not a self-directed step
        self.assertIn("only when the user asks", ins)
        self.assertIn("outside your live fleet", ins)

    def test_find_sessions_description_is_user_gated(self):
        d = _tool_desc("find_sessions").lower()
        self.assertIn("only when the user asks", d)

    def test_revive_session_description_is_user_gated(self):
        d = _tool_desc("revive_session").lower()
        self.assertIn("only when the user asks", d)

    def test_live_peer_tools_stay_unrestricted(self):
        # the guard must NOT bleed onto in-fleet coordination tools
        for name in ("send_message", "list_agents"):
            self.assertNotIn("only when the user asks", _tool_desc(name).lower(),
                             f"{name} is normal in-fleet work — no user-gate")

    def test_skill_prose_carries_the_guard(self):
        with open(SKILL, encoding="utf-8") as f:
            text = f.read().lower()
        self.assertIn("don't recruit past sessions on your own", text)
        self.assertIn("find_sessions", text)
        self.assertIn("revive_session", text)


if __name__ == "__main__":
    unittest.main()
