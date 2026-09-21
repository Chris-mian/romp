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

A third identity fault is the environment's AGE (2026-09-15): a session's postal MCP server is a child started
with the CLI, so its CLAUDE_CODE_SESSION_ID is the transcript id of that moment for the process's whole life,
while a /clear mints a new one under the same romp sid and the kernel's row moves its lastSid to it. The stale id
matched no row by id or by lastSid, and the fallback signed every tool-sent message with it ("from an unidentified
session") and read a mailbox nobody delivers to, until the CLI restarted. StaleFsidIdentity pins the third join
_self_row makes for that case: the kernel's GET /sessions/by-fsid, the authority on which live session owned a
prior transcript, answering with that one session's row; a refusal or an unreachable kernel keeps the old
fallback, and the exact-id, lastSid and Codex paths never ask. KernelGetContract drives the REAL _kernel_get and
_kernel_session_by_fsid against a loopback stand-in for the kernel: the seam StaleFsidIdentity stubs is pinned there.
"""
import contextlib
import io
import json
import os
import socket
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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


OLD_FSID = "aaaaaaaa-2222-3333-4444-555555555501"   # the transcript web's CLI had when its postal MCP server started
NEW_FSID = "aaaaaaaa-2222-3333-4444-555555555502"   # the one its /clear minted: the row's lastSid now
WEB = "11111111-2222-3333-4444-5555555555a1"
API = "11111111-2222-3333-4444-5555555555a2"
T_WEB = "66666666-7777-8888-9999-0000000000a1"      # a comment thread of web
OLD_TFSID = "aaaaaaaa-2222-3333-4444-555555555511"  # the thread's transcript before ITS /clear
NEW_TFSID = "aaaaaaaa-2222-3333-4444-555555555512"  # the one its /clear minted
THREAD_REG = pm.STATE.parent / "sdk" / (T_WEB + ".json")   # the reg the bus's thread rule reads (_thread_of)


class StaleFsidIdentity(unittest.TestCase):
    """A session's postal MCP server is a child started with the CLI, and its CLAUDE_CODE_SESSION_ID is fixed for
    the process's life; a /clear mints a new transcript id under the same romp sid, so the kernel's row moves its
    lastSid while the server still carries the PRE-clear id. That id matched no row by id or by lastSid, so
    _self_identity fell back to it: every message the session sent through its tools arrived "from an
    unidentified session" and check_inbox read a mailbox keyed by a transcript id nobody delivers to, until the
    CLI restarted (reproduced 2026-09-15; a `romp mail send` from a fresh shell, whose env carried the current id,
    was attributed). _self_row's third join asks the kernel, the authority on which session owned a prior id
    (GET /sessions/by-fsid, through _kernel_get, the seam stubbed here), and uses the ONE row it answers with;
    a 404, a 409 or an unreachable kernel keeps the old fallback, and the exact-id, lastSid and Codex paths never
    ask. Synthetic ids only."""

    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "ROMP_SESSIONS_FILE")}
        os.environ.pop("CODEX_THREAD_ID", None)
        self.rows = [
            {"id": WEB, "name": "web", "dir": "/tmp/notes-api", "state": "idle", "working": "", "bg": "", "fg": "",
             "compacting": False, "lastSid": NEW_FSID, "backend": "sdk"},
            {"id": API, "name": "api", "dir": "/tmp/notes-api", "state": "idle", "working": "", "bg": "", "fg": "",
             "compacting": False, "lastSid": API, "backend": "sdk"},
            {"id": CODEX_WEB, "name": "tests", "dir": "/tmp/notes-api", "state": "idle", "working": "",
             "lastSid": CODEX_WEB, "backend": "codex"}]
        self.sess = Path(os.environ["XDG_STATE_HOME"]) / "stale-fsid-sessions.json"
        self._listing(self.rows)
        os.environ["ROMP_SESSIONS_FILE"] = str(self.sess)
        self.err = io.StringIO()
        self.calls, self.asked = [], []
        self.kernel = {OLD_FSID: self.rows[0]}   # what GET /sessions/by-fsid knows: fsid -> the row; anything else 404s
        self.refusal = None                       # a canned refusal dict for every ask (a 409), when set
        self.down = False                         # the kernel unreachable: the seam answers None
        self._saved = (pm.ensure, pm._http, getattr(pm, "_kernel_get", None))
        pm.ensure = lambda: True
        pm._http = self._transport
        pm._kernel_get = self._kernel_get
        REG.parent.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        pm.ensure, pm._http = self._saved[:2]
        if self._saved[2] is None:
            del pm._kernel_get
        else:
            pm._kernel_get = self._saved[2]
        for k, v in self._env.items():
            restore_env(k, v)
        for f in (REG, THREAD_REG):
            if f.exists():
                f.unlink()
        pm._LOCAL_CONFIRMED[0] = False

    def _listing(self, rows):
        self.sess.write_text(json.dumps(rows))

    def _transport(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if path == "/send":
            return {"note": "delivered to '%s'" % payload["to"]}
        return {"messages": [], "agents": [], "sent": [], "removed": [], "kept": []}

    def _kernel_get(self, path, timeout=2, said_once=()):
        """The kernel's one-document GET seam, answering as the real _kernel_get does: the row on a 200, the
        refusal dict on a 4xx, None when the kernel is unreachable. Records every ask (KernelGetContract pins
        the real function, `said_once` included)."""
        self.assertTrue(path.startswith("/sessions/by-fsid?"), "the only document the identity asks for: %s" % path)
        fsid = urllib.parse.parse_qs(path.split("?", 1)[1])["fsid"][0]
        self.asked.append(fsid)
        if self.down:
            return None
        if self.refusal is not None:
            return dict(self.refusal)
        if fsid in self.kernel:
            return dict(self.kernel[fsid])
        return {"ok": False, "status": 404, "error": "no live session has transcript %s" % fsid}

    def _resolve(self, fsid):
        os.environ["CLAUDE_CODE_SESSION_ID"] = fsid
        del self.asked[:]
        with contextlib.redirect_stderr(self.err):
            return pm._self_identity()

    def _run(self, fn, *args):
        del self.calls[:]
        with contextlib.redirect_stderr(self.err), contextlib.redirect_stdout(io.StringIO()):
            rc = fn(*args)
        return rc, list(self.calls)

    def test_a_pre_clear_id_resolves_to_the_sessions_row_through_the_kernel(self):
        # red on main: the stale id matches nothing on the listing, so the identity is (OLD_FSID, None) — the
        # unattributed sender. The kernel is asked ONCE, for exactly that id, and its row is the identity.
        self.assertEqual(self._resolve(OLD_FSID), (WEB, "web"))
        self.assertEqual(self.asked, [OLD_FSID])
        self.assertEqual((pm.my_id(), pm.my_name()), (WEB, "web"))
        self.assertEqual(self.err.getvalue(), "", "a clean resolution says nothing")

    def test_a_send_and_an_inbox_read_from_the_stale_process_carry_the_row_id(self):
        # end to end through the real command and the real tool: the mail's from_id is the stable sid and its
        # from the live name (red on main: from_id OLD_FSID, from "unknown"), and the inbox read is of web's box
        os.environ["CLAUDE_CODE_SESSION_ID"] = OLD_FSID
        rc, calls = self._run(pm.cli_send, ["--kind", "coordinate", "api", "the web tests are green"])
        self.assertEqual(rc, 0, self.err.getvalue())
        posts = [b for m, p, b in calls if p == "/send"]
        self.assertEqual(len(posts), 1, calls)
        self.assertEqual((posts[0]["from_id"], posts[0]["from"]), (WEB, "web"))
        rc, calls = self._run(pm.cli_inbox, False)
        self.assertEqual(rc, 0, self.err.getvalue())
        self.assertEqual([p for _, p, _ in calls], ["/inbox?id=%s&peek=0" % WEB])
        with contextlib.redirect_stderr(self.err):
            text, is_err = pm._mcp_call("send_message", {"to": "api", "body": "the web tests are green",
                                                          "kind": "coordinate"})
            self.assertFalse(is_err, text)
            posts = [b for m, p, b in self.calls if p == "/send"]
            self.assertEqual((posts[-1]["from_id"], posts[-1]["from"]), (WEB, "web"))
            del self.calls[:]
            text, is_err = pm._mcp_call("check_inbox", {})
            self.assertFalse(is_err, text)
            self.assertEqual([p.split("&")[0] for _, p, _ in self.calls if p.startswith("/inbox?")], ["/inbox?id=%s" % WEB])
        self.assertNotIn(OLD_FSID, json.dumps(self.calls), "the stale transcript id never reaches the bus")

    def test_a_refusal_or_an_unreachable_kernel_keeps_the_env_fallback(self):
        # nothing regresses: when the kernel does not know the id (404), refuses to choose (409) or cannot be
        # reached, the identity is what it was before this join — the env id, no name — and the send goes out
        # under it as it did
        self.kernel = {}
        self.assertEqual(self._resolve(OLD_FSID), (OLD_FSID, None))
        self.assertEqual(self.asked, [OLD_FSID])
        self.refusal = {"ok": False, "status": 409,
                        "error": "2 live sessions claim transcript %s (%s, %s); refusing to guess which" % (OLD_FSID, API, WEB)}
        self.assertEqual(self._resolve(OLD_FSID), (OLD_FSID, None))
        self.refusal, self.down = None, True
        self.assertEqual(self._resolve(OLD_FSID), (OLD_FSID, None))
        rc, calls = self._run(pm.cli_send, ["--kind", "coordinate", "api", "still sending"])
        self.assertEqual(rc, 0, self.err.getvalue())
        self.assertEqual([b["from_id"] for m, p, b in calls if p == "/send"], [OLD_FSID])

    def test_an_empty_listing_is_not_asked_about(self):
        # the kernel down or no live session at all: neither can own the id, so no second fetch is made
        self._listing([])
        self.assertEqual(self._resolve(OLD_FSID), (OLD_FSID, None))
        self.assertEqual(self.asked, [])

    def test_a_cleared_comment_threads_stale_id_resolves_to_its_thread_row_and_its_send_is_refused(self):
        # a comment thread's mail is OFF until the user breaks it out (T356), and the sender gate decides that from
        # the reg under the RESOLVED id. Red on main: the thread's stale id resolved to itself, no reg sits under a
        # transcript id, so the gate read an ordinary session and the thread's send went out — unattributed AND
        # past the rule. The kernel answers the stale id with the thread's row (thread/parent as the ?threads=1
        # listing carries them), the identity is the thread's, and the gate refuses with the thread's own words
        trow = {"id": T_WEB, "name": "web-comment-1", "dir": "/tmp/notes-api", "state": "idle", "working": "",
                "thread": True, "parent": WEB, "lastSid": NEW_TFSID, "backend": "sdk",
                "postalServiceOff": True, "mailOffWhy": "thread"}
        self._listing(self.rows + [trow])
        self.kernel[OLD_TFSID] = trow
        THREAD_REG.parent.mkdir(parents=True, exist_ok=True)
        THREAD_REG.write_text(json.dumps({"sid": T_WEB, "alive": True, "threadOf": WEB, "lastSid": NEW_TFSID}))
        self.assertEqual(self._resolve(OLD_TFSID), (T_WEB, "web-comment-1"))
        self.assertEqual(self.asked, [OLD_TFSID])
        row = pm._self_row(OLD_TFSID)
        self.assertEqual((row.get("thread"), row.get("parent")), (True, WEB), "the row is marked as the listing marks it")
        self.assertEqual(pm._mail_off_why(pm.my_id()), "thread")
        rc, calls = self._run(pm.cli_send, ["--kind", "coordinate", "api", "a note from the thread"])
        self.assertEqual(rc, 1)
        self.assertEqual([p for _, p, _ in calls if p == "/send"], [], "nothing reaches the bus")
        self.assertIn(pm.THREAD_MAIL_OFF_SENDER, self.err.getvalue())
        self.assertEqual(self._resolve(NEW_TFSID), (T_WEB, "web-comment-1"), "the thread's current id: the lastSid join")
        self.assertEqual(self.asked, [])

    def test_the_current_id_the_stable_id_and_a_codex_thread_never_ask(self):
        # the two joins that already resolved (the user 2026-07-27) and the Codex resolver (2026-09-15) are
        # untouched: each answers off the listing, and the kernel hears no by-fsid question
        self.assertEqual(self._resolve(NEW_FSID), (WEB, "web"), "the CURRENT transcript id: the lastSid join")
        self.assertEqual(self.asked, [])
        self.assertEqual(self._resolve(WEB), (WEB, "web"), "the stable sid: the exact join")
        self.assertEqual(self.asked, [])
        os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
        os.environ["CODEX_THREAD_ID"] = "thread-web"
        REG.write_text(json.dumps({CODEX_WEB: _row("thread-web", "web")}))
        del self.asked[:]
        with contextlib.redirect_stderr(self.err):
            self.assertEqual(pm._self_identity(), (CODEX_WEB, "tests"), "a Codex thread: the registry, then the exact join")
        self.assertEqual(self.asked, [])
        self.assertEqual(self.err.getvalue(), "")


def _dead_port():
    """A loopback port nothing listens on (bound, read, released)."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _KernelStub(BaseHTTPRequestHandler):
    """A loopback stand-in for the kernel's GET routes, answering the way the real Handler does for the
    documents _kernel_get is asked for: the token checked first (a JSON 403 without it), a /sessions/by-fsid
    row from `rows` on a hit and the route's JSON 404 on a miss, a JSON 409 refusal, a 2xx whose body is
    not JSON, and a plain-text 404 "not found" for any other path (a kernel from before a route existed)."""
    rows = {}
    token = ""

    def do_GET(self):
        if self.headers.get("X-Romp-Token") != self.token:
            return self._send(403, json.dumps({"ok": False, "error": "forbidden"}))
        if self.path.startswith("/sessions/by-fsid?"):
            fsid = urllib.parse.parse_qs(self.path.split("?", 1)[1]).get("fsid", [""])[0]
            row = self.rows.get(fsid)
            if row is not None:
                return self._send(200, json.dumps(row))
            return self._send(404, json.dumps({"ok": False, "error": "no live session has transcript %s" % fsid}))
        if self.path == "/conflict":
            return self._send(409, json.dumps({"ok": False, "error": "2 live sessions claim it; refusing to guess which"}))
        if self.path == "/junk":
            return self._send(200, "not json", "text/plain")
        return self._send(404, "not found", "text/plain")

    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


class KernelGetContract(unittest.TestCase):
    """The real _kernel_get and _kernel_session_by_fsid against a loopback kernel stand-in (StaleFsidIdentity
    stubs the seam; this pins what the seam is): the parsed body on a 2xx; a logged {"ok": False, "status",
    "error"} for a refusal, the kernel's own text sliced in; None when the body is not JSON, the kernel is
    unreachable, or the ROMP_SESSIONS_FILE seam is set even with a kernel listening; the token on every ask; a
    by-fsid row becoming the agent row (a thread's with thread and parent) and every refusal None; and the
    route's designed 404 said once per process while a 409 is said each time."""

    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), _KernelStub)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        self._seam = os.environ.get("ROMP_SESSIONS_FILE")
        os.environ.pop("ROMP_SESSIONS_FILE", None)          # the real calls: no seam in the way
        self._base, self._token = pm.KERNEL_BASE, pm.SERVE_TOKEN
        pm.KERNEL_BASE = self.base
        _KernelStub.rows, _KernelStub.token = {}, pm.SERVE_TOKEN
        pm._KERNEL_GET_SAID.clear()
        self.err = io.StringIO()

    def tearDown(self):
        pm.KERNEL_BASE, pm.SERVE_TOKEN = self._base, self._token
        restore_env("ROMP_SESSIONS_FILE", self._seam)
        pm._KERNEL_GET_SAID.clear()

    def _get(self, path, **kw):
        with contextlib.redirect_stderr(self.err):
            return pm._kernel_get(path, **kw)

    def _by(self, fsid):
        with contextlib.redirect_stderr(self.err):
            return pm._kernel_session_by_fsid(fsid)

    def _said(self, status):
        return [l for l in self.err.getvalue().splitlines() if "kernel refused GET" in l and "HTTP %d" % status in l]

    def test_the_three_answers(self):
        _KernelStub.rows = {OLD_FSID: {"id": WEB, "name": "web"}}
        self.assertEqual(self._get("/sessions/by-fsid?fsid=" + OLD_FSID), {"id": WEB, "name": "web"})
        miss = self._get("/sessions/by-fsid?fsid=" + NEW_FSID)
        self.assertEqual((miss["ok"], miss["status"]), (False, 404), miss)
        self.assertIn("no live session has transcript " + NEW_FSID, miss["error"])
        old = self._get("/sessions/by-fsid-from-the-future")        # a kernel without the route: plain 404 text
        self.assertEqual((old["ok"], old["status"], old["error"]), (False, 404, "not found"))
        self.assertIsNone(self._get("/junk"), "a 2xx whose body is not JSON is no answer")
        self.assertEqual(len(self._said(404)), 2, "each refusal said, with its status:\n" + self.err.getvalue())
        pm.KERNEL_BASE = "http://127.0.0.1:%d" % _dead_port()
        self.assertIsNone(self._get("/sessions/by-fsid?fsid=" + OLD_FSID), "unreachable: None, the caller degrades")

    def test_the_token_rides_every_ask(self):
        _KernelStub.rows = {OLD_FSID: {"id": WEB, "name": "web"}}
        pm.SERVE_TOKEN = "not-the-kernels-token"
        denied = self._get("/sessions/by-fsid?fsid=" + OLD_FSID)
        self.assertEqual((denied["ok"], denied["status"]), (False, 403), denied)
        self.assertIsNone(self._by(OLD_FSID), "a refused lookup resolves no identity")

    def test_the_no_kernel_seam_answers_none_even_with_a_kernel_listening(self):
        _KernelStub.rows = {OLD_FSID: {"id": WEB, "name": "web"}}
        os.environ["ROMP_SESSIONS_FILE"] = "/nonexistent"
        self.assertIsNone(self._get("/sessions/by-fsid?fsid=" + OLD_FSID))
        self.assertIsNone(self._by(OLD_FSID))
        self.assertEqual(self.err.getvalue(), "", "nothing was asked, nothing is said")

    def test_a_by_fsid_row_becomes_the_agent_row_and_every_refusal_is_none(self):
        crafted = "aaaaaaaa-2222-3333-4444-555555555577"
        _KernelStub.rows = {
            OLD_FSID: {"id": WEB, "name": "web", "dir": "/tmp/notes-api", "state": "idle", "working": "",
                       "bg": "", "fg": "", "compacting": False, "lastSid": NEW_FSID, "backend": "sdk"},
            OLD_TFSID: {"id": T_WEB, "name": "web-comment-1", "dir": "/tmp/notes-api", "state": "idle",
                        "working": "", "thread": True, "parent": WEB, "lastSid": NEW_TFSID, "backend": "sdk",
                        "postalServiceOff": True, "mailOffWhy": "thread"},
            crafted: {"id": "../escape", "name": "x"}}
        row = self._by(OLD_FSID)
        self.assertEqual((row["id"], row["name"], row["lastSid"], row["dir"]), (WEB, "web", NEW_FSID, "/tmp/notes-api"))
        trow = self._by(OLD_TFSID)
        self.assertEqual((trow["id"], trow.get("thread"), trow.get("parent")), (T_WEB, True, WEB),
                         "a thread's row keeps thread and parent through the agent-row shape")
        self.assertIsNone(self._by(crafted), "a row whose id is not a session id is refused")
        self.assertIsNone(self._by(NEW_FSID), "404, no owner: None")
        pm.KERNEL_BASE = self.base.rstrip("0123456789") + str(_dead_port())
        self.assertIsNone(self._by(OLD_FSID), "unreachable: None")

    def test_a_designed_miss_is_said_once_per_process_and_a_refusal_every_time(self):
        for _ in range(3):
            self.assertIsNone(self._by(NEW_FSID))
        self.assertEqual(len(self._said(404)), 1, "one line for the same miss asked three times:\n" + self.err.getvalue())
        self.assertIsNone(self._by(OLD_FSID))
        self.assertEqual(len(self._said(404)), 2, "another id's miss is its own first line")
        for _ in range(2):
            self.assertEqual(self._get("/conflict")["status"], 409)
        self.assertEqual(len(self._said(409)), 2, "a refusal that is not the designed answer is said each time")
        for _ in range(2):
            self._get("/sessions/by-fsid?fsid=" + NEW_FSID)
        self.assertEqual(len(self._said(404)), 4, "a caller that did not ask for once-per-process hears every one")


if __name__ == "__main__":
    unittest.main()
