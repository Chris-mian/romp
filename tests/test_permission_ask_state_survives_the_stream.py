"""A parked tool-permission ask keeps its needs-you state while the CLI's stream carries on (the user's report of
2026-09-16: a session blocked on an Allow prompt showed neither the tab's dashed ring nor a card under Blocked, while the
picker stayed up). The one detector for a live permission is romp's own SDK callback: _can_use_tool marks "permission" in
states/<sid>.jsonl and stores the ask (_pending_ask); a running session's snapshot, while an ask is parked, reads its state
from that log's LAST line, and the tab ring, the card floor and the placeholder card all read the live state through
_NEEDS_INPUT_STATES. SdkBackend._forward re-asserted "working" on ANY streamed work atom whenever _cli_working was False,
and the permission mark sets it False, so a parallel tool's result (a user atom carrying a tool_result), a subagent's stream
or an assistant chunk landing while the ask stood appended "working" after "permission": the picker stayed (the ask was
untouched) and every needs-you surface went dark. The re-assert yields while the backend holds a pending ask for the
session; the ask site's own settle re-marks "working" after the answer, as before. Synthetic only (placeholder ids)."""
import json
import os
import re
import tempfile
import unittest

from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()   # hermetic state BEFORE the load: the module resolves its root at import
os.environ.pop("ROMP_STATE_DIR", None)
sb = load_source("romp_sdk_backend_permask", os.path.join(BIN, "romp_sdk_backend.py"))
KSRC = open(os.path.join(BIN, "romp-kernel")).read()
BSRC = open(os.path.join(BIN, "romp_sdk_backend.py")).read()

SID = "11111111-2222-3333-4444-777777777701"


# msg_to_atom and _block_to_dict match on the CLASS NAMES of the SDK's message and block types, so these duck types travel
# the real path: a user message carrying a tool result, an assistant message carrying a text chunk
class ToolResultBlock:
    def __init__(self, tool_use_id, content):
        self.tool_use_id, self.content, self.is_error = tool_use_id, content, False


class TextBlock:
    def __init__(self, text):
        self.text = text


class UserMessage:
    def __init__(self, uuid, blocks):
        self.uuid, self.content = uuid, blocks
        self.parent_tool_use_id = None


class AssistantMessage:
    def __init__(self, uuid, blocks):
        self.uuid, self.content, self.model = uuid, blocks, "claude-fable-5-1"
        self.parent_tool_use_id = None


def _backend():
    return sb.SdkBackend(tempfile.mkdtemp(), "/bin/true", lambda *a, **k: None)


def _session(be, sid=SID):
    """The fields _forward and the REAL _mark touch: the mark writes states/<sid>.jsonl under the backend's state dir."""
    s = object.__new__(sb.SdkSession)
    s.backend, s.sid, s.name, s.resume_sid = be, sid, "web", None
    s._skill_tool_ids, s._cli_working = set(), True
    s.inflight, s._first_out_t = 1, None
    s._note_turn_opener = lambda opener, fresh: None
    return s


def _states(be, sid):
    p = os.path.join(be.state_dir, "states", sid + ".jsonl")
    return [json.loads(l)["state"] for l in open(p) if l.strip() and "state" in json.loads(l)]


class ParkedPermissionKeepsItsState(unittest.TestCase):
    def test_a_tool_result_streamed_while_a_permission_is_parked_leaves_the_log_at_permission(self):
        be = _backend(); s = _session(be)
        s._mark("working")                                   # the turn is producing
        s._mark("permission")                                # _can_use_tool: the mark, then the ask is stored and shown
        be._pending_ask[SID] = {"kind": "single", "header": "Permission", "permission": True}
        self.assertFalse(s._cli_working)
        # a PARALLEL tool's result lands on the stream while the Allow prompt stands (the CLI runs the allowed calls
        # of the same assistant message and asks for the one that needs permission)
        be._forward(s, UserMessage("aaaaaaaa-0000-0000-0000-000000000001", [ToolResultBlock("toolu_01", "ok")]))
        self.assertEqual(_states(be, SID)[-1], "permission", "the parked ask's state stands: %r" % _states(be, SID))
        self.assertFalse(s._cli_working, "and the CLI is not read as producing while it waits on the user")
        self.assertIsNotNone(be._pending_ask.get(SID), "the ask itself was never touched by the stream")

    def test_an_assistant_chunk_streamed_while_a_permission_is_parked_leaves_the_log_at_permission(self):
        # the shape the user's record showed (2026-09-16): ONE tool_use, no tool_result, the log alternating permission and
        # working three times in thirteen seconds: the re-asserting atom was an assistant chunk or a subagent's stream
        be = _backend(); s = _session(be)
        s._mark("working"); s._mark("permission")
        be._pending_ask[SID] = {"kind": "single", "header": "Permission", "permission": True}
        be._forward(s, AssistantMessage("aaaaaaaa-0000-0000-0000-000000000002", [TextBlock("meanwhile, a chunk")]))
        self.assertEqual(_states(be, SID)[-1], "permission", "the parked ask's state stands: %r" % _states(be, SID))
        self.assertFalse(s._cli_working)
        self.assertEqual(_states(be, SID).count("working"), 1, "no second working mark was appended: %r" % _states(be, SID))

    def test_once_the_ask_is_answered_the_stream_re_asserts_working_as_before(self):
        be = _backend(); s = _session(be)
        s._mark("working"); s._mark("permission")
        be._pending_ask[SID] = {"kind": "single", "permission": True}
        be._clear_ask(s)                                     # the ask site's finally after the answer; then, in flight, it re-marks
        if s.inflight:
            s._mark("working")
        s._mark("permission"); s._cli_working = False        # a stale mark with NO ask parked is the case the re-assert exists for
        be._pending_ask.pop(SID, None)
        be._forward(s, UserMessage("aaaaaaaa-0000-0000-0000-000000000003", [ToolResultBlock("toolu_02", "ok")]))
        self.assertEqual(_states(be, SID)[-1], "working", "no ask parked: the stream is the authoritative busy signal again")
        self.assertTrue(s._cli_working)

    def test_a_picker_ask_is_kept_the_same_way(self):
        be = _backend(); s = _session(be)
        s._mark("working"); s._mark("picker")
        be._pending_ask[SID] = {"kind": "single", "header": "Question"}
        be._forward(s, AssistantMessage("aaaaaaaa-0000-0000-0000-000000000004", [TextBlock("a chunk")]))
        self.assertEqual(_states(be, SID)[-1], "picker")


class TheNeedsYouReadersShareOneState(unittest.TestCase):
    """Source pins: the tab ring (the chip), a skeleton tab's light status, the card floor and the placeholder card all read the
    live row's state through _NEEDS_INPUT_STATES, the running snapshot reads the log's last line while an ask is parked, and
    the stream's re-assert yields to a parked ask."""

    def test_one_tuple_names_the_two_needs_input_states(self):
        self.assertIn('_NEEDS_INPUT_STATES = ("permission", "picker")', KSRC)

    def test_the_chip_the_light_status_the_floor_and_the_placeholder_read_it(self):
        self.assertEqual(len(re.findall(r'"needsInput" if st in _NEEDS_INPUT_STATES else', KSRC)), 2, "the built chip and the light status")
        self.assertIn("perm_state = tm.get(\"state\") if tm else None\n    if perm_state in _NEEDS_INPUT_STATES:", KSRC, "the card floor")
        self.assertIn("elif perm_state in _NEEDS_INPUT_STATES:", KSRC, "the placeholder card for a session with no floorable goal")

    def test_the_running_snapshot_reads_the_log_while_an_ask_is_parked(self):
        self.assertIn("parked = self.backend._pending_ask.get(self.sid) is not None", BSRC)
        self.assertIn("if self.inflight > 0 and not parked:", BSRC)

    def test_the_streams_working_re_assert_yields_to_a_parked_ask(self):
        self.assertIn('and not sess._cli_working and self._pending_ask.get(sess.sid) is None:\n            sess._mark("working")', BSRC,
                      "the re-assert is gated on no pending ask for the session")
        self.assertIn('append_state(self.backend.state_dir, self.sid, state)', BSRC, "the mark writes the log the snapshot reads")


if __name__ == "__main__":
    unittest.main()
