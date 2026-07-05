"""Remote version-drift detection + `romp update` (the user 2026-07-04): the local kernel polls each attached
remote's /version, flags one running an OLDER commit (outOfDate), and offers to pull+restart it behind the
scenes. `POST /tunnels/update` runs the ssh git-pull + restart; the rail popover + a top banner surface it.
SYNTHETIC hosts; subprocess/http are stubbed so nothing actually launches or connects."""
import json
import os
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()


class _R:
    def __init__(self, out="", err="", rc=0):
        self.stdout, self.stderr, self.returncode = out, err, rc


class VersionDrift(unittest.TestCase):
    def setUp(self):
        self._sha = km._SHA
        km._SHA = "abc1234"     # pin THIS kernel's sha

    def tearDown(self):
        km._SHA = self._sha

    def test_sha_base_strips_dirty(self):
        self.assertEqual(km._sha_base("abc1234-dirty"), "abc1234")
        self.assertEqual(km._sha_base("abc1234"), "abc1234")
        self.assertIsNone(km._sha_base(""))
        self.assertIsNone(km._sha_base(None))

    def test_out_of_date_only_on_a_different_commit(self):
        self.assertTrue(km._remote_out_of_date({"kernel_sha": "def5678"}), "a different commit → out of date")
        self.assertFalse(km._remote_out_of_date({"kernel_sha": "abc1234"}), "same commit → current")
        # a LOCALLY-dirty tree on the same commit must NOT read as drift (the '-dirty' is ignored)
        km._SHA = "abc1234-dirty"
        self.assertFalse(km._remote_out_of_date({"kernel_sha": "abc1234"}), "same commit, local dirty → current")
        km._SHA = "abc1234"
        self.assertFalse(km._remote_out_of_date({}), "unknown remote sha → not flagged (no false prompt)")
        self.assertFalse(km._remote_out_of_date({"kernel_sha": ""}), "blank remote sha → not flagged")

    def test_remote_public_exposes_version_fields(self):
        pub = km._remote_public({"host": "jetty", "kernel_port": 7433, "local_port": 8801, "token": "t",
                                 "status": "up", "sids": [], "kernel_sha": "def5678"})
        self.assertEqual(pub["kernelSha"], "def5678")
        self.assertEqual(pub["localSha"], "abc1234")
        self.assertTrue(pub["outOfDate"])


class UpdateRemote(unittest.TestCase):
    """PEER-TO-PEER update (the user 2026-07-04): push local committed HEAD to the remote (no GitHub), refuse on
    a dirty/diverged remote, restart. Three subprocess calls — ssh-discover, git-push, ssh-apply — are dispatched
    by inspecting argv so each case can drive them independently."""
    LFULL = "1" * 40                        # local HEAD (full sha) the push sends
    RHEAD = "2" * 40                         # a remote at a DIFFERENT (older) commit

    def setUp(self):
        self._run, self._sha = km.subprocess.run, km._SHA
        km._SHA = "1111111"                  # a CLEAN local short sha (so _kernel_sha doesn't subprocess)

    def tearDown(self):
        km.subprocess.run, km._SHA = self._run, self._sha

    def _wire(self, rhead=None, dirty="", disc_out=None, push_rc=0, push_err="", apply_out="SYNCED:abcdef0"):
        """Install a dispatching subprocess mock; returns the list of argv it saw."""
        if disc_out is None:
            disc_out = "DIR:/home/u/romp\nHEAD:%s\nDIRTY:%s" % (rhead if rhead is not None else self.RHEAD, dirty)
        calls = []

        def fake(argv, **kw):
            calls.append(argv)
            if argv[0] == "git" and "push" in argv:
                return _R(err=push_err, rc=push_rc)
            if argv[0] == "git" and "rev-parse" in argv and "HEAD" in argv:   # _local_head
                return _R(out=self.LFULL)
            cmd = argv[-1]                                                     # ssh: dispatch on the remote command
            if "for d in" in cmd:
                return _R(out=disc_out)
            if "merge-base" in cmd or "reset --hard" in cmd:
                return _R(out=apply_out)
            return _R()
        km.subprocess.run = fake
        return calls

    def test_no_host_is_a_no_op(self):
        self.assertEqual(km._update_remote(""), (False, "no host"))

    def test_a_clean_ancestor_remote_is_pushed_reset_and_restarted(self):
        calls = self._wire(apply_out="SYNCED:abcdef0")
        ok, detail = km._update_remote("jetty")
        self.assertTrue(ok)
        self.assertIn("synced to abcdef0", detail)
        # it force-pushed local HEAD to a scratch ref at host:remote-dir
        push = next(a for a in calls if a[0] == "git" and "push" in a)
        self.assertIn("--force", push)
        self.assertIn("jetty:/home/u/romp", push)
        self.assertTrue(any(str(x).startswith("HEAD:refs/heads/") for x in push), "pushes HEAD to a scratch ref")

    def test_already_up_to_date_short_circuits(self):
        self._wire(rhead=self.LFULL)          # remote already at local HEAD
        ok, detail = km._update_remote("jetty")
        self.assertTrue(ok)
        self.assertIn("already up to date", detail)

    def test_refuses_when_the_local_tree_is_dirty(self):
        km._SHA = "1111111-dirty"
        ok, detail = km._update_remote("jetty")
        self.assertFalse(ok)
        self.assertIn("commit your local changes first", detail)

    def test_refuses_a_dirty_remote_without_clobbering(self):
        self._wire(dirty="M")
        ok, detail = km._update_remote("jetty")
        self.assertFalse(ok)
        self.assertIn("uncommitted changes", detail)

    def test_refuses_a_diverged_remote(self):
        self._wire(apply_out="DIVERGED")
        ok, detail = km._update_remote("jetty")
        self.assertFalse(ok)
        self.assertIn("diverged", detail)

    def test_no_romp_clone_fails_loudly(self):
        self._wire(disc_out="NOROMP")
        ok, detail = km._update_remote("jetty")
        self.assertFalse(ok)
        self.assertIn("not installed", detail)

    def test_a_failed_push_surfaces_the_git_error(self):
        self._wire(push_rc=1, push_err="Permission denied (publickey)")
        ok, detail = km._update_remote("jetty")
        self.assertFalse(ok)
        self.assertIn("git push", detail)
        self.assertIn("Permission denied", detail)

    def test_no_github_origin_in_the_remote_commands(self):
        # peer-to-peer: NOTHING should pull from origin / touch GitHub
        calls = self._wire()
        km._update_remote("jetty")
        for a in calls:
            cmd = a[-1] if isinstance(a[-1], str) else ""
            self.assertNotIn("git pull", cmd, "no pull-from-origin anywhere")
            self.assertNotIn("origin", cmd)


class UpdateEndpoint(unittest.TestCase):
    def test_post_tunnels_update_calls_update_remote_and_reports(self):
        import inspect
        src = inspect.getsource(km)
        self.assertIn('if u.path == "/tunnels/update":', src)
        self.assertIn("ok, detail = _update_remote(host)", src)
        self.assertIn('json.dumps({"ok": ok, "detail": detail})', src)
        # a failed update returns a non-2xx so the CLI/banner can tell (fail loudly)
        self.assertIn("200 if ok else 502", src)

    def test_supervisor_polls_the_remote_version(self):
        import inspect
        src = inspect.getsource(km._tunnel_supervisor)
        self.assertIn("_poll_remote_version(r)", src)
        self.assertIn('r["kernel_sha"] = rsha', src)


class UpdateUI(unittest.TestCase):
    def test_drift_banner_is_injected_and_offers_update(self):
        self.assertIn("id=rdrift", km._RDRIFT_HTML)
        self.assertIn("/tunnels/update", km._RDRIFT_JS)
        self.assertIn("outOfDate", km._RDRIFT_JS)
        self.assertIn("_rdrift_block()", inspect_src())

    def test_popover_shows_update_available_and_an_update_button(self):
        self.assertIn("update available", km._LANDING_REMOTES_JS)
        self.assertIn("/tunnels/update", km._LANDING_REMOTES_JS)
        self.assertIn("data-u=", km._LANDING_REMOTES_JS)


ru = SourceFileLoader("romp_update", os.path.join(BIN, "romp-update")).load_module()


class RompUpdateCLI(unittest.TestCase):
    def setUp(self):
        self._k, self._g, self._p = ru._kernel, ru._get, ru._post
        ru._kernel = lambda: "http://127.0.0.1:7433"
        self.posted = []
        ru._post = lambda u, path, body: (self.posted.append((path, body)) or {"ok": True, "detail": "updated"})

    def tearDown(self):
        ru._kernel, ru._get, ru._post = self._k, self._g, self._p

    def test_dispatch_routes_update_in_the_bash_cli(self):
        src = open(os.path.join(BIN, "romp")).read()
        self.assertIn('"${1:-}" == "update" || "${1:-}" == "--update"', src, "both `update` and `--update` route")
        self.assertIn("exec romp-update", src)

    def test_no_kernel_errors_cleanly(self):
        ru._kernel = lambda: None
        self.assertEqual(ru.main([]), 2)

    def test_named_host_updates_that_remote(self):
        self.assertEqual(ru.main(["jetty"]), 0)
        self.assertEqual(self.posted, [("/tunnels/update", {"host": "jetty"})])

    def test_no_arg_updates_only_out_of_date_remotes(self):
        ru._get = lambda u, path: {"tunnels": [{"host": "jetty", "outOfDate": True},
                                               {"host": "gpu1", "outOfDate": False}]}
        self.assertEqual(ru.main([]), 0)
        self.assertEqual(self.posted, [("/tunnels/update", {"host": "jetty"})], "only the stale remote is updated")

    def test_no_arg_all_current_updates_nothing(self):
        ru._get = lambda u, path: {"tunnels": [{"host": "gpu1", "outOfDate": False}]}
        self.assertEqual(ru.main([]), 0)
        self.assertEqual(self.posted, [], "nothing to do when every remote is current")

    def test_a_failed_update_returns_nonzero(self):
        ru._post = lambda u, path, body: {"ok": False, "detail": "git pull failed"}
        self.assertEqual(ru.main(["jetty"]), 1)


def inspect_src():
    import inspect
    return inspect.getsource(km)


if __name__ == "__main__":
    unittest.main()
