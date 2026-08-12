#!/usr/bin/env python3
"""Postal addressing is LIVE-ONLY (the user 2026-06-29): the Romp Postal Service no longer
reaches outside the live fleet. find_sessions and revive_session are GONE, and a recipient
name resolves only to a currently-live session — there is no dead-session resurrection and
no parking mail for a session that isn't running. This pins that simplification so the
removed surfaces can't quietly creep back. No real session data here (synthetic UUIDs).
"""
import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
SKILL = os.path.join(ROOT, "claude", "skills", "romp-postal", "SKILL.md")

os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()      # hermetic; constants resolve under here at import
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
pm = SourceFileLoader("romp_postal", os.path.join(BIN, "romp-postal-service")).load_module()

ALPHA = "11111111-2222-3333-4444-555555555555"
GHOST = "99999999-8888-7777-6666-555555555555"


def _tool_names():
    return {t["name"] for t in pm.MCP_TOOLS}


def _set_live(rows):
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(rows, f)
    f.close()
    os.environ["ROMP_SESSIONS_FILE"] = f.name
    return f.name


class LiveOnlyAddressing(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("ROMP_SESSIONS_FILE", None)
        pm.HEARTBEATS.clear()

    def test_live_name_resolves(self):
        _set_live([{"id": ALPHA, "name": "alpha"}])
        self.assertEqual(pm._recip_id_for("alpha"), ALPHA)

    def test_unknown_name_is_unresolvable(self):
        _set_live([{"id": ALPHA, "name": "alpha"}])
        # a name no LIVE session has resolves to nothing — no dead-history fallback
        self.assertIsNone(pm._recip_id_for("ghost"))

    def test_uuid_without_mailbox_is_unresolvable(self):
        # live-only: a bare UUID that isn't live and has no in-flight mailbox does not resolve
        _set_live([{"id": ALPHA, "name": "alpha"}])
        self.assertIsNone(pm._recip_id_for(GHOST))

    def test_heartbeat_remote_resolves(self):
        # a heartbeating remote peer is LIVE for addressing purposes
        _set_live([])
        pm.HEARTBEATS[GHOST] = ("beta", pm.time.time())
        self.assertEqual(pm._recip_id_for("beta"), GHOST)


class RemovedSurfacesAreGone(unittest.TestCase):
    def test_removed_mcp_tools_absent(self):
        names = _tool_names()
        self.assertNotIn("find_sessions", names)
        self.assertNotIn("revive_session", names)

    def test_live_tools_still_present(self):
        names = _tool_names()
        for n in ("send_message", "check_inbox", "list_agents",
                  "set_working", "check_sent", "recall_message"):
            self.assertIn(n, names)

    def test_removed_functions_absent(self):
        for fn in ("_dead_id_for_name", "_revive", "_resolve_session",
                   "_find_sessions", "_session_records", "format_find"):
            self.assertFalse(hasattr(pm, fn), f"{fn} should be removed from the postal service")

    def test_instructions_are_live_only(self):
        ins = pm.MCP_INSTRUCTIONS.lower()
        self.assertNotIn("find_sessions", ins)
        self.assertNotIn("revive_session", ins)
        self.assertIn("live-only", ins)

    def test_skill_prose_is_live_only(self):
        with open(SKILL, encoding="utf-8") as f:
            text = f.read().lower()
        self.assertNotIn("find_sessions", text)
        self.assertNotIn("revive_session", text)
        self.assertIn("live-only", text)


if __name__ == "__main__":
    unittest.main()
