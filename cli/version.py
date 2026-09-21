#!/usr/bin/env python3
"""romp-version — what version of romp is running, across all the moving parts. `romp version`.

Three things drift independently and a stale one is the usual cause of "the UI doesn't match the code":
  - the WORKING TREE (the .py/.js sources the kernel loads straight from bin/ and vscode-extension/),
  - the RUNNING KERNEL (what it last (re)started from — reported by its /version endpoint),
  - the BUILT BUNDLES on disk vs the bundle the kernel is actually serving.
This prints all three so you can see at a glance whether a `romp refresh` (or a browser hard-reload) is
owed — instead of reading restart logs. No filesystem paths are printed (privacy).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "vscode-extension" / "dist"


def _git_sha():
    try:
        r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=2)
        sha = r.stdout.strip() if r.returncode == 0 else ""
        if sha:
            d = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"],
                               capture_output=True, text=True, timeout=2)
            if d.returncode == 0 and d.stdout.strip():
                sha += "-dirty"
        return sha or None
    except Exception:
        return None


def _disk_bundles():
    out = {}
    try:
        for p in sorted(DIST.glob("*.js")) + sorted(DIST.glob("*.css")):
            try:
                out[p.name] = int(p.stat().st_mtime)
            except OSError:
                pass
    except OSError:
        pass
    return out


def _probe_kernel():
    """The running kernel's self-report. Returns ('version', dict) when /version answers,
    ('stale', url) when only /healthz answers (a kernel predating /version → restart it), or
    ('down', None) when nothing is listening."""
    import urllib.request
    for u in ["http://127.0.0.1:29855", "http://127.0.0.1:7878", "http://127.0.0.1:7432"]:
        try:
            with urllib.request.urlopen(u + "/version", timeout=1.5) as resp:
                d = json.loads(resp.read().decode())
                d["url"] = u
                return ("version", d)
        except Exception:
            pass
        try:
            with urllib.request.urlopen(u + "/healthz", timeout=1.0) as resp:
                if resp.read(2) == b"ok":
                    return ("stale", u)
        except Exception:
            continue
    return ("down", None)


def report():
    lines = ["romp     sha=%s  (working tree the kernel loads from)" % (_git_sha() or "?")]
    kind, k = _probe_kernel()
    if kind == "version":
        up = k.get("uptime_s", 0)
        lines.append("kernel   sha=%s pid=%s up=%dm%02ds dist_ver=%s  (%s)"
                     % (k.get("kernel_sha") or "?", k.get("pid"), up // 60, up % 60,
                        k.get("dist_ver"), k.get("url")))
        pa = k.get("parse") or {}
        if pa.get("fold", 0) + pa.get("full", 0) + pa.get("fallback", 0) > 0:
            # the assembly cache's live hit rate — the deploy-verification number (T210). The
            # fallback term keeps an all-fallback kernel VISIBLE: _asm_full counts "full" as its
            # last act, so a kernel whose every parse errors into fallback has fold+full == 0.
            rate = 100.0 * pa.get("fold", 0) / max(1, pa.get("fold", 0) + pa.get("full", 0))
            gates = ", ".join("%s %d" % (g[2:], n) for g, n in sorted(pa.items())
                              if g.startswith("g:") and n)
            lines.append("parse    fold %.0f%% (%d fold / %d full / %d served)%s%s%s"
                         % (rate, pa.get("fold", 0), pa.get("full", 0), pa.get("serve", 0),
                            "  fallbacks=%d" % pa["fallback"] if pa.get("fallback") else "",
                            ("  demotes: " + gates) if gates else "",
                            "  ts-repair=%d" % pa["ts-repair"] if pa.get("ts-repair") else ""))
        cf = k.get("chatfold") or {}                     # absent on kernels older than the chat fold
        if cf.get("fold", 0) + cf.get("full", 0) + cf.get("fallback", 0) > 0:
            rate = 100.0 * cf.get("fold", 0) / max(1, cf.get("fold", 0) + cf.get("full", 0))
            gates = ", ".join("%s %d" % (g[2:], n) for g, n in sorted(cf.items())
                              if g.startswith("g:") and n)
            lines.append("chat     fold %.0f%% (%d fold / %d full)%s%s"
                         % (rate, cf.get("fold", 0), cf.get("full", 0),
                            "  fallbacks=%d" % cf["fallback"] if cf.get("fallback") else "",
                            ("  demotes: " + gates) if gates else ""))
    elif kind == "stale":
        lines.append("kernel   running at %s but predates /version — `romp refresh` to populate" % k)
    else:
        lines.append("kernel   not reachable — is the manager up? (`romp up` / `romp status`)")
    served = (k.get("bundles") if kind == "version" else {}) or {}
    disk = _disk_bundles()
    lines.append("bundles  (on disk%s):" % (" / served" if served else ""))
    for name, mt in disk.items():
        s = served.get(name)
        flag = ""
        if s is not None and s != mt:
            flag = "  ⚠ disk newer than served — `romp refresh`"
        lines.append("  %-14s %s%s" % (name, mt, flag))
    return "\n".join(lines)


if __name__ == "__main__":
    sys.stdout.write(report() + "\n")
