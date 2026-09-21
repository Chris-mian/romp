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
_REAL_SEND_TO_APP = km._send_to_app                # the broadcast as shipped, for the one test that pins its reach
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
    km._held_working.pop(sid, None)   # the belt's record that the working gate holds this queue: a test that leaves the
                                      # in-flight slot kept leaves it standing, and the next test inherited it (2026-09-21)


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

    def test_the_end_route_hands_the_parked_message_to_the_chat_panes(self):
        # romp end lands here with no socket: the not-delivered frame goes to every chat pane (the broadcast the
        # kernel-parked ops already use), the same shape the WS op sends its pane.
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
                self.assertEqual((r.status, json.loads(r.read().decode())), (200, {"ok": True}))
        self.assertIn(("chat", {"type": "closed", "id": sid}), broadcast, "the tab closes as before")
        self._after_end(sid, text, n0, "/TESTDIR-compact-end-route",
                        [m for app, m in broadcast if app == "chat" and m.get("type") == "err" and m.get("copy") == text])

    def test_the_self_close_sweep_hands_the_parked_message_to_the_chat_panes(self):
        # romp end self defers to idle; the pusher's sweep kills at the turn's settle and takes the same road as the
        # other two doors. The sweep's own transcript read is stubbed quiet (tests/test_kernel_end_on_idle.py's
        # shape); the parked queue, the kill and the frames are real.
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


if __name__ == "__main__":
    unittest.main()
