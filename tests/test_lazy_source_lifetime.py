"""A restored view keeps its hydration source when another leaf of the same session restores."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

from tests.test_asm_checkpoint import Harness, SID, NOW, compacting_variant, em, G, _doc


class _PeerFill(dict):
    """A hydration memo whose first miss for one atom is the instant a peer thread finishes that same atom: its record
    memoized, its body in place, its lazy marker gone, before the caller has read the body for its source (2026-09-20).
    The put and the fill happen by hand, under the lock the caller already holds, so no second hydrate call is needed."""

    def __init__(self, atom, path):
        super().__init__()
        self.atom, self.path, self.fired = atom, str(path), False

    def get(self, key, default=None):
        hit = super().get(key, default)
        if hit is None and key == self.atom.get("uuid") and not self.fired:
            self.fired = True
            at, ln = self.atom["lazy"]["at"]
            with open(self.path, "rb") as fh:
                fh.seek(at)
                rec = json.loads(fh.read(ln))
            self[key] = (rec, ln)
            em._hydrate_one(self.atom, rec)
        return hit


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


class LazySourceLifetime(Harness):
    def tearDown(self):
        self.fresh()                                        # the event model is one module for every test module: the map
        super().tearDown()                                  #  entries, memoized bodies and assembly entries left here go with it

    def make_document(self, directory, fsid, tag, section=True):
        parent = self.td / directory
        parent.mkdir()
        path = parent / (fsid + ".jsonl")
        records = compacting_variant([
            G.uline(G.T0, "prompt for " + tag, "user-" + tag),
            G.aline(G.T0 + 5, "answer for " + tag, "assistant-" + tag, "user-" + tag),
        ], tag)
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
            self.assertTrue(atom.at_read.wait(timeout=10))
            self.assertEqual(em.hydrate([atom]), 1)         # the complete call fills the atom the held thread is about to read
            atom.resume.set()
            self.assertEqual(waiting.result(timeout=10), 1)
        self.assertIsNone(atom.get("lazy"))
        self.assertEqual(atom["message"]["content"], [{"type": "text", "text": "prompt for web"}])

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
