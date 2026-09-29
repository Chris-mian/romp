#!/usr/bin/env python3
"""Extra models from your API gateway: the comment dialog's default model (review round, 2026-09-22).

The create dialog pre-reads the kernel's default-comment trio from the authed /models payload (`commentDefaults`)
and shows it, so an untouched dialog shows what the thread will launch on. The route served the RAW comment-model
store while _comment_launch_prefs had learned to fall to inheriting the parent when the stored default is a model
this kernel no longer offers (an extra gateway model whose switch is off): the dialog showed a removed id as the
default while the create launched on the parent's model. One helper, _comment_default_model_effective, is now the
read both surfaces make: the stored value when it is "session", "default" or vouched, else "session". Pinned here:

- the helper itself, the route's commentDefaults.model and _comment_launch_prefs's model arm, for a removed id
  (both read "inherit"; the launch prefs still say so on stderr), a vouched value (both read it) and the two
  sentinels;
- the typed /model road consults _pick_vouched with the typed id (a call-recording patch, so a commented-out call
  would fail this where a source grep would not) and refuses a removed id;
- the three texts that describe the missing colour rank and capacity-fallback reading are narrowed to an id
  carrying no first-party family word (the backend's _model_rank matches a family word by substring, so an id
  that carries one ranks as that family).

Synthetic only: placeholder UUIDs, invented gateway ids (gw-6-astra, gw-7-nova), a temp state root with session
hosts off, a stub backend that records what it was asked, no network (ROMP_MODEL_CATALOG=off).
"""
import http.client
import io
import json
import os
import re
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock

from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
# Hermetic state BEFORE the loads: they resolve their state root at import time, and only pytest runs conftest's
# floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
os.environ["ROMP_MANAGER_PORT"] = "1"             # a dead port, never an inherited live one
os.environ["ROMP_MODEL_CATALOG"] = "off"          # never the Models API from a test
for _v in ("ROMP_ROUTER_MODELS", "ROMP_ROUTER_MODELS_URL"):
    os.environ.pop(_v, None)
km = load_source("romp_kernel_router_comment_default", os.path.join(BIN, "romp-kernel"))
sb = load_source("romp_sdk_backend_router_comment_default", os.path.join(BIN, "romp_sdk_backend.py"))
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
    """A backend that records what it was asked and refuses nothing (the picks module's stub, kept minimal)."""

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


class _OnThenOff(unittest.TestCase):
    """The switch flipped on (the declared families installed) and then off (removed) before each test, with
    the model globals snapshotted and restored around it. The comment-model store is cleared before and after,
    and its mtime cache with it (jd._state_str caches by mtime; two writes inside one second would otherwise
    read the first)."""

    def setUp(self):
        self._choices = [dict(c) for c in km.MODEL_CHOICES]
        self._values = set(km._MODEL_VALUES)
        self._judge = set(km._JUDGE_MODEL_VALUES)
        self._rank = list(km._MODEL_RANK)
        self._installed = set(km._ROUTER_INSTALLED)
        self._by_set = {k: set(v) for k, v in km._ROUTER_INSTALLED_BY_SET.items()}
        self._ever = set(km._ROUTER_EVER)
        self._gen = km._ROUTER_GEN[0]
        self._note = km._router_status_note[0]
        self._sb_ids = sb._ROUTER_IDS
        self._modpatch = mock.patch.dict(sys.modules, {"romp_sdk_backend": sb})   # the kernel tells THIS copy
        self._modpatch.start(); self.addCleanup(self._modpatch.stop)
        for v in ("ROMP_ROUTER_MODELS", "ROMP_ROUTER_MODELS_URL", "ANTHROPIC_BASE_URL"):
            _env(self, v, None)
        self.store = km.jd.STATE / km.ROUTER_MODELS_FILE
        self.store.unlink(missing_ok=True)
        self._saved = (km._models_changed, km._router_gateway_configured, km._codex_backend)
        km._models_changed = lambda: None
        km._router_gateway_configured = lambda: (True, None)
        km._codex_backend = False            # never build the real Codex backend from the /models handler
        self._clear_comment_default()
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
        km._models_changed, km._router_gateway_configured, km._codex_backend = self._saved
        km.MODEL_CHOICES[:] = self._choices
        km._MODEL_VALUES.clear(); km._MODEL_VALUES.update(self._values)
        km._JUDGE_MODEL_VALUES.clear(); km._JUDGE_MODEL_VALUES.update(self._judge)
        km._MODEL_RANK[:] = self._rank
        km._ROUTER_INSTALLED.clear(); km._ROUTER_INSTALLED.update(self._installed)
        for k, v in self._by_set.items():
            km._ROUTER_INSTALLED_BY_SET[k].clear(); km._ROUTER_INSTALLED_BY_SET[k].update(v)
        km._ROUTER_EVER.clear(); km._ROUTER_EVER.update(self._ever)
        km._ROUTER_GEN[0] = self._gen
        km._router_status_note[0] = self._note
        sb._ROUTER_IDS = self._sb_ids
        self.store.unlink(missing_ok=True)
        self._clear_comment_default()

    def _clear_comment_default(self):
        (km.jd.STATE / "comment-model").unlink(missing_ok=True)
        km.jd._state_cache.pop("comment-model", None)

    def _put_comment_default(self, value):
        # written DIRECTLY (the setter would refuse a removed id; this is the store a dormant pick left behind)
        (km.jd.STATE / "comment-model").write_text(value)
        km.jd._state_cache.pop("comment-model", None)


class Helper(_OnThenOff):
    def test_a_removed_id_reads_as_inherit(self):
        self._put_comment_default(REMOVED)
        self.assertEqual(km._comment_default_model_effective(), "session")

    def test_a_vouched_value_and_the_sentinels_read_through(self):
        for v in ("haiku", "session", "default"):
            self._put_comment_default(v)
            self.assertEqual(km._comment_default_model_effective(), v, v)
        self._clear_comment_default()
        self.assertEqual(km._comment_default_model_effective(), "session", "no store: the shipped sentinel")

    def test_an_installed_id_reads_through_while_the_switch_is_on(self):
        km._set_router_models(True, gt=1700000000002)
        self._put_comment_default(REMOVED)
        self.assertEqual(km._comment_default_model_effective(), REMOVED)


class LaunchPrefs(_OnThenOff):
    def test_a_removed_default_falls_to_the_parent_loudly(self):
        self._put_comment_default(REMOVED)
        self.assertEqual(km._comment_launch_prefs()[0], "", "inherit the parent")
        self.assertIn(REMOVED, self.err.getvalue(), "and say so, naming the id")

    def test_the_arm_reads_the_shared_helper(self):
        # the two surfaces must not drift apart again: the launch prefs' model arm reads the helper the route reads
        self._put_comment_default("haiku")
        with mock.patch.object(km, "_comment_default_model_effective", autospec=True,
                               side_effect=km._comment_default_model_effective) as eff:
            self.assertEqual(km._comment_launch_prefs()[0], "haiku")
        eff.assert_called_once_with()
        self.assertEqual(self.err.getvalue(), "", "a vouched default: nothing to say")

    def test_the_dialogs_explicit_pick_still_wins(self):
        self._put_comment_default(REMOVED)
        self.assertEqual(km._comment_launch_prefs(model="sonnet")[0], "sonnet")


class ModelsRoute(_OnThenOff):
    """The handler runs in-process on a loopback ThreadingHTTPServer over km.Handler, authed with the lab kernel's
    own token (the pins module's pattern)."""

    def setUp(self):
        super().setUp()
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), km.Handler)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        super().tearDown()

    def _models(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request("GET", "/models", headers={"X-Romp-Token": km.TOKEN})
            r = conn.getresponse()
            self.assertEqual(r.status, 200)
            return json.loads(r.read())
        finally:
            conn.close()

    def test_a_removed_default_pre_reads_as_inherit_after_the_off_flip(self):
        self._put_comment_default(REMOVED)
        d = self._models()
        self.assertNotIn(REMOVED, [m["value"] for m in d["models"]], "the pick left the list")
        self.assertEqual(d["commentDefaults"]["model"], "session",
                         "the dialog shows what the create will do: inherit the parent")
        self.assertEqual(km._comment_launch_prefs()[0], "", "and the create agrees")

    def test_a_vouched_default_pre_reads_as_itself(self):
        self._put_comment_default("haiku")
        self.assertEqual(self._models()["commentDefaults"]["model"], "haiku")
        self.assertEqual(km._comment_launch_prefs()[0], "haiku")

    def test_the_other_two_defaults_still_ride_raw(self):
        (km.jd.STATE / "comment-effort").write_text("low")
        km.jd._state_cache.pop("comment-effort", None)
        self.addCleanup(lambda: ((km.jd.STATE / "comment-effort").unlink(missing_ok=True),
                                 km.jd._state_cache.pop("comment-effort", None)))
        d = self._models()["commentDefaults"]
        self.assertEqual((d["effort"], d["fast"]), ("low", "session"))


class TypedRoad(_OnThenOff):
    """The typed /model road consults _pick_vouched with the typed id: a call-recording patch, so a commented-out
    call fails this where a source grep for the call text stays green."""

    def setUp(self):
        super().setUp()
        self._road_saved = (km._compacting_now, km._limit_hold, km._working_now, km._push_soon, km._push_all,
                            km._note_unknown_model, km.Sessions.backend_for, km._kernel_knows)
        km._compacting_now = lambda sid: False
        km._limit_hold = lambda sid: None
        km._working_now = lambda sid: False
        km._push_soon = lambda: None
        km._push_all = lambda: None
        km._note_unknown_model = lambda mid: None
        km._kernel_knows = lambda sid: True
        self.be = _Recorder()
        km.Sessions.backend_for = staticmethod(lambda sid: self.be)
        km._model_switch_pending.pop(SID, None)
        km._pending_ops.pop(SID, None)

    def tearDown(self):
        (km._compacting_now, km._limit_hold, km._working_now, km._push_soon, km._push_all,
         km._note_unknown_model, km.Sessions.backend_for, km._kernel_knows) = self._road_saved
        km._model_switch_pending.pop(SID, None)
        km._pending_ops.pop(SID, None)
        super().tearDown()

    def test_the_road_asks_the_vouch_with_the_typed_id_and_refuses(self):
        with mock.patch.object(km, "_pick_vouched", autospec=True, side_effect=km._pick_vouched) as vouch:
            self.assertFalse(km._route_setter_command(self.be, SID, "/model " + REMOVED),
                             "no meta command: the CLI's own error, as before")
        vouch.assert_called_once_with(REMOVED, self.be)
        self.assertEqual(self.be.calls, [], "the backend was never asked")
        self.assertNotIn(SID, km._model_switch_pending, "no switching-dots stamp")

    def test_a_first_party_pick_still_fires_through_the_same_call(self):
        with mock.patch.object(km, "_pick_vouched", autospec=True, side_effect=km._pick_vouched) as vouch:
            self.assertTrue(km._route_setter_command(self.be, SID, "/model sonnet"))
        # the road asks first; the setter it hands the pick to (_set_model_or_park) is the rule's own reader too
        self.assertEqual(vouch.call_args_list[0], mock.call("sonnet", self.be))
        self.assertEqual(self.be.calls, [(SID, "sonnet")])


class Texts(unittest.TestCase):
    """The three texts that say a gateway id has no colour rank and a swap to one is never a capacity fallback
    are narrowed to an id carrying no first-party family word: sdk_backend._model_rank walks _MODEL_TIERS by
    substring with no router gate, so an id that carries a family word ranks as that family (pinned first)."""

    def test_the_rank_helper_matches_a_family_word_inside_a_gateway_id(self):
        self.assertEqual(sb._model_rank("gw-opus-mini"), sb._model_rank("opus"))
        self.assertIsNone(sb._model_rank(REMOVED), "an id carrying no family word has no rank")

    def _narrowed(self, text, label):
        # the qualifier stands in the same sentence as the fallback clause and AHEAD of it: the clause holds for
        # that id, not for every gateway id (a qualifier on the tint half alone leaves the fallback half unqualified)
        hits = [m for m in re.finditer(r"[^.\n]*(?:\n[^.\n]*)*?capacity\s+fallback[^.]*\.", text)]
        self.assertTrue(hits, "%s: the fallback clause is there" % label)
        for m in hits:
            self.assertRegex(m.group(0).replace("\n", " "),
                             r"carr(?:ies|ying) no (?:first-party|Claude) family word.*capacity\s+fallback",
                             "%s: the fallback clause names the id it holds for" % label)

    def test_the_reference_page(self):
        text = open(os.path.join(ROOT, "docs", "reference.md")).read()
        start = text.index("Extra models")
        self._narrowed(text[start:start + 6000], "docs/reference.md")

    def test_the_router_block_comment(self):
        text = open(os.path.join(BIN, "romp-kernel")).read()
        i = text.index("ROUTER_MODELS_FILE = ")
        head = text[text.rfind("\n\n", 0, i):i]          # the block comment directly above the store's name
        self.assertIn("capacity", head)
        self._narrowed(head.replace("\n# ", " "), "the router block comment")


if __name__ == "__main__":
    unittest.main()
