"""LIVE compaction indicator in the chat (the user 2026-07-06): while a session compacts, build_session emits a
{kind:"compacting"} event so the client can render an animated inline element in the transcript flow — appended
BEFORE the {kind:"queued"} bubble so a message sent mid-compaction stacks BELOW it instead of clobbering it. It
rides the corroborated `_compacting` signal (same one the chip/timeline use), and vanishes when compaction ends,
where the transcript's {kind:"compact"} boundary divider takes over. Source pins on build_session."""
import inspect
import os
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()


class CompactingEvent(unittest.TestCase):
    def setUp(self):
        self.src = inspect.getsource(km.build_session)

    def test_compacting_signal_is_hoisted_from_the_busy_check(self):
        # the corroborated compacting signal is computed once and reused (not the raw tmux state)
        self.assertIn(
            'compacting_now = _compacting(sid, (tm0 or {}).get("state", ""), parsed, now, (tm0 or {}).get("since"))',
            self.src)
        self.assertIn('busy = _session_working(parsed["turns"]) or compacting_now', self.src)

    def test_a_compacting_event_is_emitted_while_compacting(self):
        self.assertIn('if compacting_now:', self.src)
        self.assertIn('events.append({"kind": "compacting"})', self.src)

    def test_the_compacting_event_precedes_the_queued_bubble(self):
        # ordering is the whole point: the animated element sits ABOVE any provisional/queued message so a
        # message sent mid-compaction never clobbers it.
        i_compacting = self.src.index('events.append({"kind": "compacting"})')
        i_queued = self.src.index('events.append({"kind": "queued"')
        self.assertGreater(i_compacting, 0)
        self.assertGreater(i_queued, i_compacting,
                           "the queued bubble must be appended AFTER the compacting element")


if __name__ == "__main__":
    unittest.main()
