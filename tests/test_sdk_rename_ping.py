#!/usr/bin/env python3
"""The rename ping (the user 2026-08-24; own-record form 2026-08-25): a renamed session hears its
OWN new name on its next wake — rename() stamps the reg (renameNote, restart-proof, and ONLY when
prior turns exist under the old name: a fresh session has no stale self-knowledge to correct), and
send() delivers RENAME_NUDGE as its OWN machine-dressed record ahead of whatever next enters the
session — never inside the user's bubble (the 2026-08-25 sighting: the bookkeeping line rendered as
the user's very first words), never a wake of its own. Voice pinned in test_injected_voice.py.
Deterministic: reg-level + source pins, no real claude processes."""
import os
import tempfile
import unittest
from datetime import datetime, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
sb = SourceFileLoader("romp_sdk_backend_renameping", os.path.join(BIN, "romp_sdk_backend.py")).load_module()

SID = "aaaaaaaa-1111-2222-3333-444444444444"
SRC = open(os.path.join(BIN, "romp_sdk_backend.py")).read()


def _backend(d):
    return sb.SdkBackend(d, "/bin/true", lambda *a, **k: None, log=lambda *a, **k: None)


class RenamePing(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.be = _backend(self.td.name)
        (Path(self.td.name) / "names").mkdir(parents=True, exist_ok=True)
        self.cwd = str(Path(self.td.name) / "proj")
        Path(self.cwd).mkdir()
        sb.write_reg(Path(self.td.name), SID, {"sid": SID, "name": "web", "cwd": self.cwd,
                                               "lastSid": SID})

    def tearDown(self):
        self.td.cleanup()

    def _write_history(self):
        # one prior turn under the old name — the transcript IS the record of prior turns
        tp = Path(sb.transcript_path(self.cwd, SID))
        tp.parent.mkdir(parents=True, exist_ok=True)
        tp.write_text('{"type": "user", "uuid": "u1"}\n')

    def test_rename_with_history_stamps_the_pending_note_beside_the_name(self):
        self._write_history()
        self.assertTrue(self.be.rename(SID, "tests"))
        reg = sb.read_reg(Path(self.td.name), SID)
        self.assertEqual(reg.get("name"), "tests")
        self.assertEqual(reg.get("renameNote"), "tests",
                         "reg-persisted, so the ping survives a kernel restart unspoken")

    def test_rename_before_the_first_turn_pings_nothing(self):
        # the 2026-08-25 sighting's second half: a brand-new session has no stale self-knowledge
        # to correct — it learns its name the normal way, and its user's first words stay first
        self.assertTrue(self.be.rename(SID, "tests"))
        reg = sb.read_reg(Path(self.td.name), SID)
        self.assertEqual(reg.get("name"), "tests", "the rename itself still lands")
        self.assertIsNone(reg.get("renameNote"), "…but no ping is owed")

    def test_rename_of_an_unknown_sid_stamps_nothing(self):
        self.assertFalse(self.be.rename("99999999-0000-1111-2222-333333333333", "tests"))

    def test_send_delivers_the_ping_as_its_own_machine_record_once(self):
        # send()'s consume, pinned at source (driving a real send spawns a CLI): the ping is its
        # OWN record in the machine dress — NEVER string-prepended into the user's text (the
        # 2026-08-25 sighting: the bookkeeping line rendered inside the user's first bubble) —
        # delivered before the message that triggered it, once, and a slash command passes bare
        self.assertIn('if not text.lstrip().startswith("/"):', SRC, "a bare /compact must reach the CLI bare")
        self.assertIn('if _reg.get("renameNote"):', SRC)
        self.assertIn('self.send(sid, "<!-- romp-injected --><!-- romp-system -->" + RENAME_NUDGE % _note)',
                      SRC, "its own record, wearing the machine-sent dress (author 'romp', gray bubble)")
        self.assertNotIn('text = "%s\\n\\n%s" % (RENAME_NUDGE', SRC,
                         "the string-prepend form is GONE — it contaminated the user's own words")
        self.assertIn('self._update_reg(sid, renameNote=None)', SRC, "one delivery, then the note is spent")
        idx_clear = SRC.index('self._update_reg(sid, renameNote=None)')
        idx_send = SRC.index('self.send(sid, "<!-- romp-injected --><!-- romp-system -->" + RENAME_NUDGE')
        self.assertLess(idx_clear, idx_send, "cleared BEFORE the recursive send — the recursion terminates")
        self.assertNotIn("romp-injected", sb.RENAME_NUDGE,
                         "the constant stays bare prose; the dress is added only on the separate record")


if __name__ == "__main__":
    unittest.main()
