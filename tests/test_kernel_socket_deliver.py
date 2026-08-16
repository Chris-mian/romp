#!/usr/bin/env python3
"""Postal mail's inbox-socket delivery leg (Claude Code >= 2.1.224). The CLI registers each
session's inbox socket in ~/.claude/sessions/<pid>.json; one JSON line posted there injects a
message without touching the composer. The kernel uses that leg ONLY for sessions tagged
@romp-inbound-accept — the tag bin/romp writes at the same launch that passes the CLI's
inbound-accept setting, so a held-then-dropped banner can never read as delivered (the socket
sends no ack). Untagged sessions must keep today's pane injection untouched. Synthetic
fixtures only."""
import json
import os
import socket
import tempfile
import threading
import time
import unittest
from importlib.machinery import SourceFileLoader

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "bin")
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
SourceFileLoader("romp_event_model", os.path.join(BIN, "romp-event-model")).load_module()
SourceFileLoader("romp_judge", os.path.join(BIN, "romp-judge")).load_module()
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
km = SourceFileLoader("romp_kernel_socketleg", os.path.join(BIN, "romp-kernel")).load_module()

SID = "11111111-2222-3333-4444-555555555555"
DEAD_PID = 4999999                       # above every platform's default pid ceiling


def _registry_row(dirpath, pid, session_id, sock, started_at=1000):
    with open(os.path.join(dirpath, "%d.json" % pid), "w") as f:
        json.dump({"pid": pid, "sessionId": session_id, "messagingSocketPath": sock,
                   "startedAt": started_at, "cwd": "/tmp/x", "kind": "interactive"}, f)


class _OneShotInbox:
    """A real AF_UNIX listener capturing everything one client writes (the CLI parses per
    line and acks nothing for a plain send, so capture-and-close mirrors it exactly)."""

    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="rompsock", dir="/tmp")
        self.path = os.path.join(self.dir, "inbox.sock")
        self.got = []
        self._srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._srv.bind(self.path)
        self._srv.listen(1)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        try:
            conn, _ = self._srv.accept()
        except OSError:
            return
        buf = b""
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            buf += chunk
        self.got.append(buf)
        conn.close()

    def wait(self, timeout=3.0):
        self._thread.join(timeout)
        return self.got

    def close(self):
        try:
            self._srv.close()
        except OSError:
            pass


class SocketRegistry(unittest.TestCase):
    """_messaging_socket_for: the ~/.claude/sessions registry join."""

    def setUp(self):
        self.reg = tempfile.mkdtemp(prefix="rompreg")
        os.environ["ROMP_CLAUDE_SESSIONS_DIR"] = self.reg

    def tearDown(self):
        os.environ.pop("ROMP_CLAUDE_SESSIONS_DIR", None)

    def test_matches_session_id(self):
        _registry_row(self.reg, 111, SID, "/tmp/cc-socks/111.sock")
        self.assertEqual(km._messaging_socket_for(SID), "/tmp/cc-socks/111.sock")

    def test_no_row_no_dir_and_malformed_rows(self):
        self.assertIsNone(km._messaging_socket_for(SID))            # empty registry
        with open(os.path.join(self.reg, "bad.json"), "w") as f:
            f.write("{not json")                                     # malformed → skipped
        _registry_row(self.reg, 222, "99999999-aaaa-bbbb-cccc-dddddddddddd", "/tmp/other.sock")
        self.assertIsNone(km._messaging_socket_for(SID))             # other session's row
        os.environ["ROMP_CLAUDE_SESSIONS_DIR"] = self.reg + "-missing"
        self.assertIsNone(km._messaging_socket_for(SID))             # registry dir absent

    def test_row_without_socket_is_not_a_hit(self):
        with open(os.path.join(self.reg, "333.json"), "w") as f:
            json.dump({"pid": 333, "sessionId": SID}, f)             # pre-2.1.224 CLI: no socket field
        self.assertIsNone(km._messaging_socket_for(SID))

    def test_prefers_live_pid_over_newer_dead_row(self):
        # A resumed conversation leaves the old (dead) pid's row behind under the same
        # session id; the join must pick the row whose pid is alive even when the stale
        # row looks newer.
        _registry_row(self.reg, os.getpid(), SID, "/tmp/cc-socks/alive.sock", started_at=1000)
        _registry_row(self.reg, DEAD_PID, SID, "/tmp/cc-socks/dead.sock", started_at=2000)
        self.assertEqual(km._messaging_socket_for(SID), "/tmp/cc-socks/alive.sock")


class SocketWrite(unittest.TestCase):
    """_socket_deliver: exactly one {"type":"user"} JSON line, and honest False on failure."""

    def test_writes_one_user_record(self):
        inbox = _OneShotInbox()
        try:
            self.assertTrue(km._socket_deliver(inbox.path, "mail body <!-- romp-msg-id: 1 -->"))
            got = inbox.wait()
            self.assertEqual(len(got), 1)
            rec = json.loads(got[0].decode("utf-8"))
            self.assertEqual(rec["type"], "user")
            self.assertEqual(rec["message"]["role"], "user")
            self.assertEqual(rec["message"]["content"], "mail body <!-- romp-msg-id: 1 -->")
        finally:
            inbox.close()

    def test_false_when_socket_is_gone(self):
        self.assertFalse(km._socket_deliver("/tmp/rompsock-nonexistent/inbox.sock", "x"))


class _StubTmux(km.TmuxBackend):
    """TmuxBackend with every raw tmux touchpoint stubbed; records pane-path probes so the
    tests can assert which delivery leg ran."""

    def __init__(self, accept):
        self._accept = accept
        self.pane_calls = []

    def live_sessions(self):
        return {SID: {"state": "idle", "backend": "tmux"}}

    def show_var(self, name, var, t=2.5):
        return "1" if (var == "@romp-inbound-accept" and self._accept) else ""

    def pane_in_mode(self, name):
        self.pane_calls.append("pane_in_mode")
        return False

    def capture(self, name, colour=False):
        self.pane_calls.append("capture")
        return ""                                          # never a live ❯ prompt → pane path bails

    def send_keys(self, name, *keys):
        self.pane_calls.append("send_keys")


class DeliverGate(unittest.TestCase):
    """TmuxBackend.deliver: socket leg iff tagged; pane path otherwise and on socket failure."""

    def setUp(self):
        self.reg = tempfile.mkdtemp(prefix="rompreg")
        os.environ["ROMP_CLAUDE_SESSIONS_DIR"] = self.reg
        self._name_of = km._name_of
        km._name_of = lambda sid: "tsess"
        self._last_sid = km.jd._sdk_last_sid
        km.jd._sdk_last_sid = lambda sid: None             # tmux session: fsid IS the sid

    def tearDown(self):
        os.environ.pop("ROMP_CLAUDE_SESSIONS_DIR", None)
        km._name_of = self._name_of
        km.jd._sdk_last_sid = self._last_sid

    def test_tagged_session_delivers_down_the_socket(self):
        inbox = _OneShotInbox()
        try:
            _registry_row(self.reg, os.getpid(), SID, inbox.path)
            be = _StubTmux(accept=True)
            self.assertTrue(be.deliver(SID, "banner text"))
            got = inbox.wait()
            self.assertEqual(json.loads(got[0].decode("utf-8"))["message"]["content"], "banner text")
            self.assertEqual(be.pane_calls, [])            # the pane was never touched
        finally:
            inbox.close()

    def test_untagged_session_keeps_the_pane_path(self):
        inbox = _OneShotInbox()
        try:
            _registry_row(self.reg, os.getpid(), SID, inbox.path)
            be = _StubTmux(accept=False)
            be.deliver(SID, "banner text")                 # pane stub has no ❯ prompt → undelivered
            time.sleep(0.2)
            self.assertEqual(inbox.got, [])                # nothing reached the socket
            self.assertIn("capture", be.pane_calls)        # the pane path ran instead
        finally:
            inbox.close()

    def test_tagged_but_dead_socket_falls_back_to_the_pane(self):
        _registry_row(self.reg, os.getpid(), SID, "/tmp/rompsock-nonexistent/inbox.sock")
        be = _StubTmux(accept=True)
        self.assertFalse(be.deliver(SID, "banner text"))   # pane stub can't inject either
        self.assertIn("capture", be.pane_calls)            # but it was TRIED — no silent drop


if __name__ == "__main__":
    unittest.main()
