# Linking audit: how chat, timeline, feed, and ledger point at each other

Internal design doc (not user-facing). An audit of every cross-surface link in
romp: the object types that can be pointed at, the identifiers links carry, the
granularity they resolve to, where it's wrong, and a target design + test plan.
Built 2026-06-19 from a read of `bin/romp-kernel`, `bin/romp-event-model`,
`chat-view/src/webview/render.ts`, `chat-view/src/webview/feed.ts`, and
`obsidian/romp-timeline-view.js`. Verified line refs throughout.

## TL;DR — the five findings

1. **The ledger and the feed render the SAME goal tree but link by DIFFERENT
   mechanisms.** Feed nodes carry exact `anchorUuid` / `promptAnchorUuid` and
   land BY ID (`romp-kernel:1949-1954`, `feed.ts` `showOnTimeline`); ledger nodes
   carry only `t` / `mt` and land BY NEAREST TIME within a 6-hour window
   (`romp-kernel:1629-1637`, `render.ts:2567,2602` → `scrollToNearestT`, 6h cap at
   `:1875`). The kernel already computes the uuids the ledger needs
   (`uuid2seg` / `seg_anchors`, `romp-kernel:1411-1417`) and uses them for the
   bullet fallback's `tlId` — it just never attaches them to the tree nodes.
   **This is the single highest-value fix and it is cheap.**

2. **A 6-hour nearest-time search is the ledger's only resolver and the feed's
   fallback** — a banned time-heuristic (CLAUDE.md: "Prefer exact event-based
   mechanisms over time-based heuristics… find the event it is approximating and
   key on that event instead"). The event it approximates is the atom uuid, which
   we already have.

3. **Nothing finer than a whole turn (one atom) is addressable from outside.**
   The user's question — "can we link to a side bullet like a tool use or a system
   message, vs. segments or turns?" — answers NO today. ContentBlocks have no id
   (event-model), the chat emits anchors only at `.turn` level
   (`render.ts:433-438`), and system atoms are deliberately off the rail with no
   anchor (`render.ts:79`). Yet `tool_use.id` / `tool_result.tool_use_id` are
   STABLE, API-supplied, and currently unused as anchors — block-level linking is
   within reach.

4. **There are three different notions of "the work anchor"** across the surfaces
   (feed: reply-or-work atom; timeline: `replyUuid || workUuid || uuid`; ledger:
   none, time only), and **two different highlight schemes** (feed↔timeline hover
   matches by segment id; chat `glowTurns` matches by ±2s TIME RANGE,
   `render.ts:520-527`).

5. **The timeline never moved into `ui/`** as `read-side.md:195-199` planned. It
   is a 147 KB module in `obsidian/romp-timeline-view.js` served verbatim by the
   kernel (`romp-kernel:3546-3554`), with its own id expectations
   (`t.id`/`t.promptId`/`t.workId`/`t.replyUuid`) and its tests in a different
   tree (`chat-view/src/timeline-*.test.ts` test a module that lives in
   `obsidian/`). All three panes do NOT share one view-builder.

---

## 1. The objects — what can be pointed at

The producer side (`bin/romp-event-model`) defines a strict, substrate-neutral
tree; the read side (`bin/romp-kernel`) derives projections from it. Two parallel
trees exist: the **event tree** (Layer 1, transcript structure) and the **goal
tree** (Layer 2, judge output). Plus the postal log.

### Event tree (Layer 1)

| Object | What it is | Carried in |
|---|---|---|
| **Session** | one conversation identity | keyed by `rompUuid` |
| **Turn** | `end_turn`-bounded stretch; the stream unit | `Turn.id` = `rompUuid:t:hash` |
| **Segment** | derived: turn split at each input atom; the timeline bar | `Segment.id` = `rompUuid:t:hash` |
| **Atom** | one transcript line / one streaming message | `Atom.uuid` (API-supplied) |
| **ContentBlock** | one widget: `text` / `thinking` / `tool_use` / `tool_result` | **no id** (except tool blocks) |

Containment: `Session → Turn → Segment(derived) → Atom → ContentBlock`
(`event-model.md:70-77`).

### Chat render objects (DOM, one `.turn` per ChatEvent)

`render.ts:36-82` defines ChatEvent kinds, each a `.turn-*` row:
`user`, `assistant`, `thinking`, `tool` (incl. `AskUserQuestion`→`.turn-ask`,
`Task`/`Agent`→agent-report), `postal`, `todo`, `queued`, `compact`, `apiError`,
`system`. In compact mode consecutive tools collapse into a `.turn-toolgroup`
(`render.ts:1961-2033`).

### Goal tree (Layer 2)

Nodes (`romp-kernel` `load_goals`): `id` = `rompUuid:gN`, `text`, `t` (minted),
`mt` (last touched), `parentId`/`children`, `status` (working/blocked/completed),
`nodeComplete`, `blocked`, `trail` (filed segment ids), `origin` (handoff
provenance). Rendered TWICE: as feed cards (`AskTreeNode`, `feed.ts:48-63`) and
as ledger nodes (`LedgerTreeNode`, `render.ts:143`).

### Postal log

`timeline/messages.jsonl` rows: `id` (mid), `from_id`/`to_id` (sender/recipient
`rompUuid`), `t`, `body`. The cross-session edge.

---

## 2. The identifiers — the linking primitives

| Identifier | Format | Stable? | Source | Role as a link key |
|---|---|---|---|---|
| `rompUuid` | uuid | ✅ never changes | launcher | session / tab identity |
| `Atom.uuid` | uuid | ✅ API-supplied | Claude transcript | **the one good deep-link key** |
| `tool_use.id` / `tool_result.tool_use_id` | string | ✅ API-supplied | Claude transcript | STABLE, **currently unused** as anchor |
| `mid` (postal) | uuid | ✅ | romp-postal | postal highlight (`data-mid`) |
| `Turn.id` / `Segment.id` | `rompUuid:t:sha1(triggertext)[:8]` | ⚠️ content-hashed | minted by romp | judge dedup key; breaks if trigger text edited |
| `fsid` | filename stem | ❌ positional | filename | click-to-open file only; new on resume |
| `node.id` | `rompUuid:gN` | ✅ within session | judge | goal identity |
| `t` / `mt` | epoch seconds | ⚠️ not unique | timestamp | **the ledger's only link key (wrong)** |
| ContentBlock index | array position | ❌ positional | render-time | not exposed; not addressable |

**DOM anchors the chat actually emits** (`render.ts`): `data-uuid` (`:434`),
`data-t` (`:438`), `data-mid` (postal only, `:1084`). No `id=` attributes. System
context card emits none (`:79`, "No ts/uuid → off the rail"). AskUserQuestion
swaps `data-uuid` to the tool_result line's `resultUuid` (`:433`).

**The two chat-side resolvers:**
- `scrollToAnchor(uuid)` (`render.ts:1795-1815`) — exact `.turn[data-uuid=…]`
  match, with a kind guard (a "user"-intent link refuses a non-`turn-user`
  target, `:1809`). The good path.
- `scrollToNearestT(t, kind)` (`render.ts:1850-1882`) — nearest `.turn[data-t]`
  by clock distance, capped at 6h (`:1875`), kind-restricted then "nearest any"
  fallback (`:1869`). The time path.
- `landActive` (`:2173-2206`) tries uuid first, then time **only for
  `kind==="user"`** (`:2189`); a work link that misses its uuid honest-fails to a
  toast (`:2198`), it does NOT time-fall-back.

---

## 3. The link map — what points where, by what id, at what grain

| From → To | Trigger | Id carried | Resolver | Grain |
|---|---|---|---|---|
| **Feed card title → chat** | click | `promptAnchorUuid` (or `anchorUuid` for delegations) + `t` | `showOnTimeline`→`focus`→`scrollToAnchor`, time fallback | turn (prompt) |
| **Feed modal node text → chat** | click | `node.promptAnchorUuid` + `t` | uuid-first, "user" time fallback | turn (prompt) |
| **Feed modal node check/time → chat** | click | `node.anchorUuid` + `mt` | uuid-first, honest-fail (no time fallback for work) | turn (work) |
| **Feed row (history) → chat** | click | `reply_id` (uuid) | uuid | one event |
| **Feed card hover → timeline** | hover | ask `itemId` → `showAskPath` | segment-id match | whole trail |
| **Ledger node text → chat** | click | **`t` only** | `scrollToNearestT(t,"user")` | turn (nearest, 6h) |
| **Ledger node check/time → chat** | click | **`mt` only** | `scrollToNearestT(mt,"assistant")` | turn (nearest, 6h) |
| **Ledger bullet (goal-less) → host** | click | `id`(uuid)+`t` via `ledgerLocate` | **handler not found — verify** (`render.ts:2712`) | turn |
| **Timeline bar → chat** | click | `workAnchorOf` = `replyUuid\|\|workUuid\|\|uuid` + `anchorT` | `openChat`→`focus`, uuid-first, time fallback | segment (work) |
| **Timeline dot → chat** | click | `t.uuid` + `anchorT`, `anchorKind="user"` | uuid-first, user time fallback | segment (prompt) |
| **Timeline hover → feed** | hover | `[t.id]`/`[t.promptId]`/`[t.workId]` | segment-id match (`dotLit`/`barLit`) | segment |
| **Feed/timeline → chat highlight** | hover | `glowTurns{groups, mids}` | postal by `data-mid` (exact); work by **±2s time range** (`render.ts:520-527`) | turn |
| **Postal handoff node → chat** | click | sender-side `node.id`, resolved in recipient transcript | uuid/`data-mid` | turn (may be dead) |

Translation hop: `showOnTimeline` → kernel `_focus_msg` (`romp-kernel:2841-2845`)
→ `focus{id, anchor, anchorT, anchorKind}` → `render.ts:3403` → `setActive` →
`landActive`.

---

## 4. The granularity ladder (and the gap the user asked about)

Addressable from another surface today:

```
Session         ✅ rompUuid (tab)
  Turn          ✅ data-uuid / data-t            ← the finest external target
    Segment     ✅ segment id (timeline/feed only, internal)
      Atom      ✅ = the turn row (1 atom ≈ 1 turn)
        Block   ❌ NOT addressable
          text / thinking      ❌ no id
          tool_use             ❌ no anchor — though tool_use.id is STABLE
          tool_result          ❌ no anchor — though tool_use_id is STABLE
  system atom   ❌ off the rail, no anchor (render.ts:79)
  idle atom     ❌ uuid:null, synthesized
```

So: **you can link to a turn, not to "a tool use or a system message or a
sub-bullet."** The two things the user named are exactly the two gaps:
- a **tool use** — has a stable `tool_use.id` we don't surface as a DOM anchor;
- a **system message** — deliberately rendered without a uuid/t.

Coarsest = session (tab). Finest = turn. Nothing sub-turn. Adding block anchors
is the lever that opens the rest (see §6-C).

---

## 5. Where it's wrong (ranked)

**P0 — Ledger ↔ feed link divergence (same data, two mechanisms).**
The goal tree is one dataset rendered in two panes. The feed deep-links BY ID;
the ledger by nearest-time. Symptoms: clicking the same goal in the ledger vs. the
feed can land on different turns; in a busy minute the ledger lands on the wrong
turn; a work-zone click (assistant `mt`) has no exact target at all. Root cause:
`_twalk` (`romp-kernel:1629-1637`) omits the uuids that `build_feed`
(`:1949-1954`) attaches — even though `build_chat` already has `uuid2seg` /
`seg_anchors` in scope (`:1411-1417`, used for bullets at `:1524-1527`). Cheap fix.

**P0 — Banned time-heuristic as a primary resolver.** `scrollToNearestT`'s 6h
window (`render.ts:1875`) is the ledger's ONLY path and the feed's fallback.
Violates the repo design rule. The event it approximates (the atom uuid) is known.

**P1 — No sub-turn granularity.** Can't link to a tool use, a thinking block, a
specific system injection, or a result. `tool_use.id` is stable and wasted.

**P1 — Three "work anchor" definitions.** Feed (reply-or-work), timeline
(`replyUuid||workUuid||uuid`, `obsidian/…:138-143`), ledger (none). They can
disagree on which atom is "the work." Should be one shared kernel helper
(`_seg_anchors`, `romp-kernel:2236`) feeding all three.

**P1 — Highlight is half-id, half-time.** Feed↔timeline hover is id-based;
chat `glowTurns` matches work by ±2s time range (`render.ts:520-527`). Same
inconsistency class as P0, on the hover channel.

**P2 — Compact toolgroup anchor = first tool's uuid** (`render.ts:2026-2027`);
loses its anchor if that tool is pruned, collides on the epoch fallback.

**P2 — Turn/Segment ids are content-hashed** (`rompUuid:t:sha1(text)`); editing a
prompt changes the id and breaks judge dedup + any stored reference. Deliberate
fork-stability tradeoff, but never use these as navigation keys — use the atom
uuid.

**P2 — Postal handoff nodes link by a sender-side id** resolved in the
recipient's transcript; dead link if that postal message isn't rendered.

**P2 — `ledgerLocate` may be a dead message.** Posted at `render.ts:2712` but no
handler found in `extension.ts` or `romp-kernel` — the goal-less bullet fallback
nav may be a no-op. Verify.

**P3 — Distiller `summary`/`blockSummary`/`doneWhy` have no link target**
(synthesized text). Acceptable, but they could anchor to the segment that produced
them.

**P3 — Timeline not unified into `ui/`** (`read-side.md:195-199` unrealized).
Separate module, separate id contract, tests detached from source. Divergence risk.

**P3 — `fsid` positional + resume stitching deferred** (`event-model.md:329-345`).
Cross-file history links can break; multi-file session stitching not implemented.

**P3 — idle atoms `uuid:null`**, re-parse-time-dependent; not addressable (fine,
but means the timeline's not-working gaps can't be linked to).

---

## 6. The target design — one primitive, robustly

**A. One link envelope, everywhere.** Every cross-surface link carries
`{ sid, uuid, kind, blockId? }`. `uuid` is an atom uuid; `kind ∈ {prompt, work}`
sets the landing intent (already the `anchorKind` guard); `blockId` is optional
(see C). Resolve by `scrollToAnchor` first, ALWAYS. Time is a last resort, and
when used it must `landTrail`/`landToast` so a degraded landing is visible, never
silent.

**B. Make the ledger carry uuids (the P0 fix).** In `_twalk`
(`romp-kernel:1629-1637`), attach `promptAnchorUuid` / `anchorUuid` per node by
the SAME trail→segment→anchor lookup `build_feed` uses (`:1949-1954`). Then in
`render.ts` `wireZone` (`:2563-2611`), prefer the uuid (post `showOnTimeline` /
call `scrollToAnchor`) before `scrollToNearestT`. Extract ONE kernel helper
`node_anchors(node) → (promptUuid, workUuid)` and call it from both `build_feed`
and `build_chat`, so the feed and ledger can never drift again.

**C. Block-level anchors (opens tool-use / system-message linking).** Give each
rendered ContentBlock a `data-block`:
- tool blocks → the stable `tool_use.id` (best: survives re-render);
- other blocks → `${atomUuid}#${blockIndex}` (positional but scoped to a stable
  atom).
Extend `scrollToAnchor` to try `[data-uuid]` then `[data-block]`. Now the feed,
timeline, and ledger can optionally point at a specific tool use or result.

**D. Anchor the system atoms.** They have a real `uuid` in the transcript; "off
the rail" is a render choice. Emit `data-uuid`/`data-t` so a `<task-notification>`
or system injection becomes linkable (keep it off the visual rail if desired).

**E. One work-anchor helper.** Make `_seg_anchors` (`romp-kernel:2236`) the single
definition of (promptUuid, workUuid) and feed feed + timeline + ledger from it.
Delete `workAnchorOf`'s independent chain in `obsidian/…` in favor of the kernel
value.

**F. Unify the highlight channel on ids.** Have `glowTurns` carry segment/atom
ids and match `[data-uuid]`/`[data-block]`, not a ±2s time range
(`render.ts:520-527`).

**G. Unify the timeline into `ui/`** (the deferred `read-side.md` move) so all
three panes share one view-builder, one id contract, and co-located tests. At
minimum, share the anchor helper and add a contract test (§7-E).

**H. Never navigate by a content-hashed id.** Keep `Turn.id`/`Segment.id` as judge
dedup keys only; all navigation uses atom uuids.

---

## 7. Test plan — what to verify once the design settles

Grouped by concern. Each is a unit/integration test in the existing homes
(`chat-view/src/webview/*.test.ts` for the renderer, `tests/test_*.py` for the
kernel projections).

### A. Exact-uuid landing (the core contract)
- [ ] Each surface → chat lands on the EXACT `.turn[data-uuid]`, per object kind:
      user, assistant, thinking, tool, AskUserQuestion (lands on `resultUuid`),
      postal, todo, queued, compact, apiError.
- [ ] Kind guard: a `prompt`/`"user"` link refuses a non-`turn-user` target
      (`render.ts:1809`); a `work`/`"assistant"` link refuses a `turn-user`.
- [ ] Duplicate-uuid safety: if two turns ever share a uuid, only the first is
      targeted and no exception is thrown.

### B. Cross-surface consistency (the P0 regression)
- [ ] **The same goal node, clicked in the ledger and in the feed, lands on the
      SAME turn.** (Build a fixture goal tree; assert ledger node and feed node
      resolve to identical uuids.)
- [ ] Ledger node text → the minting USER turn by uuid (not nearest-time).
- [ ] Ledger node check/time → the resolving ASSISTANT turn by uuid.
- [ ] `node_anchors` returns identical (promptUuid, workUuid) when called from
      `build_feed` and `build_chat` for the same node.

### C. Fallback behavior (degrade visibly, never silently wrong)
- [ ] uuid present but turn not rendered (paginated/rewound) → honest-fail toast,
      `landTrail` records `pointer-not-rendered` (`render.ts:1799`).
- [ ] uuid null → time fallback ONLY for prompt intent; work intent honest-fails
      (`render.ts:2189,2198`) — assert no silent wrong-turn landing.
- [ ] **Regression guard: assert no link path uses `scrollToNearestT` as its SOLE
      resolver** once B lands (grep-style test over wired zones).
- [ ] Same-second collision: two turns within the 6h window at the same `t` —
      uuid path lands exactly; time path is allowed to be wrong (documents why
      uuid is required).

### D. Granularity (the new block anchors, if §6-C is built)
- [ ] A tool-use link lands on `[data-block="<tool_use.id>"]`.
- [ ] A tool-result link lands on its block.
- [ ] A system atom is linkable by `data-uuid` (after §6-D).
- [ ] Block anchor survives a re-render (tool block keyed by `tool_use.id`, not
      index).

### E. Timeline ↔ chat ↔ feed id contract
- [ ] The segment ids the timeline emits on hover (`t.id`/`promptId`/`workId`)
      match what the kernel puts on chat bullets (`tlId`) and feed nodes.
- [ ] `dotLit`/`barLit` light the right glyph for a chat prompt-hover vs.
      work-hover.
- [ ] `glowTurns` highlights by id (after §6-F), asserted against a fixture with
      two turns 1s apart (the ±2s range would catch both; ids must catch one).
- [ ] Timeline bar click uses the shared work anchor (after §6-E), not the
      independent `workAnchorOf` chain.

### F. Edge cases
- [ ] Rewound transcript: a goal whose trail segments are gone → honest-fail, no
      wrong landing.
- [ ] Compaction stitch (the `logicalParentUuid` dangling case,
      `event-model.md:210-230`): anchors still resolve across the boundary.
- [ ] Resume fork (multi-file): click-to-open uses the right `fsid`; cross-file
      anchor resolves or honest-fails.
- [ ] Cleared node: mark+text+time all route to the minting message (no jump to a
      nonexistent checkoff, `render.ts:2592-2599`).
- [ ] Postal handoff node: links to the recipient-transcript message; if that
      message isn't rendered, honest-fail (not a wrong turn).
- [ ] Grouped ask card: title links to a live member that still exists after
      others are cleared.
- [ ] Compact toolgroup: collapsed group is linkable; expanded children each
      linkable by their own uuid; first-tool-pruned case degrades gracefully.
- [ ] `ledgerLocate`: confirm a handler exists (or remove the dead post),
      `render.ts:2712`.
- [ ] AskUserQuestion: external link uses `resultUuid`; if kernel omitted it,
      falls back to `ev.uuid` without crashing.

### G. Security/serve (unchanged contract, keep green)
- [ ] A cross-site `/ws` upgrade with a foreign Origin is rejected
      (`read-side.md:304`) — linking changes must not touch this.
