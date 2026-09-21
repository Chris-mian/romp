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
- one pointer from the guide to the reference, in its opening line, so a feature's paragraph
  stops ending with a link that sends the reader off the page they are reading;
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

# Caps, with the headroom the restored pages left (2026-09-20). Measured by _words below, which
# drops fenced code and HTML comments, the restored pages were index 394, install 259, guide 3932,
# and the pages they replaced were 394 / 690 / 11,195. (`wc -w` on the same files reads higher,
# 444 / 340 / 3997 and 428 / 755 / 11,244, since it counts the code blocks and the comments too.)
WORD_CAP = {"index.md": 600, "install.md": 400, "guide.md": 5500}
PARAGRAPH_CAP = 70          # words in one paragraph or one list item
INSTALL_CMD_LINE_CAP = 40   # the install command's first line in docs/install.md

PAGES = tuple(WORD_CAP)
_LIST_ITEM = re.compile(r"^\s{0,3}(?:[-*+]\s+|\d+[.)]\s+)")
_NOT_PROSE = ("#", "|", "!!!", "![", "```", ":::")
# A line opening with "<" is dropped only when it is BLOCK html: a video, an image, a container,
# or a tag alone on its line. A wrapped prose line that happens to begin with an inline tag
# ('<span class="romp-chip">Awaiting</span> chip. The chip clears...') is prose, and dropping it
# used to split its paragraph in two and undercount both halves.
_BLOCK_HTML = re.compile(r"^</?(?:video|img|picture|source|div|figure|figcaption|iframe|table|p)\b", re.I)
_LONE_TAG = re.compile(r"^</?[a-z][^>]*>\s*$", re.I)


def _prose_lines(text):
    """(file line number, line) for every line that carries prose: fenced code and HTML comments
    dropped. The line number is the one in the FILE, so a failure names a line you can open."""
    out, in_fence, in_comment = [], False, False
    for n, line in enumerate(text.split("\n"), 1):
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
        out.append((n, line))
    return out


def _words(text):
    return len(" ".join(line for _n, line in _prose_lines(text)).split())


def _block_html(stripped):
    return bool(_BLOCK_HTML.match(stripped) or _LONE_TAG.match(stripped))


def _units(text):
    """(file line, word count, opening words) for each paragraph and each list item."""
    units, buf, start = [], [], 0

    def flush():
        if buf:
            joined = " ".join(buf).strip()
            if joined:
                units.append((start, len(joined.split()), joined[:60]))
        buf.clear()

    for n, line in _prose_lines(text):
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        skip = stripped.startswith(_NOT_PROSE) or (stripped.startswith("<") and _block_html(stripped))
        if _LIST_ITEM.match(line) or skip:
            flush()
            if skip and not _LIST_ITEM.match(line):
                continue            # a heading, a table row, a figure, block HTML: not prose
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

    def test_the_guide_points_at_the_reference_once(self):
        text = (DOCS / "guide.md").read_text(encoding="utf-8")
        hits = [n for n, line in enumerate(text.split("\n"), 1) if "reference.md" in line]
        self.assertEqual(
            len(hits), 1,
            "docs/guide.md links to the reference %d times (lines %s): the opening points "
            "there once, and a feature's paragraph states what the feature does rather than "
            "ending in a link" % (len(hits), hits))
        self.assertLessEqual(hits[0], 12, "that one pointer belongs in the opening, not down the page")

    def test_pr_tiers_is_not_a_navigation_entry(self):
        mkdocs = (REPO / "mkdocs.yml").read_text(encoding="utf-8")
        self.assertTrue((DOCS / "pr-tiers.md").exists(), "docs/pr-tiers.md is linked by path; keep the file")
        nav = mkdocs.split("\nnav:", 1)
        self.assertEqual(len(nav), 2, "mkdocs.yml has no nav block")
        self.assertNotIn(
            "pr-tiers.md", nav[1],
            "docs/pr-tiers.md is contributor process, not a section of the site: keep it out "
            "of nav (not_in_nav declares it intentionally unlisted)")
        block = re.search(r"^not_in_nav: \|\n((?:[ \t]+\S.*\n)+)", nav[0], re.M)
        self.assertIsNotNone(block, "mkdocs.yml has no not_in_nav block for the unlisted pages")
        listed = [line.strip() for line in block.group(1).splitlines() if line.strip()]
        self.assertIn(
            "pr-tiers.md", listed,
            "pr-tiers.md needs its own not_in_nav line, which declares the page intentionally "
            "unlisted rather than forgotten (the block lists %s)" % listed)

    def test_the_rule_is_written_down(self):
        md = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("The documentation front pages", md,
                      "CLAUDE.md is where the rule lives; this test only enforces it")


if __name__ == "__main__":
    unittest.main()
