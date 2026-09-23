#!/usr/bin/env python3
"""A session host whose re-exec was deferred to the turn's end (the kernel attached mid-turn on newer code): the
handover must reach the kernel as the planned reconnect, the reconnect must attach to the re-executed host, and a
socket lost for any other reason while the handover is pending must still read as the lost host it is.

The real host program (bin/romp-session-host) drives the fake CLI (tests/fixtures/fake_claude.py) in a private
state root with `session-hosts` on (these tests mean to run a host); the kernel side is the real HostTransport built
by SdkBackend._new_host_transport and the backend's own re-exec road (_host_reexec_on_skew, _on_host_reexec_now,
_on_host_socket_lost). No SDK needed: the test plays the SDK's reader. HandoverGuards drives the same backend with no
host, on a hand-written lease and host.log, in a state root that says off. Synthetic ids; every process killed by the
test.
"""
import asyncio
import contextlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock
from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()   # hermetic BEFORE the loads
os.environ.pop("ROMP_STATE_DIR", None)
os.environ["ROMP_CLI_SCOPE"] = "0"                   # no scopes: the host is a plain child of the test
sb = load_source("romp_sdk_backend", os.path.join(BIN, "romp_sdk_backend.py"))
ht = sb._ht()
FAKE = os.path.join(HERE, "fixtures", "fake_claude.py")
SID = "11111111-2222-3333-4444-0000000000c7"
FSID = "11111111-2222-3333-4444-0000000000f7"
OLD, NEW = "abc12345", "def67890"
# A launcher for the re-exec that hands the real host a handoff with no descriptors, so the re-executed code's adopt fails
# at its first step on every platform: it logs cli-adopt-failed and exits, the death at startup the review of this lane
# probed (2026-09-23). %r is the real host program.
ADOPT_FAILS = """import json, os, sys
h = sys.argv[3]
with open(h) as f:
    d = json.load(f)
d.pop("fds", None)
with open(h, "w") as f:
    json.dump(d, f)
os.execv(sys.executable, [sys.executable, %r] + sys.argv[1:])
"""


class TookOrphanRoad(Exception):
    """Raised by a stand-in for the orphan road, which stops the connect there: what follows is not under test."""


def _user(text):
    return json.dumps({"type": "user", "message": {"role": "user", "content": text}}) + "\n"


class TurnEndHandover(unittest.TestCase):
    def setUp(self):
        self.state = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.state, True)
        Path(self.state, "session-hosts").write_text("on\n")      # these tests mean to run a host (the Testing rule)
        self.host = None
        self.addCleanup(self._kill)
        self.logs = []
        self.be = sb.SdkBackend(self.state, "/bin/true", lambda *a, **k: None, log=lambda m, *a, **k: self.logs.append(m))
        self.be.code_version = NEW
        self.be._on_host_hello = lambda sess, hello: None          # the hello's bookkeeping is not under test here

    def _start(self, **over):
        d = Path(self.state) / "hosts" / SID
        d.mkdir(parents=True, mode=0o700)
        spec = {"sid": SID, "name": "web", "version": OLD, "state_dir": self.state, "protocol": 1,
                "cli_path": FAKE, "cwd": self.state, "permission_prompt_tool_name": "stdio", "permission_mode": "default",
                "env": {"FAKE_CLI_LOG": os.path.join(self.state, "fake-cli.log"),
                        "FAKE_CLI_TRANSCRIPT_DIR": os.path.join(self.state, "transcripts"), "FAKE_CLI_SESSION_ID": FSID},
                "max_buffer_size": 1024 * 1024, "hook_self_answer_s": 2, "unattached_grace_s": 3600}
        spec.update(over)
        p = d / "spawn.json"
        p.write_text(json.dumps(spec)); p.chmod(0o600)
        env = dict(os.environ, PYTHONUNBUFFERED="1", ROMP_SDK_SITE=os.path.join(self.state, "no-sdk-here"))
        self.host = subprocess.Popen([sys.executable, os.path.join(BIN, "romp-session-host"), str(p)], stdout=subprocess.DEVNULL,
                                     stderr=open(os.path.join(self.state, "host.stderr"), "w"), env=env, start_new_session=True)
        self.sock = str(ht.host_sock(self.state, SID))
        deadline = time.time() + 15
        while time.time() < deadline and not (os.path.exists(self.sock) and sb.read_lease(self.state, SID)):   # loop-ok: bounded
            if self.host.poll() is not None:
                break
            time.sleep(0.05)
        self.assertIsNone(self.host.poll(), open(os.path.join(self.state, "host.stderr")).read()[-800:])

    @staticmethod
    def _killpg(pg):
        try:
            os.killpg(pg, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

    def _kill(self):
        if self.host is not None and self.host.poll() is None:
            try:
                os.killpg(self.host.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self.host.wait(timeout=10)

    def _rows(self):
        p = Path(self.state) / "session-events.jsonl"
        return [json.loads(l)["kind"] for l in p.read_text().splitlines() if l.strip()] if p.exists() else []

    def _hostlog(self, kind=None):
        p = Path(self.state) / "hosts" / SID / "host.log"
        rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []
        return [r for r in rows if kind is None or r.get("kind") == kind]

    def _run(self, coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    async def _accepted(self, *turns):
        """The road a kernel refresh takes: the previous kernel (older code) fed a turn and left, the host keeps it
        running; this kernel (newer code) asks for the re-exec first, which the host answers at-turn-end, then attaches
        (the order _host_transport_for runs them in) and plays the SDK's reader (a checkpoint per message, as the SDK's
        message stream has). Returns the session, its transport and the reader's queue: ("msg", record), then
        ("end", None) or ("err", exception)."""
        prev = ht.HostTransport(self.sock, kernel={"pid": 4242, "start": "1", "version": OLD}, ack=-1)
        await prev.connect()
        await prev.write(json.dumps({"type": "control_request", "request_id": "req_prev", "request": {"subtype": "initialize"}}) + "\n")
        for text in turns:
            await prev.write(_user(text))
        stream = prev.read_messages()
        async for m in stream:
            if m.get("type") == "assistant":
                break
        await stream.aclose()
        prev.detach_mode = True
        await prev.close()                                    # the previous kernel leaves; the host keeps the turn
        s = types.SimpleNamespace(sid=SID, name="web", _host_reexec_from=None, _reconnect=False, _host_end_grace=None,
                                  _on_cli_stderr=lambda line: None, _host=None, _host_ack_t=0.0)
        self.assertIsNone(await self.be._host_reexec_on_skew(s, sb.read_lease(self.state, SID)), "deferred: the attach goes on")
        self.assertEqual(s._host_reexec_from, OLD, "the host accepted, at the turn's end")
        t = self.be._new_host_transport(s, self.sock, -1)
        s._host = t
        await t.connect()
        q = asyncio.Queue()

        async def reader():                                   # the SDK Query's reader
            try:
                async for m in t.read_messages():
                    await q.put(("msg", m))
                    await asyncio.sleep(0)                    # the message stream's checkpoint
                await q.put(("end", None))
            except Exception as e:
                await q.put(("err", e))
        rt = asyncio.ensure_future(reader())
        self.addCleanup(rt.cancel)
        await t.write(json.dumps({"type": "control_request", "request_id": "req_init", "request": {"subtype": "initialize"}}) + "\n")
        while True:                                           # the initialize's answer, then the held replay
            kind, m = await asyncio.wait_for(q.get(), 15)
            self.assertEqual(kind, "msg", "the attach streams: %r" % (m,))
            if m.get("type") == "assistant":
                break
        return s, t, q

    @staticmethod
    async def _to_end(q, on_msg=None, timeout=20):
        while True:
            kind, m = await asyncio.wait_for(q.get(), timeout)
            if kind == "msg" and on_msg is not None:
                on_msg(m)
            elif kind in ("end", "err"):
                return m

    async def _host_fault_closes_the_socket(self, t):
        """A fault in the host's own handling of this kernel's connection (a `client-loop-failed` line; here an `end`
        frame whose grace is not a number): the host says so, closes THIS socket and keeps its CLI, with no exec."""
        await t._send({"t": "end", "grace": "not-a-number"})

    def _handover_problems(self):
        """The backend's problem ring (the error center's feed) filtered to the handover's own lines."""
        return [p.get("text") for p in self.be.problems() if "handover" in str(p.get("text")) or "re-exec" in str(p.get("text"))]

    def test_the_kernels_own_write_at_the_turns_end_does_not_turn_the_handover_into_a_lost_host(self):
        """Seen on a real kernel refresh from an older main (2026-09-22): the host wrote reexec-now with its kernel's backlog
        empty and exec'd, but a write the kernel made at the same result (its batch ack, its context refresh) hit the
        closed socket first; asyncio's failed write closes the whole connection, the frame still in the receive buffer was
        never read, and the stream ended as a lost host (the thread ended; no planned reconnect). This is the batch-ack
        road, pinned on every interpreter (2026-09-23, the review of this lane). Left to the event loop, which write went
        first depended on the interpreter: on 3.12 the reader's ack after a 0.1 s result hold; on 3.10 and 3.11 the ack
        went out before the hold, while the host was alive, and the loop then read the frame before the refresh was
        written, so no frame was lost and this test's first form failed there (6 of 6 runs). So the reader's ack after the
        result now waits, holding the loop as a slow reader would, for the host's own log to show the exec done: the ack
        is the first write into the closed socket, the refresh follows it, and the stream ends through the ack's branch.
        The next test pins the refresh-first road. The host's own log, which records the exec before it happens, is what
        makes the socket's end the handover, and the handover's informational lines stay out of the error center."""
        self._start()
        refresh, ack = {}, {}
        real_flush = ht.HostTransport._flush_ack

        async def flush_after_exec(tr):
            if tr.result_tags and "held" not in ack:              # the first ack after the turn's result
                ack["held"] = True
                deadline = time.time() + 15
                while time.time() < deadline and not self._hostlog("reexeced"):   # loop-ok: the event is the host's own row
                    time.sleep(0.02)                                             # loop-ok: the reader's own work holds the loop
                try:
                    await real_flush(tr)
                    ack["write"] = "ok"
                except Exception as e:
                    ack["write"] = type(e).__name__
                    raise
                return
            await real_flush(tr)

        async def go():
            s, t, q = await self._accepted("slow sleep=1.5")

            async def do_refresh():
                try:
                    await t.write(json.dumps({"type": "control_request", "request_id": "req_ctx",
                                              "request": {"subtype": "get_context_usage"}}) + "\n")
                    refresh["write"] = "ok"
                except Exception as e:
                    refresh["write"] = type(e).__name__

            def at_result(m):
                if m.get("type") == "result":
                    asyncio.ensure_future(do_refresh())
            return s, await self._to_end(q, at_result)
        with mock.patch.object(ht, "ACK_INTERVAL_S", 0.0), mock.patch.object(ht.HostTransport, "_flush_ack", flush_after_exec):
            s, end = self._run(go())
        self.assertEqual(len(self._hostlog("reexec")), 1, "the host did its part: one handover")
        self.assertEqual(self._hostlog("reexec")[0].get("frameBuffered"), 0, "the frame reached the kernel's socket")
        self.assertIn(ack.get("write"), ("ConnectionResetError", "BrokenPipeError"),
                      "the batch ack was the first write into the closed socket (%r; the refresh %r)" % (ack, refresh))
        self.assertTrue(s._reconnect, "the handover is the planned reconnect (at main the kernel read a lost host: the ack %r, "
                                      "the stream's end %r)" % (ack.get("write"), end))
        self.assertTrue(getattr(s, "_host_reexec_closed", False), "and the next attach waits for the re-executed host")
        self.assertTrue([l for l in self.logs if "its reexec-now frame unread" in l],
                        "the frame was lost (the case under test), so the socket's end is what was read as the handover: %r" % self.logs)
        self.assertIsInstance(end, ht.CLIConnectionError, "the stream ends on the transport's own error, never a bare socket error "
                                                          "out of the batch ack (%r)" % (end,))
        self.assertEqual(self._handover_problems(), [], "a planned handover is no problem for the error center (the ack road "
                                                        "logged its lines inside the socket error's handler)")

    def test_the_refresh_written_first_into_the_closed_socket_is_the_planned_reconnect_too(self):
        """The refresh-first road, pinned on every interpreter (2026-09-23, the review of this lane: only the batch-ack road
        was, and the observed refresh logs took this one, the stream ending on the host's socket closing). No batch ack is
        due (the interval and the batch patched high); the kernel's result handling holds its loop until the host's own
        log shows the exec done (`reexeced`: the new code serving), so the frame sits unread in the receive buffer; then
        the refresh goes out through the transport's writer in the same synchronous step, as a write's send does. The
        failed send closes the connection before the loop can read the frame, and the stream ends through the socket's-end
        branch, whose on_lost is what reads it as the handover. The journal writer lags each record by 0.2 s, so the host's
        handover (which waits for the journal to land) sends its frame well after the kernel has taken the result and
        begun its hold: without it the frame could reach the kernel in the result's own read and be taken with it. That
        lag is a margin, so every chunk the kernel's socket reader returns is recorded, and the result's handler notes
        whether any so far carried the frame, asserted first: a lost margin reports itself as the harness miss it is,
        never as the product failing (2026-09-23, the review of this lane)."""
        self._start(_test_journal_delay_s=0.2)
        out = {}
        chunks, real_read = [], asyncio.StreamReader.read
        frame = ht.sh.encode_frame({"t": "reexec-now"}).strip()

        async def recording_read(reader, n=-1):
            b = await real_read(reader, n)
            chunks.append(b)
            return b

        async def go():
            s, t, q = await self._accepted("slow sleep=1.5")

            def at_result(m):
                if m.get("type") != "result":
                    return
                out["frame_early"] = any(frame in c for c in chunks)
                deadline = time.time() + 15
                while time.time() < deadline and not self._hostlog("reexeced"):   # loop-ok: the event is the host's own row
                    time.sleep(0.02)                                             # loop-ok: the kernel's loop held, as a slow result branch holds it
                out["exec"] = bool(self._hostlog("reexeced"))
                out["open"] = not t._writer.is_closing()
                t._writer.write(ht.sh.encode_frame({"t": "in", "data": json.dumps(
                    {"type": "control_request", "request_id": "req_ctx", "request": {"subtype": "get_context_usage"}})}))
                out["closed_by_write"] = t._writer.is_closing()
            return s, await self._to_end(q, at_result)
        with mock.patch.object(ht, "ACK_INTERVAL_S", 3600.0), mock.patch.object(ht, "ACK_BATCH", 10 ** 9), \
                mock.patch.object(asyncio.StreamReader, "read", recording_read):
            s, end = self._run(go())
        self.assertIs(out.get("frame_early"), False, "a harness miss, not a product failure: the reexec-now frame reached the "
                                                     "kernel's reader with the result or ahead of its handling, so the host's "
                                                     "0.2 s journal lag was not margin enough (%r)" % out)
        self.assertTrue(out.get("exec"), "the host exec'd while the kernel's loop was held: %r" % self._hostlog())
        self.assertEqual(self._hostlog("reexec")[0].get("frameBuffered"), 0, "the frame reached the kernel's socket")
        self.assertTrue(out.get("open") and out.get("closed_by_write"), "the refresh was the first write, and its failure closed "
                                                                        "the connection: %r" % out)
        self.assertTrue(s._reconnect, "the handover is the planned reconnect (the stream's end %r)" % (end,))
        self.assertTrue(getattr(s, "_host_reexec_closed", False), "and the next attach waits for the re-executed host")
        self.assertTrue([l for l in self.logs if "its reexec-now frame unread" in l],
                        "the frame was lost, so the socket's end is what was read as the handover: %r" % self.logs)
        self.assertIsInstance(end, ht.CLIConnectionError, "the socket's-end branch: %r" % (end,))
        self.assertEqual(self._handover_problems(), [], "and no problem for the error center")

    def test_a_re_executed_host_that_dies_in_its_start_takes_the_orphan_road_at_once(self):
        """The planned reconnect's wait is for a host that may never serve (2026-09-23, the review of this lane): a
        re-executed host whose adopt fails logs cli-adopt-failed and exits. The wait ran its whole 20 s bound against the
        dead holder, filed a false host.reexec-failed row, and the attach branch acted on the lease read before the wait,
        so the connect went into nobody (the connect loop's launch error). The host's death now ends the wait as it
        happens, and the lease read again after it sends the connect down the orphan road (its host.died row and the
        journal's replay). The host is reaped the moment it exits, as init reaps a host whose kernel left."""
        launcher = Path(self.state) / "adopt-fails.py"
        launcher.write_text(ADOPT_FAILS % os.path.join(BIN, "romp-session-host"))
        real = ht.request_reexec

        async def via_launcher(sock, python, _launcher, version, timeout=10.0):
            return await real(sock, python, str(launcher), version, timeout)

        roads = []

        async def orphan(sess, opts, lease, msg_classes, died=True):
            roads.append(died)
            raise TookOrphanRoad()
        self._start()
        threading.Thread(target=self.host.wait, daemon=True).start()
        self.addCleanup(self._killpg, self.host.pid)           # the CLI outlives its host here; the group goes with the test

        async def go():
            s, t, q = await self._accepted("slow sleep=1.5")
            end = await self._to_end(q)
            self.assertTrue(s._reconnect, "the frame arrived: the planned reconnect (%r)" % (end,))
            t0 = time.time()
            try:
                got = await self.be._host_transport_for(s, None, None)
            except TookOrphanRoad:
                got = "orphan"
            return s, got, time.time() - t0
        with mock.patch.object(ht, "request_reexec", via_launcher), mock.patch.object(self.be, "_host_orphan_recover", orphan):
            s, got, took = self._run(go())
        self.host.wait(timeout=15)                            # the host is gone (its reaper saw the exit) before its log is read
        self.assertEqual((got, roads), ("orphan", [True]), "the orphan road, a host death, never an attach into nobody (got %r "
                                                           "after %.1f s; rows %r)" % (got, took, self._rows()))
        self.assertFalse(s._host_is_attach)
        self.assertLess(took, ht.SOCKET_WAIT_S / 2, "the death ended the wait, not its %.0f s bound" % ht.SOCKET_WAIT_S)
        self.assertNotIn("host.reexec-failed", self._rows(), "no false row: the host did not serve on under its old code")
        self.assertNotIn("host.reexec-refused", self._rows(), "and no second ask")
        self.assertTrue([l for l in self.logs if "the re-executed host is gone before it served" in l], self.logs)
        self.assertTrue(self._hostlog("cli-adopt-failed"), "the re-executed host died in its start: %r" % self._hostlog())
        self.assertIsNone(s._host_reexec_from)

    def test_the_planned_reconnect_waits_for_the_re_executed_host(self):
        """The planned road itself: the reexec-now frame arrived (nothing written at the result) and the connect loop's next
        pass runs at once. At main that pass read the old host's lease (the old version: the re-executed host takes a few
        hundred milliseconds to serve and rewrite it), asked for a re-exec again into a closed listener (a false
        host.reexec-refused row) and attached into nobody (a refused connect, which the connect loop files as a launch
        error). It must wait for the re-executed host, as the `now` answer's road does, and attach to it."""
        self._start()
        loop = asyncio.new_event_loop()
        try:
            async def go():
                s, t, q = await self._accepted("slow sleep=1.5")
                return s, await self._to_end(q)
            s, end = loop.run_until_complete(go())
            self.assertTrue(s._reconnect, "the frame arrived: the planned reconnect is armed")
            lease = sb.read_lease(self.state, SID)                 # the connect loop's next pass, at once
            got = loop.run_until_complete(self.be._host_reexec_on_skew(s, lease))
            fresh = got or lease
            self.assertEqual(str(fresh.get("version") or ""), NEW, "the attach goes to the re-executed host (got %r)" % fresh.get("version"))
            self.assertNotIn("host.reexec-refused", self._rows(), "no second ask into a closed listener")

            async def attach():
                t2 = ht.HostTransport(self.sock, kernel={"pid": 4343, "start": "1", "version": NEW}, ack=-1)
                await t2.connect()
                v = (t2.hello.get("host") or {}).get("version")
                await t2.close()
                return v
            self.assertEqual(loop.run_until_complete(attach()), NEW, "and the attach reaches it")
        finally:
            loop.close()

    def test_a_host_fault_that_closes_the_socket_mid_turn_is_not_the_handover(self):
        """The inference is narrow (the refresh review, 2026-09-22): an accepted handover stands from the answer until the
        exec, and a socket the host closes meanwhile for another reason (its client loop faulting on this connection,
        the host and its CLI alive under the same lease) is not the handover. Read as one, it would hold the next attach
        for the re-exec wait's whole bound and then file a false host.reexec-failed row."""
        self._start()

        async def go():
            s, t, q = await self._accepted("slow sleep=3")
            await self._host_fault_closes_the_socket(t)
            return s, await self._to_end(q)
        s, end = self._run(go())
        self.assertTrue(self._hostlog("client-loop-failed"), "the host faulted on this connection")
        self.assertEqual(self._hostlog("reexec"), [], "and did not exec")
        self.assertIsNone(self.host.poll(), "the host lives on, under the same lease")
        self.assertFalse(s._reconnect, "a socket the host closed without its exec is the lost host it reads as")
        self.assertFalse(getattr(s, "_host_reexec_closed", False))
        self.assertIsInstance(end, ht.CLIConnectionError)

    def test_a_socket_lost_after_a_deferred_handover_is_not_the_handover(self):
        """The deferral window: the turn's result arrived, but the host deferred the exec to the next result (a queued
        message ran as its own turn: `reexec-deferred`, output arriving), and the host then closed this socket for
        another reason. A result having arrived is not the exec; the host's own record of the exec is."""
        self._start(_test_journal_delay_s=0.4)                    # the journal writer lags, so the queued turn opens during the flush

        async def go():
            s, t, q = await self._accepted("first slow sleep=1.5", "second sleep=8")
            while True:
                kind, m = await asyncio.wait_for(q.get(), 15)
                if kind != "msg":
                    self.fail("the stream ended before the handover was deferred: %r" % (m,))
                if m.get("type") == "result":
                    break

            def deferred():
                return [r for r in self._hostlog("reexec-deferred") if r.get("reason") == "output-arriving"]
            deadline = time.time() + 15
            while time.time() < deadline and not deferred() and not self._hostlog("reexec"):   # loop-ok: the event is the host's row
                await asyncio.sleep(0.02)
            self.assertEqual((len(deferred()), self._hostlog("reexec")), (1, []), "the host deferred the handover past the first result")
            await self._host_fault_closes_the_socket(t)
            return s, await self._to_end(q)
        s, end = self._run(go())
        self.assertEqual(self._hostlog("reexec"), [], "the host did not exec")
        self.assertFalse(s._reconnect, "a result that came and a handover the host deferred are not the exec")
        self.assertFalse(getattr(s, "_host_reexec_closed", False))

    def test_a_host_killed_while_the_handover_is_pending_is_a_lost_host(self):
        """A host that dies with the handover pending (its lease's holder gone) stays the lost host: no planned reconnect,
        so the connect loop's orphan road replays its journal as for any host death."""
        self._start()

        async def go():
            s, t, q = await self._accepted("slow sleep=3")
            os.kill(self.host.pid, signal.SIGKILL)
            self.host.wait(timeout=10)                        # reaped before this loop reads the socket's end
            return s, await self._to_end(q)
        s, end = self._run(go())
        self.assertFalse(s._reconnect, "a dead host is not a handover")
        self.assertFalse(getattr(s, "_host_reexec_closed", False))

    def test_a_failed_exec_after_its_frame_does_not_hold_the_next_attach(self):
        """The host told this kernel reexec-now, then failed before the exec (a `reexec-failed` fault) and serves on under its
        old code: the fault's row is the whole of it, and the next attach asks again as it did before this change rather
        than waiting out the bound for a re-executed host that is not coming (and filing a second row)."""
        s = types.SimpleNamespace(sid=SID, name="web", _host_reexec_from=OLD, _reconnect=False)
        self.be._on_host_reexec_now(s)
        self.assertTrue(s._reconnect and s._host_reexec_closed)
        self.be._on_host_fault(s, {"t": "fault", "kind": "reexec-failed", "text": "RuntimeError"})
        self.assertEqual(self._rows(), ["host.reexec-failed"])
        self.assertFalse(s._host_reexec_closed, "the host serves on as it was: nothing to wait for")



class HandoverGuards(unittest.TestCase):
    """The guards around the lost-frame inference and the re-executed host's wait, with no real host (2026-09-23, the review
    of this lane: no real-host test decided them). The lease is written by hand, the live process being this test's own
    (pid and start time) or a sleeping child's, a dead one a pid above pid_max; host.log is synthetic rows; the transport
    is a stub carrying the hello's host identity and this kernel's pid; a re-executed host serving is a listener this
    test binds and the lease it writes. The state root is private and says `off` in session-hosts: nothing here starts a
    host."""
    KERNEL = 7001                                   # this kernel's pid as its transport names it (synthetic)

    def setUp(self):
        self.state = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.state, True)
        Path(self.state, "session-hosts").write_text("off\n")
        self.logs = []
        self.be = sb.SdkBackend(self.state, "/bin/true", lambda *a, **k: None, log=lambda m, *a, **k: self.logs.append(m))
        self.be.code_version = NEW
        self.me = {"pid": os.getpid(), "start": sb.proc_start(os.getpid())}
        self.dead = {"pid": 99999999, "start": "1"}   # above pid_max: no such process on any box

    def _lease(self, holder, cli=None):
        cli = cli or self.me
        lease = {"sid": SID, "fsid": FSID, "name": "web", "pid": cli["pid"], "start": cli["start"],
                 "holder": dict(holder, kind="host"), "version": OLD, "t": time.time()}
        sb.write_lease(self.state, lease)
        return lease

    def _hostlog(self, *rows):
        d = ht.host_dir(self.state, SID)
        d.mkdir(parents=True, exist_ok=True)
        (d / "host.log").write_text("".join(json.dumps(dict(r, t=time.time())) + "\n" for r in rows))

    def _attached(self, kernel_pid=None):
        return {"kind": "attached", "kernelPid": self.KERNEL if kernel_pid is None else kernel_pid, "ack": -1, "next": 0}

    def _sess(self, **over):
        s = types.SimpleNamespace(sid=SID, name="web", _host_reexec_from=OLD, _reconnect=False)
        for k, v in over.items():
            setattr(s, k, v)
        return s

    def _lost(self, hello_host):
        s = self._sess()
        t = types.SimpleNamespace(hello={"host": dict(hello_host)}, kernel={"pid": self.KERNEL})
        self.be._on_host_socket_lost(s, t)
        return s

    def _reconnects(self, s):
        return bool(s._reconnect) and bool(getattr(s, "_host_reexec_closed", False))

    # ── the lost-frame inference: _on_host_socket_lost ──
    def test_the_positive_control_a_live_holder_whose_log_records_the_exec_reconnects(self):
        self._lease(self.me)
        self._hostlog(self._attached(), {"kind": "reexec", "frameBuffered": 0})
        self.assertTrue(self._reconnects(self._lost(self.me)), self.logs)

    def test_a_log_whose_latest_line_is_the_new_code_serving_reconnects(self):
        """The kernel can read the log after the re-executed host has logged `reexeced` (a slow kernel, a quick exec)."""
        self._lease(self.me)
        self._hostlog(self._attached(), {"kind": "reexec"}, {"kind": "host-started"}, {"kind": "socket-ready"},
                      {"kind": "reexeced", "version": NEW})
        self.assertTrue(self._reconnects(self._lost(self.me)), self.logs)

    def test_a_dead_holder_is_a_lost_host_whatever_its_log_says(self):
        """A host that logged `reexec` and then died: the lease's holder is gone, so no handover (the orphan road replays)."""
        self._lease(self.dead)
        self._hostlog(self._attached(), {"kind": "reexec"})
        self.assertFalse(self._reconnects(self._lost(self.dead)))

    def test_a_lease_naming_another_holder_than_the_hello_is_a_lost_host(self):
        self._lease(self.me)
        self._hostlog(self._attached(), {"kind": "reexec"})
        self.assertFalse(self._reconnects(self._lost({"pid": self.me["pid"] + 1, "start": self.me["start"]})))

    def test_an_exec_logged_under_another_kernels_attach_is_not_this_kernels_handover(self):
        """The latest `attached` row names another kernel: the exec it records was that kernel's, not one this attach saw."""
        self._lease(self.me)
        self._hostlog(self._attached(kernel_pid=self.KERNEL + 1), {"kind": "reexec"})
        self.assertFalse(self._reconnects(self._lost(self.me)))

    # ── the re-executed host's wait: _await_reexeced_host, then _host_transport_for ──
    def _rows(self):
        p = Path(self.state) / "session-events.jsonl"
        return [json.loads(l)["kind"] for l in p.read_text().splitlines() if l.strip()] if p.exists() else []

    def _no_rows(self):
        """A subtest starts from no rows, so one case's row never reads as the next one's."""
        p = Path(self.state) / "session-events.jsonl"
        if p.exists():
            p.unlink()

    def _connect_sess(self, **over):
        """A session as the connect loop hands it to _host_transport_for on the planned reconnect (the frame arrived)."""
        return self._sess(**dict(dict(_host_reexec_closed=True, _host_is_attach=False, _host_end_grace=None,
                                      _on_cli_stderr=lambda line: None, _host=None), **over))

    def _connect(self, s, *patches):
        """_host_transport_for with the orphan road stood in for: the transport it returns, "orphan", and the rows the
        stand-in saw (died, the holder of the lease it was handed)."""
        roads = []

        async def orphan(sess, opts, lease, msg_classes, died=True):
            roads.append((died, self.be._holder_ident(lease)))
            raise TookOrphanRoad()
        with contextlib.ExitStack() as st:
            st.enter_context(mock.patch.object(self.be, "_host_orphan_recover", orphan))
            for p in patches:
                st.enter_context(p)
            try:
                return asyncio.run(self.be._host_transport_for(s, None, None)), roads
            except TookOrphanRoad:
                return "orphan", roads

    def test_a_wait_ends_at_once_when_the_hosts_log_records_its_end(self):
        """The host's own row, written just before it exits, ends the wait while its lease still reads live, with no row: the
        host did not serve on under its old code. cli-adopt-failed is a re-executed host whose adopt failed; host-crashed
        one whose run raised past it (its socket not served, say), which main logs on the way out (2026-09-23, the review
        of this lane: the second kind was listed and unpinned)."""
        lease = self._lease(self.me)
        for kind in ("cli-adopt-failed", "host-crashed"):
            with self.subTest(kind), mock.patch.object(ht, "SOCKET_WAIT_S", 3.0):
                self._no_rows()
                self._hostlog(self._attached(), {"kind": "reexec"}, {"kind": "host-started"}, {"kind": kind, "error": "KeyError"})
                s = self._sess()
                t0 = time.time()
                got = asyncio.run(self.be._await_reexeced_host(s, lease, OLD))
                self.assertIsNone(got)
                self.assertLess(time.time() - t0, ht.SOCKET_WAIT_S / 2, "no wait to the bound")
                self.assertEqual(s._host_reexec_wait, "ended", "the connect is told the log recorded the end")
                self.assertIsNone(s._host_reexec_from)
                self.assertEqual(self._rows(), [], "no host.reexec-failed row")
                self.assertTrue([l for l in self.logs if "its log records %s" % kind in l], self.logs)

    def test_a_wait_ends_at_once_when_the_lease_no_longer_names_a_live_host(self):
        """A death, read from the lease as it happens: the holder gone, the CLI gone, or the lease gone (a missing lease is a
        holder of no identity, so the identity check reads it, as it reads a lease another process holds, host or kernel).
        Each ends the wait at once with no row; the connect's own read after it sees the same (2026-09-23, the review of
        this lane)."""
        self._hostlog(self._attached(), {"kind": "reexec"})
        for case in ("the holder gone", "the CLI gone", "the lease gone"):
            with self.subTest(case), mock.patch.object(ht, "SOCKET_WAIT_S", 3.0):
                self._no_rows()
                self.logs.clear()
                lease = self._lease(self.dead) if case == "the holder gone" else \
                    self._lease(self.me, cli=self.dead) if case == "the CLI gone" else self._lease(self.me)
                if case == "the lease gone":
                    sb.remove_lease(self.state, SID)
                s = self._sess()
                t0 = time.time()
                self.assertIsNone(asyncio.run(self.be._await_reexeced_host(s, lease, OLD)))
                self.assertLess(time.time() - t0, ht.SOCKET_WAIT_S / 2, "no wait to the bound")
                self.assertEqual(s._host_reexec_wait, "ran", "the lease says it: the connect's own read sees it too")
                self.assertEqual(self._rows(), [])
                self.assertTrue([l for l in self.logs if "its lease no longer names that live host" in l], self.logs)

    def test_a_host_still_starting_holds_the_wait_to_its_bound(self):
        """The control: a live holder whose new code has started and not ended (a hung start) is waited for, and the bound
        files the row as before. An end row from an earlier process, with later rows after it, is not this one's: the
        log's newest line decides (2026-09-23, the review of this lane)."""
        lease = self._lease(self.me)
        self._hostlog({"kind": "host-started"}, {"kind": "cli-adopt-failed"}, {"kind": "host-started"}, self._attached(),
                      {"kind": "reexec"}, {"kind": "host-started"})
        s = self._sess()
        with mock.patch.object(ht, "SOCKET_WAIT_S", 0.3):
            self.assertIsNone(asyncio.run(self.be._await_reexeced_host(s, lease, OLD)))
        self.assertEqual(self._rows(), ["host.reexec-failed"])
        self.assertEqual(s._host_reexec_wait, "ran")

    def test_a_log_that_cannot_be_read_or_ends_mid_line_is_no_end(self):
        """No log at all (a host that never opened one, a directory being cleared), or a newest line the host is still
        writing: neither is an end, so the wait goes on to its bound (2026-09-23, the review of this lane: the unreadable
        branch was pinned only from another module)."""
        lease = self._lease(self.me)
        log = ht.host_dir(self.state, SID) / "host.log"
        for case in ("no log", "a line still being written"):
            with self.subTest(case):
                self._no_rows()
                if case == "no log":
                    shutil.rmtree(str(log.parent), ignore_errors=True)
                else:
                    self._hostlog(self._attached(), {"kind": "reexec"}, {"kind": "host-started"})
                    with open(log, "a") as f:
                        f.write('{"t": %.3f, "kind": "cli-adopt-fa' % time.time())
                s = self._sess()
                with mock.patch.object(ht, "SOCKET_WAIT_S", 0.3):
                    self.assertIsNone(asyncio.run(self.be._await_reexeced_host(s, lease, OLD)))
                self.assertEqual((self._rows(), s._host_reexec_wait), (["host.reexec-failed"], "ran"))

    def test_a_stale_beat_alone_never_ends_the_wait(self):
        """Nothing beats between the old code's exec and the new code's first lease write, which follows its socket, so a
        live host slow to start reads stale once its last beat is LEASE_TTL_S old (2026-09-23, the review of this lane: the
        fold before this one read that as a dead host and sent a live one down the orphan road). A live holder whose beat
        is stale and whose log shows a start with no end is still starting: waited for to the bound, then the row."""
        lease = self._lease(self.me)
        sb.write_lease(self.state, dict(lease, t=time.time() - sb.LEASE_TTL_S - 5))
        self.assertEqual(sb.lease_state(sb.read_lease(self.state, SID), time.time()), "stale-heartbeat", "the case under test")
        self._hostlog(self._attached(), {"kind": "reexec"}, {"kind": "host-started"})
        s = self._sess()
        with mock.patch.object(ht, "SOCKET_WAIT_S", 0.3):
            self.assertIsNone(asyncio.run(self.be._await_reexeced_host(s, lease, OLD)))
        self.assertEqual(self._rows(), ["host.reexec-failed"], "the bound's row, not an early end: %r" % self.logs)
        self.assertFalse([l for l in self.logs if "gone before it served" in l], self.logs)

    def test_the_connect_takes_the_orphan_road_when_the_log_records_the_end_ahead_of_the_lease(self):
        """_host_transport_for after the wait: the lease still reads live (the process not yet gone), but the host's log
        recorded its end, so the connect takes the orphan road, never an attach into nobody."""
        self._lease(self.me)
        self._hostlog(self._attached(), {"kind": "reexec"}, {"kind": "host-started"}, {"kind": "cli-adopt-failed"})
        s = self._connect_sess()
        got, roads = self._connect(s)
        self.assertEqual((got, roads), ("orphan", [(True, "%s:%s" % (self.me["pid"], self.me["start"]))]),
                         "a host death on the orphan road, never an attach into nobody")
        self.assertFalse(s._host_is_attach)
        self.assertEqual(s._host_reexec_wait, "", "the flag is consumed by the pass it was for")

    def test_the_connect_reads_the_lease_again_after_the_wait_and_a_dead_holder_takes_the_orphan_road(self):
        """The lease the attach branch acts on is the one read after the wait, not before it: a holder that dies while the
        connect waits (here killed and reaped as the wait begins) sends the connect down the orphan road."""
        holder, ident = self._sleeper()
        self._lease(ident)
        self._hostlog(self._attached(), {"kind": "reexec"})
        s = self._connect_sess()
        skew = self.be._host_reexec_on_skew

        async def dies_then_skew(sess, lease):
            holder.kill()
            holder.wait(timeout=10)                         # reaped: its lease no longer holds
            return await skew(sess, lease)
        got, roads = self._connect(s, mock.patch.object(self.be, "_host_reexec_on_skew", dies_then_skew))
        self.assertEqual((got, [d for d, _h in roads]), ("orphan", [True]), "the lease read after the wait decides the road")
        self.assertFalse(s._host_is_attach)

    def _sleeper(self):
        """A live process of the test's own to stand as a lease holder, and its identity; killed by the test."""
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(lambda: p.poll() is None and (p.kill(), p.wait(timeout=10)))
        return p, {"pid": p.pid, "start": sb.proc_start(p.pid)}

    def _serve(self, lease):
        """What the re-executed host does once it has started: its socket served (a listener that accepts), then its lease
        with the new version under the same holder."""
        lsn = socket.socket(socket.AF_UNIX)
        lsn.bind(str(ht.host_sock(self.state, SID)))
        lsn.listen(8)
        self.addCleanup(lsn.close)
        sb.write_lease(self.state, dict(lease, version=NEW, t=time.time()))

    def test_a_host_slow_to_start_whose_beat_goes_stale_is_waited_for_and_attached(self):
        """The slow-start shape (2026-09-23, the review of this lane, whose probe sent a live host eleven seconds into its
        start down the orphan road: a false host.died row, then a wait on the CLI that host was about to serve). The beat
        goes stale as the wait begins (the last beat was the old code's, before its exec), the wait passes over the stale
        lease and goes on, and the host then serves: the attach, never the orphan road. The host serves on the event of
        the wait having passed a stale beat, so nothing here is timed."""
        self._lease(self.me)
        self._hostlog(self._attached(), {"kind": "reexec"}, {"kind": "host-started"})
        s = self._connect_sess()
        skew, real_end, seen = self.be._host_reexec_on_skew, self.be._reexeced_host_end, []

        async def stale_then_skew(sess, lease):
            sb.write_lease(self.state, dict(lease, t=time.time() - sb.LEASE_TTL_S - 5))
            return await skew(sess, lease)

        def serves_after_a_stale_pass(sess):
            cur = sb.read_lease(self.state, SID)
            if not seen:
                seen.append(sb.lease_state(cur, time.time()))
                self._serve(cur)
            return real_end(sess)
        got, roads = self._connect(s, mock.patch.object(self.be, "_host_reexec_on_skew", stale_then_skew),
                                   mock.patch.object(self.be, "_reexeced_host_end", serves_after_a_stale_pass))
        self.assertEqual(roads, [], "never the orphan road for a host still starting: %r" % self.logs)
        self.assertIsInstance(got, ht.HostTransport, "the attach: %r" % self.logs)
        self.assertEqual(seen, ["stale-heartbeat"], "the wait passed over a stale beat (the case under test): %r" % self.logs)
        self.assertTrue(s._host_is_attach)
        self.assertEqual(self._rows(), [], "and no row: the handover completed")
        self.assertTrue([l for l in self.logs if "re-executed into this kernel's code" in l], self.logs)

    def test_a_holder_beating_on_its_old_code_past_the_bound_is_attached_with_the_row(self):
        """The lease the connect acts on after the wait is the FILE read again, not the lease it read before (2026-09-23,
        the review of this lane: a mutant that judged the pre-wait lease again passed every test). The old host's exec
        failed after its frame (its reexec-failed fault died with the socket), so it serves on under its old code and
        keeps beating: the wait runs out, files its row, and the attach meets that live host. The lease read before the
        wait was eleven seconds old, so judged again past the bound it would read stale, and the connect would send a live,
        beating host down the orphan road."""
        lease = self._lease(self.me)
        sb.write_lease(self.state, dict(lease, t=time.time() - sb.LEASE_TTL_S + 1))   # valid at the connect's first read
        self._hostlog(self._attached(), {"kind": "reexec"}, {"kind": "reexec-failed", "error": "OSError"})
        s = self._connect_sess()
        real_end = self.be._reexeced_host_end

        def beats(sess):                                     # the live holder beats while the kernel waits
            sb.write_lease(self.state, dict(sb.read_lease(self.state, SID), t=time.time()))
            return real_end(sess)
        got, roads = self._connect(s, mock.patch.object(ht, "SOCKET_WAIT_S", 1.5),
                                   mock.patch.object(self.be, "_reexeced_host_end", beats))
        self.assertEqual(roads, [], "never the orphan road for a live host that beats")
        self.assertIsInstance(got, ht.HostTransport)
        self.assertEqual(self._rows(), ["host.reexec-failed"], "the handover did not complete: the bound's row")

    def test_past_the_whole_bound_a_silent_holder_reads_as_any_connect_reads_it(self):
        """The other side of the stale beat (2026-09-23, the review of this lane): the wait forgives a stale beat only up to
        its bound, which is longer than the lease's twelve seconds. Past it, the lease is judged at the time of that read,
        as at any connect's first read: a host that has neither served nor beaten reads as an orphan, which the next pass
        would read at main too (after an attach into a socket nobody serves). Judged on the clock of the read before the
        wait, it read live and the connect attached into nobody. The beat is set to go stale a fifth of a second into a
        1.5 s bound, the one margin here; the stale pass is asserted, so a lost margin reports itself."""
        self._lease(self.me)
        self._hostlog(self._attached(), {"kind": "reexec"}, {"kind": "host-started"})
        s = self._connect_sess()
        skew, real_end, seen = self.be._host_reexec_on_skew, self.be._reexeced_host_end, []

        async def goes_stale_then_skew(sess, lease):
            sb.write_lease(self.state, dict(lease, t=time.time() - sb.LEASE_TTL_S + 0.2))
            return await skew(sess, lease)

        def notes(sess):
            seen.append(sb.lease_state(sb.read_lease(self.state, SID), time.time()))
            return real_end(sess)
        got, roads = self._connect(s, mock.patch.object(ht, "SOCKET_WAIT_S", 1.5),
                                   mock.patch.object(self.be, "_host_reexec_on_skew", goes_stale_then_skew),
                                   mock.patch.object(self.be, "_reexeced_host_end", notes))
        self.assertEqual(self._rows(), ["host.reexec-failed"], "the bound's row, not an early end: %r" % self.logs)
        self.assertEqual((got, [d for d, _h in roads]), ("orphan", [True]), "then the lease as any connect reads it")
        self.assertIn("stale-heartbeat", seen, "the wait went on over a stale beat (the case under test)")

    def test_a_lease_that_names_another_holder_ends_the_wait_and_the_attach_meets_that_holder(self):
        """The wait ends at once, with no row, when the lease names a holder other than the one the handover began with (an
        exec keeps the pid and its start time, so another identity is another process), and the attach that follows meets
        the holder the file names now, never the one read before the wait (2026-09-23, the review of this lane: the
        holder-identity stop was unpinned)."""
        lease = self._lease(self.me)
        self._hostlog(self._attached(), {"kind": "reexec"})
        _p, other = self._sleeper()
        s = self._connect_sess()
        skew = self.be._host_reexec_on_skew

        async def taken_then_skew(sess, lease):
            sb.write_lease(self.state, dict(lease, holder=dict(other, kind="host"), t=time.time()))
            return await skew(sess, lease)
        t0 = time.time()
        with mock.patch.object(ht, "SOCKET_WAIT_S", 3.0):
            got, roads = self._connect(s, mock.patch.object(self.be, "_host_reexec_on_skew", taken_then_skew))
            took = time.time() - t0
            self.assertLess(took, ht.SOCKET_WAIT_S / 2, "at once, not the bound")
        self.assertEqual(roads, [])
        self.assertIsInstance(got, ht.HostTransport)
        self.assertEqual(self._rows(), [], "no host.reexec-failed row")
        self.assertTrue([l for l in self.logs if "attaching to the live host (pid %s)" % other["pid"] in l],
                        "the attach meets the holder the lease names now: %r" % self.logs)

    def test_an_attach_that_waited_for_nothing_reads_the_lease_once(self):
        """A same-version attach waits for nothing, so the connect reads the lease once, as at main: the read after a wait,
        and its two process-start reads (a `ps` run each on macOS), come only after a wait (2026-09-23, the review of
        this lane)."""
        lease = self._lease(self.me)
        sb.write_lease(self.state, dict(lease, version=NEW))
        s = self._connect_sess(_host_reexec_closed=False)
        reads, real = [], sb.read_lease

        def counted(state_dir, sid):
            reads.append(sid)
            return real(state_dir, sid)
        got, roads = self._connect(s, mock.patch.object(sb, "read_lease", counted))
        self.assertIsInstance(got, ht.HostTransport)
        self.assertEqual(len(reads), 1, "one read of the lease for an attach that waited for nothing")

    def test_a_connect_that_finds_the_host_gone_drops_the_handover(self):
        """A host gone by the connect's first read (dead: the orphan road; its lease gone: the none road) takes the handover
        this kernel asked it for with it. _host_reexec_from stood at main, so the next host this kernel started said hello on this
        kernel's code and filed a host.reexeced row for a re-exec that never happened (2026-09-23, the review of this lane,
        on the road this lane now sends a host that dies in its start down)."""
        for road in ("orphan", "none"):
            with self.subTest(road):
                sb.remove_lease(self.state, SID)
                shutil.rmtree(str(ht.host_dir(self.state, SID)), ignore_errors=True)
                self._no_rows()
                if road == "orphan":
                    self._lease(self.dead)
                    self._hostlog(self._attached(), {"kind": "reexec"})
                s = self._connect_sess(_host_reexec_closed=True, inflight=0, _inflight_texts=[])
                got, roads = self._connect(s)
                self.assertEqual(got, "orphan" if road == "orphan" else None, "the %s road" % road)
                self.assertEqual((s._host_reexec_from, s._host_reexec_closed), (None, False), "the handover is dropped")
                hello = {"host": {"pid": 4321, "start": "9", "version": NEW}, "cli": {"pid": 4322, "start": "9"},
                         "journal": {"next": 0}}
                with mock.patch.object(self.be, "_fresh_cli_decision", lambda sess, c: None), \
                        mock.patch.object(self.be, "_file_host_log_rows", lambda sess: None):
                    self.be._on_host_hello(s, hello)                # the next host, started on this kernel's code
                self.assertEqual(self._rows(), ["host.attached"], "no host.reexeced row for a re-exec that never happened")


if __name__ == "__main__":
    unittest.main()
