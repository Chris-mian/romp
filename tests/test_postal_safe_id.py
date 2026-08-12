#!/usr/bin/env python3
"""Regression guard for the Romp Postal Service path-traversal hole (ids/names
arriving over the bus are used as path components under the mail/names roots).
The bus is token-gated now (test_postal_token.py), but these checks stay as
defense-in-depth: a crafted reference like `../../../etc` must be rejected
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
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
pm = SourceFileLoader("romp_postal", os.path.join(BIN, "romp-postal-service")).load_module()


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

    def test_recip_id_rejects_traversal(self):
        # /send reaches _recip_id_for; a traversal reference must not resolve to a
        # path component under the mail/names roots (the _safe_id guard rejects it).
        self.assertIsNone(pm._recip_id_for("../../../../etc/hosts"))

    def test_mailbox_refuses_unsafe(self):
        with self.assertRaises(ValueError):
            pm._mailbox("../../../tmp/evil")


class OutboxTraversal(unittest.TestCase):
    """The cross-host outbox keys files as OUTBOX/<host>/<mid>.json. Both host and mid arrive over the
    unauthenticated bus (a relay's `to`-route host and the peer-supplied `mid`), so a crafted `mid`
    like `../../../../foo` would escape OUTBOX and write attacker JSON anywhere (the H1 hole). All four
    path-builders must reject unsafe host/mid; a legit mid (`_unique()` form) must still round-trip."""

    def test_put_refuses_traversal_mid(self):
        tmp = tempfile.mkdtemp()
        target = os.path.join(tmp, "pwned")               # outbox_put appends ".json"
        rel = os.path.relpath(target, str(pm.OUTBOX / "TESTHOST"))  # ../../.../tmp/.../pwned — has "/"
        pm.outbox_put("TESTHOST", {"mid": rel, "body": "x"})
        self.assertFalse(os.path.exists(target + ".json"),
                         "a traversal mid must not write outside OUTBOX")

    def test_put_refuses_traversal_host(self):
        tmp = tempfile.mkdtemp()
        target = os.path.join(tmp, "pwned.json")
        pm.outbox_put(os.path.relpath(tmp, str(pm.OUTBOX)), {"mid": "px-1.2_3.TESTHOST", "body": "x"})
        self.assertFalse(os.path.exists(target), "a traversal host must not write outside OUTBOX")

    def test_get_and_del_refuse_traversal(self):
        self.assertIsNone(pm.outbox_get("TESTHOST", "../../../../etc/passwd"))
        self.assertFalse(pm.outbox_del("TESTHOST", "../../../../etc/passwd"))
        self.assertEqual(pm.outbox_list("../../../../etc"), [])

    def test_legit_mid_round_trips(self):
        mid = "px-1700000000.1234_567.TESTHOST"           # the _unique() shape: digits, ".", "_", host
        pm.outbox_put("TESTHOST", {"mid": mid, "body": "hi"})
        self.assertEqual((pm.outbox_get("TESTHOST", mid) or {}).get("body"), "hi")
        self.assertTrue(pm.outbox_del("TESTHOST", mid))


if __name__ == "__main__":
    unittest.main(verbosity=2)
