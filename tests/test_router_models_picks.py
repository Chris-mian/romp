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
- the create door resets a seed the kernel cannot vouch for, LOUDLY, through reset_sdk_default_model_if (a
  compare-and-swap on the value judged; a fresh modelTok,
  so a live pick's later refusal can stand down), and the new row launches on the account default; a vouched
  seed is left alone.

Synthetic only: placeholder UUIDs, invented gateway ids (gw-6-astra …), a temp state root with session hosts
off, a stub backend that records what it was asked, no network.
"""
import io
import json
import os
import sys
import tempfile
import time
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
        km._ROUTER_FETCH_GEN[0] = None; km._ROUTER_FETCH_FAILED_GEN[0] = None
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
        # the kernel tells the module registered as romp_sdk_backend: this harness's private copy is registered BEFORE
        # the on flip below, so the ids never land on a copy an earlier module registered (review round three; round
        # four found the lines had landed in tearDown, covering nothing)
        self._modpatch = mock.patch.dict(sys.modules, {"romp_sdk_backend": sb})
        self._modpatch.start()
        self.addCleanup(self._modpatch.stop)
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


class ParkedDrain(_OnThenOff):
    def test_a_pick_parked_while_on_and_drained_after_off_is_refused_at_fire_time(self):
        # the last road around the vouch: a ('model', id) op parked behind a queue while the switch was on fires from
        # _apply_pending_ops after the off flip; it is vouched when it fires, refused like a parked level (the stderr
        # line, the settingRefused frame the chat reads), and popped
        frames = []
        with mock.patch.object(km, "_send_to_app", lambda app, frame: frames.append((app, frame))):
            km._pending_ops[SID] = [("model", REMOVED)]
            km._apply_pending_ops()
        self.assertEqual(self.be.calls, [], "the backend was never asked")
        self.assertNotIn(SID, {k for k, v in km._pending_ops.items() if v}, "the op is popped, never wedging the queue")
        self.assertIn(REMOVED, self.err.getvalue())
        self.assertEqual([f for a, f in frames if f.get("type") == "settingRefused" and f.get("flag") == "model"],
                         [{"type": "settingRefused", "gesture": "command", "sid": SID, "flag": "model",
                           "text": km._model_refusal(REMOVED)}])

    def test_the_refusal_takes_this_picks_switching_dots_stamp_back(self):
        # the second reviewer's note: the refusal popped the op and sent the frame but left the stamp the setter put up at park time, so
        # both surfaces' dots rode it for 20 s
        with mock.patch.object(km, "_send_to_app", lambda app, frame: None):
            km._model_switch_pending[SID] = {"target": REMOVED, "until": time.time() + 20}
            km._pending_ops[SID] = [("model", REMOVED)]
            km._apply_pending_ops()
            self.assertNotIn(SID, km._model_switch_pending, "this pick's stamp is taken back")
            km._model_switch_pending[SID] = {"target": "sonnet", "until": time.time() + 20}   # a later pick's stamp
            km._pending_ops[SID] = [("model", REMOVED)]
            km._apply_pending_ops()
            self.assertIn(SID, km._model_switch_pending, "another pick's stamp is left")
        km._model_switch_pending.pop(SID, None)

    def test_a_parked_first_party_pick_still_fires(self):
        with mock.patch.object(km, "_send_to_app", lambda app, frame: None):
            km._pending_ops[SID] = [("model", "sonnet")]
            km._apply_pending_ops()
        self.assertEqual(self.be.calls, [(SID, "sonnet")])


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


class NewThreadRoad(_OnThenOff):
    """The comment-thread create door (the verify round's find: the one create door around the vouch)."""

    def _create(self, model):
        # the name claim is stubbed to REFUSE (recording the ask): a create that reaches it passed the vouch and stops
        # there, so the test never forks or sends
        claimed = []
        with mock.patch.object(km.Sessions, "backend_for", lambda sid: self.be), \
                mock.patch.object(km, "_sdk_ready", lambda: True), \
                mock.patch.object(km, "_session_row", lambda sid, now: {"name": "web", "path": str(km.jd.STATE / "none.jsonl")}), \
                mock.patch.object(km, "_claim_session_name", lambda nm, kind, sid: claimed.append(nm) or "claimed-in-test"):
            self.be.fork = lambda *a, **k: None
            err, tid = km._comment_create(SID, "", "a passage", "a comment", name="t1", model=model)
        return err, tid, claimed

    def test_a_removed_id_picked_in_the_dialog_is_refused_before_the_name_claim(self):
        err, tid, claimed = self._create(REMOVED)
        self.assertEqual((err, tid), (km._model_refusal(REMOVED), None))
        self.assertEqual(claimed, [], "nothing latched: no name claimed, no fork")
        self.assertIn(REMOVED, self.err.getvalue())

    def test_a_first_party_pick_passes_the_vouch(self):
        err, tid, claimed = self._create("sonnet")
        self.assertEqual((err, tid), ("claimed-in-test", None), "the vouch passed and the create went on to the name claim")
        self.assertEqual(claimed, ["t1"])

    def test_the_stored_default_refusal_is_said_once_per_create(self):
        # review round three: the create resolved the prefs twice (the vouch, then the fork past the name claim), two
        # identical lines. Round four: the first cut of this test stopped at the claim and was green on stock; this one
        # grants the claim and drives the create through the fork, with the fork's own doors stubbed
        (km.jd.STATE / "comment-model").write_text(REMOVED + "\n")
        self.addCleanup(lambda: (km.jd.STATE / "comment-model").unlink(missing_ok=True))
        forks = []
        self.be.fork = lambda *a, **k: forks.append((a, k))
        self.be.connect = lambda sid: None
        with mock.patch.object(km.Sessions, "backend_for", lambda sid: self.be), \
                mock.patch.object(km, "_sdk_ready", lambda: True), \
                mock.patch.object(km, "_session_row", lambda sid, now: {"name": "web", "path": str(km.jd.STATE / "none.jsonl")}), \
                mock.patch.object(km, "_claim_session_name", lambda nm, kind, sid: None), \
                mock.patch.object(km, "_load_comments", lambda sid: {"threads": []}), \
                mock.patch.object(km, "_save_comments", lambda sid, data: None), \
                mock.patch.object(km, "_user_send", lambda be, sid, text: None), \
                mock.patch.object(km, "_release_name", lambda nm: None), \
                mock.patch.object(km, "_push_soon", lambda: None), \
                mock.patch.object(km, "_comment_launch_prefs", wraps=km._comment_launch_prefs) as prefs:
            err, tid = km._comment_create(SID, "", "a passage", "a comment", name="t1", model="")
        self.assertIsNone(err, "the create went through the fork")
        self.assertEqual(len(forks), 1)
        self.assertEqual(prefs.call_count, 1, "the launch prefs are resolved once (twice before the round-three fold)")
        self.assertEqual(self.err.getvalue().count("comment-model %r is not a model" % REMOVED), 1)

    def test_a_stored_comment_default_the_kernel_cannot_vouch_for_falls_to_the_parent(self):
        (km.jd.STATE / "comment-model").write_text(REMOVED + "\n")
        self.addCleanup(lambda: (km.jd.STATE / "comment-model").unlink(missing_ok=True))
        self.assertEqual(km._comment_launch_prefs("", "", "")[0], "", "inherit the parent, not the removed id")
        self.assertIn(REMOVED, self.err.getvalue())
        self.assertEqual((km.jd.STATE / "comment-model").read_text().strip(), REMOVED, "the store is left as it is")
        (km.jd.STATE / "comment-model").write_text("sonnet\n")
        self.assertEqual(km._comment_launch_prefs("", "", "")[0], "sonnet", "a vouched default is used")


class SeedInflight(_OnThenOff):
    def _seed(self, value):
        km._sdk_defaults_module().write_sdk_default(km.jd.STATE, model=value)

    def _read(self):
        return str(km._sdk_defaults_module().read_sdk_defaults(km.jd.STATE).get("model") or "")

    def test_a_seed_the_listing_may_still_vouch_is_held_while_the_fetch_is_in_flight(self):
        # the verify round's find: a create right after boot reset a valid remembered gateway model to default before
        # the gateway's listing had landed. The store is kept and the create door launches that row on the default.
        self._seed("gw-7-nova")
        with mock.patch.object(km, "_router_listing_inflight", lambda: True):
            self.assertEqual(km._reset_unvouched_seed(), "hold")
        self.assertEqual(self._read(), "gw-7-nova", "left as it is")
        self.assertIn("still being fetched", self.err.getvalue())
        with mock.patch.object(km, "_router_listing_inflight", lambda: False):
            self.assertIsNone(km._reset_unvouched_seed(), "reset (no verdict to hold) once no listing is pending")
        self.assertEqual(self._read(), "default")

    def test_a_seed_is_held_when_the_current_generations_listing_failed(self):
        # the second reviewer's note: a listing that failed at the current generation is not a removal (nothing retries it until the next
        # flip or restart): the store is kept, the line names the cause established, the row starts on the default
        self._seed("gw-7-nova")
        km._ROUTER_FETCH_FAILED_GEN[0] = km._ROUTER_GEN[0]
        self.assertEqual(km._reset_unvouched_seed(), "hold")
        self.assertEqual(self._read(), "gw-7-nova")
        self.assertIn("could not be fetched this generation", self.err.getvalue())
        self.assertNotIn("switch is off", self.err.getvalue(), "no untrue cause")
        km._ROUTER_FETCH_FAILED_GEN[0] = km._ROUTER_GEN[0] - 1    # an older generation's failure: a removal after all
        self.assertIsNone(km._reset_unvouched_seed())
        self.assertEqual(self._read(), "default")

    def test_the_reset_is_a_compare_and_swap_on_the_seed_it_judged(self):
        # review round three: a dormant pick landing between the read and the write was overwritten; the reset lands
        # only if the store still holds the value judged
        self._seed(REMOVED)
        real = km._vouched_model

        def vouch_then_race(value):
            ok = real(value)
            if value == REMOVED:
                km._sdk_defaults_module().write_sdk_default(km.jd.STATE, model="sonnet")   # the pick lands mid-check
            return ok
        with mock.patch.object(km, "_vouched_model", vouch_then_race):
            km._reset_unvouched_seed()
        self.assertEqual(self._read(), "sonnet", "the pick that landed since stands; the stale reset stood down")
        self.assertNotIn("reset to the account default", self.err.getvalue())

    def test_a_gpt_shaped_seed_is_reset_too(self):
        # the seed feeds SDK sessions: the Codex exception does not apply (a mutant that applied it passed the suite)
        self._seed("gpt-5-codex")
        km._reset_unvouched_seed()
        self.assertEqual(self._read(), "default")


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
        # the real spawn writes a registry row, a names row and a state file under this root: every path new since
        # setUp is removed again, so no live-looking row outlasts the test (review round three, 2026-09-22)
        self._before = {str(q) for q in km.jd.STATE.rglob("*")}
        self.addCleanup(self._remove_new_paths)

    def _remove_new_paths(self):
        import shutil
        new = sorted((q for q in km.jd.STATE.rglob("*") if str(q) not in self._before), key=lambda q: -len(str(q)))
        for q in new:
            try:
                q.unlink() if not q.is_dir() else shutil.rmtree(q, ignore_errors=True)
            except OSError:
                pass

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
        self.assertNotEqual(d.get("modelTok"), tok, "written through reset_sdk_default_model_if: a fresh token, never a raw file write")
        self.assertIn(REMOVED, self.err.getvalue(), "the reset is said, naming the id")

    def test_a_held_seed_launches_the_row_on_the_default_and_keeps_the_store(self):
        # the create door's half of the hold: the reg's copied model is cleared between the spawn and the connect
        sb.write_sdk_default(km.jd.STATE, model="gw-7-nova")
        with mock.patch.object(km, "_router_listing_inflight", lambda: True):
            sid, extra = km._create_sdk_session_inner("api", self.cwd)
        reg = sb.read_reg(km.jd.STATE, sid)
        self.assertFalse(reg.get("model"), "this row starts on the account default: %r" % reg.get("model"))
        self.assertEqual(sb.read_sdk_defaults(km.jd.STATE)["model"], "gw-7-nova", "the store is kept for the listing")

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
