#!/usr/bin/env python3
"""The /file preview endpoint (the user 2026-07-08): chat path-thumbnails
load real bytes from `GET /file?path=…`, existence- and extension-gated.

Drives the REAL Handler over HTTP (the test_kernel_ws_auth.py pattern). Synthetic only — temp files,
no session state touched.
"""
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")

# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
SourceFileLoader("romp_event_model", os.path.join(BIN, "romp-event-model")).load_module()
SourceFileLoader("romp_judge", os.path.join(BIN, "romp-judge")).load_module()
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "test-token-DO-NOT-USE")
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()

TOKEN = os.environ["ROMP_SERVE_TOKEN"]

# a 1x1 transparent PNG — real image bytes so the mime/type path is exercised end-to-end
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c626001000000ffff03000006000557bfabd40000000049454e44ae426082")


class FilePreviewEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), km.Handler)
        cls.port = cls.srv.server_address[1]
        cls.t = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.t.start()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.png = os.path.join(cls.tmp.name, "plot.png")
        with open(cls.png, "wb") as f:
            f.write(PNG)
        cls.txt = os.path.join(cls.tmp.name, "notes.txt")
        with open(cls.txt, "w") as f:
            f.write("not renderable")

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.tmp.cleanup()

    def _req(self, path, method="GET"):
        url = "http://127.0.0.1:%d%s%stoken=%s" % (self.port, path, "&" if "?" in path else "?", TOKEN)
        req = urllib.request.Request(url, method=method)
        try:
            with urllib.request.urlopen(req, timeout=3) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def test_serves_an_existing_image_with_its_mime(self):
        code, hdrs, body = self._req("/file?path=" + urllib.parse.quote(self.png))
        self.assertEqual(code, 200)
        self.assertEqual(hdrs.get("Content-Type"), "image/png")
        self.assertEqual(body, PNG)

    def test_missing_file_404s(self):
        code, _, _ = self._req("/file?path=" + urllib.parse.quote(os.path.join(self.tmp.name, "gone.png")))
        self.assertEqual(code, 404)

    def test_non_renderable_extension_404s(self):
        # the allowlist is RENDERABLE media only — a .txt (or anything else) never leaves the machine
        code, _, _ = self._req("/file?path=" + urllib.parse.quote(self.txt))
        self.assertEqual(code, 404)

    def test_relative_path_without_sid_404s(self):
        # unresolvable relative path (no session cwd) must not fall back to the kernel's own cwd
        code, _, _ = self._req("/file?path=plot.png")
        self.assertEqual(code, 404)

    def test_oversize_413s_rather_than_truncating(self):
        old = km._PREVIEW_MAX_BYTES
        km._PREVIEW_MAX_BYTES = len(PNG) - 1
        try:
            code, _, _ = self._req("/file?path=" + urllib.parse.quote(self.png))
            self.assertEqual(code, 413)
        finally:
            km._PREVIEW_MAX_BYTES = old

    def test_head_probe_reports_existence_without_the_bytes(self):
        # the client's PDF-chip probe: headers only (real Content-Length), no body download
        code, hdrs, body = self._req("/file?path=" + urllib.parse.quote(self.png), method="HEAD")
        self.assertEqual(code, 200)
        self.assertEqual(hdrs.get("Content-Length"), str(len(PNG)))
        self.assertEqual(body, b"")
        code, _, _ = self._req("/file?path=" + urllib.parse.quote(self.txt), method="HEAD")
        self.assertEqual(code, 404)


if __name__ == "__main__":
    unittest.main()
