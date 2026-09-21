#!/usr/bin/env python3
"""The documentation's front pages stay readable by a person (the user rule, 2026-09-20;
CLAUDE.md "The documentation front pages").

docs/index.md, docs/install.md and docs/guide.md are what someone meets before they know
anything about romp. The user spent July making them short and human, and by September they
had grown back into reference prose: an 11,000-word guide, and an install page that spent a
screen on which interpreter the kernel picks before it gave the install command. The rule the
user set afterwards: a person's attention is the scarce thing, an agent doing the install can
find the detail elsewhere, so these three pages carry one short paragraph per feature and the
detail lives in docs/reference.md behind a link.

This test is the mechanical half of that rule. It pins:
- a word budget per page, so a page cannot grow back into a reference;
- a paragraph budget, since a page can be short and still unreadable in slabs (code blocks,
  tables, admonitions and raw HTML are not prose and are not counted);
- the install command inside the first screen of the install page, before anything optional;
- process documents out of the site's top-level navigation (docs/pr-tiers.md is contributor
  process, reachable by path and by URL, not a section of the site).

Moving text OUT of these pages is always allowed; the caps only bound what stays. When a page
genuinely needs more room, raise the cap here in the same change that spends it, so the budget
is a decision someone made rather than a line that drifted.
"""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"

# Caps, with the headroom the restored pages left (2026-09-20: index 428, install 340,
# guide 4001). The pages they replaced were 428 / 755 / 11,244.
WORD_CAP = {"index.md": 600, "install.md": 400, "guide.md": 5500}
PARAGRAPH_CAP = 70          # words in one paragraph or one list item
INSTALL_CMD_LINE_CAP = 40   # the install command's first line in docs/install.md

PAGES = tuple(WORD_CAP)
_LIST_ITEM = re.compile(r"^\s{0,3}(?:[-*+]\s+|\d+[.)]\s+)")
_NOT_PROSE = ("#", "|", "<", "!!!", "![", "```", ":::")


def _prose_lines(text):
    """Every line that carries prose: fenced code, HTML comments and indented code dropped."""
    out, in_fence, in_comment = [], False, False
    for line in text.split("\n"):
        if in_comment:
            if "-->" in line:
                in_comment = False
            continue
        if line.lstrip().startswith("<!--"):
            if "-->" not in line:
                in_comment = True
            continue
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        out.append(line)
    return out


def _words(text):
    return len(" ".join(_prose_lines(text)).split())


def _units(text):
    """(line number, word count, opening words) for each paragraph and each list item."""
    units, buf, start = [], [], 0

    def flush():
        if buf:
            joined = " ".join(buf).strip()
            if joined:
                units.append((start, len(joined.split()), joined[:60]))
        buf.clear()

    for n, line in enumerate(_prose_lines(text), 1):
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        if _LIST_ITEM.match(line) or stripped.startswith(_NOT_PROSE):
            flush()
            if stripped.startswith(_NOT_PROSE) and not _LIST_ITEM.match(line):
                continue            # a heading, a table row, a figure, raw HTML: not prose
        if not buf:
            start = n
        buf.append(stripped)
    flush()
    return units


class FrontPagesStayShort(unittest.TestCase):
    def test_word_cap_per_page(self):
        for page in PAGES:
            with self.subTest(page=page):
                got = _words((DOCS / page).read_text(encoding="utf-8"))
                self.assertLessEqual(
                    got, WORD_CAP[page],
                    "docs/%s is %d words, over its %d-word budget: move the detail into "
                    "docs/reference.md and leave a paragraph with a link"
                    % (page, got, WORD_CAP[page]))

    def test_no_paragraph_is_a_slab(self):
        for page in PAGES:
            text = (DOCS / page).read_text(encoding="utf-8")
            for line, count, opening in _units(text):
                with self.subTest(page=page, line=line):
                    self.assertLessEqual(
                        count, PARAGRAPH_CAP,
                        "docs/%s line %d is one paragraph of %d words (%r...): split it, or "
                        "move it to docs/reference.md" % (page, line, count, opening))

    def test_install_command_is_on_the_first_screen(self):
        lines = (DOCS / "install.md").read_text(encoding="utf-8").split("\n")
        hits = [n for n, line in enumerate(lines, 1) if "bootstrap.sh" in line and "bash" in line]
        self.assertTrue(hits, "docs/install.md no longer carries the one-line install command")
        self.assertLessEqual(
            hits[0], INSTALL_CMD_LINE_CAP,
            "the install command is at line %d of docs/install.md: a visitor came for it, so "
            "nothing optional goes above it (cap %d)" % (hits[0], INSTALL_CMD_LINE_CAP))

    def test_pr_tiers_is_not_a_navigation_entry(self):
        mkdocs = (REPO / "mkdocs.yml").read_text(encoding="utf-8")
        self.assertTrue((DOCS / "pr-tiers.md").exists(), "docs/pr-tiers.md is linked by path; keep the file")
        nav = mkdocs.split("\nnav:", 1)
        self.assertEqual(len(nav), 2, "mkdocs.yml has no nav block")
        self.assertNotIn(
            "pr-tiers.md", nav[1],
            "docs/pr-tiers.md is contributor process, not a section of the site: keep it out "
            "of nav (it is listed under not_in_nav, so --strict stays quiet)")
        self.assertIn("not_in_nav", nav[0], "pr-tiers.md needs a not_in_nav entry to keep the strict build quiet")

    def test_the_rule_is_written_down(self):
        md = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("The documentation front pages", md,
                      "CLAUDE.md is where the rule lives; this test only enforces it")


if __name__ == "__main__":
    unittest.main()
