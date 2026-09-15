"""One client-diag row per socket the kernel accepts (2026-09-15).

The kernel kept no durable record of page connections: an empty client-diag.jsonl read as a broken breadcrumb sink when
no browser had been on a page this kernel serves, and a count of GET /ws per app read as the attached dashboard's panes
when they may have been another kernel's federation relay dials. _note_ws_open files one `wsopen` row (surface kernel)
right after _register_ws_client: the app, the dashboard id, the shim's reconnect term, and the client's kind, decided once
at the handshake by _dial_kind(headers, query), the tell the connect-push split reads too, by the terms that decide it:
relay when the dial states relay=1 (the term the federation splice writes into the query it forwards); page when it
carries an Origin or a User-Agent header (a browser carries both, a CLI such as curl a User-Agent); page when it carries
neither term nor header and no instance id (the VS Code extension host dials from Node's ws client, which sends no
Origin and no User-Agent, without the shim); relay otherwise (a shim's instance id forwarded by a hub kernel older than
the relay term). The hub side of a spliced /remote/HOST/ws upgrade files its own row, kind hub, naming the host. A row
that cannot be written is said on stderr once.

Pins: the tell on header and term shapes, the ws npm client's shape among them; the helper's row, through the same
capture tests/test_chat_window_spans.py uses for the kernel's other row, and the once-said failure; the handler end to
end, real upgrades with a browser's headers, with the extension host's bare headers and terms, and through a splice
between two hermetic kernels (the hub's row and the remote's relay row), read back from the run's
client-diag.jsonl by their dashboard ids. Synthetic: an ephemeral server on the loopback, the run's own state root.
"""
import base64
import io
import json
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
import uuid
from http.server import ThreadingHTTPServer
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from romp_load import load_source  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, "bin")
# Hermetic state BEFORE the load: the kernel resolves its state root at import time, and only pytest runs conftest's
# floor (a bare run would write real state); the isolation pin, tests/test_state_isolation_order.py, holds this order.
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "test-token-DO-NOT-USE")
km = load_source("romp_kernel_wsopen_row", os.path.join(BIN, "romp-kernel"))


def _upgrade(port, path, origin=None, timeout=3.0, extensions=False):
    """One raw WebSocket upgrade, the socket kept open; returns (status, socket)."""
    key = base64.b64encode(os.urandom(16)).decode()
    lines = ["GET %s HTTP/1.1" % path, "Host: 127.0.0.1:%d" % port, "Upgrade: websocket", "Connection: Upgrade",
             "Sec-WebSocket-Key: %s" % key, "Sec-WebSocket-Version: 13"]
    if origin is not None:
        lines.append("Origin: %s" % origin)
    if extensions:
        lines.append("Sec-WebSocket-Extensions: permessage-deflate; client_max_window_bits")   # what Node's ws client adds
    s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
    s.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = s.recv(4096)
        if not chunk:
            break
        buf += chunk
    first = buf.split(b"\r\n", 1)[0].decode("latin-1")
    parts = first.split(" ", 2)
    return (int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else -1), s


def _rows_for(wids, deadline_s=5.0, expect=None):
    """The wsopen rows carrying these dashboard ids, read from the run's client-diag.jsonl within the deadline."""
    fp = km.jd.STATE / "client-diag.jsonl"
    end = time.time() + deadline_s
    while True:
        got = []
        if fp.exists():
            with open(fp, encoding="utf-8") as f:
                for ln in f:
                    try:
                        r = json.loads(ln)
                    except ValueError:
                        continue
                    if r.get("what") == "wsopen" and r.get("wid") in wids:
                        got.append(r)
        if len(got) >= (expect if expect is not None else len(wids)) or time.time() >= end:
            return got
        time.sleep(0.05)


class WsOpenRow(unittest.TestCase):
    def test_the_tell_by_its_terms_relay_term_then_headers_then_the_instance_id(self):
        ext = {"app": ["chat"], "wid": ["vscode-session"], "token": ["t"]}   # the extension host's dial: app, wid, token, nothing else
        shim = {"app": ["chat"], "wid": ["w"], "iid": ["page-instance"], "delta": ["1"], "token": ["t"]}   # a shim's dial
        self.assertEqual(km._dial_kind({}, dict(shim, relay=["1"])), "relay", "the splice's term decides first")
        self.assertEqual(km._dial_kind({"Origin": "http://127.0.0.1:1", "User-Agent": "Mozilla/5.0"}, dict(shim, relay=["1"])), "relay", "…over any header")
        self.assertEqual(km._dial_kind({"Origin": "http://127.0.0.1:1", "User-Agent": "Mozilla/5.0"}, shim), "page", "a browser's upgrade")
        self.assertEqual(km._dial_kind({"Origin": "vscode-webview://x"}, shim), "page", "an Origin alone")
        self.assertEqual(km._dial_kind({"User-Agent": "curl/8.5.0"}, {"app": ["chat"]}), "page", "a CLI carries a User-Agent: page, not a relay")
        self.assertEqual(km._dial_kind({}, ext), "page", "the ws npm client's dial: no Origin, no User-Agent, no instance id: the extension host")
        self.assertEqual(km._dial_kind({"Upgrade": "websocket", "Sec-WebSocket-Key": "k", "Sec-WebSocket-Extensions": "permessage-deflate"}, ext), "page",
                         "…whatever WebSocket headers the client adds")
        self.assertEqual(km._dial_kind({}, shim), "relay", "no term, no header, the shim's instance id forwarded: a hub kernel older than the term")

    def test_the_helper_files_one_row_with_app_wid_kind_and_reconnect(self):
        rows = []
        with mock.patch.object(km, "_client_diag_append", lambda fp, line: rows.append((fp.name, json.loads(line)))):
            self.assertTrue(km._note_ws_open({"app": "feed", "wid": "w1", "iid": "i1", "cid": "c1", "kind": "page"}, reconnect=True, now=1700000000))
            self.assertTrue(km._note_ws_open({"app": "chat", "wid": "w2", "iid": "", "cid": "c2", "kind": "hub", "host": "TESTHOST"}, now=1700000001))
        self.assertEqual(rows, [("client-diag.jsonl", {"t": 1700000000, "wid": "w1", "surface": "kernel", "what": "wsopen",
                                                       "data": {"app": "feed", "kind": "page", "reconnect": True, "iid": True, "cid": "c1"}}),
                                ("client-diag.jsonl", {"t": 1700000001, "wid": "w2", "surface": "kernel", "what": "wsopen",
                                                       "data": {"app": "chat", "kind": "hub", "reconnect": False, "iid": False, "cid": "c2", "host": "TESTHOST"}})],
                         "the host only on a hub row")

    def test_a_row_that_cannot_be_written_never_fails_the_socket_and_is_said_once(self):
        km._ws_open_row_failed = False
        err = io.StringIO()
        try:
            with mock.patch.object(km, "_client_diag_append", mock.Mock(side_effect=OSError("disk full"))), mock.patch.object(sys, "stderr", err):
                self.assertFalse(km._note_ws_open({"app": "chat", "wid": "", "kind": "relay"}))
                self.assertFalse(km._note_ws_open({"app": "feed", "wid": "", "kind": "page"}))
        finally:
            km._ws_open_row_failed = False
        lines = [ln for ln in err.getvalue().splitlines() if ln.strip()]
        self.assertEqual(len(lines), 1, "said once, however many rows fail: %r" % lines)
        self.assertIn("[client-diag] could not file a wsopen row (disk full)", lines[0])

    def test_a_browser_dial_files_page_the_extension_hosts_bare_dial_files_page_and_a_splice_files_hub_here_and_relay_there(self):
        hub = ThreadingHTTPServer(("127.0.0.1", 0), km.Handler)
        remote = ThreadingHTTPServer(("127.0.0.1", 0), km.Handler)
        for srv in (hub, remote):
            threading.Thread(target=srv.serve_forever, daemon=True).start()
        port, rport = hub.server_address[1], remote.server_address[1]
        tag = uuid.uuid4().hex[:8]
        w_page, w_ext, w_spliced = "wsopen-page-" + tag, "wsopen-ext-" + tag, "wsopen-spliced-" + tag
        socks = []
        with km._remotes_lock:
            km._remotes["TESTHOST"] = {"local_port": rport, "token": km.TOKEN}   # the hub's attached host: the second hermetic kernel
        try:
            # a browser's dial: an Origin header (same-origin, as a page this kernel serves sends it), the shim's instance id
            st, s1 = _upgrade(port, "/ws?app=chat&wid=%s&iid=i-%s&token=%s" % (w_page, w_page, km.TOKEN), origin="http://127.0.0.1:%d" % port)
            socks.append(s1)
            self.assertEqual(st, 101, "a same-origin browser dial with the token upgrades")
            # the VS Code extension host's dial: Node's ws client sends no Origin and no User-Agent; the query is app, wid, token
            st, s2 = _upgrade(port, "/ws?app=feed&wid=%s&token=%s" % (w_ext, km.TOKEN), extensions=True)
            socks.append(s2)
            self.assertEqual(st, 101, "the extension host's dial upgrades")
            # a browser's pane relayed through the hub to the remote: the hub files hub, the remote files relay on the splice's term
            st, s3 = _upgrade(port, "/remote/TESTHOST/ws?app=chat&wid=%s&iid=i-%s&reconnect=1&proto=2&token=%s" % (w_spliced, w_spliced, km.TOKEN),
                              origin="http://127.0.0.1:%d" % port)
            socks.append(s3)
            self.assertEqual(st, 101, "the spliced upgrade answers with the remote's 101")
            rows = _rows_for({w_page, w_ext, w_spliced}, expect=4)
            shape = sorted((r["wid"], r["data"]["app"], r["data"]["kind"], r["data"]["reconnect"], r["data"]["iid"], r["data"].get("host")) for r in rows)
            self.assertEqual(shape, sorted([(w_page, "chat", "page", False, True, None),
                                            (w_ext, "feed", "page", False, False, None),
                                            (w_spliced, "chat", "hub", True, True, "TESTHOST"),
                                            (w_spliced, "chat", "relay", True, True, None)]),
                             "one wsopen row per accepted socket, the kind by its terms; the splice a hub row here and a relay row there: %r" % rows)
            self.assertTrue(all(r["surface"] == "kernel" and isinstance(r["t"], int) and r["data"].get("cid") for r in rows), "the kernel's clock and a connection id on every row: %r" % rows)
        finally:
            with km._remotes_lock:
                km._remotes.pop("TESTHOST", None)
            for s in socks:
                try:
                    s.close()
                except OSError:
                    pass
            for srv in (hub, remote):
                srv.shutdown()
                srv.server_close()


if __name__ == "__main__":
    unittest.main()
