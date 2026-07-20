# Guide

New to Romp? [Install it first](install.md), then come back here.

Romp turns a fleet of Claude Code sessions into one thing you can watch and
steer. It reads each session's transcript as it grows, groups the work into
task cards, surfaces what needs a decision from you, and keeps everything else
moving on its own. You see all of it through four views of the same live
state, each answering a different question:

- **The chat** drives one agent: its transcript, condensed so you can scan it.
- **The feed** is where you spend most of your time: the work as task cards,
  sorted into moving on its own, needs you, and done.
- **The outline** is for finding things: every session with its tasks, all
  searchable.
- **The timeline** shows coordination: the sessions over time and the messages
  that pass between them.

![The dashboard: chat, outline, and feed over one fleet](assets/guide/dashboard-annotated.png){ width="100%" }

## The chat

The transcript, condensed for scanning: turns read as gists, tool calls fold
into runs, and every detail stays one click deeper. Expand a run for its
calls, and a call for its full input and output.

![Tool calls fold into runs; each expands to one line per call](assets/guide/chat-detail.png){ width="100%" }

## The feed and task cards

Romp organizes what the agents do into task cards, so you follow the work by
outcome instead of scrolling transcripts. Cards land in three columns: moving
on its own, waiting on you, and finished. A completed card carries its
takeaway, so you read the outcome without opening anything.

![The feed's three columns, with the cues on a card](assets/guide/feed-annotated.png){ width="100%" }

The cards are generated automatically: Romp's judges read each session's
transcript as it grows, group the work into tasks, and keep every card's
status and summary current, with no reporting step for the agent and no filing
step for you.

The title is the gist. **Background** is why the work exists: what led to it
and whose ask it is. **Summary** is what the agent did, written to stand on its
own. Sub-tasks nest beneath when the work splits. Each level is one click, so
you spend attention only where the work earns it.

![The anatomy of a task card](assets/guide/card-anatomy.png){ width="100%" }

Cards follow the work rather than the session: a session that interleaves
several efforts gets a card per effort, and one effort handed across sessions
stays a single card, so a handoff never drops a thread. Summaries favor the
latest stretch of work, and a card you return to after hours away tells you
what changed since you last looked. When you're done with a card, **Clear** it
(**Undo clear** brings it back); cleared cards are archived.

## The outline

Every session with its task tree: open work stays up top, finished work folds
beneath, and the search box reaches all of it.

![The outline: each session's tasks as a tree](assets/guide/outline.png){ width="100%" }

## The timeline

Each lane is one session; bars are stretches of work.

![A timeline lane per session, with status and context at the left](assets/guide/timeline-annotated.png){ width="100%" }

The story of any bar is a hover away:

![Hovering a bar pops what happened and when](assets/guide/timeline-hover.png){ width="100%" }

### Status colors

A session wears the same color for the same state everywhere it appears: on its
tab, its timeline lane, and its cards.

![Session states and what each means](assets/guide/status-legend.png){ width="70%" }

- **Working** (yellow): the agent is running.
- **Ready** (blue): idle, waiting for your next message.
- **Blocked** (red): a prompt or decision needs you.
- **Awaiting** (straw): idle, waiting on background work it started.
- **Compacting** (teal): compacting its context.
- **API error** (bright red): the session stopped on an API error.

## Automatic nudges

An agent that goes idle with open work gets nudged back to it, so progress does
not wait on you noticing a stall.

Claude Code sessions routinely stop with to-dos still open. With auto-nudge on
(the gear menu; off by default), Romp notices the stall and asks the agent,
item by item, where each open piece stands: continue what it can, and say what
blocks the rest.

- If the agent can keep going, it does, and you were never interrupted.
- If something needs you, the card flips to **Blocked** and names exactly what
  it needs.

Either way you only get pulled in when you are the bottleneck.

Auto-nudge holds off while you are actively driving a session, and it re-arms
only after a real turn ends, so it never talks over you and never loops on its
own messages.

## Messaging between agents

Sessions message each other through a mailbox Romp gives them, and every
exchange is visible to you. Each session gets mail tools: send a message to a
session by name, check the inbox, see who is live and what they hold. Agents
use them to ask each other questions, hand off work, and announce results. You
watch it happen on the timeline and in the chat.

![A message hop between two sessions, with its gist on hover](assets/guide/postal-timeline.png){ width="100%" }

![The same message as the recipient's chat shows it](assets/guide/postal-chat.png){ width="80%" }

Every message declares what it is: **delegate** (the recipient owns the work
now), **coordinate** (a heads-up; reply optional), or **question** (an answer
is required). The declaration travels with the message, so the recipient and
the task cards treat it accordingly.

The same mailbox is on the command line, for you and for scripts:

```bash
romp --mail send --kind question api "Which auth approach did we settle on?"
romp --mail inbox
```

The full mail surface, shell and in-session, is in the
[Reference](reference.md#mail-from-the-shell). Names resolve against the
currently live fleet; sending to a dead session's name errors instead of
silently parking mail.

## Sessions, revival, and search

Nothing gets lost: sessions are named and persistent, closed ones revive with
their history, and old work stays findable.

A Romp session is a name that outlives any one conversation. Its identity
survives `/clear`, relaunches, and kernel restarts, and each name keeps its own
color on every surface, so `api` is the same `api` wherever you see it.

Type a closed session's name into the picker and it offers to revive it: the
session comes back live with its history intact. Stepping away, or shutting the
laptop, costs nothing.

The picker matches against every session, live or closed. As sessions run, a
lightweight index judge writes each one a headline and an abstract of what it
did, so the search reaches inside a session's work, and a fleet of many
sessions stays navigable months later.

Which backend a session runs on (Agent SDK or tmux) is a per-session choice;
[Session backends](reference.md#session-backends) covers the difference.

## Self-hosted and remote access

You run Romp yourself and reach it from wherever you are, with no hosted service
in between. The kernel runs on your machine and serves the dashboard on
`127.0.0.1:7433`, to a browser tab or the VS Code / Cursor extension. Everything
Romp stores stays local; the only external traffic is the `claude` CLI you
already use.

### More machines, one fleet

Federation is the heart of remote access: every machine runs its own kernel,
and attached machines present as a single fleet.

![One fleet across your phone, your laptop, and a remote host](assets/guide/federation.png){ width="100%" }

Once a host is attached:

- Its sessions appear as `host:name` tabs and timeline lanes next to your local
  ones, and you drive them from the same chat.
- Its task cards share the feed, so one glance covers every machine.
- Sessions message each other across machines through the same postal service,
  so an agent on your desktop can hand work to one on the server.

Setup is one install and one click:

1. On the remote machine: clone romp and run `./install.sh` (`ROMP_NO_EXT=1`
   skips the editor extension on a headless box). Make sure `ssh <host>` works
   non-interactively.
2. In your dashboard: open the network icon in the top bar and attach the host.

The attach fetches the remote kernel's token over ssh, opens the tunnels, and
starts the remote kernel if it isn't running.

### Your phone

The kernel never listens beyond `127.0.0.1`. To reach it from your phone, let
[Tailscale](https://tailscale.com) carry the traffic: `tailscale serve` proxies
HTTPS at your machine's tailnet name to the loopback port, on the machine
itself.

```bash
tailscale serve --bg 7433     # https://<machine>.<tailnet>.ts.net -> 127.0.0.1:7433
tailscale serve status        # show the active proxy
tailscale serve reset         # back to local-only
```

With Tailscale on the phone, the full dashboard is in your pocket: check the
feed, answer a blocked card, start a session. Only devices signed into your
tailnet can connect (WireGuard device identity plus TLS); nothing is opened to
your LAN or the internet, and the proxy persists across restarts of both
Tailscale and the kernel. Don't use `tailscale funnel` (the public-internet
variant): the kernel trusts loopback-proxied connections as local, so a funnel
would publish the dashboard unauthenticated.
