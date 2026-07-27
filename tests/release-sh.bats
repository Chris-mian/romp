#!/usr/bin/env bats

# scripts/release.sh — the release gate. Two rules it exists to enforce:
#   * the tag must be v-prefixed (bootstrap.sh's `git tag -l 'v*'` selector matches
#     nothing otherwise, and the installer silently falls back to main), and
#   * the macOS CI run — which is dispatch-only, since macOS is billed even on public
#     repos — must be GREEN before a version is tagged.
# The GitHub CLI is stubbed via ROMP_GH so none of this touches real CI.

ROMP_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"

setup() {
    TEST_DIR="$(mktemp -d)"
    REPO="$TEST_DIR/repo"
    mkdir -p "$REPO/scripts"
    cp "$ROMP_DIR/scripts/release.sh" "$REPO/scripts/"
    git init -q "$REPO"
    git -C "$REPO" config user.email t@e.invalid
    git -C "$REPO" config user.name t
    echo "0.1.0" > "$REPO/VERSION"
    git -C "$REPO" add -A
    git -C "$REPO" commit -qm init
    export ROMP_RELEASE_POLL=0          # no sleeping in tests
    export GH_LOG="$TEST_DIR/gh.log"
}
teardown() { rm -rf "$TEST_DIR"; }

# STUB_CONCLUSION = what the stubbed `gh run view` reports (default success).
# STUB_FLAKY_VIEWS = report nothing for the first N `run view` calls, as a
# transient API error looks to the poll loop, then the real conclusion.
_stub_gh() {
    cat > "$TEST_DIR/gh" <<STUB
#!/usr/bin/env bash
TEST_DIR="$TEST_DIR"
echo "\$@" >> "$GH_LOG"
case "\$1 \$2" in
  # a NEW run id appears only after a dispatch, as the real API behaves
  "run list")   if [ -f "$TEST_DIR/dispatched" ]; then echo 1000; else echo 999; fi ;;
  "workflow run") touch "$TEST_DIR/dispatched"; exit 0 ;;
  "run view")
      n=\$(( \$(cat "$TEST_DIR/views" 2>/dev/null || echo 0) + 1 )); echo "\$n" > "$TEST_DIR/views"
      if [ "\$n" -le "\${STUB_FLAKY_VIEWS:-0}" ]; then exit 1; fi
      echo "\${STUB_CONCLUSION:-success}" ;;
esac
exit 0
STUB
    chmod +x "$TEST_DIR/gh"
    export ROMP_GH="$TEST_DIR/gh"
}

@test "release: refuses a tag that is not v-prefixed" {
    _stub_gh
    run "$REPO/scripts/release.sh" 0.1.0
    [ "$status" -ne 0 ]
    [[ "$output" == *"must be v-prefixed"* ]]
    # and it bailed BEFORE spending 16 minutes of macOS CI
    [ ! -s "$GH_LOG" ]
}

@test "release: refuses when the macOS run fails, and does NOT tag" {
    _stub_gh
    STUB_CONCLUSION=failure run "$REPO/scripts/release.sh" v0.1.0
    [ "$status" -ne 0 ]
    [[ "$output" == *"macOS run did not pass"* ]]
    run git -C "$REPO" tag -l
    [ -z "$output" ]
}

@test "release: a transient API error while watching does not fail the gate" {
    # `gh run watch` treated a dropped connection as a failed RUN and refused a
    # green release twice (2026-07-27); the poll must ride out empty answers.
    _stub_gh
    ROMP_RELEASE_POLL=0.01 STUB_FLAKY_VIEWS=3 run "$REPO/scripts/release.sh" v0.1.0
    [ "$status" -eq 0 ]
    [[ "$output" == *"macOS run green"* ]]
    run git -C "$REPO" tag -l
    [ "$output" = "v0.1.0" ]
}

@test "release: tags when the macOS run is green" {
    _stub_gh
    run "$REPO/scripts/release.sh" v0.1.0
    [ "$status" -eq 0 ]
    [[ "$output" == *"macOS run green"* ]]
    run git -C "$REPO" tag -l
    [ "$output" = "v0.1.0" ]
    grep -q "workflow run CI" "$GH_LOG"      # it really did dispatch
}

@test "release: --skip-macos tags without CI, but says so loudly" {
    _stub_gh
    run "$REPO/scripts/release.sh" v0.1.0 --skip-macos
    [ "$status" -eq 0 ]
    [[ "$output" == *"SKIPPING the macOS check"* ]]
    [ ! -s "$GH_LOG" ]                        # no CI was dispatched
    run git -C "$REPO" tag -l
    [ "$output" = "v0.1.0" ]
}

@test "release: refuses when VERSION disagrees with the tag" {
    _stub_gh
    run "$REPO/scripts/release.sh" v9.9.9
    [ "$status" -ne 0 ]
    [[ "$output" == *"VERSION says"* ]]
}

@test "release: refuses a dirty tree" {
    _stub_gh
    echo dirty > "$REPO/junk.txt"
    git -C "$REPO" add junk.txt
    run "$REPO/scripts/release.sh" v0.1.0
    [ "$status" -ne 0 ]
    [[ "$output" == *"dirty"* ]]
}

@test "release: refuses a tag that already exists" {
    _stub_gh
    git -C "$REPO" tag v0.1.0
    run "$REPO/scripts/release.sh" v0.1.0
    [ "$status" -ne 0 ]
    [[ "$output" == *"already exists"* ]]
}

@test "release: the v-prefix guard accepts a prerelease tag" {
    _stub_gh
    echo "0.2.0-rc.1" > "$REPO/VERSION"
    git -C "$REPO" commit -qam ver
    run "$REPO/scripts/release.sh" v0.2.0-rc.1
    [ "$status" -eq 0 ]
    run git -C "$REPO" tag -l
    [ "$output" = "v0.2.0-rc.1" ]
}
