"""The macOS CI cells run on a weekly schedule as well as on a manual dispatch (.github/workflows/ci.yml, 2026-09-16): with the
manual switch alone the release gate was the first macOS run in two weeks and found twenty-nine accumulated failures. Pins:
the schedule exists, fires once a week at a quiet hour Pacific, and selects the macOS matrix the way workflow_dispatch does
in BOTH matrix jobs (Python and bats); the manual dispatch is kept."""
import os
import re
import unittest

HERE = os.path.dirname(os.path.realpath(__file__))
WF = os.path.join(os.path.dirname(HERE), ".github", "workflows", "ci.yml")


class MacosSchedule(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(WF, encoding="utf-8") as fh:
            cls.wf = fh.read()
        m = re.search(r"^on:\n(.*?)^\S", cls.wf, re.S | re.M)
        assert m, "the on: block"
        cls.triggers = m.group(1)

    def test_the_workflow_keeps_the_manual_dispatch_and_adds_a_weekly_schedule(self):
        self.assertIn("workflow_dispatch:", self.triggers, "the manual on-switch stays")
        self.assertIn("schedule:", self.triggers, "a schedule trigger exists (the base had the manual switch alone)")
        crons = re.findall(r'- cron: "([^"]+)"', self.triggers)
        self.assertEqual(len(crons), 1, "one scheduled run: %r" % crons)
        minute, hour, dom, month, dow = crons[0].split()
        self.assertEqual((dom, month), ("*", "*"), "weekly, not monthly")
        self.assertRegex(dow, r"^[0-6]$", "one day of the week")
        self.assertTrue(minute.isdigit() and hour.isdigit(), "a fixed minute and hour")
        self.assertIn(int(hour), range(8, 14), "a quiet hour Pacific: 08:00 to 13:00 UTC is midnight to 06:00 Pacific")

    def test_the_schedule_selects_the_macos_matrix_in_both_jobs(self):
        exprs = re.findall(r"os: \$\{\{ fromJSON\((.*?)\) \}\}", self.wf)
        self.assertEqual(len(exprs), 2, "the Python matrix and the bats matrix: %r" % exprs)
        for e in exprs:
            self.assertIn("github.event_name == 'workflow_dispatch'", e)
            self.assertIn("github.event_name == 'schedule'", e, "the scheduled run selects macOS the way a dispatch does: %s" % e)
            self.assertIn('"macos-latest"', e)
        self.assertIn("weekly", self.triggers.lower(), "the schedule line says what it is for")


if __name__ == "__main__":
    unittest.main()
