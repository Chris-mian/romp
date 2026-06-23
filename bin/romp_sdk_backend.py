"""SdkBackend — non-tmux romp sessions driven by the Claude Agent SDK.

A second SessionBackend that coexists with tmux (selectable per session). It runs
the SAME `claude` binary romp launches in tmux, so it writes the SAME transcripts
to the SAME paths (the read side — event model, judges, panes — is unchanged).
What changes is the control channel: a long-lived SDK client per session instead
of TUI-scraping. Design: design/sdk-backend.md.

Concurrency: the kernel is threaded and synchronous (no asyncio). Each SDK session
runs in its own daemon thread that owns a private asyncio loop (quarantined — the
loop never escapes the thread); the kernel bridges via thread-safe scheduling.
State is event-based (a turn enqueued -> working; ResultMessage -> waiting), per
the repo's "events over heuristics" rule.

The module imports cleanly WITHOUT claude_agent_sdk; the SDK is imported lazily
when a session actually starts, so the tmux-only path keeps zero third-party deps
and the kernel degrades gracefully when the SDK is absent.
"""
from __future__ import annotations
import asyncio
import json
import os
import threading
import time
import uuid
from pathlib import Path

# ---------------------------------------------------------------------------
# Pure translation logic (no SDK import — unit-tested in CI without the dep).
# ---------------------------------------------------------------------------

# Identity palette — mirrors bin/romp's `_palette`/`_fg` (the same hex SET the vault dashboard
# uses). The tmux launcher picks the first unused colour; for an SDK session we pick deterministically
# by a stable hash of the sid (the launcher's own fallback when all are taken), so the session gets a
# consistent colour without cross-backend "used" bookkeeping. Keep the SET in sync with bin/romp.
_PALETTE = ["#1EA1EB", "#54B204", "#4EA8A9", "#DD42FF", "#E87221",
            "#98998A", "#F85B5A", "#F9D849", "#9088F0"]
_FG = ["white", "black", "white", "white", "black", "black", "white", "black", "black"]


def pick_identity_color(sid: str) -> tuple[str, str]:
    """A stable (bg, fg) for a session, hashed from its sid into the romp palette."""
    import zlib
    i = zlib.crc32(sid.encode()) % len(_PALETTE)
    return _PALETTE[i], _FG[i]


def _block_to_dict(b):
    """One SDK content block → the transcript/event-model block dict (by type name, so no SDK import)."""
    n = type(b).__name__
    if n == "TextBlock":
        return {"type": "text", "text": getattr(b, "text", "")}
    if n == "ThinkingBlock":
        return {"type": "thinking", "thinking": getattr(b, "thinking", ""), "signature": getattr(b, "signature", None)}
    if n == "ToolUseBlock":
        return {"type": "tool_use", "id": getattr(b, "id", ""), "name": getattr(b, "name", ""), "input": getattr(b, "input", {})}
    if n == "ToolResultBlock":
        return {"type": "tool_result", "tool_use_id": getattr(b, "tool_use_id", ""),
                "content": getattr(b, "content", ""), "is_error": bool(getattr(b, "is_error", False))}
    return None


def msg_to_atom(msg, sid, fsid, t):
    """An SDK stream message → an event-model atom (the SAME shape the file adapter emits from a
    transcript line), so the chat renders a LIVE atom identically and it dedups against the transcript
    by uuid (verified: the SDK message uuid == the transcript atom uuid). Returns None for messages
    with no renderable content (init/result/etc.)."""
    n = type(msg).__name__
    u = getattr(msg, "uuid", None)
    if n == "AssistantMessage":
        content = [d for b in (getattr(msg, "content", []) or []) if (d := _block_to_dict(b))]
        if not content:
            return None
        return {"type": "assistant", "uuid": u, "session_id": sid, "t": t, "fsid": fsid, "parentUuid": None,
                "message": {"role": "assistant", "model": getattr(msg, "model", "") or "",
                            "content": content, "stop_reason": getattr(msg, "stop_reason", None)}}
    if n == "UserMessage":
        c = getattr(msg, "content", None)
        content = [d for b in c if (d := _block_to_dict(b))] if isinstance(c, list) else (
            [{"type": "text", "text": str(c)}] if c else [])
        if not content:
            return None
        return {"type": "user", "uuid": u, "session_id": sid, "t": t, "fsid": fsid, "parentUuid": None,
                "message": {"role": "user", "content": content}}
    return None


def ask_question_to_live(question: dict, qi: int, total: int, selected=None) -> dict:
    """Translate ONE AskUserQuestion question into the askLive `ask` shape the
    existing picker UI already renders (the same shape bin/romp-askparse emits),
    so SDK sessions reuse the pane-scraper's UI with zero changes.

    `question` is one element of the tool input's `questions[]`:
      {question, header, multiSelect, options:[{label, description, preview?}]}.
    `selected` is the set of 1-based option numbers currently toggled (multi).
    """
    selected = selected or set()
    multi = bool(question.get("multiSelect"))
    opts = []
    for i, o in enumerate(question.get("options") or []):
        n = i + 1
        opt = {"n": n, "label": o.get("label", ""), "desc": o.get("description", "")}
        if multi:
            opt["checked"] = n in selected
        else:
            opt["selected"] = n in selected
        if o.get("preview"):
            opt["preview"] = o["preview"]
        opts.append(opt)
    ask = {
        "kind": "multi" if multi else "single",
        "header": question.get("header", ""),
        "question": question.get("question", ""),
        "options": opts,
        "multiSelect": multi,
        "cursor": 0,
        "cursorFound": True,
    }
    if total > 1:
        ask["progress"] = {"i": qi + 1, "n": total}   # "question 2 of 3"
    if question.get("preview"):
        ask["preview"] = question["preview"]
    return ask


def label_for_target(question: dict, target) -> str:
    """Map a 1-based option number (what the UI sends as `target`) to its label.
    A non-numeric / out-of-range target is returned verbatim (free-text answer)."""
    opts = question.get("options") or []
    try:
        n = int(target)
    except (TypeError, ValueError):
        return str(target)
    if 1 <= n <= len(opts):
        return opts[n - 1].get("label", str(target))
    return str(target)


def build_answers(questions: list, picks: dict) -> dict:
    """Assemble the AskUserQuestion `answers` mapping (question-text -> label or
    [labels]) from per-question picks keyed by question index."""
    answers = {}
    for i, q in enumerate(questions):
        if i not in picks:
            continue
        answers[q.get("question", "")] = picks[i]
    return answers


def permission_to_live(tool_name: str, tool_input: dict) -> dict:
    """Render an ordinary tool-permission request as a 2-option askLive picker
    (Allow / Deny), so permissions reuse the same UI as questions."""
    summary = tool_input.get("command") or tool_input.get("file_path") \
        or tool_input.get("path") or tool_input.get("description") or ""
    q = f"Allow {tool_name}?"
    if summary:
        q += f"\n{str(summary)[:300]}"
    return {
        "kind": "single",
        "header": "Permission",
        "question": q,
        "options": [
            {"n": 1, "label": "Allow", "desc": f"Run {tool_name}", "selected": False},
            {"n": 2, "label": "Deny", "desc": "Refuse this call", "selected": False},
        ],
        "multiSelect": False,
        "cursor": 0,
        "cursorFound": True,
        "permission": True,
    }


# State-log helpers — match the kernel's `states/<sid>.jsonl` format exactly
# ({"t": epoch, "state": ...}) so the timeline + judges read both backends
# uniformly.
_STATES = ("working", "waiting", "idle", "permission", "compacting", "picker")


def append_state(state_dir: Path, sid: str, state: str, t: int | None = None) -> None:
    p = Path(state_dir) / "states" / (sid + ".jsonl")
    p.parent.mkdir(parents=True, exist_ok=True)
    rec = {"t": int(time.time()) if t is None else int(t), "state": state}
    with open(p, "a") as f:
        f.write(json.dumps(rec) + "\n")


def append_awaiting(state_dir: Path, sid: str, awaiting: bool, why: str = "") -> None:
    """Append an "awaiting" OVERLAY record to states/<sid>.jsonl (interleaved with the state
    records; the kernel reader scans for the latest line carrying an "awaiting" key). "Awaiting" =
    the session is idle but waiting on dispatched/background work — a flavour of working, exempt from
    auto-nudge (bugz's event-model awaiting, contract confirmed 2026-06-22). awaiting:true carries a
    "why"; awaiting:false clears it."""
    p = Path(state_dir) / "states" / (sid + ".jsonl")
    p.parent.mkdir(parents=True, exist_ok=True)
    rec = {"t": int(time.time()), "awaiting": bool(awaiting)}
    if awaiting and why:
        rec["why"] = why
    with open(p, "a") as f:
        f.write(json.dumps(rec) + "\n")


def last_state(state_dir: Path, sid: str) -> dict:
    p = Path(state_dir) / "states" / (sid + ".jsonl")
    try:
        line = ""
        with open(p) as f:
            for line in f:
                pass
        return json.loads(line) if line.strip() else {}
    except (OSError, ValueError):
        return {}


def write_name(state_dir: Path, sid: str, name: str, cwd: str, bg: str = "", fg: str = "") -> None:
    """Write the shared identity/discovery file `names/<sid>` in the kernel's
    tab-delimited format (name\\tcwd\\tbg\\tfg), so discover() finds the
    transcript and the UI gets the identity colour."""
    p = Path(state_dir) / "names" / sid
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text("\t".join([name, cwd, bg, fg]) + "\n")
    os.replace(tmp, p)


# ---------------------------------------------------------------------------
# Session registry (which sids are SDK-backed; survives kernel restart).
# ---------------------------------------------------------------------------

def _reg_path(state_dir: Path, sid: str) -> Path:
    return Path(state_dir) / "sdk" / (sid + ".json")


def read_reg(state_dir: Path, sid: str) -> dict | None:
    try:
        return json.loads(_reg_path(state_dir, sid).read_text())
    except (OSError, ValueError):
        return None


def write_reg(state_dir: Path, sid: str, reg: dict) -> None:
    p = _reg_path(state_dir, sid)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(reg))
    os.replace(tmp, p)


def list_regs(state_dir: Path) -> list[dict]:
    d = Path(state_dir) / "sdk"
    out = []
    if not d.is_dir():
        return out
    for f in d.glob("*.json"):
        try:
            r = json.loads(f.read_text())
            r.setdefault("sid", f.stem)
            out.append(r)
        except (OSError, ValueError):
            continue
    return out


# ---------------------------------------------------------------------------
# The live session (one quarantined asyncio thread).
# ---------------------------------------------------------------------------

class _AskCancelled(Exception):
    pass


class SdkSession:
    """One long-lived SDK client running in its own thread + asyncio loop."""

    def __init__(self, backend: "SdkBackend", reg: dict):
        self.backend = backend
        self.sid = reg["sid"]
        self.name = reg.get("name", self.sid)
        self.cwd = reg.get("cwd") or os.path.expanduser("~")
        self.mode = reg.get("mode") or "acceptEdits"
        self.resume_sid = reg.get("lastSid") or None  # resume target after a restart/crash
        # protocol/runtime state
        self.loop: asyncio.AbstractEventLoop | None = None
        self.client = None
        self.inflight = 0
        self.since = 0
        self.model = ""
        self.effort = ""
        self.perm_mode = self.mode
        self.ended = False
        # input + ask bridging
        self._pre = []                       # turns enqueued before the loop is ready
        self._inq: asyncio.Queue | None = None
        self._cur_ask_fut: asyncio.Future | None = None
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self.thread = threading.Thread(target=self._run, name=f"sdk:{self.name}", daemon=True)

    # ---- kernel-thread API (thread-safe) ----

    def start(self):
        self.thread.start()

    def enqueue(self, text: str):
        """Deliver a user turn (called from the kernel thread)."""
        with self._lock:
            if self.loop is None or self._inq is None:
                self._pre.append(text)
                return
            loop, q = self.loop, self._inq
        loop.call_soon_threadsafe(q.put_nowait, text)

    def interrupt(self):
        if self.loop and self.client:
            self.loop.call_soon_threadsafe(
                lambda: asyncio.ensure_future(self._do_interrupt()))

    def resolve_ask(self, kind: str, payload=None):
        """Deliver a picker/permission UI action (answer/toggle/submit/custom/
        cancel/text) into the waiting can_use_tool coroutine."""
        if not self.loop:
            return
        def _set():
            fut = self._cur_ask_fut
            if fut and not fut.done():
                fut.set_result((kind, payload))
        self.loop.call_soon_threadsafe(_set)

    def shutdown(self):
        self.ended = True
        if self.loop and self._inq is not None:
            self.loop.call_soon_threadsafe(self._inq.put_nowait, None)
        if self.loop and self.client:
            self.loop.call_soon_threadsafe(
                lambda: asyncio.ensure_future(self._do_interrupt()))

    # ---- async internals (run inside the quarantined loop) ----

    async def _do_interrupt(self):
        try:
            await self.client.interrupt()
        except Exception:
            pass

    async def _next_ask_action(self):
        fut = asyncio.get_running_loop().create_future()
        self._cur_ask_fut = fut
        try:
            return await fut
        finally:
            self._cur_ask_fut = None

    def _run(self):
        try:
            asyncio.run(self._amain())
        except Exception as e:                       # surfaced for debugging; never crash kernel
            self.backend._log(f"sdk session {self.name} crashed: {type(e).__name__}: {e}")
        finally:
            self.backend._on_session_gone(self)

    async def _amain(self):
        # Lazy SDK import — keeps the module importable without the dep.
        from claude_agent_sdk import (
            ClaudeSDKClient, ClaudeAgentOptions,
            AssistantMessage, ResultMessage, SystemMessage,
        )
        self.loop = asyncio.get_running_loop()
        self._inq = asyncio.Queue()
        with self._lock:
            for t in self._pre:
                self._inq.put_nowait(t)
            self._pre = []
            self._ready.set()

        async def inputs():
            while True:
                item = await self._inq.get()
                if item is None:
                    return
                if self.inflight == 0:
                    self.since = int(time.time())
                self.inflight += 1
                append_state(self.backend.state_dir, self.sid, "working")
                self.backend._poke()
                yield {"type": "user",
                       "message": {"role": "user", "content": [{"type": "text", "text": item}]}}

        opts = self.backend._options(self, ClaudeAgentOptions)
        async with ClaudeSDKClient(options=opts) as client:
            self.client = client
            # Feed turns and receive messages CONCURRENTLY: query() with a streaming
            # input iterable BLOCKS until the iterable ends (it writes each turn to
            # stdin), and our input generator never ends (long-lived) — so awaiting it
            # before receiving would starve the receive loop forever. The SDK's control
            # channel (can_use_tool) runs in its own reader task regardless; the message
            # stream does not, so it must be drained here, alongside the feeder.
            feeder = asyncio.ensure_future(client.query(inputs()))
            try:
                async for msg in client.receive_messages():
                    if self.ended:
                        break
                    self._on_message(msg, AssistantMessage, ResultMessage, SystemMessage)
            finally:
                feeder.cancel()
                try:
                    await feeder
                except BaseException:
                    pass

    def _on_message(self, msg, AssistantMessage, ResultMessage, SystemMessage):
        if isinstance(msg, SystemMessage) and msg.subtype == "init":
            d = msg.data if isinstance(msg.data, dict) else {}
            self.model = d.get("model") or self.model
            self.perm_mode = d.get("permissionMode") or self.perm_mode
            fsid = d.get("session_id")
            if fsid and fsid != self.resume_sid:
                self.resume_sid = fsid
                self.backend._update_reg(self.sid, lastSid=fsid)
        elif isinstance(msg, AssistantMessage):
            if getattr(msg, "model", None):
                self.model = msg.model
        elif isinstance(msg, ResultMessage):
            self.inflight = max(0, self.inflight - 1)
            if self.inflight == 0:
                append_state(self.backend.state_dir, self.sid, "waiting")
                self.backend._poke()
        # Forward the raw message to the kernel for live chat/event use.
        self.backend._forward(self, msg)

    # ---- the permission/AskUserQuestion callback (the headless-parity piece) ----

    async def _can_use_tool(self, tool_name: str, tool_input: dict, context):
        from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny
        if tool_name == "AskUserQuestion":
            try:
                answers = await self._ask_user(tool_input)
            except _AskCancelled:
                return PermissionResultDeny(behavior="deny",
                                            message="User cancelled the question.", interrupt=False)
            return PermissionResultAllow(
                behavior="allow",
                updated_input={"questions": tool_input.get("questions", []), "answers": answers})
        # Ordinary tool permission -> Allow/Deny picker.
        ask = permission_to_live(tool_name, tool_input)
        append_state(self.backend.state_dir, self.sid, "permission")
        self.backend._emit_ask(self, ask)
        try:
            while True:
                kind, payload = await self._next_ask_action()
                if kind in ("answer",):
                    allow = (str(payload) == "1")
                    break
                if kind == "cancel":
                    allow = False
                    break
        finally:
            self.backend._clear_ask(self)
            if self.inflight:
                append_state(self.backend.state_dir, self.sid, "working")
        if allow:
            return PermissionResultAllow(behavior="allow")
        return PermissionResultDeny(behavior="deny", message="Denied by user.", interrupt=False)

    async def _ask_user(self, tool_input: dict) -> dict:
        """Drive the picker UI for each question (sequentially for multi-question),
        returning the AskUserQuestion `answers` mapping."""
        questions = tool_input.get("questions") or []
        picks: dict[int, object] = {}
        append_state(self.backend.state_dir, self.sid, "picker")
        try:
            for qi, q in enumerate(questions):
                picks[qi] = await self._ask_one(q, qi, len(questions))
        finally:
            self.backend._clear_ask(self)
            if self.inflight:
                append_state(self.backend.state_dir, self.sid, "working")
        return build_answers(questions, picks)

    async def _ask_one(self, question: dict, qi: int, total: int):
        multi = bool(question.get("multiSelect"))
        selected: set[int] = set()
        self.backend._emit_ask(self, ask_question_to_live(question, qi, total, selected))
        while True:
            kind, payload = await self._next_ask_action()
            if kind == "cancel":
                raise _AskCancelled()
            if kind == "custom" and payload:
                return str(payload)
            if kind == "text" and payload:
                return str(payload)
            if not multi and kind == "answer":
                return label_for_target(question, payload)
            if multi and kind == "toggle":
                try:
                    n = int(payload)
                    selected.discard(n) if n in selected else selected.add(n)
                except (TypeError, ValueError):
                    pass
                self.backend._emit_ask(self, ask_question_to_live(question, qi, total, selected))
                continue
            if multi and kind == "submit":
                return [label_for_target(question, n) for n in sorted(selected)]
            # single-select that received a toggle, or vice versa: re-emit.
            self.backend._emit_ask(self, ask_question_to_live(question, qi, total, selected))

    # ---- the awaiting producer (bugz's event-model overlay) ----

    async def _stop_hook(self, inp, tool_use_id, context):
        """At turn-end, emit the awaiting overlay: awaiting:true while background work is still
        outstanding (run_in_background tasks survive the turn), awaiting:false otherwise. The Stop
        hook fires again on the follow-up turn a task-completion notification triggers, so this
        self-corrects to awaiting:false when the work finishes. The kernel reader only honours
        awaiting while the session is IDLE, so mid-turn (working) it's ignored — Stop is the right
        and sufficient hook."""
        bg = inp.get("background_tasks") if isinstance(inp, dict) else None
        n = len(bg) if isinstance(bg, (list, tuple)) else (1 if bg else 0)
        if n:
            append_awaiting(self.backend.state_dir, self.sid, True, "%d background task(s) running" % n)
        else:
            append_awaiting(self.backend.state_dir, self.sid, False)
        self.backend._poke()
        return {}

    # ---- snapshot for live_sessions() ----

    def snapshot(self) -> dict:
        if self.inflight > 0:
            state, since = "working", self.since
        else:
            ls = last_state(self.backend.state_dir, self.sid)
            state, since = ls.get("state") or "waiting", ls.get("t") or 0
        return {"state": state, "since": str(since) if since else "",
                "model": self.model, "effort": self.effort,
                "mode": self.perm_mode, "ctx": "", "summary": ""}


# ---------------------------------------------------------------------------
# The backend.
# ---------------------------------------------------------------------------

class SdkBackend:
    """Manages SDK-backed sessions. Constructed by the kernel with callbacks for
    pushing to clients and a few launch parameters that mirror the tmux launch."""

    def __init__(self, state_dir, claude_bin: str, notify, poke=None, push=None,
                 mcp_config: str | None = None, append_prompt_path: str | None = None,
                 log=None):
        self.state_dir = Path(state_dir)
        self.claude_bin = claude_bin
        self._notify = notify              # notify(app, msg) -> push to clients (kernel._send_to_app)
        self._poke_cb = poke               # wake the kernel's producer/judges (optional)
        self._push_cb = push               # wake the kernel's PUSHER → immediate chat push (live tail)
        self.mcp_config = mcp_config
        self.append_prompt_path = append_prompt_path
        self._log_cb = log
        self.sessions: dict[str, SdkSession] = {}
        self._lock = threading.Lock()
        self._pending_ask: dict[str, bool] = {}   # sid -> has an ask awaiting answer
        self._live: dict[str, dict] = {}          # sid -> {key -> atom}: the in-memory LIVE TAIL (ahead of disk)

    # ---- logging / wakeups ----
    def _log(self, m):
        if self._log_cb:
            self._log_cb(m)

    def _poke(self):
        if self._poke_cb:
            try:
                self._poke_cb()
            except Exception:
                pass

    # ---- SDK option assembly (mirrors the tmux launch flags) ----
    def _options(self, sess: SdkSession, ClaudeAgentOptions):
        from claude_agent_sdk import HookMatcher
        extra = {}
        if self.append_prompt_path and os.path.exists(self.append_prompt_path):
            try:
                extra["append-system-prompt"] = Path(self.append_prompt_path).read_text()
            except OSError:
                pass
        kw = dict(
            cli_path=self.claude_bin,
            cwd=sess.cwd,
            can_use_tool=sess._can_use_tool,
            hooks={"Stop": [HookMatcher(matcher=None, hooks=[sess._stop_hook])]},   # awaiting overlay producer
            permission_mode=sess.mode,
            include_partial_messages=False,
        )
        if sess.resume_sid:
            kw["resume"] = sess.resume_sid
        else:
            kw["session_id"] = sess.sid
        if self.mcp_config:
            kw["mcp_servers"] = self.mcp_config
        if extra:
            kw["extra_args"] = extra
        return ClaudeAgentOptions(**kw)

    # ---- lifecycle (kernel-thread API) ----
    def spawn(self, name: str, cwd: str, bg: str = "", fg: str = "", sid: str | None = None) -> str:
        sid = sid or str(uuid.uuid4())
        cwd = os.path.realpath(cwd) if os.path.exists(cwd) else cwd
        if not bg:                                   # give the session a stable identity colour like tmux sessions get
            bg, fg = pick_identity_color(sid)
        write_name(self.state_dir, sid, name, cwd, bg, fg)
        write_reg(self.state_dir, sid, {"sid": sid, "name": name, "cwd": cwd,
                                        "mode": "acceptEdits", "lastSid": "", "alive": True})
        append_state(self.state_dir, sid, "waiting")
        self._poke()
        return sid

    def resume(self, name: str, sid: str, cwd: str | None = None) -> bool:
        reg = read_reg(self.state_dir, sid) or {}
        cwd = cwd or reg.get("cwd") or os.path.expanduser("~")
        write_reg(self.state_dir, sid, {"sid": sid, "name": name, "cwd": cwd,
                                        "mode": reg.get("mode", "acceptEdits"),
                                        "lastSid": sid, "alive": True})
        append_state(self.state_dir, sid, "waiting")
        self._poke()
        return True

    def _ensure(self, sid: str) -> SdkSession | None:
        with self._lock:
            s = self.sessions.get(sid)
            if s and s.thread.is_alive():
                return s
            reg = read_reg(self.state_dir, sid)
            if not reg or not reg.get("alive"):
                return None
            reg["sid"] = sid
            s = SdkSession(self, reg)
            self.sessions[sid] = s
            s.start()
            return s

    def send(self, sid: str, text: str) -> bool:
        s = self._ensure(sid)
        if not s:
            return False
        s.enqueue(text)
        # optimistic input echo: show the user's own message INSTANTLY (neither the transcript nor the
        # stream has it yet at send time — only we know the text). Synthetic uuid; pruned by text once the
        # transcript writes the real user atom.
        key = "echo:" + uuid.uuid4().hex
        self._live.setdefault(sid, {})[key] = {
            "type": "user", "uuid": key, "session_id": sid, "t": int(time.time()), "parentUuid": None,
            "_echo_text": text, "message": {"role": "user", "content": [{"type": "text", "text": text}]}}
        self._wake_push()
        return True

    def interrupt(self, sid: str) -> bool:
        s = self.sessions.get(sid)
        if not s:
            return False
        s.interrupt()
        append_state(self.state_dir, sid, "idle", int(time.time()) - 1)
        self._poke()
        return True

    def kill(self, sid: str) -> bool:
        reg = read_reg(self.state_dir, sid)
        if reg:
            reg["alive"] = False
            write_reg(self.state_dir, sid, reg)
        s = self.sessions.pop(sid, None)
        if s:
            s.shutdown()
        self._poke()
        return True

    def rename(self, sid: str, new_name: str) -> bool:
        reg = read_reg(self.state_dir, sid)
        if not reg:
            return False
        reg["name"] = new_name
        write_reg(self.state_dir, sid, reg)
        # keep the shared names/ identity file in sync (preserve colours)
        try:
            parts = (Path(self.state_dir) / "names" / sid).read_text().rstrip("\n").split("\t")
        except OSError:
            parts = [new_name, reg.get("cwd", "")]
        parts += ["", "", ""]
        write_name(self.state_dir, sid, new_name, parts[1], parts[2], parts[3])
        s = self.sessions.get(sid)
        if s:
            s.name = new_name
        return True

    def set_mode(self, sid: str, mode: str) -> bool:
        reg = read_reg(self.state_dir, sid)
        if not reg:
            return False
        reg["mode"] = mode
        write_reg(self.state_dir, sid, reg)
        s = self.sessions.get(sid)
        if s:
            s.mode = mode           # applied on next (re)connect
        return True

    def owns(self, sid: str) -> bool:
        return read_reg(self.state_dir, sid) is not None

    def live_sessions(self) -> dict[str, dict]:
        """{sid: state-dict} for every alive SDK session — merged by the kernel
        into its session enumeration so SDK sessions appear in the UI."""
        out = {}
        for reg in list_regs(self.state_dir):
            if not reg.get("alive"):
                continue
            sid = reg["sid"]
            s = self.sessions.get(sid)
            if s and s.thread.is_alive():
                out[sid] = s.snapshot()
            else:
                ls = last_state(self.state_dir, sid)
                out[sid] = {"state": ls.get("state") or "waiting",
                            "since": str(ls.get("t") or ""), "model": "", "effort": "",
                            "mode": reg.get("mode", ""), "ctx": "", "summary": ""}
        return out

    # ---- picker/permission UI bridge (kernel-thread API) ----
    def on_ask(self, sid: str, kind: str, payload=None) -> bool:
        """Route an inbound picker action (answer/toggle/submit/custom/cancel/text)
        to the SDK session's waiting callback. Returns False if not SDK-backed."""
        s = self.sessions.get(sid)
        if not s:
            return False
        s.resolve_ask(kind, payload)
        return True

    # ---- callbacks used by sessions ----
    def _emit_ask(self, sess: SdkSession, ask: dict):
        self._pending_ask[sess.sid] = True
        self._notify("chat", {"type": "askLive", "id": sess.sid, "ask": ask})
        self._poke()

    def _clear_ask(self, sess: SdkSession):
        self._pending_ask.pop(sess.sid, None)
        self._notify("chat", {"type": "askLiveClear", "id": sess.sid})

    def _forward(self, sess: SdkSession, msg):
        # LIVE TAIL: translate the streamed message to an atom and stash it in memory, AHEAD of the
        # transcript on disk (the SDK stream leads the disk write), then wake the kernel's pusher for an
        # immediate chat push. build_session merges these and the transcript supersedes them by uuid.
        atom = msg_to_atom(msg, sess.sid, sess.resume_sid, int(time.time()))
        if not (atom and atom.get("uuid")):
            return
        d = self._live.setdefault(sess.sid, {})
        d[atom["uuid"]] = atom
        while len(d) > 100:                      # safety cap if no client ever drains/prunes
            del d[next(iter(d))]
        self._wake_push()

    def _wake_push(self):
        if self._push_cb:
            try:
                self._push_cb()
            except Exception:
                pass

    def live_atoms(self, sid: str) -> list:
        """The session's in-memory live-tail atoms (newest last), for build_session to merge ahead of disk."""
        d = self._live.get(sid)
        return sorted(d.values(), key=lambda a: a.get("t", 0)) if d else []

    def prune_live(self, sid: str, tx_uuids, tx_user_texts=()) -> None:
        """Drop live atoms the transcript has now caught up on — by uuid (assistant/tool/user from the
        stream) or by text (the optimistic input echo, which has a synthetic uuid)."""
        d = self._live.get(sid)
        if not d:
            return
        for k in list(d.keys()):
            a = d[k]
            if a.get("uuid") in tx_uuids or (a.get("_echo_text") and a["_echo_text"] in tx_user_texts):
                del d[k]
        if not d:
            self._live.pop(sid, None)

    def _update_reg(self, sid: str, **fields):
        reg = read_reg(self.state_dir, sid) or {"sid": sid}
        reg.update(fields)
        write_reg(self.state_dir, sid, reg)

    def _on_session_gone(self, sess: SdkSession):
        with self._lock:
            if self.sessions.get(sess.sid) is sess:
                self.sessions.pop(sess.sid, None)
        if not sess.ended:
            # process exited on its own (crash / EOF) — settle state; next send resumes
            append_state(self.state_dir, sess.sid, "waiting")
        self._poke()
