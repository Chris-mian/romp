#!/usr/bin/env python3
"""A session that CANNOT START says why — instead of swallowing every message sent to it.

The failure this closes (the user 2026-07-28, on a fresh install): romp-sdk-setup had bailed on that
machine (a python3 with no ensurepip, so the venv was never built), the kernel logged ONE stderr line and
built the SDK backend anyway, and every SDK session then accepted messages it could never run. From the
user's side: a message sent to a session did nothing at all — no flip to working, no error — a brand-new
session behaved the same, and the model/effort readouts and the usage bars stayed blank (all three publish
only AFTER a connect that could never happen). tmux sessions worked throughout, so it read as an outage at
Anthropic rather than a missing local dependency.

What is pinned here:
  1. the backend detects its own missing dependency ONCE, up front, and reports EVERY session as unable to
     start — no session has to die first for the user to be told;
  2. the text names the REMEDY (bin/romp-sdk-setup), not the symptom, and never a bare ModuleNotFoundError;
  3. a launch failure recorded on a session survives on the registry (the thread that saw it is dying) and
     is cleared by the connect that DISPROVES it, never by a timer;
  4. queued messages do NOT vanish when the session's thread dies — the persisted queue answers
     pending_queued, so what the user typed stays on screen;
  5. the account-out-of-usage flavor is classified apart, because that queue is parked, not broken.

SYNTHETIC fixtures only (placeholder ids, hostname TESTHOST).
"""
import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
sb = SourceFileLoader("romp_sdk_backend_launcherr", os.path.join(BIN, "romp_sdk_backend.py")).load_module()

SID = "11111111-2222-3333-4444-555555555555"
OTHER = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


class _FakeSess:
    """The two attributes _record_launch_error reads off a session."""

    def __init__(self, sid=SID, name="api"):
        self.sid = sid
        self.name = name


def _backend(state, missing=False):
    saved = sb.sdk_importable
    sb.sdk_importable = lambda: not missing
    try:
        return sb.SdkBackend(state, "/bin/true", lambda *a, **k: None)
    finally:
        sb.sdk_importable = saved


class MissingDependencyIsReportedForEverySession(unittest.TestCase):
    """The dep is checked at construction, so the report needs no session to have crashed first."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.state = self.td.name

    def tearDown(self):
        self.td.cleanup()

    def test_every_session_reports_unable_to_start(self):
        be = _backend(self.state, missing=True)
        for sid in (SID, OTHER):
            err = be.launch_error(sid)
            self.assertIsNotNone(err, "a session that cannot possibly run must not read as fine")
            self.assertFalse(err["limit"], "a missing dependency is not a usage limit")

    def test_the_text_names_the_remedy_not_the_symptom(self):
        err = _backend(self.state, missing=True).launch_error(SID)
        self.assertIn("romp-sdk-setup", err["text"],
                      "the user needs the command to run, not the name of a python module")
        self.assertNotIn("ModuleNotFoundError", err["text"])
        self.assertIn("tmux", err["text"], "say what still works — tmux sessions are unaffected")

    def test_a_healthy_install_reports_nothing(self):
        self.assertIsNone(_backend(self.state, missing=False).launch_error(SID))


class RecordedLaunchFailures(unittest.TestCase):
    """A failure the thread saw on its way out has to outlive the thread — so it lands on the registry."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.be = _backend(self.td.name, missing=False)

    def tearDown(self):
        self.td.cleanup()

    def _reg(self, sid=SID):
        return sb.read_reg(Path(self.td.name), sid) or {}

    def test_an_import_failure_records_the_remedy(self):
        self.be._record_launch_error(_FakeSess(), ImportError("No module named 'claude_agent_sdk'"))
        rec = self._reg()["launchError"]
        self.assertIn("romp-sdk-setup", rec["text"])
        self.assertTrue(rec["dep"])
        self.assertEqual(self.be.launch_error(SID)["text"], rec["text"])

    def test_an_ordinary_failure_keeps_its_own_text(self):
        self.be._record_launch_error(_FakeSess(), RuntimeError("claude exited with code 1"))
        rec = self._reg()["launchError"]
        self.assertIn("claude exited with code 1", rec["text"])
        self.assertFalse(rec["limit"], "a plain crash is not a usage limit")

    def test_the_connect_that_disproves_it_clears_it(self):
        self.be._record_launch_error(_FakeSess(), RuntimeError("transport closed"))
        self.assertIsNotNone(self.be.launch_error(SID))
        self.be._clear_launch_error(SID)
        self.assertIsNone(self.be.launch_error(SID),
                          "the record clears on the connect that disproves it, never on a timer")

    def test_clearing_a_session_that_never_failed_is_a_no_op(self):
        self.be._clear_launch_error(SID)
        self.assertIsNone(self.be.launch_error(SID))


class LaunchFailureText(unittest.TestCase):
    """Pick the line that actually names the cause, and know a usage limit when the CLI states one."""

    def test_the_clis_own_stderr_wins_over_the_exception_repr(self):
        exc = RuntimeError("Command failed")
        exc.stderr = "You've hit your session limit · resets 4:00pm (America/Los_Angeles)"
        self.assertIn("session limit", sb.launch_failure_text(exc))

    def test_a_long_stderr_dump_is_bounded(self):
        exc = RuntimeError("boom")
        exc.stderr = "x" * 5000
        self.assertLessEqual(len(sb.launch_failure_text(exc)), 601, "this text lands in a chat card")

    def test_a_bare_exception_still_yields_text(self):
        self.assertIn("ValueError", sb.launch_failure_text(ValueError("no executable found")))

    def test_usage_limits_are_classified_apart_from_breakage(self):
        self.assertTrue(sb.is_launch_limit("You've hit your session limit · resets 4:00pm"))
        self.assertTrue(sb.is_launch_limit("usage limit reached"))
        self.assertFalse(sb.is_launch_limit("claude: command not found"))
        self.assertFalse(sb.is_launch_limit(""))


class QueuedMessagesSurviveTheSessionsDeath(unittest.TestCase):
    """What the user typed must stay on screen when the CLI dies — it is still owed to them."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.be = _backend(self.td.name, missing=False)

    def tearDown(self):
        self.td.cleanup()

    def test_the_persisted_queue_answers_when_no_session_is_running(self):
        typed = "set up the deploy script for the notes-api"
        self.be._update_reg(SID, queue=[typed])
        self.assertEqual(self.be.pending_queued(SID), [typed],
                         "a dead thread must not make the user's message vanish from the chat")

    def test_a_session_with_no_queue_reports_nothing(self):
        self.be._update_reg(SID, queue=[])
        self.assertEqual(self.be.pending_queued(SID), [])
        self.assertEqual(self.be.pending_queued(OTHER), [])

    def test_a_corrupt_queue_mirror_does_not_crash_the_chat(self):
        self.be._update_reg(SID, queue="not a list")
        self.assertEqual(self.be.pending_queued(SID), [])
        self.be._update_reg(OTHER, queue=[None, "", "keep me", 7])
        self.assertEqual(self.be.pending_queued(OTHER), ["keep me"])


class ContractConformance(unittest.TestCase):
    """launch_error is part of the backend contract, with a None default for tmux."""

    def test_the_abc_defaults_to_no_known_failure(self):
        mod = SourceFileLoader(
            "romp_session_backend_launcherr",
            os.path.join(BIN, "romp_session_backend.py")).load_module()
        self.assertIsNone(mod.SessionBackend.launch_error(object(), SID),
                          "a backend whose CLI launches into a visible pane reports nothing here")


class KernelSurfaces(unittest.TestCase):
    """The kernel side: the error reaches the chat, and a usage-limit launch parks the queue instead."""

    @classmethod
    def setUpClass(cls):
        cls.kernel_src = Path(BIN).parent.joinpath("kernel", "kernel.py").read_text()

    def test_the_chat_raises_a_card_for_a_launch_failure(self):
        self.assertIn("_lerr = _launch_error(sid)", self.kernel_src,
                      "the chat build must ask the backend why the session could not start")
        self.assertIn('"This session\'s claude process could not start — %s" % _lerr["text"]',
                      self.kernel_src)
        self.assertIn('_lerr["text"] if _lerr.get("dep")', self.kernel_src,
                      "a missing dependency already reads as a sentence — don't wrap it in a second one")

    def test_a_usage_limit_launch_parks_the_queue_instead_of_erroring(self):
        self.assertIn('if _lerr and not _lerr.get("limit")', self.kernel_src,
                      "a parked queue is a wait, not damage — it must not also raise a red card")
        self.assertIn('_le = _launch_error(sid)', self.kernel_src,
                      "_limit_hold reads the launch that the limit refused — usage.json cannot see it")


if __name__ == "__main__":
    unittest.main()


class SessionCreationRefusesWhenTheSdkCannotRun(unittest.TestCase):
    """The gap the user actually hit: they created a session in the BROWSER and got no error at all.

    Both creation paths (the WS createSession op and POST /new for `romp new`) already carried the
    right refusal — never silently hand back something that can't work — and both asked `_sdk()`.
    But the backend object is built even with the dependency missing, on purpose, so it can keep
    owning the registry and the chat. `_sdk()` therefore answered "yes" and the refusal never fired:
    a session was created that could never run, silently (the user 2026-07-28)."""

    def test_the_backend_reports_its_own_unavailability(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.assertFalse(_backend(td.name, missing=True).available(),
                         "a backend that cannot import its SDK must not answer 'ready'")
        self.assertTrue(_backend(td.name, missing=False).available())

    def test_both_creation_paths_gate_on_ready_not_on_the_object(self):
        src = Path(BIN).parent.joinpath("kernel", "kernel.py").read_text()
        self.assertIn("def _sdk_ready():", src)
        self.assertIn("if _sdk_ready():", src, "the WS createSession op")
        self.assertIn("if not _sdk_ready():", src, "POST /new, the `romp new` path")
        self.assertNotIn("if _sdk():\n                        _create_sdk_session", src,
                         "the old check took a dependency-less backend as a yes")

    def test_the_refusal_names_the_remedy_and_says_nothing_was_created(self):
        src = Path(BIN).parent.joinpath("kernel", "kernel.py").read_text()
        self.assertIn("SDK_SETUP_HINT = ", src)
        i = src.index("SDK_SETUP_HINT = ")
        hint = src[i:i + 400]
        self.assertIn("Session not created", hint, "say plainly that nothing was made")
        self.assertIn("romp-sdk-setup", hint, "name the one command that fixes it")
