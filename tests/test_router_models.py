#!/usr/bin/env python3
"""Extra models from your API gateway: an OPT-IN switch (2026-09-21). A loopback gateway set as Claude Code's
ANTHROPIC_BASE_URL forwards a first-party pick byte-exact and routes any other id it knows to that id's
provider, so a session can pick one of the gateway's families exactly as it picks a first-party one. Stock romp
offers the first-party families alone; the switch (per-install, default off) installs the families the operator
DECLARED (ROMP_ROUTER_MODELS in service.env) as top-level picker choices, add-only and exactly reversible.
Pinned here:

- the parser and its sdk_backend twin (the badge reads the same variable in-process); the picker label;
- apply/remove: add-only, after the first-party families, vouched and judge-allowed, no colour rank, never a
  catalog version, remove undoes exactly what apply added and nothing else;
- the switch: absent/garbled store reads off, gt-gated like its siblings (echo and stale stand down), the
  models frame on every applied flip (outside the catalog lock), the advisories are never gates;
- boot: installs only when the switch is on, never under ROMP_MODEL_CATALOG=off, the URL augment on a thread;
- the gateway probe reads Claude Code's settings through the credentials module under CLAUDE_CONFIG_DIR;
- the badge shows a declared id VERBATIM, and nothing keys on a vendor prefix.

Synthetic only; no network on any path exercised here (the fetch is stubbed), and every test that would read
the operator's settings points CLAUDE_CONFIG_DIR at a temp dir or stubs the probe.
"""
import ast
import inspect
import io
import json
import os
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
km = load_source("romp_kernel_router", os.path.join(BIN, "romp-kernel"))
sb = load_source("romp_sdk_backend_router", os.path.join(BIN, "romp_sdk_backend.py"))
km.jd.STATE.mkdir(parents=True, exist_ok=True)
(km.jd.STATE / "session-hosts").write_text("off")   # this root is outside conftest's belt (repo rule, 2026-09-11)

DECLARED = "gw-6-astra, gw-5.6-luna,gw-5.6-terra"
IDS = ["gw-6-astra", "gw-5.6-luna", "gw-5.6-terra"]


def _env(tc, key, value):
    prev = os.environ.get(key)
    if value is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = value
    tc.addCleanup(lambda: os.environ.__setitem__(key, prev) if prev is not None else os.environ.pop(key, None))


class _Catalog(unittest.TestCase):
    """The apply mutates the module's model globals in place; snapshot and restore around each test so an
    installed family never leaks into another test's view of the picker. The store, the env and the two
    outward seams (the gateway probe, the models frame) are reset too."""

    def setUp(self):
        self._choices = [dict(c) for c in km.MODEL_CHOICES]
        self._values = set(km._MODEL_VALUES)
        self._judge = set(km._JUDGE_MODEL_VALUES)
        self._rank = list(km._MODEL_RANK)
        self._installed = set(km._ROUTER_INSTALLED)
        self._note = km._router_status_note[0]
        for v in ("ROMP_ROUTER_MODELS", "ROMP_ROUTER_MODELS_URL", "ROMP_MODEL_CATALOG"):
            _env(self, v, None)
        self.store = km.jd.STATE / km.ROUTER_MODELS_FILE
        self.store.unlink(missing_ok=True)
        self.frames = []
        self._orig_changed = km._models_changed
        self._orig_gw = km._router_gateway_configured
        km._models_changed = lambda: self.frames.append(km._catalog_lock.locked())
        km._router_gateway_configured = lambda: (True, None)
        self.err = io.StringIO()
        self._p = mock.patch.object(km.sys, "stderr", self.err)
        self._p.start()

    def tearDown(self):
        self._p.stop()
        km._models_changed = self._orig_changed
        km._router_gateway_configured = self._orig_gw
        km.MODEL_CHOICES[:] = self._choices
        km._MODEL_VALUES.clear(); km._MODEL_VALUES.update(self._values)
        km._JUDGE_MODEL_VALUES.clear(); km._JUDGE_MODEL_VALUES.update(self._judge)
        km._MODEL_RANK[:] = self._rank
        km._ROUTER_INSTALLED.clear(); km._ROUTER_INSTALLED.update(self._installed)
        km._router_status_note[0] = self._note
        self.store.unlink(missing_ok=True)


class Parser(unittest.TestCase):
    def test_parse_keeps_order_strips_dedupes_and_drops_empties(self):
        self.assertEqual(km._parse_router_models(" b-1-x ,a-2-y,,b-1-x, ,"), ["b-1-x", "a-2-y"])
        self.assertEqual(km._parse_router_models(None), [])
        self.assertEqual(km._parse_router_models(""), [])

    def test_the_kernel_and_sdk_parsers_are_twins(self):
        # by behaviour over a table, and by the function body's AST (the docstring aside): the sdk module
        # may be absent from a kernel install, so neither imports the other's and they must not drift
        for raw in ("", None, "a", " a , b ,a", "x,,y", ",", "a-1-b, a-1-b"):
            self.assertEqual(km._parse_router_models(raw), sb._parse_router_models(raw), repr(raw))

        def body(fn):
            node = ast.parse(inspect.getsource(fn)).body[0]
            stmts = node.body[1:] if isinstance(node.body[0], ast.Expr) else node.body
            return [ast.dump(s) for s in stmts]
        self.assertEqual(body(km._parse_router_models), body(sb._parse_router_models))

    def test_the_declared_list_is_read_from_the_environment(self):
        _env(self, "ROMP_ROUTER_MODELS", DECLARED)
        self.assertEqual(km._router_declared_families(), IDS)
        self.assertEqual(sorted(sb._router_declared()), sorted(IDS))
        _env(self, "ROMP_ROUTER_MODELS", None)
        self.assertEqual(km._router_declared_families(), [])


class Label(unittest.TestCase):
    def test_vendor_version_codename_reads_as_a_label_and_other_shapes_show_verbatim(self):
        self.assertEqual(km._router_label("gw-6-astra"), "GW-6 Astra")
        self.assertEqual(km._router_label("gw-5.6-luna"), "GW-5.6 Luna")
        for odd in ("gw-6-astra-preview", "my-gateway-model", "claude-opus-4-8", "weird", ""):
            self.assertEqual(km._router_label(odd), odd, odd)


class ApplyRemove(_Catalog):
    def test_apply_adds_labeled_top_level_choices_after_the_first_party_families(self):
        added = km._apply_router_families(IDS[:2])
        self.assertEqual(added, IDS[:2])
        lbl = {c["value"]: c["label"] for c in km.MODEL_CHOICES}
        self.assertEqual(lbl.get("gw-6-astra"), "GW-6 Astra", "a top-level choice with its picker label")
        vals = [c["value"] for c in km.MODEL_CHOICES]
        self.assertLess(vals.index("fable"), vals.index("gw-6-astra"), "the first-party families keep the head")
        # a picked id is vouched (the WS setModel / '/model …' paths) and allowed for the judge
        self.assertTrue(km._vouched_model("gw-6-astra"))
        self.assertIn("gw-6-astra", km._MODEL_VALUES)
        self.assertIn("gw-6-astra", km._JUDGE_MODEL_VALUES)
        self.assertEqual(km._ROUTER_INSTALLED, set(IDS[:2]), "the undo set records exactly what was added")

    def test_add_only_idempotent_and_empties_never_join(self):
        km._apply_router_families(["gw-6-astra"])
        self.assertEqual(km._apply_router_families(["gw-6-astra", ""]), [], "a family already present is not re-added")
        self.assertEqual(sum(1 for c in km.MODEL_CHOICES if c["value"] == "gw-6-astra"), 1, "exactly one row")

    def test_no_colour_rank_and_never_a_catalog_version(self):
        before = dict(km._MODEL_RANK)
        km._apply_router_families(IDS)
        self.assertEqual(dict(km._MODEL_RANK), before, "a gateway row wears no capability tint; no rank moves")
        self.assertIsNone(km._catalog_family("gw-6-astra"))
        self.assertIsNone(km._MODEL_ID_RE.match("gw-6-astra"))

    def test_remove_undoes_exactly_what_apply_added_and_nothing_else(self):
        first_party = [dict(c) for c in km.MODEL_CHOICES]
        km._apply_router_families(IDS)
        self.assertEqual(km._remove_router_families(), sorted(IDS))
        self.assertEqual(km.MODEL_CHOICES, first_party, "the first-party rows are untouched")
        for g in IDS:
            self.assertNotIn(g, km._MODEL_VALUES)
            self.assertNotIn(g, km._JUDGE_MODEL_VALUES)
            self.assertFalse(km._vouched_model(g), "a later pick of a removed id is refused")
        self.assertEqual(km._ROUTER_INSTALLED, set())
        self.assertEqual(km._remove_router_families(), [], "nothing installed, nothing removed")

    def test_a_declared_id_that_is_already_first_party_is_neither_added_nor_removed(self):
        self.assertIn("opus", km._MODEL_VALUES)
        self.assertEqual(km._apply_router_families(["opus", "gw-6-astra"]), ["gw-6-astra"])
        self.assertEqual(km._remove_router_families(), ["gw-6-astra"])
        self.assertIn("opus", km._MODEL_VALUES, "a first-party value never leaves on the switch's account")


class Switch(_Catalog):
    def test_absent_or_garbled_store_reads_off_and_a_zero_stamp(self):
        self.assertFalse(km._router_models_on())
        self.assertEqual(km._router_models_gt(), 0)
        self.store.write_text("{not json")
        self.assertFalse(km._router_models_on())
        self.assertEqual(km._router_models_gt(), 0)
        self.store.write_text(json.dumps({"enabled": "yes", "gt": 5}))
        self.assertFalse(km._router_models_on(), "only a literal true switches it on")
        self.assertEqual(km._router_models_gt(), 5)

    def test_switching_on_installs_the_declared_families_stamps_the_store_and_sends_the_models_frame(self):
        _env(self, "ROMP_ROUTER_MODELS", DECLARED)
        stamp = km._set_router_models(True, gt=1700000000000)
        self.assertEqual(stamp, 1700000000000)
        self.assertEqual(json.loads(self.store.read_text()), {"enabled": True, "gt": 1700000000000})
        self.assertTrue(km._router_models_on())
        self.assertTrue(km._vouched_model("gw-5.6-terra"))
        self.assertEqual(self.frames, [False], "one models frame, sent OUTSIDE the catalog lock")
        # the setting tables the gear's gt clock and the pin rows read
        self.assertIn("router-models", km._GT_STORES)
        self.assertEqual(km._setting_stored_gt("router-models"), 1700000000000)
        self.assertIs(km._setting_kept_value("router-models"), True)
        self.assertIsNone(km._router_status_note[0], "declared families and a gateway: no advisory")

    def test_switching_off_removes_them_and_sends_the_models_frame(self):
        _env(self, "ROMP_ROUTER_MODELS", DECLARED)
        km._set_router_models(True, gt=1700000000000)
        self.frames.clear()
        self.assertEqual(km._set_router_models(False, gt=1700000000001), 1700000000001)
        self.assertFalse(km._router_models_on())
        self.assertFalse(km._vouched_model("gw-6-astra"))
        self.assertEqual(km._ROUTER_INSTALLED, set())
        self.assertEqual(self.frames, [False])
        self.assertIs(km._setting_kept_value("router-models"), False)

    def test_an_echo_and_a_stale_gesture_stand_down_without_a_frame(self):
        _env(self, "ROMP_ROUTER_MODELS", DECLARED)
        km._set_router_models(True, gt=1700000000000)
        self.frames.clear()
        self.assertIsNone(km._set_router_models(True, gt=1700000000000), "the same value at the same stamp is an echo")
        self.assertIsNone(km._set_router_models(False, gt=1600000000000), "an older stamp stands down")
        self.assertTrue(km._router_models_on(), "neither moved the switch")
        self.assertEqual(self.frames, [], "and neither sent a frame")

    def test_an_unstamped_gesture_takes_the_clock(self):
        before = int(time.time() * 1000)
        stamp = km._set_router_models(True)
        self.assertGreaterEqual(stamp, before)
        self.assertEqual(json.loads(self.store.read_text())["gt"], stamp)

    def test_on_with_nothing_declared_still_applies_and_says_so(self):
        stamp = km._set_router_models(True, gt=1700000000000)
        self.assertEqual(stamp, 1700000000000, "the switch is the operator's intent; an empty list is advice, not a refusal")
        self.assertEqual(km._ROUTER_INSTALLED, set())
        self.assertEqual(self.frames, [False], "the frame still goes: the gear's status line reads the payload")
        self.assertIn("ROMP_ROUTER_MODELS", km._router_status_note[0])
        self.assertIn("ROMP_ROUTER_MODELS", self.err.getvalue())

    def test_no_gateway_is_an_advisory_never_a_gate(self):
        _env(self, "ROMP_ROUTER_MODELS", DECLARED)
        km._router_gateway_configured = lambda: (False, None)
        km._set_router_models(True, gt=1700000000000)
        self.assertTrue(km._vouched_model("gw-6-astra"), "installed all the same")
        self.assertIn("gateway", km._router_status_note[0])
        st = km._router_status()
        self.assertEqual(set(st), {"enabled", "declared", "gateway", "error"})
        self.assertEqual((st["enabled"], st["declared"], st["gateway"]), (True, IDS, False))
        self.assertIn("gateway", st["error"])

    def test_off_names_the_live_sessions_still_running_a_removed_id(self):
        _env(self, "ROMP_ROUTER_MODELS", DECLARED)
        km._set_router_models(True, gt=1700000000000)
        with mock.patch.object(km, "_live_map", lambda: {"11111111-2222-4333-8444-555555555555": {"model": "gw-6-astra"},
                                                          "11111111-2222-4333-8444-666666666666": {"model": "opus"}}):
            km._set_router_models(False, gt=1700000000001)
        self.assertIn("1 live session", km._router_status_note[0])
        self.assertIn("1 live session", self.err.getvalue())

    def test_version_carries_the_switch_alone(self):
        _env(self, "ROMP_ROUTER_MODELS", DECLARED)
        km._set_router_models(True, gt=1700000000000)
        v = km._version_info()
        self.assertIs(v["routerModels"], True)
        self.assertNotIn("gw-6-astra", json.dumps(v), "the declared list rides the AUTHED /models section, never /version")


class Boot(_Catalog):
    def test_off_installs_nothing(self):
        _env(self, "ROMP_ROUTER_MODELS", DECLARED)
        self.assertEqual(km._router_models_boot(), [])
        self.assertFalse(km._vouched_model("gw-6-astra"))

    def test_on_installs_the_declared_families(self):
        _env(self, "ROMP_ROUTER_MODELS", DECLARED)
        self.store.write_text(json.dumps({"enabled": True, "gt": 1}))
        self.assertEqual(km._router_models_boot(), IDS)
        self.assertTrue(km._vouched_model("gw-6-astra"))

    def test_catalog_off_serves_the_shipped_list_alone(self):
        _env(self, "ROMP_ROUTER_MODELS", DECLARED)
        _env(self, "ROMP_MODEL_CATALOG", "off")
        self.store.write_text(json.dumps({"enabled": True, "gt": 1}))
        self.assertEqual(km._router_models_boot(), [])

    def test_a_listing_gateway_unions_its_models_in_on_a_thread(self):
        _env(self, "ROMP_ROUTER_MODELS", "gw-6-astra")
        _env(self, "ROMP_ROUTER_MODELS_URL", "http://127.0.0.1:1/v1/models")
        self.store.write_text(json.dumps({"enabled": True, "gt": 1}))
        with mock.patch.object(km, "_fetch_router_models", lambda url, timeout=4: ["gw-7-nova", "gw-6-astra"]):
            self.assertEqual(km._router_models_boot(), ["gw-6-astra"], "the declared list lands synchronously")
            deadline = time.time() + 5
            while "gw-7-nova" not in km._ROUTER_INSTALLED and time.time() < deadline:
                time.sleep(0.02)
        self.assertTrue(km._vouched_model("gw-7-nova"))
        self.assertEqual(self.frames, [False], "the augment sends its own frame, outside the lock")

    def test_a_failing_listing_is_loud_and_the_declared_list_still_serves(self):
        _env(self, "ROMP_ROUTER_MODELS", "gw-6-astra")
        _env(self, "ROMP_ROUTER_MODELS_URL", "http://127.0.0.1:1/v1/models")
        self.store.write_text(json.dumps({"enabled": True, "gt": 1}))

        def boom(url, timeout=4):
            raise OSError("connection refused")
        with mock.patch.object(km, "_fetch_router_models", boom):
            self.assertEqual(km._router_models_boot(), ["gw-6-astra"])
            deadline = time.time() + 5
            while "failed" not in self.err.getvalue() and time.time() < deadline:
                time.sleep(0.02)
        self.assertIn("connection refused", self.err.getvalue())
        self.assertTrue(km._vouched_model("gw-6-astra"))


class Fetch(unittest.TestCase):
    def test_the_listing_skips_first_party_ids_and_duplicates(self):
        payload = {"data": [{"id": "claude-opus-4-8"}, {"id": "gw-6-astra"}, {"id": "gw-6-astra"}, {"id": ""},
                            {"id": "claude-sonnet-4-5"}, {"id": "gw-5.6-luna"}, "junk"]}

        class R(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        import urllib.request
        with mock.patch.object(urllib.request, "urlopen", lambda req, timeout=4: R(json.dumps(payload).encode())):
            self.assertEqual(km._fetch_router_models("http://127.0.0.1:1/v1/models"), ["gw-6-astra", "gw-5.6-luna"])


class Gateway(unittest.TestCase):
    """The real probe, over a settings file under a temp CLAUDE_CONFIG_DIR (the credentials module's own
    resolution; the managed path is a system file this suite never has)."""

    def _settings(self, body):
        d = tempfile.mkdtemp()
        _env(self, "CLAUDE_CONFIG_DIR", d)
        if body is not None:
            with open(os.path.join(d, "settings.json"), "w") as f:
                f.write(body)
        return d

    def test_a_loopback_base_url_is_a_gateway(self):
        self._settings(json.dumps({"env": {"ANTHROPIC_BASE_URL": "http://127.0.0.1:8787/t/redacted"}}))
        self.assertEqual(km._router_gateway_configured(), (True, None))

    def test_anthropics_own_host_or_no_base_url_is_no_gateway(self):
        self._settings(json.dumps({"env": {"ANTHROPIC_BASE_URL": "https://api.anthropic.com"}}))
        self.assertEqual(km._router_gateway_configured(), (False, None))
        self._settings(json.dumps({"env": {}}))
        self.assertEqual(km._router_gateway_configured(), (False, None))
        self._settings(None)
        self.assertEqual(km._router_gateway_configured(), (False, None))

    def test_an_unparsable_settings_file_is_reported_not_swallowed(self):
        self._settings("{not json")
        ok, err = km._router_gateway_configured()
        self.assertFalse(ok)
        self.assertTrue(err, "the advisory carries the fault")


class SdkBadge(unittest.TestCase):
    def test_a_declared_id_shows_verbatim_on_the_badge(self):
        _env(self, "ROMP_ROUTER_MODELS", DECLARED)
        self.assertEqual(sb.pretty_model("gw-6-astra"), "gw-6-astra")
        self.assertEqual(sb.model_label("", "gw-6-astra"), "gw-6-astra")
        self.assertEqual(sb._alias_label("gw-5.6-terra"), "gw-5.6-terra")
        # and the first-party labels are unchanged
        self.assertEqual(sb.pretty_model("claude-opus-4-8"), "Opus 4.8")
        self.assertEqual(sb._alias_label("opus"), "Opus")

    def test_an_undeclared_id_takes_the_ordinary_path(self):
        _env(self, "ROMP_ROUTER_MODELS", None)
        self.assertEqual(sb.model_label("", "gw-6-astra"), "Gw-6-astra")

    def test_a_pick_of_a_declared_id_is_recognised_as_landed_by_both_matchers(self):
        _env(self, "ROMP_ROUTER_MODELS", DECLARED)
        for g in IDS:
            self.assertTrue(sb._model_reflects_alias(sb.pretty_model(g), g), g)
            self.assertTrue(km._alias_reflects(sb.pretty_model(g), g), g)
        self.assertFalse(sb._model_reflects_alias("gw-6-astra", "gw-5.6-luna"))
        self.assertFalse(km._alias_reflects("gw-6-astra", "gw-5.6-luna"))
        self.assertTrue(sb._model_reflects_alias("Opus 4.8", "opus"))
        self.assertTrue(sb._model_reflects_alias("Opus 4.8", "claude-opus-4-8"))
        self.assertFalse(sb._model_reflects_alias("Opus 4.8", "haiku"))

    def test_nothing_keys_on_a_vendor_prefix(self):
        # the CODE, docstrings aside (a docstring may name a vendor's id as its example shape)
        self.assertNotIn('startswith("gpt', inspect.getsource(sb))
        for fn in (km._parse_router_models, km._router_label, km._apply_router_families, km._remove_router_families,
                   km._router_apply_declared, km._set_router_models, km._router_models_boot, km._fetch_router_models,
                   sb.pretty_model, sb.model_label, sb._alias_label, sb._router_declared):
            node = ast.parse(inspect.getsource(fn)).body[0]
            code = "\n".join(ast.dump(s) for s in node.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)))
            self.assertNotIn("gpt", code.lower(), fn.__name__)


if __name__ == "__main__":
    unittest.main()
