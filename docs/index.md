# romp

A multi-agent session manager for **Claude Code** on tmux. romp turns a fleet of
terminal Claude sessions into a coordinated, observable system: named, colored,
persistent sessions; inter-session mail; automatic per-turn captions; and a live
activity feed, goal inbox, and timeline.

!!! note "This site is a scaffold"
    The pages here are stubs to show the shape and styling. Start writing — they
    publish automatically to GitHub Pages once the repo is public and Pages is
    enabled. See [Getting started](getting-started.md) to set up locally.

## Why romp

> The bottleneck in AI coding is human attention.

romp lets one person direct a whole fleet of agents by spending that attention
where it counts and surfacing only what is worth acting on — so you keep the
focus and flow that good work needs while running many agents at once.

<div class="grid cards" markdown>

-   :material-console:{ .lg .middle } **Sessions**

    ---

    Named, colored, persistent tmux sessions tagged `@romp` — launch, resume, attach.

    [:octicons-arrow-right-24: Getting started](getting-started.md)

-   :material-email-fast-outline:{ .lg .middle } **Postal service**

    ---

    Inter-session mail: send, inbox, working-notes, parked handoffs, revive.

    [:octicons-arrow-right-24: The postal service](guide/postal-service.md)

-   :material-sitemap-outline:{ .lg .middle } **The kernel**

    ---

    One always-on process parses transcripts, runs the judges, serves the UI.

    [:octicons-arrow-right-24: Architecture](architecture.md)

-   :material-view-dashboard-outline:{ .lg .middle } **The panes**

    ---

    Chat, feed, and timeline — open `http://127.0.0.1:7433/` in any browser.

</div>

## Everything stays on your machine

romp only ever talks to `127.0.0.1` (the local kernel and postal service); the
only external traffic is the `claude` CLI you already use. Recorded state lives
under `${XDG_STATE_HOME:-~/.local/state}/romp/` and is never uploaded.
