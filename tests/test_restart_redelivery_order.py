"""tests/test_restart_redelivery.py the way a whole suite runs it: IMPORTED first (collection), RUN a long while later. On
the devbox the whole Python suite reaches that module past the twenty-minute mark, and under two suites at once well past
it; its send stamps were taken at import, ten minutes before, so at the run they read as older than the re-delivery age
line (REDELIVER_MAX_AGE_S, thirty minutes) and every human send was flagged instead of re-queued: four reds under the suite
(2026-09-16, three peer sessions in one morning), green alone and on CI's faster legs. The gap is played by moving the
clock the product reads after the import; nothing sleeps. The stamps are now taken when each test runs (_recent)."""
import importlib.util
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

# Hermetic state BEFORE any load (tests/test_state_isolation_order.py): the module loaded below floors its own root at
# import, and this one restores the environment after it; the floor here keeps a bare run off the real state too.
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)
HERE = os.path.dirname(os.path.realpath(__file__))
GAP_S = 1300.0          # collection to run: past the 1200 s at which a ten-minute-old stamp crosses the thirty-minute line


class ImportedThenRunLater(unittest.TestCase):
    def test_the_redelivery_module_is_green_when_run_long_after_its_import(self):
        env = dict(os.environ)                                      # the module floors its own state root at import
        try:
            spec = importlib.util.spec_from_file_location("romp_test_restart_redelivery_ordered",
                                                          os.path.join(HERE, "test_restart_redelivery.py"))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)                            # the import: any import-time stamp is taken here
            real = time.time
            with mock.patch.object(time, "time", lambda: real() + GAP_S):   # the run, GAP_S later
                suite = unittest.defaultTestLoader.loadTestsFromModule(mod)
                res = unittest.TextTestRunner(stream=open(os.devnull, "w"), verbosity=0).run(suite)
        finally:
            os.environ.clear(); os.environ.update(env)
        self.assertGreaterEqual(res.testsRun, 7)
        self.assertEqual([t.id().split(".")[-1] for t, _ in res.failures], [],
                         "the module's sends read as stale when run %.0f s after its import" % GAP_S)
        self.assertEqual(res.errors, [])


if __name__ == "__main__":
    unittest.main()
