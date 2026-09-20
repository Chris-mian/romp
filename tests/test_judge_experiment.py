#!/usr/bin/env python3
"""The judge prompt experiment's harness (plans/judge-prompt-experiments.md; scripts/judge_experiment.py) against a fake
`claude -p` that answers by the judge it sees in the system prompt and by a marker the candidate arm's prompt carries:
the corpus builder reads synthetic roots as files and writes only under its destination (a destination inside a git
checkout is refused, no transcript text reaches the manifest); an arm runs the planner, the closer and the unblocker over
copies and the measures read the placements (the baseline leaks every offer, question and undone item into Completed,
the candidate leaks none and interrupts no finished thread); the prompt swap reaches the calls and is restored; the
budget stops a run from its own ledger; the report writes the table with counts only. Every string invented."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPT = os.path.join(ROOT, "scripts", "judge_experiment.py")
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()          # hermetic before any romp load
os.environ.pop("ROMP_STATE_DIR", None)
os.makedirs(os.path.join(os.environ["XDG_STATE_HOME"], "romp"), exist_ok=True)
Path(os.environ["XDG_STATE_HOME"], "romp", "session-hosts").write_text("off")

T0 = 1_700_000_000
SIDS = ["11111111-2222-3333-4444-eeeeeeeeee%02d" % i for i in (1, 2)]

FAKE_CLAUDE = r'''#!/usr/bin/env python3
"""A fake `claude -p` for the harness tests: answers by the judge named in the system prompt and by the candidate marker.
Invented text only; the cost is fixed so the ledger sums predictably."""
import json, os, re, sys
args = sys.argv[1:]
if args and args[0] in ("-v", "--version"):
    print("2.1.0 (fake)"); sys.exit(0)
sysp = args[args.index("--system-prompt") + 1] if "--system-prompt" in args else ""
user = sys.stdin.read()
cand = "CANDIDATE-MARK" in sysp
log = os.environ.get("JE_TEST_LOG")
if log:
    with open(log, "a") as fh:
        fh.write(json.dumps({"candidate": cand, "head": sysp[:40]}) + "\n")
m = re.search(r"<(turn|segment)[^>]*>\n(.*?)\n</(turn|segment)", user, re.S)
text = m.group(2) if m else user
flag = bool(re.search(r"i can also|which option|not done", text, re.I))
menu = re.search(r"<open-goals[^>]*>\n(.*?)\n</open-goals", user, re.S)
menu_has = bool(menu and re.search(r"^\s*\d+\. ", menu.group(1), re.M))
if "turn-end auditor" in sysp:
    reply = ({"done": [], "block": [{"goal": 1, "why": "the go-ahead is owed"}]} if (cand and flag)
             else {"done": [{"goal": 1, "why": "delivered"}], "block": []})
elif "planner" in sysp[:120]:
    if not menu_has:
        reply = {"ops": [{"why": "the ask", "do": "mint", "text": "The synthetic goal"}]}
    elif cand and flag:
        reply = {"ops": [{"why": "the go-ahead is owed", "do": "block", "goal": 1}]}
    else:
        reply = {"ops": [{"why": "delivered", "do": "done", "goal": 1}]}
elif "marked blocked" in sysp:
    reply = {"verdicts": []}
else:
    reply = {"result": "ok"}
env = {"type": "result", "subtype": "success", "is_error": False, "duration_ms": 7, "duration_api_ms": 5, "num_turns": 1,
       "result": json.dumps(reply), "stop_reason": "end_turn", "session_id": "11111111-2222-4333-8444-555555555555",
       "total_cost_usd": 0.01, "usage": {"input_tokens": 10, "output_tokens": 5}}
print(json.dumps(env))
'''

ENDINGS = [  # (the user's ask, the assistant's last text, the class the heuristic must give it)
    ("please fix the flicker on the notes page", "Fixed the flicker: the list re-rendered on every tick. I can also add a test for it.", "offer"),
    ("pick the storage layout", "Two layouts fit. Which option do you prefer?", "question"),
    ("wire the export button", "Wired the button. The docs update is not done yet.", "undone"),
    ("add a test for the render count", "Added a test that pins the render count.", "finished"),
]


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def uline(sid, t, text, uid, parent=None):
    return {"type": "user", "timestamp": iso(t), "uuid": uid, "parentUuid": parent, "sessionId": sid, "cwd": "/TESTDIR",
            "promptSource": "typed", "message": {"role": "user", "content": text}}


def aline(sid, t, text, uid, parent):
    return {"type": "assistant", "timestamp": iso(t), "uuid": uid, "parentUuid": parent, "sessionId": sid, "cwd": "/TESTDIR",
            "message": {"role": "assistant", "content": [{"type": "text", "text": text}], "stop_reason": "end_turn"}}


class Harness(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.exists(SCRIPT), "the harness script exists (the base has none)")
        self.je = load_source("romp_judge_experiment", SCRIPT)
        self.td = tempfile.mkdtemp(prefix="romp-je-")
        self.addCleanup(shutil.rmtree, self.td, True)
        # the "live" roots the corpus builder reads as files: two sessions, two endings each
        self.state = Path(self.td, "live-state", "romp"); self.claude = Path(self.td, "live-claude")
        (self.state / "names").mkdir(parents=True); (self.state / "goals").mkdir(); (self.state / "overrides").mkdir()
        self.cwd = os.path.join(self.td, "proj"); os.makedirs(self.cwd)
        pdir = self.claude / "projects" / self.je.munge(self.cwd); pdir.mkdir(parents=True)
        self.texts = []
        for k, sid in enumerate(SIDS):
            recs, t, parent = [], T0 + k * 10000, None
            for j, (ask, answer, _cls) in enumerate(ENDINGS[k * 2:k * 2 + 2]):
                u, a = "u%d%d" % (k, j), "a%d%d" % (k, j)
                recs.append(uline(sid, t, ask, u, parent)); recs.append(aline(sid, t + 30, answer, a, u))
                parent = a; t += 600; self.texts.append(answer)
            (pdir / (sid + ".jsonl")).write_text("".join(json.dumps(r) + "\n" for r in recs))
            (self.state / "names" / sid).write_text("web\t%s\t#abcdef\n" % self.cwd)
            (self.state / "goals" / (sid + ".json")).write_text(json.dumps({"nodes": {}, "status": {}}))
            (self.state / "overrides" / (sid + ".jsonl")).write_text(json.dumps({"node": sid + ":g9", "op": "clear", "src": "user", "why": "x", "t": T0 + 10**6}) + "\n")
        self.fake = os.path.join(self.td, "fake_claude_p.py")
        Path(self.fake).write_text(FAKE_CLAUDE); os.chmod(self.fake, 0o755)
        self.log = os.path.join(self.td, "calls.log")
        os.environ["JE_TEST_LOG"] = self.log
        self.addCleanup(lambda: os.environ.pop("JE_TEST_LOG", None))

    def _tree_hash(self, root):
        h = hashlib.sha256()
        for p in sorted(Path(root).rglob("*")):
            if p.is_file():
                h.update(str(p.relative_to(root)).encode()); h.update(p.read_bytes())
        return h.hexdigest()

    def _corpus(self):
        dest = os.path.join(self.td, "corpus")
        m = self.je.build_corpus(self.state, self.claude, dest, per_class=10, now=T0 + 10**6)
        return dest, m

    def test_the_corpus_builder_writes_only_under_its_destination_and_classifies_the_endings(self):
        before = self._tree_hash(Path(self.td, "live-state")), self._tree_hash(self.claude)
        dest, m = self._corpus()
        self.assertEqual(sorted(e["class"] for e in m["endings"]), sorted(c for _, _, c in ENDINGS), "each ending in its class")
        self.assertEqual((self._tree_hash(Path(self.td, "live-state")), self._tree_hash(self.claude)), before, "the live roots are read, never written")
        manifest = Path(dest, "manifest.json").read_text()
        for text in self.texts:
            self.assertNotIn(text[:24], manifest, "no transcript text reaches the manifest")
        for sid in SIDS:
            self.assertNotIn(sid, manifest, "the session ids are hashed, not copied")
        written = [str(p.relative_to(dest)) for p in Path(dest).rglob("*") if p.is_file()]
        self.assertTrue(all(w.startswith(("claude/", "state/")) or w == "manifest.json" for w in written), written)
        eid = m["endings"][0]["id"]
        self.assertTrue(list(Path(dest, "claude", "projects").glob("*/%s.jsonl" % eid)), "each ending is its own truncated transcript")
        self.assertTrue(Path(dest, "state", "romp", "names", eid).exists(), "each ending has its names entry")
        self.assertEqual(Path(dest, "state", "romp", "session-hosts").read_text(), "off")
        cut = [e for e in m["endings"] if e["turn"] == 0][0]["cutT"]
        ov = Path(dest, "state", "romp", "overrides", cut and [e for e in m["endings"] if e["turn"] == 0][0]["id"] + ".jsonl")
        self.assertEqual(ov.read_text(), "", "an override journaled after the cut is not part of the ending")
        inside = os.path.join(self.td, "repo", "sub"); os.makedirs(os.path.join(self.td, "repo", ".git")); os.makedirs(inside)
        with self.assertRaises(SystemExit, msg="a destination inside a git checkout is refused"):
            self.je.build_corpus(self.state, self.claude, inside, per_class=10)
        self.assertFalse(list(Path(inside).rglob("*")), "and nothing was written there")

    def test_an_arm_runs_the_judges_on_copies_and_the_measures_read_the_placements(self):
        dest, m = self._corpus()
        corpus_before = self._tree_hash(dest)
        run_root = os.path.join(self.td, "runs")
        cand = os.path.join(self.td, "candidate.json")
        Path(cand).write_text(json.dumps({"CLOSER_SYS": "CANDIDATE-MARK You are a turn-end auditor in a logging pipeline.",
                                          "PLAN_SYS": "CANDIDATE-MARK You are a planner in a logging pipeline."}))
        base = self.je.run_arm(dest, "current", None, run_root, None, self.fake, now=T0 + 10**6)
        cand_res = self.je.run_arm(dest, "candidate", cand, run_root, None, self.fake, now=T0 + 10**6)
        self.assertEqual(self._tree_hash(dest), corpus_before, "the corpus is copied, never written")
        mb, mc = self.je.measure(m, base), self.je.measure(m, cand_res)
        self.assertEqual((mb["endings"], mb["leaks"], mb["falseInterrupts"], mb["flaps"]), (4, 3, 0, 0),
                         "the current prompt files the offer, the question and the undone item as done: three leaks, no false interrupt, no flap: %r" % mb)
        self.assertEqual((mc["endings"], mc["leaks"], mc["falseInterrupts"], mc["flaps"]), (4, 0, 0, 0),
                         "the candidate blocks all three and leaves the finished thread alone: %r" % mc)
        self.assertGreater(mb["costUsd"], 0, "the cost comes from the arm's own ledger")
        self.assertEqual(mb["calls"], round(mb["costUsd"] / 0.01), "one fixed-cost row per call")
        finished = [e["id"] for e in m["endings"] if e["class"] == "finished"][0]
        self.assertTrue(all(c == "completed" for c in cand_res["endings"][finished]["builds"][-1].values()), "the finished thread reads completed")
        offer = [e["id"] for e in m["endings"] if e["class"] == "offer"][0]
        self.assertTrue(all(c == "needs_input" for c in cand_res["endings"][offer]["builds"][-1].values()), "the offer reads needs_input")
        self.assertIsNone(base["stopped"])
        self.assertTrue(Path(run_root, "current", "results.json").exists() and Path(run_root, "candidate", "results.json").exists())

    def test_the_prompt_swap_reaches_the_calls_and_the_module_is_restored(self):
        dest, m = self._corpus()
        run_root = os.path.join(self.td, "runs")
        cand = os.path.join(self.td, "candidate.json")
        Path(cand).write_text(json.dumps({"CLOSER_SYS": "CANDIDATE-MARK You are a turn-end auditor in a logging pipeline."}))
        saved_env = dict(os.environ)
        try:
            self.je.run_arm_inprocess(dest, "inproc", cand, run_root, None, self.fake, now=T0 + 10**6, builds=1)
            jd = sys.modules[self.je.JUDGE_MODULE_NAME]
            self.assertNotIn("CANDIDATE-MARK", jd.CLOSER_SYS, "the module attribute is restored after the run")
            self.assertIn("turn-end auditor", jd.CLOSER_SYS)
        finally:
            os.environ.clear(); os.environ.update(saved_env)
        rows = [json.loads(l) for l in Path(self.log).read_text().splitlines() if l.strip()]
        self.assertTrue(rows, "the fake was called")
        closer = [r for r in rows if "auditor" in r["head"] or r["candidate"]]
        self.assertTrue(closer and all(r["candidate"] for r in closer), "every closer call carried the candidate's prompt: %r" % rows[:4])
        with self.assertRaises(SystemExit):
            self.je.apply_prompts(jd, {"NOT_A_PROMPT": "x"})

    def test_the_budget_stops_the_run_from_its_own_ledger(self):
        dest, m = self._corpus()
        run_root = os.path.join(self.td, "runs")
        res = self.je.run_arm(dest, "tight", None, run_root, 0.005, self.fake, now=T0 + 10**6)
        self.assertIsNotNone(res["stopped"], "past a fifth over the budget the run stops")
        self.assertLess(len(res["endings"]), 4, "before every ending ran")
        self.assertGreater(res["stopped"]["cost"], 0.005 * self.je.BUDGET_OVERRUN)

    def test_the_report_writes_the_table_from_the_results_with_counts_only(self):
        dest, m = self._corpus()
        run_root = os.path.join(self.td, "runs")
        self.je.run_arm(dest, "current", None, run_root, None, self.fake, now=T0 + 10**6)
        rows = self.je.report(dest, run_root, figure=None)
        table = Path(run_root, "table.md").read_text()
        self.assertEqual([r["arm"] for r in rows], ["current"])
        self.assertIn("| current | 4 | 3 | 0 | 0 |", table)
        for text in self.texts:
            self.assertNotIn(text[:24], table)
        self.assertNotIn("The synthetic goal", table, "no goal title in the report")
        out = subprocess.run([sys.executable, SCRIPT, "report", "--corpus", dest, "--run-root", run_root], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr[-500:])
        self.assertIn('"leaks": 3', out.stdout)


if __name__ == "__main__":
    unittest.main()
