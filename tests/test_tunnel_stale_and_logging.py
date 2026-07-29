#!/usr/bin/env python3
"""A live ssh proc is not proof of a live tunnel, and every dial leaves a record (the user 2026-07-29).

A morning was lost to a host that would not come back after the laptop moved from ethernet to Wi-Fi,
while plain `ssh <host>` worked the entire time. Two things in here made that undiagnosable and then
unrecoverable:

  1. _spawn_tunnel sent ssh's stdout AND stderr to DEVNULL. The one line naming the cause of a failed
     dial was destroyed as it was printed, so afterwards nothing on the machine could say why.
  2. The supervisor re-dials only a DEAD proc. ssh answers a local connect from its own listener, so an
     ssh whose transport is gone is indistinguishable from a healthy tunnel with no romp behind it —
     the row sat at 'no-kernel' forever with no re-dial and no reap, and the panel offered only "Start",
     which says to go restart the REMOTE kernel. Worse, Try now called attach_remote, which spawned only
     when the proc was dead — so the button meant to break this wedge declined to act on exactly it.

The fix keys on the probe's SHAPE, which separates the two exactly: a far side that refused SPOKE (the
tunnel carries traffic, romp is genuinely absent), one that timed out never did (the path is gone).

Synthetic only — hermetic temp STATE, placeholder hostnames/tokens, no real ssh.
"""
import json
import os
import socket
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel_stale", os.path.join(BIN, "romp-kernel")).load_module()


class ProbeVerdict(unittest.TestCase):
    """_poll_remote_sids must say HOW it failed, not just that it did."""

    def _poll(self, port):
        r = {"host": "TESTHOST", "local_port": port, "token": ""}
        sids = km._poll_remote_sids(r)
        return sids, r.get("_probe")

    def test_a_far_side_that_refuses_is_recorded_as_refused_not_as_a_dead_path(self):
        # nothing listening → the connect is refused outright: this is what "no kernel over there" looks
        # like, and it must never be mistaken for a tunnel that stopped carrying traffic
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        sids, probe = self._poll(port)
        self.assertIsNone(sids)
        self.assertEqual(probe, "refused")

    def test_a_listener_that_never_answers_is_recorded_as_a_timeout(self):
        # accepts the connect, then says nothing — exactly how an ssh holding a forward over a dead
        # transport behaves, and the case that must trigger a re-dial
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        try:
            sids, probe = self._poll(port)
            self.assertIsNone(sids)
            self.assertEqual(probe, "timeout", "silence is a dead path, not a missing kernel")
        finally:
            srv.close()


class SupervisorActsOnTheVerdict(unittest.TestCase):
    """The kill is gated on the verdict, so a host whose romp is simply not running keeps its tunnel."""

    def setUp(self):
        import inspect as _i
        self.src = _i.getsource(km._tunnel_supervisor)

    def test_a_timed_out_no_kernel_row_is_killed_so_the_dead_proc_path_redials(self):
        self.assertIn('if st == "no-kernel" and r.get("_probe") == "timeout":', self.src,
                      "the stale-tunnel kill keys on the probe verdict, never on a timer or a counter")
        self.assertIn('r["proc"].terminate()', self.src)
        self.assertIn("stale-tunnel", self.src, "and it goes on the record")

    def test_the_kill_is_never_reached_on_a_refusal(self):
        # A refusal proves the tunnel carries traffic — churning its ssh would be pure damage, and would
        # re-dial every 15s forever against a box whose romp is deliberately off. So the ONLY terminate()
        # in the supervisor must sit under the timeout-qualified guard, not under the plain no-kernel
        # branch that writes the row's detail.
        lines = self.src.splitlines()
        guard = [i for i, ln in enumerate(lines) if 'st == "no-kernel" and r.get("_probe") == "timeout"' in ln]
        kills = [i for i, ln in enumerate(lines) if "terminate()" in ln]
        self.assertEqual(len(guard), 1, "one guard")
        self.assertEqual(len(kills), 1, "one kill")
        self.assertLess(guard[0], kills[0], "the kill is inside the guard")
        self.assertLess(kills[0] - guard[0], 6, "and directly under it, not in some later branch")
        plain = [i for i, ln in enumerate(lines) if 'elif st == "no-kernel"' in ln]
        self.assertTrue(plain and plain[0] > kills[0],
                        "the detail-only no-kernel branch comes after, and kills nothing")

    def test_a_dead_dial_is_logged_once_with_what_ssh_printed(self):
        self.assertIn('not r.get("_death_logged")', self.src, "once per death, not once per pass")
        self.assertIn('_tunnel_log(r["host"], "died"', self.src)
        self.assertIn("_forward_bind_failed(err)", self.src,
                      "a bind failure repeats forever unless the ports move")


class ForwardBindFailure(unittest.TestCase):
    def test_ssh_s_own_words_for_a_port_it_cannot_bind_are_recognised(self):
        for line in ("bind: Address already in use",
                     "Error: remote port forwarding failed for listen port 52025",
                     "channel_setup_fwd_listener_tcpip: cannot listen to port: 57946"):
            self.assertTrue(km._forward_bind_failed(line), line)

    def test_an_unrelated_failure_is_not_mistaken_for_one(self):
        for line in ("", "Permission denied (publickey).", "ssh: Could not resolve hostname TESTHOST",
                     "Timeout, server TESTHOST not responding."):
            self.assertFalse(km._forward_bind_failed(line), line)

    def test_reminting_moves_every_forwarded_port_off_the_one_that_collided(self):
        r = {"host": "TESTHOST", "local_port": 51000, "bus_port": 51001, "_peer_notified": (True, "trusted")}
        km._remint_forward_ports(r)
        self.assertNotEqual(r["local_port"], 51000)
        self.assertNotEqual(r["bus_port"], 51001)
        self.assertIsNone(r["_peer_notified"], "the bus holds a stale endpoint until it is re-notified")

    def test_reminting_a_checked_in_row_also_moves_its_reverse_ports_and_re_handshakes(self):
        r = {"host": "TESTHOST", "local_port": 51000, "bus_port": 51001, "checkin": True,
             "rk_port": 52025, "rb_port": 52026, "_handshook": 999}
        km._remint_forward_ports(r)
        self.assertNotEqual(r["rk_port"], 52025)
        self.assertNotEqual(r["rb_port"], 52026)
        self.assertNotIn("_handshook", r, "the hub must be told the new ports")


class DialLog(unittest.TestCase):
    def test_every_dial_and_death_is_appended_with_its_reason(self):
        km._tunnel_log("TESTHOST", "dial", pid=4242, fails=0, argv=["ssh", "-N", "--", "TESTHOST"])
        km._tunnel_log("TESTHOST", "died", code=255, stderr="bind: Address already in use", fails=1)
        rows = [json.loads(x) for x in km.TUNNEL_LOG.read_text().splitlines() if x.strip()]
        rows = [x for x in rows if x.get("host") == "TESTHOST"]
        self.assertEqual([x["event"] for x in rows][-2:], ["dial", "died"])
        self.assertEqual(rows[-1]["stderr"], "bind: Address already in use",
                         "the REASON is the whole point of the log")
        self.assertTrue(all("t" in x for x in rows), "each line is dated")

    def test_logging_never_raises_into_the_supervisor(self):
        # an unserialisable value must not take down the thread that is trying to reconnect you
        km._tunnel_log("TESTHOST", "dial", proc=object(), sock=socket.socket())

    def test_ssh_stderr_is_captured_to_a_file_rather_than_discarded(self):
        import inspect as _i
        src = _i.getsource(km._spawn_tunnel)
        self.assertIn("stderr=(errf or subprocess.DEVNULL)", src)
        self.assertNotIn("stderr=subprocess.DEVNULL", src,
                         "discarding it is what made the outage undiagnosable")

    def test_the_last_dial_s_words_are_readable_back_minus_ssh_s_advisory_chatter(self):
        km.TUNNEL_ERR_DIR.mkdir(parents=True, exist_ok=True)
        km._tunnel_err_path("TESTHOST").write_text(
            "Warning: Permanently added 'TESTHOST' to the list of known hosts.\n"
            "bind: Address already in use\n")
        err = km._tunnel_stderr("TESTHOST")
        self.assertIn("bind: Address already in use", err)
        self.assertNotIn("Permanently added", err, "advisories are not failure reasons")

    def test_a_host_name_can_never_escape_the_error_directory(self):
        p = km._tunnel_err_path("../../etc/passwd")
        self.assertEqual(p.parent, km.TUNNEL_ERR_DIR)


class TryNowActuallyDials(unittest.TestCase):
    def test_attach_redials_a_live_proc_whose_row_is_not_up(self):
        import inspect as _i
        src = _i.getsource(km.attach_remote)
        self.assertIn('elif r.get("status") != "up":', src,
                      "Try now on a wedged-but-alive tunnel used to do nothing at all")
        self.assertIn("forced-redial", src)
        self.assertIn('r["proc"].wait(timeout=3)', src,
                      "wait for the old ssh to exit, or the new dial dies on its listener")


if __name__ == "__main__":
    unittest.main()
