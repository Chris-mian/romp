#!/usr/bin/env python3
"""SdkBackend (bin/romp_sdk_backend.py) — the non-tmux session backend.

Two layers:
  * Pure translation logic (AskUserQuestion <-> the existing askLive picker shape,
    state/registry files) is tested WITHOUT the SDK, so it runs in CI.
  * The async runner + the can_use_tool round-trip is tested with a FAKE
    ClaudeSDKClient (monkeypatched in), skipped where claude_agent_sdk is absent.
    This exercises the headline path: a user turn -> the model calls
    AskUserQuestion -> it surfaces as an askLive picker -> the UI answers ->
    PermissionResultAllow(updated_input={questions, answers}) goes back.
"""
import os
import time
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
sb = SourceFileLoader("romp_sdk_backend", os.path.join(BIN, "romp_sdk_backend.py")).load_module()


class PureTranslation(unittest.TestCase):
    def test_single_question_to_live(self):
        q = {"question": "Pick one", "header": "H", "multiSelect": False,
             "options": [{"label": "A", "description": "aa"}, {"label": "B", "description": "bb"}]}
        ask = sb.ask_question_to_live(q, 0, 1)
        self.assertEqual(ask["kind"], "single")
        self.assertEqual(ask["header"], "H")
        self.assertFalse(ask["multiSelect"])
        self.assertEqual([o["n"] for o in ask["options"]], [1, 2])
        self.assertEqual(ask["options"][0]["label"], "A")
        self.assertEqual(ask["options"][0]["desc"], "aa")
        self.assertFalse(ask["options"][0]["selected"])
        self.assertNotIn("progress", ask)        # single question -> no "n of m"

    def test_multi_question_marks_checked_and_progress(self):
        q = {"question": "Pick many", "header": "H", "multiSelect": True,
             "options": [{"label": "A"}, {"label": "B"}, {"label": "C"}]}
        ask = sb.ask_question_to_live(q, 1, 3, selected={2})
        self.assertEqual(ask["kind"], "multi")
        self.assertTrue(ask["options"][1]["checked"])      # option 2 toggled on
        self.assertFalse(ask["options"][0]["checked"])
        self.assertEqual(ask["progress"], {"i": 2, "n": 3})

    def test_preview_passthrough(self):
        q = {"question": "q", "header": "h", "multiSelect": False,
             "options": [{"label": "A", "preview": "<b>mock</b>"}]}
        ask = sb.ask_question_to_live(q, 0, 1)
        self.assertEqual(ask["options"][0]["preview"], "<b>mock</b>")

    def test_label_for_target(self):
        q = {"options": [{"label": "cats"}, {"label": "dogs"}]}
        self.assertEqual(sb.label_for_target(q, 1), "cats")
        self.assertEqual(sb.label_for_target(q, "2"), "dogs")
        self.assertEqual(sb.label_for_target(q, 9), "9")        # out of range -> verbatim
        self.assertEqual(sb.label_for_target(q, "custom text"), "custom text")

    def test_build_answers(self):
        qs = [{"question": "Q1"}, {"question": "Q2"}, {"question": "Q3"}]
        ans = sb.build_answers(qs, {0: "a", 2: ["x", "y"]})
        self.assertEqual(ans, {"Q1": "a", "Q3": ["x", "y"]})    # Q2 unanswered -> omitted

    def test_permission_to_live(self):
        ask = sb.permission_to_live("Bash", {"command": "rm -rf /tmp/x"})
        self.assertTrue(ask["permission"])
        self.assertEqual([o["label"] for o in ask["options"]], ["Allow", "Deny"])
        self.assertIn("rm -rf", ask["question"])

    def test_pretty_model(self):
        self.assertEqual(sb.pretty_model("claude-opus-4-8"), "Opus 4.8")
        self.assertEqual(sb.pretty_model("claude-sonnet-4-6"), "Sonnet 4.6")
        self.assertEqual(sb.pretty_model("claude-haiku-4-5-20251001"), "Haiku 4.5")  # trailing date dropped
        self.assertEqual(sb.pretty_model("claude-fable-5"), "Fable 5")               # no minor version
        self.assertEqual(sb.pretty_model(""), "")
        self.assertEqual(sb.pretty_model("some-custom-id"), "some-custom-id")        # unrecognised → verbatim

    def test_identity_color_stable_and_in_palette(self):
        bg, fg = sb.pick_identity_color("11111111-2222-3333-4444-555555555555")
        self.assertIn(bg, sb._PALETTE)
        self.assertIn(fg, sb._FG)
        self.assertEqual(sb.pick_identity_color("11111111-2222-3333-4444-555555555555"), (bg, fg))  # stable per sid


# --- live tail (in-memory stream → atoms, ahead of disk). Pure: fakes match by type-name, no SDK. ---
class _TextBlock:
    def __init__(self, text): self.text = text
class _ToolUseBlock:
    def __init__(self, id, name, inp): self.id, self.name, self.input = id, name, inp
class _AssistantMessage:
    def __init__(self, content, model="claude-x", uuid="a1", stop_reason="end_turn"):
        self.content, self.model, self.uuid, self.stop_reason = content, model, uuid, stop_reason
class _UserMessage:
    def __init__(self, content, uuid="u1"): self.content, self.uuid = content, uuid
class _ResultMessage:
    uuid = "r1"
# rename so type(...).__name__ matches what msg_to_atom checks
_TextBlock.__name__ = "TextBlock"; _ToolUseBlock.__name__ = "ToolUseBlock"
_AssistantMessage.__name__ = "AssistantMessage"; _UserMessage.__name__ = "UserMessage"
_ResultMessage.__name__ = "ResultMessage"


class LiveTail(unittest.TestCase):
    def test_msg_to_atom_assistant(self):
        m = _AssistantMessage([_TextBlock("hi"), _ToolUseBlock("t1", "Bash", {"command": "ls"})])
        a = sb.msg_to_atom(m, "sid9", "fsidA", 100)
        self.assertEqual(a["type"], "assistant")
        self.assertEqual(a["uuid"], "a1")
        self.assertEqual(a["session_id"], "sid9")
        self.assertEqual(a["t"], 100)
        self.assertEqual(a["fsid"], "fsidA")
        self.assertEqual(a["message"]["content"],
                         [{"type": "text", "text": "hi"},
                          {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls"}}])

    def test_msg_to_atom_user_and_nonrenderable(self):
        a = sb.msg_to_atom(_UserMessage([_TextBlock("hello")]), "s", "f", 5)
        self.assertEqual(a["type"], "user")
        self.assertEqual(a["message"]["content"], [{"type": "text", "text": "hello"}])
        self.assertIsNone(sb.msg_to_atom(_ResultMessage(), "s", "f", 5))   # result has no renderable content
        self.assertIsNone(sb.msg_to_atom(_AssistantMessage([]), "s", "f", 5))  # empty content → None

    def test_live_store_and_prune(self):
        be = sb.SdkBackend(tempfile.mkdtemp(), "/bin/true", lambda *a, **k: None)
        be._live["s"] = {"a1": {"uuid": "a1", "t": 2}, "echo:x": {"uuid": "echo:x", "t": 1, "_echo_text": "hi"}}
        self.assertEqual([a["uuid"] for a in be.live_atoms("s")], ["echo:x", "a1"])   # sorted by t
        be.prune_live("s", {"a1"}, {"hi"})     # a1 now on disk; echo text "hi" now on disk
        self.assertEqual(be.live_atoms("s"), [])

    def test_send_adds_optimistic_echo(self):
        be = sb.SdkBackend(tempfile.mkdtemp(), "/bin/true", lambda *a, **k: None)
        be._ensure = lambda sid: type("S", (), {"enqueue": lambda self, t: None})()   # no real session thread
        self.assertTrue(be.send("s", "type this"))
        echoes = [a for a in be.live_atoms("s") if a.get("_echo_text") == "type this"]
        self.assertEqual(len(echoes), 1)
        self.assertEqual(echoes[0]["type"], "user")
        self.assertEqual(echoes[0]["message"]["content"], [{"type": "text", "text": "type this"}])


class StateAndRegistryFiles(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def test_state_log_roundtrip(self):
        sb.append_state(self.d, "sid1", "working", t=100)
        sb.append_state(self.d, "sid1", "waiting", t=200)
        self.assertEqual(sb.last_state(self.d, "sid1"), {"t": 200, "state": "waiting"})
        # matches the kernel's format: one JSON object per line
        p = os.path.join(self.d, "states", "sid1.jsonl")
        with open(p) as f:
            self.assertEqual(len(f.read().strip().splitlines()), 2)

    def test_names_file_format(self):
        sb.write_name(self.d, "sid2", "alpha", "/work/dir", "#fff", "black")
        with open(os.path.join(self.d, "names", "sid2")) as f:
            line = f.read().rstrip("\n")
        self.assertEqual(line.split("\t"), ["alpha", "/work/dir", "#fff", "black"])

    def test_registry_roundtrip(self):
        sb.write_reg(self.d, "sid3", {"sid": "sid3", "name": "n", "alive": True})
        self.assertEqual(sb.read_reg(self.d, "sid3")["name"], "n")
        sb.write_reg(self.d, "sid4", {"sid": "sid4", "alive": False})
        regs = {r["sid"]: r for r in sb.list_regs(self.d)}
        self.assertEqual(set(regs), {"sid3", "sid4"})
        self.assertTrue(regs["sid3"]["alive"])

    def test_spawn_assigns_identity_color(self):
        be = sb.SdkBackend(self.d, "/bin/true", lambda *a, **k: None)
        sid = be.spawn("c", self.d)
        with open(os.path.join(self.d, "names", sid)) as f:
            parts = f.read().rstrip("\n").split("\t")
        self.assertTrue(parts[2].startswith("#"), "SDK session gets an identity colour like tmux ones")

    def _last_awaiting(self, sid):
        import json as _j
        rec = None
        with open(os.path.join(self.d, "states", sid + ".jsonl")) as f:
            for line in f:
                o = _j.loads(line)
                if "awaiting" in o:
                    rec = o
        return rec

    def test_awaiting_overlay_shape(self):
        # bugz's reader scans for the latest line with an "awaiting" key (interleaved with state records)
        sb.append_state(self.d, "a1", "working")
        sb.append_awaiting(self.d, "a1", True, "2 background task(s) running")
        rec = self._last_awaiting("a1")
        self.assertEqual(rec["awaiting"], True)
        self.assertEqual(rec["why"], "2 background task(s) running")
        sb.append_awaiting(self.d, "a1", False)
        rec = self._last_awaiting("a1")
        self.assertEqual(rec["awaiting"], False)
        self.assertNotIn("why", rec)               # false clears, no why

    def test_stop_hook_emits_from_background_tasks(self):
        import asyncio
        be = sb.SdkBackend(self.d, "/bin/true", lambda *a, **k: None)
        sess = sb.SdkSession(be, {"sid": "h1", "name": "n", "cwd": self.d, "mode": "acceptEdits"})
        asyncio.run(sess._stop_hook({"background_tasks": [{"id": "t1"}, {"id": "t2"}]}, None, None))
        self.assertEqual(self._last_awaiting("h1"), {"t": self._last_awaiting("h1")["t"],
                                                     "awaiting": True, "why": "2 background task(s) running"})
        asyncio.run(sess._stop_hook({"background_tasks": []}, None, None))   # tasks finished
        self.assertEqual(self._last_awaiting("h1")["awaiting"], False)


class SetModelModePure(unittest.TestCase):
    """set_model / set_mode persist to the registry even with no live session thread (CI-safe,
    no SDK). The live control-channel apply is covered by AskRoundTrip.test_set_model_and_mode_apply_live."""
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.be = sb.SdkBackend(self.d, "/bin/true", lambda *a, **k: None)

    def test_set_model_persists_to_registry(self):
        sid = self.be.spawn("m", self.d)                  # writes reg; no session thread until send()
        self.assertTrue(self.be.set_model(sid, "opus"))
        self.assertEqual(sb.read_reg(self.d, sid)["model"], "opus")
        self.assertFalse(self.be.set_model("no-such-sid", "opus"))

    def test_set_mode_persists_to_registry(self):
        sid = self.be.spawn("m", self.d)
        self.assertTrue(self.be.set_mode(sid, "plan"))
        self.assertEqual(sb.read_reg(self.d, sid)["mode"], "plan")

    def test_chosen_model_read_from_reg_on_construct(self):
        sess = sb.SdkSession(self.be, {"sid": "x", "name": "n", "cwd": self.d, "model": "sonnet"})
        self.assertEqual(sess.chosen_model, "sonnet")
        plain = sb.SdkSession(self.be, {"sid": "y", "name": "n", "cwd": self.d})
        self.assertEqual(plain.chosen_model, "")          # default: no model flag → CLI default

    def test_spawn_sets_default_effort_and_set_effort_validates(self):
        sid = self.be.spawn("e", self.d)
        self.assertEqual(sb.read_reg(self.d, sid)["effort"], sb.DEFAULT_EFFORT)   # explicit default so the picker shows a true value
        self.assertTrue(self.be.set_effort(sid, "low"))
        self.assertEqual(sb.read_reg(self.d, sid)["effort"], "low")
        self.assertFalse(self.be.set_effort(sid, "ultra"))   # not a real level → rejected
        self.assertEqual(sb.read_reg(self.d, sid)["effort"], "low")   # reg unchanged after a bad value
        self.assertFalse(self.be.set_effort("no-such-sid", "low"))

    def test_effort_read_from_reg_on_construct(self):
        s1 = sb.SdkSession(self.be, {"sid": "a", "name": "n", "cwd": self.d, "effort": "max"})
        self.assertEqual(s1.effort, "max")
        s2 = sb.SdkSession(self.be, {"sid": "b", "name": "n", "cwd": self.d})
        self.assertEqual(s2.effort, sb.DEFAULT_EFFORT)   # no reg effort → default (so the picker is never empty)


# --- Runner + can_use_tool bridge (needs the SDK message classes) ---
try:
    import claude_agent_sdk as _sdk
    _HAVE_SDK = True
except Exception:
    _HAVE_SDK = False


@unittest.skipUnless(_HAVE_SDK, "claude_agent_sdk not installed")
class AskRoundTrip(unittest.TestCase):
    """Drive a full turn through a fake client and assert the AskUserQuestion
    answer round-trips as PermissionResultAllow(updated_input)."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self._orig_client = _sdk.ClaudeSDKClient

        QUESTION = {"questions": [{
            "question": "Cats or dogs?", "header": "Pet", "multiSelect": False,
            "options": [{"label": "cats", "description": "c"}, {"label": "dogs", "description": "d"}],
        }]}

        class _Ctx:
            title = display_name = decision_reason = None

        import asyncio as _aio

        class FakeClient:
            """Models the real split: query(iterable) WRITES each turn (blocking until the
            iterable ends), receive_messages() yields outputs independently. So this only
            works if the backend runs feeder + receiver CONCURRENTLY — if it awaited query()
            first (the bug the live smoke caught), the never-ending input generator would
            starve the receive loop and this test would hang."""
            instances = []

            def __init__(self, options=None, transport=None):
                self.options = options
                self.captured = None
                self.interrupted = False
                self.model_calls = []        # records set_model() over the control channel
                self.mode_calls = []         # records set_permission_mode()
                self._turnq = _aio.Queue()
                FakeClient.instances.append(self)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def query(self, prompt, session_id="default"):
                async for turn in prompt:                # writes each turn (blocks like the real one)
                    await self._turnq.put(turn)

            async def interrupt(self):
                self.interrupted = True

            async def set_model(self, model=None):
                self.model_calls.append(model)

            async def set_permission_mode(self, mode):
                self.mode_calls.append(mode)

            async def receive_messages(self):
                yield _sdk.SystemMessage("init", {
                    "model": "claude-x", "permissionMode": "acceptEdits",
                    "session_id": (self.options.session_id or "fsid")})
                while True:
                    await self._turnq.get()              # next enqueued user turn
                    allow = await self.options.can_use_tool("AskUserQuestion", QUESTION, _Ctx())
                    self.captured = allow
                    yield _sdk.AssistantMessage(content=[_sdk.TextBlock("ok")], model="claude-x")
                    yield _sdk.ResultMessage("success", 1, 1, False, 1, "fsid")

        _sdk.ClaudeSDKClient = FakeClient
        self.Fake = FakeClient
        FakeClient.instances = []

        self.notes = []

        def notify(app, msg):
            self.notes.append((app, msg))
            if msg.get("type") == "askLive":            # the UI auto-answers option 1 (cats)
                self.backend.on_ask(msg["id"], "answer", 1)

        self.backend = sb.SdkBackend(self.d, "/bin/true", notify)

    def tearDown(self):
        _sdk.ClaudeSDKClient = self._orig_client

    def _wait(self, pred, timeout=6.0):
        end = time.time() + timeout
        while time.time() < end:
            if pred():
                return True
            time.sleep(0.02)
        return False

    def test_spawn_then_ask_round_trip(self):
        sid = self.backend.spawn("alpha", self.d)
        # spawn registers identity + registry + initial state, all on disk
        self.assertTrue(sb.read_reg(self.d, sid)["alive"])
        self.assertTrue(os.path.exists(os.path.join(self.d, "names", sid)))
        self.assertIn(sid, self.backend.live_sessions())

        self.assertTrue(self.backend.send(sid, "hello"))
        self.assertTrue(self._wait(lambda: self.Fake.instances and self.Fake.instances[0].captured),
                        "can_use_tool never returned an answer")

        allow = self.Fake.instances[0].captured
        self.assertEqual(allow.behavior, "allow")
        self.assertEqual(allow.updated_input["answers"], {"Cats or dogs?": "cats"})
        self.assertEqual(allow.updated_input["questions"], [{
            "question": "Cats or dogs?", "header": "Pet", "multiSelect": False,
            "options": [{"label": "cats", "description": "c"}, {"label": "dogs", "description": "d"}]}])

        # an askLive went out and was later cleared
        kinds = [m.get("type") for _app, m in self.notes]
        self.assertIn("askLive", kinds)
        self.assertIn("askLiveClear", kinds)

        # state settled working -> waiting after the result
        self.assertTrue(self._wait(
            lambda: sb.last_state(self.d, sid).get("state") == "waiting"))

    def test_connect_publishes_model_without_a_turn(self):
        """Eager-connect (used at createSession) brings up the session WITHOUT a user turn, so the model
        publishes from the init message right away — like a tmux session shows it on launch."""
        sid = self.backend.spawn("eager", self.d)
        self.assertEqual(self.backend.live_sessions()[sid]["model"], "", "no model before connect")
        self.assertTrue(self.backend.connect(sid))
        self.assertTrue(self._wait(lambda: self.backend.live_sessions().get(sid, {}).get("model")),
                        "eager-connect publishes the model from init, with no user turn sent")
        self.assertFalse(self.backend.connect("no-such-sid"))

    def test_kill_marks_dead(self):
        sid = self.backend.spawn("beta", self.d)
        self.backend.send(sid, "hi")
        self._wait(lambda: self.Fake.instances and self.Fake.instances[0].captured)
        self.assertTrue(self.backend.kill(sid))
        self.assertFalse(sb.read_reg(self.d, sid)["alive"])
        self.assertNotIn(sid, self.backend.live_sessions())

    def test_set_model_and_mode_apply_live(self):
        """The model/mode pickers go over the SDK CONTROL channel (set_model / set_permission_mode),
        not a /model or /effort slash injection into the prompt stream (which the SDK ignores)."""
        sid = self.backend.spawn("ctrl", self.d)
        self.assertTrue(self.backend.send(sid, "hi"))
        self.assertTrue(self._wait(lambda: self.Fake.instances and self.Fake.instances[0].captured),
                        "session never connected")
        c = self.Fake.instances[0]
        self.backend.set_model(sid, "opus")
        self.assertTrue(self._wait(lambda: "opus" in c.model_calls),
                        "model alias not sent via set_model control request")
        self.backend.set_model(sid, "default")
        self.assertTrue(self._wait(lambda: None in c.model_calls),
                        "'default' must reset via set_model(None)")
        self.backend.set_mode(sid, "plan")
        self.assertTrue(self._wait(lambda: "plan" in c.mode_calls),
                        "mode not sent via set_permission_mode control request")
        # persisted so a reconnect keeps the choice; _options carries chosen_model
        self.assertEqual(sb.read_reg(self.d, sid)["model"], "default")
        self.assertEqual(sb.read_reg(self.d, sid)["mode"], "plan")
        sess = self.backend.sessions[sid]
        sess.chosen_model = "sonnet"
        opts = self.backend._options(sess, _sdk.ClaudeAgentOptions)
        self.assertEqual(opts.model, "sonnet")

    def test_effort_change_reconnects_with_new_flag(self):
        """effort is a connect-time CLI flag, so changing it RECONNECTS the client (a 2nd ClaudeSDKClient)
        with the new --effort, resuming the same conversation — not a /effort slash the SDK ignores."""
        sid = self.backend.spawn("eff", self.d)
        self.assertTrue(self.backend.send(sid, "hi"))
        self.assertTrue(self._wait(lambda: self.Fake.instances and self.Fake.instances[0].captured),
                        "first connection never completed a turn")
        self.assertEqual(self.Fake.instances[0].options.effort, sb.DEFAULT_EFFORT)   # spawned at the default
        self.assertTrue(self.backend.set_effort(sid, "low"))
        self.assertTrue(self._wait(lambda: len(self.Fake.instances) >= 2),
                        "effort change did not reconnect the client")
        c2 = self.Fake.instances[1]
        self.assertEqual(c2.options.effort, "low")          # reconnected with the new flag
        self.assertEqual(c2.options.resume, sid)             # resume continues the SAME conversation, not a fresh session
        self.assertEqual(sb.read_reg(self.d, sid)["effort"], "low")
        self.backend.kill(sid)


if __name__ == "__main__":
    unittest.main()
