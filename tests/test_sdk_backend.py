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
import threading
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

    def test_model_label(self):
        # the live (init/assistant-echoed) name always wins once known
        self.assertEqual(sb.model_label("Opus 4.8", "opus"), "Opus 4.8")
        self.assertEqual(sb.model_label("Opus 4.8", ""), "Opus 4.8")
        # before the live name arrives, show a best-effort label from the CHOSEN model so the badge isn't
        # blank on a freshly-created SDK session (the user 2026-06-24)
        self.assertEqual(sb.model_label("", "opus"), "Opus")                 # CLI alias → capitalised
        self.assertEqual(sb.model_label("", "sonnet"), "Sonnet")
        self.assertEqual(sb.model_label("", "claude-opus-4-8"), "Opus 4.8")  # raw id → pretty_model
        # 'default'/unset → blank: the REAL default name fills in from the init message (eager-connect pokes it)
        self.assertEqual(sb.model_label("", "default"), "")
        self.assertEqual(sb.model_label("", ""), "")

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

    def test_dormant_session_reports_waiting_not_stale_inflight(self):
        """False blocked/approval state (the user 2026-06-24): after a kernel restart an alive SDK session's
        thread is gone, but its state log still reads its last in-flight state. A NOT-running session can't be
        mid-turn, so live_sessions must report 'waiting' — else the UI shows it blocked/needs-approval with no
        prompt to resolve (the prompt died with the thread). A running session is unaffected (snapshot path)."""
        be = sb.SdkBackend(self.d, "/bin/true", lambda *a, **k: None)
        sid = be.spawn("reorder_like", self.d)            # reg(alive) + a 'waiting' state; NOT started (no thread)
        for stale in ("working", "permission", "picker", "compacting", "retrying"):
            sb.append_state(self.d, sid, stale)           # ...it went mid-turn, then the kernel restarted
            ls = be.live_sessions()                        # registry-only path (session not running here)
            self.assertEqual(ls[sid]["state"], "waiting",
                             "a dormant session must read 'waiting', not the stale '%s'" % stale)

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


class LiveAskReplay(unittest.TestCase):
    """A blocked SDK session's prompt must REPLAY, not vanish (the user 2026-06-24: blocked-no-prompt). _emit_ask
    STORES the ask (not just a bool) so the kernel's _ask_poll can re-push it to any chat client that connects /
    refocuses / reloads after the ask was raised; _clear_ask removes it on answer/cancel. Before this, the ask
    was a one-shot push and _ask_poll pane-scraped the (pane-less) SDK session, found nothing, and cleared the
    prompt every 1.2s tick."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.backend = sb.SdkBackend(self.d, "/bin/true", lambda app, msg: None)

    def test_emit_stores_ask_for_replay_and_clear_removes(self):
        class _Sess:
            sid = "11111111-2222-3333-4444-555555555555"
        sess = _Sess()
        ask = {"kind": "single", "header": "Pet",
               "options": [{"n": 1, "label": "cats"}, {"n": 2, "label": "dogs"}]}
        self.assertIsNone(self.backend.current_ask(sess.sid))       # nothing pending yet
        self.backend._emit_ask(sess, ask)
        self.assertEqual(self.backend.current_ask(sess.sid), ask)   # stored verbatim → _ask_poll replays it
        self.backend._clear_ask(sess)
        self.assertIsNone(self.backend.current_ask(sess.sid))       # answered/cancelled → gone


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


@unittest.skipUnless(_HAVE_SDK, "claude_agent_sdk not installed")
class ApiRetryState(unittest.TestCase):
    """An api_retry storm (API rate-limit/overload) must surface as a distinct 'retrying' state, not a
    silent 'working', so a stall reads as an API issue (the user 2026-06-23). Cleared on real output."""

    def test_api_retry_shows_retrying_then_clears(self):
        d = tempfile.mkdtemp()
        be = sb.SdkBackend(d, "/bin/true", lambda *a, **k: None)
        sess = sb.SdkSession(be, {"sid": "r1", "name": "n", "cwd": d, "mode": "acceptEdits"})
        sess.inflight = 1                                        # a turn is in flight
        self.assertEqual(sess.snapshot()["state"], "working")
        sess._on_message(_sdk.SystemMessage("api_retry", {}), _sdk.AssistantMessage, _sdk.ResultMessage, _sdk.SystemMessage)
        self.assertTrue(sess.retrying)
        self.assertEqual(sess.snapshot()["state"], "retrying", "api_retry stall reads as 'retrying'")
        sess._on_message(_sdk.AssistantMessage(content=[_sdk.TextBlock("hi")], model="m"),
                         _sdk.AssistantMessage, _sdk.ResultMessage, _sdk.SystemMessage)
        self.assertFalse(sess.retrying)
        self.assertEqual(sess.snapshot()["state"], "working", "real output clears 'retrying'")


@unittest.skipUnless(_HAVE_SDK, "claude_agent_sdk not installed")
class InterruptSettlesStall(unittest.TestCase):
    """Interrupt must drop a session out of 'working' even if the turn never produces a ResultMessage
    (e.g. it's stuck in an API-retry backoff) — the snapshot reads 'working' purely from inflight>0, so a
    user interrupt that the CLI is slow to honour would otherwise leave it 'working' forever."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self._orig = _sdk.ClaudeSDKClient
        import asyncio as _aio

        class StallClient:
            instances = []

            def __init__(self, options=None, transport=None):
                self.options = options
                self.interrupted = False
                self._turnq = _aio.Queue()
                StallClient.instances.append(self)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def query(self, prompt, session_id="default"):
                async for turn in prompt:
                    await self._turnq.put(turn)

            async def interrupt(self):
                self.interrupted = True

            async def receive_messages(self):
                yield _sdk.SystemMessage("init", {"session_id": self.options.session_id or "fsid"})
                await self._turnq.get()              # consume the turn → inflight goes to 1...
                while True:
                    await _aio.sleep(3600)            # ...then STALL forever (never a ResultMessage)

        _sdk.ClaudeSDKClient = StallClient
        self.Fake = StallClient
        StallClient.instances = []
        self.backend = sb.SdkBackend(self.d, "/bin/true", lambda *a, **k: None)

    def tearDown(self):
        _sdk.ClaudeSDKClient = self._orig

    def _wait(self, pred, timeout=6.0):
        end = time.time() + timeout
        while time.time() < end:
            if pred():
                return True
            time.sleep(0.02)
        return False

    def test_interrupt_settles_a_stalled_turn(self):
        sid = self.backend.spawn("stall", self.d)
        self.backend.send(sid, "go")
        self.assertTrue(self._wait(lambda: self.backend.live_sessions().get(sid, {}).get("state") == "working"),
                        "a stalled in-flight turn reads as working")
        self.assertTrue(self.backend.interrupt(sid))
        self.assertTrue(self._wait(lambda: self.Fake.instances and self.Fake.instances[0].interrupted),
                        "client.interrupt() was sent")
        self.assertTrue(self._wait(lambda: self.backend.live_sessions().get(sid, {}).get("state") != "working"),
                        "after interrupt the session is no longer 'working' even with no ResultMessage")


class PendingQueue(unittest.TestCase):
    """The visible pending queue (no SDK / no loop needed) — enqueue holds turns in a list that
    pending_queued exposes, so the kernel can render the 'queued' indicator for SDK sessions."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.be = sb.SdkBackend(self.d, "/bin/true", lambda *a, **k: None)

    def _sess(self, sid="q1"):
        s = sb.SdkSession(self.be, {"sid": sid, "name": "n", "cwd": self.d, "mode": "acceptEdits"})
        self.be.sessions[sid] = s          # register WITHOUT starting the thread (no loop)
        return s

    def test_enqueue_holds_in_pending_oldest_first(self):
        s = self._sess()
        s.enqueue("first"); s.enqueue("second")
        self.assertEqual(s.pending(), ["first", "second"])              # both held, in order
        self.assertEqual(self.be.pending_queued("q1"), ["first", "second"])

    def test_pending_returns_a_copy(self):
        s = self._sess()
        s.enqueue("a")
        snap = s.pending(); snap.append("mutated")
        self.assertEqual(s.pending(), ["a"])                            # internal list untouched

    def test_pending_queued_empty_for_unknown_or_idle(self):
        self.assertEqual(self.be.pending_queued("no-such-sid"), [])     # not an SDK session
        self._sess("q2")
        self.assertEqual(self.be.pending_queued("q2"), [])             # session exists, nothing queued


@unittest.skipUnless(_HAVE_SDK, "claude_agent_sdk not installed")
class PendingQueueLoop(unittest.TestCase):
    """End-to-end gate: a turn enqueued while another is IN FLIGHT stays in pending_queued and is
    NOT fed to the SDK until the in-flight turn ends, then is released in order. This is the fix —
    before it, queued turns were flushed straight into the SDK and were invisible to the chat."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self._orig_client = _sdk.ClaudeSDKClient
        import asyncio as _aio

        class GatedClient:
            instances = []
            received = []                  # turn texts actually fed to the SDK, in order
            release = threading.Event()    # test sets this to let the in-flight turn complete

            def __init__(self, options=None, transport=None):
                self.options = options
                self._turnq = _aio.Queue()
                GatedClient.instances.append(self)

            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False

            async def query(self, prompt, session_id="default"):
                async for turn in prompt:                 # the feeder writes each released turn here
                    await self._turnq.put(turn)

            async def interrupt(self): pass
            async def set_model(self, model=None): pass
            async def set_permission_mode(self, mode): pass

            async def receive_messages(self):
                yield _sdk.SystemMessage("init", {
                    "model": "claude-x", "permissionMode": "acceptEdits",
                    "session_id": (self.options.session_id or "fsid")})
                while True:
                    turn = await self._turnq.get()
                    GatedClient.received.append(turn["message"]["content"][0]["text"])
                    while not GatedClient.release.is_set():
                        await _aio.sleep(0.01)            # hold the turn 'in flight' until released
                    GatedClient.release.clear()
                    yield _sdk.ResultMessage("success", 1, 1, False, 1, "fsid")

        _sdk.ClaudeSDKClient = GatedClient
        self.Gated = GatedClient
        GatedClient.instances = []
        GatedClient.received = []
        GatedClient.release = threading.Event()
        self.backend = sb.SdkBackend(self.d, "/bin/true", lambda *a, **k: None)

    def tearDown(self):
        self.Gated.release.set()                          # unblock any in-flight turn so the thread can exit
        _sdk.ClaudeSDKClient = self._orig_client

    def _wait(self, pred, timeout=6.0):
        end = time.time() + timeout
        while time.time() < end:
            if pred():
                return True
            time.sleep(0.01)
        return False

    def test_second_turn_held_until_first_completes(self):
        sid = self.backend.spawn("q", self.d)
        self.assertTrue(self.backend.send(sid, "A"))
        self.assertTrue(self._wait(lambda: self.Gated.received == ["A"]), "A never reached the SDK")

        # B is enqueued while A is in flight: VISIBLE as queued, and NOT fed to the SDK.
        self.assertTrue(self.backend.send(sid, "B"))
        self.assertTrue(self._wait(lambda: self.backend.pending_queued(sid) == ["B"]),
                        "B should show as queued while A is in flight")
        self.assertEqual(self.Gated.received, ["A"], "B must NOT be fed to the SDK until A finishes")

        # Let A finish: B is released in order and drains from the pending list.
        self.Gated.release.set()
        self.assertTrue(self._wait(lambda: self.Gated.received == ["A", "B"]),
                        "B should be released to the SDK once A completes")
        self.assertTrue(self._wait(lambda: self.backend.pending_queued(sid) == []),
                        "pending clears the instant B starts processing")


@unittest.skipUnless(_HAVE_SDK, "claude_agent_sdk not installed")
class InterruptWithQueue(unittest.TestCase):
    """Interrupt must NOT settle inflight or release the next queued turn itself — that's the
    double-count api caught (the forced interrupt-settle AND the aborted turn's ResultMessage both
    decrement, so the next turn is released early while the prior is still counted). Modeled
    deterministically with a STALLED interrupt (no ResultMessage, like InterruptSettlesStall) so
    there is no result-ordering race: the interrupted turn stays in flight, so its queued follower
    must WAIT (honest queue-pause; the CLI is stuck) rather than be force-fed into a wedged CLI.
      fix : B stays queued, session reads 'waiting' (inflight held, display only).
      bug : the forced settle frees inflight → B is popped + fed into the stuck CLI."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self._orig = _sdk.ClaudeSDKClient
        import asyncio as _aio

        class StallClient:
            instances = []
            received = []                  # turn texts actually fed to the SDK, in order

            def __init__(self, options=None, transport=None):
                self.options = options
                self.interrupted = False
                self._turnq = _aio.Queue()
                StallClient.instances.append(self)

            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False

            async def query(self, prompt, session_id="default"):
                async for turn in prompt:
                    await self._turnq.put(turn)

            async def interrupt(self):
                self.interrupted = True    # interrupt sent, but the wedged turn never produces a result

            async def receive_messages(self):
                yield _sdk.SystemMessage("init", {"session_id": self.options.session_id or "fsid"})
                while True:
                    turn = await self._turnq.get()
                    StallClient.received.append(turn["message"]["content"][0]["text"])
                    await _aio.sleep(3600)           # stall this turn forever (never a ResultMessage)

        _sdk.ClaudeSDKClient = StallClient
        self.Fake = StallClient
        StallClient.instances = []
        StallClient.received = []
        self.backend = sb.SdkBackend(self.d, "/bin/true", lambda *a, **k: None)

    def tearDown(self):
        _sdk.ClaudeSDKClient = self._orig

    def _wait(self, pred, timeout=6.0):
        end = time.time() + timeout
        while time.time() < end:
            if pred():
                return True
            time.sleep(0.01)
        return False

    def test_interrupt_does_not_release_or_double_count_the_queue(self):
        sid = self.backend.spawn("x", self.d)
        self.backend.send(sid, "A")
        self.assertTrue(self._wait(lambda: self.Fake.received == ["A"]), "A is in flight")
        self.backend.send(sid, "B")
        self.assertTrue(self._wait(lambda: self.backend.pending_queued(sid) == ["B"]))

        # Interrupt the (wedged) A. Interrupt must only FLAG it — not drop inflight or release B.
        self.assertTrue(self.backend.interrupt(sid))
        self.assertTrue(self._wait(lambda: self.Fake.instances[0].interrupted), "client.interrupt() sent")

        # Settle window: a forced-settle-on-interrupt (the bug) would free inflight and pop B into the
        # stuck CLI here. The fix holds inflight, so B is never released no matter how long we wait.
        time.sleep(0.3)
        self.assertEqual(self.backend.pending_queued(sid), ["B"],
                         "B stays queued behind the still-in-flight interrupted turn — not force-released")
        self.assertEqual(self.Fake.received, ["A"], "B was NOT fed to the SDK by the interrupt")
        self.assertEqual(self.backend.live_sessions().get(sid, {}).get("state"), "waiting",
                         "the interrupted turn reads 'waiting' (display) while inflight is held — not 'working'")


if __name__ == "__main__":
    unittest.main()
