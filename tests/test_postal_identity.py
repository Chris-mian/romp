#!/usr/bin/env python3
"""Postal must resolve THIS session's identity from CLAUDE_CODE_SESSION_ID (the harness's reliable
per-session fsid), never from the process's surroundings. The user 2026-06-24 hit the failure: an SDK
session whose MCP had been started under another session's leftover process tree sent mail AS that
other (isolated) session and was wrongly blocked as isolated, while the timeline icon (keyed on the real
fsid) correctly showed it un-isolated. Synthetic only — placeholder ids.

A CODEX session's shell carries no CLAUDE_CODE_SESSION_ID and no romp id at all, only CODEX_THREAD_ID
(Codex's own id for the thread), so every `romp mail send|peek|inbox` from one was refused as anonymous
(2026-09-15, reported from inside a Codex session) although the kernel's Codex backend records the mapping
in its registry (<state>/codex/registry.json: rows keyed by the STABLE romp sid, each carrying "tid" = the
thread id). The backend runs ONE app-server for every thread, so a CLAUDE_CODE_SESSION_ID exported into that
process would sign every Codex session's mail as one sender; the resolution is per command instead, in
_self_id_why → _codex_self_id, and fails CLOSED for anything but exactly one live, well-formed row: (None, why).
The resolver says nothing itself; the command that refuses on the missing identity prints `why`, and a Codex
shell whose lookup failed is refused OUTRIGHT, `send --from <label>` included (the label is a door for a caller
with no session, and a session with a broken identity walking through it would mail as a script and hide the
bug), while a shell with NEITHER variable keeps the label. CodexSelfIdentity below pins that: two concurrent
sessions → two identities, each signing, reading and isolation-checked as its own stable sid; unknown /
ambiguous / ended / missing / unreadable / not JSON / malformed key / blank variable → refused with its own
sentence, and never through --from; the Claude variable wins when both are set, whatever the registry would have
said; recall needs the sender's identity like inbox, sent and working do (a recall is of the caller's OWN mail, and
the bus answers an empty from_id with a bare 400 "missing from_id", which is what a broken Codex shell used to hear)
and refuses with the reason; `agents`, which needs no identity, says nothing about it.
"""
import contextlib
import io
import json
import os
import unittest
from pathlib import Path
from romp_load import load_source
import tempfile

from tests.conftest import restore_env

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "bin")
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
pm = load_source("romp_postal_id", os.path.join(BIN, "romp-postal-service"))

FSID = "11111111-2222-3333-4444-555555555555"


class SelfIdentity(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.get("CLAUDE_CODE_SESSION_ID")
        # the second identity source (a Codex shell's variable) must be absent too, or a run launched from
        # inside a Codex session resolves an identity in the "env absent" case below
        self._codex = os.environ.pop("CODEX_THREAD_ID", None)

    def tearDown(self):
        if self._env is None:
            os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
        else:
            os.environ["CLAUDE_CODE_SESSION_ID"] = self._env
        restore_env("CODEX_THREAD_ID", self._codex)

    def test_my_id_is_the_env_session_id(self):
        # the env IS the identity — the bus has nothing else to fall back to, by design (an identity read
        # from the process's surroundings was the wrong id for an SDK session; the env is always right).
        os.environ["CLAUDE_CODE_SESSION_ID"] = FSID
        self.assertEqual(pm.my_id(), FSID)

    def test_my_id_is_none_when_env_absent(self):
        os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
        self.assertIsNone(pm.my_id())


CODEX_WEB = "11111111-2222-3333-4444-5555555555aa"   # a Codex session named web, native thread "thread-web"
CODEX_API = "11111111-2222-3333-4444-5555555555bb"   # a second one running beside it: api, "thread-api"
CODEX_OLD = "11111111-2222-3333-4444-5555555555cc"   # an ended one


# the registry's path derived here from the state root (not read off the module), so that on a source without
# the resolver the tests below fail on the wrong ANSWER, (None, None), rather than on a missing attribute
REG = pm.STATE.parent / "codex" / "registry.json"


def _row(tid, name, dead=False):
    """A Codex registry row of the shape the kernel's backend writes (its _registry_snapshot). Synthetic."""
    return {"tid": tid, "name": name, "cwd": "/tmp/notes-api", "model": "", "effort": "", "mode": "sandboxed",
            "dead": dead, "queue": [], "note": "", "color": "", "launchError": None}


TWO = {CODEX_WEB: _row("thread-web", "web"), CODEX_API: _row("thread-api", "api")}   # two live sessions, two threads


class CodexSelfIdentity(unittest.TestCase):
    """CODEX_THREAD_ID → the stable romp sid, through the Codex registry, per command (the module docstring)."""

    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "ROMP_SESSIONS_FILE")}
        os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
        os.environ.pop("CODEX_THREAD_ID", None)
        # the kernel's GET /sessions as the seam: a Codex row's id IS the stable sid, and so is its lastSid
        sess = Path(os.environ["XDG_STATE_HOME"]) / "codex-identity-sessions.json"
        sess.write_text(json.dumps([
            {"id": CODEX_WEB, "name": "web", "dir": "/tmp/notes-api", "state": "idle", "working": "",
             "lastSid": CODEX_WEB, "backend": "codex"},
            {"id": CODEX_API, "name": "api", "dir": "/tmp/notes-api", "state": "idle", "working": "",
             "lastSid": CODEX_API, "backend": "codex"}]))
        os.environ["ROMP_SESSIONS_FILE"] = str(sess)
        REG.parent.mkdir(parents=True, exist_ok=True)
        self.err = io.StringIO()
        self._saved = (pm.ensure, pm._http, pm._mail_off_why)
        # the transport, stubbed: every command's HTTP recorded, nothing sent (a bus answer of the shape each reads)
        self.calls = []
        pm.ensure = lambda: True
        pm._http = self._transport

    def tearDown(self):
        pm.ensure, pm._http, pm._mail_off_why = self._saved
        for k, v in self._env.items():
            restore_env(k, v)
        for f in (REG, pm.SESSION_FLAGS):
            if f.is_dir():
                f.rmdir()
            elif f.exists():
                f.unlink()

    def _transport(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if path == "/send":
            return {"note": "delivered to '%s'" % payload["to"]}
        return {"messages": [], "agents": [], "sent": [], "removed": [], "kept": []}

    def _registry(self, rows):
        REG.write_text(json.dumps(rows, indent=1))

    def _as(self, tid):
        """The environment of thread `tid`'s shell; None clears it (a shell with neither variable)."""
        if tid is None:
            os.environ.pop("CODEX_THREAD_ID", None)
        else:
            os.environ["CODEX_THREAD_ID"] = tid

    def _resolve(self, tid):
        self._as(tid)
        with contextlib.redirect_stderr(self.err):
            return pm._self_identity()

    def _why(self, tid):
        """(sid, why) as the resolver reports it: the reason is RETURNED, for the refusing command to print."""
        self._as(tid)
        with contextlib.redirect_stderr(self.err):
            return pm._self_id_why()

    def _run(self, tid, fn, *args):
        """Drive a CLI command as the shell of thread `tid` would: (rc, the HTTP it made)."""
        self._as(tid)
        del self.calls[:]
        with contextlib.redirect_stderr(self.err), contextlib.redirect_stdout(io.StringIO()):
            rc = fn(*args)
        return rc, list(self.calls)

    def _send(self, tid, argv):
        rc, calls = self._run(tid, pm.cli_send, argv)
        return rc, [(m, p, b) for m, p, b in calls if p == "/send"]

    def _posted(self, tid, argv):
        rc, posts = self._send(tid, argv)
        self.assertEqual(rc, 0, self.err.getvalue())
        self.assertEqual(len(posts), 1, posts)
        return posts[0][2]

    # ── the fix ───────────────────────────────────────────────────────────────────────────────

    def test_two_codex_sessions_resolve_to_two_identities(self):
        # two threads under the one app-server, two commands, two DIFFERENT senders (the constraint the fix
        # is shaped by: one exported id in that process would have made them one). Red on main: both (None, None).
        self._registry(TWO)
        self.assertEqual(self._resolve("thread-web"), (CODEX_WEB, "web"))
        self.assertEqual(self._resolve("thread-api"), (CODEX_API, "api"))
        self.assertEqual(self.err.getvalue(), "", "a clean resolution says nothing")
        self.assertEqual(pm.CODEX_REGISTRY, REG, "the resolver reads the kernel's Codex registry under the state root")

    def test_two_threads_send_read_and_are_isolation_checked_as_their_own_stable_sids(self):
        # end to end through the real commands, each thread in turn: the mail's from_id, the inbox read, and the
        # sid the isolation check is consulted for are all the matched STABLE sid, never the raw native thread id
        self._registry(TWO)
        seen = []
        pm._mail_off_why = lambda sid: seen.append(sid) or ""      # the isolation seam: records what it was asked about
        for tid, sid, name in (("thread-web", CODEX_WEB, "web"), ("thread-api", CODEX_API, "api")):
            body = self._posted(tid, ["--kind", "coordinate", "tests", "the %s tests are green" % name])
            self.assertEqual((body["from_id"], body["from"]), (sid, name), "the mail carries the stable sid and the live name")
            for peek in (False, True):
                rc, calls = self._run(tid, pm.cli_inbox, peek)
                self.assertEqual(rc, 0, self.err.getvalue())
                self.assertEqual([p for _, p, _ in calls], ["/inbox?id=%s&peek=%d" % (sid, 1 if peek else 0)])
            self.assertEqual(seen, [sid], "the isolation check is consulted for the stable sid, once per send")
            del seen[:]
        self.assertEqual(self.err.getvalue(), "")
        self.assertNotIn("thread-", json.dumps(self.calls), "the native thread id never reaches the bus")

    def test_an_ended_row_beside_the_live_one_does_not_count(self):
        # only LIVE rows claim a thread: an ended record of the same thread is history, not a second claimant
        self._registry({CODEX_OLD: _row("thread-web", "web", dead=True), CODEX_WEB: _row("thread-web", "web")})
        self.assertEqual(self._resolve("thread-web"), (CODEX_WEB, "web"))

    def test_the_claude_id_wins_over_a_stray_codex_variable(self):
        # a Claude Code session whose shell also carries a Codex variable keeps its own identity, and the
        # registry is never opened for it (an unreadable one here would have said so) ...
        REG.write_text("{not json")
        os.environ["CLAUDE_CODE_SESSION_ID"] = FSID
        self.assertEqual(self._resolve("thread-web"), (FSID, None))
        self.assertEqual(self._why("thread-web"), (FSID, None))
        self.assertEqual(self.err.getvalue(), "")
        # ... and a registry that WOULD resolve the thread, to another session, is not consulted either. Only this half
        # tells the Claude-first order from a Codex-first lookup that falls back to the Claude variable on a miss: the
        # corrupt file above is a miss to both orders, so both answer (FSID, None) there; here the wrong order answers
        # CODEX_WEB. The mail is then signed by the Claude id.
        self._registry(TWO)
        self.assertEqual(self._resolve("thread-web"), (FSID, None))
        self.assertEqual(self._why("thread-web"), (FSID, None))
        self.assertEqual(self._posted("thread-web", ["api", "hello from a Claude session"])["from_id"], FSID)
        self.assertEqual(self.err.getvalue(), "")

    def test_isolation_holds_for_a_codex_resolved_identity(self):
        # the resolved id is the stable sid every store is keyed by, so the user's mailbox-off boundary on it holds,
        # and holds for THAT session only: web's mailbox off refuses web, and api beside it still sends
        self._registry(TWO)
        pm.SESSION_FLAGS.parent.mkdir(parents=True, exist_ok=True)
        pm.SESSION_FLAGS.write_text(json.dumps({CODEX_WEB: {"postalServiceOff": True}}))
        rc, posts = self._send("thread-web", ["api", "hello from an isolated session"])
        self.assertEqual((rc, posts), (1, []))
        self.assertIn("isolation: YOUR OWN mailbox is OFF", self.err.getvalue())
        self.assertEqual(self._posted("thread-api", ["web", "hello from beside it"])["from_id"], CODEX_API)

    # ── fail closed, and say why ──────────────────────────────────────────────────────────────

    def _refused(self, tid, *words):
        """The resolver's (None, why) for thread `tid`, `why` carrying every word; and _self_identity is (None, None),
        silently (the resolver never prints; the refusing command does)."""
        sid, why = self._why(tid)
        self.assertIsNone(sid)
        for w in ("CODEX_THREAD_ID",) + words:
            self.assertIn(w, why or "")
        self.assertEqual(self._resolve(tid), (None, None))
        self.assertEqual(self.err.getvalue(), "", "the resolver itself says nothing")
        return why

    def test_an_unknown_thread_refuses_rather_than_guessing(self):
        self._registry({CODEX_WEB: _row("thread-web", "web")})
        self._refused("thread-tests", str(REG), "has no session for")

    def test_two_live_rows_for_one_thread_refuse_as_ambiguous(self):
        self._registry({CODEX_WEB: _row("thread-web", "web"), CODEX_API: _row("thread-web", "api")})
        self._refused("thread-web", "2 live sessions", "refusing to guess")

    def test_only_an_ended_row_refuses(self):
        self._registry({CODEX_OLD: _row("thread-web", "web", dead=True)})
        self._refused("thread-web", "has ended")

    def test_a_missing_registry_refuses_and_names_the_file(self):
        self.assertFalse(REG.exists())
        self._refused("thread-web", str(REG), "does not exist")

    def test_a_registry_that_is_not_json_refuses_with_the_parse_error(self):
        REG.write_text("{not json")
        why = self._refused("thread-web", str(REG), "is not valid JSON")
        self.assertIn("Expecting", why, "the parser's own words follow, so the fix is named")
        REG.write_bytes(b"\xff\xfe{")                             # bytes that are not text at all: the same sentence
        self._refused("thread-web", str(REG), "is not valid JSON")
        REG.write_text("[]")
        self._refused("thread-web", str(REG), "is not an object of sessions")

    def test_a_registry_that_cannot_be_read_refuses_with_the_os_error(self):
        # a directory in the file's place: the read fails at the OS, not the parser, and the sentence says which
        REG.mkdir()
        why = self._refused("thread-web", str(REG), "could not be read")
        self.assertNotIn("JSON", why)
        self.assertIn("directory", why.lower(), "the OS's own words follow: %r" % why)

    def test_a_matching_row_whose_key_is_not_a_session_id_refuses(self):
        # the registry's key becomes the sender's id, a path component under the mail and names roots: a corrupted
        # key is refused with its own words, never returned (and so never read as <names>/../other by the fallback)
        for key in ("../other", "", ".hidden", "a/b"):
            self._registry({key: _row("thread-web", "web")})
            self._refused("thread-web", "a malformed row in %s" % REG, "not a session id")
        # a clean row beside the malformed claim does not rescue the thread: the registry is not one to trust about it
        self._registry({"../other": _row("thread-web", "web"), CODEX_WEB: _row("thread-web", "web")})
        self._refused("thread-web", "a malformed row in %s" % REG)
        rc, posts = self._send("thread-web", ["api", "hello"])
        self.assertEqual((rc, posts), (1, []))
        self.assertIn("a malformed row in", self.err.getvalue())

    def test_a_blank_codex_variable_refuses_with_its_own_line(self):
        # set but empty is a Codex shell with a broken identity, never a silent None: the refusal that points at
        # "the reason above" must always have one
        for blank in ("", "   "):
            self._refused(blank, "is set but empty")
            rc, posts = self._send(blank, ["--from", "morning-brief", "api", "hello"])
            self.assertEqual((rc, posts), (1, []))
            self.assertIn("[romp mail] CODEX_THREAD_ID is set but empty", self.err.getvalue())
            self.err = io.StringIO()

    # ── the refusal is the command's, and --from is no door for a Codex shell ─────────────────

    def _broken(self):
        """(name, arrange) for each way a Codex shell's identity fails to resolve: unknown, ambiguous, corrupt."""
        return (("unknown", lambda: self._registry({CODEX_WEB: _row("thread-web", "web")})),
                ("ambiguous", lambda: self._registry({CODEX_WEB: _row("thread-tests", "web"), CODEX_API: _row("thread-tests", "api")})),
                ("corrupt", lambda: REG.write_text("{not json")))

    def test_an_unresolved_codex_caller_cannot_send_through_from(self):
        # before this, a shell with an unknown, ambiguous or unreadable CODEX_THREAD_ID printed the lookup's reason
        # and then sent anyway under ext:<label>: a session's mail signed as a script's, the bug buried in a label
        for name, arrange in self._broken():
            arrange()
            self.err = io.StringIO()
            rc, posts = self._send("thread-tests", ["--from", "morning-brief", "api", "hello"])
            err = self.err.getvalue()
            self.assertEqual((rc, posts), (1, []), "%s: %s" % (name, err))
            self.assertEqual(err.count("[romp mail] CODEX_THREAD_ID"), 1, "%s: the reason, once: %s" % (name, err))
            self.assertIn("no session identity resolved", err)
            self.assertIn("--from included", err)
            self.assertEqual(self.calls, [], "nothing reached the bus")
        # the door still opens for the caller it was built for: a shell that is not a session's (neither variable)
        self._registry(TWO)
        self.err = io.StringIO()
        body = self._posted(None, ["--from", "morning-brief", "api", "the morning summary"])
        self.assertEqual((body["from_id"], body["from"]), ("ext:morning-brief", "morning-brief"))
        self.assertNotIn("CODEX_THREAD_ID", self.err.getvalue(), "a non-session shell hears nothing about a Codex variable")
        # and without --from that shell hears the door named, not a Codex diagnosis
        rc, posts = self._send(None, ["api", "anonymous attempt"])
        self.assertEqual((rc, posts), (1, []))
        self.assertIn("pass --from <label>", self.err.getvalue())
        self.assertNotIn("[romp mail] CODEX_THREAD_ID", self.err.getvalue())

    def test_inbox_sent_working_and_recall_refuse_with_the_reason_and_fetch_nothing(self):
        # recall included: a recall is of the caller's OWN mail, so it needs the sender's identity, and the bus answers
        # an empty from_id with a bare 400 "missing from_id" (the /recall route), which is what a Codex shell whose
        # lookup failed heard instead of the reason, while the recall_message tool already said it
        self._registry({CODEX_WEB: _row("thread-web", "web")})
        for fn, args in ((pm.cli_inbox, (False,)), (pm.cli_inbox, (True,)), (pm.cli_sent, ()), (pm.cli_working, (["x"],)),
                         (pm.cli_recall, (["api"],))):
            self.err = io.StringIO()
            rc, calls = self._run("thread-tests", fn, *args)
            self.assertEqual((rc, calls), (1, []), self.err.getvalue())
            err = self.err.getvalue()
            self.assertIn("[romp mail] CODEX_THREAD_ID names a thread that %s has no session for" % REG, err)
            self.assertIn("session-identity bug", err)
            # the same command from a shell with neither variable keeps its short words, and hears nothing of Codex
            self.err = io.StringIO()
            rc, calls = self._run(None, fn, *args)
            self.assertEqual((rc, calls), (1, []))
            self.assertNotIn("CODEX_THREAD_ID", self.err.getvalue())
            self.assertIn("romp session", self.err.getvalue())

    def test_agents_needs_no_identity_and_says_nothing_about_it(self):
        # `agents` runs for a shell with no identity (the listing is everyone's); a failed Codex lookup is not its
        # refusal to print. recall is not here: it withdraws the caller's OWN mail, so it needs the sender's identity
        # (the refusing test above)
        self._registry({CODEX_WEB: _row("thread-web", "web")})
        rc, calls = self._run("thread-tests", pm.cli_agents)
        self.assertEqual((rc, [p for _, p, _ in calls]), (0, ["/agents?me="]))
        self.assertEqual(self.err.getvalue(), "")

    def test_the_mcp_tools_refuse_with_the_reason(self):
        # the tool surface of the same commands: a failed lookup's reason in the tool result, never a bare refusal
        self._registry({CODEX_WEB: _row("thread-web", "web")})
        self._as("thread-tests")
        pm._LOCAL_CONFIRMED[0] = False
        try:
            with contextlib.redirect_stderr(self.err):
                for name, args in (("send_message", {"to": "api", "body": "hi", "kind": "coordinate"}),
                                   ("check_inbox", {}), ("check_sent", {}), ("set_working", {"text": "x"}),
                                   ("recall_message", {"to": "api"})):
                    text, is_err = pm._mcp_call(name, args)
                    self.assertTrue(is_err, name)
                    self.assertIn("CODEX_THREAD_ID names a thread that %s has no session for" % REG, text, name)
                    self.assertIn("session-identity bug", text, name)
                self.assertEqual(self.calls, [], "nothing reached the bus")
                self._as(None)
                text, is_err = pm._mcp_call("check_inbox", {})
                self.assertEqual((text, is_err), ("Not inside a romp session.", True))
        finally:
            pm._LOCAL_CONFIRMED[0] = False


if __name__ == "__main__":
    unittest.main()
