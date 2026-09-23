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
- the gateway probe reads the environment first, then Claude Code's settings through the credentials module under
  CLAUDE_CONFIG_DIR, and reports a read fault as a static phrase (never the file's path), only while the switch is on;
- the switch generation: a listing that lands after an off flip, or an apply delayed past a concurrent flip, installs
  nothing; a first-party id on either road is skipped; removal strips from each set only what the apply added to it;
- the backend is told every installed id, a listing's included, so the badge shows any of them VERBATIM; the live count
  reads the raw id and says when it cannot count; nothing keys on a vendor prefix.

Synthetic only; no network on any path exercised here (the fetch is stubbed), and every test that would read the
operator's settings points CLAUDE_CONFIG_DIR and the managed path at a temp dir (hermetic under a bare run too) or stubs
the probe.
"""
import ast
import inspect
import io
import json
import os
import sys
import tempfile
import threading
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

FIRST_PARTY_AT_IMPORT = set(km._MODEL_VALUES)   # the shipped families, before any test's apply
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
        self._by_set = {k: set(v) for k, v in km._ROUTER_INSTALLED_BY_SET.items()}
        self._ever = set(km._ROUTER_EVER)
        self._gen = km._ROUTER_GEN[0]
        km._ROUTER_FETCH_GEN[0] = None; km._ROUTER_FETCH_FAILED_GEN[0] = None   # a previous test's generation numbers recur here
        self._note = km._router_status_note[0]
        self._said = km._router_probe_said[0]
        self._sb_ids = sb._ROUTER_IDS
        for v in ("ROMP_ROUTER_MODELS", "ROMP_ROUTER_MODELS_URL", "ROMP_MODEL_CATALOG", "ANTHROPIC_BASE_URL"):
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
        # the kernel tells the module registered as romp_sdk_backend; this harness loads its private copy under another
        # name, so register that copy for the test (the review's find: an earlier module's shared copy took the ids)
        self._m = mock.patch.dict(sys.modules, {"romp_sdk_backend": sb})
        self._m.start()

    def tearDown(self):
        self._m.stop()
        self._p.stop()
        km._models_changed = self._orig_changed
        km._router_gateway_configured = self._orig_gw
        km.MODEL_CHOICES[:] = self._choices
        km._MODEL_VALUES.clear(); km._MODEL_VALUES.update(self._values)
        km._JUDGE_MODEL_VALUES.clear(); km._JUDGE_MODEL_VALUES.update(self._judge)
        km._MODEL_RANK[:] = self._rank
        km._ROUTER_INSTALLED.clear(); km._ROUTER_INSTALLED.update(self._installed)
        for k, v in self._by_set.items():
            km._ROUTER_INSTALLED_BY_SET[k].clear(); km._ROUTER_INSTALLED_BY_SET[k].update(v)
        km._ROUTER_EVER.clear(); km._ROUTER_EVER.update(self._ever)
        km._ROUTER_GEN[0] = self._gen
        km._ROUTER_FETCH_GEN[0] = None; km._ROUTER_FETCH_FAILED_GEN[0] = None
        km._router_status_note[0] = self._note
        km._router_probe_said[0] = self._said
        sb._ROUTER_IDS = self._sb_ids
        self.store.unlink(missing_ok=True)

    def _wait(self, pred, what, timeout=5.0):
        deadline = time.time() + timeout
        while not pred() and time.time() < deadline:
            time.sleep(0.02)
        self.assertTrue(pred(), "timed out waiting for " + what)


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
    def test_the_picker_label_is_the_id_itself(self):
        # one name per model: the badge shows the raw id and the pickers' tick compares the two (review find)
        for mid in ("gw-6-astra", "gw-5.6-luna", "Qwen/Qwen3-235B", "gw-6-astra-preview", "weird", ""):
            self.assertEqual(km._router_label(mid), mid, mid)


class ApplyRemove(_Catalog):
    def test_apply_adds_labeled_top_level_choices_after_the_first_party_families(self):
        added = km._apply_router_families(IDS[:2])
        self.assertEqual(added, IDS[:2])
        lbl = {c["value"]: c["label"] for c in km.MODEL_CHOICES}
        self.assertEqual(lbl.get("gw-6-astra"), "gw-6-astra", "a top-level choice labelled with its id")
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


class PerSetRecords(_Catalog):
    def test_remove_strips_from_each_set_only_what_the_apply_added_to_it(self):
        # an id a set already held (here the judge tiers' allowed set, which may hold a learned id) is not the switch's
        # to remove: only the ids the apply ADDED to that set leave it
        km._JUDGE_MODEL_VALUES.add("gw-x-9-held")
        self.assertEqual(km._apply_router_families(["gw-x-9-held"]), ["gw-x-9-held"])
        self.assertIn("gw-x-9-held", km._MODEL_VALUES)
        self.assertEqual(km._remove_router_families(), ["gw-x-9-held"])
        self.assertNotIn("gw-x-9-held", km._MODEL_VALUES, "added by the apply, removed by the remove")
        self.assertIn("gw-x-9-held", km._JUDGE_MODEL_VALUES, "held before the apply, kept after the remove")
        self.assertFalse(any(c["value"] == "gw-x-9-held" for c in km.MODEL_CHOICES))

    def test_a_first_party_id_leaked_by_a_listing_is_skipped_on_that_road(self):
        # the road itself: a gateway whose listing carries a Claude version id (the fetch filters the grammar, but the
        # apply is the last word on both roads)
        vid = next(iter(km._VERSION_FAMILY))
        _env(self, "ROMP_ROUTER_MODELS_URL", "http://127.0.0.1:1/v1/models")
        self.store.write_text(json.dumps({"enabled": True, "gt": 1}))
        with mock.patch.object(km, "_fetch_router_models", lambda url, timeout=4: [vid, "gw-6-astra"]):
            km._router_models_boot()
            self._wait(lambda: len(self.frames) >= 1, "the listing's frame")
        self.assertTrue(km._vouched_model("gw-6-astra"))
        self.assertEqual(sum(1 for c in km.MODEL_CHOICES if c["value"] == vid), 0)
        self.assertIn("skipped", self.err.getvalue())
        self.assertIn(vid, self.err.getvalue())


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
        self.assertIn("ROMP_ROUTER_MODELS", km._router_status()["error"], "derived live from the declaration")
        self.assertIsNone(km._router_status_note[0], "not a frozen note")
        self.assertIn("ROMP_ROUTER_MODELS", self.err.getvalue())

    def test_no_gateway_is_an_advisory_never_a_gate(self):
        _env(self, "ROMP_ROUTER_MODELS", DECLARED)
        km._router_gateway_configured = lambda: (False, None)
        km._set_router_models(True, gt=1700000000000)
        self.assertTrue(km._vouched_model("gw-6-astra"), "installed all the same")
        self.assertIsNone(km._router_status_note[0], "the probe-shaped advisory is never frozen into the note")
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

    def test_a_listing_that_lands_after_an_off_flip_installs_nothing(self):
        # the review's find (2026-09-21): the fetch thread applied on return without asking whether the store was still
        # on, so an off flip during the fetch left the listing's families installed under an off store until another
        # on-then-off cycle. The generation the on flip captured is stale once the off flip bumped it: discarded.
        _env(self, "ROMP_ROUTER_MODELS", "gw-6-astra")
        _env(self, "ROMP_ROUTER_MODELS_URL", "http://127.0.0.1:1/v1/models")
        gate = threading.Event()

        def fetch(url, timeout=4):
            gate.wait(5)
            return ["gw-7-nova"]
        with mock.patch.object(km, "_fetch_router_models", fetch):
            km._set_router_models(True, gt=10)
            self.assertTrue(km._vouched_model("gw-6-astra"))
            km._set_router_models(False, gt=11)
            self.assertFalse(km._vouched_model("gw-6-astra"))
            gate.set()
            self._wait(lambda: "stale apply" in self.err.getvalue(), "the stale-apply line")
        self.assertFalse(km._vouched_model("gw-7-nova"), "nothing installs under an off store")
        self.assertEqual(km._ROUTER_INSTALLED, set())
        self.assertEqual(self.frames, [False, False], "the on and the off frames; the stale apply sends none")
        self.assertIs(km._router_status()["enabled"], False)

    def test_an_apply_or_remove_carrying_an_older_generation_is_discarded(self):
        # the same guard on the synchronous road: a declared apply delayed past a concurrent flip, a remove delayed
        # past a later on
        stale = km._ROUTER_GEN[0] - 1
        self.assertIsNone(km._apply_router_families(["gw-6-astra"], gen=stale), "stale is its own verdict, not nothing-to-do")
        self.assertFalse(km._vouched_model("gw-6-astra"))
        self.assertEqual(km._apply_router_families([], gen=km._ROUTER_GEN[0]), [], "nothing to do is a list")
        km._apply_router_families(["gw-6-astra"], gen=km._ROUTER_GEN[0])
        self.assertIsNone(km._remove_router_families(gen=stale), "a stale remove leaves a later install alone")
        self.assertTrue(km._vouched_model("gw-6-astra"))
        self.assertIn("stale", self.err.getvalue())

    def test_a_first_party_version_id_declared_is_skipped_and_the_judge_set_keeps_it(self):
        # the review's find: a declared version id installed a duplicate tinted row and, on off, left the judge tiers'
        # allowed set (which already held it), so the judge setters refused it until a catalog rebuild
        vid = next(iter(km._VERSION_FAMILY))
        self.assertIn(vid, km._JUDGE_MODEL_VALUES)
        _env(self, "ROMP_ROUTER_MODELS", "%s, gw-6-astra" % vid)
        km._set_router_models(True, gt=10)
        self.assertEqual(sum(1 for c in km.MODEL_CHOICES if c["value"] == vid), 0, "never a gateway row")
        self.assertIn(vid, self.err.getvalue(), "the skip is said")
        self.assertTrue(km._vouched_model("gw-6-astra"))
        km._set_router_models(False, gt=11)
        self.assertIn(vid, km._JUDGE_MODEL_VALUES, "the judge tiers keep their version id")

    def test_the_backend_is_told_every_installed_id_including_a_listings(self):
        # the review's find: sdk_backend read the variable alone, so a listing's id was unknown to the badge, the
        # served-model learn and the live count. The kernel tells the loaded backend module at every apply and remove.
        _env(self, "ROMP_ROUTER_MODELS", "gw-6-astra")
        _env(self, "ROMP_ROUTER_MODELS_URL", "http://127.0.0.1:1/v1/models")
        with mock.patch.dict(sys.modules, {"romp_sdk_backend": sb}), \
                mock.patch.object(km, "_fetch_router_models", lambda url, timeout=4: ["gw-7-nova"]):
            km._set_router_models(True, gt=10)
            self._wait(lambda: len(self.frames) >= 2, "the listing's frame")
            self.assertTrue({"gw-6-astra", "gw-7-nova"} <= sb._router_declared())
            self.assertEqual(sb.pretty_model("gw-7-nova"), "gw-7-nova", "a listing's id shows verbatim too")
            self.assertEqual(sb.model_label("", "gw-7-nova"), "gw-7-nova")
            km._set_router_models(False, gt=11)
            self.assertIn("gw-7-nova", sb._router_declared(), "a session still running it keeps its badge: the told set is monotonic")

    def test_the_live_count_matches_the_raw_id_and_says_when_it_cannot_count(self):
        _env(self, "ROMP_ROUTER_MODELS", DECLARED)
        km._set_router_models(True, gt=10)
        with mock.patch.object(km, "_live_map", lambda: {"11111111-2222-4333-8444-555555555555": {"model": "gw-6-astra"}}):
            self.assertEqual(km._router_live_on({"gw-6-astra"}), 1)

        def boom():
            raise RuntimeError("snapshot unavailable")
        with mock.patch.object(km, "_live_map", boom):
            self.assertIsNone(km._router_live_on({"gw-6-astra"}))
            km._set_router_models(False, gt=11)
        self.assertIn("could not be counted", km._router_status_note[0])
        self.assertIn("snapshot unavailable", self.err.getvalue())
        self.assertIn("? live session(s) keep running one", self.err.getvalue(), "the off line says the count is unknown")

    def test_the_advisory_is_a_static_phrase_and_only_while_the_switch_is_on(self):
        # the review's find: a settings-read fault put the file's absolute path into the authed /models section, with
        # the switch off. The probe's fault is a static phrase, and an advisory is about a switch that is on.
        km._router_gateway_configured = lambda: (False, km.ROUTER_SETTINGS_FAULT)
        self.assertIsNone(km._router_status()["error"], "off: no advisory")
        _env(self, "ROMP_ROUTER_MODELS", DECLARED)
        km._set_router_models(True, gt=10)
        err = km._router_status()["error"]
        self.assertEqual(err, km.ROUTER_SETTINGS_FAULT)
        self.assertNotIn("/", err, "never a path")

    def test_the_off_flip_advisory_reaches_the_payload(self):
        # the review's find: the live-sessions note is written on the off flip and was masked while off, so it could
        # never reach the gear. Only the probe's fault is gated on the switch; gateway is null while off (not probed)
        _env(self, "ROMP_ROUTER_MODELS", DECLARED)
        km._set_router_models(True, gt=10)
        with mock.patch.object(km, "_live_map", lambda: {"11111111-2222-4333-8444-555555555555": {"model": "gw-6-astra"}}):
            km._set_router_models(False, gt=11)
        st = km._router_status()
        self.assertIs(st["enabled"], False)
        self.assertIn("1 live session", st["error"])
        self.assertIsNone(st["gateway"], "not probed while off")

    def test_a_stale_remove_or_apply_does_no_bookkeeping(self):
        # the review's find: the guard stopped the install, but the caller still nulled the standing advisory, sent a
        # frame, and started the listing fetch. A concurrent flip is simulated by bumping the generation between the
        # store write and the catalog step.
        _env(self, "ROMP_ROUTER_MODELS", DECLARED)
        _env(self, "ROMP_ROUTER_MODELS_URL", "http://127.0.0.1:1/v1/models")
        km._router_gateway_configured = lambda: (False, None)
        calls = []
        real_remove, real_apply = km._remove_router_families, km._apply_router_families
        with mock.patch.object(km, "_fetch_router_models", lambda url, timeout=4: calls.append(url) or []):
            km._set_router_models(True, gt=10)
            self._wait(lambda: calls, "the on flip's listing fetch")      # the event, not a sleep (review round three)
            self._wait(lambda: not km._router_listing_inflight(), "the fetch thread to end")
            note_on, n_on, n_calls = km._router_status_note[0], len(self.frames), len(calls)
            self.assertIsNone(note_on, "the on flip's note is clear (the no-gateway advisory is derived live)")
            self.assertEqual(km._router_status()["error"], km.ROUTER_NOTE_NO_GATEWAY)

            def late_remove(gen=None):
                km._ROUTER_GEN[0] += 1        # a later on flip lands first
                return real_remove(gen=gen)
            with mock.patch.object(km, "_remove_router_families", late_remove):
                self.assertEqual(km._set_router_models(False, gt=11), 11, "the store took the gesture")
            self.assertEqual(km._router_status_note[0], note_on, "the standing advisory is not nulled")
            self.assertEqual(len(self.frames), n_on + 1, "a frame on every applied flip, the stale remove included")
            self.assertTrue(km._vouched_model("gw-6-astra"), "the later on's rows stand")

            def late_apply(ids, gen=None, reason=""):
                km._ROUTER_GEN[0] += 1        # a later off flip lands first
                return real_apply(ids, gen=gen, reason=reason)
            with mock.patch.object(km, "_apply_router_families", late_apply):
                self.assertEqual(km._set_router_models(True, gt=12), 12)
            # a stale _router_apply_declared returns before any fetch generation is set or a thread starts: the state
            # is the evidence, not a sleep (review round four)
            self.assertIsNone(km._ROUTER_FETCH_GEN[0], "a stale apply arms no listing fetch")
            self.assertEqual(len(calls), n_calls, "and none ran")
            self.assertEqual(len(self.frames), n_on + 2, "but the flip frames, as every applied flip does")

    def test_a_slower_earlier_flip_cannot_overwrite_a_later_flips_advisory(self):
        # the verify round's find: the note was written after the apply or remove with no generation check, so an on
        # flip parked in its probe finished after an off flip and erased the off flip's live-sessions advisory (and the
        # mirror left a removed-model advisory standing under an on switch). Every note write goes through
        # _router_set_note at its own generation; a stale writer says and sends nothing.
        _env(self, "ROMP_ROUTER_MODELS", DECLARED)
        gate = threading.Event()
        probe_calls = []

        def slow_probe():
            probe_calls.append(1)
            if len(probe_calls) == 1:
                gate.wait(5)          # the on flip parks here, after its apply
            return (True, None)
        km._router_gateway_configured = slow_probe
        t = threading.Thread(target=lambda: km._set_router_models(True, gt=10))
        t.start()
        self._wait(lambda: probe_calls, "the on flip to reach its probe")
        with mock.patch.object(km, "_live_map", lambda: {"11111111-2222-4333-8444-555555555555": {"model": "gw-6-astra"}}):
            km._set_router_models(False, gt=11)
        off_note = km._router_status_note[0]
        self.assertIn("1 live session", off_note)
        n = len(self.frames)
        gate.set(); t.join(5)
        self.assertEqual(km._router_status_note[0], off_note, "the later off flip's advisory stands")
        self.assertEqual(len(self.frames), n + 1, "the stale on flip still frames (every applied flip does); it wrote nothing")
        self.assertFalse(km._vouched_model("gw-6-astra"))
        st = km._router_status()
        self.assertIs(st["enabled"], False)
        self.assertIn("1 live session", st["error"])

    def test_the_probe_shaped_advisory_clears_when_the_operator_fixes_the_gateway(self):
        _env(self, "ROMP_ROUTER_MODELS", DECLARED)
        km._router_gateway_configured = lambda: (False, None)
        km._set_router_models(True, gt=10)
        self.assertEqual(km._router_status()["error"], km.ROUTER_NOTE_NO_GATEWAY)
        km._router_gateway_configured = lambda: (True, None)     # the operator sets ANTHROPIC_BASE_URL; no flip
        st = km._router_status()
        self.assertIsNone(st["error"], "derived live: the line clears on the next read")
        self.assertIs(st["gateway"], True)
        km._router_gateway_configured = lambda: (False, km.ROUTER_SETTINGS_FAULT)
        self.assertEqual(km._router_status()["error"], km.ROUTER_SETTINGS_FAULT)
        km._router_gateway_configured = lambda: (True, None)
        self.assertIsNone(km._router_status()["error"])

    def test_a_listing_that_fails_after_an_off_flip_leaves_no_advisory(self):
        _env(self, "ROMP_ROUTER_MODELS", "gw-6-astra")
        _env(self, "ROMP_ROUTER_MODELS_URL", "http://127.0.0.1:1/v1/models")
        gate = threading.Event()

        def fetch(url, timeout=4):
            gate.wait(5)
            raise OSError("connection refused")
        with mock.patch.object(km, "_fetch_router_models", fetch):
            km._set_router_models(True, gt=10)
            self.assertTrue(km._router_listing_inflight())
            km._set_router_models(False, gt=11)
            gate.set()
            self._wait(lambda: "failed" in self.err.getvalue(), "the failure line")
            self._wait(lambda: not km._router_listing_inflight(), "the fetch to end")
        self.assertIsNone(km._router_status_note[0], "a failure at an old generation files nothing")
        self.assertIsNone(km._router_status()["error"])
        self.assertEqual(self.frames, [False, False], "the on and the off frames alone")

    def test_a_failed_listing_does_not_hide_the_live_advisories(self):
        # review round three: the failed-listing note stood as an event note and the no-gateway advisory, derived only
        # when no note stood, vanished behind it. The live advisories are composed ahead of the event note.
        _env(self, "ROMP_ROUTER_MODELS", "gw-6-astra")
        _env(self, "ROMP_ROUTER_MODELS_URL", "http://127.0.0.1:1/v1/models")
        km._router_gateway_configured = lambda: (False, None)

        def boom(url, timeout=4):
            raise OSError("connection refused")
        with mock.patch.object(km, "_fetch_router_models", boom):
            km._set_router_models(True, gt=10)
            self._wait(lambda: km._router_status_note[0] == km.ROUTER_NOTE_LISTING_FAILED, "the failed-listing note")
        self.assertEqual(km._router_status()["error"], km.ROUTER_NOTE_NO_GATEWAY, "the gateway advisory comes first")
        km._router_gateway_configured = lambda: (True, None)
        self.assertEqual(km._router_status()["error"], km.ROUTER_NOTE_LISTING_FAILED, "then the event note, with declared models offered")

    def test_a_failed_listing_under_a_url_only_configuration_says_nothing_is_offered(self):
        _env(self, "ROMP_ROUTER_MODELS_URL", "http://127.0.0.1:1/v1/models")

        def boom(url, timeout=4):
            raise OSError("connection refused")
        with mock.patch.object(km, "_fetch_router_models", boom):
            km._set_router_models(True, gt=10)
            self._wait(lambda: km._router_status_note[0] == km.ROUTER_NOTE_LISTING_FAILED, "the failed-listing note")
        self.assertEqual(km._router_status()["error"], km.ROUTER_NOTE_LISTING_FAILED_NONE, "worded by the declared count")

    def test_a_repeated_off_gesture_keeps_the_standing_advisory(self):
        # review round three: a same-value off at a newer stamp passed the echo check, removed nothing, and cleared the
        # advisory over live sessions still on the removed model
        _env(self, "ROMP_ROUTER_MODELS", DECLARED)
        km._set_router_models(True, gt=10)
        with mock.patch.object(km, "_live_map", lambda: {"11111111-2222-4333-8444-555555555555": {"model": "gw-6-astra"}}):
            km._set_router_models(False, gt=11)
            note = km._router_status_note[0]
            self.assertIn("1 live session", note)
            n = len(self.frames)
            # every applied off RECOUNTS against every id ever installed (the second reviewer's note): the session is still there, so the
            # advisory stands by recount, not by being skipped
            self.assertEqual(km._set_router_models(False, gt=12), 12, "the store takes the newer stamp")
        self.assertEqual(km._router_status_note[0], note, "nothing removed, the session still counted: the advisory stands")
        self.assertEqual(len(self.frames), n + 1, "and the frame goes out as on every applied flip (the gear reads it alone)")
        self.assertIs(self.frames[-1], False, "sent outside the catalog lock")

    def test_two_interleaved_offs_keep_the_advisory_and_the_removal_line(self):
        # the second reviewer's note: a second off landing during the first's live-session count found nothing installed and returned
        # unrecounted, while the first's note write was refused as stale: the sessions on the removed rows were named
        # nowhere and the log carried no removal. Every applied off recounts against the ever-installed set, and the
        # stderr summary is written before the note write a later flip may refuse.
        _env(self, "ROMP_ROUTER_MODELS", DECLARED)
        km._set_router_models(True, gt=10)
        fired = []

        def live_map():
            if not fired:
                fired.append(1)
                km._set_router_models(False, gt=12)      # the second off lands during the first's count
            return {"11111111-2222-4333-8444-555555555555": {"model": "gw-6-astra"}}
        (km.jd.STATE / "judge-model").write_text("gw-6-astra\n")
        (km.jd.STATE / "comment-model").write_text("gw-6-astra\n")
        self.addCleanup(lambda: [(km.jd.STATE / f).unlink(missing_ok=True) for f in ("judge-model", "comment-model")])
        with mock.patch.object(km, "_live_map", live_map):
            self.assertEqual(km._set_router_models(False, gt=11), 11)
        note = km._router_status_note[0]
        self.assertIn("1 live session", note, "the advisory stands, by the second off's recount")
        self.assertIn("triage, distill judge tier", note, "the tiers are recounted against the ever-installed set too")
        self.assertIn("new comment threads", note)
        self.assertIn("left the pickers", self.err.getvalue(), "the removal is on the log")
        self.assertEqual(self.frames, [False, False, False], "the on and both offs: a frame each, outside the lock")
        self.assertIs(km._router_status()["enabled"], False)

    def test_an_off_after_an_empty_on_clears_the_listing_note_and_sends_the_frame(self):
        # review round four: the no-op off skipped the note clear and the frame, so a URL-only configuration whose
        # listing failed kept the failed-listing advisory under the off switch, and nothing repainted
        _env(self, "ROMP_ROUTER_MODELS_URL", "http://127.0.0.1:1/v1/models")
        gate = threading.Event()

        def boom(url, timeout=4):
            gate.wait(5)              # gated: the on flip's frame is recorded before the thread can hold the lock
            raise OSError("connection refused")
        with mock.patch.object(km, "_fetch_router_models", boom):
            km._set_router_models(True, gt=10)
            self.assertEqual(self.frames, [False], "the on flip's frame, outside the lock")
            gate.set()
            self._wait(lambda: km._router_status_note[0] == km.ROUTER_NOTE_LISTING_FAILED, "the failed-listing note")
            self._wait(lambda: len(self.frames) >= 2, "its frame")
            self._wait(lambda: not km._router_listing_inflight(), "the fetch thread to end")   # before the off, so the
            #                                                                                   recorder sees no other holder
        km._set_router_models(False, gt=11)
        self.assertIsNone(km._router_status()["error"], "the on generation's note is cleared by the off")
        self.assertEqual(self.frames, [False, False, False], "on, the listing's failure, off: a frame each, outside the lock")

    def test_an_off_with_nothing_declared_still_sends_the_frame(self):
        km._set_router_models(True, gt=10)
        n = len(self.frames)
        km._set_router_models(False, gt=11)
        self.assertEqual(len(self.frames), n + 1)
        self.assertIs(self.frames[-1], False, "sent outside the catalog lock")
        self.assertIsNone(km._router_status()["error"])

    def test_a_gateway_id_that_cleans_to_a_first_party_alias_is_first_party(self):
        for mid in ("Opus", "OPUS", "claude-opus-4-8[1m]", "Claude-Fable-5-1"):
            self.assertTrue(km._router_first_party(mid), mid)
            self.assertTrue(sb._router_first_party(mid), mid)
        self.assertEqual(km._apply_router_families(["Opus", "gw-6-astra"]), ["gw-6-astra"])

    def test_the_off_flip_names_the_judge_tiers_still_on_a_removed_model(self):
        _env(self, "ROMP_ROUTER_MODELS", DECLARED)
        (km.jd.STATE / "judge-model").write_text("gw-6-astra\n")
        self.addCleanup(lambda: (km.jd.STATE / "judge-model").unlink(missing_ok=True))
        km._set_router_models(True, gt=10)
        km._set_router_models(False, gt=11)
        self.assertIn("triage, distill judge tier", km._router_status_note[0], "the distill tier follows the triage pick")
        self.assertIn("triage, distill judge tier", self.err.getvalue())
        self.assertEqual((km.jd.STATE / "judge-model").read_text().strip(), "gw-6-astra", "the store is left as it is")

    def test_the_off_flip_words_the_comment_default_as_what_it_is(self):
        # the verify round's find: the default for new comment threads was filed as a judge tier
        _env(self, "ROMP_ROUTER_MODELS", DECLARED)
        (km.jd.STATE / "comment-model").write_text("gw-6-astra\n")
        self.addCleanup(lambda: (km.jd.STATE / "comment-model").unlink(missing_ok=True))
        km._set_router_models(True, gt=10)
        km._set_router_models(False, gt=11)
        self.assertIn("new comment threads", km._router_status_note[0])
        self.assertNotIn("judge tier", km._router_status_note[0])

    def test_a_url_only_configuration_declares_nothing_but_says_nothing_wrong(self):
        _env(self, "ROMP_ROUTER_MODELS_URL", "http://127.0.0.1:1/v1/models")
        with mock.patch.object(km, "_fetch_router_models", lambda url, timeout=4: ["gw-7-nova"]):
            km._set_router_models(True, gt=10)
            self._wait(lambda: len(self.frames) >= 2, "the listing's frame")
        self.assertTrue(km._vouched_model("gw-7-nova"))
        st = km._router_status()
        self.assertEqual(st["declared"], [])
        self.assertIsNone(st["error"], "no nothing-declared advisory when a listing is configured")

    def test_declared_is_reported_after_the_first_party_skip(self):
        vid = next(iter(km._VERSION_FAMILY))
        _env(self, "ROMP_ROUTER_MODELS", "%s, opus, gw-6-astra" % vid)
        km._set_router_models(True, gt=10)
        self.assertEqual(km._router_status()["declared"], ["gw-6-astra"])

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
        self.assertEqual(self.frames, [False], "the boot frames what it installed, outside the lock (the second reviewer's note)")

    def test_the_boots_on_branch_tells_the_backend_itself(self):
        # the told set is read on the backend's own field, with the apply's tell out of the way (stubbed stale): the
        # subset check on _router_declared held from the environment alone (review round nine)
        _env(self, "ROMP_ROUTER_MODELS", DECLARED)
        self.store.write_text(json.dumps({"enabled": True, "gt": 1}))
        km._ROUTER_EVER.update(["gw-6-astra"])          # what an earlier apply installed this kernel life
        sb._ROUTER_IDS = frozenset({"gw-stale-1-x"})
        with mock.patch.object(km, "_router_apply_declared", lambda reason, gen=None: None):   # stale: no apply, no apply tell
            self.assertEqual(km._router_models_boot(), [])
        self.assertEqual(sb._ROUTER_IDS, frozenset({"gw-6-astra"}), "the boot's own tell, on the on branch")

    def test_the_boot_reads_the_store_under_the_lock_it_bumps_in(self):
        # the second reviewer's note: a store read hoisted above the lock passed the placement pin; behaviourally, a flip that lands inside
        # the lock's acquisition must be what the boot reads
        _env(self, "ROMP_ROUTER_MODELS", DECLARED)
        self.store.write_text(json.dumps({"enabled": True, "gt": 1}))
        real = km._SETTINGS_LOCK
        flipped = []

        class Flipping:
            def __enter__(self_):
                r = real.__enter__()
                if not flipped:
                    flipped.append(1)
                    self.store.write_text(json.dumps({"enabled": False, "gt": 2}))   # the off lands as the lock is taken
                return r

            def __exit__(self_, *a):
                return real.__exit__(*a)
        with mock.patch.object(km, "_SETTINGS_LOCK", Flipping()):
            self.assertEqual(km._router_models_boot(), [], "the boot read the store under the lock and saw the off")
        self.assertFalse(km._vouched_model("gw-6-astra"))

    def test_catalog_off_gates_the_listing_alone_on_both_roads(self):
        # the knob is the hermetic lab's no-network rule; the declared install is network-free and is never suppressed
        # (a boot that installed nothing while the payload read on, then a live flip that fetched, was the review's find)
        _env(self, "ROMP_ROUTER_MODELS", DECLARED)
        _env(self, "ROMP_ROUTER_MODELS_URL", "http://127.0.0.1:1/v1/models")
        _env(self, "ROMP_MODEL_CATALOG", "off")
        calls = []
        with mock.patch.object(km, "_fetch_router_models", lambda url, timeout=4: calls.append(url) or ["gw-7-nova"]):
            self.store.write_text(json.dumps({"enabled": True, "gt": 1}))
            self.assertEqual(km._router_models_boot(), IDS, "the declared list installs at boot under the knob")
            self.assertIsNone(km._ROUTER_FETCH_GEN[0], "no fetch armed by the boot")
            km._set_router_models(False, gt=2)
            km._set_router_models(True, gt=3)
            self.assertIsNone(km._ROUTER_FETCH_GEN[0], "no fetch armed by the flip")
        self.assertEqual(calls, [], "the listing is never fetched under the knob, on either road")
        self.assertIn("ROMP_MODEL_CATALOG=off", self.err.getvalue())
        self.assertFalse(km._vouched_model("gw-7-nova"))

    def test_boot_tells_the_backend_even_when_off(self):
        sb._ROUTER_IDS = frozenset({"gw-stale-1-x"})
        self.assertEqual(km._router_models_boot(), [])
        self.assertEqual(sb._ROUTER_IDS, frozenset(), "the backend holds the kernel's current set, told unconditionally")

    def test_a_listing_gateway_unions_its_models_in_on_a_thread(self):
        _env(self, "ROMP_ROUTER_MODELS", "gw-6-astra")
        _env(self, "ROMP_ROUTER_MODELS_URL", "http://127.0.0.1:1/v1/models")
        self.store.write_text(json.dumps({"enabled": True, "gt": 1}))
        with mock.patch.object(km, "_fetch_router_models", lambda url, timeout=4: ["gw-7-nova", "gw-6-astra"]):
            self.assertEqual(km._router_models_boot(), ["gw-6-astra"], "the declared list lands synchronously")
            self._wait(lambda: len(self.frames) >= 2, "the listing's models frame (the thread's last act), after the boot's own")
        self.assertTrue(km._vouched_model("gw-7-nova"))
        self.assertEqual(self.frames, [False, False], "the boot's frame for the declared install, then the augment's, outside the lock")

    def test_a_failing_listing_is_loud_and_the_declared_list_still_serves(self):
        _env(self, "ROMP_ROUTER_MODELS", "gw-6-astra")
        _env(self, "ROMP_ROUTER_MODELS_URL", "http://127.0.0.1:1/v1/models")
        self.store.write_text(json.dumps({"enabled": True, "gt": 1}))

        def boom(url, timeout=4):
            raise OSError("connection refused")
        with mock.patch.object(km, "_fetch_router_models", boom):
            self.assertEqual(km._router_models_boot(), ["gw-6-astra"])
            self._wait(lambda: "failed" in self.err.getvalue(), "the failure line")
        self.assertIn("connection refused", self.err.getvalue())
        self.assertTrue(km._vouched_model("gw-6-astra"))
        self._wait(lambda: km._router_status_note[0] == km.ROUTER_NOTE_LISTING_FAILED, "the listing-failed advisory")
        self._wait(lambda: len(self.frames) >= 2, "the frame that carries it")
        self.assertEqual(self.frames, [False, False], "the boot's frame, then the advisory's: the gear reads the models frame alone")


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
    resolution). The managed path is pointed at an absent file under the same temp dir here, not left to conftest,
    so a bare run is hermetic too (the review's find: a scratch managed file on the box failed two of these)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        _env(self, "CLAUDE_CONFIG_DIR", self.tmp)
        _env(self, "ANTHROPIC_BASE_URL", None)
        managed = os.path.join(self.tmp, "managed-settings.json")
        p = mock.patch.object(km.jd._cred, "managed_settings_path", lambda: managed)
        p.start(); self.addCleanup(p.stop)
        self._said = km._router_probe_said[0]
        self.addCleanup(lambda: km._router_probe_said.__setitem__(0, self._said))

    def _settings(self, body):
        path = os.path.join(self.tmp, "settings.json")
        if body is None:
            if os.path.exists(path):
                os.unlink(path)
        else:
            with open(path, "w") as f:
                f.write(body)
        return self.tmp

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

    def test_the_status_runs_no_probe_while_off(self):
        # the second reviewer's note: a probe run unconditionally and masked while off passed the tests; over a bad settings file and no
        # store, the status must not probe and must say nothing
        self._settings("{not json")
        (km.jd.STATE / km.ROUTER_MODELS_FILE).unlink(missing_ok=True)
        calls = []
        real = km._router_gateway_configured
        with mock.patch.object(km, "_router_gateway_configured", lambda: calls.append(1) or real()), \
                mock.patch.object(km.sys, "stderr", io.StringIO()) as err:
            st = km._router_status()
        self.assertEqual(calls, [], "no probe while the switch is off")
        self.assertEqual(err.getvalue(), "", "and nothing said")
        self.assertEqual((st["enabled"], st["gateway"], st["error"]), (False, None, None))

    def test_an_unparsable_settings_file_is_a_static_fault_with_the_detail_on_stderr_once(self):
        self._settings("{not json")
        with mock.patch.object(km.sys, "stderr", io.StringIO()) as err:
            ok, fault = km._router_gateway_configured()
            self.assertFalse(ok)
            self.assertEqual(fault, km.ROUTER_SETTINGS_FAULT, "the payload's phrase is static")
            self.assertNotIn(self.tmp, fault, "never the file's path")
            self.assertIn(self.tmp, err.getvalue(), "the detail goes to stderr")
            km._router_gateway_configured()
            self.assertEqual(err.getvalue().count(km.ROUTER_SETTINGS_FAULT), 1, "once per distinct fault")

    def test_anthropics_host_is_matched_on_a_label_boundary(self):
        self._settings(None)
        for base, is_gw in (("https://notanthropic.com/v1", True), ("https://api.anthropic.com", False),
                            ("https://anthropic.com", False), ("http://127.0.0.1:8787", True)):
            _env(self, "ANTHROPIC_BASE_URL", base)
            self.assertEqual(km._router_gateway_configured(), (is_gw, None), base)

    def test_the_environment_is_consulted_first(self):
        # sessions inherit the kernel's environment and service.env is where the docs send the operator, so a base URL
        # there counts before any settings file (the review's find: env-only read as no gateway)
        self._settings(None)
        _env(self, "ANTHROPIC_BASE_URL", "http://127.0.0.1:8787/t/redacted")
        self.assertEqual(km._router_gateway_configured(), (True, None))
        _env(self, "ANTHROPIC_BASE_URL", "https://api.anthropic.com")
        self._settings(json.dumps({"env": {"ANTHROPIC_BASE_URL": "http://127.0.0.1:8787/t/redacted"}}))
        self.assertEqual(km._router_gateway_configured(), (False, None), "the environment's word wins over the file")


class SdkBadge(unittest.TestCase):
    def test_a_declared_id_shows_verbatim_on_the_badge(self):
        _env(self, "ROMP_ROUTER_MODELS", DECLARED)
        self.assertEqual(sb.pretty_model("gw-6-astra"), "gw-6-astra")
        self.assertEqual(sb.model_label("", "gw-6-astra"), "gw-6-astra")
        self.assertEqual(sb._alias_label("gw-5.6-terra"), "gw-5.6-terra")
        # and the first-party labels are unchanged
        self.assertEqual(sb.pretty_model("claude-opus-4-8"), "Opus 4.8")
        self.assertEqual(sb._alias_label("opus"), "Opus")

    def test_the_twin_skips_first_party_ids_the_variable_names(self):
        # the review's find: with claude-opus-4-8 declared the badge showed the raw id instead of Opus 4.8, with the
        # switch off; the twin applies the kernel's first-party skip (the regex and the family aliases, pinned equal)
        vid = next(iter(km._VERSION_FAMILY))
        _env(self, "ROMP_ROUTER_MODELS", "%s, opus, gw-6-astra" % vid)
        self.assertEqual(sb._router_declared(), frozenset({"gw-6-astra"}))
        self.assertEqual(sb.pretty_model("claude-opus-4-8"), "Opus 4.8")
        self.assertEqual(sb._alias_label("opus"), "Opus")
        self.assertEqual(sb._ROUTER_FIRST_PARTY_RE.pattern, km._MODEL_ID_RE.pattern, "the grammar twin, byte for byte")
        self.assertEqual(set(sb._ROUTER_FIRST_PARTY_ALIASES), FIRST_PARTY_AT_IMPORT, "the alias twin is the shipped families")

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
                   km._router_apply_declared, km._router_apply_declared_inner, km._set_router_models, km._router_models_boot,
                   km._fetch_router_models,
                   km._router_first_party, km._router_tell_backend, km._router_live_on, km._router_gateway_configured,
                   km._router_declared_effective, km._router_tiers_on, km._router_fetch_allowed,
                   km._router_declared_families, km._reset_unvouched_seed, km._router_switch_state,
                   sb.pretty_model, sb.model_label, sb._alias_label, sb._router_declared, sb.set_router_ids):
            node = ast.parse(inspect.getsource(fn)).body[0]
            code = "\n".join(ast.dump(s) for s in node.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)))
            self.assertNotIn("gpt", code.lower(), fn.__name__)


if __name__ == "__main__":
    unittest.main()
