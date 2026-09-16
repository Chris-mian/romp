#!/usr/bin/env python3
"""Several Claude logins (T346, the user 2026-09-11: a personal and an enterprise Claude account under one
email, and a session billed to either, the way the Billing row offers Login vs API key).

The mechanics under test:
  * kernel/logins.py: the registry of STORED logins under STATE/logins/<id>.json (label, email, organisation,
    kind word, the COMMAND that prints the token), the pick vocabulary "login" | "key" | "login:<id>", the
    display label, the reasons a login is unavailable (refused, a year old, no command), and the helper command
    a session billed to one carries. No token anywhere: the credential lives wherever the user keeps it, and
    romp only runs the command (a secret manager's read command, typically; no store is ever assumed or named).
  * The machine's own login record grows the organisation (name + a digest of its uuid) and the kind word read
    from Claude Code's credentials file (subscriptionType folded: pro/max personal, team/enterprise enterprise,
    never guessed); nothing else of that file leaves the kernel.
  * The availability reply lists every login (the machine's own first) plus their reasons; a remembered pick of
    a stored login stands as the default while that login is usable.
  * set_auth takes "login:<id>", persists auth=login + authLogin, refuses a refused, expired, reference-less or
    unknown stored login; the machine signing out leaves a stored-login session untouched; the launch writes
    that login's helper into the per-session settings layer and restores no machine token beside it.
  * The doors still refuse a credential name from a client payload; GET/POST /logins list, add and remove.
  * The judges bill the judged session's login (the pick value, the helper in their overlay), stamp their
    usage rows with it and file their outcomes into the API-health ring under the login's own bucket.
  * The spend ledger folds a stored-login turn into byLogin and the spend detail carries a by-login row.

Synthetic ids, labels and references only; a token-shaped string is ASSEMBLED at run time, never a literal.
"""
import inspect
import json
import os
import secrets
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from pathlib import Path
from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
# Hermetic state BEFORE the loads (they resolve their state root at import time)
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)
os.environ.pop("ROMP_SUPERVISED", None)
os.environ["ROMP_SERVICE_ENV_FILE"] = os.path.join(os.environ["XDG_STATE_HOME"], "no-such-service.env")
os.environ["ROMP_SERVICE_ENV"] = os.environ["ROMP_SERVICE_ENV_FILE"]
os.environ["CLAUDE_CONFIG_DIR"] = tempfile.mkdtemp()
for _n in ("ANTHROPIC_API_KEY", "ROMP_API_KEY_CMD", "ROMP_API_KEY_REF", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"):
    os.environ.pop(_n, None)
lg = load_source("romp_logins", os.path.join(ROOT, "kernel", "logins.py"))
sb = load_source("romp_sdk_backend_logins", os.path.join(BIN, "romp_sdk_backend.py"))
km = load_source("romp_kernel_logins", os.path.join(BIN, "romp-kernel"))
jd = km.jd

SID = "11111111-2222-3333-4444-000000000001"
# a synthetic record id, computed so the scanner sees no key-shaped literal beside the word "key"
ZID = "%012x" % 0x0123456789AB
FAKE_KEY = "synthetic-helper-output-logins"


def _token_shaped():
    """A synthetic bearer of the setup-token's shape, assembled at run time (the scanner reads this file)."""
    return "".join(["sk", "-ant-", "oat01-", secrets.token_hex(12)])


def _stage_helper(cfg, out=FAKE_KEY):
    script = Path(cfg) / "helper.sh"
    script.write_text("#!/bin/sh\necho '%s'\n" % out)
    script.chmod(0o700)
    (Path(cfg) / "settings.json").write_text(json.dumps({"apiKeyHelper": str(script)}))


def _rec(state, label="Work", **kw):
    """One stored-login record under `state`, its token command a secret manager's read, by a synthetic tool name."""
    rec = {"id": kw.pop("id", None) or lg.mint_id(), "label": label,
           "tokenCmd": kw.pop("tokenCmd", "token-read 'romp login %s'" % label),
           "addedAt": kw.pop("addedAt", int(time.time()) - 86400)}
    rec.update(kw)
    lg.write_record(state, rec)
    return rec


class Registry(unittest.TestCase):
    def setUp(self):
        self.state = Path(tempfile.mkdtemp())

    def test_pick_vocabulary(self):
        self.assertEqual(lg.parse_pick("login"), ("login", ""))
        self.assertEqual(lg.parse_pick("key"), ("key", ""))
        self.assertEqual(lg.parse_pick("login:" + ZID), ("login", ZID))
        for junk in ("", None, "credit-card", "login:", "login:XYZ", "login:0123456789abc", "key:abc"):
            self.assertEqual(lg.parse_pick(junk), ("", ""), repr(junk))
        self.assertEqual(lg.pick_value("login", ZID), "login:" + ZID)
        self.assertEqual(lg.pick_value("login"), "login")
        self.assertEqual(lg.pick_value("key", ZID), "key")

    def test_kind_word_is_folded_never_guessed(self):
        self.assertEqual([lg.kind_word(w) for w in ("pro", "Max", "team", "ENTERPRISE")],
                         ["personal", "personal", "enterprise", "enterprise"])
        self.assertEqual(lg.kind_word("free"), "")
        self.assertEqual(lg.kind_word(None), "")

    def test_records_are_private_files_in_a_private_directory(self):
        import stat
        rec = _rec(self.state, "Work")
        self.assertEqual(stat.S_IMODE(os.stat(lg.record_path(self.state, rec["id"])).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(lg.logins_dir(self.state)).st_mode), 0o700)
        os.chmod(lg.record_path(self.state, rec["id"]), 0o644)
        lg.mark_refused(self.state, rec["id"], "x")
        self.assertEqual(stat.S_IMODE(os.stat(lg.record_path(self.state, rec["id"])).st_mode), 0o600, "a rewrite tightens a loosened record")

    def test_records_read_back_sorted_with_derived_state(self):
        a = _rec(self.state, "Personal", addedAt=1_700_000_000)
        b = _rec(self.state, "Work", addedAt=1_700_000_100, email="user@example.com", org="Acme", kind="enterprise")
        rows = lg.records(self.state, now=1_700_000_500)
        self.assertEqual([r["label"] for r in rows], ["Personal", "Work"])
        self.assertTrue(all(r["hasCmd"] for r in rows))
        self.assertFalse(rows[0]["expiresSoon"])
        self.assertEqual(rows[1]["expiresAt"], 1_700_000_100 + lg.TOKEN_LIFE_S)
        self.assertEqual(lg.display(b), "Work · user@example.com · Acme · enterprise")
        self.assertEqual(lg.display(a), "Personal")
        self.assertEqual(lg.display({"label": "user@example.com", "email": "USER@example.com", "kind": "pro"}),
                         "user@example.com · personal", "the email is not repeated; a CLI kind word folds")
        self.assertIsNone(lg.read_record(self.state, "not-an-id"))
        self.assertIsNone(lg.read_record(self.state, ZID))

    def test_availability_reasons(self):
        now = 1_700_000_000
        ok = _rec(self.state, "Fine", addedAt=now - 10 * 86400)
        self.assertEqual(lg.why_unavailable(lg.record_state(self.state, ok["id"], now), now), "")
        old = _rec(self.state, "Old", addedAt=now - lg.TOKEN_LIFE_S - 1)
        self.assertIn("a year old", lg.why_unavailable(lg.record_state(self.state, old["id"], now), now))
        soon = _rec(self.state, "Soon", addedAt=now - lg.EXPIRY_WARN_S - 1)
        st = lg.record_state(self.state, soon["id"], now)
        self.assertTrue(st["expiresSoon"] and not st["expired"])
        self.assertEqual(lg.why_unavailable(st, now), "", "eleven months warns, it does not refuse")
        nocmd = _rec(self.state, "NoCmd", tokenCmd="")
        self.assertIn("no token command", lg.why_unavailable(lg.record_state(self.state, nocmd["id"], now), now))
        self.assertTrue(lg.mark_refused(self.state, ok["id"], "OAuth token has expired"))
        self.assertFalse(lg.mark_refused(self.state, ok["id"], "OAuth token has expired"), "idempotent")
        why = lg.why_unavailable(lg.record_state(self.state, ok["id"], now), now)
        self.assertEqual(why, "the Fine login was refused: OAuth token has expired")
        self.assertTrue(lg.clear_refused(self.state, ok["id"]))
        self.assertEqual(lg.why_unavailable(lg.record_state(self.state, ok["id"], now), now), "")
        self.assertEqual(lg.why_unavailable(None), "no stored login with that id")

    def test_resolve_and_remove(self):
        a = _rec(self.state, "Work")
        _rec(self.state, "Twin"); _rec(self.state, "Twin")
        self.assertEqual(lg.resolve(self.state, "Work"), (a["id"], ""))
        self.assertEqual(lg.resolve(self.state, a["id"]), (a["id"], ""))
        lid, err = lg.resolve(self.state, "Twin")
        self.assertEqual(lid, "")
        self.assertIn("2 stored logins carry the label", err)
        self.assertIn("no stored login named", lg.resolve(self.state, "Nope")[1])
        self.assertTrue(lg.remove(self.state, a["id"]))
        self.assertFalse(lg.remove(self.state, a["id"]))
        self.assertIsNone(lg.read_record(self.state, a["id"]))

    def test_the_token_command_is_the_records_and_a_missing_record_or_command_is_a_static_error(self):
        rec = _rec(self.state, "Work")
        self.assertEqual(lg.token_command(self.state, rec["id"]), "token-read 'romp login Work'")
        with self.assertRaises(ValueError) as cm:
            lg.token_command(self.state, ZID)
        self.assertEqual(str(cm.exception), "no stored login with that id")
        nocmd = _rec(self.state, "NoCmd", tokenCmd="")
        with self.assertRaises(ValueError) as cm:
            lg.token_command(self.state, nocmd["id"])
        self.assertEqual(str(cm.exception), "the NoCmd login's record names no token command")
        self.assertNotIn("romp-login-helper", open(os.path.join(ROOT, "kernel", "logins.py")).read(), "the helper road is gone (2026-09-14)")
        self.assertFalse(os.path.exists(os.path.join(BIN, "romp-login-helper")))

    def test_the_module_never_touches_a_token_and_assumes_no_store(self):
        src = open(os.path.join(ROOT, "kernel", "logins.py")).read()
        for word in ("token_path", "store_token", "token_env", "import subprocess"):
            self.assertNotIn(word, src, word)
        # no store's shorthand inside romp (the user 2026-09-13): the module names none and offers no read-command helper
        self.assertFalse(hasattr(lg, "op_read_command"))
        self.assertNotIn("1Password", src); self.assertNotIn("op://", src); self.assertNotIn("OP_REF", src)
        self.assertEqual(lg.token_cmd_error(""), "a token command (a shell line that prints the token) is required")
        self.assertIn("one line", lg.token_cmd_error("cat x\ncat y"))
        self.assertEqual(lg.token_cmd_error("cat ~/.secrets/enterprise-token"), "", "any command; romp runs it, never reads it")
        # a command that carries the credential itself would ride the shell's argument list on every refresh: refused
        self.assertIn("looks like it carries the credential", lg.token_cmd_error("printf %s " + _token_shaped()))
        self.assertIn("looks like it carries the credential", lg.token_cmd_error("echo " + "".join(["A1b2"] * 11)))
        self.assertEqual(lg.token_cmd_error("cat /a/" + "x" * 60 + "/token"), "", "a long path segment is not a credential")
        # a JWT-shaped bearer (three dot-joined base64url segments) is one credential; dotted NAMES are not
        self.assertIn("looks like it carries the credential",
                      lg.token_cmd_error("echo " + ".".join(["eyJ" + "A1" * 8, "B2" * 10, "c3" * 12])))
        for ok in ("pass show claude.login.work.setup.token.credential",
                   "gopass show -o work.claude.enterprise.setup.token.value",
                   "fetch-token --host vault.internal.example.com --name claude.enterprise.login.token",
                   "echo " + ".".join(["verylongwordsegmentone", "verylongwordsegmenttwo", "verylongwordsegmentthree"])):
            self.assertEqual(lg.token_cmd_error(ok), "", ok)
        self.assertIn("looks like it carries the credential", lg.token_cmd_error("echo name." + "Zz9" * 14),
                      "a dotted prefix hides no plain run")
        # accepted: a four-segment run is not a JWT and its short segments pass the plain rule
        self.assertEqual(lg.token_cmd_error("echo " + ".".join(["A1" * 9] * 4)), "")
        # the refusal says the value typed here is already exposed and must be rotated
        self.assertIn("rotate", lg.token_cmd_error("printf %s " + _token_shaped()))
        # a forty-digit hex run is also a gpg key fingerprint: it passes in a gpg command or after --recipient
        fp = "0123456789abcdef" * 2 + "01234567"
        self.assertEqual(len(fp), 40)
        self.assertEqual(lg.token_cmd_error("gpg --quiet --decrypt --recipient %s ~/.secrets/token.gpg" % fp), "")
        self.assertEqual(lg.token_cmd_error("gpg2 -d -r %s ~/.secrets/token.gpg" % fp), "")
        self.assertEqual(lg.token_cmd_error("some-tool --recipient=%s" % fp), "")
        self.assertIn("looks like it carries the credential", lg.token_cmd_error("echo " + fp), "a bare hex run is still refused")
        self.assertEqual(lg.token_cmd_error("token-read 'romp login Work'"), "", "a secret manager's read with a spaced item name")

    def test_a_stored_record_is_never_re_read_against_the_shape_rule(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            # the add-time rule refuses this command today; a record written under an older rule keeps its sessions
            cmd = "printf %s " + _token_shaped()
            self.assertNotEqual(lg.token_cmd_error(cmd), "")
            rec = _rec(Path(d), "Work", tokenCmd=cmd)
            st = lg.record_state(Path(d), rec["id"])
            self.assertTrue(st["hasCmd"])
            self.assertEqual(lg.why_unavailable(st), "")
            self.assertEqual(lg.why_unavailable(rec), "", "a bare record too")
            self.assertFalse(lg.has_token_cmd(dict(rec, tokenCmd="  ")), "presence is the only read-time rule")
            self.assertIn("no token command is recorded", lg.why_unavailable(dict(rec, tokenCmd="")))
            # a non-string command is no command, never coerced into one
            for odd in (123, ["cat", "x"], {"cmd": "x"}, True):
                self.assertFalse(lg.has_token_cmd(dict(rec, tokenCmd=odd)), repr(odd))
                self.assertIn("no token command is recorded", lg.why_unavailable(dict(rec, tokenCmd=odd)), repr(odd))
            odd_rec = _rec(Path(d), "Odd", tokenCmd=7)
            self.assertFalse(lg.record_state(Path(d), odd_rec["id"])["hasCmd"])


class TheTokenCommand(unittest.TestCase):
    """The environment road (2026-09-14): a launch or a judge call billed to a stored login runs the record's token
    command through credentials.run_helper (labelled "the token command") and hands the output to that ONE child as
    CLAUDE_CODE_OAUTH_TOKEN; logins.token_value never runs a command itself. The command here is a secret manager's
    read by a synthetic tool name (token-read), answered by a fake of it on PATH."""

    def setUp(self):
        self.state = Path(tempfile.mkdtemp())
        self.bin = tempfile.mkdtemp()
        self.tok = _token_shaped()
        fake_op = Path(self.bin) / "token-read"
        # the fake tool prints the synthetic bearer for the one item it knows and refuses any other
        fake_op.write_text("#!/bin/sh\n[ \"$1\" = 'romp login Work' ] || { echo 'token-read: no such item' >&2; exit 1; }\n"
                           "printf '%s' '" + self.tok + "'\n")
        fake_op.chmod(0o700)
        self._path = os.environ.get("PATH", "")
        os.environ["PATH"] = self.bin + ":" + self._path

    def tearDown(self):
        os.environ["PATH"] = self._path

    def _read(self, login_id, timeout_s=None):
        return lg.token_value(self.state, login_id, lambda c: sb._cred.run_helper(c, label="the token command", timeout_s=timeout_s))

    def test_prints_the_item_for_a_recorded_command(self):
        rec = _rec(self.state, "Work")
        self.assertEqual(self._read(rec["id"]), self.tok)

    def test_failures_name_the_step_never_a_value(self):
        with self.assertRaises(ValueError) as cm:
            self._read(ZID)
        self.assertEqual(str(cm.exception), "no stored login with that id")
        rec = _rec(self.state, "Other")          # a reference the fake tool does not know
        with self.assertRaises(sb._cred.CredentialError) as cm:
            self._read(rec["id"])
        self.assertEqual(str(cm.exception), "the token command failed (non-zero exit)")
        self.assertNotIn(self.tok, str(cm.exception))
        nocmd = _rec(self.state, "NoCmd", tokenCmd="")
        with self.assertRaises(ValueError) as cm:
            self._read(nocmd["id"])
        self.assertIn("names no token command", str(cm.exception))
        empty = _rec(self.state, "Empty", tokenCmd="true")
        with self.assertRaises(sb._cred.CredentialError) as cm:
            self._read(empty["id"])
        self.assertEqual(str(cm.exception), "the token command printed an empty or invalid key (one line on stdout, exit 0)")

    def test_the_command_runs_under_a_whitelisted_environment_with_its_stderr_discarded(self):
        # the command sees PATH/HOME and the XDG names, never the kernel's serve token or a stray variable; whatever it
        # writes on stderr goes nowhere (a secret manager's diagnostics can quote the value it read)
        probe = Path(tempfile.mkdtemp()) / "seen.json"
        code = 'import json,os,sys; json.dump(dict(os.environ), open(sys.argv[1], "w")); sys.stderr.write("secret-manager diagnostic quoting NOISE"); print("tok-out")'
        rec = _rec(self.state, "Env", tokenCmd="python3 -c '%s' %s" % (code, probe))
        saved = {k: os.environ.get(k) for k in ("ROMP_SERVE_TOKEN", "STRAY_VAR", "XDG_CONFIG_HOME", "LC_TIME")}
        os.environ.update(ROMP_SERVE_TOKEN="serve-token-value", STRAY_VAR="stray", XDG_CONFIG_HOME="/x/config", LC_TIME="C")
        try:
            self.assertEqual(self._read(rec["id"]), "tok-out", "stdout is the command's, one trailing newline forgiven")
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        seen = json.loads(probe.read_text())
        self.assertNotIn("ROMP_SERVE_TOKEN", seen)
        self.assertNotIn("STRAY_VAR", seen)
        for k in ("PATH", "HOME"):
            self.assertIn(k, seen, k)
        self.assertEqual((seen.get("XDG_CONFIG_HOME"), seen.get("LC_TIME")), ("/x/config", "C"), "the XDG and LC names pass")
        injected = {"__CF_USER_TEXT_ENCODING"} if sys.platform == "darwin" else set()   # CoreFoundation adds it to every child at
        #                                                                                  start-up on macOS; romp passed nothing
        self.assertTrue(set(seen) <= {"PATH", "HOME", "USER", "LOGNAME", "TMPDIR", "LANG", "LC_ALL", "TERM", "CLAUDE_CONFIG_DIR", "PWD", "SHLVL", "_", "OLDPWD"}
                        | {k for k in seen if k.startswith(("LC_", "XDG_"))} | injected, sorted(seen))

    def test_a_hung_command_is_cut_by_the_bound(self):
        import time as _t
        rec = _rec(self.state, "Hung", tokenCmd="sleep 30")
        t0 = _t.time()
        with self.assertRaises(sb._cred.CredentialError) as cm:
            self._read(rec["id"], timeout_s=1)
        self.assertLess(_t.time() - t0, 10, "the bound cut it")
        self.assertEqual(str(cm.exception), "the token command timed out after 1 s")

    def test_any_command_serves(self):
        # a token kept in a private file, read by a plain command: romp assumes nothing about the store
        priv = Path(tempfile.mkdtemp()) / "enterprise-token"
        priv.write_text(self.tok)
        priv.chmod(0o600)
        rec = _rec(self.state, "File", tokenCmd="cat %s" % priv)
        self.assertEqual(self._read(rec["id"]), self.tok)


class MachineLoginRecord(unittest.TestCase):
    """The machine's own login record: organisation and kind word, read from Claude Code's own files."""

    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.cfg = tempfile.mkdtemp()
        self._home, self._cfg = os.environ.get("HOME"), os.environ.get("CLAUDE_CONFIG_DIR")
        os.environ["HOME"], os.environ["CLAUDE_CONFIG_DIR"] = self.home, self.cfg
        self._acct_saved, self._kind_saved = dict(km._ACCT_CACHE), dict(km._KIND_CACHE)
        km._ACCT_CACHE.update({"mtime": -1.0, "val": "", "label": "", "state": "none", "org": "", "orgDigest": ""})
        km._KIND_CACHE.update({"mtime": -1.0, "kind": ""})

    def tearDown(self):
        os.environ["HOME"], os.environ["CLAUDE_CONFIG_DIR"] = self._home, self._cfg
        km._ACCT_CACHE.update(self._acct_saved)
        km._KIND_CACHE.update(self._kind_saved)

    def _acct(self, **oa):
        p = Path(self.home, ".claude.json")
        p.write_text(json.dumps({"oauthAccount": oa}))
        os.utime(p, (1_800_000_000 + len(oa), 1_800_000_000 + len(oa)))
        km._ACCT_CACHE["mtime"] = -2.0

    def _creds(self, text, t=1_800_000_000):
        p = Path(self.cfg, ".credentials.json")
        p.write_text(text)
        os.utime(p, (t, t))
        km._KIND_CACHE["mtime"] = -2.0

    def test_organisation_rides_as_name_plus_digest_and_the_display_joins_the_pieces(self):
        self._acct(accountUuid="11111111-2222-3333-4444-555555555555", emailAddress="user@example.com",
                   organizationName="Acme", organizationUuid="66666666-7777-8888-9999-000000000000")
        tok = _token_shaped()
        self._creds(json.dumps({"claudeAiOauth": {"accessToken": tok, "refreshToken": tok[::-1],
                                                  "subscriptionType": "enterprise"}}))
        self.assertEqual(km._claude_account_label(), "user@example.com", "the account label is unchanged")
        self.assertEqual(km._ACCT_CACHE["org"], "Acme")
        self.assertEqual(len(km._ACCT_CACHE["orgDigest"]), 12)
        self.assertNotIn("66666666", json.dumps(km._ACCT_CACHE), "the organisation uuid never sits in the cache")
        self.assertEqual(km._kind_read(), "enterprise")
        self.assertEqual(km._claude_login_display(), "user@example.com · Acme · enterprise")
        self.assertNotIn(tok, json.dumps(km._KIND_CACHE) + json.dumps(km._ACCT_CACHE) + km._claude_login_display(),
                         "nothing of the credentials file but the folded word leaves the kernel")

    def test_the_kind_is_never_guessed_from_an_organisation(self):
        self._acct(accountUuid="11111111-2222-3333-4444-555555555555", emailAddress="user@example.com",
                   organizationName="Acme")
        self.assertEqual(km._kind_read(), "", "no credentials file: no word")
        self.assertEqual(km._claude_login_display(), "user@example.com · Acme")
        self._creds(json.dumps({"claudeAiOauth": {"subscriptionType": "free-trial"}}))
        self.assertEqual(km._kind_read(), "", "an unknown word is no word")
        self._creds(json.dumps({"claudeAiOauth": {"subscriptionType": "max"}}), t=1_800_000_001)
        self.assertEqual(km._kind_read(), "personal")

    def test_a_failed_credentials_read_is_not_cached(self):
        self._creds('{"claudeAiOauth": {"subscri', t=1_800_000_002)
        self.assertEqual(km._kind_read(), "")
        self.assertEqual(km._KIND_CACHE["mtime"], -1.0, "retried on the next read")
        self._creds(json.dumps({"claudeAiOauth": {"subscriptionType": "team"}}), t=1_800_000_002)
        self.assertEqual(km._kind_read(), "enterprise", "the same mtime, re-read")


class AvailabilityLists(unittest.TestCase):
    """_auth_avail lists every login (the machine's own first) with reasons; a remembered stored pick stands."""

    def setUp(self):
        self.saved = (km._sdk, km._claude_account, km._claude_account_label, km._claude_account_state,
                      km.jd._cred.helper_source, km._claude_login_display)
        self.state = km.jd.STATE
        self.state.mkdir(parents=True, exist_ok=True)
        for p in lg.logins_dir(self.state).glob("*.json") if lg.logins_dir(self.state).exists() else []:
            p.unlink()
        (self.state / "sdk-defaults.json").unlink(missing_ok=True)

    def tearDown(self):
        (km._sdk, km._claude_account, km._claude_account_label, km._claude_account_state,
         km.jd._cred.helper_source, km._claude_login_display) = self.saved
        for p in lg.logins_dir(self.state).glob("*.json") if lg.logins_dir(self.state).exists() else []:
            p.unlink()
        (self.state / "sdk-defaults.json").unlink(missing_ok=True)

    def _world(self, key, acct, label="user@example.com", managed=False, display="user@example.com · Acme · enterprise"):
        km._sdk = lambda: type("B", (), {"key_available": bool(key)})()
        km._claude_account = lambda: acct
        km._claude_account_label = lambda: (label if acct else "")
        km._claude_account_state = lambda: ("ok" if acct else "none")
        km._claude_login_display = lambda: (display if acct else "")
        km.jd._cred.helper_source = lambda: ("managed" if managed else ("user" if key else None))

    def test_the_machine_login_is_first_and_stored_logins_follow_with_reasons(self):
        self._world(FAKE_KEY, "aaaaaaaaaaaa")
        ok = _rec(self.state, "Work", org="Acme", kind="enterprise")
        bad = _rec(self.state, "Old", addedAt=int(time.time()) - lg.TOKEN_LIFE_S - 5)
        a = km._auth_avail()
        logins = a["logins"]
        # the machine's own first, then the stored logins oldest first (the registry's order)
        self.assertEqual([l["value"] for l in logins], ["login", "login:" + bad["id"], "login:" + ok["id"]])
        self.assertEqual(logins[0], {"id": "", "value": "login", "label": "user@example.com · Acme · enterprise",
                                     "machine": True, "available": True})
        self.assertEqual(logins[2]["label"], "Work · Acme · enterprise")
        self.assertTrue(logins[2]["available"] and "why" not in logins[2])
        self.assertFalse(logins[1]["available"])
        self.assertIn("a year old", logins[1]["why"])
        self.assertEqual(a["acct"], "user@example.com", "older readers keep the account name")
        st = km._auth_avail_status()
        self.assertEqual(sorted(st), ["default", "defaultExplicit", "key", "login", "logins"],
                         "the login list rides beside the machine default and its explicit flag (T380)")
        self.assertEqual(st["logins"][2]["value"], "login:" + ok["id"])

    def test_a_signed_out_machine_still_offers_a_stored_login(self):
        self._world("", "")
        ok = _rec(self.state, "Work")
        a = km._auth_avail()
        self.assertFalse(a["login"])
        self.assertEqual(a["logins"][0]["why"], km.jd._cred.WHY_NO_LOGIN)
        self.assertTrue(a["logins"][1]["available"], "the stored login does not depend on the machine's account")

    def test_a_managed_helper_bars_stored_logins_too(self):
        self._world(FAKE_KEY, "aaaaaaaaaaaa", managed=True)
        ok = _rec(self.state, "Work")
        a = km._auth_avail()
        self.assertEqual(a["logins"][1]["why"], km.jd._cred.WHY_MANAGED_HELPER)

    def test_a_remembered_stored_login_is_the_default_while_usable(self):
        self._world(FAKE_KEY, "aaaaaaaaaaaa")
        ok = _rec(self.state, "Work")
        (self.state / "sdk-defaults.json").write_text(json.dumps({"auth": "login", "authLogin": ok["id"]}))
        self.assertEqual(km._auth_avail()["default"], "login:" + ok["id"])
        lg.mark_refused(self.state, ok["id"], "refused by the API")
        self.assertEqual(km._auth_avail()["default"], "login", "a refused stored login falls through the machine rules")
        lg.remove(self.state, ok["id"])
        self.assertEqual(km._auth_avail()["default"], "login")

    def test_an_explicit_stored_login_default_is_reported_as_the_explicit_default(self):
        """The user 2026-09-14: a stored login set under Set default billing reads "login:<id>" with defaultExplicit true
        while usable, and falls through the machine rules like any remembered login pick when it is not."""
        self._world(FAKE_KEY, "aaaaaaaaaaaa")
        ok = _rec(self.state, "Work")
        (self.state / "sdk-defaults.json").write_text(json.dumps({"auth": "login", "authLogin": ok["id"], "authExplicit": True}))
        a = km._auth_avail()
        self.assertEqual((a["default"], a["defaultExplicit"]), ("login:" + ok["id"], True))
        lg.mark_refused(self.state, ok["id"], "refused by the API")
        a = km._auth_avail()
        self.assertEqual((a["default"], a["defaultExplicit"]), ("login", True), "a refused stored default falls to the machine's own login, still explicit")

    def test_the_status_push_and_the_live_map_carry_the_login_fields(self):
        src = inspect.getsource(km.build_session)
        self.assertIn('"authLogin": tm.get("authLogin", "")', src)
        self.assertIn('"authLabel": tm.get("authLabel", "") or _claude_login_display()', src)
        src = inspect.getsource(km.Sessions.live)
        self.assertIn('"authLogin": st.get("authLogin", "")', src)
        self.assertIn('"authLabel": st.get("authLabel", "")', src)


class _Backend(unittest.TestCase):
    """A real backend on a box with a fixture apiKeyHelper, a signed-in machine login (login_ok True), no tokens."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.cfg = tempfile.mkdtemp()
        self._cfg_before = os.environ.get("CLAUDE_CONFIG_DIR")
        os.environ["CLAUDE_CONFIG_DIR"] = self.cfg
        self._exp = os.environ.pop("ROMP_EXPECTED_AUTH", None)
        self._fetch = sb._fetch_key_fast_org
        sb._fetch_key_fast_org = lambda key: None
        sb._FAST_ORG_VERDICTS.clear()
        sb._cred.forget_helper_key()
        self._managed = sb._cred.managed_settings_path
        sb._cred.managed_settings_path = lambda: os.path.join(self.cfg, "no-managed-settings.json")
        self._tokens = sb._STARTUP_AUTH_ENV
        sb._STARTUP_AUTH_ENV = {}
        _stage_helper(self.cfg)
        # the environment road (2026-09-14): a launch billed to a stored login RUNS the record's token command; the records'
        # default command is a read by a synthetic tool name (token-read), so a fake of it sits on the runner's PATH and
        # prints one synthetic bearer for any `romp login <label>` item, refusing anything else
        self.tools = tempfile.mkdtemp()
        self.tok = _token_shaped()
        tool = Path(self.tools) / "token-read"
        tool.write_text("#!/bin/sh\ncase \"$1\" in 'romp login '*) printf '%s' '" + self.tok + "' ;; *) echo 'token-read: no such item' >&2; exit 1 ;; esac\n")
        tool.chmod(0o700)
        self._henv = sb._cred.helper_env
        sb._cred.helper_env = lambda: dict(self._henv(), PATH=self.tools + ":" + self._henv().get("PATH", ""))
        self.be = sb.SdkBackend(self.d, "/bin/true", lambda *a, **k: None)
        self.be.login_ok = lambda: True
        import sys, types
        self._fake_sdk = "claude_agent_sdk" not in sys.modules and not sb.sdk_importable()
        if self._fake_sdk:
            fake = types.ModuleType("claude_agent_sdk")
            # an attribute-bearing stand-in, like the SDK's dataclass: with hosts on the options loop sets each
            # matcher's `timeout`, which a plain dict refuses (the test_session_auth harness's rule)
            fake.HookMatcher = lambda **kw: types.SimpleNamespace(**kw)
            sys.modules["claude_agent_sdk"] = fake

    def tearDown(self):
        import sys
        if self._fake_sdk:
            sys.modules.pop("claude_agent_sdk", None)
        sb._fetch_key_fast_org = self._fetch
        sb._FAST_ORG_VERDICTS.clear()
        sb._cred.forget_helper_key()
        sb._cred.managed_settings_path = self._managed
        sb._cred.helper_env = self._henv
        sb._STARTUP_AUTH_ENV = self._tokens
        os.environ["CLAUDE_CONFIG_DIR"] = self._cfg_before
        if self._exp is not None:
            os.environ["ROMP_EXPECTED_AUTH"] = self._exp

    def _sess(self, n=1, **reg):
        return sb.SdkSession(self.be, {"sid": "11111111-2222-3333-4444-%012d" % n, "name": "s%d" % n, "cwd": "/tmp", **reg})

    def _settings_of(self, kw):
        p = kw.get("settings")
        return json.loads(Path(p).read_text()) if p else {}


class StoredLoginPick(_Backend):
    def _launch_options(self, s):
        """The options build for a LAUNCH, followed by the launch-login stamp the connect loop makes for a kernel child at the
        connect (the stamp moved out of _options, 2026-09-14: it is made once per CLI, at a kernel child's connect or at a
        host's hello for a CLI the reg does not name, so an attach to a surviving CLI keeps the restored evidence and login);
        the two together are what a launch's options build used to do here."""
        kw = self.be._options(s, dict)
        self.be._stamp_launch_login(s)
        return kw

    def test_set_auth_persists_the_login_and_seeds_the_next_session(self):
        rec = _rec(self.be.state_dir, "Work", org="Acme", kind="enterprise")
        sid = self.be.spawn("n", "/tmp")
        self.assertTrue(self.be.set_auth(sid, "login:" + rec["id"]))
        reg = sb.read_reg(self.be.state_dir, sid)
        self.assertEqual((reg["auth"], reg["authLogin"], reg["authPending"]), ("login", rec["id"], True))
        d = sb.read_sdk_defaults(self.be.state_dir)
        self.assertEqual((d.get("auth"), d.get("authLogin")), ("login", rec["id"]))
        sid2 = self.be.spawn("m", "/tmp")
        reg2 = sb.read_reg(self.be.state_dir, sid2)
        self.assertEqual((reg2.get("auth"), reg2.get("authLogin")), ("login", rec["id"]), "the next spawn seeds the stored login")
        # a plain login pick clears the stored one, in the reg and in the remembered default
        self.assertTrue(self.be.set_auth(sid, "login"))
        self.assertEqual(sb.read_reg(self.be.state_dir, sid).get("authLogin"), "")
        self.assertEqual(sb.read_sdk_defaults(self.be.state_dir).get("authLogin"), "")

    def test_an_explicit_machine_default_clears_a_stored_login_left_in_the_seed(self):
        """The merge of T380 read (2026-09-12): set_auth_default wrote auth and authExplicit and left authLogin as a
        per-session stored-login pick had seeded it (the not-explicit seed), so every new session billed the stored
        login while the Default group marked the machine's own, and the stale id survived Automatic and came back
        with the next explicit Login. An explicit default is always the machine's own side: login, key and auto each
        clear the id."""
        rec = _rec(self.be.state_dir, "Work")
        sid = self.be.spawn("n", "/tmp")
        self.assertTrue(self.be.set_auth(sid, "login:" + rec["id"]))
        self.assertEqual(sb.read_sdk_defaults(self.be.state_dir).get("authLogin"), rec["id"], "the not-explicit seed")
        self.assertTrue(self.be.set_auth_default("login"))
        d = sb.read_sdk_defaults(self.be.state_dir)
        self.assertEqual((d.get("auth"), d.get("authExplicit"), d.get("authLogin")), ("login", True, ""), "the machine's own login, no stored id")
        reg = sb.read_reg(self.be.state_dir, self.be.spawn("m", "/tmp"))
        self.assertEqual((reg.get("auth"), reg.get("authLogin") or ""), ("login", ""), "a new session bills the machine's own login")
        # the id must not survive Automatic and come back with the next explicit Login
        self.assertTrue(self.be.set_auth_default("auto"))
        self.assertTrue(self.be.set_auth(sid, "login:" + rec["id"]))          # seeds again while automatic
        self.assertEqual(sb.read_sdk_defaults(self.be.state_dir).get("authLogin"), rec["id"])
        self.assertTrue(self.be.set_auth_default("auto"))
        self.assertEqual(sb.read_sdk_defaults(self.be.state_dir).get("authLogin"), "", "auto clears the id too")
        self.assertTrue(self.be.set_auth(sid, "login:" + rec["id"]))
        self.assertTrue(self.be.set_auth_default("key"))
        self.assertEqual(sb.read_sdk_defaults(self.be.state_dir).get("authLogin"), "", "key clears it")
        self.assertTrue(self.be.set_auth_default("login"))
        self.assertEqual(sb.read_reg(self.be.state_dir, self.be.spawn("o", "/tmp")).get("authLogin") or "", "")
        self.assertEqual(sb.read_reg(self.be.state_dir, sid).get("authLogin"), rec["id"], "the session's own pick is untouched")

    def test_a_stored_login_can_be_the_explicit_machine_default_and_unpicked_sessions_follow_it(self):
        """The user 2026-09-14: the Set default billing submenu offers a stored login. set_auth_default takes "login:<id>",
        judged on its record as a pick of it would be; the seed carries the id; a session with no pick of its own reads
        that login in its status (live and dormant), launches with its helper, and its judges' resolver names it. A
        refused (or removed) stored default falls through to the machine's own login everywhere, and is refused at the door."""
        default_tok = _token_shaped()
        rec = _rec(self.be.state_dir, "Work", org="Acme", tokenCmd="printf '%%s' '%s'" % default_tok)
        self.assertTrue(self.be.set_auth_default("login:" + rec["id"]))
        d = sb.read_sdk_defaults(self.be.state_dir)
        self.assertEqual((d.get("auth"), d.get("authExplicit"), d.get("authLogin")), ("login", True, rec["id"]))
        self.assertEqual((self.be.explicit_default_auth(), self.be.explicit_default_login()), ("login", rec["id"]))
        self.assertEqual(self.be.fallback_auth(), "login")
        self.assertEqual(self.be.default_login({}), rec["id"], "the judges' resolver names the stored default for an unpicked reg")
        self.assertEqual(self.be.default_login({"auth": "key"}), "", "a key pick of its own: no login")
        self.assertEqual(self.be.default_login({"auth": "login"}), "", "a machine-login pick of its own: the machine's own")
        reg = sb.read_reg(self.be.state_dir, self.be.spawn("m", "/tmp"))
        self.assertEqual((reg.get("auth"), reg.get("authLogin")), ("login", rec["id"]), "a new session seeds the stored default")
        s = self._sess(1)                                   # no pick of its own
        snap = s.snapshot()
        self.assertEqual((snap["auth"], snap["authLogin"], snap["authLabel"]), ("login", rec["id"], "Work · Acme"), "the live status reads the login it follows")
        row = self.be._live_row({"sid": s.sid}, s.sid)
        self.assertEqual((row["auth"], row["authLogin"], row["authLabel"]), ("login", rec["id"], "Work · Acme"), "the dormant row too")
        kw = self._launch_options(s)
        self.assertEqual(self._settings_of(kw).get("apiKeyHelper"), "", "the box's helper disabled")
        self.assertEqual(kw["env"].get("CLAUDE_CODE_OAUTH_TOKEN"), default_tok, "the launch carries that login's token (the environment road)")
        self.assertEqual(s._launched_login, rec["id"])
        # refused: the status, the launch and the resolver fall through to the machine's own login
        lg.mark_refused(self.be.state_dir, rec["id"], "refused")
        self.assertEqual((self.be.explicit_default_login(), self.be.fallback_auth(), self.be.default_login({})), ("", "login", ""))
        s2 = self._sess(2)
        snap2 = s2.snapshot()
        self.assertEqual((snap2["auth"], snap2["authLogin"], snap2["authLabel"]), ("login", "", ""))
        kw2 = self._launch_options(s2)
        self.assertEqual(self._settings_of(kw2).get("apiKeyHelper"), "", "the machine's own login launch: the helper disabled")
        self.assertEqual(s2._launched_login, "")
        # the door: a refused or unknown stored login is no default, with the reason
        self.assertFalse(self.be.set_auth_default("login:" + rec["id"]))
        self.assertIn("refused", self.be.last_auth_refusal)
        self.assertFalse(self.be.set_auth_default("login:" + ZID))
        self.assertEqual(self.be.last_auth_refusal, "no stored login with that id")
        # the machine's own login and the key still write the id EMPTY (the T380 merge read), and auto clears it
        lg.clear_refused(self.be.state_dir, rec["id"])
        self.assertTrue(self.be.set_auth_default("login:" + rec["id"]))
        self.assertTrue(self.be.set_auth_default("key"))
        self.assertEqual(sb.read_sdk_defaults(self.be.state_dir).get("authLogin"), "")
        self.assertTrue(self.be.set_auth_default("login:" + rec["id"]))
        self.assertTrue(self.be.set_auth_default("auto"))
        d = sb.read_sdk_defaults(self.be.state_dir)
        self.assertEqual((d.get("auth"), d.get("authExplicit"), d.get("authLogin")), ("", False, ""))

    def test_the_picker_pick_and_a_fork_carry_the_stored_login(self):
        rec = _rec(self.be.state_dir, "Work")
        sid = self.be.spawn("n", "/tmp", auth="login:" + rec["id"])
        reg = sb.read_reg(self.be.state_dir, sid)
        self.assertEqual((reg["auth"], reg["authLogin"]), ("login", rec["id"]))
        self.assertEqual(self.be.default_auth(reg), "login", "older readers see a login pick")
        # an explicit pick naming a stored login this box does not know lands as picked, like every explicit
        # pick (the launch falls to the side that exists and says so); the status names the reason
        unk = sb.read_reg(self.be.state_dir, self.be.spawn("k", "/tmp", auth="login:" + ZID))
        self.assertEqual((unk.get("auth"), unk.get("authLogin")), ("login", ZID))
        self.assertEqual(self.be.pick_unavailable("login", ZID), "login")
        self.assertEqual(self.be.auth_unavailable_why("login", ZID), "no stored login with that id")

    def test_refusals_name_the_reason(self):
        sid = self.be.spawn("n", "/tmp")
        self.assertFalse(self.be.set_auth(sid, "login:" + ZID))
        self.assertEqual(self.be.last_auth_refusal, "no stored login with that id")
        rec = _rec(self.be.state_dir, "Work")
        lg.mark_refused(self.be.state_dir, rec["id"], "OAuth token has expired")
        self.assertFalse(self.be.set_auth(sid, "login:" + rec["id"]))
        self.assertEqual(self.be.last_auth_refusal, "the Work login was refused: OAuth token has expired")
        lg.clear_refused(self.be.state_dir, rec["id"])
        self.assertTrue(self.be.set_auth(sid, "login:" + rec["id"]))
        nocmd = _rec(self.be.state_dir, "NoCmd", tokenCmd="")
        self.assertFalse(self.be.set_auth(sid, "login:" + nocmd["id"]))
        self.assertIn("no token command", self.be.last_auth_refusal)

    def test_the_machine_signing_out_leaves_a_stored_login_session_untouched(self):
        rec = _rec(self.be.state_dir, "Work")
        self.be.login_ok = lambda: False
        self.assertEqual(self.be.pick_unavailable("login"), "login", "the machine's login is gone")
        self.assertEqual(self.be.pick_unavailable("login", rec["id"]), "", "the stored login stands")
        self.assertEqual(self.be.pick_fall("login", rec["id"]), "")
        self.assertTrue(self.be.set_auth(self.be.spawn("n", "/tmp"), "login:" + rec["id"]),
                        "a stored login can still be picked on a signed-out machine")

    def test_a_dead_stored_login_falls_like_a_dead_machine_login(self):
        rec = _rec(self.be.state_dir, "Work")
        lg.mark_refused(self.be.state_dir, rec["id"], "refused")
        self.assertEqual(self.be.pick_unavailable("login", rec["id"]), "login")
        self.assertEqual(self.be.pick_fall("login", rec["id"]), "key", "a helper exists: the key")
        os.unlink(os.path.join(self.cfg, "settings.json"))
        sb._cred.forget_helper_key()
        self.assertEqual(self.be.pick_fall("login", rec["id"]), "login", "no helper: the machine's own login")
        self.be.login_ok = lambda: False
        self.assertEqual(self.be.pick_fall("login", rec["id"]), "", "nothing to fall to")

    def test_the_rows_carry_which_login(self):
        rec = _rec(self.be.state_dir, "Work", org="Acme")
        s = self._sess(1, auth="login", authLogin=rec["id"])
        snap = s.snapshot()
        self.assertEqual((snap["auth"], snap["authLogin"], snap["authLabel"]), ("login", rec["id"], "Work · Acme"))
        row = self.be._live_row({"sid": s.sid, "auth": "login", "authLogin": rec["id"]}, s.sid)
        self.assertEqual((row["auth"], row["authLogin"], row["authLabel"]), ("login", rec["id"], "Work · Acme"))
        plain = self._sess(2, auth="login").snapshot()
        self.assertEqual((plain["authLogin"], plain["authLabel"]), ("", ""), "the machine's own login: the kernel fills the label")
        junk = self._sess(3, auth="login", authLogin="not-an-id")
        self.assertEqual(junk.auth_login, "", "junk reads as the machine's login")

    def test_the_launch_carries_the_stored_token_in_its_environment_and_no_machine_token(self):
        """The environment road (2026-09-14): the launch runs the record's token command and hands the output to this
        one CLI as CLAUDE_CODE_OAUTH_TOKEN, the box's helper disabled; the machine's own token is not beside it."""
        tok = _token_shaped()
        rec = _rec(self.be.state_dir, "Work", tokenCmd="printf '%%s' '%s'" % tok)
        machine_tok = _token_shaped()
        sb._STARTUP_AUTH_ENV = {"CLAUDE_CODE_OAUTH_TOKEN": machine_tok}
        s = self._sess(1, auth="login", authLogin=rec["id"])
        kw = self._launch_options(s)
        st = self._settings_of(kw)
        self.assertEqual(st.get("apiKeyHelper"), "", "the box's helper disabled, as for the machine's own login")
        self.assertEqual(kw["env"].get("CLAUDE_CODE_OAUTH_TOKEN"), tok, "the stored login's token, from its command")
        self.assertNotEqual(kw["env"].get("CLAUDE_CODE_OAUTH_TOKEN"), machine_tok, "the machine's token stays out of a stored-login launch")
        self.assertNotIn("ANTHROPIC_AUTH_TOKEN", kw["env"])
        # ANTHROPIC_API_KEY outranks the helper in the CLI's precedence, and the launch's overlay cannot unset an
        # inherited variable: the guarantee is the kernel's own environment, which the boot check refuses to run with
        # while that name is set (credentials.check_boot_environment, RETIRED_VARS), so no child inherits it
        self.assertNotIn("ANTHROPIC_API_KEY", kw["env"])
        self.assertIn("ANTHROPIC_API_KEY", sb._cred.RETIRED_VARS)
        self.assertIn("RETIRED_VARS", inspect.getsource(sb._cred.check_boot_environment))
        self.assertEqual(s._launched_login, rec["id"])
        self.assertFalse(s._launched_keyed)
        # the machine's own login launch is exactly as before: the helper disabled, the machine's token restored
        s2 = self._sess(2, auth="login")
        kw2 = self._launch_options(s2)
        self.assertEqual(self._settings_of(kw2).get("apiKeyHelper"), "")
        self.assertEqual(kw2["env"].get("CLAUDE_CODE_OAUTH_TOKEN"), machine_tok)
        self.assertEqual(s2._launched_login, "")

    def test_a_failing_token_command_marks_the_record_refused_and_the_launch_takes_the_fall(self):
        """A command that fails at launch (the fake tool knows no such item) is loud, never a quiet fall: the record is
        marked refused with the reason, the problem ring says so, and this launch falls exactly as a refused stored
        login does (the key: a helper is configured here), carrying neither the stored nor the machine's token."""
        rec = _rec(self.be.state_dir, "Work", tokenCmd="false")   # a command that exits non-zero
        sb._STARTUP_AUTH_ENV = {"CLAUDE_CODE_OAUTH_TOKEN": _token_shaped()}
        logs = []
        self.be._log = lambda m, problem=False: logs.append((m, problem))
        s = self._sess(1, auth="login", authLogin=rec["id"])
        kw = self._launch_options(s)
        self.assertNotIn("CLAUDE_CODE_OAUTH_TOKEN", kw["env"], "a key launch: no token of either kind")
        self.assertNotIn("apiKeyHelper", self._settings_of(kw), "the box's helper runs (the fall is the key)")
        self.assertEqual(s._launched_login, "")
        state = lg.record_state(self.be.state_dir, rec["id"])
        self.assertTrue(state.get("refused"))
        self.assertEqual(str(state.get("refused")), "the token command did not answer: the token command failed (non-zero exit)")
        self.assertTrue(any("token command failed" in m and p for m, p in logs), logs)
        self.assertEqual(self.be.pick_unavailable("login", rec["id"]), "login")

    def test_a_refused_stored_login_launch_falls_to_the_key_and_says_so_once(self):
        rec = _rec(self.be.state_dir, "Work")
        lg.mark_refused(self.be.state_dir, rec["id"], "refused")
        logs = []
        self.be._log = lambda m, problem=False: logs.append((m, problem))
        s = self._sess(1, auth="login", authLogin=rec["id"])
        kw = self._launch_options(s)
        self.assertNotIn("apiKeyHelper", self._settings_of(kw), "a key launch runs the box's helper")
        self.assertEqual(s._launched_login, "")
        self._launch_options(s)
        said = [m for m, p in logs if "cannot apply" in m]
        self.assertEqual(len(said), 1, said)
        self.assertIn("'Work' login", said[0][:80] + said[0]) if False else self.assertIn("Work", said[0])
        self.assertIn("billing the API key", said[0])

    def test_the_init_reads_a_bearer_landing_as_the_stored_login_and_labels_its_own_bucket(self):
        """The environment road (2026-09-14): the launch handed the CLI the stored login's token as a bearer, so an init
        reporting NO key source is that login's landing (a bearer outranks the machine's credentials file, and the
        machine's tokens were not restored beside it)."""
        rec = _rec(self.be.state_dir, "Work", org="Acme", kind="enterprise")
        s = self._sess(1, auth="login", authLogin=rec["id"])
        self._launch_options(s)
        self.be._note_auth_source(s, "none")
        self.assertEqual(s.auth_live, "login", "the stored login rides the environment as a bearer, so a bearer landing IS the login")
        self.assertTrue(s.auth_label.startswith("login:"), s.auth_label)
        self.assertNotEqual(s.auth_label, self.be.api_health.auth_label("none"), "its own bucket, not the machine's")
        self.assertNotEqual(s.auth_label, "login:unknown")
        ah = self.be.api_health
        ah.note_ok(time.time(), auth=s.auth_label, family="fable", sid=s.sid, message_id="m1")
        snap = ah.snapshot(time.time(), uptime_s=100)
        self.assertEqual(snap["buckets"][s.auth_label + "|fable"]["label"], "Work · Acme · enterprise")
        # a machine-login session's helper landing is still the key (unchanged)
        s2 = self._sess(2, auth="login")
        self._launch_options(s2)
        self.be._note_auth_source(s2, "apiKeyHelper")
        self.assertEqual(s2.auth_live, "key")

    def test_a_landing_on_a_key_is_loud_refused_and_cleared_by_a_served_bearer_reply(self):
        rec = _rec(self.be.state_dir, "Work")
        logs = []
        self.be._log = lambda m, problem=False: logs.append((m, problem))
        # two sessions launched on the stored login while it stands: the CLI's init is the EVIDENCE of what each did
        s = self._sess(1, auth="login", authLogin=rec["id"])
        s2 = self._sess(2, auth="login", authLogin=rec["id"])
        self._launch_options(s)
        self._launch_options(s2)
        self.assertEqual((s._launched_login, s2._launched_login), (rec["id"], rec["id"]))
        self.assertIsNone(s.auth_login_live, "no evidence before an init")
        self.assertIsNone(s.snapshot()["authLoginLive"])
        # the first CLI reports a KEY source: it never used the bearer and signed in with a key it found
        self.be._note_auth_source(s, "apiKeyHelper")
        self.assertEqual(s.auth_login_live, "")
        self.assertEqual(s.snapshot()["authLoginLive"], "")
        self.assertTrue(any("token was not used" in m and p for m, p in logs), logs)
        self.assertIn("the token was not used and the CLI signed in with the CLI's apiKeyHelper credential", lg.read_record(self.be.state_dir, rec["id"])["refused"])
        self.assertIn("was refused", self.be.auth_unavailable_why("login", rec["id"]), "every menu leaves it out")
        # the second CLI DID use the bearer (no key source): a served reply there is the deciding event that clears the refusal
        self.be._note_auth_source(s2, "none")
        self.assertEqual(s2.auth_login_live, rec["id"])
        import types
        s2._ah_note_assistant(types.SimpleNamespace(model="claude-opus-5", message_id="m1", parent_tool_use_id=None, error=None))
        self.assertNotIn("refused", lg.read_record(self.be.state_dir, rec["id"]))
        self.assertEqual(self.be.auth_unavailable_why("login", rec["id"]), "")
        # …but a reply on the session that fell back to the machine's login clears nothing (it is not that login's)
        lg.mark_refused(self.be.state_dir, rec["id"], "again")
        s._ah_note_assistant(types.SimpleNamespace(model="claude-opus-5", message_id="m2", parent_tool_use_id=None, error=None))
        self.assertEqual(lg.read_record(self.be.state_dir, rec["id"])["refused"], "again")

    def test_a_landing_on_another_credential_is_refused_named_and_reconnected(self):
        rec = _rec(self.be.state_dir, "Work")
        logs, recon = [], []
        self.be._log = lambda m, problem=False: logs.append((m, problem))
        for word, named in (("/login managed key", "the CLI's /login managed key credential"),
                            ("ANTHROPIC_API_KEY", "the CLI's ANTHROPIC_API_KEY credential"),
                            ("apiKeyHelper", "the CLI's apiKeyHelper credential"), ("user", "the CLI's user credential")):
            lg.clear_refused(self.be.state_dir, rec["id"])
            s = self._sess(9, auth="login", authLogin=rec["id"])
            self._launch_options(s)
            self.assertEqual(s._launched_login, rec["id"])
            s.request_reconnect = lambda defer=True: recon.append(1)
            self.be._note_auth_source(s, word)
            self.assertEqual(s.auth_login_live, "", word)
            self.assertEqual(s._launched_login, "", "this process does not bill the stored login (spend and the ring say so)")
            self.assertIn(named, lg.read_record(self.be.state_dir, rec["id"])["refused"], word)
        self.assertEqual(len(recon), 4, "every wrong landing asks for the reconnect onto the fallback side")
        self.assertTrue(all("reconnecting onto the fallback side" in m for m, p in logs if "token was not used" in m))

    def test_a_wrong_landing_with_nothing_to_fall_to_stays_put_and_reconnects_at_most_once(self):
        rec = _rec(self.be.state_dir, "Work")
        logs, recon = [], []
        self.be._log = lambda m, problem=False: logs.append((m, problem))
        # a box with no helper and no signed-in machine login: a relaunch would carry the same failing helper
        self.be.key_state = lambda: "missing"
        self.be.login_ok = lambda: False
        s = self._sess(3, auth="login", authLogin=rec["id"])
        self._launch_options(s)
        s.request_reconnect = lambda defer=True: recon.append(1)
        self.be._note_auth_source(s, "apiKeyHelper")     # a key word: the wrong landing
        self.assertEqual(self.be.pick_fall("login", rec["id"]), "", "the probe: nothing to fall to")
        self.assertEqual(recon, [], "an identical relaunch is never asked for")
        self.assertEqual((s.auth_login_live, s._launched_login), ("", ""), "refused and flagged where it landed")
        self.assertIn("refused", lg.read_record(self.be.state_dir, rec["id"]))
        rows = [m for m, p in logs if "token was not used" in m and p]
        self.assertEqual(len(rows), 1, logs)
        self.assertIn("nothing to fall to", rows[0])
        self.assertNotIn("reconnecting", rows[0])
        # the machine's login back: one reconnect per session however many inits report the wrong landing
        lg.clear_refused(self.be.state_dir, rec["id"])
        self.be.login_ok = lambda: True
        s2 = self._sess(4, auth="login", authLogin=rec["id"])
        self._launch_options(s2)
        s2.request_reconnect = lambda defer=True: recon.append(2)
        self.be._note_auth_source(s2, "apiKeyHelper")
        self.assertEqual(recon, [2])
        self.assertTrue(any("reconnecting onto the fallback side (login)" in m for m, p in logs), logs)
        s2._launched_login = rec["id"]           # a second init reporting the same wrong landing
        self.be._note_auth_source(s2, "apiKeyHelper")
        self.assertEqual(recon, [2], "asked once")
        self.assertTrue(any("already reconnected once" in m for m, p in logs), logs)

    def test_api_health_files_under_the_credential_that_answered_not_the_pick(self):
        rec = _rec(self.be.state_dir, "Work")
        self.be._log = lambda m, problem=False: None
        picked = self.be.api_health.auth_label("none", login_id=rec["id"], display=self.be.login_display(rec["id"]))
        machine = self.be.api_health.auth_label("none")
        self.assertNotEqual(picked, machine)
        # the bearer answered (no key source): the bucket is the stored login's
        s = self._sess(5, auth="login", authLogin=rec["id"])
        self._launch_options(s)
        self.be._note_auth_source(s, "none")
        self.assertEqual(s.auth_label, picked)
        # the CLI took a key instead: the key's bucket, never the pick's
        s = self._sess(6, auth="login", authLogin=rec["id"])
        self._launch_options(s)
        s.request_reconnect = lambda defer=True: None
        self.be._note_auth_source(s, "apiKeyHelper")
        self.assertTrue(s.auth_label.startswith("key"), s.auth_label)
        self.assertNotEqual(s.auth_label, picked)
        self.assertNotEqual(s.auth_label, machine)
        # the fallback relaunch (the record now refused, the key does the work) files under the key's bucket
        s = self._sess(7, auth="login", authLogin=rec["id"])
        self._launch_options(s)
        self.assertEqual(s._launched_login, "", "the refused record falls to the key")
        self.be._note_auth_source(s, "apiKeyHelper")
        self.assertTrue(s.auth_label.startswith("key"), s.auth_label)
        self.assertNotEqual(s.auth_label, picked)

    def test_a_relaunch_without_the_token_clears_the_live_evidence_and_persists_it(self):
        rec = _rec(self.be.state_dir, "Work")
        self.be._log = lambda m, problem=False: None
        sid = self.be.spawn("n", "/tmp", auth="login:" + rec["id"])
        s = sb.SdkSession(self.be, sb.read_reg(self.be.state_dir, sid))
        self._launch_options(s)
        self.assertEqual(s._launched_login, rec["id"])
        self.be._note_auth_source(s, "none")
        self.assertEqual(s.auth_login_live, rec["id"])
        reg = sb.read_reg(self.be.state_dir, sid)
        self.assertEqual((reg.get("launchedLogin"), reg.get("authLoginLive")), (rec["id"], rec["id"]), "persisted with the evidence")
        # a hosted re-attach after a kernel restart replays no init: the fresh object restores both
        s_re = sb.SdkSession(self.be, reg)
        self.assertEqual((s_re._launched_login, s_re.auth_login_live), (rec["id"], rec["id"]))
        # the login goes unavailable, then a reconnect for a model change relaunches on the fall: the old evidence goes
        lg.mark_refused(self.be.state_dir, rec["id"], "refused")
        self._launch_options(s)
        self.assertEqual(s._launched_login, "", "fell to the key")
        self.assertIsNone(s.auth_login_live, "no evidence from this process yet")
        self.assertIsNone(s.snapshot()["authLoginLive"])
        reg = sb.read_reg(self.be.state_dir, sid)
        self.assertEqual((reg.get("launchedLogin"), reg.get("authLoginLive")), ("", None))
        # so a revoked KEY's auth error on this session refuses nothing (the feed's gate reads the evidence)
        row = {"authLogin": rec["id"], "authLabel": "Work", "authLoginLive": s.snapshot()["authLoginLive"]}
        self.assertEqual(km._login_refusal_label(row, {"authErr": True, "text": "invalid x-api-key"}), "")
        # and a reply served on the fallback clears nothing
        import types
        s._ah_note_assistant(types.SimpleNamespace(model="claude-opus-5", message_id="m3", parent_tool_use_id=None, error=None))
        self.assertEqual(lg.read_record(self.be.state_dir, rec["id"])["refused"], "refused")
        # a wrong landing's evidence is persisted too ("" = another credential answered)
        lg.clear_refused(self.be.state_dir, rec["id"])
        self._launch_options(s)
        s.request_reconnect = lambda defer=True: None
        self.be._note_auth_source(s, "apiKeyHelper")
        self.assertEqual(sb.read_reg(self.be.state_dir, sid).get("authLoginLive"), "")
        self.assertEqual(sb.read_reg(self.be.state_dir, sid).get("launchedLogin"), "")

    def test_an_attach_to_a_live_host_keeps_the_evidence_and_the_launched_login(self):
        rec = _rec(self.be.state_dir, "Work")
        self.be._log = lambda m, problem=False: None
        sid = self.be.spawn("n", "/tmp", auth="login:" + rec["id"])
        s = sb.SdkSession(self.be, sb.read_reg(self.be.state_dir, sid))
        # a kernel child's launch: the options build, then the connect's stamp from them
        self._launch_options(s)
        self.assertEqual((s._options_login, s._launched_login, s.auth_login_live), (rec["id"], rec["id"], None))
        self.be._note_auth_source(s, "none")
        reg = sb.read_reg(self.be.state_dir, sid)
        self.assertEqual((reg["launchedLogin"], reg["authLoginLive"]), (rec["id"], rec["id"]))
        # the kernel restarts while a host keeps the CLI running; the reg names that CLI (the identity the hello's decision
        # compares against), and the new kernel's session restores the evidence from the row
        self.be._update_reg(sid, spawnedAt=1700000000, spawnedAtCli="4242:a1")
        s2 = sb.SdkSession(self.be, sb.read_reg(self.be.state_dir, sid))
        self.assertEqual((s2._launched_login, s2.auth_login_live), (rec["id"], rec["id"]), "restored from the row")
        # meanwhile another session got the record refused: TODAY's availability would carry no login at all
        lg.mark_refused(self.be.state_dir, rec["id"], "refused elsewhere")
        self.be._options(s2, dict)
        self.assertEqual(s2._options_login, "", "the options would fall to the key")
        # the host's hello names the CLI the reg already names: nothing is stamped
        base = {"host": {"pid": 7, "start": "h"}, "journal": {"next": 0}, "parked": [], "inflight": 0}
        self.be._on_host_hello(s2, dict(base, cli={"pid": 4242, "start": "a1", "fsid": sid, "spawnedAt": 1700000000, "login": ""}))
        self.assertEqual((s2._launched_login, s2.auth_login_live), (rec["id"], rec["id"]),
                         "an attach replays no init: the evidence about the running CLI stands, and its login is not recomputed")
        reg2 = sb.read_reg(self.be.state_dir, sid)
        self.assertEqual((reg2["launchedLogin"], reg2["authLoginLive"], reg2["spawnedAt"]), (rec["id"], rec["id"], 1700000000),
                         "the row keeps it for the next restart")
        # so the feed's gate still speaks for the login, and a served reply on it still clears
        row = {"authLogin": rec["id"], "authLabel": "Work", "authLoginLive": s2.snapshot()["authLoginLive"]}
        self.assertEqual(km._login_refusal_label(row, {"authErr": True, "text": "invalid x-api-key"}), "Work")
        import types
        s2._ah_note_assistant(types.SimpleNamespace(model="claude-opus-5", message_id="m4", parent_tool_use_id=None, error=None))
        self.assertNotIn("refused", lg.read_record(self.be.state_dir, rec["id"]))
        # a hello naming a FRESH CLI (a host spawned for this session, whose handshake may have failed before this attach):
        # the launch login is the one the spawn's spec carried (cli.login), not the one today's options would pick, and the
        # init evidence resets to none
        self.be._on_host_hello(s2, dict(base, cli={"pid": 4343, "start": "b1", "fsid": sid, "spawnedAt": 1700005000, "login": rec["id"]}))
        self.assertEqual((s2._launched_login, s2.auth_login_live), (rec["id"], None), "the login the launch used; the evidence reset")
        reg3 = sb.read_reg(self.be.state_dir, sid)
        self.assertEqual((reg3["launchedLogin"], reg3["authLoginLive"], reg3["spawnedAt"], reg3["spawnedAtCli"]),
                         (rec["id"], None, 1700005000, "4343:b1"))
        # a kernel child after all (the hosts file off, no lease): the host road ends at a kernel child, and the connect's
        # stamp is from the options built for this connect
        import asyncio
        (Path(self.be.state_dir) / "session-hosts").write_text("off\n")
        self.assertIsNone(asyncio.run(self.be._host_transport_for(s2, {}, ())), "the host road ends at a kernel child")
        self.be._stamp_launch_login(s2)
        self.assertEqual((s2._launched_login, s2.auth_login_live), ("", None), "launched after all: stamped from the options")
        reg4 = sb.read_reg(self.be.state_dir, sid)
        self.assertEqual((reg4["launchedLogin"], reg4["authLoginLive"]), ("", None))

    def test_the_once_flag_resets_on_a_new_pick_and_on_a_bearer_answered_init(self):
        rec = _rec(self.be.state_dir, "Work")
        recon = []
        self.be._log = lambda m, problem=False: None
        sid = self.be.spawn("n", "/tmp", auth="login:" + rec["id"])
        s = sb.SdkSession(self.be, sb.read_reg(self.be.state_dir, sid))
        self.be.sessions[sid] = s
        s.request_reconnect = lambda defer=True: recon.append(1)
        self._launch_options(s)
        self.be._note_auth_source(s, "apiKeyHelper")  # the wrong landing (a key word): the one reconnect
        self.assertTrue(s._wrong_landing_reconnected)
        self.assertEqual(len(recon), 1)
        # the user fixes the command and picks the login again: the fall may be taken again
        lg.clear_refused(self.be.state_dir, rec["id"])
        self.assertTrue(self.be.set_auth(sid, "login:" + rec["id"]))
        self.assertFalse(s._wrong_landing_reconnected)
        n0 = len(recon)
        self._launch_options(s)
        self.assertEqual(s._launched_login, rec["id"])
        self.be._note_auth_source(s, "apiKeyHelper")
        self.assertEqual(len(recon), n0 + 1, "the documented fall is taken again after a new pick")
        # a bearer-answered init (no key source) resets it as well
        lg.clear_refused(self.be.state_dir, rec["id"])
        self._launch_options(s)
        self.be._note_auth_source(s, "none")
        self.assertFalse(s._wrong_landing_reconnected)

    def test_the_seed_skip_names_a_dead_remembered_stored_login(self):
        rec = _rec(self.be.state_dir, "Work")
        lg.mark_refused(self.be.state_dir, rec["id"], "refused")
        sb.write_sdk_default(self.be.state_dir, auth="login", authLogin=rec["id"])
        logs = []
        self.be._log = lambda m, problem=False: logs.append(m)
        sid = self.be.spawn("n", "/tmp")
        self.assertNotIn("auth", sb.read_reg(self.be.state_dir, sid), "a dead remembered pick seeds nothing")
        self.assertTrue(any("Work" in m and "start unpicked" in m for m in logs), logs)

    def test_spend_folds_by_login(self):
        rec = _rec(self.be.state_dir, "Work")
        self.be._record_spend(0.02, {"input_tokens": 100, "output_tokens": 40}, keyed=False, sid=SID, login=rec["id"])
        self.be._record_spend(0.03, {"input_tokens": 10, "output_tokens": 5}, keyed=True, sid=SID)
        d = json.loads((Path(self.d) / "spend.json").read_text())
        day = d["days"][time.strftime("%Y-%m-%d")]
        self.assertEqual(day["byLogin"], {rec["id"]: {"usd": 0.02, "turns": 1, "tok": 140}}, "the key turn is carried past, not folded in")
        self.assertEqual(day["usd"], 0.05)


class UsersShape(_Backend):
    """The user's own setup (2026-09-11), the exact shape: the PERSONAL account on the ordinary Claude Code login
    as now (Max, so 'personal'), and the ENTERPRISE account as a stored login whose command reads a setup-token
    from their secret manager. Both listed with their kinds, each pickable per session, the stored one's launch carrying
    its helper and the machine one's launch exactly as before."""

    def setUp(self):
        super().setUp()
        self.home = tempfile.mkdtemp()
        self._home = os.environ.get("HOME")
        os.environ["HOME"] = self.home
        self._acct, self._kind = dict(km._ACCT_CACHE), dict(km._KIND_CACHE)
        Path(self.home, ".claude.json").write_text(json.dumps({"oauthAccount": {
            "accountUuid": "11111111-2222-3333-4444-555555555555", "emailAddress": "user@example.com"}}))
        Path(self.cfg, ".credentials.json").write_text(json.dumps({"claudeAiOauth": {
            "accessToken": _token_shaped(), "subscriptionType": "max"}}))
        km._ACCT_CACHE["mtime"] = -2.0
        km._KIND_CACHE["mtime"] = -2.0
        self.ent_tok = _token_shaped()
        self.ent = _rec(self.be.state_dir, "Enterprise", org="Acme", kind="enterprise",
                        tokenCmd="printf '%%s' '%s'" % self.ent_tok)   # a command that prints the synthetic bearer (the environment road)
        self.saved = (km._sdk, km.jd._cred.helper_source)
        km._sdk = lambda: self.be
        self._state = km.jd.STATE
        km.jd._rebind_state(Path(self.d))

    def tearDown(self):
        km._sdk, km.jd._cred.helper_source = self.saved
        km.jd._rebind_state(self._state)
        os.environ["HOME"] = self._home
        km._ACCT_CACHE.update(self._acct)
        km._KIND_CACHE.update(self._kind)
        super().tearDown()

    def test_both_accounts_listed_and_pickable_per_session(self):
        logins = km._auth_avail()["logins"]
        self.assertEqual([(l["label"], l["available"]) for l in logins],
                         [("user@example.com · personal", True), ("Enterprise · Acme · enterprise", True)])
        self.assertEqual(logins[1]["value"], "login:" + self.ent["id"])
        personal = self.be.spawn("notes", "/tmp", auth="login")
        enterprise = self.be.spawn("api", "/tmp", auth="login:" + self.ent["id"])
        sp = sb.SdkSession(self.be, sb.read_reg(self.be.state_dir, personal))
        se = sb.SdkSession(self.be, sb.read_reg(self.be.state_dir, enterprise))
        kwp, kwe = self.be._options(sp, dict), self.be._options(se, dict)
        self.assertEqual(self._settings_of(kwp).get("apiKeyHelper"), "", "personal: the ordinary login, as now")
        self.assertEqual(self._settings_of(kwe).get("apiKeyHelper"), "", "enterprise: the helper disabled too")
        self.assertEqual(kwe["env"].get("CLAUDE_CODE_OAUTH_TOKEN"), self.ent_tok, "…and the enterprise token in its environment (the environment road)")
        self.assertEqual((sp.snapshot()["authLabel"], se.snapshot()["authLabel"]), ("", "Enterprise · Acme · enterprise"))
        # the judges follow each session's account
        (jd.SDKDIR).mkdir(parents=True, exist_ok=True)
        self.assertEqual(jd._judge_auth(personal), "login")
        self.assertEqual(jd._judge_auth(enterprise), "login:" + self.ent["id"])
        # switching a running session's pick, both ways
        self.assertTrue(self.be.set_auth(personal, "login:" + self.ent["id"]))
        self.assertEqual(sb.read_reg(self.be.state_dir, personal)["authLogin"], self.ent["id"])
        self.assertTrue(self.be.set_auth(personal, "login"))
        self.assertEqual(sb.read_reg(self.be.state_dir, personal)["authLogin"], "")


class Doors(unittest.TestCase):
    """The credential names stay refused at every door; /logins lists, adds and removes; the op routes accept the pick."""

    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), km.Handler)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        self.state = km.jd.STATE
        for p in lg.logins_dir(self.state).glob("*.json") if lg.logins_dir(self.state).exists() else []:
            p.unlink()

    tearDown = setUp

    def _req(self, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, path), data=data,
                                     headers={"Content-Type": "application/json", "X-Romp-Token": os.environ["ROMP_SERVE_TOKEN"]})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    def test_a_client_payload_naming_a_credential_is_still_refused_for_a_stored_login_pick(self):
        tok = _token_shaped()
        for auth in ("", "key", "login", "login:" + ZID):
            a = km._env_error({"CLAUDE_CODE_OAUTH_TOKEN": tok}, auth)
            b = sb.env_request_error({"CLAUDE_CODE_OAUTH_TOKEN": tok}, auth)
            self.assertEqual(a, b)
            self.assertIn("CLAUDE_CODE_OAUTH_TOKEN is reserved", a)
            self.assertNotIn(tok, a)

    def test_list_add_and_remove(self):
        st, d = self._req("/logins")
        self.assertEqual((st, d["ok"], d["logins"]), (200, True, []))
        self.assertIn("machine", d)
        # a store's shorthand is not a door (the user 2026-09-13): a body with a reference and no command is refused
        st, d = self._req("/logins", {"add": {"label": "Work", "opRef": "op://Vault/romp login Work/credential", "kind": "team"}})
        self.assertEqual(st, 400, "no shorthand: only tokenCmd adds a login")
        self.assertIn("a token command", d["error"])
        st, d = self._req("/logins", {"add": {"label": "Work", "tokenCmd": "token-read 'romp login Work'", "kind": "team"}})
        self.assertEqual((st, d["ok"]), (200, True))
        lid = d["id"]
        self.assertTrue(lg.ID_RE.match(lid))
        self.assertEqual(d["display"], "Work · enterprise")
        self.assertEqual(lg.read_record(self.state, lid)["tokenCmd"], "token-read 'romp login Work'", "the command is recorded verbatim")
        st, d = self._req("/logins")
        self.assertEqual([r["label"] for r in d["logins"]], ["Work"])
        self.assertEqual(d["logins"][0]["hasCmd"], True)
        self.assertNotIn("token-read", json.dumps(d), "the command itself never rides the list")
        st, d = self._req("/logins", {"add": {"label": "Work", "tokenCmd": "cat x"}})
        self.assertEqual((st, d["ok"]), (200, False))
        self.assertIn("exists", d["error"])
        st, d = self._req("/logins", {"add": {"label": "Bad", "tokenCmd": "two\nlines"}})
        self.assertEqual(st, 400)
        st, d = self._req("/logins", {"add": {"tokenCmd": "cat x"}})
        self.assertEqual(st, 400)
        st, d = self._req("/logins", {"add": {"label": "Pasted", "tokenCmd": "printf %s " + _token_shaped()}})
        self.assertEqual(st, 400, "a credential pasted as the command is refused at the door")
        self.assertIn("looks like it carries the credential", d["error"])
        st, d = self._req("/logins", {"add": {"label": "Plain", "tokenCmd": "cat ~/.secrets/enterprise-token"}})
        self.assertEqual((st, d["ok"]), (200, True), "any command that prints the token")
        self.assertTrue(lg.remove(self.state, d["id"]))
        st, d = self._req("/logins", {"remove": "Nope"})
        self.assertEqual((st, d["ok"]), (200, False))
        st, d = self._req("/logins", {"remove": "Work"})
        self.assertEqual((st, d["ok"], d["removed"]), (200, True, lid))
        self.assertIsNone(lg.read_record(self.state, lid))
        st, d = self._req("/logins", {})
        self.assertEqual(st, 400)

    def test_the_op_doors_take_the_stored_login_value(self):
        src = open(os.path.join(BIN, "romp-kernel")).read()
        self.assertIn('elif t == "setAuth" and lg.parse_pick(msg.get("value"))[0]:', src)
        self.assertIn('if not lg.parse_pick(value)[0]:', src)
        self.assertEqual(src.count('auth=(a if lg.parse_pick(a)[0] else "")'), 2, "both create doors")
        self.assertIn('msg.get("type") == "loginRemove"', src)
        self.assertIn('jd._API_HEALTH_NOTE_FN = _judge_api_health_note', src)


    def test_an_auth_error_refuses_the_stored_login_only_when_its_helper_answered(self):
        err = {"authErr": True, "text": "invalid x-api-key"}
        row = {"authLogin": ZID, "authLabel": "Work", "authLoginLive": ZID}
        self.assertEqual(km._login_refusal_label(row, err), "Work", "the helper answered: the error is the login's")
        self.assertEqual(km._login_refusal_label(dict(row, authLoginLive=""), err), "",
                         "the CLI signed in with something else: the fallback's error says nothing about the login")
        self.assertEqual(km._login_refusal_label(dict(row, authLoginLive=None), err), "",
                         "before an init, or a launch that fell to the key under a managed helper: never tried")
        self.assertEqual(km._login_refusal_label(row, {"authErr": False, "text": "overloaded"}), "")
        self.assertEqual(km._login_refusal_label({}, err), "")
        src = open(os.path.join(ROOT, "kernel", "kernel.py")).read()
        self.assertEqual(src.count("_auth_login_lbl = _login_refusal_label(tm or {}, aerr)"), 1,
                         "the feed's one refusal site reads the gate")


class Judges(unittest.TestCase):
    """The judges bill the judged session's login, stamp their rows and feed the ring under its bucket."""

    def setUp(self):
        self.state = km.jd.STATE
        km.jd.SDKDIR.mkdir(parents=True, exist_ok=True)
        self.rec_tok = _token_shaped()
        self.rec = _rec(self.state, "Work", org="Acme", kind="enterprise", tokenCmd="printf '%%s' '%s'" % self.rec_tok)
        (km.jd.SDKDIR / (SID + ".json")).write_text(json.dumps({"sid": SID, "auth": "login", "authLogin": self.rec["id"]}))

    def tearDown(self):
        (km.jd.SDKDIR / (SID + ".json")).unlink(missing_ok=True)
        lg.remove(self.state, self.rec["id"])

    def test_the_call_bills_the_stored_login_through_its_token_in_the_childs_environment(self):
        """The environment road (2026-09-14): the child's overlay disables the box's helper as for the machine's login, and
        its environment carries the token the record's command printed, never the machine's own; a command that fails is a
        CredentialError the call notes in its own words."""
        self.assertEqual(jd._judge_auth(SID), "login:" + self.rec["id"])
        cmd = jd._judge_cmd("sonnet", "SYS", None, auth="login:" + self.rec["id"])
        overlay = json.loads(cmd[cmd.index("--settings") + 1])
        self.assertEqual(overlay["apiKeyHelper"], "", "the box's helper disabled, as for the machine's login")
        plain = jd._judge_cmd("sonnet", "SYS", None, auth="login")
        self.assertEqual(json.loads(plain[plain.index("--settings") + 1])["apiKeyHelper"], "", "the machine's login: unchanged")
        machine_tok = _token_shaped()
        saved = jd._LOGIN_AUTH_ENV_FN
        jd._LOGIN_AUTH_ENV_FN = lambda: {"CLAUDE_CODE_OAUTH_TOKEN": machine_tok}
        try:
            env = jd._judge_env("triage", "login:" + self.rec["id"])
            self.assertEqual(env.get("CLAUDE_CODE_OAUTH_TOKEN"), self.rec_tok, "the stored login's token, from its command")
            self.assertNotEqual(env.get("CLAUDE_CODE_OAUTH_TOKEN"), machine_tok, "never the machine's token beside it")
            self.assertEqual(jd._judge_env("triage", "login").get("CLAUDE_CODE_OAUTH_TOKEN"), machine_tok)
            bad = _rec(self.state, "Bad", tokenCmd="false")   # a command that exits non-zero
            with self.assertRaises(jd._cred.CredentialError) as cm:
                jd._judge_env("triage", "login:" + bad["id"])
            self.assertEqual(str(cm.exception), "the token command failed (non-zero exit)")
            with self.assertRaises(jd._cred.CredentialError) as cm:
                jd._judge_env("triage", "login:" + ZID)
            self.assertEqual(str(cm.exception), "no stored login with that id")
            lg.remove(self.state, bad["id"])
        finally:
            jd._LOGIN_AUTH_ENV_FN = saved
        self.assertTrue(jd._is_login_auth("login:" + self.rec["id"]) and jd._is_login_auth("login") and not jd._is_login_auth("key"))
        self.assertFalse(hasattr(jd, "_login_helper_cmd"), "the helper road is gone")

    def test_a_refused_stored_login_never_runs_a_judge_call(self):
        import io, contextlib
        lg.mark_refused(self.state, self.rec["id"], "OAuth token has expired")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            first = jd._judge_auth(SID)
            second = jd._judge_auth(SID)
        self.assertIn(first, ("key", "login"), "the session's own fallback, never the refused login")
        self.assertEqual(first, second)
        self.assertEqual(err.getvalue().count("bills a stored login that is unavailable"), 1, "said once per session")
        self.assertIn("was refused", err.getvalue())
        lg.clear_refused(self.state, self.rec["id"])
        self.assertEqual(jd._judge_auth(SID), "login:" + self.rec["id"], "cleared: the login is run as again")

    def test_the_latch_and_the_usage_row_say_which_login(self):
        jd._auth_down_mark(SID, "login:" + self.rec["id"], "OAuth token has expired")
        row = jd._auth_down_map()[SID]
        self.assertEqual((row["mode"], row["login"]), ("login", self.rec["id"]))
        jd._auth_down_clear(SID)
        usage = km.jd.STATE / "judge-usage.jsonl"
        before = usage.read_text() if usage.exists() else ""
        jd._log_judge_usage("planner", "triage", "opus", SID, {"usage": {}, "duration_ms": 5, "total_cost_usd": 0.01}, 1.0, 2.0,
                            auth="login:" + self.rec["id"])
        last = json.loads(usage.read_text()[len(before):].strip().splitlines()[-1])
        self.assertEqual(last["auth"], "login:" + self.rec["id"])
        jd._log_judge_usage("planner", "triage", "opus", SID, {"usage": {}, "duration_ms": 5, "total_cost_usd": 0.01}, 1.0, 2.0)
        last = json.loads(usage.read_text().strip().splitlines()[-1])
        self.assertNotIn("auth", last, "an unstamped call writes the row it always wrote")

    def test_the_ring_source_files_under_the_login_bucket(self):
        cfg = tempfile.mkdtemp()
        d = tempfile.mkdtemp()
        be = sb.SdkBackend(d, "/bin/true", lambda *a, **k: None)
        _rec(d, "Work", id=self.rec["id"], org="Acme", kind="enterprise")
        saved = km._sdk
        km._sdk = lambda: be
        try:
            calls = []
            jd._API_HEALTH_NOTE_FN = lambda *a: calls.append(a)
            jd._note_api_health("ok", "login:" + self.rec["id"], "claude-opus-5", "", SID)
            jd._note_api_health("gaveup", "codex", "gpt", "err", SID)
            self.assertEqual(calls, [("ok", "login:" + self.rec["id"], "claude-opus-5", "", SID)], "codex calls are never filed")
            km._judge_api_health_note("ok", "login:" + self.rec["id"], "claude-opus-5", "", SID)
            km._judge_api_health_note("gaveup", "login:" + self.rec["id"], "claude-opus-5", "API Error: 429 rate limit", SID)
            km._judge_api_health_note("ok", "key", "claude-opus-5", "", SID)
            snap = be.api_health.snapshot(time.time(), uptime_s=100)
            labels = {k.split("|")[0]: v for k, v in snap["buckets"].items()}
            stored = [k for k in labels if k.startswith("login:") and labels[k]["label"] == "Work · Acme · enterprise"]
            self.assertEqual(len(stored), 1, snap["buckets"].keys())
            b = labels[stored[0]]
            self.assertEqual(b["family"], sb.model_family("claude-opus-5"))
            w = b["windows"]["900"] if "900" in b["windows"] else list(b["windows"].values())[-1]
            self.assertEqual((w["requests"], w["gaveUp"]), (2, 1))
            self.assertIn("key:helper", labels, "a key call files under the helper's bucket, unchanged")
            lg.mark_refused(d, self.rec["id"], "refused once")
            km._judge_api_health_note("ok", "login:" + self.rec["id"], "claude-opus-5", "", SID)
            self.assertEqual(lg.read_record(d, self.rec["id"])["refused"], "refused once",
                             "a served judge call clears nothing: its envelope carries no evidence of which login answered")
        finally:
            km._sdk = saved
            jd._API_HEALTH_NOTE_FN = None

    def test_the_rollup_splits_by_the_account_billed(self):
        src = inspect.getsource(km._judge_usage)
        self.assertIn('by_auth.setdefault(o.get("auth") or "unstamped", blank())', src)
        self.assertIn('"byAuth": by_auth', src)


class SpendDetailByLogin(unittest.TestCase):
    def test_the_payload_carries_the_by_login_rows_and_each_sessions_login(self):
        d = tempfile.mkdtemp()
        be = sb.SdkBackend(d, "/bin/true", lambda *a, **k: None)
        rec = _rec(d, "Work", org="Acme")
        saved_state, saved_sdk = km.jd.STATE, km._sdk
        km.jd._rebind_state(Path(d)) if hasattr(km.jd, "_rebind_state") else None
        km._sdk = lambda: be
        try:
            day = time.strftime("%Y-%m-%d")
            (Path(d) / "spend.json").write_text(json.dumps({"days": {day: {"usd": 0.05, "turns": 2, "tokIn": 110, "tokOut": 45, "tokCacheR": 0, "tokCacheW": 0,
                                                                       "bySid": {SID: {"usd": 0.05, "turns": 2, "tok": 155}},
                                                                       "byLogin": {rec["id"]: {"usd": 0.02, "turns": 1, "tok": 140}}}},
                                                             "hours": {}}))
            sb.write_reg(Path(d), SID, {"sid": SID, "name": "web", "cwd": "/tmp", "auth": "login", "authLogin": rec["id"], "alive": True})
            p = km._spend_detail_local(now=time.time())
            self.assertEqual(p["byLogin"], [{"id": rec["id"], "label": "Work · Acme", "usd": 0.02, "tok": 140, "turns": 1}])
            self.assertEqual(p["sessions"][0]["login"], "Work · Acme")
        finally:
            km._sdk = saved_sdk
            if hasattr(km.jd, "_rebind_state"):
                km.jd._rebind_state(saved_state)


class Documentation(unittest.TestCase):
    def test_the_reference_says_the_three_plain_things(self):
        import re
        doc = re.sub(r"\s+", " ", open(os.path.join(ROOT, "docs", "reference.md"), encoding="utf-8").read())
        self.assertIn("### Several Claude logins", doc)
        self.assertIn("lives wherever the user keeps it, nowhere in romp", doc)
        self.assertIn("Romp assumes nothing about where it is kept; it only runs the recorded command", doc)
        self.assertIn("works exactly as today: the ordinary Claude Code login and the API key path are untouched", doc)
        self.assertIn("The judges bill the SAME account as the session they judge", doc)
        self.assertIn("A pasted token's label is the user's word", doc)
        self.assertIn("`romp login add <label>", doc)
        self.assertIn("`login:<salted digest of the id>`", doc)
        self.assertIn("- `label`: the display label of the stored login", doc)


if __name__ == "__main__":
    unittest.main()
