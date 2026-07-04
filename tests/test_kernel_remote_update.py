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
    def setUp(self):
        self._run = km.subprocess.run

    def tearDown(self):
        km.subprocess.run = self._run

    def _mock(self, out="", err="", rc=0):
        km.subprocess.run = lambda argv, **kw: _R(out, err, rc)

    def test_no_host_is_a_no_op(self):
        self.assertEqual(km._update_remote(""), (False, "no host"))

    def test_a_successful_pull_reports_the_git_summary(self):
        self._mock(out="UPDATED:Updating a1b2c3d..e4f5g6h\n 3 files changed, 40 insertions(+)")
        ok, detail = km._update_remote("jetty")
        self.assertTrue(ok)
        self.assertIn("3 files changed", detail)

    def test_already_up_to_date_is_success_no_restart(self):
        self._mock(out="NOCHANGE:Already up to date.")
        self.assertEqual(km._update_remote("jetty"), (True, "already up to date"))

    def test_no_romp_clone_fails_loudly(self):
        self._mock(out="NOROMP")
        ok, detail = km._update_remote("jetty")
        self.assertFalse(ok)
        self.assertIn("not installed", detail)

    def test_a_pull_conflict_surfaces_the_git_error(self):
        self._mock(out="PULLFAIL:error: Your local changes would be overwritten by merge")
        ok, detail = km._update_remote("jetty")
        self.assertFalse(ok)
        self.assertIn("git pull failed", detail)
        self.assertIn("overwritten", detail)

    def test_uses_ff_only_and_the_conventional_dir_search(self):
        # the remote command must never MERGE/REBASE (ff-only), and must look in the same dirs _start_remote_kernel does
        captured = {}
        km.subprocess.run = lambda argv, **kw: captured.setdefault("argv", argv) or _R(out="NOCHANGE:Already up to date.")
        km._update_remote("jetty")
        cmd = captured["argv"][-1]
        self.assertIn("git pull --ff-only", cmd)
        self.assertIn("$HOME/GitRepos/romp", cmd)
        self.assertIn("--refresh", cmd, "restarts the remote kernel after pulling")


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
