#!/usr/bin/env bats

# romp-postal-context.sh is a SessionStart hook: in a romp session (the @romp
# tmux flag) it emits the romp-postal skill body as additionalContext, so the
# postal norms load for romp sessions without living in the global CLAUDE.md.
# Outside a romp session it must be silent — and it must never fail the turn.

setup() {
    TEST_DIR="$(mktemp -d)"
    export HOME="$TEST_DIR/home"
    mkdir -p "$HOME/.claude/skills/romp-postal"
    printf -- '---\nname: romp-postal\ndescription: d\n---\nPOSTAL NORMS: lead with DELEGATE/COORDINATE/QUESTION.\n' \
        > "$HOME/.claude/skills/romp-postal/SKILL.md"
    MOCK="$TEST_DIR/mock"; mkdir -p "$MOCK"
    # mock tmux: `tmux show -v @romp` prints $FAKE_ROMP
    cat > "$MOCK/tmux" <<'MOCK'
#!/usr/bin/env bash
[ "$1" = show ] && echo "${FAKE_ROMP:-}"
exit 0
MOCK
    chmod +x "$MOCK/tmux"
    export PATH="$MOCK:$PATH"
    HOOK="$(cd "$(dirname "$BATS_TEST_FILENAME")/../hooks" && pwd)/romp-postal-context.sh"
}

teardown() { rm -rf "$TEST_DIR"; }

@test "in a romp session it emits the skill body as additionalContext" {
    FAKE_ROMP=1 run bash -c 'echo "{}" | "'"$HOOK"'"'
    [ "$status" -eq 0 ]
    [[ "$output" == *'"additionalContext"'* ]]
    [[ "$output" == *'"hookEventName": "SessionStart"'* ]]
    [[ "$output" == *'POSTAL NORMS: lead with DELEGATE'* ]]
    [[ "$output" != *'name: romp-postal'* ]]   # YAML frontmatter is stripped
}

@test "outside a romp session it is silent" {
    FAKE_ROMP="" run bash -c 'echo "{}" | "'"$HOOK"'"'
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}

@test "in a romp session with no skill file it is silent and does not fail" {
    rm -rf "$HOME/.claude/skills/romp-postal"
    FAKE_ROMP=1 run bash -c 'echo "{}" | "'"$HOOK"'"'
    [ "$status" -eq 0 ]
    [ -z "$output" ]
}
