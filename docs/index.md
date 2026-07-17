# Romp

AI agents like Claude Code can work autonomously for long stretches, so
running several in parallel multiplies what you can accomplish. But it also
means more to manage: keeping track of which agent is doing what,
scrolling through transcripts to find the background a
decision needs, checking in to see which agents are stuck, and coordinating
handoffs of work and context.

Romp provides the tools to make this management seamless, so you can stay
focused on what you're trying to accomplish instead of how the work is
happening. It does this by keeping track of every agent and the tasks it is
working on, surfacing what needs your attention and keeping the rest moving on
its own:

<!-- Feature grid. Real captures live in docs/assets/; the README grid points at the same files.
     The docs home embeds the MP4 in a <video> for the last tile; the README embeds the GIF. -->
<div class="grid cards" markdown>

-   ![Every session with its status in one view](assets/tile-glance.png)

    **Everything at a glance**

    What's running, what's stuck, and what needs your attention.

-   ![Work grouped into task cards](assets/tile-tasks.png)

    **A task management layer**

    Automatically inferred from the transcripts, so nothing gets lost.

</div>

**Context where you need it** &mdash; what the agent did and why, without having to
scroll through transcripts.

<div class="grid" markdown>
![A card's background: why the work is happening](assets/tile-context-background.png)
![A card's summary: what the agent did](assets/tile-context-summary.png)
</div>

**Coordination you can see** &mdash; agents asking each other questions and handing off
tasks, through a mailbox Romp gives them.

![A message crossing between two sessions on the timeline](assets/tile-coordination-timeline.png)

![The same message, shown in the chat](assets/tile-coordination-chat.png)

**Detail on demand** &mdash; hover a work bar, open a summary, expand a tool call:
everything opens up when you want more.

<video src="assets/overview.mp4" autoplay loop muted playsinline width="100%"></video>

Romp adds all of this on top of the agents you already run, whatever they are
and whatever tools they use, without changing how you work.

## Self-hosted, reachable from anywhere

You run Romp yourself, on your laptop or a server, with no hosted service in
between. Connect several machines over SSH and they federate into one fleet
whose agents message across the boundary. Open the dashboard in a browser or
as a VS Code / Cursor extension, and reach it from your phone over Tailscale
to check in or keep a conversation going. The only traffic that leaves your
machine is the `claude` CLI you already use.

## Quick start

```bash
git clone https://github.com/romp-on/romp.git
cd romp
./install.sh
export PATH="$PATH:$(pwd)/bin"   # add this to your shell rc
```

Then open `http://127.0.0.1:7433/` in any browser and start a session. Full
requirements, remote-host setup, and configuration are in
[Getting started](getting-started.md).

## See it in action

Romp presents the fleet through four views: the feed (work as task cards), the
fleet (every session with its open tasks), the timeline (sessions over time and
where they interact), and the chat you already know. The walkthrough above runs
through all four.

