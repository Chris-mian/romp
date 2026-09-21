#!/usr/bin/env python3
"""The judge prompt experiment (plans/judge-prompt-experiments.md): a corpus of transcript endings, arms of judge prompts
run over copies of it with the judge module rebound onto scratch roots, the four measures and a report.

    judge_experiment.py build-corpus --state-root ~/.local/state/romp --claude-root ~/.claude --dest DIR [--per-class N]
    judge_experiment.py run --corpus DIR --run-root DIR --arm NAME[=PROMPTS.json] ... [--budget-usd X] [--claude-bin PATH]
    judge_experiment.py report --run-root DIR [--figure PNG]

Every path the experiment writes is under the destination the caller names, and a destination inside a git checkout is
refused: the corpus is the user's own history and stays out of the repository. The corpus builder reads the live state
root and the Claude root as FILES (names, transcripts, goal stores, override journals) and loads no romp module against
them; each arm runs in a subprocess of its own with the judge module loaded against the arm's scratch root. Paid passes
are the caller's decision: the binary the arm calls is `--claude-bin` (the tests hand a fake).
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
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
COLUMN_OF = {"blocked": "needs_input", "completed": "completed"}


# ── the corpus ──────────────────────────────────────────────────────────────────────────────────
def classify_ending(text):
    """The heuristic pre-pass over a turn's last assistant text: one of CLASSES. The selection, not the truth (the labels
    are the design's tiers); an offer outranks a question outranks an undone item, and the rest is finished."""
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


def turn_ends(records):
    """Indexes of the assistant records that end a turn: an assistant record followed by a user record with typed content
    (or the end of the file), skipping tool results and progress rows."""
    ends = []
    for i, r in enumerate(records):
        if r.get("type") != "assistant":
            continue
        nxt = next((x for x in records[i + 1:] if x.get("type") in ("user", "assistant")), None)
        if nxt is None or (nxt.get("type") == "user" and isinstance((nxt.get("message") or {}).get("content"), str)):
            ends.append(i)
    return ends


def store_before(store, cut_t):
    """The goal store as the judges held it before `cut_t`: nodes born at or before the cut, each node's verdict log cut to
    events at or before it, the rolled-up status left for the arm's own rollup."""
    nodes = {}
    for nid, nd in (store.get("nodes") or {}).items():
        log = [e for e in (nd.get("log") or []) if float(e.get("t") or 0) <= cut_t]
        born = float(nd.get("t") or 0) or (float(log[0].get("t") or 0) if log else 0)
        if born and born > cut_t:
            continue
        nd2 = dict(nd)
        nd2["log"] = log
        for flag in ("nodeComplete", "blocked", "cleared"):
            nd2.pop(flag, None)
        nodes[nid] = nd2
    for nid in list(nodes):
        parent = nodes[nid].get("parentId")
        if parent is not None and parent not in nodes:
            nodes.pop(nid)
    out = {k: v for k, v in store.items() if k not in ("nodes", "status")}
    out["nodes"] = nodes
    out["status"] = {}
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
    for entry in sorted(names_dir.iterdir()) if names_dir.is_dir() else []:
        try:
            fields = entry.read_text(encoding="utf-8").strip().split("\t")
        except OSError:
            continue
        if len(fields) < 2:
            continue
        name, cwd = fields[0], fields[1]
        color = fields[2] if len(fields) > 2 else "#888888"
        sid = entry.name
        transcript = claude_root / "projects" / munge(cwd) / (sid + ".jsonl")
        if not transcript.is_file():
            continue
        records = _records(transcript)
        ends = turn_ends(records)
        if len(ends) < min_turns:
            continue
        for k, i in enumerate(ends):
            cut_t = _ts(records[i]) or 0
            cls = classify_ending(_text_of(records[i]))
            candidates.append((sid, name, cwd, color, k, i, cut_t, cls, transcript))
    # spread across sessions: round-robin over sessions within each class
    by_class = {c: {} for c in CLASSES}
    for cand in candidates:
        by_class[cand[7]].setdefault(cand[0], []).append(cand)
    for c in CLASSES:
        queues = [list(reversed(v)) for v in by_class[c].values()]      # newest endings first per session
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
    manifest = {"built": now, "classes": list(CLASSES), "endings": []}
    for c in CLASSES:
        for sid, name, cwd, color, k, i, cut_t, cls, transcript in picked[c]:
            eid = str(uuid.uuid5(uuid.NAMESPACE_URL, "romp-judge-experiment:%s:%d" % (sid, k)))
            pdir = dest / "claude" / "projects" / munge(cwd)
            pdir.mkdir(parents=True, exist_ok=True)
            records = _records(transcript)[:i + 1]
            with open(pdir / (eid + ".jsonl"), "w", encoding="utf-8") as fh:
                for r in records:
                    fh.write(json.dumps(r) + "\n")
            (dest / "state" / "romp" / "names" / eid).write_text("%s\t%s\t%s\n" % (name, cwd, color))
            store_path = state_root / "goals" / (sid + ".json")
            store = {}
            if store_path.is_file():
                try:
                    store = json.loads(store_path.read_text(encoding="utf-8"))
                except ValueError:
                    store = {}
            before = store_before(store, cut_t) if store.get("nodes") else None
            if before is not None:                        # a session with no store yet starts the arm fresh (load_goals mints the shape)
                (dest / "state" / "romp" / "goals" / (eid + ".json")).write_text(json.dumps(before))
            ov = state_root / "overrides" / (sid + ".jsonl")
            if ov.is_file():
                kept = [l for l in ov.read_text(encoding="utf-8").splitlines() if l.strip()
                        and float((json.loads(l) if l.strip().startswith("{") else {}).get("t") or 0) <= cut_t]
                (dest / "state" / "romp" / "overrides" / (eid + ".jsonl")).write_text("".join(x + "\n" for x in kept))
            manifest["endings"].append({"id": eid, "session": hashlib.sha256(sid.encode()).hexdigest()[:12], "turn": k,
                                        "class": cls, "cutT": cut_t,
                                        "topsBefore": sorted(n for n, nd in (before or {"nodes": {}})["nodes"].items() if nd.get("parentId") is None)})
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
    load_source("romp_event_model", str(BIN / "romp-event-model"))
    jd = load_source(JUDGE_MODULE_NAME, str(BIN / "romp-judge"))   # a name of the run's own: the tests' shared-state guard
    return jd                                                        # watches the module named romp_judge


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
    results = {"arm": arm, "prompts": sorted(prompts), "endings": {}, "stopped": None}
    usage = jd.USAGE
    try:
        for e in manifest["endings"]:
            eid = e["id"]
            path = next(iter((corpus / "claude" / "projects").glob("*/%s.jsonl" % eid)), None)
            if path is None:
                continue
            seed_path = corpus / "state" / "romp" / "goals" / (eid + ".json")
            seed = seed_path.read_text() if seed_path.is_file() else None
            builds_out = []
            for _b in range(builds):
                target = state / "romp" / "goals" / (eid + ".json")             # the same store copy for every build
                if seed is None:
                    target.unlink(missing_ok=True)
                else:
                    target.write_text(seed)
                jd.parse_cache_clear()
                jd._plan_session(eid, str(path), now)
                store = jd.load_goals(eid)
                session = jd.parsed_session(eid, [str(path)], now)
                turns = session.get("turns") or []
                closed_turns = [t for t in turns if not jd._turn_open(t, turns)]
                if closed_turns:
                    jd._close_turn(store, closed_turns[-1])
                jd.rollup_status(store, jd._session_settled(eid, str(path), session, store, now=now), now=now)
                jd.save_goals(eid, store)
                jd._unblock_session(eid, str(path), now)
                store = jd.load_goals(eid)
                tops = {nid: column_of((store.get("status") or {}).get(nid))
                        for nid, nd in (store.get("nodes") or {}).items() if nd.get("parentId") is None}
                builds_out.append(tops)
            results["endings"][eid] = {"class": e["class"], "builds": builds_out}
            cost, n, _ = ledger_cost(usage)
            if budget_usd is not None and cost > budget_usd * BUDGET_OVERRUN:
                results["stopped"] = {"after": eid, "cost": round(cost, 4), "budget": budget_usd}
                break
    finally:
        restore_prompts(jd, saved)
    cost, n, mean_ms = ledger_cost(usage)
    results["cost"] = round(cost, 4); results["calls"] = n; results["callMsMean"] = round(mean_ms)
    arm_root.mkdir(parents=True, exist_ok=True)
    (arm_root / "results.json").write_text(json.dumps(results, indent=1))
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
def measure(manifest, results):
    """Per arm: leaks into Completed (an offer, question or undone ending with a top read completed), false interrupts
    (a finished ending with a top read needs_input), flaps (a top whose column differs between builds), cost."""
    classes = {e["id"]: e["class"] for e in manifest["endings"]}
    leaks = false_interrupts = flaps = 0
    for eid, r in results["endings"].items():
        cls = classes.get(eid, r.get("class"))
        builds = r["builds"]
        final = builds[-1] if builds else {}
        if cls in ("offer", "question", "undone") and any(c == "completed" for c in final.values()):
            leaks += 1
        if cls == "finished" and any(c == "needs_input" for c in final.values()):
            false_interrupts += 1
        if len(builds) >= 2:
            for nid in set(builds[0]) | set(builds[1]):
                if builds[0].get(nid) != builds[1].get(nid):
                    flaps += 1
    return {"arm": results["arm"], "endings": len(results["endings"]), "leaks": leaks, "falseInterrupts": false_interrupts,
            "flaps": flaps, "costUsd": results.get("cost", 0.0), "calls": results.get("calls", 0),
            "callMsMean": results.get("callMsMean", 0), "stopped": results.get("stopped")}


def report(corpus, run_root, figure=None):
    """The table (markdown, written beside the arms) and the figure (the cleanplots skill; skipped with a note when the
    library is absent). Counts and dollars only: nothing from the corpus."""
    corpus, run_root = Path(corpus), Path(run_root)
    manifest = json.loads((corpus / "manifest.json").read_text())
    rows = []
    for d in sorted(p for p in run_root.iterdir() if (p / "results.json").is_file()):
        rows.append(measure(manifest, json.loads((d / "results.json").read_text())))
    lines = ["| arm | endings | leaks into Completed | false interrupts | flaps | cost (USD) | calls | mean call ms | stopped |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append("| %s | %d | %d | %d | %d | %.2f | %d | %d | %s |" % (r["arm"], r["endings"], r["leaks"], r["falseInterrupts"],
                                                                        r["flaps"], r["costUsd"], r["calls"], r["callMsMean"],
                                                                        "yes" if r["stopped"] else "no"))
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
               ("flaps", "Cards that flap between builds"), ("costUsd", "Cost per pass (USD)")]
    f, axes = cp.fig(rows=1, cols=4, w=22, h=5)
    axes = list(axes.flat) if hasattr(axes, "flat") else list(axes)
    labels = [r["arm"] for r in rows]
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


# ── the command line ───────────────────────────────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build-corpus"); b.add_argument("--state-root", required=True); b.add_argument("--claude-root", required=True)
    b.add_argument("--dest", required=True); b.add_argument("--per-class", type=int, default=75)
    r = sub.add_parser("run"); r.add_argument("--corpus", required=True); r.add_argument("--run-root", required=True)
    r.add_argument("--arm", action="append", required=True, help="NAME or NAME=PROMPTS.json")
    r.add_argument("--budget-usd", type=float, default=None); r.add_argument("--claude-bin", default="claude"); r.add_argument("--now", type=int, default=None)
    ra = sub.add_parser("run-arm"); ra.add_argument("--corpus", required=True); ra.add_argument("--run-root", required=True)
    ra.add_argument("--arm", required=True); ra.add_argument("--prompts", default=None); ra.add_argument("--budget-usd", type=float, default=None)
    ra.add_argument("--claude-bin", default="claude"); ra.add_argument("--now", type=int, default=None)
    rp = sub.add_parser("report"); rp.add_argument("--corpus", required=True); rp.add_argument("--run-root", required=True); rp.add_argument("--figure", default=None)
    a = ap.parse_args(argv)
    if a.cmd == "build-corpus":
        m = build_corpus(a.state_root, a.claude_root, a.dest, per_class=a.per_class)
        counts = {c: sum(1 for e in m["endings"] if e["class"] == c) for c in CLASSES}
        print(json.dumps({"endings": len(m["endings"]), "byClass": counts}))
    elif a.cmd == "run":
        for spec in a.arm:
            name, _, prompts = spec.partition("=")
            res = run_arm(a.corpus, name, prompts or None, a.run_root, a.budget_usd, a.claude_bin, now=a.now)
            print(json.dumps({"arm": name, "endings": len(res["endings"]), "cost": res.get("cost"), "stopped": res.get("stopped")}))
    elif a.cmd == "run-arm":
        run_arm_inprocess(a.corpus, a.arm, a.prompts, a.run_root, a.budget_usd, a.claude_bin, now=a.now)
    elif a.cmd == "report":
        rows = report(a.corpus, a.run_root, figure=a.figure)
        print(json.dumps(rows, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
