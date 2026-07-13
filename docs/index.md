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
working on, surfacing what needs you and keeping the rest moving on its own:

- **See the whole fleet at a glance.** One place shows every agent: who is
  working, who is stuck, and who is waiting on you.
- **Pick up any thread in a glance.** Each task carries a plain-language
  summary and the background a decision needs, so you never dig through
  transcripts to get your bearings.
- **The fleet keeps moving on its own.** An agent that stalls with work left
  gets nudged back to it, so progress does not wait on you noticing.
- **Agents coordinate with each other.** They hand off work and ask each other
  questions directly, across machines, while you stay in the loop.
- **Never lose your place.** A closed session revives with its full history,
  and everything is searchable, so stepping away is always safe.

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
where they interact), and the chat you already know.

<!-- TODO: screenshots / short GIFs go here. Planned captures:
     - The fleet at a glance: the dashboard with several agents, each showing status (working / stuck / needs you).
     - A task card opening to its summary and background ("Tasks, not transcripts").
     - A stalled agent getting nudged back to its open work.
     - Two agents exchanging postal mail (a delegate / handoff / question).
     - The timeline laying sessions out over time and showing where they interact.
     - Reviving a closed session with its history intact.
     - Reaching the dashboard from a phone over Tailscale.
     - The VS Code / Cursor extension panel beside a browser tab (same fleet, two surfaces).
-->

