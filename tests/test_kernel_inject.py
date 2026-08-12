#!/usr/bin/env python3
"""Composer↔pane input consistency (the user 2026-06-19): the kernel CLEARS the pane's input box before it
pastes a message, and CLEARS the prompt Claude Code restores on interrupt — so Stop → type-and-send can no
longer concatenate a recalled prompt with the new message. Self-contained: drives the tmux helpers with a
fake subprocess so it doesn't share test_kernel.py's setUp.
"""
import os
import unittest
from unittest import mock
from importlib.machinery import SourceFileLoader
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
# These exercise tmux BEHAVIOUR (they stub subprocess.run and assert on the argv). Declare a tmux
# host explicitly so they assert the same thing on a machine without tmux installed, where the
# backend is otherwise inert by design (see TmuxBackend.available).
os.environ["ROMP_TMUX_AVAILABLE"] = "1"
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
km = SourceFileLoader("romp_kernel_inj", os.path.join(BIN, "romp-kernel")).load_module()


class _Res:
    def __init__(self, stdout=""):
        self.stdout = stdout


class Inject(unittest.TestCase):
    def setUp(self):
        self.calls = []

        def rec(args, **kw):
            self.calls.append(list(args))
            return _Res("")            # stdout "" → not in copy-mode, no image paths left in the input
        self.p_run = mock.patch.object(km.subprocess, "run", side_effect=rec)
        self.p_sleep = mock.patch.object(km.time, "sleep", lambda *a, **k: None)
        self.p_run.start()
        self.p_sleep.start()

    def tearDown(self):
        self.p_run.stop()
        self.p_sleep.stop()

    def _cmds(self):
        return [c[1:] for c in self.calls if c and c[0] == "tmux"]   # the tmux sub-command sequence

    CLEAR = ["send-keys", "-t", "sess", "C-a", "BSpace"]

    def test_clear_selects_all_then_deletes(self):
        km._clear_pane_input("sess")
        self.assertEqual(self._cmds(), [self.CLEAR], "Ctrl+A selects the whole input, Backspace deletes it")

    def test_clear_is_a_noop_without_a_name(self):
        km._clear_pane_input("")
        self.assertEqual(self.calls, [])

    def test_interrupt_stops_then_wipes_the_restored_prompt(self):
        km._interrupt("sess", _async=False)
        cmds = self._cmds()
        esc = ["send-keys", "-t", "sess", "Escape"]
        self.assertIn(esc, cmds, "Esc stops the turn")
        self.assertIn(self.CLEAR, cmds, "then the restored prompt is cleared")
        self.assertLess(cmds.index(esc), cmds.index(self.CLEAR), "stop BEFORE clear (let the restore land first)")

    def test_inject_clears_before_pasting_so_it_replaces_not_appends(self):
        km._tmux_send("sess", "hello", _async=False)
        cmds = self._cmds()
        paste = next(c for c in cmds if c[:1] == ["paste-buffer"])
        self.assertIn(self.CLEAR, cmds, "the input is cleared as part of the inject")
        self.assertLess(cmds.index(self.CLEAR), cmds.index(paste),
                        "clear happens BEFORE the paste — a paste REPLACES, never appends to leftover text")
        self.assertEqual(cmds[-1], ["send-keys", "-t", "sess", "Enter"], "Enter submits after the paste")

    def test_inject_without_a_name_or_text_does_nothing(self):
        km._tmux_send("", "hello", _async=False)
        km._tmux_send("sess", "", _async=False)
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
