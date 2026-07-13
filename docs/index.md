# romp

AI coding agents can do more and more on their own, so it is natural to run
several at once. But managing them can consume the attention you meant to
spend directing them: keeping track of which agent is working on which task,
scrolling through transcripts for the background a decision needs, checking
in on the agents to see which ones are stuck or need you, and coordinating
work across the agents yourself, since they have no way to talk to each
other.

Romp provides the tools to do the managing, so your attention stays on
directing: one dashboard shows every agent and what needs you, the work is
organized by task rather than by session, stalled agents get nudged back to
their open work, and agents message each other directly, across machines.

<div class="grid cards" markdown>

-   :material-console:{ .lg .middle } **Sessions**

    ---

    Named, colored, persistent sessions on the Agent SDK or tmux backend:
    launch, resume, attach, revive.

    [:octicons-arrow-right-24: Getting started](getting-started.md)

-   :material-email-fast-outline:{ .lg .middle } **Postal service**

    ---

    Inter-session mail: send, inbox, working-notes, parked handoffs, revive.

    [:octicons-arrow-right-24: The postal service](guide/postal-service.md)

-   :material-sitemap-outline:{ .lg .middle } **The kernel**

    ---

    One always-on process reads the transcripts, infers the tasks, and serves
    the UI.

    [:octicons-arrow-right-24: Architecture](architecture.md)

-   :material-view-dashboard-outline:{ .lg .middle } **The four views**

    ---

    Feed, fleet, timeline, and chat. Open `http://127.0.0.1:7433/` in any
    browser.

</div>

## Everything stays on your machine

romp only ever talks to `127.0.0.1` (the local kernel and postal service); the
only external traffic is the `claude` CLI you already use. Recorded state lives
under `${XDG_STATE_HOME:-~/.local/state}/romp/` and is never uploaded.
