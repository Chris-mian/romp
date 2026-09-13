# The chat is one scrollable conversation: lazy history regions and one landing notice (T386)

**Status:** the user approved the design and answered the four questions (2026-09-12 about 3:45 PM PT; the answers are folded
into the sections below). Stage 1 is its own fix pull request; stages 2 and 3 follow. Written against upstream/main at ff6b46cb;
the line references describe the repo at that commit.

## What the user saw and asked for (paraphrased, 2026-09-12 about 2:25 PM PT)

They clicked a card. The chat did not land on the message the first time; a second click was needed. Then a strip
at the bottom said the chat was showing the message from 7:41 AM with live updates paused, and they do not see why
live has to pause at all. The model they want:

- The whole conversation is ONE scrollable surface. A stretch not yet loaded renders as a placeholder with a loading
  mark and loads lazily as it scrolls into view.
- The live tail keeps updating below. There is no return-to-live, because live never left; the history in between
  is simply not resident until scrolled to.
- A landing deep into history: the view first jumps toward the target, and instead of today's two messages (the
  loading pill at the top and the strip at the bottom) there is ONE notice saying the view is going to the earlier
  message, cancelable by clicking it. If not cancelled, the view snaps to the target as soon as that region has
  loaded.

Today (proto 2, T323 stage 4b) a client holds one contiguous run of events. A landing outside the run asks the
kernel for a window around the anchor (`loadAround` → `chatWindow`); a window with more after it leaves the client
DETACHED: the kernel sends it no live delta, a bottom strip says so and offers "Return to live", and the client walks
forward page by page (`loadNewer` → `chatMore`) or asks for a full frame to re-attach. The pill "Loading earlier
messages…" shows while any fetch is in flight. The detached mode is the reason live pauses; the user's model has no
detached mode.

## Part A: the double click, from the landing audit

The rows (the kernel serving the session files one per landing attempt in `locate-audit.jsonl`; read on the devbox,
not copied into the repo) show the same shape three times in four minutes, in a session of this project:

1. `ok false`, trail `pointer-fetch-window`, the anchor's time present. The click: the anchor is outside the resident
   run, so `scrollToAnchor` asks for a window (`requestAround`) and files the honest "not yet".
2. Two seconds later `ok true`, trail `pointer-exact`, the anchor's time NULL. The window arrived (`chatWindow`),
   the re-render found the anchor's turn and landed it.
3. Seventeen seconds later `ok true`, `pointer-exact`, the time present again. A second click on the same card: the
   anchor is resident now, the landing is direct and the reader sees it.

Between rows 2 and 3 the reader saw the view somewhere else. So row 2's `ok` was not a lie about what it asserts, but
what it asserts is too little.

**What `pointer-exact` asserts** (render.ts `scrollToAnchor`, ~11192): the target element was FOUND in the rendered
DOM by one of five selectors, the kind guard passed, and `landOn(target)` was called. `landOn` (~11280) issues one
write (`scrollElInto(content, target, "start")`, attributed `land-on`) and re-aligns for 1.2 s ONLY when `#tabbar`
or `#ledger` change size (a ResizeObserver on those two), stopping on the reader's first wheel. Nothing measures
where the viewport is afterwards, and nothing re-aligns when the TRANSCRIPT's own boxes move: the top spacer being
re-sized from its estimate to its measured height (`sizeSpacers`, ~11620: units × `avgTurnH`, 60 px until the rows
are measured), a rewindow write (`virtualizeToViewport`, ~13370, attributed `rewindow`), or the walk-forward that
`edgeCheckAfterWindow` (~17065) starts when a detached window fits the viewport (`requestNewer` → `chatMore` →
`showActive`, a rebuild). Any of those moves the target off the top after `land-on` has been filed as exact.

**What the first click's null time did**: nothing to the landing itself, and one thing to the record. The time
rides `pendingAnchorT`, set by `setActive` from the card's frame (~16455). `requestAround` copies it into
`pendingWindowNav.t` for the strip's sentence (that is how the strip could later say "7:41 AM"). The window's
adoption (`chatWindow`, ~17056) then re-arms the anchor for the landing pass and RESETS `pendingAnchorT` to null
(and `pendingAnchorKind`), so the landing pass has the id and no time, and files the row without it. The landing
never needed the time (the id resolved), but the row lost the datum that ties it to the click, and any future
nearest-moment fallback would have nothing. Carrying the time through the adoption is a one-line correctness fix.

**The other shape** (twice more in the same session, minutes apart): `ok false pointer-fetch-window` then `ok true
pointer-exact` a second or seven later, then a second click within seconds. Same mechanism.

### The red-first lab (before any fix)

`tests/test_landing_settles_browser.py`, from the T366 lab's boot (a hermetic kernel, a synthetic transcript of 320
turns so older history stays on the server, the real `/chat` page): a navigation frame with an anchor and its time
into history the page does not hold (the card's road, T366 road 2). The lab reads three things:

- the landing row the page posts (`locateDiag` on the socket hook): trail, `ok`, `anchorT`;
- the target turn's offset from the viewport top at the landing row, then again at 300 ms, 700 ms and 1500 ms;
- the page's own scroll-write ledger (the `scrollwrite` diagnostic rows carry the writer's name, T262j: `land-on`,
  `land-realign`, `rewindow`, `anchor-restore`, `append-raw`, `land-saved` …), so the run names WHICH write moved the
  view after `land-on`, and by how much.

Red today when the offset at 1500 ms is more than a row away from the top, or when the row's `anchorT` is null on a
frame that carried a time. The writer named in the ledger is the diagnosis; the fix below covers every candidate,
but the lab's ledger decides which one it was, and the head mail quotes it.

### The fix (stage 1)

- **A landing settles, and says so.** `landOn` keeps the target aligned until the transcript stops moving under it:
  the ResizeObserver also watches the view's spacers and the target's own box, a `rewindow` or `anchor-restore` write
  during the settle window re-lands instead of moving the reader, and the wait ends on the reader's own gesture as
  today. The landing row is filed when the landing SETTLES, with two new fields: `dist` (the target's offset from the
  viewport top in px at settle time) and `settled` (`dist` within one row height). `ok` keeps its meaning (resolved
  by id); a row with `ok true, settled false` is the shape row 2 should have been.
- **The time rides through the adoption.** `chatWindow` keeps `pendingAnchorT`/`pendingAnchorKind` when the window's
  anchor is the pending one (it re-arms the same landing, not a new one).
- **A detached window that fits the viewport is not walked forward under a fresh landing.** The walk that
  `edgeCheckAfterWindow` starts waits for the landing to settle (in stage 2 the walk disappears with the detached
  mode).

Pins: `ui/webview/landing-settle.test.ts` executes the settle rule as a pure module (`landing-settle.ts`: given the
target's offsets over time and the writes in between, when the landing is settled, when it re-lands, when it gives
up), and the render.ts wiring pins (`landOn` observes the spacers and the target; the row carries `dist` and
`settled`; the adoption keeps the time). The T366 lab's road 2 gains the settle measurement too.

## Part B: the design

### The model

A session's transcript is an ordered list of REGIONS covering turns `[0, floor)` plus the live tail:

- a **run**: resident events (rendered turns, virtualised as today);
- a **gap**: a turn span `[lo, hi)` the page does not hold, rendered as EMPTY SPACE in the thread, one placeholder
  element of an estimated height, with a loading mark that says it is loading: the romp loading glyph (the swirl, the
  wordmark and the three accent dots, the dashboard's own loading vocabulary, `_pane_spin` and the boot splash) drawn
  large enough to read at a glance, never the small pill (the user 2026-09-12).

The **tail run** is always resident and always live: `chatTail` deltas apply to it by `afterUuid` exactly as today.
No client is ever detached, so the kernel never withholds a delta; the bottom strip, "Return to live",
`windowDetached`, `windowLanding`'s reattach road, `reattachLive`, `reattachKeys` and `requestNewer`'s walk all go.
The jump-to-bottom chip stays as the way to the tail; the scrollbar spans the whole transcript through the gaps'
estimated heights, as the spacers make it span the resident run today.

The pure rules live in a new `ui/webview/chat-regions.ts` (executed by `chat-regions.test.ts`):

- `insertRun(regions, run, span)`: a window's events with the kernel's turn span become a run; the gaps on either
  side shrink or split; an overlap merges (the T323 `mergeWindow` order rule carries over).
- `gapHeight(span, avgTurnH)`: turns × the measured average row height (60 px until measured), rounded, so a gap's
  size has the same estimate the spacers use today.
- `pagesToAsk(gap, viewport, avgTurnH)`: the page-aligned span to request when a gap enters the viewport: the page
  nearest the viewport's edge first (scrolling up through a gap asks for its bottom page; a landing asks for the
  anchor's pages), one request per gap in flight.
- `foldCandidates(regions, viewportRegion, budgetBytes)`: which runs fold back to gaps (see the bound below).
- `landingNotice(t, clock)`: the one notice's sentence; `landingCancel(state)`: what cancel leaves behind.

### DOM and scroll anchoring

A gap is one `.tx-gap` element inside the view (`data-lo`, `data-hi`, `style.height`): empty space with the romp loading
glyph centred in it while a request is in flight (the boot splash's glyph at a size read at a glance; the loading pill's
small dress is not this mark). Gaps carry `overflow-anchor: none`: the browser then never picks a gap as its scroll anchor node, so
when a gap above the viewport is replaced by its turns, or re-sized from estimate to measurement, Chromium keeps the
first visible TURN where it is (styles.css already records why `#content` keeps `overflow-anchor` on: 0 px drift with
it, 194 to 246 px without). A gap entering the viewport is detected by one `IntersectionObserver` over the gap
elements (an event, not a scroll poll), which asks for `pagesToAsk` and marks the gap loading. When the reply
arrives, the gap is replaced by a run region in one DOM operation (`replaceChildren` on a fragment): the turns
render through the existing virtualiser, so a large run still has spacers inside it. **A fill moves nothing** (the user
2026-09-12): the content appears in place and `scrollTop` does not change at all, on every fill, above the viewport
included. The placeholder's height is an estimate, so the fill compensates the difference exactly in the same frame:
after the replace, the rendered run's height minus the gap's height is added to `scrollTop` when the gap sat above
the viewport's top (one attributed write, `gap-fill`), and nothing is written when it sat below; `overflow-anchor`
stays on as the belt for the browser's own compensation. The lab reads `scrollTop` and the target turn's rect before
and after every fill and asserts both unchanged, for a gap above the viewport and for one below.

The virtualiser's two spacers become the gaps' cousins: a run longer than the render window keeps its own
`.tx-spacer` pair as today; gaps stand between runs. `virtualizeToViewport` keeps its edge logic per run; the
"older on server" band at the top of the FIRST run becomes a gap `[0, lo)` when the head is not resident, so the
existing older-history ask is the gap's ask.

### Landing

A card, lane, notch, deep link or seek names an anchor (uuid, time, kind). If the anchor is resident, the landing is
today's (`scrollToAnchor`, settled per part A). If not:

1. The page asks the kernel for the anchor's pages (`loadAround` as today, whose reply now carries the turn span).
2. Immediately, the view jumps STRAIGHT to the position where the target will be (the user 2026-09-12): the anchor's
   time against the resident runs' times picks the gap it falls in, and its place inside the gap is the time's
   proportion between the gap's neighbours' times, so the reader sees the loading glyph in the empty space at the
   spot the words will fill. With no time and no resident neighbour (a bare uuid into a wholly unloaded history)
   the view does not move until the reply; the notice still shows.
3. The ONE notice appears at the loading pill's anchor before `#content` (`.tx-loading-anchor`, the place T365 chose
   so the pill follows the tab strip's bottom by layout): "Going to the message from 7:41 AM, click to stay here" (the
   time in the user's clock, as the strip renders it today) or "Going to the earlier message, click to stay here"
   (without a time). The pill's "Loading earlier messages…" is retired for landings; a scroll-driven gap fill shows
   the glyph inside the gap and no notice. Clicking the notice is the ONLY cancel (the user 2026-09-12): the reader's
   own scroll during the wait does not cancel the landing.
4. When the reply lands, the run is inserted and, unless cancelled, the view snaps to the target (top-aligned, the
   flash, the settle rule) and the notice goes. The landing row is filed at settle time.
5. **Cancel** (a click on the notice): drops the pending target and the notice; the reply still inserts its run
   when it arrives (the pages are loaded; nothing is thrown away) and the view is NOT moved. The reader stays where
   they are, including where step 2 put them; a second click on the same card is a new landing.

This is also the answer to the item held for the user after T366 (whether a landing that arrives after the reader
scrolled since the click should still land): the reader's own gesture during the wait does not cancel; the notice is
the cancel, one click, visible the whole time.

### The kernel

Today the kernel keeps one base per client (`{first, last, detached}`) to decide whether a window `connected` to the
held run and whether to withhold deltas. With the tail always resident:

- The client's base is the TAIL only (`{last}`, plus `first` for the tail run's older edge as `loadOlder` uses it).
  `detached` and `connected` retire from the base and the replies.
- `loadAround` keeps its shape and gains `span: [lo, hi]` (turn indices) and `floor`, so the client can place the run
  among its gaps and size the remaining gaps; `loadOlder` (a gap's bottom page) gains the same span; a new
  `loadTurns {lo, hi}` asks for a page-aligned span directly (a gap's page nearest the viewport that is not an
  older-edge ask). `_window_turns`, `_history_pages` and the pages cache serve all three unchanged.
- `loadNewer`/`chatMore` retire with the walk (a gap fills from either edge through `loadTurns`).
- The pusher's floor decision (`_chat_floor0_of`) and the per-client protocol are untouched; `reattachKeys` and the
  "reattach" full-frame reason retire; `fullFrameMerges` keeps only its change-driven replace meaning.

### The memory bound

**Stage 3 waits for a measurement** (the user 2026-09-12, deferring to the performance thread): before any fold rule, the
performance session is asked, with numbers from a lab over a long synthetic transcript, what a resident run costs in
the page (DOM nodes and JS heap per turn), whether a bound is needed at all, and if so which fraction rule they would
use; stage 3's shape follows their answer. The user's rule stands whatever the answer: any cap is a fraction of memory,
never a literal. The design below is the shape a bound would take.

Runs far from the viewport fold back to gaps under a bytes budget (the events' JSON size as the estimate the page
already keeps for its perf rows). Never folded: the tail run, the run holding the viewport, and its nearest
neighbours on each side. `foldCandidates` orders the rest by distance from the viewport and folds until under budget;
a folded run's span becomes a gap sized by the measured average, so the scrollbar does not jump. The budget is a
fraction of the DEVICE's memory (`navigator.deviceMemory`, in gigabytes, where the browser exposes it; else a stated
fallback), never a small literal, under the same "one shared pool" rule the kernel's caches follow; the budget in
force and the bytes resident ride the chat's diagnostic rows (the perf minute row), so a report can read them.

### Diagnostics

- The landing row (`locateDiag`) gains `dist` and `settled` (part A) and keeps trail, anchor, time, kind, keep.
- The T366 `windowask` row becomes `regionask` with the span asked, the reason (landing, gap-scroll, fold-refill) and
  whether a notice is showing; same per-minute budget.
- New `regionfold` rows (span, bytes freed, distance from the viewport), under the same budget, so a report of a
  scrollbar jump can be read against folds.
- Retired: nothing else; `scrollwrite` rows keep their writer names and gain `land-settle` as a writer.

### Tests

Served labs (hermetic kernel, synthetic 320-turn transcript, the T366 lab's boot; browser suites one at a time under
capped): `test_landing_settles_browser.py` (part A, above; stage 1); `test_landing_notice_browser.py`: one notice, its
sentence with and without a time, the jump toward the gap before the reply, the snap on arrival, cancel keeps the
view and still inserts the run, no strip anywhere, the pill not shown for a landing; `test_history_regions_browser.py`:
the tail keeps updating (a `chatTail` frame appends) while a history run is resident above a gap and the reader's
viewport in that run does not move; scrolling into a gap asks for exactly its nearest page once (the socket hook
counts `loadTurns` frames) and the view holds through the fill (a distance pin over the fill, 0 px within one row);
the head reached folds the top gap away; `test_history_regions_fold_browser.py` (stage 3): a small budget folds the far
run back to a gap and the scrollbar's total does not jump. Node: `chat-regions.test.ts` (every rule above, executed),
`landing-settle.test.ts`, the render.ts wiring pins (the observer over gaps, the notice's element and its anchor, the
retired strip and its CSS gone, the DISTANCE pins for the snap). Kernel: `tests/test_chat_window_spans.py` over a
synthetic parse (the span on `loadAround` and `loadOlder`, `loadTurns` page alignment, the tail-only base), and the
retirements in `test_chat_split*`/the window tests re-pointed. Python tests that pin render.ts lines are re-run in
full (the 31-file set).

### Staging

- **Stage 1 (a fix PR, first):** part A. The settle rule and the measured row, the time carried through the
  adoption, the walk-forward waiting for the landing; the red-first lab. The window protocol and the strip stay. This
  removes the double click on its own and gives every later stage the instrument (`dist`, `settled`).
- **Stage 2 (a feature PR):** regions and the notice. `chat-regions.ts`, gaps in the DOM, the tail always resident,
  the kernel's tail-only base and spans, the one notice with cancel, the strip and Return-to-live and the walk
  retired, the pill retired for landings. The largest step; the labs above are its gate.
- **Stage 3 (a fix or feature PR):** the fold-back budget and the `regionfold` rows; gap prefetch tuning if the labs
  show a visible loading mark on a plain scroll.

Why not the whole thing at once: stage 1 is a user-visible bug with a small fix and its own lab; stage 2 changes the
wire and the kernel's per-client state and needs its own verification round; putting the bug fix behind it would
leave the double click on the user's screen for the whole design round.

### Answered by the user (2026-09-12 about 3:45 PM PT; the proposed defaults were put to them and stand as below)

1. The notice's words: "Going to the message from 7:41 AM, click to stay here" (the time in the user's clock, as the
   strip renders it today) / "Going to the earlier message, click to stay here". Yes.
2. Only the click on the notice cancels; a scroll during the wait does not. Yes.
3. The view moves before the reply: yes, straight to the position where the target will be, into empty space with the
   loading glyph; the fill then appears in place with the scroll position unchanged (the sharpened model, folded into
   the sections above).
4. The memory bound: the user defers to the performance thread; stage 3 asks it for the measured cost of a resident run
   and whether a bound is needed, and any cap is a fraction of memory, never a literal. A folded run's refill shows the
   loading glyph like any gap.
