#!/usr/bin/env python3
"""The judge prompt experiment (plans/judge-prompt-experiments.md): a corpus of transcript endings, arms of judge prompts
run over copies of it with the judge module rebound onto scratch roots, the four measures and a report.

    judge_experiment.py build-corpus --state-root ~/.local/state/romp --claude-root ~/.claude --dest DIR [--per-class N]
    judge_experiment.py run --corpus DIR --run-root DIR --arm NAME[=PROMPTS.json] ... --budget-usd X --claude-bin PATH
    judge_experiment.py label --corpus DIR --run-root DIR --live-state ROOT --claude-bin PATH [--model M]
    judge_experiment.py report --corpus DIR --run-root DIR [--figure PNG]

Every path the experiment writes is under the destination the caller names, and a destination inside a git checkout is
refused: the corpus is the user's own history and stays out of the repository. The corpus builder reads the live state
root and the Claude root as FILES (names, the registry, transcripts, goal stores, override journals) and loads no romp
module against them; each arm runs in a subprocess of its own with the judge module loaded against the arm's scratch
root. Every model call is paid by whoever owns the binary named in `--claude-bin`, which is required, as is a budget on
`run` (`inf` for none): nothing here can tell a real binary from a fake, so nothing runs without both being said.
"""
import argparse
import errno
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BIN = ROOT / "bin"
CLASSES = ("offer", "question", "undone", "finished")
PROMPT_KEYS = ("PLAN_SYS", "CLOSER_SYS", "UNBLOCK_SYS")
JUDGE_MODULE_NAME = "romp_judge_experiment_arm"
OFFER_RE = re.compile(r"\b(i can also|i could also|if you (want|like|prefer)|shall i|want me to|would you like( me)?|"
                      r"let me know if you|happy to|say the word)\b", re.I)
UNDONE_RE = re.compile(r"\b(not (yet )?done|left (undone|for later|open)|to ?do|did not run|didn't run|not run|"
                       r"remains? (to be done|undone|open)|unfinished|still (need|needs) to|haven't)\b|- \[ \]", re.I)
QUESTION_RE = re.compile(r"\?\s*$")
BUDGET_OVERRUN = 1.2          # a run stops once its ledger passes this multiple of its budget
COLUMN_OF = {"blocked": "needs_input", "completed": "completed", "cleared": "cleared"}   # the store-derivable part of the feed's rule
AGREEMENT_GATE_PCT = 90.0     # the labeller's agreement with the user's recorded actions must reach this before its labels count
FAILURE_KINDS = ("parse", "give-up", "pass-crash", "call", "auth", "rate-limited", "fast-refused", "scratch",
                 "unregistered-caller", "history-unreadable", "store-quarantined")   # judge-errors rows that mean the ending was not judged:
#   a rejected reply, a crashed or refused call, the two pause kinds (`auth`, `rate-limited`), the call-level stand-downs (`fast-refused`,
#   `scratch`, `unregistered-caller`). A `timeout` files under `call`, so it is not named. The `*-unreadable` family and the store-fault pair
#   (`history-unreadable` aside) cannot fire on the arm's road (it hands the judges a store it just wrote and read), and are named only so a
#   future road that can reach them counts them.
ID_EPOCH_RE = re.compile(r"^[0-9a-f-]{36}:(\d{9,11})(?::|$)")   # a turn id or segment id carries its epoch second after the fsid


def event_time(ev):
    """A verdict log event's time: `ev_t` (the evidence time) first, `at` (the arrival) second. The events never carry `t`
    (round two of the harness: a filter on `t` kept every event, so a copy carried verdicts from after the cut)."""
    for key in ("ev_t", "at", "t"):
        v = ev.get(key)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return None


def id_epoch(ident):
    """The epoch second inside a turn id or a segment id (`<fsid>:<epoch>:<hash>`, a placement key may carry a phase suffix),
    or None when the id has another shape."""
    m = ID_EPOCH_RE.match(str(ident or ""))
    return float(m.group(1)) if m else None


# ── the corpus ──────────────────────────────────────────────────────────────────────────────────
def classify_ending(text):
    """The heuristic pre-pass over a turn's last NON-COMMAND assistant text (the caller passes it): one of CLASSES. The
    selection, not the truth; an offer outranks a question outranks an undone item, and the rest is finished."""
    t = (text or "").strip()
    if not t:
        return "finished"
    if OFFER_RE.search(t):
        return "offer"
    last = [p for p in re.split(r"\n\s*\n", t) if p.strip()]
    if last and QUESTION_RE.search(last[-1].strip()):
        return "question"
    if UNDONE_RE.search(t):
        return "undone"
    return "finished"


def refuse_inside_repo(dest):
    """A destination inside a git checkout is refused: the corpus never enters a repository."""
    p = Path(dest).resolve()
    for anc in (p, *p.parents):
        if (anc / ".git").exists():
            raise SystemExit("refused: %s lies inside a git checkout (%s); the corpus stays out of every repository" % (dest, anc))


def munge(cwd):
    return re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(cwd))


def _records(path):
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def _text_of(rec):
    m = rec.get("message") or {}
    c = m.get("content")
    if isinstance(c, str):
        return c
    return "\n".join(b.get("text", "") for b in (c or []) if isinstance(b, dict) and b.get("type") == "text")


def _ts(rec):
    s = rec.get("timestamp")
    if not s:
        return None
    try:
        from datetime import datetime, timezone
        return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


# Turn boundaries come from the event model ITSELF (kernel/event_model.py), loaded hermetically against a scratch state root
# (never the live one): `parse_session` folds a transcript into the same turns the judges segment, so the builder's endings are
# theirs by construction. A copy of the opener rule drifted (round three of the review: it reproduced three of the fold's
# refusals and none of the command-twin, local-command, skill-content or restore-replay handling), so the copy is gone.
_EM = [None]


def _event_model():
    """kernel/event_model.py, loaded once against a throwaway state root so `parse_session` reads no live state (it parses the
    explicit transcript path either way; its bound roots only reach postal-log and states annotations the boundaries do not use)."""
    if _EM[0] is None:
        saved = {k: os.environ.get(k) for k in ("XDG_STATE_HOME", "ROMP_STATE_DIR", "ROMP_POSTAL_CLIENT_ONLY")}
        scratch = tempfile.mkdtemp(prefix="je-em-")
        os.makedirs(os.path.join(scratch, "romp"), exist_ok=True)
        with open(os.path.join(scratch, "romp", "session-hosts"), "w") as f:
            f.write("off")
        os.environ["XDG_STATE_HOME"] = scratch
        os.environ.pop("ROMP_STATE_DIR", None)
        os.environ["ROMP_POSTAL_CLIENT_ONLY"] = "1"
        sys.path.insert(0, str(ROOT / "tests"))
        from romp_load import load_source
        try:
            _EM[0] = load_source("romp_event_model_ends", str(BIN / "romp-event-model"))
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            shutil.rmtree(scratch, ignore_errors=True)   # the module has bound its roots; parse_session reads the explicit path,
            #                                              and the roots reach only absent postal-log/states files (handled as absence)
    return _EM[0]


def _worked_assistant_atom(turn):
    """The judge's own line (kernel/judge.py `_seg_command_worked`): a turn put the MODEL to work iff it has an assistant
    atom that is not the `command`-flagged local-command stdout echo."""
    return any(a.get("type") == "assistant" and not a.get("command") for a in (turn.get("atoms") or []))


def _atom_text(a):
    body = a.get("text") if isinstance(a.get("text"), str) else (a.get("message") or {}).get("content")
    return _text_of({"message": {"content": body}})


def session_endings(path, fsid):
    """(records, [(end_index, start_t, last_text)]) per ENDED turn the model WORKED, from the event model's segmentation. A turn
    with no non-command assistant atom (a bare /model or /usage, an idle compaction with no continuation) or an interrupt tail
    is not an ending: it inflates the finished class and the denominator without a card to judge. `end_index` is the record of
    the turn's last atom (so an interrupted continuation still reads open to the arm's judges); `start_t` is the turn's own
    start, None when the turn has no opener (the ending is then ineligible); `last_text` is the turn's last NON-COMMAND
    assistant text, what classify_ending reads."""
    records = _records(path)
    uuid_idx = {r.get("uuid"): i for i, r in enumerate(records) if r.get("uuid")}
    em = _event_model()
    sess = em.parse_session(str(path), rompuuid=fsid)   # a parse that raises is surfaced (fail loud): the builder counts parse-failed
    out = []
    for turn in sess.get("turns") or []:
        atoms = turn.get("atoms") or []
        if not turn.get("ended") or not _worked_assistant_atom(turn):
            continue
        if atoms and getattr(em, "is_interrupt_record", None) and em.is_interrupt_record(atoms[-1]):
            continue                                  # an interrupted turn is open to the judges, not an ending
        idxs = [uuid_idx[a.get("uuid")] for a in atoms if a.get("uuid") in uuid_idx]
        if not idxs:
            continue
        last_text = next((_atom_text(a) for a in reversed(atoms) if a.get("type") == "assistant" and not a.get("command")), "")
        start = float(turn["t"]) if turn.get("trigger") else None
        out.append((max(idxs), start, last_text))
    out.sort(key=lambda x: x[0])
    return records, out


def turn_ends(records):
    """The record indices that end a turn, via the event model (a temp file, since `parse_session` reads a path). For the
    tests and any caller holding records rather than a path; the builder calls `session_endings` on the transcript directly."""
    fd, p = tempfile.mkstemp(suffix=".jsonl")
    try:
        with os.fdopen(fd, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
        fsid = next((r.get("sessionId") for r in records if r.get("sessionId")), "s")
        return [t[0] for t in session_endings(p, fsid)[1]]
    finally:
        os.unlink(p)


def turn_start(records, end_index):
    """The start time of the turn ending at `end_index`, or None when that index is not a turn end."""
    fd, p = tempfile.mkstemp(suffix=".jsonl")
    try:
        with os.fdopen(fd, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
        fsid = next((r.get("sessionId") for r in records if r.get("sessionId")), "s")
        return next((st for i, st, _tx in session_endings(p, fsid)[1] if i == end_index), None)
    finally:
        os.unlink(p)


def custom_title(path):
    """The transcript's custom-title record in its head (the judge's `_custom_title`), or None."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(65536).decode("utf-8", "replace")
    except OSError:
        return None
    for line in head.split("\n"):
        if "custom-title" not in line:
            continue
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if o.get("type") == "custom-title" and o.get("customTitle"):
            return o["customTitle"]
    return None


_TITLE_MEMO = {}


def fork_lanes(project_dir, name, exclude):
    """The same-customTitle fork transcripts in the session's project directory (the judge's discovery lists each as its own
    lane): every other transcript there whose head carries the session's name as its custom title. The head read is memoized
    across sessions (the judge's `title_memo`), so a project directory shared by many sessions is read once per transcript."""
    out = []
    try:
        entries = sorted(os.listdir(project_dir))
    except OSError:
        return out
    for fn in entries:
        stem = fn[:-6] if fn.endswith(".jsonl") else None
        if not stem or stem in exclude:
            continue
        path = os.path.join(project_dir, fn)
        if path not in _TITLE_MEMO:
            _TITLE_MEMO[path] = custom_title(path)
        if name and _TITLE_MEMO[path] == name:
            out.append(stem)
    return out


def known_fsids(state_root, sid):
    """Every transcript fsid romp has on record for `sid`, read as files the way the kernel's registry reader does: the sid
    itself, the registry's lastSid, each /clear episode head and both ends of every resume fork."""
    out = {str(sid)}
    state_root = Path(state_root)
    reg_path = state_root / "sdk" / (sid + ".json")
    if reg_path.is_file():
        reg = json.loads(reg_path.read_text(encoding="utf-8"))   # a corrupt registry RAISES (the builder counts registry-unreadable)
        if isinstance(reg, dict) and reg.get("lastSid"):
            out.add(str(reg["lastSid"]))
    for sub, pick in (("episodes", lambda r: [r.get("fsid")]),
                      ("states", lambda r: [(r.get("resumeFork") or {}).get(k) for k in ("from", "to")])):
        fp = state_root / sub / (sid + ".jsonl")
        try:
            lines = fp.read_text(encoding="utf-8").splitlines()
        except OSError as e:
            if e.errno in (errno.ENOENT, errno.ENOTDIR):
                continue                              # absent: contributes nothing, as before
            raise                                     # a real read fault (EACCES, EIO): surfaced, the builder counts it
        for line in lines:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if isinstance(r, dict):
                out.update(str(v) for v in pick(r) if v)
    return out


def in_turn_window(t, start_t, cut_t):
    """Whether a verdict time belongs to the ending's turn: from the turn's start to the cut. No closer or planner done carries
    an evidence time past its own cut, so a done after the cut is the next turn's; an ending with no turn start (None) has no
    window and is ineligible."""
    if start_t is None:
        return False
    return start_t <= t <= cut_t


DROP_STORE_FIELDS = ("seams", "closeFails", "confirming", "groupedSig", "consolidatedSig", "rewindSwept", "summaryQuote",
                     "summaryAnchors", "summaryQuoteOff", "warns", "unblockFails", "parseFails", "courierDeferred")   # store-level
#   state from after the cut (a re-key makes the id-keyed ones live under the ending id); the arm's rollup remakes what it needs
DROP_NODE_FIELDS = ("nodeComplete", "blocked", "cleared", "doneWhy", "settledAt", "settledDone", "rolledUp", "summary",
                    "summaryParts", "summaryAnchor", "distilledMt")          # the flag cache and the sealing fields: the arm's rollup remakes them
DROP_STAMPS = ("blockCheckT", "blockCheckDoneT", "delegLookT", "closerLookT", "awaitingAt")   # gate stamps: kept only when before the
#   turn start, else dropped (a blockCheckT at or before the cut hides a node from the unblocker's strict gate, so clamping is not enough)
CLAMP_STAMPS = ("titledT", "servingT")   # capped at the cut, never dropped: dropping titledT buys a title call per node per build


def deep_rekey(obj, old, new):
    """Every string in `obj` (keys and values, nested) with `old` replaced by `new`: the store's ids all carry the session
    id as their prefix (node ids, segment ids, turn ids, placement keys), and the arm parses under the ending id."""
    if isinstance(obj, str):
        return obj.replace(old, new) if old else obj
    if isinstance(obj, list):
        return [deep_rekey(x, old, new) for x in obj]
    if isinstance(obj, dict):
        return {deep_rekey(k, old, new): deep_rekey(v, old, new) for k, v in obj.items()}
    return obj


def store_before(store, cut_t, start_t=None, eid=None):
    """The goal store as the judges held it when the ending's turn OPENED, keyed for the arm. Every id prefix (the session
    id) becomes the ending id, so the arm's segment and turn ids match the seed's (`_placed_key` and the closer's one-shot
    read them; without the re-key the planner re-planned the whole history on every build). The cut is the turn's start
    (`start_t`; the caller passes the previous ended turn's cut for an opener-less ending, or the cut itself when there is no
    previous): nodes born before it, each node's verdict
    log cut to events before it (`ev_t`, then `at`), trails to segments before it, `closedTurns`, `closedSig` and
    placements to turns and segments before it; the ending turn's own prompt-run placement (`#p`, and a delegation's `#d`)
    and the node it points to are kept, so the planner runs the turn's work-run once, as the live pass would; the flag
    cache and the sealing fields are dropped for the arm's rollup (kept, they sealed the seeded top out of the menu and a
    twin was minted); gate stamps at or after the turn start are dropped (`titledT`/`servingT` clamped, never dropped, to spare a re-title);
    store-level state from after the cut (the fields in DROP_STORE_FIELDS) is dropped; nodes whose first trail entry is a
    dropped segment go, and the orphan pass runs to a fixed point. Nothing keyed to the turn or later survives except that
    prompt-run node; what stays is re-keyed to the ending id. A node the user CLEARED before the turn start keeps its clear
    log row (its rollup reads `cleared`); a clear INSIDE the turn is dropped with the rest of the turn's verdicts, so that
    card is the arm's to rule on, open at the seed."""
    sid = str(store.get("rompUuid") or "")
    src = deep_rekey(store, sid, eid) if (eid and sid) else store
    lo = start_t if start_t is not None else cut_t
    placements, targets, dropped_segs = {}, set(), set()
    for k, v in (src.get("placements") or {}).items():
        ep = id_epoch(k)
        if ep is not None and ep < lo:
            placements[k] = v
        elif ep is not None and ep <= cut_t and k.rsplit("#", 1)[-1] in ("p", "d"):
            placements[k] = v                        # the turn's own prompt-run (or delegation) placement: its mint stands; the
            #                                          work-run, live re-plan (#live) and extra-target (#n<i>) keys are the arm's to make
            if isinstance(v, str):
                targets.add(v)
        else:
            dropped_segs.add(k.split("#")[0])
    nodes = {}
    for nid, nd in (src.get("nodes") or {}).items():
        times = [t for t in (event_time(e) for e in (nd.get("log") or [])) if t is not None]
        born = float(nd.get("t") or 0) or (min(times) if times else 0)
        target = nid in targets
        if not (born < lo or (target and born <= cut_t)):
            continue
        trail = list(nd.get("trail") or [])
        if trail and trail[0] in dropped_segs and not target:
            continue                                 # minted from a segment the copy does not hold
        log = [e for e in (nd.get("log") or []) if (event_time(e) or 0) < lo]   # a node is kept by BIRTH; its verdict rows before the turn stay,
        #                                                                          the turn's own drop (no writer emits a `mint` row to keep)
        nd2 = {k: v for k, v in nd.items() if k not in DROP_NODE_FIELDS}
        nd2["log"] = log
        nd2["trail"] = [t for t in trail if (id_epoch(t) or 0) < lo or (target and (id_epoch(t) or 0) <= cut_t)]
        for stamp in DROP_STAMPS:
            try:
                if nd2.get(stamp) is not None and float(nd2[stamp]) >= lo:
                    nd2.pop(stamp)
            except (TypeError, ValueError):
                nd2.pop(stamp, None)
        for stamp in CLAMP_STAMPS:
            try:
                if nd2.get(stamp) is not None and float(nd2[stamp]) > cut_t:
                    nd2[stamp] = cut_t
            except (TypeError, ValueError):
                nd2.pop(stamp, None)
        if nd2.get("mt") and float(nd2["mt"]) > cut_t:
            nd2["mt"] = cut_t
        nodes[nid] = nd2
    changed = True
    while changed:                                   # loop-ok: the orphan pass to a fixed point over a finite dict
        changed = False
        for nid in list(nodes):
            parent = nodes[nid].get("parentId")
            if parent is not None and parent not in nodes:
                nodes.pop(nid); changed = True
    out = {k: v for k, v in src.items()
           if k not in ("nodes", "status", "closedTurns", "closedSig", "placements", "lastNode") + DROP_STORE_FIELDS}
    out["rompUuid"] = eid or sid
    out["nodes"] = nodes
    out["status"] = {}
    out["closedTurns"] = [t for t in (src.get("closedTurns") or []) if (id_epoch(t) or 0) < lo]
    cs = src.get("closedSig")
    out["closedSig"] = {k: v for k, v in cs.items() if (id_epoch(k) or 0) < lo} if isinstance(cs, dict) else cs
    out["placements"] = placements
    if src.get("lastNode") in nodes:
        out["lastNode"] = src["lastNode"]
    return out


def store_with_archive(state_root, sid):
    """The session's live goal store with the CLEARED tops the kernel's compaction moved into goals-archive/<sid>.json unioned
    back into its nodes (they carry their full verdict log there). The four readers of a session's cards (the done times, the
    eligibility mark, tier one and the seed) all take this, so a top the user crossed off is not invisible for being archived."""
    state_root = Path(state_root)
    store = {}
    live = state_root / "goals" / (sid + ".json")
    if live.is_file():
        store = json.loads(live.read_text(encoding="utf-8"))   # a corrupt live store RAISES (fail loud): the caller counts store-unreadable
    if not isinstance(store, dict):
        raise ValueError("goal store top level is not an object")   # a non-object top is a fault, not an empty store
    nodes = dict(store.get("nodes") or {})
    swept = set(store.get("rewindSwept") or {})      # ids the rewind path tombstoned: their archive copies are not cleared subtrees
    arch_path = state_root / "goals-archive" / (sid + ".json")
    if arch_path.is_file():
        arch = json.loads(arch_path.read_text(encoding="utf-8"))   # a corrupt archive RAISES too
        if not isinstance(arch, dict):
            raise ValueError("goal archive top level is not an object")
        for nid, nd in (arch.get("nodes") or {}).items():
            if nid in swept:
                continue                             # a rewound node, not a user-cleared card: never unioned in
            nodes.setdefault(nid, nd)                # the live store wins a shared key; a cleared top lives only in the archive
    store = dict(store)
    store["nodes"] = nodes
    store.setdefault("rompUuid", sid)
    return store


def top_done_times(store):
    """The evidence times of every closer or planner `done` on a top-level node (of a store already unioned with its archive):
    the endings these fall within are the ones the user's later card actions can label (tier one)."""
    out = []
    for nid, nd in (store.get("nodes") or {}).items():
        if nd.get("parentId") is not None:
            continue
        for ev in nd.get("log") or []:
            if ev.get("kind") == "done" and ev.get("src") in ("closer", "planner"):
                t = event_time(ev)
                if t is not None:
                    out.append(t)
    return out


def build_corpus(state_root, claude_root, dest, per_class=75, now=None, min_turns=2):
    """Read the live roots as files, write the corpus under `dest`: per ending a truncated transcript under
    dest/claude/projects/<munged cwd>/<ending id>.jsonl, a names entry, the store before the cut and the override journal
    before the cut under dest/state/romp/, and a manifest of ids, classes and cut times (no text)."""
    refuse_inside_repo(dest)
    state_root, claude_root, dest = Path(state_root), Path(claude_root), Path(dest)
    now = time.time() if now is None else now
    names_dir = state_root / "names"
    picked = {c: [] for c in CLASSES}
    candidates = []
    skipped = {"no-transcript": 0, "few-turns": 0, "unreadable-names-entry": 0, "parse-failed": 0,
               "store-unreadable": 0, "registry-unreadable": 0}
    dones_by_key = {}                                  # store key -> the top-done times of that lane's own store (cached)
    def dones_for(key):
        if key not in dones_by_key:
            dones_by_key[key] = top_done_times(store_with_archive(state_root, key))
        return dones_by_key[key]
    entries = [e for e in (sorted(names_dir.iterdir()) if names_dir.is_dir() else [])]
    registered = {e.name for e in entries}             # every session's sid: a fork lane is never one of these
    claimed = set()                                    # transcript paths an earlier session already took as its own
    for entry in entries:
        try:
            fields = entry.read_text(encoding="utf-8").strip().split("\t")
        except OSError:
            skipped["unreadable-names-entry"] += 1
            continue
        if len(fields) < 2:
            skipped["unreadable-names-entry"] += 1
            continue
        name, cwd = fields[0], fields[1]
        color = fields[2] if len(fields) > 2 else "#888888"
        sid = entry.name
        try:
            own = known_fsids(state_root, sid)         # the sid, its /clear and resume leaves: all keyed under the sid
        except (OSError, ValueError):
            skipped["registry-unreadable"] += 1
            sys.stderr.write("judge-experiment: a registry or lineage record could not be read; the session is skipped\n")
            continue
        pdir = claude_root / "projects" / munge(cwd)
        lanes = set(fork_lanes(pdir, name, registered | own))   # same-titled forks, excluding every registered sid and the own leaves
        found = False
        for fsid in sorted(own | lanes):
            transcript = pdir / (fsid + ".jsonl")
            if not transcript.is_file() or str(transcript) in claimed:
                continue
            claimed.add(str(transcript))
            found = True
            is_lane = fsid in lanes and fsid not in own
            store_key = fsid if is_lane else sid       # a title lane's store/journal is keyed under its own stem; the leaves' under the sid
            try:
                dones = dones_for(store_key)
            except (OSError, ValueError):
                skipped["store-unreadable"] += 1
                sys.stderr.write("judge-experiment: a goal store could not be read; the lane is skipped\n")
                continue
            try:
                records, endings = session_endings(transcript, fsid)
            except Exception:
                skipped["parse-failed"] += 1
                sys.stderr.write("judge-experiment: the event model could not parse a transcript (%s); skipped\n" % type(sys.exc_info()[1]).__name__)
                continue
            if len(endings) < min_turns:
                skipped["few-turns"] += 1
                continue
            prev_cut = None
            for k, (i, start_t, last_text) in enumerate(endings):
                cut_t = _ts(records[i]) or 0
                cls = classify_ending(last_text)
                eligible = any(in_turn_window(t, start_t, cut_t) for t in dones)   # keys on the real start: a None start is never in a window
                seed_start = start_t if start_t is not None else prev_cut   # an opener-less ending's seed cuts at the previous ended turn's end
                candidates.append((sid, name, cwd, color, k, i, cut_t, cls, transcript, eligible, start_t, fsid, store_key, seed_start))
                prev_cut = cut_t
        if not found:
            skipped["no-transcript"] += 1
    # spread across sessions: round-robin over sessions within each class, the tier-one-eligible endings first
    by_class = {c: {} for c in CLASSES}
    for cand in candidates:
        by_class[cand[7]].setdefault(cand[0], []).append(cand)
    for c in CLASSES:
        for want_eligible in (True, False):
            # eligible endings OLDEST first (the user had the most time to act on their cards), the rest newest first;
            # each session's list sorted by the cut TIME first (candidates arrive in stem order, not time), then pop() takes
            # the last: for eligible, oldest; for the rest, newest
            queues = [sorted((x for x in v if x[9] == want_eligible), key=lambda x: x[6]) for v in by_class[c].values()]
            queues = [(list(reversed(q)) if want_eligible else q) for q in queues if q]
            while queues and len(picked[c]) < per_class:
                for q in list(queues):
                    if len(picked[c]) >= per_class:
                        break
                    picked[c].append(q.pop())
                    if not q:
                        queues.remove(q)
    (dest / "state" / "romp" / "names").mkdir(parents=True, exist_ok=True)
    for sub in ("goals", "overrides"):
        (dest / "state" / "romp" / sub).mkdir(parents=True, exist_ok=True)
    (dest / "state" / "romp" / "session-hosts").write_text("off")
    manifest = {"built": now, "classes": list(CLASSES), "endings": [], "skipped": skipped}
    for c in CLASSES:
        for sid, name, cwd, color, k, i, cut_t, cls, transcript, eligible, start_t, fsid, store_key, seed_start in picked[c]:
            eid = str(uuid.uuid5(uuid.NAMESPACE_URL, "romp-judge-experiment:%s:%s:%d" % (sid, fsid, k)))
            pdir = dest / "claude" / "projects" / munge(cwd)
            pdir.mkdir(parents=True, exist_ok=True)
            records = _records(transcript)[:i + 1]
            with open(pdir / (eid + ".jsonl"), "w", encoding="utf-8") as fh:
                for r in records:
                    fh.write(json.dumps(r) + "\n")
            (dest / "state" / "romp" / "names" / eid).write_text("%s\t%s\t%s\n" % (name, cwd, color))
            try:
                store = store_with_archive(state_root, store_key)   # the lane's own store (its stem for a title lane, the sid otherwise)
            except (OSError, ValueError):
                continue                              # already counted above for this lane
            before = store_before(store, cut_t, seed_start, eid) if store.get("nodes") else None
            if before is not None:                        # a session with no store yet starts the arm fresh (load_goals mints the shape)
                (dest / "state" / "romp" / "goals" / (eid + ".json")).write_text(json.dumps(before))
            lo = seed_start if seed_start is not None else cut_t   # the journal cut matches the seed's cut (the previous turn's end for an opener-less ending)
            ov = state_root / "overrides" / (store_key + ".jsonl")   # the lane's own journal
            if ov.is_file():
                kept = []
                for l in ov.read_text(encoding="utf-8").splitlines():
                    try:
                        row = json.loads(l)
                    except ValueError:
                        continue
                    if lo is not None and float(row.get("t") or 0) < lo:
                        kept.append(json.dumps(deep_rekey(row, store_key, eid)))
                (dest / "state" / "romp" / "overrides" / (eid + ".jsonl")).write_text("".join(x + "\n" for x in kept))
            manifest["endings"].append({"id": eid, "session": hashlib.sha256(sid.encode()).hexdigest()[:12],
                                        "lane": hashlib.sha256(store_key.encode()).hexdigest()[:12], "turn": k,
                                        "class": cls, "cutT": cut_t, "startT": start_t, "tierOneEligible": bool(eligible),
                                        "topsBefore": sorted(n.split(":")[-1] for n, nd in (before or {"nodes": {}})["nodes"].items()
                                                             if nd.get("parentId") is None)})
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest


# ── the arms ────────────────────────────────────────────────────────────────────────────────────
def load_judge(state_root, claude_root, claude_bin):
    """Load the event model and the judge module against the arm's roots: the module binds its roots from the environment
    at import, so the environment is set first and the modules are loaded fresh under names of the run's own."""
    os.environ["XDG_STATE_HOME"] = str(state_root)
    os.environ.pop("ROMP_STATE_DIR", None)
    os.environ["CLAUDE_CONFIG_DIR"] = str(claude_root)
    os.environ["ROMP_CLAUDE_BIN"] = str(claude_bin)
    os.environ.setdefault("ROMP_POSTAL_CLIENT_ONLY", "1")
    sys.path.insert(0, str(ROOT / "tests"))
    from romp_load import load_source
    shared = sys.modules.pop("romp_event_model", None)              # the judge module re-executes the event model under its shared
    try:                                                             # name at import; a caller's own event model (the tests') must not
        load_source("romp_event_model", str(BIN / "romp-event-model"))   # be left bound to the arm's scratch roots
        jd = load_source(JUDGE_MODULE_NAME, str(BIN / "romp-judge"))   # a name of the run's own: the tests' shared-state guard
    finally:                                                         # watches the module named romp_judge
        if shared is not None:
            sys.modules["romp_event_model"] = shared
        else:
            sys.modules.pop("romp_event_model", None)
    return jd


def apply_prompts(jd, prompts):
    """Swap the arm's prompts into the module attributes the calls read; returns what to restore."""
    saved = {}
    for key, text in (prompts or {}).items():
        if key not in PROMPT_KEYS:
            raise SystemExit("unknown prompt key %r (one of %s)" % (key, ", ".join(PROMPT_KEYS)))
        saved[key] = getattr(jd, key)
        setattr(jd, key, text)
    return saved


def restore_prompts(jd, saved):
    for key, text in saved.items():
        setattr(jd, key, text)


def column_of(status):
    return COLUMN_OF.get(status, "working")


def count_failure_rows(errors_path):
    """Rows on an arm's judge-errors ledger that mean a call failed, was skipped or its reply was rejected (FAILURE_KINDS); the
    other rows there are the judges' anomaly notes (a stale close, a workless done), which are verdict facts, not failures."""
    n = 0
    try:
        for line in Path(errors_path).open(encoding="utf-8"):
            try:
                if json.loads(line).get("err") in FAILURE_KINDS:
                    n += 1
            except ValueError:
                continue
    except OSError:
        return 0
    return n


def ledger_cost(usage_path):
    """(dollars, calls, mean ms) from the arm's own usage ledger."""
    cost, n, ms = 0.0, 0, 0.0
    if not Path(usage_path).is_file():
        return 0.0, 0, 0.0
    for line in Path(usage_path).read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        cost += float(r.get("cost") or 0); n += 1; ms += float(r.get("ms") or 0)
    return cost, n, (ms / n if n else 0.0)


def run_arm_inprocess(corpus, arm, prompts_file, run_root, budget_usd, claude_bin, now=None, builds=2):
    """One arm over the corpus, in this process: the corpus state copied under run_root/<arm>/state, the judge module
    loaded against it, the arm's prompts swapped in, and per ending and per build the planner, the closer over the last
    closed turn and the unblocker, the tops' columns recorded. Two builds from the same store copy give the flaps. The
    arm's ledger is read after every ending and the run stops past BUDGET_OVERRUN times the budget."""
    corpus, run_root = Path(corpus), Path(run_root)
    refuse_inside_repo(run_root)
    manifest = json.loads((corpus / "manifest.json").read_text())
    arm_root = run_root / arm
    state = arm_root / "state"
    if state.exists():
        shutil.rmtree(state)
    shutil.copytree(corpus / "state", state)
    jd = load_judge(state, corpus / "claude", claude_bin)
    prompts = json.loads(Path(prompts_file).read_text()) if prompts_file else {}
    saved = apply_prompts(jd, prompts)
    now = int(time.time()) if now is None else int(now)
    results = {"arm": arm, "prompts": sorted(prompts), "endings": {}, "stopped": None, "failures": 0, "closerNone": 0}
    usage = jd.USAGE
    errors_path = Path(jd.ERRORS)
    def error_rows():
        return count_failure_rows(errors_path)
    def flush():
        arm_root.mkdir(parents=True, exist_ok=True)
        (arm_root / "results.json").write_text(json.dumps(results, indent=1))
    try:
        for e in manifest["endings"]:
            eid = e["id"]
            path = next(iter((corpus / "claude" / "projects").glob("*/%s.jsonl" % eid)), None)
            if path is None:
                continue
            lo = e.get("startT")
            seed_path = corpus / "state" / "romp" / "goals" / (eid + ".json")
            seed = seed_path.read_text() if seed_path.is_file() else None
            builds_out = []
            try:
                for _b in range(builds):
                    errs0 = error_rows()
                    target = state / "romp" / "goals" / (eid + ".json")             # the same store copy for every build
                    if seed is None:
                        target.unlink(missing_ok=True)
                    else:
                        target.write_text(seed)
                    jd.parse_cache_clear()
                    session = jd.parsed_session(eid, [str(path)], now)
                    turns = session.get("turns") or []
                    store = jd.load_goals(eid)
                    closed = jd._session_settled(eid, str(path), session, store, now=now)   # the settled gate over the ending's own transcript
                    jd.rollup_status(store, closed, now=now)                            # the flags from the seed's diary, before the first menu
                    jd.save_goals(eid, store)
                    jd._plan_session(eid, str(path), now)
                    store = jd.load_goals(eid)
                    closed_turns = [t for t in turns if not jd._turn_open(t, turns)]
                    if closed_turns:
                        seg_by_id = {seg["id"]: seg for turn in turns for seg in jd._segs(turn, store)}   # the goal-history map production sends
                        rows_before = error_rows()
                        if jd._close_turn(store, closed_turns[-1], seg_by_id=seg_by_id) is None:
                            results["closerNone"] += 1
                            if error_rows() == rows_before:
                                results["failures"] += 1      # the closer gave nothing and filed no row (the cap road): counted once here
                    jd.rollup_status(store, closed, now=now)
                    jd.save_goals(eid, store)
                    jd._unblock_session(eid, str(path), now)
                    store = jd.load_goals(eid)
                    tops = {}
                    for nid, nd in (store.get("nodes") or {}).items():
                        if nd.get("parentId") is not None:
                            continue
                        born = float(nd.get("t") or 0)
                        # SCORED for this ending: born in the turn, OR the ARM filed a done/block on it this build. record_verdict
                        # stamps a verdict's `at` with the pass's `now`, so a row the ARM wrote reads `at` == now while a seed row
                        # kept its earlier `at`; that parts them. A lift RIDER's done keeps the lift's own ev_t (before the turn),
                        # so an ev_t test missed its leak; the arm's filing catches it (the rider residual: a done the arm files
                        # for an EARLIER turn's lift also reads scored, named here and left as the one over-count).
                        arm_filed = any(ev.get("kind") in ("done", "block") and float(ev.get("at") or 0) >= now
                                        for ev in (nd.get("log") or []))
                        scored = bool((lo is not None and born >= lo) or arm_filed)
                        tops[nid.split(":")[-1]] = {"column": column_of((store.get("status") or {}).get(nid)), "scored": scored}
                    builds_out.append(tops)
                    results["failures"] += error_rows() - errs0
            except Exception as ex:                       # one ending's build must not abort the arm: file it, keep the rest
                jd._log_judge_error("planner", eid, "pass-crash", note=repr(ex)[:200])
                results["failures"] += 1
                results["endings"][eid] = {"class": e["class"], "builds": builds_out, "crashed": repr(ex)[:200]}
                flush()
                continue
            results["endings"][eid] = {"class": e["class"], "builds": builds_out}
            flush()
            cost, n, _ = ledger_cost(usage)
            if budget_usd is not None and cost > budget_usd * BUDGET_OVERRUN:
                results["stopped"] = {"after": eid, "cost": round(cost, 4), "budget": budget_usd}
                break
    finally:
        restore_prompts(jd, saved)
        try:
            cost, n, mean_ms = ledger_cost(usage)
            results["cost"] = round(cost, 4); results["calls"] = n; results["callMsMean"] = round(mean_ms)
        except Exception:
            pass                                     # a ledger read that raises must not lose the summary written just below
        flush()                                      # results.json is written in the finally, whatever raised in the loop or after it
    return results


def run_arm(corpus, arm, prompts_file, run_root, budget_usd, claude_bin, now=None):
    """The arm in a subprocess of its own (the judge module binds its roots at import)."""
    cmd = [sys.executable, str(Path(__file__).resolve()), "run-arm", "--corpus", str(corpus), "--run-root", str(run_root),
           "--arm", arm, "--claude-bin", str(claude_bin)]
    if prompts_file:
        cmd += ["--prompts", str(prompts_file)]
    if budget_usd is not None:
        cmd += ["--budget-usd", str(budget_usd)]
    if now is not None:
        cmd += ["--now", str(int(now))]
    subprocess.run(cmd, check=True)
    return json.loads((Path(run_root) / arm / "results.json").read_text())


# ── the measures and the report ────────────────────────────────────────────────────────────────
def _scored(build):
    """{card: column} for the cards the ending scores (born, or given a done or block verdict, in the ending's turn)."""
    out = {}
    for nid, v in (build or {}).items():
        if isinstance(v, dict):
            if v.get("scored"):
                out[nid] = v.get("column")
        else:
            out[nid] = v                                 # an older results file: every card counted
    return out


def measure(manifest, results):
    """Per arm: leaks into Completed (an offer, question or undone ending with a SCORED top read completed), false interrupts
    (a finished ending with a scored top read needs_input), flaps (a scored top whose column differs between builds), the
    failures (calls that failed or replies the parser rejected: a row with any is not comparable), and cost."""
    classes = {e["id"]: e["class"] for e in manifest["endings"]}
    leaks = false_interrupts = flaps = 0
    for eid, r in results["endings"].items():
        cls = classes.get(eid, r.get("class"))
        builds = [_scored(b) for b in r["builds"]]
        final = builds[-1] if builds else {}
        if cls in ("offer", "question", "undone") and "completed" in set(final.values()):
            leaks += 1
        if cls == "finished" and "needs_input" in set(final.values()):
            false_interrupts += 1
        if len(builds) >= 2:
            for nid in set(builds[0]) | set(builds[1]):
                if builds[0].get(nid) != builds[1].get(nid):
                    flaps += 1
    failures = int(results.get("failures") or 0)
    return {"arm": results["arm"], "endings": len(results["endings"]), "leaks": leaks, "falseInterrupts": false_interrupts,
            "flaps": flaps, "costUsd": results.get("cost", 0.0), "calls": results.get("calls", 0),
            "callMsMean": results.get("callMsMean", 0), "stopped": results.get("stopped"), "failures": failures,
            "comparable": failures == 0}


def report(corpus, run_root, figure=None):
    """The table (markdown, written beside the arms) and the figure (the cleanplots skill; skipped with a note when the
    library is absent). Counts and dollars only: nothing from the corpus."""
    corpus, run_root = Path(corpus), Path(run_root)
    manifest = json.loads((corpus / "manifest.json").read_text())
    rows = []
    for d in sorted(p for p in run_root.iterdir() if (p / "results.json").is_file()):
        rows.append(measure(manifest, json.loads((d / "results.json").read_text())))
    lines = ["| arm | endings | leaks into Completed | false interrupts | flaps | cost (USD) | calls | mean call ms | stopped | failures |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append("| %s | %d | %d | %d | %d | %.2f | %d | %d | %s | %s |" % (r["arm"], r["endings"], r["leaks"], r["falseInterrupts"],
                                                                             r["flaps"], r["costUsd"], r["calls"], r["callMsMean"],
                                                                             "yes" if r["stopped"] else "no",
                                                                             "0" if r["comparable"] else "%d, not comparable" % r["failures"]))
    (run_root / "table.md").write_text("\n".join(lines) + "\n")
    (run_root / "measures.json").write_text(json.dumps(rows, indent=1))
    if figure:
        try:
            draw_figure(rows, figure)
        except ImportError as e:
            (run_root / "figure.note").write_text("no figure: %s\n" % e)
    return rows


def draw_figure(rows, out):
    import cleanplots as cp
    metrics = [("leaks", "Leaks into Completed, must be zero"), ("falseInterrupts", "False interrupts, must not rise"),
               ("flaps", "Cards that flap between builds"), ("costUsd", "Cost per pass (USD)"), ("failures", "Failed calls, a row with any is not comparable")]
    f, axes = cp.fig(rows=1, cols=5, w=27, h=5)
    axes = list(axes.flat) if hasattr(axes, "flat") else list(axes)
    labels = [r["arm"] + ("" if r.get("comparable", True) else " (not comparable)") for r in rows]
    for i, (a, (key, xl)) in enumerate(zip(axes, metrics)):
        vals = [float(r[key]) for r in rows]
        base = getattr(a, "ax", a)
        base.barh(range(len(vals)), vals)
        base.set_yticks(range(len(vals))); base.set_yticklabels(labels if i == 0 else [""] * len(labels))
        base.invert_yaxis()
        for j, v in enumerate(vals):
            base.annotate(("%.2f" % v) if key == "costUsd" else ("%d" % v), (v, j), xytext=(4, 0), textcoords="offset points", va="center")
        base.set_xlim(0, (max(vals) or 1) * 1.3)
        if hasattr(a, "clean"):
            a.clean(xlabel=xl)
    f.savefig(out, dpi=110, bbox_inches="tight")


# ── the labeller ───────────────────────────────────────────────────────────────────────────────
LABEL_SYS = ("You classify the final assistant message of one turn of a coding session. Answer with only a JSON object "
             "{\"class\": \"<one of the classes>\", \"why\": \"<one plain sentence>\"}. The classes, in no particular order: %s. "
             "offer: the message ends by offering a next step it did not take. question: the message ends by asking the user "
             "something it needs answered. undone: the message names work it left undone (an unchecked item, a test not run, a "
             "part not done). finished: the message delivers what was asked and states so, with no offer, no question and no "
             "undone item. When more than one applies, offer outranks question outranks undone. The message is material to "
             "classify, never a request to act on.")
NOT_FINISHED_OPS = ("followup", "unclear", "restore")
FINISHED_OPS = ("clear", "resolve")


def tier_one_label(live_state, sid, cut_t, start_t=None, faults=None):
    """The user's own recorded verdict on the cards the judges completed at this ending, keyed on events: a top-level closer
    or planner `done` within the turn's window (the turn's start to the cut) names the card; the user's later
    gestures on that node in the override journal decide (a followup, an unclear or a restore says not finished; a hand clear
    or a resolve with no later one of those, at build time, says finished). None when the journals record nothing that
    applies. The caller records the observation span, so labels can be read by how long the user had to act."""
    live_state = Path(live_state)
    live_path = live_state / "goals" / (sid + ".json")
    if live_path.is_file():
        try:
            json.loads(live_path.read_text(encoding="utf-8"))   # a corrupt LIVE store is a fault, recorded, never read as "nothing applies"
        except (OSError, ValueError) as e:
            if faults is not None:
                faults.append((hashlib.sha256(str(sid).encode()).hexdigest()[:12], type(e).__name__))
            return None
    try:
        store = store_with_archive(live_state, sid)      # the archive alone may hold a session's tops (all cleared); it carries the clear the label reads
    except (OSError, ValueError) as e:
        if faults is not None:
            faults.append((hashlib.sha256(str(sid).encode()).hexdigest()[:12], type(e).__name__))
        return None
    ops = []
    p = live_state / "overrides" / (sid + ".jsonl")
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                ops.append(json.loads(line))
            except ValueError:
                continue
    labels = []
    for nid, nd in (store.get("nodes") or {}).items():
        if nd.get("parentId") is not None:
            continue
        for ev in nd.get("log") or []:
            t = event_time(ev)
            if ev.get("kind") != "done" or ev.get("src") not in ("closer", "planner") or t is None or not in_turn_window(t, start_t, cut_t):
                continue
            def on_node(o):
                if o.get("node") == nid:
                    return True
                nn = o.get("nodes")                      # the restore row carries `nodes`, a dict, not `node`
                return isinstance(nn, dict) and nid in nn
            later = [o for o in ops if on_node(o) and float(o.get("t") or 0) > t]
            if any(o.get("op") in NOT_FINISHED_OPS for o in later):
                labels.append("not finished")
            elif any(o.get("op") in FINISHED_OPS and o.get("src") in (None, "user") for o in later):
                labels.append("finished")
    if not labels:
        return None
    return "not finished" if "not finished" in labels else "finished"


def _last_assistant_text(path, cap=6000):
    last = ""
    first_ask = ""
    for r in _records(path):
        if r.get("type") == "assistant":
            t = _text_of(r)
            if t.strip():
                last = t
        elif r.get("type") == "user" and not r.get("isMeta") and not first_ask:
            t = _text_of(r)
            if t.strip():
                first_ask = t
    ask = ("\nThe user's ask that opened the last turn: %s" % first_ask[:1500]) if first_ask else ""
    return (last[-cap:] + ask)


def ask_class(claude_bin, model, text, order, ledger_path):
    """One labeller call: the class in `order`'s wording, the cost from the envelope onto the ledger. None on an unusable reply."""
    cmd = [str(claude_bin), "-p", "--safe-mode", "--model", model, "--tools", "", "--strict-mcp-config", "--mcp-config",
           '{"mcpServers":{}}', "--system-prompt", LABEL_SYS % ", ".join(order), "--exclude-dynamic-system-prompt-sections",
           "--output-format", "json"]
    t0 = time.time()
    try:
        p = subprocess.run(cmd, input="<message>\n%s\n</message>" % text, capture_output=True, text=True, timeout=240)
        out, rc = p.stdout, p.returncode
    except (OSError, subprocess.TimeoutExpired) as e:
        out, rc = "", -1
    try:
        env = json.loads(out)
    except ValueError:
        env = {}
    cost = float(env.get("total_cost_usd") or 0)
    with open(ledger_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"t": time.time(), "judge": "labeller", "model": model, "ms": int((time.time() - t0) * 1000),
                             "cost": cost, "rc": rc}) + "\n")
    m = re.search(r"\{.*\}", env.get("result") or "", re.S)
    try:
        cls = json.loads(m.group(0)).get("class") if m else None
    except ValueError:
        cls = None
    return (cls if cls in CLASSES else None), cost


def label(corpus, run_root, live_state, claude_bin, model="fable", seed=20260921):
    """The labelling pass: tier one from the live journals (read only) for every ending whose session the live names directory
    still lists; tier two twice per ending with the classes in two orders, the label their agreement; the agreement of tier
    two with tier one on every ending that has both, against AGREEMENT_GATE_PCT. Writes labels.json and labels-summary.json
    under the run root; every call's cost on labeller-ledger.jsonl there."""
    import random
    corpus, run_root, live_state = Path(corpus), Path(run_root), Path(live_state)
    refuse_inside_repo(run_root)
    run_root.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((corpus / "manifest.json").read_text())
    names_dir = live_state / "names"
    key_of = {}                                        # session/lane hash -> the sid or lane stem to read the store and journal under
    for n in (os.listdir(names_dir) if names_dir.is_dir() else []):
        key_of[hashlib.sha256(n.encode()).hexdigest()[:12]] = n
    goals_dir = live_state / "goals"
    for f in (os.listdir(goals_dir) if goals_dir.is_dir() else []):
        if f.endswith(".json"):
            stem = f[:-5]
            key_of.setdefault(hashlib.sha256(stem.encode()).hexdigest()[:12], stem)
    ledger = run_root / "labeller-ledger.jsonl"
    rng = random.Random(seed)
    rows, spent, faults = [], 0.0, []
    for e in manifest["endings"]:
        key = key_of.get(e.get("lane") or e["session"])   # the lane's own store; never the anchor's when a lane hash is present but unresolved
        row_faults = []
        t1 = tier_one_label(live_state, key, float(e["cutT"] or 0), e.get("startT"), faults=row_faults) if key else None
        faults.extend(row_faults)
        path = next(iter((corpus / "claude" / "projects").glob("*/%s.jsonl" % e["id"])), None)
        text = _last_assistant_text(path) if path else ""
        a, c1 = ask_class(claude_bin, model, text, list(CLASSES), ledger)
        order = list(CLASSES); rng.shuffle(order)
        if order == list(CLASSES):
            order = list(reversed(CLASSES))          # a four-class shuffle is the identity 1 in 24; never ask the same order twice
        b, c2 = ask_class(claude_bin, model, text, order, ledger)
        spent += c1 + c2
        rows.append({"id": e["id"], "class": e["class"], "tierOne": t1, "labelA": a, "labelB": b, "label": a if a == b else None,
                     "spanS": int(time.time() - float(e["cutT"] or 0)),
                     "tierOneError": row_faults[0][1] if row_faults else None})   # a faulted read, told apart from a genuine tierOne null
    (run_root / "labels.json").write_text(json.dumps(rows, indent=1))
    both = [r for r in rows if r["tierOne"] and r["label"]]
    agree = sum(1 for r in both if (r["label"] == "finished") == (r["tierOne"] == "finished"))
    pct = round(100.0 * agree / len(both), 1) if both else None
    summary = {"endings": len(rows), "tierOneLabelled": sum(1 for r in rows if r["tierOne"]),
               "labellerStable": sum(1 for r in rows if r["label"]), "both": len(both), "agree": agree, "agreementPct": pct,
               "gatePct": AGREEMENT_GATE_PCT, "gatePassed": bool(both) and pct >= AGREEMENT_GATE_PCT,
               "heuristicMatchesLabel": sum(1 for r in rows if r["label"] and r["label"] == r["class"]), "spentUsd": round(spent, 4),
               "tierOneErrors": [{"session": h, "error": ex} for h, ex in sorted(set(faults))]}
    (run_root / "labels-summary.json").write_text(json.dumps(summary, indent=1))
    return summary


# ── the command line ───────────────────────────────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build-corpus"); b.add_argument("--state-root", required=True); b.add_argument("--claude-root", required=True)
    b.add_argument("--dest", required=True); b.add_argument("--per-class", type=int, default=75)
    r = sub.add_parser("run"); r.add_argument("--corpus", required=True); r.add_argument("--run-root", required=True)
    r.add_argument("--arm", action="append", required=True, help="NAME or NAME=PROMPTS.json")
    r.add_argument("--budget-usd", type=float, required=True, help="dollars for each arm; inf for no stop"); r.add_argument("--claude-bin", required=True)
    r.add_argument("--now", type=int, default=None)
    ra = sub.add_parser("run-arm"); ra.add_argument("--corpus", required=True); ra.add_argument("--run-root", required=True)
    ra.add_argument("--arm", required=True); ra.add_argument("--prompts", default=None); ra.add_argument("--budget-usd", type=float, default=None)
    ra.add_argument("--claude-bin", required=True); ra.add_argument("--now", type=int, default=None)
    rp = sub.add_parser("report"); rp.add_argument("--corpus", required=True); rp.add_argument("--run-root", required=True); rp.add_argument("--figure", default=None)
    lb = sub.add_parser("label"); lb.add_argument("--corpus", required=True); lb.add_argument("--run-root", required=True)
    lb.add_argument("--live-state", required=True); lb.add_argument("--claude-bin", required=True); lb.add_argument("--model", default="fable")
    a = ap.parse_args(argv)
    if a.cmd == "build-corpus":
        m = build_corpus(a.state_root, a.claude_root, a.dest, per_class=a.per_class)
        counts = {c: sum(1 for e in m["endings"] if e["class"] == c) for c in CLASSES}
        print(json.dumps({"endings": len(m["endings"]), "byClass": counts}))
    elif a.cmd == "run":
        for spec in a.arm:
            name, _, prompts = spec.partition("=")
            budget = None if a.budget_usd == float("inf") else a.budget_usd
            res = run_arm(a.corpus, name, prompts or None, a.run_root, budget, a.claude_bin, now=a.now)
            print(json.dumps({"arm": name, "endings": len(res["endings"]), "cost": res.get("cost"), "stopped": res.get("stopped")}))
    elif a.cmd == "run-arm":
        run_arm_inprocess(a.corpus, a.arm, a.prompts, a.run_root, a.budget_usd, a.claude_bin, now=a.now)
    elif a.cmd == "report":
        rows = report(a.corpus, a.run_root, figure=a.figure)
        print(json.dumps(rows, indent=1))
    elif a.cmd == "label":
        print(json.dumps(label(a.corpus, a.run_root, a.live_state, claude_bin=a.claude_bin, model=a.model), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
