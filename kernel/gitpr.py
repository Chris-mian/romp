#!/usr/bin/env python3
"""PRs as a session's artifacts: the git and gh reads behind the Outline pane's per-goal PR chip.

Every `git` and `gh` shell-out for that surface lives here, so build_session stays a pure assembler and
the one place that talks to the network is the one place that caches and reports its own failures.

Rules this module is bound by:
  * `gh` is the authoritative source for PR state, never scraped prose.
  * When git or gh cannot answer, say so: a blank chip would claim "no PR" when the truth is "we could
    not look".
  * Refresh is event-driven: a moved ref, a push/gh-pr command, a newly cited PR number, a user click.
    The one timer is the poll that waits for running CI checks (and for a failed read to recover).
"""
import calendar
import json
import os
import re
import subprocess
import threading
import time

GIT_BIN = os.environ.get("ROMP_GIT_BIN", "git")
GH_BIN = os.environ.get("ROMP_GH_BIN", "gh")
PR_STATUS_OFF = os.environ.get("ROMP_PR_STATUS", "").strip().lower() == "off"   # skips every git and gh read
_TIMEOUT = 20        # a hung network call must never stall a refresh forever
_MEMO_CAP = 512      # bound on every per-directory memo below

# owner/repo out of any GitHub remote form, including a per-account ssh host alias
# (git@github.com-personal:owner/repo.git). The optional .git suffix and trailing slash are stripped.
_REMOTE_RE = re.compile(r"^(?:https://github\.com/"
                        r"|(?:ssh://)?git@github\.com(?:-[A-Za-z0-9._-]+)?[:/])"
                        r"([A-Za-z0-9._-]+/[A-Za-z0-9._-]+?)(?:\.git)?/?$")

_MAIN_BRANCHES = ("main", "master")
_HEADS_PREFIX = "refs/heads/"
_SYMREF_PREFIX = "ref:"
_GITDIR_PREFIX = "gitdir:"

# A command that pushes or acts on a PR, at COMMAND POSITION: the start of the string or just after a
# shell separator, past any VAR=value prefixes. The words inside an argument (`grep -rn 'git push' docs/`)
# never count, and read-only subcommands (view / list / checks / diff / status) are absent: looking at a
# PR is not acting on it. The judge's PR-ref mining and the kernel's push counter both read this one.
_CMD_HEAD = r"(?:^|[\n;&|(]|&&|\|\|)\s*(?:[A-Za-z_][A-Za-z0-9_]*=\S+\s+)*"
PR_ACT_CMD_RE = re.compile(_CMD_HEAD + r"(?:gh\s+pr\s+(?:create|edit|merge|ready|close|reopen|comment"
                                       r"|review)\b|git\s+push\b)")


class GitPrError(Exception):
    """A gh call that could not answer, carrying the reason verbatim so a caller can render it."""


def is_push_command(cmd):
    """True when a Bash command pushed or acted on a PR: a refresh event."""
    return bool(PR_ACT_CMD_RE.search(cmd or ""))


def _git(cwd, *args, timeout=8):
    """(ok, stdout); never raises. Local git failing is "not a repo" or "no upstream", read as absence."""
    if not cwd or not os.path.isdir(cwd):
        return False, ""
    try:
        p = subprocess.run([GIT_BIN, "-C", cwd] + list(args), capture_output=True, text=True,
                           timeout=timeout)
    except Exception:
        return False, ""
    return p.returncode == 0, (p.stdout or "").strip()


# ── the local half: pointer files, statted, so an unchanged checkout costs no fork ────────────────────

def _first_line(path):
    """The first line of a small pointer file, stripped, or '' when unreadable (absent, or torn bytes)."""
    try:
        with open(path) as f:
            return f.readline().strip()
    except (OSError, ValueError):
        return ""


def _mtime(path):
    """st_mtime_ns, or None when the path is absent: absence is part of a signature, not an error."""
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return None


def _resolve(base, rel):
    """`rel` as an absolute path, relative paths taken against `base`."""
    return rel if os.path.isabs(rel) else os.path.normpath(os.path.join(base, rel))


def _find_dotgit(cwd):
    """The `.git` entry of the work tree containing cwd, walking up; '' outside every tree."""
    d = os.path.abspath(cwd)
    while True:
        cand = os.path.join(d, ".git")
        if os.path.exists(cand):
            return cand
        parent = os.path.dirname(d)
        if parent == d:
            return ""
        d = parent


def git_dirs(cwd):
    """(gitdir, commondir) for the tree containing cwd, read from its pointer files, or None.

    A worktree's `.git` is a file naming its private gitdir, whose `commondir` names the shared dir that
    holds the refs, packed-refs and config every worktree reads. No fork: this runs every build pass."""
    if not cwd:
        return None
    dotgit = _find_dotgit(cwd)
    if not dotgit:
        return None
    gitdir = dotgit
    if os.path.isfile(dotgit):
        line = _first_line(dotgit)
        if not line.startswith(_GITDIR_PREFIX):
            return None
        gitdir = _resolve(os.path.dirname(dotgit), line[len(_GITDIR_PREFIX):].strip())
    rel = _first_line(os.path.join(gitdir, "commondir"))
    return gitdir, (_resolve(gitdir, rel) if rel else gitdir)


_REPO_OF = {}     # commondir → ('owner/repo' or '', config mtime)


def repo_of(cwd):
    """'owner/repo' when this checkout's origin is on GitHub, else ''. Memoized on the config file's
    mtime, the file `git remote add` / `set-url` rewrites, so a remote added later is seen."""
    dirs = git_dirs(cwd)
    if not dirs:
        return ""
    config_mtime = _mtime(os.path.join(dirs[1], "config"))
    hit = _REPO_OF.get(dirs[1])
    if hit is not None and hit[1] == config_mtime:
        return hit[0]
    ok, url = _git(cwd, "remote", "get-url", "origin")
    m = _REMOTE_RE.match(url) if (ok and url) else None
    repo = m.group(1) if m else ""
    if len(_REPO_OF) > _MEMO_CAP:
        _REPO_OF.clear()
    _REPO_OF[dirs[1]] = (repo, config_mtime)
    return repo


def _ref_mtimes(common, refs):
    """The mtimes of each loose ref file plus packed-refs: a moved ref rewrites one of them."""
    return tuple(_mtime(os.path.join(common, r)) for r in refs) + (_mtime(os.path.join(common, "packed-refs")),)


_UPSTREAM = {}    # cwd → ((HEAD line, config mtime), upstream full ref name or '')
_LOCAL = {}       # cwd → (signature, (branch, ahead))


def _upstream_ref(cwd, head_line, common):
    """The full ref name of the branch's upstream ('refs/remotes/origin/x'), or ''. It changes only
    with the checked-out branch or the config, so it is re-read only when one of those moved."""
    key = (head_line, _mtime(os.path.join(common, "config")))
    hit = _UPSTREAM.get(cwd)
    if hit is not None and hit[0] == key:
        return hit[1]
    ref = ""
    if head_line.startswith(_SYMREF_PREFIX):
        ok, out = _git(cwd, "rev-parse", "--symbolic-full-name", "@{u}")
        ref = out if ok else ""
    if len(_UPSTREAM) > _MEMO_CAP:
        _UPSTREAM.clear()
    _UPSTREAM[cwd] = (key, ref)
    return ref


def local_state(cwd):
    """(branch, ahead, moved) for the checkout at cwd.

    `branch` is '' when detached or outside a repo. `ahead` counts commits on HEAD its upstream lacks (0
    with no upstream). `moved` is True when HEAD, the branch ref or its upstream moved since the last
    call: the event that says "re-read this repo's PRs". An unchanged checkout costs stats, no fork."""
    dirs = git_dirs(cwd)
    if not dirs:
        return "", 0, False
    gitdir, common = dirs
    head_line = _first_line(os.path.join(gitdir, "HEAD"))
    head_ref = head_line[len(_SYMREF_PREFIX):].strip() if head_line.startswith(_SYMREF_PREFIX) else ""
    upstream = _upstream_ref(cwd, head_line, common)
    sig = (head_line, upstream) + _ref_mtimes(common, [r for r in (head_ref, upstream) if r])
    hit = _LOCAL.get(cwd)
    if hit is not None and hit[0] == sig:
        return hit[1][0], hit[1][1], False
    branch = head_ref[len(_HEADS_PREFIX):] if head_ref.startswith(_HEADS_PREFIX) else ""
    ahead = 0
    if upstream:
        ok, out = _git(cwd, "rev-list", "--count", "@{u}..HEAD")
        ahead = int(out) if (ok and out.isdigit()) else 0
    if len(_LOCAL) > _MEMO_CAP:
        _LOCAL.clear()
    _LOCAL[cwd] = (sig, (branch, ahead))
    return branch, ahead, hit is not None


def commits_ahead_of_main(cwd):
    """Commits on HEAD that the repo's main branch lacks, or 0 when the count cannot be taken, which
    reads as "nothing to open a PR for" rather than "open one anyway"."""
    for base in _MAIN_BRANCHES:
        ok, out = _git(cwd, "rev-list", "--count", "origin/%s..HEAD" % base)
        if ok and out.isdigit():
            return int(out)
    return 0


# ── gh: the authoritative PR state ───────────────────────────────────────────────────────────────────
# ONE list call per repo, shared by every session in it; 100 rows covers the PRs a working day touches,
# and a cited PR older than that window is fetched on its own. statusCheckRollup is kept out of the list
# because asking for it across 100 PRs makes GitHub's GraphQL endpoint time out on a busy repo; checks
# are fetched only for the few PRs a session references.
_LIST_LIMIT = 100
_GH_FIELDS = ("number,title,url,headRefName,state,isDraft,reviewDecision,"
              "updatedAt,additions,deletions,changedFiles")
_CHECK_FIELDS = "number,statusCheckRollup"
_MAX_SINGLE_FETCHES = 12   # cited PRs outside the list window, per refresh
_MAX_CHECK_FETCHES = 12    # checks rollups per refresh
_MAX_FAILING_NAMES = 6
_PR_STATES = ("open", "merged", "closed")

# Conclusions that mean a check FAILED. SKIPPED / NEUTRAL / SUCCESS are not failures.
_CHECK_BAD = ("FAILURE", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE")
_CHECK_PENDING = ("IN_PROGRESS", "QUEUED", "PENDING", "WAITING", "REQUESTED")


def _iso_to_epoch(s):
    """GitHub's '2026-08-17T10:00:00Z' as epoch seconds, or 0 when unparseable (no age, not a wrong one)."""
    try:
        return calendar.timegm(time.strptime(s, "%Y-%m-%dT%H:%M:%SZ"))
    except Exception:
        return 0


def _checks(rollup):
    """(state, failing names). A failure outranks a running check, since "running" reads as "nothing
    wrong yet". None means not asked yet: "unknown", distinct from "none" (this PR has no checks)."""
    if rollup is None:
        return "unknown", []
    failing, running, any_check = [], False, False
    for c in rollup or []:
        if not isinstance(c, dict):
            continue
        any_check = True
        concl = (c.get("conclusion") or "").upper()
        status = (c.get("status") or "").upper()
        if concl in _CHECK_BAD:
            failing.append(c.get("name") or "check")
        elif not concl or status in _CHECK_PENDING:
            running = True
    if failing:
        return "fail", failing
    if running:
        return "running", []
    return ("pass", []) if any_check else ("none", [])


def normalize(raw):
    """One `gh pr list` row as the payload dict the pane renders, every enum lowercased. A row with no
    statusCheckRollup key (the cheap list query) yields checksState "unknown"."""
    state = (raw.get("state") or "").lower()
    cstate, failing = _checks(raw["statusCheckRollup"] if "statusCheckRollup" in raw else None)
    return {"num": int(raw.get("number") or 0),
            "url": raw.get("url") or "",
            "title": raw.get("title") or "",
            "branch": raw.get("headRefName") or "",
            "state": state if state in _PR_STATES else "open",
            "draft": bool(raw.get("isDraft")),
            "checksState": cstate,
            "checksFailing": failing[:_MAX_FAILING_NAMES],
            "reviewDecision": (raw.get("reviewDecision") or "").lower() or "none",
            "adds": int(raw.get("additions") or 0),
            "dels": int(raw.get("deletions") or 0),
            "files": int(raw.get("changedFiles") or 0),
            "updatedT": _iso_to_epoch(raw.get("updatedAt") or "")}


def branch_pr(prs, branch):
    """The PR number for `branch`, or None. A reused branch name can carry several PRs: an open one wins,
    the newest (largest number) first; else the newest of any state."""
    if not branch:
        return None
    on_branch = [n for n, pr in prs.items() if pr.get("branch") == branch]
    open_ones = [n for n in on_branch if prs[n].get("state") == "open"]
    pool = open_ones or on_branch
    return max(pool) if pool else None


def _gh_json(args, what):
    """Run gh and parse its JSON, or raise GitPrError carrying gh's own last stderr line."""
    try:
        p = subprocess.run([GH_BIN] + list(args), capture_output=True, text=True, timeout=_TIMEOUT)
    except FileNotFoundError:
        raise GitPrError("gh CLI not found on PATH — install it to see PR status")
    except Exception as e:
        raise GitPrError("%s failed: %s" % (what, str(e)[:160]))
    if p.returncode != 0:
        tail = [l for l in (p.stderr or "").strip().splitlines() if l.strip()]
        raise GitPrError(tail[-1][:200] if tail else "%s failed (exit %d)" % (what, p.returncode))
    try:
        return json.loads(p.stdout or "[]")
    except Exception:
        raise GitPrError("%s returned output that is not JSON" % what)


def hydrate(repo, limit=_LIST_LIMIT):
    """{number: PR} for one repo. Raises GitPrError on any gh failure."""
    rows = _gh_json(["pr", "list", "--repo", repo, "--state", "all", "--limit", str(limit),
                     "--json", _GH_FIELDS], "gh pr list")
    out = {}
    for r in rows if isinstance(rows, list) else []:
        pr = normalize(r)
        if pr["num"]:
            out[pr["num"]] = pr
    return out


def hydrate_one(repo, num):
    """A single PR outside the list window. Same shape as hydrate's values."""
    row = _gh_json(["pr", "view", str(num), "--repo", repo, "--json", _GH_FIELDS], "gh pr view")
    return normalize(row) if isinstance(row, dict) else None


def _fill_checks(repo, prs, nums):
    """Fetch statusCheckRollup for `nums` (in order, bounded) into the UNPUBLISHED dict `prs`. A failed
    call leaves that PR "unknown"; the list read already succeeded, so there is no repo error to show."""
    for n in [n for n in nums if n in prs][:_MAX_CHECK_FETCHES]:
        try:
            row = _gh_json(["pr", "view", str(n), "--repo", repo, "--json", _CHECK_FIELDS], "gh pr view")
        except GitPrError:
            continue
        state, failing = _checks((row or {}).get("statusCheckRollup"))
        prs[n] = dict(prs[n], checksState=state, checksFailing=failing[:_MAX_FAILING_NAMES])


# ── the cache ────────────────────────────────────────────────────────────────────────────────────────
# repo → {"prs": {num: PR}, "err": str, "fresh": bool}. A published entry is never mutated: a refresh
# assembles its dict privately and swaps the entry in whole, so a build-thread reader cannot see a dict
# change size under it. `_GEN` counts invalidations; a refresh that finishes after one happened publishes
# `fresh` False, so a push landing mid-refresh is re-read rather than lost.
_CACHE = {}
_GEN = {}          # repo → invalidation count
_WANTED = {}       # repo → every PR number a session has cited (cumulative, so none is later evicted)
_BRANCHES = {}     # repo → branch names sessions are on, whose PR's checks come first
_TRIED = {}        # repo → cited numbers gh could not return, so they are not re-kicked forever
_INFLIGHT = set()  # repos with a refresh running
_LOCK = threading.Lock()


def invalidate(repo):
    """Mark a repo's PR set stale, including one being refreshed right now."""
    with _LOCK:
        _GEN[repo] = _GEN.get(repo, 0) + 1
        ent = _CACHE.get(repo)
        if ent and ent.get("fresh"):
            _CACHE[repo] = dict(ent, fresh=False)


def retry(repo):
    """A user asked for a re-read: forget which cited numbers gh could not return, then invalidate."""
    with _LOCK:
        _TRIED.pop(repo, None)
    invalidate(repo)


def _want(repo, nums, branch):
    """Record what a session needs from `repo`; invalidate when it names a number never asked for, so
    the next refresh fetches it (and checks its CI) instead of serving a set that lacks it."""
    with _LOCK:
        wanted = _WANTED.setdefault(repo, set())
        new = set(nums) - wanted
        wanted.update(new)
        if branch:
            _BRANCHES.setdefault(repo, set()).add(branch)
    if new:
        invalidate(repo)


def _check_order(prs, branches, wanted):
    """The PRs to fetch checks for: every session branch's own PR first, then the cited ones."""
    heads = sorted({branch_pr(prs, b) for b in branches} - {None}, reverse=True)
    return heads + sorted(n for n in wanted if n not in heads)


def _assemble(repo, prs):
    """Complete a fresh list read in private: fetch cited PRs outside the window, then checks."""
    with _LOCK:
        wanted = set(_WANTED.get(repo) or ())
        branches = set(_BRANCHES.get(repo) or ())
        tried = _TRIED.setdefault(repo, set())
    for n in sorted(wanted - set(prs) - tried, reverse=True)[:_MAX_SINGLE_FETCHES]:
        try:
            one = hydrate_one(repo, n)
        except GitPrError:
            one = None
        if one:
            prs[one["num"]] = one
        else:
            with _LOCK:
                tried.add(n)
    _fill_checks(repo, prs, _check_order(prs, branches, wanted))
    return prs


def _refresh(repo):
    """The background body: one list read, completed privately, published once."""
    with _LOCK:
        gen = _GEN.get(repo, 0)
    try:
        prs, err = _assemble(repo, hydrate(repo)), ""
    except GitPrError as e:
        prs, err = None, str(e)
    with _LOCK:
        if prs is None:
            # Keep the last good snapshot beside the reason: the pane shows both, and the poll retries.
            prs = (_CACHE.get(repo) or {}).get("prs") or {}
        _CACHE[repo] = {"prs": prs, "err": err, "fresh": _GEN.get(repo, 0) == gen}


def repo_prs(repo, nums=(), branch=""):
    """(prs, error) for one repo, never blocking. gh is a network call (seconds on a busy repo) reached
    from the per-push build pass, so a stale entry serves what it has and refreshes in the background."""
    if not repo:
        return {}, ""
    _want(repo, nums, branch)
    ent = _CACHE.get(repo)
    if not (ent and ent.get("fresh")):
        _kick(repo)
    return (ent or {}).get("prs") or {}, (ent or {}).get("err") or ""


def _kick(repo):
    """Start one background refresh per repo, never two. A request made while one runs is not lost: it
    bumped the generation or the wanted set, which the running refresh re-reads or publishes as stale."""
    with _LOCK:
        if repo in _INFLIGHT:
            return
        _INFLIGHT.add(repo)

    def run():
        try:
            _refresh(repo)
        finally:
            with _LOCK:
                _INFLIGHT.discard(repo)

    threading.Thread(target=run, name="gitpr-" + repo, daemon=True).start()


def needs_poll(repo):
    """True while a cached PR's check is still running, or the last read failed. Neither CI finishing
    nor the network recovering produces a local event, so these are what the one poll waits on."""
    ent = _CACHE.get(repo) or {}
    if ent.get("err"):
        return True
    return any(pr.get("checksState") == "running" for pr in list((ent.get("prs") or {}).values()))


# ── the refresh events ───────────────────────────────────────────────────────────────────────────────
_POLLED = {}      # repo → time.monotonic() of the last poll-driven refresh
_POLL_SECS = 30   # the one interval in this module; see needs_poll


def note_local_state(cwd, repo):
    """(branch, ahead) for cwd, invalidating `repo` when HEAD, the branch or its upstream moved."""
    branch, ahead, moved = local_state(cwd)
    if moved:
        invalidate(repo)
    return branch, ahead


def note_push_turn(repo):
    """A turn ran git push / gh pr in this repo: the remote moved, so re-read it."""
    invalidate(repo)


def poll_due(repo, now):
    """True when the poll should re-read `repo` now: gated on needs_poll, paced by _POLL_SECS. `now` is
    time.monotonic(), passed in so a test can drive it."""
    if not needs_poll(repo):
        return False
    last = _POLLED.get(repo)
    if last is not None and (now - last) < _POLL_SECS:
        return False
    _POLLED[repo] = now
    invalidate(repo)
    return True
