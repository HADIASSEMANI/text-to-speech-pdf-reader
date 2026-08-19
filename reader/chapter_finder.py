import re
from collections import Counter

from reader.models import TextBlock


CONTENTS_HEADINGS = {"contents", "table of contents"}
CHAPTER_ONE_PATTERN = re.compile(r"\bchapter\s+(?:1|one)\b", re.IGNORECASE)


def find_first_chapter_page(pages: list[list[TextBlock]]) -> int | None:
    """Return the PDF page containing Chapter 1, using the contents section."""
    contents_page = _find_contents_page(pages)
    if contents_page is None:
        return None

    body_font_size = _estimate_body_font_size(pages)

    # A chapter heading should occur after the contents section and be styled
    # more prominently than a table-of-contents entry.
    for blocks in pages[contents_page:]:
        for block in blocks:
            if (
                CHAPTER_ONE_PATTERN.search(block.text)
                and len(block.text.strip()) < 160
                and block.font_size >= body_font_size * 1.05
            ):
                return block.page

    return None


def _find_contents_page(pages: list[list[TextBlock]]) -> int | None:
    for blocks in pages[:30]:
        for block in blocks:
            heading = block.text.strip().lower().rstrip(":")
            if heading in CONTENTS_HEADINGS:
                return block.page

    return None


def _estimate_body_font_size(pages: list[list[TextBlock]]) -> float:
    sizes = [
        round(block.font_size, 1)
        for blocks in pages
        for block in blocks
        if block.font_size > 0
    ]

    if not sizes:
        return 12.0

    return Counter(sizes).most_common(1)[0][0]
