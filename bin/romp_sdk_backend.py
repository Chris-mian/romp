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
import difflib
import json
import os
import re
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


# Reasoning effort for SDK sessions. effort is a CONNECT-TIME CLI flag (--effort) with no runtime control,
# and the init message does NOT echo it back, so romp sets it explicitly and tracks it (otherwise the picker
# can't show a true value). "high" suits agentic coding; the user changes it per session via the picker.
DEFAULT_EFFORT = "high"
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")


def pretty_model(raw: str) -> str:
    """A raw SDK model id → the short badge the tmux statusline shows, so SDK and tmux sessions read the
    same and the model picker's 'current' highlight (which matches on the leading word) lights up.
    'claude-opus-4-8' → 'Opus 4.8', 'claude-haiku-4-5-20251001' → 'Haiku 4.5', 'claude-fable-5' → 'Fable 5'.
    Unrecognised ids pass through verbatim."""
    if not raw:
        return ""
    m = re.match(r"claude-([a-z]+)-(\d+)(?:[-.](\d+))?", raw)
    if not m:
        return raw
    fam, maj, minor = m.groups()
    return f"{fam.capitalize()} {maj}" + (f".{minor}" if minor else "")


def model_label(live: str, chosen: str) -> str:
    """The model badge to show for an SDK session. Prefer the LIVE name once the init / assistant message has
    echoed it; otherwise fall back to a best-effort label from the CHOSEN alias so a freshly-created session
    shows its model RIGHT AWAY (the user 2026-06-24) — like a tmux session does on launch — instead of a blank
    until the first turn. A raw id → pretty_model ('claude-opus-4-8' → 'Opus 4.8'); a CLI alias (opus/sonnet/…)
    → capitalised (matches set_model's live-change label); 'default'/unset → '' (the real default name fills in
    on connect from get_context_usage(), which _amain pulls before the first turn)."""
    if live:
        return live
    if not chosen or chosen == "default":
        return ""
    return pretty_model(chosen) if chosen.startswith("claude-") else chosen.capitalize()


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


# Claude Code's slash-command wrappers, TWINS of bin/romp-event-model's (kept in lockstep — see its
# "slash-command transcript wrappers" block): the CLI streams its /model, /compact etc. feedback as
# UserMessages wrapped in these markers, and the LIVE atom must classify them exactly like the file
# adapter classifies the matching transcript records.
_COMMAND_NAME_RE = re.compile(r"^\s*<command-name>([^<]*)</command-name>")
_COMMAND_ARGS_RE = re.compile(r"<command-args>([\s\S]*?)</command-args>")
_LOCAL_STDOUT_RE = re.compile(r"^\s*<local-command-stdout>([\s\S]*?)</local-command-stdout>")
_CMD_WRAP_RE = re.compile(r"^\s*<(?:command-(?:name|message|args|contents)|local-command-(?:stdout|caveat))>")


def msg_to_atom(msg, sid, fsid, t):
    """An SDK stream message → an event-model atom (the SAME shape the file adapter emits from a
    transcript line), so the chat renders a LIVE atom identically and it dedups against the transcript
    by uuid (verified: the SDK message uuid == the transcript atom uuid). Returns None for messages
    with no renderable content (init/result/etc.).

    Slash-command wrappers get the FILE ADAPTER's classification, not a raw user atom (the user
    2026-07-02): client.set_model() makes the CLI stream a `<local-command-stdout>Set model to …`
    UserMessage; as a raw user atom it OPENED a turn no reply would ever close — the chat chip then read
    "working" forever while the timeline (disk-only; the CLI persists no transcript for a turn-less
    control request) showed nothing. Mirroring the adapter, the output becomes a synthetic ASSISTANT
    command atom with stop_reason end_turn — the turn closes, the chip stays consistent, and the chat
    still shows the confirmation line."""
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
        text = " ".join(b.get("text", "") for b in content
                        if isinstance(b, dict) and b.get("type") == "text")
        mcmd = _COMMAND_NAME_RE.match(text)
        if mcmd:                                     # the command INVOCATION → the command-flagged user atom
            name = mcmd.group(1).strip() or "/?"
            if not name.startswith("/"):
                name = "/" + name
            margs = _COMMAND_ARGS_RE.search(text)
            args = (margs.group(1).strip() if margs else "")
            disp = name + ((" " + args) if args else "")
            return {"type": "user", "uuid": u, "session_id": sid, "t": t, "fsid": fsid, "parentUuid": None,
                    "author": "human", "command": name,
                    "message": {"role": "user", "content": [{"type": "text", "text": disp}]}}
        mout = _LOCAL_STDOUT_RE.match(text)
        if mout:                                     # the command OUTPUT → a synthetic assistant atom that ENDS the turn
            return {"type": "assistant", "uuid": u, "session_id": sid, "t": t, "fsid": fsid, "parentUuid": None,
                    "command": True,
                    "message": {"role": "assistant",
                                "content": [{"type": "text", "text": mout.group(1).strip()}],
                                "stop_reason": "end_turn"}}
        if _CMD_WRAP_RE.match(text):                 # the remaining wrappers (message/args/contents/caveat) — noise
            return None
        return {"type": "user", "uuid": u, "session_id": sid, "t": t, "fsid": fsid, "parentUuid": None,
                "message": {"role": "user", "content": content}}
    return None


TYPE_SOMETHING = "Type something"   # meta-option label the webview turns into the inline "add your own" field


def ask_question_to_live(question: dict, qi: int, total: int, selected=None, customs=None) -> dict:
    """Translate ONE AskUserQuestion question into the askLive `ask` shape the
    existing picker UI already renders (the same shape bin/romp-askparse emits),
    so SDK sessions reuse the pane-scraper's UI with zero changes.

    `question` is one element of the tool input's `questions[]`:
      {question, header, multiSelect, options:[{label, description, preview?}]}.
    `selected` is the set of 1-based option numbers currently toggled (multi).
    `customs` are free-text answers the user has typed so far (multi-select shows them as already-checked
    rows). A trailing "Type something" meta option is ALWAYS appended so the webview renders the inline
    "add your own answer" field — the TUI always offers it, but the SDK's raw tool input doesn't, so the
    SDK backend synthesizes it (the user 2026-06-27). The webview filters the meta row out of the pickable
    options (isMetaOption); numbering stays contiguous (real → customs → meta) so a toggle ordinal maps
    back here unambiguously.
    """
    selected = selected or set()
    customs = customs or []
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
    for c in customs:                                 # already-typed free-text (multi) → checked rows
        opt = {"n": len(opts) + 1, "label": c}
        opt["checked" if multi else "selected"] = True
        opts.append(opt)
    meta = {"n": len(opts) + 1, "label": TYPE_SOMETHING, "desc": "add your own answer"}
    meta["checked" if multi else "selected"] = False
    opts.append(meta)
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


_PREVIEW_MAX_LINES = 200             # cap a diff/plan preview so a huge edit can't bloat the push


def _clip_lines(lines: list[str]) -> str:
    if len(lines) > _PREVIEW_MAX_LINES:
        kept = lines[:_PREVIEW_MAX_LINES]
        kept.append("… (%d more lines)" % (len(lines) - _PREVIEW_MAX_LINES))
        lines = kept
    return "\n".join(lines)


def _unified(path: str, old: str, new: str) -> list[str]:
    """A unified diff old→new, headed by the path. +/- prefixed so the webview can colorize it."""
    a, b = (old or "").splitlines(), (new or "").splitlines()
    body = list(difflib.unified_diff(a, b, lineterm="", n=2))
    # difflib emits ---/+++ file headers; drop them (we print our own path header) but keep @@ hunks.
    body = [ln for ln in body if not ln.startswith("--- ") and not ln.startswith("+++ ")]
    head = path or "(file)"
    return [head] + (body if body else ["(no textual change)"])


def tool_preview(tool_name: str, tool_input: dict) -> tuple[str, str] | None:
    """A monospace preview for a tool-permission prompt — (kind, text) or None when there's nothing
    visual to show. kind is "diff" (Edit/Write/MultiEdit, colorizable +/- lines) or "plan"
    (ExitPlanMode). Lets the user SEE what they're approving instead of a bare tool name, the way the
    tmux pane scrape shows the TUI's diff/plan (the user 2026-06-27). Pure → unit-tested."""
    ti = tool_input or {}
    if tool_name == "ExitPlanMode":
        plan = str(ti.get("plan") or "").rstrip()
        return ("plan", _clip_lines(plan.split("\n"))) if plan else None
    if tool_name in ("Edit", "NotebookEdit"):
        path = ti.get("file_path") or ti.get("notebook_path") or ti.get("path") or ""
        return ("diff", _clip_lines(_unified(path, ti.get("old_string", ""), ti.get("new_string", ""))))
    if tool_name == "MultiEdit":
        path = ti.get("file_path") or ti.get("path") or ""
        lines: list[str] = []
        for e in (ti.get("edits") or []):
            lines += _unified(path, e.get("old_string", ""), e.get("new_string", ""))
            lines.append("")
        return ("diff", _clip_lines(lines)) if lines else None
    if tool_name == "Write":
        path = ti.get("file_path") or ti.get("path") or ""
        content = str(ti.get("content") or "")
        # a new/overwritten file → show its content as all-additions
        return ("diff", _clip_lines([path or "(file)"] + ["+" + ln for ln in content.split("\n")]))
    return None


def permission_to_live(tool_name: str, tool_input: dict, context=None) -> dict:
    """Render an ordinary tool-permission request as an askLive picker — Allow / Deny, plus an
    "Allow & don't ask again" option when the SDK offers permission-rule suggestions (the user
    2026-06-27). Uses the SDK's own prompt sentence (context.title) and subtitle (context.description)
    when present — the DESIGNED text — instead of reconstructing from the tool name, and attaches a
    diff/plan preview so the user can see what they're approving."""
    title = getattr(context, "title", None)
    desc = getattr(context, "description", None)
    summary = tool_input.get("command") or tool_input.get("file_path") \
        or tool_input.get("path") or tool_input.get("description") or ""
    q = title or (f"Allow {tool_name}?" + (f"\n{str(summary)[:300]}" if summary else ""))
    options = [{"n": 1, "label": "Allow", "desc": desc or f"Run {tool_name} once", "selected": False}]
    if getattr(context, "suggestions", None):
        options.append({"n": 2, "label": "Allow & don't ask again",
                        "desc": "Allow and remember this for the session", "selected": False})
    options.append({"n": len(options) + 1, "label": "Deny", "desc": "Refuse this call", "selected": False})
    ask = {
        "kind": "single",
        "header": "Permission",
        "question": q,
        "options": options,
        "multiSelect": False,
        "cursor": 0,
        "cursorFound": True,
        "permission": True,
    }
    pv = tool_preview(tool_name, tool_input)
    if pv:
        ask["previewKind"], ask["preview"] = pv[0], pv[1]
    return ask


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


def last_awaiting(state_dir: Path, sid: str) -> bool | None:
    """The latest awaiting-OVERLAY value in states/<sid>.jsonl — the most recent line carrying an
    "awaiting" key (state records interleave with overlays, so the very last line isn't necessarily one).
    None if the session has no awaiting overlay. Used to heal a stale awaiting:true that lost its clearing
    writer (the Stop hook) to a kernel restart / thread death."""
    p = Path(state_dir) / "states" / (sid + ".jsonl")
    val = None
    try:
        with open(p) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if isinstance(rec, dict) and "awaiting" in rec:
                    val = bool(rec["awaiting"])
    except OSError:
        return None
    return val


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
# Remembered SDK defaults (model + effort) for NEW sessions. A brand-new SDK session starts at the hardcoded
# fallbacks (DEFAULT_EFFORT + the account-default model); but the moment the user picks a model or effort on
# ANY session, we remember it here and seed the NEXT new session with it — so "what I last chose" becomes the
# startup default (the user 2026-06-27). No desync risk: the remembered value is written into the new
# session's OWN reg, which is exactly what _options launches with AND what the badge reads. Per-session
# changes still persist per-session (the reg, restored on resume); this is only the seed for new sessions.
# Stored OUTSIDE sdk/ so list_regs' sdk/*.json glob never mistakes it for a session.
# ---------------------------------------------------------------------------

def _defaults_path(state_dir: Path) -> Path:
    return Path(state_dir) / "sdk-defaults.json"


def read_sdk_defaults(state_dir: Path) -> dict:
    """{'model': <alias|'default'>, 'effort': <level>, 'mode': <permission mode>} — whatever the user last
    picked on any session, seeded into the next new session by spawn(); {} if never set."""
    try:
        d = json.loads(_defaults_path(state_dir).read_text())
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def write_sdk_default(state_dir: Path, **fields) -> None:
    """Merge {model?, effort?} into the remembered defaults (atomic tmp+rename). Only non-None keys passed
    are touched, so remembering a model never clobbers the remembered effort and vice-versa."""
    d = read_sdk_defaults(state_dir)
    d.update({k: v for k, v in fields.items() if v is not None})
    p = _defaults_path(state_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d))
    os.replace(tmp, p)


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
        self.model = reg.get("liveModel") or ""   # seed from the last-known model so the badge/picker show on
        #                                           OPEN (even once eager-connected, before init/a turn reports)
        _lc0 = reg.get("liveCtx")                 # context-window fill %, as the SDK reports it (see _ctx_pct).
        self._ctx: int | None = _lc0 if isinstance(_lc0, (int, float)) else None  # seeded from the last persisted
        #   value so the bar survives idle/restart; refreshed live from get_context_usage() on connect + each turn.
        self._ctx_refreshing = False             # one get_context_usage control request in flight at a time
        self.retrying = False                        # an api_retry storm (API rate-limit/overload) is stalling the turn → 'retrying', not 'working'
        self._interrupted = False                    # user interrupted the in-flight turn → snapshot reads 'waiting' (display only; inflight stays event-driven)
        self._subagents: dict[str, dict] = {}        # LIVE Task-spawned subagents: agent_id -> {"type","since"}. Fed
        #   by the SubagentStart/SubagentStop hooks — the exact, event-based "what's running right now" signal the
        #   tmux backend never had. Keeps the session 'working' while any run and surfaces a live count on the lane.
        self._sub_lock = threading.Lock()            #   hooks mutate on the loop thread; snapshot() reads from the kernel thread
        self.chosen_model = reg.get("model") or ""   # the alias the user picked (opus/sonnet/…); self.model is the display name
        self.effort = reg.get("effort") or DEFAULT_EFFORT   # connect-time --effort; tracked since the init msg doesn't echo it
        self.perm_mode = self.mode
        # reconnect machinery: effort changes (a connect-time flag) reconnect the client; _wake breaks the
        # receive loop cleanly for shutdown OR reconnect even when idle (a bare async-for would block forever).
        self._wake: asyncio.Event | None = None
        self._reconnect = False                 # the current break is a reconnect (not a shutdown)
        self._reconnect_when_idle = False        # a reconnect was requested mid-turn → apply at turn end
        self.ended = False
        # input + ask bridging
        # Queued user turns are held in a VISIBLE list (not flushed into the SDK) until the
        # in-flight turn ends, so the kernel can render them as the chat's "queued" indicator
        # (pending_queued). One turn in flight at a time; the not-yet-started turns persist here
        # across a reconnect. _input_wake is set whenever a turn may have become releasable.
        self._pending: list[str] = []
        self._input_wake: asyncio.Event | None = None
        self._cur_ask_fut: asyncio.Future | None = None
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self.thread = threading.Thread(target=self._run, name=f"sdk:{self.name}", daemon=True)

    # ---- kernel-thread API (thread-safe) ----

    def start(self):
        self.thread.start()

    def enqueue(self, text: str):
        """Deliver a user turn (called from the kernel thread). Held in self._pending —
        VISIBLE to pending_queued — until the input generator releases it at turn end. Works
        before the loop is ready too (the generator drains _pending on its first pass)."""
        with self._lock:
            self._pending.append(text)
            loop, wake = self.loop, self._input_wake
        if loop is not None and wake is not None:
            loop.call_soon_threadsafe(wake.set)

    def pending(self) -> list[str]:
        """The queued user turns not yet started (oldest first); thread-safe. The kernel
        renders these as the chat's 'queued' indicator for this SDK session."""
        with self._lock:
            return list(self._pending)

    def unqueue(self, idx: int) -> str | None:
        """Remove the queued turn at position `idx` (the chat's queued list is this same _pending order)
        and return its raw text, or None if out of range. Lets the user CANCEL a message they queued
        behind a busy turn — click it in the chat to pull it back out and re-edit (the user 2026-06-27).
        Only pending (not-yet-started) turns are cancelable; once the input generator has fed a turn to
        the SDK it's gone from _pending and no longer listed, so there's nothing to mis-cancel."""
        with self._lock:
            if 0 <= idx < len(self._pending):
                return self._pending.pop(idx)
        return None

    def interrupt(self):
        if self.loop and self.client:
            self.loop.call_soon_threadsafe(
                lambda: asyncio.ensure_future(self._do_interrupt()))

    def set_model_live(self, model):
        """Change the model on a CONNECTED session via the SDK control channel. No-op if not yet
        connected — _options applies chosen_model on connect instead."""
        if self.loop and self.client:
            self.loop.call_soon_threadsafe(
                lambda: asyncio.ensure_future(self._do_set_model(model)))

    def set_mode_live(self, mode):
        """Change the permission mode on a CONNECTED session via the SDK control channel."""
        if self.loop and self.client:
            self.loop.call_soon_threadsafe(
                lambda: asyncio.ensure_future(self._do_set_mode(mode)))

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
        if self.loop:
            self.loop.call_soon_threadsafe(self._wake_set)   # break the receive loop even if idle (no msg coming)
        if self.loop and self.client:
            self.loop.call_soon_threadsafe(
                lambda: asyncio.ensure_future(self._do_interrupt()))   # stop an in-flight turn promptly

    def _wake_set(self):
        if self._wake is not None:
            self._wake.set()

    def request_reconnect(self):
        """Apply a connect-time option change (effort) by reconnecting the client — resume continues the same
        conversation. Reconnect NOW when idle; defer to the end of the current turn when busy. No-op if the
        session is shutting down or not yet connected (the new value is in the registry → it applies on connect)."""
        if self.loop is None or self.ended:
            return
        self.loop.call_soon_threadsafe(self._do_request_reconnect)

    def _do_request_reconnect(self):
        if self.inflight == 0 and not self._pending:
            self._reconnect = True
            self._wake_set()
        else:
            self._reconnect_when_idle = True   # the ResultMessage handler fires it when the turn ends

    # ---- async internals (run inside the quarantined loop) ----

    async def _do_interrupt(self):
        # ACKNOWLEDGE FIRST, then send the control request. client.interrupt() BLOCKS until the CLI
        # acknowledges the interrupt — and the CLI won't acknowledge until the in-flight model call reaches
        # a boundary, which can take SECONDS mid-stream. Setting _interrupted only AFTER that await meant the
        # snapshot kept reading 'working' the whole time, so a stopped turn still looked like it was spinning
        # (the user 2026-06-30: "I interrupted but it said working for a while"). Flip + poke up front so the
        # lane reads 'waiting' the instant the user hits stop; the interrupt itself completes below.
        #
        # Don't touch inflight or release the next queued turn here. A normal interrupt aborts the turn and the
        # SDK emits its ResultMessage, which does the SINGLE decrement + the natural release in _on_message;
        # forcing inflight=0 here too would double-count and corrupt the next turn's release. The snapshot
        # reads 'waiting' while inflight>0 (kills the 2026-06-23 zombie-working); a truly-wedged turn that
        # never results keeps inflight>0 and PAUSES the queue — honest (kill recovers). A fresh turn clears
        # _interrupted (see inputs()), and the ResultMessage clears it too.
        self._interrupted = True
        self.backend._poke()
        try:
            await self.client.interrupt()
        except Exception:
            pass

    async def _do_set_model(self, model):
        try:
            await self.client.set_model(model)
        except Exception:
            pass

    async def _do_set_mode(self, mode):
        try:
            await self.client.set_permission_mode(mode)
        except Exception:
            pass

    async def _do_refresh_context(self):
        """Pull authoritative context-window usage from the SDK — the DESIGNED source. `get_context_usage()` is
        the SDK's native control request behind the CLI's `/context`: it returns a `percentage` already computed
        against the real window AND the autocompact buffer, plus the live model id. This replaces inferring the
        window from peak prompt sizes (the user 2026-06-24: the SDK read 14% where tmux read 3% on a 1M-context
        model — a wrong-window guess). Updates the live % + model and persists both (so a dormant / restarted
        session keeps showing them). Cheap; guarded so only one is in flight."""
        if not self.client or self._ctx_refreshing:
            return
        self._ctx_refreshing = True
        try:
            cu = await self.client.get_context_usage()
        except Exception:
            cu = None
        finally:
            self._ctx_refreshing = False
        if not isinstance(cu, dict):
            return
        changed = False
        pct = cu.get("percentage")
        if isinstance(pct, (int, float)):
            v = max(0, min(100, round(pct)))
            if v != self._ctx:
                self._ctx, changed = v, True
        pm = pretty_model(cu.get("model"))
        if pm and pm != self.model:
            self.model, changed = pm, True
        upd = {}
        if self.model:
            upd["liveModel"] = self.model
        if self._ctx is not None:
            upd["liveCtx"] = self._ctx
        if upd:
            try:
                self.backend._update_reg(self.sid, **upd)
            except Exception:
                pass
        if changed:
            self.backend._poke()

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
        self._wake = asyncio.Event()
        with self._lock:
            self._input_wake = asyncio.Event()
            self._ready.set()
        # Turns enqueued before the loop was ready are already in self._pending; the input
        # generator below picks them up on its first pass (no separate pre-buffer needed).

        async def inputs():
            # Forward queued turns to the SDK AS SOON AS they're available — even while a turn is in flight —
            # so a message you send mid-turn reaches the model at its NEXT tool boundary instead of being held
            # until the whole turn finishes (the user 2026-06-27: "forward it in as soon as you can, that's
            # what I do with a queued message"). The CLI's streaming input owns the boundary timing; romp just
            # stops artificially holding. EXCEPTION: when the current turn is INTERRUPTED/wedged (inflight>0
            # AND _interrupted), HOLD the queue — feeding the next turn into a stuck CLI is the double-count /
            # zombie hazard the interrupt path guards against; it releases once that turn's ResultMessage
            # settles inflight to 0. Recreated per reconnect; self._pending carries unstarted turns across it.
            while not self.ended:
                self._input_wake.clear()
                with self._lock:
                    blocked = self.inflight > 0 and self._interrupted   # wedged turn → don't feed a stuck CLI
                    item = self._pending.pop(0) if (self._pending and not blocked) else None
                    fresh = item is not None and self.inflight == 0     # starting from idle, not mid-turn
                if item is None:
                    await self._input_wake.wait()   # idle, or holding behind a wedged turn → wait for a change
                    continue
                if fresh:
                    self.since = int(time.time())    # a new turn starts now (mid-turn forwards keep the turn's clock)
                    self._interrupted = False        # a fresh turn → clear any stale interrupt flag
                self.inflight += 1
                append_state(self.backend.state_dir, self.sid, "working")
                self.backend._poke()
                yield {"type": "user",
                       "message": {"role": "user", "content": [{"type": "text", "text": item}]}}

        async def drain(client):
            # Feed turns and receive messages CONCURRENTLY: query() with a streaming input iterable BLOCKS
            # until the iterable ends (it writes each turn to stdin), and our input generator never ends —
            # so awaiting it before receiving would starve the receive loop. The control channel
            # (can_use_tool) has its own reader; the message stream does not, so it's drained here.
            async for msg in client.receive_messages():
                if self.ended:
                    break
                self._on_message(msg, AssistantMessage, ResultMessage, SystemMessage)

        # Reconnect loop: one persistent client per iteration. A connect-time option change (effort, a CLI
        # flag with no runtime control) reconnects with fresh options — resume_sid continues the conversation
        # and self._pending carries any not-yet-started turns. The receive loop is RACED against a wake Event so it stops
        # cleanly for BOTH shutdown and reconnect even when idle (a bare async-for would block forever with no
        # incoming message, leaking the client + its claude subprocess).
        while not self.ended:
            self._wake.clear()
            self._reconnect = False
            # RECONCILE INFLIGHT ACROSS A RECONNECT (the user 2026-07-01: "switch the model on a new session
            # → it says working indefinitely"). A reconnect abandons the previous client; a turn it left in
            # flight can NEVER get its ResultMessage on the new connection (that client, and its receive loop,
            # are gone) — so inflight, and the "working" signal it drives, would be stranded elevated FOREVER.
            # request_reconnect defers while inflight>0, but a race (it fired at inflight==0, then the input
            # generator started a turn before the teardown ran) can still leave a turn stranded here. At the
            # TOP of the loop no client is connected, so nothing can legitimately be in flight: settle it to
            # idle. A not-yet-STARTED _pending turn survives (it was never fed to the dead client) and the new
            # inputs() re-feeds it, re-stamping "working". No-op on the first connect and on a clean reconnect
            # (inflight already 0). Event-based on the reconnect itself, not a time/age heuristic.
            if self.inflight:
                self.inflight = 0
                self._interrupted = False
                append_state(self.backend.state_dir, self.sid, "waiting")
                self.backend._poke()
            opts = self.backend._options(self, ClaudeAgentOptions)
            async with ClaudeSDKClient(options=opts) as client:
                self.client = client
                # PRE-TURN PUBLISH (the user 2026-06-27): pull the live model + context % the INSTANT we
                # connect — before any turn — so a freshly-created SDK session shows its model and context on
                # OPEN, like a tmux session does on launch. The old path keyed model/ctx resolution off the
                # `init` SystemMessage (see _on_message's init branch), but that message is NOT emitted on a
                # turn-less streaming connection: it only arrives with the FIRST user turn (verified against the
                # SDK — get_context_usage() answers pre-turn, but no init/system message streams until a turn is
                # sent). That false assumption is why every prior fix left the model/context blank until the
                # first message. get_context_usage() is the DESIGNED control request behind the CLI's /context
                # and returns BOTH the live model id and the % pre-turn, so this one refresh fills both. Runs on
                # every (re)connect; guarded + idempotent + pokes only on change.
                asyncio.ensure_future(self._do_refresh_context())
                feeder = asyncio.ensure_future(client.query(inputs()))
                recv = asyncio.ensure_future(drain(client))
                waker = asyncio.ensure_future(self._wake.wait())
                try:
                    await asyncio.wait({recv, waker}, return_when=asyncio.FIRST_COMPLETED)
                finally:
                    for tk in (feeder, recv, waker):
                        tk.cancel()
                    for tk in (feeder, recv, waker):
                        try:
                            await tk
                        except asyncio.CancelledError:
                            pass
                        except Exception as e:                 # a genuine stream/transport error — surface it
                            self.backend._log(f"sdk session {self.name}: {type(e).__name__}: {e}")
                    self.client = None
            if self.ended or not self._reconnect:
                break        # drain ended on its own (process exit) or we're shutting down → done

    def _learn_model(self, pm):
        """Record a freshly-observed display model (from the init message or an assistant turn). Updates the
        live value AND persists it to the registry as `liveModel`, so a DORMANT / post-restart session still
        shows its model via live_sessions' registry path — the registry's `model` field is the user's CHOSEN
        alias, which is absent for a default-model session, so without this the badge (and, on the timeline,
        the effort too) goes blank whenever the session isn't actively running (the user 2026-06-24). Pokes a
        push so the badge updates promptly. No-op when unchanged, so it doesn't rewrite the reg every turn."""
        if not pm or pm == self.model:
            return
        self.model = pm
        try:
            self.backend._update_reg(self.sid, liveModel=pm)
        except Exception:
            pass
        self.backend._poke()

    def _ctx_pct(self):
        """Current context-window fill %, as the SDK reports it via get_context_usage() — the same number the
        CLI's `/context` shows (it already divides by the real window and accounts for the autocompact buffer;
        we no longer guess the window). Refreshed on connect/init and after every turn by _do_refresh_context.
        None until the first refresh lands."""
        return self._ctx

    def _on_message(self, msg, AssistantMessage, ResultMessage, SystemMessage):
        if isinstance(msg, SystemMessage) and msg.subtype == "init":
            d = msg.data if isinstance(msg.data, dict) else {}
            self._learn_model(pretty_model(d.get("model")))
            self.perm_mode = d.get("permissionMode") or self.perm_mode
            fsid = d.get("session_id")
            if fsid and fsid != self.resume_sid:
                self.resume_sid = fsid
                self.backend._update_reg(self.sid, lastSid=fsid)
            self.backend._poke()   # publish the model + permission-mode from init promptly: the snapshot reads
                                   # self.model, but with no poke the new model would wait out the 3s producer
                                   # backstop. NB: this init branch fires only once the FIRST turn arrives — the
                                   # CLI emits no init message on a turn-less connect — so the PRE-turn publish
                                   # is _amain's on-connect _do_refresh_context() (get_context_usage); this is
                                   # the refinement once a real turn lands.
            asyncio.ensure_future(self._do_refresh_context())   # re-pull the real context % + model from the SDK
        elif isinstance(msg, SystemMessage) and msg.subtype == "compact_boundary":
            # Compaction just landed: the active context dropped to the summary. Re-pull the % NOW, on the
            # boundary event itself, rather than waiting for the next turn's ResultMessage — the CLI auto-runs
            # a continuation turn after /compact that can work for minutes, and until it settled the bar kept
            # showing the STALE pre-compaction % (the user 2026-06-30: "I compacted but it still says 72%").
            # get_context_usage() reads current state, so it reports the post-compaction number here.
            asyncio.ensure_future(self._do_refresh_context())
        elif isinstance(msg, SystemMessage) and msg.subtype == "api_retry":
            # the API returned a retryable error (rate-limit / overload); the CLI is backing off + retrying.
            # Surface a distinct 'retrying' state so a stall reads as an API issue, not a silent hang (the
            # user 2026-06-23). Cleared the moment real output flows again (assistant text / result).
            self.retrying = True
            append_state(self.backend.state_dir, self.sid, "retrying")
            self.backend._poke()
        elif isinstance(msg, AssistantMessage):
            self.retrying = False                      # real output is flowing → the API recovered
            m = getattr(msg, "model", None)
            # Only adopt a REAL model id. Injected / synthetic assistant turns carry model="<synthetic>" (and
            # the CLI writes it to the transcript too); pretty_model passes unrecognised ids through verbatim,
            # so an unguarded assign would CORRUPT the model badge to "<synthetic>". A real id always contains
            # "claude" (claude-opus-4-8, us.anthropic.claude-…); keep the last good one otherwise.
            if m and "claude" in m.lower():
                self._learn_model(pretty_model(m))
        elif isinstance(msg, ResultMessage):
            self.retrying = False
            self._interrupted = False              # this turn's result settled it (whether it finished or was interrupted)
            self.inflight = max(0, self.inflight - 1)
            if self.inflight == 0:
                append_state(self.backend.state_dir, self.sid, "waiting")
                asyncio.ensure_future(self._do_refresh_context())   # refresh ctx % + model from the SDK and
                #   persist them, so the bar reflects the turn that just landed and survives idle/restart.
                self.backend._poke()
                if self._input_wake is not None:   # turn done → release the next queued turn, if any
                    self._input_wake.set()
                if self._reconnect_when_idle and not self.ended:   # an effort change waited for this turn to end
                    self._reconnect_when_idle = False
                    self._reconnect = True
                    self._wake_set()
        elif getattr(msg, "rate_limit_info", None) is not None:
            # A RateLimitEvent: the account-wide /usage limits (5h + weekly) the CLI streams when the limit state
            # changes — the SDK's designed source for the rail usage bars. Duck-typed (no SDK-type import needed).
            info = msg.rate_limit_info
            # CADENCE INSTRUMENTATION (the user 2026-07-01, TEMPORARY): before dropping the usage.json/statusline
            # path in favor of reading the SDK's in-memory rate-limit state, measure how OFTEN these events
            # actually arrive. The SDK docs say they fire only on status TRANSITIONS (sparse) — if that's true,
            # event-only can't keep the 5h bar live as usage climbs and we'll need a staleness cue; if they
            # actually arrive ~per-turn, the in-memory-SDK design is fully fresh. One jsonl line per arrival →
            # analyze the real frequency, then remove this. Best-effort; never disturbs the stream.
            try:
                with open(self.backend.state_dir / "rate-limit-events.jsonl", "a") as _f:
                    _f.write(json.dumps({"t": int(time.time()), "sid": self.sid, "name": self.name,
                                         "type": getattr(info, "rate_limit_type", None),
                                         "util": getattr(info, "utilization", None),
                                         "status": getattr(info, "status", None),
                                         "resets_at": getattr(info, "resets_at", None)}) + "\n")
            except Exception:
                pass
            self.backend._record_rate_limit(info)
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
        if tool_name == "ExitPlanMode":
            return await self._approve_plan(tool_input)
        # Ordinary tool permission. Options are Allow (1), optionally Allow-&-don't-ask-again (2 when the
        # SDK supplied permission suggestions), then Deny (last). _next_ask_action returns the chosen
        # ordinal so we map it back to the action here.
        ask = permission_to_live(tool_name, tool_input, context)
        remember_n = 2 if getattr(context, "suggestions", None) else None
        append_state(self.backend.state_dir, self.sid, "permission")
        self.backend._emit_ask(self, ask)
        decision = "deny"
        try:
            while True:
                kind, payload = await self._next_ask_action()
                if kind == "answer":
                    n = str(payload)
                    decision = "allow" if n == "1" else "remember" if n == str(remember_n) else "deny"
                    break
                if kind == "cancel":
                    decision = "deny"
                    break
        finally:
            self.backend._clear_ask(self)
            if self.inflight:
                append_state(self.backend.state_dir, self.sid, "working")
        if decision == "remember":
            return PermissionResultAllow(behavior="allow", updated_permissions=list(context.suggestions))
        if decision == "allow":
            return PermissionResultAllow(behavior="allow")
        return PermissionResultDeny(behavior="deny", message="Denied by user.", interrupt=False)

    async def _approve_plan(self, tool_input: dict):
        """Plan-mode approval (ExitPlanMode): show the PLAN itself, not a bare 'Allow ExitPlanMode?'.
        Options: proceed (exit plan mode), proceed + auto-accept edits (also flip the session into
        acceptEdits via a setMode permission update), or keep planning (deny → stay in plan mode).
        (the user 2026-06-27.)"""
        from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny, PermissionUpdate
        pv = tool_preview("ExitPlanMode", tool_input)
        ask = {
            "kind": "single", "header": "Plan ready",
            "question": "Proceed with this plan?",
            "options": [
                {"n": 1, "label": "Yes, proceed", "desc": "Exit plan mode and start", "selected": False},
                {"n": 2, "label": "Yes, auto-accept edits",
                 "desc": "Proceed and don't prompt for each edit", "selected": False},
                {"n": 3, "label": "No, keep planning", "desc": "Stay in plan mode", "selected": False},
            ],
            "multiSelect": False, "cursor": 0, "cursorFound": True, "permission": True,
        }
        if pv:
            ask["previewKind"], ask["preview"] = pv[0], pv[1]
        append_state(self.backend.state_dir, self.sid, "permission")
        self.backend._emit_ask(self, ask)
        choice = "3"
        try:
            while True:
                kind, payload = await self._next_ask_action()
                if kind == "answer":
                    choice = str(payload); break
                if kind == "cancel":
                    choice = "3"; break
        finally:
            self.backend._clear_ask(self)
            if self.inflight:
                append_state(self.backend.state_dir, self.sid, "working")
        if choice == "1":
            return PermissionResultAllow(behavior="allow")
        if choice == "2":
            return PermissionResultAllow(behavior="allow",
                                         updated_permissions=[PermissionUpdate(type="setMode", mode="acceptEdits")])
        return PermissionResultDeny(behavior="deny", message="Keep planning.", interrupt=False)

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
        nreal = len(question.get("options") or [])
        selected: set[int] = set()
        customs: list[str] = []                       # free-text answers the user typed (multi accumulates)
        def emit():
            self.backend._emit_ask(self, ask_question_to_live(question, qi, total, selected, customs))
        emit()
        while True:
            kind, payload = await self._next_ask_action()
            if kind == "cancel":
                raise _AskCancelled()
            if kind in ("custom", "text") and payload:
                if not multi:
                    return str(payload)               # single-select: the typed answer IS the answer
                customs.append(str(payload)); emit(); continue   # multi: add it, keep going until Submit
            if not multi and kind == "answer":
                return label_for_target(question, payload)
            if multi and kind == "toggle":
                try:
                    n = int(payload)
                except (TypeError, ValueError):
                    n = -1
                if 1 <= n <= nreal:
                    selected.discard(n) if n in selected else selected.add(n)
                elif nreal < n <= nreal + len(customs):   # unchecking a typed custom row removes it
                    del customs[n - nreal - 1]
                emit(); continue
            if multi and kind == "submit":
                return [label_for_target(question, n) for n in sorted(selected)] + customs
            # single-select that received a toggle, or vice versa: re-emit.
            emit()

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

    # ---- subagent tracking (the transparency tmux never had) ----

    async def _subagent_start_hook(self, inp, tool_use_id, context):
        """A Task-spawned subagent just STARTED. Record it live (agent_id -> type + start time) so the session
        reads 'working' while it runs and the lane can show how many are in flight. The SDK's SubagentStart
        hook input carries agent_id + agent_type. Best-effort; never raises inside the hook."""
        aid = inp.get("agent_id") if isinstance(inp, dict) else None
        if aid:
            with self._sub_lock:
                self._subagents[aid] = {"type": (inp.get("agent_type") or ""), "since": int(time.time())}
            self.backend._poke()
        return {}

    async def _subagent_stop_hook(self, inp, tool_use_id, context):
        """A Task-spawned subagent FINISHED — drop it from the live set (SubagentStop carries the same agent_id).
        When the last one clears, the session falls back to its real state (working if the main turn is still in
        flight, else idle)."""
        aid = inp.get("agent_id") if isinstance(inp, dict) else None
        if aid:
            with self._sub_lock:
                self._subagents.pop(aid, None)
            self.backend._poke()
        return {}

    def _live_subagents(self) -> list:
        """The Task subagents running RIGHT NOW: [{"type","since"}], oldest first. Copied under the lock (hooks
        mutate on the loop thread; snapshot() reads on the kernel thread)."""
        with self._sub_lock:
            return sorted((dict(v) for v in self._subagents.values()), key=lambda d: d.get("since") or 0)

    # ---- snapshot for live_sessions() ----

    def snapshot(self) -> dict:
        # Parked in can_use_tool/_ask_user waiting on the USER (a permission Allow/Deny or an
        # AskUserQuestion picker)? The turn stays inflight through that wait, so reporting "working" made
        # the feed/timeline miss it — the kernel floors a card to BLOCKED off the live "permission"/"picker"
        # state, exactly as it does for tmux (the user 2026-06-27: an SDK AskUserQuestion didn't register as
        # blocked the way tmux's does). _pending_ask is set for the whole ask (both kinds), and the ask
        # handlers append the needs-input state BEFORE raising it, so last_state is authoritative here.
        parked = self.backend._pending_ask.get(self.sid) is not None
        subs = self._live_subagents()
        if self.inflight > 0 and not parked:
            # actively producing. A user interrupt shows 'waiting' (stopped) even though inflight stays 1
            # until the aborted turn's ResultMessage settles it — see _do_interrupt. A synchronous Task keeps
            # the main turn in flight, so this branch already reads 'working' the whole time it runs.
            state = "waiting" if self._interrupted else ("retrying" if self.retrying else "working")
            since = self.since
        elif subs and not parked and not self._interrupted:
            # The main turn settled (inflight 0) but a Task subagent is still running — a BACKGROUNDED one that
            # outlives the turn. The session IS still working; surface that instead of idling to 'waiting' (the
            # user 2026-06-30: "mark it working when it has subagents running"). Clears itself when the last
            # SubagentStop lands and the set empties.
            state, since = "working", (min((s.get("since") or 0) for s in subs) or self.since)
        else:
            ls = last_state(self.backend.state_dir, self.sid)
            state, since = ls.get("state") or "waiting", ls.get("t") or 0
        return {"state": state, "since": str(since) if since else "",
                "model": model_label(self.model, self.chosen_model), "effort": self.effort,
                "mode": self.perm_mode, "ctx": self._ctx_pct(), "summary": "",
                "subagents": subs}   # live Task subagents (count + types) → lane affordance; [] when none


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
        self._rl: dict[str, dict] = {}            # rate_limit_type -> {"pct","resets_at"}: account-wide /usage
        self._rl_lock = threading.Lock()          #   windows the CLI streams as RateLimitEvents (_record_rate_limit)
        # Kernel-restart heal: nothing is running yet, so any alive session still reading awaiting:true is stale
        # — its background tasks (and the Stop hook that clears the overlay) died with the previous kernel. Left
        # uncleared it reads working/awaiting forever, climbing a ghost work-timer (reorder_bug 2026-06-24).
        for reg in list_regs(self.state_dir):
            if reg.get("alive"):
                self._heal_stale_awaiting(reg["sid"])
        # NOTE: we deliberately do NOT heal a stale in-flight STATE ("working"/…) on restart. A session whose
        # turn was killed by the kernel restart (e.g. the user hit Refresh mid-turn) keeps its last "working" in
        # the log, so the auto-nudge GENUINE-STOP GATE (_last_state_value in _PROGRESSING_STATES) correctly SKIPS
        # it — it was interrupted, not stopped, and must not be nudged (the user 2026-06-29: refresh was nudging
        # in-progress sessions). A session that genuinely FINISHED a turn before the restart already logged
        # "waiting" (ResultMessage), so it stays nudge-eligible. The dormant in-flight→waiting DISPLAY heal lives
        # independently in live_sessions, so the feed/fleet still render dormant sessions as waiting.

    def _heal_stale_awaiting(self, sid: str) -> None:
        """Clear a stale awaiting:true overlay for a NOT-running session. A dormant SDK session can't have live
        background tasks — its claude subprocess (and the Stop hook that would write awaiting:false) is gone — so
        a lingering awaiting:true is stale. Idempotent: writes only when the overlay is currently true, so it
        never spams the log. The exact event-based analogue of live_sessions' dormant in-flight→waiting heal."""
        try:
            if last_awaiting(self.state_dir, sid) is True:
                append_awaiting(self.state_dir, sid, False)
        except Exception:
            pass

    def _record_rate_limit(self, info) -> None:
        """Persist the account-wide rate-limit /usage the CLI streams as a RateLimitEvent — the SDK's DESIGNED
        source for the rail's usage bars (the user 2026-06-30). Each event carries ONE window's utilization
        (0.0-1.0) + resets_at; we accumulate the windows and write the SAME usage.json the tmux statusline
        writes (account-wide, latest writer wins), so the bars stay fresh for SDK sessions that have NO tmux
        statusline. Event-based, not polled: the CLI emits it whenever the limit state changes — get_context_usage()
        is the CONTEXT window, a different number. `info` is a duck-typed RateLimitInfo (rate_limit_type /
        utilization / resets_at)."""
        rlt = getattr(info, "rate_limit_type", None)
        if rlt not in ("five_hour", "seven_day", "seven_day_opus", "seven_day_sonnet"):
            return   # the bars show only the 5h + weekly windows; overage / None are ignored
        util = getattr(info, "utilization", None)
        if not isinstance(util, (int, float)):
            return
        ra = getattr(info, "resets_at", None)
        seg = {"pct": max(0, min(100, round(util * 100))),
               "resets_at": int(ra) if isinstance(ra, (int, float)) else None}
        with self._rl_lock:
            self._rl[rlt] = seg
            rl = dict(self._rl)
        def pick(*types):
            segs = [rl[t] for t in types if t in rl]
            return max(segs, key=lambda s: s["pct"]) if segs else None   # weekly = the binding (highest) window
        five, seven = pick("five_hour"), pick("seven_day", "seven_day_opus", "seven_day_sonnet")
        # NEVER null a window this backend hasn't seen an event for — usage.json is account-wide and ALSO
        # written by the tmux statusline (and by earlier events); each event carries ONE window, so writing the
        # whole file from our partial accumulator would clobber the other window to null (the user 2026-06-30:
        # "the session limit disappeared" — a seven_day event nulled the statusline's five_hour). Merge with the
        # current file: overwrite only the window(s) we actually have, preserve the rest.
        try:
            cur = json.loads((self.state_dir / "usage.json").read_text())
            if not isinstance(cur, dict):
                cur = {}
        except Exception:
            cur = {}
        # PREFER THE FRESHER READING PER WINDOW — never let this backend's data clobber a fresher value in the
        # file (the user 2026-07-01: /usage read 5h=69% but the rail showed 0%). The statusline writes the CLI's
        # current rate_limits on every render (always fresh); this backend only sees the transition-gated
        # RateLimitEvent (the CLI emits it on a status change — allowed↔warning↔rejected — NOT on a plain
        # utilization reset), so our five_hour can be hours stale. Freshness is authoritative, not a heuristic:
        # a LATER resets_at is a newer window, and WITHIN a window utilization only climbs (it drops only at the
        # reset, which advances resets_at), so a higher pct is the more recent reading; an EXPIRED window
        # (resets_at already passed) loses to any live one. So an SDK seven_day event can no longer drag a stale
        # five_hour back over the statusline's fresh one.
        now_ = int(time.time())
        def fresher(a, b):
            if not a:
                return b
            if not b:
                return a
            ra_a = a.get("resets_at") if isinstance(a.get("resets_at"), (int, float)) else None
            ra_b = b.get("resets_at") if isinstance(b.get("resets_at"), (int, float)) else None
            live_a, live_b = (ra_a is not None and ra_a > now_), (ra_b is not None and ra_b > now_)
            if live_a != live_b:                                  # a live window beats an expired/undated one
                return a if live_a else b
            if ra_a is not None and ra_b is not None and ra_a != ra_b:
                return a if ra_a > ra_b else b                    # newer window (later reset) wins
            return a if (a.get("pct") or 0) >= (b.get("pct") or 0) else b   # same window → higher (later) usage
        five = fresher(five, cur.get("five_hour"))
        seven = fresher(seven, cur.get("seven_day"))
        if not five and not seven:
            return
        data = {"t": int(time.time()), "five_hour": five, "seven_day": seven}
        try:
            tmp = self.state_dir / "usage.json.tmp"
            tmp.write_text(json.dumps(data))
            os.replace(tmp, self.state_dir / "usage.json")
            self._poke()   # nudge the producer so the rail re-reads usage.json promptly, not on the next backstop
        except Exception:
            pass

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
        kw = dict(
            cli_path=self.claude_bin,
            cwd=sess.cwd,
            can_use_tool=sess._can_use_tool,
            hooks={"Stop": [HookMatcher(matcher=None, hooks=[sess._stop_hook])],          # awaiting overlay producer
                   "SubagentStart": [HookMatcher(matcher=None, hooks=[sess._subagent_start_hook])],  # live subagent
                   "SubagentStop": [HookMatcher(matcher=None, hooks=[sess._subagent_stop_hook])]},    #   count/types
            permission_mode=sess.mode,
            include_partial_messages=False,
            effort=sess.effort or DEFAULT_EFFORT,   # connect-time --effort (no runtime control); a change reconnects
        )
        # romp's harness prompt is APPENDED via the SDK's DESIGNED system_prompt field — the Claude Code preset
        # plus an `append` (types.py SystemPromptPreset) — NOT extra_args={"append-system-prompt"}. Same effect
        # (append to the default Claude Code system prompt) but it's the typed, documented option; extra_args is
        # the SDK's last-resort passthrough for CLI flags that have NO field, which this one does (the user
        # 2026-06-24: implement things the way the SDK designed them, not via raw-flag escape hatches).
        if self.append_prompt_path and os.path.exists(self.append_prompt_path):
            try:
                kw["system_prompt"] = {"type": "preset", "preset": "claude_code",
                                       "append": Path(self.append_prompt_path).read_text()}
            except OSError:
                pass
        if sess.chosen_model and sess.chosen_model != "default":
            kw["model"] = sess.chosen_model    # keep the picked model across a reconnect (runtime set_model is per-connection)
        if sess.resume_sid:
            kw["resume"] = sess.resume_sid
        else:
            kw["session_id"] = sess.sid
        if self.mcp_config:
            kw["mcp_servers"] = self.mcp_config
        return ClaudeAgentOptions(**kw)

    # ---- lifecycle (kernel-thread API) ----
    def spawn(self, name: str, cwd: str, bg: str = "", fg: str = "", sid: str | None = None) -> str:
        sid = sid or str(uuid.uuid4())
        cwd = os.path.realpath(cwd) if os.path.exists(cwd) else cwd
        if not bg:                                   # give the session a stable identity colour like tmux sessions get
            bg, fg = pick_identity_color(sid)
        write_name(self.state_dir, sid, name, cwd, bg, fg)
        # Seed model + effort from the REMEMBERED defaults (the user's last pick on any session), falling back
        # to the hardcoded ones (the user 2026-06-27). effort always has a value (the connect flag). A model is
        # recorded ONLY when a real choice was remembered: an unset / 'default' model stays the account default
        # (model_label + _options both treat '' and 'default' as "no override"), and the real default name still
        # fills in on connect from get_context_usage(). The seed lands in THIS session's reg — exactly what
        # _options launches with and what the badge reads — so the display can never desync from what's used.
        d = read_sdk_defaults(self.state_dir)
        eff = d.get("effort") if d.get("effort") in EFFORT_LEVELS else DEFAULT_EFFORT
        mode = d.get("mode") or "acceptEdits"   # seed the permission mode from the remembered default too (the user 2026-06-27)
        reg = {"sid": sid, "name": name, "cwd": cwd, "mode": mode,
               "effort": eff, "lastSid": "", "alive": True}
        if d.get("model") and d["model"] != "default":
            reg["model"] = d["model"]
        write_reg(self.state_dir, sid, reg)
        append_state(self.state_dir, sid, "waiting")
        self._poke()
        return sid

    def resume(self, name: str, sid: str, cwd: str | None = None) -> bool:
        reg = read_reg(self.state_dir, sid) or {}
        cwd = cwd or reg.get("cwd") or os.path.expanduser("~")
        write_reg(self.state_dir, sid, {"sid": sid, "name": name, "cwd": cwd,
                                        "mode": reg.get("mode", "acceptEdits"),
                                        "effort": reg.get("effort", DEFAULT_EFFORT),
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

    def connect(self, sid: str) -> bool:
        """Eagerly start (connect) a session WITHOUT sending a turn, so its model + context % publish right
        away — like a tmux session shows them on launch — instead of only after the first message (the user
        2026-06-23). The streaming `init` SystemMessage does NOT arrive until the first turn, so _amain pulls
        the model + % on connect via get_context_usage() (the designed control request that answers pre-turn);
        permission-mode shows the registry default immediately, refined by init once a turn lands. Idempotent;
        a no-op if already running."""
        return self._ensure(sid) is not None

    def pending_queued(self, sid: str) -> list[str]:
        """Queued-but-not-yet-started user turns for an SDK session (oldest first), or [] if the
        session isn't SDK-backed / not running. The kernel calls this to build the chat's
        kind:"queued" event for SDK sessions — the SDK keeps its queue in memory, so there are no
        transcript queue-operation records for _pending_queued to read."""
        with self._lock:
            s = self.sessions.get(sid)
        return s.pending() if s else []

    def unqueue(self, sid: str, idx: int) -> str | None:
        """Cancel the queued turn at `idx` for an SDK session (the kernel's cancelQueued route). Returns
        its text, or None. tmux has no equivalent (its queue lives in Claude Code), so only SDK sessions
        expose this — the kernel gates the chat's cancel affordance on the backend having `unqueue`.

        ALSO drops the message's optimistic echo from the live tail: send() adds a blue 'you' bubble that
        normally prunes when the real user atom lands in the transcript — but a CANCELED message never
        lands, so without this the echo lingered and the canceled message kept rendering as 'sent' even
        though it wasn't (the user 2026-06-27)."""
        with self._lock:
            s = self.sessions.get(sid)
        if not s:
            return None
        text = s.unqueue(idx)
        if text is not None:
            live = self._live.get(sid) or {}
            for k, a in list(live.items()):                # snapshot: the live-tail thread may mutate concurrently
                if a.get("_echo_text") == text:
                    live.pop(k, None)                      # one echo per canceled message
                    break
            self._wake_push()                              # repaint without the echo so it stops reading as sent
        return text

    def send(self, sid: str, text: str) -> bool:
        s = self._ensure(sid)
        if not s:
            return False
        s.enqueue(text)
        # optimistic input echo: show the user's own message INSTANTLY (neither the transcript nor the
        # stream has it yet at send time — only we know the text). Synthetic uuid; pruned by text once the
        # transcript writes the real user atom.
        key = "echo:" + uuid.uuid4().hex
        # AUTHOR the echo from the romp markers, exactly as the event model authors the REAL atom — else a
        # romp-injected nudge/auto-nudge sent through send() echoed as a BLUE HUMAN bubble (a "Follow-up"),
        # not the GRAY "from romp" auto-nudge it is, until the transcript atom replaced it (the user
        # 2026-06-28). romp-injected → author 'romp'; romp-auto → the romp-logo (rompAuto) marker.
        injected = "romp-injected" in text
        echo = {
            "type": "user", "uuid": key, "session_id": sid, "t": int(time.time()), "parentUuid": None,
            "author": "romp" if injected else "human", "_echo_text": text,
            "message": {"role": "user", "content": [{"type": "text", "text": text}]}}
        if injected and "romp-auto" in text:
            echo["rompAuto"] = True                          # auto-nudge → romp-logo on the chat/timeline
        self._live.setdefault(sid, {})[key] = echo
        self._wake_push()
        return True

    def deliver(self, sid: str, text: str) -> bool:
        """Deliver-time wake for an SDK session: enqueue the postal banner so the session processes it on its
        next turn — the SDK analogue of the tmux pane-inject (the user 2026-06-26). NO optimistic human echo:
        it's a peer's mail, not the user's composer input; the transcript records it and the chat renders it as
        a postal card. True if the session is live/resumable (so the bus consumed the maildir copy), else False
        (the bus keeps it for the drain backstop)."""
        s = self._ensure(sid)
        if not s:
            return False
        s.enqueue(text)
        self._poke()
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

    def set_model(self, sid: str, value: str) -> bool:
        """Change the session's model. Persisted in the registry (so a reconnect keeps it) and applied
        LIVE on a connected session via the SDK control channel — NOT a /model slash injection, which the
        SDK input stream does not interpret. 'default' resets to the CLI default (set_model(None))."""
        reg = read_reg(self.state_dir, sid)
        if not reg:
            return False
        reg["model"] = value
        write_reg(self.state_dir, sid, reg)
        write_sdk_default(self.state_dir, model=value)   # remember as the seed for the NEXT new session (the user 2026-06-27)
        s = self.sessions.get(sid)
        if s:
            s.chosen_model = value
            s.model = value.capitalize()   # immediate label feedback ("Opus"); next assistant turn republishes "Opus 4.8"
            s.set_model_live(None if value in ("", "default") else value)
        return True

    def set_mode(self, sid: str, mode: str) -> bool:
        """Change the permission mode. Persisted in the registry and applied LIVE via the SDK control
        channel (set_permission_mode) — not merely stored for the next reconnect."""
        reg = read_reg(self.state_dir, sid)
        if not reg:
            return False
        reg["mode"] = mode
        write_reg(self.state_dir, sid, reg)
        write_sdk_default(self.state_dir, mode=mode)   # remember as the seed for the NEXT new session, like model/effort (the user 2026-06-27)
        s = self.sessions.get(sid)
        if s:
            s.mode = mode
            s.perm_mode = mode      # snapshot reflects it immediately (clears the picker's meta-pending)
            s.set_mode_live(mode)
        return True

    def set_effort(self, sid: str, value: str) -> bool:
        """Change the reasoning effort. effort is a connect-time CLI flag (--effort) with no SDK runtime
        control, so this persists it and RECONNECTS to apply (resume continues the conversation): immediately
        if the session is idle, at the end of the current turn if it's busy. The label updates at once."""
        if value not in EFFORT_LEVELS:
            return False
        reg = read_reg(self.state_dir, sid)
        if not reg:
            return False
        reg["effort"] = value
        write_reg(self.state_dir, sid, reg)
        write_sdk_default(self.state_dir, effort=value)   # remember as the seed for the NEXT new session (the user 2026-06-27)
        s = self.sessions.get(sid)
        if s:
            s.effort = value        # picker label reflects it now; the reconnect makes it real
            s.request_reconnect()
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
                st = ls.get("state") or "waiting"
                # A NOT-running (dormant, resumable) SDK session can't actually be mid-turn: after a kernel
                # restart its thread is gone, but the state log still reads its last in-flight state
                # ("working"/"permission"/"picker"/…). Reporting that verbatim makes a dormant session look
                # FALSELY blocked/working with NO live ask to resolve it — the prompt died with the thread (the
                # user 2026-06-24: reorder_bug showed "blocked, needs approval" with no prompt after a refresh).
                # Map any in-flight state → "waiting", the true state of a dormant session (it resumes on the
                # next drive). A GENUINELY-blocked session is RUNNING → snapshot() above (with a real
                # current_ask), so it's unaffected. Keyed on thread-not-running, not a time heuristic.
                if st in ("working", "permission", "picker", "compacting", "retrying"):
                    st = "waiting"
                lc = reg.get("liveCtx")   # last persisted context fill → bar survives idle/restart
                out[sid] = {"state": st,
                            "since": str(ls.get("t") or ""),
                            # not running (e.g. post-restart): prefer the last LIVE model we persisted
                            # (liveModel), else the chosen alias — so the badge isn't blank while dormant.
                            "model": model_label(reg.get("liveModel") or "", reg.get("model") or ""),
                            "effort": reg.get("effort", ""),
                            "mode": reg.get("mode", ""),
                            "ctx": lc if isinstance(lc, (int, float)) else "", "summary": ""}
        return out

    # ---- picker/permission UI bridge (kernel-thread API) ----
    def on_ask(self, sid: str, kind: str, payload=None) -> bool:
        """Route an inbound picker action (answer/toggle/submit/custom/cancel/text)
        to the SDK session's waiting callback. Returns False if not SDK-backed."""
        s = self.sessions.get(sid)
        if not s:
            return False
        if kind == "focus":
            return True   # ↑/↓ preview-step: SDK options carry their OWN preview, so the webview swaps it
                          # locally — there's no TUI cursor to drive, and it must NOT resolve the ask.
        s.resolve_ask(kind, payload)
        return True

    # ---- callbacks used by sessions ----
    def _emit_ask(self, sess: SdkSession, ask: dict):
        # STORE the ask (not just a bool): the kernel's _ask_poll replays it to chat clients each tick, so a
        # blocked SDK session still shows its prompt to a client that connects/refocuses/reloads AFTER the ask
        # was raised — the durable replay tmux gets from pane-scraping. The immediate push below is just for
        # snappiness (no 1.2s wait); the poll is the source of truth. (the user 2026-06-24: blocked-no-prompt.)
        self._pending_ask[sess.sid] = ask
        self._notify("chat", {"type": "askLive", "id": sess.sid, "ask": ask})
        self._poke()

    def _clear_ask(self, sess: SdkSession):
        self._pending_ask.pop(sess.sid, None)
        self._notify("chat", {"type": "askLiveClear", "id": sess.sid})

    def current_ask(self, sid: str):
        """The live ask a blocked SDK session is waiting on (the dict _emit_ask stored), or None. The kernel's
        _ask_poll calls this for SDK-backed sids instead of scraping a tmux pane (there is none), so the prompt
        replays durably to chat clients — and so the poll never clobbers it with an askLiveClear."""
        return self._pending_ask.get(sid)

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

    def prune_live(self, sid: str, tx_uuids, tx_user_texts=(), human_floor: int = 0) -> None:
        """Drop live atoms the transcript has now caught up on — by uuid (assistant/tool/user from the
        stream) or by text (the optimistic input echo, which has a synthetic uuid).

        FIFO floor for echoes: an input echo whose text can't match — because the transcript EXTRACTED an
        image path out of the user text, so `_atom_user_text` no longer contains the echoed path (the
        screenshots-piling-up-at-the-bottom bug, the user 2026-06-25) — is also retired once the transcript's
        newest GENUINE-HUMAN turn is at/after the echo's send time. SDK sends always enqueue and land in
        submission order, so a human turn that recent means this (earlier or equal) echo's message has been
        processed; a still-queued send keeps showing via the event-based `queued` indicator, so this never
        hides a message. (Echo-only: real stream atoms have no _echo_text and prune by uuid as before.)"""
        d = self._live.get(sid)
        if not d:
            return
        for k in list(d.keys()):
            a = d[k]
            et = a.get("_echo_text")
            landed = a.get("uuid") in tx_uuids or (et and et in tx_user_texts)
            stale_echo = bool(et) and human_floor and a.get("t", 0) <= human_floor
            if landed or stale_echo:
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
        # the thread (and its claude subprocess) is gone, so any background work is too — clear a stale
        # awaiting overlay so the session doesn't read working/awaiting forever (reorder_bug 2026-06-24).
        self._heal_stale_awaiting(sess.sid)
        self._poke()
