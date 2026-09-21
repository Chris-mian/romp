"""A parked tool-permission ask keeps its needs-you state while the CLI's stream carries on and while texts are fed
(the user's report of 2026-09-15: a session blocked on an Allow prompt showed neither the tab's dashed ring nor a card under
Blocked, while the picker stayed up). The one detector for a live permission is romp's own SDK callback: _can_use_tool marks "permission" in
states/<sid>.jsonl and stores the ask (_pending_ask); a running session's snapshot, while an ask is parked, reads its state
from that log's LAST line, and the tab ring, the card floor and the placeholder card all read the live state through
_NEEDS_INPUT_STATES. SdkBackend._forward re-asserted "working" on ANY streamed work atom whenever _cli_working was False,
and the permission mark sets it False, so a parallel tool's result (a user atom carrying a tool_result), a subagent's stream
or an assistant chunk landing while the ask stood appended "working" after "permission": the picker stayed (the ask was
untouched) and every needs-you surface went dark. The re-assert yields while the backend holds a pending ask for the
session. Round two of PR 1739 found the second door: the turn FEEDER marked "working" at its pop with no parked-ask term, so a
text landing in a session standing on a prompt (the composer's message, a peer's postal message, a nudge, a scheduled prompt)
put the readers out the same way. One gate now, SdkSession._mark_producing, the module's only writer of "working": the feeder,
the stream and the ask sites' settle all take it; the text still feeds, only the state mark yields. Synthetic only."""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
_XDG = tempfile.mkdtemp()
os.environ["XDG_STATE_HOME"] = _XDG   # hermetic state BEFORE the load: the module resolves its root at import
os.environ.pop("ROMP_STATE_DIR", None)
os.makedirs(os.path.join(_XDG, "romp"), exist_ok=True)
open(os.path.join(_XDG, "romp", "session-hosts"), "w").write("off\n")   # a minted state root pins the per-session hosts off
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
    root = tempfile.mkdtemp()
    open(os.path.join(root, "session-hosts"), "w").write("off\n")   # the backend's own state root too
    return sb.SdkBackend(root, "/bin/true", lambda *a, **k: None)


def _producing(s):
    """What a writer of "working" does: the one gate at the head, the bare mark at the base (the new name reached through
    getattr so the base run executes the old behaviour and reads red)."""
    fn = getattr(s, "_mark_producing", None)
    return fn() if fn else s._mark("working")


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


def _working_census(src):
    """Every ast.Constant "working" in `src` as (enclosing def or <module>, the holding node's kind), sorted with counts."""
    import ast
    tree, found = ast.parse(src), []
    def walk(node, stack):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                walk(child, stack + [child.name]); continue
            if isinstance(child, ast.Constant) and child.value == "working":
                found.append((stack[-1] if stack else "<module>", type(node).__name__))
            walk(child, stack)
    walk(tree, [])
    return sorted(((k, found.count(k)) for k in set(found)))


def _callers_of_the_gate(src):
    import ast
    tree, callers = ast.parse(src), []
    def walk(node, stack):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                walk(child, stack + [child.name]); continue
            if isinstance(child, ast.Call):
                f = child.func
                if (f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)) == "_mark_producing":
                    callers.append(stack[-1] if stack else "<module>")
            walk(child, stack)
    walk(tree, [])
    return sorted(set(callers))


# the holders of the constant "working" in kernel/sdk_backend.py, by def and by the node that holds it (a count each): two
# state tuples at module level, _mark's comparison, snapshot's conditional and tuple, drive_idle_queue's and _live_row's
# tuples, and the gate's call, the module's ONE writer
WORKING_HOLDERS = sorted([(("<module>", "Tuple"), 2), (("_live_row", "Tuple"), 1), (("_mark", "Compare"), 1),
                          (("_mark_producing", "Call"), 1), (("drive_idle_queue", "Tuple"), 1), (("snapshot", "IfExp"), 1),
                          (("snapshot", "Tuple"), 1)])


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
        # the shape the user's record showed (2026-09-15): ONE tool_use, no tool_result, the log alternating permission and
        # working three times in thirteen seconds: the re-asserting atom was an assistant chunk or a subagent's stream
        be = _backend(); s = _session(be)
        s._mark("working"); s._mark("permission")
        be._pending_ask[SID] = {"kind": "single", "header": "Permission", "permission": True}
        be._forward(s, AssistantMessage("aaaaaaaa-0000-0000-0000-000000000002", [TextBlock("meanwhile, a chunk")]))
        self.assertEqual(_states(be, SID)[-1], "permission", "the parked ask's state stands: %r" % _states(be, SID))
        self.assertFalse(s._cli_working)
        self.assertEqual(_states(be, SID).count("working"), 1, "no second working mark was appended: %r" % _states(be, SID))

    def test_a_text_fed_while_a_permission_is_parked_leaves_the_log_at_permission(self):
        # the second door (round two): the feeder's pop marks working with what a writer of working does; under a standing
        # prompt the composer's message, a postal message, a nudge or a scheduled prompt all land here. The text still feeds.
        be = _backend(); s = _session(be)
        s._mark("working"); s._mark("permission")
        be._pending_ask[SID] = {"kind": "single", "header": "Permission", "permission": True}
        _producing(s)                                        # the feeder's mark at its pop
        self.assertEqual(_states(be, SID), ["working", "permission"], "the fed text left the prompt's state alone")
        self.assertFalse(s._cli_working)
        be._clear_ask(s)                                     # the answer: the ask site's settle takes the same gate
        _producing(s)
        self.assertEqual(_states(be, SID)[-1], "working", "no ask parked any more: the gate marks")
        self.assertTrue(s._cli_working)

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

    def test_the_one_gate_yields_to_a_parked_ask_and_every_writer_of_working_takes_it(self):
        self.assertIn('    def _mark_producing(self) -> None:', BSRC, "the gate exists")
        self.assertIn('        if self.backend._pending_ask.get(self.sid) is not None:\n            return\n        self._mark("working")', BSRC,
                      "the gate yields while the backend holds a pending ask for the session")
        self.assertIn('append_state(self.backend.state_dir, self.sid, state)', BSRC, "the mark writes the log the snapshot reads")
        self.assertEqual(_callers_of_the_gate(BSRC), ["_approve_plan", "_ask_user", "_can_use_tool", "_forward", "inputs"],
                         "the five doors take the gate: the feeder's pop, the stream's re-assert, the three ask sites' settle")

    def test_every_constant_working_in_the_module_has_a_named_holder_and_the_gate_is_the_only_writer_shape(self):
        # EVERY ast.Constant whose value is "working", mapped to its enclosing def and the node that holds it: the readers by
        # their shapes (tuples of states, a comparison, a conditional), and the gate as the ONLY call-argument holder. A new
        # holder of the constant anywhere in the module, of any shape, changes this multiset and fails here; a reader added
        # later is registered here on purpose.
        self.assertEqual(_working_census(BSRC), WORKING_HOLDERS, "the holders of the working constant, by def and shape")
        write_shapes = {k for (k, n) in WORKING_HOLDERS if k[1] in ("Call", "keyword", "Assign", "AnnAssign", "Return")}
        self.assertEqual(write_shapes, {("_mark_producing", "Call")}, "one write-shaped holder: the gate")

    def test_the_census_catches_the_four_shapes_of_a_sixth_writer(self):
        # proven, not promised: a copy of the module with a sixth writer spliced in, in each shape the round-two read tried,
        # changes the census (a literal in a new method, a VARIABLE holding the string, the state as a KEYWORD, a wrapper
        # taking the string, and a module-level function)
        anchor = "    def _mark(self, state: str) -> None:"
        self.assertEqual(BSRC.count(anchor), 1)
        mutants = {
            "a literal in a new method": '    def _sixth_door(self):\n        self._mark("working")\n\n',
            "a variable holding the string": '    def _sixth_door(self):\n        st = "working"\n        self._mark(st)\n\n',
            "the state as a keyword": '    def _sixth_door(self):\n        append_state(self.backend.state_dir, self.sid, state="working")\n\n',
            "a wrapper taking the string": '    def _mark_busy(self, s):\n        self._mark(s)\n\n    def _sixth_door(self):\n        self._mark_busy("working")\n\n',
        }
        for label, ins in mutants.items():
            self.assertNotEqual(_working_census(BSRC.replace(anchor, ins + anchor, 1)), WORKING_HOLDERS, "caught: " + label)
        self.assertNotEqual(_working_census(BSRC + '\n\ndef _module_door(sess):\n    sess._mark("working")\n'), WORKING_HOLDERS,
                            "caught: a module-level function writing the literal")

    def test_the_real_feeder_leaves_a_parked_asks_state_alone_and_feeds_the_text(self):
        # the real inputs() generator under the real _amain with a stub SDK client, the real ask coroutines and the real
        # forward, in its own process (the stub module must not sit in this process's sys.modules): a permission parked,
        # the composer's text fed, the log unchanged; the stream likewise; the answer settles with one working line; the
        # control pop marks working with nothing parked; a picker the same way. Red at the base on feeder_left_permission.
        drive = os.path.join(HERE, "permission_ask_feeder_drive.py")
        p = subprocess.run([sys.executable, drive, os.path.dirname(HERE)], capture_output=True, text=True, timeout=120)
        line = next((l for l in p.stdout.splitlines() if l.startswith("CHECKS:")), None)
        self.assertIsNotNone(line, "the drive reported (stderr tail: %s)" % p.stderr[-1500:])
        checks = json.loads(line[len("CHECKS:"):])
        failed = {k: v for k, v in checks.items() if not v[0]}
        self.assertEqual(failed, {}, "every check of the real feeder drive holds")
        self.assertEqual(sorted(checks), sorted(["parked_marks_permission", "text_fed", "feeder_left_permission", "ask_still_parked",
                                                 "stream_left_permission", "answer_delivered", "settle_marks_working_once", "ask_cleared",
                                                 "control_pop_marks_working", "picker_text_fed_state_stands", "picker_settle_marks_working"]))

if __name__ == "__main__":
    unittest.main()
