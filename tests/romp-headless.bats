#!/usr/bin/env bats

# `romp send|interrupt|end <session> [text]` — headless session control through the kernel
# HTTP API (2026-07-05: interrupt/end existed only as browser WS ops, so a runaway session had no
# headless stop). Bare words since round 3 (2026-07-25); the dashed spellings stay as SILENT
# aliases because agent-facing text delivered before then names them. A tiny one-shot python
# server stands in for the kernel; failures must be LOUD (non-zero exit + a message), never a
# silent curl swallow.

ROMP_SCRIPT="$(cd "$(dirname "$BATS_TEST_FILENAME")/../bin" && pwd)/romp"

setup() {
    TEST_DIR="$(mktemp -d)"
}

teardown() {
    [ -n "${SERVER_PID:-}" ] && kill "$SERVER_PID" 2>/dev/null
    rm -rf "$TEST_DIR"
}

# Start a one-shot fake kernel; writes its port to $TEST_DIR/port and its request to $TEST_DIR/req.
# $2 (optional): seconds to hold the answer AFTER reading the request — a kernel that took the message
# but answers late (the boot-storm shape the exit-code test below drives).
start_fake_kernel() {   # $1 = response body, $2 = answer delay in seconds (default 0)
    python3 - "$1" "$TEST_DIR" "${2:-0}" <<'PY' &
import http.server, json, sys, time
body, tdir, delay = sys.argv[1].encode(), sys.argv[2], float(sys.argv[3])
class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        with open(tdir + "/req", "w") as f:
            f.write(self.path + "\n" + self.rfile.read(n).decode())
        if delay:
            time.sleep(delay)
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):   # `romp compact --wait` reads /sessions once BEFORE its POST (the baseline notice, 2026-09-21): no rows here
        self.send_response(200); self.send_header("Content-Length", "2"); self.end_headers(); self.wfile.write(b"[]")
    def log_message(self, *a):
        pass
class _Bound(http.server.HTTPServer):   # no reverse lookup of the bind address: HTTPServer.server_bind runs socket.getfqdn(host), about 36 s on GitHub's macOS images
    def server_bind(self):
        import socketserver
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]
s = _Bound(("127.0.0.1", 0), H)
with open(tdir + "/port", "w") as f:
    f.write(str(s.server_address[1]))
for _ in range(4):   # the one POST, and the /sessions read a --wait makes before it; teardown ends the server either way
    s.handle_request()
PY
    SERVER_PID=$!
    until [ -s "$TEST_DIR/port" ]; do sleep 0.05; done
    export ROMP_KERNEL_PORT="$(cat "$TEST_DIR/port")"
}

@test "romp interrupt <name> POSTs /interrupt and exits 0 on ok" {
    start_fake_kernel '{"ok": true}'
    run "$ROMP_SCRIPT" interrupt runaway
    [ "$status" -eq 0 ]
    [[ "$output" == *"ok (runaway)"* ]]
    grep -q "^/interrupt$" <(head -1 "$TEST_DIR/req")
    grep -q '"name": "runaway"' "$TEST_DIR/req"
}

@test "romp end stops a session through /end" {
    start_fake_kernel '{"ok": true}'
    run "$ROMP_SCRIPT" end done-with-it
    [ "$status" -eq 0 ]
    grep -q "^/end$" <(head -1 "$TEST_DIR/req")
}

@test "romp end self resolves through ROMP_SID and defers to idle by default" {
    # a session closing ITSELF after its work (the user 2026-08-15): self = the spawn-frozen sid,
    # and the kernel kills at the turn's settle so the goodbye lands first
    start_fake_kernel '{"ok": true}'
    ROMP_SID="11111111-2222-3333-4444-555555555555" run "$ROMP_SCRIPT" end self
    [ "$status" -eq 0 ]
    grep -q "^/end$" <(head -1 "$TEST_DIR/req")
    grep -q '"id": "11111111-2222-3333-4444-555555555555"' "$TEST_DIR/req"
    grep -q '"when": "idle"' "$TEST_DIR/req"
}

@test "romp end self --now skips the deferral; self outside a session fails loudly" {
    start_fake_kernel '{"ok": true}'
    ROMP_SID="11111111-2222-3333-4444-555555555555" run "$ROMP_SCRIPT" end self --now
    [ "$status" -eq 0 ]
    run grep -q '"when"' "$TEST_DIR/req"
    [ "$status" -ne 0 ]
    ROMP_SID="" run "$ROMP_SCRIPT" end self
    [ "$status" -eq 2 ]
    [[ "$output" == *"only works from inside a romp SDK session"* ]]
}

@test "the dashed spellings are silent aliases: --send works and says nothing about it" {
    # Agent-facing text delivered before 2026-07-25 (postal reply footers, skill
    # docs in old transcripts) names the dashed forms; they must keep working
    # with no retirement noise.
    start_fake_kernel '{"ok": true}'
    run "$ROMP_SCRIPT" --send helper "hello"
    [ "$status" -eq 0 ]
    [[ "$output" != *"retired"* ]]
    grep -q "^/send$" <(head -1 "$TEST_DIR/req")
    grep -q '"name": "helper"' "$TEST_DIR/req"
}

@test "romp send ships JSON-safe text" {
    start_fake_kernel '{"ok": true}'
    run "$ROMP_SCRIPT" send helper 'fix the "thing" \ and this'
    [ "$status" -eq 0 ]
    grep -q "^/send$" <(head -1 "$TEST_DIR/req")
    python3 - "$TEST_DIR/req" <<'PY'
import json, sys
body = open(sys.argv[1]).read().split("\n", 1)[1]
assert json.loads(body) == {"name": "helper", "text": 'fix the "thing" \\ and this'}, body
PY
}

@test "romp send --tag appends the render-hint marker; bad labels and missing text exit 2" {
    start_fake_kernel '{"ok": true}'
    run "$ROMP_SCRIPT" send helper --tag kickoff 'boot brief for the run'
    [ "$status" -eq 0 ]
    python3 - "$TEST_DIR/req" <<'PY'
import json, sys
body = open(sys.argv[1]).read().split("\n", 1)[1]
d = json.loads(body)
assert d["name"] == "helper", d
assert d["text"] == "boot brief for the run\n\n<!-- romp-tag: kickoff -->", d
PY
    run "$ROMP_SCRIPT" send helper --tag 'two words' 'text'
    [ "$status" -eq 2 ]
    [[ "$output" == *"--tag must be one word"* ]]
    run "$ROMP_SCRIPT" send helper --tag kickoff
    [ "$status" -eq 2 ]
    [[ "$output" == *"usage: romp send"* ]]
}

@test "romp send reports queued when the kernel parked it" {
    # a sender inside the target's own open turn (an agent sending itself a slash command) must learn
    # the command has not run yet (2026-09-03: a parked /clear read 'ok' and never fired)
    start_fake_kernel '{"ok": true, "queued": true}'
    run "$ROMP_SCRIPT" send busy1 "/frobnicate now"
    [ "$status" -eq 0 ]
    [[ "$output" == *"romp send: queued (busy1)"* ]]
    [[ "$output" == *"delivers when the session is quiet"* ]]
}

@test "romp send still says ok on queued:false and on a bare ok reply" {
    start_fake_kernel '{"ok": true, "queued": false}'
    run "$ROMP_SCRIPT" send web "hello"
    [ "$status" -eq 0 ]
    [[ "$output" == *"romp send: ok (web)"* ]]
}

@test "a kernel refusal is loud: non-zero exit + the kernel's answer" {
    start_fake_kernel '{"ok": false, "error": "id or name required"}'
    run "$ROMP_SCRIPT" interrupt ghost
    [ "$status" -eq 1 ]
    [[ "$output" == *"refused"* ]]
    [[ "$output" == *"id or name required"* ]]   # the kernel's own words, not the raw body
}

@test "an unreachable kernel is loud, not a silent curl swallow" {
    ROMP_KERNEL_PORT=1 run "$ROMP_SCRIPT" interrupt anyone
    [ "$status" -eq 1 ]
    [[ "$output" == *"kernel not reachable"* ]]
}

@test "usage errors exit 2: missing session name, send without text" {
    run "$ROMP_SCRIPT" interrupt
    [ "$status" -eq 2 ]
    run "$ROMP_SCRIPT" send lonely
    [ "$status" -eq 2 ]
    [[ "$output" == *"usage: romp send"* ]]
}

# ── romp compact (2026-08-30, the user via the dashboard team) ──
# First-class in-place compaction: POSTs /compact, tells the caller which arm ran (now vs queued),
# refuses honestly. The one-shot fake kernel captures the request like the send/interrupt tests.

@test "romp compact <name> POSTs /compact and says compacting now" {
    start_fake_kernel '{"ok": true, "queued": false}'
    run "$ROMP_SCRIPT" compact bigctx
    [ "$status" -eq 0 ]
    [[ "$output" == *"compacting bigctx now"* ]]
    grep -q "^/compact$" <(head -1 "$TEST_DIR/req")
    grep -q '"name": "bigctx"' "$TEST_DIR/req"
}

@test "romp compact reports queued when a turn is open" {
    start_fake_kernel '{"ok": true, "queued": true}'
    run "$ROMP_SCRIPT" compact busy1
    [ "$status" -eq 0 ]
    [[ "$output" == *"queued for busy1"* ]]
    [[ "$output" == *"fires the moment the current turn ends"* ]]
}

@test "romp compact refusals are loud: dead session, unreachable kernel, usage" {
    start_fake_kernel '{"ok": false, "error": "no live session named '"'"'ghost'"'"' — a dead session has no context to compact; revive it first"}'
    run "$ROMP_SCRIPT" compact ghost
    [ "$status" -eq 1 ]
    [[ "$output" == *"revive it first"* ]]
    ROMP_KERNEL_PORT=1 run "$ROMP_SCRIPT" compact anyone
    [ "$status" -eq 1 ]
    [[ "$output" == *"kernel not reachable"* ]]
    run "$ROMP_SCRIPT" compact
    [ "$status" -eq 2 ]
    [[ "$output" == *"usage: romp compact"* ]]
    run "$ROMP_SCRIPT" compact who --timeout notanumber
    [ "$status" -eq 2 ]
}

@test "romp help lists compact beside the other session verbs" {
    run "$ROMP_SCRIPT" help
    [[ "$output" == *"romp compact <session>"* ]]
}

# The queued+--wait path died before its first poll (set -e killed the arming assignment — review
# find, 2026-08-30) and the --wait fake below is MULTI-request: POST answers queued, then GET
# /sessions walks quiet → compacting → quiet, the armed-only-after-quiet sequence. A leading-zero
# --timeout was octal to (( )) and the timeout never fired; a remote response refuses --wait
# honestly (the local /sessions never lists remote rows).

start_wait_kernel() {   # $1 = POST response body; $2 = the poll script; $3 = the baseline read's notice; $4 = baseline reads to fail
    # The CLI reads /sessions once BEFORE its POST (the baseline, 2026-09-21) and polls it after. $2 scripts the polls
    # after the POST: comma-separated samples, each "q" (quiet) or "c" (compacting), with "A", "B", "R" or "T" appended
    # for the row's launch error (four notices: A the systemError end and B the notLoaded end, both marked a
    # compaction's end by noRetry as the kernel marks them; R the systemError end once more, A's words at a later
    # stamp, as a second compaction failing the same way leaves them (2026-09-21); T a turn's rejection, which carries
    # no mark), the last sample repeating;
    # the default "q,c,c,q" is the armed-only-after-quiet walk. $3 puts notice A on the baseline read ("A" = a notice
    # from before this wait). $4 makes that many baseline reads answer 500 first (a kernel blip the CLI must retry).
    python3 - "$1" "$TEST_DIR" "${2:-q,c,c,q}" "${3:-}" "${4:-0}" <<'PY' &
import http.server, json, sys
body, tdir, script, base, basefail = sys.argv[1].encode(), sys.argv[2], sys.argv[3].split(","), sys.argv[4], int(sys.argv[5])
state = {"posted": False, "polls": 0, "failed": 0}
NOTICES = {"A": {"text": "Codex could not compact this conversation (it reported systemError); the conversation continues as it was",
                 "at": 1781100004.5, "limit": False, "noRetry": True},
           "B": {"text": "This conversation stopped being available while it was compacting (Codex reported notLoaded); nothing was compacted as far as romp can tell",
                 "at": 1781100009.5, "limit": False, "noRetry": True},
           "T": {"text": "codex turn/start rejected: the synthetic rejection a turn leaves as it ends",
                 "at": 1781100006.5, "limit": False}}
NOTICES["R"] = dict(NOTICES["A"], at=1781100014.5)   # the same words as A at a new stamp: told from A by the stamp alone
class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0); self.rfile.read(n)
        state["posted"] = True
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        if not state["posted"] and state["failed"] < basefail:
            state["failed"] += 1
            self.send_response(500); self.send_header("Content-Length", "0"); self.end_headers(); return
        if state["posted"]:
            state["polls"] += 1
            sample = script[min(state["polls"], len(script)) - 1]
        else:
            sample = "q" + base
        rows = [{"id": "11111111-2222-3333-4444-555555555555", "name": "busy1",
                 "compacting": sample[0] == "c", "launchError": NOTICES.get(sample[1:2])}]
        b = json.dumps(rows).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers()
        self.wfile.write(b)
    def log_message(self, *a):
        pass
class _Bound(http.server.HTTPServer):   # no reverse lookup of the bind address: HTTPServer.server_bind runs socket.getfqdn(host), about 36 s on GitHub's macOS images
    def server_bind(self):
        import socketserver
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]
s = _Bound(("127.0.0.1", 0), H)
with open(tdir + "/port", "w") as f:
    f.write(str(s.server_address[1]))
for _ in range(16):
    s.handle_request()
PY
    SERVER_PID=$!
    until [ -s "$TEST_DIR/port" ]; do sleep 0.05; done
    export ROMP_KERNEL_PORT="$(cat "$TEST_DIR/port")"
}

NOTICE_A="Codex could not compact this conversation"
NOTICE_B="This conversation stopped being available while it was compacting"
NOTICE_T="codex turn/start rejected"

@test "romp compact --wait on a QUEUED compaction survives set -e, arms after quiet, and completes" {
    start_wait_kernel '{"ok": true, "queued": true}'
    run "$ROMP_SCRIPT" compact busy1 --wait --timeout 30
    [ "$status" -eq 0 ]
    [[ "$output" == *"queued for busy1"* ]]
    [[ "$output" == *"done — busy1 compacted"* ]]
}

# A compaction that ends loudly (Codex reported systemError) drops the row's compacting bit exactly as a clean end does,
# so the poll alone read "done" over an uncompacted thread and exited 0 (the second review of the native compaction,
# 2026-09-21). The row carries the backend's launch error; the wait exits 1 with the notice's words when that notice
# is NEW against the wait's baseline, whether or not a compacting sample was caught. The baseline is per path: a
# compaction that runs at once is judged against the row as read BEFORE the request (a loud end can land before the
# first poll); a queued one is judged against the first sample that reads not compacting, the earliest ours could have
# fired, so the prior compaction's loud end is not attributed to ours. A notice standing at the baseline is not this
# wait's. A baseline read that fails is retried, and a wait whose baseline never came is refused, not judged blind.
# Only a notice the kernel marks a compaction's end (noRetry) is judged: a queued wait arms mid-turn (the compacting
# bit is off for the whole turn it waits behind), so the turn's own end notice is new against the baseline while the
# compaction proceeds, and read as a loud end it failed a wait over a thread that was compacted (review, 2026-09-21).
@test "romp compact --wait exits 1 with the notice's words when the compaction it saw ended loudly" {
    start_wait_kernel '{"ok": true, "queued": false}' 'q,c,c,qA'
    run "$ROMP_SCRIPT" compact busy1 --wait --timeout 30
    [ "$status" -eq 1 ]
    [[ "$output" == *"compacting busy1 now"* ]]
    [[ "$output" == *"busy1 did not compact: $NOTICE_A"* ]]
    [[ "$output" != *"busy1 compacted"* ]]
}

@test "romp compact --wait exits 1 on a loud end it never saw compacting, instead of waiting out the timeout" {
    start_wait_kernel '{"ok": true, "queued": false}' 'q,qA'
    run "$ROMP_SCRIPT" compact busy1 --wait --timeout 30
    [ "$status" -eq 1 ]
    [[ "$output" == *"busy1 did not compact: $NOTICE_A"* ]]
    [[ "$output" != *"didn't see the compaction start"* ]]
}

@test "romp compact --wait exits 1 on a loud end that landed before its first poll, judged against the read before the POST" {
    # the baseline is the notice that stood BEFORE the request: taken from the first poll after it, a compaction that
    # ran and failed in between was read as a standing notice and the wait ran to its timeout (2026-09-21)
    start_wait_kernel '{"ok": true, "queued": false}' 'qA'
    run "$ROMP_SCRIPT" compact busy1 --wait --timeout 8
    [ "$status" -eq 1 ]
    [[ "$output" == *"busy1 did not compact: $NOTICE_A"* ]]
    [[ "$output" != *"didn't see the compaction start"* ]]
}

@test "romp compact --wait reads a notice that stood before it armed as not this wait's and still reports done" {
    start_wait_kernel '{"ok": true, "queued": false}' 'qA,cA,cA,qA' A
    run "$ROMP_SCRIPT" compact busy1 --wait --timeout 30
    [ "$status" -eq 0 ]
    [[ "$output" == *"done — busy1 compacted"* ]]
    [[ "$output" != *"did not compact"* ]]
}

@test "romp compact --wait exits 1 on a loud end wearing the standing notice's words at a new stamp: the identity is the stamp too" {
    # the notice's identity is its stamp and its text together: a compaction that fails the way the standing notice's
    # did leaves the same words at a later stamp, and that is this wait's loud end. A wait judging the words alone read
    # it as the notice that stood at the baseline and printed done over an uncompacted thread (the post-merge review of
    # the exit clause, 2026-09-21); no case drove the two halves apart before this one.
    start_wait_kernel '{"ok": true, "queued": false}' 'q,c,c,qR' A
    run "$ROMP_SCRIPT" compact busy1 --wait --timeout 30
    [ "$status" -eq 1 ]
    [[ "$output" == *"compacting busy1 now"* ]]
    [[ "$output" == *"busy1 did not compact: $NOTICE_A"* ]]
    [[ "$output" != *"busy1 compacted"* ]]
}

@test "romp compact --wait on a QUEUED compaction takes its baseline from the arming sample: the prior compaction's loud end is not ours" {
    # the prior compaction (compacting on the first poll) ends loudly; ours runs after it and completes: judged against
    # the read before the request, that notice was new and a clean compaction exited 1 (2026-09-21)
    start_wait_kernel '{"ok": true, "queued": true}' 'c,qA,c,qA'
    run "$ROMP_SCRIPT" compact busy1 --wait --timeout 30
    [ "$status" -eq 0 ]
    [[ "$output" == *"queued for busy1"* ]]
    [[ "$output" == *"done — busy1 compacted"* ]]
    [[ "$output" != *"did not compact"* ]]
}

@test "romp compact --wait on a QUEUED compaction still exits 1 with the words of a notice new since the arming sample" {
    start_wait_kernel '{"ok": true, "queued": true}' 'qA,c,qB'
    run "$ROMP_SCRIPT" compact busy1 --wait --timeout 30
    [ "$status" -eq 1 ]
    [[ "$output" == *"busy1 did not compact: $NOTICE_B"* ]]
    [[ "$output" != *"$NOTICE_A"* ]]
}

@test "romp compact --wait on a QUEUED compaction is not failed by the turn's own end notice landing after the arming sample" {
    # armed on the mid-turn sample with an empty baseline, the turn ends with a rejection (no mark), then ours runs
    # and completes with that notice standing: read as a loud end, the wait exited 1 with the turn's words
    start_wait_kernel '{"ok": true, "queued": true}' 'q,qT,cT,qT'
    run "$ROMP_SCRIPT" compact busy1 --wait --timeout 30
    [ "$status" -eq 0 ]
    [[ "$output" == *"queued for busy1"* ]]
    [[ "$output" == *"done — busy1 compacted"* ]]
    [[ "$output" != *"did not compact"* ]]
    [[ "$output" != *"$NOTICE_T"* ]]
}

@test "romp compact --wait on a QUEUED compaction still exits 1 with the compaction's own loud end after the turn's notice" {
    start_wait_kernel '{"ok": true, "queued": true}' 'q,qT,cT,qB'
    run "$ROMP_SCRIPT" compact busy1 --wait --timeout 30
    [ "$status" -eq 1 ]
    [[ "$output" == *"busy1 did not compact: $NOTICE_B"* ]]
    [[ "$output" != *"$NOTICE_T"* ]]
}

@test "romp compact --wait on a QUEUED compaction reports a loud end between the request and the arming sample by the timeout, never attributed" {
    # ours fired and failed before the first sample read quiet: the notice is baselined with the arming sample (it cannot
    # be told from a prior compaction's or a failed turn's), so the wait sees no compaction start and says so
    start_wait_kernel '{"ok": true, "queued": true}' 'qA'
    run "$ROMP_SCRIPT" compact busy1 --wait --timeout 6
    [ "$status" -eq 1 ]
    [[ "$output" == *"didn't see the compaction start"* ]]
    [[ "$output" != *"did not compact"* ]]
}

@test "romp compact --wait retries a baseline read that failed, so a standing notice is not read as this compaction's failure" {
    # the read before the request answers 500 once while the row carries a standing notice: taken as an empty baseline,
    # the standing notice read as new and a clean compaction exited 1 with the old words (2026-09-21)
    start_wait_kernel '{"ok": true, "queued": false}' 'qA,cA,cA,qA' A 1
    run "$ROMP_SCRIPT" compact busy1 --wait --timeout 30
    [ "$status" -eq 0 ]
    [[ "$output" == *"done — busy1 compacted"* ]]
    [[ "$output" != *"did not compact"* ]]
}

@test "romp compact --wait refuses the wait loudly when the baseline never came, instead of judging blind" {
    start_wait_kernel '{"ok": true, "queued": false}' 'qA,cA,cA,qA' A 3
    run "$ROMP_SCRIPT" compact busy1 --wait --timeout 30
    [ "$status" -eq 1 ]
    [[ "$output" == *"compacting busy1 now"* ]]
    [[ "$output" == *"can't judge this compaction from here"* ]]
    [[ "$output" == *"still requested"* ]]
    [[ "$output" != *"did not compact"* ]]
}

@test "romp compact --wait on a QUEUED compaction is not refused when the baseline never came: its baseline is the arming sample" {
    # the refusal is scoped to a compaction that runs at once, the one judged against the read before the request. A
    # queued one takes its baseline from the first sample that reads not compacting and has no use for that read, so
    # the same three failed reads leave it waiting and judging; a refusal of both paths passed every case before this
    # one (the post-merge review of the exit clause, 2026-09-21).
    start_wait_kernel '{"ok": true, "queued": true}' 'q,c,c,q' '' 3
    run "$ROMP_SCRIPT" compact busy1 --wait --timeout 30
    [ "$status" -eq 0 ]
    [[ "$output" == *"queued for busy1"* ]]
    [[ "$output" == *"done — busy1 compacted"* ]]
    [[ "$output" != *"can't judge this compaction from here"* ]]
    [[ "$output" != *"did not compact"* ]]
}

@test "romp compact --wait refuses a leading-zero timeout (octal to the poll arithmetic)" {
    run "$ROMP_SCRIPT" compact who --timeout 08
    [ "$status" -eq 2 ]
    [[ "$output" == *"usage: romp compact"* ]]
}

@test "romp compact --wait on a remote session refuses honestly instead of reporting it dead" {
    start_fake_kernel '{"ok": true, "queued": false, "remote": "TESTHOST-B"}'
    run "$ROMP_SCRIPT" compact farswitch --wait --timeout 10
    [ "$status" -eq 1 ]
    [[ "$output" == *"compacting farswitch now"* ]]
    [[ "$output" == *"can't follow a remote session from here (it lives on TESTHOST-B)"* ]]
    [[ "$output" == *"still requested"* ]]
}

@test "a dash-leading session name reaches the kernel like send does; the verb's own flags still get usage" {
    start_fake_kernel '{"ok": true, "queued": false}'
    run "$ROMP_SCRIPT" compact -oddname
    [ "$status" -eq 0 ]
    grep -q '"name": "-oddname"' "$TEST_DIR/req"
    run "$ROMP_SCRIPT" compact --wait
    [ "$status" -eq 2 ]
}

@test "romp send: a kernel that took the request but answers late exits 3 and says the message may be delivered" {
    # 2026-09-12: this shape wore "kernel not reachable" and exit 1, so a retry-on-exit caller re-sent a delivered
    # message on every try (nine copies of one wake, twenty seconds apart, after a restart). The request must be
    # on the fake kernel's disk (it was taken), the exit distinct from a refusal, and the words honest.
    start_fake_kernel '{"ok": true}' 3
    ROMP_KERNEL_HTTP_TIMEOUT_S=1 run "$ROMP_SCRIPT" send helper 'a wake the kernel took slowly'
    [ "$status" -eq 3 ]
    [[ "$output" == *"took the request but did not answer within 1s"* ]]
    [[ "$output" == *"may already have delivered the message"* ]]
    [[ "$output" == *"do not retry blindly"* ]]
    [[ "$output" != *"not reachable"* ]]
    grep -q "^/send$" <(head -1 "$TEST_DIR/req")
}

@test "romp send: a kernel nobody is listening on is 'not reachable', exit 1, and nothing was sent" {
    # a port with no listener: the request never left, so the old message and code stand, and the curl code is named
    export ROMP_KERNEL_PORT=1
    run "$ROMP_SCRIPT" send helper 'a message nobody took'
    [ "$status" -eq 1 ]
    [[ "$output" == *"kernel not reachable"* ]]
    [[ "$output" == *"[curl exit"* ]]
}

@test "romp send --tag ahead of the session name tags the send instead of addressing a session called --tag" {
    # 2026-09-12: a timer's `romp send --tag <label> <session> <text>` read `--tag` AS the session name four
    # times in one night and the kernel refused a paste to a target that does not exist, while the timer read
    # "sent". A verb's own flag is never a session name; the leading form tags and addresses like the trailing one.
    start_fake_kernel '{"ok": true}'
    run "$ROMP_SCRIPT" send --tag wake helper 'the ten-minute pulse'
    [ "$status" -eq 0 ]
    python3 - "$TEST_DIR/req" <<'PY'
import json, sys
body = open(sys.argv[1]).read().split("\n", 1)[1]
d = json.loads(body)
assert d["name"] == "helper", d
assert d["text"] == "the ten-minute pulse\n\n<!-- romp-tag: wake -->", d
PY
    run "$ROMP_SCRIPT" send --tag
    [ "$status" -eq 2 ]
    [[ "$output" == *"usage: romp send"* ]]
    run "$ROMP_SCRIPT" send --tag wake
    [ "$status" -eq 2 ]
    [[ "$output" == *"usage: romp send"* ]]
}
