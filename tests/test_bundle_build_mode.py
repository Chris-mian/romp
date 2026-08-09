#!/usr/bin/env python3
"""An INSTALL must ship a production bundle, and the two things that can build one must agree.

Without --production the dashboard shipped a development build: render.js — the chat pane's
code — was 578 KB of unminified JS the browser parsed before anything appeared (a slow chat load
on a fresh install, the user 2026-07-27). Minified it is 297 KB, with no sourcemaps emitted.

The drift this guards is subtle and silent: vscode-extension/install.sh builds dist at install
time, and the kernel's _ensure_bundles() REBUILDS it whenever a .ts/.css looks newer. If only one
passed --production, any later source touch would swap the served dashboard back to the slow
bundle on the next kernel restart, with nothing saying so. Source-level assertions, because the
real build needs npm install and a network.
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
KERNEL = os.path.join(ROOT, "kernel", "kernel.py")
EXT_INSTALL = os.path.join(ROOT, "vscode-extension", "install.sh")
ESBUILD = os.path.join(ROOT, "vscode-extension", "esbuild.js")


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


class BundleBuildMode(unittest.TestCase):
    def test_esbuild_ties_minify_and_sourcemaps_to_the_production_flag(self):
        """The flag has to actually mean something — this is what the other two rely on."""
        src = _read(ESBUILD)
        self.assertIn('const production = process.argv.includes("--production")', src)
        self.assertIn("minify: production", src)
        self.assertIn("sourcemap: !production", src)

    def test_the_installer_builds_production(self):
        src = _read(EXT_INSTALL)
        self.assertIn("--production", src,
                      "vscode-extension/install.sh must build a minified bundle for an install")

    def test_the_kernel_rebuild_also_builds_production(self):
        """The rebuild path is the one that silently undoes the installer's work."""
        src = _read(KERNEL)
        m = re.search(r"def _ensure_bundles\(\):.*?(?=\ndef )", src, re.S)
        self.assertIsNotNone(m, "_ensure_bundles not found")
        body = m.group(0)
        self.assertIn("esbuild.js", body)
        self.assertIn("--production", body,
                      "_ensure_bundles must match the installer, or a .ts/.css touch reverts "
                      "the served dashboard to the unminified bundle")

    def test_both_honour_the_same_dev_opt_out(self):
        """One knob for a UI dev loop, spelled the same in both places — two names would mean
        turning it off in one builder and silently not the other."""
        self.assertIn("ROMP_EXT_DEV_BUILD", _read(EXT_INSTALL))
        self.assertIn("ROMP_EXT_DEV_BUILD", _read(KERNEL))

    def test_the_staleness_scan_covers_every_source_root_esbuild_reads(self):
        """esbuild.js builds the webview entrypoints from ../ui/webview (render.ts, styles.css,
        feed.ts, …), but _ensure_bundles used to scan only vscode-extension/src — so a
        ui/webview-only edit never marked the bundle stale, and the fix sat unshipped through
        every kernel restart with the ?v= cache token frozen (found 2026-08-09 hunting the
        optimistic-echo bug: the docstring promised a rebuild the check couldn't see)."""
        self.assertIn("ui/webview", _read(ESBUILD).replace("\\", "/"),
                      "esbuild reads the shared webview sources — the premise of this guard")
        src = _read(KERNEL)
        m = re.search(r"def _ensure_bundles\(\):.*?(?=\ndef )", src, re.S)
        body = m.group(0)
        self.assertIn('ROOT / "ui" / "webview"', body,
                      "the staleness scan must watch ui/webview, where the webview sources live")
        self.assertIn("for src in srcs", body, "…as one scan over every source root")


if __name__ == "__main__":
    unittest.main()
