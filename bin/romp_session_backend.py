#!/usr/bin/env python3
"""The SessionBackend contract — ONE clean, backend-agnostic session API.

romp drives Claude Code sessions through two backends: the legacy TMUX backend (a Claude Code TUI running
in a tmux pane, controlled by shelling `tmux`) and the SDK backend (`romp_sdk_backend.SdkBackend`, the
Agent SDK). Historically the kernel + the postal bus reached straight past this split and shelled tmux
inline, so tmux assumptions leaked all over the higher layers. This ABC formalizes the contract both
backends already (de-facto) honor, so EVERYTHING above the backend speaks one API and nothing shells tmux
except the one TmuxBackend that implements it (a guard test enforces that — see tests/test_session_api.py).

The API is SID-KEYED (a romp session uuid), the kernel's native identity, even though tmux is keyed by
session NAME — a backend maps sid→its own handle internally. `SdkBackend` conforms by duck-typing (it is
SDK-gated, so it can't import this module when the SDK dep is absent); `TmuxBackend` inherits this ABC.
A conformance test asserts SdkBackend implements every abstract method, so the duck-typing can't drift.

Method groups:
  liveness/identity — owns, live_sessions
  control           — send, interrupt, set_model, set_mode, set_effort
  lifecycle         — spawn, resume, connect, kill, rename
  coordination      — working_note, set_working_note, wake   (backend-agnostic; tmux used @romp-working +
                      send-keys, the SDK now gets a store + an enqueue-wake so it has both too)
  chat tail         — pending_queued, live_atoms, prune_live
  ask picker        — on_ask, current_ask

A backend that genuinely cannot do an op returns the documented empty value (False / [] / "" / None) rather
than raising, so callers never need to know which backend they hold.
"""
from __future__ import annotations
from abc import ABC, abstractmethod


class SessionBackend(ABC):
    # ── liveness / identity ──────────────────────────────────────────────────────────────────────
    @abstractmethod
    def owns(self, sid: str) -> bool:
        """True if THIS backend currently drives `sid`. The dispatcher routes per-sid ops to whichever
        backend owns the sid (see Sessions.backend_for)."""

    @abstractmethod
    def live_sessions(self) -> dict:
        """{sid: {state, model, effort, mode, since, context, color, backend, ...}} for every session this
        backend currently runs. state ∈ working|waiting|idle|permission|compacting (compacting/context% are
        tmux-only → None elsewhere). The kernel MERGES every backend's map for one fleet-wide liveness view."""

    # ── control (per-sid) ────────────────────────────────────────────────────────────────────────
    @abstractmethod
    def send(self, sid: str, text: str) -> bool:
        """Deliver a user message / command to `sid` (the chat composer, /compact, retry, an injected
        nudge). True if delivered/queued."""

    @abstractmethod
    def interrupt(self, sid: str) -> bool:
        """Stop the in-flight turn (Esc) and leave the input clean."""

    @abstractmethod
    def set_model(self, sid: str, value: str) -> bool: ...

    @abstractmethod
    def set_mode(self, sid: str, mode: str) -> bool:
        """Set the permission mode (auto/default/acceptEdits/plan/…)."""

    @abstractmethod
    def set_effort(self, sid: str, value: str) -> bool: ...

    # ── lifecycle ────────────────────────────────────────────────────────────────────────────────
    @abstractmethod
    def spawn(self, name: str, cwd: str, bg: str = "", fg: str = "", sid: str | None = None) -> str | None:
        """Start a NEW session; return its sid (or None on failure)."""

    @abstractmethod
    def resume(self, name: str, sid: str, cwd: str | None = None) -> bool:
        """Revive a DEAD session by sid (resumes its conversation)."""

    @abstractmethod
    def kill(self, sid: str) -> bool: ...

    @abstractmethod
    def rename(self, sid: str, new_name: str) -> bool: ...

    # ── coordination (working-note + deliver-time wake) ──────────────────────────────────────────
    # Concrete no-op defaults so the EXISTING contract (what SdkBackend already has) stays the abstract
    # surface for P0; P3 makes these real on both backends (tmux had @romp-working + a pane Enter; the SDK
    # gets a backend-agnostic store + an enqueue-wake) and promotes them to part of the enforced contract.
    def working_note(self, sid: str) -> str:
        """The session's published 'what I'm working on' ownership note for the postal bus (list_agents),
        or '' if none. Backend-agnostic: tmux stored it in @romp-working, the SDK in a kernel-side store."""
        return ""

    def set_working_note(self, sid: str, text: str) -> None:
        """Publish (text) or clear (text='') the session's working-note."""
        return None

    def wake(self, sid: str) -> bool:
        """Nudge `sid` to PROCESS pending input now (e.g. mail just delivered to a session sitting idle).
        tmux pressed Enter in the pane; the SDK enqueues a drain. True if a wake was issued."""
        return False

    def deliver(self, sid: str, text: str) -> bool:
        """Live-deliver a postal banner to `sid` as the deliver-time WAKE — put it into the session's input so
        an idle recipient surfaces the mail NOW instead of on its next turn. tmux pastes it into the pane
        (draft-preserving); the SDK enqueues it. True iff delivered. Default: not delivered (the postal bus
        then leaves the mail for its maildir-drain backstop). The bus reaches this via the kernel's POST
        /deliver so it never shells tmux."""
        return False

    # ── chat tail ────────────────────────────────────────────────────────────────────────────────
    @abstractmethod
    def pending_queued(self, sid: str) -> list:
        """User messages submitted while busy that haven't started yet (the chat's 'queued' indicator)."""

    @abstractmethod
    def live_atoms(self, sid: str) -> list:
        """In-memory chat-tail atoms AHEAD of the transcript on disk (the optimistic input echo + any live
        stream), [] if none. Merged before the on-disk parse so a just-sent message shows instantly."""

    @abstractmethod
    def prune_live(self, sid: str, tx_uuids, tx_user_texts=()) -> None:
        """Drop live atoms the transcript now carries (by uuid or echo text), so they don't double-show."""

    # ── ask picker ───────────────────────────────────────────────────────────────────────────────
    @abstractmethod
    def on_ask(self, sid: str, kind: str, payload=None) -> bool:
        """Drive a live AskUserQuestion picker (answer/focus/toggle/submit/custom/cancel/text)."""

    @abstractmethod
    def current_ask(self, sid: str):
        """The session's live AskUserQuestion state for the webview, or None."""
