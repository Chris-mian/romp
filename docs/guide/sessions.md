# Sessions and revival

Nothing gets lost: sessions are named and persistent, closed ones revive with
their history, and old work stays findable.

## Named, colored, persistent

A Romp session is a name that outlives any one conversation. Its identity
survives `/clear`, relaunches, and kernel restarts, and each name keeps its
own color on every surface, so `api` is the same `api` wherever you see it.

## Revival

Type a closed session's name into the picker and it offers to revive it: the
session comes back live with its history intact. Stepping away, or shutting
the laptop, costs nothing.

The judges also keep a short archive per session (a headline and abstract of
what it did), so a fleet of many sessions stays navigable months later.

## Two backends

Sessions run on one of two backends, chosen per session:

- **Agent SDK (the default).** The kernel drives the session through the
  Claude Agent SDK. Sessions started from the dashboard use this; it is the
  most robust path, with native pickers, queued sends, and model switching.
- **tmux.** A regular Claude Code terminal session running inside tmux. Romp
  reads the same transcript, and delivers messages and nudges by injecting
  text into the terminal. Injection is inherently less robust than the SDK,
  but it lets Romp ride along with the terminal Claude Code you already use:
  run `romp <name>` and the session shows up on the dashboard like any other.
