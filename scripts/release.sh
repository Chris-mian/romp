#!/usr/bin/env bash
# scripts/release.sh vX.Y.Z — cut a romp release, with the macOS check as a HARD GATE.
#
# Why a script rather than `git tag`: two release rules are easy to get wrong by hand
# and expensive to get wrong in public.
#
#   1. The tag MUST be v-prefixed. bootstrap.sh picks the release with
#      `git tag -l 'v*' --sort=-v:refname | head -n1`. A tag like "0.1.0" matches
#      NOTHING, so the one-line installer silently falls back to main instead of
#      installing the release — no error, just the wrong thing. This refuses a
#      non-v tag outright.
#   2. macOS CI does not run on pushes (it is billed even on public repos, ~10x,
#      so it is workflow_dispatch-only). That means a macOS-only breakage can sit
#      undetected until a user hits it. Releasing is exactly when that matters, so
#      this triggers the macOS run and REFUSES to tag unless it goes green.
#
# --skip-macos exists for the case where you must ship anyway; it is deliberately
# an explicit flag (never an env default) and it says so loudly.
set -euo pipefail

GH="${ROMP_GH:-gh}"                       # overridable so tests can stub the GitHub CLI
POLL="${ROMP_RELEASE_POLL:-5}"            # seconds between checks while the run starts
REF="${ROMP_RELEASE_REF:-main}"
skip_macos=0

usage() { echo "usage: scripts/release.sh vX.Y.Z [--skip-macos]" >&2; exit 2; }

tag=""
while [ $# -gt 0 ]; do
    case "$1" in
        --skip-macos) skip_macos=1 ;;
        -h|--help)    usage ;;
        -*)           echo "release: unknown flag $1" >&2; usage ;;
        *)            [ -z "$tag" ] || usage; tag="$1" ;;
    esac
    shift
done
[ -n "$tag" ] || usage

die() { echo "release: $*" >&2; exit 1; }

# ── 1. the v-prefix rule ──────────────────────────────────────────────
if [[ ! "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+([-.][0-9A-Za-z.-]+)?$ ]]; then
    die "tag must be v-prefixed semver, e.g. v0.1.0 (got '$tag').
  bootstrap.sh selects releases with \`git tag -l 'v*'\`; a non-v tag matches
  nothing and the installer silently falls back to main."
fi

# Resolve the repo from THIS SCRIPT's location, never the caller's cwd. With
# `git rev-parse --show-toplevel` the script would inspect — and tag — whatever
# repo you happened to be standing in, reading that tree's cleanliness and
# VERSION instead of the one being released.
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

# `&&` would make a MISSING tag (the normal case) the last command and exit
# non-zero under `set -e`, so this is an explicit if.
if git rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
    die "tag $tag already exists."
fi

# ── 2. the tree must be releasable ────────────────────────────────────
[ -z "$(git status --porcelain)" ] || die "working tree is dirty — commit or stash first."

# VERSION carries the number without the v; a mismatch means one of them was forgotten.
if [ -f VERSION ]; then
    want="${tag#v}"
    have="$(tr -d '[:space:]' < VERSION)"
    [ "$want" = "$have" ] || die "VERSION says '$have' but the tag is '$tag' — update VERSION first."
fi

# ── 3. the macOS gate ─────────────────────────────────────────────────
if [ "$skip_macos" -eq 1 ]; then
    echo "release: !! SKIPPING the macOS check at your explicit request (--skip-macos)."
    echo "release: !! a macOS-only breakage in $tag would reach users undetected."
else
    echo "release: triggering the macOS CI run on $REF (it is dispatch-only, so this is the check)..."
    before="$("$GH" run list --workflow CI --event workflow_dispatch -L 1 --json databaseId -q '.[0].databaseId // ""' 2>/dev/null || true)"
    "$GH" workflow run CI --ref "$REF" || die "could not dispatch the CI workflow."

    # Identify OUR run by waiting for the newest dispatch run to differ from the one
    # that was newest before we dispatched — `gh workflow run` prints no run id, and
    # taking the newest unconditionally would happily watch a PREVIOUS run and pass
    # the gate on a stale green.
    #
    # Each guard is a full `if`: under `set -e`, a bare `[ x ] && y` whose test is
    # false makes the whole list non-zero and kills the script.
    run_id=""
    for _ in $(seq 1 60); do
        if [ "$POLL" != "0" ]; then sleep "$POLL"; fi
        cur="$("$GH" run list --workflow CI --event workflow_dispatch -L 1 --json databaseId -q '.[0].databaseId // ""' 2>/dev/null || true)"
        if [ -n "$cur" ] && [ "$cur" != "$before" ]; then run_id="$cur"; break; fi
        if [ "$POLL" = "0" ]; then break; fi     # test mode: never spin
    done
    if [ -z "$run_id" ]; then
        die "the dispatched CI run never appeared — check the Actions tab."
    fi

    echo "release: watching run $run_id (macOS bats is ~16 min; this is the wait you are paying for)..."
    # Poll `run view`, never `gh run watch`: watch holds one long connection and
    # treats ANY hiccup — a GitHub 502, a local socket error — as run failure.
    # Twice (2026-07-27) it declared a still-running, ultimately GREEN gate "did
    # not pass". Here a transient API error just yields an empty conclusion and
    # we poll again; only the run's own verdict ends the wait.
    conclusion=""
    while :; do
        conclusion="$("$GH" run view "$run_id" --json conclusion -q .conclusion 2>/dev/null || true)"
        if [ -n "$conclusion" ]; then break; fi
        if [ "$POLL" = "0" ]; then break; fi     # test mode: never spin
        sleep "$POLL"
    done
    if [ "$conclusion" != "success" ]; then
        die "the macOS run did not pass (conclusion: ${conclusion:-none}) — NOT tagging $tag.
  Fix it, or re-run with --skip-macos if you have decided to ship anyway."
    fi
    echo "release: macOS run green."
fi

# ── 4. tag ────────────────────────────────────────────────────────────
git tag -a "$tag" -m "romp $tag"
echo "release: created tag $tag."
echo "release: push it with:  git push origin $tag"
