#!/usr/bin/env bash
# One-line install for romp:
#   curl -fsSL https://raw.githubusercontent.com/romp-on/romp/main/bootstrap.sh | bash
#
# Clones romp, checks out the newest release, runs install.sh, and puts bin/ on
# your PATH. The clone IS the installation (install.sh symlinks the hooks, MCP
# config and skills out of it, and bin/ links back into it), so this keeps the
# clone at a stable location rather than a temp dir.
#
# Knobs:
#   ROMP_DIR=~/romp     where to clone (default ~/romp)
#   ROMP_REF=main       install a specific tag/branch instead of the newest release
#   ROMP_NO_PATH=1      don't touch your shell rc
# install.sh's own switches (ROMP_NO_EXT, ROMP_NO_SERVICE, ROMP_NO_SDK) pass through.
set -euo pipefail

REPO="${ROMP_REPO:-https://github.com/romp-on/romp.git}"
DIR="${ROMP_DIR:-$HOME/romp}"

command -v git >/dev/null 2>&1 || {
    echo "romp: git not found. Install git and re-run." >&2; exit 1; }

# Clone, or reuse an existing clone. Refuse to touch a directory that is not a
# romp checkout: this script writes into it and checks out refs, which would be
# destructive to somebody else's files.
if [ -e "$DIR" ]; then
    if [ -d "$DIR/.git" ] && [ -f "$DIR/install.sh" ] && [ -d "$DIR/kernel" ]; then
        echo "==> Updating the romp clone at $DIR"
        git -C "$DIR" fetch --quiet --tags origin
    else
        echo "romp: $DIR exists and is not a romp clone. Refusing to write into it." >&2
        echo "  Move it aside, or choose another location:" >&2
        echo "    curl -fsSL <url> | ROMP_DIR=\"\$HOME/elsewhere\" bash" >&2
        exit 1
    fi
else
    # Name the destination and the knob in the same breath. The clone lands in $HOME
    # regardless of where you run the one-liner from — reasonable for a `curl | bash`
    # (your cwd could be /, /tmp, or somebody else's repo), but surprising if unstated
    # (the user 2026-07-27 asked whether it installs into the current directory).
    echo "==> Cloning romp into $DIR   (override with ROMP_DIR=/path)"
    git clone --quiet "$REPO" "$DIR"
fi

# Pick the ref. Releases are `v`-prefixed, so match on that rather than taking
# the newest tag of any kind: the repo also carries non-release tags, and
# installing one of those would silently pin somebody to an old baseline.
ref="${ROMP_REF:-}"
if [ -z "$ref" ]; then
    ref="$(git -C "$DIR" tag -l 'v*' --sort=-v:refname | head -n1 || true)"
    if [ -z "$ref" ]; then
        ref=main
        echo "    No release tag published yet, so installing the latest code (main)."
    fi
fi

echo "==> Checking out $ref"
git -C "$DIR" checkout --quiet "$ref"
# Fast-forward when the ref is a branch; a tag leaves a detached HEAD, where
# pull is meaningless and expected to fail.
git -C "$DIR" pull --quiet --ff-only >/dev/null 2>&1 || true

# Wire the publishing remote. CLAUDE.md's worktree rule says to publish with
# `git push -u fork <branch>` and never to origin — upstream rulesets reject a
# direct push — but a plain clone has only `origin`, so a fresh install could not
# follow the workflow the repo documents (found on a first Linux install,
# 2026-07-27). Set it up here so the clone arrives ready to contribute.
#
# Only for someone who ACTUALLY HAS a fork. The first cut of this derived <gh-user>/romp from
# whoever gh happened to be logged in as and wired it blind, so anyone with gh installed — the
# overwhelming majority, who only ever want to run romp — got a `fork` remote pointing at a repo
# that does not exist, remote.pushDefault aimed at it, and a line of confusing output in the
# middle of a plain install (the user 2026-07-27, who asked what it was and whether it leaked
# someone else's fork; it does not — it shows the READER's own login — but it was still wrong).
#
# So the auto-detected case must PROVE the fork exists before touching anything, and say nothing
# at all when it doesn't. ROMP_FORK is the explicit escape hatch and is trusted as given (it may
# name a fork on a host gh cannot see). Never overwrites an existing `fork` remote — a
# contributor may have pointed it somewhere deliberately.
if [ -z "${ROMP_NO_FORK_REMOTE:-}" ] && ! git -C "$DIR" remote get-url fork >/dev/null 2>&1; then
    fork_url="${ROMP_FORK:-}"
    if [ -z "$fork_url" ] && command -v gh >/dev/null 2>&1; then
        gh_user="$(gh api user --jq .login 2>/dev/null || true)"
        # `gh repo view` is the existence check the first version lacked. Requiring it to be a
        # FORK too keeps us off an unrelated repo that merely happens to be called "romp".
        if [ -n "$gh_user" ] \
           && [ "$(gh repo view "$gh_user/romp" --json isFork --jq .isFork 2>/dev/null)" = "true" ]; then
            fork_url="https://github.com/$gh_user/romp.git"
        fi
    fi
    if [ -n "$fork_url" ]; then
        git -C "$DIR" remote add fork "$fork_url" 2>/dev/null || true
        git -C "$DIR" config remote.pushDefault fork
        echo "    Publishing remote 'fork' -> $fork_url (a bare \`git push\` goes there, not upstream)"
    fi
fi

echo "==> Running install.sh"
"$DIR/install.sh"

# Put bin/ on PATH. Idempotent: keyed on the exact line, so re-running this
# script never stacks up duplicates.
if [ -z "${ROMP_NO_PATH:-}" ]; then
    case "$(basename "${SHELL:-}")" in
        zsh)  rc="$HOME/.zshrc";  line="export PATH=\"\$PATH:$DIR/bin\"" ;;
        bash) if [ -f "$HOME/.bashrc" ]; then rc="$HOME/.bashrc"
              else rc="$HOME/.bash_profile"; fi
              line="export PATH=\"\$PATH:$DIR/bin\"" ;;
        fish) rc="$HOME/.config/fish/config.fish"; line="fish_add_path $DIR/bin" ;;
        *)    rc=""; line="export PATH=\"\$PATH:$DIR/bin\"" ;;
    esac
    if [ -n "$rc" ]; then
        mkdir -p "$(dirname "$rc")"
        if [ -f "$rc" ] && grep -qF "$DIR/bin" "$rc"; then
            echo "    PATH already set in $rc"
        else
            printf '\n# romp\n%s\n' "$line" >> "$rc"
            echo "    Added romp to your PATH in $rc"
        fi
    else
        echo "    Unknown shell. Add this to your shell rc yourself:"
        echo "      $line"
    fi
fi

echo
echo "romp is installed at $DIR"
echo "Open a new terminal (or 'source' your shell rc), then run:  romp"
