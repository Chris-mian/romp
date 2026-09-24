#!/usr/bin/env python3
"""T401 (5c), the boot arc: the planner's seen memo (fsid -> the plan key of its last pass that had nothing to do) persists across
boots in the tick-seen shape, so a boot's first planner pass skips every session whose key stands instead of re-planning all of
them (the 5a read boot: plannerSkip planned 20, skipped 0, and 149,696 atoms built under judge.triage). A row is never an answer
on its own: the key is recomputed at the pass and compared, JSON-normalized on both sides; a malformed row is refused; rows are
dropped with the sessions the pass discovered; the write is atomic under a per-writer tmp, the tmp unlinked and the flag re-armed on a failed replace,
the failure said once per episode. Hermetic: the judge against a temp state root; synthetic transcripts only."""
import ast
import hashlib
import inspect
import re
import io
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import tokenize
import threading
import unittest
from pathlib import Path
from unittest import mock
from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
_ROOT = tempfile.mkdtemp()
os.environ["XDG_STATE_HOME"] = _ROOT
os.environ.pop("ROMP_STATE_DIR", None)
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
os.makedirs(os.path.join(_ROOT, "romp"), exist_ok=True)
Path(_ROOT, "romp", "session-hosts").write_text("off\n")      # a fresh state root pins the hosts off (the 2026-09-11 rule)
em = load_source("romp_event_model", os.path.join(BIN, "romp-event-model"))
jd = load_source("romp_judge", os.path.join(BIN, "romp-judge"))

FSID = "11111111-2222-4333-8444-0000000000f5"          # this module's own synthetic sids
FSID2 = "22222222-2222-4333-8444-0000000000f6"


def _iso(t):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _transcript(path, n=2, t0=1_700_000_000):
    recs, parent = [], None
    for k in range(n):
        u, a = "u%d" % k, "a%d" % k
        recs.append({"type": "user", "uuid": u, "parentUuid": parent, "timestamp": _iso(t0 + 60 * k), "promptSource": "typed",
                     "message": {"role": "user", "content": "prompt %d" % k}})
        recs.append({"type": "assistant", "uuid": a, "parentUuid": u, "timestamp": _iso(t0 + 60 * k + 20),
                     "message": {"role": "assistant", "content": [{"type": "text", "text": "reply %d" % k}], "stop_reason": "end_turn"}})
        parent = a
    Path(path).write_text("".join(json.dumps(r) + "\n" for r in recs))



def _lock_with_bodies(tree):
    """Every statement inside a `with _PLANNER_SEEN_LOCK:` body, at any depth."""
    import ast
    inside = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.With) and any(isinstance(i.context_expr, ast.Name) and i.context_expr.id == "_PLANNER_SEEN_LOCK" for i in n.items):
            for b in n.body:
                for m in ast.walk(b):
                    inside.add(id(m))
    return inside


def _mutation_targets(tree):
    """(node, name) for every AugAssign or Assign whose target is a subscript of _PLANNER_STATS or _PLANNER_SEEN_READ_FAULT."""
    import ast
    out = []
    for n in ast.walk(tree):
        if isinstance(n, (ast.AugAssign, ast.Assign)):
            targets = [n.target] if isinstance(n, ast.AugAssign) else n.targets
            for t in targets:
                if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) and t.value.id in ("_PLANNER_STATS", "_PLANNER_SEEN_READ_FAULT"):
                    out.append((n, t.value.id))
    return out


def _mutations_outside_the_lock(src):
    import ast, textwrap
    tree = ast.parse(textwrap.dedent(src))
    inside = _lock_with_bodies(tree)
    return [name for n, name in _mutation_targets(tree) if id(n) not in inside]


def _mutation_count(src):
    import ast, textwrap
    return len(_mutation_targets(ast.parse(textwrap.dedent(src))))

class PlannerSeenMemo(unittest.TestCase):
    def _reset_memo(self):
        """The memo's module state back to a fresh boot's; tolerant of a tree without the persisted memo (the base run), so
        every test reaches its OWN assertion there instead of a shared setUp raising for all of them."""
        lock = getattr(jd, "_PLANNER_SEEN_LOCK", None) or threading.Lock()
        with lock:
            jd._PLANNER_SEEN.clear()
            for flag in ("_PLANNER_SEEN_DIRTY", "_PLANNER_SEEN_LOADED", "_PLANNER_SEEN_READ_FAULT"):
                if hasattr(jd, flag):
                    getattr(jd, flag)[0] = False
        for k in jd._PLANNER_STATS:
            jd._PLANNER_STATS[k] = {} if k == "mismatchByTerm" else 0

    def setUp(self):
        self.saved = jd.STATE; self.root = Path(tempfile.mkdtemp()); jd._rebind_state(self.root)
        self.addCleanup(jd._rebind_state, self.saved)         # a cleanup runs after a failing setUp too: the shared STATE goes back
        (self.root / "session-hosts").write_text("off\n")
        self._reset_memo()
        self.d = tempfile.mkdtemp(); self.path = os.path.join(self.d, FSID + ".jsonl"); _transcript(self.path)

    def tearDown(self):
        self._reset_memo()

    def _key(self):
        session = jd.parsed_session(FSID, [self.path], 1_700_000_500)
        return jd._plan_key(FSID, self.path, session, 1_700_000_500)

    def test_a_row_round_trips_and_stands_only_while_its_recomputed_key_equals_it(self):
        """The tick-seen rule: recompute and compare, never trust. A recorded key persists, a fresh load restores it, and the skip
        predicate holds while the key stands; a transcript that moved since the row was written changes the key, so the session
        is re-planned."""
        pkey = self._key(); self.assertIsNotNone(pkey, "a keyable session")
        norm = jd._planner_key_norm(pkey); self.assertIsNotNone(norm)
        jd._planner_seen_set(FSID, norm)
        self.assertTrue(jd._PLANNER_SEEN_DIRTY[0]); self.assertTrue(jd.persist_planner_seen(), "a changed row: written")
        self.assertFalse(jd.persist_planner_seen(), "nothing changed since: not written")
        d = json.loads((self.root / jd._PLANNER_SEEN_FILE).read_text()); self.assertEqual(d["v"], 1); self.assertIn(FSID, d["rows"])
        with jd._PLANNER_SEEN_LOCK:
            jd._PLANNER_SEEN.clear()
        jd._PLANNER_SEEN_LOADED[0] = False
        self.assertEqual(jd._load_planner_seen(), 1, "the next kernel loads the row"); self.assertEqual(jd._PLANNER_STATS["restored"], 1)
        self.assertEqual(jd._PLANNER_SEEN.get(FSID), jd._planner_key_norm(self._key()), "the key stands: the pass would skip")
        with open(self.path, "a") as f:                                                  # the transcript moves
            f.write(json.dumps({"type": "user", "uuid": "u9", "parentUuid": "a1", "timestamp": _iso(1_700_000_400), "promptSource": "typed",
                                "message": {"role": "user", "content": "one more"}}) + "\n")
        jd.parse_cache_drop_leaf(self.path)
        self.assertNotEqual(jd._PLANNER_SEEN.get(FSID), jd._planner_key_norm(self._key()), "a moved transcript changes the key: re-planned")

    def test_malformed_rows_are_refused_and_good_ones_loaded_and_another_version_loads_nothing(self):
        p = self.root / jd._PLANNER_SEEN_FILE
        good = ["/p", [1, 2], [[1, 2, 3], None, None], None, None, None, None, []]
        p.write_text(json.dumps({"v": 1, "derivation": [jd._PLANNER_SEEN_DERIVATION_V, jd.PLACEMENTS_V],
                                 "rows": {FSID: good, "not-a-uuid": good, FSID2: "a string"}}))
        self.assertEqual(jd._load_planner_seen(), 1, "one row trusted")
        self.assertEqual(jd._PLANNER_STATS["refused"], 2, "the non-uuid sid and the non-list row refused")
        self.assertEqual(jd._PLANNER_SEEN, {FSID: good})
        self.assertEqual(jd._PLANNER_STATS["restored"], 1)
        jd._PLANNER_SEEN_LOADED[0] = False
        with jd._PLANNER_SEEN_LOCK:
            jd._PLANNER_SEEN.clear()
        p.write_text(json.dumps({"v": 0, "derivation": [jd._PLANNER_SEEN_DERIVATION_V, jd.PLACEMENTS_V], "rows": {FSID: good}}))
        self.assertEqual(jd._load_planner_seen(), 0, "another version: nothing trusted")
        jd._PLANNER_SEEN_LOADED[0] = False
        jd._PLANNER_SEEN_READ_FAULT[0] = False
        p.write_text("{torn"); self.assertEqual(jd._load_planner_seen(), 0, "a torn file: an empty memo, no raise")
        self.assertEqual(jd._PLANNER_STATS["refused"], 4, "the other version and the torn file each counted once (round two, low 1)")
        for bad in ("", "null", "[]"):
            jd._PLANNER_SEEN_LOADED[0] = False; jd._PLANNER_SEEN_READ_FAULT[0] = False; before = jd._PLANNER_STATS["refused"]
            p.write_text(bad); self.assertEqual(jd._load_planner_seen(), 0)
            self.assertEqual(jd._PLANNER_STATS["refused"], before + 1, "%r: one refusal" % bad)
        jd._PLANNER_SEEN_LOADED[0] = False; before = jd._PLANNER_STATS["refused"]; p.unlink()
        self.assertEqual(jd._load_planner_seen(), 0); self.assertEqual(jd._PLANNER_STATS["refused"], before, "a missing file is a fresh root, no refusal")

    def test_a_file_written_under_another_derivation_is_refused_whole(self):
        """Round two, medium 3: a row asserts the planner had nothing to do under the code that wrote it; a derivation or a
        placements-identity change refuses every row, so the first pass after the change plans everything once."""
        p = self.root / jd._PLANNER_SEEN_FILE
        good = ["/p", [1, 2], [[1, 2, 3], None, None], None, None, None, None, [], None, None, None]
        for der in ([jd._PLANNER_SEEN_DERIVATION_V + 1, jd.PLACEMENTS_V], [jd._PLANNER_SEEN_DERIVATION_V, jd.PLACEMENTS_V + 1], None):
            jd._PLANNER_SEEN_LOADED[0] = False; jd._PLANNER_STATS["refused"] = 0
            with jd._PLANNER_SEEN_LOCK:
                jd._PLANNER_SEEN.clear()
            doc = {"v": 1, "rows": {FSID: good, FSID2: good}}
            if der is not None:
                doc["derivation"] = der
            p.write_text(json.dumps(doc))
            self.assertEqual(jd._load_planner_seen(), 0, "derivation %r: nothing trusted" % der)
            self.assertEqual(jd._PLANNER_STATS["refused"], 2, "every row counted refused")
        jd._PLANNER_SEEN_LOADED[0] = False
        p.write_text(json.dumps({"v": 1, "derivation": [jd._PLANNER_SEEN_DERIVATION_V, jd.PLACEMENTS_V], "rows": {FSID: good}}))
        self.assertEqual(jd._load_planner_seen(), 1, "the running derivation: trusted")
        jd._planner_seen_set(FSID2, good); jd.persist_planner_seen()
        self.assertEqual(json.loads(p.read_text())["derivation"], [jd._PLANNER_SEEN_DERIVATION_V, jd.PLACEMENTS_V], "the write stamps the pair")

    def test_an_unserializable_row_is_said_once_and_re_raised_with_the_flag_still_dirty(self):
        """Round two, low 2 (the tick-seen shape, 1610 round two medium 3): the dump runs before the flag clears; a row that
        cannot serialize is a bug that raises to the caller's guard, said once, and the flag stays dirty for the retry."""
        jd._planner_seen_set(FSID, ["a"]); jd.persist_planner_seen()
        with jd._PLANNER_SEEN_LOCK:
            jd._PLANNER_SEEN[FSID2] = [object()]; jd._PLANNER_SEEN_DIRTY[0] = True   # past the norm: a bug's shape
        err = io.StringIO()
        with mock.patch.object(jd, "_PLANNER_SEEN_SAID", [False]), mock.patch.object(jd.sys, "stderr", err):
            for _ in range(2):
                with self.assertRaises(TypeError):
                    jd.persist_planner_seen()
                self.assertTrue(jd._PLANNER_SEEN_DIRTY[0], "still dirty: the next persist retries")
        self.assertEqual(err.getvalue().count("planner-seen memo: not serialized"), 1, err.getvalue())
        with jd._PLANNER_SEEN_LOCK:
            del jd._PLANNER_SEEN[FSID2]
        self.assertTrue(jd.persist_planner_seen(), "the row gone: written")

    def test_a_key_with_a_sentinel_is_neither_recorded_nor_compared(self):
        self.assertIsNone(jd._planner_key_norm(("/p", object())), "a _file_key sentinel cannot be persisted or matched")
        self.assertEqual(jd._planner_key_norm(("/p", (1, 2), 3.5)), ["/p", [1, 2], 3.5], "tuples become lists, numbers stay")

    def test_rows_are_dropped_with_the_sessions_this_pass_discovered(self):
        jd._planner_seen_set(FSID, ["a"]); jd._planner_seen_set(FSID2, ["b"]); jd.persist_planner_seen()
        jd._planner_seen_drop({FSID})
        self.assertEqual(list(jd._PLANNER_SEEN), [FSID]); self.assertTrue(jd._PLANNER_SEEN_DIRTY[0], "the drop dirties: written next")
        self.assertTrue(jd.persist_planner_seen()); self.assertEqual(jd._PLANNER_STATS["persisted"], 1)

    def test_a_failed_replace_unlinks_the_tmp_re_arms_the_flag_and_says_it_once_per_episode(self):
        jd._planner_seen_set(FSID, ["a"])
        p = self.root / jd._PLANNER_SEEN_FILE
        err = io.StringIO()
        def broken_replace(a, b):
            raise OSError("EIO: replace refused")
        with mock.patch.object(jd, "_PLANNER_SEEN_SAID", [False]), mock.patch.object(jd.sys, "stderr", err), mock.patch("os.replace", side_effect=broken_replace):
            self.assertFalse(jd.persist_planner_seen()); self.assertTrue(jd._PLANNER_SEEN_DIRTY[0], "re-armed: the next persist retries")
            self.assertEqual(list(p.parent.glob(p.name + ".tmp.*")), [], "the written tmp was unlinked")
            self.assertFalse(jd.persist_planner_seen())
        self.assertEqual(err.getvalue().count("planner-seen memo: not written"), 1, "said once per episode: %r" % err.getvalue())
        self.assertTrue(jd.persist_planner_seen(), "the fault gone: written")
        self.assertTrue(p.exists()); self.assertTrue(p.read_text().endswith("}"))
        self.assertTrue(list(p.parent.glob("planner-seen.json.tmp.*")) == [], "no tmp left")

    def test_the_plan_pass_loads_once_and_persists_at_its_end_and_the_kernel_drains_it_at_exit(self):
        import inspect
        src = inspect.getsource(jd.run_plan)
        self.assertIn("_load_planner_seen()", src); self.assertIn("persist_planner_seen()", src)
        self.assertIn("_planner_seen_drop({s[0] for s in fleet})", src, "dropped with the sessions this pass discovered, before the pass")
        ksrc = open(os.path.join(BIN, "romp-kernel"), encoding="utf-8").read()
        self.assertIn("jd.persist_planner_seen(force=True)", ksrc, "the exit drain persists it in its own try")

    def test_a_forced_persist_before_any_pass_loaded_the_memo_leaves_the_previous_kernels_rows_alone(self):
        """Round three, medium 1: a kernel that takes SIGTERM before its first planner pass (no session attached yet, or a retry
        pause) never calls run_plan and never loads the memo; its exit drain's forced persist must not replace the previous
        kernel's rows with an empty document. Cross-process: a fresh judge module over the same root, never loaded, forced."""
        jd._planner_seen_set(FSID, ["a"]); jd._planner_seen_set(FSID2, ["b"]); self.assertTrue(jd.persist_planner_seen())
        code = ("import os, sys; sys.path.insert(0, %r); from romp_load import load_source; "
                "jd = load_source('romp_judge_exit_drain', %r); print(jd.persist_planner_seen(force=True))"
                % (HERE, os.path.join(BIN, "romp-judge")))
        env = dict(os.environ, ROMP_STATE_DIR=str(self.root), ROMP_KERNEL_NO_OPEN="1")
        env.pop("XDG_STATE_HOME", None)
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr[-800:])
        self.assertEqual(out.stdout.strip(), "False", "nothing loaded and nothing to say: the forced write declines")
        d = json.loads((self.root / jd._PLANNER_SEEN_FILE).read_text())
        self.assertEqual(sorted(d["rows"]), sorted([FSID, FSID2]), "the previous kernel's rows survive the exit of a kernel that never planned")
        jd._PLANNER_SEEN_LOADED[0] = False
        with jd._PLANNER_SEEN_LOCK:
            jd._PLANNER_SEEN.clear()
        self.assertEqual(jd._load_planner_seen(), 2, "and the next boot restores them")
        jd._planner_seen_drop(set()); self.assertTrue(jd.persist_planner_seen(force=True), "a loaded memo emptied by the drop writes its empty rows: a change")
        self.assertEqual(json.loads((self.root / jd._PLANNER_SEEN_FILE).read_text())["rows"], {})

    def test_a_memo_file_that_is_not_utf8_is_one_refusal_and_the_pass_runs(self):
        """Round three, medium 2: read_text raised UnicodeDecodeError (a ValueError, not an OSError) out of _load_planner_seen and
        out of run_plan, aborting the boot's whole first triage pass; the decode runs under the parse try now."""
        (self.root / jd._PLANNER_SEEN_FILE).write_bytes(b"\xff\xfe{\"v\": 1")
        jd.run_plan(now=1_700_000_500)                                 # the whole pass, over an empty root: must not raise
        self.assertEqual(jd._PLANNER_STATS["refused"], 1, "one refusal for the undecodable file")
        self.assertFalse(jd._PLANNER_SEEN_LOADED[0], "unlatched on a fault since the 5c follow-up: the next pass retries the read")

    def test_a_rebound_root_clears_the_load_latch_with_the_table(self):
        """Round three, low 2: a rebind after a load must load the new root's rows on the next pass, and a forced persist before
        that must not wipe the new root's file."""
        jd._planner_seen_set(FSID, ["a"]); jd.persist_planner_seen()
        self.assertEqual(jd._load_planner_seen(), 1, "this boot's load"); self.assertEqual(jd._load_planner_seen(), 0, "latched: once per boot")
        other = Path(tempfile.mkdtemp()); (other / jd._PLANNER_SEEN_FILE).write_text(json.dumps(
            {"v": 1, "derivation": [jd._PLANNER_SEEN_DERIVATION_V, jd.PLACEMENTS_V], "rows": {FSID2: ["b"]}}))
        jd._rebind_state(other)
        try:
            self.assertFalse(jd._PLANNER_SEEN_LOADED[0], "the latch cleared with the table")
            self.assertFalse(jd.persist_planner_seen(force=True), "nothing loaded under the new root: the forced write declines")
            self.assertEqual(json.loads((other / jd._PLANNER_SEEN_FILE).read_text())["rows"], {FSID2: ["b"]}, "the new root's file stands")
            self.assertEqual(jd._load_planner_seen(), 1, "the new root's rows load")
        finally:
            jd._rebind_state(self.root)

    PLAN_SESSION_TOKENS_SHA16 = "922ce487873ca7eb"   # 2026-09-23: the work run's content-refusal strike (the stash reset, the strike and the give-up note); a due unit's failed call only, no derivation change

    def test_a_change_to_the_plan_session_bumps_the_derivation_or_this_pin(self):
        """Round three, low 3: the derivation bump rule made mechanical. A persisted row asserts the planner had nothing to do
        under the code that wrote it, so a change to _plan_session's body must either bump _PLANNER_SEEN_DERIVATION_V (when a pass
        that had nothing to do under the old code could have something under the new: a heal, a unit shape, a retire rule) or,
        when it cannot move a verdict, update this pin's hash. The hash is of the function's TOKEN stream with comments, newlines
        and indentation dropped: ast.dump and ast.unparse both change their text between Python minors (3.10 to 3.13 gave three
        dump hashes and two unparse hashes for one source in CI), while the token strings of an f-string-free function do not."""
        seg = textwrap.dedent(inspect.getsource(jd._plan_session))
        skip = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING, tokenize.ENDMARKER}
        toks = [t.string for t in tokenize.generate_tokens(io.StringIO(seg).readline) if t.type not in skip]
        self.assertFalse(any(re.match(r"(?i:f|rf|fr)[\"']", t) for t in toks), "no f-string in _plan_session (any of the f, F, rf, fr, Rf prefixes): the token stream stays one across minors")
        h = hashlib.sha256(" ".join(toks).encode()).hexdigest()[:16]
        self.assertEqual(h, self.PLAN_SESSION_TOKENS_SHA16,
                         "_plan_session changed (token sha16 %s): bump _PLANNER_SEEN_DERIVATION_V in kernel/judge.py if a pass that had "
                         "nothing to do under the old code could have something under the new, else set PLAN_SESSION_TOKENS_SHA16 to %s" % (h, h))

    def test_an_unreadable_memo_file_leaves_the_load_unlatched_and_the_forced_drain_write_declines(self):
        """The 5c follow-up (a): the latch was set before the read, so a present-but-unreadable file (EACCES, a transient EIO)
        latched an empty table and a kernel exiting before any pass emptied the file through the drain. Cross-process: a fresh
        judge module over a root whose memo file is unreadable, forced."""
        jd._planner_seen_set(FSID, ["a"]); jd._planner_seen_set(FSID2, ["b"]); self.assertTrue(jd.persist_planner_seen())
        p = self.root / jd._PLANNER_SEEN_FILE
        os.chmod(p, 0)
        self.addCleanup(os.chmod, p, 0o644)
        if os.access(p, os.R_OK):
            self.skipTest("optional: this user reads a mode-000 file (root); the unreadable-file case cannot be staged here")
        code = ("import os, sys; sys.path.insert(0, %r); from romp_load import load_source; "
                "jd = load_source('romp_judge_exit_drain_fault', %r); n = jd._load_planner_seen(); "
                "print(n, jd._PLANNER_SEEN_LOADED[0], jd._PLANNER_STATS['refused'], jd.persist_planner_seen(force=True))"
                % (HERE, os.path.join(BIN, "romp-judge")))
        env = dict(os.environ, ROMP_STATE_DIR=str(self.root), ROMP_KERNEL_NO_OPEN="1")
        env.pop("XDG_STATE_HOME", None)
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr[-800:])
        self.assertEqual(out.stdout.split(), ["0", "False", "1", "False"],
                         "nothing loaded, the latch unset, one refusal, the forced write declined: %r" % out.stdout)
        os.chmod(p, 0o644)
        self.assertEqual(sorted(json.loads(p.read_text())["rows"]), sorted([FSID, FSID2]), "the previous kernel's rows survive")

    def test_a_read_fault_counts_one_refusal_per_fault_spell_and_a_successful_load_re_arms_it(self):
        """The refinement on (a): with the latch left unset on a fault every pass retries the read, so a file that stays unreadable
        counts ONE refusal per fault spell (a flag re-armed by a successful load), not one per pass."""
        p = self.root / jd._PLANNER_SEEN_FILE
        p.write_bytes(b"\xff\xfe torn")
        for _ in range(3):
            self.assertEqual(jd._load_planner_seen(), 0)
            self.assertFalse(jd._PLANNER_SEEN_LOADED[0], "unlatched on a fault: the next pass retries")
        self.assertEqual(jd._PLANNER_STATS["refused"], 1, "three faulting passes, one refusal")
        self.assertFalse(jd.persist_planner_seen(force=True), "the forced write declines while nothing loaded")
        self.assertEqual(p.read_bytes(), b"\xff\xfe torn", "the file untouched")
        p.write_text(json.dumps({"v": 1, "derivation": [jd._PLANNER_SEEN_DERIVATION_V, jd.PLACEMENTS_V], "rows": {FSID: ["a"]}}))
        self.assertEqual(jd._load_planner_seen(), 1, "the fault over: loaded and latched")
        self.assertTrue(jd._PLANNER_SEEN_LOADED[0]); self.assertFalse(jd._PLANNER_SEEN_READ_FAULT[0], "re-armed by the successful load")
        jd._PLANNER_SEEN_LOADED[0] = False; p.write_bytes(b"{torn")
        self.assertEqual(jd._load_planner_seen(), 0); self.assertEqual(jd._PLANNER_STATS["refused"], 2, "a new fault spell counts again")
        p.unlink(); jd._PLANNER_SEEN_LOADED[0] = False
        self.assertEqual(jd._load_planner_seen(), 0); self.assertTrue(jd._PLANNER_SEEN_LOADED[0], "a missing file is a successful empty load: latched")
        self.assertEqual(jd._PLANNER_STATS["refused"], 2, "and no refusal")

    def test_a_read_fault_is_said_once_per_spell_on_stderr_like_the_persists(self):
        """The tidy's low 2: the load's fault was counted but never said though its docstring promised 'said once'."""
        p = self.root / jd._PLANNER_SEEN_FILE; p.write_bytes(b"\xff\xfe torn")
        err = io.StringIO()
        with mock.patch.object(jd.sys, "stderr", err):
            for _ in range(3):
                jd._load_planner_seen()
        self.assertEqual(err.getvalue().count("planner-seen memo: not decoded"), 1, err.getvalue())
        p.write_text(json.dumps({"v": 1, "derivation": [jd._PLANNER_SEEN_DERIVATION_V, jd.PLACEMENTS_V], "rows": {}}))
        self.assertEqual(jd._load_planner_seen(), 0); self.assertTrue(jd._PLANNER_SEEN_LOADED[0])
        jd._PLANNER_SEEN_LOADED[0] = False; p.write_bytes(b"{torn")
        with mock.patch.object(jd.sys, "stderr", err):
            jd._load_planner_seen()
        self.assertEqual(err.getvalue().count("planner-seen memo: not decoded"), 2, "a new spell is said again")

    def test_the_mismatch_histogram_bumps_under_the_memo_lock(self):
        """The tidy's low 4: the pool workers bump mismatchByTerm together; unlocked, a boot read under-counted."""
        import inspect
        src = inspect.getsource(jd._planner_seen_stands)
        self.assertIn("with _PLANNER_SEEN_LOCK:", src)
        self.assertLess(src.index("with _PLANNER_SEEN_LOCK:"), src.index('hist = _PLANNER_STATS["mismatchByTerm"]'))
        jd._planner_seen_set(FSID, ["a", 1, 2]); jd._planner_seen_set(FSID2, ["b", 1, 2])
        for k in list(jd._PLANNER_STATS["mismatchByTerm"]):
            del jd._PLANNER_STATS["mismatchByTerm"][k]
        def bump(fsid, n):
            for _ in range(n):
                jd._planner_seen_stands(fsid, ["x", 9, 2])
        ts = [threading.Thread(target=bump, args=(f, 500)) for f in (FSID, FSID2) for _ in range(3)]
        [t.start() for t in ts]; [t.join(10) for t in ts]
        self.assertEqual(jd._PLANNER_STATS["mismatchByTerm"], {"0": 3000, "1": 3000}, "every bump counted")
        # round two of the tidy: the sibling counters (skipped, planned, recorded) and the read-fault check-and-set with its
        # refused bump go through the same lock. The pin is an AST check (the third tidy): every mutation of _PLANNER_STATS or
        # _PLANNER_SEEN_READ_FAULT in the two helpers sits INSIDE a `with _PLANNER_SEEN_LOCK` body, so a refactor that leaves
        # the with and moves the mutation out fails here (a string pin on the with's presence passed that)
        import inspect
        for fn in (jd._planner_bump, jd._planner_seen_read_fault):
            self.assertEqual(_mutations_outside_the_lock(inspect.getsource(fn)), [], fn.__name__)
        self.assertGreaterEqual(_mutation_count(inspect.getsource(jd._planner_bump)), 1, "the bump is a mutation the check sees")
        self.assertGreaterEqual(_mutation_count(inspect.getsource(jd._planner_seen_read_fault)), 2, "the flag set and the refused bump")
        moved = "def _planner_bump(key):\n    with _PLANNER_SEEN_LOCK:\n        pass\n    _PLANNER_STATS[key] += 1\n"   # the with kept, the
        self.assertEqual(_mutations_outside_the_lock(moved), ["_PLANNER_STATS"],                                       #  mutation moved out
                         "the check is red on a copy whose mutation left the with (red first by construction); a string pin on the with passed it")
        for key, fn in (("skipped", jd._plan_session), ("planned", jd._plan_session), ("recorded", jd._plan_session)):
            fn_src = inspect.getsource(fn)
            self.assertIn('_planner_bump("%s")' % key, fn_src, key)
            self.assertNotIn('_PLANNER_STATS["%s"] += 1' % key, fn_src, "a bare bump outside the lock")

    def test_the_perf_row_carries_the_three_new_counters(self):
        self.assertEqual(set(jd.planner_skip_stats()), {"skipped", "planned", "recorded", "restored", "refused", "persisted", "mismatchByTerm"})
        s = jd.planner_skip_stats(); s["mismatchByTerm"]["9"] = 5
        self.assertEqual(jd.planner_skip_stats()["mismatchByTerm"], {}, "the histogram is copied, not shared")


if __name__ == "__main__":
    unittest.main()
