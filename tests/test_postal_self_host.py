#!/usr/bin/env python3
"""The self-host safety net: neither the bus nor the kernel may ever declare a machine name that
fails _safe_id. Peers key the mail they hold FOR this machine by that name, as a path component —
so a kern.hostname stomped with junk (control bytes, 2026-08-11) used to HALF-break peering:
presence still crossed (PEER_STATE is a dict), but outbox_put on every peer refused the name, so
each reply parked "unreachable" forever with only a server-log line as trace — and _unique() baked
the junk into message ids, killing outbound the same way. self_host (bus) and _self_host (kernel)
now validate and fall back loudly: the platform's user-set machine name, else a minted id persisted
at the state root's self-host file, SHARED between the two daemons so the machine can never appear
under two names. peer_exchange_handle refuses an unkeyable declared name (guarding against
un-updated dialers) — but only AFTER _canon_peer_name, so the checked-in-alias fold keeps
self-healing.

Synthetic only — invented hostnames (TESTHOST, a control-byte junk form), hermetic temp state dir,
no real machine data.
"""
import os
import socket as _socket
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")

# Hermetic state dir BEFORE the loads: both daemons resolve their state root at import, and the
# minted-id file must land here — shared by the two module instances, never in real state.
# (ROMP_POSTAL_HOST / ROMP_HOST_NAME are deliberately NOT popped here: they are read at CALL time,
# other test modules set them at IMPORT time, and pytest imports every module before running any
# test — a module-level pop would erase theirs for the whole run. _HostnameSeams clears per test.)
STATE_HOME = os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
pm = SourceFileLoader("romp_postal_selfhost", os.path.join(BIN, "romp-postal-service")).load_module()
km = SourceFileLoader("romp_kernel_selfhost", os.path.join(BIN, "romp-kernel")).load_module()

JUNK = "TEST\x04HOST"          # a control byte mid-name, the 2026-08-11 shape — fails _safe_id


class _HostnameSeams(unittest.TestCase):
    """Shared seams: fake gethostname (the stdlib socket module is one object, shared by both
    loads), no platform name candidates unless a test supplies them, fallback caches reset — every
    test states its own hostname world and leaks nothing."""

    def setUp(self):
        self._env = {k: os.environ.pop(k, None) for k in ("ROMP_POSTAL_HOST", "ROMP_HOST_NAME")}
        self._gethostname = _socket.gethostname
        self._pc, self._kc = pm._host_name_candidates, km._host_name_candidates
        pm._host_name_candidates = km._host_name_candidates = lambda: []
        pm._self_host_fb = km._self_host_fb = None

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        _socket.gethostname = self._gethostname
        pm._host_name_candidates, km._host_name_candidates = self._pc, self._kc
        pm._self_host_fb = km._self_host_fb = None


class BusSelfHost(_HostnameSeams):
    def test_safe_hostname_passes_through_live(self):
        _socket.gethostname = lambda: "TESTHOST.local"
        self.assertEqual(pm.self_host(), "TESTHOST")
        _socket.gethostname = lambda: "TESTHOST2"
        self.assertEqual(pm.self_host(), "TESTHOST2", "a hostname fix lands with no restart")
        self.assertIsNone(pm._self_host_fb, "no fallback engages for a healthy name")

    def test_junk_falls_back_to_the_platform_machine_name(self):
        _socket.gethostname = lambda: JUNK
        pm._host_name_candidates = lambda: ["Test Person's Laptop!!"]
        self.assertEqual(pm.self_host(), "Test-Person-s-Laptop", "sanitized, never raw")
        self.assertTrue(pm._safe_id(pm.self_host()))

    def test_junk_mints_a_stable_persisted_id(self):
        _socket.gethostname = lambda: JUNK
        a = pm.self_host()
        self.assertTrue(pm._safe_id(a))
        self.assertEqual(a, pm.self_host(), "cached within the process")
        # A fresh load of the same bin (= a restarted bus) must resolve the SAME identity: peers
        # key our mailbox by this name, so a per-process id would strand mail on every restart.
        # Pin XDG to THIS module's state dir for the load — a later-imported test module may have
        # re-pointed the env at its own tempdir during collection (imports all run before tests).
        saved = os.environ.get("XDG_STATE_HOME")
        os.environ["XDG_STATE_HOME"] = STATE_HOME
        try:
            pm2 = SourceFileLoader("romp_postal_selfhost_reload",
                                   os.path.join(BIN, "romp-postal-service")).load_module()
        finally:
            os.environ["XDG_STATE_HOME"] = saved
        pm2._host_name_candidates = lambda: []
        pm2._self_host_fb = None
        self.assertEqual(pm2.self_host(), a, "the minted id is persisted, not per-process")

    def test_unique_mid_stays_path_safe(self):
        # Mids are path components at outbox_put on BOTH ends, so a junk hostname baked into them
        # killed outbound cross-host mail the same way the declared name killed inbound.
        _socket.gethostname = lambda: JUNK
        mid = pm._unique()
        self.assertTrue(pm._safe_id(mid), "the mid must survive the outbox path check")
        pm.outbox_put("TESTHOST", {"mid": mid, "body": "hi"})
        self.assertEqual((pm.outbox_get("TESTHOST", mid) or {}).get("body"), "hi")
        self.assertTrue(pm.outbox_del("TESTHOST", mid))


class ExchangeUnkeyableHostGate(_HostnameSeams):
    """peer_exchange_handle refuses a declared name that fails _safe_id — an un-updated dialer
    could still declare one — but only AFTER _canon_peer_name, so the checked-in-alias fold (the
    existing self-heal for a bus we already peer with under a dialable name) keeps working."""

    def setUp(self):
        super().setUp()
        self._peers, self._pstate = dict(pm.PEERS), dict(pm.PEER_STATE)
        self._agents = pm.local_agents
        pm.local_agents = lambda: []          # presence enumeration is not under test; stay hermetic

    def tearDown(self):
        pm.local_agents = self._agents
        pm.PEERS.clear(); pm.PEERS.update(self._peers)
        pm.PEER_STATE.clear(); pm.PEER_STATE.update(self._pstate)
        super().tearDown()

    def test_unkeyable_declared_host_is_refused_400(self):
        payload, status = pm.peer_exchange_handle({"host": JUNK, "proto": pm.PEER_PROTO})
        self.assertEqual(status, 400, "refuse whole — half-working (presence without replies) is worse")
        self.assertIn("error", payload)
        self.assertNotIn(JUNK, pm.PEER_STATE, "no half-registered row for an unkeyable name")

    def test_canon_fold_to_checked_in_alias_still_accepted(self):
        pm.PEERS["safealias"] = {"port": 1}                       # dialable: the kernel notified this alias
        pm.PEER_STATE["safealias"] = {"busId": "bus-11111111"}    # same bus, seen before under the alias
        payload, status = pm.peer_exchange_handle(
            {"host": JUNK, "busId": "bus-11111111", "proto": pm.PEER_PROTO})
        self.assertEqual(status, 200, "the alias fold self-heals ahead of the gate")
        self.assertIn("safealias", pm.PEER_STATE)
        self.assertNotIn(JUNK, pm.PEER_STATE)


class KernelSelfHost(_HostnameSeams):
    def test_env_override_wins(self):
        os.environ["ROMP_HOST_NAME"] = "TESTHOST"
        try:
            self.assertEqual(km._self_host(), "TESTHOST")
        finally:
            os.environ.pop("ROMP_HOST_NAME", None)

    def test_safe_hostname_passes_through_live(self):
        _socket.gethostname = lambda: "TESTHOST"
        self.assertEqual(km._self_host(), "TESTHOST")
        self.assertIsNone(km._self_host_fb, "no fallback engages for a healthy name")

    def test_junk_is_never_declared_and_kernel_matches_bus(self):
        _socket.gethostname = lambda: JUNK
        k = km._self_host()
        self.assertTrue(km._safe_id(k))
        self.assertNotIn("\x04", k)
        self.assertEqual(k, pm.self_host(),
                         "kernel and bus share the persisted identity — one machine, one name")


if __name__ == "__main__":
    unittest.main(verbosity=2)
