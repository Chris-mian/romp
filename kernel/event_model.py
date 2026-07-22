#!/usr/bin/env python3
"""romp-event-model — the rebuilt bottom-layer parser (docs/event-model.md).

Turns a romp session's transcript(s) into the Session -> Turn -> Atom tree the
design doc pins down: the Claude streaming protocol made graph-aware. An atom is
a streaming message, a turn is the user-to-`end_turn` cycle, and the on-disk
transcript is those messages plus the graph metadata needed to rebuild them
after rewinds and resume-forks.

NOT wired into the live pipeline. This is a standalone module built for
side-by-side evaluation against bin/romp-events (inventory Decision 1); it does
NO summaries / relevance / asks / links / model calls — only the event layer.

The Session/Turn/Atom shapes are substrate-neutral. Everything specific to
rebuilding them from the append-only on-disk graph lives in the FILE ADAPTER
section and only there; on a future stream substrate the same tree is filled
directly (steps that recover linearity, `ended`, and idle simply disappear).

CLI:
  romp-event-model --test <transcript>   # human dump of one session's turn/atom tree
  romp-event-model --emit <transcript>   # the Session tree as JSON

Auxiliary inputs the file adapter may read (same category as the transcript):
  states/<sid>.jsonl        -> idle atoms (real idle transitions, not a silence heuristic)
  timeline/messages.jsonl   -> peer rompUuid for a postal atom (join on the msg id)
"""
import json, os, re, sys, time, hashlib
from datetime import datetime
from pathlib import Path

HOME     = Path.home()
STATE    = Path(os.environ.get("XDG_STATE_HOME", str(HOME / ".local/state"))) / "romp"
PROJECTS = HOME / ".claude" / "projects"
NAMES    = STATE / "names"
STATES_DIR   = STATE / "states"
MESSAGES_LOG = STATE / "timeline" / "messages.jsonl"

# A turn ends when the model hands the floor back: stream `end_turn` / `stop_sequence`.
# Mid-turn the model stops with `tool_use` (a tool cycle) — that does NOT end the turn.
END_STOPS = ("end_turn", "stop_sequence")
# romp's own postal marker, injected into a delivered message body. It is the ONLY
# postal signal — never the generic "Stop hook feedback:" prefix (any blocking Stop
# hook produces that). The sender rompUuid is resolved from timeline/messages.jsonl
# by joining this id (the on-disk marker carries the id but not the sender).
POSTAL_RE = re.compile(r"romp-msg-id:\s*(\S+)")
POSTAL_KIND_RE = re.compile(r"romp-msg-kind:\s*(delegate|coordinate|question)")
# romp's marker on a message IT injected straight into a pane (a feed NUDGE / auto-nudge / Retry — NOT a
# peer message, and NOT a follow-up YOU typed). It means "render this as a romp-injected system message"
# (the gray bubble), distinct from a human prompt or a peer's postal message. ONLY romp-injected authors
# romp: romp-goal-id is orthogonal "which goal" metadata that rides EVERY feed follow-up, INCLUDING ones
# you type yourself — those are yours (blue human bubble), so a goal-id alone must NOT author romp; the
# kernel adds romp-injected for nudges only (the user 2026-06-20).
# COMMENT FORM ONLY (the user 2026-07-08): every real emitter writes the literal `<!-- romp-injected -->`
# (kernel _followup_body / RETRY_MSG, the sdk backend's restart notices; romp-judge's NUDGE_MARKER_RE
# already matches this way). A bare word-match also fired on message CONTENT that merely *mentions* the
# marker — the user's typed follow-up quoted a card summary discussing romp-injected and rendered as a
# GRAY ROMP CARD. \s* so the absorbed-atom path's historical whitespace-collapse still matches.
ROMP_INJECT_RE = re.compile(r"<!--\s*romp-injected\s*-->")
# romp-AUTO: an AUTO-nudge (the kernel's background _auto_nudge_tick), distinct from a Nudge BUTTON click or a
# typed follow-up — both of which are romp-injected too. Only auto-nudges (+ postal) are "from romp" for the
# romp-logo marker; the user's own button/follow-ups are not (the user 2026-06-23). Rides alongside
# romp-injected; an atom carrying it gets atom["rompAuto"]=True for the timeline/chat to mark.
# Comment form only, same reason as ROMP_INJECT_RE (content mentioning the marker must not match).
ROMP_AUTO_RE = re.compile(r"<!--\s*romp-auto\s*-->")
# Harness-injected SYSTEM wrappers that are NOT the user: a background-task completion (`<task-notification>`,
# fired when a backgrounded Agent/Task finishes) and `<system-reminder>` blocks. In an SDK session these arrive
# over the stream as promptSource "sdk", so sdk_human would author them 'human' → _is_opener opens a turn →
# the planner force-pins a junk goal titled "<task-notification>" (the user 2026-06-30, screenshot). Anchored
# at the START so a real user message with a reminder APPENDED isn't caught (the kernel splits those off).
SYSTEM_WRAPPER_RE = re.compile(r"^\s*<(?:task-notification|system-reminder)\b")
# Claude Code's NATIVE teammate/agent-message channel — one agent messages another, DISTINCT from romp's
# own postal bus (no romp-msg-id). It's delivered as a promptSource "sdk" user record whose text is a
# <prompt> wrapper: "Another Claude session sent a message:" + one or more <teammate-message
# teammate_id="…" color="…" [summary="…"]>body</teammate-message> blocks + a fixed "permission laundering"
# boilerplate. We recognize it so the chat renders it as its OWN collapsed card, not a blue "you typed
# this" bubble (the user 2026-07-05: idle_notification coordination JSON showed as a human message).
# Anchored at the START (optionally inside a one-level <prompt>/<unit> wrapper) so it matches a real
# DELIVERY and NOT a conversation SUMMARY that merely quotes one ("<turn>\nUSER ASKED: Another Claude…").
TEAMMATE_MSG_RE = re.compile(r"^\s*(?:<\w+>\s*)?Another Claude session sent a message:", re.I)
TEAMMATE_BLOCK_RE = re.compile(r"<teammate-message\b([^>]*)>(.*?)</teammate-message>", re.S)
# Claude Code's slash-command transcript wrappers. The INVOCATION (`<command-name>`) and its OUTPUT
# (`<local-command-stdout>`) become a tracked COMMAND TURN (the user 2026-06-29) — see atoms(); the rest
# (`<command-message|args|contents>`, `<local-command-caveat>`) stay skipped as harness noise.
CMD_WRAP_RE = re.compile(r"^\s*<(?:command-(?:name|message|args|contents)|local-command-(?:stdout|caveat))>")
COMMAND_NAME_RE = re.compile(r"^\s*<command-name>([^<]*)</command-name>")           # the slash command itself, e.g. "/usage"
COMMAND_ARGS_RE = re.compile(r"<command-args>([\s\S]*?)</command-args>")            # its arguments (often empty)
LOCAL_STDOUT_RE = re.compile(r"^\s*<local-command-stdout>([\s\S]*?)</local-command-stdout>")   # the command's output
# A slash command's stdout is captured from the TUI VERBATIM, so it can carry ANSI SGR color codes
# (e.g. /rate-limit-options prints "\x1b[38;5;114mRemoved monthly spend limit\x1b[39m" in green). The
# ESC byte is invisible but the "[38;5;114m…[39m" renders as LITERAL text in the chat (the user
# 2026-07-16). Strip the full CSI/SGR family at the atom source — the one place both the chat and the
# timeline read — so the codes never reach any renderer. Only local-command-stdout needs this; model
# API text never contains ANSI.
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def strip_ansi(s: str) -> str:
    """Remove ANSI CSI/SGR escape sequences (color, cursor) from captured terminal output."""
    return ANSI_RE.sub("", s) if s else s
# The Skill tool's INSTRUCTIONS record (the user 2026-07-08): after a `Skill` tool_use + its "Launching
# skill: X" tool_result, the CLI writes the skill's full markdown as an isMeta user record opening with
# this line. It's the ONE isMeta payload worth keeping — surfaced as a flagged, content-EMPTY atom (the
# text rides atom["skillMd"], so no assistant-text reader — judge work text, captions, summary anchors —
# ever mistakes the skill's instructions for something the agent wrote). The kernel folds it into the
# invoking Skill tool event, collapsed by default.
SKILL_CONTENT_RE = re.compile(r"^\s*Base directory for this skill:")
SKILL_MD_CAP = 16000              # transport cap for the joined skill markdown (skills run ~2-15k chars)
SUMMARY_CAP = 8000                # cap the compaction-summary text attached to a compact_boundary atom (a raw
#   summary runs ~16k chars; the head carries the key sections, and it re-ships with the tail — keep it bounded)


# ───────────────────────── small helpers ─────────────────────────
def parse_z(s):
    """Transcript timestamp (ISO-8601 UTC, '…Z') -> epoch int, or None.

    Every transcript record carries a timestamp, so this runs tens of thousands of times per fleet parse
    — the C-accelerated datetime.fromisoformat (3.11+, accepts a '+00:00' offset + fractional secs) is
    ~13x faster than strptime and was a real chunk of "startup is slow" (the user 2026-07-03). strptime
    stays as a fallback for any exotic form fromisoformat rejects, so behavior is unchanged."""
    if not s:
        return None
    s = s.strip()
    try:
        return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())
    except Exception:
        pass
    s = s.replace("Z", "+0000")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return int(datetime.strptime(s, fmt).timestamp())
        except Exception:
            pass
    return None


def _read_jsonl(path):
    """Yield parsed json objects from a .jsonl file; [] on any error."""
    try:
        with open(path, errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except Exception:
                    continue
    except OSError:
        return


# Append-incremental transcript reads (the user 2026-07-05: the dashboard re-parsed a 40MB streaming
# transcript FROM BYTE ZERO on every push — ~0.6s of json.loads per append, saturating the push loop and
# queueing every click behind it). Transcripts are append-only, so cache each file's parsed records with
# the byte offset of the last COMPLETE line: a grown file loads only the appended bytes. Guards, in order:
#  - same (mtime, size)   → serve the cached records as-is (the common no-change poll);
#  - grew                 → verify the cached tail bytes still sit before the cached offset (a REWRITE that
#                           happens to be larger would otherwise serve a corrupt splice), then parse just
#                           the new bytes. Mismatch → full re-read;
#  - shrank / same-size-new-mtime → full re-read (a rewrite, not an append).
# A trailing line with no "\n" yet (a writer caught mid-append) is NOT consumed — the offset stays before
# it, so the next read picks the completed line up. Records are treated as IMMUTABLE by every consumer
# (FileAdapter builds fresh atom dicts; nothing writes into a record), matching the kernel's existing
# whole-parse cache contract. The cached list itself is never extended in place — a grown file stores a
# NEW list — so a concurrent reader holding the old list is never surprised mid-iteration.
_JSONL_CACHE = {}                 # path -> (mtime, size, offset, tail_bytes, records)
_JSONL_CACHE_MAX = 64             # bounded by fleet size; wholesale clear is fine (one cold re-read each)
_JSONL_TAIL_GUARD = 64            # bytes of pre-offset content re-verified before an incremental read


def _scan_jsonl_bytes(data, base_offset):
    """(records, consumed) for a bytes blob of jsonl starting at base_offset: parsed objects of every
    COMPLETE line, and the byte offset just past the last complete line (a trailing partial is left)."""
    end = data.rfind(b"\n")
    if end < 0:
        return [], base_offset
    records = []
    for line in data[:end + 1].splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line.decode("utf-8", "replace")))
        except Exception:
            continue
    return records, base_offset + end + 1


def _read_jsonl_incremental(path):
    """The parsed records of `path` (a list, NOT a generator), served append-incrementally per the cache
    contract above. Falls back to a full read on any surprise; [] on any error, like _read_jsonl."""
    path = str(path)
    try:
        st = os.stat(path)
    except OSError:
        _JSONL_CACHE.pop(path, None)
        return []
    hit = _JSONL_CACHE.get(path)
    if hit is not None and hit[0] == st.st_mtime and hit[1] == st.st_size:
        return hit[4]
    try:
        with open(path, "rb") as fh:
            if hit is not None and st.st_size > hit[1]:
                _, _, offset, tail, records = hit
                fh.seek(max(0, offset - len(tail)))
                if fh.read(len(tail)) == tail:            # the file really is our cached prefix + more
                    new, offset = _scan_jsonl_bytes(fh.read(), offset)
                    records = records + new               # a NEW list — never extend the served one in place
                else:
                    fh.seek(0)                            # prefix changed → a rewrite → full re-read
                    records, offset = _scan_jsonl_bytes(fh.read(), 0)
            else:
                records, offset = _scan_jsonl_bytes(fh.read(), 0)
            tail_from = max(0, offset - _JSONL_TAIL_GUARD)
            fh.seek(tail_from)
            tail = fh.read(offset - tail_from)
    except OSError:
        _JSONL_CACHE.pop(path, None)
        return []
    if len(_JSONL_CACHE) > _JSONL_CACHE_MAX:
        _JSONL_CACHE.clear()
    _JSONL_CACHE[path] = (st.st_mtime, st.st_size, offset, tail, records)
    return records


def _content(message):
    """The content[] of a message, normalized: a bare string becomes one text block,
    so every atom carries a list of blocks (the 'one atom, many blocks' shape)."""
    if not isinstance(message, dict):
        return []
    c = message.get("content")
    if isinstance(c, str):
        return [{"type": "text", "text": c}] if c.strip() else []
    return c if isinstance(c, list) else []


def _text_of(blocks):
    """Joined text of the text blocks in a content list (thinking/tool_use/tool_result skipped)."""
    return " ".join(b.get("text", "") for b in blocks
                    if isinstance(b, dict) and b.get("type") == "text").strip()


def _block_types(blocks):
    return [b.get("type") for b in blocks if isinstance(b, dict)]


def _is_real_prompt(blocks):
    """A user line is a genuine PROMPT (vs a tool_result-only harness line) when it
    carries any text. A tool_result-only line has no text block."""
    return bool(_text_of(blocks))


def _has_tool_result(blocks):
    return any(isinstance(b, dict) and b.get("type") == "tool_result" for b in blocks)


def _norm_message(message):
    """The Anthropic message object kept verbatim where it exists (role, content blocks,
    model, usage, stop_reason). Content is normalized to a block list."""
    if not isinstance(message, dict):
        return None
    out = {"role": message.get("role"), "content": _content(message)}
    for k in ("model", "stop_reason", "usage"):
        if message.get(k) is not None:
            out[k] = message[k]
    return out


# ───────────────────────── authorship (the one real addition over the stream) ─────────────────────────
# A user atom's author is the ONE field the stream lacks: it cannot tell a peer romp
# message from a human prompt (both are `user` messages). Everything else the old
# typed/queued/absorbed/decision/postal enum encoded is derived from position
# (opener vs mid-turn) and content, not stored here.
def author_of(blocks, prompt_source, postal_index, sdk_human=False):
    """human | romp | sdk | system | {"peer": <rompUuid|None>} | None.

    Order matters: the postal marker wins over promptSource (a delivered message can
    arrive with any promptSource). A tool_result-only user atom has no author.

    sdk_human: this session is SDK-backed, so its HUMAN input arrives over the programmatic
    stream-json channel as promptSource "sdk" (the human typed it in the composer). romp's own
    injections still carry the romp-injected marker and peers the postal marker (both handled
    above), so an UNMARKED "sdk" prompt here is the human → render it as the blue human bubble.
    Off (the default) elsewhere, where "sdk" means a genuine programmatic/autonomous injection."""
    text = _text_of(blocks)
    if text:
        if SYSTEM_WRAPPER_RE.match(text):         # a harness <task-notification> / <system-reminder>, not the user
            return "system"                       # → author 'system' so _is_opener folds it in, never a goal
        if TEAMMATE_MSG_RE.match(text):           # Claude Code's native agent-to-agent delivery, not the user typing
            return "teammate"                     # → its own collapsed chat card; a non-opener (like 'system'), so
            #   high-frequency coordination pings never pin a junk goal. Checked before the postal marker: the
            #   OUTER native wrapper wins even if a forwarded body happened to carry a romp-msg-id.
        mids = POSTAL_RE.findall(text)
        if mids:
            peer = None
            for mid in mids:
                peer = postal_index.get(mid)
                if peer:
                    break
            return {"peer": peer}
        if ROMP_INJECT_RE.search(text):           # romp pasted this into the pane (a feed nudge) → system, not human
            return "romp"
    if prompt_source == "sdk":
        return "human" if sdk_human else "sdk"
    if prompt_source == "system":
        return "system"
    if prompt_source in ("typed", "queued"):
        return "human"
    # promptSource absent: a genuine prompt with no SDK/system/postal signal is presumed
    # human (a typed prompt the harness recorded without the field — ~10% on disk). A
    # tool_result-only line (no text) gets no author.
    if _is_real_prompt(blocks):
        return "human"
    return None


def parse_teammate_message(text):
    """Split a native Claude Code teammate-message delivery (see TEAMMATE_MSG_RE) into per-sender blocks
    for the chat to render its own way: a list of {"id", "summary", "body"}. `color` is DELIBERATELY
    dropped — these get a neutral treatment, NOT the per-peer color chrome of a romp postal card, so the
    two are tellable apart (the user 2026-07-05). The fixed "permission laundering" boilerplate and the
    <prompt> wrapper fall away naturally (only the <teammate-message> block contents are kept). Returns []
    when there are no blocks (a delivery with no parseable block → caller shows the raw text)."""
    out = []
    for attrs, body in TEAMMATE_BLOCK_RE.findall(text or ""):
        a = dict(re.findall(r'(\w+)="([^"]*)"', attrs))
        out.append({"id": (a.get("teammate_id") or "").strip(),
                    "summary": (a.get("summary") or "").strip(),
                    "body": body.strip()})
    return out


# ═════════════════════════ FILE ADAPTER: graph recovery, quarantined ═════════════════════════
class FileAdapter:
    """Rebuilds the active linear message sequence from the append-only on-disk graph.

    Reads every candidate transcript once into a uuid index, then does a DIRECTED
    backward walk from the leaf via parentUuid (crossing files on resume), so the
    active path is exactly the leaf->root ancestors. Rewound branches are non-
    ancestors and drop out for free; `/clear` leaves no parent link so the walk
    stops there and pre-clear history drops out naturally."""

    def __init__(self, candidate_files, leaf_path, leaf_override=None):
        self.by_uuid = {}        # uuid -> record
        self.fsid_of = {}        # uuid -> transcript file stem (provenance / click-to-open)
        self.seq_of = {}         # uuid -> global read order (tie-break for equal timestamps)
        self.parent_of = {}      # uuid -> parentUuid (or logicalParentUuid, for the compaction stitch)
        self.qatts = []          # queued_command attachment records IN FILE ORDER — the CLI's own splice
                                 #   witnesses: {uuid, ts (the ENQUEUE timestamp the record carries),
                                 #   text (full prompt, markers intact), seq}
        self.leaf_uuid = None
        leaf_stem = Path(leaf_path).stem
        seq = 0
        # read the leaf last so its trailing uuid wins as the walk anchor even if a
        # sibling file happens to sort after it
        files = [f for f in candidate_files if Path(f).stem != leaf_stem] + [Path(leaf_path)]
        for fp in files:
            fsid = Path(fp).stem
            is_leaf = (fsid == leaf_stem)
            for r in _read_jsonl_incremental(fp):   # append-incremental: a streaming transcript costs only its delta
                seq += 1
                t = r.get("type")
                u = r.get("uuid")
                if u:
                    self.by_uuid[u] = r
                    self.fsid_of[u] = fsid
                    self.seq_of[u] = seq
                    # parentUuid normally; compact_boundary carries parentUuid:null +
                    # logicalParentUuid:<pre-compaction leaf> — follow that so the active
                    # path survives compaction instead of orphaning every pre-compaction turn.
                    self.parent_of[u] = r.get("parentUuid") or r.get("logicalParentUuid")
                    if is_leaf:
                        self.leaf_uuid = u
                if t == "attachment":
                    a = r.get("attachment") or {}
                    if a.get("type") == "queued_command" and a.get("prompt"):
                        # the prompt can be a plain string OR a content-block LIST (the SDK injection
                        # path) — extract the TEXT either way; str() of a list keyed the Python repr,
                        # which no enqueue content ever matches (the user 2026-07-06)
                        ptext = a["prompt"] if isinstance(a["prompt"], str) else _text_of(a["prompt"])
                        self.qatts.append({"uuid": u, "ts": parse_z(r.get("timestamp")),
                                           "text": ptext, "seq": seq})
        # A PENDING bare rollback (chat delete): the kernel passes the cut point as leaf_override so
        # the walk starts there and the not-yet-abandoned tail drops exactly as it will once the CLI's
        # --resume-session-at branch takes. Applied only when the uuid is really in this graph — a
        # stale override (wrong file, raced clear) falls back to the true file leaf, never an empty parse.
        if leaf_override and leaf_override in self.by_uuid:
            self.leaf_uuid = leaf_override
        self._repair_compaction_stitches()

    def _repair_compaction_stitches(self):
        """Claude Code sometimes writes a compact_boundary whose logicalParentUuid points
        at a message that exists in compactMetadata.allUuids but was NEVER written as its
        own transcript line (3/69 compactions in the live corpus). Followed blindly, that
        dangling stitch orphans ALL pre-compaction history. The real in-file pre-compaction
        leaf is in compactMetadata.preservedSegment (tail/anchor/head), so when the stitch
        target is missing, re-point parent_of there — reconnecting the pre-compaction tree.
        (Verified: rescues 100% of the corpus's broken stitches.)"""
        for u, r in self.by_uuid.items():
            if r.get("type") != "system" or r.get("subtype") != "compact_boundary":
                continue
            target = self.parent_of.get(u)
            if target is None or target in self.by_uuid:
                continue                          # no stitch, or stitch is intact
            seg = (r.get("compactMetadata") or {}).get("preservedSegment") or {}
            for k in ("tailUuid", "anchorUuid", "headUuid"):   # tail = the pre-compaction leaf
                cand = seg.get(k)
                if cand and cand in self.by_uuid:
                    self.parent_of[u] = cand
                    break

    def active_path(self):
        """The set of uuids on the leaf->root chain (directed walk, O(chain length))."""
        active, u, guard = set(), self.leaf_uuid, 0
        while u is not None and u not in active and guard < 500000:
            active.add(u)
            u = self.parent_of.get(u)
            guard += 1
        return active

    def kept_uuids(self, active):
        """The active leaf-ancestors PLUS any line on a BROKEN chain (its parentUuid points
        at a uuid that exists in NO transcript — corruption / a partial write). The two
        kinds of off-path line we DO drop are both intentional: a rewind fork (its chain
        rejoins the active spine) and a clear branch (its chain reaches a clean null root
        the leaf does not share — `/clear` breaks the parent link, spec-mandated drop). A
        dangling chain is the one thing we cannot prove dead, and silently dropping a real
        ask is this repo's one fatal error, so we keep it. (Verified 0 dangling cases
        across the live corpus: this is a safety net, not a behavior change.)"""
        verdict = {}
        def classify(start):
            path, u = [], start
            while True:
                if u in active:
                    res = "rewind"; break          # chain rejoins the active spine -> rewound fork
                if u in verdict:
                    res = verdict[u]; break
                if u not in self.by_uuid:
                    res = "broken"; break           # dangling target uuid (corruption)
                if u in path:
                    res = "broken"; break           # cycle -> unprovable, keep
                path.append(u)
                p = self.parent_of.get(u)
                if p is None:
                    res = "clear"; break            # clean null root, not the leaf's -> pre-clear
                u = p
            for x in path:
                verdict[x] = res
            return res
        kept = set(active)
        for u in self.by_uuid:
            if u not in active and classify(u) == "broken":
                kept.add(u)
        return kept

    def _absorbed_atom(self, full, t, seq, auid, rompuuid, postal_index):
        """One synthesized user atom for a mid-turn splice. The atom carries the FULL text — any
        whitespace-collapsed form is for MATCHING only (the user 2026-07-08: collapsing ate the blank
        line between a follow-up's quoted context and the typed reply, so markdown folded the reply
        INTO the blockquote; and the kernel's optimistic echo could never text-prune against the
        collapsed copy, so the message rendered TWICE)."""
        blocks = [{"type": "text", "text": full}]
        atom = {
            "type": "user", "uuid": auid, "session_id": rompuuid,
            "t": t, "fsid": self.fsid_of.get(auid),
            "parentUuid": (self.by_uuid.get(auid) or {}).get("parentUuid"),
            "message": {"role": "user", "content": blocks},
            "author": author_of(blocks, None, postal_index, getattr(self, "sdk_human", False)),
            "_seq": seq,
        }
        if ROMP_AUTO_RE.search(full):   # an AUTO-nudge → flag it, mirroring the native user-record path
            atom["rompAuto"] = True
        return atom

    def _absorbed(self, kept, rompuuid, postal_index):
        """Mid-turn prompts spliced into a running turn. The witness is the queued_command
        ATTACHMENT record: the CLI writes one per splice, uuid-bearing and parent-chained,
        carrying the FULL prompt text and stamped with the ENQUEUE timestamp — and writes
        NONE for a dequeued prompt (that resurfaces as a native user line), a still-pending
        one, or a popAll (a recall: the queue is cleared, nothing spliced). So each
        attachment becomes one user atom, at its own timestamp: the moment the user sent it.

        The queue-operation ledger is deliberately NOT read at all: its dequeue/remove
        records are anonymous, and a CLI killed with items queued never writes their
        resolutions — one missing resolution shifted EVERY later FIFO pairing, so a message
        typed at 16:56 was stamped with another message's resolution time and rendered as
        the NEWEST message in the chat, hours out of place, while never-delivered
        task-notifications rendered as absorbed prompts at junk times (the user 2026-07-10,
        the nimbus session). The witness is universal: 0 of the live corpus's 104
        remove-bearing transcripts lack attachments, so dropping the ledger loses nothing.

        DEPLOY RULE: changing WHICH atoms this class emits from an existing transcript (here
        or in atoms()) changes placement identity just like an id drift — previously-invisible
        atoms become fresh plannable segments and dormant sessions replay them as new goals
        (2026-07-10). Bump jd.PLACEMENTS_V in the same commit; tests/test_placements_canary.py
        pins both dimensions."""
        atoms, emitted = [], set()
        for q in self.qatts:
            if q["ts"] is None:
                continue   # unparseable timestamp — nowhere truthful to place it
            key = (q["ts"], " ".join(q["text"].split()))
            if key in emitted:
                continue   # identical (ts, text) copies are the SAME splice written more than
                           # once (compaction/resume replays the record verbatim — x2 is common
                           # in the live corpus, one retry storm hit x24)
            if q["uuid"] is not None and q["uuid"] not in kept:
                continue   # this copy sits on a rewound branch — a kept twin may still emit
            emitted.add(key)
            atoms.append(self._absorbed_atom(q["text"], q["ts"], q["seq"], q["uuid"],
                                             rompuuid, postal_index))
        return atoms

    def atoms(self, rompuuid, postal_index):
        """Every emitted atom on the active path (plus broken-chain survivors), plus
        synthesized absorbed atoms. (Idle atoms are added separately from the state log.)"""
        active = self.active_path()
        kept = self.kept_uuids(active)
        # Post-compaction REPLAY dedup (the user 2026-06-22): a compact_boundary restores the recent message
        # tail VERBATIM with NEW uuids/timestamps. A replayed user prompt is the same text as an EARLIER one,
        # after a boundary — NOT new work; left in, it gets a fresh seg-id and the judges re-mint an
        # already-done (even CLEARED) goal. Identify replays in CHRONOLOGICAL order (the main emit loop below
        # is leaf-first) so we keep the ORIGINAL and drop the later replay — then placements dedup still holds.
        replay_uuids, _seen_text, _compacted = set(), set(), False
        summaries, last_boundary = {}, None   # boundary_uuid -> the compaction SUMMARY text (the isCompactSummary
        #   user record that FOLLOWS each compact_boundary — Claude's "what it kept"; captured here to attach to
        #   the boundary atom, so the chat can show it in a collapsible box, the user 2026-07-07).
        for u in sorted(kept, key=lambda x: (parse_z((self.by_uuid.get(x) or {}).get("timestamp")) or 0,
                                             self.seq_of.get(x, 0))):
            r = self.by_uuid.get(u)
            if not r:
                continue
            if r.get("type") == "system" and r.get("subtype") == "compact_boundary":
                _compacted = True
                last_boundary = u
            elif r.get("type") == "user" and r.get("isCompactSummary") is True:
                stext = _text_of(_content(r.get("message")))
                if last_boundary and stext:            # attach to the boundary just seen; cap for transport
                    summaries[last_boundary] = stext[:SUMMARY_CAP] + (
                        "\n\n…(summary truncated)" if len(stext) > SUMMARY_CAP else "")
            elif r.get("type") == "user" and not r.get("isMeta"):
                txt = _text_of(_content(r.get("message")))
                if txt:
                    replay_uuids.add(u) if (_compacted and txt in _seen_text) else _seen_text.add(txt)
        # Skill tool_use block ids: the anchor for the NEW skill-instructions shape (2026-07-10). Newer
        # CLIs inject the payload as an isMeta user record whose sourceToolUseID names the invoking Skill
        # tool_use — the text no longer starts with the "Base directory for this skill:" preamble
        # SKILL_CONTENT_RE keys on, so the designed link is the id, not a prefix.
        skill_tool_ids = set()
        for u in kept:
            r = self.by_uuid.get(u) or {}
            if r.get("type") == "assistant":
                for b in _content(r.get("message")) or []:
                    if isinstance(b, dict) and b.get("type") == "tool_use" and \
                            b.get("name") == "Skill" and b.get("id"):
                        skill_tool_ids.add(b["id"])
        # Bare invocation TWINS (CLI 2.1.215+, the user 2026-07-20): a typed slash command lands TWICE —
        # a raw-text user record (the submitted prompt verbatim, carrying promptId) AND the
        # <command-name> wrapper (same promptId). The wrapper becomes the tracked command atom below;
        # the raw twin carries no wrapper, no isMeta, no isCompactSummary, so it would fall through as
        # a genuine HUMAN atom — and the planner minted a feed card from a /compact ("Compact
        # conversation context", the rescue thread). Collect wrapper promptIds so the twin drops as the
        # invocation echo it is.
        cmd_prompt_names = {}
        for u in kept:
            r = self.by_uuid.get(u) or {}
            if r.get("type") == "user" and r.get("promptId"):
                m = COMMAND_NAME_RE.match(_text_of(_content(r.get("message"))) or "")
                if m:
                    name = m.group(1).strip() or "/?"
                    cmd_prompt_names.setdefault(r["promptId"], set()).add(
                        name if name.startswith("/") else "/" + name)
        out = []
        for u in kept:
            r = self.by_uuid.get(u)
            if not r:
                continue
            t = r.get("type")
            ts = parse_z(r.get("timestamp"))
            fsid = self.fsid_of.get(u)
            seq = self.seq_of.get(u, 0)
            if t == "assistant":
                a = {"type": "assistant", "uuid": u, "session_id": rompuuid,
                     "t": ts, "fsid": fsid, "parentUuid": r.get("parentUuid"),
                     "message": _norm_message(r.get("message")), "_seq": seq}
                if r.get("isApiErrorMessage"):
                    a["isApiError"] = True   # a FAILURE record — Claude Code writes the error as an
                                             # assistant text block, so it carries text but is NOT a
                                             # reply; deep-link anchors must skip it (kernel _seg_anchors)
                out.append(a)
            elif t == "user":
                blocks = _content(r.get("message"))
                btext = _text_of(blocks) if blocks else ""
                # SLASH-COMMAND TURN (the user 2026-06-29): a "/usage"-style command is no longer dropped — its
                # INVOCATION becomes a `command`-flagged user atom (an opener → a tracked, working turn that
                # shows in the chat + timeline) and its OUTPUT a synthetic assistant atom (so the turn has a
                # reply and ENDS naturally). The `command` flag makes the planner/judge skip it (never a goal /
                # feed card — see _seg_command). This runs BEFORE the isMeta skip because some Claude versions
                # mark these records isMeta. The other wrappers (message/args/contents/caveat) stay skipped.
                mcmd = COMMAND_NAME_RE.match(btext)
                if mcmd and u not in replay_uuids:
                    name = mcmd.group(1).strip() or "/?"
                    if not name.startswith("/"):
                        name = "/" + name
                    margs = COMMAND_ARGS_RE.search(btext)
                    args = (margs.group(1).strip() if margs else "")
                    disp = name + ((" " + args) if args else "")
                    out.append({"type": "user", "uuid": u, "session_id": rompuuid, "t": ts,
                                "fsid": fsid, "parentUuid": r.get("parentUuid"), "_seq": seq,
                                "author": "human", "command": name,
                                "message": {"role": "user", "content": [{"type": "text", "text": disp}]}})
                    continue
                mout = LOCAL_STDOUT_RE.match(btext)
                if mout and u not in replay_uuids:
                    out.append({"type": "assistant", "uuid": u, "session_id": rompuuid, "t": ts,
                                "fsid": fsid, "parentUuid": r.get("parentUuid"), "_seq": seq, "command": True,
                                "message": {"role": "assistant",
                                            "content": [{"type": "text", "text": strip_ansi(mout.group(1)).strip()}],
                                            "stop_reason": "end_turn"}})
                    continue
                has_tool_result = any(isinstance(b, dict) and b.get("type") == "tool_result"
                                      for b in (blocks or []))
                twins = cmd_prompt_names.get(r.get("promptId") or "")
                if twins and not has_tool_result and any(
                        btext.strip() == n or btext.strip().startswith(n + " ") for n in twins):
                    continue   # the raw-text TWIN of a slash invocation (see the pre-pass above) — the
                               # wrapper is the one tracked command atom; this is its echo, not a message
                if btext and not has_tool_result and u not in replay_uuids and \
                        (SKILL_CONTENT_RE.match(btext) or r.get("sourceToolUseID") in skill_tool_ids):
                    # a Skill invocation's INSTRUCTIONS payload — kept, but flagged and content-EMPTY:
                    # assistant-flavored with no stop so it can neither open nor close the running turn,
                    # and the markdown rides skillMd where generic text readers never look. BEFORE the
                    # isMeta skip (the CLI marks the record isMeta), like the command paths above (the
                    # user 2026-07-08). TWO shapes: the legacy "Base directory for this skill:" preamble
                    # (SKILL_CONTENT_RE) and the newer sourceToolUseID link to the invoking Skill
                    # tool_use (the user 2026-07-10 — a 151KB skill md rendered as a giant note box
                    # because the prefix missed, the isMeta skip ate the record, and the un-superseded
                    # LIVE atom stuck around forever). The tool_result guard keeps the Skill tool's own
                    # "Launching skill: X" result out of this branch if it ever carries the same link.
                    out.append({"type": "assistant", "uuid": u, "session_id": rompuuid, "t": ts,
                                "fsid": fsid, "parentUuid": r.get("parentUuid"), "_seq": seq,
                                "skillMd": btext[:SKILL_MD_CAP] + ("\n\n…(skill content truncated)"
                                                                   if len(btext) > SKILL_MD_CAP else ""),
                                "message": {"role": "assistant", "content": [], "stop_reason": None}})
                    continue
                if r.get("isMeta") is True:
                    continue   # `<command-…>` echoes / caveats — harness noise, not a message
                if r.get("isCompactSummary") is True:
                    continue   # the compaction SUMMARY payload — kept in the graph (above) but not an atom;
                               # the compaction itself is the system:compact_boundary atom below
                if u in replay_uuids:
                    continue   # a post-compaction REPLAY of restored context (see the pre-pass above) — not new
                               # work; dropping it keeps the planner's seg-id dedup intact, so no goal re-mints
                if not blocks:
                    continue
                if CMD_WRAP_RE.match(btext):
                    continue   # the remaining slash-command wrappers (message/args/contents/caveat) — noise
                ps = r.get("promptSource")
                atom = {"type": "user", "uuid": u, "session_id": rompuuid, "t": ts,
                        "fsid": fsid, "parentUuid": r.get("parentUuid"),
                        "message": _norm_message(r.get("message")), "_seq": seq}
                if ps:
                    atom["promptSource"] = ps
                author = author_of(blocks, ps, postal_index, getattr(self, "sdk_human", False))
                if author is not None:
                    atom["author"] = author
                if ROMP_AUTO_RE.search(_text_of(blocks)):   # an AUTO-nudge → flag it (vs a button/typed follow-up)
                    atom["rompAuto"] = True
                out.append(atom)
            elif t == "system" and r.get("subtype") == "compact_boundary":
                cm = r.get("compactMetadata") or r.get("compact_metadata") or {}
                out.append({"type": "system", "subtype": "compact_boundary", "uuid": u,
                            "session_id": rompuuid, "t": ts, "fsid": fsid,
                            "parentUuid": self.parent_of.get(u),   # the repaired stitch (see _repair_compaction_stitches)
                            "compact_metadata": {"trigger": cm.get("trigger"),
                                                 "pre_tokens": cm.get("preTokens") or cm.get("pre_tokens"),
                                                 "post_tokens": cm.get("postTokens") or cm.get("post_tokens")},
                            "summary": summaries.get(u),   # the compaction SUMMARY captured in the pre-pass (or None)
                            "_seq": seq})
            # other system subtypes (turn_duration, stop_hook_summary, local_command,
            # away_summary) are harness bookkeeping, not conversational messages -> skipped.
        out += self._absorbed(kept, rompuuid, postal_index)
        return out


# A session is NOT working once it has STOPPED: the tmux hook writes state:"waiting" on the Stop event (the
# agent handed the floor back) and state:"idle" on the idle-prompt later. Both terminate the turn — keying
# only on "idle" left a finished session whose last assistant message wasn't a clean end_turn (e.g. it ended
# on a tool_use) stuck reading "working" from Stop until the idle-prompt eventually landed (the user 2026-06-25,
# "reverting working when stuff isn't working"). Event-based, not a grace timer.
_IDLE_STATES = ("idle", "waiting")


def synthesize_idle(states, atoms, now):
    """Idle atoms from real idle/stopped transitions in states/<sid>.jsonl — NOT a 15-minute silence
    heuristic. An idle span runs from an `state` in _IDLE_STATES (the Stop "waiting" or the idle-prompt
    "idle") to the next state record (or to `now` if it is the last). Only spans overlapping the session's
    atom timespan are kept, so unrelated history doesn't leak in."""
    rows = sorted([r for r in states if isinstance(r, dict) and r.get("t") is not None],
                  key=lambda r: r["t"])
    if not rows or not atoms:
        return []
    lo = min(a["t"] for a in atoms)
    hi = max(a.get("end", a["t"]) for a in atoms)
    out = []
    for i, r in enumerate(rows):
        if r.get("state") not in _IDLE_STATES:
            continue
        start = r["t"]
        end = rows[i + 1]["t"] if i + 1 < len(rows) else (now if now is not None else hi)
        if end <= start:
            continue
        if end < lo or start > max(hi, now or hi):
            continue   # span entirely outside the session's activity window
        out.append({"type": "idle", "uuid": None, "session_id": atoms[0]["session_id"],
                    "t": start, "end": end, "_seq": 10 ** 12 + start})
    return out


# ═════════════════════════ SUBSTRATE-NEUTRAL: turns over atoms ═════════════════════════
def is_interrupt_record(atom):
    """The CLI's own stop record — a user atom reading '[Request interrupted by user]' (Esc) or
    '[Request interrupted by user for tool use]' (a permission prompt dismissed). It is the interrupt
    EVENT itself, written by the CLI whether the stop came from romp's Stop button or a raw Esc in the
    pane — so it must END its turn (the user 2026-07-05: without this, the dangling user atom read as
    an OPEN turn, so the chip latched 'Interrupting…' for the full 120s cap and _ops_gate parked a
    /model pick against a session that was actually idle). Public: the kernel's auto-nudge gate keys
    on the same event."""
    if atom.get("type") != "user":
        return False
    return _text_of(_content(atom.get("message"))).startswith("[Request interrupted by user")


def _is_opener(atom):
    """A genuine new prompt opens a turn: author human / sdk / peer / romp. `system`
    (`<task-notification>`) and tool_result-only atoms fold in, never open. A romp follow-up
    (a feed NUDGE / auto-nudge carrying the romp-injected marker, author 'romp') IS a fresh
    prompt to the agent — it MUST open its own turn so the planner reads the romp-goal-id off
    the trigger, reopens that goal, and files the reply under it. Without this it folds into the
    prior (often already-completed) turn, so the judges never see the follow-up and the goal
    never reopens (the user 2026-06-21)."""
    if atom["type"] != "user":
        return False
    a = atom.get("author")
    return a in ("human", "sdk", "romp") or isinstance(a, dict)


def _turn_id(rompuuid, turn):
    """`${rompUuid}:${t}:${hash}` — anchor-keyed, fork-stable (the trigger's text, or the
    first atom's text for an autonomous turn)."""
    atoms = turn["atoms"]
    text = ""
    trig = turn["trigger"]
    if trig:
        a = next((x for x in atoms if x.get("uuid") == trig["uuid"]), None)
        if a:
            text = _text_of(_content(a.get("message")))
    elif atoms:
        text = _text_of(_content(atoms[0].get("message")))
    h = hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:8]
    return "%s:%d:%s" % (rompuuid, turn["t"], h)


def segment_turns(atoms, rompuuid):
    """Group atoms into `end_turn`-bounded turns. A turn opens at an opener atom (or at
    the first non-opener if work begins without one) and runs until the next opener
    that arrives AFTER the turn hit `end_turn`. A new prompt arriving while the turn is
    still open (last assistant stop_reason != end_turn) is a mid-turn input (absorb),
    kept inside the turn — that is how one turn holds several inputs."""
    atoms = sorted(atoms, key=lambda a: (a["t"], a.get("_seq", 0)))
    turns = []
    cur = None
    ended = False     # has the current turn hit end_turn since its last opener?
    for atom in atoms:
        if atom["type"] == "system" and atom.get("subtype") == "compact_boundary":
            # Compaction always opens a FRESH turn (the user 2026-07-13): a non-opener would absorb into
            # the current turn, and _finalize_turn's end = max(atom ends) then stretched that turn's bar
            # to the boundary's timestamp — the timeline drew a phantom work period spanning the whole
            # idle gap "leading up to the moment of compaction", growing live while the compact ran. The
            # boundary anchors its own turn instead. ended=True so a GENUINE post-compact prompt opens
            # its own turn (it's a real ask — the planner needs it as a trigger); the CLI's autonomous
            # continuation (assistant atoms, non-openers) still files under the boundary turn, so its
            # bar starts AT the compaction, never before.
            cur = {"trigger": None, "atoms": [atom]}
            turns.append(cur)
            ended = True
            continue
        if _is_opener(atom):
            if cur is None or ended:
                cur = {"trigger": {"uuid": atom.get("uuid")}, "atoms": [atom]}
                turns.append(cur)
                ended = False
            else:
                cur["atoms"].append(atom)   # mid-turn input (absorbed)
        else:
            if cur is None:
                cur = {"trigger": None, "atoms": [atom]}   # autonomous / continuation
                turns.append(cur)
                ended = False
            else:
                cur["atoms"].append(atom)
        if atom["type"] == "assistant":
            sr = (atom.get("message") or {}).get("stop_reason")
            ended = sr in END_STOPS
        if atom["type"] == "user" and atom.get("command"):
            ended = True   # a slash-command invocation is self-contained → ends its turn so the NEXT prompt opens fresh
        if atom["type"] == "user" and is_interrupt_record(atom):
            ended = True   # the CLI's stop record — the interrupted turn is OVER; the next prompt opens fresh
    for turn in turns:
        _finalize_turn(turn, rompuuid)
    turns.sort(key=lambda t: t["t"])
    return turns


def _finalize_turn(turn, rompuuid):
    atoms = turn["atoms"]
    turn["t"] = atoms[0]["t"]
    turn["end"] = max(a.get("end", a["t"]) for a in atoms)
    # ended (FILE substrate): inferred from the turn's last assistant stop_reason, since
    # the transcript carries no `result` line. Interrupted / still-streaming -> False.
    last_sr = None
    for a in atoms:
        if a["type"] == "assistant":
            last_sr = (a.get("message") or {}).get("stop_reason")
    turn["ended"] = last_sr in END_STOPS
    # a slash-COMMAND turn with no reply/output atom is SELF-CONTAINED → ended (the user 2026-06-29). Without
    # this, a command that produced no output (a hung /usage, a control command) leaves the turn open forever,
    # so the session reads as "working" indefinitely and a stuck provisional card never resolves (the JLD case).
    # A command WITH output / model work ends naturally on that assistant atom's stop_reason above; this only
    # catches the bare-invocation case. (Working-during-execution is the live backend state's job, not this.)
    if not turn["ended"] and atoms[0].get("command") and not any(a["type"] == "assistant" for a in atoms):
        turn["ended"] = True
    # a compaction turn with no assistant work yet is likewise SELF-CONTAINED (the user 2026-07-13): the
    # boundary is a completed event, not in-flight work — left open it reads as a phantom open bar/WORKING
    # until the CLI's continuation lands (whose stop_reason then owns `ended` via the rule above).
    if (not turn["ended"] and atoms[0].get("type") == "system" and atoms[0].get("subtype") == "compact_boundary"
            and not any(a["type"] == "assistant" for a in atoms)):
        turn["ended"] = True
    # an INTERRUPT record at the turn's tail ends it (the user 2026-07-05): the CLI's stop record is the
    # interrupt event — the aborted assistant work before it never wrote an end_turn, so without this the
    # turn read open forever (stuck 'Interrupting…' chip, /model picks parked against an idle session).
    # Tail = last atom ignoring idle spans (a states overlay lands one after the record) and command
    # confirmations (a completed exchange, same skip _session_working does). An interrupt record MID-turn
    # (later work follows) means the turn resumed — that later work decides `ended`, so only the tail counts.
    if not turn["ended"]:
        i = len(atoms) - 1
        while i >= 0 and (atoms[i].get("command") or atoms[i]["type"] == "idle"):
            i -= 1
        if i >= 0 and is_interrupt_record(atoms[i]):
            turn["ended"] = True
    turn["id"] = _turn_id(rompuuid, turn)


# ── segment derivation: a turn split at its input atoms (timeline grain). DERIVED, not stored.
def _is_segment_input(atom):
    """A segment boundary is a genuine new input (opener or absorbed human/peer prompt).
    tool_result and `system` (task-notification) atoms do not start a segment; a
    higher layer MAY additionally split at a decision atom — the bottom layer does not."""
    return _is_opener(atom)


def _segment_id(rompuuid, seg_t, atoms, trigger_uuid):
    """`${rompUuid}:${seg.t}:${hash}` — parallel to the turn id; the summarizer layer's
    dedup key for a segment. Hash of the trigger atom's text (or the first atom's text
    for a triggerless/autonomous segment).

    A TEXT-LESS segment (a settle-seam tail, a tool-only continuation) has no content to hash —
    sha1("") is the SAME for every one, so a content key would alias them ALL under the
    timestamp-invariant _seg_key: a fresh working seam inherited a long-done seam's placement, and a
    session working past a completed goal showed a blank board (the user 2026-07-22). Its identity is
    instead its ANCHOR ATOM's uuid — unique per atom, present in the transcript, and STABLE across the
    judge parse (which carries the states/idle overlay) and the kernel render parse (which omits it),
    since the anchor is the segment's opener, a real atom the overlay never displaces (verified).
    Text-BEARING segments keep the content hash: it is drift-invariant across the SDK optimistic echo
    (send time) and the real transcript atom (process time), which share text but NOT uuid — so an
    atom-uuid key there would MISS its own echo. Hash the content, or — only when there is none — the
    anchor atom's identity."""
    text = ""
    anchor = None
    if trigger_uuid:
        a = next((x for x in atoms if x.get("uuid") == trigger_uuid), None)
        if a:
            text = _text_of(_content(a.get("message")))
            anchor = a
    if not text and atoms:
        anchor = anchor or atoms[0]
        text = _text_of(_content(atoms[0].get("message")))
    basis = text or (anchor or {}).get("uuid") \
        or next((a.get("uuid") for a in atoms if a.get("uuid")), "")   # first uuid-bearing atom if the anchor has none
    h = hashlib.sha1(basis.encode("utf-8", "replace")).hexdigest()[:8]
    return "%s:%d:%s" % (rompuuid, seg_t, h)


def segments(turn):
    """The per-input spans of a turn (what the timeline draws as bars). A segment runs
    from one input to the next (or to the turn end). Each carries a stable `id` for the
    summarizer layer. Pure function over a turn."""
    atoms = turn["atoms"]
    rompuuid = atoms[0]["session_id"] if atoms else ""
    starts = [i for i, a in enumerate(atoms) if _is_segment_input(a)]
    if not starts:
        segs = [{"t": turn["t"], "end": turn["end"],
                 "trigger": turn["trigger"]["uuid"] if turn["trigger"] else None,
                 "atoms": list(atoms)}]
    else:
        bounds = starts + [len(atoms)]
        segs = []
        for k, i0 in enumerate(starts):
            i1 = bounds[k + 1]
            segs.append({"t": atoms[i0]["t"],
                         "end": atoms[i1]["t"] if i1 < len(atoms) else turn["end"],
                         "trigger": atoms[i0].get("uuid"),
                         "atoms": atoms[i0:i1]})
        if starts[0] > 0:   # leading atoms before the first input attach to the first segment
            lead = atoms[:starts[0]]
            segs[0]["atoms"] = lead + segs[0]["atoms"]
            segs[0]["t"] = turn["t"]
    for seg in segs:        # id last: after the leading-attach may have moved seg[0]'s t/atoms
        seg["id"] = _segment_id(rompuuid, seg["t"], seg["atoms"], seg["trigger"])
    return segs


# ── settle-time SEAM split (plans/segment-regrowth.md): when a goal settles while its segment is
# still growing, the post-settle tail becomes its OWN segment so the planner can see it. The split
# primitive lives here (pure over a segment); WHICH segments split — ownership via the goal store's
# placements — is the judge's call (jd.apply_seams), keeping this layer store-free.
SEAM_PROSE_FLOOR = 80                     # tail "real work" = a tool_use atom or assistant prose past this


def _seam_real_work(atoms):
    """True if `atoms` hold REAL work — any assistant tool_use, or assistant prose ≥ SEAM_PROSE_FLOOR
    chars (above connective stubs). The event condition that gates a seam split: post-settle wrap-up
    chatter never mints a noise segment."""
    for a in atoms:
        if a.get("type") != "assistant":
            continue
        blocks = _content(a.get("message"))
        if not isinstance(blocks, list):
            continue
        for b in blocks:
            if isinstance(b, dict) and b.get("type") == "tool_use":
                return True
        if len(_text_of(blocks)) >= SEAM_PROSE_FLOOR:
            return True
    return False


def split_segment(seg, t):
    """(head, tail) or None — split `seg` after the last atom at/before wall-clock `t` (a goal's settle
    moment, plans/segment-regrowth.md). None unless BOTH sides are non-empty and the tail holds real
    work (_seam_real_work). The head keeps the original id (its t + trigger text are unchanged, so an
    existing placement still matches); the tail is trigger-less, `seam`-flagged, with a STABLE id from
    its own first atom — every pass re-derives the same split, so placement idempotency holds."""
    atoms = seg.get("atoms") or []
    head_a = [a for a in atoms if a.get("t", 0) <= t]
    tail_a = [a for a in atoms if a.get("t", 0) > t]
    if not head_a or not tail_a or not _seam_real_work(tail_a):
        return None
    rompuuid = atoms[0].get("session_id", "")
    head = dict(seg, atoms=head_a, end=tail_a[0]["t"])
    tail = {"t": tail_a[0]["t"], "end": seg["end"], "trigger": None, "atoms": tail_a, "seam": True,
            "id": _segment_id(rompuuid, tail_a[0]["t"], tail_a, None)}
    return head, tail


# ═════════════════════════ assembly ═════════════════════════
def _load_postal_index(postal_log):
    """{msg-id -> sender rompUuid} from timeline/messages.jsonl (`from_id` is the sender's
    anchor sid). Accepts a path or an in-memory list of rows (tests)."""
    idx = {}
    rows = postal_log if isinstance(postal_log, list) else _read_jsonl(postal_log or MESSAGES_LOG)
    for o in rows:
        if not isinstance(o, dict):
            continue
        mid, frm = o.get("id"), o.get("from_id")
        if mid and frm and mid not in idx:
            idx[mid] = frm
    return idx


def _load_states(states):
    if states is None:
        return []
    return list(states) if isinstance(states, list) else list(_read_jsonl(states))


def parse_session(leaf_path, rompuuid=None, name=None, color="#888888", dir=None,
                  candidate_files=None, states=None, postal_log=None, now=None, sdk_human=False,
                  leaf_override=None):
    """Build one session's Session -> Turn -> Atom tree from the on-disk transcript graph.

    leaf_path        the newest (leaf) transcript file; the walk's start pointer.
    rompuuid         stable session identity (binds everything). Real runs resolve it from
                     names/<sid> (the anchor sid); defaults to the leaf file stem for --test.
    candidate_files  the session's transcript files the resume walk may cross into.
                     Defaults to JUST [leaf_path] — a safe single-file parse. Cross-file
                     resume requires the caller to pass the explicit session file set;
                     we deliberately do NOT glob the project dir (that would read every
                     unrelated transcript in it). Session->files resolution is a
                     higher-layer concern, not the parser's.
    states           states/<sid>.jsonl path or rows -> idle atoms.
    postal_log       timeline/messages.jsonl path or rows -> peer rompUuid.
    leaf_override    start the walk at this record instead of the file's last (a PENDING
                     bare rollback — the kernel's pending_cut); ignored if absent from the graph.
    """
    leaf_path = Path(leaf_path)
    if dir is None:
        dir = str(leaf_path.parent)
    if rompuuid is None:
        rompuuid = leaf_path.stem
    if candidate_files is None:
        candidate_files = [str(leaf_path)]
    postal_index = _load_postal_index(postal_log)
    adapter = FileAdapter(candidate_files, leaf_path, leaf_override=leaf_override)
    adapter.sdk_human = sdk_human            # SDK-backed session → unmarked promptSource "sdk" is the human
    atoms = adapter.atoms(rompuuid, postal_index)
    atoms += synthesize_idle(_load_states(states), atoms, now)
    turns = segment_turns(atoms, rompuuid)
    for turn in turns:
        for a in turn["atoms"]:
            a.pop("_seq", None)
        turn_keys = {"id": turn["id"], "trigger": turn["trigger"], "t": turn["t"],
                     "end": turn["end"], "ended": turn["ended"], "atoms": turn["atoms"]}
        turn.clear()
        turn.update(turn_keys)
    return {"rompUuid": rompuuid, "name": name or rompuuid, "dir": dir,
            "color": color, "leafFsid": leaf_path.stem, "turns": turns}


def task_store_plan(fsid):
    """The agent's to-do list read from Claude Code's LIVE task store (<config>/tasks/<fsid>/<N>.json,
    honoring $CLAUDE_CONFIG_DIR) — the AUTHORITATIVE state TaskList/TaskGet read, updated by EVERY
    writer including subagents. The transcript fold (declared_plan below) is a lossy reconstruction:
    it misses a completion whose record fell off the transcript's live chain — an api-error retry
    forks the parent graph and the abandoned branch keeps the TaskUpdate that actually RAN (store
    updated, transcript forgot), leaving a mirror card phantom-open that re-mints itself after every
    clear (the 2026-07-09 g204 loop). Same item shape as declared_plan: [{key, text, activeForm,
    status}], ordered by numeric id. Returns None when the fsid has no store dir — a session that
    never declared a plan there (the caller may fall back to the fold). Raises OSError when the dir
    EXISTS but can't be listed: that is the authoritative source failing, and the caller must surface
    it loudly, never silently fold (repo policy). A single corrupt item file is skipped."""
    if not fsid:
        return None
    d = Path(os.environ.get("CLAUDE_CONFIG_DIR") or str(HOME / ".claude")) / "tasks" / fsid
    if not d.is_dir():
        return None
    items = []
    for n in os.listdir(d):                                # raises OSError → the caller surfaces it
        if not n.endswith(".json"):
            continue
        try:
            t = json.loads((d / n).read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(t, dict):
            continue
        key = str(t.get("id") or n.rsplit(".", 1)[0])
        af = t.get("activeForm")
        items.append({"key": key, "text": str(t.get("subject") or ""),
                      "activeForm": str(af) if af else None,
                      "status": str(t.get("status") or "pending")})
    items.sort(key=lambda t: (0, int(t["key"])) if t["key"].isdigit() else (1, t["key"]))
    return items


def declared_plan(session):
    """The agent's OWN to-do list (Claude Code's Task tool) folded into ordered items
    [{key, text, activeForm, status}] — the FALLBACK behind task_store_plan for a session with no
    live task store, so downstream (the judge's plan-sync) sees a generic 'declared plan' shape
    instead of raw tool calls. Mirrors the kernel's _fold_tasks, with the same blind spots: only the
    MAIN agent's TaskCreate/TaskUpdate calls, and only those on the transcript's live chain.
    `key` is the stable `Task #N` id lifted from TaskCreate's
    result text (a creation-order `cN` fallback if the result is unreadable); `status` rides each
    TaskUpdate. Only TaskCreate/TaskUpdate are folded — plain TodoWrite (no durable ids) is not
    used by romp. Empty list if the session declared no plan."""
    results = {}                                           # tool_use_id → result text (carries 'Task #N')
    for turn in session["turns"]:
        for a in turn["atoms"]:
            if a.get("type") != "user":
                continue
            for b in (a.get("message") or {}).get("content", []) or []:
                if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id"):
                    c = b.get("content")
                    results[b["tool_use_id"]] = c if isinstance(c, str) else json.dumps(c)
    tasks, order = {}, 0
    for turn in session["turns"]:
        for a in turn["atoms"]:
            if a.get("type") != "assistant":
                continue
            for b in (a.get("message") or {}).get("content", []) or []:
                if not isinstance(b, dict) or b.get("type") != "tool_use":
                    continue
                inp = b.get("input") or {}
                if b.get("name") == "TaskCreate":
                    m = re.search(r"Task #(\d+)", results.get(b.get("id"), "") or "")
                    key = m.group(1) if m else "c%d" % order
                    af = inp.get("activeForm")
                    tasks[key] = {"_order": order, "key": key, "text": str(inp.get("subject") or ""),
                                  "activeForm": str(af) if af else None, "status": "pending"}
                    order += 1
                elif b.get("name") == "TaskUpdate":
                    t = tasks.get(str(inp.get("taskId", "")))
                    if t:
                        t["status"] = str(inp.get("status") or t["status"])
    return sorted(tasks.values(), key=lambda t: t["_order"])


# ───────────────────────── CLI ─────────────────────────
def _hh(t):
    return datetime.fromtimestamp(t).strftime("%H:%M:%S") if t else "--:--:--"


def _atom_line(a):
    t = a["type"]
    if t == "idle":
        return "    · idle            %s-%s  (not working)" % (_hh(a["t"]), _hh(a.get("end")))
    if t == "system":
        cm = a.get("compact_metadata") or {}
        return "    · system:%-9s %s  trigger=%s pre_tokens=%s" % (
            a.get("subtype", "?"), _hh(a["t"]), cm.get("trigger"), cm.get("pre_tokens"))
    blocks = _content(a.get("message"))
    kinds = _block_types(blocks)
    if t == "assistant":
        sr = (a.get("message") or {}).get("stop_reason")
        tools = [b.get("name") for b in blocks if isinstance(b, dict) and b.get("type") == "tool_use"]
        extra = ("tools=" + ",".join(tools)) if tools else ""
        return "    · assistant       %s  %s %s (stop=%s)" % (_hh(a["t"]), "+".join(kinds), extra, sr)
    # user
    author = a.get("author")
    auth = (("peer:" + str(author.get("peer"))) if isinstance(author, dict)
            else (author or "-"))
    snippet = _text_of(blocks)[:48].replace("\n", " ")
    if not snippet and _has_tool_result(blocks):
        snippet = "(tool_result)"
    return "    · user/%-11s %s  %s" % (auth, _hh(a["t"]), snippet)


def _dump(session):
    s = session
    print("Session %s  [%s]  leaf=%s" % (s["name"], s["rompUuid"], s["leafFsid"]))
    print("  dir=%s  color=%s  turns=%d" % (s["dir"], s["color"], len(s["turns"])))
    for i, turn in enumerate(s["turns"], 1):
        trig = turn["trigger"]
        tatom = next((a for a in turn["atoms"] if trig and a.get("uuid") == trig["uuid"]), None)
        tlabel = "autonomous"
        if tatom:
            author = tatom.get("author")
            tlabel = (("peer:" + str(author.get("peer"))) if isinstance(author, dict)
                      else (author or "?")) + " " + repr(_text_of(_content(tatom.get("message")))[:40])
        segs = segments(turn)
        print("\n  Turn %d  [%s-%s]  ended=%s  segments=%d  trigger=%s" % (
            i, _hh(turn["t"]), _hh(turn["end"]), turn["ended"], len(segs), tlabel))
        for a in turn["atoms"]:
            print(_atom_line(a))


def main():
    args = sys.argv[1:]
    if len(args) < 2 or args[0] not in ("--test", "--emit"):
        sys.stderr.write("usage: romp-event-model [--test | --emit] <transcript> "
                         "[--rompuuid X] [--states PATH] [--name N]\n")
        sys.exit(2)
    mode, path = args[0], args[1]
    opts = {}
    rest = args[2:]
    for i in range(0, len(rest) - 1, 2):
        opts[rest[i].lstrip("-")] = rest[i + 1]
    states = opts.get("states")
    if states is None:                       # default: states/<leaf-stem>.jsonl if present
        cand = STATES_DIR / (Path(path).stem + ".jsonl")
        states = str(cand) if cand.exists() else None
    session = parse_session(path, rompuuid=opts.get("rompuuid"), name=opts.get("name"),
                            states=states, now=int(time.time()))
    if mode == "--emit":
        sys.stdout.write(json.dumps(session, indent=1, sort_keys=True))
        sys.stdout.write("\n")
    else:
        _dump(session)


if __name__ == "__main__":
    main()
