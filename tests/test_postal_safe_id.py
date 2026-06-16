#!/usr/bin/env python3
"""Regression guard for the Romp Postal Service path-traversal hole (the bus is
unauthenticated and ids/names arriving over it are used as path components under
the mail/names roots). A crafted reference like `../../../etc` must be rejected
before any path join, so it cannot read or clobber files outside those roots.

Synthetic only — placeholder UUIDs, hermetic temp state dir, no real session data.
"""
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")

# Hermetic state dir so exercising the bus never touches real mail.
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
pm = SourceFileLoader("romp_postal", os.path.join(BIN, "romp-postal")).load_module()


class SafeId(unittest.TestCase):
    def test_accepts_uuids_and_names(self):
        for ok in ("11111111-2222-3333-4444-555555555555", "my-session",
                   "feed_1", "abc123", "A.B-c_2"):
            self.assertTrue(pm._safe_id(ok), "should accept %r" % ok)

    def test_rejects_traversal_and_junk(self):
        for bad in ("../../../etc", "..", "a/b", "a\\b", "/etc/passwd",
                    ".hidden", "", "a\x00b", "x" * 200):
            self.assertFalse(pm._safe_id(bad), "should reject %r" % bad)


class TraversalAtSinks(unittest.TestCase):
    def test_read_box_rejects_traversal(self):
        # /inbox and /drain reach read_box; a traversal id must yield nothing,
        # never read another directory's `new/`.
        self.assertEqual(pm.read_box("../../../../etc", consume=False), [])

    def test_resolve_session_rejects_traversal(self):
        # revive_session reaches _resolve_session; a traversal target must not
        # resolve to an arbitrary file's contents.
        self.assertEqual(
            pm._resolve_session("../../../../etc/hosts"),
            (None, None, None, False))

    def test_mailbox_refuses_unsafe(self):
        with self.assertRaises(ValueError):
            pm._mailbox("../../../tmp/evil")


if __name__ == "__main__":
    unittest.main(verbosity=2)
