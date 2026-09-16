"""Keep the extension's synthetic replay on the actual kernel encoder and rendered shim."""
import json
import unittest

from tests.extension_delta_fixture import FIXTURE, fixture


class ExtensionDeltaFixture(unittest.TestCase):
    def test_fixture_matches_current_kernel_encoder_and_rendered_browser(self):
        self.assertEqual(json.loads(FIXTURE.read_text()), fixture(),
                         "regenerate with python3 -m tests.extension_delta_fixture, then replay the Node pipe tests")
