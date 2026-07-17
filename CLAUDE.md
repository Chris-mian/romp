# romp — repo instructions

## Philosophy
The bottleneck in AI coding is human attention. romp lets one person direct a
whole fleet of agents by spending that attention where it counts and surfacing
only what is worth acting on, so they keep the focus and flow that good work needs
while running many agents at once. Every feature should serve that aim:
- **Spend attention, don't drain it.** A feature should take load off the user's
  working memory, not add to it. Glanceable by default; mechanics one click away.
- **Make re-engagement cheap.** Speak in the user's terms, the outcome and the
  why, never the agent's play-by-play, so picking a thread back up costs a glance.
- **Interrupt only when the human is the bottleneck.** "Needs you" means a
  decision only they can make. Waiting on a peer, a build, or another session is
  not that. Every false interrupt is a broken flow state.
- **Scale to parallelism.** Features should hold up across many concurrent
  sessions and let agents coordinate among themselves, handling the details the
  user never needs to see.
- **Never lose the thread.** Context persists, dead sessions revive with their
  history, nothing important silently drops, so stepping away is safe.

## Privacy — no real session data or personal identifiers in this repo
This repo may go public; assume every commit is permanent and world-readable.
- **Never copy real recorded data into the repo** — no real prompts,
  transcripts, per-turn summaries, postal messages, or message ids, not even
  "just one" to reproduce a bug. When a real session triggers a bug, write a
  SYNTHETIC reproduction: invented prompt text, placeholder UUIDs
  (`11111111-2222-...`), hostname `TESTHOST`. Live data belongs only under
  `~/.local/state/romp/` and `~/.claude/` (both outside the repo).
- **No personal identifiers** in code, comments, fixtures, docs, or commit
  messages: no names, machine/host names, vault names, emails, or absolute
  home paths (use `$HOME`/`~`).
- `tests/test_no_personal_identifiers.py` enforces this mechanically (local
  hostname, home path, plus `~/.config/romp/private-strings.txt`); run it
  before committing fixtures.

## Worktrees — work on an isolated worktree by default (user rule, 2026-06-29)
Do ALL non-trivial work on its own git worktree, not the shared main tree — concurrent
peer sessions clobber/commit each other's uncommitted edits in the shared tree (a peer's
broad `git add` will sweep up your work). Conventions:
- **One worktree per session, named after the session.** Branch + directory take the
  session's name, e.g. session `bugsdk2` → branch `bugsdk2`, dir `../romp-bugsdk2`
  (`git worktree add -b <session> ../romp-<session> HEAD`). So a glance at
  `git worktree list` says who owns what.
- **Standing green light to merge.** When the work is done and tests pass, merge it back
  to `main` and push — no need to ask first. (This is explicit standing permission from
  the user; the usual "branch first / ask before committing" caution is lifted here.)
- **Clean up when finished.** After merging, remove the worktree
  (`git worktree remove ../romp-<session>`) and delete its branch — don't leave stale
  worktrees lying around.
- **Exception:** a quick, already-in-flight change in the main tree (or an explicit
  "do this in main") can stay there — commit it promptly with a focused `git add <paths>`
  (never `git add -A`, which sweeps peers' edits). See [[shared-worktree-use-isolated]].

## Testing
Every bug fix or feature change must land with a test that covers it (user rule,
2026-06-12). Test homes: `tests/test_romp_events_golden.py` and the other
`tests/test_*.py` for the Python pipeline (`kernel/`, `cli/`, `postal/`), `tests/*.bats` for shell
surfaces. Reproduce the bug in a failing test first when practical; fixtures
live in `tests/fixtures/`.

## Authoritative sources — fail loudly, don't degrade silently (user rule, 2026-07-03)
Read state from its AUTHORITATIVE source — a designed API, or the live store that
owns the data — never a lossy reconstruction (scraping a transcript, a heuristic
guess). When choosing a source, first look for a real API; only fall to reading a
store/file if none exists, and say so.

When the authoritative source is UNAVAILABLE, **surface an error to the user** —
do NOT silently fall back to a worse heuristic that can be quietly wrong. A visible
error we can see and fix beats stale/incorrect data that looks fine and misleads.
A silent fallback hides the very breakage we need to know about. (Triggered by the
TO-DO card, which folded the transcript — missing subagent updates — instead of
reading Claude's task store; the fix reads the store and surfaces an error when it
can't, rather than quietly folding. There is no SDK API for the to-do checklist —
verified, not assumed.) This is the same spirit as the event-vs-heuristic rule
below: don't approximate when the real thing is available; when it isn't, be loud.

## Design
Prefer exact event-based mechanisms over time-based heuristics (grace periods,
debounces, age thresholds). If a time window seems needed, find the event it is
approximating and key on that event instead.

### Progressive disclosure is the UI's organizing principle (user rule, 2026-07-17)
Every surface defaults to its most COMPACT legible form, and you can always click
to go one level deeper — gist → summary → full mechanics, each level a click. When
adding or changing any UI element, ask "what is the one-line version?" and render
that by default, with the rest behind a keyed expand (state survives re-renders —
`openFolds` / `expandedGroups`). Never dead-end a compact view: if there is more
underneath, it must be clickable. Existing examples: tool heads with inline folds,
collapsed tool-group runs, notice cards, postal/teammate cards, nudge gists,
Task/Agent prompt+report. This is the "Glanceable by default; mechanics one click
away" bullet of the Philosophy, stated as the standing rule for every new surface.

### Font sizes: few, and consistent by information type (user rule, 2026-07-02)
Do not multiply font sizes. Similar kinds of information wear the SAME size — labels
match labels, times match the lines they annotate, section bodies match each other.
Before adding a new `font-size`, reuse one already on the surface; nesting relative
`em` sizes compounds (a 0.74em button inside 0.86em text renders smaller than its
siblings), so prefer flat contexts or compensate explicitly. Triggered by the
follow-up header rendering as a soup of 0.74/0.78/0.9em fragments.

### The accent color is light blue `#9cd2ff` — use `var(--accent)`
The romp accent is light blue `#9cd2ff` (`--accent` in `ui/webview/styles.css`, with
`--accent-fg: #0c1a2e` for text on it). Use it for accent/highlight chrome — selected
toggles, in-progress loading dots, the Fleet pill, focus cues — anywhere you want "the
romp blue." Do NOT use it for STATUS colors, which keep their own meaning: working =
`--st-working-bg` (yellow), blocked/API-error = red, ready = `--st-ready-bg`, compacting =
teal. New accent chrome should reference `var(--accent)`, never re-hardcode the hex.

### Loading/waiting states: show the romp loader FIRST
Anytime something is loading, parsing, or otherwise making the user wait, the FIRST
thing to put up is the romp loader animation — the spinning swirl glyph
(`/media/romp-swirl-glyph.svg`, reverse spin) + the "romp" wordmark + three pulsing
accent-blue (`#9cd2ff`) dots — centered over the waiting surface, fading the instant
real content arrives (event-based; a backstop timeout so it can never trap the user).
It's the boot splash (`_landing` `#romp-boot`) and every pane's loader (`_pane_spin`).
Reuse that treatment for any new wait state rather than a blank, a bare spinner, or
text — a consistent "something's happening, it's romp" beats a frozen-looking screen.
A determinate progress bar is even better *when real progress is knowable*; default to
the loader animation otherwise.

### Buttons must stay click-safe across re-renders, and always acknowledge
The dashboard re-renders on every kernel push (a 0.5–3s backstop, plus an
immediate push per SDK stream event and per hook `/tick`). A control whose action
is hung on a DOM node that a re-render rebuilds gets destroyed mid-click — a
native `click` needs mousedown AND mouseup on the same element, so a rebuild
between them silently drops the click. That is the "had to click it several
times" bug. Every interactive control MUST therefore:

1. **Be click-safe across re-renders.** Never attach the action to a node you
   rebuild. Either:
   - **Delegate** to a STABLE ancestor — the container fetched by id survives
     `replaceChildren()`; only its children are swapped — and key the action off a
     `data-act` attribute. Use the shared helper `ui/webview/actions.ts`
     (`delegate(root, handlers)`), installed ONCE per root, never in a render
     loop. This is the default for HTML lists (chat tab bar `#tabs`, Fleet
     `#fleet-list`). A click whose original target was swapped mid-press still
     bubbles to the stable ancestor, so it always lands.
   - For full-canvas redraw surfaces (the SVG timeline) where threading every
     action param through data-attrs is impractical, **defer the rebuild while a
     pointer is pressed** over the surface and flush on `pointerup`/`pointercancel`
     (event-based, not a time heuristic), so the pressed element survives the
     click. See `ui/romp-timeline-view.js` `draw()`'s `_pointerHeld` guard.
2. **Always acknowledge the click immediately**, before any kernel round-trip —
   so the user never re-clicks because "nothing happened." `actions.ts`'s
   `flash()` adds a layout-safe `.romp-acted` press pulse on every delegated
   activation; a button that posts-and-waits (e.g. feed Nudge) must also disable +
   change its own label on click and self-restore. The error / dialog / result
   follows the acknowledgement; it does not replace it.

Reuse `ui/webview/actions.ts` for any new dashboard control. (`.romp-acted` is
defined in both `styles.css` and `feed.css` since the feed page loads only the
latter.)
