# Romp

AI agents like Claude Code can work autonomously for long stretches, so
running several in parallel multiplies what you can accomplish. But it also
means more to manage: keeping track of which agent is doing what,
scrolling through transcripts to find the background a
decision needs, checking in to see which agents are stuck, and coordinating
handoffs of work and information between them.

Romp provides the tools to make this management seamless, so you can stay
focused on what you're trying to accomplish instead of how the work is
happening. It organizes your interaction with the agents by human-facing
tasks and goals:

- **See the whole fleet at a glance.** One place shows every agent: who is
  working, who is stuck, and who is waiting on you.
- **Pick up any thread in a glance.** Each task carries a plain-language
  summary and the background a decision needs, so you never dig through
  transcripts to get your bearings.
- **The fleet keeps moving on its own.** An agent that stalls with work left
  gets nudged back to it, so progress does not wait on you noticing.
- **Agents coordinate with each other.** They hand off work and ask each other
  questions directly, across machines, while you stay in the loop.

New to Romp? Start with [Getting started](getting-started.md).

## Everything stays on your machine

Romp only ever talks to `127.0.0.1` (the local kernel and postal service); the
only external traffic is the `claude` CLI you already use. Recorded state lives
under `${XDG_STATE_HOME:-~/.local/state}/romp/` and is never uploaded.
