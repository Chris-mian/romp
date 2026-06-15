# The read side: the kernel, the UI, and the three panes

Internal design doc (not user-facing). Layer 3 of the rebuilt romp: it turns the
records written by the event model (`design/event-model.md`) and the summarizer
layer (`design/judge.md`) into the three web-UI panes the user actually looks at:
the **feed**, the **chat**, and the **timeline**. Built fresh beside the existing
`chat-view/` kernel + `obsidian/` timeline + `bin/romp-feed`, which stay until the
new one is proven. Started 2026-06-15.

## The governing principle

**Layer 3 derives no meaning. All meaning is computed below it (almost all in
Layer 2); the read side only selects and displays.** Every decision here follows
from that. The old read side rebuilt a DAG, re-derived every node's status,
classified handoffs, and repaired missed ones on every 800ms tick. None of that
belongs here. The judges write durable meaning once; the panes are thin
projections of it.

A direct consequence: the completion **rollup + "settled" gate** moves *down* into
Layer 2. The producer publishes each goal's rolled-up status (working / blocked /
completed); the feed just paints columns. (Reflected back into `design/judge.md`.)

## Decisions locked

- **One always-on process: the kernel.** It is the core. It runs Layer 1 (parse) +
  Layer 2 (the judges) **and** an HTTP server. It comes up with the first romp
  session, like the postal bus, and stays up. There is no separate UI server
  process and nothing to "start."
- **The UI is served by the kernel.** The front-end (the three panes) is `ui/`
  (renamed from `chat-view/`). A browser hits the kernel's port and gets it.
- **`romp --on` is removed.** It was only ever "start the UI server"; the kernel is
  always on, so it is vestigial. No backwards-compatibility shim. The UI is a URL.
- **Clean break, no backwards compatibility.** The old record stores (`summaries/`,
  `requests/`, `decision-log`, `corrections/`, `digest/`, ...) are **disposable**.
  The new system does not read or migrate them. We need not delete them, but the
  producer ignores them and the kernel discovers only new-model sessions, so old
  data cannot pollute the new model or confuse future sessions that never knew the
  old shape. It is fine for pre-rebuild sessions to never appear (no resume picker
  entry, no scrollback over old history). Actively reject any back-compat path that
  makes the system more confusing to reason about.
- **The VS Code extension is a thin client, unchanged in kind.** It already speaks
  the kernel's WebSocket protocol (`chat-view/src/extension.ts`: "a THIN CLIENT of
  the romp web kernel", `ws://HOST:kernelPort()/ws?app=...`). Browser and extension
  render the **same served UI** over the **same protocol**, so the two front ends
  stay consistent by construction. Keeping the WS protocol stable is the
  compatibility contract.
- **A connected browser is the presence signal that gates the triage tier.** While
  at least one client (browser or extension) is connected, the kernel runs the
  triage judges (planner + courier) and the Layer 3 projections; on last
  disconnect, triage idles and only the index tier (captioner + archiver) keeps
  running. (See the tiering in `design/judge.md`.) Single process means single
  writer for free, no matter how many tabs are open.
- **A setting can keep triage warm when disconnected** (per-machine), for users who
  want the inbox always current. Default: triage only when watched.
- **Views are URL-hash tag selections.** `localhost:PORT/#work,personal` is one
  view; `#work` is another. Each browser tab is an independent view over the same
  kernel, ephemeral, zero-config, many at once. A saved default can live behind the
  settings gear.
- **Port is a per-machine config.** One fixed port the kernel binds at startup.
- **Liveness collapses to three states** (+ the user's `cleared`): **working**
  (open, nothing for you to do; absorbs the old active / delegated / stalled /
  waiting-on-a-non-user-trigger), **blocked** (needs *you*), **completed**. They map
  1:1 onto the three feed columns. The old four-way active/delegated/stalled verdict
  is gone.
- **`blocked` has a deterministic floor the judge cannot override.** A live
  permission / decision prompt is a fact, not a judgment. `blocked = hard OR soft`,
  hard wins: the planner's output can never clear a hard block. We tell the judge
  nothing special; we just never let its verdict remove a hard block (a merge rule,
  not a prompt instruction). They rarely collide in time anyway (the planner runs
  on *ended* segments; a live prompt sits on an *open* turn).
- **The read side has two inputs: durable judge records + a thin real-time
  live-state read.** Live state (the chip, the timeline stripes, the hard-block
  floor, "is a session mid-turn right now") comes from `states/<sid>.jsonl` + the
  event tree's open turn. It is deterministic and mechanical, not meaning-logic, so
  it does not violate the principle; it is the one thing that cannot be precomputed
  into a record because it is about *right now*.
- **Comms scope is directory-based, group-wide, alive-gated** (see below). A
  separate axis from view tags.
- **Tags are directory-derived, overridable.** A `directory → tag` map auto-tags a
  session at launch; a per-session manual override handles "get this out of work."
- **Hard data isolation is a separate `ROMP_STATE` root, manual, rare.** Default is
  one shared root (so views can overlap). Point a kernel at another root only when
  you genuinely need segregated data (a dedicated machine). Free, because the root
  is already a parameter.

## The runtime picture

```
THE KERNEL  (one always-on process, single writer)
  Layer 1   parse transcripts → event tree
  Layer 2   index tier  (captioner + archiver)     ALWAYS
            triage tier (planner + courier)         while a client is connected
  HTTP/WS   serve the UI + push pane payloads
  writes →  ~/.local/state/romp/   (the interface)

POSTAL BUS  (always-on infra, below Layer 2)        delivery never waits on a judge

CLIENTS  (0..N, pure readers, render only)
  browser tab(s)      ── each a view (URL-hash tags)
  VS Code extension   ── same WS protocol
```

The records dir is the only interface. The kernel is the only writer. Clients only
read and render. This is the producer/consumer split the whole rebuild rests on,
collapsed into a single process for the common (one-machine) case while preserving
single-writer.

## The two inputs

1. **Durable judge records** (`design/judge.md` writes these):
   - **captions** — per segment and per turn, keyed by id. The activity log.
   - **the goal tree** — nodes + edges + per-node and rolled-up status. The inbox.
   - **courier records** — handoff (propagating / FYI) + which sender goal, keyed by
     message/segment id. The cross-session edges.
   - **archive** — per session, keyed by rompUuid: a sub-sentence **headline** + a
     2-3 sentence **abstract**, summarized from the session's captions (cheap
     input), continuously refreshed as the session gains turns. The index + the
     TOC header. Replaces the old `romp-digest` pass entirely.
2. **A thin real-time live-state read**: `states/<sid>.jsonl` (working / permission /
   compacting / idle / closed transitions) + the event tree's open turn. Drives the
   chip, the timeline stripes, the hard-block floor, and the mid-turn pulse.

## The three panes (each a thin projection)

Chat is a zoom into Layer 1; the feed is a zoom into Layer 2; the timeline is the
bridge that shows Layer 1 spatially with Layer 2 labels.

### Chat = the event tree, rendered directly

Per-session tabs. Renders the event tree at the Atom / ContentBlock level (one
widget per block), **no second transcript parser** (the old `chat.ts` parser is
deleted; the event model already produced the tree). Plus the live chip from the
state read, and the TOC ledger below the tabs.

**The ledger is a table of contents** (pure projection of captions + archive):
- top: the archiver's one-sentence headline for the session,
- then **turn captions** as top-level bullets, the whole session (not just recent),
- a multi-segment turn expands to its **segment captions** indented beneath,
- click any line to jump to that point in the transcript.

The captioner already emits both grains; the event model already gives the
turn→segment nesting; so the TOC is free. (Caveat to verify during build: a live
permission prompt's *content* may exist only in tmux, not the transcript; a live
AskUserQuestion/ExitPlanMode is in the tree as an unanswered tool_use. The chip
state comes from `states/` regardless.)

### Feed = the goal tree + the caption stream

- **Inbox**: top-level goals are the cards, bucketed into the three columns by the
  rolled-up status the producer already wrote (working / blocked / completed). A
  card's modal shows the goal's trail (its filed segments, interleaved). No
  read-time DAG rebuild, no status derivation, no handoff repair.
- **Stream**: captions, newest-first, faded by recency (the one kept display
  heuristic; pure cosmetics).
- **Card detail (TBD)**: the old expand-paragraph card detail (`romp-feed-detail`,
  the deferred expand writer) is to be **remade entirely** and is parked until the
  inbox is in. Until then a card shows its caption trail.
- **Clear-all + undo**: a button retires every currently-open top-level card at
  once (batch `cleared`); an **undo** restores that batch if invoked right after.
  For sweeping away a stale backlog you know you don't care about.

### Timeline = segments as bars, with connectors and overlays

- **Lanes**: one per session; each **segment** is a bar `[t, end]` (segments are
  exactly "what the timeline draws as a bar" in the event model), a dot at the
  trigger, idle atoms as the not-working gaps (replaces the old idle-clip), caption
  on hover.
- **Stripes**: awaiting / compacting, from the state read.
- **Connectors**: postal messages between lanes, from courier records / the message
  log.
- **Overlays**: focus / hover from the feed and chat (UI ephemera, one WS channel).
- Reads **segments straight from the event model**. `romp-events --emit` (the
  separate full-pipeline run that produced a bespoke `{events, pending,
  compactions}` blob) is **deleted**.
- The timeline moves **into `ui/`** next to chat and feed (out of `obsidian/`),
  sharing one view-builder, one bundle, one set of types. The kernel's special-case
  live-reload of the obsidian JS module goes away.

## One view-builder

A single read library (TS, in `ui/`) of pure functions `records → ChatView |
FeedView | TimelineView`. It **replaces four duplicated reducers**: `kernel/feed.ts`,
`bin/romp-feed` (the Python twin, gone with the TUI), `kernel/chat.ts`'s parser,
and `romp-events --emit`. One implementation, because there is one front end now.

## The heuristics, triaged

Most of the ~17 old read-time heuristics existed to rebuild or repair meaning the
judges now write. Gone, subsumed by Layer 1/2: decision-answered + session-moved-on
(planner un-blocks via newest-wins), origin discriminator (it's `trigger.author`),
**missed-handoff suspects** (the courier classifies at write time; the auditor it
rode on is gone — the single biggest deletion), DETAILS-latching + relevance
normalization + row-ranking (the TAG enum is gone; one segment files at one node),
reply dedup (captions keyed by id upstream), followup-reopen + claim-lag-hold (both
patched the old async daemon's write lag; the per-turn end-known engine removes the
race). Kept, but now thin reads: completion rollup + column derivation + the
settled gate — and these move *into Layer 2*, leaving the feed to read status.
Kept as display: recency fade.

## Comms scope (directory groups, alive-gated)

At the postal/infra level, below Layer 2, keyed on the working directory. Separate
from view tags.

- Sessions in the **same directory talk freely** (one project). Fits the
  shared-worktree reality: sibling sessions in one checkout are one group.
- **Cross-directory is blocked by default.** The first attempt surfaces an approval
  to the user; approving opens a **group-wide** edge (every session in dir A ↔ every
  session in dir B), not just the two that triggered it.
- The edge is **alive-gated**: it lives while both directories have ≥1 live session
  and tears down when either empties, so it re-asks next time. Event-based, no
  timer. ("Allow personal and work to talk today; tomorrow they're separate again.")
- A **config allowlist** (directory-pairs or tag-pairs) permanently bypasses the
  gate for pairs you always want open.
- **Agent norm**: sessions should not attempt cross-directory messages unless the
  user directs it; an unsanctioned attempt surfaces the approval prompt rather than
  delivering silently or failing silently.

## Tags and views

Two grains, both directory-rooted, matching the "things in the same folder" model:

- **Tag assignment**: a `directory → tag` map in settings auto-tags a session at
  launch (e.g. `~/work/* → work`); a manual per-session override in the UI handles
  reclassification. Tags are mutable identity metadata (alongside name / dir /
  color).
- **View selection**: the URL hash (`#work,personal`), ad-hoc and per-tab; a saved
  default behind the settings gear; or a quick selector control at the timeline
  bottom. The hash is the fast lever.

The exact project directory defines a **comms group**; a directory→tag rule defines
the coarser **display label**. Both default from where you launched, both
adjustable.

## The UI progress surface

When triage wakes (a client connects after a backlog, or a session is opened that
needs goals), the kernel is catching up: judging segments it hasn't judged yet. The
UI shows a **progress indicator** ("re-judging…", N pending) so the inbox filling
in is legible rather than mysterious. The kernel exposes the pending-judgment count;
the UI renders it.

## Remote kernels + postal federation

The pieces already exist; here is how they compose with the merged kernel.

- **Each machine runs its own kernel** (its own records, its own indexing). Records
  stay local to the machine that produced them.
- **Postal federates over SSH.** Local and remote sessions share one bus address; a
  remote session tunnels the bus port to the laptop with `ssh -R
  PORT:127.0.0.1:PORT` and heartbeats for presence (`bin/romp-postal`). So messages
  cross machines today; nothing in the merged kernel changes that.
- **Viewing remote sessions**: simplest path is to forward the remote kernel's HTTP
  port and open a second browser view at it (one view per machine). A unified view
  that proxies remote records into the local kernel (read-federation over the
  tunnel) is the richer option and is **deferred**.
- **Comms across machines**: directory groups are per-machine, so cross-machine is
  inherently cross-group and runs through the same approval gate / config allowlist.

## Naming

- **kernel** — the one always-on core (Layer 1 + Layer 2 + HTTP/WS serving).
- **ui/** — the front-end package (the three panes), renamed from `chat-view/`.
- **postal bus** — always-on messaging infra, below Layer 2.
- (No "UI server" / "UI kernel" process: merged into the kernel. No `romp --on`.)

## Open questions

- **Live permission-prompt content** may live only in tmux, not the transcript;
  the chip state is safe (from `states/`), but rendering *what* is being asked in
  chat for a bare permission prompt may need a fallback. Verify during build.
- **Read-federation** (one local view spanning multiple machines' records) — design
  when the SSH-forward-a-second-view stopgap proves insufficient.
- **The "settled" gate's exact definition** now that it lives in Layer 2 (see
  `design/judge.md`).
- **Where the comms-approval prompt surfaces** (the UI, the requesting session, or
  both) and how the approved-edge + alive-gating state is stored in postal.
