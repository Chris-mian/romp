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
- **Paraphrase the user, never quote them.** The `(the user <date>: ...)`
  attribution convention that explains WHY code exists is fine — but it must
  paraphrase, never embed a verbatim quote of what they typed. A quoted
  utterance is real recorded data. Write `(the user 2026-07-02, who wanted one
  shared picker)`, NOT `(the user 2026-07-02: "same code path, one picker")`.
- **No real session or goal names from OTHER projects.** A bug that surfaced in
  some other session is documented with a SYNTHETIC session name (`web`, `api`,
  `TESTHOST`) and an invented goal title — never the real project's nickname or
  goal text (which leaks what that unrelated project is). Add any coined
  project/session nickname to `~/.config/romp/private-strings.txt` so the test
  catches it. Reuse the neutral demo domain the doc screenshots use (a
  `notes-api` with `web`/`api`/`tests` sessions) rather than inventing per-test
  worlds.
- The maintainer's clone carries an UNTRACKED `tests/test_no_personal_identifiers.py`
  that scans for that machine's own hostname, home path and private strings, wired
  into the pre-push hook. It is deliberately not in the repo: those strings are
  specific to one machine and mean nothing on anyone else's clone, so a
  contributor's test run must never trip over it. Where it is absent, the hook and
  its tests no-op. Either way it is a backstop, not the rule — the rule is the
  bullets above. It also reads text only, so screenshots and recordings under
  `docs/assets/` must be eyeballed for on-screen session content before release.

## Worktrees — work on an isolated worktree by default (user rule, 2026-06-29)
Do ALL non-trivial work on its own git worktree, not the shared main tree — concurrent
peer sessions clobber/commit each other's uncommitted edits in the shared tree (a peer's
broad `git add` will sweep up your work). Conventions:
- **One worktree per session, named after the session.** Branch + directory take the
  session's name, e.g. session `bugsdk2` → branch `bugsdk2`, dir `../romp-bugsdk2`
  (`git worktree add -b <session> ../romp-<session> HEAD`). So a glance at
  `git worktree list` says who owns what.
- **Never commit on the shared `main` checkout** (user rule, 2026-07-24). Branches and
  worktrees are how work happens here, with no "quick one in main" exception. A commit
  that lands on the local `main` branch and is not pushed immediately makes local `main`
  diverge from `origin/main`, and then every peer session is stuck: they cannot push,
  cannot fast-forward, and cannot reset the shared tree without destroying whatever
  uncommitted edits other sessions are holding in it. This happened on 2026-07-24 (six
  docs commits stranded on local `main`, already duplicated on a PR branch, blocking two
  other sessions).
- **Standing green light to publish.** When the work is done and tests pass, publish it
  without asking: push your branch, then merge it on the remote or open a PR. If `main`
  itself needs moving, do that in a throwaway worktree at `origin/main` and push right
  away, so local `main` is never left ahead of `origin/main`.
- **Clean up when finished.** After publishing, remove the worktree
  (`git worktree remove ../romp-<session>`) and delete its branch — don't leave stale
  worktrees lying around.
- **When you do touch the shared tree** (reading, or an explicit "do this in main"), use
  a focused `git add <paths>` — never `git add -A`, which sweeps peers' edits — and never
  `git reset --hard` or `git clean` there: other sessions' uncommitted work lives in that
  tree and it is not yours to discard. See [[shared-worktree-use-isolated]].

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

## Messages we inject into a session: the agent does not know romp exists (user rule, 2026-07-24)
Every message romp puts into a session — a nudge, a follow-up, a clear wrap-up, a
canned status ask — is read by an agent with NO idea it is being tracked. It has
never seen the feed, has no concept of a card, a goal, a board, or a column, and
cannot act on any of it. So write these as **the person it works for asking for
something**, in their words:
- **No romp nouns in the prose**: card, board, goal, column, cleared, dismissal,
  nudge, status check. Say the thing instead. "Status check on this card" → "Where
  does each of these stand?"; "the goal above was cleared off the board — a
  dismissal, not a completion" → "I'm dropping this one."
- **No taxonomy handed over as reply slots.** romp's planner files four verdicts
  (done / in progress / blocked-on-you / obsolete), but naming them at the agent
  turns a question into a form. Ask like a person — "what shipped, what's next, or
  exactly what you need from me if you're stuck" — and the same four answers come
  back for the planner to file.
- **Short.** A long directive reads as a system notice however it is worded. The
  clear wrap-up carries the same content in about half the words it started with.
- Draft this copy with the `jld` skill, the way any user-facing writing is drafted.

TWO deliberate exceptions, both fine, neither a licence to widen:
- **The SessionStart instruction** that asks a session to report what it finished
  and what it is blocked on. That asks for ordinary self-reporting; it names no
  romp machinery and needs none.
- **The marker tail** (`<!-- romp-note: … an external tracking system that is not
  relevant to your work — ignore them -->`). It describes the markers WITHOUT
  naming romp, on purpose: naming it would explain nothing to a model that has
  never heard of it.
- Also fine: the `[romp] The kernel restarted…` notices in `sdk_backend.py`. Those
  are genuinely ABOUT romp — they tell a session why its turn was cut — so they
  name it.

`tests/test_injected_voice.py` renders every injected body and fails on romp
vocabulary in the prose, so this holds without anyone remembering it.

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
