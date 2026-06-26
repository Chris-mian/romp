# Event model: the bottom-layer schema

Internal design and schema doc, not user-facing (those live in `docs/`). This is
the pinned target for the rebuilt bottom layer of romp: how a session's
transcript becomes a structured, queryable model of turns and atoms. Built
during the bottom-up redesign, 2026-06-13.

The guiding principle: **the data model is the Claude streaming protocol, made
graph-aware.** An atom is a streaming message, a turn is the streaming protocol's
user-to-result cycle, and the on-disk transcript is just those messages plus the
graph metadata needed to reconstruct them after rewinds and resume-forks. One
model serves both substrates: on a stream you receive it, on a file you rebuild
it. We name fields after the streaming API wherever an equivalent exists, so a
future stream substrate is a near passthrough.

## Decisions log (what's settled)

- **ROMP UUID** is the stable session identity, assigned once at session birth,
  never changes across resume / clear / fork. Everything binds to it. It is the
  one durable id; per-fork transcript ids (`fsid`) are provenance only.
- **atom** = one transcript line = one streaming message. Its payload is a
  `content[]` array of blocks, so one atom can render as several chat rows.
- **turn** = a contiguous group of atoms, opened by a trigger and ended at the
  next turn boundary. A turn has no `kind`; its character is its trigger.
- **trigger** = the user atom that opened a turn, or null (autonomous /
  continuation). Its provenance is the atom's `author`, not a separate flavor.
- **`kind` lives on the atom**, and equals the streaming message `type`/`subtype`
  (`assistant`, `user`, `system:init`, `system:compact_boundary`, `result`),
  plus one synthetic kind, `idle`.
- **compaction is an atom** (`system:compact_boundary`), not a turn. It has no
  trigger and is a streaming message.
- **idle is an atom** (`idle`), not a turn. It has no trigger, is one contiguous
  span, and is synthesized on the file substrate from the state log.
- **"reduce" replaces "fold"** in all naming. The lineage fold becomes the
  **lineage reduce**.
- **Turn boundary = `end_turn` / `result`** (streaming parity). A turn opens at a
  user-prompt atom; mid-turn prompts (the old "absorbed") and decisions stay
  inside the turn. Whether to sub-segment there is a higher-layer choice.
- **Authorship is the one real addition over the stream.** A user atom carries an
  `author` (human / sdk / system / peer), because the stream cannot tell a peer
  romp message from a human prompt. The old typed/queued/absorbed/decision/postal
  flavor enum collapses: author + position (opener vs mid-turn) + content derive
  all of them.
- **Openers are `human`, `sdk`, and `peer`; `system` is not an opener.** `system`
  atoms are harness injections (e.g. `<task-notification>` when a background
  task/agent completes); they fold into the current work, never start a new ask.
- **Turn vs segment** are two groupings over the atoms, both derived. A *turn* is
  `end_turn`-bounded (the stream unit, what `num_turns` counts) and may contain
  several inputs. A *segment* runs from one input to the next (or to `end_turn`)
  and is what the timeline draws as a bar. The bottom layer stays unopinionated;
  consumers pick the grain.
- **Postal is detected by the existing `<!-- romp-msg-id: <id> -->` marker**, with
  the peer ROMP UUID filled by joining the id to `timeline/messages.jsonl`
  (`from_id` = sender anchor sid). Never the `"Stop hook feedback"` prefix (any
  blocking Stop hook produces it). No new marker, no romp-postal-service change.
- **The event layer is not opinionated** about which atom matters. No `workUuid`,
  no `replyUuid`. "Which line a click lands on" is a render-time function over a
  turn's atoms.
- **Clear drops pre-clear history.** Within a file the `parentUuid` graph encodes
  it for free: clear breaks the link, so the leaf-to-root walk stops there. (Resume
  KEEPING history across files is NOT free — resume forks don't link via
  `parentUuid` in practice; that's the deferred session→files concern below.)
- **Idle comes from the state log**, not a 15-minute silence heuristic. Period
  clipping keys on the real idle transition in `states/<sid>.jsonl`.
- **Delete the per-turn headless backend now.** Build nothing to replace it yet.
- **Deferred:** headless-with-terminal-parity is either the Agent SDK or a
  stream-json client; decision postponed. Also deferred: whether summaries operate
  at turn grain or segment grain (the timeline uses segments).

## Hierarchy

```
Session            ← keyed by ROMP UUID
└─ Turn            ← end_turn-bounded; the stream unit (num_turns); may hold many inputs
   └─ Atom         ← one message / one transcript line              (chat zoom)
      └─ ContentBlock   ← text | thinking | tool_use | tool_result  (one chat widget each)
```

One parse produces the whole tree. The chat reads it at the Atom/ContentBlock
level. No second parser.

**Turn vs segment.** A *turn* is `end_turn`-bounded: one continuous stretch where
the model held the floor. It is not "one ask", mid-turn injection (absorb) and
decisions add inputs without an intervening `end_turn`, so a turn may hold
several. A *segment* runs from one input to the next (or to `end_turn`) and is
what the timeline draws as a bar. Segments are a turn split at its input atoms, a
pure derivation, not stored. The old `romp-events` only ever produced segments
(its "events"); naming the coarser turn lets each consumer pick its grain.

## Schema

Pseudo-TypeScript. Field names mirror the streaming API / Agent SDK where an
equivalent exists; file-only fields are grouped and labeled.

```ts
// ── Session ───────────────────────────────────────────────
// Identity lives here and never changes across forks.
interface Session {
  rompUuid: string;         // THE stable identity key (binds summaries, DAG, everything)
  name: string;
  dir: string;
  color: string;
  leafFsid: string;         // newest transcript file; the walk's start pointer (updates on resume)
  turns: Turn[];            // ordered oldest → newest
}

// ── Turn ──────────────────────────────────────────────────
// No kind. A turn IS its trigger plus the atoms until the next turn boundary.
interface Turn {
  id: string;               // `${rompUuid}:${t}:${hash}` — anchor-keyed, fork-stable
  trigger: Trigger | null;  // the user atom that opened it, or null (autonomous / continuation)
  t: number;                // start (trigger.t, else first atom.t)
  end: number;              // last atom's end (or next turn's t)
  ended: boolean;           // STREAM: from `result` / stop_reason. FILE: inferred from stop_reason.
  atoms: Atom[];            // every atom in [t, nextTurn), in order: assistant, user,
                            //   system:compact_boundary, idle — all of it
}

// The trigger references the opening user-prompt atom. Its provenance is that
// atom's `author` (below); opener-vs-mid-turn is position, derived from turn
// structure, not stored; "decision" is read from the atom's content.
interface Trigger {
  uuid: string;             // the user-prompt atom that opened the turn
}                           // STREAM: a trigger is simply a user message

// ── Atom = one message (one transcript line) ──────────────
interface Atom {
  // Parity with the streaming API:
  type: "assistant" | "user" | "system" | "result" | "idle";   // "idle" is ours
  subtype?: "init" | "compact_boundary" | "status" | "task_notification"; // when type==="system"
  uuid: string;             // message id (same value in stream and transcript)
  session_id: string;       // = rompUuid
  message?: ApiMessage;     // assistant/user: the Anthropic message object (below)
  compact_metadata?: { trigger: "auto" | "manual"; pre_tokens: number }; // system:compact_boundary
  init?: { tools: string[]; model: string; cwd: string; permission_mode: string }; // system:init
  result?: {                // type==="result"
    subtype: "success" | "error_during_execution" | "error_max_turns" | string;
    num_turns: number; stop_reason: string | null;
    usage: Usage; total_cost_usd: number; duration_ms: number; is_error: boolean;
  };

  // Synthetic atom (FILE substrate; no stream equivalent):
  end?: number;             // type==="idle": the contiguous idle span is [t, end]

  // FILE-only provenance (the graph the stream doesn't carry):
  t: number;                // timestamp (transcript has it; on a stream you stamp on arrival)
  fsid?: string;            // which transcript file this line physically lives in (click-to-open)
  parentUuid?: string;      // graph link (parentUuid ?? logicalParentUuid)
  promptSource?: "typed" | "queued" | "sdk" | "system";  // raw signal; ABSENT on
                                        //   hook-injected (postal) and tool_result lines

  // THE one genuine addition over the stream: who authored a user atom. Derived —
  // promptSource typed/queued→human, sdk→sdk, system→system; the romp-postal-service
  // marker→peer. A tool_result-only user atom has no author (it's harness output).
  author?: "human" | "sdk" | "system" | { peer: string /* peer rompUuid */ };
}

// ── ApiMessage / ContentBlock — verbatim Anthropic shapes ─
interface ApiMessage {
  role: "assistant" | "user";
  content: ContentBlock[];
  model?: string;
  usage?: Usage;
  stop_reason?: "end_turn" | "tool_use" | "stop_sequence" | "max_tokens" | null;
}
type ContentBlock =
  | { type: "text"; text: string }
  | { type: "thinking"; thinking: string; signature?: string }
  | { type: "tool_use"; id: string; name: string; input: unknown }
  | { type: "tool_result"; tool_use_id: string; content: unknown; is_error?: boolean };

interface Usage { input_tokens: number; output_tokens: number }
```

### One atom, many blocks

A single transcript line is one message whose `content` is a list of blocks. An
assistant atom routinely carries a `thinking` block, a `text` block, and a
`tool_use` block at once, and the chat renders one widget per block, so the atom
paints as several rows. A tool call spans two atoms: the `assistant` atom with
the `tool_use` block, then the next `user` atom with the matching `tool_result`
block. This is exactly the Messages API shape.

## Turn boundaries and the absorb/queue mechanism

The objective turn boundary is `end_turn` / `result`. Understanding why requires
knowing that a Claude Code turn is a loop of streaming requests, not one call.

A turn runs as: the model emits text and a `tool_use` and stops with
`stop_reason: "tool_use"`; the client runs the tool and sends a follow-up
request carrying the `tool_result`; the model continues; repeat until
`stop_reason: "end_turn"`. So a turn with N tool calls is N+1 streaming requests,
and the model generates only in bursts, one request per cycle, with gaps between
while the client runs tools and composes the next request.

Those gaps are the only injection points. When the user types mid-turn, the
client holds the text and, at the next request boundary, either:

- splices it into the next request alongside the tool_results, so the model
  continues in the same turn. This is **absorb** (transcript `queue-operation`
  `remove`).
- sends it as a fresh top-level request because the turn already hit `end_turn`.
  This is **queue / new turn** (transcript `queue-operation` `dequeue`, then a
  normal `promptSource: "queued"` user line).

The Messages API has no queue. It is stateless and sees only a `messages` array.
Absorb versus queue is entirely the client's choice of where the user text lands
in that array and when the request is sent. In the streaming output the
distinction is pure position: a `user` message before the turn's `result` was
absorbed, one after it opened a new turn. The transcript's `queue-operation`
records are the client's bookkeeping of the same fact, a file-side artifact, not
API truth.

Consequences for the model:

- **A user-prompt atom (any author) or a postal message** arriving after
  `end_turn` opens a turn.
- **A user-prompt atom or a decision** arriving mid-turn (before `end_turn`) is an
  atom inside the current turn, not an opener.
- A higher layer may sub-segment a turn at a mid-turn prompt or a decision for
  summary or timeline granularity. The bottom layer does not; it records the atom
  (with its `author`) so the choice stays available above.

## Authorship, position, and what we add over the stream

The guiding rule is to mirror the stream and add only what it genuinely lacks.
The old five-flavor enum (typed/queued/absorbed/decision/drain) sorts into three
buckets, and only the third is real new information:

- **Position labels (typed, queued, absorbed) add nothing.** They only describe
  where a user message sits relative to `end_turn`: idle-opener, busy-opener,
  mid-turn. The stream already encodes that as position. typed-vs-queued (idle vs
  busy when typed) is the lowest-value distinction of all; nothing branches on it.
  Derive position; do not store these.
- **decision is a content tag, not a kind.** It is "a `tool_result` whose
  `tool_use` was `AskUserQuestion` or `ExitPlanMode`." The tool name is in the
  stream, so this is read from the atom's content, not stored. (Permission
  allow/deny is excluded: no post-choice line to anchor.)
- **postal is the one genuine addition.** The stream cannot tell a peer romp
  message from a human prompt: both arrive as `user` messages. Only romp's marker
  distinguishes them.

So the five flavors collapse to **`author` on the user atom** plus derivation:

```
author: "human" | "sdk" | "system" | { peer: <rompUuid> }
```

| author | derived from | opener? | was (old flavor) |
|---|---|---|---|
| `human` | `promptSource: "typed" | "queued"` | yes | typed, queued, absorbed |
| `sdk` | `promptSource: "sdk"` | yes | (dropped by old code) |
| `{peer}` | the `romp-msg-id` marker + `messages.jsonl` `from_id` join | yes | drain |
| `system` | `promptSource: "system"` | no (folds in) | (dropped by old code) |
| (none) | a `tool_result`-only user atom | no | (decision is read from content) |

`promptSource` values observed on disk (field/value extraction over the live
transcript corpus, 2026-06-13):

| value | count | meaning |
|---|---|---|
| `"sdk"` | 11360 | injected programmatically (Agent SDK / headless / `claude -p` / scheduled / workflow-spawned agents); lands in ORDINARY transcript files |
| `"typed"` | 1813 | human keystroke while idle |
| `"queued"` | 90 | human keystroke while busy, queued |
| `"system"` | 70 | harness control injection; observed example `<task-notification>` (a background task/agent completed) |
| *(absent)* | n/a | hook-injected (postal) and `tool_result` lines carry no `promptSource` |

**Turn-opener rule (a rebuild fix).** A turn opener is a genuine new prompt
(`author ∈ {human, sdk}`) or a postal message (`author: {peer}`). `system` atoms
(`<task-notification>` and the like) are NOT openers; they fold into the current
work, matching the old `_is_harness_injected` handling. The old chopper minted
boundaries only for typed and queued (`romp-events:274`), so it silently dropped
every `sdk` prompt, meaning SDK/headless sessions got no triggers at all. Keying
on `author` covers all origins uniformly.

**Postal detection.** A user atom is postal when it carries the existing
`<!-- romp-msg-id: <id> -->` marker. Fill the peer ROMP UUID by joining that id to
`timeline/messages.jsonl`: the `sent` row's `from_id` is the sender's anchor sid,
`to_id` the recipient. peer = null only when the id isn't in the log (legacy/rare).
The postal log is the authoritative sender-identity source (the same contract
postal-spec.ts relies on), so no inline `from=` and no romp-postal-service change are
needed. Never key on the `"Stop hook feedback"` prefix: Claude Code's generic
wrapper around any blocking Stop hook, not a postal signal.

**Queue operations** seen on disk: `enqueue`, `dequeue`, `remove`, and a single
`popAll` (clear the whole queue at once). These are only used to derive position
(absorbed = a mid-turn `remove`); the old code handles three of the four and must
account for `popAll`.

## The file adapter: graph recovery, quarantined

The `Session`/`Turn`/`Atom` types are substrate-neutral. Everything specific to
reconstructing them from the append-only graph on disk lives in the file adapter,
and only there.

1. **Get the file set.** The caller provides the session's transcript file(s).
   NOTE (verified against the corpus 2026-06-14): resume forks do NOT link
   child→parent via `parentUuid` in real data (0/8 multi-file dirs stitch), so the
   parser CANNOT discover a session's files by walking `parentUuid` across files.
   "Which files belong to one session" is a DEFERRED higher-layer concern (see
   below); the parser consumes the files it is given.
2. **Resolve the active path.** Walk leaf-to-root by `parentUuid` (within the
   given files); drop dead / rewound branches. Clear is handled for free: it
   leaves no parent link, so the walk stops at it and pre-clear atoms are never
   reached. COMPACTION STITCH: a `compact_boundary` carries `logicalParentUuid` to
   the pre-compaction leaf, but Claude Code sometimes points it at a uuid listed in
   `compactMetadata.allUuids` yet never written as a line; following it blindly
   orphans ALL pre-compaction history (3/69 corpus compactions, ~156 prompts). Fall
   back to `compactMetadata.preservedSegment.tailUuid` (the in-file pre-compaction
   leaf).
3. **Order atoms** by timestamp; tag each with its `fsid`.
4. **Set `author` and detect triggers.** A prompt atom whose `author ∈ {human,
   sdk}` (from `promptSource`), or a postal atom (`author: {peer}`, from the
   romp-msg-id marker + the `messages.jsonl` `from_id` join), that arrives after
   `end_turn` is a trigger. `system` atoms
   (`<task-notification>` etc.) and mid-turn prompts/decisions are kept inline,
   not treated as openers. (Do not restrict openers to typed/queued, the old bug
   that dropped every SDK/headless turn.)
5. **Infer `ended`.** From the turn's last assistant `stop_reason`. (The stream
   states this via `result`; the transcript usually omits a result line.)
6. **Synthesize idle atoms.** From `states/<sid>.jsonl` idle transitions, insert
   `{type: "idle", t, end}` into the turn's atom list. Replaces the 15-minute
   clip, and lets the timeline color the gap as not-working.

On a future stream substrate, steps 1, 2, 5, and 6 disappear (the stream is
already linear and marks turn-end), and steps 3 and 4 reduce to reading messages
in arrival order. Same `Session`/`Turn`/`Atom` out either way.

### Session → files is a deferred higher-layer concern

The original spec assumed a resume fork's first line links to its parent via
`parentUuid`, so a directed leaf→root walk would gather a session's files.
VERIFIED FALSE against the corpus (2026-06-14): 0/8 multi-file dirs stitch that
way; the only cross-file `parentUuid` link was an aborted 0-turn fork. So the
parser cannot resolve "which files are one session" from the transcript graph. The
old `romp-events` did it a layer up (same `customTitle` + shared-node
intersection), but that inference is fragile and node-intersection does not hold
here either.

So this is OWNED ABOVE the parser and is DEFERRED: caption-only works per-file and
does not need it; it matters only for stitching a resumed session's history and
for the goals layer. Lean when we build it: track it EXPLICITLY, a `rompUuid → its
fork files` registry updated on resume (the headless backend's `lastSid` pattern,
extended to the interactive launcher), rather than re-inferring. The parser stays
correct, it consumes a caller-provided file set.

### Identity vs the walk vs click-landing

Three separate concerns, kept separate:

- **Identity** binds to `rompUuid` (stable). Nothing downstream sees an unstable
  id. This removes the need to reassemble identity at all.
- **The walk** starts at `leafFsid`, a pointer that updates on each resume (the
  same role headless-backend's `lastSid` already plays). It is an index, not an
  identity, so its changing is harmless.
- **Click-to-open** uses the per-atom `fsid` to know which physical file to open.
  It may vary per atom; that is fine, it is provenance.

## What is different from the streaming API

The overlap is near total: atom `type`/`subtype`, `message.content` blocks,
`tool_use`/`tool_result`, `usage`, `stop_reason`, `num_turns`, `compact_metadata`,
and `session_id` are all verbatim. The genuine deltas are five, four of which are
file-substrate recovery:

1. **`rompUuid` identity.** A stable session key above the stream's per-run
   `session_id`, because resume mints a new `session_id` and the file fragments
   identity. A romp-level addition.
2. **The `idle` atom.** The one atom kind with no stream counterpart. The stream
   marks turn-end explicitly and never needs to represent "nothing happened"; we
   do, to clip revived turns and to color the gap.
3. **`result` is inferred, not received.** The stream emits a `result` atom per
   turn; the transcript usually does not, so on the file substrate `ended` is
   synthesized from `stop_reason`. Same field, different origin.
4. **`author` on user atoms.** The one field that carries information the stream
   lacks: the stream cannot tell a peer romp message from a human prompt (both are
   `user` messages), so `author` (esp. `{peer}`) is a genuine addition. The rest
   of the old flavor enum (typed/queued/absorbed/decision) was derivable from
   position and content and is not stored.
5. **Graph fields** (`parentUuid`, `fsid`, active-path resolution). The stream is
   already linear and resolved; these exist only to rebuild that linearity from
   the append-only graph on disk.

Everything else is the streaming API. The model is not a parallel invention; it
is the streaming message protocol with a stable identity on top and a thin file
adapter underneath that reconstructs what a stream would have streamed.

## Open questions

- **Agent SDK vs hand-rolled stream-json client** for the future
  headless-with-parity substrate. Both yield the same message types; the SDK adds
  typed objects, `canUseTool`/permission callbacks (which make AskUserQuestion
  work headless), and hooks.
- **Higher-layer sub-segmentation.** Whether summaries / timeline split a turn at
  an absorbed message or a decision atom, or treat the whole `end_turn`-bounded
  turn as one unit. The bottom layer preserves the information either way.
