# UI parity checklist: porting the tuned UI onto the new model

Internal design doc. The existing `chat-view` webview UI was hand-tuned over a long
time; the rebuild ports it as the render layer onto the new Python kernel rather
than reinventing it. This is the curated port checklist AND the completeness
reference for "did the port lose any of the human's tuning?"

Each item is tagged against the NEW data model (`event-model.md`, `judge.md`,
`read-side.md`):

- **KEEP** — transfers as-is; reuse the existing render + CSS, only rewire transport
  (HTTP polling + new payloads, vs the old WS message types / vscode webview shims).
- **ADAPT** — the visual/interaction stays, but the data behind it changed (goal tree
  vs request-DAG, captions vs summaries, segments vs events, working/blocked/completed
  vs the old columns).
- **DROP** — wired to a concept we deleted; do not port.

Source render files to port from: `chat-view/src/webview/render.ts`,
`chat-view/src/webview/feed.ts`, `styles.css`, `feed.css`,
`obsidian/romp-timeline-view.js`, `chat-view/src/page-skeleton.ts`. Do NOT port
`chat-view/src/kernel/*` (the old reducers; superseded by the one Python view-builder).

## Chat pane

Mostly KEEP: chat renders the event tree, which is close to the old transcript.

**KEEP — tabs & frame:** per-session tabs; status chip colored by state
(working/awaiting/idle/closed); working yellow dot; awaiting dashed-red outline;
faded idle color + hover un-fade; selected-tab identity-color outline; tab-row wrap;
double-click tab → toggle ledger; right-click → rename; inline rename
(Enter/Esc/blur); close (×); drag-reorder with drop indicators; tab order synced
with the timeline; "+" session picker; ledger ▾/▸; keyboard nav (←/→ tabs, ↑/↓
rows/scroll).

**KEEP — transcript & rendering:** lazy per-session cached views; scroll position
preserved per tab; sticky-to-bottom with restore-if-scrolled-up; deep-link anchoring
(uuid exact + nearest-time fallback, kind-guarded) + anchor flash + landing
diagnostics/toast; user bubble (blue, right) vs injected note box (neutral, left);
images thumbnail+caption (click-open, ⧉ copy); path linkify; queued-message dashed
bubble + count; assistant ring dot + markdown; thinking condensed→expand; tool calls
✓/✗ disc + name + file/desc; tool IO fold (ACK_TOOLS suppress on success, errors
shown); Edit/MultiEdit diff folds; Read/Bash/Grep output line-counts + fold;
subagent Task fold + report sub-transcript.

**KEEP — rail:** vertical conversation rail in identity color; time markers (HH:MM,
date on day change, spacing pass); worked-duration footer; rail dots (blue ✓ user,
ring assistant, green/red tool); rail-dot hover (120ms) → light timeline + outline
feed; rail-dot click → open feed card; hover-whole-turn → light timeline; white-ring
from feed-card hover.

**KEEP — live picker / footer / overlays:** AskUserQuestion picker
(single/multi/free-text, ↑/↓ nav, TUI preview box, "(new!)", sending opacity); status
line (work timer, model/effort dropdowns with pending cue, context % battery,
compact cue); working chip pulsing; composer auto-grow; Ctrl+C interrupt flash;
placeholder; attach 📎 + drop outline; session picker (search, running list,
open-all, new-session); opening modal; confirm dialog; selection context menu
(Reply/Copy); markdown + syntax highlight; image paste; scrollbar styling; draft
autosave per session; settings panel; file links.

**ADAPT — the ledger becomes the TOC.** Old ledger = digest summary line + flat
timestamped bullets. New = the **archiver headline** + the **turn captions** as
top-level lines, with a multi-segment turn's **segment captions** nested beneath,
each click-to-jump. Keep the box, the collapse, the recency tint, the hover→timeline
+ click→jump; change the contents from digest-bullets to the caption hierarchy.

**ADAPT — postal messages, compaction, agent to-do:** KEEP the postal card (peer
mail, ✓ delivered / ⏸ parked badge, clickable sender/recipient chips, working dot),
now sourced from the event model's `author:{peer}` atoms + the message log; KEEP the
"✦ Compacted" marker and compact-mode folding (compaction is an atom now); KEEP the
Claude Code Task to-do checklist (judge.md keeps it as a derived chat view).

**ADAPT — status chip states:** map to the collapsed liveness — working / blocked /
idle / closed (blocked = the hard live-prompt floor or the planner's soft block).

**DROP:** nothing major in chat.

## Feed pane

The most ADAPT/DROP, because the feed's data model changed most.

**KEEP — layout & card mechanics:** three-column responsive layout (stacks when
narrow) with header chip + count; infinite scroll; per-card recency tint; inbox-zero
logo; day separators; card hover overlay + lift; card click → modal; double-click →
pin; pinned faint ring; focused/hovered bright ring + timeline highlight; dismiss
(×) clears; session name click → open tab; working dot before an active session; age
recency hue; full-screen tree modal (⛶) for deep trees; two-view toggle
(inbox vs stream); reopened badge.

**KEEP — cross-pane:** hover a card → white-ring the timeline atoms for that work;
hover → outline sibling cards; modal row click → jump timeline + open chat.

**ADAPT — columns:** old NEEDS-INPUT / ASKS / COMPLETED → new **BLOCKED / WORKING /
COMPLETED** (the collapsed liveness). Keep the 3-column visual; change the bucket
semantics to read the goal's published status.

**ADAPT — card body = the goal tree.** Old ask card showed the request-DAG; new shows
the **goal tree** (goal → sub-goals → sibling step checklist). The tree render
(indentation, ▶/▼ toggles, clickable nodes, working dot, jump-to-turn) transfers;
the status marks map to **completed / blocked / open** (was ● done / ? question / ○
open). Once flattened (per the planner tuning) the trees are shallow checklists.

**ADAPT — modal = the goal trail.** Old modal listed linked-work rows / DAG; new
shows the goal's **trail** (its filed segments, each a caption + jump). Keep the modal
shell, clear button, follow-up composer; change rows from link-relevance to caption
trail.

**ADAPT — stream view:** old "deliverables stream" of relevance-tagged replies → new
**caption stream** (newest-first, recency-faded). Card = caption + session + time +
expand/dismiss. No relevance chip (see DROP).

**ADAPT — blocked card:** amber, top-pinned, click → open the session, no Clear
button. Keep, now driven by the new `blocked` status (hard floor or planner soft).

**ADAPT — origin filter:** the old "INTERNAL" (user- vs agent-prompted) toggle maps
to `trigger.author` (human/sdk/peer); keep it as an author filter if wanted.

**DROP — deleted concepts (do not port):**
- Relevance chips + relevance filter badges (DONE/DECISION/ACTION/DETAILS) — the TAG
  enum is gone.
- Liveness-anomaly rings (green settled-in-asks / dashed stalled / gold
  active-in-completed) — the four-way verdict collapsed; columns now reflect status
  directly, no mismatch to encode.
- Missed-handoff ⚠ badge + its explanation modal — the auditor/suspect machinery is
  gone.
- Exception report (evidence + category + free-text) in the modal — the corrections
  tier is gone.
- Status-tally badges (✓ done / ? question / · update evidence counts) — tied to the
  old link-relevance model; the tree shows status directly.
- In-feed decision sub-cards with inline answer buttons — answering happens in the
  session (the chat live picker); the feed shows `blocked` and links to the session.
  (Revisit if we want inline answering back.)
- External-wait ⏳ chip — the WAIT tag folded into `working` (non-user waits aren't
  surfaced for now; open question if we re-add).

## Timeline pane

Mostly KEEP — it already renders lanes / bars / states / connectors, which map onto
the new model.

**KEEP — frame & controls:** SVG lanes per session; left-justified names + color
chip; time axis with auto-stepped ticks; pan slider (window width + position); wheel
zoom; lock-to-now toggle; restart-kernel button; settings gear; Claude usage bars
(5h + weekly); snap-to-open-work; tooltips (cursor-following, viewport-clamped);
coloring/fading + hover un-fade.

**KEEP — lanes & atoms:** lane label + state badge (WORKING/READY/BLOCKED/IDLE/CLOSED);
lane click → open chat; lane hover tint; lane drag-reorder synced with tabs; work
bars with hover-grow + tooltip + click-to-open; prompt dots; green/red tool discs;
awaiting candy-cane stripe; compacting cross-hatch; pending-message connector
(animated dashed → solid on delivery) + hover + pending-count badge; model/effort
dropdowns on lane.

**ADAPT — bars are segments.** The work bar's grain is now the **segment** `[t,end]`
(event-model), read straight from the parser, not from `romp-events --emit` (deleted).

**ADAPT — idle gaps are event-based.** The "collapse idle gaps" toggle now keys on
the event model's **idle atoms** (real idle transitions from `states/`), not a 20-min
silence threshold. Same control, event-based mechanism.

**ADAPT — stripes & connectors sources:** awaiting/compacting stripes from `states/`
(compaction is also an atom); message connectors from the courier records / message
log (arrive with the courier increment).

**ADAPT — overlays:** feed-focus yellow outline + DAG-journey white-ring map onto the
**goal tree** instead of the old DAG.

**DROP:** nothing major; any auditor/suspect overlay if present.

## Global / frame / keyboard

**KEEP:** fixed 2px window frame; flex layout (tab bar / ledger / content / live-ask
/ footer); content overflow rules; sticky ledger header + footer; session color
propagation (rail accent, tab outline, chips); keyboard map (tab nav, window arrows,
picker nav, composer ⏎/⇧⏎, Ctrl+C interrupt, Esc closes overlays); deep-link landing
diagnostics + flash.

**ADAPT — theming:** the old UI used VS Code theme vars (`--vscode-*`). In the browser
there are none, so the kernel-served UI needs a self-contained theme (the dark
fallback is the base). The VS Code extension keeps the `--vscode-*` path at switchover.

**ADAPT — deep-links & host bridge:** in the browser, navigation is in-app over the
kernel (HTTP), not the `vscode://` protocol; the `acquireVsCodeApi()` shim already
abstracts host vs browser. Keep in-app jump; the `vscode://` variant is
extension-only and reconnects at switchover.
