"""One set of usage bars per Claude ACCOUNT (the user 2026-07-30).

The 5h / 7d windows are account-wide, so a fleet signed into one login has ONE allowance and drawing it
per host would just repeat the same number — that case renders exactly as it always did, a single bare
set. But sign a second machine into a DIFFERENT account and the single set was flatly wrong: two
independent allowances, shown as one.

The account is read from Claude Code's own ~/.claude.json (`oauthAccount.accountUuid`) — the identity the
CLI itself uses, with no API that reports it. It travels as an opaque digest, never the email: the only
question is "same login or not", and an email is a personal identifier that would otherwise ride to every
federated host, sit in a payload and appear in any screenshot of the bars.

Synthetic accounts and hosts only; no real uuid, email or hostname appears here.
"""
import inspect
import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ.setdefault("XDG_STATE_HOME", tempfile.mkdtemp())
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel_acctusage", os.path.join(BIN, "romp-kernel")).load_module()

ACCT_A = "aaaaaaaaaaaa"
ACCT_B = "bbbbbbbbbbbb"


def _usage(acct):
    return {"fiveHour": {"pct": 12, "resetsAt": None, "color": [1, 2, 3]},
            "sevenDay": None, "fable": None, "t": 1000, "acct": acct, "limited": None}


class AccountIdentity(unittest.TestCase):
    def test_it_is_a_digest_and_never_the_raw_identifier(self):
        src = inspect.getsource(km._claude_account)
        self.assertIn("accountUuid", src, "the account identity the CLI itself uses")
        self.assertIn("sha256", src)
        self.assertNotIn('"emailAddress"', src)
        self.assertNotIn("emailAddress\"", src)
        # the digest is short and opaque: enough to answer "same or not", carrying nothing back
        self.assertIn("hexdigest()[:12]", src)

    def test_a_missing_or_unreadable_file_is_no_account_not_a_crash(self):
        old = os.environ.get("HOME")
        try:
            os.environ["HOME"] = tempfile.mkdtemp()      # a home with no ~/.claude.json at all
            km._ACCT_CACHE["mtime"] = -1.0
            self.assertEqual(km._claude_account(), "")
        finally:
            if old is not None:
                os.environ["HOME"] = old
            km._ACCT_CACHE["mtime"] = -1.0

    def test_the_reading_is_cached_on_the_file_and_not_reparsed_per_poll(self):
        self.assertIn('_ACCT_CACHE["mtime"] == m', inspect.getsource(km._claude_account))

    def test_the_usage_payload_carries_it(self):
        self.assertIn('"acct": _claude_account(),', inspect.getsource(km._usage))


class FleetRollup(unittest.TestCase):
    def setUp(self):
        self._usage_real = km._usage
        with km._remotes_lock:
            km._remotes.clear()

    def tearDown(self):
        km._usage = self._usage_real
        with km._remotes_lock:
            km._remotes.clear()

    def _remote(self, host, acct, status="up"):
        with km._remotes_lock:
            km._remotes[host] = {"host": host, "status": status, "usage": _usage(acct) if acct else None}

    def test_one_account_everywhere_stays_one_set(self):
        km._usage = lambda: _usage(ACCT_A)
        self._remote("api", ACCT_A)
        self._remote("gpu", ACCT_A)
        rows = km._fleet_usage()
        self.assertEqual(len(rows), 1, "an account-wide window drawn twice would repeat one number")
        self.assertEqual(rows[0]["host"], "", "the local row is unlabelled")

    def test_a_second_account_gets_its_own_set(self):
        km._usage = lambda: _usage(ACCT_A)
        self._remote("api", ACCT_B)
        rows = km._fleet_usage()
        self.assertEqual([r["host"] for r in rows], ["", "api"])
        self.assertEqual(rows[1]["acct"], ACCT_B)

    def test_two_hosts_on_the_same_second_account_share_one_set(self):
        km._usage = lambda: _usage(ACCT_A)
        self._remote("api", ACCT_B)
        self._remote("gpu", ACCT_B)
        rows = km._fleet_usage()
        self.assertEqual(len(rows), 2, "one allowance, however many machines are burning it")

    def test_a_disconnected_host_contributes_nothing(self):
        km._usage = lambda: _usage(ACCT_A)
        self._remote("api", ACCT_B, status="down")
        self.assertEqual(len(km._fleet_usage()), 1)

    def test_a_host_that_cannot_report_an_account_is_left_out_rather_than_guessed(self):
        # an older remote kernel has no `acct` field; a phantom second set of bars would be worse than
        # the honest single one
        km._usage = lambda: _usage(ACCT_A)
        self._remote("api", "")
        with km._remotes_lock:
            km._remotes["api"]["usage"] = {"fiveHour": {"pct": 5}, "t": 1}
        self.assertEqual(len(km._fleet_usage()), 1)

    def test_the_local_row_is_always_first_so_the_notices_read_off_this_machine(self):
        km._usage = lambda: _usage(ACCT_A)
        self._remote("aaa-sorts-first", ACCT_B)
        self.assertEqual(km._fleet_usage()[0]["host"], "")


class Polling(unittest.TestCase):
    def test_a_remote_is_polled_at_most_once_a_minute(self):
        src = inspect.getsource(km._poll_remote_usage)
        self.assertIn("REMOTE_USAGE_EVERY", src)
        self.assertGreaterEqual(km.REMOTE_USAGE_EVERY, 60)
        self.assertIn('r.get("_usage_at")', src)

    def test_a_blip_keeps_the_last_good_reading_rather_than_blanking_the_bars(self):
        src = inspect.getsource(km._poll_remote_usage)
        self.assertEqual(src.count('return r.get("usage")'), 3)

    def test_the_supervisor_polls_it_beside_the_version(self):
        src = inspect.getsource(km._tunnel_supervisor)
        self.assertIn("ruse = _poll_remote_usage(r) if up else None", src)
        self.assertIn('r["usage"] = ruse', src)

    def test_the_snapshot_never_reaches_the_credential_file(self):
        # remotes.json is 0600 because every row holds a serve token; rewriting it every minute to store
        # a usage snapshot would be pure churn on a file that exists to survive a restart
        self.assertIn("usage", km._NOT_SAVED)
        self.assertIn("_usage_at", km._NOT_SAVED)
        self.assertIn("k not in _NOT_SAVED", inspect.getsource(km._remotes_rows_for_save))


class RailRendering(unittest.TestCase):
    js = km._LANDING_USAGE_JS

    def test_the_rail_reads_the_fleet_view(self):
        self.assertIn("fetch('/usage/fleet'", self.js)
        self.assertIn("function renderRows(rows,selfHost)", self.js)

    def test_a_single_account_renders_exactly_as_before_with_no_label(self):
        self.assertIn("if(live.length===1)", self.js)
        # the host label markup is reached only on the many-account branch
        self.assertIn("class=ru-set", self.js)
        self.assertIn("class=ru-host", self.js)

    def test_the_label_is_the_chat_tabs_quiet_lowercase_italic_host_prefix(self):
        css = km._landing()
        self.assertIn(".ru-host{font:italic 400 10px", css)
        self.assertIn("text-transform:lowercase", css)
        self.assertIn("'<span class=ru-host>'+esc(hn)+':</span>'", self.js, "…and it ends in a colon")

    def test_the_account_wide_notices_read_off_THIS_machine(self):
        # a limit pauses THIS kernel's retries and judges; a remote account's limit does not
        self.assertIn("function notices(u)", self.js)
        self.assertIn("var local=rows.length?rows[0].usage:null;\nnotices(local);", self.js)

    def test_the_tooltip_names_each_account_only_when_there_is_more_than_one(self):
        self.assertIn("var many=sets.length>1;", self.js)
        self.assertIn("many?'<div class=ru-tip-host>'", self.js)

    def test_the_route_reads_the_cached_poll_rather_than_dialling_per_request(self):
        # a dashboard refresh must not cost an ssh round-trip per attached host: _fleet_usage reads the
        # rows the tunnel supervisor already filled, and does no network of its own
        src = inspect.getsource(km._fleet_usage)
        self.assertIn("_remotes.values()", src)
        for net in ("HTTPConnection", "_poll_remote_usage", "subprocess"):
            self.assertNotIn(net, src, "the route must answer from the cache")


if __name__ == "__main__":
    unittest.main()
