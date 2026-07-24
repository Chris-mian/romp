# Guide

This guide covers what Romp puts on screen and what it does with your sessions:
the views, the task cards, the nudges that keep agents moving, and the messaging
between them.

## The Romp UI

Romp gathers all your Claude Code sessions into a single dashboard you can watch
and steer. You see it through four views, each answering a different question:

- **[The chat](#the-chat)** is the normal way of talking to a coding agent, but
  easier to scan: tool calls fold away and expand only when you want them.
- **[The feed](#the-feed)** shows Romp's task-management layer: Romp analyzes
  each session's transcript, breaks the work into tasks, and shows each task as
  a card. One session can produce several, and agents can hand tasks off to one
  another.
- **[The timeline](#the-timeline)** shows what each session has been doing over
  time and how they have been coordinating; click any part to jump to that
  moment in the chat.
- **[The outline](#the-outline)** lists every session with its tasks, for
  reviewing what a session has done and searching across all of them.

### The chat

The same conversation you would have in the terminal, only easier to scan: tool
calls fold into runs so a long session stays legible, and you expand a run for
its calls, or a call for its full input and output, when you want it.

![Tool calls fold into runs; each expands to one line per call](assets/guide/chat-detail.png){ width="100%" }

### The feed

The feed is Romp's task-management layer: a card for each task. Romp's
[judges](judges.md) watch each session's work, split it into those tasks, and
keep every card current.

Cards sit in three columns:

- **Working** — the session is actively working on the task.
- **Blocked** — it needs your input to move on.
- **Completed** — done, ready for you to review and clear.

![The feed's three columns, with the cues on a card](assets/guide/feed-annotated.png){ width="100%" }

The title is the gist. **Background** is why the agent is taking this action.
**Summary** is what it did. Sub-tasks nest beneath when the work splits.

Cards follow the work rather than the session: a session that interleaves
several efforts gets a card per effort, and one effort handed across sessions
stays a single card. Summaries favor the latest stretch of work, so a card you
return to after hours away tells you what changed since you last looked.
**Clear** a card when you are done with it; cleared cards are archived.

### The timeline

Each lane is one session. A line is the session working, and a circle on it is a
message you sent. A striped stretch means the session is blocked, waiting on
your input.

![A timeline lane per session, with status and context at the left](assets/guide/timeline-annotated.png){ width="100%" }

Click a bar or a message marker to jump straight to where it happened in the
chat.

A session wears the same color for its state everywhere it appears: its tab, its
timeline lane, its cards.

![Each session state and what its color means](assets/guide/status-legend.png){ width="70%" }

### The outline

Every session with its task tree: open work stays up top, finished work folds
beneath. Open the outline to review what a session has worked through, or to
find past work: the search box reaches every session, live or closed.

![The outline: each session's tasks as a tree](assets/guide/outline.png){ width="100%" }

## Automatic nudges

To keep agents moving forward whenever your input isn't needed, Romp nudges a
stalled session back to its open work: when it hit an API error, when it was
interrupted, or when it simply stopped with a task still open and never said
whether the task was done.

Romp asks the agent, item by item, where each open piece stands: continue what
it can, and say what blocks the rest.

- If the agent can keep going, it does, and you were never interrupted.
- If something needs you, the card flips to **Blocked** and names exactly what
  it needs.

Nudging holds off while you are actively driving a session, and it re-arms only
after a real turn ends, so it never talks over you and never loops on its own
messages.

A session can also be waiting on something that is not you. When it dispatches
work and pauses for the result, it shows an <span class="romp-chip-await">Awaiting</span>
chip on the fleet rail, on the chat statusline above the message box, and on its
timeline lane, where the pending stretch is drawn faded. Awaiting never means it
needs you: it means the work is in flight until what the session sent for comes
back. The chip clears on the session's next turn, when the task finishes or
blocks, when you clear the card, or as soon as you reply.

## Messaging between agents (the Romp Postal Service)

Sessions message each other through a mailbox Romp gives them, and every
exchange is visible to you. Each session gets mail tools: send a message to a
session by name, check the inbox, and see who is live. Each session also
publishes a working note saying what it currently holds, so agents can see who
to talk to instead of messaging each other to find out.

The timeline draws an arc for each message. Hover one for its gist:

<video src="../assets/guide/coordination.mp4" controls autoplay loop muted playsinline width="100%"></video>

The recipient sees it in its chat, with the sender and the kind on the card:

![A message from another session, as the recipient's chat shows it](assets/guide/postal-chat.png){ width="100%" }

Every message declares its kind:

- **delegate** — the recipient owns the work now.
- **coordinate** — a heads-up; a reply is optional.
- **question** — an answer is required.

The same mailbox is on the command line, for you and for scripts:

```bash
romp --mail send --kind question api "Which auth approach did we settle on?"
romp --mail inbox
```

The full mail surface, shell and in-session, is in the
[Reference](reference.md#mail-from-the-shell). Names resolve against the
currently live sessions; sending to a dead session's name errors instead of
silently parking mail.

## Sessions, revival, and search

A Romp session is a name that outlives any one conversation. Its identity
survives `/clear`, relaunches, and kernel restarts, and each name keeps its own
color on every surface, so `api` is the same `api` wherever you see it.

Type a closed session's name into the picker and it offers to revive it: the
session comes back live with its history intact. Stepping away, or shutting the
laptop, costs nothing.

The picker matches against every session, live or closed. As sessions run, a
lightweight index judge writes each one a headline and an abstract of what it
did, so the search reaches inside a session's work, and many sessions stay
navigable months later.

### Session backends

Sessions run on one of two backends, chosen per session:

- **Agent SDK (the default, strongly recommended).** The kernel drives the
  session through the Claude Agent SDK: a direct programmatic connection, with
  native pickers, queued sends, and model switching. Sessions started from the
  dashboard use this.
- **tmux.** A regular Claude Code terminal session running inside tmux. Romp has
  no direct connection to it, so it works by reading what appears in the
  terminal and on disk, and delivers messages and nudges by injecting
  keystrokes. That makes it inherently less reliable and less responsive than
  the SDK: scraping a terminal has edge cases a real API does not, and updates
  wait on the transcript reaching disk.

The tmux backend exists for when you want the session in an actual terminal: run
`romp <name>` and that terminal session shows up on the dashboard like any
other. The two interleave freely, so a terminal session can sit alongside SDK
sessions.

## Where Romp runs

You run Romp on your own machine; there is no hosted service in between. The
kernel runs there and serves the dashboard on `127.0.0.1:7433`. Everything Romp
stores stays local; the only traffic that leaves your machine is `claude`
itself, both the agents' own model calls and the LLM calls in Romp's judge
pipeline.

### Attaching another machine

Each machine runs its own kernel. Attach one and its sessions join your
dashboard:

- Its sessions appear as `host:name` tabs and timeline lanes next to your local
  ones, and you drive them from the same chat.
- Its task cards share the feed.
- Sessions message each other across machines through the same postal service,
  so an agent on your desktop can hand work to one on the server.

To attach a host:

1. On the remote machine, clone romp and run `./install.sh` (`ROMP_NO_EXT=1`
   skips the editor extension on a machine with no VS Code or Cursor). Make
   sure `ssh <host>` works non-interactively.
2. In your dashboard, click the network button at the bottom right and attach
   the host.

![The network button, bottom right, is where machines attach](assets/guide/network-button.png){ width="100%" }

The attach fetches the remote kernel's token over ssh, opens the tunnels, and
starts the remote kernel if it isn't running.

The popover remembers every host you have attached. Detaching one moves it to a
**Previously attached** list rather than dropping it, so bringing it back is one
click (**Re-attach**), and it keeps the trust level you last chose. **Forget**
removes a host from that list; it does nothing to the machine itself.

Each attached host carries a trust level that governs its mail; see
[Security and trust](#security-and-trust).

### Publishing a roaming machine to a hub

A machine that moves between networks can publish itself to an always-on hub
over its own outbound ssh, so the hub never holds credentials into it. Tick
**keep connected** on the hub's row in the network popover (or run
`romp checkin <hub>`): the attach tunnel gains reverse forwards for this
machine's kernel and postal bus, and a handshake hands the hub its ports and
dashboard token. The hub's dashboard then sees and drives this machine's
sessions whenever it is online, from any network.

The two postal buses peer over the same tunnel, so messages flow both ways. Mail
for an unreachable machine parks in an outbox and delivers on reconnect, or
bounces back if the recipient is gone. Untick the box (or `romp checkout <hub>`)
and the hub forgets the machine and its token.

Every machine runs its own postal bus, so a laptop off the network keeps full
local messaging; connecting only adds reach.

## Reaching the dashboard

The kernel serves the dashboard on `127.0.0.1` and never listens beyond it. You
reach it in a browser tab, in the VS Code / Cursor extension, or from your phone
over Tailscale.

### Your phone

Let [Tailscale](https://tailscale.com) carry the traffic: `tailscale serve`
proxies HTTPS at your machine's tailnet name to the loopback port, on the
machine itself.

```bash
tailscale serve --bg 7433     # https://<machine>.<tailnet>.ts.net -> 127.0.0.1:7433
tailscale serve status        # show the active proxy
tailscale serve reset         # back to local-only
```

On the phone's first open, append the access token:
`https://<machine>.<tailnet>.ts.net/?token=<token>`, with the token from
`romp launch` (or paste it into the page a bare open serves). A year-long cookie
remembers the phone after that.

Only devices signed into your tailnet can connect, through WireGuard device
identity plus TLS; nothing is opened to your LAN or the internet, and the proxy
persists across restarts of both Tailscale and the kernel. Do not use
`tailscale funnel`, the public-internet variant: the token would then be the
only thing between the internet and your agents, with no device identity in
front of it.

## Security and trust

Romp drives agents that run tools and shell commands as you, so reaching its API
is equivalent to running code as you. Everything below follows from that.

**One token, required on every request.** The kernel and the postal bus both
demand a token on every request, local ones included. Loopback is not a
security boundary: on a multi-user machine every local account can reach your
ports, so without this any other user could inject prompts into your live
sessions. The token is 144-bit random and lives at
`~/.local/state/romp/serve-token` with mode `0600`; file permissions are the
actual gate. Local tools (the CLI, hooks, the bus, the editor extension) read
that file and send it automatically, so you never type it. Only liveness probes
(`/healthz`, `/version`, `/busy`, and the bus's `/ping`) are exempt.

**Remote machines.** Every machine mints its own token. When you attach a host,
your machine reads that host's token over ssh and stores it locally (in
`~/.local/state/romp/remotes.json`, also `0600`: it is a credential store).
Dashboard traffic to a remote never crosses the network in the open; it rides
the ssh tunnel, which supplies encryption and machine identity, while the token
authorizes at the far end. Check-in reverses the direction, so credentials
always flow outward from the machine that initiates, and a hub never holds a way
in.

**Trust levels for attached hosts.** A message that reaches an agent's context
can steer it, so each attached host carries a trust level, set on its row in the
network popover and remembered per host:

- **trusted** — full two-way postal, for a machine you control.
- **directed** (the default for a newly attached host) — you can send work to
  its sessions, but its mail to you is held for approval. Each held message
  becomes a needs-you card with **Approve**, **Edit**, and **Deny**, so a person
  decides before that host's content reaches one of your agents. This is the
  posture for rented or shared compute.
- **isolated** — no postal at all; the host's sessions still show in the
  dashboard, but its bus never peers with yours.

**What this does not protect against.** Root on a machine can read any file
(including the token) and inspect any process, so don't keep long-lived
credentials on a machine whose root you don't trust. Anything already running as
*you* can read the token: same-machine sessions are separated by policy, not by
this boundary. The enforceable lines are per-user (the token file) and
per-machine (the trust level).

Full details, including how to report a vulnerability, are in
[SECURITY.md](https://github.com/romp-on/romp/blob/main/SECURITY.md).

## How many tokens does Romp use?

Romp spends tokens on top of what you spend yourself. If you are running models
like Opus or Fable at high effort, the judging costs much less than the sessions
themselves. The analytics modal in settings shows what you actually spent,
separating your sessions from the judge pipeline. You can also reconfigure the
judges from the gear: the high-volume indexing tier defaults to Haiku, and the
judgment tier defaults to Sonnet.
