# The postal service

Sessions message each other through a mailbox Romp gives them, and every
exchange is visible to you.

Each session gets mail tools: send a message to a session by name, check the
inbox, see who is live and what they hold. Agents use them to ask each other
questions, hand off work, and announce results. You watch it happen on the
timeline and in the chat:

![A message hop between two sessions, with its gist on hover](../assets/guide/postal-timeline.png){ width="100%" }

![The same message as the recipient's chat shows it](../assets/guide/postal-chat.png){ width="80%" }

## Message kinds

Every message declares what it is: **delegate** (the recipient owns the work
now), **coordinate** (a heads-up; reply optional), or **question** (an answer
is required). The declaration travels with the message, so the recipient and
the task cards treat it accordingly.

## From the shell

The same mailbox is on the command line, for you and for scripts:

```bash
romp --mail send --kind question api "Which auth approach did we settle on?"
romp --mail inbox
```

The full mail surface, shell and in-session, is in the
[Reference](../reference.md).

!!! info "Only live sessions"
    Names resolve against the currently live fleet. Sending to a dead
    session's name errors instead of silently parking mail.
