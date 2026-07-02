#!/usr/bin/env python3
"""Phase 2a — the kernel's SSH tunnel concierge for the federated dashboard. The kernel manages the
ssh -L/-R tunnels that let the browser reach a remote kernel (and remote sessions reach this bus),
reads ~/.ssh/config for the attach UI, and fetches the remote kernel's token. These tests drive the
real Handler with a MOCK ssh (no network): a `*serve-token*` command echoes a token; anything else
(the -N tunnel) blocks so the proc looks alive.

Synthetic only — hermetic temp STATE, placeholder hostnames/token, no real ssh.
"""
import http.client
import json
import os
import stat
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")

# Hermetic STATE (so remotes.json + serve-token never touch real state) BEFORE import, and a token so
# _load_token() returns early. NO_OPEN so importing never launches a browser. Mirrors test_kernel_ws_auth.
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "test-token-DO-NOT-USE")
SourceFileLoader("romp_event_model", os.path.join(BIN, "romp-event-model")).load_module()
SourceFileLoader("romp_judge", os.path.join(BIN, "romp-judge")).load_module()
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()

FAKE_TOKEN = "FAKETOKEN-123"
MOCK_SSH = """#!/usr/bin/env bash
for a in "$@"; do
  case "$a" in
    *serve-token*) echo "%s"; exit 0;;
  esac
done
sleep 20    # the -N tunnel: block so the proc looks alive
""" % FAKE_TOKEN


def _req(port, method, path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    c.request(method, path, data, headers)
    resp = c.getresponse()
    raw = resp.read()
    c.close()
    try:
        return resp.status, json.loads(raw.decode() or "{}")
    except Exception:
        return resp.status, raw.decode(errors="replace")


class TunnelConcierge(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.mkdtemp()
        ssh = os.path.join(self.td, "mock-ssh")
        with open(ssh, "w") as f:
            f.write(MOCK_SSH)
        os.chmod(ssh, os.stat(ssh).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        cfg = os.path.join(self.td, "ssh_config")
        with open(cfg, "w") as f:
            f.write("Host alpha\n  HostName 10.0.0.1\n\nHost beta gamma\n  User x\n\nHost *\n  ForwardAgent yes\n")
        km.SSH_BIN = ssh
        km.SSH_CONFIG = km.Path(cfg)
        km._remotes.clear()
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), km.Handler)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        for host in list(km._remotes):
            km.detach_remote(host)      # kills the mock proc
        km._remotes.clear()
        self.srv.shutdown()
        self.srv.server_close()

    def test_ssh_hosts_lists_concrete_config_aliases(self):
        status, body = _req(self.port, "GET", "/ssh-hosts")
        self.assertEqual(status, 200)
        hosts = body["hosts"]
        self.assertIn("alpha", hosts)
        self.assertIn("beta", hosts)
        self.assertIn("gamma", hosts)
        self.assertNotIn("*", hosts, "wildcard Host patterns are not connectable targets")

    def test_attach_fetches_token_and_spawns_tunnel(self):
        status, body = _req(self.port, "POST", "/tunnels", {"host": "testhost"})
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        t = body["tunnel"]
        self.assertEqual(t["host"], "testhost")
        self.assertEqual(t["token"], FAKE_TOKEN, "the remote serve-token must be fetched over ssh")
        self.assertGreater(t["localPort"], 0, "a local -L port must be allocated for the browser")
        self.assertIn(t["status"], ("authorizing", "connecting", "starting", "up"))
        self.assertTrue(km._tunnel_proc_alive(km._remotes["testhost"]), "the ssh tunnel proc must be running")

    def test_list_tunnels_includes_attached_host(self):
        _req(self.port, "POST", "/tunnels", {"host": "testhost"})
        status, body = _req(self.port, "GET", "/tunnels")
        self.assertEqual(status, 200)
        hosts = {t["host"]: t for t in body["tunnels"]}
        self.assertIn("testhost", hosts)
        self.assertEqual(hosts["testhost"]["token"], FAKE_TOKEN)

    def test_detach_kills_and_forgets(self):
        _req(self.port, "POST", "/tunnels", {"host": "testhost"})
        proc = km._remotes["testhost"]["proc"]
        status, body = _req(self.port, "POST", "/tunnels/detach", {"host": "testhost"})
        self.assertEqual(status, 200)
        self.assertTrue(body["detached"])
        self.assertNotIn("testhost", km._remotes)
        proc.wait(timeout=5)
        self.assertIsNotNone(proc.poll(), "the tunnel proc must be terminated on detach")
        _, body2 = _req(self.port, "GET", "/tunnels")
        self.assertNotIn("testhost", {t["host"] for t in body2["tunnels"]})

    def test_attach_requires_host(self):
        status, body = _req(self.port, "POST", "/tunnels", {})
        self.assertEqual(status, 400)


class HostForSidMap(unittest.TestCase):
    """The host↔sid map the wake-router (Phase 3) reads. Populated by the supervisor's poll; here we set it
    directly to pin the lookup."""
    def setUp(self):
        km._remotes.clear()

    def tearDown(self):
        km._remotes.clear()

    def test_host_for_sid_resolves_remote_else_none(self):
        km._remotes["gpu1"] = {"host": "gpu1", "kernel_port": 7433, "local_port": 9001,
                               "token": "t", "proc": None, "status": "up",
                               "detail": "", "sids": ["aaaa-1111"]}
        self.assertIs(km._host_for_sid("aaaa-1111"), km._remotes["gpu1"])
        self.assertIsNone(km._host_for_sid("local-only-sid"))


class _StubRemoteKernel(BaseHTTPRequestHandler):
    """Stands in for the remote kernel at the far end of the -L tunnel: records the forwarded /deliver."""
    received = []  # class-level capture: [(path, body)]

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}") if n else {}
        _StubRemoteKernel.received.append((self.path, body))
        out = json.dumps({"ok": True, "injected": True}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


class WakeRouter(unittest.TestCase):
    """Phase 3: the bus POSTs /deliver {id} to the LOCAL kernel; for a REMOTE session the kernel forwards the
    wake over that host's -L tunnel so the idle remote session starts immediately (not at its next turn)."""
    REMOTE_SID = "bbbb-2222-cccc-3333"

    def setUp(self):
        km._remotes.clear()
        _StubRemoteKernel.received = []
        # the "remote kernel" at the tunnel's far end
        self.remote = ThreadingHTTPServer(("127.0.0.1", 0), _StubRemoteKernel)
        self.remote_port = self.remote.server_address[1]
        threading.Thread(target=self.remote.serve_forever, daemon=True).start()
        # the local kernel under test
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), km.Handler)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        # register the remote, pointing its -L local_port at the stub, owning REMOTE_SID
        km._remotes["gpu1"] = {"host": "gpu1", "kernel_port": 7433, "local_port": self.remote_port,
                               "token": "", "proc": None, "status": "up", "detail": "",
                               "sids": [self.REMOTE_SID]}

    def tearDown(self):
        km._remotes.clear()
        self.srv.shutdown(); self.srv.server_close()
        self.remote.shutdown(); self.remote.server_close()

    def test_deliver_to_remote_sid_forwards_over_the_tunnel(self):
        status, body = _req(self.port, "POST", "/deliver", {"id": self.REMOTE_SID, "text": "DELEGATE: go"})
        self.assertEqual(status, 200)
        self.assertTrue(body["injected"], "the remote kernel's injected result must propagate back")
        self.assertEqual(len(_StubRemoteKernel.received), 1, "exactly one forwarded /deliver")
        path, fwd = _StubRemoteKernel.received[0]
        self.assertEqual(path, "/deliver")
        self.assertEqual(fwd, {"id": self.REMOTE_SID, "text": "DELEGATE: go"})

    def test_deliver_to_unknown_sid_does_not_forward(self):
        # a sid no remote owns is local: it must NOT be forwarded (it would inject locally — no session here,
        # but crucially the stub remote sees nothing).
        _req(self.port, "POST", "/deliver", {"id": "some-local-sid", "text": "hi"})
        self.assertEqual(_StubRemoteKernel.received, [], "a local sid must never forward to a remote kernel")


class ReapStrayTunnels(unittest.TestCase):
    """A kernel restart / re-attach used to leak a SECOND ssh -L tunnel (orphan reparented to init). Before
    spawning, _reap_stray_tunnels SIGTERMs orphans matching our exact signature for the host — and nothing
    else (not the user's own ssh, not a tunnel to another host, not ourselves)."""

    def test_kills_only_matching_orphan_tunnels(self):
        BUS = km.BUS_PORT
        fake_ps = "\n".join([
            "  12345 /usr/bin/ssh -N -T -L 50512:127.0.0.1:7433 -R %d:127.0.0.1:%d jetty" % (BUS, BUS),  # orphan → kill
            "  22222 ssh -N -T -L 9:127.0.0.1:7433 -R %d:127.0.0.1:%d otherhost" % (BUS, BUS),           # other host → keep
            "  33333 ssh jetty",                                                                          # user's own ssh → keep
            "  %d ssh -N -T -L 1:127.0.0.1:7433 -R %d:127.0.0.1:%d jetty" % (os.getpid(), BUS, BUS),      # us → keep
        ])

        class _R:
            stdout = fake_ps
        killed = []
        saved_run, saved_kill = km.subprocess.run, km.os.kill
        km.subprocess.run = lambda *a, **k: _R()
        km.os.kill = lambda pid, sig: killed.append((pid, sig))
        try:
            km._reap_stray_tunnels("jetty")
        finally:
            km.subprocess.run, km.os.kill = saved_run, saved_kill
        self.assertEqual(killed, [(12345, 15)], "only the jetty orphan tunnel is SIGTERM'd")


if __name__ == "__main__":
    unittest.main(verbosity=2)
