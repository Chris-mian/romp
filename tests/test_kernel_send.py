#!/usr/bin/env python3
"""POST /send body parsing — the human->agent input channel the Obsidian track-changes
plugin posts to. The kernel then injects the text via _tmux_send (the same delivery the
chat composer's WS sendMessage uses), so the plugin never touches tmux itself.
"""
import os
import unittest
from unittest import mock
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
km = SourceFileLoader("romp_kernel_send", os.path.join(BIN, "romp-kernel")).load_module()


class ParseSendBody(unittest.TestCase):
    def test_id_and_text(self):
        self.assertEqual(km._parse_send_body(b'{"id":"alpha","text":"hi"}'), {"who": "alpha", "text": "hi"})

    def test_name_is_accepted_as_who(self):
        self.assertEqual(km._parse_send_body(b'{"name":"beta","text":"yo"}'), {"who": "beta", "text": "yo"})

    def test_rejects_missing_or_empty(self):
        self.assertIsNone(km._parse_send_body(b'{"id":"alpha"}'))           # no text
        self.assertIsNone(km._parse_send_body(b'{"text":"hi"}'))            # no id/name
        self.assertIsNone(km._parse_send_body(b'{"id":"alpha","text":""}'))  # empty text
        self.assertIsNone(km._parse_send_body(b'{"id":"","text":"hi"}'))    # empty id

    def test_rejects_bad_json_non_object_and_non_string_text(self):
        self.assertIsNone(km._parse_send_body(b'not json'))
        self.assertIsNone(km._parse_send_body(b'[1,2,3]'))
        self.assertIsNone(km._parse_send_body(b''))
        self.assertIsNone(km._parse_send_body(b'{"id":"a","text":123}'))


class SessionList(unittest.TestCase):
    """GET /sessions — the UNIFIED (tmux + SDK) romp session list external tools read (the Obsidian Cmd+M
    picker + diff chips, the postal bus) instead of shelling tmux. _session_rows assembles each LIVE session
    from Sessions.live() (the backend query) + the names registry + working-notes."""

    def _stub(self, live, notes, names):
        saved = (km.Sessions.live, km._working_notes, km._name_of, km._cwd_of, km._identity_of)
        km.Sessions.live = staticmethod(lambda: live)
        km._working_notes = lambda: notes
        km._name_of = lambda sid: names.get(sid, (sid[:8],))[0]
        km._cwd_of = lambda sid: names[sid][1]
        km._identity_of = lambda sid: names[sid][2:4]
        self.addCleanup(lambda: setattr(km.Sessions, "live", saved[0]))
        self.addCleanup(lambda: (setattr(km, "_working_notes", saved[1]), setattr(km, "_name_of", saved[2]),
                                 setattr(km, "_cwd_of", saved[3]), setattr(km, "_identity_of", saved[4])))

    def test_session_rows_assembles_both_backends(self):
        self._stub(
            live={"sid-t": {"state": "working", "backend": "tmux"},
                  "sid-s": {"state": "waiting", "backend": "sdk"}},
            notes={"sid-t": "owns feed.ts"},           # SDK has no working-note yet (P3) → ''
            names={"sid-t": ("alpha", "/work/a", "#112233", "#ffffff"),
                   "sid-s": ("beta", "/work/b", "blue", "white")})
        rows = {r["id"]: r for r in km._session_rows()}
        self.assertEqual(set(rows), {"sid-t", "sid-s"})
        self.assertEqual(rows["sid-t"], {"id": "sid-t", "name": "alpha", "state": "working", "dir": "/work/a",
                                         "bg": "#112233", "fg": "#ffffff", "working": "owns feed.ts", "backend": "tmux"})
        self.assertEqual(rows["sid-s"], {"id": "sid-s", "name": "beta", "state": "waiting", "dir": "/work/b",
                                         "bg": "blue", "fg": "white", "working": "", "backend": "sdk"})

    def test_empty_when_no_live_sessions(self):
        self._stub(live={}, notes={}, names={})
        self.assertEqual(km._session_rows(), [])


if __name__ == "__main__":
    unittest.main()
