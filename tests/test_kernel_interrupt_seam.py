#!/usr/bin/env python3
"""The interrupt SEAM in the chat (the user 2026-07-09): a turn cut mid-flight (kernel restart drain, a
crash heal, or a user stop) leaves two artifacts in the transcript — the CLI's stop record and the model's
null settle-reply ("No response requested.") that closes the turn. The chat already rendered the stop
record as a slim rail marker; the settle-reply still rendered as a full assistant bubble, one per session
per restart. _interrupt_settle flags the filler so the client folds it into the seam, and
_stamp_interrupt_causes labels the marker with WHY the turn was cut when romp's own resume notice (the
next user-role event) says so. Synthetic fixtures only."""
import os
import unittest
from importlib.machinery import SourceFileLoader

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "bin")
SourceFileLoader("romp_event_model", os.path.join(BIN, "romp-event-model")).load_module()
SourceFileLoader("romp_judge", os.path.join(BIN, "romp-judge")).load_module()
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
km = SourceFileLoader("romp_kernel_seam", os.path.join(BIN, "romp-kernel")).load_module()

FILLER = "No response requested."
MARKER = {"kind": "user", "md": "[Request interrupted by user]", "interruptMarker": True}


class InterruptSettle(unittest.TestCase):
    def test_the_filler_directly_after_the_marker_is_the_seam(self):
        self.assertTrue(km._interrupt_settle([MARKER], FILLER))

    def test_surrounding_whitespace_still_matches(self):
        self.assertTrue(km._interrupt_settle([MARKER], "  No response requested. \n"))

    def test_a_thinking_block_between_does_not_break_the_seam(self):
        self.assertTrue(km._interrupt_settle([MARKER, {"kind": "thinking", "text": ""}], FILLER))

    def test_a_substantive_reply_after_the_marker_stays_a_bubble(self):
        self.assertFalse(km._interrupt_settle([MARKER], "Stopped; the partial edit is reverted."),
                         "only the exact null filler folds into the seam — real content never")

    def test_the_filler_without_a_preceding_marker_stays_a_bubble(self):
        self.assertFalse(km._interrupt_settle([{"kind": "user", "md": "say nothing"}], FILLER),
                         "a model that literally answers 'No response requested.' to a prompt is content")

    def test_empty_history_is_not_a_seam(self):
        self.assertFalse(km._interrupt_settle([], FILLER))


class StampInterruptCauses(unittest.TestCase):
    def _events(self, notice=None, typed_first=False):
        evs = [dict(MARKER),
               {"kind": "assistant", "md": FILLER, "interruptSettle": True},
               {"kind": "thinking", "text": ""}]
        if typed_first:
            evs.append({"kind": "user", "md": "actually, try the other approach", "human": True})
        if notice is not None:
            evs.append({"kind": "user", "md": notice, "romp": True, "rompSystem": True})
        return evs

    def test_a_restart_resume_notice_names_the_seam(self):
        evs = self._events("[romp] The romp kernel restarted and cut this session's in-flight turn; …")
        km._stamp_interrupt_causes(evs)
        self.assertEqual(evs[0].get("interruptCause"), "restart")

    def test_a_crash_resume_notice_names_the_seam(self):
        evs = self._events("[romp] This session's claude process died mid-turn (killed or crashed); …")
        km._stamp_interrupt_causes(evs)
        self.assertEqual(evs[0].get("interruptCause"), "crash")

    def test_no_notice_means_a_genuine_user_stop_and_stays_unlabeled(self):
        evs = self._events(None)
        km._stamp_interrupt_causes(evs)
        self.assertNotIn("interruptCause", evs[0],
                         "an unlabeled seam keeps the 'you stopped this turn' reading")

    def test_a_typed_prompt_before_the_notice_decides_the_seam(self):
        # the FIRST user-role event after the marker is the seam's answer: the user typed → a user stop,
        # even if a later restart notice appears further down the thread
        evs = self._events("[romp] The romp kernel restarted and cut this session's in-flight turn; …",
                           typed_first=True)
        km._stamp_interrupt_causes(evs)
        self.assertNotIn("interruptCause", evs[0])

    def test_settle_reply_and_thinking_between_are_skipped(self):
        # the null settle-reply (assistant) and thinking sit between the marker and the notice — the scan
        # must reach past them to the first user-role event (the nimbus shape, 2026-07-09 16:55)
        evs = self._events("[romp] The romp kernel restarted and cut this session's in-flight turn; …")
        self.assertEqual(evs[1].get("kind"), "assistant")
        km._stamp_interrupt_causes(evs)
        self.assertEqual(evs[0].get("interruptCause"), "restart")


class BuildSessionWiring(unittest.TestCase):
    """build_session is too dependency-heavy to run here (live backends) — source pins, matching the
    established InterruptMarker pin style in test_kernel_interrupt.py."""

    def test_the_settle_flag_rides_the_assistant_event(self):
        import inspect
        src = inspect.getsource(km.build_session)
        self.assertIn("if _interrupt_settle(events, txt):", src)
        self.assertIn('ev["interruptSettle"] = True', src)

    def test_causes_are_stamped_after_hydration(self):
        import inspect
        src = inspect.getsource(km.build_session)
        self.assertIn("_stamp_interrupt_causes(events)", src)


if __name__ == "__main__":
    unittest.main()
