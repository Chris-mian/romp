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

## Search

The session picker matches against every session, live or closed. The judges
index each one with a headline and abstract of what it did, so a fleet of
many sessions stays navigable months later.

Which backend a session runs on (Agent SDK or tmux) is a per-session choice;
[Session backends](../reference.md#session-backends) covers the difference.
