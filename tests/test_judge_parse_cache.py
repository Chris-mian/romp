#!/usr/bin/env python3
"""parsed_session: ONE event-model parse per (transcript, mtime+size), reused across the captioner /
planner / sweep / courier instead of each re-parsing the same leaf every pass (the redundancy that
forced the PLAN_SESSIONS cap). An unchanged transcript is served from cache; a changed one re-parses."""
import os
import tempfile
import time
from importlib.machinery import SourceFileLoader

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "bin")
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
SourceFileLoader("romp_event_model", os.path.join(BIN, "romp-event-model")).load_module()
jd = SourceFileLoader("romp_judge", os.path.join(BIN, "romp-judge")).load_module()


def test_parsed_session_caches_until_the_transcript_changes():
    jd._PARSE_CACHE.clear()
    calls = []
    orig = jd.em.parse_session
    jd.em.parse_session = lambda *a, **k: calls.append(1) or {"turns": []}   # count real parses
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            f.write("{}\n")
            p = f.name
        s1 = jd.parsed_session("sid1", [p], 0)
        s2 = jd.parsed_session("sid1", [p], 0)
        assert s1 is s2, "an unchanged transcript returns the SAME cached parse"
        assert len(calls) == 1, "...parsed exactly once"

        time.sleep(0.01)
        with open(p, "a") as fh:
            fh.write("{}\n")                                                  # grow it → new (mtime,size)
        jd.parsed_session("sid1", [p], 0)
        assert len(calls) == 2, "a CHANGED transcript re-parses (cache keyed on mtime+size)"
    finally:
        jd.em.parse_session = orig
        os.unlink(p)


if __name__ == "__main__":
    test_parsed_session_caches_until_the_transcript_changes()
    print("ok")
