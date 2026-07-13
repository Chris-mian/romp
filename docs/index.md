# Romp

AI agents like Claude Code can work autonomously for long stretches, so
running several in parallel multiplies what you can get done. But it also
creates management overhead: keeping track of which agent is doing what,
scrolling through transcripts to find the background a
decision needs, checking in to see which agents are stuck, and coordinating
handoffs of work and information between them.

Romp provides the tools to make this management seamless, so you can stay
focused on what you're trying to accomplish instead of how the work is
happening. It organizes your interaction with the agents by human-facing
tasks and goals.

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

Romp only ever talks to `127.0.0.1` (the local kernel and postal service); the
only external traffic is the `claude` CLI you already use. Recorded state lives
under `${XDG_STATE_HOME:-~/.local/state}/romp/` and is never uploaded.
