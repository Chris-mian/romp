#!/usr/bin/env python3
"""The judge prompt experiment's harness (plans/judge-prompt-experiments.md; scripts/judge_experiment.py) against a fake
`claude -p` that answers by the judge it sees in the system prompt and by a marker the candidate arm's prompt carries. The
corpus builder reads synthetic roots as files and writes only under its destination; a store the live judges wrote is cut to
the ending's turn start and re-keyed to the ending id, so the arm plans the turn once and inherits nothing from after the
cut; the measures score only the ending's own cards; a failed call marks the row not comparable; the closer sees the goal
history; the prompt swap reaches the calls and is restored; the budget stops a run past a fifth over; the labeller reads tier
one from the journals and gates on the agreement; the report writes counts only. Every string invented."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from romp_load import load_source

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
BIN = os.path.join(ROOT, "bin")
SCRIPT = os.path.join(ROOT, "scripts", "judge_experiment.py")
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()          # hermetic before any romp load
os.environ.pop("ROMP_STATE_DIR", None)
os.makedirs(os.path.join(os.environ["XDG_STATE_HOME"], "romp"), exist_ok=True)
Path(os.environ["XDG_STATE_HOME"], "romp", "session-hosts").write_text("off")
em = load_source("romp_event_model", os.path.join(BIN, "romp-event-model"))   # the shared event model an in-process arm must leave alone

T0 = 1_700_000_000
SIDS = ["11111111-2222-3333-4444-eeeeeeeeee%02d" % i for i in (1, 2)]

FAKE_CLAUDE = r'''#!/usr/bin/env python3
"""A fake `claude -p` for the harness tests: answers by the judge named in the system prompt and by the candidate marker; with
JE_TEST_PROSE set, a candidate-marked prompt gets a sentence of prose no parser accepts. Invented text only; a fixed cost."""
import json, os, re, sys
args = sys.argv[1:]
if args and args[0] in ("-v", "--version"):
    print("2.1.0 (fake)"); sys.exit(0)
sysp = args[args.index("--system-prompt") + 1] if "--system-prompt" in args else ""
user = sys.stdin.read()
cand = "CANDIDATE-MARK" in sysp
judge = ("labeller" if "You classify the final assistant message" in sysp else "closer" if "turn-end auditor" in sysp
         else "planner" if "planner" in sysp[:120] else "unblocker" if "marked blocked" in sysp else "other")
log = os.environ.get("JE_TEST_LOG")
if log:
    with open(log, "a") as fh:
        fh.write(json.dumps({"judge": judge, "candidate": cand, "head": sysp[:40], "goalHistory": "<goal-history" in user,
                             "menu": (re.search(r"<open-goals[^>]*>\n(.*?)\n</open-goals", user, re.S) or [None, ""])[1] if judge == "planner" else None}) + "\n")
m = re.search(r"<(turn|segment|message)[^>]*>\n(.*?)\n</(turn|segment|message)", user, re.S)
text = m.group(2) if m else user
flag = bool(re.search(r"i can also|which option|not done", text, re.I))
menu = re.search(r"<open-goals[^>]*>\n(.*?)\n</open-goals", user, re.S)
menu_has = bool(menu and re.search(r"^\s*\d+\. ", menu.group(1), re.M))
if cand and os.environ.get("JE_TEST_PROSE"):
    reply_text = "I would rather not say in the shape you asked for."
elif judge == "labeller":
    cls = ("offer" if re.search(r"i can also", text, re.I) else "question" if re.search(r"which option", text, re.I)
           else "undone" if re.search(r"not done", text, re.I) else "finished")
    reply_text = json.dumps({"class": cls, "why": "synthetic"})
elif judge == "closer":
    reply_text = json.dumps({"done": [], "block": [{"goal": 1, "why": "the go-ahead is owed"}]} if (cand and flag)
                            else {"done": [{"goal": 1, "why": "delivered"}], "block": []})
elif judge == "planner":
    if not menu_has:
        reply_text = json.dumps({"ops": [{"why": "the ask", "do": "mint", "text": "The synthetic goal"}]})
    elif cand and flag:
        reply_text = json.dumps({"ops": [{"why": "the go-ahead is owed", "do": "block", "goal": 1}]})
    else:
        reply_text = json.dumps({"ops": [{"why": "delivered", "do": "done", "goal": 1}]})
elif judge == "unblocker":
    reply_text = json.dumps({"verdicts": []})
else:
    reply_text = json.dumps({"result": "ok"})
env = {"type": "result", "subtype": "success", "is_error": False, "duration_ms": 7, "duration_api_ms": 5, "num_turns": 1,
       "result": reply_text, "stop_reason": "end_turn", "session_id": "11111111-2222-4333-8444-555555555555",
       "total_cost_usd": 0.01, "usage": {"input_tokens": 10, "output_tokens": 5}}
print(json.dumps(env))
'''

ENDINGS = [  # (the user's ask, the assistant's last text, the class the heuristic must give it)
    ("please fix the flicker on the notes page", "Fixed the flicker: the list re-rendered on every tick. I can also add a test for it.", "offer"),
    ("pick the storage layout", "Two layouts fit. Which option do you prefer?", "question"),
    ("wire the export button", "Wired the button. The docs update is not done yet.", "undone"),
    ("add a test for the render count", "Added a test that pins the render count.", "finished"),
]

# a judge-shaped seed the way the live judges write one: run the judge module itself over the synthetic roots with the fake
JUDGE_WRITER = r'''
import json, os, sys
sys.path.insert(0, os.path.join(os.environ["JE_ROOT"], "tests"))
from romp_load import load_source
load_source("romp_event_model", os.path.join(os.environ["JE_ROOT"], "bin", "romp-event-model"))
jd = load_source("romp_judge_seed_writer", os.path.join(os.environ["JE_ROOT"], "bin", "romp-judge"))
now = int(os.environ["JE_NOW"])
for sid in os.environ["JE_SIDS"].split(","):
    fsid, path, anchor, name = next(x for x in jd.discover(now, window=10**9) if x[0] == sid)
    jd._plan_session(fsid, str(path), now)
    store = jd.load_goals(fsid)
    session = jd.parsed_session(fsid, [str(path)], now)
    turns = session.get("turns") or []
    seg_by_id = {seg["id"]: seg for t in turns for seg in jd._segs(t, store)}
    for t in turns:
        if not jd._turn_open(t, turns):
            jd._close_turn(store, t, seg_by_id=seg_by_id)
    jd.rollup_status(store, True, now=now)
    jd.save_goals(fsid, store)
print("ok")
'''


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def uline(sid, t, text, uid, parent=None, blocks=False):
    content = [{"type": "text", "text": text}] if blocks else text
    return {"type": "user", "timestamp": iso(t), "uuid": uid, "parentUuid": parent, "sessionId": sid, "cwd": "/TESTDIR",
            "promptSource": "sdk" if blocks else "typed", "message": {"role": "user", "content": content}}


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
        self.live = Path(self.td, "live-state")
        self.state = self.live / "romp"; self.claude = Path(self.td, "live-claude")
        for sub in ("names", "goals", "overrides", "sdk", "states", "episodes"):
            (self.state / sub).mkdir(parents=True)
        (self.state / "session-hosts").write_text("off")
        self.cwd = os.path.join(self.td, "proj"); os.makedirs(self.cwd)
        self.pdir = self.claude / "projects" / self.je.munge(self.cwd); self.pdir.mkdir(parents=True)
        self.texts = []
        for k, sid in enumerate(SIDS):
            recs, t, parent = [], T0 + k * 10000, None
            for j, (ask, answer, _cls) in enumerate(ENDINGS[k * 2:k * 2 + 2]):
                u, a = "u%d%d" % (k, j), "a%d%d" % (k, j)
                recs.append(uline(sid, t, ask, u, parent)); recs.append(aline(sid, t + 30, answer, a, u))
                parent = a; t += 600; self.texts.append(answer)
            (self.pdir / (sid + ".jsonl")).write_text("".join(json.dumps(r) + "\n" for r in recs))
            (self.state / "names" / sid).write_text("web\t%s\t#abcdef\n" % self.cwd)
            (self.state / "overrides" / (sid + ".jsonl")).write_text(json.dumps({"node": sid + ":g9", "op": "clear", "src": "user", "why": "x", "t": T0 + 10**6}) + "\n")
        self.fake = os.path.join(self.td, "fake_claude_p.py")
        Path(self.fake).write_text(FAKE_CLAUDE); os.chmod(self.fake, 0o755)
        self.log = os.path.join(self.td, "calls.log")
        os.environ["JE_TEST_LOG"] = self.log
        self.addCleanup(lambda: os.environ.pop("JE_TEST_LOG", None))
        self.addCleanup(lambda: os.environ.pop("JE_TEST_PROSE", None))

    # ── helpers ──
    def _tree_hash(self, root):
        h = hashlib.sha256()
        for p in sorted(Path(root).rglob("*")):
            if p.is_file():
                h.update(str(p.relative_to(root)).encode()); h.update(p.read_bytes())
        return h.hexdigest()

    def _corpus(self, per_class=10, name="corpus"):
        dest = os.path.join(self.td, name)
        m = self.je.build_corpus(self.state, self.claude, dest, per_class=per_class, now=T0 + 10**6)
        return dest, m

    def _calls(self, judge=None):
        rows = [json.loads(l) for l in Path(self.log).read_text().splitlines() if l.strip()] if os.path.exists(self.log) else []
        return [r for r in rows if judge is None or r["judge"] == judge]

    def _clear_log(self):
        Path(self.log).write_text("")

    def _judge_written_stores(self):
        """The live judges' own stores over the synthetic sessions (the judge module, the fake as its model): what a real root holds."""
        env = dict(os.environ, XDG_STATE_HOME=str(self.live), CLAUDE_CONFIG_DIR=str(self.claude), ROMP_CLAUDE_BIN=self.fake,
                   JE_ROOT=ROOT, JE_NOW=str(T0 + 10**6), JE_SIDS=",".join(SIDS), ROMP_POSTAL_CLIENT_ONLY="1")
        env.pop("ROMP_STATE_DIR", None)
        out = subprocess.run([sys.executable, "-c", JUDGE_WRITER], env=env, capture_output=True, text=True, timeout=600)
        self.assertEqual(out.returncode, 0, out.stderr[-1500:])
        stores = {sid: json.loads((self.state / "goals" / (sid + ".json")).read_text()) for sid in SIDS}
        self._clear_log()
        return stores

    def _ending(self, m, sid, turn):
        return [e for e in m["endings"] if e["session"] == hashlib.sha256(sid.encode()).hexdigest()[:12] and e["turn"] == turn][0]

    # ── the corpus ──
    def test_the_corpus_builder_writes_only_under_its_destination_and_classifies_each_ending(self):
        before = self._tree_hash(self.live), self._tree_hash(self.claude)
        dest, m = self._corpus()
        self.assertEqual(len(m["endings"]), 4)
        for k, sid in enumerate(SIDS):
            for j in range(2):
                self.assertEqual(self._ending(m, sid, j)["class"], ENDINGS[k * 2 + j][2], "each ending in its own class")
        self.assertEqual((self._tree_hash(self.live), self._tree_hash(self.claude)), before, "the live roots are read, never written")
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
        self.assertEqual(m.get("skipped"), {"no-transcript": 0, "few-turns": 0, "unreadable-names-entry": 0}, "skips are counted, never named")
        # the journal is cut at the turn's start: a row before it stays, in the ending's own re-keyed journal; a later one goes
        e0 = self._ending(m, SIDS[0], 0)
        (self.state / "overrides" / (SIDS[0] + ".jsonl")).write_text(
            json.dumps({"node": SIDS[0] + ":g9", "op": "followup", "t": e0["startT"] - 100}) + "\n"
            + json.dumps({"node": SIDS[0] + ":g9", "op": "clear", "src": "user", "why": "x", "t": e0["cutT"] + 5}) + "\n")
        dest2, m2 = self._corpus(name="corpus2")
        e0 = self._ending(m2, SIDS[0], 0)
        rows = [json.loads(l) for l in Path(dest2, "state", "romp", "overrides", e0["id"] + ".jsonl").read_text().splitlines()]
        self.assertEqual([(r["op"], r["node"]) for r in rows], [("followup", e0["id"] + ":g9")], "the pre-cut row, re-keyed to the ending; the later clear gone")
        inside = os.path.join(self.td, "repo", "sub"); os.makedirs(os.path.join(self.td, "repo", ".git")); os.makedirs(inside)
        with self.assertRaises(SystemExit, msg="a destination inside a git checkout is refused"):
            self.je.build_corpus(self.state, self.claude, inside, per_class=10)
        self.assertFalse(list(Path(inside).rglob("*")), "and nothing was written there")

    def test_the_selection_caps_each_class_spreads_across_sessions_and_prefers_endings_the_judges_completed(self):
        # a third session with three offers, newest last; the first session's offer (turn 0) is the only one the judges completed
        sid3 = "11111111-2222-3333-4444-eeeeeeeeee03"
        recs, t, parent = [], T0 + 50000, None
        for j in range(3):
            recs.append(uline(sid3, t, "ask %d" % j, "u3%d" % j, parent)); recs.append(aline(sid3, t + 30, "Done %d. I can also tidy the names." % j, "a3%d" % j, "u3%d" % j))
            parent = "a3%d" % j; t += 600
        (self.pdir / (sid3 + ".jsonl")).write_text("".join(json.dumps(r) + "\n" for r in recs))
        (self.state / "names" / sid3).write_text("api\t%s\t#abcdef\n" % self.cwd)
        m_all = self._corpus(per_class=10, name="all")[1]
        self.assertEqual(sum(1 for e in m_all["endings"] if e["class"] == "offer"), 4, "one offer in the first session, three in the third")
        e0 = self._ending(m_all, SIDS[0], 0)
        self._live_store_with_done(SIDS[0], e0["startT"], e0["cutT"], [])
        m1 = self._corpus(per_class=1, name="one")[1]
        offers = [e for e in m1["endings"] if e["class"] == "offer"]
        self.assertEqual([(e["session"], e["turn"], e["tierOneEligible"]) for e in offers],
                         [(hashlib.sha256(SIDS[0].encode()).hexdigest()[:12], 0, True)],
                         "the cap holds one per class, and the eligible offer wins the slot over the three newer ones the judges never ruled on")
        m2 = self._corpus(per_class=2, name="two")[1]
        offers = sorted((e["session"], e["turn"]) for e in m2["endings"] if e["class"] == "offer")
        self.assertEqual(len(offers), 2)
        self.assertEqual(len({s for s, _ in offers}), 2, "two slots go to two sessions before a second ending of one: %r" % offers)
        self.assertTrue(all("tierOneEligible" in e and "startT" in e for e in m2["endings"]))

    def test_sdk_composer_prompts_end_turns_too(self):
        sid = SIDS[0]
        recs = [uline(sid, T0, "first ask", "u1", None, blocks=True), aline(sid, T0 + 30, "First answer.", "a1", "u1"),
                {"type": "user", "timestamp": iso(T0 + 40), "uuid": "t1", "parentUuid": "a1", "sessionId": sid, "cwd": "/TESTDIR",
                 "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "x", "content": "ok"}]}},
                aline(sid, T0 + 50, "Continued after the tool.", "a2", "t1"),
                {"type": "user", "timestamp": iso(T0 + 60), "uuid": "m1", "parentUuid": "a2", "sessionId": sid, "isMeta": True,
                 "message": {"role": "user", "content": "a skill's markdown nobody typed"}},
                uline(sid, T0 + 600, "second ask", "u2", "a2", blocks=True), aline(sid, T0 + 630, "Second answer.", "a3", "u2")]
        ends = self.je.turn_ends(recs)
        self.assertEqual([recs[i]["uuid"] for i in ends], ["a2", "a3"], "the tool result and the meta record end nothing; the composer's text-block prompt does")
        self.assertEqual(self.je.turn_start(recs, ends[0]), T0)
        self.assertEqual(self.je.turn_start(recs, ends[1]), T0 + 600)

    def test_the_registry_names_the_leaf_transcripts_too(self):
        sid = SIDS[0]; leaf = "11111111-2222-3333-4444-ffffffffff01"
        (self.state / "sdk" / (sid + ".json")).write_text(json.dumps({"sid": sid, "lastSid": leaf}))
        (self.state / "episodes" / (sid + ".jsonl")).write_text(json.dumps({"fsid": "11111111-2222-3333-4444-ffffffffff02"}) + "\n")
        (self.state / "states" / (sid + ".jsonl")).write_text(json.dumps({"resumeFork": {"from": "11111111-2222-3333-4444-ffffffffff03", "to": leaf}}) + "\n")
        fsids = getattr(self.je, "known_fsids", None)
        self.assertIsNotNone(fsids, "the builder reads the registry's transcripts (the base read the sid's own only)")
        self.assertEqual(fsids(self.state, sid), {sid, leaf, "11111111-2222-3333-4444-ffffffffff02", "11111111-2222-3333-4444-ffffffffff03"})
        recs = [uline(leaf, T0 + 90000, "after the clear", "u1"), aline(leaf, T0 + 90030, "Cleared and continued. Which option do you prefer?", "a1", "u1"),
                uline(leaf, T0 + 90600, "one more", "u2", "a1"), aline(leaf, T0 + 90630, "Done.", "a2", "u2")]
        (self.pdir / (leaf + ".jsonl")).write_text("".join(json.dumps(r) + "\n" for r in recs))
        m = self._corpus(name="leaves")[1]
        h = hashlib.sha256(sid.encode()).hexdigest()[:12]
        self.assertEqual(sum(1 for e in m["endings"] if e["session"] == h), 4, "the leaf's two endings join the anchor's two under the same session")
        self.assertNotIn(leaf, Path(os.path.join(self.td, "leaves", "manifest.json")).read_text())

    # ── the store cut ──
    def _live_store_with_done(self, sid, start_t, cut_t, later_ops):
        """A live store in the judges' own shape: one top the planner minted from the ending's turn (its prompt-run placement at the
        turn's start) and one older top, the closer's done on the older one at the cut, later verdicts, and the user's later
        gestures in the journal."""
        seg0 = "%s:%d:aaaaaaaa" % (sid, start_t - 5000); segp = "%s:%d:bbbbbbbb" % (sid, start_t); segl = "%s:%d:cccccccc" % (sid, cut_t + 3000)
        old = {"id": sid + ":g1", "text": "The older goal", "parentId": None, "t": start_t - 5000, "mt": cut_t + 5000, "nodeComplete": True,
               "blocked": False, "cleared": False, "doneWhy": "synthetic", "settledDone": True, "settledAt": cut_t + 9, "rolledUp": False,
               "trail": [seg0, segp, segl], "blockCheckT": cut_t + 700, "closerLookT": start_t - 4000,
               "log": [{"ev_t": start_t - 5000, "at": start_t - 4999, "src": "planner", "kind": "mint"},
                       {"ev_t": start_t - 4000, "at": start_t - 3999, "src": "planner", "kind": "block", "why": "synthetic"},
                       {"ev_t": cut_t + 2, "at": cut_t + 9, "src": "closer", "kind": "done", "why": "synthetic"},
                       {"ev_t": cut_t + 4000, "at": cut_t + 4001, "src": "closer", "kind": "block", "why": "synthetic later"}]}
        new = {"id": sid + ":g2", "text": "The turn's own goal", "parentId": None, "t": start_t, "mt": cut_t + 10, "nodeComplete": True,
               "blocked": False, "cleared": False, "doneWhy": "synthetic", "trail": [segp],
               "log": [{"ev_t": start_t, "at": start_t + 1, "src": "planner", "kind": "mint"},
                       {"ev_t": cut_t, "at": cut_t + 8, "src": "closer", "kind": "done", "why": "synthetic"}]}
        sub_later = {"id": sid + ":g3", "text": "A sub of the later turn", "parentId": sid + ":g2", "t": cut_t + 3000, "trail": [segl], "log": []}
        store = {"rompUuid": sid, "seq": 3, "nodes": {old["id"]: old, new["id"]: new, sub_later["id"]: sub_later},
                 "status": {old["id"]: "completed", new["id"]: "completed"}, "placementsV": 14, "rev": 4, "lastNode": sub_later["id"],
                 "placements": {seg0: old["id"], segp + "#p": new["id"], segp: new["id"], segl: sub_later["id"]},
                 "closedTurns": ["%s:%d:dddddddd" % (sid, start_t - 4990), "%s:%d:eeeeeeee" % (sid, start_t), "%s:%d:ffffffff" % (sid, cut_t + 3000)],
                 "closedSig": {"%s:%d:dddddddd" % (sid, start_t - 4990): "x", "%s:%d:eeeeeeee" % (sid, start_t): "y"}}
        (self.state / "goals" / (sid + ".json")).write_text(json.dumps(store))
        (self.state / "overrides" / (sid + ".jsonl")).write_text("".join(json.dumps(o) + "\n" for o in later_ops))
        return store

    def test_the_store_copy_is_cut_at_the_turns_start_and_keyed_to_the_ending(self):
        """The reviews of the harness (2026-09-21): a filter on `t` kept every verdict (the logs carry ev_t and at); the cut at the
        turn's END kept the live planner's node from the ending's own turn and the closer's verdict on it; the seed kept the
        session id, so no placement matched the arm's segment ids and the planner re-planned the history; the sealing fields
        sealed the seeded top out of the menu and a twin was minted; gate stamps from after the cut hid a node from the
        unblocker. The copy is now the store as the judges held it when the turn opened, keyed for the arm."""
        sid = SIDS[0]
        m = self._corpus()[1]
        e = self._ending(m, sid, 0)
        start, cut = float(e["startT"]), float(e["cutT"])
        store = self._live_store_with_done(sid, start, cut, [])
        eid = e["id"]
        try:
            before = self.je.store_before(store, cut, start, eid)
        except TypeError:
            self.fail("store_before takes the turn's start and the ending id (the base cut at the turn's end under the session id)")
        self.assertEqual(before["rompUuid"], eid)
        self.assertNotIn(sid, json.dumps(before), "every id prefix is the ending's now")
        g1, g2 = before["nodes"].get(eid + ":g1"), before["nodes"].get(eid + ":g2")
        self.assertEqual(sorted(before["nodes"]), [eid + ":g1", eid + ":g2"], "the older top and the turn's own prompt-run node; the later sub is gone")
        self.assertEqual([ev["kind"] for ev in g1["log"]], ["mint", "block"], "the done filed at the cut and the later block are gone: %r" % g1["log"])
        self.assertEqual([ev["kind"] for ev in g2["log"]], ["mint"], "the turn's own node keeps its mint and nothing the turn's judging wrote")
        for field in ("nodeComplete", "doneWhy", "settledDone", "settledAt", "rolledUp"):
            self.assertNotIn(field, g1, field)
        self.assertNotIn("blockCheckT", g1, "a gate stamp from after the cut is dropped"); self.assertIn("closerLookT", g1, "one from before stays")
        self.assertEqual(g1["trail"], ["%s:%d:aaaaaaaa" % (eid, start - 5000)], "the older top's trail: the segment before the turn, re-keyed; the turn's own segment is not its")
        self.assertEqual(g2["trail"], ["%s:%d:bbbbbbbb" % (eid, start)], "the turn's own node keeps the segment that minted it")
        self.assertEqual(sorted(before["placements"]), sorted(["%s:%d:aaaaaaaa" % (eid, start - 5000), "%s:%d:bbbbbbbb#p" % (eid, start)]),
                         "the older placement and the turn's prompt-run; the turn's own work-run placement dropped so the arm plans it once")
        self.assertEqual(before["closedTurns"], ["%s:%d:dddddddd" % (eid, start - 4990)]); self.assertEqual(list(before["closedSig"]), ["%s:%d:dddddddd" % (eid, start - 4990)])
        self.assertEqual(before["status"], {}); self.assertNotIn("lastNode", before, "the last node pointed at a dropped node")
        self.assertLessEqual(g1["mt"], cut)
        self.assertEqual(self.je.event_time({"ev_t": 5, "at": 9}), 5); self.assertEqual(self.je.event_time({"at": 9}), 9)
        self.assertEqual(self.je.id_epoch("%s:1700000000:abcdef12#p" % sid), 1700000000.0); self.assertIsNone(self.je.id_epoch("g1"))
        # through the builder: the manifest names the tops by suffix, never by the session id
        m2 = self._corpus(name="corpus-seeded")[1]
        e2 = self._ending(m2, sid, 0)
        self.assertEqual(e2["topsBefore"], ["g1", "g2"])
        self.assertNotIn(sid, Path(os.path.join(self.td, "corpus-seeded", "manifest.json")).read_text())

    def test_a_judge_written_store_re_keyed_plans_the_turn_once_and_mints_no_twin(self):
        """Executed by the reviewer on a store the live planner wrote: 0 seed keys matched, the planner ran 1, 2, 3 times for the
        three endings, and a twin top was minted beside the sealed seeded one. Now one planner call and no twin per ending per
        build, over the judges' own stores."""
        stores = self._judge_written_stores()
        self.assertTrue(all(st["nodes"] and len(st["placements"]) == 2 for st in stores.values()),
                        "the live judges wrote real stores: a node and a placement per turn: %r" % {k: (len(v["nodes"]), len(v["placements"])) for k, v in stores.items()})
        dest, m = self._corpus(name="corpus-judged")
        run_root = os.path.join(self.td, "runs")
        res = self.je.run_arm(dest, "current", None, run_root, None, self.fake, now=T0 + 10**6)
        planner = self._calls("planner")
        self.assertEqual(len(planner), 4 * 2, "one planner call per ending per build over four endings and two builds: %d" % len(planner))
        for eid, r in res["endings"].items():
            e = next(x for x in m["endings"] if x["id"] == eid)
            for build in r["builds"]:
                scored = [n for n, v in build.items() if v["scored"]]
                self.assertEqual(len(scored), 1, "the turn's own card, one per ending, no twin: %r" % build)
                self.assertEqual(len(build), 1, "no twin top beside the seeded one (the fake's same-titled mint lands on it): %r" % build)
        self.assertEqual(res["failures"], 0)

    # ── the arms and the measures ──
    def test_an_arm_runs_the_judges_on_copies_and_the_measures_read_the_endings_own_cards(self):
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
        self.assertEqual((mb["endings"], mb["leaks"], mb["falseInterrupts"], mb["flaps"], mb.get("comparable")), (4, 3, 0, 0, True),
                         "the current prompt files the offer, the question and the undone item as done: three leaks: %r" % mb)
        self.assertEqual((mc["endings"], mc["leaks"], mc["falseInterrupts"], mc["flaps"], mc.get("comparable")), (4, 0, 0, 0, True),
                         "the candidate blocks all three and leaves the finished thread alone: %r" % mc)
        self.assertGreater(mb["costUsd"], 0); self.assertEqual(mb["calls"], round(mb["costUsd"] / 0.01), "one fixed-cost row per call")
        finished = [e["id"] for e in m["endings"] if e["class"] == "finished"][0]
        offer = [e["id"] for e in m["endings"] if e["class"] == "offer"][0]
        self.assertEqual({v["column"] for v in cand_res["endings"][finished]["builds"][-1].values() if v["scored"]}, {"completed"})
        self.assertEqual({v["column"] for v in cand_res["endings"][offer]["builds"][-1].values() if v["scored"]}, {"needs_input"})
        self.assertIsNone(base["stopped"])
        closer = self._calls("closer")
        self.assertTrue(closer and all(r["goalHistory"] for r in closer), "every closer call carried the goal-history section production sends: %r" % closer[:2])

    def test_the_measures_score_only_the_endings_own_cards_and_count_flaps_and_interrupts(self):
        manifest = {"endings": [{"id": "e1", "class": "finished"}, {"id": "e2", "class": "offer"}, {"id": "e3", "class": "finished"}]}
        results = {"arm": "x", "failures": 0, "endings": {
            "e1": {"class": "finished", "builds": [{"g1": {"column": "needs_input", "scored": False}, "g2": {"column": "completed", "scored": True}},
                                                   {"g1": {"column": "needs_input", "scored": False}, "g2": {"column": "completed", "scored": True}}]},
            "e2": {"class": "offer", "builds": [{"g1": {"column": "completed", "scored": False}, "g2": {"column": "needs_input", "scored": True}},
                                                {"g1": {"column": "completed", "scored": False}, "g2": {"column": "working", "scored": True}}]},
            "e3": {"class": "finished", "builds": [{"g1": {"column": "needs_input", "scored": True}}, {"g1": {"column": "needs_input", "scored": True}}]}}}
        mm = self.je.measure(manifest, results)
        self.assertEqual((mm["leaks"], mm["falseInterrupts"], mm["flaps"]), (0, 1, 1),
                         "the inherited blocked and completed cards count nothing; the finished ending's own blocked card is the one false interrupt; "
                         "the offer's own card that read needs_input then working is the one flap: %r" % mm)
        old = {"arm": "old", "endings": {"e2": {"class": "offer", "builds": [{"g1": "completed"}, {"g1": "completed"}]}}}
        self.assertEqual(self.je.measure(manifest, old)["leaks"], 1, "an older results file counts every card")

    def test_a_failed_call_or_a_rejected_reply_marks_the_row_not_comparable(self):
        """Executed by the reviewer: a prompt whose replies the parser rejected scored the perfect row. The failures count and mark it."""
        dest, m = self._corpus()
        run_root = os.path.join(self.td, "runs")
        cand = os.path.join(self.td, "prose.json")
        Path(cand).write_text(json.dumps({"CLOSER_SYS": "CANDIDATE-MARK You are a turn-end auditor in a logging pipeline."}))
        os.environ["JE_TEST_PROSE"] = "1"
        res = self.je.run_arm(dest, "prose", cand, run_root, None, self.fake, now=T0 + 10**6)
        os.environ.pop("JE_TEST_PROSE", None)
        self.assertGreaterEqual(res.get("closerNone", 0), 4, "every closer reply was prose the parser rejected (the base counted nothing): %r" % res.get("closerNone"))
        self.assertGreaterEqual(res.get("failures", 0), res.get("closerNone", 0))
        mm = self.je.measure(m, res)
        self.assertIs(mm.get("comparable"), False, "a row with failures is not comparable: %r" % mm); self.assertEqual(mm.get("failures"), res["failures"])
        rows = self.je.report(dest, run_root, figure=None)
        table = Path(run_root, "table.md").read_text()
        self.assertIn("not comparable", table); self.assertIn("| prose |", table)
        current = self.je.run_arm(dest, "current", None, run_root, None, self.fake, now=T0 + 10**6)
        self.assertTrue(self.je.measure(m, current)["comparable"])

    def test_the_prompt_swap_reaches_the_calls_and_the_process_is_left_as_it_was(self):
        dest, m = self._corpus()
        run_root = os.path.join(self.td, "runs")
        cand = os.path.join(self.td, "candidate.json")
        Path(cand).write_text(json.dumps({"CLOSER_SYS": "CANDIDATE-MARK You are a turn-end auditor in a logging pipeline."}))
        saved_env = dict(os.environ)
        shared_before, state_before = sys.modules.get("romp_event_model"), getattr(em, "STATE", None)
        try:
            self.je.run_arm_inprocess(dest, "inproc", cand, run_root, None, self.fake, now=T0 + 10**6, builds=1)
            jd = sys.modules[self.je.JUDGE_MODULE_NAME]
            self.assertNotIn("CANDIDATE-MARK", jd.CLOSER_SYS, "the module attribute is restored after the run")
            self.assertIn("turn-end auditor", jd.CLOSER_SYS)
        finally:
            os.environ.clear(); os.environ.update(saved_env)
        self.assertIs(sys.modules.get("romp_event_model"), shared_before, "the shared event model is the one the process had")
        self.assertIs(em, shared_before); self.assertEqual(getattr(em, "STATE", None), state_before, "and its roots are where they were")
        rows = self._calls("closer")
        self.assertTrue(rows and all(r["candidate"] for r in rows), "every closer call carried the candidate's prompt: %r" % rows[:2])
        with self.assertRaises(SystemExit):
            self.je.apply_prompts(jd, {"NOT_A_PROMPT": "x"})

    def test_the_budget_stops_the_run_a_fifth_over_from_its_own_ledger(self):
        dest, m = self._corpus()
        run_root = os.path.join(self.td, "runs")
        full = self.je.run_arm(dest, "full", None, run_root, None, self.fake, now=T0 + 10**6)
        per_ending = full["cost"] / len(full["endings"])
        budget = per_ending / self.je.BUDGET_OVERRUN + 0.001            # one ending's cost sits under a fifth over; two endings' does not
        res = self.je.run_arm(dest, "tight", None, run_root, budget, self.fake, now=T0 + 10**6)
        self.assertIsNotNone(res["stopped"], "past a fifth over the budget the run stops")
        self.assertEqual(len(res["endings"]), 2, "the first ending runs inside the fifth, the second trips it (a stop at the bare budget would stop after one)")
        self.assertGreater(res["stopped"]["cost"], budget * self.je.BUDGET_OVERRUN)
        with self.assertRaises(SystemExit) as cm:
            self.je.main(["run", "--corpus", dest, "--run-root", run_root, "--arm", "x"])
        self.assertNotEqual(cm.exception.code, 0, "run without a binary and a budget refuses")
        with self.assertRaises(SystemExit) as cm:
            self.je.main(["run-arm", "--corpus", dest, "--run-root", run_root, "--arm", "x"])
        self.assertNotEqual(cm.exception.code, 0)
        inside = os.path.join(self.td, "repo3", "runs"); os.makedirs(os.path.join(self.td, "repo3", ".git"))
        with self.assertRaises(subprocess.CalledProcessError):
            self.je.run_arm(dest, "bad", None, inside, None, self.fake, now=T0 + 10**6)
        self.assertFalse(list(Path(inside).rglob("*")) if os.path.exists(inside) else False, "the subprocess entry refuses a run root inside a checkout and writes nothing")

    # ── the labeller and the report ──
    def test_the_label_pass_reads_tier_one_from_the_journals_and_gates_on_the_agreement(self):
        fn = getattr(self.je, "label", None)
        self.assertIsNotNone(fn, "the labeller is a subcommand of the harness")
        dest, m = self._corpus()
        e_a = self._ending(m, SIDS[0], 0)                # the offer: the closer filed done, the user came back with a followup
        self._live_store_with_done(SIDS[0], e_a["startT"], e_a["cutT"], [{"node": SIDS[0] + ":g1", "op": "followup", "t": e_a["cutT"] + 7200}])
        e_b = self._ending(m, SIDS[1], 1)                # the finished thread: done, then the user cleared it and nothing more
        self._live_store_with_done(SIDS[1], e_b["startT"], e_b["cutT"], [{"node": SIDS[1] + ":g1", "op": "clear", "src": "user", "why": "x", "t": e_b["cutT"] + 600}])
        run_root = os.path.join(self.td, "runs")
        summary = fn(dest, run_root, self.state, claude_bin=self.fake, model="fake")
        rows = {r["id"]: r for r in json.loads(Path(run_root, "labels.json").read_text())}
        self.assertEqual(rows[e_a["id"]]["tierOne"], "not finished", "a followup after the judges' done: not finished")
        self.assertEqual(rows[e_b["id"]]["tierOne"], "finished", "a clear with nothing after: finished")
        self.assertTrue(all(r["spanS"] > 0 for r in rows.values()), "the observation span is recorded per ending")
        self.assertEqual((summary["endings"], summary["tierOneLabelled"], summary["both"], summary["agree"]), (4, 2, 2, 2), summary)
        self.assertEqual((summary["agreementPct"], summary["gatePassed"]), (100.0, True))
        self.assertEqual((summary["labellerStable"], summary["heuristicMatchesLabel"]), (4, 4))
        ledger = [json.loads(l) for l in Path(run_root, "labeller-ledger.jsonl").read_text().splitlines() if l.strip()]
        self.assertEqual((len(ledger), round(sum(r["cost"] for r in ledger), 2)), (8, 0.08), "two calls per ending, each on the ledger")
        # a followup nine days later still says not finished: the label keys on events, never on a window
        self._live_store_with_done(SIDS[1], e_b["startT"], e_b["cutT"], [{"node": SIDS[1] + ":g1", "op": "clear", "src": "user", "why": "x", "t": e_b["cutT"] + 600},
                                                                          {"node": SIDS[1] + ":g1", "op": "followup", "t": e_b["cutT"] + 9 * 86400}])
        self.assertEqual(self.je.tier_one_label(self.state, SIDS[1], e_b["cutT"], e_b["startT"]), "not finished")
        with self.assertRaises(SystemExit):
            inside = os.path.join(self.td, "repo2", "runs"); os.makedirs(os.path.join(self.td, "repo2", ".git"))
            fn(dest, inside, self.state, claude_bin=self.fake, model="fake")

    def test_the_figure_marks_an_arm_that_is_not_comparable(self):
        rows = [{"arm": "current", "leaks": 3, "falseInterrupts": 0, "flaps": 0, "costUsd": 0.1, "failures": 0, "comparable": True},
                {"arm": "prose", "leaks": 0, "falseInterrupts": 0, "flaps": 0, "costUsd": 0.1, "failures": 4, "comparable": False}]
        seen = []
        class _Ax:
            def barh(self, *a, **k): pass
            def set_yticks(self, *a): pass
            def set_yticklabels(self, labels): seen.append(list(labels))
            def invert_yaxis(self): pass
            def annotate(self, *a, **k): pass
            def set_xlim(self, *a): pass
        class _Fig:
            def savefig(self, out, **k): Path(out).write_bytes(b"PNG")
        stub = types.ModuleType("cleanplots"); stub.fig = lambda **k: (_Fig(), [_Ax() for _ in range(k.get("cols", 5))])
        saved = sys.modules.get("cleanplots"); sys.modules["cleanplots"] = stub
        try:
            self.je.draw_figure(rows, os.path.join(self.td, "f.png"))
        finally:
            if saved is not None:
                sys.modules["cleanplots"] = saved
            else:
                sys.modules.pop("cleanplots", None)
        self.assertIn(["current", "prose (not comparable)"], seen, "the headline artifact says which arm cannot be read: %r" % seen)

    def test_the_report_writes_the_table_and_the_figure_road_both_ways(self):
        dest, m = self._corpus()
        run_root = os.path.join(self.td, "runs")
        self.je.run_arm(dest, "current", None, run_root, None, self.fake, now=T0 + 10**6)
        rows = self.je.report(dest, run_root, figure=None)
        table = Path(run_root, "table.md").read_text()
        self.assertEqual([r["arm"] for r in rows], ["current"])
        self.assertIn("| current | 4 | 3 | 0 | 0 |", table); self.assertIn("| 0 |", table)
        for text in self.texts:
            self.assertNotIn(text[:24], table)
        self.assertNotIn("The synthetic goal", table, "no goal title in the report")
        out = subprocess.run([sys.executable, SCRIPT, "report", "--corpus", dest, "--run-root", run_root], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr[-500:]); self.assertIn('"leaks": 3', out.stdout)
        # the figure road: a stub library writes the file; no library leaves the note
        png = os.path.join(run_root, "fig.png")
        drawn = []
        seen_labels = []
        class _Ax:
            def barh(self, *a, **k): pass
            def set_yticks(self, *a): pass
            def set_yticklabels(self, labels): seen_labels.append(list(labels))
            def invert_yaxis(self): pass
            def annotate(self, *a, **k): pass
            def set_xlim(self, *a): pass
            def clean(self, **k): pass
        class _Fig:
            def savefig(self, out, **k): drawn.append(out); Path(out).write_bytes(b"PNG")
        panels = []
        def fig(**k):
            panels.append(k.get("cols")); return _Fig(), [_Ax() for _ in range(k.get("cols", 4))]
        stub = types.ModuleType("cleanplots"); stub.fig = fig
        saved = sys.modules.get("cleanplots"); sys.modules["cleanplots"] = stub
        try:
            self.je.report(dest, run_root, figure=png)
        finally:
            if saved is not None:
                sys.modules["cleanplots"] = saved
            else:
                sys.modules.pop("cleanplots", None)
        self.assertEqual(drawn, [png]); self.assertTrue(Path(png).exists(), "the figure is written through the library")
        self.assertEqual(panels, [5], "five panels: the four measures and the failures")
        self.assertIn(["current"], seen_labels, "a comparable arm is named plainly")
        self.assertFalse(Path(run_root, "figure.note").exists())
        import builtins
        real_import = builtins.__import__
        def no_cleanplots(name, *a, **k):
            if name == "cleanplots":
                raise ImportError("no cleanplots here")
            return real_import(name, *a, **k)
        builtins.__import__ = no_cleanplots
        try:
            self.je.report(dest, run_root, figure=os.path.join(run_root, "fig2.png"))
        finally:
            builtins.__import__ = real_import
        self.assertIn("no figure", Path(run_root, "figure.note").read_text())
        self.assertFalse(Path(run_root, "fig2.png").exists())

    # ── round two of the fold ──
    def test_turn_boundaries_are_the_event_models_over_every_record_kind(self):
        """Round three: the copied opener rule reproduced three of the fold's refusals and none of the command-twin,
        local-command, skill-content or restore-replay handling, so an SDK corpus split turns the event model folds. The
        builder now takes its boundaries from `em.parse_session` itself; this pin drives a transcript carrying a wrapper of
        every kind between the assistant answers and asserts the builder's ends and starts equal the event model's own ended
        turns (mapped atoms to record indices the same way), and that a mid-turn wrapper leaves one turn with its start at the
        prompt."""
        sid = SIDS[0]
        # one turn's worth per opener kind, each followed by an assistant answer, all chained; wrappers between are non-openers
        recs = []
        t = [T0]
        prev = [None]
        def add(rec):
            rec = dict(rec); rec["parentUuid"] = prev[0]; recs.append(rec); prev[0] = rec["uuid"]; t[0] += 60
        def usr(text, uid, **f):
            add(dict({"type": "user", "timestamp": iso(t[0]), "uuid": uid, "sessionId": sid, "cwd": "/TESTDIR",
                      "promptSource": "typed", "message": {"role": "user", "content": text}}, **f))
        def asst(text, uid):
            add({"type": "assistant", "timestamp": iso(t[0]), "uuid": uid, "sessionId": sid, "cwd": "/TESTDIR",
                 "message": {"role": "assistant", "content": [{"type": "text", "text": text}], "stop_reason": "end_turn"}})
        # a real opener, then wrappers that must NOT open, interleaved with answers
        usr("first ask", "u1", promptSource="typed"); asst("first answer", "a1")
        usr("<system-reminder>\nnoise\n</system-reminder>", "w1", promptSource="typed"); asst("noted", "a2")
        usr("[SYSTEM NOTIFICATION - NOT USER INPUT]\na task finished", "w2", promptSource="sdk", origin={"kind": "task-notification"}); asst("saw it", "a3")
        usr("Another Claude session sent a message: ping", "w3", promptSource="sdk"); asst("pong", "a4")
        usr("<command-name>/usage</command-name>", "w4", isMeta=True, promptSource="typed"); asst("usage shown", "a5")
        usr("[Image: a screenshot]", "w5", isMeta=True); asst("looked", "a6")
        usr("second ask", "u2", promptSource="sdk"); asst("second answer", "a7")   # a composer (text-string) opener
        pth = os.path.join(self.td, "parity.jsonl"); open(pth, "w").write("".join(json.dumps(r) + "\n" for r in recs))
        _recs, endings = self.je.session_endings(pth, sid)
        # the event model's own ended turns, mapped the same way
        sess = em.parse_session(pth, rompuuid=sid)
        uuid_idx = {r.get("uuid"): i for i, r in enumerate(recs)}
        want = sorted((max(uuid_idx[a["uuid"]] for a in tn["atoms"] if a.get("uuid") in uuid_idx), float(tn["t"]))
                      for tn in sess["turns"] if tn.get("ended") and any(a.get("uuid") in uuid_idx for a in tn["atoms"]))
        self.assertEqual(endings, want, "the builder's boundaries are the event model's own, over every record kind")
        self.assertTrue(endings, "the transcript has ended turns")
        # a wrapper mid-turn: one prompt, a non-final assistant, a system-reminder, the final assistant → ONE ended turn at the prompt
        mid = [{"type": "user", "timestamp": iso(T0), "uuid": "p1", "parentUuid": None, "sessionId": sid, "cwd": "/TESTDIR",
                "promptSource": "typed", "message": {"role": "user", "content": "do the thing"}},
               {"type": "assistant", "timestamp": iso(T0 + 30), "uuid": "m1", "parentUuid": "p1", "sessionId": sid, "cwd": "/TESTDIR",
                "message": {"role": "assistant", "content": [{"type": "text", "text": "working"}], "stop_reason": "tool_use"}},
               {"type": "user", "timestamp": iso(T0 + 40), "uuid": "sr", "parentUuid": "m1", "sessionId": sid, "cwd": "/TESTDIR",
                "promptSource": "typed", "message": {"role": "user", "content": "<system-reminder>\nnoise\n</system-reminder>"}},
               {"type": "assistant", "timestamp": iso(T0 + 50), "uuid": "m2", "parentUuid": "sr", "sessionId": sid, "cwd": "/TESTDIR",
                "message": {"role": "assistant", "content": [{"type": "text", "text": "done"}], "stop_reason": "end_turn"}}]
        pth2 = os.path.join(self.td, "midturn.jsonl"); open(pth2, "w").write("".join(json.dumps(r) + "\n" for r in mid))
        _r2, e2 = self.je.session_endings(pth2, sid)
        self.assertEqual(len(e2), 1, "the mid-turn system-reminder does not split the turn: %r" % e2)
        self.assertEqual((mid[e2[0][0]]["uuid"], e2[0][1]), ("m2", float(T0)), "one ending at the final assistant, its start at the prompt")

    def test_eligible_endings_are_picked_oldest_first(self):
        """Round two: the branches were swapped, so the eligible endings came newest first, the ones the user had had the least
        time to act on. With three eligible offers and one slot, the oldest wins."""
        sid3 = "11111111-2222-3333-4444-eeeeeeeeee03"
        recs, t, parent = [], T0 + 50000, None
        for j in range(3):
            recs.append(uline(sid3, t, "ask %d" % j, "u3%d" % j, parent)); recs.append(aline(sid3, t + 30, "Done %d. I can also tidy the names." % j, "a3%d" % j, "u3%d" % j))
            parent = "a3%d" % j; t += 600
        (self.pdir / (sid3 + ".jsonl")).write_text("".join(json.dumps(r) + "\n" for r in recs))
        (self.state / "names" / sid3).write_text("api\t%s\t#abcdef\n" % self.cwd)
        # every offer of the third session completed by the judges in its own turn
        ends = self.je.turn_ends(recs)
        log = [{"ev_t": self.je._ts(recs[i]) + 1, "at": self.je._ts(recs[i]) + 2, "src": "closer", "kind": "done", "why": "x"} for i in ends]
        store = {"rompUuid": sid3, "seq": 1, "placementsV": 14, "placements": {}, "status": {},
                 "nodes": {sid3 + ":g1": {"id": sid3 + ":g1", "text": "The goal", "parentId": None, "t": T0 + 49000, "trail": [], "log": log}}}
        (self.state / "goals" / (sid3 + ".json")).write_text(json.dumps(store))
        m = self._corpus(per_class=1, name="oldest")[1]
        offers = [e for e in m["endings"] if e["class"] == "offer"]
        self.assertEqual([(e["session"], e["turn"], e["tierOneEligible"]) for e in offers],
                         [(hashlib.sha256(sid3.encode()).hexdigest()[:12], 0, True)], "the oldest eligible offer, not the newest: %r" % offers)

    def test_a_pre_turn_top_the_arm_leaves_alone_is_not_scored(self):
        """Round two: `scored` was unpinned. A seed with two older tops the arm does not touch and the turn's own card: the older
        ones read unscored, the turn's own scored."""
        sid = SIDS[0]
        m = self._corpus()[1]
        e = self._ending(m, sid, 1)
        start = float(e["startT"])
        seg0 = "%s:%d:aaaaaaaa" % (sid, start - 5000)
        nodes = {}
        for n in ("g1", "g2"):
            nodes[sid + ":" + n] = {"id": sid + ":" + n, "text": "An older goal %s" % n, "parentId": None, "t": start - 5000, "trail": [seg0],
                                    "log": [{"ev_t": start - 5000, "at": start - 4999, "src": "planner", "kind": "mint"},
                                            {"ev_t": start - 4000, "at": start - 3999, "src": "planner", "kind": "block", "why": "waiting"}]}
        store = {"rompUuid": sid, "seq": 2, "placementsV": 14, "placements": {seg0: sid + ":g1"}, "status": {}, "nodes": nodes,
                 "closedTurns": [], "closedSig": {}}
        (self.state / "goals" / (sid + ".json")).write_text(json.dumps(store))
        dest, m = self._corpus(name="corpus-scored")
        run_root = os.path.join(self.td, "runs")
        res = self.je.run_arm(dest, "current", None, run_root, None, self.fake, now=T0 + 10**6)
        build = res["endings"][self._ending(m, sid, 1)["id"]]["builds"][-1]
        self.assertTrue(all(isinstance(v, dict) and "scored" in v for v in build.values()),
                        "each card carries a scored stamp (the base recorded a bare column): %r" % build)
        flags = sorted(v["scored"] for v in build.values())
        self.assertEqual(flags, [False, True], "the pre-turn top the arm rules on this turn scores; the one it leaves alone does not: %r" % build)
        self.assertEqual(self.je.measure(m, res)["falseInterrupts"], 0, "the untouched inherited blocked top counts against no finished ending")

    def test_the_seed_is_rolled_up_before_the_first_menu(self):
        """Round two: without the rollup before the first judge, the planner's first menu listed a pre-cut done sub and a
        user-cleared top (the flag cache the cut strips is what `open_menu` reads). The fake logs the menu it sees."""
        sid = SIDS[0]
        m = self._corpus()[1]
        e = self._ending(m, sid, 1)
        start = float(e["startT"])
        seg0 = "%s:%d:aaaaaaaa" % (sid, start - 5000)
        top = {"id": sid + ":g1", "text": "An open top with a finished part", "parentId": None, "t": start - 5000, "trail": [seg0],
               "log": [{"ev_t": start - 5000, "at": start - 4999, "src": "planner", "kind": "mint"}]}
        sub = {"id": sid + ":g2", "text": "The finished part nobody should see", "parentId": sid + ":g1", "t": start - 4900, "trail": [seg0],
               "log": [{"ev_t": start - 4900, "at": start - 4899, "src": "planner", "kind": "mint"},
                       {"ev_t": start - 4000, "at": start - 3999, "src": "closer", "kind": "done", "why": "x"}]}
        cleared = {"id": sid + ":g3", "text": "A top the user crossed off", "parentId": None, "t": start - 4800, "trail": [seg0],
                   "log": [{"ev_t": start - 4800, "at": start - 4799, "src": "planner", "kind": "mint"},
                           {"ev_t": start - 3000, "at": start - 2999, "src": "user", "kind": "clear", "why": "seen"}]}
        store = {"rompUuid": sid, "seq": 3, "placementsV": 14, "placements": {seg0: sid + ":g1"}, "status": {},
                 "nodes": {n["id"]: n for n in (top, sub, cleared)}, "closedTurns": [], "closedSig": {}}
        (self.state / "goals" / (sid + ".json")).write_text(json.dumps(store))
        dest, m = self._corpus(name="corpus-menu")
        run_root = os.path.join(self.td, "runs")
        self.je.run_arm(dest, "current", None, run_root, None, self.fake, now=T0 + 10**6)
        menus = [r["menu"] for r in self._calls("planner") if r["menu"] and "An open top" in r["menu"]]
        self.assertTrue(menus, "the planner saw the seeded top: %r" % [r["menu"][:60] for r in self._calls("planner")])
        for menu in menus:
            self.assertNotIn("The finished part nobody should see", menu, "the pre-cut done sub is off the first menu")
            self.assertNotIn("A top the user crossed off", menu, "the cleared top is off the first menu")

    def test_failure_rows_of_every_kind_that_means_nothing_was_judged_count_once(self):
        counter = getattr(self.je, "count_failure_rows", None)
        self.assertIsNotNone(counter, "the arm counts only the judge-errors rows that mean nothing was judged (the base folded the count into the loop)")
        ledger = os.path.join(self.td, "judge-errors.jsonl")
        Path(ledger).write_text("".join(json.dumps({"err": k}) + "\n" for k in ("parse", "auth", "rate-limited", "fast-refused", "scratch", "stale-close", "workless-done", "timeout")))
        self.assertEqual(counter(ledger), 5, "the pause kinds and the call-level stand-downs count; anomaly notes do not; timeout is no kind the judges write")
        for k in ("auth", "rate-limited", "fast-refused", "scratch", "call", "parse", "give-up", "pass-crash", "unregistered-caller"):
            self.assertIn(k, self.je.FAILURE_KINDS)
        self.assertNotIn("timeout", self.je.FAILURE_KINDS)
        # a rejected closer reply files its own row: it is counted once, not once as a row and once as a None
        dest, m = self._corpus()
        run_root = os.path.join(self.td, "runs")
        cand = os.path.join(self.td, "prose.json")
        Path(cand).write_text(json.dumps({"CLOSER_SYS": "CANDIDATE-MARK You are a turn-end auditor in a logging pipeline."}))
        os.environ["JE_TEST_PROSE"] = "1"
        res = self.je.run_arm(dest, "prose", cand, run_root, None, self.fake, now=T0 + 10**6)
        os.environ.pop("JE_TEST_PROSE", None)
        self.assertGreaterEqual(res["closerNone"], 1, "the closer was reached and its prose rejected")
        arm_ledger = os.path.join(run_root, "prose", "state", "romp", "judge-errors.jsonl")
        self.assertEqual(res["failures"], self.je.count_failure_rows(arm_ledger),
                         "failures is the ledger's own count, never the rows plus the Nones (a planner parse row would break an equality with closerNone): %r" % res["failures"])

    def test_the_turns_own_live_and_extra_target_placements_are_the_arms_to_make(self):
        sid = SIDS[0]
        m = self._corpus()[1]
        e = self._ending(m, sid, 0)
        start, cut = float(e["startT"]), float(e["cutT"])
        segp = "%s:%d:bbbbbbbb" % (sid, start)
        node = {"id": sid + ":g2", "text": "The turn's own goal", "parentId": None, "t": start, "trail": [segp], "log": []}
        store = {"rompUuid": sid, "seq": 2, "placementsV": 14, "status": {}, "nodes": {node["id"]: node},
                 "placements": {segp + "#p": node["id"], segp + "#d": node["id"], segp: node["id"], segp + "#live": node["id"], segp + "#n2": node["id"]}}
        try:
            before = self.je.store_before(store, cut, start, e["id"])
        except TypeError:
            self.fail("store_before cuts at the turn's start under the ending id (the base cut at the cut alone)")
        self.assertEqual(sorted(k.rsplit("#", 1)[-1] for k in before["placements"]), ["d", "p"], "only the prompt-run and the delegation keys survive from the turn")

    def test_the_same_titled_fork_lanes_join_the_sessions_transcripts(self):
        sid = SIDS[0]; fork = "11111111-2222-3333-4444-ffffffffff09"
        recs = [{"type": "custom-title", "customTitle": "web", "sessionId": fork, "timestamp": iso(T0 + 80000)},
                uline(fork, T0 + 80000, "in the fork", "u1"), aline(fork, T0 + 80030, "Forked and answered. Which option do you prefer?", "a1", "u1"),
                uline(fork, T0 + 80600, "and more", "u2", "a1"), aline(fork, T0 + 80630, "Done.", "a2", "u2")]
        (self.pdir / (fork + ".jsonl")).write_text("".join(json.dumps(r) + "\n" for r in recs))
        other = "11111111-2222-3333-4444-ffffffffff08"
        (self.pdir / (other + ".jsonl")).write_text(json.dumps({"type": "custom-title", "customTitle": "somebody else", "sessionId": other}) + "\n")
        fl = getattr(self.je, "fork_lanes", None)
        self.assertIsNotNone(fl, "the builder reads the same-titled fork lanes beside the registry's fsids (the base read neither)")
        self.assertEqual(fl(self.pdir, "web", {sid}), [fork], "a same-titled transcript is a lane; another title is not")
        m = self._corpus(name="forks")[1]
        h = hashlib.sha256(sid.encode()).hexdigest()[:12]
        self.assertEqual(sum(1 for e in m["endings"] if e["session"] == h), 4, "the fork's two endings join the anchor's two")

    def test_the_skip_counters_count(self):
        (self.state / "names" / "11111111-2222-3333-4444-eeeeeeeeee07").write_text("gone\t%s\t#abcdef\n" % os.path.join(self.td, "nowhere"))
        (self.state / "names" / "11111111-2222-3333-4444-eeeeeeeeee08").write_text("one-field-only\n")
        short = "11111111-2222-3333-4444-eeeeeeeeee09"
        (self.pdir / (short + ".jsonl")).write_text(json.dumps(uline(short, T0, "only ask", "u1")) + "\n" + json.dumps(aline(short, T0 + 30, "Only answer.", "a1", "u1")) + "\n")
        (self.state / "names" / short).write_text("short\t%s\t#abcdef\n" % self.cwd)
        m = self._corpus(name="skips")[1]
        self.assertIn("skipped", m, "the manifest counts skips (the base wrote none)")
        self.assertEqual(m["skipped"], {"no-transcript": 1, "few-turns": 1, "unreadable-names-entry": 1})
        self.assertNotIn("nowhere", json.dumps(m["skipped"]))

    def test_the_label_entry_takes_no_default_binary(self):
        import inspect
        sig = inspect.signature(self.je.label)
        self.assertIs(sig.parameters["claude_bin"].default, inspect.Parameter.empty, "the binary is the caller's to name, on every road")

    def test_the_shared_event_models_checkpoint_provider_survives_an_in_process_arm(self):
        dest, m = self._corpus()
        run_root = os.path.join(self.td, "runs")
        cand = os.path.join(self.td, "candidate.json")
        Path(cand).write_text(json.dumps({"CLOSER_SYS": "CANDIDATE-MARK You are a turn-end auditor in a logging pipeline."}))
        self.assertTrue(hasattr(em, "_CKPT_DIR_FN"), "the event model has a checkpoint-dir provider slot (the arm's judge could leave its own)")
        provider_before = em._CKPT_DIR_FN               # None at the floor: the test wires no kernel
        saved_env = dict(os.environ)
        try:
            self.je.run_arm_inprocess(dest, "inproc2", cand, run_root, None, self.fake, now=T0 + 10**6, builds=1)
        finally:
            os.environ.clear(); os.environ.update(saved_env)
        self.assertIs(em._CKPT_DIR_FN, provider_before, "the arm's judge left the shared provider as it was, not its own scratch-rooted one")


if __name__ == "__main__":
    unittest.main()
