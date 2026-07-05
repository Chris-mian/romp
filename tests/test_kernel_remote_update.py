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
        self._hc = dict(km._HEAD_CACHE)
        km._HEAD_CACHE.update(ts=9e18, full="abc12340000", short="abc1234")   # pin local HEAD, skip the subprocess

    def tearDown(self):
        km._HEAD_CACHE.clear(); km._HEAD_CACHE.update(self._hc)

    def test_sha_base_strips_dirty(self):
        self.assertEqual(km._sha_base("abc1234-dirty"), "abc1234")
        self.assertEqual(km._sha_base("abc1234"), "abc1234")
        self.assertIsNone(km._sha_base(""))
        self.assertIsNone(km._sha_base(None))

    def test_shas_agree_tolerates_different_short_lengths(self):
        self.assertTrue(km._shas_agree("abc1234", "abc1234567"), "one a prefix of the other → same commit")
        self.assertTrue(km._shas_agree("abc1234-dirty", "abc1234"), "'-dirty' ignored")
        self.assertFalse(km._shas_agree("abc1234", "def5678"))
        self.assertFalse(km._shas_agree("abc1234", ""))

    def test_drift_is_measured_against_live_HEAD_and_CLEARS_when_matched(self):
        # the fix (the user 2026-07-04): drift compares the remote to the LIVE HEAD — the SAME thing the push
        # sends — so once the remote is pushed to HEAD the flag goes away (it used to compare to the kernel's
        # cached startup sha while the push sent HEAD, so it never reconciled → banner stuck forever).
        self.assertTrue(km._remote_out_of_date({"kernel_sha": "def5678"}), "different commit → out of date")
        self.assertFalse(km._remote_out_of_date({"kernel_sha": "abc1234"}), "remote pushed to HEAD → CLEARS")
        self.assertFalse(km._remote_out_of_date({"kernel_sha": "abc12345"}), "same commit, longer short → clears")
        self.assertFalse(km._remote_out_of_date({}), "unknown remote sha → not flagged")
        self.assertFalse(km._remote_out_of_date({"kernel_sha": ""}), "blank remote sha → not flagged")

    def test_remote_public_exposes_version_fields(self):
        pub = km._remote_public({"host": "jetty", "kernel_port": 7433, "local_port": 8801, "token": "t",
                                 "status": "up", "sids": [], "kernel_sha": "def5678"})
        self.assertEqual(pub["kernelSha"], "def5678")
        self.assertEqual(pub["localSha"], "abc1234", "localSha is the live HEAD short (what a push would send)")
        self.assertTrue(pub["outOfDate"])


class UpdateRemote(unittest.TestCase):
    """PEER-TO-PEER update (the user 2026-07-04): push local committed HEAD to the remote (no GitHub), refuse on
    a dirty/diverged remote, restart. Three subprocess calls — ssh-discover, git-push, ssh-apply — are dispatched
    by inspecting argv so each case can drive them independently."""
    LFULL = "1" * 40                        # local HEAD (full sha) the push sends
    RHEAD = "2" * 40                         # a remote at a DIFFERENT (older) commit

    def setUp(self):
        self._run, self._hc = km.subprocess.run, dict(km._HEAD_CACHE)
        km._HEAD_CACHE.update(ts=0.0, full=None, short=None)   # force _local_head to consult the mocked git

    def tearDown(self):
        km.subprocess.run = self._run
        km._HEAD_CACHE.clear(); km._HEAD_CACHE.update(self._hc)

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

    def test_a_dirty_local_is_not_refused_it_pushes_committed_head(self):
        # "just take what is committed on local" (the user 2026-07-04): a dirty working tree is NOT a blocker —
        # _update_remote pushes the committed HEAD and never asks you to commit first.
        self._wire(apply_out="SYNCED:abcdef0")
        ok, detail = km._update_remote("jetty")
        self.assertTrue(ok)
        self.assertNotIn("commit", detail.lower())

    def test_no_local_checkout_fails_cleanly(self):
        def fake(argv, **kw):
            if argv[0] == "git" and "rev-parse" in argv:
                return _R(rc=1)                            # not a git checkout
            return _R()
        km.subprocess.run = fake
        km._HEAD_CACHE.update(ts=0.0, full=None, short=None)
        ok, detail = km._update_remote("jetty")
        self.assertFalse(ok)
        self.assertIn("git checkout", detail)

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

    def test_restart_goes_through_the_manager_then_falls_back(self):
        # the user 2026-07-04: the restart should keep the remote MANAGER-owned (romp's durable supervisor, no
        # orphan) — kill the kernel, `romp-manager ensure` (respawns via a live manager, or STARTS one that spawns
        # a supervised kernel — upgrading an attach-bootstrapped bare host), then port-poll; bare romp-serve is a
        # LAST-RESORT fallback only when the port never returns. It must NOT rely on `romp --refresh` (the stuck bug).
        km._remotes = {"jetty": {"host": "jetty", "kernel_port": 7433}}
        calls = self._wire()
        km._update_remote("jetty")
        apply = next(a[-1] for a in calls if isinstance(a[-1], str) and "merge-base" in a[-1])
        self.assertIn("pkill -f", apply, "kills the running kernel")
        self.assertIn('"$R/bin/romp-manager" ensure', apply, "prefers the manager (ensure = idempotent supervised start)")
        self.assertIn("/dev/tcp/127.0.0.1/7433", apply, "polls the remote's kernel port to confirm it came back")
        self.assertIn('if [ "$UP" = 0 ]; then nohup "$R/bin/romp-serve"', apply, "bare romp-serve only as a last resort")
        self.assertNotIn("--refresh", apply, "does NOT rely on `romp --refresh` (needs a manager) — the stuck bug")


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
    def test_drift_banner_uses_the_push_framing(self):
        # mirrors the #rstale reload banner, but asks to PUSH the local build (the user 2026-07-04)
        self.assertIn("id=rdrift", km._RDRIFT_HTML)
        self.assertIn(">Push<", km._RDRIFT_HTML, "the action button says Push")
        self.assertIn("Push your version", km._RDRIFT_JS, "the prompt asks to push your version to the remote")
        self.assertIn("/tunnels/update", km._RDRIFT_JS)
        self.assertIn("outOfDate", km._RDRIFT_JS)
        self.assertIn("_rdrift_block()", inspect_src())

    def test_drift_banner_shows_live_progress_success_and_failure(self):
        # the user 2026-07-04: the banner must stay up through the push with a spinner + status, a success
        # confirmation, and a persistent actionable error — not silently flip back to the prompt.
        self.assertIn("rd-spin", km._RDRIFT_HTML)
        self.assertIn("romp-swirl-glyph.svg", km._RDRIFT_CSS)   # the spinner is the romp loader glyph
        self.assertIn("Pushing your build", km._RDRIFT_JS, "a 'pushing…' progress message")
        self.assertIn("waiting for", km._RDRIFT_JS, "a 'waiting for it to restart' verify phase")
        self.assertIn("Up to date", km._RDRIFT_JS, "a success confirmation")
        self.assertIn("Push failed", km._RDRIFT_JS, "a persistent, specific failure message")
        self.assertIn("phase", km._RDRIFT_JS, "a state machine drives the flow")

    def test_popover_shows_behind_and_a_push_button(self):
        self.assertIn("behind", km._LANDING_REMOTES_JS)
        self.assertIn(">Push</button>", km._LANDING_REMOTES_JS)
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
