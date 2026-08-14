#!/usr/bin/env python3
"""The /remote/<host>/file relay — previews for a FEDERATED session's mentioned paths.

A remote session's chat mentions paths on the REMOTE machine's disk, but a preview <img> can only
dial the origin that served the page — its /file hit the local kernel, read the local disk, 404'd,
and every mentioned plot/screenshot on a federated session silently hid itself (2026-07-31). The
kernel now relays: GET/HEAD /remote/<host>/file forwards the one request to the attached host's
kernel through the same ssh -L tunnel the /remote/<host>/ws splice uses, after the normal local
auth gate, rewriting the remote kernel's own token into the forwarded query so the per-host trust
boundary is unchanged (THAT kernel still runs its allowlist, size cap and path resolution).

These tests run the real Handler against a fake "remote kernel" (an HTTP server that answers
/file and records what it was asked). Synthetic only: host name `gpu1`, invented tokens, no
session state touched.
"""
import os
import socket
import threading
import unittest
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.machinery import SourceFileLoader
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")

# Mirror tests/test_kernel_ws_auth.py's load order. The token env keeps _load_token() away from
# the real state dir; NO_OPEN keeps the import from launching a browser.
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
SourceFileLoader("romp_event_model", os.path.join(BIN, "romp-event-model")).load_module()
SourceFileLoader("romp_judge", os.path.join(BIN, "romp-judge")).load_module()
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "test-token-DO-NOT-USE")
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()

REMOTE_TOKEN = "remote-token-DO-NOT-USE"
PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-png-bytes"
PY_BYTES = b"print('hello from the remote box')\n"


class _FakeRemoteFileHandler(BaseHTTPRequestHandler):
    """The attached host's kernel behind the ssh -L port, /file route only: serves PNG_BYTES for
    path=/tmp/plot.png and PY_BYTES for path=/tmp/app.py (recording the request lines), 404s
    anything else."""
    requests = []               # class-level: the recorded request lines
    ctype = "image/png"         # what this remote CLAIMS the bytes are (a hostile one lies)

    def _serve(self, head):
        _FakeRemoteFileHandler.requests.append(self.path)
        if "app.py" in self.path:
            self.send_response(200)
            self.send_header("Content-Type", _FakeRemoteFileHandler.ctype)
            self.send_header("Content-Length", str(len(PY_BYTES)))
            self.end_headers()
            if not head:
                self.wfile.write(PY_BYTES)
            return
        if "plot.png" not in self.path:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", _FakeRemoteFileHandler.ctype)
        self.send_header("Content-Length", str(len(PNG_BYTES)))
        self.end_headers()
        if not head:
            self.wfile.write(PNG_BYTES)

    def do_GET(self):
        self._serve(head=False)

    def do_HEAD(self):
        self._serve(head=True)

    def log_message(self, *a):  # keep the test output clean
        pass


class RemoteFileRelay(unittest.TestCase):
    def setUp(self):
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), km.Handler)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.fake = ThreadingHTTPServer(("127.0.0.1", 0), _FakeRemoteFileHandler)
        threading.Thread(target=self.fake.serve_forever, daemon=True).start()
        _FakeRemoteFileHandler.requests = []
        _FakeRemoteFileHandler.ctype = "image/png"
        self._saved_remotes = dict(km._remotes)

    def tearDown(self):
        with km._remotes_lock:
            km._remotes.clear()
            km._remotes.update(self._saved_remotes)
        for s in (self.srv, self.fake):
            s.shutdown()
            s.server_close()

    def _register(self, host, local_port, token=REMOTE_TOKEN):
        with km._remotes_lock:
            km._remotes[host] = {"host": host, "kernel_port": 29855, "local_port": local_port,
                                 "token": token, "status": "up"}

    def _get(self, path, token=True, method="GET"):
        req = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, path), method=method)
        if token:
            req.add_header("X-Romp-Token", km.TOKEN)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    def test_relays_the_bytes_and_rewrites_the_token(self):
        self._register("gpu1", self.fake.server_address[1])
        status, body, headers = self._get(
            "/remote/gpu1/file?path=%2Ftmp%2Fplot.png&sid=11111111-2222-3333-4444-555555555555"
            "&token=whatever-the-browser-sent")
        self.assertEqual(status, 200)
        self.assertEqual(body, PNG_BYTES, "the remote's bytes must pass through unmodified")
        self.assertEqual(headers.get("Content-Type"), "image/png")
        # the forwarded request: path /file, the REMOTE's token (not what the browser sent, and
        # never the local serve token), the sid + path intact
        (req,) = _FakeRemoteFileHandler.requests
        self.assertTrue(req.startswith("/file?"), req)
        self.assertIn("token=" + REMOTE_TOKEN, req)
        self.assertNotIn("whatever-the-browser-sent", req)
        self.assertNotIn(km.TOKEN, req)
        self.assertIn("path=%2Ftmp%2Fplot.png", req)
        self.assertIn("sid=11111111-2222-3333-4444-555555555555", req)

    def test_head_relays_the_verdict_without_a_body(self):
        # the PDF chip's existence probe: headers only, the remote's real length
        self._register("gpu1", self.fake.server_address[1])
        status, body, headers = self._get("/remote/gpu1/file?path=%2Ftmp%2Fplot.png", method="HEAD")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"")
        self.assertEqual(headers.get("Content-Length"), str(len(PNG_BYTES)))
        (req,) = _FakeRemoteFileHandler.requests
        self.assertTrue(req.startswith("/file?"), req)

    def test_remote_404_passes_through(self):
        # a deleted/hallucinated path: the REMOTE's 404 reaches the <img> so it hides itself
        self._register("gpu1", self.fake.server_address[1])
        status, _, _ = self._get("/remote/gpu1/file?path=%2Ftmp%2Fgone.png")
        self.assertEqual(status, 404)

    def test_text_relays_with_a_locally_derived_type_the_remote_cannot_override(self):
        """The text half of /file relays too — this gate predated it, so a remote session's
        .py/.md 404'd here while the LOCAL route served the same file (the viewer just failed
        on every federated text file). The defense is unchanged and now covers text: the type
        is OURS — a lying remote's text/html arrives as inert text/plain + nosniff."""
        self._register("gpu1", self.fake.server_address[1])
        _FakeRemoteFileHandler.ctype = "text/html"
        status, body, headers = self._get("/remote/gpu1/file?path=%2Ftmp%2Fapp.py")
        self.assertEqual(status, 200)
        self.assertEqual(body, PY_BYTES)
        self.assertEqual(headers.get("Content-Type"), "text/plain; charset=utf-8")
        self.assertNotIn("html", (headers.get("Content-Type") or "").lower())

    def test_unknown_host_404s(self):
        status, _, _ = self._get("/remote/nosuch/file?path=%2Ftmp%2Fplot.png")
        self.assertEqual(status, 404)
        self.assertEqual(_FakeRemoteFileHandler.requests, [])

    def test_unauthorized_403s_before_any_dial(self):
        self._register("gpu1", self.fake.server_address[1])
        status, _, _ = self._get("/remote/gpu1/file?path=%2Ftmp%2Fplot.png", token=False)
        self.assertEqual(status, 403, "the local auth gate must run before the relay")
        self.assertEqual(_FakeRemoteFileHandler.requests, [],
                         "an unauthorized request must never touch the tunnel")

    def test_dead_tunnel_502s(self):
        # a registered host whose forwarded port has no listener (the ssh died mid-flight)
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("127.0.0.1", 0))
        dead_port = probe.getsockname()[1]
        probe.close()
        self._register("gpu1", dead_port)
        status, _, _ = self._get("/remote/gpu1/file?path=%2Ftmp%2Fplot.png")
        self.assertEqual(status, 502)


if __name__ == "__main__":
    unittest.main()
