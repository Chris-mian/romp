#!/usr/bin/env python3
"""The bus's live-push (auto-wake on deliver) goes through the kernel (POST /deliver), not a tmux pane-inject
(the user 2026-06-26): drain the maildir, hand the banner to the kernel, and put the mail BACK if the kernel
didn't inject — so the maildir-drain stays the backstop and the bus never shells tmux. Synthetic only.
"""
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
pm = SourceFileLoader("romp_postal_delivery", os.path.join(BIN, "romp-postal-service")).load_module()


class PushThroughKernel(unittest.TestCase):
    def setUp(self):
        self._seam = os.environ.pop("ROMP_SESSIONS_FILE", None)   # not a seam test: let _push actually run
        self.saved = (pm._drain, pm._kernel_post, pm.deliver, pm._push_disabled)
        self.posted, self.redelivered = [], []
        pm._push_disabled = lambda: False
        pm._drain = lambda sid: {"messages": [{"from": "alpha", "from_id": "uuid-a", "body": "hi"}]}
        pm.deliver = lambda sid, frm, frm_id, body, **k: self.redelivered.append((sid, body))

    def tearDown(self):
        if self._seam is not None:
            os.environ["ROMP_SESSIONS_FILE"] = self._seam
        pm._drain, pm._kernel_post, pm.deliver, pm._push_disabled = self.saved

    def test_injected_consumes_and_returns_true(self):
        pm._kernel_post = lambda path, body, timeout=2: (self.posted.append((path, body)),
                                                         {"ok": True, "injected": True})[1]
        self.assertTrue(pm._push("sid-b", {"id": "sid-b", "state": "idle"}))
        self.assertEqual(self.posted[0][0], "/deliver")
        self.assertEqual(self.posted[0][1]["id"], "sid-b")
        self.assertTrue(self.posted[0][1]["text"], "the banner text is handed to the kernel")
        self.assertEqual(self.redelivered, [], "injected → nothing put back")

    def test_not_injected_redelivers_for_the_drain(self):
        pm._kernel_post = lambda path, body, timeout=2: {"ok": True, "injected": False}
        self.assertFalse(pm._push("sid-b", {"id": "sid-b", "state": "idle"}))
        self.assertEqual(self.redelivered, [("sid-b", "hi")], "not injected → mail put back for the drain")

    def test_unreachable_kernel_redelivers(self):
        pm._kernel_post = lambda path, body, timeout=2: None
        self.assertFalse(pm._push("sid-b", {"id": "sid-b", "state": "idle"}))
        self.assertEqual(self.redelivered, [("sid-b", "hi")])

    def test_skips_not_ready_local_without_draining(self):
        pm._kernel_post = lambda *a, **k: self.fail("must not POST for a skipped session")
        pm._drain = lambda sid: self.fail("must not drain a skipped session")
        self.assertFalse(pm._push("sid-b", {"id": "sid-b", "state": "permission"}))
        self.assertEqual(self.redelivered, [])

    def test_remote_agent_is_woken_through_the_kernel(self):
        # A REMOTE (federated) peer has no local 'state' here; _push must still POST /deliver so the local
        # kernel's wake-router forwards it over the host's -L tunnel to the owning kernel. (Regression: the
        # bus used to SKIP remote agents, so an idle remote peer could never be woken cross-machine.)
        self.posted = []
        pm._kernel_post = lambda path, body, timeout=2: (self.posted.append((path, body)),
                                                         {"ok": True, "injected": True})[1]
        self.assertTrue(pm._push("sid-r", {"id": "sid-r", "remote": True}))
        self.assertEqual(self.posted[0][0], "/deliver")
        self.assertEqual(self.posted[0][1]["id"], "sid-r")

    def test_heartbeat_records_remote_but_ignores_local(self):
        # Only sids the local kernel does NOT own get remote-presence; a local session is already visible via
        # /sessions and must not linger as a phantom [remote] after it dies.
        saved = pm.local_agents
        pm.local_agents = lambda: [{"id": "local-1", "name": "mysess"}]
        try:
            pm.HEARTBEATS.clear()
            pm._record_heartbeat("11111111-2222-3333-4444-555555555555", "remotetest")   # not local → recorded
            pm._record_heartbeat("local-1", "mysess")                                    # local → ignored
            self.assertIn("11111111-2222-3333-4444-555555555555", pm.HEARTBEATS)
            self.assertNotIn("local-1", pm.HEARTBEATS)
        finally:
            pm.local_agents = saved
            pm.HEARTBEATS.clear()

    def test_source_uses_the_kernel_deliver_not_a_tmux_inject(self):
        src = open(os.path.join(BIN, "romp-postal-service"), encoding="utf-8").read()
        self.assertIn('_kernel_post("/deliver"', src, "the live-push wakes via the kernel")
        self.assertNotIn("paste-buffer", src, "no tmux pane-inject remains in the bus")
        self.assertNotIn("capture-pane", src, "no tmux pane-capture remains in the bus")


if __name__ == "__main__":
    unittest.main()
