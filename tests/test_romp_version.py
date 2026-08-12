#!/usr/bin/env python3
"""Tests for bin/romp-version (`romp --version`) — the report that shows working tree vs running kernel
vs served-vs-built bundles. Network/git are stubbed so the formatting + the stale-bundle flag are pinned
deterministically."""
import os
from importlib.machinery import SourceFileLoader
import tempfile

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "bin")
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
ver = SourceFileLoader("romp_version", os.path.join(BIN, "romp-version")).load_module()


def test_report_flags_stale_served_bundle(monkeypatch=None):
    ver._git_sha = lambda: "abc1234-dirty"
    ver._disk_bundles = lambda: {"feed.js": 200, "render.js": 100}
    # kernel reports it is SERVING an older feed.js (100) than what's on disk (200) → must flag it
    ver._probe_kernel = lambda: ("version", {"kernel_sha": "abc1234", "pid": 9, "uptime_s": 65,
                                             "dist_ver": 100, "url": "http://127.0.0.1:29855",
                                             "bundles": {"feed.js": 100, "render.js": 100}})
    out = ver.report()
    assert "abc1234-dirty" in out
    assert "pid=9" in out
    assert "feed.js" in out and "romp refresh" in out    # stale flag present on the newer-on-disk bundle


def test_report_handles_down_kernel():
    ver._git_sha = lambda: "abc1234"
    ver._disk_bundles = lambda: {"feed.js": 200}
    ver._probe_kernel = lambda: ("down", None)
    out = ver.report()
    assert "not reachable" in out


def test_report_handles_predating_kernel():
    ver._git_sha = lambda: "abc1234"
    ver._disk_bundles = lambda: {}
    ver._probe_kernel = lambda: ("stale", "http://127.0.0.1:29855")
    out = ver.report()
    assert "predates /version" in out


if __name__ == "__main__":
    test_report_flags_stale_served_bundle()
    test_report_handles_down_kernel()
    test_report_handles_predating_kernel()
    print("ok")
