#!/usr/bin/env python3
"""The new-session directory: completion, status, and the create-it-or-edit-it fork (the user 2026-07-28).

A session's cwd is fixed at creation, so a wrong path can't be fixed later — it was already rejected up
front. What was missing is everything around that rejection: the picker typed paths blind (a datalist of
past dirs and a native dialog that only ever showed the LOCAL machine), and a missing directory came back
as a toast the "Opening…" cue was covering, so the create looked like it silently did nothing.

Now the kernel that will OWN the session answers three questions over the wire — what does this path
complete to, what IS it, and shall I make it — which is also what makes the field work for a session on a
remote host: federation routes the same ops to that host's kernel, and it reads its own disk.

Synthetic paths in a temp dir only.
"""
import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel_newdir", os.path.join(BIN, "romp-kernel")).load_module()


class _Dirs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: None)   # the temp tree is the OS's to reap; nothing here is precious


class ResolveCreateDir(_Dirs):
    def test_an_existing_directory_resolves(self):
        p, err = km._resolve_create_dir(self.tmp)
        self.assertIsNone(err)
        self.assertEqual(os.path.realpath(p), os.path.realpath(self.tmp))

    def test_blank_is_the_kernel_default(self):
        self.assertEqual(km._resolve_create_dir("")[0], km._default_create_dir())
        self.assertEqual(km._resolve_create_dir(None)[1], None)

    def test_a_missing_directory_is_refused_without_create(self):
        p, err = km._resolve_create_dir(os.path.join(self.tmp, "nope"))
        self.assertIsNone(p)
        self.assertIn("directory not found", err)

    def test_create_makes_the_whole_missing_chain(self):
        target = os.path.join(self.tmp, "a", "b", "c")
        p, err = km._resolve_create_dir(target, create=True)
        self.assertIsNone(err)
        self.assertTrue(os.path.isdir(target))
        self.assertEqual(os.path.realpath(p), os.path.realpath(target))

    def test_a_file_in_the_way_is_never_created_over(self):
        f = os.path.join(self.tmp, "afile")
        open(f, "w").close()
        for create in (False, True):
            p, err = km._resolve_create_dir(f, create=create)
            self.assertIsNone(p)
            self.assertIn("not a directory", err)
        self.assertTrue(os.path.isfile(f), "the file is untouched")

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root ignores the mode bits")
    def test_a_creation_that_fails_reports_instead_of_pretending(self):
        blocked = os.path.join(self.tmp, "ro")
        os.makedirs(blocked)
        os.chmod(blocked, 0o500)
        self.addCleanup(os.chmod, blocked, 0o700)
        p, err = km._resolve_create_dir(os.path.join(blocked, "child"), create=True)
        self.assertIsNone(p)
        self.assertIn("could not create", err)


class DirStatus(_Dirs):
    def test_blank_reports_the_default_and_offers_nothing_to_create(self):
        st = km._dir_status("")
        self.assertTrue(st["isDefault"])
        self.assertTrue(st["isDir"])
        self.assertFalse(st["canCreate"])

    def test_an_existing_directory(self):
        st = km._dir_status(self.tmp)
        self.assertTrue(st["exists"])
        self.assertTrue(st["isDir"])
        self.assertFalse(st["isFile"])
        self.assertFalse(st["canCreate"])
        self.assertEqual(st["missing"], 0)

    def test_a_missing_path_names_the_deepest_ancestor_and_how_much_is_missing(self):
        st = km._dir_status(os.path.join(self.tmp, "x", "y", "z"))
        self.assertFalse(st["exists"])
        self.assertTrue(st["canCreate"])
        self.assertEqual(st["missing"], 3)
        self.assertEqual(os.path.realpath(os.path.expanduser(st["nearest"])), os.path.realpath(self.tmp))

    def test_a_file_can_never_be_created_into_a_directory(self):
        f = os.path.join(self.tmp, "afile")
        open(f, "w").close()
        st = km._dir_status(f)
        self.assertTrue(st["isFile"])
        self.assertFalse(st["canCreate"], "no create offer for a path that is already something else")

    def test_tilde_and_vars_expand(self):
        st = km._dir_status("~")
        self.assertTrue(st["isDir"])
        os.environ["ROMP_TEST_DIR"] = self.tmp
        self.addCleanup(os.environ.pop, "ROMP_TEST_DIR", None)
        self.assertTrue(km._dir_status("$ROMP_TEST_DIR")["isDir"])


class DirCompletions(_Dirs):
    def setUp(self):
        super().setUp()
        for d in ("alpha", "album", "beta", ".hidden"):
            os.makedirs(os.path.join(self.tmp, d))
        open(os.path.join(self.tmp, "alfile"), "w").close()

    def names(self, raw, **kw):
        return [i["name"] for i in km._dir_completions(raw, **kw)["items"]]

    def test_a_trailing_slash_lists_the_children(self):
        self.assertEqual(self.names(self.tmp + "/"), ["album", "alpha", "beta"])

    def test_a_fragment_narrows_by_prefix(self):
        self.assertEqual(self.names(os.path.join(self.tmp, "al")), ["album", "alpha"])

    def test_files_are_never_offered(self):
        # a session cwd is a directory; "alfile" matches the prefix and must still not appear
        self.assertNotIn("alfile", self.names(os.path.join(self.tmp, "al")))

    def test_hidden_directories_appear_only_once_the_dot_is_typed(self):
        self.assertNotIn(".hidden", self.names(self.tmp + "/"))
        self.assertEqual(self.names(os.path.join(self.tmp, ".")), [".hidden"])

    def test_matching_is_case_insensitive(self):
        self.assertEqual(self.names(os.path.join(self.tmp, "AL")), ["album", "alpha"])

    def test_the_reply_is_capped_and_says_so(self):
        big = os.path.join(self.tmp, "many")
        for i in range(8):
            os.makedirs(os.path.join(big, "d%d" % i))
        out = km._dir_completions(big + "/", limit=3)
        self.assertEqual(len(out["items"]), 3)
        self.assertTrue(out["truncated"])
        self.assertFalse(km._dir_completions(big + "/", limit=50)["truncated"])

    def test_an_unreadable_or_absent_base_answers_empty_rather_than_raising(self):
        out = km._dir_completions(os.path.join(self.tmp, "nothing-here", "x"))
        self.assertEqual(out["items"], [])
        self.assertFalse(out["truncated"])

    def test_paths_come_back_home_collapsed(self):
        out = km._dir_completions("~/")
        self.assertTrue(out["base"].startswith("~"), out["base"])
        for it in out["items"]:
            self.assertTrue(it["path"].startswith("~/"), it["path"])


class _Wire(_Dirs):
    """The two WS ops, driven through the real dispatcher with a fake client."""

    def setUp(self):
        super().setUp()
        self.sent = []
        self.client = {"app": "chat", "alive": True,
                       "send": lambda s: self.sent.append(json.loads(s))}
        self.handler = object.__new__(km.Handler)

    def send(self, msg):
        km.Handler._dispatch_ws(self.handler, msg, self.client)
        return self.sent[-1] if self.sent else None


class DirCompleteOp(_Wire):
    def test_the_reply_carries_the_completions_the_status_and_the_request_id(self):
        r = self.send({"type": "dirComplete", "value": self.tmp + "/", "reqId": 12})
        self.assertEqual(r["type"], "dirCompletions")
        self.assertEqual(r["reqId"], 12, "echoed so a late reply for an older keystroke can be dropped")
        self.assertEqual(r["value"], self.tmp + "/")
        self.assertIn("items", r)
        self.assertTrue(r["status"]["isDir"])


class CreateSessionDirFork(_Wire):
    def setUp(self):
        super().setUp()
        self.spawned = []
        self._real_sdk = km._create_sdk_session
        self._real_ready = km._sdk_ready
        km._create_sdk_session = lambda nm, cwd: self.spawned.append((nm, cwd)) or "TESTSID"
        km._sdk_ready = lambda: True
        self.addCleanup(setattr, km, "_create_sdk_session", self._real_sdk)
        self.addCleanup(setattr, km, "_sdk_ready", self._real_ready)

    def test_a_missing_directory_asks_instead_of_warning_into_the_void(self):
        target = os.path.join(self.tmp, "not", "yet")
        r = self.send({"type": "createSession", "name": "web", "dir": target, "backend": "sdk"})
        self.assertEqual(r["type"], "createDirMissing")
        self.assertEqual(r["name"], "web")
        self.assertTrue(r["status"]["canCreate"])
        self.assertEqual(r["status"]["missing"], 2)
        self.assertEqual(self.spawned, [], "nothing is created until the user answers")
        self.assertFalse(os.path.exists(target))

    def test_answering_create_makes_the_directory_and_starts_there(self):
        target = os.path.join(self.tmp, "not", "yet")
        self.send({"type": "createSession", "name": "web", "dir": target, "backend": "sdk", "mkdir": True})
        self.assertTrue(os.path.isdir(target))
        self.assertEqual(len(self.spawned), 1)
        self.assertEqual(os.path.realpath(self.spawned[0][1]), os.path.realpath(target))

    def test_a_file_in_the_way_stays_a_plain_warning_there_is_nothing_to_offer(self):
        f = os.path.join(self.tmp, "afile")
        open(f, "w").close()
        r = self.send({"type": "createSession", "name": "web", "dir": f, "backend": "sdk"})
        self.assertEqual(r["type"], "warn")
        self.assertIn("not a directory", r["text"])

    def test_a_good_directory_still_just_starts(self):
        self.send({"type": "createSession", "name": "web", "dir": self.tmp, "backend": "sdk"})
        self.assertEqual(len(self.spawned), 1)
        self.assertNotIn("createDirMissing", [m.get("type") for m in self.sent])


class HeadlessParity(unittest.TestCase):
    def test_the_new_route_can_create_the_directory_too(self):
        import inspect
        src = inspect.getsource(km.Handler)
        self.assertIn('_resolve_create_dir(b.get("dir"), create=bool(b.get("mkdir")))', src,
                      "`romp new` gets the same create-it answer the dashboard offers")
        self.assertIn('"dirStatus": _dir_status(b.get("dir"))', src,
                      "a headless caller is told WHY, in the same shape the picker reads")


if __name__ == "__main__":
    unittest.main()
