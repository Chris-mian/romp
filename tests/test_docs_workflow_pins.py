#!/usr/bin/env python3
"""The docs site's strict build runs on pull requests that touch the site's inputs, build only (.github/workflows/docs.yml,
2026-09-21). The build used to run only on pushes to main, so a docs pull request could land a broken link and the site broke
after the merge. The pull request's own runs were the fail-before evidence (a deliberate broken link went red, its removal
green); this pin keeps the shape: the pull-request trigger names the docs directory, the site config and the overrides
directory, and the artifact upload and the deploy job both stand down on a pull request. The orphan-page half of the claim
rests on mkdocs.yml raising `validation.nav.omitted_files` to warn, pinned here too. Source pins, as
tests/test_ci_bats_bound.py: the test dependencies carry no YAML library."""
import os
import re
import unittest

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
WF = os.path.join(ROOT, ".github", "workflows", "docs.yml")
CFG = os.path.join(ROOT, "mkdocs.yml")


class DocsBuildOnPullRequests(unittest.TestCase):
    def setUp(self):
        self.src = open(WF).read()

    def test_the_pull_request_trigger_names_the_sites_inputs(self):
        m = re.search(r"^  pull_request:\n    paths:\n((?:      - .*\n)+)", self.src, re.M)
        self.assertTrue(m, "no pull_request trigger with paths: the strict build would run only after the merge again")
        paths = [ln.strip()[2:] for ln in m.group(1).splitlines()]
        for want in ("docs/**", "mkdocs.yml", "overrides/**"):
            self.assertIn(want, paths, "the pull-request paths name %s (the site's inputs)" % want)
        self.assertNotIn("README.md", paths, "the README is not an input of the site: a README-only pull request runs no build")
        push = re.search(r"^  push:\n    branches: \[main\]\n    paths:\n((?:      - .*\n)+)", self.src, re.M)
        self.assertTrue(push)
        self.assertEqual(sorted(paths), sorted(ln.strip()[2:] for ln in push.group(1).splitlines()), "the two triggers name one input set")

    def test_a_pull_request_run_stops_after_the_build(self):
        up = re.search(r"^      - uses: actions/upload-pages-artifact@v\d+\n        if: (.*)\n", self.src, re.M)
        self.assertTrue(up, "the artifact upload carries no condition: a pull request would upload the site")
        self.assertIn("github.event_name != 'pull_request'", up.group(1))
        dep = re.search(r"^  deploy:\n    needs: build\n(?:    #.*\n)*    if: (.*)\n", self.src, re.M)
        self.assertTrue(dep, "the deploy job's condition moved: re-anchor this pin")
        self.assertIn("github.event_name != 'pull_request'", dep.group(1), "a pull request never publishes")

    def test_a_pull_requests_run_keys_on_its_own_ref_and_a_push_keeps_the_pages_group(self):
        self.assertIn("group: ${{ github.event_name == 'pull_request' && format('docs-pr-{0}', github.ref) || 'pages' }}", self.src)
        self.assertIn("cancel-in-progress: ${{ github.event_name == 'pull_request' }}", self.src)


class OrphanPagesFailTheStrictBuild(unittest.TestCase):
    def test_the_site_config_raises_omitted_files_to_warn_and_lists_the_pages_that_stay_out_of_the_nav(self):
        cfg = open(CFG).read()
        self.assertTrue(re.search(r"^validation:\n  nav:\n    omitted_files: warn$", cfg, re.M), "MkDocs reports an orphan page at info by default; strict mode promotes warnings alone")
        m = re.search(r"^not_in_nav: \|\n((?:  .*\n)+)", cfg, re.M)
        self.assertTrue(m)
        listed = {ln.strip() for ln in m.group(1).splitlines()}
        self.assertIn("codex.md", listed, "the one page that lives outside the nav today is listed, so the build stays green")


if __name__ == "__main__":
    unittest.main()
