#!/usr/bin/env python3
"""Every compaction door on a Codex session takes the backend's own verb (2026-09-19).

The guard in front of the setter route (tests/test_codex_slash_guard.py) refuses a slash command a Codex session cannot
take; the native clear registered the first heads in its handler table (tests/test_codex_clear_route.py); this is the
third head, and the one door every compaction surface shares. The chat and timeline batteries, POST /compact and `romp
compact` land in _compact_or_park, a typed or sent "/compact" in the route's Codex arm: for a backend that compacts
natively (SessionBackend.compact, _native_compact) the verb is called after the same one drive-op gate, with NO
optimistic "compacting" stamp (the backend's compacting() bracket is the authority the kernel already reads first);
"busy" parks the ("compact",) op the drain retries at the turn's end; a reason is said with the session and, on the
typed path, the press named, filed for POST /send and POST /compact, and kept on the bell. Typed instructions are
refused loudly: Codex takes none, and compacting anyway would drop the words silently. The drain fires a parked
("compact",) op and a ("command", "/compact") op a Codex session parked before this head existed through the same verb,
leaves a "busy" head with no clock and no in-flight record, and ends the pass on a fired compaction as it does on a
send. Every backend without the verb keeps the literal "/compact" send and the stamp, byte for byte
(tests/test_kernel_compact_route.py pins that path over a send-only fake).

Fixtures are synthetic: private placeholder sids (parked ops, notices and registry rows key by sid, and another
module's journal must never land on these), an invented copy id in the kernel's echo form, the demo world's session
names, invented prompts. The stub below is the kernel's view of a backend with the verb: compact(sid) answers a
scripted string and records; send/set_effort record; busy reads True once a compaction stands (the bracket), else
None; _session/owns/live_sessions answer for the module's sid the way _session_backend's durable-row read does."""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from romp_load import load_source
from unittest import mock

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
# Hermetic state BEFORE the load: the kernel resolves its state root at import time, and only pytest runs
# conftest's floor (a bare unittest run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
os.environ["ROMP_MANAGER_PORT"] = "1"             # a dead port, never an inherited live one
km = load_source("romp_kernel_codex_compact", os.path.join(BIN, "romp-kernel"))
# Per-session hosts are on by default: a state root without this file starts a real host for any session a
# backend connects. Nothing here connects one; the rule is unconditional for a module that mints its own root.
_HOSTS = Path(os.environ["XDG_STATE_HOME"], "romp", "session-hosts")
_HOSTS.parent.mkdir(parents=True, exist_ok=True)
_HOSTS.write_text("off")

SID = "11111111-2222-4333-8444-0c0e0c0e0001"      # private to this module: the door, route and drain classes
SID_REAL = "11111111-2222-4333-8444-0c0e0c0e0002" # the real-backend class (a registry row is written for it)
QID = "echo:" + "ce" * 16                          # the press-minted copy id, in the kernel's echo form


def until(fn, timeout=5.0, step=0.01):
    dl = time.time() + timeout
    while time.time() < dl:
        if fn():
            return True
        time.sleep(step)
    return False


class _Backend:
    """The kernel's view of a backend that compacts natively."""
    def __init__(self):
        self.calls = []
        self.answer = ""
        self.bracket = False

    def compact(self, sid):
        self.calls.append(("compact", sid))
        if self.answer == "":
            self.bracket = True
        return self.answer

    def compacting(self, sid):
        return self.bracket

    def send(self, sid, text):
        self.calls.append(("send", text))
        return True

    def set_effort(self, sid, v):
        self.calls.append(("effort", v))
        return True

    def busy(self, sid):
        return True if self.bracket else None

    def _session(self, sid):
        return {"sid": sid} if sid == SID else None

    def owns(self, sid):
        return sid == SID

    def live_sessions(self):
        return {}


def _forget(sid):
    """Drop the sid's parked ops from memory AND the disk mirror, and every per-sid latch these paths touch."""
    km._pending_ops.pop(sid, None)
    km._save_pending_ops()
    km._moving.discard(sid)
    km._drain_hold.pop(sid, None)
    km._inflight_ops.pop(sid, None)
    km._model_switch_pending.pop(sid, None)
    km._compact_clicked.pop(sid, None)


class _Base(unittest.TestCase):
    """The stub is THE Codex backend (`be is _codex()` is the identity the route's arm tests) and owns SID; the
    drive-op gate is a counter answering `verdict`; the drain's gates are quiet; the chat broadcast and the optimistic
    cue stamp are recorders; the bell ring's length is noted so a test can assert its own row."""
    def setUp(self):
        self.be = _Backend()
        self.sent, self.broadcast, self.gate_calls, self.marked = [], [], [], []
        self.verdict = False
        self.client = {"send": lambda t: self.sent.append(json.loads(t))}
        _forget(SID)
        self.addCleanup(_forget, SID)
        stubs = {
            "_codex": lambda: self.be,
            "_sdk": lambda: None,                        # no SdkBackend is built for a lookup that ends at Codex
            "_ops_gate": lambda sid: (self.gate_calls.append(str(sid)), self.verdict)[1],
            "_compacting_now": lambda sid, **k: False,
            "_working_now": lambda sid: False,
            "_limit_hold": lambda sid: None,             # the account gate is its own axis
            "_kernel_knows": lambda sid: True,
            "_push_soon": lambda *a, **k: None,
            "_host_for_sid": lambda sid: None,
            "_send_to_app": lambda app, msg: self.broadcast.append((app, msg)),
            "_mark_compacting": lambda sid: self.marked.append(str(sid)),
        }
        for name, stub in stubs.items():
            p = mock.patch.object(km, name, stub)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(km.Sessions, "backend_for", staticmethod(lambda sid: self.be))
        p.start()
        self.addCleanup(p.stop)
        self.ring0 = len(km._SYNC_NOTICES)

    def _last_notice(self):
        self.assertGreater(len(km._SYNC_NOTICES), self.ring0, "a refusal files one row on the bell's ring")
        return km._SYNC_NOTICES[-1]

    def _warns(self):
        return [msg for app, msg in self.broadcast if app == "chat" and msg.get("type") == "warn"]

    def _live(self):
        return mock.patch.object(km.Sessions, "live", staticmethod(lambda: {SID: {"state": "waiting", "backend": "codex"}}))


class CodexCompactDoor(_Base):
    def test_the_compact_door_calls_the_native_verb_never_send_nor_the_stamp(self):
        state = {}
        self.assertIs(km._compact_or_park(self.be, SID, state=state), False, "fired now: the bracket is the cue")
        self.assertEqual(self.be.calls, [("compact", SID)])
        self.assertEqual(self.marked, [], "no optimistic stamp: the backend's compacting() is the authority")
        self.assertEqual(state, {})
        self.assertEqual(self.gate_calls, [SID], "the same one gate every door pays")
        self.assertNotIn(SID, km._pending_ops)
        self.assertEqual(self._warns(), [])
        with self._live():
            self.assertEqual(km._compact_request(SID), {"ok": True, "queued": False}, "POST /compact's brain: the same door")
        self.assertEqual(self.be.calls, [("compact", SID)] * 2)

    def test_a_gated_or_busy_compact_parks_the_compact_op(self):
        self.verdict = True                               # mid-turn, behind a queue, compacting or under a hold
        self.assertIs(km._compact_or_park(self.be, SID), True)
        self.assertEqual(km._pending_ops[SID], [("compact",)], "a visible '/compact' chip in press order")
        self.assertEqual(self.be.calls, [], "parked: the drain asks the backend at the turn's end")
        _forget(SID)
        self.verdict = False
        self.be.answer = "busy"                           # the worker's lock sliver, or a compaction already standing
        self.assertIs(km._compact_or_park(self.be, SID), True)
        self.assertEqual(self.be.calls, [("compact", SID)])
        self.assertEqual(km._pending_ops[SID], [("compact",)], "parked after the answer; the drain retries")
        self.assertEqual(self._warns(), [], "'busy' is an internal answer, never shown")
        self.assertEqual(self.marked, [])

    def test_a_refused_compact_is_said_and_filed_for_post_compact(self):
        why = "this session has ended — revive it first"
        self.be.answer = why
        state = {}
        self.assertIsNone(km._compact_or_park(self.be, SID, state=state), "neither parked nor fired")
        self.assertEqual(state, {"refused": why})
        self.assertEqual(self._warns(), [{"type": "warn", "id": SID, "sid": SID, "text": why}],
                         "no socket reaches this door: the chat panes hear a broadcast naming the session")
        self.assertEqual([msg for app, msg in self.broadcast if app == "timeline"],
                         [{"type": "settingRefused", "gesture": "command", "sid": SID, "flag": "", "text": why, "filed": True}],
                         "the timeline lane that took the battery click hears it on the frame that page renders (a warn it "
                         "drops), so its click stamp ends on this event; `filed` says the bell row below is already the ring's")
        self.assertEqual(self._last_notice()["kind"], "refused")
        self.assertEqual(self.marked, [], "no cue for a compaction that never started")
        self.assertNotIn(SID, km._pending_ops, "a refusal is not an op")
        with self._live():
            self.assertEqual(km._compact_request(SID), {"ok": False, "error": why}, "`romp compact` prints the backend's words")

    def test_a_backend_without_the_verb_keeps_the_literal_send_and_the_stamp(self):
        class SendOnly:
            def __init__(self):
                self.calls = []

            def send(self, sid, text, user=False):
                self.calls.append(("send", text, user))
                return True
        be = SendOnly()
        self.assertFalse(km._native_compact(be), "no verb: the SDK-shaped path")
        self.assertFalse(km._native_compact(km._UNOWNED), "the unowned route inherits the ABC's default, never the native branch")
        self.assertTrue(km._native_compact(self.be))
        self.assertIs(km._compact_or_park(be, SID), False)
        self.assertEqual(be.calls, [("send", "/compact", True)], "the word, as the user's gesture")
        self.assertEqual(self.marked, [SID], "and the instant cue: the SDK path is byte-identical")


class CodexCompactRoute(_Base):
    def test_a_typed_compact_takes_the_route_never_the_send(self):
        state = {}
        self.assertTrue(km._route_meta_command(self.be, SID, "/compact", self.client, state=state, qid=QID))
        self.assertEqual(self.be.calls, [("compact", SID)])
        self.assertEqual(state, {"queued": False})
        self.assertEqual(self.sent, [], "a compaction that started says nothing on the socket: the chip flips")
        self.assertEqual(self.gate_calls, [SID], "ONE drive-op gate read, the /effort arm's cost")
        self.assertEqual(self.marked, [])
        self.assertNotIn(SID, km._pending_ops)
        # Claude's /compact keeps its path: with another object as the Codex backend, this one is not it, and the
        # setter body's one-token guard answers False so the caller sends the text the CLI executes
        other = _Backend()
        with mock.patch.object(km, "_codex", lambda: other):
            self.assertFalse(km._route_meta_command(self.be, SID, "/compact", self.client, state={}))
        self.assertEqual((self.be.calls, other.calls), ([("compact", SID)], []))

    def test_typed_instructions_are_refused_loudly_never_dropped(self):
        for text in ("/compact focus on the tests", "/compact\tnow"):
            self.be.calls.clear()
            self.sent.clear()
            state = {}
            self.assertTrue(km._route_meta_command(self.be, SID, text, self.client, state=state, qid=QID), text)
            self.assertEqual(self.be.calls, [], "%r: no compaction with the words dropped" % text)
            why = state["refused_compact"]
            self.assertIn("without instructions", why)
            self.assertIn("bare /compact", why)
            self.assertNotIn("backend", why)
            self.assertIs(state["queued"], False)
            self.assertEqual(self.sent, [{"type": "warn", "text": why, "sid": SID, "qid": QID}], text)
            self.assertEqual(self._last_notice()["kind"], "refused")
            self.assertNotIn(SID, km._pending_ops)
        # a second LINE after the head is refused before the handler is reached, by the route's whole-message rule
        # for every registered head (the native clear's fold, 2026-09-19): the words name what the message must be,
        # filed under the guard's own key, on the socket with the press named, and the verb never runs
        self.be.calls.clear()
        self.sent.clear()
        state = {}
        text = "/compact\nfocus on the tests"
        self.assertTrue(km._route_meta_command(self.be, SID, text, self.client, state=state, qid=QID), text)
        self.assertEqual(self.be.calls, [], "no compaction with the second line dropped")
        self.assertIn("must be the whole message", state["refused"])
        self.assertIn("/compact", state["refused"])
        self.assertNotIn("refused_compact", state)
        self.assertNotIn("queued", state)
        self.assertEqual([(f["type"], f["sid"], f["qid"]) for f in self.sent], [("warn", SID, QID)], text)
        self.assertNotIn(SID, km._pending_ops)
        self.assertEqual(km._deliver_text(SID, "/compact with words"), (False, km._CODEX_COMPACT_NO_WORDS, False),
                         "POST /send and `romp send` answer the same words")

    def test_a_busy_or_gated_typed_compact_parks_as_the_compact_op(self):
        self.verdict = True
        state = {}
        self.assertTrue(km._route_meta_command(self.be, SID, "/compact", self.client, state=state, qid=QID))
        self.assertEqual(km._pending_ops[SID], [("compact",)], "the same op the battery parks: one chip body, one cancel")
        self.assertIs(state["queued"], True)
        self.assertEqual(self.be.calls, [])
        _forget(SID)
        self.verdict = False
        self.be.answer = "busy"
        state = {}
        self.assertTrue(km._route_meta_command(self.be, SID, "/compact", self.client, state=state))
        self.assertEqual(self.be.calls, [("compact", SID)])
        self.assertEqual(km._pending_ops[SID], [("compact",)], "parked after the answer")
        self.assertIs(state["queued"], True)
        self.assertEqual(self.sent, [], "'busy' is never shown")
        self.assertEqual(km._parked_md(("compact",)), "/compact")

    def test_a_refused_typed_compact_is_said_with_the_press_named(self):
        why = "Couldn't compact this conversation: synthetic"
        self.be.answer = why
        state = {}
        self.assertTrue(km._route_meta_command(self.be, SID, "/compact", self.client, state=state, qid=QID))
        self.assertEqual(state, {"refused_compact": why, "queued": False})
        self.assertEqual(self.sent, [{"type": "warn", "text": why, "sid": SID, "qid": QID}],
                         "the frame names the session and the press: the chat retires the bubble it drew and puts the words back")
        self.assertEqual(self._warns(), [], "the socket carried it: no broadcast")
        self.assertEqual(self.broadcast, [], "no timeline frame either: no lane clicked, and the words rode the socket")
        self.assertEqual(self._last_notice()["kind"], "refused")
        self.assertNotIn(SID, km._pending_ops)
        self.assertEqual(self.marked, [])
        self.assertEqual(km._deliver_text(SID, "/compact"), (False, why, False))
        warns = self._warns()
        self.assertEqual(len(warns), 1, "POST /send's press has no socket: the chat panes hear a broadcast")
        self.assertEqual((warns[0]["id"], warns[0]["sid"], warns[0]["text"]), (SID, SID, why))
        self.assertNotIn("qid", warns[0], "a POST route's press has no copy id")

    def test_the_palette_and_the_table_list_compact(self):
        names = [c["name"] for c in km._CODEX_COMMANDS]
        self.assertIn("compact", names, "the composer's '/' list offers what the route now takes")
        self.assertLess(names.index("new"), names.index("compact"))
        self.assertIs(km._CODEX_SLASH_HANDLERS["/compact"], km._codex_compact_command)


class CodexCompactDrain(_Base):
    def test_the_drain_fires_a_parked_compact_natively_and_ends_the_pass(self):
        km._pending_ops[SID] = [("compact",), ("send", "then this", None)]
        km._save_pending_ops()
        km._apply_pending_ops()
        self.assertEqual(self.be.calls, [("compact", SID)], "the verb, never the word")
        self.assertEqual(km._pending_ops[SID], [("send", "then this", None)],
                         "the compaction must END before the message behind it fires: the pass ends here")
        self.assertEqual(self.marked, [], "no stamp: the bracket is the cue")
        self.assertNotIn(SID, km._inflight_ops)
        self.assertNotIn(SID, km._drain_hold, "busy() reads True under the bracket: no hold armed")
        self.assertEqual(self._warns(), [])

    def test_a_typed_compact_parked_before_the_upgrade_runs_natively(self):
        # pending-ops.json survives a restart: a ("command", "/compact") op a Codex session parked before this head
        # existed is the native compaction, not the guard's refusal and never the word as text
        km._pending_ops[SID] = [("command", "/compact", "human", QID, True), ("send", "after it", None)]
        km._save_pending_ops()
        km._apply_pending_ops()
        self.assertEqual(self.be.calls, [("compact", SID)])
        self.assertEqual(self.marked, [], "the typed form gets no stamp either: the bracket is the cue")
        self.assertEqual(km._pending_ops[SID], [("send", "after it", None)])
        self.assertEqual(self._warns(), [])
        _forget(SID)
        self.be.calls.clear()
        self.be.bracket = False
        # words after the head, from the old mirror: refused with the reason and the parked copy's id, popped, the
        # setting behind it delivered; the words are never dropped silently into a compaction
        km._pending_ops[SID] = [("command", "/compact focus on x", "human", QID, True), ("effort", "high")]
        km._save_pending_ops()
        km._apply_pending_ops()
        self.assertEqual(self.be.calls, [("effort", "high")], "no compaction; the setting behind it delivers")
        warns = self._warns()
        self.assertEqual(len(warns), 1)
        self.assertEqual((warns[0]["sid"], warns[0]["qid"]), (SID, QID))
        self.assertIn("without instructions", warns[0]["text"])
        self.assertNotIn(SID, km._pending_ops)
        self.assertEqual(self._last_notice()["kind"], "refused")

    def test_a_busy_answer_leaves_the_head_and_clears_the_inflight_slot(self):
        self.be.answer = "busy"
        km._pending_ops[SID] = [("compact",), ("send", "then this", None)]
        km._save_pending_ops()
        km._apply_pending_ops()
        self.assertEqual(self.be.calls, [("compact", SID)], "the pass ends at the busy compact: nothing behind it fires")
        self.assertEqual(km._pending_ops[SID], [("compact",), ("send", "then this", None)], "the head stays for the next cycle")
        self.assertNotIn(SID, km._drain_hold, "no clock: the turn-end poke's cycle (or the backstop) is the retry")
        self.assertNotIn(SID, km._inflight_ops, "nothing was handed over, so nothing is recorded…")
        self.assertIsNone(km._cancel_parked(SID, 0, "/compact"), "…and the chip's cancel still takes it")
        self.assertEqual(km._pending_ops[SID], [("send", "then this", None)])
        self.assertEqual(self._warns(), [], "'busy' is never shown")
        self.assertEqual(self.marked, [])

    def test_a_refused_compact_in_the_drain_warns_and_pops(self):
        why = "this session has ended — revive it first"
        self.be.answer = why
        km._pending_ops[SID] = [("compact",), ("effort", "high")]
        km._save_pending_ops()
        km._apply_pending_ops()
        self.assertEqual(self.be.calls, [("compact", SID), ("effort", "high")], "popped; the setting behind it still delivers")
        self.assertNotIn(SID, km._pending_ops)
        self.assertEqual(self._warns(), [{"type": "warn", "id": SID, "sid": SID, "text": why}])
        self.assertEqual([msg for app, msg in self.broadcast if app == "timeline"],
                         [{"type": "settingRefused", "gesture": "command", "sid": SID, "flag": "", "text": why, "filed": True}],
                         "a parked click is a click: the lane whose battery press parked still holds its stamp, so the drain's "
                         "refusal reaches the timeline on the same frame the door's does (2026-09-21)")
        self.assertEqual(self._last_notice()["kind"], "refused")
        self.assertEqual(self.marked, [])
        self.assertFalse(any("backend refused it" in str(m.get("text")) for _, m in self.broadcast),
                         "the backend's own words, never the generic toast")


class RealBackendCompact(unittest.TestCase):
    """The route, the gates and the drain over the REAL CodexBackend with the codex-backend module's own scripted
    client, installed as the kernel's singleton so `be is _codex()` holds against the real object, Sessions.backend_for
    resolves through it, and _compacting_now reads the backend's bracket. The per-session gates are real except the
    account one (quiet)."""
    @classmethod
    def setUpClass(cls):
        saved = os.environ["XDG_STATE_HOME"]
        try:
            cls.cbt = load_source("romp_codex_backend_tests_for_compact", os.path.join(HERE, "test_codex_backend.py"))
        finally:
            os.environ["XDG_STATE_HOME"] = saved     # that module floors its own root at import; this one keeps its own

    def setUp(self):
        self.fake = self.cbt.FakeClient()
        # Over km.jd.STATE read AT SETUP, with a scrub after (2026-09-19): load_source re-executes judge.py into
        # ONE shared module object, so under a suite jd.STATE is whichever module bound it last, and the kernel's
        # read side (_path_of, discovery) resolves a Codex transcript through that shared module at run time. The
        # backend must write where that read side reads, and without the scrub its registry row, names/ entry and
        # transcript stayed in a root two other modules' discovery walks read (an extra discovered session there).
        # Green alone, red only under the whole suite; the clear route's real-backend class is the twin.
        self.root = km.jd.STATE
        self.be = self.cbt.cb.CodexBackend(self.root, client_factory=lambda: self.fake)
        with km._codex_lock:
            self._saved_singleton = km._codex_backend
            km._codex_backend = self.be
        self.sent, self.marked = [], []
        self.client = {"send": lambda t: self.sent.append(json.loads(t))}
        for name, stub in {"_sdk": lambda: None, "_push_soon": lambda *a, **k: None, "_limit_hold": lambda sid: None,
                           "_mark_compacting": lambda sid: self.marked.append(str(sid))}.items():
            p = mock.patch.object(km, name, stub)
            p.start()
            self.addCleanup(p.stop)
        _forget(SID_REAL)
        self.addCleanup(_forget, SID_REAL)
        self._reg = self.root / "codex" / "registry.json"
        self._reg_before = self._reg.read_bytes() if self._reg.exists() else None
        projects = self.root / "codex" / "projects"
        self._files_before = set(projects.rglob("*")) if projects.exists() else set()
        self.addCleanup(self._scrub)                    # after tearDown (cleanup order): no worker writes then

    def _scrub(self):
        """Leave the root as found: the transcript the test's thread wrote, the names/ entry and the registry row."""
        projects = self.root / "codex" / "projects"
        if projects.exists():
            for path in sorted(set(projects.rglob("*")) - self._files_before, key=lambda q: -len(q.parts)):
                try:
                    path.unlink() if path.is_file() else path.rmdir()
                except OSError:
                    pass
        try:
            (self.root / "names" / SID_REAL).unlink()
        except FileNotFoundError:
            pass
        if self._reg_before is None:
            try:
                self._reg.unlink()
            except FileNotFoundError:
                pass
        else:
            self._reg.write_bytes(self._reg_before)

    def tearDown(self):
        for _, sess in self.be._session_items():        # a worker returns when it wakes to a dead session
            with sess.lock:
                sess.dead = True
            sess.kick.set()
        self.fake.close()                               # the pump returns when its client reads as closed
        with km._codex_lock:
            km._codex_backend = self._saved_singleton
        deadline = time.time() + 5
        while time.time() < deadline and any(t.is_alive() for t in self._threads()):
            time.sleep(0.02)

    def _threads(self):
        out = []
        for _, sess in self.be._session_items():
            w = getattr(sess, "worker", None)
            if w is not None:
                out.append(w)
        return out

    def _status(self, kind):
        status = {"type": kind, **({"activeFlags": []} if kind == "active" else {})}
        self.fake.push_global("thread/status/changed", {"threadId": "T-1", "status": status})

    def test_a_typed_compact_latches_the_bracket_every_gate_reads_and_the_idle_writes_the_divider(self):
        sid = self.be.spawn("web", "/TESTDIR-compact", sid=SID_REAL)
        self.assertIs(km.Sessions.backend_for(sid), self.be, "the real singleton owns the row")
        self.assertTrue(self.be.send(sid, "first synthetic turn"))
        self.assertTrue(self.cbt._lock_free(self.be, sid))
        state = {}
        self.assertTrue(km._route_meta_command(self.be, sid, "/compact", self.client, state=state, qid=QID))
        self.assertEqual(state, {"queued": False})
        self.assertEqual(self.sent, [], "no warn: the compaction started")
        self.assertEqual(self.fake.called("thread_compact"), [("thread_compact", "T-1")])
        self.assertEqual(len(self.fake.called("turn_start")), 1, "no turn opened with the word")
        self.assertEqual(self.be._session(sid).queue, [], "the durable queue took nothing")
        self.assertEqual(self.marked, [], "no optimistic stamp")
        self.assertIs(km._compacting_now(sid), True, "the kernel's compacting gate reads the backend's bracket")
        self.assertEqual(km.Sessions.live()[sid]["state"], "compacting")
        self.assertIs(km._send_or_park(self.be, sid, "typed meanwhile", user=True), True, "a message typed meanwhile parks")
        self.assertEqual([op[:2] for op in km._pending_ops[sid]], [("send", "typed meanwhile")])
        self._status("active")
        self._status("idle")
        self.assertTrue(until(lambda: km._compacting_now(sid) is False), "the idle after the active ends it on every surface")
        path = self.be.transcript_path(sid)
        recs = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
        cbs = [r for r in recs if r.get("subtype") == "compact_boundary"]
        self.assertEqual(len(cbs), 1)
        self.assertEqual(cbs[0]["compactMetadata"], {"trigger": "manual"})
        km._apply_pending_ops()                          # the pusher's cycle after the poke: the parked message goes in
        self.assertNotIn(sid, km._pending_ops)
        self.assertTrue(until(lambda: not self.be.busy(sid) and not self.be.pending_queued(sid)))
        last = self.fake.called("turn_start")[-1]
        self.assertEqual((last[1], [i["text"] for i in last[2]]), ("T-1", ["typed meanwhile"]))
        self.assertEqual(km.Sessions.live()[sid]["state"], "waiting")

    def test_a_failed_compactions_card_carries_no_retry_action(self):
        # The failed compaction rides the launch-error card, which wears the API-error dress: a retrying-soon meta and
        # two Retry buttons, and the press sent the word "retry" into the thread as a turn (review find, 2026-09-21).
        # Nothing retries a compaction, so the bracket's end notices carry noRetry and the built status says so
        # (apiNoRetry, the apiRefusal precedent): the chat renders the card with no meta and no actions. Scoped to the
        # bracket's ends: a failed turn's card keeps its button.
        sid = self.be.spawn("web", "/TESTDIR-compact-failed", sid=SID_REAL)
        self.assertTrue(self.be.send(sid, "first synthetic turn"))
        self.assertTrue(self.cbt._lock_free(self.be, sid))
        self.assertIs(km._compact_or_park(self.be, sid), False, "fired now, through the one door")
        self._status("active")
        self._status("systemError")
        self.assertTrue(until(lambda: km._compacting_now(sid) is False), "the loud end")
        err = self.be.launch_error(sid)
        self.assertIn("could not compact", err["text"])
        self.assertIs(err.get("noRetry"), True, "the notice says nothing retries it")
        out = km.build_session(sid, time.time())
        cards = [e for e in out["events"] if e.get("kind") == "apiError"]
        self.assertEqual(len(cards), 1, cards)
        self.assertIn("could not compact", cards[0]["text"])
        self.assertIs(out["status"]["apiNoRetry"], True, "the flag the card reads off the live status: no Retry, no countdown")
        s = self.be._session(sid)
        with s.lock:
            s.launch_error = {"text": "codex turn rejected: model gpt-x is not supported", "at": time.time(), "limit": False}
        out = km.build_session(sid, time.time())
        self.assertEqual(len([e for e in out["events"] if e.get("kind") == "apiError"]), 1)
        self.assertIs(out["status"]["apiNoRetry"], False, "a failed turn's card keeps its button")


if __name__ == "__main__":
    unittest.main()
