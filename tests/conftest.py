"""Global test isolation (2026-07-07): point XDG_STATE_HOME at a fresh temp dir BEFORE any test module
loads bin/romp-judge or bin/romp-kernel — both resolve their state root at import time. Without this,
any test that skips its own rebind writes into the REAL ~/.local/state/romp (the diary guard's
judge-errors.jsonl lines from legacy-flag fixtures made that visible). conftest.py imports before every
test module, so this is a suite-wide floor; per-class _rebind_state/tempdir isolation still layers on
top exactly as before."""
import os
import sys
import tempfile

import pytest

os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp(prefix="romp-tests-state-")
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel exports this to its sessions; it outranks the XDG floor

# No test may reach the REAL `claude` CLI (2026-08-12): _judge_claude_bin honors ROMP_CLAUDE_BIN
# first, so this floors every judge call a test forgot to stub at /bin/false — empty stdout, the
# dead-CLI row, byte-for-byte what a claude-less CI runner produces. Found when an unstubbed
# _judge_run in the kernel suite exec'd the live CLI on a dev machine: run alone it made a real
# (billed!) model call and passed; in the full suite the process env's key had already been claimed
# by an sdk-backend construction, the live CLI refused "Not logged in", and the judge-auth latch
# that refusal now correctly feeds floored the synthetic session's cards — 25 stays-in-Working
# tests red locally, green on CI, purely machine-dependent. Tests that assert _judge_claude_bin's
# own resolution pop this var themselves (test_judge.py), as they always had to.
os.environ["ROMP_CLAUDE_BIN"] = "/bin/false"


@pytest.fixture(autouse=True)
def _stub_place_llm(monkeypatch):
    """Card-first placer floor (2026-07-08): every loaded romp-judge instance gets a no-op place_llm so
    no test can reach a real `claude -p` subprocess through _card_route_subs (a plan test whose mocked
    sub lands on a card with open sub-goals would otherwise fire the real second call). Placer tests
    override jd.place_llm in-body; monkeypatch restores whatever was there after each test."""
    seen = set()
    for m in list(sys.modules.values()):
        for j in (m, getattr(m, "jd", None)):
            if j is not None and id(j) not in seen and getattr(j, "_card_route_subs", None) is not None:
                seen.add(id(j))
                monkeypatch.setattr(j, "place_llm", lambda *a, **k: "")
    yield
