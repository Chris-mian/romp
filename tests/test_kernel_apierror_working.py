"""An API error is a transient stall, not a block (the user 2026-06-29): build_feed no longer floors the
api-error focus card under needs-input — it stays in its natural column (working) and just carries the
'apiError' blocked badge (the feed renders that as the ⚠ chip + Retry). Source pin on build_feed."""
import inspect
import os
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()


class ApiErrorWorking(unittest.TestCase):
    def test_api_top_no_longer_forces_needs_input(self):
        src = inspect.getsource(km.build_feed)
        # the column condition no longer includes `nid == api_top` — an API error doesn't move the card
        self.assertIn('column = ("needs_input" if (col == "blocked" and not recheck)', src)
        self.assertNotIn('"needs_input" if (nid == api_top', src)

    def test_api_top_still_computed_for_the_badge_and_awaiting_exclusion(self):
        # api_top is still derived (it carries the apiError blocked badge + excludes the card from the awaiting floor)
        src = inspect.getsource(km.build_feed)
        self.assertIn("api_top", src)
        self.assertIn('"state": "apiError"', src)


if __name__ == "__main__":
    unittest.main()
