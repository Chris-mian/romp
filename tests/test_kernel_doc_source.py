#!/usr/bin/env python3
"""The /doc endpoint (the user 2026-08-14): the chat pane's review reader fetches a markdown doc's SOURCE
so a highlighted span can be anchored to a real line number, and its mtime so a file the agent edited under
you is called out before the comments are sent.

Text documents only, capped, and 413 rather than a silent truncation — half a doc would mis-number every
anchor below the cut. Drives the REAL Handler over HTTP (the test_kernel_preview.py pattern). Synthetic
only: temp files, no session state touched.
"""
import json
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

# Hermetic state BEFORE the loads — they resolve their state root at import time.
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)
SourceFileLoader("romp_event_model", os.path.join(BIN, "romp-event-model")).load_module()
SourceFileLoader("romp_judge", os.path.join(BIN, "romp-judge")).load_module()
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "test-token-DO-NOT-USE")
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()

TOKEN = os.environ["ROMP_SERVE_TOKEN"]
DOC = "# Rollout plan\n\nThe judge files a verdict per build.\n"


class DocSourceEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), km.Handler)
        cls.port = cls.srv.server_address[1]
        cls.t = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.t.start()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.md = os.path.join(cls.tmp.name, "plan.md")
        with open(cls.md, "w") as f:
            f.write(DOC)
        cls.py = os.path.join(cls.tmp.name, "secrets.py")
        with open(cls.py, "w") as f:
            f.write("TOKEN = 'nope'\n")

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

    def test_serves_the_source_text_and_its_mtime(self):
        code, hdrs, body = self._req("/doc?path=" + urllib.parse.quote(self.md))
        self.assertEqual(code, 200)
        self.assertEqual(hdrs.get("Content-Type"), "application/json")
        d = json.loads(body)
        self.assertEqual(d["text"], DOC)          # verbatim: the reader anchors comments to these lines
        self.assertEqual(d["path"], self.md)
        self.assertAlmostEqual(d["mtime"], os.path.getmtime(self.md), places=3)

    def test_a_non_document_extension_404s(self):
        # the allowlist is TEXT DOCUMENTS only — /doc is not a general file reader
        code, _, _ = self._req("/doc?path=" + urllib.parse.quote(self.py))
        self.assertEqual(code, 404)

    def test_missing_file_404s(self):
        code, _, _ = self._req("/doc?path=" + urllib.parse.quote(os.path.join(self.tmp.name, "gone.md")))
        self.assertEqual(code, 404)

    def test_relative_path_without_sid_404s(self):
        # an unresolvable relative path must not fall back to the kernel's own cwd
        code, _, _ = self._req("/doc?path=plan.md")
        self.assertEqual(code, 404)

    def test_relative_path_resolves_against_the_session_cwd(self):
        # the same resolution click-to-open uses: `plan.md` means the repo the agent runs in
        real = km._cwd_of
        km._cwd_of = lambda sid: self.tmp.name if sid == "sid-1" else None
        try:
            code, _, body = self._req("/doc?path=plan.md&sid=sid-1")
            self.assertEqual(code, 200)
            self.assertEqual(json.loads(body)["text"], DOC)
        finally:
            km._cwd_of = real

    def test_oversize_413s_rather_than_truncating(self):
        old = km._DOC_MAX_BYTES
        km._DOC_MAX_BYTES = len(DOC) - 1
        try:
            code, _, _ = self._req("/doc?path=" + urllib.parse.quote(self.md))
            self.assertEqual(code, 413)
        finally:
            km._DOC_MAX_BYTES = old

    def test_unauthorized_without_a_token(self):
        url = "http://127.0.0.1:%d/doc?path=%s" % (self.port, urllib.parse.quote(self.md))
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                self.fail("expected the serve-token gate to reject, got %d" % r.status)
        except urllib.error.HTTPError as e:
            self.assertIn(e.code, (401, 403))

    def test_undecodable_bytes_do_not_break_the_reader(self):
        p = os.path.join(self.tmp.name, "binary.md")
        with open(p, "wb") as f:
            f.write(b"# ok\n\xff\xfe not utf-8\n")
        code, _, body = self._req("/doc?path=" + urllib.parse.quote(p))
        self.assertEqual(code, 200)
        self.assertIn("# ok", json.loads(body)["text"])   # replaced, not a 500


if __name__ == "__main__":
    unittest.main()
