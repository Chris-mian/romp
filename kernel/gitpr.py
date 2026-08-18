#!/usr/bin/env python3
"""PRs as a session's artifacts (the user 2026-08-17).

The Outline pane shows, per goal, the PR that goal shipped and that PR's live state. Every `git` and `gh`
shell-out for that surface lives HERE, so the read side (build_session) stays a pure assembler and the one
place that talks to the network is the one place that caches and reports its own failures.

Rules this module is bound by:
  * `gh` is the AUTHORITATIVE source for PR state — never scraped prose, never a guess.
  * When git or gh cannot answer, say so. A caller must be able to render the REASON; a blank chip would
    claim "no PR" when the truth is "we could not look".
  * Refresh is EVENT-DRIVEN — a new HEAD sha, a branch change, a push/gh-pr turn, a mined url, a user
    click. No age thresholds anywhere in the cache.

The probes below are the LOCAL half: which repo a session sits in, which branch, how far ahead of its
upstream and of main it is. All are a few milliseconds and safe to call per build pass.
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
_TIMEOUT = 20        # a hung network call must never stall a build pass


class GitPrError(Exception):
    """A gh call that could not answer, carrying the reason verbatim so a caller can render it. Raised
    rather than swallowed: a blank chip would claim "no PR" when the truth is "we could not look"."""

# owner/repo out of any GitHub remote form, including a per-account ssh HOST ALIAS
# (git@github.com-personal:owner/repo.git) — a user's identity machinery is their business, and the repo
# it names is still on github.com. The optional .git suffix and trailing slash are stripped.
_REMOTE_RE = re.compile(r"^(?:https://github\.com/"
                        r"|(?:ssh://)?git@github\.com(?:-[A-Za-z0-9._-]+)?[:/])"
                        r"([A-Za-z0-9._-]+/[A-Za-z0-9._-]+?)(?:\.git)?/?$")

_MAIN_BRANCHES = ("main", "master")


def _git(cwd, *args, timeout=8):
    """(ok, stdout) — never raises. git here is local, so a failure is nearly always "not a repo" or
    "no upstream", both of which callers read as a plain absence rather than an error to surface."""
    if not cwd or not os.path.isdir(cwd):
        return False, ""
    try:
        p = subprocess.run([GIT_BIN, "-C", cwd] + list(args), capture_output=True, text=True,
                           timeout=timeout)
    except Exception:
        return False, ""
    return p.returncode == 0, (p.stdout or "").strip()


def repo_of(cwd):
    """'owner/repo' when this session's checkout has a GitHub origin, else ''. A non-GitHub forge, a
    remote-less repo and a non-repo are all '' — there is no PR surface for any of them."""
    ok, url = _git(cwd, "remote", "get-url", "origin")
    if not ok or not url:
        return ""
    m = _REMOTE_RE.match(url)
    return m.group(1) if m else ""


def is_repo(cwd):
    """True when cwd is inside a git work tree. Lets a caller tell 'not a repo' (say nothing) from 'a
    repo we could not read' (say something)."""
    ok, out = _git(cwd, "rev-parse", "--is-inside-work-tree")
    return ok and out == "true"


def branch_of(cwd):
    """The current branch, or '' when detached (rev-parse answers the literal 'HEAD') or not a repo.
    Detached is not a branch: there is nothing to attribute a PR to, and nothing to open one for."""
    ok, out = _git(cwd, "rev-parse", "--abbrev-ref", "HEAD")
    return "" if (not ok or out == "HEAD") else out


def head_of(cwd):
    """HEAD's sha, or ''. The event key that says 'this checkout moved, re-read its PRs'."""
    ok, out = _git(cwd, "rev-parse", "HEAD")
    return out if ok else ""


def ahead_of(cwd):
    """Commits on HEAD that its upstream does not have — the signal behind the chip's live mark. 0 when
    there is no upstream (nothing to be ahead OF, not infinitely ahead) or no repo."""
    ok, out = _git(cwd, "rev-list", "--count", "@{u}..HEAD")
    return int(out) if (ok and out.isdigit()) else 0


def commits_ahead_of_main(cwd):
    """Commits on HEAD that the repo's main branch does not have — 'this branch carries work', measured
    against what a PR would actually target. 0 when the count cannot be taken (no origin/main, no repo),
    which reads as 'nothing to open a PR for' rather than 'open one anyway'."""
    for base in _MAIN_BRANCHES:
        ok, out = _git(cwd, "rev-list", "--count", "origin/%s..HEAD" % base)
        if ok and out.isdigit():
            return int(out)
    return 0


# ── gh: the authoritative PR state ───────────────────────────────────────────────────────────────────
# ONE gh call per REPO — not per PR, and not per session: several sessions commonly share a checkout's
# repo, and 100 rows covers every PR a working day touches. A mined PR older than that window is fetched
# individually by hydrate_one.
# statusCheckRollup is DELIBERATELY not in the list query. Asking for it across 100 PRs makes GitHub's
# GraphQL endpoint time out on a busy repo — measured 2026-08-18 against a real one: 504 with the rollup,
# and the identical call without it answered in 5.3s. So the list stays cheap and checks are fetched only
# for the handful of PRs a session actually references (_CHECK_FIELDS, via checks_for).
_GH_FIELDS = ("number,title,url,headRefName,state,isDraft,reviewDecision,"
              "updatedAt,additions,deletions,changedFiles")
_CHECK_FIELDS = "number,statusCheckRollup"

# Conclusions that mean a check FAILED. SKIPPED / NEUTRAL / SUCCESS are not failures — flagging a skipped
# optional job would cry wolf on every PR that has one.
_CHECK_BAD = ("FAILURE", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE")
_CHECK_PENDING = ("IN_PROGRESS", "QUEUED", "PENDING", "WAITING", "REQUESTED")


def _iso_to_epoch(s):
    """GitHub's '2026-08-17T10:00:00Z' → epoch seconds, or 0 when unparseable — the pane then shows no
    age rather than a wrong one."""
    try:
        return calendar.timegm(time.strptime(s, "%Y-%m-%dT%H:%M:%SZ"))
    except Exception:
        return 0


def _checks(rollup):
    """(state, failing names). A FAILURE outranks a still-running check: the worst KNOWN state is what
    the chip has to show, because 'running' reads as 'nothing wrong yet'.

    `rollup` is None when we have not asked yet — "unknown", which must stay DISTINCT from "none" (this PR
    has no checks): rendering unknown as a green tick would invent a passing CI out of missing data."""
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
    """One `gh pr list` row → the payload dict the pane renders. Every enum is lowercased here so no
    client ever has to branch on GitHub's SHOUTING vocabulary. A row with no statusCheckRollup key at all
    (the cheap list query) yields checksState "unknown", not "none"."""
    state = (raw.get("state") or "").lower()
    cstate, failing = _checks(raw["statusCheckRollup"] if "statusCheckRollup" in raw else None)
    return {"num": int(raw.get("number") or 0),
            "url": raw.get("url") or "",
            "title": raw.get("title") or "",
            "branch": raw.get("headRefName") or "",
            "state": state if state in ("open", "merged", "closed") else "open",
            "draft": bool(raw.get("isDraft")),
            "checksState": cstate,
            "checksFailing": failing[:6],
            "reviewDecision": (raw.get("reviewDecision") or "").lower() or "none",
            "adds": int(raw.get("additions") or 0),
            "dels": int(raw.get("deletions") or 0),
            "files": int(raw.get("changedFiles") or 0),
            "updatedT": _iso_to_epoch(raw.get("updatedAt") or "")}


def _gh_json(args, what):
    """Run gh and parse its JSON, or raise GitPrError carrying gh's own words. gh's stderr already says
    the useful thing ("run: gh auth login"), so it is passed through rather than paraphrased."""
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


def hydrate(repo, limit=100):
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
    """A single PR outside the list window (an old mined url). Same shape as hydrate's values."""
    row = _gh_json(["pr", "view", str(num), "--repo", repo, "--json", _GH_FIELDS], "gh pr view")
    return normalize(row) if isinstance(row, dict) else None


# ── the cache ────────────────────────────────────────────────────────────────────────────────────────
# repo → {"prs": {num: PR}, "err": str, "fresh": bool}. Invalidation is EVENT-DRIVEN: the kernel calls
# invalidate() on a new HEAD sha, a branch change, a turn that ran git push / gh pr, a newly mined url, or
# a user opening a chip. There is deliberately NO age field — an age would be exactly the time-based
# heuristic the design rules send you looking for an event instead.
_CACHE = {}
_INFLIGHT = set()          # repos with a refresh in flight
_INFLIGHT_LOCK = threading.Lock()


def invalidate(repo):
    """Mark a repo's PR set stale; the next repo_prs() re-hydrates it."""
    ent = _CACHE.get(repo)
    if ent:
        ent["fresh"] = False


def checks_for(repo, nums):
    """Fill in statusCheckRollup for just these PR numbers, in place on the cache. Kept OUT of the list
    query because the rollup across 100 PRs times GitHub out (see _GH_FIELDS); a session references a
    handful, so a handful of small calls is both faster and survivable."""
    ent = _CACHE.get(repo)
    if not ent:
        return
    for n in list(nums)[:12]:                # a bound, so a pathological session cannot fan out
        pr = ent["prs"].get(n)
        if not pr or pr.get("checksState") != "unknown":
            continue
        try:
            row = _gh_json(["pr", "view", str(n), "--repo", repo, "--json", _CHECK_FIELDS], "gh pr view")
        except GitPrError:
            continue                          # leave it unknown; the repo-level error already shows
        state, failing = _checks((row or {}).get("statusCheckRollup"))
        pr["checksState"], pr["checksFailing"] = state, failing[:6]


def _refresh(repo, nums):
    """The background body: one cheap list, then checks for the referenced few."""
    try:
        prs, err = hydrate(repo), ""
    except GitPrError as e:
        prs, err = {}, str(e)
    ent = _CACHE.get(repo) or {}
    if err and ent.get("prs"):
        # Keep the last good snapshot AND surface the error. PR state is inherently a snapshot, and a
        # visible "we could not re-read" over known data beats blanking the pane — but the error must ride
        # along, never be swallowed into a confident-looking display.
        _CACHE[repo] = {"prs": ent["prs"], "err": err, "fresh": True}
    else:
        _CACHE[repo] = {"prs": prs, "err": err, "fresh": True}
    if err:
        return
    # A referenced PR older than the list window: fetch it individually so an old goal's chip still works.
    ent = _CACHE[repo]
    for n in sorted(set(nums) - set(ent["prs"]))[:6]:
        try:
            one = hydrate_one(repo, n)
        except GitPrError:
            continue
        if one:
            ent["prs"][one["num"]] = one
    checks_for(repo, nums)


def repo_prs(repo, nums=()):
    """(prs, error) for one repo — NEVER blocking.

    gh is a network call: measured at 5s on a busy repo, and it is reached from the kernel's per-push build
    pass, so calling it inline would stall every pane on the dashboard (found 2026-08-18 running this on a
    real machine). So a stale cache serves what it has and schedules a refresh in the background; the pane
    pushes again within seconds and picks up the answer. '' repo is a silent empty: no PR surface at all."""
    if not repo:
        return {}, ""
    ent = _CACHE.get(repo)
    if ent and ent.get("fresh"):
        return ent["prs"], ent["err"]
    _kick(repo, nums)
    return (ent or {}).get("prs") or {}, (ent or {}).get("err") or ""


def _kick(repo, nums=()):
    """Start one background refresh per repo — never two, so a burst of pushes cannot fan out into a pile
    of concurrent gh calls."""
    with _INFLIGHT_LOCK:
        if repo in _INFLIGHT:
            return
        _INFLIGHT.add(repo)

    def run():
        try:
            _refresh(repo, nums)
        finally:
            with _INFLIGHT_LOCK:
                _INFLIGHT.discard(repo)

    t = threading.Thread(target=run, name="gitpr-" + repo, daemon=True)
    t.start()


def needs_poll(repo):
    """True while any cached PR of this repo has a non-terminal check. CI finishing is a genuinely
    external event with no local signal, so this ONE poll is justified — and it stops the moment every
    check reaches a terminal state."""
    ent = _CACHE.get(repo) or {}
    return any(pr.get("checksState") == "running" for pr in (ent.get("prs") or {}).values())


# ── the refresh events ───────────────────────────────────────────────────────────────────────────────
_LOCAL = {}       # cwd → (head sha, branch) last seen
_POLLED = {}      # repo → time.monotonic() of the last poll-driven refresh
_POLL_SECS = 30   # the ONE interval in this module; see poll_due for why it earns its place

# A turn that pushed or acted on a PR moved remote state with no other local signal. Anchored to the
# command's START, so a command that merely CONTAINS the words — a grep for "git push" in the docs —
# never fires a refresh.
_PUSH_RE = re.compile(r"^\s*(?:git\s+push\b|gh\s+pr\b)")


def is_push_command(cmd):
    """True when a Bash command pushed or acted on a PR: a refresh event."""
    return bool(_PUSH_RE.search(cmd or ""))


def note_local_state(cwd, repo):
    """Record this checkout's (HEAD, branch) and invalidate `repo` when either moved; True when it did.
    The ordinary per-build event check — two local git calls, no network."""
    cur = (head_of(cwd), branch_of(cwd))
    prev = _LOCAL.get(cwd)
    _LOCAL[cwd] = cur
    if prev == cur:
        return False
    invalidate(repo)
    return True


def note_push_turn(repo):
    """A turn ran git push / gh pr in this repo — the remote moved, so re-read it."""
    invalidate(repo)


def poll_due(repo, now):
    """True when the checks-bounded poll should re-read `repo` now.

    Gated on needs_poll FIRST, so a repo whose every check is terminal is never polled again; _POLL_SECS
    only paces the wait for CI, the one state change that produces no local event to key on. `now` is
    time.monotonic(), passed in so a test can drive it."""
    if not needs_poll(repo):
        return False
    last = _POLLED.get(repo)
    if last is not None and (now - last) < _POLL_SECS:
        return False
    _POLLED[repo] = now
    invalidate(repo)
    return True
