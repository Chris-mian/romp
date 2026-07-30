#!/usr/bin/env python3
"""Which tab you are looking at is YOURS (the user 2026-07-29).

Two dashboards on one kernel are two pairs of eyes, and one should not move the other. But every
cross-pane reveal went through _send_to_app, which pushes to EVERY client of an app, so opening a session
in one window switched tabs in the other, and clicking a distilled summary jumped both to the same turn.

Each dashboard now reports a `wid` (the shell mints one per browser tab in sessionStorage, shared with its
same-origin pane iframes and passed on the WS connect), and a reveal handled inside a WS op is aimed at
the asker's wid alone. An empty wid keeps the broadcast, so a client that reports none behaves as before.

Synthetic clients only; no sockets.
"""
import inspect
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ.setdefault("XDG_STATE_HOME", tempfile.mkdtemp())
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel_pvf", os.path.join(BIN, "romp-kernel")).load_module()


def _client(app, wid, sink):
    return {"app": app, "wid": wid, "alive": True, "send": lambda s: sink.append((wid, s))}


class TargetedSend(unittest.TestCase):
    def setUp(self):
        self.sink = []
        self._saved = list(km._clients)
        km._clients[:] = [_client("chat", "win-A", self.sink), _client("chat", "win-B", self.sink),
                          _client("feed", "win-A", self.sink)]

    def tearDown(self):
        km._clients[:] = self._saved

    def test_only_the_asking_dashboard_hears_it(self):
        km._send_to_view("chat", {"type": "focus", "id": "s1"}, "win-A")
        self.assertEqual([w for w, _ in self.sink], ["win-A"], "the other window is left where it was")

    def test_a_wid_names_a_dashboard_not_a_pane(self):
        # every pane of one window shares the wid, so a shell reveal reaches that window's shell only
        km._send_to_view("feed", {"type": "x"}, "win-A")
        self.assertEqual(len(self.sink), 1)
        self.sink.clear()
        km._send_to_view("feed", {"type": "x"}, "win-B")
        self.assertEqual(self.sink, [], "win-B has no feed pane open")

    def test_no_wid_still_broadcasts(self):
        # an older client, or a surface that supplies no id, must not silently receive nothing
        km._send_to_view("chat", {"type": "focus", "id": "s1"}, "")
        self.assertEqual(sorted(w for w, _ in self.sink), ["win-A", "win-B"])


class Wiring(unittest.TestCase):
    def test_the_ops_a_user_clicks_are_aimed_at_the_asker(self):
        src = inspect.getsource(km.Handler)
        # openByName/pickResult, openSession, deepLink and showOnTimeline all have the client in hand
        self.assertGreaterEqual(src.count("_reveal_chat_for(client,"), 3)
        self.assertIn("_reveal_or_confirm(msg[\"sid\"], _show_on_timeline_focus(msg), client)", src,
                      "the distilled-summary jump is one viewer's navigation")
        self.assertIn("\"anchorKind\": msg.get(\"anchorKind\")}, client)", src, "…and so is a deep link")

    def test_the_shell_mints_one_id_per_tab_and_the_panes_read_it(self):
        html = km._landing()
        self.assertIn("sessionStorage.getItem('romp:wid')", html)
        self.assertIn("sessionStorage.setItem('romp:wid'", html)
        # the pane's own shim prefers ?wid= (the VS Code host supplies one) then the shell's per-tab id
        shim = km._shim("chat", 1)
        self.assertIn('get("wid")', shim)
        self.assertIn('window.sessionStorage.getItem("romp:wid")', shim)

    def test_an_empty_wid_falls_through_to_the_broadcast(self):
        self.assertIn("if not wid:\n        return _send_to_app(app, msg)",
                      inspect.getsource(km._send_to_view))


if __name__ == "__main__":
    unittest.main()
