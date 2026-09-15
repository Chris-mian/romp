"""One client-diag row per socket the kernel accepts (2026-09-15).

The kernel kept no durable record of page connections: an empty client-diag.jsonl read as a broken breadcrumb sink when
no browser had been on a page this kernel serves, and a count of GET /ws per app read as the attached dashboard's panes
when they may have been another kernel's federation relay dials. _note_ws_open files one `wsopen` row (surface kernel)
right after _register_ws_client: the app, the dashboard id, the shim's reconnect term, and the client's kind, decided once
at the handshake by _dial_kind(headers), the tell the connect-push split reads too: "page" for a dial carrying an Origin
or a User-Agent header (a browser's upgrade carries both), "relay" for one carrying neither (the federation splice,
_remote_ws, forwards only the six WebSocket upgrade headers and dials with the remote's own token; a CLI dial has the
same shape).

Three pins: the tell on header shapes; the helper's row, through the same capture tests/test_chat_window_spans.py uses
for the kernel's other row; and
the handler end to end, a real upgrade with an Origin header and a real upgrade without one, read back from the run's
client-diag.jsonl by their dashboard ids. Synthetic: an ephemeral server on the loopback, the run's own state root.
"""
import base64
import json
import os
import socket
import sys
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
os.environ.setdefault("ROMP_SERVE_TOKEN", "test-token-DO-NOT-USE")
km = load_source("romp_kernel_wsopen_row", os.path.join(BIN, "romp-kernel"))


def _upgrade(port, path, origin=None, timeout=3.0):
    """One raw WebSocket upgrade, the socket kept open; returns (status, socket)."""
    key = base64.b64encode(os.urandom(16)).decode()
    lines = ["GET %s HTTP/1.1" % path, "Host: 127.0.0.1:%d" % port, "Upgrade: websocket", "Connection: Upgrade",
             "Sec-WebSocket-Key: %s" % key, "Sec-WebSocket-Version: 13"]
    if origin is not None:
        lines.append("Origin: %s" % origin)
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


def _rows_for(wids, deadline_s=5.0):
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
        if len({r["wid"] for r in got}) == len(wids) or time.time() >= end:
            return got
        time.sleep(0.05)


class WsOpenRow(unittest.TestCase):
    def test_the_tell_reads_origin_or_user_agent_and_relay_is_neither(self):
        self.assertEqual(km._dial_kind({"Origin": "http://127.0.0.1:1", "User-Agent": "Mozilla/5.0"}), "page")
        self.assertEqual(km._dial_kind({"Origin": "vscode-webview://x"}), "page", "an Origin alone is a browser")
        self.assertEqual(km._dial_kind({"User-Agent": "Mozilla/5.0"}), "page", "a User-Agent alone is a browser too")
        self.assertEqual(km._dial_kind({}), "relay", "neither header: the splice's dial, or a CLI's")
        self.assertEqual(km._dial_kind({"Upgrade": "websocket", "Sec-WebSocket-Key": "k"}), "relay", "the six upgrade headers alone are the relay's shape")

    def test_the_helper_files_one_row_with_app_wid_kind_and_reconnect(self):
        rows = []
        with mock.patch.object(km, "_client_diag_append", lambda fp, line: rows.append((fp.name, json.loads(line)))):
            self.assertTrue(km._note_ws_open({"app": "feed", "wid": "w1", "iid": "i1", "cid": "c1", "kind": "page"}, reconnect=True, now=1700000000))
        self.assertEqual(rows, [("client-diag.jsonl", {"t": 1700000000, "wid": "w1", "surface": "kernel", "what": "wsopen",
                                                       "data": {"app": "feed", "kind": "page", "reconnect": True, "iid": True, "cid": "c1"}})])
        # the file's failure is never the socket's
        with mock.patch.object(km, "_client_diag_append", mock.Mock(side_effect=OSError("disk"))):
            self.assertFalse(km._note_ws_open({"app": "chat", "wid": "", "kind": "relay"}))

    def test_a_browser_dial_files_page_and_a_token_dial_without_origin_files_relay(self):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), km.Handler)
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        w_page, w_relay = "wsopen-page-" + uuid.uuid4().hex[:8], "wsopen-relay-" + uuid.uuid4().hex[:8]
        socks = []
        try:
            # a browser's dial: an Origin header (same-origin, as a page this kernel serves sends it), an instance id, no reconnect
            st, s1 = _upgrade(port, "/ws?app=chat&wid=%s&iid=i-%s&token=%s" % (w_page, w_page, km.TOKEN), origin="http://127.0.0.1:%d" % port)
            socks.append(s1)
            self.assertEqual(st, 101, "a same-origin browser dial with the token upgrades")
            # the federation splice's dial as the remote kernel sees it: no Origin, the token in the query, a redial's terms
            st, s2 = _upgrade(port, "/ws?app=feed&wid=%s&reconnect=1&proto=2&token=%s" % (w_relay, km.TOKEN))
            socks.append(s2)
            self.assertEqual(st, 101, "an absent-Origin dial with the token upgrades")
            rows = _rows_for({w_page, w_relay})
            shape = sorted((r["surface"], r["wid"], r["data"]["app"], r["data"]["kind"], r["data"]["reconnect"], r["data"]["iid"]) for r in rows)
            self.assertEqual(shape, sorted([("kernel", w_page, "chat", "page", False, True),
                                            ("kernel", w_relay, "feed", "relay", True, False)]),
                             "one wsopen row per accepted socket, the kind told at the handshake: %r" % rows)
            self.assertTrue(all(isinstance(r["t"], int) and r["data"].get("cid") for r in rows), "the kernel's clock and the connection id: %r" % rows)
        finally:
            for s in socks:
                try:
                    s.close()
                except OSError:
                    pass
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
