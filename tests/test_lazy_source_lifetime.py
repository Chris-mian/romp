"""A restored view keeps its hydration source when another leaf of the same session restores."""
import inspect
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))          # a script run puts only tests/ on sys.path; the harness import wants the checkout root
from tests.test_asm_checkpoint import Harness, SID, NOW, compacting_variant, em, G, _doc   # noqa: E402


class _PeerFill(dict):
    """A hydration memo whose first miss for one atom is the instant a peer thread finishes that same atom: its record
    memoized, its body in place, its lazy marker gone, before the caller has read the body for its source (2026-09-20).
    The put and the fill happen by hand, under the lock the caller already holds, so no second hydrate call is needed.
    `puts` False is a peer whose put has left the memo already (a cap the record does not fit under): the atom is
    filled and the memo holds nothing for it (2026-09-20)."""

    def __init__(self, atom, path, puts=True):
        super().__init__()
        self.atom, self.path, self.puts, self.fired = atom, str(path), puts, False

    def get(self, key, default=None):
        hit = super().get(key, default)
        if hit is None and key == self.atom.get("uuid") and not self.fired:
            self.fired = True
            at, ln = self.atom["lazy"]["at"]
            with open(self.path, "rb") as fh:
                fh.seek(at)
                rec = json.loads(fh.read(ln))
            if self.puts:
                self[key] = (rec, ln)
            self.fill(rec)
        return hit

    def fill(self, rec):
        em._hydrate_one(self.atom, rec)


class _PeerMidFill(_PeerFill):
    """The same peer caught between its statements: the record memoized and the message set, the marker pop still to
    come (the double sets the message alone so the arm's own _hydrate_one is what puts the tool result in place), so the
    caller that meets the plain-dict body has a fill to finish from the memo (2026-09-20)."""

    def fill(self, rec):
        self.atom["message"] = em._norm_message(rec["message"])


class _PausedAtom(dict):
    """An atom whose first body read from a thread other than its owner waits for a signal: that thread stands between
    its memo miss and the read of the body while the owner's complete call fills the atom (2026-09-20)."""

    def __init__(self, atom, owner):
        super().__init__(atom)
        self.owner, self.paused = owner, False
        self.at_read, self.resume = threading.Event(), threading.Event()

    def get(self, key, default=None):
        if key == "message" and not self.paused and threading.current_thread() is not self.owner:
            self.paused = True
            self.at_read.set()
            self.resume.wait(timeout=10)
        return super().get(key, default)


class _PausedFill(dict):
    """An atom whose first message write from a thread other than its owner waits for a signal: that thread stands inside
    _hydrate_one just after its message set, its memo put behind it, while the owner's call meets the plain-dict body
    (2026-09-20)."""

    def __init__(self, atom, owner):
        super().__init__(atom)
        self.owner, self.paused = owner, False
        self.at_set, self.resume = threading.Event(), threading.Event()

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        if key == "message" and not self.paused and threading.current_thread() is not self.owner:
            self.paused = True
            self.at_set.set()
            self.resume.wait(timeout=10)


TOOL_RESULT = {"answers": {"which": "the first"}}     # a question tool's structured result: `answers` is a consumed key, so the
#                                                        emit carries it on the atom and the lazy marker gets its tur bit


class LazySourceLifetime(Harness):
    def tearDown(self):
        self.fresh()                                        # the event model is one module for every test module: the map
        super().tearDown()                                  #  entries, memoized bodies and assembly entries left here go with it

    def make_document(self, directory, fsid, tag, section=True, tool=False):
        """`tool` True puts a tool call, its result record (a kind-u atom whose toolUseResult is TOOL_RESULT) and the reply
        before the cut, so a restored view holds a lazy atom with a tool result to fill (2026-09-20)."""
        parent = self.td / directory
        parent.mkdir()
        path = parent / (fsid + ".jsonl")
        before = [G.uline(G.T0, "prompt for " + tag, "user-" + tag)]
        if tool:
            result = G.trline(G.T0 + 6, "tu_assistant-%s_0" % tag, "result-" + tag, "assistant-" + tag, content="asked")
            result["toolUseResult"] = dict(TOOL_RESULT)
            before += [G.aline(G.T0 + 5, "answer for " + tag, "assistant-" + tag, "user-" + tag, tools=("AskUserQuestion",),
                               stop="tool_use"),
                       result,
                       G.aline(G.T0 + 8, "noted for " + tag, "close-" + tag, "result-" + tag)]
        else:
            before.append(G.aline(G.T0 + 5, "answer for " + tag, "assistant-" + tag, "user-" + tag))
        records = compacting_variant(before, tag)
        path.write_text("".join(json.dumps(r) + "\n" for r in records))
        tree = self.parse_leaf(path)
        self.assertTrue(em.asm_checkpoint_write(str(path), SID, tree=tree if section else None))
        return path

    def parse_leaf(self, path, modes=None):
        return em.parse_session(str(path), rompuuid=SID, name="web", dir="/TESTDIR",
                                candidate_files=[str(path)], postal_log=[], now=NOW, asm_mode_out=modes)

    def restore(self, path):
        modes = []
        tree = self.parse_leaf(path, modes)
        self.assertEqual(modes, ["restore"])
        return tree

    @staticmethod
    def atom_of(tree, uuid):
        return next(a for t in tree["turns"] for a in t["atoms"] if a.get("uuid") == uuid)

    def user_atom(self, tree, tag):
        return self.atom_of(tree, "user-" + tag)

    def tool_atom(self, tree, tag):
        return self.atom_of(tree, "result-" + tag)

    @staticmethod
    def index_atom(doc, path, uuid):
        """The atom `uuid` built by a LazyIndex over `doc`, the road a restored tree's pre-cut turns take."""
        index = em.LazyIndex(doc, SID, str(path))
        return next(index.build(k) for k in range(len(index.rowb)) if index.uuid_of(k) == uuid)

    def test_another_leaf_does_not_remove_a_held_views_source(self):
        first = self.make_document("web", G.FSID_A, "web")
        second = self.make_document("api", G.FSID_B, "api")
        self.fresh()
        old = self.restore(first)
        atom = self.user_atom(old, "web")
        self.assertIsNotNone(atom.get("lazy"))
        self.restore(second)
        self.assertTrue(first.exists())
        em.hydrate([atom])
        self.assertEqual(atom["message"]["content"], [{"type": "text", "text": "prompt for web"}])

    def test_same_fsid_in_another_location_does_not_retarget_a_held_view(self):
        first = self.make_document("web", G.FSID_A, "web")
        second = self.make_document("api", G.FSID_A, "api")
        self.fresh()
        atom = self.user_atom(self.restore(first), "web")
        self.restore(second)
        em.hydrate([atom])
        self.assertEqual(atom["message"]["content"], [{"type": "text", "text": "prompt for web"}])

    def test_atoms_only_checkpoint_keeps_its_source_too(self):
        first = self.make_document("web", G.FSID_A, "web", section=False)
        second = self.make_document("api", G.FSID_B, "api")
        self.fresh()
        atom = self.user_atom(self.restore(first), "web")
        self.restore(second)
        copied = dict(atom)
        em.hydrate([copied])
        self.assertEqual(copied["message"]["content"], [{"type": "text", "text": "prompt for web"}])

    def test_materializing_after_another_restore_uses_the_original_document(self):
        first = self.make_document("web", G.FSID_A, "web")
        second = self.make_document("api", G.FSID_B, "api")
        self.fresh()
        old = self.restore(first)
        self.restore(second)
        atom = self.user_atom(old, "web")
        em.hydrate([atom])
        self.assertEqual(atom["message"]["content"], [{"type": "text", "text": "prompt for web"}])

    def test_concurrent_restores_hydrate_their_own_views(self):
        first = self.make_document("web", G.FSID_A, "web")
        second = self.make_document("api", G.FSID_B, "api")
        self.fresh()
        barrier = threading.Barrier(2)

        def run(path, tag):
            tree = self.restore(path)
            barrier.wait(timeout=5)
            atom = self.user_atom(tree, tag)
            em.hydrate([atom])
            return atom["message"]["content"]

        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(run, first, "web")
            b = pool.submit(run, second, "api")
            self.assertEqual(a.result(timeout=10), [{"type": "text", "text": "prompt for web"}])
            self.assertEqual(b.result(timeout=10), [{"type": "text", "text": "prompt for api"}])

    def test_a_removed_source_does_not_redirect_to_another_document(self):
        first = self.make_document("web", G.FSID_A, "web")
        second = self.make_document("api", G.FSID_A, "api")
        self.fresh()
        atom = self.user_atom(self.restore(first), "web")
        self.restore(second)
        first.unlink()
        with self.assertRaises(FileNotFoundError):         # the open of the bound path itself fails, unconverted: a read redirected
            em.hydrate([atom])                              #  to the api copy would answer for another document instead of failing

    def test_a_peer_finishing_the_atom_at_the_memo_miss_does_not_fail_the_call(self):
        """The first loop of hydrate misses the memo under the lock and reads the body for its source after releasing it. A
        peer that finishes the same atom in that window leaves a plain dict, which has no source; the per-session map, which
        the api restore has since repointed, then refused an atom whose body was already in place, and with it every other
        atom of the call (2026-09-20)."""
        first = self.make_document("web", G.FSID_A, "web")
        second = self.make_document("api", G.FSID_B, "api")
        self.fresh()
        old = self.restore(first)
        atom, answer = self.user_atom(old, "web"), self.atom_of(old, "assistant-web")
        self.restore(second)
        with mock.patch.object(em, "_HYDRATED", _PeerFill(atom, first)):
            self.assertEqual(em.hydrate([atom, answer]), 2)
        self.assertIsNone(atom.get("lazy"))
        self.assertEqual(atom["message"]["content"], [{"type": "text", "text": "prompt for web"}])
        self.assertEqual(answer["message"]["content"], [{"type": "text", "text": "answer for web"}])

    def test_a_peers_complete_call_during_the_body_read_does_not_fail_the_call(self):
        """The same window with two real threads: the second is held between its memo miss and its body read while the
        first runs a complete call that fills the atom; the second resumes into a filled body (2026-09-20)."""
        first = self.make_document("web", G.FSID_A, "web")
        second = self.make_document("api", G.FSID_B, "api")
        self.fresh()
        atom = _PausedAtom(self.user_atom(self.restore(first), "web"), threading.current_thread())
        self.restore(second)
        with ThreadPoolExecutor(max_workers=1) as pool:
            waiting = pool.submit(em.hydrate, [atom])
            if not atom.at_read.wait(timeout=10):
                waiting.result(timeout=0)              # the worker failed before its body read: on main the first loop never
                self.fail("the worker never reached the body read")   # reads the body, so its LazyBodyRead is the evidence, not a timeout
            self.assertEqual(em.hydrate([atom]), 1)         # the complete call fills the atom the held thread is about to read
            atom.resume.set()
            self.assertEqual(waiting.result(timeout=10), 1)
        self.assertIsNone(atom.get("lazy"))
        self.assertEqual(atom["message"]["content"], [{"type": "text", "text": "prompt for web"}])

    def test_a_peers_fill_caught_between_its_statements_is_finished_from_the_memo(self):
        """The first loop meets a plain-dict body while the peer's entry stands: the peer memoized its record and set
        the message, its marker pop still to come (the double leaves the tool result unset so the finish is observable).
        The memo re-read under the lock finishes the fill from the hit, so the call returns a whole atom, marker gone
        and tool result in place (2026-09-20)."""
        first = self.make_document("web", G.FSID_A, "web", tool=True)
        self.fresh()
        atom = self.tool_atom(self.restore(first), "web")
        self.assertTrue(atom["lazy"].get("tur"))
        with mock.patch.object(em, "_HYDRATED", _PeerMidFill(atom, first)):
            self.assertEqual(em.hydrate([atom]), 1)
        self.assertIsNone(atom.get("lazy"))
        self.assertEqual(atom["toolUseResult"], TOOL_RESULT)
        self.assertEqual(atom["message"]["content"][0]["tool_use_id"], "tu_assistant-web_0")

    def test_a_peers_finished_fill_whose_entry_left_the_memo_counts_the_atom_filled(self):
        """The same plain-dict body with the entry gone: the peer filled the atom whole and its put left the memo at once
        (a cap the record does not fit under). There is nothing to finish from; the atom counts as filled, and the
        call neither reads a gone entry nor refuses the body (2026-09-20)."""
        first = self.make_document("web", G.FSID_A, "web", tool=True)
        self.fresh()
        atom = self.tool_atom(self.restore(first), "web")
        memo = _PeerFill(atom, first, puts=False)
        with mock.patch.object(em, "_HYDRATED", memo):
            self.assertEqual(em.hydrate([atom]), 1)
        self.assertEqual(dict(memo), {})                    # the entry-gone arm is the one the call took
        self.assertIsNone(atom.get("lazy"))
        self.assertEqual(atom["toolUseResult"], TOOL_RESULT)

    def test_a_kind_u_body_met_mid_fill_carries_its_tool_result(self):
        """Two real threads under a cap of 0: the peer's put leaves the memo at once, and the peer is held inside
        _hydrate_one just after its message set. The other thread's call then meets a plain-dict body with no entry to
        finish from and returns; the tool result must already be on the atom, so _hydrate_one writes it before the
        message and only the marker pop is still in flight (2026-09-20)."""
        first = self.make_document("web", G.FSID_A, "web", tool=True)
        self.fresh()
        atom = _PausedFill(self.tool_atom(self.restore(first), "web"), threading.current_thread())
        with mock.patch.object(em, "_HYDRATED_CAP", 0), ThreadPoolExecutor(max_workers=1) as pool:
            peer = pool.submit(em.hydrate, [atom])
            if not atom.at_set.wait(timeout=10):
                peer.result(timeout=0)
                self.fail("the peer never set the body")
            with em._ASM_CKPT_LOCK:
                self.assertEqual(dict(em._HYDRATED), {})    # the put self-evicted: this call takes the entry-gone arm
            self.assertIsNotNone(atom.get("lazy"))          # the peer's marker pop is the write still to come
            self.assertEqual(em.hydrate([atom]), 1)
            self.assertEqual(atom.get("toolUseResult"), TOOL_RESULT)   # at return, not after the peer resumes
            atom.resume.set()
            self.assertEqual(peer.result(timeout=10), 1)
        self.assertIsNone(atom.get("lazy"))
        self.assertEqual(atom["toolUseResult"], TOOL_RESULT)

    def test_a_sentinel_of_a_rebound_class_is_still_read(self):
        """The module loader re-executes an existing name into the same module object, rebinding every class, so a body
        built before a re-execution is no instance of the class the module holds afterward. The first loop keys on the
        body's source slot, not its class: such a BOUND body is read, not counted filled and left in place with its
        marker for the caller's next body read to raise on. An unbound body built before the re-execution still fails
        loudly, since its stale source sentinel is no path; the product re-executes the module only at import time,
        before any body exists (2026-09-20)."""
        first = self.make_document("web", G.FSID_A, "web")
        self.fresh()
        atom = self.user_atom(self.restore(first), "web")
        rebound = type("_LazyBody", (dict,), {})           # the name after a re-execution: another class object
        with mock.patch.object(em, "_LazyBody", rebound):
            self.assertEqual(em.hydrate([atom]), 1)
        self.assertIsNone(atom.get("lazy"))
        self.assertEqual(atom["message"]["content"], [{"type": "text", "text": "prompt for web"}])

    def test_is_lazy_answers_for_a_sentinel_of_a_rebound_class(self):
        """The same re-execution, seen by the module's one public predicate: is_lazy keys on the body's source slot, as the
        first loop does, so a bound body built before the module was re-executed still answers True, where a class check
        against the rebound name answered False for it. The edges hold as before: a plain-dict body, a None body and an
        atom with no message key have no slot and answer False. The product re-executes the module only at import time,
        before any body exists, so this pins the module's one rule rather than a reachable defect. Two shapes separate the
        slot from the lazy marker: a plain-dict body under a marker still present is the mid-fill window (_hydrate_one
        sets the message and pops the marker as its last write) and answers False, where a marker-keyed predicate says
        True; a lazy body with no marker answers True, where a predicate wanting both says False. The product never
        builds the second shape, since the pop is the last write, so that assert pins the rule alone (2026-09-21)."""
        first = self.make_document("web", G.FSID_A, "web")
        self.fresh()
        atom = self.user_atom(self.restore(first), "web")
        self.assertTrue(em.is_lazy(atom))
        rebound = type("_LazyBody", (dict,), {})           # the name after a re-execution: another class object
        with mock.patch.object(em, "_LazyBody", rebound):
            self.assertTrue(em.is_lazy(atom))
        plain = {"role": "user", "content": "prompt for web"}
        self.assertFalse(em.is_lazy({"uuid": "user-web", "message": plain}))
        self.assertFalse(em.is_lazy({"uuid": "user-web", "message": None}))
        self.assertFalse(em.is_lazy({"uuid": "user-web"}))
        self.assertFalse(em.is_lazy({"uuid": "user-web", "lazy": {"k": "u"}, "message": plain}))   # the mid-fill window
        p = str(self.td / "web" / (G.FSID_A + ".jsonl"))
        self.assertTrue(em.is_lazy({"uuid": "user-web", "message": em._LazyBody("user-web", p)}))   # the rule, not a product shape

    def test_two_sentinels_of_one_uuid_compare_equal_across_a_rebound_class(self):
        """The re-execution's shape for equality: the module's class name rebound to a REAL second class, built by
        executing the module's own class statement again over the helpers it names, so a sentinel of the old class and one
        of the new class of one uuid meet. They compare equal in both directions, unequal in neither, are members of each
        other's one-element list, and hash alike, as do two old-class sentinels; equality keys on the source slot and the
        uuid, and the hash already keyed on the uuid alone. A class-identity check made the cross-class pair unequal, and
        a check against the rebound name made two old-class sentinels unequal. A plain dict and the unhydrated marker,
        which carries a uuid but no source slot, stay unequal, as do two sentinels of different uuids. The != side
        answers the opposite of == throughout, under the rebinding too (the standalone pin of that side is the next test)
        (2026-09-21)."""
        u, p = "user-web", str(self.td / "web" / (G.FSID_A + ".jsonl"))
        a, b, other = em._LazyBody(u, p), em._LazyBody(u, p), em._LazyBody("user-api", p)
        scope = {"_Unhydrated": em._Unhydrated, "_UNBOUND_LAZY_SOURCE": em._UNBOUND_LAZY_SOURCE, "LazyBodyRead": em.LazyBodyRead}
        exec(inspect.getsource(em._LazyBody), scope)     # the class statement run again: another class object, same body
        rebound = scope["_LazyBody"]
        self.assertIsNot(rebound, em._LazyBody)
        c = rebound(u, p)
        with mock.patch.object(em, "_LazyBody", rebound):
            self.assertTrue(a == b)
            self.assertTrue(b == a)
            self.assertTrue(a == c)
            self.assertTrue(c == a)
            self.assertFalse(a != c)
            self.assertFalse(c != a)
            self.assertIn(a, [c])
            self.assertIn(c, [a])
            self.assertIn(a, [b])
            self.assertEqual(hash(a), hash(b))
            self.assertEqual(hash(a), hash(c))
            self.assertFalse(a == other)
            self.assertFalse(a == {})
            self.assertFalse(a == em._Unhydrated(u))
            self.assertFalse(a != b)
            self.assertFalse(b != a)
            self.assertTrue(a != other)
            self.assertTrue(a != {})
            self.assertTrue(a != em._Unhydrated(u))
        self.assertTrue(a == b)                             # and with the module's own class back in place
        self.assertTrue(a == c)
        self.assertFalse(a != b)

    def test_not_equal_answers_the_opposite_of_equal_for_two_sentinels(self):
        """Two sentinels of one uuid, the module's own class and no rebinding: == True and != False. The class defined
        __eq__ alone, and the dict base's own __ne__ sits before object's in the method lookup, so != never consulted the
        class's __eq__: it compared the two storages, each holding its own unhydrated marker object, and the pair answered
        both == True and != True. A plain dict and the unhydrated marker stay unequal on the != side as well (2026-09-21)."""
        u, p = "user-web", str(self.td / "web" / (G.FSID_A + ".jsonl"))
        a, b = em._LazyBody(u, p), em._LazyBody(u, p)
        self.assertTrue(a == b)
        self.assertFalse(a != b)
        self.assertFalse(b != a)
        self.assertTrue(a != em._LazyBody("user-api", p))
        self.assertTrue(a != {})
        self.assertTrue(a != em._Unhydrated(u))

    def test_a_bound_body_missing_from_its_files_map_does_not_borrow_another_documents_path(self):
        """A files map that lacks the body's fsid (hand-edited or corrupt: the writer keys files and fsids from the same
        ingested file) is a loud failure even when the per-session map names another document under that fsid (2026-09-20)."""
        first = self.make_document("web", G.FSID_A, "web")
        second = self.make_document("api", G.FSID_A, "api")
        self.fresh()
        self.restore(first)
        self.restore(second)                                # the per-session map names the api document under the shared fsid
        doc = _doc(first)
        del doc["files"][G.FSID_A]
        atom = self.index_atom(doc, first, "user-web")
        with self.assertRaisesRegex(em.LazyBodyRead, "no file known"):
            em.hydrate([atom])

    def test_an_unbound_body_hydrates_through_the_per_session_map(self):
        """The legacy road: a descriptor built without a verified document (no files key) carries the unbound sentinel and
        hydrates through the per-session map the restore's own write primed (2026-09-20)."""
        first = self.make_document("web", G.FSID_A, "web")
        self.fresh()
        self.restore(first)
        self.assertEqual(em._LAZY_FILES[SID].get(G.FSID_A), str(first))
        doc = _doc(first)
        del doc["files"]
        atom = self.index_atom(doc, first, "user-web")
        self.assertIs(atom["message"].source_path, em._UNBOUND_LAZY_SOURCE)
        self.assertEqual(em.hydrate([atom]), 1)
        self.assertEqual(atom["message"]["content"], [{"type": "text", "text": "prompt for web"}])

    def test_an_unbound_body_with_no_entry_is_refused(self):
        first = self.make_document("web", G.FSID_A, "web")
        self.fresh()                                        # nothing restored under this session: the map has no entry for it
        doc = _doc(first)
        del doc["files"]
        atom = self.index_atom(doc, first, "user-web")
        self.assertIs(atom["message"].source_path, em._UNBOUND_LAZY_SOURCE)
        with self.assertRaisesRegex(em.LazyBodyRead, "no file known"):
            em.hydrate([atom])
