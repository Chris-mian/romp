#!/usr/bin/env python3
"""The documentation's front pages stay readable by a person (the user rule, 2026-09-20;
CLAUDE.md "The documentation front pages").

docs/index.md, docs/install.md and docs/guide.md are what someone meets before they know
anything about romp. The user spent July making them short and human, and by September they
had grown back into reference prose: an 11,000-word guide, and an install page that spent a
screen on which interpreter the kernel picks before it gave the install command. The rule the
user set afterwards: a person's attention is the scarce thing, an agent doing the install can
find the detail elsewhere, so these three pages carry one short paragraph per feature and the
detail lives in docs/reference.md under a heading matching the feature's name.

This test is the mechanical half of that rule. It pins:
- a word budget per page, so a page cannot grow back into a reference;
- a paragraph budget, since a page can be short and still unreadable in slabs (code blocks,
  tables, admonitions and raw HTML are not prose and are not counted);
- the install command inside the first screen of the install page, before anything optional;
- one pointer from the guide to the reference, in its opening line, and no paragraph on any
  governed page ending on a link, so a paragraph states what a feature does instead of sending
  the reader off the page they are reading;
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
# README.md mirrors the home page, so the no-trailing-link rule covers it too.
GOVERNED = ("docs/index.md", "docs/install.md", "docs/guide.md", "README.md")
# A paragraph that ends on a link sends the reader off the page instead of saying the thing:
# the link belongs inside a clause that carries the reason for it, with the sentence going on
# past it. Target-blind on purpose, so a link to a section of the SAME page counts too. The
# match is SHAPE-SPECIFIC: a link inside a closing parenthetical ("(source in [docs/](docs/)).")
# and a link followed by anything but a period both pass, so a reviewer reads the pages too.
_ENDS_ON_LINK = re.compile(r"\[[^\]]+\]\([^)]+\)\.?$")
# A paragraph that is ONLY a link, DIRECTLY under a heading, is a navigation line rather than a
# paragraph closing on one: the heading is what the link belongs to (README's License line is the
# class). Structural, not a judgement about the heading's words, and the position is load-bearing:
# the same line further down a page, under prose, is the shape the rule forbids.
_LINK_ONLY = re.compile(r"^\[[^\]]+\]\([^)]+\)\.?$")
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


def _paragraphs(text):
    """(file line, joined text) for each paragraph and each list item, in file order."""
    units, buf, start = [], [], 0

    def flush():
        if buf:
            joined = " ".join(buf).strip()
            if joined:
                units.append((start, joined))
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


def _units(text):
    """(file line, word count, opening words) for each paragraph and each list item."""
    return [(line, len(joined.split()), joined[:60]) for line, joined in _paragraphs(text)]


def _prose_line_above(text):
    """file line -> the nearest non-blank prose line above it. Read from _prose_lines, which has
    already dropped fenced code and HTML comments, so a comment sitting between a heading and the
    line under it does not hide the heading."""
    above, prev = {}, ""
    for n, line in _prose_lines(text):
        above[n] = prev
        if line.strip():
            prev = line.strip()
    return above


def _trailing_link_checks(text):
    """(file line, joined text, offends) for EVERY paragraph and list item: the whole rule in one
    place, so the page test reads a verdict instead of composing the patterns itself, and the unit
    test below can hold the composition. A paragraph offends when it ends on a link and is not a
    link-only navigation line directly under a heading."""
    above = _prose_line_above(text)
    out = []
    for line, joined in _paragraphs(text):
        exempt = bool(_LINK_ONLY.match(joined)) and above.get(line, "").startswith("#")
        out.append((line, joined, bool(_ENDS_ON_LINK.search(joined)) and not exempt))
    return out


def _trailing_link_violations(text):
    """The (file line, joined text) pairs of _trailing_link_checks that offend, in file order."""
    return [(line, joined) for line, joined, offends in _trailing_link_checks(text) if offends]


class ParagraphHelper(unittest.TestCase):
    """The helper the page tests read, over a synthetic snippet: every failure message's line number
    and every word count comes out of it, and no page paragraph sits on either boundary today, so a
    regression here would surface as a wrong line in some future failure rather than as a red."""

    SNIPPET = "\n".join([
        "<!-- a comment, dropped -->",         # 1
        "# A heading",                         # 2
        "",                                    # 3
        "First paragraph, one line.",          # 4
        "",                                    # 5
        "A wrapped paragraph whose second",    # 6
        '<span class="romp-chip">Chip</span> line opens with an inline tag.',   # 7
        "",                                    # 8
        "<video src=\"a.mp4\"></video>",       # 9
        "",                                    # 10
        "```",                                 # 11
        "code, dropped",                       # 12
        "```",                                 # 13
        "- a list item",                       # 14
    ]) + "\n"

    def test_each_paragraph_comes_back_at_its_file_line_with_its_text(self):
        got = _paragraphs(self.SNIPPET)
        self.assertEqual(
            got,
            [(4, "First paragraph, one line."),
             (6, 'A wrapped paragraph whose second <span class="romp-chip">Chip</span> line opens '
                 "with an inline tag."),
             (14, "- a list item")],
            "each paragraph and list item once, at the line it starts on in the FILE (the comment "
            "and the fenced block are dropped without shifting the numbers), text joined")

    def test_an_inline_tag_does_not_split_a_paragraph_and_a_block_tag_yields_none(self):
        # The MECHANISM, not the count: a line 7 read as block HTML would flush the paragraph at 6
        # and start none of its own, so "no paragraph starts at 7" holds either way. What separates
        # the two readings is whether line 7's words are IN the paragraph at line 6.
        byline = dict((line, joined) for line, joined in _paragraphs(self.SNIPPET))
        self.assertIn('<span class="romp-chip">Chip</span> line opens', byline[6],
                      "a line opening with an inline tag continues the paragraph above it")
        starts = list(byline)
        self.assertNotIn(9, starts, "a lone video tag is block HTML: no paragraph of its own")
        self.assertEqual(len(_paragraphs('<video src="a.mp4"></video>\n')), 0,
                         "a page of nothing but a block tag has no prose paragraph")

    # the three shapes the trailing-link rule turns on, each its own page
    NAV_UNDER_HEADING = "## License\n\n[Apache-2.0](LICENSE).\n"
    NAV_UNDER_PROSE = "# Title\n\nA paragraph of prose that says something.\n\n[Apache-2.0](LICENSE).\n"
    PARAGRAPH_ON_A_LINK = "# Title\n\nThe mechanics are in\n[How it works](architecture.md).\n"

    def test_a_link_only_paragraph_is_exempt_only_directly_under_a_heading(self):
        self.assertEqual(_trailing_link_violations(self.NAV_UNDER_HEADING), [],
                         "a line that is only a link, under its heading, is a navigation line")
        self.assertEqual(_trailing_link_violations(self.NAV_UNDER_PROSE),
                         [(5, "[Apache-2.0](LICENSE).")],
                         "the same line under prose is the shape the rule forbids, at its file line")
        self.assertEqual(_trailing_link_violations(self.PARAGRAPH_ON_A_LINK),
                         [(3, "The mechanics are in [How it works](architecture.md).")],
                         "a prose paragraph that ends on a link offends wherever it sits")
        self.assertEqual([offends for _line, _joined, offends in _trailing_link_checks(self.NAV_UNDER_PROSE)],
                         [False, True],
                         "a verdict per paragraph, in file order: the page test's subTest per paragraph")

    def test_the_nearest_prose_line_above_sees_through_a_comment(self):
        above = _prose_line_above(self.SNIPPET)
        self.assertEqual(above[4], "# A heading", "the heading, not the blank line between")
        self.assertEqual(above[2], "", "the dropped comment is not the line above the heading")
        # the shape the link-only exemption turns on: a comment between the heading and the line
        # under it is dropped before this reads, so it cannot hide the heading
        commented = "## License\n\n<!-- kept short on purpose -->\n\n[Apache-2.0](LICENSE).\n"
        self.assertEqual(_prose_line_above(commented)[5], "## License")


class FrontPagesStayShort(unittest.TestCase):
    def test_word_cap_per_page(self):
        for page in PAGES:
            with self.subTest(page=page):
                got = _words((DOCS / page).read_text(encoding="utf-8"))
                self.assertLessEqual(
                    got, WORD_CAP[page],
                    "docs/%s is %d words, over its %d-word budget: move the detail into "
                    "docs/reference.md and leave a paragraph stating what the feature does"
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

    def test_no_paragraph_ends_on_a_link(self):
        for page in GOVERNED:
            text = (REPO / page).read_text(encoding="utf-8")
            for line, joined, offends in _trailing_link_checks(text):
                with self.subTest(page=page, line=line):
                    self.assertFalse(
                        offends,
                        "%s line %d ends on a link (%r...): a paragraph states what the thing "
                        "does and carries the link inside a clause that says why a reader wants "
                        "it, rather than closing on somewhere else to go"
                        % (page, line, joined[:60]))

    def test_the_rule_is_written_down(self):
        md = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("The documentation front pages", md,
                      "CLAUDE.md is where the rule lives; this test only enforces it")


class DocsChipClassesHaveRules(unittest.TestCase):
    """Every `romp-chip-<name>` class a docs page draws has a rule in docs/stylesheets/extra.css (the site does not load the
    app's sheets, so a class without a rule is an unstyled word: the Needs you chip glyph, `romp-chip-needs`, renamed off
    the retired `romp-chip-blocked` in plans/needs-you.md's phase two)."""

    def test_every_chip_class_in_the_docs_has_a_rule(self):
        used = set()
        for page in DOCS.glob("*.md"):
            used |= set(re.findall(r"romp-chip-([a-z]+)", page.read_text(encoding="utf-8")))
        ruled = set(re.findall(r"\.romp-chip-([a-z]+)\b", (DOCS / "stylesheets" / "extra.css").read_text(encoding="utf-8")))
        self.assertTrue(used, "the docs draw at least one chip")
        self.assertEqual(sorted(used - ruled), [], "a chip class the docs draw with no rule in extra.css")
        self.assertNotIn("blocked", used, "the retired chip glyph: the category reads Needs you (plans/needs-you.md)")


if __name__ == "__main__":
    unittest.main()
