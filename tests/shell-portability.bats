#!/usr/bin/env bats
# The shell surfaces run on a stock mac too: /bin/sh, and a /bin/bash at 3.2. The bats macOS cell runs on manual dispatch
# alone, so nothing in CI reads them under that bash; this pins the bash-4-plus constructs out of every shell script the
# repo ships (bin/, scripts/*.sh, install.sh, bootstrap.sh, hooks/*.sh, .githooks/pre-push, tools/ and the extension's
# install.sh) statically instead (round four of issue 1600: a ${1,,} in romp-service's escape-hatch reader made the
# install die with a bad substitution after writing the plist and before bootstrapping the agent). Non-comment lines
# only, so a construct NAMED in a comment is fine; one named in a string is a hit, and the line is reworded. The patterns
# are bash-shaped on purpose: a Python heredoc inside a script writes [-1] and a nested ${a:-${b:-c}} default is not a
# negative-length substring, and neither may read as a hit.

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
EPOCHSECONDS / EPOCHREALTIME (bash 5)	\$\{?EPOCH(SECONDS|REALTIME)
[ -v var ] and test -v (bash 4.2)	(^|[^A-Za-z0-9_])(\[|test)[[:space:]]+-v[[:space:]]
shopt -s globstar or lastpipe (bash 4, 4.2)	shopt[[:space:]]+-s[[:space:]]+[a-z ]*(globstar|lastpipe)
BASHPID (bash 4)	\$\{?BASHPID
declare -g (bash 4.2)	(declare|typeset)[[:space:]]+-[A-Za-z]*g([[:space:]]|$)
negative array index, ${a[-1]} or a[-1]= (bash 4.3)	\$\{[A-Za-z_][A-Za-z0-9_]*\[-[0-9]+\]|(^|[^A-Za-z0-9_])[A-Za-z_][A-Za-z0-9_]*\[-[0-9]+\]=
printf %(...)T (bash 4.2)	printf[^|;&]*%\([^)]*\)T
read -N (bash 4.1)	(^|[^A-Za-z0-9_])read[[:space:]]+(-[a-zA-Z]*)?N[[:space:]]
exec {fd}< or {fd}> (bash 4.1)	exec[[:space:]]+\{[A-Za-z_][A-Za-z0-9_]*\}[<>]
negative-length substring ${var:off:-n} (bash 4.2)	\$\{[A-Za-z_][A-Za-z0-9_]*:[0-9]+:-[0-9]+\}
dollar-quote unicode escape (bash 4.2)	\$'"'"'[^'"'"']*\\[uU][0-9A-Fa-f]'

_shell_files() {   # the surfaces: every shell script the repo ships, found by an sh or bash shebang on its first line
    local f
    for f in "$REPO"/bin/* "$REPO"/scripts/*.sh "$REPO"/install.sh "$REPO"/bootstrap.sh "$REPO"/hooks/*.sh "$REPO"/.githooks/pre-push "$REPO"/tools/* "$REPO"/vscode-extension/install.sh; do
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
    [[ "$output" == *"/bootstrap.sh"* ]]
    [[ "$output" == *"/hooks/romp-wake.sh"* ]]
    [[ "$output" == *"/.githooks/pre-push"* ]]
    [[ "$output" == *"/vscode-extension/install.sh"* ]]
    [[ "$output" != *".py"* ]]                        # a python file under bin/ is not read
    [[ "$output" != *".mjs"* ]]                       # nor a node tool under tools/
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
[ -v v ] && :
shopt -s globstar
p=$BASHPID
declare -g G=1
last="${arr[-1]}"
printf '%(%Y)T\n' -1
read -N 4 chunk
exec {fd}<file
tail="${v:1:-1}"
u=$'\u00e9'
EOF
    run _scan "$planted"
    local families; families="$(printf '%s\n' "$CONSTRUCTS" | grep -c .)"
    [ "$families" -eq 22 ]
    local caught; caught="$(printf '%s\n' "$output" | cut -d: -f1 | sort -u | grep -c .)"
    [ "$caught" -eq "$families" ]
    [[ "$output" != *"a comment may say"* ]]
}

@test "portability pin: a Python heredoc's negative index and a nested default are not hits" {
    local benign="$TEST_DIR/benign.sh"
    cat > "$benign" <<'EOF'
#!/usr/bin/env bash
port="${ROMP_SERVE_PORT:-${ROMP_KERNEL_PORT:-29855}}"
python3 - <<'PYCODE'
last = mins[-1]["data"] if mins else {}
PYCODE
EOF
    run _scan "$benign"
    [ -z "$output" ]
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
