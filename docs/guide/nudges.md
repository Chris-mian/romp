# Automatic nudges

An agent that goes idle with open work gets nudged back to it, so progress
does not wait on you noticing a stall.

Claude Code sessions routinely stop with to-dos still open. With auto-nudge
on (the gear menu; off by default), Romp notices the stall and asks the
agent, item by item, where each open piece stands: continue what it can, and
say what blocks the rest.

- If the agent can keep going, it does, and you were never interrupted.
- If something needs you, the card flips to **Blocked** and names exactly
  what it needs.

Either way you only get pulled in when you are the bottleneck.

A nudge is also a button: every card has one, so you can prod a single
session yourself without typing a message.

Auto-nudge holds off while you are actively driving a session, and it re-arms
only after a real turn ends, so it never talks over you and never loops on
its own messages.
