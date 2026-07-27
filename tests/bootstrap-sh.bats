#!/usr/bin/env bats

# ./bootstrap.sh — the one-line installer:
#   curl -fsSL .../bootstrap.sh | bash
# Hermetic: HOME points at a temp dir and the "origin" is a local fixture repo whose install.sh is
# a stub, so the real install.sh never runs (it would symlink this machine's ~/.claude at the temp
# clone and break Claude Code when the temp dir is removed).

REPO_ROOT="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"

setup() {
    TEST_DIR="$(mktemp -d)"
    export HOME="$TEST_DIR/home"
    mkdir -p "$HOME"
    export SHELL=/bin/zsh
    export ROMP_REPO="$TEST_DIR/origin"

    # A fake romp origin: enough structure for bootstrap's clone check, plus a
    # non-release tag alongside two releases so tag selection is exercised.
    mkdir -p "$ROMP_REPO/kernel"
    printf '#!/usr/bin/env bash\necho STUB_INSTALL_RAN\n' > "$ROMP_REPO/install.sh"
    chmod +x "$ROMP_REPO/install.sh"
    touch "$ROMP_REPO/kernel/.keep"
    git -C "$ROMP_REPO" init -q -b main .
    git -C "$ROMP_REPO" add -A
    git -C "$ROMP_REPO" -c user.email=t@t -c user.name=t commit -qm init
    git -C "$ROMP_REPO" tag not-a-release
    git -C "$ROMP_REPO" -c user.email=t@t -c user.name=t commit -q --allow-empty -m r1
    git -C "$ROMP_REPO" tag v0.1.0
    git -C "$ROMP_REPO" -c user.email=t@t -c user.name=t commit -q --allow-empty -m r2
    git -C "$ROMP_REPO" tag v0.2.0
    git -C "$ROMP_REPO" -c user.email=t@t -c user.name=t commit -q --allow-empty -m post-release
}

teardown() { rm -rf "$TEST_DIR"; }

@test "bootstrap.sh: clones, checks out the newest RELEASE tag, installs, sets PATH" {
    ROMP_DIR="$HOME/romp" run bash "$REPO_ROOT/bootstrap.sh"
    [ "$status" -eq 0 ]
    [[ "$output" == *STUB_INSTALL_RAN* ]]
    # v0.2.0, not the newer untagged commit and not the non-release tag.
    [ "$(git -C "$HOME/romp" describe --tags)" = "v0.2.0" ]
    grep -qF "$HOME/romp/bin" "$HOME/.zshrc"
}

@test "bootstrap.sh: re-running updates in place and does not duplicate the PATH line" {
    ROMP_DIR="$HOME/romp" bash "$REPO_ROOT/bootstrap.sh"
    ROMP_DIR="$HOME/romp" run bash "$REPO_ROOT/bootstrap.sh"
    [ "$status" -eq 0 ]
    [[ "$output" == *"Updating the romp clone"* ]]
    [ "$(grep -cF "$HOME/romp/bin" "$HOME/.zshrc")" = "1" ]
}

@test "bootstrap.sh: ROMP_REF pins a branch instead of the newest release" {
    ROMP_DIR="$HOME/romp" ROMP_REF=main run bash "$REPO_ROOT/bootstrap.sh"
    [ "$status" -eq 0 ]
    [ "$(git -C "$HOME/romp" rev-parse --abbrev-ref HEAD)" = "main" ]
}

@test "bootstrap.sh: falls back to main when no release is tagged yet" {
    git -C "$ROMP_REPO" tag -d v0.1.0 v0.2.0
    ROMP_DIR="$HOME/romp" run bash "$REPO_ROOT/bootstrap.sh"
    [ "$status" -eq 0 ]
    [[ "$output" == *"No release tag published yet"* ]]
    [ "$(git -C "$HOME/romp" rev-parse --abbrev-ref HEAD)" = "main" ]
}

@test "bootstrap.sh: refuses a target directory that is not a romp clone, leaving it untouched" {
    mkdir -p "$HOME/mine" && echo keep > "$HOME/mine/important.txt"
    ROMP_DIR="$HOME/mine" run bash "$REPO_ROOT/bootstrap.sh"
    [ "$status" -eq 1 ]
    [[ "$output" == *"not a romp clone"* ]]
    [ "$(cat "$HOME/mine/important.txt")" = "keep" ]
    [ ! -e "$HOME/mine/.git" ]
}

@test "bootstrap.sh: ROMP_NO_PATH leaves the shell rc alone" {
    ROMP_DIR="$HOME/romp" ROMP_NO_PATH=1 run bash "$REPO_ROOT/bootstrap.sh"
    [ "$status" -eq 0 ]
    [ ! -f "$HOME/.zshrc" ]
}

@test "install.sh: refuses to run piped from curl instead of dangling every hook symlink" {
    # Piped, \$0 is "bash", so install.sh's ROMP_DIR would resolve to the caller's
    # cwd and `ln -s` would happily point ~/.claude at paths that do not exist.
    cd "$TEST_DIR"
    run bash -c "cat '$REPO_ROOT/install.sh' | bash"
    [ "$status" -eq 1 ]
    [[ "$output" == *"cannot be piped from curl"* ]]
    [[ "$output" == *bootstrap.sh* ]]
    [ ! -e "$HOME/.claude/hooks" ]
}

# ── the publishing remote ────────────────────────────────────────────────────
# CLAUDE.md's worktree rule says publish with `git push -u fork <branch>` and never to
# origin (upstream rulesets reject a direct push) — but a plain clone has only `origin`,
# so a fresh install could not follow the workflow the repo documents.

@test "bootstrap.sh: wires a 'fork' remote and pushDefault so a fresh clone can publish" {
    ROMP_DIR="$HOME/romp" ROMP_FORK="https://example.invalid/someone/romp.git" \
        run bash "$REPO_ROOT/bootstrap.sh"
    [ "$status" -eq 0 ]
    [ "$(git -C "$HOME/romp" remote get-url fork)" = "https://example.invalid/someone/romp.git" ]
    [ "$(git -C "$HOME/romp" config --get remote.pushDefault)" = "fork" ]
    # A bare `git push` must target the fork, never upstream.
    [[ "$output" == *"Publishing remote 'fork'"* ]]
}

@test "bootstrap.sh: never clobbers a fork remote the contributor already set" {
    ROMP_DIR="$HOME/romp" ROMP_FORK="https://example.invalid/first/romp.git" \
        run bash "$REPO_ROOT/bootstrap.sh"
    [ "$status" -eq 0 ]
    # Re-running (the documented way to update) must leave their remote alone.
    ROMP_DIR="$HOME/romp" ROMP_FORK="https://example.invalid/second/romp.git" \
        run bash "$REPO_ROOT/bootstrap.sh"
    [ "$status" -eq 0 ]
    [ "$(git -C "$HOME/romp" remote get-url fork)" = "https://example.invalid/first/romp.git" ]
}

@test "bootstrap.sh: no fork remote is not fatal — installing is not contributing" {
    # Most people never push to romp, and gh may be absent or logged out. PATH without gh
    # and no ROMP_FORK: the install must still succeed, just without the remote.
    PATH="/usr/bin:/bin" ROMP_DIR="$HOME/romp" run bash "$REPO_ROOT/bootstrap.sh"
    [ "$status" -eq 0 ]
    [[ "$output" == *STUB_INSTALL_RAN* ]]
}

@test "bootstrap.sh: ROMP_NO_FORK_REMOTE opts out" {
    ROMP_DIR="$HOME/romp" ROMP_FORK="https://example.invalid/someone/romp.git" \
        ROMP_NO_FORK_REMOTE=1 run bash "$REPO_ROOT/bootstrap.sh"
    [ "$status" -eq 0 ]
    ! git -C "$HOME/romp" remote get-url fork 2>/dev/null
}

# ── where the clone lands ────────────────────────────────────────────────────

@test "bootstrap.sh: names the install directory and the knob, since it ignores cwd" {
    # It clones into $HOME regardless of where the one-liner is run from. Reasonable for a
    # `curl | bash`, surprising if unstated (the user asked whether it uses the cwd).
    cd "$TEST_DIR"
    ROMP_DIR="$HOME/romp" run bash "$REPO_ROOT/bootstrap.sh"
    [ "$status" -eq 0 ]
    [[ "$output" == *"Cloning romp into $HOME/romp"* ]]
    [[ "$output" == *"ROMP_DIR"* ]]
    [ ! -e "$TEST_DIR/romp" ]           # never the cwd
}
