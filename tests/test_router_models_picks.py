#!/usr/bin/env python3
"""Extra models from your API gateway: a REMOVED id is refused on every pick road, and the new-session seed
never outlives the removal (review round, 2026-09-22). Before this only the typed "/model <id>" road consulted
_vouched_model; the setter, the WS setModel arm and the POST /new body took a pick unvouched, so after the switch
was turned on and then off a removed gateway id still landed on all three (registry, pending dots, pick memory).
And a dormant pick had written the id into sdk-defaults.json, which spawn copies into every new registry row
unchecked, so every new session launched on the removed id. Pinned here:

- _pick_vouched: ONE rule for every road — _vouched_model, or the Codex exception the typed road already admitted
  (a gpt-… value when the backend is the unowned route or the Codex backend); the typed road reads the same rule;
- the setter, the WS arm and the POST /new body each refuse a removed id AHEAD of anything that latches (no
  backend call, no pending stamp, no parked op, no pick memory), say so (a settingRefused frame on the WS arm in
  setEffort's shape, a `refused` echo on POST /new, one stderr line each), and still take a first-party pick
  and the Codex case;
- the create door resets a seed the kernel cannot vouch for, LOUDLY, through write_sdk_default (a fresh modelTok,
  so a live pick's later refusal can stand down), and the new row launches on the account default; a vouched
  seed is left alone.

Synthetic only: placeholder UUIDs, invented gateway ids (gw-6-astra …), a temp state root with session hosts
off, a stub backend that records what it was asked, no network.
"""
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only pytest runs
# conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
for _v in ("ROMP_ROUTER_MODELS", "ROMP_ROUTER_MODELS_URL", "ROMP_MODEL_CATALOG"):
    os.environ.pop(_v, None)
km = load_source("romp_kernel_router_picks", os.path.join(BIN, "romp-kernel"))
sb = load_source("romp_sdk_backend_router_picks", os.path.join(BIN, "romp_sdk_backend.py"))
km.jd.STATE.mkdir(parents=True, exist_ok=True)
(km.jd.STATE / "session-hosts").write_text("off")   # this root is outside conftest's belt (repo rule, 2026-09-11)

DECLARED = "gw-6-astra, gw-7-nova"
REMOVED = "gw-6-astra"
SID = "11111111-2222-4333-8444-555555555555"


def _env(tc, key, value):
    prev = os.environ.get(key)
    if value is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = value
    tc.addCleanup(lambda: os.environ.__setitem__(key, prev) if prev is not None else os.environ.pop(key, None))


class _Recorder:
    """A backend that records what it was asked and refuses nothing: every latch the roads could leave is
    then visible in one place (calls), next to the kernel-side stamps."""

    def __init__(self):
        self.calls = []

    def owns(self, sid):
        return True

    def set_model(self, sid, value):
        self.calls.append((sid, value))
        return True

    def busy(self, sid):
        return None

    def model_switches_live(self):
        return False

    def forwards_sends(self):
        return True


class _Codex(_Recorder):
    pass


class _OnThenOff(unittest.TestCase):
    """The switch flipped on (the declared families installed) and then off (removed) before each test, with
    the model globals snapshotted and restored around it, as the feature module's _Catalog does. Every
    kernel-side latch a pick can leave is cleared before and after."""

    def setUp(self):
        self._choices = [dict(c) for c in km.MODEL_CHOICES]
        self._values = set(km._MODEL_VALUES)
        self._judge = set(km._JUDGE_MODEL_VALUES)
        self._rank = list(km._MODEL_RANK)
        self._installed = set(km._ROUTER_INSTALLED)
        self._by_set = {k: set(v) for k, v in km._ROUTER_INSTALLED_BY_SET.items()}
        self._ever = set(km._ROUTER_EVER)
        self._gen = km._ROUTER_GEN[0]
        self._sb_ids = sb._ROUTER_IDS
        for v in ("ROMP_ROUTER_MODELS", "ROMP_ROUTER_MODELS_URL", "ROMP_MODEL_CATALOG", "ANTHROPIC_BASE_URL"):
            _env(self, v, None)
        self.store = km.jd.STATE / km.ROUTER_MODELS_FILE
        self.store.unlink(missing_ok=True)
        self._saved = (km._models_changed, km._router_gateway_configured, km._compacting_now, km._limit_hold,
                       km._working_now, km._push_soon, km._push_all, km._note_unknown_model, km._codex,
                       km.Sessions.backend_for, km._kernel_knows)
        km._models_changed = lambda: None
        km._router_gateway_configured = lambda: (True, None)
        km._compacting_now = lambda sid: False
        km._limit_hold = lambda sid: None
        km._working_now = lambda sid: False
        km._push_soon = lambda: None
        km._push_all = lambda: None
        self.unknown = []
        km._note_unknown_model = lambda mid: self.unknown.append(mid)
        self.codex = _Codex()
        km._codex = lambda: self.codex
        km._kernel_knows = lambda sid: True
        self.be = _Recorder()
        km.Sessions.backend_for = staticmethod(lambda sid: self.be)
        self._clear_latches()
        self.err = io.StringIO()
        self._p = mock.patch.object(km.sys, "stderr", self.err)
        self._p.start()
        _env(self, "ROMP_ROUTER_MODELS", DECLARED)
        km._set_router_models(True, gt=1700000000000)
        self.assertTrue(km._vouched_model(REMOVED), "installed while on")
        km._set_router_models(False, gt=1700000000001)
        self.assertFalse(km._vouched_model(REMOVED), "removed at off")
        self.err.truncate(0); self.err.seek(0)

    def tearDown(self):
        self._p.stop()
        (km._models_changed, km._router_gateway_configured, km._compacting_now, km._limit_hold,
         km._working_now, km._push_soon, km._push_all, km._note_unknown_model, km._codex,
         km.Sessions.backend_for, km._kernel_knows) = self._saved
        km.MODEL_CHOICES[:] = self._choices
        km._MODEL_VALUES.clear(); km._MODEL_VALUES.update(self._values)
        km._JUDGE_MODEL_VALUES.clear(); km._JUDGE_MODEL_VALUES.update(self._judge)
        km._MODEL_RANK[:] = self._rank
        km._ROUTER_INSTALLED.clear(); km._ROUTER_INSTALLED.update(self._installed)
        for k, v in self._by_set.items():
            km._ROUTER_INSTALLED_BY_SET[k].clear(); km._ROUTER_INSTALLED_BY_SET[k].update(v)
        km._ROUTER_EVER.clear(); km._ROUTER_EVER.update(self._ever)
        km._ROUTER_GEN[0] = self._gen
        sb._ROUTER_IDS = self._sb_ids
        self.store.unlink(missing_ok=True)
        self._clear_latches()

    def _clear_latches(self):
        km._model_switch_pending.clear()
        km._pending_ops.clear()
        (km.jd.STATE / km.MODEL_PICKS_FILE_NAME).unlink(missing_ok=True)

    def assertNothingLatched(self):
        self.assertEqual(self.be.calls, [], "the backend was never asked")
        self.assertNotIn(SID, km._model_switch_pending, "no switching-dots stamp")
        self.assertNotIn(SID, km._pending_ops, "no parked op")
        self.assertFalse((km.jd.STATE / km.MODEL_PICKS_FILE_NAME).exists(), "no pick memory write")
        self.assertEqual(self.unknown, [], "no staleness refresh for the id")
        self.assertIn(REMOVED, self.err.getvalue(), "the refusal is said on stderr, naming the id")


class Rule(_OnThenOff):
    def test_one_rule_for_every_road(self):
        self.assertFalse(km._pick_vouched(REMOVED, self.be))
        self.assertFalse(km._pick_vouched(REMOVED, self.codex), "the Codex exception is gpt-shaped only")
        self.assertTrue(km._pick_vouched("sonnet", self.be))
        self.assertTrue(km._pick_vouched("claude-fable-5", self.be))
        self.assertTrue(km._pick_vouched("default", self.be))
        # the Codex exception, exactly as the typed road admitted it: a gpt-… value on the Codex backend or the
        # unowned route (a dead Codex session still reports its backend), never on another backend or no backend
        self.assertTrue(km._pick_vouched("gpt-5-codex", self.codex))
        self.assertTrue(km._pick_vouched("gpt-5-codex", km._UNOWNED))
        self.assertFalse(km._pick_vouched("gpt-5-codex", self.be))
        self.assertFalse(km._pick_vouched("gpt-5-codex", None))
        # …or a CodexBackend by class: the setter reads the rule now, and tests/test_model_live_midturn.py drives
        # it with a real CodexBackend of its own, never the kernel's singleton

        class CodexBackend(_Recorder):
            pass
        self.assertTrue(km._pick_vouched("gpt-5-codex", CodexBackend()))
        km._set_router_models(True, gt=1700000000002)
        self.assertTrue(km._pick_vouched(REMOVED, self.be), "installed again → vouched again")

    def test_the_typed_road_reads_the_same_rule_and_still_refuses(self):
        import inspect
        src = inspect.getsource(km._route_setter_command)
        self.assertIn("_pick_vouched(value, be)", src, "the typed road is the rule's fourth reader, not a fork of it")
        # a typed pick of the removed id is no meta command (the CLI's own error, as before); nothing latches
        self.assertFalse(km._route_setter_command(self.be, SID, "/model " + REMOVED))
        self.assertEqual(self.be.calls, [])
        self.assertNotIn(SID, km._model_switch_pending)
        self.assertTrue(km._route_setter_command(self.be, SID, "/model sonnet"))
        self.assertEqual(self.be.calls, [(SID, "sonnet")])
        self.assertTrue(km._route_setter_command(self.codex, SID, "/model gpt-5-codex"))
        self.assertEqual(self.codex.calls, [(SID, "gpt-5-codex")])


class SetterRoad(_OnThenOff):
    def test_a_removed_id_is_refused_ahead_of_every_latch(self):
        self.assertIsNone(km._set_model_or_park(self.be, SID, REMOVED), "the third verdict: refused")
        self.assertNothingLatched()

    def test_a_first_party_pick_and_the_codex_case_still_fire(self):
        self.assertIs(km._set_model_or_park(self.be, SID, "sonnet"), False)
        self.assertEqual(self.be.calls, [(SID, "sonnet")])
        self.assertIs(km._set_model_or_park(self.codex, SID, "gpt-5-codex"), False)
        self.assertEqual(self.codex.calls, [(SID, "gpt-5-codex")])

    def test_an_installed_id_fires_while_the_switch_is_on(self):
        km._set_router_models(True, gt=1700000000002)
        self.assertIs(km._set_model_or_park(self.be, SID, REMOVED), False)
        self.assertEqual(self.be.calls, [(SID, REMOVED)])


class WsRoad(_OnThenOff):
    def setUp(self):
        super().setUp()
        self.sent = []
        self.client = {"send": lambda s: self.sent.append(json.loads(s)), "app": "chat"}

    def _refusals(self):
        return [f for f in self.sent if f.get("type") == "settingRefused"]

    def test_a_removed_id_is_refused_on_the_timelines_own_frame(self):
        self.assertTrue(km._drive({"type": "setModel", "id": SID, "value": REMOVED}, self.client))
        self.assertNothingLatched()
        fr = self._refusals()
        self.assertEqual(len(fr), 1, self.sent)
        # setEffort's refusal frame, flag model: gesture command, the sid, the flag the pending map is filed under
        self.assertEqual((fr[0]["gesture"], fr[0]["sid"], fr[0]["flag"]), ("command", SID, "model"))
        self.assertIn(REMOVED, fr[0]["text"])
        self.assertEqual([f for f in self.sent if f.get("type") == "warn"], [], "never a bare warn")

    def test_a_first_party_pick_and_the_codex_case_still_land(self):
        self.assertTrue(km._drive({"type": "setModel", "id": SID, "value": "opus"}, self.client))
        self.assertEqual(self.be.calls, [(SID, "opus")])
        km.Sessions.backend_for = staticmethod(lambda sid: self.codex)
        self.assertTrue(km._drive({"type": "setModel", "id": SID, "value": "gpt-5-codex"}, self.client))
        self.assertEqual(self.codex.calls, [(SID, "gpt-5-codex")])
        self.assertEqual(self._refusals(), [])


class NewBodyRoad(_OnThenOff):
    def test_a_removed_id_is_refused_in_the_echo(self):
        out = km._apply_new_session_prefs(SID, {"model": REMOVED})
        self.assertNothingLatched()
        self.assertNotIn("model", out, "never echoed as applied")
        self.assertIn(REMOVED, out.get("refused", ""), out)

    def test_a_first_party_pick_and_the_codex_case_still_echo_as_applied(self):
        self.assertEqual(km._apply_new_session_prefs(SID, {"model": "claude-fable-5"}), {"model": "claude-fable-5"})
        self.assertEqual(self.be.calls, [(SID, "claude-fable-5")])
        km.Sessions.backend_for = staticmethod(lambda sid: self.codex)
        self.assertEqual(km._apply_new_session_prefs(SID, {"model": "gpt-5-codex"}), {"model": "gpt-5-codex"})
        self.assertEqual(self.codex.calls, [(SID, "gpt-5-codex")])


class Seed(_OnThenOff):
    """The create door, with the REAL SdkBackend spawn over this root (the copy of the seed into the row is the
    line under test) and the connect and the pushes stubbed."""

    def setUp(self):
        super().setUp()
        self.sdk = sb.SdkBackend(km.jd.STATE, "/bin/true", lambda *a, **k: None)
        self.sdk.connect = lambda sid: None
        self._saved2 = (km._sdk, km._pick_identity_color, km._commands_for_cwd, km._mark_views_dirty,
                        km._push_session_now)
        km._sdk = lambda: self.sdk
        km._pick_identity_color = lambda: ("#000000", "#ffffff")
        km._commands_for_cwd = lambda cwd: None
        km._mark_views_dirty = lambda: None
        km._push_session_now = lambda sid: None
        self.cwd = tempfile.mkdtemp()
        self.seed = km.jd.STATE / "sdk-defaults.json"
        self.seed.unlink(missing_ok=True)
        self.addCleanup(lambda: self.seed.unlink(missing_ok=True))

    def tearDown(self):
        (km._sdk, km._pick_identity_color, km._commands_for_cwd, km._mark_views_dirty,
         km._push_session_now) = self._saved2
        super().tearDown()

    def test_a_removed_seed_is_reset_loudly_and_the_row_launches_on_the_default(self):
        sb.write_sdk_default(km.jd.STATE, model=REMOVED)
        tok = sb.read_sdk_defaults(km.jd.STATE)["modelTok"]
        sid, extra = km._create_sdk_session_inner("web", self.cwd)
        self.assertNotIn("error", extra)
        reg = sb.read_reg(km.jd.STATE, sid)
        self.assertNotEqual(reg.get("model"), REMOVED)
        self.assertFalse(reg.get("model"), "the row launches on the account default: %r" % reg.get("model"))
        d = sb.read_sdk_defaults(km.jd.STATE)
        self.assertEqual(d["model"], "default")
        self.assertNotEqual(d.get("modelTok"), tok, "written through write_sdk_default: a fresh token, never a raw file write")
        self.assertIn(REMOVED, self.err.getvalue(), "the reset is said, naming the id")

    def test_a_vouched_seed_is_left_alone(self):
        sb.write_sdk_default(km.jd.STATE, model="claude-fable-5")
        before = sb.read_sdk_defaults(km.jd.STATE)
        sid, _ = km._create_sdk_session_inner("api", self.cwd)
        self.assertEqual(sb.read_reg(km.jd.STATE, sid).get("model"), "claude-fable-5")
        self.assertEqual(sb.read_sdk_defaults(km.jd.STATE), before)
        self.assertEqual(self.err.getvalue(), "")

    def test_an_installed_seed_is_left_alone_while_the_switch_is_on(self):
        km._set_router_models(True, gt=1700000000002)
        sb.write_sdk_default(km.jd.STATE, model=REMOVED)
        before = sb.read_sdk_defaults(km.jd.STATE)
        sid, _ = km._create_sdk_session_inner("tests", self.cwd)
        self.assertEqual(sb.read_reg(km.jd.STATE, sid).get("model"), REMOVED)
        self.assertEqual(sb.read_sdk_defaults(km.jd.STATE), before)


if __name__ == "__main__":
    unittest.main()
