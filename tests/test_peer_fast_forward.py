#!/usr/bin/env python3
"""Getting a CHECKED-IN peer to fast-forward ITSELF (the user 2026-07-28).

A peer that checked in here owns the only ssh between the two machines, so this side cannot push to it.
That used to be a dead end that still ADVERTISED itself: the drift banner offered a push every few
seconds and _update_remote refused every one of them with "no ssh path". The route that exists is the
peer's own — it holds an ssh to us and its kernel already knows how to fetch a hub's HEAD and
fast-forward onto it — so romp drives that through the tunnel the peer keeps open (_ask_peer_to_pull),
and every surface offers it only when it is a PROVABLE fast-forward.

SYNTHETIC fixtures only — invented hosts and placeholder shas; every network call is stubbed.
"""
import json
import os
import unittest
from romp_load import load_source
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
km = load_source("romp_kernel_peerff", os.path.join(BIN, "romp-kernel"))

LOCAL = "a" * 40        # this machine's HEAD
REMOTE = "b" * 40       # the peer's older commit
PEER = "TESTHOST"


def _row(**over):
    r = {"host": PEER, "checkin_peer": True, "kernel_port": 52025, "local_port": 52025,
         "token": "peertok", "kernel_sha": REMOTE, "status": "up", "trust": "trusted"}
    r.update(over)
    return r


class _Calls(list):
    """Stands in for _peer_call: records (method, path, body) and replays scripted answers."""

    def __init__(self, answers):
        super().__init__()
        self.answers = list(answers)

    def __call__(self, r, method, path, body=None, timeout=8):
        self.append((method, path, body))
        return self.answers.pop(0) if self.answers else (0, {"error": "no scripted answer"})


class AskGate(unittest.TestCase):
    """_is_ask_pull decides whether the row may offer this in one click, and whether the supervisor may
    fire it. It must clear the SAME bar as the push gate — provable fast-forward, nothing less."""

    def _gate(self, behind, ahead, checkin=True, ood=True):
        saved = (km._remote_out_of_date, km._behind_info)
        km._remote_out_of_date = lambda r, head=None: ood
        km._behind_info = lambda sha, head=None: {"behind": behind, "ahead": ahead, "date": ""}
        try:
            return km._is_ask_pull(_row(checkin_peer=checkin))
        finally:
            km._remote_out_of_date, km._behind_info = saved

    def test_a_checked_in_peer_strictly_behind_can_be_asked(self):
        self.assertTrue(self._gate(behind=3, ahead=0), "it only ADDS commits over there")

    def test_an_ssh_attached_host_is_pushed_not_asked(self):
        self.assertFalse(self._gate(behind=3, ahead=0, checkin=False),
                         "we own the ssh to that one — the push direction still applies")

    def test_nothing_unprovable_is_ever_asked(self):
        self.assertFalse(self._gate(behind=0, ahead=2), "it has commits we lack")
        self.assertFalse(self._gate(behind=3, ahead=2), "diverged")
        self.assertFalse(self._gate(behind=None, ahead=None), "a build this repo has never seen")
        self.assertFalse(self._gate(behind=0, ahead=0, ood=False), "already on this build")

    def test_the_row_publishes_the_verdict(self):
        saved = (km._remote_out_of_date, km._behind_info)
        km._remote_out_of_date = lambda r, head=None: True
        km._behind_info = lambda sha, head=None: {"behind": 3, "ahead": 0, "date": "2026-07-28"}
        try:
            pub = km._remote_public(_row())
        finally:
            km._remote_out_of_date, km._behind_info = saved
        self.assertTrue(pub["askPull"], "the row can say the peer is askable")
        self.assertFalse(pub["fastPull"], "and that there is nothing here to pull")


class AskingThePeer(unittest.TestCase):
    """_ask_peer_to_pull: pull THEN restart, over the tunnel the peer holds — and a refusal comes back
    with the peer's own reason rather than a generic failure (CLAUDE.md: fail loudly, with the why)."""

    def setUp(self):
        self._saved = (km._peer_call, km._peer_hub_name, km._local_head, dict(km._remotes))
        km._peer_hub_name = lambda r: "hubname"
        km._local_head = lambda short=False: (LOCAL[:8] if short else LOCAL)
        km._remotes.clear()
        km._remotes[PEER] = _row()

    def tearDown(self):
        km._peer_call, km._peer_hub_name, km._local_head, saved_remotes = self._saved
        km._remotes.clear()
        km._remotes.update(saved_remotes)

    def _ask(self, answers):
        km._peer_call = calls = _Calls(answers)
        return km._ask_peer_to_pull(PEER), calls

    def test_it_pulls_then_restarts(self):
        (ok, detail), calls = self._ask([(200, {"ok": True, "detail": "pulled 8 commits from hubname"}),
                                         (200, {"ok": True, "restarting": True})])
        self.assertTrue(ok)
        self.assertEqual([c[1] for c in calls], ["/tunnels/pull", "/restart"],
                         "a pull alone leaves the OLD kernel running and still reporting the old sha")
        self.assertEqual(calls[0][2], {"host": "hubname"}, "the peer is handed the name it knows us by")
        self.assertEqual(calls[1][2], {"fleet": False},
                         "and told to restart ITSELF only — its /restart defaults to the broad kind, "
                         "which would fan back out onto this hub (tests/test_fleet_restart.py)")
        self.assertIn("pulled 8 commits", detail)
        self.assertIn("restarting it", detail)

    def test_a_pull_that_changed_no_kernel_code_asks_no_restart(self):
        """plans/drift-by-running-code.md: the peer's pull answer carries its own verdict on whether what it now holds
        changes what its process runs; a docs, tests or UI pull converges in place there, and a restart would only cut
        its turns and drop every pane's socket (the laptop kernel restarted once per merge on 2026-09-14)."""
        (ok, detail), calls = self._ask([(200, {"ok": True, "detail": "pulled 2 commits from hubname", "kernel_code_changed": False})])
        self.assertTrue(ok)
        self.assertEqual([c[1] for c in calls], ["/tunnels/pull"], "no restart asked")
        self.assertIn("no kernel code changed", detail)
        self.assertIn("keeps running", detail)

    def test_a_pull_that_changed_kernel_code_asks_the_restart(self):
        (ok, detail), calls = self._ask([(200, {"ok": True, "detail": "pulled 2 commits from hubname", "kernel_code_changed": True}),
                                         (200, {"ok": True, "restarting": True})])
        self.assertTrue(ok)
        self.assertEqual([c[1] for c in calls], ["/tunnels/pull", "/restart"])
        self.assertEqual(calls[1][2], {"fleet": False})
        self.assertIn("restarting it", detail)

    def test_a_peer_older_than_the_field_gets_the_hubs_own_reading_over_the_two_commits(self):
        saved = (km._kernel_code_changed, km._fresh_local_head)
        seen = []
        km._fresh_local_head = lambda: LOCAL
        try:
            km._kernel_code_changed = lambda a, b: seen.append((a, b)) or False
            (ok, detail), calls = self._ask([(200, {"ok": True, "detail": "pulled 2 commits from hubname"})])
            self.assertEqual([c[1] for c in calls], ["/tunnels/pull"], "the hub read the diff itself: no kernel code, no restart")
            self.assertEqual(seen, [(REMOTE, LOCAL)], "the peer's booted commit against this HEAD, both in this repository")
            km._kernel_code_changed = lambda a, b: True
            (ok, detail), calls = self._ask([(200, {"ok": True, "detail": "pulled 2 commits from hubname"}),
                                             (200, {"ok": True, "restarting": True})])
            self.assertEqual([c[1] for c in calls], ["/tunnels/pull", "/restart"], "kernel code changed by the hub's reading: the restart")
        finally:
            km._kernel_code_changed, km._fresh_local_head = saved

    def test_the_restart_sweep_asks_the_restart_whatever_the_pull_changed(self):
        # the rail's Restart is a restart the user asked for: the verdict decides nothing there
        km._peer_call = calls = _Calls([(200, {"ok": True, "detail": "already up to date", "kernel_code_changed": False}),
                                        (200, {"ok": True, "restarting": True})])
        ok, detail = km._ask_peer_to_pull(PEER, restart="always")
        self.assertTrue(ok)
        self.assertEqual([c[1] for c in calls], ["/tunnels/pull", "/restart"])

    def test_the_peer_s_own_refusal_is_passed_through(self):
        (ok, detail), calls = self._ask([(502, {"ok": False, "detail": "this machine's tree has "
                                                "uncommitted changes — commit or stash them first"})])
        self.assertFalse(ok)
        self.assertIn("uncommitted changes", detail, "the reason it refused, not a generic failure")
        self.assertEqual(len(calls), 1, "a refused pull is never followed by a restart")

    def test_an_unreachable_peer_kernel_says_so(self):
        (ok, detail), _ = self._ask([(0, {"error": "connection refused"})])
        self.assertFalse(ok)
        self.assertIn("connection refused", detail)

    def test_a_peer_too_old_to_have_the_route_names_the_fix(self):
        (ok, detail), _ = self._ask([(404, {})])
        self.assertFalse(ok)
        self.assertIn("too old", detail)
        self.assertIn("by hand", detail, "one manual update there breaks the chicken-and-egg")

    def test_a_pull_that_lands_but_a_restart_that_does_not_still_reports_the_commits(self):
        (ok, detail), _ = self._ask([(200, {"ok": True, "detail": "pulled 2 commits"}), (0, {"error": "gone"})])
        self.assertTrue(ok, "the commits DID land — that is not a failure")
        self.assertIn("restart romp on %s" % PEER, detail, "and it says what is left to do")
        self.assertIn("gone", detail, "and why the restart never acked, in _peer_call's own words")

    def test_a_restart_the_peer_refuses_comes_back_with_its_reason(self):
        """The peer's /restart refuses a body it cannot take with a 400 naming why (it no longer
        takes a malformed one as the broad default). This function was that text's only reader and
        it discarded it, leaving "did not ack" with no why (review find, 2026-09-08)."""
        (ok, detail), calls = self._ask([(200, {"ok": True, "detail": "pulled 2 commits"}),
                                         (400, {"ok": False, "error": "body is not JSON"})])
        self.assertTrue(ok, "the commits DID land")
        self.assertEqual(len(calls), 2)
        self.assertIn("did not ack the restart", detail)
        self.assertIn("body is not JSON", detail, "the peer's own words, not a bare 'did not ack'")
        self.assertIn("restart romp on %s" % PEER, detail)

    def test_an_ssh_attached_host_is_refused_with_the_direction_that_works(self):
        km._remotes[PEER] = _row(checkin_peer=False)
        (ok, detail), calls = self._ask([])
        self.assertFalse(ok)
        self.assertIn("push to it instead", detail)
        self.assertEqual(calls, [], "nothing is sent to a host we can reach directly")

    def test_a_peer_with_no_token_or_forward_is_refused_before_the_network(self):
        km._remotes[PEER] = _row(token="")
        (ok, detail), calls = self._ask([])
        self.assertFalse(ok)
        self.assertIn("no admin path", detail)
        self.assertEqual(calls, [])


class NamingThisMachine(unittest.TestCase):
    """_peer_hub_name: the ssh destination the peer must be handed is read from the PEER's own tunnel
    list — its real alias for us — not guessed from our hostname (which need not match)."""

    def setUp(self):
        self._saved = (km._peer_call, km._kernel_sha)
        km._kernel_sha = lambda: "abc1234"
        os.environ["ROMP_HOST_NAME"] = "myhostname"

    def tearDown(self):
        km._peer_call, km._kernel_sha = self._saved
        os.environ.pop("ROMP_HOST_NAME", None)

    def test_it_reads_the_alias_the_peer_actually_uses(self):
        km._peer_call = lambda r, m, p, body=None, timeout=8: (200, {"tunnels": [
            {"host": "some-other-hub", "checkin": False, "kernelSha": "999999"},
            {"host": "linux-box-alias", "checkin": True, "kernelSha": "abc1234"},
        ]})
        self.assertEqual(km._peer_hub_name(_row()), "linux-box-alias")

    def test_a_lone_check_in_row_is_us_whatever_the_sha_says(self):
        # its sha of us is the last one it polled; a build that moved since must not lose the alias
        km._peer_call = lambda r, m, p, body=None, timeout=8: (200, {"tunnels": [
            {"host": "linux-box-alias", "checkin": True, "kernelSha": "0000000"}]})
        self.assertEqual(km._peer_hub_name(_row()), "linux-box-alias")

    def test_an_unusable_answer_falls_back_to_our_own_name(self):
        for answer in ((0, {"error": "no route"}), (200, {"tunnels": []}),
                       (200, {"tunnels": [{"host": "a", "checkin": True, "kernelSha": "1"},
                                          {"host": "b", "checkin": True, "kernelSha": "2"}]})):
            km._peer_call = lambda r, m, p, body=None, timeout=8, a=answer: a
            self.assertEqual(km._peer_hub_name(_row()), "myhostname",
                             "ambiguity degrades to today's identity, never to a wrong host")


class PhaseIsPublished(unittest.TestCase):
    """The ask announces itself on the row exactly like the push and pull it stands in for."""

    def setUp(self):
        self._saved = km._ask_peer_to_pull
        km._auto_push.clear()

    def tearDown(self):
        km._ask_peer_to_pull = self._saved
        km._auto_push.clear()

    def test_success_parks_at_waiting_for_the_restart(self):
        km._ask_peer_to_pull = lambda h: (True, "pulled 8 commits; restarting it")
        self.assertTrue(km._auto_ask_peer(PEER))
        st = km._auto_push_state(PEER)
        self.assertEqual(st["phase"], "waiting")
        self.assertIn("restarting it", st["detail"])

    def test_a_failure_stays_visible_and_carries_the_reason(self):
        km._ask_peer_to_pull = lambda h: (False, "TESTHOST refused: its tree has uncommitted changes")
        self.assertFalse(km._auto_ask_peer(PEER))
        st = km._auto_push_state(PEER)
        self.assertEqual(st["phase"], "failed")
        self.assertIn("uncommitted changes", st["detail"], "a silent failure looks like an up-to-date host")

    def test_a_raising_ask_is_reported_not_swallowed(self):
        def _boom(h):
            raise RuntimeError("tunnel died")
        km._ask_peer_to_pull = _boom
        self.assertFalse(km._auto_ask_peer(PEER))
        self.assertEqual(km._auto_push_state(PEER)["phase"], "failed")


class SurfacesOnlyOfferWhatCanWork(unittest.TestCase):
    """Source pins on both row copies and on the mid-screen drift banner — the surface that was making
    the impossible offer over and over."""

    def setUp(self):
        self.strip = open(os.path.join(os.path.dirname(HERE), "ui", "webview", "strip.ts")).read()

    def test_the_banner_raises_only_a_host_romp_can_move(self):
        self.assertIn("(t.fastForward&&!t.checkinPeer)||t.askPull", km._RDRIFT_JS,
                      "no prompt for a drift with no working route — that was the every-4s dead end")

    def test_the_banner_sends_each_host_down_the_route_that_works(self):
        self.assertIn("route[t.host]=t.askPull?'/tunnels/askpull':'/tunnels/update'", km._RDRIFT_JS)
        self.assertIn("fetch(route[h]||'/tunnels/update'", km._RDRIFT_JS)

    def test_the_web_row_offers_update_to_a_checked_in_peer(self):
        self.assertIn("t.status==='up'&&t.askPull&&!apx", km._LANDING_REMOTES_JS)
        self.assertIn("/tunnels/askpull", km._LANDING_REMOTES_JS)
        self.assertIn("data-a=", km._LANDING_REMOTES_JS)

    def test_the_strip_row_matches(self):
        self.assertIn('t.status === "up" && t.askPull && !apx', self.strip)
        self.assertIn('act("/tunnels/askpull", t.host, a, "Asking…")', self.strip)
        self.assertIn('t.status === "up" && t.fastForward && !apx && !t.checkinPeer', self.strip)

    def test_an_ask_in_flight_counts_as_busy_in_both_copies(self):
        self.assertIn("t.autoPush.phase==='asking'", km._LANDING_REMOTES_JS)
        self.assertIn('t.autoPush.phase === "asking"', self.strip)

    def test_the_route_is_wired(self):
        src = open(os.path.join(os.path.dirname(HERE), "kernel", "kernel.py")).read()
        self.assertIn('u.path == "/tunnels/askpull"', src)
        self.assertIn("ok, detail = _ask_peer_to_pull(host)", src)

    def test_the_push_refusal_points_at_the_action_that_exists(self):
        km._remotes[PEER] = _row()
        try:
            ok, detail = km._update_remote(PEER)
        finally:
            km._remotes.pop(PEER, None)
        self.assertFalse(ok)
        self.assertIn("Update asks it to fast-forward itself", detail)


class DriftOnTheCheckout(unittest.TestCase):
    """plans/drift-by-running-code.md: a remote is behind by its CHECKOUT, not by the commit its kernel booted from; whether
    it runs older kernel code is a separate fact with its own offer. A peer that pulled a docs commit and, rightly, did
    not restart used to read "behind 1 commit" forever and be asked again on every pass."""

    def setUp(self):
        self._saved = (km._local_head, km._behind_info)
        km._local_head = lambda short=False: (LOCAL[:8] if short else LOCAL)
        km._behind_info = lambda sha, head=None: {"behind": 1, "ahead": 0, "date": ""}

    def tearDown(self):
        km._local_head, km._behind_info = self._saved

    def test_a_peer_whose_checkout_matches_is_not_behind_whatever_it_booted_from(self):
        row = {"host": PEER, "kernel_sha": REMOTE[:8], "checkout_sha": LOCAL[:8]}
        self.assertFalse(km._remote_out_of_date(row))
        self.assertFalse(km._is_fast_forward(row))
        self.assertEqual(km._drift_sha(row), LOCAL[:8])

    def test_a_row_without_a_checkout_sha_reads_the_booted_commit_as_before(self):
        row = {"host": PEER, "kernel_sha": REMOTE[:8]}
        self.assertTrue(km._remote_out_of_date(row))
        self.assertEqual(km._drift_sha(row), REMOTE[:8])

    def test_the_row_says_which_and_offers_the_ask_for_a_peer_running_older_code(self):
        pub = km._remote_public(_row(kernel_sha=REMOTE[:8], checkout_sha=LOCAL[:8], restart_pending=True))
        self.assertFalse(pub["outOfDate"], "its checkout matches: not behind")
        self.assertTrue(pub["restartPending"], "but its process runs older kernel code")
        self.assertEqual(pub["checkoutSha"], LOCAL[:8])
        self.assertTrue(pub["askPull"], "the ask is offered: the peer's answer calls for the restart it needs")
        quiet = km._remote_public(_row(kernel_sha=LOCAL[:8], checkout_sha=LOCAL[:8], restart_pending=False))
        self.assertFalse(quiet["restartPending"]); self.assertFalse(quiet["askPull"])

    def test_version_carries_the_checkout_and_the_pending_verdict(self):
        saved = (km._kernel_sha, km._kernel_code_changed)
        km._RESTART_PENDING_MEMO.clear()
        try:
            km._kernel_sha = lambda reask=False: REMOTE[:8]
            km._kernel_code_changed = lambda a, b: True
            v = km._version_info()
            self.assertEqual(v["checkout_sha"], LOCAL[:8])
            self.assertTrue(v["restart_pending"], "the checkout holds kernel code this process does not run")
            km._kernel_code_changed = lambda a, b: (_ for _ in ()).throw(AssertionError("memoized: not asked again"))
            self.assertTrue(km._restart_pending())
            km._kernel_sha = lambda reask=False: LOCAL[:8]
            self.assertFalse(km._restart_pending(), "one commit booted and checked out: nothing pending")
            km._kernel_sha = lambda reask=False: None
            self.assertIsNone(km._restart_pending(), "no claim when the booted commit cannot be read")
        finally:
            km._kernel_sha, km._kernel_code_changed = saved
            km._RESTART_PENDING_MEMO.clear()

    def test_a_classification_that_failed_is_answered_safe_and_never_latched(self):
        """The round-two review's medium: _kernel_code_changed reads True on any error by design, and the memo stored that
        True for the pair, so one git flake right after a pull made a docs-only checkout report a restart pending on
        every poll. Only a verdict that was read is kept; a failed read answers True for that call alone."""
        saved = (km._kernel_sha, km._converge_classes)
        km._RESTART_PENDING_MEMO.clear()
        try:
            km._kernel_sha = lambda reask=False: REMOTE[:8]
            km._converge_classes = lambda a, b: None                        # the flake
            self.assertTrue(km._restart_pending(), "unreadable this time: the safe answer")
            self.assertEqual(km._RESTART_PENDING_MEMO, {}, "and nothing remembered")
            km._converge_classes = lambda a, b: {"kernel": [], "bus": [], "skip": ["docs/a.md"], "ast_equal": []}
            self.assertFalse(km._restart_pending(), "the next read judges again: a docs-only pair, nothing pending")
            self.assertEqual(km._RESTART_PENDING_MEMO, {(REMOTE[:8], LOCAL[:8]): False}, "a verdict that was read is kept")
            km._converge_classes = lambda a, b: None
            self.assertFalse(km._restart_pending(), "and the kept verdict answers, not the later flake")
        finally:
            km._kernel_sha, km._converge_classes = saved
            km._RESTART_PENDING_MEMO.clear()

    def test_the_pull_route_answers_with_the_peers_verdict_read_on_the_fresh_head(self):
        """The route driven: POST /tunnels/pull on a live handler with the pull itself stubbed. Its answer carries the
        peer's verdict on the head the pull just moved, read fresh (the round-two review's low 4: the polls' 15 s cache
        would still name the head before the fast-forward)."""
        import http.client, threading
        from http.server import ThreadingHTTPServer
        FRESH = "c" * 40
        saved = (km._pull_remote, km._kernel_sha, km._local_head, km._fresh_local_head, km._converge_classes)
        judged = []
        km._RESTART_PENDING_MEMO.clear()
        srv = ThreadingHTTPServer(("127.0.0.1", 0), km.Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            km._pull_remote = lambda host: (True, "pulled 1 commit from %s" % host)
            km._kernel_sha = lambda reask=False: LOCAL[:8]                       # booted at LOCAL
            km._local_head = lambda short=False: (LOCAL[:8] if short else LOCAL)   # the polls' cache still says LOCAL
            km._fresh_local_head = lambda: FRESH                                  # the fast-forward moved the checkout
            km._converge_classes = lambda a, b: judged.append((a, b)) or {"kernel": ["kernel/kernel.py"], "bus": [], "skip": [], "ast_equal": []}
            c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
            c.request("POST", "/tunnels/pull", json.dumps({"host": "hubname"}).encode(),
                      {"Content-Type": "application/json", "X-Romp-Token": km.TOKEN})
            resp = c.getresponse(); body = json.loads(resp.read().decode()); c.close()
            self.assertEqual(resp.status, 200)
            self.assertTrue(body["ok"]); self.assertIn("pulled 1 commit", body["detail"])
            self.assertIs(body["kernel_code_changed"], True, "the peer's own verdict rides the answer")
            self.assertEqual(judged, [(LOCAL[:8], FRESH[:8] if False else km._sha_base(FRESH))],
                             "judged against the head the pull moved, not the cached one")
            km._RESTART_PENDING_MEMO.clear()
            km._converge_classes = lambda a, b: {"kernel": [], "bus": [], "skip": ["docs/x.md"], "ast_equal": []}
            c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
            c.request("POST", "/tunnels/pull", json.dumps({"host": "hubname"}).encode(),
                      {"Content-Type": "application/json", "X-Romp-Token": km.TOKEN})
            resp = c.getresponse(); body = json.loads(resp.read().decode()); c.close()
            self.assertIs(body["kernel_code_changed"], False, "a docs-only pull: no restart asked for")
            km._pull_remote = lambda host: (False, "this machine's tree has uncommitted changes")
            c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
            c.request("POST", "/tunnels/pull", json.dumps({"host": "hubname"}).encode(),
                      {"Content-Type": "application/json", "X-Romp-Token": km.TOKEN})
            resp = c.getresponse(); body = json.loads(resp.read().decode()); c.close()
            self.assertEqual(resp.status, 502); self.assertIsNone(body["kernel_code_changed"], "a refused pull claims nothing")
        finally:
            srv.shutdown(); srv.server_close()
            km._pull_remote, km._kernel_sha, km._local_head, km._fresh_local_head, km._converge_classes = saved
            km._RESTART_PENDING_MEMO.clear()


if __name__ == "__main__":
    unittest.main()
