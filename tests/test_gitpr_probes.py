#!/usr/bin/env python3
"""kernel/gitpr.py — the local git probes behind the Outline pane's PR chip (the user 2026-08-17).

Every git/gh shell-out for the PR surface lives in one module, so the read side (build_session) stays a
pure assembler and the one place that talks to the network is the one place that caches and reports its
own failures. These tests cover the LOCAL half: which repo a session sits in, which branch, and how far
ahead of its upstream it is. Real git repos in tmp_path — a mock of git tells us nothing about whether the
argv is right.
"""
import os
import subprocess
import tempfile
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.realpath(__file__))).parent
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)
gp = SourceFileLoader("romp_gitpr", str(ROOT / "kernel" / "gitpr.py")).load_module()


def _run(cwd, *args):
    subprocess.run(list(args), cwd=str(cwd), check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _repo(tmp_path, remote="https://github.com/notes-api-org/notes-api.git"):
    """A synthetic repo with one commit, optionally with a GitHub origin."""
    d = tmp_path / "notes-api"
    d.mkdir()
    _run(d, "git", "init", "-q", "-b", "main")
    _run(d, "git", "config", "user.email", "dev@example.invalid")
    _run(d, "git", "config", "user.name", "Dev")
    (d / "README.md").write_text("notes-api\n")
    _run(d, "git", "add", "README.md")
    _run(d, "git", "commit", "-qm", "init")
    if remote:
        _run(d, "git", "remote", "add", "origin", remote)
    return d


def test_repo_of_an_https_remote(tmp_path):
    assert gp.repo_of(str(_repo(tmp_path))) == "notes-api-org/notes-api"


def test_repo_of_an_ssh_remote(tmp_path):
    d = _repo(tmp_path, remote="git@github.com:notes-api-org/notes-api.git")
    assert gp.repo_of(str(d)) == "notes-api-org/notes-api"


def test_repo_of_an_ssh_host_alias(tmp_path):
    """A per-account host alias (github.com-personal) is still github.com — the identity machinery is
    the user's business, not this module's."""
    d = _repo(tmp_path, remote="git@github.com-personal:notes-api-org/notes-api.git")
    assert gp.repo_of(str(d)) == "notes-api-org/notes-api"


def test_repo_of_a_non_github_remote_is_empty(tmp_path):
    d = _repo(tmp_path, remote="https://git.example.invalid/notes-api.git")
    assert gp.repo_of(str(d)) == ""


def test_repo_of_a_repo_with_no_remote_is_empty(tmp_path):
    assert gp.repo_of(str(_repo(tmp_path, remote=None))) == ""


def test_repo_of_a_non_repo_is_empty(tmp_path):
    assert gp.repo_of(str(tmp_path)) == ""


def test_repo_of_a_missing_directory_is_empty():
    assert gp.repo_of("/nonexistent/notes-api") == ""


def test_is_repo(tmp_path):
    assert gp.is_repo(str(_repo(tmp_path))) is True
    assert gp.is_repo(str(tmp_path)) is False


def test_branch_of(tmp_path):
    d = _repo(tmp_path)
    _run(d, "git", "checkout", "-q", "-b", "dev/fix-notes-index")
    assert gp.branch_of(str(d)) == "dev/fix-notes-index"


def test_branch_of_a_detached_head_is_empty(tmp_path):
    """Detached is not a branch — nothing to open or attribute a PR to."""
    d = _repo(tmp_path)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(d), capture_output=True,
                         text=True).stdout.strip()
    _run(d, "git", "checkout", "-q", sha)
    assert gp.branch_of(str(d)) == ""


def test_head_of(tmp_path):
    d = _repo(tmp_path)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(d), capture_output=True,
                         text=True).stdout.strip()
    assert gp.head_of(str(d)) == sha
    assert gp.head_of(str(tmp_path)) == ""


def test_ahead_of_without_an_upstream_is_zero(tmp_path):
    """No upstream means nothing to be ahead OF — not 'infinitely ahead'."""
    assert gp.ahead_of(str(_repo(tmp_path))) == 0


def test_ahead_of_counts_unpushed_commits(tmp_path):
    up = _repo(tmp_path)
    clone = tmp_path / "clone"
    _run(tmp_path, "git", "clone", "-q", str(up), str(clone))
    _run(clone, "git", "config", "user.email", "dev@example.invalid")
    _run(clone, "git", "config", "user.name", "Dev")
    assert gp.ahead_of(str(clone)) == 0
    for n in ("a", "b"):
        (clone / (n + ".txt")).write_text(n + "\n")
        _run(clone, "git", "add", n + ".txt")
        _run(clone, "git", "commit", "-qm", n)
    assert gp.ahead_of(str(clone)) == 2


def test_commits_ahead_of_main(tmp_path):
    """'this branch carries work' — measured against origin/main, which is what a PR would target."""
    up = _repo(tmp_path)
    clone = tmp_path / "clone"
    _run(tmp_path, "git", "clone", "-q", str(up), str(clone))
    _run(clone, "git", "config", "user.email", "dev@example.invalid")
    _run(clone, "git", "config", "user.name", "Dev")
    assert gp.commits_ahead_of_main(str(clone)) == 0
    _run(clone, "git", "checkout", "-q", "-b", "dev/op-values")
    (clone / "a.txt").write_text("a\n")
    _run(clone, "git", "add", "a.txt")
    _run(clone, "git", "commit", "-qm", "one")
    assert gp.commits_ahead_of_main(str(clone)) == 1


def test_commits_ahead_of_main_without_an_origin_main_is_zero(tmp_path):
    """Unknowable reads as 'nothing to open a PR for', never as 'open one anyway'."""
    assert gp.commits_ahead_of_main(str(_repo(tmp_path))) == 0
