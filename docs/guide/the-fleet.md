# The fleet at a glance

See every agent in one place: what's running, what's stuck, and what's
waiting on you, and for how long.

![The dashboard: chat, feed, and timeline around one fleet](../assets/guide/dashboard-annotated.png){ width="100%" }

One kernel serves four views of the same live state. The **chat** is where you
talk to one agent. The **feed** shows the work as task cards. The **fleet**
lists every session with its open tasks. The **timeline** lays the sessions
out over time. Reach for whichever matches the question: "what needs me" is
the feed; "what happened while I was away" is the timeline.

## Status, in one color language

Tabs, lanes, and cards all speak the same states:

![The five session states and what each means](../assets/guide/status-legend.png){ width="70%" }

Blocked means a decision only you can make. Waiting on a build, a peer, or an
API retry never shows as blocked, so a red chip is always worth a look.

## The feed: what needs you

![The feed's three columns, with the cues on a card](../assets/guide/feed-annotated.png){ width="100%" }

Cards land in three columns: work that is moving on its own, work waiting on
you, and work that finished, each completed card carrying a takeaway summary.
[Tasks, not transcripts](tasks.md) covers what a card holds.

## The timeline: the fleet over time

![A timeline lane per session, with status and context at the left](../assets/guide/timeline-annotated.png){ width="100%" }

Each lane is one session; bars are stretches of work. The story of any bar is
a hover away:

![Hovering a bar pops what happened and when](../assets/guide/timeline-hover.png){ width="100%" }

## The chat: a transcript built for reading

![Tool calls fold into runs; each expands to one line per call](../assets/guide/chat-detail.png){ width="100%" }

Turns read as gists and tool calls fold into runs, so scanning is cheap and
every detail stays one click deeper: expand a run for its calls, and a call
for its full input and output.
