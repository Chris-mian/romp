#!/usr/bin/env python3
"""WebSocket per-message compression (RFC 7692 permessage-deflate) on the kernel's hand-rolled server.

The panes' view frames are JSON and deflate about seven to one (the whole feed frame of a 374-card board:
2.53 MB plain, 0.36 MB deflated), and until this every frame crossed plain: the upgrade ignored the
Sec-WebSocket-Extensions offer every browser and Node's `ws` make on every dial, so a tunnelled dashboard
fell megabytes behind on the feed and was dropped. Pinned here:

- negotiation: an offer is answered with the extension (no context takeover on either side; a bounded server
  window echoed), an absent, foreign or malformed offer is not, and the kill switch declines every offer;
- the wire: a message at or over the size floor goes compressed with RSV1 set and inflates back to its text;
  a short one, and every message to a client without the extension, gets the plain frame it always did,
  byte for byte;
- the reader: a client's compressed message (RSV1 on its first frame, fragments included) is inflated before
  it is parsed; an inflate past the reassembly cap, bytes that are not a deflate stream, or RSV1 from a client
  that negotiated nothing end the read as a dead connection; a plain message is untouched;
- end to end through the real Handler on a loopback server: both directions on one negotiated socket, and a
  socket that offered nothing stays plain;
- the federated relay keeps forwarding the offer header, since the browser negotiates with the REMOTE kernel
  through it.

Synthetic only: invented frame text, no session data.
"""
import base64
import inspect
import io
import json
import os
import socket
import struct
import tempfile
import threading
import time
import unittest
import zlib
from http.server import ThreadingHTTPServer
from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "test-token-DO-NOT-USE")
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
load_source("romp_event_model", os.path.join(BIN, "romp-event-model"))
load_source("romp_judge", os.path.join(BIN, "romp-judge"))
km = load_source("romp_kernel_wsdeflate", os.path.join(BIN, "romp-kernel"))

TAIL = b"\x00\x00\xff\xff"
MASK = b"\x11\x22\x33\x44"
ACCEPT = "permessage-deflate; server_no_context_takeover; client_no_context_takeover"


def deflate(data, level=6, wbits=15):
    """A client's compressed payload, as a browser makes it: one raw deflate stream, sync-flushed, tail stripped."""
    z = zlib.compressobj(level, zlib.DEFLATED, -wbits)
    out = z.compress(data) + z.flush(zlib.Z_SYNC_FLUSH)
    assert out.endswith(TAIL)
    return out[:-4]


def inflate(data):
    """What a browser does with an RSV1 frame's payload — independent of the kernel's own inflater."""
    return zlib.decompressobj(-15).decompress(data + TAIL)


def cframe(payload, opcode=0x1, fin=True, rsv1=False, mask=MASK):
    """One client (masked) frame, wire-encoded."""
    b0 = (0x80 if fin else 0x00) | (0x40 if rsv1 else 0x00) | opcode
    ln = len(payload)
    if ln < 126:
        hdr = bytes([b0, 0x80 | ln])
    elif ln < 65536:
        hdr = bytes([b0, 0x80 | 126]) + struct.pack(">H", ln)
    else:
        hdr = bytes([b0, 0x80 | 127]) + struct.pack(">Q", ln)
    return hdr + mask + bytes(c ^ mask[i % 4] for i, c in enumerate(payload))


def cfragments(payload, chunk, rsv1=False):
    """A message split into continuation frames of `chunk` bytes; RSV1, when set, on the FIRST frame only (RFC 7692 §6.1)."""
    parts = [payload[i:i + chunk] for i in range(0, len(payload), chunk)] or [b""]
    out = b""
    for i, p in enumerate(parts):
        out += cframe(p, 0x1 if i == 0 else 0x0, fin=(i == len(parts) - 1), rsv1=(rsv1 and i == 0))
    return out


def recv_message(wire, inflate_=False):
    pings = []
    return km._ws_recv_message(io.BytesIO(wire), pings.append, inflate=inflate_)


def parse_sframe(b):
    """One server frame from bytes → (byte0, payload, bytes consumed)."""
    b0, ln, at = b[0], b[1] & 0x7F, 2
    if ln == 126:
        ln, at = struct.unpack(">H", b[2:4])[0], 4
    elif ln == 127:
        ln, at = struct.unpack(">Q", b[2:10])[0], 10
    return b0, b[at:at + ln], at + ln


def big_text(n=300):
    return json.dumps({"type": "feed", "asks": [{"itemId": "item-%d" % i, "title": "invented card %d" % i,
                                                 "status": "completed", "why": "synthetic fixture text"} for i in range(n)]})


class Offer(unittest.TestCase):
    def test_offers_the_kernel_takes_and_the_window_it_keeps_to(self):
        for hdr, (wbits, bounded) in {
            "permessage-deflate": (15, False),
            "PerMessage-Deflate": (15, False),                                    # the token is case-insensitive
            "permessage-deflate; client_max_window_bits": (15, False),           # Chrome, Firefox, Node's ws
            "permessage-deflate; client_max_window_bits=15": (15, False),
            "permessage-deflate; server_no_context_takeover; client_no_context_takeover": (15, False),
            "permessage-deflate; server_max_window_bits=10": (10, True),         # a bounded server window is kept to
            'permessage-deflate; server_max_window_bits="12"': (12, True),       # quoted-string values are allowed
            "permessage-deflate; server_max_window_bits=15": (15, True),         # named at the default: still named
            "x-webkit-deflate-frame, permessage-deflate; client_max_window_bits": (15, False),   # a foreign extension first
            "permessage-deflate; bogus, permessage-deflate": (15, False),        # the first offer declined, the second taken
        }.items():
            self.assertEqual(km._ws_deflate_offer(hdr), {"wbits": wbits, "bounded": bounded}, hdr)

    def test_offers_a_server_must_decline(self):
        for hdr in (None, "", "x-webkit-deflate-frame",
                    "permessage-deflate; bogus",                               # an unknown parameter
                    "permessage-deflate; server_max_window_bits",              # the value is required in an offer
                    "permessage-deflate; server_max_window_bits=8",            # zlib cannot build a window that small
                    "permessage-deflate; server_max_window_bits=16",
                    "permessage-deflate; client_max_window_bits=7",
                    "permessage-deflate; server_no_context_takeover=1",        # a flag with a value
                    "permessage-deflate; client_max_window_bits; client_max_window_bits"):   # repeated
            self.assertIsNone(km._ws_deflate_offer(hdr), repr(hdr))

    def test_the_response_states_no_context_takeover_for_both_sides(self):
        self.assertEqual(km._ws_deflate_response({"wbits": 15, "bounded": False}), ACCEPT)
        self.assertEqual(km._ws_deflate_response({"wbits": 10, "bounded": True}), ACCEPT + "; server_max_window_bits=10")

    def test_a_server_window_the_offer_named_is_echoed_even_at_the_default(self):
        # RFC 7692 §7.1.2.1: an offer carrying server_max_window_bits is accepted only WITH the parameter in the
        # response; a client that asked for 15 (Python's websockets does when told to) refuses a response without it
        # (review find, 2026-09-23: it could not connect at all, where declining the offer had let it connect plain)
        terms = km._ws_deflate_offer("permessage-deflate; server_max_window_bits=15")
        self.assertEqual(km._ws_deflate_response(terms), ACCEPT + "; server_max_window_bits=15")


class Wire(unittest.TestCase):
    class Sock:
        def __init__(self):
            self.out = b""

        def sendall(self, b):
            self.out += b

    def _sent(self, text, deflate_):
        sock = self.Sock()
        km._ws_send(sock, threading.Lock(), text, deflate_)
        return parse_sframe(sock.out)

    def test_a_negotiated_clients_large_message_goes_compressed_with_rsv1(self):
        text = big_text()
        b0, payload, used = self._sent(text, {"wbits": 15})
        self.assertEqual(b0, 0xC1, "FIN + RSV1 + text")
        self.assertEqual(inflate(payload).decode("utf-8"), text)
        self.assertLess(len(payload), len(text.encode()) // 4, "the JSON frame shrinks several-fold")

    def test_a_bounded_server_window_is_kept_to(self):
        text = big_text()
        b0, payload, _ = self._sent(text, {"wbits": 9})
        self.assertEqual(b0, 0xC1)
        self.assertEqual(zlib.decompressobj(-9).decompress(payload + TAIL).decode("utf-8"), text,
                         "a client that asked for a 9-bit window can inflate with one")

    def test_a_short_message_goes_plain_even_when_negotiated(self):
        text = json.dumps({"type": "ka", "dv": "abc"})
        b0, payload, _ = self._sent(text, {"wbits": 15})
        self.assertEqual((b0, payload), (0x81, text.encode()))

    def test_a_client_without_the_extension_gets_the_frame_it_always_did(self):
        text = big_text()
        sock = self.Sock()
        km._ws_send(sock, threading.Lock(), text)                              # the old call shape, no terms
        data = text.encode()
        self.assertEqual(sock.out, bytes([0x81, 126]) + struct.pack(">H", len(data)) + data if len(data) < 65536
                         else bytes([0x81, 127]) + struct.pack(">Q", len(data)) + data)
        self.assertEqual(self._sent(text, None)[:2], (0x81, data))

    def test_incompressible_bytes_go_plain(self):
        noise = zlib.compress(os.urandom(4096))
        self.assertIsNone(km._ws_deflate(noise, 15), "deflate that does not shrink is not used")

    def test_the_sender_thread_hands_the_clients_terms_to_the_framer(self):
        self.assertIn('_ws_send(sock, lock, s, client.get("deflate"))', inspect.getsource(km._ws_sender))


class Reader(unittest.TestCase):
    BODY = json.dumps({"type": "invented", "pad": "y" * 3000}).encode()

    def test_a_compressed_message_is_inflated_before_it_is_parsed(self):
        self.assertEqual(recv_message(cframe(deflate(self.BODY), rsv1=True), inflate_=True), (0x1, self.BODY))

    def test_rsv1_rides_the_first_fragment_only(self):
        wire = cfragments(deflate(self.BODY), chunk=7, rsv1=True)
        self.assertEqual(recv_message(wire, inflate_=True), (0x1, self.BODY))

    def test_a_ping_between_compressed_fragments_is_still_answered(self):
        z = deflate(self.BODY)
        wire = cframe(z[:5], 0x1, fin=False, rsv1=True) + cframe(b"hi", 0x9) + cframe(z[5:], 0x0, fin=True)
        pings = []
        self.assertEqual(km._ws_recv_message(io.BytesIO(wire), pings.append, inflate=True), (0x1, self.BODY))
        self.assertEqual(pings, [b"hi"])

    def test_a_plain_message_is_untouched_when_the_extension_is_on(self):
        self.assertEqual(recv_message(cframe(self.BODY), inflate_=True), (0x1, self.BODY))
        self.assertEqual(recv_message(cfragments(self.BODY, chunk=100), inflate_=True), (0x1, self.BODY))

    def test_rsv1_from_a_client_that_negotiated_nothing_ends_the_read(self):
        self.assertEqual(recv_message(cframe(deflate(self.BODY), rsv1=True), inflate_=False), (None, None))

    def test_bytes_that_are_not_a_deflate_stream_end_the_read(self):
        self.assertEqual(recv_message(cframe(b"\xff\xfe\xfd not deflate at all", rsv1=True), inflate_=True), (None, None))

    def test_an_inflate_past_the_reassembly_cap_ends_the_read(self):
        saved = km._WS_MAX_MESSAGE
        km._WS_MAX_MESSAGE = 2048
        try:
            self.assertEqual(recv_message(cframe(deflate(b"\0" * 10000), rsv1=True), inflate_=True), (None, None))
            self.assertEqual(recv_message(cframe(deflate(b"\0" * 2048), rsv1=True), inflate_=True), (0x1, b"\0" * 2048),
                             "exactly the cap is allowed")
        finally:
            km._WS_MAX_MESSAGE = saved

    def test_the_frame_reader_carries_rsv1_above_the_opcode(self):
        op, payload, fin = km._ws_recv(io.BytesIO(cframe(b"x", 0x1, rsv1=True)))
        self.assertEqual((op, payload, fin), (0x41, b"x", True))
        op, payload, fin = km._ws_recv(io.BytesIO(cframe(b"x", 0x1)))
        self.assertEqual((op, payload, fin), (0x1, b"x", True), "a plain frame's opcode reads as before")


class _Reader:
    """Frames off a real socket, with the bytes that arrived behind the handshake head."""

    def __init__(self, sock, rest=b""):
        self.sock, self.buf = sock, rest

    def rd(self, n):
        while len(self.buf) < n:
            c = self.sock.recv(65536)
            if not c:
                raise EOFError("socket closed")
            self.buf += c
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def frame(self):
        h = self.rd(2)
        ln = h[1] & 0x7F
        if ln == 126:
            ln = struct.unpack(">H", self.rd(2))[0]
        elif ln == 127:
            ln = struct.unpack(">Q", self.rd(8))[0]
        return h[0], self.rd(ln)


def upgrade(port, extensions=None, wid="w-deflate", app="feed"):
    """One raw upgrade with the token (an absent Origin passes with it) → (status, headers, socket, bytes after the head)."""
    key = base64.b64encode(os.urandom(16)).decode()
    lines = ["GET /ws?app=%s&wid=%s&token=%s HTTP/1.1" % (app, wid, km.TOKEN), "Host: 127.0.0.1:%d" % port,
             "Upgrade: websocket", "Connection: Upgrade", "Sec-WebSocket-Key: %s" % key, "Sec-WebSocket-Version: 13"]
    if extensions is not None:
        lines.append("Sec-WebSocket-Extensions: %s" % extensions)
    s = socket.create_connection(("127.0.0.1", port), timeout=10)
    s.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
    buf = b""
    while b"\r\n\r\n" not in buf:
        c = s.recv(4096)
        if not c:
            break
        buf += c
    head, _, rest = buf.partition(b"\r\n\r\n")
    hl = head.decode("latin-1").split("\r\n")
    status = int(hl[0].split(" ")[1]) if len(hl[0].split(" ")) > 1 else -1
    headers = {}
    for line in hl[1:]:
        k, _, v = line.partition(":")
        headers[k.strip().lower()] = v.strip()
    return status, headers, s, rest


class EndToEnd(unittest.TestCase):
    """The real Handler on a loopback ThreadingHTTPServer, driven by raw sockets."""

    def setUp(self):
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), km.Handler)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.socks = []

    def tearDown(self):
        for s in self.socks:
            try:
                s.close()
            except OSError:
                pass
        self.srv.shutdown()
        self.srv.server_close()

    def _client(self, wid, timeout=5.0):
        """The kernel's record of the pane that dialed with `wid`, once the handler has registered it."""
        t0 = time.time()
        while time.time() - t0 < timeout:
            with km._clients_lock:
                for c in km._clients:
                    if c.get("wid") == wid and c.get("alive"):
                        return c
            time.sleep(0.02)
        self.fail("the handler never registered the client %r" % wid)

    def test_a_browsers_offer_is_taken_and_both_directions_are_compressed(self):
        status, headers, s, rest = upgrade(self.port, "permessage-deflate; client_max_window_bits", wid="w-both")
        self.socks.append(s)
        self.assertEqual(status, 101)
        self.assertEqual(headers.get("sec-websocket-extensions"), ACCEPT)
        client = self._client("w-both")
        self.assertEqual(client.get("deflate"), {"wbits": 15, "bounded": False})
        rd = _Reader(s, rest)
        # kernel → client: a frame the size of a view goes compressed, a keepalive-sized one plain
        text = big_text()
        client["send"](text)
        b0, payload = rd.frame()
        self.assertEqual(b0, 0xC1)
        self.assertEqual(inflate(payload).decode("utf-8"), text)
        self.assertLess(len(payload), len(text) // 4)
        client["send"]('{"type":"ka"}')
        self.assertEqual(rd.frame(), (0x81, b'{"type":"ka"}'))
        # client → kernel: a compressed message reaches the dispatcher as the text it was
        seen = []
        real = km.Handler._dispatch_ws
        km.Handler._dispatch_ws = lambda self_, msg, c: seen.append(msg)
        try:
            body = json.dumps({"type": "invented-op", "pad": "z" * 5000, "n": 1})
            s.sendall(cframe(deflate(body.encode()), rsv1=True))
            body2 = json.dumps({"type": "invented-op", "pad": "z" * 5000, "n": 2})
            s.sendall(cfragments(deflate(body2.encode()), chunk=64, rsv1=True))   # as Chrome fragments a large send
            s.sendall(cframe(b'{"type":"invented-op","n":3}'))                       # …and a plain one still lands
            t0 = time.time()
            while len(seen) < 3 and time.time() - t0 < 5:
                time.sleep(0.02)
        finally:
            km.Handler._dispatch_ws = real
        self.assertEqual([m.get("n") for m in seen], [1, 2, 3])
        self.assertEqual(seen[0], json.loads(body))
        self.assertEqual(seen[1], json.loads(body2))

    def test_a_client_that_offered_nothing_stays_plain(self):
        status, headers, s, rest = upgrade(self.port, None, wid="w-plain")
        self.socks.append(s)
        self.assertEqual(status, 101)
        self.assertNotIn("sec-websocket-extensions", headers)
        client = self._client("w-plain")
        self.assertIsNone(client.get("deflate"))
        text = big_text()
        client["send"](text)
        self.assertEqual(_Reader(s, rest).frame(), (0x81, text.encode()))

    def test_an_offer_naming_the_default_window_gets_it_echoed(self):
        status, headers, s, _ = upgrade(self.port, "permessage-deflate; server_max_window_bits=15", wid="w-named15")
        self.socks.append(s)
        self.assertEqual(status, 101)
        self.assertEqual(headers.get("sec-websocket-extensions"), ACCEPT + "; server_max_window_bits=15")

    def test_a_malformed_offer_is_declined_not_refused(self):
        status, headers, s, _ = upgrade(self.port, "permessage-deflate; bogus_param", wid="w-bogus")
        self.socks.append(s)
        self.assertEqual(status, 101, "the upgrade still happens; only the extension is declined")
        self.assertNotIn("sec-websocket-extensions", headers)

    def test_the_kill_switch_declines_every_offer(self):
        saved = km._WS_DEFLATE_ON
        km._WS_DEFLATE_ON = False
        try:
            status, headers, s, _ = upgrade(self.port, "permessage-deflate; client_max_window_bits", wid="w-off")
            self.socks.append(s)
            self.assertEqual(status, 101)
            self.assertNotIn("sec-websocket-extensions", headers)
            self.assertIsNone(self._client("w-off").get("deflate"))
        finally:
            km._WS_DEFLATE_ON = saved


class Relay(unittest.TestCase):
    def test_the_federated_relay_forwards_the_offer_to_the_remote_kernel(self):
        # the hub splices bytes without parsing frames, so the browser negotiates with the REMOTE kernel: its offer
        # must reach it, and the remote's answer rides back in the head the hub forwards whole
        self.assertIn('"Sec-WebSocket-Extensions"', inspect.getsource(km.Handler._remote_ws))


if __name__ == "__main__":
    unittest.main(verbosity=2)
