# romp Request-Tree / Intent Layer — design + build plan

> **Note to self:** You are the `feed_design` romp session (formerly `update_feed`).
> You own the **feed** surface. This doc is the source of truth for the intent-layer
> work. Design finalized with the user 2026-06-09 after a full audit pass; build is GO.
> **Updated 2026-06-10** (§7): the system is live and in daily use; the day's
> corrections-driven evolution — leaf-path accounting, the teaching loop,
> AWAITING, follow-ups, per-request phrases, the link-landing rebuild — is
> §7. Where a 06-09 section below was SUPERSEDED, an inline note says so.

---

## 0. TL;DR — what to build

Add an **intent layer** on top of the existing romp summarization pipeline: every
piece of work traces to one of the user's **asks** via a **request DAG**. A weak model
only does **local** matches; parent edges recorded at handoffs make tracing back to
the user ask a read-time walk. The **feed** then shows only **the user's asks**
(persistent until he clears them), nesting all agent-internal work underneath.
Resolution is a single binary flag: **Clear**, done only by the user (inbox-zero).

---

## 1. Orientation — the romp system as it exists today

the user runs ~10–28 **romp sessions** (Claude Code agents in tmux) that coordinate
via a postal service. Everything is **file-based** under `~/.local/state/romp/`.

**The pipeline (how a turn becomes data):**
1. **`romp-events`** (`~/GitRepos/dotfiles/scripts/romp-events`) — deterministic,
   no-LLM parser of Claude Code transcripts into events. Runs **on demand**
   (`--emit`), disk-cached by (mtime,size). NOT a resident daemon. Assigns the
   **stable id** `<sid>:<turnStartEpoch>:<sha1(text)[:8]>` via `_eid()`.
   ⚠️ Its event set is **unstable**: it infers turn boundaries and *folds/absorbs*
   them as more transcript arrives, so events shift. **Summaries are the stable
   spine; romp-events is not.** Anchor deliverable-views on summaries.
2. **`romp-summarize-backfill`** — the always-on daemon (kqueue-driven). Imports
   `events_for` from romp-events. Per reply, ONE model call → `TAG :: phrase`
   (DONE/DECISION/DETAILS + ≤8-word phrase). Sole writer of `summaries/<sid>.jsonl`.
   `_is_real_ask()` gates request-side summaries: ONLY typed/queued user prompts
   get a `kind:"request"` line; postal banners / drains / task-notifications do not.
3. **`romp-feed-detail`** — per DONE/DECISION only (cost gate), a JLD-method
   paragraph → `feed-detail/<id>.json` (`{id,t,paragraph,next_steps?,relevance}`).
4. **`romp-digest`** — rolling per-session rollup → `digest/<sid>.json`
   (`{summary,bullets:[{text,t}]}`).
   The per-session **Stop hook** (`dotfiles/claude/hooks/romp-summarize.sh`) only
   sets a live tmux var + pings the daemon; it does NOT write history.

**State dir layout** (`~/.local/state/romp/`): `summaries/` `digest/` `feed-detail/`
`names/` (`name<TAB>dir<TAB>bg<TAB>fg`) `events-cache/` `states/` (liveness)
`postal/`+`mail/` (inter-agent messages) `timeline/` `SEARCH.md` (search guide).

**Surfaces (read-only views):**
- **Feed** (MINE) — VS Code `romp-chat-view` extension, the "romp feed" panel
  (`dotfiles/romp-chat-view/src/webview/feed.ts`+`feed.css`, host in
  `src/extension.ts`). Also terminal `romp -f` (`scripts/romp-feed`).
- **Ledger** (vs_chat) — per-session digest box in the chat panel (`render.ts` +
  `styles.css`). Also terminal `romp -l` (`scripts/romp-ledger`).
- **Timeline** (db_timeline) — vault-code plugin (Obsidian + VS Code
  `vscode-trackchanges`); reads romp-events + postal messages.
- **Pipeline status** (MINE) — `romp -p` (`scripts/romp-pipeline`): per-turn DAG
  status (summarized? detailed? timing). Drives off **summaries** (ground truth),
  overlays romp-events for timing + the pending front.
- **Dashboard** `romp -d`. **Retired:** `romp -g` browser timeline (unwired).

**Ownership / coordination:**
- haiku_summaries = PIPELINE (romp-events, backfill/classifier, romp-feed-detail,
  romp-digest, the cost gate). The most important collaborator for this work.
- vs_chat = LEDGER + chat-view + `render.ts`/`styles.css` + picker.
- db_timeline = TIMELINE + the romp-events data model + message connectors.
- router = dispatcher.
- **Install protocol for romp-chat-view:** single shared working tree, single
  shared `romp-chat-view.vsix`. `install.sh` bumps version + builds + installs.
  **Wait-for-ack RETIRED (the user, 2026-06-09, via vs_chat):** installs are
  "always clear" — just bump+build+install when ready; concurrent installs are
  safe (disjoint files: me = feed.ts/feed.css + extension.ts feed block;
  vs_chat = render.ts/styles.css + ledger/tab code; last writer rebuilds the
  shared dist from current source). Currently at **v0.4.76+**.
  My terminal scripts (romp-feed/pipeline) need NO install — just edit + run.

**Stable id is the spine:** feed `itemId` == romp-events `e.id` == `feed-detail`
filename == the join key everywhere. Everything keys off `<sid>:<ts>:<hash>`,
never the mutable display name (rename-safe).

**Cost model:** the whole pipeline runs on the user's Claude **subscription**, not
per-token API. "Cheaper" = less rate-limit burn, NOT dollars. Direct-API would ADD
cost. Keep this in mind for any optimization.

---

## 2. Key decisions/learnings (pre-audit session)

- **Relevance taxonomy is right as 3 buckets** (decision-maker's view): DONE
  (finished, optional look), DECISION ("ball's in your court" — needs the user,
  incl. blocked/broke), DETAILS (routine, the default-when-unsure). Distribution
  ~**75% DETAILS / ~13% DONE / ~13% DECISION**. NO sub-types; if DECISION ever
  splits, the axis is **urgency**, not type. Untagged is transitional.
  **SUPERSEDED 2026-06-10 (the user's ruling, §7.3):** the taxonomy grew TWO tags —
  **ACTION** (the user must DO something outside chat: reload, install, approve;
  typing does NOT cross it off, only his explicit "did it") and **IDEA**
  (suggestion he may react to; his next typed turn crosses it off). Precedence
  DECISION > ACTION > IDEA > DONE > DETAILS. The split axis turned out to be
  *what crosses it off*, not urgency.
- **Feed = curated actionable inbox** (not complete log). The pipeline (cost gate,
  DETAILS-no-paragraph) was *built for* this framing; it reinforces it.
- **DETAILS get no paragraph** — permanent cost gate. Expand on DETAILS/untagged
  shows the one-liner, never spawns generation.
- **romp-events instability** = inferred-and-revised turn boundaries (folding).
  Real fix someday: capture turn-end authoritatively at write-time (Stop hook).
  For now: anchor on summaries.
- **Storage:** knowledge backup is LIVE. `~/.config/git-mirror-backup/projects.d/romp-cache.conf`
  mirrors the knowledge subset (summaries/digest/feed-detail/names) of
  `~/.local/state/romp` → Proton bare repo every 15 min (mirror at
  `~/.git-mirror-backup/romp-cache`). Live data was NOT moved. `SEARCH.md`
  documents the layout. **Add `requests/` to the backed-up set when it exists.**
- **Transcripts** (`~/.claude/projects/`) = 789 MB / 7,969 files, no retention —
  they accumulate forever. OPEN: retention policy someday.

**Current feed state (v0.4.76):** rounded recency-tinted cards (hawaii colormap,
`romp_colormap.py`, alpha 0.22), TITLE on top → name + relevance chip → Expand
(Ask/Response) → right rail time + Dismiss; relevance filter badges (DONE #54B204 /
DECISION #1EA1EB / DETAILS dim); dismiss persisted in globalState;
FEED_FLOOR=1780964820; whole-card click → `timeline-focus.json` for the timeline
to pan/pulse. Dead session = faded name.

---

## 3. THE DESIGN (audited + finalized with the user, 2026-06-09)

### The problem
The feed floods the user with **agent-internal** work he never asked for and can't
remember, and there is no durable record of what he HAS asked for. What taxes his
memory: he can't remember what he has abandoned vs what's still live. He wants
**inbox-zero at the top level**.

### Roots are ASKS, not turns
- The unit of the system is an **ask**: one item the user can look at during
  inbox-zero and clear as a whole. The capture model (request-side summarizer)
  emits **0..N asks per user turn** (turn id kept as provenance; ask id =
  turn id + index). A turn with three requests becomes three roots.
- **Follow-ups amend, not spawn:** "actually make it blue" → local match against
  the user's open (= uncleared) asks in that session → amends the existing root.
- **Approvals are asks:** vague ask → agent proposes X/Y/Z → "okay great" →
  the capture model reads the approval in conversation context and materializes
  the approved items as asks, content drawn from the proposal. Origin = user,
  because the defining act is the user's sign-off.

### The DAG (not a strict tree)
- **Internal request** nodes are created when an agent hands work to another
  agent. The handoff postal message IS the internal request: its id = the message
  id (system-assigned; **agents never see or mint ids**). Its **`parent_ids[]`**
  (PLURAL — one handoff can serve several asks; one deliverable can resolve
  several) = the request(s) the sender was working on, decided by a **local
  match in the sender's scope**.
- **Attribution decomposes:** the weak model only ever answers a small
  multiple-choice question ("which of THIS agent's received requests does this
  serve?"); the recorded parent edges make tracing to the root ask(s) a
  **read-time walk**. Hard global attribution = local match × recorded edges.
- **No orphan UI.** When a match is uncertain, best-guess or leave unlinked —
  unlinked internal work simply stays hidden from the user-level feed. the user
  does not want to manage misattribution internals. The **safety net is root
  persistence**: the ask never disappears, so if it lingers he can tell an agent
  "go figure out what happened with this" and it searches the knowledge cache.
- Misattribution is acceptable; **losing a root is not.**

### Lifecycle: Clear is the only resolution
- **One binary flag, the user-only: cleared.** No done/abandoned distinction, no
  auto-resolve, no confidence threshold, no staleness machinery. The system
  NEVER decides a request is complete.
- Linker DONE/DECISION links are **evidence displayed on the card** ("2 done ·
  1 needs you"), not state transitions.
- Default to **too much for the user to clear**; tighten/automate later if needed.
- Stored human fact: `cleared_t`. Everything else (status display, owners,
  tallies) is **derived at read time** — pure file reads/joins, zero LLM calls.
- **REFINED 2026-06-10 (§7.2):** Clear remains the only *retirement*, but the user
  gained a second human-asserted fact: **corrections** (mark done / "did it" /
  "didn't need me"). A correction completes the card at read time AND is the
  linker's training label — Clear teaches nothing, mark-done teaches. Risk
  posture made explicit: **false-completed is SAFE** (the user verifies everything
  in COMPLETED before clearing); the only fatal error is LOSING an ask.

### The linker = the summarizer, extended (fused)
- Extend the existing per-reply summarizer call (romp-summarize-backfill) to also
  emit the **local** request link: given the agent's open received-requests
  (small candidate set), "which does this serve — or none?" Constrained
  multiple-choice, same call, no extra rate-limit burn.
- **Split to a stronger model ONLY if measured unreliable** — which requires the
  measurement log (below) from day one.

### Ordering (analyzed — the race dissolves)
- A postal message to agent B is delivered **into B's transcript** before the
  reply that answers it. So **candidate extraction and linking MUST run in the
  same per-session transcript pass** (haiku's daemon, single writer). That's the
  one hard requirement; given it, candidates always exist before the linker
  needs them.
- **Parent edges may land late, harmlessly:** edges are computed on the sender's
  stream; nodes are created idempotently keyed on the message id by whichever
  side processes first; the root-walk happens at read time. A late edge just
  means work attaches to its root a moment later — invisible, since the feed
  shows only the user's roots (captured from his own turns, racing nothing).
- No retro-reconcile machinery needed.

### Measurement log (day one)
- Log every link decision WITH its candidate set (a few ids + 8-word phrases ≈
  hundreds of bytes; ~30–50 KB/day; cap/rotate). the user's re-filings/corrections
  become labeled data. This is what makes "fused vs split" decidable later.

### v0 (ships FIRST, before the registry): origin filter
- Tag each feed item `origin: user | agent` and default-filter the feed to
  user-origin. No registry, no linker — immediate relief from the flood +
  validates the "user-level only" hypothesis cheaply.
- **Detection (verified in code):** `_is_real_ask()` already gates request-side
  summaries — only typed/queued prompts get a `kind:"request"` line in
  `summaries/<sid>.jsonl`; postal banners/drains/task-notifications don't. So:
  reply id has a same-id request line → **user**; none → **agent**. The sign-off
  case is free (the user's "okay great" is a typed prompt → request line → user).
- Known edge: an absorbed turn mixing the user's typed text WITH a mail banner is
  classified banner (no request line) → agent-origin. Rare; acceptable for v0.

### Registry (the new store)
- `~/.local/state/romp/requests/` — **single writer = the pipeline daemon**
  (haiku's; same pattern as `summaries/`). Schema (to finalize with
  haiku_summaries):
  - ask node: `{id, kind:"ask", sid, turn_id, t, text, cleared_t?}`
  - internal node: `{id(=msg id), kind:"internal", from_sid, to_sid, t, text,
    parent_ids[]}`
  - link record (from the linker): `{reply_id, request_id, relevance, t}`
  - decision-log line: `{reply_id, candidates[], chosen, t}`
- A `REQUESTS.md` spec next to `SEARCH.md` (three sessions consume this schema)
  — THE authoritative schema; this section is the design sketch it grew from.
- **Floor at ship time** (FEED_FLOOR pattern) — no backfill of pre-registry work.
- Backup: no conf change needed — romp-cache.conf is exclude-based, so
  `requests/` mirrors to Proton automatically (decision log included).
- All registry `sid` fields are ANCHOR session ids (@romp-session-id, what
  postal stamps), not transcript fsids; event-derived ids keep fsids as
  provenance. Anchor = the registry's canonical session key (fork-safe).

### Feed rework (MINE, downstream of registry)
- Default view = **the user's asks only**, persistent cards: ask text + owner(s) +
  derived tally ("2 done · 1 needs you"), staying until **Cleared**.
- Clear state lives in the state dir (NOT extension globalState) so `romp -f`
  and the panel agree. Per-card Dismiss becomes Clear.
- Internal sub-tree is drillable (expand), not in your face.

### Tree view (later, likely db_timeline's surface)
- Visualize a request's subtree; "subgraph of all activity for request R" =
  filter events+messages by the subtree's ids (db_timeline confirmed feasible).

---

## 4. Build plan (in order)

0. **v0 origin filter** (MINE, no dependencies): same-id-request detection, tag
   feed items, default filter to user-origin. Terminal `romp -f` first (no
   install), then the panel via wait-for-ack install.
1. **Registry schema + `REQUESTS.md`** — co-design with haiku_summaries.
   Single-writer = their daemon.
2. **Capture**: user-turn → 0..N asks (split / amend / approval) — extends the
   request-side summarizer prompt (haiku's).
3. **Internal requests**: postal handoffs → nodes (id = message id), sender-side
   local match → `parent_ids[]`.
4. **Linker**: fused into the per-reply call, same-pass candidate extraction,
   decision log.
5. **Feed rework** (MINE): asks-only default, persistent cards, Clear,
   drillable internals. Install via wait-for-ack.
6. **Tree view** (db_timeline's, coordinate).

**Deferred:** prompt-quality pass (classify-once for TAG; action-framed DECISION
phrasing; classify completion against the open ask once requests exist);
transcript retention policy; storage single-copy option.

---

## 5. Resolved during audit (don't re-open)

- ~~Orphan UI / confidence surfacing~~ → no orphan UI; root persistence is the
  safety net; misattribution acceptable, lost roots not.
- ~~parent single vs multiple~~ → `parent_ids[]`, walk to roots plural.
- ~~Auto-resolve threshold / open-vs-resolved policy / staleness~~ → deleted;
  Clear (binary, the user-only) is the only resolution.
- ~~done vs abandoned~~ → NOT distinguished; just cleared.
- ~~Registry writer~~ → pipeline daemon (haiku's), single writer.
- ~~Linker fused vs split~~ → start fused; measurement log decides any split.
- ~~Backfill~~ → floor at ship time.

## 6. Current status / next moves

- [x] Design audited + finalized with the user (2026-06-09). GO to build.
- [x] haiku_summaries co-design DONE (same day): layout + fused formats agreed
      (numbered candidates, request_ids[] plural, parents/amend as separate
      records, cleared.jsonl UI-owned, REQ filter, two-wave passes, cap-12 with
      DONE-link as eviction tiebreaker, anchor-sid keying). They are BUILDING
      (registry plumbing → message-side → request-side → linker+log).
- [x] v0 origin filter: terminal `romp -f` SHIPPED (user-origin default, --all,
      hidden count in header). Data: 37% of all-time items are agent-origin;
      66–73% on busy fleet days.
- [x] v0 panel SHIPPED (v0.4.77): origin field + per-class cap in extension.ts;
      "internal" toggle chip (default-hidden) in feed.ts; feed.css. the user must
      reload the editor window to pick it up.
- [x] REQUESTS.md WRITTEN at ~/.local/state/romp/REQUESTS.md — the authoritative
      schema, incl. haiku's amendments (eviction tiebreaker, anchor-sid keying,
      no backup-conf change needed).
- [x] REGISTRY LIVE (haiku SHIPPED, 2026-06-09 15:25): requests/{nodes,links,
      decision-log}.jsonl, REQUESTS_FLOOR=1781036800, all three fused calls,
      two-wave pass, anchor-sid keying. cleared.jsonl is MINE to create on
      first Clear (they only read it). Transition note: typed turns between
      the floor and the daemon restart were request-summarized by old code →
      never grow ask nodes; registry effectively starts at restart time.
- [x] `romp -f --asks` dormant inbox built + fold logic verified on synthetic
      data (amend latest-wins, parents-walk rollup, clear drops). Lights up
      as real nodes accumulate.
- [x] Validated against first real data: internal node + correct link
      discrimination (one rejection, one DONE match) + first real ask rendered
      with attribution/tally in `romp -f --asks`.
- [x] PANEL ASKS VIEW + CLEAR SHIPPED (v0.4.81): header "asks N (· M need you)"
      toggle ↔ deliverables; ask cards = ask text + owner + done/needs-you tally
      chips + recency tint; expand = linked work (joined deliverable phrases);
      Clear appends requests/cleared.jsonl (UI is sole writer) and removes the
      card; whole-card click locates the TYPED TURN on the timeline (turn_id).
      Deliverables remain the default view — flip default to asks once the user's
      comfortable + splitting proves itself.
- [x] TESTS (the user: "more tests, always"): read-side suite at
      dotfiles/tests/test_romp_read_side.py (13 green — fold rules, origin
      detection, registry readers; each encodes a real 2026-06-09 failure).
      Pipeline-side suite dispatched to haiku (transcript fixtures, parser
      guards, registry semantics, anchor-sid); corrections.jsonl entries
      become permanent fixtures; selftest-before-daemon-restart discipline.
- [x] Model tier CONFIRMED (haiku): all three classification calls already on
      Sonnet 4.6 (one llm() chokepoint); nothing below tier. Pipeline-side
      suite SHIPPED same day: 45 tests green (transcript fixtures through the
      real extractor, junk-tail matrix, two-wave same-pass, fork→anchor);
      selftest-before-restart discipline adopted.
- [x] DAG PATH ACCOUNTING SHIPPED (2026-06-09 eve, the user's status model):
      column = per-node terminal accounting, NOT newest-link-anywhere. Node
      status = newest link on it (DONE closed; DECISION = open question unless
      the user typed later in that session — his answer CROSSES IT OFF; else
      open). All closed → completed; any open question → needs_input; else
      asks + DROP POINT per open leaf naming the responsible session.
      Implemented read-time in BOTH extension.ts computeAskItems (v0.4.95:
      column/openQuestions[]/openPaths[]/per-row status, answerQuestion
      handler → sendToSession) and romp-feed ask_items (✓/?/· marks, "waiting
      on NAME age"). Read-side suite now 18 green (answered-crossoff,
      all-paths-done, open-branch drop point, reopen-after-done,
      question-beats-done). REQUESTS.md semantics updated. Rejected
      alternative (the user): liveness join / stalled timers — an ask implies a
      working agent; broken invariants surface via drop points + corrections,
      not activity monitoring.
- [x] DECISION BRIEFS LIVE (haiku, same eve): decision-brief/<reply_id>.json
      {context, question, options|null} prewarmed on DECISION links + 24h
      catch-up; file-presence guarantees non-empty context+question; Sonnet.
- [x] vs_chat render track: colored linked-work rows (done/question/update),
      click row → timeline jump (absorbs their backlogged ask), decision
      sub-card (brief + answer box → answerQuestion), drop-point line on open
      cards. Payload shape + GO sent (v0.4.95 live, brief dir populated).
- [x] WATCH item RESOLVED (2026-06-10): asks held open by stale handoff nodes
      whose DONE went to the root — dissolved by leaf-path accounting (§7.1):
      an intermediate node is *transparent* when all paths below it end DONE,
      so the class disappeared structurally instead of via per-case training.
- [ ] LATER: flip panel default view to asks (the three-column board IS now
      the asks view — see §7.3); Clear from terminal `romp -f --asks`; tree
      view on the timeline (db_timeline).

---

## 7. 2026-06-10 — corrections-driven evolution (the system in daily use)

A full day of the user working his real inbox against the live system. Pattern of
the day: every misbehavior became (a) a correction row = training data, (b) a
fold/prompt fix with a regression fixture, or (c) a structural rule that
deleted the whole error class. Suites grew: read-side 18 → **34** green
(dotfiles/tests/test_romp_read_side.py + test_romp_idle_dots.py), pipeline-side
45 → **104** (llm_summaries). Panel at **v0.4.179**.

### 7.1 Leaf-path accounting (the user's status model, superseding 06-09 DAG rules)
An ask is judged by **where its paths END**, not by every node needing its own
DONE: leaves keep their own status; an intermediate node is **transparent**
when every path below it ends DONE (its restatement/answered question rolls
up); questions bubble from anywhere. Column fold: any open question →
AWAITING; rollup(root)=done → COMPLETED; else ASKS, with a **drop point** per
open LEAF (owner = the internal node's recipient). Delegated chains now
complete through restatements — the 06-09 WATCH class dissolved. Node marks
are the chat-timeline vocabulary: ● done (green) / ? question / ○ open;
"there's no such thing as a progress update that isn't a completed thing" —
every report row is a green ●. Tree renders with indentation only (no ASCII
tree syntax), children chronological (oldest at top at every level), modals
open one level deep, parent-line hover highlights the UNION of everything
underneath on the timeline.

### 7.2 The teaching loop (corrections as re-verdicts)
corrections.jsonl rows act as **links at read time** (newest-wins), so the user's
adjudication closes a node exactly like a real terminal reply — and the same
row is a labeled training example + permanent fixture. Affordances: **mark
done** (modal, on any open leaf), **"✓ Done — I did it"** (ACTION cards),
**"didn't need me"** (false-AWAITING). Display rule learned from a bug: a
correction re-verdicts an EXISTING report — it upgrades that row's status but
never duplicates the row, bumps its time, or claims the corrector's identity.
`--rejudge` (llm_summaries) re-runs verdicts over open leaves after prompt
changes and appends corrections — the user's workflow: **batch-click mark-done,
then have the prompts reworked**; that's as valuable as careful per-card
tracing. Write-side rules hardened the same day: a reply may only stamp DONE
on requests it *explicitly* finished (demotion guardrail); **never amend a
completed ask** (an amend on one converts to corrective re-title + palette
fix — the incident class the user predicted).

### 7.3 Board semantics: AWAITING, group cards, standalone cards
Columns renamed/colored to match the session-chip language: **ASKS / AWAITING
(#c0392b, awaiting-chip red) / COMPLETED (#2b7fb8, ready-chip blue)**.
AWAITING now catches everything that needs the user — questions (DECISION),
actions (ACTION: "reload VS Code"; survives typed turns, closed only by "did
it"), and suggestions (IDEA: crossed off by his next typed turn). One typed
prompt that mints several asks renders as **ONE group card** (title = the
turn's phrase) with a circle-line per member that checks off individually —
presentation only; each member keeps its own DAG/column/Clear. User-origin
unlinked DONE/DECISION turns render as **standalone cards** (DECISION crossed
off by a later typed turn in that session).

### 7.4 Follow-up mechanism (completed ≠ finished forever)
Completed cards carry a **Follow up** box: the text is delivered to the
session as a typed prompt prefixed `Follow-up on "<card title>": …`, recorded
in **followups.jsonl** (feed-UI-written, like cleared.jsonl), and the card
returns to ASKS — **same title** (the user: consistency; scope legitimately
grows). Deterministic reopen: the record alone holds the card in ASKS until
the bookkeeper mints the delivered turn as a **child of the root** (parents
edge; an ask with parents renders inside its root's card, never as its own) or
a newer verdict lands on the root — then ordinary leaf-path rollup owns it;
the child's DONE re-completes the card. A follow-up on a cleared card
resurrects it (a sent follow-up may never be invisible). Write side: a
follow-up turn is matched to its record (sid + closest-t ≤15min + text
sanity), never re-titles the root, AMEND-on-follow-up converts to a child ASK,
unknown root degrades to a plain root (never a dangling edge — lost ask is the
one fatal error). Verified working in the wild the same evening.

### 7.5 Per-request phrases (the cross-workstream leak)
One reply often discharges SEVERAL requests across unrelated workstreams
(peer messages land mid-turn), and its single whole-turn phrase used to bleed
into every card it was filed under. General fix, both sides: multi-request
LINK lines grow a `DID` tail → `did_by_request: {<rid>: "≤6-word scoped
phrase"}` per link row, scoped per relevance group; read side prefers the
scoped phrase, whole-turn phrase is the fallback (old rows render unchanged).
DID is the rightmost tail and strips FIRST (else its numbers would feed the
DONE parse and fabricate completions). Regression fixture: reply dde32f03 —
3 requests, 2 workstreams.

### 7.6 The link-landing chain (title clicks land on the user's prompts, always)
Rebuilt end-to-end after repeated wrong landings (thinking blocks, assistant
answers, "very recent" bottom-dumps). Producer side: per-event `uuid`
(boundary/prompt line; substitute = replyUuid, NEVER workUuid), `replyUuid`
(last assistant line with text), compaction stitch (`parentUuid ??
logicalParentUuid` in romp-events AND transcript.ts — pre-compaction history
stays on the active path). Carrier: `/open?…&anchor=<uuid>&anchorT=<epoch>&
anchorKind=user` — a fallback may degrade PRECISION, never KIND. Landing side
(the one place that can't be fooled): **KIND GUARD** — a prompt-intent anchor
resolving to a non-user turn is refused; the time fallback considers ONLY
user turns (no degrade-to-any); give-up = honest default scroll. Then the
structural cut (after the rewind-orphaned `"yes go ahead"` incident): title
clicks **no longer ride the event-pointer pipeline at all** — the feed locates
the chat first-party from the card's own (sid, mint-t) via `locateInChat`,
kind-restricted; exact in the normal case (data-t == mint t), nearest-prompt
in the degenerate one. **Landing diagnostics** (the user's ask): every deep-link
landing posts its resolution trail → `locate-diag.jsonl`, and degraded
landings show a toast ("landed nearby / showing latest (logged)") — a bad jump
announces itself instead of impersonating a good one.

### 7.7 Timeline interaction contract (the user's ruling)
Feed-card hover and single click → **paint only** (white DAG outline, no pan).
Double-click pin → `jump:true` in timeline-focus.json → timeline **pans only**
(no pulse, no chat-open). Title click → chat jump (first-party, §7.6) +
paint-only focus. Work-intent clicks (deliverable rows) unchanged: full
pan+pulse+open on db_timeline's side.

### 7.8 State doctor (stuck-working heal)
Claude fires NO hook on an Esc-interrupt, so a session interrupted in the
terminal stranded @claude-state=working — chip, timeline work-bar, and ghostty
🟡 dot all wrong (test_slector, 34 min). A stale `since` alone can't
distinguish interrupted from a long tool call (neither fires events); the
PANE disambiguates: "(esc to interrupt)" = genuinely busy; idle composer (❯) =
heal. The healer lives in **scripts/romp-idle-dots** (already the timer-side
watcher for the idle-dot fade — same missing-timer problem), sweeping every
60s: working/compacting + since stale >120s + readable idle-looking pane →
mirror the hook's Stop branch (state+since+emoji+states/<sid>.jsonl) so all
three surfaces recover in one write; anything ambiguous is left alone, and
`since` is re-read just before writing so a real hook event wins. Hook now
`--ensure`s the watcher on UserPromptSubmit too (a turn can only get stuck
after a prompt starts it). romp-chat-view's Ctrl+C path stays the instant
in-app reset; the watcher is the ≤3 min backstop for terminal interrupts.

### 7.9 Standing communication rules (the user, applies to everything above)
Executive altitude: surface decisions/blockers/milestones, suppress mechanics.
Self-contained replies rebuilt from zero context (he context-switches
constantly); no coined shorthand, no link/graph jargon ("filed under", not
"linked"). His name is not hard-coded in romp software ("the user" in
scripts/tests).
