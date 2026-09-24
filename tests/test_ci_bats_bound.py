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


class PythonJobCeiling(unittest.TestCase):
    """The python job's ceiling is per cell (2026-09-16): the macOS cells run the same suite in 17 to 25 minutes on the
    image's slower runners, and the 3.10 cell was cancelled at the job's 25-minute ceiling after 25 min 27 s on one
    dispatch having completed in 24 min 43 s on the one before, so the release's combined proof could die on a minute's
    margin. macOS gets 40 minutes; Linux keeps 25, where the suite finishes in 12 to 15."""
    def setUp(self):
        src = open(WF).read()
        m = re.search(r"^  python:\n((?:    .*\n|\n)+?)    strategy:\n", src, re.M)
        self.assertTrue(m, "the python job's head moved: re-anchor this pin")
        self.head = m.group(1)

    def test_macos_cells_get_forty_minutes_and_linux_keeps_twenty_five(self):
        m = re.search(r"^    timeout-minutes: \$\{\{ matrix\.os == 'macos-latest' && (\d+) \|\| (\d+) \}\}$", self.head, re.M)
        self.assertTrue(m, "the python job's timeout-minutes is not the per-cell expression (macos-latest && N || M)")
        macos, linux = int(m.group(1)), int(m.group(2))
        self.assertGreaterEqual(macos, 40, "the macOS cells need the margin: 25 min 27 s measured against a 25-minute ceiling")
        self.assertLessEqual(macos, 60, "past an hour a hung macOS cell eats the dispatch")
        self.assertEqual(linux, 25, "the Linux cells keep their measured ceiling (12 to 15 minutes of suite under it)")


class ExtensionJobCeiling(unittest.TestCase):
    """The vscode-extension job runs the served labs, which grow with every lab added: PR 1790's run was cancelled at the
    job's 25-minute ceiling after 25 min 04 s mid lab (2026-09-16), and under the 40-minute cap that followed, PR 2061's red
    run 35821212036 (attempt 1) was cut at 40 min 15 s. Sixty minutes (2026-09-23): the rule is a served step of up to 38 min
    plus the 600 s per-test timeout plus about 2 min of earlier steps, about 50; the served step took 35.97 to 37.92 min over
    main's sixteen runs after the raise, the closest call the run on 23c2a9960 ending its served step at 40 min 09 s. The
    floor is 50, not 60, so the pin keeps the file's range style and a revert to 40 goes red on it."""
    def test_the_extension_job_gets_sixty_minutes_and_never_reverts_below_fifty(self):
        src = open(WF).read()
        m = re.search(r"^  vscode-extension:\n((?:    .*\n|\n)+?)    defaults:\n", src, re.M)
        self.assertTrue(m, "the extension job's head moved: re-anchor this pin")
        t = re.search(r"^    timeout-minutes: (\d+)$", m.group(1), re.M)
        self.assertTrue(t, "the extension job has no plain timeout-minutes line")
        self.assertGreaterEqual(int(t.group(1)), 50, "the served step ran 35.97 to 37.92 min on main after 2026-09-23 (40 min 09 s to its end at the closest call): "
                                                     "up to 38 min plus the 600 s per-test timeout plus about 2 min of earlier steps is about 50, so a cap below it cuts a green run")
        self.assertLessEqual(int(t.group(1)), 60, "past an hour a hung lab eats the run")


if __name__ == "__main__":
    unittest.main()
