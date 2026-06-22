#!/usr/bin/env python3
"""POST /send body parsing — the human->agent input channel the Obsidian track-changes
plugin posts to. The kernel then injects the text via _tmux_send (the same delivery the
chat composer's WS sendMessage uses), so the plugin never touches tmux itself.
"""
import os
import unittest
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


if __name__ == "__main__":
    unittest.main()
