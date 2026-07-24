#!/usr/bin/env python3
"""romp-judge-monitor — a live terminal health view of the romp judges (`romp -j`).

Answers two questions at a glance, no log-spelunking:
  KEEPING UP  — is the judge producer processing units promptly, or is a backlog
                building? Per active session: pending = parsed units (the
                judge-units-cache) not yet captioned (the captions store), plus
                how long since the newest caption was written.
  EXCEPTIONS  — is the engine crashing? Producer-level tracebacks land in
                manager.log ('producer:' lines); kernel CRASH-restarts (a non-
                SIGTERM/non-zero exit) show there too. Both are surfaced here.

Like romp-feed, this is INDEPENDENT of the kernel: it re-reads the same raw state
files + manager.log and probes the kernel's /version, and never imports
romp-kernel / romp-judge. That independence is the point — it's a cross-check on
the machinery, so keep it that way.

KNOWN GAP (surfaced in the footer): individual judge-CALL failures (a `claude -p`
caption/plan that times out or raises) are currently swallowed in romp-judge and
recorded NOWHERE, so this view can't show them yet — only producer-level crashes.
Closing that needs a small instrumentation change in romp-judge.

Usage:
  romp -j            live TUI, refreshes every few seconds (^C to quit)
  romp -j --once     render one frame and exit (no alt-screen)
  romp -j --json     print the computed health model as JSON and exit
  romp -j --no-color disable ANSI colour
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REFRESH_SECS = 3
ACTIVE_WINDOW_SECS = 2 * 3600     # headless fallback: a session is "active" if its cache changed this recently
KERNEL_URLS = ["http://127.0.0.1:29855", "http://127.0.0.1:7878", "http://127.0.0.1:7432"]


# ───────────────────────── raw readers (independent of the kernel) ─────────────────────────

def state_dir():
    home = Path(os.environ.get("HOME") or Path.home())
    override = os.environ.get("ROMP_STATE_DIR")   # per-kernel state root (plans/multi-kernel.md)
    if override:
        return Path(override)
    base = os.environ.get("XDG_STATE_HOME") or str(home / ".local/state")
    return Path(base) / "romp"


def session_names(state):
    """{fsid: (name, color)} from names/<fsid> (tab-separated: name \\t dir \\t #bg \\t fg)."""
    out = {}
    for fp in (state / "names").glob("*"):
        try:
            parts = fp.read_text().split("\t")
            name = parts[0].strip() if parts else fp.name
            color = parts[2].strip() if len(parts) > 2 else ""
            out[fp.name] = (name or fp.name, color)
        except Exception:
            pass
    return out


def caption_index(state, fsid):
    """(set_of_caption_ids, newest_t) for captions/<fsid>.jsonl. ({}, None) if absent/empty."""
    ids, newest = set(), None
    fp = state / "captions" / (fsid + ".jsonl")
    try:
        for line in fp.read_text().splitlines():
            try:
                o = json.loads(line)
            except Exception:
                continue
            cid = o.get("id")
            if cid:
                ids.add(cid)
            t = o.get("t")
            if isinstance(t, (int, float)) and (newest is None or t > newest):
                newest = t
    except OSError:
        pass
    return ids, newest


def cache_tasks(state, fsid):
    """(tasks, mtime) for judge-units-cache/<fsid>.json. Each task: {text, writes:[{id,grain,t}]}."""
    fp = state / "judge-units-cache" / (fsid + ".json")
    try:
        d = json.loads(fp.read_text())
        return (d.get("tasks") or []), fp.stat().st_mtime
    except (OSError, ValueError):
        return [], None


def tmux_alive():
    """set of alive romp-session fsids (@romp-session-id where @romp==1), or None when tmux is absent
    (headless) so the caller can fall back to recently-active caches."""
    try:
        out = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{@romp}|#{@romp-session-id}"],
            capture_output=True, text=True, timeout=3)
    except Exception:
        return None
    if out.returncode != 0:
        return None
    alive = set()
    for line in out.stdout.splitlines():
        flag, _, sid = line.partition("|")
        if flag == "1" and sid:
            alive.add(sid)
    return alive


def probe_kernel():
    """The running kernel's self-report from /version: {alive, uptime_s, sha, pid, url} (alive False when
    nothing answers)."""
    import urllib.request
    for u in KERNEL_URLS:
        try:
            with urllib.request.urlopen(u + "/version", timeout=1.5) as r:
                d = json.loads(r.read().decode())
                return {"alive": True, "uptime_s": d.get("uptime_s"), "sha": d.get("kernel_sha"),
                        "pid": d.get("pid"), "url": u}
        except Exception:
            continue
    return {"alive": False}


_EXIT_RE = re.compile(r"kernel '([^']+)' exited \(code=(\S+) sig=(\S+)\)")


def manager_exceptions(state):
    """Scan manager.log for engine errors: producer tracebacks and kernel CRASH-restarts (exits that are
    NOT a clean SIGTERM / code=0 manager restart). Returns counts + the last crash line."""
    producer_crashes = 0
    restarts = crashes = 0
    last_crash = None
    try:
        text = (state / "manager.log").read_text(errors="replace")
    except OSError:
        return {"producer_crashes": 0, "kernel_restarts": 0, "kernel_crashes": 0, "last_crash": None}
    for line in text.splitlines():
        if line.startswith("producer:"):
            producer_crashes += 1
        m = _EXIT_RE.search(line)
        if m:
            restarts += 1
            code, sig = m.group(2), m.group(3)
            clean = (sig == "SIGTERM") or (code == "0")     # a romp refresh / managed restart, not a crash
            if not clean:
                crashes += 1
                last_crash = line.strip()
    return {"producer_crashes": producer_crashes, "kernel_restarts": restarts,
            "kernel_crashes": crashes, "last_crash": last_crash}


def judge_call_errors(state, now, window_long=3600, window_recent=900):
    """Swallowed judge-call failures from judge-errors.jsonl (parse-fails, call timeouts/exceptions that
    romp-judge would otherwise drop silently): counts in the last hour / 15 min + the most recent one."""
    long_n = recent_n = 0
    last = None
    try:
        lines = (state / "judge-errors.jsonl").read_text().splitlines()
    except OSError:
        return {"count_1h": 0, "count_15m": 0, "last": None}
    for line in lines:
        try:
            o = json.loads(line)
        except Exception:
            continue
        t = o.get("t")
        if not isinstance(t, (int, float)):
            continue
        age = now - t
        if age <= window_long:
            long_n += 1
            last = o                                  # lines are chronological → last in-window is newest
        if age <= window_recent:
            recent_n += 1
    return {"count_1h": long_n, "count_15m": recent_n, "last": last}


USAGE_WINDOW_SECS = 24 * 3600


def judge_usage(state, now, window=USAGE_WINDOW_SECS):
    """Token/cost rollup from judge-usage.jsonl (one line per judge call) over the last `window` seconds:
    a grand total + per-judge + per-tier {calls,in,out,cost,ms}. This is the PIPELINE half of the
    sessions-vs-pipeline split the timeline footer shows. Empty/zeros when the log is absent."""
    def blank():
        return {"calls": 0, "in": 0, "out": 0, "cost": 0.0, "ms": 0}
    total, by_judge, by_tier = blank(), {}, {}
    try:
        lines = (state / "judge-usage.jsonl").read_text().splitlines()
    except OSError:
        return {"total": total, "by_judge": by_judge, "by_tier": by_tier, "window_s": window}
    for line in lines:
        try:
            o = json.loads(line)
        except Exception:
            continue
        t = o.get("t")
        if not isinstance(t, (int, float)) or now - t > window:
            continue
        for b in (total, by_judge.setdefault(o.get("judge") or "?", blank()),
                  by_tier.setdefault(o.get("tier") or "?", blank())):
            b["calls"] += 1
            b["in"] += int(o.get("in") or 0)
            b["out"] += int(o.get("out") or 0)
            b["cost"] += float(o.get("cost") or 0.0)
            b["ms"] += int(o.get("ms") or 0)
    return {"total": total, "by_judge": by_judge, "by_tier": by_tier, "window_s": window}


# ───────────────────────── health model ─────────────────────────

def build_model(state, now):
    names = session_names(state)
    alive = tmux_alive()
    kernel = probe_kernel()
    exc = manager_exceptions(state)
    je = judge_call_errors(state, now)

    sessions = []
    total_pending = 0
    oldest_pending_age = None
    last_caption_t = None

    for fsid, (name, color) in names.items():
        cap_ids, newest_cap = caption_index(state, fsid)
        tasks, cmtime = cache_tasks(state, fsid)

        if alive is not None:
            active = fsid in alive
        else:   # headless: no tmux to ask → treat a recently-touched cache as active
            active = cmtime is not None and (now - cmtime) < ACTIVE_WINDOW_SECS
        if not active:
            continue

        pending = 0
        oldest_pending_t = None
        for tk in tasks:
            writes = tk.get("writes") or []
            done = any(w.get("id") in cap_ids for w in writes)
            if done:
                continue
            pending += 1
            for w in writes:
                wt = w.get("t")
                if isinstance(wt, (int, float)) and (oldest_pending_t is None or wt < oldest_pending_t):
                    oldest_pending_t = wt

        total_pending += pending
        if newest_cap is not None and (last_caption_t is None or newest_cap > last_caption_t):
            last_caption_t = newest_cap
        op_age = (now - oldest_pending_t) if oldest_pending_t is not None else None
        if op_age is not None and (oldest_pending_age is None or op_age > oldest_pending_age):
            oldest_pending_age = op_age

        sessions.append({
            "fsid": fsid, "name": name, "color": color, "pending": pending,
            "last_caption_age_s": (now - newest_cap) if newest_cap is not None else None,
            "oldest_pending_age_s": op_age,
        })

    sessions.sort(key=lambda s: (-s["pending"], s["name"]))
    last_caption_age = (now - last_caption_t) if last_caption_t is not None else None

    # Verdict. down = kernel unreachable. warn = an engine crash, or a backlog that hasn't drained
    # (event-driven now, so pending lingering past a tick means something's stuck). ok otherwise.
    if not kernel.get("alive"):
        verdict = "down"
    elif exc["producer_crashes"] > 0 or exc["kernel_crashes"] > 0:
        verdict = "warn"
    elif je["count_15m"] >= 3:                        # sustained recent judge-call failures
        verdict = "warn"
    elif total_pending > 0 and (last_caption_age is None or last_caption_age > 45):
        verdict = "warn"
    else:
        verdict = "ok"

    return {
        "t": now, "verdict": verdict, "kernel": kernel, "exceptions": exc, "judge_errors": je,
        "backlog": {"total_pending": total_pending, "oldest_pending_age_s": oldest_pending_age,
                    "last_caption_age_s": last_caption_age, "active_sessions": len(sessions)},
        "sessions": sessions, "usage": judge_usage(state, now),
    }


# ───────────────────────── rendering ─────────────────────────

C = {"reset": "\x1b[0m", "dim": "\x1b[2m", "bold": "\x1b[1m",
     "green": "\x1b[32m", "yellow": "\x1b[33m", "red": "\x1b[31m", "cyan": "\x1b[36m"}
_USE_COLOR = True


def c(s, *names):
    if not _USE_COLOR:
        return s
    return "".join(C[n] for n in names) + s + C["reset"]


def fmt_age(s):
    if s is None:
        return "—"
    s = int(s)
    if s < 60:
        return "%ds" % s
    if s < 3600:
        return "%dm%02ds" % (s // 60, s % 60)
    return "%dh%02dm" % (s // 3600, (s % 3600) // 60)


def _fmt_tok(n):
    n = int(n or 0)
    return "%.1fM" % (n / 1e6) if n >= 1e6 else ("%dk" % round(n / 1e3) if n >= 1e3 else str(n))


def _agecol(s):
    """Colour an age by staleness: fresh green, getting old yellow, stale red, unknown dim."""
    if s is None:
        return "dim"
    return "green" if s < 60 else ("yellow" if s < 300 else "red")


def _countcol(n):
    """Colour a backlog count: 0 green, a few yellow, a pile red."""
    return "green" if n == 0 else ("yellow" if n < 5 else "red")


def _name_in_identity_color(cell, hexstr):
    """Render a (pre-padded) session-name cell in its romp identity colour — the SAME #hex the tmux tab
    and dashboard use — via an ANSI truecolour escape, so the monitor's rows match the rest of romp at a
    glance. Pad BEFORE colouring so the zero-width escapes don't break column alignment. Plain fallback
    when colour is off or the hex is missing/malformed."""
    if not _USE_COLOR or not (hexstr or "").startswith("#") or len(hexstr) != 7:
        return cell
    try:
        r, g, b = (int(hexstr[i:i + 2], 16) for i in (1, 3, 5))
    except ValueError:
        return cell
    return "\x1b[1;38;2;%d;%d;%dm%s%s" % (r, g, b, cell, C["reset"])


def render(m):
    out = []
    v = m["verdict"]
    vcol = {"ok": "green", "warn": "yellow", "down": "red"}[v]
    badge = {"ok": c(" OK ", "green", "bold"), "warn": c(" WARN ", "yellow", "bold"),
             "down": c(" DOWN ", "red", "bold")}[v]
    out.append("%s  romp judges %s" % (c("●", vcol), badge))

    k = m["kernel"]
    if k.get("alive"):
        out.append("  kernel     %s up %s  %s pid=%s" % (
            c("●", "green"), c(fmt_age(k.get("uptime_s")), "green"),
            c("sha=" + (k.get("sha") or "?"), "dim"), k.get("pid")))
    else:
        out.append("  kernel     %s %s — is the manager up? (`romp --version` / `romp --status`)"
                   % (c("●", "red"), c("unreachable", "red", "bold")))

    e = m["exceptions"]
    pc, kc = e["producer_crashes"], e["kernel_crashes"]
    estr = "producer-crashes:%s  kernel-crashes:%s  %s" % (
        c(str(pc), _countcol(pc)), c(str(kc), _countcol(kc)),
        c("(restarts:%s)" % e["kernel_restarts"], "dim"))
    out.append("  exceptions %s %s" % (c("●", "green" if pc == 0 and kc == 0 else "red"), estr))
    if e["last_crash"]:
        out.append("             %s" % c("last crash: " + e["last_crash"][:96], "red", "dim"))

    je = m["judge_errors"]
    jn = je["count_1h"]
    jcol = "green" if jn == 0 else ("yellow" if je["count_15m"] < 3 else "red")
    jstr = "call failures: %s in 1h" % c(str(jn), jcol)
    if je["last"]:
        L = je["last"]
        jstr += " · last %s/%s %s ago" % (L.get("tier", "?"), L.get("err", "?"),
                                          fmt_age(m["t"] - L.get("t", m["t"])))
    out.append("  judge      %s %s" % (c("●", jcol), jstr))

    b = m["backlog"]
    keeping = "pending:%s across %d session(s) · oldest %s · last caption %s ago" % (
        c(str(b["total_pending"]), _countcol(b["total_pending"])), b["active_sessions"],
        c(fmt_age(b["oldest_pending_age_s"]), _agecol(b["oldest_pending_age_s"])),
        c(fmt_age(b["last_caption_age_s"]), _agecol(b["last_caption_age_s"])))
    out.append("  keeping up %s %s" % (c("●", "green" if b["total_pending"] == 0 else vcol), keeping))

    out.append("")
    out.append(c("    %-20s %7s  %-10s  %-10s" % ("SESSION", "PENDING", "LAST-CAP", "OLDEST"), "dim"))
    if not m["sessions"]:
        out.append(c("    (no active sessions)", "dim"))
    for s in m["sessions"]:
        out.append("  %s %s %s  %s  %s" % (
            c("●", _countcol(s["pending"])),
            _name_in_identity_color("%-20s" % s["name"][:20], s.get("color")),
            c("%7d" % s["pending"], _countcol(s["pending"])),
            c("%-10s" % fmt_age(s["last_caption_age_s"]), _agecol(s["last_caption_age_s"])),
            c("%-10s" % fmt_age(s["oldest_pending_age_s"]), _agecol(s["oldest_pending_age_s"]))))

    u = m.get("usage") or {}
    ut = u.get("total") or {}
    if ut.get("calls"):
        out.append("")
        out.append(c("  pipeline cost (last %s) — the judges' token spend" % fmt_age(u.get("window_s")), "dim"))
        out.append("    total      %s tok · %s calls · %s" % (
            c(_fmt_tok(ut["in"] + ut["out"]), "cyan", "bold"), ut["calls"], c("$%.2f" % ut["cost"], "cyan", "bold")))
        bt = u.get("by_tier") or {}
        tier_str = "   ".join("%s %s tok / $%.2f" % (k, _fmt_tok(bt[k]["in"] + bt[k]["out"]), bt[k]["cost"])
                              for k in ("index", "triage") if k in bt)
        if tier_str:
            out.append("    by tier    %s" % c(tier_str, "dim"))
        bj = u.get("by_judge") or {}
        for k in sorted(bj, key=lambda j: -bj[j]["cost"]):
            j = bj[k]
            out.append("    %-10s %s tok · %d calls · %s" % (
                k, _fmt_tok(j["in"] + j["out"]), j["calls"], c("$%.2f" % j["cost"], "dim")))

    out.append("")
    out.append(c("  note: judge-call failures (parse / timeout / exception) are now recorded; a captioner", "dim"))
    out.append(c("        empty ('no finished work') is NOT counted — too noisy to be a signal. ^C to quit.", "dim"))
    return "\n".join(out)


def run_live():
    sys.stdout.write("\x1b[?1049h\x1b[?25l")   # alt screen + hide cursor
    try:
        while True:
            frame = render(build_model(state_dir(), time.time()))
            sys.stdout.write("\x1b[2J\x1b[H" + frame + "\n")
            sys.stdout.flush()
            time.sleep(REFRESH_SECS)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\x1b[?25h\x1b[?1049l")   # restore cursor + main screen
        sys.stdout.flush()


def main(argv):
    global _USE_COLOR
    args = set(argv)
    if "--no-color" in args or not sys.stdout.isatty():
        _USE_COLOR = False
    if "--json" in args:
        print(json.dumps(build_model(state_dir(), time.time()), indent=2))
        return 0
    if "--once" in args:
        print(render(build_model(state_dir(), time.time())))
        return 0
    run_live()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
