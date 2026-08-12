#!/usr/bin/env python3
"""Judges bill the account of the session they judge (the user 2026-08-12).

The incident this pins: per-session billing (f48af49c) claims the manager env's
ANTHROPIC_API_KEY out of os.environ (sdk_backend.work_api_key) so no session CLI
inherits it ambiently — but the judges' subprocess env was still a plain copy of
os.environ, taken AFTER that claim. On a host whose only credential is the env key
(no login), every judge call refused "Not logged in · Please run /login" for 13
hours (~53k errors) while the cards sat parked in Working with nothing on screen
saying why. The mechanics under test:

  * _work_key READS the key, never claims it: through the kernel's wire
    (_WORK_KEY_FN → sdk_backend.work_api_key, the one claimer) once it lands, and
    straight from os.environ before it / standalone — no second pop to race.
  * _judge_auth resolves a call's billing to the JUDGED SESSION's own pick (the
    registry's `auth`), with the session picker's exact fallback: explicit
    'login' → login; anything else → key when one exists, else login.
  * _judge_env strips the ambient key from every child env and injects it back
    explicitly for a key-mode call only (removal, not blanking — the CLI treats
    an empty var as key-mode-without-a-key and refuses).
  * A credential-class error envelope LATCHES judge-auth-down for the session
    (STATE/judge-auth.json); the session's next successful call clears it. Both
    edges are events — no timers, no per-build re-derivation.
  * build_feed floors a latched session's focus card to needs-you wearing the
    "judgeAuth" story (source pins, the build_feed test pattern), and the feed
    bundle carries the chip.

Synthetic sids only; the fixture key is an invented string; no real key material.
"""
import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from types import SimpleNamespace

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ.setdefault("XDG_STATE_HOME", tempfile.mkdtemp())
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
jd = SourceFileLoader("romp_judge_authbill", os.path.join(BIN, "romp-judge")).load_module()

FAKE_KEY = "romp-test-fixture-key-not-real"   # nothing under test validates the shape, so no sk- prefix:
                                              # the maintainer's gitleaks pre-commit hook rightly refuses
                                              # anything that even looks like a real key in a commit
SID = "11111111-2222-3333-4444-555555555555"
NOT_LOGGED_IN = "Not logged in · Please run /login"   # the CLI's live refusal, verbatim shape


class _JudgeAuthBase(unittest.TestCase):
    """Clean slate per test: no wire, no latch file, no ambient key, no session reg."""

    def setUp(self):
        self._env_before = os.environ.pop("ANTHROPIC_API_KEY", None)
        self._fn_before = jd._WORK_KEY_FN
        jd._WORK_KEY_FN = None
        jd._auth_cache[:] = [None, {}]
        jd.SDKDIR.mkdir(parents=True, exist_ok=True)
        for p in (jd.JUDGE_AUTH, jd.SDKDIR / (SID + ".json"),
                  jd.STATE / "retry-paused.json", jd.STATE / "usage.json"):
            try:
                p.unlink()
            except OSError:
                pass

    def tearDown(self):
        jd._WORK_KEY_FN = self._fn_before
        os.environ.pop("ANTHROPIC_API_KEY", None)
        if self._env_before is not None:
            os.environ["ANTHROPIC_API_KEY"] = self._env_before
        jd._judge_ctx.fsid = None
        # leave NOTHING latched in the shared STATE: the suite runs every test file against one
        # XDG state home, and a leftover judge-auth.json row for the shared synthetic sid floors
        # OTHER files' build_feed cards to needs-you (25 stays-in-Working tests, found 2026-08-12)
        jd._auth_cache[:] = [None, {}]
        for p in (jd.JUDGE_AUTH, jd.SDKDIR / (SID + ".json")):
            try:
                p.unlink()
            except OSError:
                pass

    def _reg(self, auth):
        (jd.SDKDIR / (SID + ".json")).write_text(json.dumps({"sid": SID, "auth": auth}))


class WorkKeyRead(_JudgeAuthBase):
    def test_reads_through_the_kernel_wire_once_it_lands(self):
        jd._WORK_KEY_FN = lambda: FAKE_KEY
        self.assertEqual(jd._work_key(), FAKE_KEY)

    def test_reads_the_environment_before_the_wire_lands_without_claiming_it(self):
        os.environ["ANTHROPIC_API_KEY"] = FAKE_KEY
        self.assertEqual(jd._work_key(), FAKE_KEY)
        # never a second claimer: the variable is still there for sdk_backend's own pop
        self.assertEqual(os.environ.get("ANTHROPIC_API_KEY"), FAKE_KEY)

    def test_a_broken_wire_reads_as_no_key_not_a_crash(self):
        jd._WORK_KEY_FN = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        self.assertEqual(jd._work_key(), "")


class JudgeBillingResolution(_JudgeAuthBase):
    def test_defaults_to_the_key_when_one_exists(self):
        jd._WORK_KEY_FN = lambda: FAKE_KEY
        self.assertEqual(jd._judge_auth(SID), "key")      # no reg on disk
        self.assertEqual(jd._judge_auth(None), "key")     # fleet-level call, same default

    def test_defaults_to_login_when_no_key_exists(self):
        self.assertEqual(jd._judge_auth(SID), "login")
        self.assertEqual(jd._judge_auth(None), "login")

    def test_an_explicit_login_pick_wins_over_an_available_key(self):
        jd._WORK_KEY_FN = lambda: FAKE_KEY
        self._reg("login")
        self.assertEqual(jd._judge_auth(SID), "login")

    def test_a_key_pick_rides_the_key(self):
        jd._WORK_KEY_FN = lambda: FAKE_KEY
        self._reg("key")
        self.assertEqual(jd._judge_auth(SID), "key")

    def test_a_key_pick_with_no_key_falls_to_login_like_the_session_itself(self):
        self._reg("key")   # effective_auth logs the fall loudly and launches on login; judges mirror it
        self.assertEqual(jd._judge_auth(SID), "login")


class JudgeEnvBilling(_JudgeAuthBase):
    def test_key_mode_injects_the_key_explicitly(self):
        jd._WORK_KEY_FN = lambda: FAKE_KEY
        env = jd._judge_env("triage", "key")
        self.assertEqual(env.get("ANTHROPIC_API_KEY"), FAKE_KEY)

    def test_login_mode_carries_no_key_at_all(self):
        jd._WORK_KEY_FN = lambda: FAKE_KEY
        env = jd._judge_env("triage", "login")
        self.assertNotIn("ANTHROPIC_API_KEY", env)        # removal, not blanking

    def test_the_ambient_key_is_stripped_from_a_login_mode_child_standalone(self):
        # standalone (romp-judge --once): nobody claimed the env key, but a login-mode child
        # must still not inherit it — billing is an explicit choice per call, never ambient
        os.environ["ANTHROPIC_API_KEY"] = FAKE_KEY
        env = jd._judge_env("index", "login")
        self.assertNotIn("ANTHROPIC_API_KEY", env)
        env = jd._judge_env("index", "key")
        self.assertEqual(env.get("ANTHROPIC_API_KEY"), FAKE_KEY)

    def test_the_existing_env_contract_survives(self):
        os.environ["TMUX"] = "sock,1,0"
        try:
            env = jd._judge_env("index", "login")
            self.assertNotIn("TMUX", env)
            self.assertEqual(env.get("ROMP_SUMMARIZING"), "1")
            self.assertEqual(env.get("MAX_THINKING_TOKENS"), "0")
        finally:
            os.environ.pop("TMUX", None)


class AuthErrorClass(_JudgeAuthBase):
    def test_credential_failures_classify(self):
        for s in (NOT_LOGGED_IN, "API key is invalid · Please run /login",
                  "invalid x-api-key", "Failed to authenticate",
                  "OAuth token has expired", '{"type":"authentication_error"}'):
            self.assertTrue(jd._is_auth_error(s), s)

    def test_transient_failures_do_not(self):
        for s in ("overloaded_error", "prompt is too long", "rate_limit_error",
                  "Internal server error", "", None):
            self.assertFalse(jd._is_auth_error(s), repr(s))


class AuthLatch(_JudgeAuthBase):
    def test_mark_then_clear_round_trip(self):
        jd._auth_down_mark(SID, "key", NOT_LOGGED_IN)
        row = jd._auth_down_map().get(SID)
        self.assertTrue(row and row["mode"] == "key" and row["note"] == NOT_LOGGED_IN)
        self.assertGreater(row["t"], 0)
        jd._auth_down_clear(SID)
        self.assertNotIn(SID, jd._auth_down_map())

    def test_repeat_marks_keep_the_first_failure_time_and_skip_identical_writes(self):
        jd._auth_down_mark(SID, "key", NOT_LOGGED_IN)
        t0 = jd._auth_down_map()[SID]["t"]
        m0 = jd.JUDGE_AUTH.stat().st_mtime_ns
        jd._auth_down_mark(SID, "key", NOT_LOGGED_IN)     # same evidence: no write, no mtime churn
        self.assertEqual(jd.JUDGE_AUTH.stat().st_mtime_ns, m0)
        jd._auth_down_mark(SID, "key", "API key is invalid")   # new evidence: note moves, t holds
        row = jd._auth_down_map()[SID]
        self.assertEqual(row["t"], t0)
        self.assertEqual(row["note"], "API key is invalid")

    def test_no_session_no_row(self):
        jd._auth_down_mark(None, "key", NOT_LOGGED_IN)
        jd._auth_down_mark("", "key", NOT_LOGGED_IN)
        self.assertEqual(jd._auth_down_map(), {})

    def test_clear_without_a_row_writes_nothing(self):
        jd._auth_down_clear(SID)
        self.assertFalse(jd.JUDGE_AUTH.exists())


class JudgeRunLatchAndInjection(_JudgeAuthBase):
    """_judge_run end to end with a fake CLI: the envelope drives the latch, the env carries the billing."""

    def _run(self, envelope, auth_reg=None, key=FAKE_KEY):
        if key:
            jd._WORK_KEY_FN = lambda: key
        if auth_reg:
            self._reg(auth_reg)
        jd._judge_ctx.fsid = SID
        seen = {}

        def fake_run(cmd, input=None, capture_output=None, text=None, cwd=None, env=None, timeout=None):
            seen["env"] = env
            return SimpleNamespace(stdout=json.dumps(envelope), stderr="", returncode=0)

        saved = jd.subprocess.run
        jd.subprocess.run = fake_run
        try:
            out = jd._judge_run("sonnet", "SYS", "u", judge="planner", tier="triage")
        finally:
            jd.subprocess.run = saved
        return out, seen

    def test_a_not_logged_in_envelope_latches_and_the_call_reports_failure(self):
        out, seen = self._run({"is_error": True, "result": NOT_LOGGED_IN})
        self.assertEqual(out, "")
        row = jd._auth_down_map().get(SID)
        self.assertTrue(row, "credential refusal must latch judge-auth-down")
        self.assertEqual(row["mode"], "key")
        self.assertIn("Not logged in", row["note"])
        self.assertEqual(seen["env"].get("ANTHROPIC_API_KEY"), FAKE_KEY)   # key-mode call carried the key

    def test_a_transient_error_envelope_does_not_latch(self):
        out, _ = self._run({"is_error": True, "result": "Overloaded, please retry"})
        self.assertEqual(out, "")
        self.assertEqual(jd._auth_down_map(), {})

    def test_the_next_success_clears_the_latch(self):
        self._run({"is_error": True, "result": NOT_LOGGED_IN})
        self.assertIn(SID, jd._auth_down_map())
        out, _ = self._run({"result": "ok", "usage": {}, "duration_ms": 3})
        self.assertEqual(out, "ok")
        self.assertNotIn(SID, jd._auth_down_map())

    def test_a_login_pick_launches_the_judge_with_a_clean_env(self):
        _, seen = self._run({"result": "ok", "usage": {}, "duration_ms": 3}, auth_reg="login")
        self.assertNotIn("ANTHROPIC_API_KEY", seen["env"])


class KernelWiringAndFloorPins(unittest.TestCase):
    """The kernel side, pinned the way every build_feed behavior is (inspect.getsource)."""

    @classmethod
    def setUpClass(cls):
        cls.km = SourceFileLoader("romp_kernel_authbill", os.path.join(BIN, "romp-kernel")).load_module()

    def test_the_kernel_wires_judges_to_the_one_key_claimer(self):
        import inspect
        self.assertIn("jd._WORK_KEY_FN = sbmod.work_api_key", inspect.getsource(self.km._sdk_locked))

    def test_build_feed_floors_a_latched_session_yielding_to_the_live_floors(self):
        import inspect
        src = inspect.getsource(self.km.build_feed)
        self.assertIn("_jauth_map = jd._auth_down_map()", src)
        self.assertIn("jerr and api_top is None and perm_top is None", src)
        self.assertIn('column = ("needs_input" if (api_block or nid == jauth_top or nid == perm_top', src)

    def test_the_floored_card_carries_the_judgeAuth_story(self):
        import inspect
        src = inspect.getsource(self.km.build_feed)
        self.assertIn('"state": "judgeAuth"', src)
        self.assertIn("the API key its judges bill is being refused. Fix the key (service.env)", src)
        self.assertIn("the login its judges bill is being refused. Sign in again (claude /login)", src)

    def test_the_judge_auth_classifier_mirrors_the_kernels(self):
        # judge.py loads standalone, so the classifier is a copy, not an import — the two must agree
        # on the strings that matter (each side may only ever grow strictly looser together).
        for s in ("Not logged in", "API key is invalid", "invalid x-api-key",
                  "failed to authenticate", "OAuth token has expired", "oauth token revoked",
                  "authentication_error", "overloaded", "rate_limit_error", ""):
            self.assertEqual(jd._is_auth_error(s), self.km._is_auth_error(s), s)

    def test_the_feed_bundle_carries_the_chip(self):
        ts = open(os.path.join(os.path.dirname(HERE), "ui", "webview", "feed.ts")).read()
        css = open(os.path.join(os.path.dirname(HERE), "ui", "webview", "feed.css")).read()
        self.assertIn('it.blocked?.state === "judgeAuth"', ts)
        self.assertIn("fask-jauth", ts)
        self.assertIn(".fask-jauth", css)


if __name__ == "__main__":
    unittest.main()
