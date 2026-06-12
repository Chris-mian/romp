# romp request registry — spec

The **intent layer**: every piece of fleet work traces to one of the user's **asks**
through a request DAG. Agents never see or mint request ids; the pipeline daemon
(`romp-summarize-backfill`) builds the graph from transcripts + postal messages.
Surfaces fold the files below at READ TIME (no compactor, no materialized view).
Co-designed by feed_design + haiku_summaries, 2026-06-09; design doc at
`~/GitRepos/dotfiles/romp-request-tree-design.md`.

## Files (`~/.local/state/romp/requests/`)

All append-only JSONL. **One writer per file** — that's the concurrency model.

**Session-id semantics:** every `sid` field below is the ANCHOR session id
(`@romp-session-id` — what postal stamps as from_id/to_id), NOT a transcript
fsid. Event-derived ids (`turn_id`, `reply_id`, ask id = `turn_id#i`) still
embed transcript fsids — that's provenance, unchanged. Forked transcripts
(/clear, resume, skills) get fresh fsids while the anchor persists, so keying
nodes + candidate sets by anchor means a reply in a fork still sees asks typed
pre-fork. Anchor sid is the canonical session key for the registry layer.

- `nodes.jsonl` — writer: the daemon.
  - `{kind:"ask", id:"<turn_eid>#<i>", sid, turn_id, t, text}` — one of the user's
    asks. The request-side summarizer splits a typed turn into 0..N asks
    (id = the turn's event id + `#index`; turn kept as provenance). Approvals of
    an agent proposal materialize asks from the proposal content.
  - `{kind:"internal", id:"<msg id>", from_sid, to_sid, t, text}` — an
    agent→agent handoff; the postal message IS the request (id = message id).
    Created by the message call (REQ=yes) in wave 1, idempotent on msg id
    (whichever side's pass runs first); a transiently failed call degrades one
    pass's candidate set, decision-logged (a deterministic fallback can be
    added later if the log shows it's needed).
  - `{kind:"parents", id:"<msg id>", parent_ids:[...], t}` — which request(s)
    the SENDER was serving when it delegated (a local match on the sender's
    stream). A separate record so edges can land after the node, no rewrites.
  - `{kind:"amend", id:"<ask id>", turn_id, t, text}` — a follow-up turn revised
    an existing ask. Read-time fold: latest text wins.
- `links.jsonl` — writer: the daemon.
  `{kind:"link", reply_id, request_ids:[...], relevance, sid, t}` — this reply
  (a `summaries/` deliverable) served those request(s). PLURAL: one deliverable
  can serve several. Links are **display evidence**, never state transitions.
  The link's `relevance` is AUTHORITATIVE for routing (column derivation) and
  may disagree with the reply's summary tag (e.g. a repair/reprocess judged the
  link DONE while the original tag was details) — readers must not require the
  two to mirror.
- `cleared.jsonl` — writer: the UI ONLY (feed panel + `romp -f`).
  `{id, t}` — the user cleared this ask. The one human-asserted fact in the system.
  Binary; no done/abandoned distinction.
- `decision-log.jsonl` — writer: the daemon.
  `{reply_id|msg_id, sid, t, candidates:[{id,text}], chosen:[...], raw}` — every
  link + PARENTS match WITH its candidate set (the measurement loop; the user's
  corrections become labels; decides fused-vs-split later). Rotate at 2 MB.
  Also logs the capture calls' NEGATIVE decisions (REQ=no on a message;
  zero-asks on a typed turn), so silent drops are visible, not absence-only.
- `../decision-brief/<reply_id>.json` — writer: the daemon (sibling dir of
  feed-detail). Prewarmed when a link gets relevance=DECISION:
  `{context, question, options|null, sid, t}` — context summarizes the upstream
  chain (parents-walk to roots + delivered siblings), question is what the user
  must decide, options when the reply offers discrete choices. A present file
  always has non-empty context+question (generation withholds on model
  under-fire); 24h catch-up sweep each pass. Consumed by the feed panel's
  decision sub-card.
- `corrections.jsonl` — writer: ANY session relaying one of the user's explicit
  judgments (deliberate exception to single-writer; short atomic appends).
  `{t, by_sid, kind:"link"|"req"|"ask-split"|..., decision_ref, should_have,
  note}` — ground truth attached to the decision it corrects. Workflow: the user
  says "this is wrong / where's X?" in plain language to whatever session;
  that session traces the miss in the decision log and appends here. These
  rows are the few-shot + regression set for every capture/linker prompt
  change: replay logged decisions, check corrections now pass, ship.

Backup: no conf change needed — `romp-cache.conf` is exclude-based, so
`requests/` (decision log included) mirrors to Proton automatically.

## Semantics

- **Roots are asks, not turns.** One ask = one unit the user can clear (inbox-zero).
- **Resolution = Clear, the user-only.** The system NEVER decides an ask is
  complete. DONE links are evidence on the card ("2 done · 1 needs you").
- **Column = DAG path accounting** (the user's status model, 2026-06-09; refined to
  LEAF-PATH 2026-06-10; readers: feed panel + `romp-feed --asks`). Per node (ask
  or internal), status = the NEWEST link directly on it: DONE → closed;
  DECISION → open question UNLESS the user has typed a later turn in that session
  (his answer crosses it off and the node reverts to open/in-flight);
  DETAILS/none → open. An ask is judged by where its paths END: every LEAF
  closed → COMPLETED; any open question anywhere → NEEDS INPUT; else ASKS, with
  a **drop point** per OPEN LEAF naming the responsible session — internal node
  → its `to_sid`, root → the ask's own sid. Intermediate nodes whose newest
  direct row is a restatement or an answered question are TRANSPARENT (the work
  continued downstream) — a fully delegated ask completes even though nothing
  was ever filed directly on it (workers downstream of a handoff chain never
  have the root ask in their palette, by design). Surfaces render a ROLLED-UP
  per-node status (done when every path below ends done; questions bubble up),
  so a completed ask reads as a column of ✓. Every non-terminated path is
  attributable: some session owes the user either a completion or a question, at a
  known transcript position. Strictness is deliberate: one missed DONE on a
  LEAF visibly holds the ask open and points at the reply to correct
  (corrections loop), instead of being papered over by a later DONE elsewhere.
  the user's adjudications in `corrections.jsonl` (rows whose `should_have` names
  `request_ids` × `relevance`) merge as links at read time — the feed panel's
  per-node "mark done" writes one — so a fix both completes the card and trains
  the linker. Column moves are derived; Clear remains the only retirement.
- **Candidate sets** (per session): open = not-cleared asks ∪ ALL internal nodes
  addressed to the session. When the set exceeds the cap of 12, evict
  DONE-linked internal nodes first, then oldest. (No-DONE-link is an eviction
  TIEBREAKER, not a hard filter: multi-deliverable handoffs are the norm, and a
  hard filter would prune a handoff after its FIRST done reply, structurally
  missing every later deliverable on it.) Under-clearing pushes the oldest asks
  out of range — accepted: misattribution is ok, roots persist regardless; the
  decision log records the misses.
- **Misattribution is acceptable; losing a root is not.** Uncertain matches are
  best-guess or unlinked; unlinked internal work stays out of the user-level
  view. No orphan UI.
- **Read-time fold:** group records by id across nodes/amend/links/cleared,
  last-wins per kind. Root-walk: follow `parents` edges from a link's
  request_ids up to ask nodes (a deliverable can reach multiple roots).
- **Floor:** `REQUESTS_FLOOR` stamped at ship time; no backfill of older work.

## Model output formats (fused into existing summarizer calls — no new calls)

- 2026-06-11 additions: TAG gains `WAIT` (turn ended on purpose pending an
  EXTERNAL event — not the user; read side holds the card in WORKING, exempt
  from auto-filing and the settled ring, ⏳ chip). And the STRUCTURAL own-turn
  link: whatever the model's LINK says, the reply of a turn that minted ask X
  is attached to X deterministically (same-pass candidates guarantee) — a
  user-prompted reply can never float free of its own ask, which closes the
  standalone-card class for good. DONE still requires the model/corrections.
- Reply call: `TAG :: phrase :: LINK <#[,#]|none> :: DONE <#[,#]|none>` —
  numbers index the prompt's numbered candidate list; the daemon maps #→id at
  write time (no id hallucination). DONE marks which LINKed requests this reply
  COMPLETES (ask-relative, distinct from the reply's own tag): DONE is
  subset-guarded (DONE ∩ LINK), completed ids get link relevance=DONE, the
  rest keep the reply tag, the summary tag itself is untouched. Parsing strips
  the DONE tail first, then LINK, so a junk DONE payload degrades only the
  completion marker, never the link. Decision log carries `done` + `raw_done`
  per link decision (watch for completion inflation).
- Request call: `PHRASE :: <8-word phrase>` (byte-compatible with the existing
  `summaries/` request line) then a CLOSED classification (2026-06-11): either
  1..N of `ASK :: <text>` / `AMEND <#> :: <text>`, or exactly one explicit
  terminal line — `ANSWER :: <text>` (the turn only answers/decides for work
  already underway) or `ACK` (small talk / approves nothing). A bare PHRASE is
  a capture FAILURE, not a judgment: the daemon's deterministic backstop then
  auto-mints one ask from the phrase (also on an `ACK` whose turn contains a
  `?` or runs >30 words — real acks are short and ask nothing; explicit
  `ANSWER` is trusted). Every capture row in the decision log carries
  `verdict` (ask/answer/ack/null) + `backstop` (null when the verdict stood),
  so under-fire is measurable. Rationale: cost asymmetry — an over-minted ask
  costs one Clear; a silent drop breaks the registry's only hard guarantee.
  The prompt carries a <context> block (tail of the preceding assistant reply)
  so approvals can draw ask content from the proposal.
- Answer rows (2026-06-11): an anchored `ANSWER <number> :: <text>` writes
  `{kind:"answer", id:<ask id>, turn_id, t, text}` to nodes.jsonl — the user's
  reply to a pending question recorded as an explicit child event on the card,
  never inferred. Read side injects it as a link-equivalent: as the newest link
  it crosses the pending DECISION off and reads "in flight again"; it renders
  as a ↩ row in the card's history, and its turn_id joins the live turn to the
  card (blocked-fold + liveness claim). The old next-typed-turn inference
  survives ONLY as the fallback for unanchored answers.
- Message call: `phrase :: REQ <yes|no> :: PARENTS <#[,#]|none>` — REQ filters
  FYI/acks out of node creation; PARENTS candidates = the sender's open
  received-requests.

Processing is **two waves inside one backfill pass** over one events_for()
snapshot: wave 1 = ask extraction + message REQ/PARENTS + deterministic internal
nodes; wave 2 = reply linking with wave-1 output visible. Guarantees the linker
sees split asks even when ask and reply arrive in the same catch-up pass.

## Joins

`links.reply_id` == `summaries/<sid>.jsonl` reply id == romp-events event id ==
`feed-detail/<id>.json`. `nodes(kind:internal).id` == postal message id (joins to
`postal/` logs + timeline message connectors). Ask `turn_id` == the typed turn's
event id. Resolve anchor sids to names/dirs via `names/<sid>`. See `SEARCH.md`
for the wider cache.
