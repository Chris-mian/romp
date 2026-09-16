#!/usr/bin/env python3
"""The bats step of CI carries a per-test bound from bats itself (.github/workflows/ci.yml, 2026-09-16).

The macOS bats leg (a manual dispatch) was cancelled at the job's 35-minute ceiling on every run, nameless:
the job annotation says only that the maximum execution time was exceeded, and the TAP stream stops at the
last test that finished. BATS_TEST_TIMEOUT is bats-core's own bound (since 1.8, in the pinned 1.11.1 and in
Homebrew's 1.14.0 alike): a background sleep, then pkill or ps on the test's children, and the test's TAP
line ends "# timeout after Ns", so a hung test fails in minutes and is named. No coreutils timeout, which the
macOS image lacks. Source pins, as tests/test_ci_workflow_concurrency.py: no YAML library in the test deps."""
import os
import re
import unittest

HERE = os.path.dirname(os.path.realpath(__file__))
WF = os.path.join(os.path.dirname(HERE), ".github", "workflows", "ci.yml")


class BatsStepBound(unittest.TestCase):
    def setUp(self):
        src = open(WF).read()
        m = re.search(r"^      - name: Run bats\n((?:        .*\n)*?)        run: (bats .*)\n", src, re.M)   # zero lines between: the step without an env
        self.assertTrue(m, "the Run bats step moved or was renamed: re-anchor this pin")
        self.head, self.cmd = m.group(1), m.group(2)

    def test_the_step_sets_bats_own_per_test_timeout(self):
        m = re.search(r'^          BATS_TEST_TIMEOUT: "?(\d+)"?$', self.head, re.M)
        self.assertTrue(m, "no BATS_TEST_TIMEOUT in the step's env: a hung test would eat the job's whole budget, nameless")
        secs = int(m.group(1))
        self.assertGreaterEqual(secs, 120, "below two minutes the slowest legitimate macOS test (the 60 s romp-serve probes) is at risk")
        self.assertLessEqual(secs, 600, "above ten minutes a hang still eats most of the 35-minute job")

    def test_the_step_still_runs_every_bats_file(self):
        self.assertIn("tests/*.bats", self.cmd)
        self.assertIn("--print-output-on-failure", self.cmd)


if __name__ == "__main__":
    unittest.main()
