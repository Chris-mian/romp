#!/usr/bin/env python3
"""Two executed pins the Extra models review round 2 (2026-09-22) found missing from tests/test_router_models.py:

- GET /models carries a `router` section equal to kernel._router_status() at that moment, read through the authed
  handler on a loopback lab kernel (the test_codex_models_route idiom), and its shape after an off flip follows the
  contract the lead is adding in parallel: with one live session still running a removed id the section's `error`
  names the live count and `gateway` is null while the switch is off; off with no note, `error` is null. (Red on the
  two off-state fields until that contract lands.)

- Nothing in the router functions keys on a model vendor: a STRUCTURAL check over each function's AST rather than a
  substring pin (which a planted startswith("gemini-") passed). The checker and its rule are documented on
  `vendor_keys` below, and the checker is proved on synthetic functions carrying planted vendor tests, including a
  copy of a real router function's source with startswith("gemini-") planted in it.

Synthetic only. The kernel and the backend are loaded under private module names; the state root is a temp dir with
session hosts off; the gateway probe and the models frame are stubbed; no network on any path exercised here.
"""
import ast
import http.client
import inspect
import io
import json
import os
import re
import sys
import tempfile
import textwrap
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock

from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
# Hermetic state BEFORE the loads: they resolve their state root at import time, and only pytest runs conftest's
# floor (a bare unittest or script run otherwise writes REAL state, and a kernel module that can reach a live
# manager port restarts the live kernel).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
os.environ["ROMP_MANAGER_PORT"] = "1"             # a dead port, never an inherited live one
os.environ["ROMP_MODEL_CATALOG"] = "off"          # never the Models API from a test
for _v in ("ROMP_ROUTER_MODELS", "ROMP_ROUTER_MODELS_URL", "ANTHROPIC_BASE_URL"):
    os.environ.pop(_v, None)
km = load_source("romp_kernel_router_pins", os.path.join(BIN, "romp-kernel"))
sb = load_source("romp_sdk_backend_router_pins", os.path.join(BIN, "romp_sdk_backend.py"))
km.jd.STATE.mkdir(parents=True, exist_ok=True)
(km.jd.STATE / "session-hosts").write_text("off")   # this root is outside conftest's belt (repo rule, 2026-09-11)

DECLARED = "gw-6-astra, gw-5.6-luna,gw-5.6-terra"
IDS = ["gw-6-astra", "gw-5.6-luna", "gw-5.6-terra"]
LIVE_SID = "11111111-2222-4333-8444-555555555555"
OTHER_SID = "11111111-2222-4333-8444-666666666666"


def _env(tc, key, value):
    prev = os.environ.get(key)
    if value is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = value
    tc.addCleanup(lambda: os.environ.__setitem__(key, prev) if prev is not None else os.environ.pop(key, None))


class ModelsRouteRouterSection(unittest.TestCase):
    """The apply mutates the module's model globals in place; snapshot and restore around each test. The handler
    runs in-process on a loopback ThreadingHTTPServer over km.Handler, authed with the lab kernel's own token."""

    def setUp(self):
        self._choices = [dict(c) for c in km.MODEL_CHOICES]
        self._modpatch = mock.patch.dict(sys.modules, {"romp_sdk_backend": sb})   # the kernel tells THIS copy (review round three)
        self._modpatch.start(); self.addCleanup(self._modpatch.stop)
        self._sb_ids = sb._ROUTER_IDS
        self.addCleanup(lambda: setattr(sb, "_ROUTER_IDS", self._sb_ids))
        self._values = set(km._MODEL_VALUES)
        self._judge = set(km._JUDGE_MODEL_VALUES)
        self._rank = list(km._MODEL_RANK)
        self._installed = set(km._ROUTER_INSTALLED)
        self._by_set = {k: set(v) for k, v in km._ROUTER_INSTALLED_BY_SET.items()}
        self._ever = set(km._ROUTER_EVER)
        self._gen = km._ROUTER_GEN[0]
        self._note = km._router_status_note[0]
        self._codex = km._codex_backend
        km._codex_backend = False            # never build the real Codex backend from the /models handler
        for v in ("ROMP_ROUTER_MODELS", "ROMP_ROUTER_MODELS_URL", "ANTHROPIC_BASE_URL"):
            _env(self, v, None)
        self.store = km.jd.STATE / km.ROUTER_MODELS_FILE
        self.store.unlink(missing_ok=True)
        self._orig_changed = km._models_changed
        self._orig_gw = km._router_gateway_configured
        km._models_changed = lambda: None
        km._router_gateway_configured = lambda: (True, None)
        self.err = io.StringIO()
        self._p = mock.patch.object(km.sys, "stderr", self.err)
        self._p.start()
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), km.Handler)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self._p.stop()
        km._models_changed = self._orig_changed
        km._router_gateway_configured = self._orig_gw
        km._codex_backend = self._codex
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
        self.store.unlink(missing_ok=True)

    def _models(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request("GET", "/models", headers={"X-Romp-Token": km.TOKEN})
            r = conn.getresponse()
            self.assertEqual(r.status, 200)
            return json.loads(r.read())
        finally:
            conn.close()

    def _router(self):
        d = self._models()
        self.assertIn("router", d, "the authed /models payload carries the section")
        self.assertEqual(d["router"], km._router_status(), "the section IS _router_status() at that moment")
        self.assertEqual(set(d["router"]), {"enabled", "declared", "gateway", "error"})
        return d["router"]

    def test_the_route_is_token_gated(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request("GET", "/models")
            self.assertNotEqual(conn.getresponse().status, 200, "the declared list rides an AUTHED payload only")
        finally:
            conn.close()

    def test_off_with_no_note_carries_no_error(self):
        _env(self, "ROMP_ROUTER_MODELS", DECLARED)
        r = self._router()
        self.assertIs(r["enabled"], False)
        self.assertEqual(r["declared"], IDS, "the ids this kernel parsed are listed whatever the switch")
        self.assertIsNone(r["error"], "off with no note: no advisory")
        self.assertIsNone(r["gateway"], "the gateway is not probed for a switch that is off")

    def test_on_carries_the_switch_the_declared_list_and_the_gateway(self):
        _env(self, "ROMP_ROUTER_MODELS", DECLARED)
        km._set_router_models(True, gt=10)
        r = self._router()
        self.assertEqual((r["enabled"], r["declared"], r["gateway"], r["error"]), (True, IDS, True, None))
        self.assertIn("gw-6-astra", [m["value"] for m in self._models()["models"]], "and the pick is offered")

    def test_off_with_a_live_session_on_a_removed_id_names_the_count_and_the_gateway_is_null(self):
        _env(self, "ROMP_ROUTER_MODELS", DECLARED)
        km._set_router_models(True, gt=10)
        with mock.patch.object(km, "_live_map", lambda: {LIVE_SID: {"model": "gw-6-astra"},
                                                          OTHER_SID: {"model": "opus"}}):
            km._set_router_models(False, gt=11)
        r = self._router()
        self.assertIs(r["enabled"], False)
        self.assertNotIn("gw-6-astra", [m["value"] for m in self._models()["models"]], "the pick left the list")
        self.assertIsNotNone(r["error"], "a session still runs a removed id: the advisory stands while off")
        self.assertIn("1 live session", r["error"])
        self.assertIsNone(r["gateway"], "off: the gateway field is null")


# --- the structural vendor-key check ------------------------------------------------------------------------------

# The allowlist: whole-value constants the honest router code compares against in a position the checker visits,
# none a vendor. Every entry is load-bearing, and test_the_real_functions_do_exercise_the_allowlist pins each one:
# dropping it flags honest code. (Constants that are tokens under the rule but never reach a visited position need no
# entry — "utf-8" and "router-models" are call arguments in the checked functions (.decode, _setting_stale, the
# thread's name); a bare "claude" appears in NO checked function at all: its compares are the served-turn guard's in
# kernel/sdk_backend.py, outside ROUTER_FUNCTIONS and pinned behaviourally in tests/test_router_models_backend.py;
# review rounds five and six.)
#   "claude-"          the first-party marker: model_label's and _alias_label's startswith (pretty_model's own compare
#                      is its regex lead, which the checker reads too)
#   "anthropic.com"    Anthropic's own host, the gateway probe's boundary match; the token rule DOES read it as a token
#                      (a dot join), so it passes only through this list (".anthropic.com", the suffix match's constant,
#                      starts with a dot and is never a token: no entry)
#   "default", "off"   the CLI's default-model alias (model_label / _alias_label) and the ROMP_MODEL_CATALOG knob's value
#   "triage", "session"   the judge tier stores' sentinels (_router_tiers_on reads them whole)
#   "comment"          the tier _set_router_models words apart from the judge tiers
VENDOR_ALLOW = frozenset({"claude-", "anthropic.com", "default", "off", "triage", "session", "comment"})

# A model-vendor-looking token: lowercase words and digits joined by "-" or ".", optionally ONE trailing separator — the
# shape a vendor prefix or a family word takes ("gemini-", "gpt-", "gpt", "grok", "o3", "gpt5-", "gemini-2", "gpt-5",
# "gemini-1.5-", "o4-mini"). An underscore, an uppercase letter, a space, a leading dot or digit, a format directive or
# punctuation is not one, and neither is "". Constants that ARE tokens but are no vendor ride the allowlist above.
_VENDOR_TOKEN = re.compile(r"^[a-z][a-z0-9]*(?:[-.][a-z0-9]+)*[-.]?$")
# a regex pattern's leading literal run, after an optional anchor: the part a vendor prefix would occupy
_REGEX_LEAD = re.compile(r"^\^?([a-z0-9.-]+)")


def _vendor_token(s):
    return isinstance(s, str) and s not in VENDOR_ALLOW and bool(_VENDOR_TOKEN.match(s))


def _const_str(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def vendor_keys(source):
    """The places a function's source keys on a vendor-looking string constant: each hit is (what, line).

    Walks the function's AST (docstrings and comments are not code and are never visited as tests) and flags:
    - a Call to .startswith / .endswith whose argument (or any member of a tuple argument) is a string constant;
    - a Compare with a string constant as any operand — that is `x == "…"`, `x != "…"`, `x.lower() == "…"`,
      `"…" in x`, `"…" in x.lower()`, `x in "…"`, and their negations;
    - a Call to re.match / re.search / re.fullmatch whose pattern's leading literal run is one;
    UNLESS the constant is on VENDOR_ALLOW or is not a vendor-looking token (_VENDOR_TOKEN). Arguments to any
    other call (.get("data"), .split(","), .decode("utf-8")) are not tests and are not visited."""
    tree = ast.parse(textwrap.dedent(source))
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            attr = node.func.attr
            if attr in ("startswith", "endswith"):
                for a in node.args:
                    for c in (a.elts if isinstance(a, ast.Tuple) else [a]):
                        s = _const_str(c)
                        if s is not None and _vendor_token(s):
                            hits.append(("%s(%r)" % (attr, s), node.lineno, node.col_offset))
            elif attr in ("match", "search", "fullmatch", "compile") and isinstance(node.func.value, ast.Name) \
                    and node.func.value.id == "re" and node.args:
                s = _const_str(node.args[0])
                lead = _REGEX_LEAD.match(s or "")
                if lead and _vendor_token(lead.group(1)):
                    hits.append(("re.%s(%r)" % (attr, s), node.lineno, node.col_offset))
        elif isinstance(node, ast.Compare):
            ops = [type(o).__name__ for o in node.ops]
            for c in [node.left] + node.comparators:
                for e in (c.elts if isinstance(c, (ast.Tuple, ast.List, ast.Set)) else [c]):   # `x in ("gemini", "gpt")`
                    s = _const_str(e)
                    if s is not None and _vendor_token(s):
                        hits.append(("%s %r" % ("/".join(ops), s), node.lineno, node.col_offset))
    hits.sort(key=lambda h: (h[1], h[2]))     # source order (ast.walk is breadth-first)
    return [(what, line) for what, line, _col in hits]


ROUTER_FUNCTIONS = (km._parse_router_models, km._router_label, km._apply_router_families, km._remove_router_families,
                    km._router_apply_declared, km._router_apply_declared_inner, km._set_router_models, km._router_models_boot,
                    km._fetch_router_models,
                    km._router_first_party, km._router_tell_backend, km._router_live_on, km._router_gateway_configured,
                    km._router_declared_effective, km._router_tiers_on, km._router_fetch_allowed, km._router_status,
                    sb.pretty_model, sb.model_label, sb._alias_label, sb._router_declared, sb.set_router_ids,
                    sb._router_first_party)


class GenerationBumpsUnderTheLock(unittest.TestCase):
    """The generation bump sits INSIDE the `with _SETTINGS_LOCK:` body of both writers (a mutant that moves it out
    leaves every behavioural test green, the verify round found): pinned on the AST, as the vendor-key rule is."""

    def _bump_is_locked(self, fn):
        tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
        for node in ast.walk(tree):
            if isinstance(node, ast.With) and any(isinstance(i.context_expr, ast.Name) and i.context_expr.id == "_SETTINGS_LOCK"
                                                  for i in node.items):
                for inner in ast.walk(node):
                    if isinstance(inner, ast.AugAssign) and isinstance(inner.target, ast.Subscript) \
                            and isinstance(inner.target.value, ast.Name) and inner.target.value.id == "_ROUTER_GEN":
                        return True
        return False

    def test_the_flip_publishes_the_mark_in_the_bumps_own_catalog_hold(self):
        # review round thirteen: the bump-and-mark-in-one-hold claim had no test; pinned on the AST: in _set_router_models
        # the mark store sits in the same `with _catalog_lock:` body as the bump
        tree = ast.parse(textwrap.dedent(inspect.getsource(km._set_router_models)))
        holds = [w for w in ast.walk(tree) if isinstance(w, ast.With)
                 and any(isinstance(i.context_expr, ast.Name) and i.context_expr.id == "_catalog_lock" for i in w.items)]
        together = [w for w in holds
                    if any(isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Subscript)
                           and isinstance(n.target.value, ast.Name) and n.target.value.id == "_ROUTER_GEN" for n in ast.walk(w))
                    and any(isinstance(n, ast.Assign) and any(isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name)
                                                              and t.value.id == "_ROUTER_FETCH_GEN" for t in n.targets)
                            for n in ast.walk(w))]
        self.assertEqual(len(together), 1, "one catalog hold carries both the bump and the mark")

    def test_the_snapshot_takes_the_settings_lock_then_the_catalog_lock(self):
        tree = ast.parse(textwrap.dedent(inspect.getsource(km._router_listing_state)))
        outer = [w for w in ast.walk(tree) if isinstance(w, ast.With)
                 and any(isinstance(i.context_expr, ast.Name) and i.context_expr.id == "_SETTINGS_LOCK" for i in w.items)]
        self.assertEqual(len(outer), 1)
        inner = [w for w in ast.walk(outer[0]) if isinstance(w, ast.With)
                 and any(isinstance(i.context_expr, ast.Name) and i.context_expr.id == "_catalog_lock" for i in w.items)]
        self.assertEqual(len(inner), 1, "the catalog hold sits inside the settings hold")
        reads = [n for n in ast.walk(inner[0]) if isinstance(n, ast.Name) and n.id in ("_ROUTER_GEN", "_ROUTER_FETCH_GEN", "_ROUTER_FETCH_FAILED_GEN")]
        self.assertTrue(reads, "the marks are read inside both holds")

    def test_the_setter_and_the_boot_bump_the_generation_under_the_settings_lock(self):
        self.assertTrue(self._bump_is_locked(km._set_router_models))
        self.assertTrue(self._bump_is_locked(km._router_models_boot))
        self.assertEqual(sum(1 for n in ast.walk(ast.parse(textwrap.dedent(inspect.getsource(km._set_router_models))))
                             if isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Subscript)
                             and isinstance(n.target.value, ast.Name) and n.target.value.id == "_ROUTER_GEN"), 1,
                         "one bump per applied flip")


class NoteWriters(unittest.TestCase):
    """The standing advisory has exactly two writers, _router_set_note and _router_swap_note, each writing inside a
    `with _catalog_lock:` body (review round six: a guarded third in-line write that set the same value left every
    behavioural test green, since they read the note's value, never its writer). Pinned on the kernel's whole AST.

    SCOPE, stated (review round eight): the walk sees writes THROUGH THE BARE NAME `_router_status_note`, anywhere in
    the module, module level and class bodies included:
      - a Subscript over the name in Store or Del context, whatever statement carries it (assignment plain, augmented,
        annotated or slice; `del`; a `for`, `with … as` or comprehension target);
      - a call of one of the list's mutating methods on the name (MUTATORS);
      - a rebinding of the name itself (a Name in Store context) anywhere but its one module-level definition.
    Outside it, by choice: an alias (`n = _router_status_note; n[0] = …`), a helper's parameter, operator.setitem,
    list.__setitem__(_router_status_note, …), globals()[…]. Those are the shapes of code written to evade a pin, not of
    a third writer added in good faith; the behavioural tests read the note's value and the reviewers execute the head.
    A read of the note as another target's index (`other[_router_status_note[0]] = …`) is a Load and is NOT a write."""

    MUTATORS = ("append", "clear", "extend", "insert", "pop", "remove", "__setitem__", "__delitem__", "reverse", "sort")
    NAME = "_router_status_note"

    @classmethod
    def _writes(cls, tree):
        """(node, enclosing function name or "<module>") for every write to the note's contents, keyed on the
        Store/Del context of the Subscript, never on the statement's shape; plus every rebinding of the name."""
        parents = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[child] = node

        def enclosing(n):
            while n in parents:
                n = parents[n]
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    return n.name
            return "<module>"

        def is_note(n):
            return isinstance(n, ast.Name) and n.id == cls.NAME
        out = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Subscript) and is_note(node.value) and isinstance(node.ctx, (ast.Store, ast.Del)):
                out.append((node, enclosing(node)))
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and is_note(node.func.value) \
                    and node.func.attr in cls.MUTATORS:
                out.append((node, enclosing(node)))
            elif isinstance(node, ast.Name) and node.id == cls.NAME and isinstance(node.ctx, ast.Store):
                out.append((node, enclosing(node)))          # a rebinding; the module-level definition is one of these
        return out

    def test_every_write_to_the_note_sits_in_one_of_the_two_helpers_under_the_lock(self):
        src = open(os.path.join(os.path.dirname(HERE), "kernel", "kernel.py"), encoding="utf-8").read()
        tree = ast.parse(src)
        writes = self._writes(tree)
        binds = [(n, f) for n, f in writes if isinstance(n, ast.Name)]
        self.assertEqual([f for _, f in binds], ["<module>"], "the name is bound once, at module level, and never rebound")
        content = [(n, f) for n, f in writes if not isinstance(n, ast.Name)]
        self.assertTrue(content, "no write found: the walk is broken")
        self.assertEqual(sorted({f for _, f in content}), ["_router_set_note", "_router_swap_note"])
        fns = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        for node, fname in content:
            fn = fns[fname]
            locked = [w for w in ast.walk(fn) if isinstance(w, ast.With)
                      and any(isinstance(i.context_expr, ast.Name) and i.context_expr.id == "_catalog_lock" for i in w.items)]
            self.assertTrue(any(node in ast.walk(w) for w in locked), "%s writes the note outside _catalog_lock" % fname)

    def test_the_walk_sees_every_shape_in_its_scope_and_no_read(self):
        # every shape the scope names is planted, one per function, and found exactly there; the read-as-index is not
        planted = textwrap.dedent('''
            _router_status_note = [None]
            _router_status_note[0] = "module level"
            def a_plain():   _router_status_note[0] = "x"
            def a_aug():     _router_status_note[0] += "x"
            def a_ann():     _router_status_note[0]: str = "x"
            def a_slice():   _router_status_note[:] = ["x"]
            def a_del():     del _router_status_note[0]
            def a_for():
                for _router_status_note[0] in ("x",): pass
            def a_with(cm):
                with cm as _router_status_note[0]: pass
            def a_comp():    return [1 for _router_status_note[0] in ("x",)]
            def m_append():  _router_status_note.append("x")
            def m_clear():   _router_status_note.clear()
            def m_extend():  _router_status_note.extend(["x"])
            def m_insert():  _router_status_note.insert(0, "x")
            def m_pop():     _router_status_note.pop()
            def m_remove():  _router_status_note.remove("x")
            def m_setitem(): _router_status_note.__setitem__(0, "x")
            def m_delitem(): _router_status_note.__delitem__(0)
            def m_reverse(): _router_status_note.reverse()
            def m_sort():    _router_status_note.sort()
            def r_global():
                global _router_status_note
                _router_status_note = ["x"]
            def r_aug_global():
                global _router_status_note
                _router_status_note += ["x"]
            def not_a_write(other):
                other[_router_status_note[0]] = "read as an index"
                return _router_status_note[0], len(_router_status_note), _router_status_note.index("x")
        ''')
        found = sorted(f for _, f in self._writes(ast.parse(planted)))
        expected = sorted(["<module>", "<module>",   # the definition (a Name Store) and the module-level subscript write
                           "a_plain", "a_aug", "a_ann", "a_slice", "a_del", "a_for", "a_with", "a_comp",
                           "m_append", "m_clear", "m_extend", "m_insert", "m_pop", "m_remove", "m_setitem", "m_delitem",
                           "m_reverse", "m_sort", "r_global", "r_aug_global"])
        self.assertEqual(found, expected)
        self.assertNotIn("not_a_write", found, "a Load of the note, as an index or an argument, is no write")


class NothingKeysOnAVendor(unittest.TestCase):
    def test_no_router_function_keys_on_a_vendor_looking_constant(self):
        for fn in ROUTER_FUNCTIONS:
            self.assertEqual(vendor_keys(inspect.getsource(fn)), [], fn.__module__ + "." + fn.__name__)

    def test_the_real_functions_do_exercise_the_allowlist(self):
        # the check is not vacuous: the honest code tests against allowlisted constants in the positions the
        # checker visits, and would be flagged without the allowlist (the bare host included: the rule reads it as a
        # token, and only the list passes it)
        with mock.patch.object(sys.modules[__name__], "VENDOR_ALLOW", frozenset()):
            hits = [h[0] for fn in ROUTER_FUNCTIONS for h in vendor_keys(inspect.getsource(fn))]
        # every entry of the list, in the position the honest code uses it (an entry none of these reach is inert)
        self.assertIn("startswith('claude-')", hits)
        self.assertIn("Eq 'anthropic.com'", hits)             # the host's boundary match: on the list, not passed by the rule
        self.assertIn("Eq 'default'", hits)
        self.assertIn("NotEq 'off'", hits)      # _router_fetch_allowed: the catalog knob's whole-value compare
        self.assertIn("Eq 'triage'", hits)      # _router_tiers_on's sentinels
        self.assertIn("In 'session'", hits)
        self.assertIn("NotEq 'comment'", hits)  # _set_router_models words the comment default apart
        for entry in VENDOR_ALLOW:
            self.assertTrue(any(("'%s'" % entry) in h for h in hits), "an inert allowlist entry: %r" % entry)
        # and the two constants that are call arguments alone in the checked functions need no entry: never a hit,
        # allowlist or not (a bare "claude" is absent from every checked function; no pin here would be about it)
        for never in ("utf-8", "router-models"):
            self.assertFalse(any(("'%s'" % never) in h for h in hits), never)
        self.assertNotIn("endswith('.anthropic.com')", hits, "a dotted suffix is no vendor token; it needs no entry")
        self.assertTrue(any(h.startswith("re.match('claude-") for h in hits), hits)

    def test_a_planted_startswith_in_a_copy_of_a_real_function_fails_the_check(self):
        src = inspect.getsource(km._router_first_party)
        self.assertEqual(vendor_keys(src), [])
        planted = re.sub(r"\n(\s+)return (.+)\n$", lambda m: '\n%sreturn mid.startswith("gemini-") or (%s)\n' % (m.group(1), m.group(2)), src)
        self.assertNotEqual(planted, src, "the plant landed")
        self.assertEqual([h[0] for h in vendor_keys(planted)], ["startswith('gemini-')"])

    def test_every_planted_shape_is_flagged(self):
        def planted(mid, d):
            if mid.startswith("gemini-") or mid.startswith("gemini-2") or mid.split("-")[0] in ("gemini", "gpt"):
                return 1
            if mid.endswith(("-astra", "gpt-")):
                return 2
            if "grok" in mid.lower():
                return 3
            if mid.lower() == "o3":
                return 4
            if mid == "gpt5-" or "mistral" != mid:
                return 5
            if re.match(r"^gemini-\d", mid):
                return 6
            return d.get("gemini-")   # a .get argument is not a test: not flagged
        what = [h[0] for h in vendor_keys(inspect.getsource(planted))]
        self.assertEqual(what, ["startswith('gemini-')", "startswith('gemini-2')", "In 'gemini'", "In 'gpt'",
                                "endswith('gpt-')", "In 'grok'", "Eq 'o3'", "Eq 'gpt5-'",
                                "NotEq 'mistral'", "re.match('^gemini-\\\\d')"])

    def test_the_honest_shapes_are_not_flagged(self):
        def honest(mid, host, chosen, raw, d, knob):
            if mid.startswith("claude-") or host.endswith("anthropic.com") or host.endswith(".anthropic.com"):
                return 1
            if chosen == "default" or knob.lower() == "off" or knob == "triage" or knob in ("session", "default"):
                return 2
            if re.match(r"claude-([a-z]+)-(\d+)", raw) or re.match(r"^([a-z]+)-([0-9][0-9.]*)-([a-z]+)$", raw):
                return 3
            if mid in d or mid not in ("_MODEL_VALUES", "_JUDGE_MODEL_VALUES") or knob != "comment":
                return 4
            return (d.get("data"), raw.split(","), raw.decode("utf-8", "replace"), "%s-%s" % (mid, host),
                    threading_name("router-models"), "" == raw, "<synthetic>" != raw)

        def threading_name(x):
            return x
        self.assertEqual(vendor_keys(inspect.getsource(honest)), [])

        # the constants the list dropped in round five ARE tokens: a compare against one is flagged, which is why the
        # checked code may only pass them as call arguments (the served-turn guard's `"claude" in m.lower()` sits
        # outside ROUTER_FUNCTIONS and is pinned behaviourally in tests/test_router_models_backend.py)
        def unlisted(mid, raw):
            return "claude" in mid.lower() or "utf-8" == raw or "router-models" in raw
        self.assertEqual([h[0] for h in vendor_keys(inspect.getsource(unlisted))],
                         ["In 'claude'", "Eq 'utf-8'", "In 'router-models'"])

    def test_the_token_rule_is_narrow(self):
        for s in ("gemini-", "gpt-", "gpt", "grok", "o3", "gpt5-", "llama.", "qwen3",
                  "utf-8", "router-models", "claude"):   # tokens under the rule, unlisted: "utf-8" and "router-models" are
            self.assertTrue(_vendor_token(s), s)          # call arguments in the checked code, a bare "claude" is in none
        for s in ("", "_MODEL_VALUES", "<synthetic>", "Gemini-", "gpt 5", " (%s)", "romp_sdk_backend", "gemini--",
                  "5-astra", ".anthropic.com"):
            self.assertFalse(_vendor_token(s), s)
        for s in ("anthropic.com", "claude-", "default", "off"):   # tokens under the rule, passed by the list alone
            self.assertFalse(_vendor_token(s), s)
            with mock.patch.object(sys.modules[__name__], "VENDOR_ALLOW", frozenset()):
                self.assertTrue(_vendor_token(s), s)


if __name__ == "__main__":
    unittest.main()
