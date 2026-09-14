#!/usr/bin/env bats
# The shell surfaces run on a stock mac too: /bin/sh, and a /bin/bash at 3.2. The bats macOS cell runs on manual dispatch
# alone, so nothing in CI reads them under that bash; this pins the bash-4-only constructs out of bin/, scripts/*.sh and
# install.sh statically instead (round four of issue 1600: a ${1,,} in romp-service's escape-hatch reader made the
# install die with a bad substitution after writing the plist and before bootstrapping the agent). Non-comment lines
# only, so a construct NAMED in a comment is fine; one named in a string is a hit, and the line is reworded.

setup() {
    REPO="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
    TEST_DIR="$(mktemp -d)"
}
teardown() { rm -rf "$TEST_DIR"; }

# One construct family per line: a name, a tab, an extended regex.
CONSTRUCTS='case modification, ${x,,} ${x^^} ${x,} ${x^} (bash 4)	\$\{[A-Za-z0-9_@*#?!-]+(\[[^]]*\])?[,^]
associative array, declare -A (bash 4)	(declare|local|typeset)[[:space:]]+-[A-Za-z]*A([[:space:]]|$)
nameref, declare -n (bash 4.3)	(declare|local|typeset)[[:space:]]+-[A-Za-z]*n([[:space:]]|$)
[[ -v var ]] (bash 4.2)	\[\[[^]]*[[:space:]]-v[[:space:]]
mapfile / readarray (bash 4)	(^|[^A-Za-z0-9_])(mapfile|readarray)([^A-Za-z0-9_]|$)
wait -n (bash 4.3)	(^|[^A-Za-z0-9_])wait[[:space:]]+-n([^A-Za-z0-9_]|$)
coproc (bash 4)	(^|[^A-Za-z0-9_])coproc([^A-Za-z0-9_]|$)
&> and &>> redirection (&>> is bash 4; neither is sh)	&>
;& and ;;& case fall-through (bash 4)	;&
|& pipe (bash 4)	\|&
${var@Q} transformation (bash 4.4)	\$\{[A-Za-z0-9_]+@[A-Za-z]
EPOCHSECONDS / EPOCHREALTIME (bash 5)	\$\{?EPOCH(SECONDS|REALTIME)'

_shell_files() {   # the surfaces: every file under bin/, scripts/*.sh and install.sh whose first line is an sh or bash shebang
    local f
    for f in "$REPO"/bin/* "$REPO"/scripts/*.sh "$REPO"/install.sh; do
        [ -f "$f" ] || continue
        head -1 "$f" | grep -qE '^#!.*(/|env )(ba)?sh([[:space:]]|$)' && echo "$f"
    done
    return 0
}

_scan() {   # $@ files: every non-comment line holding a construct, as "family: file:line:text"
    local name re f line
    while IFS=$'\t' read -r name re; do
        [ -n "$name" ] || continue
        for f in "$@"; do
            while IFS= read -r line; do
                printf '%s: %s:%s\n' "$name" "${f#$REPO/}" "$line"
            done < <(grep -nE -- "$re" "$f" 2>/dev/null | grep -vE '^[0-9]+:[[:space:]]*#')
        done
    done <<< "$CONSTRUCTS"
    return 0
}

@test "portability pin: the file set is the shell surfaces, found by shebang" {
    run _shell_files
    [[ "$output" == *"/bin/romp-node-launch"* ]]     # #!/bin/sh
    [[ "$output" == *"/bin/romp-service"* ]]         # #!/usr/bin/env bash
    [[ "$output" == *"/install.sh"* ]]
    [[ "$output" == *"/scripts/release.sh"* ]]
    [[ "$output" != *".py"* ]]                        # a python file under bin/ is not read
}

@test "portability pin: every construct family is caught in a planted file, and a comment naming one is not" {
    local planted="$TEST_DIR/planted.sh"
    cat > "$planted" <<'EOF'
#!/usr/bin/env bash
# a comment may say ${x,,} or declare -A or mapfile; only code counts
v="${1,,}"
declare -A map
local -n ref=v
[[ -v v ]] && :
mapfile -t lines < file
wait -n
coproc { :; }
cmd &>/dev/null
case x in a) ;& b) ;; esac
cmd |& tee
q="${v@Q}"
t=$EPOCHSECONDS
EOF
    run _scan "$planted"
    local families; families="$(printf '%s\n' "$CONSTRUCTS" | grep -c .)"
    [ "$families" -eq 12 ]
    local caught; caught="$(printf '%s\n' "$output" | cut -d: -f1 | sort -u | grep -c .)"
    [ "$caught" -eq "$families" ]
    [[ "$output" != *"a comment may say"* ]]
}

@test "portability pin: the shell surfaces use no bash-4-only construct" {
    local files; files="$(_shell_files)"
    [ -n "$files" ]
    run _scan $files
    if [ -n "$output" ]; then
        echo "bash-4-only constructs in the shell surfaces (a stock mac's /bin/bash is 3.2; use a case pattern, tr, a plain array, 2>&1):"
        echo "$output"
        return 1
    fi
}
