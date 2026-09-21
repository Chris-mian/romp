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
import inspect
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
_REAL_SEND_TO_APP = km._send_to_app                # the broadcast as shipped, for the one test that pins its reach
# Per-session hosts are on by default: a state root without this file starts a real host for any session a
# backend connects. Nothing here connects one; the rule is unconditional for a module that mints its own root.
_HOSTS = Path(os.environ["XDG_STATE_HOME"], "romp", "session-hosts")
_HOSTS.parent.mkdir(parents=True, exist_ok=True)
_HOSTS.write_text("off")

SID = "11111111-2222-4333-8444-0c0e0c0e0001"      # private to this module: the door, route and drain classes
SID_REAL = "11111111-2222-4333-8444-0c0e0c0e0002" # the real-backend class (a registry row is written for it)
QID = "echo:" + "ce" * 16                          # the press-minted copy id, in the kernel's echo form
QID2 = "echo:" + "cf" * 16                         # a second press's id, for two texts parked together


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
        self.live = {}              # what live_sessions reports: a resume or a move makes the row live, a kill takes it out
        self.move_answer = ""       # SdkBackend.move's shape: "" moved; any other string a refusal after the resume

    def compact(self, sid):
        self.calls.append(("compact", sid))
        if self.answer == "":
            self.bracket = True
        return self.answer

    def compacting(self, sid):
        return self.bracket

    def clear(self, sid, text):
        self.calls.append(("clear", sid))
        return self.answer          # the native clear's verdict: "" ran, "busy" the worker's lock sliver, else the reason

    def send(self, sid, text):
        self.calls.append(("send", text))
        return True

    def set_effort(self, sid, v):
        self.calls.append(("effort", v))
        return True

    def busy(self, sid):
        return True if self.bracket else None

    def resume(self, name, sid, cwd=None):
        self.calls.append(("resume", sid))
        self.live = {sid: {"state": "waiting"}}
        return True

    def move(self, sid, path):
        self.calls.append(("move", sid, path))
        self.live = {sid: {"state": "waiting"}}   # SdkBackend.move revives a dormant row first, whatever it then answers
        return self.move_answer

    def kill(self, sid):
        self.calls.append(("kill", sid))
        self.live = {}
        return True

    def _session(self, sid):
        return {"sid": sid} if sid == SID else None

    def owns(self, sid):
        return sid == SID

    def live_sessions(self):
        return dict(self.live)


def _forget(sid):
    """Drop the sid's parked ops from memory AND the disk mirror, and every per-sid latch these paths touch."""
    km._pending_ops.pop(sid, None)
    km._save_pending_ops()
    km._moving.discard(sid)
    km._drain_hold.pop(sid, None)
    km._inflight_ops.pop(sid, None)
    km._model_switch_pending.pop(sid, None)
    km._compact_clicked.pop(sid, None)
    km._held_working.pop(sid, None)   # the belt's record that the working gate holds this queue: a test that leaves the
                                      # in-flight slot kept leaves it standing, and the next test inherited it (2026-09-21)
    getattr(km, "_ending_sids", {}).pop(sid, None)     # the End latch (2026-09-21); absent on a kernel before it


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


class EndHandbackTargets(_Base):
    """Where the End doors' handback lands and which parked ops it takes (2026-09-21), over the module's stub backend: the
    queue is the kernel's own, so no backend is driven."""

    def _restore_undelivered(self):
        path = km.jd.STATE / "undelivered.jsonl"
        before = path.read_bytes() if path.exists() else None

        def restore():
            if before is None:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
            else:
                path.write_bytes(before)
        self.addCleanup(restore)

    def _connect(self, *panes):
        """Register `panes` as this kernel's live dashboard sockets for the test, gone at its end."""
        with km._clients_lock:
            km._clients.extend(panes)

        def unregister():
            with km._clients_lock:
                km._clients[:] = [c for c in km._clients if not any(c is pane for pane in panes)]
        self.addCleanup(unregister)

    def _name(self, sid, name):
        """A names-registry row for `sid` in the kernel's tab format (name, cwd, colors), gone at the test's end. Over the
        kernel's own NAMES, which _name_of reads, not a root another module's load may have rebound jd.STATE to."""
        km.NAMES.mkdir(parents=True, exist_ok=True)
        (km.NAMES / sid).write_text("%s\t/TESTDIR-compact-end\t#112233\t#ffffff\n" % name)
        self.addCleanup(lambda: (km.NAMES / sid).unlink(missing_ok=True))

    def _pane(self, app, frames, **slots):
        """A connected pane of `app` whose frames land in `frames`; `slots` are the liveness and tab bookkeeping."""
        return dict({"app": app, "alive": True, "send": lambda t: frames.append(json.loads(t))}, **slots)

    def test_a_socketless_end_hands_the_message_to_one_chat_pane_the_one_watching_the_session_first(self):
        # The socket-less doors (the end route, the self-close sweep) broadcast to every chat pane: two chat columns
        # drew two modals and two bell entries for one message (review find, 2026-09-21). One chat client hears it,
        # the one watching the session when there is one.
        self._restore_undelivered()
        km._park_op(SID, ("send", "words the user typed", "human", QID, True))
        frames = {"first": [], "watching": []}
        first = {"app": "chat", "alive": True, "send": lambda t: frames["first"].append(json.loads(t))}
        watching = {"app": "chat", "alive": True, "active": SID, "send": lambda t: frames["watching"].append(json.loads(t))}
        with km._clients_lock:
            km._clients.extend([first, watching])

        def unregister():
            with km._clients_lock:
                km._clients[:] = [c for c in km._clients if c is not first and c is not watching]
        self.addCleanup(unregister)
        with mock.patch.object(km, "_send_to_app", _REAL_SEND_TO_APP):   # the shipped broadcast, so its reach is what is pinned
            self.assertEqual(km._drop_parked_on_end(SID), 1)
        errs = [f for f in frames["first"] + frames["watching"] if f.get("type") == "err"]
        self.assertEqual(len(errs), 1, "one modal for one message: %r" % [f.get("copy") for f in errs])
        self.assertEqual(errs[0]["copy"], "words the user typed")
        self.assertEqual([f["type"] for f in frames["watching"]], ["err"], "the pane watching the session shows it")
        self.assertEqual(frames["first"], [], "the other chat column hears nothing")
        self.assertNotIn(SID, km._pending_ops)

    def test_a_socketless_end_with_no_chat_pane_hands_the_message_to_a_pane_that_renders_the_frame(self):
        # romp end or the self-close sweep with a feed pane connected and no chat pane: the pick considered chat clients
        # only, so the frame went to the empty chat broadcast, though the feed's bundle reads an err frame (review find,
        # 2026-09-21): it hands the frame to the shell's bell through the notify bridge, so the words reach the person
        # where a shell hosts the pane (the standalone feed page and the extension's feed webview have no bridge), and
        # its own dialog carries the words (its box attached to the overlay since this change). With no
        # live chat client the pick is a live client of a pane whose bundle reads the frame; a pane whose bundle drops
        # it (the timeline) is never the target, however fresh its socket.
        self._restore_undelivered()
        text = "words typed with only the feed open"
        km._park_op(SID, ("send", text, "human", QID, True))
        feed_frames, timeline_frames = [], []
        self._connect(self._pane("timeline", timeline_frames, lastIn=20.0), self._pane("feed", feed_frames, lastIn=10.0))
        self.assertEqual(km._drop_parked_on_end(SID), 1)
        self.assertEqual([(f["type"], f.get("copy")) for f in feed_frames], [("err", text)], "the feed pane shows the one dialog")
        self.assertEqual(timeline_frames, [], "a pane that cannot show it is never the target")
        self.assertEqual([m for app, m in self.broadcast if m.get("type") == "err"], [],
                         "the empty chat broadcast is not the road")
        self.assertNotIn(SID, km._pending_ops)

    def test_the_dialog_lands_on_the_freshest_socket_among_the_panes_watching_the_session(self):
        # The pick took the first chat socket watching the session, and _client_send answers True on the enqueue, so a
        # chat pane whose peer went silent without closing (a forwarder holding the kernel's end open) took the one
        # dialog until the heartbeat dropped it, three beats, while a pane whose peer was answering heard nothing
        # (review find, 2026-09-21). The socket whose peer proved itself alive last (lastIn, stamped on every inbound
        # frame, a pong each beat included) is the pick, and a fresher socket showing another session does not outrank
        # a watching one.
        self._restore_undelivered()
        km._park_op(SID, ("send", "words for the freshest watching pane", "human", QID, True))
        stale, fresh, elsewhere = [], [], []
        self._connect(self._pane("chat", stale, active=SID, lastIn=100.0),
                      self._pane("chat", fresh, active=SID, lastIn=200.0),
                      self._pane("chat", elsewhere, active=SID_REAL, lastIn=300.0))
        self.assertEqual(km._drop_parked_on_end(SID), 1)
        self.assertEqual([f["type"] for f in fresh], ["err"], "the freshest pane watching the session shows it")
        self.assertEqual((stale, elsewhere), ([], []), "the silent watcher and the fresher pane on another session hear nothing")

    def test_with_no_pane_watching_the_session_the_freshest_live_chat_socket_takes_the_dialog_before_any_feed_pane(self):
        # The fallback took the oldest chat socket, the same silent-peer window as the watching set's (review find,
        # 2026-09-21): the freshest live chat socket is the pick; a chat pane outranks a feed pane however fresh the
        # feed's socket, and a socket already marked dead is skipped whatever its stamp, as before.
        self._restore_undelivered()
        km._park_op(SID, ("send", "words for the freshest chat pane", "human", QID, True))
        stale, fresh, feed, dead = [], [], [], []
        self._connect(self._pane("chat", stale, lastIn=100.0),
                      self._pane("chat", fresh, active=SID_REAL, lastIn=200.0),
                      self._pane("feed", feed, lastIn=300.0),
                      self._pane("chat", dead, alive=False, lastIn=400.0))
        self.assertEqual(km._drop_parked_on_end(SID), 1)
        self.assertEqual([f["type"] for f in fresh], ["err"], "the freshest live chat socket shows it")
        self.assertEqual((stale, feed, dead), ([], [], []),
                         "the oldest chat socket, the fresher feed pane and the dead socket hear nothing")

    def test_two_equal_stamps_keep_the_older_socket_the_order_the_pick_had(self):
        # Two panes watching the session whose peers proved themselves alive at the same instant: neither is fresher,
        # and the older socket takes the frame, the order the pick had before it read the stamps (2026-09-21). Green at
        # the base by construction, where the first watching socket was always the pick.
        self._restore_undelivered()
        km._park_op(SID, ("send", "words for two panes of one stamp", "human", QID, True))
        older, newer = [], []
        self._connect(self._pane("chat", older, active=SID, lastIn=100.0),
                      self._pane("chat", newer, active=SID, lastIn=100.0))
        self.assertEqual(km._drop_parked_on_end(SID), 1)
        self.assertEqual([f["type"] for f in older], ["err"], "the older socket takes the frame")
        self.assertEqual(newer, [], "the newer of two equal stamps hears nothing")

    def test_the_dialogs_detail_names_the_ended_session_as_the_person_knows_it(self):
        # The frame lands on one pane, and on a chat column showing another session the detail named the ended one by
        # its uuid alone (review find, 2026-09-21): now the registered name, as moveFailed names a session. The frame's
        # sid slot and the undelivered file's row keep the uuid; those are read by machines.
        self._restore_undelivered()
        self._name(SID, "web")
        text = "words for a named session"
        km._park_op(SID, ("send", text, "human", QID, True))
        frames = []
        self._connect(self._pane("chat", frames, active=SID_REAL))
        self.assertEqual(km._drop_parked_on_end(SID), 1)
        self.assertEqual([f["type"] for f in frames], ["err"])
        self.assertIn("(session web)", frames[0]["text"], "the detail names the session as the person knows it")
        self.assertNotIn(SID, frames[0]["text"], "and not by its uuid")
        self.assertEqual(frames[0]["sid"], SID, "the machine-read slot keeps the uuid")
        rows = [json.loads(l) for l in (km.jd.STATE / "undelivered.jsonl").read_text().splitlines() if l.strip()]
        self.assertEqual([(r["sid"], r["text"]) for r in rows if r.get("sid") == SID], [(SID, text)], "the file keys by uuid")

    def test_a_session_no_row_names_is_named_by_its_uuid_on_every_refusal_that_says_why(self):
        # No registry row (a session this kernel never named): the uuid, as before. The askFollowUp refusal shares the
        # why branch, so a card reply refused for a session no backend owns names the session the same way.
        self._restore_undelivered()
        frames = []
        pane = {"send": lambda t: frames.append(json.loads(t))}
        km._refuse_drive(pane, "askFollowUp", SID, {"text": "a reply typed on a card", "itemId": "g1"},
                         why="No running backend owns this session")
        self.assertIn("(session %s)" % SID, frames[0]["text"], "no name registered: the uuid")
        self._name(SID, "api")
        km._refuse_drive(pane, "askFollowUp", SID, {"text": "a reply typed on a card", "itemId": "g1"},
                         why="No running backend owns this session")
        self.assertIn("(session api)", frames[1]["text"], "the card reply's refusal names it too")
        self.assertEqual((frames[1]["op"], frames[1]["itemId"]), ("askFollowUp", "g1"))

    def _card_reply_parked_behind_a_compaction(self, msg):
        """A follow-up through the live askFollowUp door while a compaction stands, so it parks in the kernel's queue as
        the body the door composed (the goal quote when one is given, the romp-note and romp-goal-id comments; the canned
        words with their marker for a Continue press, which with no card id are the whole body). Returns the one parked
        op. The reopen the door attempts finds no goal under this module's private sid and writes nothing; the cue
        frames land on the stubbed feed broadcast."""
        self._restore_undelivered()
        with mock.patch.object(km, "_compacting_now", lambda sid, **k: True):
            self.assertTrue(km._drive(dict(msg, type="askFollowUp", qid=QID), self.client))
        ops = km._pending_ops.get(SID) or []
        self.assertEqual([op[0] for op in ops], ["send"], ops)
        self.assertTrue(km._op_user(ops[0]), "the door parks a follow-up as the user's")
        return ops[0]

    def _undelivered_rows(self):
        path = km.jd.STATE / "undelivered.jsonl"
        rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()] if path.exists() else []
        return [(r["op"], r["itemId"], r["text"]) for r in rows if r.get("sid") == SID]

    def test_end_hands_a_parked_card_reply_back_as_the_typed_words_not_the_composed_body(self):
        # The hand-back passed the parked op's body to the not-delivered path, and for a card reply that is the wrapper
        # the askFollowUp door composed around the typed words: the goal quote, the romp-note and romp-goal-id comments.
        # The copy slot, undelivered.jsonl and the log carried romp's quote and markers as the user's words, where the
        # queued bubble and the live refusal of the same follow-up carry the typed words alone (the post-merge review of
        # the hand-back, 2026-09-21). The words come back through the bubble's own split, under the reply verb and the
        # card's id, the frame the live refusal sends and the feed re-arms its latched button on.
        import contextlib, io
        iid, words, summary = SID + ":g1", "the typed reply, nothing else", "the card's distilled summary"
        op = self._card_reply_parked_behind_a_compaction({"itemId": iid, "title": summary, "text": words})
        self.assertTrue(op[1].startswith("> " + summary), "the door parks the composed body: the quote first")
        self.assertIn("<!-- romp-goal-id: %s -->" % iid, op[1])
        self.assertEqual(km._parked_md(op), words, "the queued bubble shows the typed words alone")
        chat = {"app": "chat", "send": lambda t: self.sent.append(json.loads(t))}
        log = io.StringIO()
        with contextlib.redirect_stderr(log):
            self.assertEqual(km._drop_parked_on_end(SID, chat), 1)
        errs = [f for f in self.sent if f.get("type") == "err"]
        self.assertEqual(len(errs), 1, errs)
        self.assertEqual(errs[0]["copy"], words, "the copy slot holds what was typed, not the quote and the markers")
        self.assertEqual((errs[0]["op"], errs[0]["itemId"], errs[0]["sid"]), ("askFollowUp", iid, SID),
                         "the live refusal's frame: the reply verb and the card it answers")
        self.assertIn("reply", errs[0]["title"])
        self.assertEqual(self._undelivered_rows(), [("askFollowUp", iid, words)], "kept verbatim as typed, once")
        self.assertIn(repr(words), log.getvalue())
        for leaked in ("romp-goal-id", "romp-note", summary):
            self.assertNotIn(leaked, log.getvalue(), "the log carries the typed words, never the wrapper")
        self.assertNotIn(SID, km._pending_ops)

    def test_end_hands_a_parked_continue_press_back_as_the_live_refusal_does_empty_text_under_the_reply_verb(self):
        # A Continue press parks the canned words with their marker inside the same wrapper, and the base handed the
        # canned prose back as the user's typed words. The press typed nothing: it comes back as the live refusal of a
        # Continue sends it, empty text under the reply verb with the card's id, so the dialog and the undelivered row
        # name the reply and the card the way the live refusal does. Not dropped with the machine sends: the press was
        # the user's gesture, and the dialog is how they learn it went nowhere. The marker is read on the body before
        # the split strips every comment, which would leave the canned prose.
        import contextlib, io
        iid = SID + ":g2"
        op = self._card_reply_parked_behind_a_compaction({"itemId": iid, "cont": True})
        self.assertTrue(op[1].startswith(km.CONTINUE_TEXT), "the door parks the canned body")
        self.assertIn("<!-- romp-canned: continue -->", op[1])
        chat = {"app": "chat", "send": lambda t: self.sent.append(json.loads(t))}
        log = io.StringIO()
        with contextlib.redirect_stderr(log):
            self.assertEqual(km._drop_parked_on_end(SID, chat), 1, "handed back, not dropped")
        errs = [f for f in self.sent if f.get("type") == "err"]
        self.assertEqual(len(errs), 1, errs)
        self.assertEqual(errs[0]["copy"], "", "nothing was typed, so nothing is offered to copy")
        self.assertEqual((errs[0]["op"], errs[0]["itemId"], errs[0]["sid"]), ("askFollowUp", iid, SID))
        self.assertEqual(self._undelivered_rows(), [("askFollowUp", iid, "")])
        self.assertIn("undeliverable askFollowUp", log.getvalue())
        for leaked in (km.CONTINUE_TEXT[:24], "romp-canned", "romp-goal-id"):
            self.assertNotIn(leaked, log.getvalue(), "the canned words are romp's, never logged as the user's")
        self.assertNotIn(SID, km._pending_ops)

    def test_a_continue_press_parked_with_no_card_id_comes_back_empty_under_the_reply_verb_too(self):
        # The door takes a Continue addressed by session id alone (no itemId), and then composes no wrapper: the parked
        # body is the canned words and their marker, with no goal marker for the follow-up split to find. Read after
        # that split, the marker was gone and the body fell to the plain-send branch: the canned prose plus its marker
        # came back under the message verb, the defect this change fixes (review find, 2026-09-21). The marker is read
        # on the body before the follow-up test, so the press comes back empty under the reply verb with no card named.
        import contextlib, io
        op = self._card_reply_parked_behind_a_compaction({"id": SID, "cont": True})
        self.assertEqual(op[1], km.CONTINUE_TEXT + "\n\n<!-- romp-canned: continue -->", "no wrapper: no card to quote")
        self.assertNotIn("romp-goal-id", op[1])
        chat = {"app": "chat", "send": lambda t: self.sent.append(json.loads(t))}
        log = io.StringIO()
        with contextlib.redirect_stderr(log):
            self.assertEqual(km._drop_parked_on_end(SID, chat), 1)
        errs = [f for f in self.sent if f.get("type") == "err"]
        self.assertEqual(len(errs), 1, errs)
        self.assertEqual((errs[0]["copy"], errs[0]["op"], errs[0]["itemId"], errs[0]["sid"]), ("", "askFollowUp", "", SID))
        self.assertEqual(self._undelivered_rows(), [("askFollowUp", "", "")])
        self.assertNotIn(km.CONTINUE_TEXT[:24], log.getvalue(), "the canned words are romp's, never logged as the user's")
        self.assertNotIn(SID, km._pending_ops)

    def test_a_typed_command_parked_behind_a_compaction_comes_back_as_typed_under_the_command_verb(self):
        # The helper's command arm: a typed slash command parks as a ("command",) op whose body IS the bubble, and comes
        # back as typed under the command verb, as before this change (the arm was pinned by nothing, review find,
        # 2026-09-21).
        self._restore_undelivered()
        km._park_op(SID, ("command", "/autocompact auto", None, QID, True))
        chat = {"app": "chat", "send": lambda t: self.sent.append(json.loads(t))}
        self.assertEqual(km._drop_parked_on_end(SID, chat), 1)
        errs = [f for f in self.sent if f.get("type") == "err"]
        self.assertEqual(len(errs), 1, errs)
        self.assertEqual((errs[0]["copy"], errs[0]["op"], errs[0]["itemId"], errs[0]["sid"]),
                         ("/autocompact auto", "sendCommand", "", SID))
        self.assertIn("command", errs[0]["title"])
        self.assertEqual(self._undelivered_rows(), [("sendCommand", "", "/autocompact auto")])
        self.assertNotIn(SID, km._pending_ops)

    def test_the_in_flight_op_is_kept_by_slot_so_a_second_compact_press_behind_it_is_dropped(self):
        # _compact_or_park parks the literal ("compact",), one interned tuple, so a second press `is` the first; an
        # identity filter kept both behind the in-flight one (review find, 2026-09-21). The slot the drain holds is the
        # one kept, as _cancel_parked finds it.
        import contextlib, io
        km._park_op(SID, ("compact",))
        km._park_op(SID, ("compact",))
        ops = km._pending_ops[SID]
        self.assertEqual(len(ops), 2)
        self.assertIs(ops[0], ops[1], "one interned tuple, two slots")
        km._inflight_ops[SID] = ops[0]
        log = io.StringIO()
        with contextlib.redirect_stderr(log):
            self.assertEqual(km._drop_parked_on_end(SID), 0, "a compact press carries no text to hand back")
        self.assertEqual(km._pending_ops.get(SID), [("compact",)], "exactly the in-flight slot remains")
        self.assertEqual(log.getvalue().count("parked compact op dropped with the ending session %s" % SID), 1)

    def test_an_emptied_queue_takes_the_drain_hold_and_the_held_working_latch_with_it(self):
        # The two per-sid latches the hand-back pops when the queue empties had no test (the post-merge review of
        # #1970, 2026-09-21): the drain hold (a window the drain skips the sid for) and the belt's held-working record
        # (_mark_held_working: the working gate holds this queue). An emptied queue leaves neither behind: nothing is
        # left for the hold to protect, and the next hold on this sid must say again.
        self._restore_undelivered()
        km._park_op(SID, ("send", "words the user typed", "human", QID, True))
        km._drain_hold[SID] = (time.monotonic() + 60, False)
        km._mark_held_working(SID, time.monotonic())
        self.assertIn(SID, km._held_working, "seeded: the belt records the hold")
        self.assertEqual(km._drop_parked_on_end(SID), 1)
        self.assertNotIn(SID, km._pending_ops)
        self.assertNotIn(SID, km._drain_hold, "no queue, no hold")
        self.assertNotIn(SID, km._held_working, "no queue, no belt state")

    def test_a_kept_in_flight_slot_keeps_both_latches_and_the_cleanup_drops_the_belt_state(self):
        # With the in-flight head kept the queue is not empty, so both latches stand for the op the drain still
        # holds. The module's cleanup (_forget) then has to drop the held-working latch as well as the hold, or the
        # next test inherits belt state for this sid; the latch survived _forget before 2026-09-21.
        self._restore_undelivered()
        km._park_op(SID, ("send", "in the backend's hands", "human", QID, True))
        km._park_op(SID, ("send", "typed behind it", "human", None, True))
        ops = km._pending_ops[SID]
        km._inflight_ops[SID] = ops[0]
        km._drain_hold[SID] = (time.monotonic() + 60, False)
        km._mark_held_working(SID, time.monotonic())
        self.assertEqual(km._drop_parked_on_end(SID), 1, "the one behind the in-flight head")
        self.assertEqual(km._pending_ops.get(SID), [ops[0]], "exactly the in-flight slot remains")
        self.assertIn(SID, km._drain_hold, "a kept slot keeps its hold")
        self.assertIn(SID, km._held_working, "and its belt state")
        _forget(SID)
        self.assertNotIn(SID, km._inflight_ops)
        self.assertNotIn(SID, km._drain_hold)
        self.assertNotIn(SID, km._held_working, "the cleanup leaves no belt state for the next test")
    def _death_record(self, sid):
        """The kernel's own death marker for `sid`, as _record_death writes it at every End door, restored after."""
        gd = km.jd.STATE / "gone"
        gd.mkdir(parents=True, exist_ok=True)
        path = gd / (sid + ".json")
        before = path.read_bytes() if path.exists() else None
        path.write_text(json.dumps({"t": int(time.time()) - 1, "by": "kill"}))

        def restore():
            if before is None:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
            else:
                path.write_bytes(before)
        self.addCleanup(restore)

    def _errs(self):
        return [m for app, m in self.broadcast if app == "chat" and m.get("type") == "err"]

    def test_a_dead_rows_queue_is_handed_back_at_the_top_of_its_pass_ahead_of_the_gates(self):
        # The post-merge review of the End hand-back (2026-09-21): a dead row's queue (a park that landed after End's
        # cancel, a queue mirrored to disk before the End) sat behind a hold nothing would lift, and past the gates went
        # to the unowned route with the refusal ignored. The backstop runs at the top of the sid's pass, ahead of every
        # gate, keyed on the death record with no live row: the account hold below is real for the pass and irrelevant.
        import contextlib, io
        self._restore_undelivered()
        self._death_record(SID)
        text = "typed into a row that had ended"
        km._pending_ops[SID] = [("send", text, "human", QID, True), ("send", "a notice the kernel composed", None)]
        km._save_pending_ops()
        hold = {"reason": "limit", "resetsAt": None, "what": "waiting for your usage limit to reset"}
        log = io.StringIO()
        with mock.patch.object(km, "_limit_hold", lambda sid: hold), \
             mock.patch.object(km.Sessions, "backend_for", staticmethod(lambda sid: km._UNOWNED)), \
             contextlib.redirect_stderr(log):
            km._apply_pending_ops()
        self.assertNotIn(SID, km._pending_ops, "the dead row's queue is gone with it, hold or no hold")
        self.assertEqual([m.get("copy") for m in self._errs()], [text], "the typed one comes back once, to the chat")
        self.assertIn("ended", self._errs()[0]["text"])
        self.assertEqual(self.be.calls, [], "nothing is handed to a backend")
        self.assertIn("parked send op dropped with the ending session %s" % SID, log.getvalue(), "the machine's, by kind")
        self.assertNotIn("a notice the kernel composed", log.getvalue())
        self.assertIs(km._ended_for_good(SID), True, "the key: the marker stands and no backend reports the sid live")

    def test_an_unowned_sid_with_no_death_record_keeps_its_held_queue(self):
        # The other half of the key (the review's parenthesis): a kernel before its backends are built reads every sid as
        # unowned, so the unowned route alone is no death. With no marker the held queue waits, as before.
        km._pending_ops[SID] = [("send", "typed while the backends come up", "human", QID, True)]
        km._save_pending_ops()
        hold = {"reason": "limit", "resetsAt": None, "what": "waiting for your usage limit to reset"}
        with mock.patch.object(km, "_limit_hold", lambda sid: hold), \
             mock.patch.object(km.Sessions, "backend_for", staticmethod(lambda sid: km._UNOWNED)):
            km._apply_pending_ops()
        self.assertEqual([op[1] for op in km._pending_ops.get(SID, [])], ["typed while the backends come up"])
        self.assertEqual(self._errs(), [], "nothing is handed back for a session that may yet attach")
        self.assertIs(km._ended_for_good(SID), False, "no marker: the unowned route alone is no death")

    def test_a_send_the_backend_refuses_after_the_pop_comes_back_typed_only(self):
        # The drain pops a send run whole before the handover and, until 2026-09-21, discarded each send's False: a run
        # refused after the pop was gone with no modal and no undelivered row. The refusal is read per op now: the
        # user's words take the not-delivered path to one pane (a chat pane first), a machine's goes to the log by kind, and the reason
        # is read from the backend at hand (this one still owns the sid: it refused the message itself).
        import contextlib, io
        self._restore_undelivered()
        text = "typed, popped, then refused"
        km._pending_ops[SID] = [("send", text, "human", QID, True), ("send", "a notice the kernel composed", None)]
        km._save_pending_ops()
        self.be.send = lambda sid, t: False
        log = io.StringIO()
        with contextlib.redirect_stderr(log):
            km._apply_pending_ops()
        self.assertNotIn(SID, km._pending_ops)
        self.assertEqual([m.get("copy") for m in self._errs()], [text])
        self.assertEqual((self._errs()[0]["sid"], self._errs()[0]["op"]), (SID, "sendMessage"))
        self.assertIn("backend refused", self._errs()[0]["text"])
        rows = [json.loads(l) for l in (km.jd.STATE / "undelivered.jsonl").read_text().splitlines() if l.strip()]
        self.assertEqual([r["text"] for r in rows if r.get("sid") == SID], [text], "kept verbatim, once; the machine's not filed")
        self.assertIn("parked send op dropped after its backend refused it, for %s" % SID, log.getvalue())
        self.assertNotIn("a notice the kernel composed", log.getvalue())

    def test_a_refused_send_on_a_row_whose_death_stands_says_ended_though_its_registry_row_remains(self):
        # The reason is read with the death FIRST (review find, 2026-09-21): the SDK backend's owns() is registry presence,
        # which a kill does not remove, and the pusher cycle's snapshot predates the End, so a reason that asked the
        # backend first, or read the snapshot, said the backend refused a message the End had made undeliverable. The
        # stub's owns() answers True for the sid throughout, the snapshot lists the row, the death record stands, and
        # the backends read fresh report nothing: the frame says the session ended.
        self._restore_undelivered()
        self._death_record(SID)
        text = "typed, popped, refused by a row whose death stands"
        km._pending_ops[SID] = [("send", text, "human", QID, True)]
        km._save_pending_ops()
        self.be.send = lambda sid, t: False
        self.assertTrue(self.be.owns(SID), "the registry row remains")
        km._live_scope.snapshot = {SID: {"state": "waiting", "backend": "codex"}}
        try:
            self.assertIs(km._ended_for_good(SID), False, "the cycle's snapshot still lists the row")
            km._apply_pending_ops()
        finally:
            km._live_scope.snapshot = None
        self.assertEqual([m.get("copy") for m in self._errs()], [text])
        self.assertIn("ended", self._errs()[0]["text"], self._errs()[0]["text"])
        self.assertNotIn("backend refused", self._errs()[0]["text"])

    def test_a_park_after_the_end_cancel_is_refused_and_the_sending_pane_is_told(self):
        # A park landing after End's cancel (the handler read the row as owned before the kill) sat in the dead row's
        # queue as a queued bubble until the drain got to it (review find, 2026-09-21). The cancel latches the sid, the
        # park is refused under the same lock, and the sendMessage arm hands the words back to its own pane through the
        # not-delivered path, the End hand-back's shape. The latch lifts on the event it stands for, the session coming
        # back under its sid (the revive door, a thread's resume, a move), never on a clock or a liveness snapshot.
        self._restore_undelivered()
        text = "typed in the instant after End"
        with mock.patch.object(km, "_compacting_now", lambda sid, **k: True):   # a park condition: the cue still reads
            self.assertEqual(km._drop_parked_on_end(SID), 0, "End's cancel, nothing parked yet")
            self.assertTrue(km._drive({"type": "sendMessage", "id": SID, "text": text}, self.client))
        self.assertNotIn(SID, km._pending_ops, "the park is refused: no queued bubble on a dead row")
        self.assertEqual(self.be.calls, [], "and nothing is handed over in its place")
        errs = [f for f in self.sent if f.get("type") == "err"]
        self.assertEqual([f.get("copy") for f in errs], [text], "the sending pane gets the words back")
        self.assertEqual((errs[0]["sid"], errs[0]["op"]), (SID, "sendMessage"))
        self.assertIn("ended", errs[0]["text"])
        rows = [json.loads(l) for l in (km.jd.STATE / "undelivered.jsonl").read_text().splitlines() if l.strip()]
        self.assertEqual([r["text"] for r in rows if r.get("sid") == SID], [text])
        self.assertIn(SID, km._ending_sids, "the latch stands until the session comes back under its sid")

    # ── the End latch lifts on the event it stands for, never on a clock or a snapshot (the review, 2026-09-21) ──

    # the cycle's stage jobs other than the drain, quieted so the real cycle function runs over the stub; the drain itself
    # runs real, since it is the one job that writes the latch and reads the snapshot (the fourth review, 2026-09-21)
    _CYCLE_JOBS = ("_begin_checkpoint_cycle", "_sessions_listing_refresh", "_push_all", "_artifacts_signal",
                   "_turn_notify_tick", "_persist_checkpoints", "_converge_checkpoints", "_boot_row_backstop", "_kernel_sample_tick",
                   "_api_health_frame", "_api_health_push")

    def test_a_cycle_whose_snapshot_lists_the_sid_between_the_latch_and_the_kill_leaves_the_latch(self):
        # Every End door stamps the latch BEFORE the kill and wakes the pusher, so a cycle can start while the kill is
        # still pending (the SDK kill waits on its lock) with a snapshot that lists the sid live. A lift keyed on that
        # snapshot behind a second-boundary guard popped the latch before the row died, and a later park landed in the
        # dead row (review find, 2026-09-21). The real cycle function with the real drain (the one job that writes the
        # latch and reads the snapshot; the fourth review found it stubbed here), a machine's send in the latched sid's
        # queue, a snapshot listing the sid and a clock two seconds on: the send drains to the row the snapshot lists,
        # the latch stands, and a typed park is still refused.
        self.assertEqual(km._drop_parked_on_end(SID), 0)
        km._pending_ops[SID] = [("send", "a notice the kernel composed", None)]   # placed behind the latch, as a mirror restores one
        km._save_pending_ops()
        snapshot = {SID: {"state": "waiting", "backend": "codex"}}
        now = int(time.time()) + 2
        with mock.patch.multiple(km, **{nm: (lambda *a, **k: None) for nm in self._CYCLE_JOBS}):
            km._live_scope.snapshot = snapshot
            try:
                km._pusher_cycle_jobs(now, snapshot, False)
                km._pusher_cycle_jobs(now, snapshot, True)
            finally:
                km._live_scope.snapshot = None
        self.assertEqual(self.be.calls, [("send", "a notice the kernel composed")], "the drain ran real and delivered the machine's send")
        self.assertNotIn(SID, km._pending_ops)
        self.assertIn(SID, km._ending_sids, "a cycle lifts no latch, whatever its snapshot lists and whenever it runs")
        with mock.patch.object(km, "_compacting_now", lambda sid, **k: True):
            self.assertIsNone(km._send_or_park(self.be, SID, "typed while the kill is pending", user=True, qid=QID))
        self.assertNotIn(SID, km._pending_ops, "and a park in that window is still refused")
        for fn in (km._pusher_cycle_jobs, km._apply_pending_ops, km._jobs_pass):
            src = inspect.getsource(fn)
            for word in ("_ending_sids", "_lift_end_latch", "_unlatch_ended"):
                self.assertNotIn(word, src, "%s names no latch sweep" % fn.__name__)

    def test_the_revive_door_lifts_the_latch_and_parks_are_welcome_again(self):
        # The event the latch stands for: the session comes back under its sid. The real revive door over the stub (a
        # dead Codex row: _session answers, owns is the SDK's question), its neighbors stubbed the way the Codex revive
        # tests stub them; after it a park is taken again.
        self.assertEqual(km._drop_parked_on_end(SID), 0)
        with mock.patch.object(km, "_compacting_now", lambda sid, **k: True):
            self.assertIsNone(km._send_or_park(self.be, SID, "typed before the revive", user=True, qid=QID), "refused: latched")
        with mock.patch.multiple(km, _codex_ready=lambda: True, _models_changed=lambda: None, _name_of=lambda s: "web",
                                 _cwd_of=lambda s: "/TESTDIR", _commands_for_cwd=lambda cwd: None,
                                 _send_to_view=lambda app, msg, wid: self.fail("a refusal frame: %r" % (msg,))):
            km._revive_session_inner(SID)
        self.assertEqual(self.be.calls[-1], ("resume", SID), "the door resumed the row")
        self.assertNotIn(SID, km._ending_sids, "live again under its sid: the latch is gone")
        with mock.patch.object(km, "_compacting_now", lambda sid, **k: True):
            self.assertIs(km._send_or_park(self.be, SID, "typed after the revive", user=True, qid=QID), True)
        self.assertEqual([op[1] for op in km._pending_ops[SID]], ["typed after the revive"], "parks are welcome again")

    def test_a_cue_teardown_whose_kill_raised_lifts_the_latch(self):
        # The Opening cue's teardown latches before its kill, and a kill that raises is logged, not raised: the session
        # did not end, so a latch left standing would refuse its parks for the kernel's life. The raise lifts it.
        import contextlib, io
        self.be.kill = lambda sid: (_ for _ in ()).throw(RuntimeError("the backend's kill raised"))
        log = io.StringIO()
        with mock.patch.object(km, "_path_of", lambda sid, now=None: None), contextlib.redirect_stderr(log):
            km._end_pending_sid(SID)
        self.assertIn("cancelCreate kill", log.getvalue())
        self.assertNotIn(SID, km._ending_sids, "the session did not end: no latch")
        with mock.patch.object(km, "_compacting_now", lambda sid, **k: True):
            self.assertIs(km._send_or_park(self.be, SID, "typed after the failed teardown", user=True, qid=QID), True)

    def test_a_move_that_answers_ok_lifts_the_latch(self):
        # SdkBackend.move revives a dormant row in its old folder before moving it, and no kernel road there lifted the
        # latch, so a move on an ended row left a live session whose every park was refused as ending (the second
        # review, 2026-09-21). The move's "" is the event: the row is live after it.
        self.assertEqual(km._drop_parked_on_end(SID), 0)
        frames = []
        with mock.patch.multiple(km, _cwd_of=lambda s: "/TESTDIR-moved", _commands_for_cwd=lambda cwd: None,
                                 _send_to_view=lambda app, msg, wid: frames.append(msg)):
            self.assertEqual(km._move_now(self.be, SID, "/TESTDIR-moved", 0, ""), "")
        self.assertEqual(self.be.calls[-1], ("move", SID, "/TESTDIR-moved"))
        self.assertEqual([f["type"] for f in frames], ["moved"])
        self.assertNotIn(SID, km._ending_sids, "live after the move: the latch is gone")
        with mock.patch.object(km, "_compacting_now", lambda sid, **k: True):
            self.assertIs(km._send_or_park(self.be, SID, "typed after the move", user=True, qid=QID), True)

    def test_a_move_the_backend_refused_after_its_resume_lifts_the_latch_too(self):
        # Executed by the third review over the real SdkBackend.move (2026-09-21): the backend revives the dormant row,
        # then refuses (the CLI did not start, the connect wait expired, a claim refusal, the CLI's rejection), and a lift
        # keyed on the "" answer left the live row latched. The move's return is the event; the backends are asked then.
        self.assertEqual(km._drop_parked_on_end(SID), 0)
        self.be.move_answer = "the CLI did not start in the new folder"
        frames = []
        with mock.patch.multiple(km, _cwd_of=lambda s: "/TESTDIR-moved", _commands_for_cwd=lambda cwd: None,
                                 _send_to_view=lambda app, msg, wid: frames.append(msg)):
            self.assertEqual(km._move_now(self.be, SID, "/TESTDIR-moved", 0, ""), self.be.move_answer)
        self.assertEqual([f["type"] for f in frames], ["moveFailed"], "the refusal is said as before")
        self.assertNotIn(SID, km._ending_sids, "the row is live after the resume the move made: no latch")
        with mock.patch.object(km, "_compacting_now", lambda sid, **k: True):
            self.assertIs(km._send_or_park(self.be, SID, "typed after the refused move", user=True, qid=QID), True)
        self.assertEqual([op[1] for op in km._pending_ops[SID]], ["typed after the refused move"], "a park is taken")

    def test_a_move_that_returns_while_an_end_lands_mid_call_leaves_that_ends_latch(self):
        # Executed by the fourth review (2026-09-21): an End door latches first, hands the queue back, and only then kills,
        # so a move returning inside that window reads the row live, and a lift keyed on the read alone popped the newer
        # End's latch; the kill then left a dead row refused by nothing (a park was taken into its queue, a gateless send
        # got the fading warn). The latch's generation orders the two events: the move read the counter before its call,
        # and a latch written after it is left standing. The stub's move runs the End's cancel inside the call.
        def move(sid, path):
            self.be.calls.append(("move", sid, path))
            self.be.live = {sid: {"state": "waiting"}}
            self.assertEqual(km._drop_parked_on_end(SID), 0)   # the End lands mid-move, before its kill
            return ""
        self.be.move = move
        with mock.patch.multiple(km, _cwd_of=lambda s: "/TESTDIR-moved", _commands_for_cwd=lambda cwd: None,
                                 _send_to_view=lambda app, msg, wid: None):
            self.assertEqual(km._move_now(self.be, SID, "/TESTDIR-moved", 0, ""), "")
        self.assertIn(SID, km._ending_sids, "the End that landed mid-move keeps its latch: its kill follows")
        self.be.kill(SID)                                      # the door's kill lands
        with mock.patch.object(km, "_compacting_now", lambda sid, **k: True):
            self.assertIsNone(km._send_or_park(self.be, SID, "typed after the End", user=True, qid=QID), "still refused")
        self.assertNotIn(SID, km._pending_ops, "no park lands in the dead row's queue")

    def test_a_busy_move_that_returns_while_an_end_lands_mid_call_re_parks_nothing_on_the_dying_row(self):
        # The move thread's busy re-insert writes the queue directly, outside _park_op_locked, so it never met the latch
        # (the fifth review, 2026-09-21): an End landing mid-move kept its latch at the return, and the very next statement
        # re-queued the cwd op on the dying row with a hold armed, a queued bubble the latch refuses everywhere else; at the
        # cancelled cue's door, which records no death, the drain later fired that move and revived the cancelled session.
        # The latch is read under the re-insert's own lock hold: the op is dropped by kind, "busy" is still answered.
        import contextlib, io
        def move(sid, path):
            self.be.calls.append(("move", sid, path))
            self.be.live = {sid: {"state": "waiting"}}
            self.assertEqual(km._drop_parked_on_end(SID), 0)   # the End lands mid-move, before its kill
            return "busy"
        self.be.move = move
        log = io.StringIO()
        with mock.patch.multiple(km, _cwd_of=lambda s: "/TESTDIR-moved", _commands_for_cwd=lambda cwd: None,
                                 _send_to_view=lambda app, msg, wid: None), contextlib.redirect_stderr(log):
            self.assertEqual(km._move_now(self.be, SID, "/TESTDIR-moved", 0, ""), "busy")
        self.assertIn(SID, km._ending_sids, "the End that landed mid-move keeps its latch")
        self.assertNotIn(SID, km._pending_ops, "no cwd chip is re-queued on the dying row")
        self.assertNotIn(SID, km._drain_hold, "and no retry hold is armed for it")
        self.assertNotIn(SID, km._move_askers)
        self.assertIn("parked cwd op dropped with the ending session %s" % SID, log.getvalue(), "dropped by kind, in the log")
        self.be.kill(SID)                                      # the door's kill lands; a later drain pass has nothing to fire
        with mock.patch.object(km, "_fire_move", lambda *a: self.fail("a move fired on the dead row")):
            km._apply_pending_ops()

    def test_a_busy_move_on_an_unlatched_sid_re_parks_at_the_head_as_before(self):
        # The counterpart the session move modules pin: with no latch the busy answer re-parks the cwd op at the head,
        # with the retry count bumped and the hold armed.
        self.be.move_answer = "busy"
        with mock.patch.multiple(km, _cwd_of=lambda s: "/TESTDIR-moved", _commands_for_cwd=lambda cwd: None,
                                 _send_to_view=lambda app, msg, wid: None):
            self.assertEqual(km._move_now(self.be, SID, "/TESTDIR-moved", 0, "w-1"), "busy")
        self.assertEqual(km._pending_ops.get(SID), [("cwd", "/TESTDIR-moved", 1, None)])
        self.assertIn(SID, km._drain_hold)
        self.assertEqual(km._move_askers.pop(SID, None), "w-1")

    def test_a_revive_that_returns_while_an_end_lands_mid_call_leaves_that_ends_latch(self):
        # The revive door's twin (the fourth review, 2026-09-21): the SDK resume makes the row live, the End lands during
        # the connect, and the door's exit reads the row live; only a latch that predates the resume lifts.
        sdk = self.be
        def connect(sid):
            sdk.calls.append(("connect", sid))
            self.assertEqual(km._drop_parked_on_end(SID), 0)   # the End lands mid-revive, before its kill
            return True
        sdk.connect = connect
        with mock.patch.multiple(km, _sdk=lambda: sdk, _codex=lambda: None, _name_of=lambda s: "web",
                                 _cwd_of=lambda s: "/TESTDIR", _commands_for_cwd=lambda cwd: None,
                                 _send_to_view=lambda app, msg, wid: self.fail("a refusal frame: %r" % (msg,))):
            km._revive_session_inner(SID)
        self.assertEqual(sdk.calls[-2:], [("resume", SID), ("connect", SID)])
        self.assertIn(SID, km._ending_sids, "the End that landed mid-revive keeps its latch")
        with mock.patch.object(km, "_compacting_now", lambda sid, **k: True):
            self.assertIsNone(km._send_or_park(self.be, SID, "typed after the End", user=True, qid=QID), "still refused")

    def test_a_typed_clear_whose_busy_re_park_the_latch_refused_is_said_never_queued(self):
        # The third site of the refused re-parks, missed by the previous amend and executed by the fourth review
        # (2026-09-21): the native clear's "busy" answer re-parks the words, and a refused re-park filed queued for an op
        # that vanished, so POST /send and the composer's sendMessage arm reported a typed /clear or /new as queued with
        # nothing queued and nothing said. The refusal takes the arm's own refused-clear road: filed in the state, one
        # warn frame on the delivering socket with the copy's id, a row on the bell, and queued stays False.
        self.assertEqual(km._drop_parked_on_end(SID), 0)
        self.be.answer = "busy"
        state = {}
        self.assertTrue(km._route_meta_command(self.be, SID, "/clear", self.client, state=state, qid=QID))
        self.assertEqual(self.be.calls, [("clear", SID)], "the verb was asked once")
        self.assertEqual(state.get("refused_clear"), km._ENDING_PARK_REFUSAL)
        self.assertFalse(state.get("queued"), "never queued for an op that vanished: %r" % (state,))
        self.assertEqual(self.sent, [{"type": "warn", "text": km._ENDING_PARK_REFUSAL, "sid": SID, "qid": QID}])
        self.assertEqual(self._last_notice().get("kind"), "refused")
        self.assertNotIn(SID, km._pending_ops, "no queued chip for words that went nowhere")

    def test_a_move_whose_backend_raised_lifts_nothing(self):
        # The counterpart: a raise is not a return, so the backends are not asked and the latch stands (the row's state
        # is the backend's to settle); the raise is worded as a refusal, as before.
        self.assertEqual(km._drop_parked_on_end(SID), 0)
        self.be.move = lambda sid, path: (_ for _ in ()).throw(RuntimeError("mid-move"))
        with mock.patch.multiple(km, _cwd_of=lambda s: "/TESTDIR-moved", _commands_for_cwd=lambda cwd: None,
                                 _send_to_view=lambda app, msg, wid: None):
            self.assertEqual(km._move_now(self.be, SID, "/TESTDIR-moved", 0, ""), "RuntimeError: mid-move")
        self.assertIn(SID, km._ending_sids)

    def test_a_revive_whose_connect_failed_after_the_resume_lifts_the_latch(self):
        # The SDK resume alone makes the row live (the registry's alive flips), and the door's connect may fail after
        # it; a lift on the door's success bit left that live row latched (the third review, 2026-09-21). The door's
        # exit asks the backends, whatever its verdict: the refusal is still said, and the latch is gone.
        self.assertEqual(km._drop_parked_on_end(SID), 0)
        sdk = self.be                                      # the stub wears the SDK's hat: owns() True, resume True, connect False
        sdk.connect = lambda sid: (sdk.calls.append(("connect", sid)), False)[1]
        frames = []
        with mock.patch.multiple(km, _sdk=lambda: sdk, _codex=lambda: None, _name_of=lambda s: "web",
                                 _cwd_of=lambda s: "/TESTDIR", _commands_for_cwd=lambda cwd: None,
                                 _send_to_view=lambda app, msg, wid: frames.append((app, msg["type"]))):
            km._revive_session_inner(SID)
        self.assertEqual(sdk.calls[-2:], [("resume", SID), ("connect", SID)])
        self.assertEqual(frames, [("chat", "reviveFailed"), ("feed", "reviveFailed")], "the failed connect is still said")
        self.assertNotIn(SID, km._ending_sids, "the resume made the row live: the latch is gone")

    def test_a_send_refused_by_a_latched_row_with_no_marker_yet_says_ended(self):
        # The doors write the death marker only after the kill returns, and the cancelled cue writes none, so a send the
        # dying row refused during the kill read "backend refused" or "no running backend" from a reason that looked for
        # the marker first (the third review, 2026-09-21). The End latch is the kernel's earliest record, and it is
        # read first. No marker, no snapshot, the stub still owns the row: the frame says the session ended.
        self._restore_undelivered()
        self.assertEqual(km._drop_parked_on_end(SID), 0)   # latched; no marker is written here
        self.assertFalse((km.jd.STATE / "gone" / (SID + ".json")).exists())
        text = "typed, then refused by the dying row during its kill"
        km._pending_ops[SID] = [("send", text, "human", QID, True)]   # placed behind the latch, as the drain's pop finds it
        km._save_pending_ops()
        self.be.send = lambda sid, t: False
        km._apply_pending_ops()
        self.assertEqual([m.get("copy") for m in self._errs()], [text])
        self.assertIn("ended", self._errs()[0]["text"], self._errs()[0]["text"])
        self.assertNotIn("backend refused", self._errs()[0]["text"])

    def test_a_model_pick_whose_park_the_latch_refused_is_answered_as_a_refusal_never_queued(self):
        # Three doors reported parked after a park the latch refused, so the op vanished while the route answered
        # queued (the third review, 2026-09-21). The model pick under a compaction, through the route POST /send takes
        # and through the WS arm: the state carries the refusal and no queued, the pane hears a settingRefused frame,
        # the pending dots are taken back, and nothing reaches the backend (the stub has no set_model: a hand-over raises).
        self.assertEqual(km._drop_parked_on_end(SID), 0)
        state = {}
        with mock.patch.object(km, "_compacting_now", lambda sid, **k: True):
            self.assertTrue(km._route_meta_command(self.be, SID, "/model gpt-5-test", self.client, state=state))
            self.assertTrue(km._drive({"type": "setModel", "id": SID, "value": "gpt-5-test"}, self.client))
        self.assertFalse(state.get("queued"), "the route never answers queued for a pick that vanished: %r" % (state,))
        self.assertEqual(state.get("refused"), km._ENDING_PARK_REFUSAL)
        refused = [f for f in self.sent if f.get("type") == "settingRefused"]
        self.assertEqual([(f["gesture"], f["sid"], f["flag"], f["text"]) for f in refused],
                         [("command", SID, "model", km._ENDING_PARK_REFUSAL)] * 2, "the route's door and the WS arm both say it")
        self.assertNotIn(SID, km._pending_ops)
        self.assertNotIn(SID, km._model_switch_pending, "the switching dots are taken back")

    def test_a_compact_press_whose_busy_re_park_the_latch_refused_is_said_never_queued(self):
        # The compact door's "busy" answer re-parks the press; refused by the latch, it answered queued for a press that
        # vanished (the third review, 2026-09-21). The refusal takes the door's own refusal road: filed in the state, said
        # on the pressing socket with the copy's id, on the bell, and answered None.
        self.assertEqual(km._drop_parked_on_end(SID), 0)
        self.be.answer = "busy"
        state = {}
        self.assertIsNone(km._compact_or_park(self.be, SID, state=state, client=self.client, qid=QID))
        self.assertEqual(state.get("refused"), km._ENDING_PARK_REFUSAL)
        self.assertEqual(self.sent, [{"type": "warn", "text": km._ENDING_PARK_REFUSAL, "sid": SID, "qid": QID}])
        self.assertNotIn(SID, km._pending_ops, "no queued chip for a press that went nowhere")

    def test_a_kill_that_raises_at_an_end_door_lifts_the_latch_and_raises_on(self):
        # The dashboard's End, the end route and the self-close sweep latch before their kill; a kill that raised left
        # the latch on a row that did not end (the second review, 2026-09-21). The WS arm executed: the latch is gone,
        # the attribution line names the door, and the raise propagates as it did (no death record for a session that
        # may be alive; the WS loop logs it). The other doors are pinned to take the same helper.
        import contextlib, io
        self.be.kill = lambda sid: (_ for _ in ()).throw(RuntimeError("the backend's kill raised"))
        log = io.StringIO()
        with contextlib.redirect_stderr(log), self.assertRaises(RuntimeError):
            km._drive({"type": "endSession", "id": SID}, self.client)
        self.assertNotIn(SID, km._ending_sids, "the session did not end: no latch")
        self.assertIn("via endSession WS op raised; the End latch is lifted", log.getvalue())
        self.assertFalse((km.jd.STATE / "gone" / (SID + ".json")).exists(), "no death record for a kill that raised")
        route = inspect.getsource(km.Handler.do_POST)
        route = route[route.index("via /kill route"):]
        for src, door in ((inspect.getsource(km._end_on_idle_sweep), "the self-close sweep"), (route[:route.index("_record_death")], "the end route"),
                          (inspect.getsource(km._end_pending_sid), "the cue's teardown")):
            self.assertIn("_kill_at_end_door(be, sid, ", src, "%s kills through the helper that lifts on a raise" % door)
            self.assertNotIn("be.kill(sid)", src, "%s has no bare kill left" % door)

    def test_a_live_sids_standing_marker_costs_the_drain_no_states_read(self):
        # The snapshot is read first (the second review, 2026-09-21): a marker outlived by a revive (the Codex resume
        # writes no states row) put the states file's whole read on every drain pass for the revived row's queue. A sid
        # the cycle's snapshot lists is live, one dict lookup, and nothing else is read: the send delivers, no latch. The
        # undelivered file is restored although no hand-back is expected: under a kernel that hands this send back, the
        # row it files must not leak into the module's later undelivered assertions.
        self._restore_undelivered()
        self._death_record(SID)
        km._pending_ops[SID] = [("send", "typed on the revived row", "human", QID, True)]
        km._save_pending_ops()
        reads, real_states, real_marker = [], km._last_states_row, km._death_marker
        live_reads = []
        km._live_scope.snapshot = {SID: {"state": "waiting", "backend": "codex"}}
        try:
            # every read past the snapshot is counted: the states file, the marker (named so it can be: the third review,
            # 2026-09-21) and a fresh liveness read, which the predicate's own guard would swallow if it merely raised
            with mock.patch.object(km, "_last_states_row", lambda sid: (reads.append(("states", sid)), real_states(sid))[1]), \
                 mock.patch.object(km, "_death_marker", lambda sid: (reads.append(("marker", sid)), real_marker(sid))[1]), \
                 mock.patch.object(km.Sessions, "live", staticmethod(lambda: (live_reads.append(1), {})[1])):
                km._apply_pending_ops()
        finally:
            km._live_scope.snapshot = None
        self.assertEqual(reads, [], "a sid the snapshot lists is live: no marker read, no states-file read")
        self.assertEqual(live_reads, [], "and no fresh liveness read")
        self.assertEqual(self.be.calls, [("send", "typed on the revived row")], "delivered")
        self.assertNotIn(SID, km._ending_sids)
        self.assertEqual(self._errs(), [])

    def test_every_road_that_brings_a_sid_back_lifts_the_latch(self):
        # The two thread roads resume a sid outside the revive door (a relayed thread's reply, a resolved thread's promote);
        # each lifts the latch on its resume. Source pins, since driving either needs a forking backend and a thread store.
        for fn in (km._comment_reply, km._comment_promote_inner):
            src = inspect.getsource(fn)
            resume, lift = src.index("be.resume("), src.find("_lift_end_latch(tsid)")
            self.assertGreater(lift, resume, "%s lifts the latch after its resume" % fn.__name__)
        door = inspect.getsource(km._revive_session_inner)
        self.assertLess(door.index("since = _end_latch_now()"), door.index("be.resume("),
                        "the revive door reads the latch generation before its resume (the fourth review)")
        self.assertLess(door.index("_lift_end_latch_if_live(sid, since)"), door.index("if not ok:"),
                        "the revive door lifts on fresh liveness at its exit, ahead of its refusal branch, whatever its verdict")
        move = inspect.getsource(km._move_now)
        self.assertLess(move.index("since = _end_latch_now()"), move.index("be.move("),
                        "the move reads the latch generation before its backend call (the fourth review)")
        self.assertLess(move.index("_lift_end_latch_if_live(sid, since)"), move.index('if res == "busy":'),
                        "the move lifts on fresh liveness after the backend answered, whatever the answer")

    def test_a_message_and_a_command_parked_together_come_back_in_one_dialog_that_counts_each_kind(self):
        # Two texts handed back one frame each showed one dialog: the pane replaces the dialog before it on every err
        # frame (post-merge review of the hand-back, 2026-09-21). One frame carries both under their own headers; its
        # title counts by kind, so a message and a typed slash command read as one of each, never as two of one; the
        # frame names no request, where the frame for one text names its own. Each text still gets its own row.
        self._restore_undelivered()
        self._name(SID, "web")
        km._park_op(SID, ("send", "words the user typed", "human", QID, True))
        km._park_op(SID, ("command", "/model opus", "human", None, True))
        frames = []
        pane = {"app": "chat", "alive": True, "send": lambda t: frames.append(json.loads(t))}
        self.assertEqual(km._drop_parked_on_end(SID, pane), 2, "two texts handed back")
        errs = [f for f in frames if f.get("type") == "err"]
        self.assertEqual(len(errs), 1, "one dialog for one End: %r" % [f.get("title") for f in errs])
        self.assertEqual(errs[0]["title"], "1 message and 1 command were not delivered")
        self.assertEqual(errs[0]["copy"], "--- message 1 of 2 ---\nwords the user typed\n\n--- command 2 of 2 ---\n/model opus")
        # The feed's err arm re-arms latches by these two slots: apiRetry with a sid, askFollowUp with an id, and an EMPTY
        # op with a sid as an older kernel's session-wide reply (Retry and Revive). Two doors folded carry the verb
        # "handback", which matches no latch kind, so this frame re-arms nothing, as the one-text frame does not.
        self.assertEqual((errs[0]["sid"], errs[0]["op"], errs[0]["itemId"]), (SID, "handback", ""),
                         "a frame folding two doors carries the hand-back verb and no id")
        self.assertTrue(errs[0]["op"] and errs[0]["op"] not in ("apiRetry", "askFollowUp"), "not a latch kind, not the empty op")
        self.assertIn("ended", errs[0]["text"])
        self.assertIn("(session web)", errs[0]["text"], "the session as the person knows it, as the one-text frame names it")
        self.assertIn("1 message and 1 command", errs[0]["text"])
        rows = [json.loads(l) for l in (km.jd.STATE / "undelivered.jsonl").read_text().splitlines() if l.strip()]
        self.assertEqual([(r["op"], r["text"]) for r in rows if r.get("sid") == SID],
                         [("sendMessage", "words the user typed"), ("sendCommand", "/model opus")], "one row per text, in typed order")
        self.assertNotIn(SID, km._pending_ops)


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
        self.client = {"app": "chat", "send": lambda t: self.sent.append(json.loads(t))}   # a chat pane's socket: it renders err
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

    def _restore_file(self, path):
        """Leave `path` as found after the test: the bytes it held, or absent."""
        before = path.read_bytes() if path.exists() else None

        def restore():
            if before is None:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
            else:
                path.write_bytes(before)
        self.addCleanup(restore)

    def _bracket_nothing_ends(self, where):
        """The second review's probe (2026-09-21): a compaction the server acks and never runs (the bracket stands with
        no status seen). Returns the sid; the files End records and the refusal keeps are restored after the test. Split
        from the park below after the post-merge review of #1970 (2026-09-21), so a case can park through a live road
        (the send route, the sendCommand door) instead of the helper's own park."""
        for name in ("gone/%s.json" % SID_REAL, "states/%s.jsonl" % SID_REAL, "undelivered.jsonl", "end-on-idle.json"):
            self._restore_file(self.root / name)
        sid = self.be.spawn("web", where, sid=SID_REAL)
        self.assertTrue(self.be.send(sid, "first synthetic turn"))
        self.assertTrue(self.cbt._lock_free(self.be, sid))
        self.assertIs(km._compact_or_park(self.be, sid), False, "fired now: the ack, and no status ever follows")
        self.assertIs(km._compacting_now(sid), True, "the bracket stands with no active seen")
        return sid

    def _parked_behind_a_bracket_nothing_ends(self, text, where):
        """The probe's bracket, then a message typed under it, parked in the kernel's queue with BOTH markers the
        hand-back's predicate reads (the user flag and a press-minted copy id: the composer's park)."""
        sid = self._bracket_nothing_ends(where)
        self.assertIs(km._send_or_park(self.be, sid, text, user=True, qid=QID), True, "parks behind the bracket")
        self.assertEqual([op[:2] for op in km._pending_ops[sid]], [("send", text)])
        return sid

    def _after_end(self, sid, text, n0, where, errs, op="sendMessage"):
        """What every End door owes the parked message: the drain's pass in End's own wake (the push-soon), then a
        Revive and another pass, and the text reaches the not-delivered frame exactly once and the thread never; the
        undelivered file keeps it once; the queue and its disk mirror no longer hold the sid. `op` is the request the
        frame and the file name: a parked message is handed back as a sendMessage, a parked command as a sendCommand
        (2026-09-21)."""
        self.assertIs(self.be.owns(sid), False, "End killed the row")
        km._apply_pending_ops()
        self.assertTrue(self.be.resume("web", sid, cwd=where))
        self.assertIs(self.be.owns(sid), True)
        km._apply_pending_ops()
        delivered = [c for c in self.fake.called("turn_start")[n0:] if any(i.get("text") == text for i in c[2])]
        self.assertTrue(delivered or errs, "the text reached neither the thread nor the not-delivered frame: dropped silently")
        self.assertEqual(delivered, [], "nothing typed under the cue runs unasked on the row End killed or the revived one")
        self.assertEqual(len(errs), 1, errs)
        self.assertEqual((errs[0]["sid"], errs[0]["op"]), (sid, op))
        self.assertIn("not delivered", errs[0]["title"])
        self.assertIn("ended", errs[0]["text"])
        rows = [json.loads(l) for l in (self.root / "undelivered.jsonl").read_text().splitlines() if l.strip()]
        self.assertEqual([(r["sid"], r["op"], r["text"]) for r in rows if r.get("sid") == sid], [(sid, op, text)],
                         "kept verbatim, once, under the request's verb")
        self.assertNotIn(sid, km._pending_ops, "the ending session's queue is gone with it")
        mirror = json.loads(km._PENDING_OPS_FILE.read_text()) if km._PENDING_OPS_FILE.exists() else {}
        self.assertNotIn(sid, mirror, "and the disk mirror does not replay it into a restart")
        self.assertEqual(self.be.pending_queued(sid), [], "the backend's own queue never had it")

    def _parked_behind_an_account_hold(self, text, where, prompted):
        """A message typed while the account cannot serve a request, parked in the kernel's queue behind the hold
        (_limit_hold), on a session that was prompted once or never (an Opening cue's spawn). Returns the sid; the
        files End records and the refusal keeps are restored after the test."""
        for name in ("gone/%s.json" % SID_REAL, "states/%s.jsonl" % SID_REAL, "undelivered.jsonl", "end-on-idle.json"):
            self._restore_file(self.root / name)
        sid = self.be.spawn("web", where, sid=SID_REAL)
        if prompted:
            self.assertTrue(self.be.send(sid, "first synthetic turn"))
            self.assertTrue(self.cbt._lock_free(self.be, sid))
        hold = {"reason": "limit", "resetsAt": None, "what": "waiting for your usage limit to reset"}
        with mock.patch.object(km, "_limit_hold", lambda sid: hold):
            self.assertIs(km._send_or_park(self.be, sid, text, user=True, qid=QID), True, "parks behind the account hold")
        self.assertEqual([op[:2] for op in km._pending_ops[sid]], [("send", text)])
        return sid

    def test_cancel_create_hands_a_message_parked_under_the_opening_cue_back(self):
        # The fourth End door (the post-merge review of the End hand-back, 2026-09-21): the Opening cue's cancel resolves
        # the name to the just-spawned session and kills it, and a message typed under the cue while the account could
        # not serve it, parked behind the hold, was dropped with the kill: the drain popped it in the same wake and
        # handed it to a row that read as unowned. The teardown now cancels the queue before the kill, like the other
        # three doors; no socket reaches it, so the words go to one pane that renders them (a chat pane first, the feed
        # when no chat pane is connected).
        text = "typed under the opening cue, behind the account hold"
        sid = self._parked_behind_an_account_hold(text, "/TESTDIR-compact-cancel-create", prompted=False)
        self.assertIs(km._session_has_history(sid), False, "never prompted: the history guard lets the teardown through")
        n0 = len(self.fake.called("turn_start"))
        broadcast = []
        with mock.patch.object(km, "_send_to_app", lambda app, m: broadcast.append((app, m))):
            km._end_pending_sid(sid)
        self.assertIn(("chat", {"type": "closed", "id": sid}), broadcast, "the tab closes as before")
        self._after_end(sid, text, n0, "/TESTDIR-compact-cancel-create",
                        [m for app, m in broadcast if app == "chat" and m.get("type") == "err" and m.get("copy") == text])

    def test_a_send_run_the_drain_popped_just_before_end_is_handed_back(self):
        # The drain pops a send run whole before the handover; an End landing in between finds the queue already empty
        # and hands nothing back, and the delivery discarded the backend's False for a row that had just died (review
        # find, 2026-09-21). The interleaving is exact: End runs inside the backend's send, after the pop, before the
        # real send answers. The refused send now takes the not-delivered path to one pane, once.
        text = "popped by the drain, then the session ended"
        sid = self._parked_behind_an_account_hold(text, "/TESTDIR-compact-popped-end", prompted=True)
        n0 = len(self.fake.called("turn_start"))
        broadcast = []
        real_send = self.be.send

        def send(sid_, text_):
            self.assertEqual(km._pending_ops.get(sid) or [], [], "the run is already popped when End lands")
            self.assertTrue(km._drive({"type": "endSession", "id": sid}, self.client))
            return real_send(sid_, text_)
        self.be.send = send
        try:
            # the drain runs inside a pusher cycle whose liveness snapshot was taken BEFORE the End: it still lists the
            # row End kills mid-handover, and the hand-back's reason must not read it (review find, 2026-09-21)
            km._live_scope.snapshot = km.Sessions.live()
            self.assertIn(sid, km._live_scope.snapshot, "the cycle's snapshot lists the row, pre-End")
            with mock.patch.object(km, "_send_to_app", lambda app, m: broadcast.append((app, m))):
                km._apply_pending_ops()
        finally:
            del self.be.send
            km._live_scope.snapshot = None
        self.assertEqual([f for f in self.sent if f.get("type") == "err"], [], "End's own cancel found nothing to hand back")
        self._after_end(sid, text, n0, "/TESTDIR-compact-popped-end",
                        [m for app, m in broadcast if app == "chat" and m.get("type") == "err" and m.get("copy") == text])

    def test_a_drain_pass_on_a_snapshot_that_predates_the_revive_leaves_the_live_rows_park_and_writes_no_latch(self):
        # Reproduced by the second review over this backend (2026-09-21): End, then a cycle's snapshot taken before the
        # revive, the real revive door (the latch lifts), a park on the live row, and a drain pass on that snapshot. The
        # backstop read the snapshot (no row), the marker (standing: CodexBackend.resume writes no states row) and handed
        # the park back as ended, re-latching a LIVE row until a restart. The not-live verdict is confirmed against the
        # backends now before anything is handed back or latched: the park stands under its hold, no latch, no frame.
        for name in ("gone/%s.json" % SID_REAL, "states/%s.jsonl" % SID_REAL, "undelivered.jsonl", "end-on-idle.json"):
            self._restore_file(self.root / name)
        where = "/TESTDIR-compact-stale-snapshot"
        sid = self.be.spawn("web", where, sid=SID_REAL)
        self.assertTrue(self.be.send(sid, "first synthetic turn"))
        self.assertTrue(self.cbt._lock_free(self.be, sid))
        self.assertTrue(km._drive({"type": "endSession", "id": sid}, self.client))
        self.assertIs(self.be.owns(sid), False, "End killed the row")
        self.assertIn(sid, km._ending_sids, "and latched it")
        stale = km.Sessions.live()                        # a cycle's snapshot, taken between the End and the revive
        self.assertNotIn(sid, stale)
        with mock.patch.multiple(km, _codex_ready=lambda: True, _models_changed=lambda: None, _commands_for_cwd=lambda cwd: None,
                                 _send_to_view=lambda app, msg, wid: self.fail("a refusal frame: %r" % (msg,))):
            km._revive_session_inner(sid)                 # the real revive door
        self.assertIs(self.be.owns(sid), True, "live again under its sid")
        self.assertNotIn(sid, km._ending_sids, "the revive lifted the latch")
        text = "typed on the revived row, drained on a stale snapshot"
        hold = {"reason": "limit", "resetsAt": None, "what": "waiting for your usage limit to reset"}
        with mock.patch.object(km, "_limit_hold", lambda sid: hold):
            self.assertIs(km._send_or_park(self.be, sid, text, user=True, qid=QID), True, "parks behind the hold, welcome again")
        broadcast = []
        km._live_scope.snapshot = stale
        try:
            with mock.patch.object(km, "_limit_hold", lambda sid: hold), \
                 mock.patch.object(km, "_send_to_app", lambda app, m: broadcast.append((app, m))):
                km._apply_pending_ops()
        finally:
            km._live_scope.snapshot = None
        self.assertEqual([op[1] for op in km._pending_ops.get(sid, [])], [text], "the live row's park stands under the hold")
        self.assertNotIn(sid, km._ending_sids, "no latch is written for a live row")
        self.assertEqual([m for app, m in broadcast if m.get("type") == "err"], [], "nothing is handed back")
        self.assertEqual([f for f in self.sent if f.get("type") == "err"], [], "and nothing reached the pane that pressed End")

    def test_end_hands_a_message_parked_behind_a_bracket_the_server_never_ran_back_as_not_delivered(self):
        # The probe replayed through the dashboard's End (the WS op): End killed the row and woke the drain, which
        # popped the send and handed it to a row that read as unowned, whose refusal the delivery ignored, so the chat
        # heard nothing, and Revive drains only the backend's own queue, which is empty: the message was gone, while
        # the doc said End then Revive delivered it. The End doors now cancel the ending session's parked sends
        # through the not-delivered path: the err frame hands the text back in its copy slot on the ending pane.
        text = "typed behind a cue nothing ends"
        sid = self._parked_behind_a_bracket_nothing_ends(text, "/TESTDIR-compact-end")
        n0 = len(self.fake.called("turn_start"))
        self.assertTrue(km._drive({"type": "endSession", "id": sid}, self.client))
        self._after_end(sid, text, n0, "/TESTDIR-compact-end",
                        [f for f in self.sent if f.get("type") == "err" and f.get("copy") == text])

    def test_an_end_from_a_pane_that_cannot_show_the_modal_hands_it_to_a_chat_pane(self):
        # The Sessions pane's End arrives on that pane's own socket, whose bundle has no err arm: handed there, the
        # frame showed nothing and reached no chat pane either, since a client was supplied (review find, 2026-09-21).
        # A client whose app does not render err falls to the chat target.
        text = "typed behind a cue, ended from the sessions pane"
        sid = self._parked_behind_a_bracket_nothing_ends(text, "/TESTDIR-compact-end-fleet")
        n0 = len(self.fake.called("turn_start"))
        fleet_frames, broadcast = [], []
        fleet = {"app": "fleet", "send": lambda t: fleet_frames.append(json.loads(t))}
        with mock.patch.object(km, "_send_to_app", lambda app, m: broadcast.append((app, m))):
            self.assertTrue(km._drive({"type": "endSession", "id": sid}, fleet))
        self.assertEqual([f for f in fleet_frames if f.get("type") == "err"], [], "the pane that cannot show it gets no frame")
        self._after_end(sid, text, n0, "/TESTDIR-compact-end-fleet",
                        [m for app, m in broadcast if app == "chat" and m.get("type") == "err" and m.get("copy") == text])

    def test_end_drops_a_machines_send_parked_beside_the_typed_one_with_no_modal(self):
        # A machine's send parks through the same road (a watch notice, the spend-ceiling body, a tagged romp send):
        # handed back as the user's words, End would offer to copy text they never typed and file it in the
        # undelivered file as theirs, a false interrupt (review find, 2026-09-21). Only the typed one comes back;
        # the machine's is dropped with a log line naming the kind and never the body.
        import contextlib, io
        text = "typed behind a cue nothing ends"
        sid = self._parked_behind_a_bracket_nothing_ends(text, "/TESTDIR-compact-end-machine")
        machine = "a watch notice the kernel composed"
        self.assertIs(km._send_or_park(self.be, sid, machine), True, "the machine's send parks behind the typed one")
        self.assertEqual([op[:2] for op in km._pending_ops[sid]], [("send", text), ("send", machine)])
        self.assertFalse(km._op_user(km._pending_ops[sid][1]) or km._op_qid(km._pending_ops[sid][1]), "no user flag, no press id")
        n0 = len(self.fake.called("turn_start"))
        log = io.StringIO()
        with contextlib.redirect_stderr(log):
            self.assertTrue(km._drive({"type": "endSession", "id": sid}, self.client))
        errs = [f for f in self.sent if f.get("type") == "err"]
        self.assertEqual([f.get("copy") for f in errs], [text], "exactly one modal, carrying the typed text")
        self.assertIn("parked send op dropped with the ending session %s" % sid, log.getvalue())
        self.assertNotIn(machine, log.getvalue(), "the log names the kind, never the body")
        self._after_end(sid, text, n0, "/TESTDIR-compact-end-machine", errs)
        rows = [json.loads(l) for l in (self.root / "undelivered.jsonl").read_text().splitlines() if l.strip()]
        self.assertEqual([r["text"] for r in rows if r.get("sid") == sid], [text], "the machine's text is not filed as the user's")
        self.assertEqual([c for c in self.fake.called("turn_start")[n0:] if any(i.get("text") == machine for i in c[2])], [])

    def test_the_end_route_hands_the_parked_message_to_a_chat_pane(self):
        # romp end lands here with no socket: the not-delivered frame goes to one pane that renders it
        # (_send_to_one_chat: a chat pane first, the feed when no chat pane is connected), the same shape the WS op
        # sends its pane. No chat or feed client is connected in this case, so the picker falls to the chat broadcast,
        # and that fallback is what this test reads (the post-merge review of 2026-09-21 read the earlier "every chat
        # pane" here as stale against the picker: the broadcast is the fallback, not the road).
        import threading
        from http.server import ThreadingHTTPServer
        import urllib.request
        text = "typed behind a cue, ended from the shell"
        sid = self._parked_behind_a_bracket_nothing_ends(text, "/TESTDIR-compact-end-route")
        n0 = len(self.fake.called("turn_start"))
        broadcast = []
        srv = ThreadingHTTPServer(("127.0.0.1", 0), km.Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        req = urllib.request.Request("http://127.0.0.1:%d/end" % srv.server_address[1], method="POST",
                                     data=json.dumps({"id": sid}).encode(),
                                     headers={"Content-Type": "application/json", "X-Romp-Token": km.TOKEN})
        with mock.patch.object(km, "_send_to_app", lambda app, m: broadcast.append((app, m))):
            with urllib.request.urlopen(req, timeout=10) as r:
                # the answer counts the typed text handed back (2026-09-21): the shell caller, with no pane to show
                # the frame, learns from the answer alone that a message did not go through
                self.assertEqual((r.status, json.loads(r.read().decode())), (200, {"ok": True, "undelivered": 1}))
        self.assertIn(("chat", {"type": "closed", "id": sid}), broadcast, "the tab closes as before")
        self._after_end(sid, text, n0, "/TESTDIR-compact-end-route",
                        [m for app, m in broadcast if app == "chat" and m.get("type") == "err" and m.get("copy") == text])

    def test_the_self_close_sweep_hands_the_parked_message_to_a_chat_pane(self):
        # romp end self defers to idle; the pusher's sweep kills at the turn's settle and takes the end route's road:
        # no socket, so one pane that renders it, read here through the broadcast fallback with no chat or feed client
        # connected, as the route test does (reworded 2026-09-21, the post-merge review). The sweep's own transcript read is stubbed quiet
        # (tests/test_kernel_end_on_idle.py's shape); the parked queue, the kill and the frames are real.
        text = "typed behind a cue, ended by the session itself"
        sid = self._parked_behind_a_bracket_nothing_ends(text, "/TESTDIR-compact-end-sweep")
        n0 = len(self.fake.called("turn_start"))
        broadcast = []
        km._end_on_idle_save({sid})
        with mock.patch.object(km, "_send_to_app", lambda app, m: broadcast.append((app, m))), \
             mock.patch.object(km, "_parse", lambda path, sid, now: {"turns": []}), \
             mock.patch.object(km, "_session_working", lambda turns: False):
            km._end_on_idle_sweep(int(time.time()), km.Sessions.live())
        self.assertEqual(km._end_on_idle_load(), set(), "the wish is spent")
        self.assertIn(("chat", {"type": "closed", "id": sid}), broadcast)
        self._after_end(sid, text, n0, "/TESTDIR-compact-end-sweep",
                        [m for app, m in broadcast if app == "chat" and m.get("type") == "err" and m.get("copy") == text])

    def test_end_hands_back_a_send_parked_with_the_user_flag_and_no_press_id(self):
        # Every End case above parks with both markers (user=True, qid=QID), so the hand-back predicate's flag-only
        # half was pinned by nothing (the post-merge review of #1970, 2026-09-21), while an untagged romp send parks
        # with the flag alone: POST /send and `romp send` land in _deliver_text, which sets the user flag from the
        # absence of the romp-tag comment the CLI adds only on --tag and mints no press id. Parked through that
        # route, the op's PROPERTY is what the case asserts (the flag True, the id None), never its tuple spelling.
        text = "typed into romp send behind a cue nothing ends"
        sid = self._bracket_nothing_ends("/TESTDIR-compact-end-flag-only")
        self.assertEqual(km._deliver_text(sid, text), (True, "", True), "the send route parks it and answers queued")
        ops = km._pending_ops[sid]
        self.assertEqual([op[:2] for op in ops], [("send", text)])
        self.assertIs(km._op_user(ops[0]), True, "the user's words")
        self.assertIsNone(km._op_qid(ops[0]), "and no press id rode")
        n0 = len(self.fake.called("turn_start"))
        self.assertTrue(km._drive({"type": "endSession", "id": sid}, self.client))
        self._after_end(sid, text, n0, "/TESTDIR-compact-end-flag-only",
                        [f for f in self.sent if f.get("type") == "err" and f.get("copy") == text])

    def test_end_hands_back_a_command_parked_through_the_send_command_door(self):
        # The predicate's command arm had no case either (the post-merge review of #1970, 2026-09-21). The lane
        # menu's sendCommand door parks a typed slash command with the flag alone; on a Codex session that is a head
        # outside the refused and setter sets, prose to the model, parked as a ("command", ...) op while the bracket
        # stands. End hands it back under the command's own verb, and the thread never runs it. The door resolves an
        # id or a name in its name slot; the sid keeps the case free of a name lookup.
        cmd = "/cost"
        sid = self._bracket_nothing_ends("/TESTDIR-compact-end-command")
        self.assertTrue(km._drive({"type": "sendCommand", "name": sid, "cmd": cmd}, self.client))
        self.assertEqual(self.sent, [], "no refusal: the command parked")
        ops = km._pending_ops[sid]
        self.assertEqual([op[:2] for op in ops], [("command", cmd)])
        self.assertIs(km._op_user(ops[0]), True, "the user typed it")
        self.assertIsNone(km._op_qid(ops[0]), "and the door mints no press id")
        n0 = len(self.fake.called("turn_start"))
        self.assertTrue(km._drive({"type": "endSession", "id": sid}, self.client))
        errs = [f for f in self.sent if f.get("type") == "err" and f.get("copy") == cmd]
        self._after_end(sid, cmd, n0, "/TESTDIR-compact-end-command", errs, op="sendCommand")
        self.assertEqual(errs[0]["title"], "That command was not delivered")

    def _end_over_the_socket(self, sid, text):
        """The dashboard's End (the WS op) on the chat pane's socket; returns the frames that pane got carrying `text`."""
        self.assertTrue(km._drive({"type": "endSession", "id": sid}, self.client))
        return [f for f in self.sent if f.get("type") == "err" and f.get("copy") == text]

    def _end_over_the_route(self, sid, text):
        """romp end (POST /end, no socket); returns the chat broadcast's frames carrying `text`."""
        import threading
        from http.server import ThreadingHTTPServer
        import urllib.request
        broadcast = []
        srv = ThreadingHTTPServer(("127.0.0.1", 0), km.Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        req = urllib.request.Request("http://127.0.0.1:%d/end" % srv.server_address[1], method="POST",
                                     data=json.dumps({"id": sid}).encode(),
                                     headers={"Content-Type": "application/json", "X-Romp-Token": km.TOKEN})
        with mock.patch.object(km, "_send_to_app", lambda app, m: broadcast.append((app, m))):
            with urllib.request.urlopen(req, timeout=10) as r:
                self.assertEqual((r.status, json.loads(r.read().decode()).get("ok")), (200, True))
        return [m for app, m in broadcast if app == "chat" and m.get("type") == "err" and m.get("copy") == text]

    def _end_by_the_sweep(self, sid, text):
        """romp end self, deferred to idle: the pusher's sweep, its own transcript read stubbed quiet; returns the chat
        broadcast's frames carrying `text`."""
        broadcast = []
        km._end_on_idle_save({sid})
        with mock.patch.object(km, "_send_to_app", lambda app, m: broadcast.append((app, m))), \
             mock.patch.object(km, "_parse", lambda path, sid, now: {"turns": []}), \
             mock.patch.object(km, "_session_working", lambda turns: False):
            km._end_on_idle_sweep(int(time.time()), km.Sessions.live())
        self.assertEqual(km._end_on_idle_load(), set(), "the wish is spent")
        return [m for app, m in broadcast if app == "chat" and m.get("type") == "err" and m.get("copy") == text]

    def _ended_with_a_drain_on_the_kills_heels(self, text, where, door):
        """The hand-back runs BEFORE the kill: the claim every End door's order rests on, pinned after the post-merge
        review of #1970 found it asserted by nothing (2026-09-21). The backend's kill is wrapped to run the real kill
        and then one drain pass, the pass End's own wake brought before the hand-back existed. Handed back first,
        the queue is already empty when that pass runs and the text reaches the frame once. Handed back after, the
        pass pops the send to the row the kill just left unowned, whose refusal the delivery ignores, and the
        hand-back then finds nothing: no frame anywhere, the second review's silent drop."""
        sid = self._parked_behind_a_bracket_nothing_ends(text, where)
        n0 = len(self.fake.called("turn_start"))
        real_kill = self.be.kill
        parked_at_kill = []

        def kill_then_drain(sid_):
            parked_at_kill.append(sid_ in km._pending_ops)
            r = real_kill(sid_)
            km._apply_pending_ops()
            return r
        with mock.patch.object(self.be, "kill", kill_then_drain):
            errs = door(sid, text)
        self._after_end(sid, text, n0, where, errs)
        self.assertEqual(parked_at_kill, [False], "the queue was handed back before the kill ran, and the kill ran once")

    def test_the_socket_end_hands_back_before_the_kill(self):
        text = "typed behind a cue, ended over the socket with a drain on the kill's heels"
        self._ended_with_a_drain_on_the_kills_heels(text, "/TESTDIR-compact-end-order-socket", self._end_over_the_socket)

    def test_the_end_route_hands_back_before_the_kill(self):
        text = "typed behind a cue, ended from the shell with a drain on the kill's heels"
        self._ended_with_a_drain_on_the_kills_heels(text, "/TESTDIR-compact-end-order-route", self._end_over_the_route)

    def test_the_self_close_sweep_hands_back_before_the_kill(self):
        text = "typed behind a cue, ended by the session itself with a drain on the kill's heels"
        self._ended_with_a_drain_on_the_kills_heels(text, "/TESTDIR-compact-end-order-sweep", self._end_by_the_sweep)

    def test_end_hands_two_parked_messages_back_in_one_dialog_carrying_both_in_typed_order(self):
        # Two messages typed behind the cue, then End: the hand-back sent one err frame per text, and the pane's
        # dialog replaces the one before it on every frame, so only the second text was ever seen; the first survived
        # in the undelivered file and the log alone (post-merge review of the hand-back, 2026-09-21). One frame per
        # End now carries both in typed order, each under a header naming its kind and place, and the blank line
        # inside the first stays inside it: joined by a bare blank line the two would read as three. Each text still
        # gets its own undelivered row and its own log line, and neither runs on the row End killed or the revived one.
        import contextlib, io
        first = "first words typed behind the cue\n\nafter a blank line inside the same message"
        second = "second words typed behind the cue"
        where = "/TESTDIR-compact-end-two"
        sid = self._parked_behind_a_bracket_nothing_ends(first, where)
        self.assertIs(km._send_or_park(self.be, sid, second, user=True, qid=QID2), True, "the second parks behind the first")
        self.assertEqual([op[:2] for op in km._pending_ops[sid]], [("send", first), ("send", second)])
        n0 = len(self.fake.called("turn_start"))
        log = io.StringIO()
        with contextlib.redirect_stderr(log):
            self.assertTrue(km._drive({"type": "endSession", "id": sid}, self.client))
        errs = [f for f in self.sent if f.get("type") == "err"]
        self.assertEqual(len(errs), 1, "one dialog for one End: %r" % [f.get("copy") for f in errs])
        self.assertEqual(errs[0]["copy"], "--- message 1 of 2 ---\n" + first + "\n\n--- message 2 of 2 ---\n" + second,
                         "both texts in typed order, each under its own header")
        self.assertEqual(errs[0]["title"], "2 messages were not delivered")
        self.assertIn("ended", errs[0]["text"])
        # Two messages share one door, so the folded frame keeps its op (sendMessage) and an empty id: the feed's err arm
        # re-arms a latch for apiRetry with a sid, askFollowUp with an id, or an EMPTY op with a sid (an older kernel's
        # session-wide reply), and sendMessage is none of those, so the frame re-arms nothing, as the one-text frame does not.
        self.assertEqual((errs[0]["sid"], errs[0]["op"], errs[0]["itemId"]), (sid, "sendMessage", ""),
                         "a frame folding two messages keeps their shared op and names no id")
        self.assertTrue(errs[0]["op"] and errs[0]["op"] not in ("apiRetry", "askFollowUp"), "not a latch kind, not the empty op")
        self.assertEqual(log.getvalue().count("undeliverable sendMessage: The session ended before romp could hand this over %s" % sid), 2,
                         "one log line per text")
        rows = [json.loads(l) for l in (self.root / "undelivered.jsonl").read_text().splitlines() if l.strip()]
        self.assertEqual([r["text"] for r in rows if r.get("sid") == sid], [first, second], "one row per text, verbatim, in typed order")
        self.assertIs(self.be.owns(sid), False, "End killed the row")
        km._apply_pending_ops()
        self.assertTrue(self.be.resume("web", sid, cwd=where))
        km._apply_pending_ops()
        self.assertEqual([c for c in self.fake.called("turn_start")[n0:] if any(i.get("text") in (first, second) for i in c[2])], [],
                         "nothing typed under the cue runs unasked on the row End killed or the revived one")
        self.assertNotIn(sid, km._pending_ops, "the ending session's queue is gone with it")
        self.assertEqual(self.be.pending_queued(sid), [], "the backend's own queue never had them")


if __name__ == "__main__":
    unittest.main()
