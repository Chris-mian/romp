#!/usr/bin/env python3
"""kernel/gitpr.py — turning `gh` output into the PR payload the Outline chip renders, and the
event-keyed cache in front of it (the user 2026-08-17).

gh is stubbed here (a real network call in a test suite is a flake), but the SHAPE it returns is gh's
own `--json` vocabulary, so the normalizer is tested against the words GitHub actually sends.
"""
import json
import os
import subprocess
import tempfile
import threading
import time
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.realpath(__file__))).parent
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)
gp = SourceFileLoader("romp_gitpr_hydrate", str(ROOT / "kernel" / "gitpr.py")).load_module()

REPO = "notes-api-org/notes-api"

OPEN_PASSING = {
    "number": 12, "title": "notes: index rebuild", "url": "https://github.com/%s/pull/12" % REPO,
    "headRefName": "dev/fix-notes-index", "state": "OPEN", "isDraft": False,
    "reviewDecision": "APPROVED", "updatedAt": "2026-08-17T10:00:00Z",
    "additions": 64, "deletions": 7, "changedFiles": 2,
    "statusCheckRollup": [{"name": "pytest", "conclusion": "SUCCESS", "status": "COMPLETED"}],
}
DRAFT_FAILING = {
    "number": 15, "title": "notes: op values", "url": "https://github.com/%s/pull/15" % REPO,
    "headRefName": "dev/op-values", "state": "OPEN", "isDraft": True,
    "reviewDecision": None, "updatedAt": "2026-08-17T10:05:00Z",
    "additions": 12, "deletions": 0, "changedFiles": 1,
    "statusCheckRollup": [{"name": "pytest", "conclusion": "FAILURE", "status": "COMPLETED"},
                          {"name": "mypy", "conclusion": None, "status": "IN_PROGRESS"}],
}
MERGED = {
    "number": 9, "title": "notes: trashed link", "url": "https://github.com/%s/pull/9" % REPO,
    "headRefName": "dev/trashed-link", "state": "MERGED", "isDraft": False,
    "reviewDecision": "APPROVED", "updatedAt": "2026-08-17T09:00:00Z",
    "additions": 3, "deletions": 3, "changedFiles": 1, "statusCheckRollup": [],
}


def _stub_gh(monkeypatch, payload, code=0, stderr=""):
    """Replace the subprocess gitpr uses, recording every argv it builds."""
    calls = []

    def fake_run(argv, **kw):
        calls.append(argv)
        out = payload if isinstance(payload, str) else json.dumps(payload)
        return subprocess.CompletedProcess(argv, code, stdout=out, stderr=stderr)

    monkeypatch.setattr(gp.subprocess, "run", fake_run)
    return calls


# ── normalize ────────────────────────────────────────────────────────────────────────────────────────

def test_open_and_passing():
    pr = gp.normalize(OPEN_PASSING)
    assert (pr["num"], pr["state"], pr["draft"]) == (12, "open", False)
    assert pr["checksState"] == "pass" and pr["checksFailing"] == []
    assert pr["reviewDecision"] == "approved"
    assert pr["branch"] == "dev/fix-notes-index"
    assert (pr["adds"], pr["dels"], pr["files"]) == (64, 7, 2)
    assert pr["updatedT"] > 0


def test_a_failure_outranks_a_still_running_check():
    """The worst KNOWN state is what the chip must show: 'running' would read as nothing wrong yet."""
    pr = gp.normalize(DRAFT_FAILING)
    assert pr["draft"] is True
    assert pr["checksState"] == "fail"
    assert pr["checksFailing"] == ["pytest"]
    assert pr["reviewDecision"] == "none"


def test_merged_with_no_checks():
    pr = gp.normalize(MERGED)
    assert pr["state"] == "merged" and pr["checksState"] == "none"


def test_running_only():
    raw = dict(OPEN_PASSING, statusCheckRollup=[{"name": "pytest", "conclusion": None,
                                                 "status": "IN_PROGRESS"}])
    assert gp.normalize(raw)["checksState"] == "running"


def test_a_cancelled_or_timed_out_check_counts_as_failing():
    for concl in ("CANCELLED", "TIMED_OUT", "ACTION_REQUIRED"):
        raw = dict(OPEN_PASSING, statusCheckRollup=[{"name": "pytest", "conclusion": concl,
                                                    "status": "COMPLETED"}])
        assert gp.normalize(raw)["checksState"] == "fail", concl


def test_a_neutral_or_skipped_check_is_not_a_failure():
    raw = dict(OPEN_PASSING, statusCheckRollup=[{"name": "lint", "conclusion": "SKIPPED",
                                                 "status": "COMPLETED"}])
    assert gp.normalize(raw)["checksState"] == "pass"


def test_an_unparseable_timestamp_yields_no_age_rather_than_a_wrong_one():
    assert gp.normalize(dict(OPEN_PASSING, updatedAt="whenever"))["updatedT"] == 0


def test_failing_names_are_capped():
    many = [{"name": "c%d" % i, "conclusion": "FAILURE", "status": "COMPLETED"} for i in range(20)]
    assert len(gp.normalize(dict(OPEN_PASSING, statusCheckRollup=many))["checksFailing"]) == 6


# ── hydrate ──────────────────────────────────────────────────────────────────────────────────────────

def test_hydrate_shells_out_once_and_keys_by_number(monkeypatch):
    calls = _stub_gh(monkeypatch, [OPEN_PASSING, DRAFT_FAILING, MERGED])
    prs = gp.hydrate(REPO)
    assert len(calls) == 1, "one gh call per repo, not per PR"
    assert sorted(prs) == [9, 12, 15]
    assert prs[15]["checksFailing"] == ["pytest"]
    assert "--repo" in calls[0] and REPO in calls[0]


def test_hydrate_raises_with_gh_s_own_reason(monkeypatch):
    _stub_gh(monkeypatch, "", code=4, stderr="gh: To use GitHub CLI, run: gh auth login\n")
    try:
        gp.hydrate(REPO)
    except gp.GitPrError as e:
        assert "gh auth login" in str(e)
    else:
        raise AssertionError("expected GitPrError")


def test_hydrate_raises_when_gh_is_missing(monkeypatch):
    def fake_run(argv, **kw):
        raise FileNotFoundError("gh")

    monkeypatch.setattr(gp.subprocess, "run", fake_run)
    try:
        gp.hydrate(REPO)
    except gp.GitPrError as e:
        assert "gh" in str(e)
    else:
        raise AssertionError("expected GitPrError")


def test_hydrate_raises_on_output_that_is_not_json(monkeypatch):
    _stub_gh(monkeypatch, "not json at all")
    try:
        gp.hydrate(REPO)
    except gp.GitPrError:
        pass
    else:
        raise AssertionError("expected GitPrError")


def test_hydrate_one_fetches_a_single_pr(monkeypatch):
    calls = _stub_gh(monkeypatch, OPEN_PASSING)
    pr = gp.hydrate_one(REPO, 12)
    assert pr["num"] == 12
    assert "view" in calls[0]


# ── the cache ────────────────────────────────────────────────────────────────────────────────────────

def _drain():
    """Wait for the background refresh to land — repo_prs is non-blocking by design."""
    for _ in range(200):
        with gp._INFLIGHT_LOCK:
            busy = bool(gp._INFLIGHT)
        if not busy:
            return
        time.sleep(0.01)
    raise AssertionError("background refresh never finished")


def test_repo_prs_never_blocks_and_fills_in_behind(monkeypatch):
    """gh is a 5s network call reached from the per-push build pass, so it must NEVER be called inline:
    the first read serves what it has (nothing) and schedules the work."""
    gp._CACHE.clear()
    started = []
    monkeypatch.setattr(gp, "hydrate", lambda repo: (started.append(repo),
                                                     {12: gp.normalize(OPEN_PASSING)})[1])
    prs, err = gp.repo_prs(REPO)
    assert prs == {} and err == "", "first read must not wait for gh"
    _drain()
    prs, err = gp.repo_prs(REPO)
    assert sorted(prs) == [12] and err == ""
    assert started == [REPO]


def test_repo_prs_caches_until_invalidated(monkeypatch):
    gp._CACHE.clear()
    calls = []
    monkeypatch.setattr(gp, "hydrate", lambda repo: (calls.append(repo),
                                                     {12: gp.normalize(OPEN_PASSING)})[1])
    gp.repo_prs(REPO); _drain()
    gp.repo_prs(REPO); gp.repo_prs(REPO)
    assert len(calls) == 1, "a fresh cache is served without touching gh"
    gp.invalidate(REPO)
    gp.repo_prs(REPO); _drain()
    assert len(calls) == 2


def test_only_one_refresh_per_repo_is_in_flight(monkeypatch):
    """A burst of pushes must not fan out into a pile of concurrent gh calls."""
    gp._CACHE.clear()
    calls = []
    gate = threading.Event()

    def slow(repo):
        calls.append(repo)
        gate.wait(2)
        return {}

    monkeypatch.setattr(gp, "hydrate", slow)
    for _ in range(5):
        gp.repo_prs(REPO)
    gate.set()
    _drain()
    assert len(calls) == 1


def test_a_failed_refresh_keeps_the_last_good_snapshot_and_surfaces_the_reason(monkeypatch):
    """PR state is inherently a snapshot. Blanking the pane on a transient 502 is worse than showing what
    we knew WITH the error riding along — what must never happen is the error being swallowed."""
    gp._CACHE.clear()
    monkeypatch.setattr(gp, "hydrate", lambda repo: {12: gp.normalize(OPEN_PASSING)})
    gp.repo_prs(REPO); _drain()

    def boom(repo):
        raise gp.GitPrError("HTTP 502: 502 Bad Gateway")

    monkeypatch.setattr(gp, "hydrate", boom)
    gp.invalidate(REPO)
    gp.repo_prs(REPO); _drain()
    prs, err = gp.repo_prs(REPO)
    assert sorted(prs) == [12], "the known PR is still shown"
    assert "502" in err, "and the failure is visible, not swallowed"


def test_a_first_refresh_that_fails_serves_nothing_plus_the_reason(monkeypatch):
    gp._CACHE.clear()

    def boom(repo):
        raise gp.GitPrError("gh auth login")

    monkeypatch.setattr(gp, "hydrate", boom)
    gp.repo_prs(REPO); _drain()
    prs, err = gp.repo_prs(REPO)
    assert prs == {} and "gh auth login" in err


def test_repo_prs_with_no_repo_is_a_silent_empty():
    assert gp.repo_prs("") == ({}, "")


def test_checks_for_fills_only_the_referenced_prs(monkeypatch):
    """The rollup is excluded from the list query because it times GitHub out across 100 PRs, so checks
    are fetched for the handful a session actually references."""
    gp._CACHE.clear()
    monkeypatch.setattr(gp, "hydrate", lambda repo: {12: gp.normalize(dict(OPEN_PASSING, **{})),
                                                    15: gp.normalize(DRAFT_FAILING)})
    # strip the rollup so both land as "unknown", the way the real list query returns them
    monkeypatch.setattr(gp, "hydrate", lambda repo: {
        12: gp.normalize({k: v for k, v in OPEN_PASSING.items() if k != "statusCheckRollup"}),
        15: gp.normalize({k: v for k, v in DRAFT_FAILING.items() if k != "statusCheckRollup"})})
    gp.repo_prs(REPO); _drain()
    prs, _ = gp.repo_prs(REPO)
    assert prs[12]["checksState"] == "unknown" and prs[15]["checksState"] == "unknown"

    asked = []

    def fake(args, what):
        asked.append(args[2])
        return {"number": int(args[2]),
                "statusCheckRollup": [{"name": "pytest", "conclusion": "FAILURE", "status": "COMPLETED"}]}

    monkeypatch.setattr(gp, "_gh_json", fake)
    gp.checks_for(REPO, [15])
    assert asked == ["15"], "only the referenced PR is fetched"
    prs, _ = gp.repo_prs(REPO)
    assert prs[15]["checksState"] == "fail" and prs[15]["checksFailing"] == ["pytest"]
    assert prs[12]["checksState"] == "unknown", "the unreferenced one is left alone"


def test_unknown_is_distinct_from_none():
    """"we have not asked" must never collapse into "this PR has no checks" — one is missing data, the
    other is a fact, and only the fact may read as green."""
    assert gp.normalize({k: v for k, v in OPEN_PASSING.items()
                         if k != "statusCheckRollup"})["checksState"] == "unknown"
    assert gp.normalize(dict(OPEN_PASSING, statusCheckRollup=[]))["checksState"] == "none"


def test_needs_poll_only_while_a_check_runs(monkeypatch):
    gp._CACHE.clear()
    running = dict(OPEN_PASSING, statusCheckRollup=[{"name": "pytest", "conclusion": None,
                                                    "status": "IN_PROGRESS"}])
    monkeypatch.setattr(gp, "hydrate", lambda repo: {12: gp.normalize(running)})
    gp.repo_prs(REPO); _drain()
    assert gp.needs_poll(REPO) is True

    monkeypatch.setattr(gp, "hydrate", lambda repo: {12: gp.normalize(OPEN_PASSING)})
    gp.invalidate(REPO)
    gp.repo_prs(REPO); _drain()
    assert gp.needs_poll(REPO) is False, "a terminal check must end the poll"
