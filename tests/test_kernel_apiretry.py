#!/usr/bin/env python3
"""The API-error "Retry" pastes "retry" into the session to resume the stalled turn — tagged with the
romp-injected marker so the chat renders it as a GRAY romp bubble (romp sent it), not a blue human "retry"
prompt (the user 2026-06-19). Source-pin on the kernel's inject + an end-to-end author_of check.

Also covers auto-retry IDEMPOTENCY (the user 2026-07-08): the 10s auto-loop must NOT stack a fresh "retry"
when the one romp already sent is still queued and unconsumed — that piled N bare "retry"s into the SDK
queue during one API-error storm (the "retry retry retry retry…" card). A MANUAL "Retry now" still fires.
"""
import os
import types
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
SRC = open(os.path.join(BIN, "romp-kernel")).read()
em = SourceFileLoader("romp_event_model", os.path.join(BIN, "romp-event-model")).load_module()
SourceFileLoader("romp_judge", os.path.join(BIN, "romp-judge")).load_module()
km = SourceFileLoader("romp_kernel_apiretry", os.path.join(BIN, "romp-kernel")).load_module()

RETRY = "retry\n\n<!-- romp-injected -->"


class FakeBackend:
    """A minimal backend: a controllable pending queue + a record of what got sent."""
    def __init__(self, pending):
        self._pending = list(pending)
        self.sent = []

    def pending_queued(self, sid):
        return list(self._pending)

    def send(self, sid, text):
        self.sent.append(text)
        return True


class ApiRetryRendersAsRomp(unittest.TestCase):
    def test_the_apiretry_handler_tags_retry_with_the_romp_injected_marker(self):
        # the retry is ALWAYS marked romp-injected — BOTH backends (the user 2026-06-30): an auto-retry is
        # romp's action, not the human's. The old tmux-only marking left the SDK retry authored 'human'
        # (blue bubble) and let the planner mint a junk goal per bare "retry". See
        # tests/test_kernel_retry_authorship.py for the authorship end-to-end.
        ap = SRC.split('t == "apiRetry"', 1)[1].split("elif t ==", 1)[0]
        self.assertIn("be.send(sid, RETRY_MSG)", ap, "the handler sends the shared RETRY_MSG constant")
        # the constant itself carries the romp-injected marker → never a bare retry on either backend
        self.assertEqual(km.RETRY_MSG, RETRY, "RETRY_MSG is the marked retry text")
        self.assertIn("romp-injected", km.RETRY_MSG)

    def test_manual_retry_bypasses_the_auto_retry_pause_suppression_gate(self):
        # the gate (global pause / interrupted-thread suppression) stops the AUTO-retry loop only; a MANUAL
        # "Retry now" click (msg.manual) is an explicit one-shot override that ALWAYS fires, so the button is
        # never a dead no-op on a suppressed/paused thread (the user 2026-07-06, SDK backend)
        ap = SRC.split('t == "apiRetry"', 1)[1].split("elif t ==", 1)[0]
        self.assertIn('if not msg.get("manual") and (_retry_paused_on() or _session_retry_suppressed(sid)):', ap,
                      "the auto-retry gate is skipped for a manual click")

    def test_that_injected_retry_is_authored_romp_not_human(self):
        # end-to-end: the exact text romp pastes → author 'romp' (the gray bubble), NOT 'human', even though
        # it arrives via a paste+Enter that Claude Code records as promptSource='typed'
        blocks = [{"type": "text", "text": RETRY}]
        self.assertEqual(em.author_of(blocks, "typed", {}), "romp",
                         "the romp-injected marker wins over promptSource=typed → renders as a romp bubble")
        # sanity: a bare 'retry' (the old behavior) would have been a human prompt
        self.assertEqual(em.author_of([{"type": "text", "text": "retry"}], "typed", {}), "human")


class ApiRetryIdempotency(unittest.TestCase):
    """Drive _drive({type:'apiRetry'}) with a stubbed backend + gate globals and observe what gets sent."""
    def setUp(self):
        self._saved_name_of = km._name_of
        self._saved = (km.Sessions, km._retry_paused_on, km._session_retry_suppressed,
                       km._api_error, km._path_of)
        km._retry_paused_on = lambda: False
        km._name_of = lambda sid: "web"   # these tests drive ops on a session this kernel HAS; _drive refuses one it doesn't (2026-07-29)
        km._session_retry_suppressed = lambda sid: False
        # the one-retry-per-error-episode gate (2026-07-20) reads the CURRENT error record; these tests
        # exercise the queued-idempotency layer, so give each its own live error episode (fresh uuid per
        # test via the counter) — episode semantics themselves are pinned by test_kernel_retry_episode.py
        self._ep = {"n": 0}
        def _aerr(path):
            self._ep["n"] += 1
            return {"text": "500", "status": 500, "category": "server_error",
                    "uuid": "ep-%d" % self._ep["n"], "tooLong": False, "spendLimit": False}
        km._api_error = _aerr
        km._path_of = lambda sid, now=None: "/TESTDIR/x.jsonl"
        km._auto_retried.clear()
        km._auto_retry_state.clear()   # …and the backoff ladder (2026-07-29): each case starts at rung one

    def tearDown(self):
        (km.Sessions, km._retry_paused_on, km._session_retry_suppressed,
         km._api_error, km._path_of) = self._saved
        km._name_of = self._saved_name_of
        km._auto_retried.clear()
        km._auto_retry_state.clear()

    def _drive_retry(self, be, **msg):
        km.Sessions = types.SimpleNamespace(backend_for=lambda sid: be)
        m = {"type": "apiRetry", "id": "s1"}
        m.update(msg)
        km._drive(m, {})

    def test_auto_retry_skips_when_an_identical_retry_is_already_queued(self):
        # the pileup bug: the session is blocked, the previous romp retry is still in the queue unconsumed →
        # the next 10s auto-tick must NOT enqueue another (else "retry retry retry retry…").
        be = FakeBackend(pending=[RETRY])
        self._drive_retry(be)
        self.assertEqual(be.sent, [], "no second retry stacked on top of the pending one")

    def test_auto_retry_fires_once_when_the_queue_is_empty(self):
        be = FakeBackend(pending=[])
        self._drive_retry(be)
        self.assertEqual(be.sent, [RETRY], "an empty queue → exactly one retry is sent")

    def test_a_users_own_queued_message_does_not_block_the_auto_retry(self):
        # only an identical romp RETRY_MSG dedups; a real user turn sitting in the queue must not suppress the
        # recovery retry (exact-match, so no false positive on "retry the build" etc.)
        be = FakeBackend(pending=["retry the build please"])
        self._drive_retry(be)
        self.assertEqual(be.sent, [RETRY], "a non-identical queued message doesn't count as a pending retry")

    def test_manual_retry_always_fires_even_with_one_already_queued(self):
        # "Retry now" is an explicit user override — it fires even if a retry is already pending (and resets
        # the client countdown). The dedup is for the silent 10s AUTO-loop only.
        be = FakeBackend(pending=[RETRY])
        self._drive_retry(be, manual=True)
        self.assertEqual(be.sent, [RETRY], "a manual retry is not deduped by the pending-queue guard")


if __name__ == "__main__":
    unittest.main()
