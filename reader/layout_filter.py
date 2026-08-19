import re
from collections import Counter

from reader.models import TextBlock
from reader.models import NarrationSettings

HEADER_RATIO = 0.08
FOOTER_RATIO = 0.08

FOOTNOTE_BOTTOM_RATIO = 0.72
FOOTNOTE_FONT_RATIO = 0.82

REPEAT_THRESHOLD = 3


def normalize_repeated_text(text: str) -> str:

    text = text.lower().strip()

    # Remove standalone numbers
    text = re.sub(r"\b\d+\b", "", text)

    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def find_repeated_margin_text(pages: list[list[TextBlock]]) -> set[str]:

    candidates = []

    for blocks in pages:

        for block in blocks:

            top_limit = block.page_height * HEADER_RATIO

            bottom_limit = block.page_height * (1 - FOOTER_RATIO)

            if block.y0 <= top_limit or block.y1 >= bottom_limit:

                normalized = normalize_repeated_text(block.text)

                if normalized:
                    candidates.append(normalized)

    counts = Counter(candidates)

    return {text for text, count in counts.items() if count >= REPEAT_THRESHOLD}


def is_page_number(block: TextBlock) -> bool:

    text = block.text.strip()

    if not text.isdigit():
        return False

    # Only consider small isolated numbers
    if len(text) > 4:
        return False

    near_top = block.y0 <= block.page_height * 0.10

    near_bottom = block.y1 >= block.page_height * 0.90

    return near_top or near_bottom


def is_probable_caption(block: TextBlock, body_font_size: float) -> bool:

    text = block.text.strip().lower()

    caption_prefixes = (
        "figure ",
        "fig. ",
        "fig ",
        "image ",
        "illustration ",
        "photo ",
        "photograph ",
        "diagram ",
        "chart ",
    )

    return text.startswith(caption_prefixes)


def mark_caption_neighbors(pages: list[list[TextBlock]]):

    for blocks in pages:

        for index, block in enumerate(blocks):

            if block.kind != "caption":
                continue

            # Check the following block
            next_index = index + 1

            if next_index >= len(blocks):
                continue

            next_block = blocks[next_index]

            vertical_distance = next_block.y0 - block.y1

            # Close to the caption
            close_below = 0 <= vertical_distance <= 25

            # Similar horizontal region
            horizontally_related = abs(next_block.x0 - block.x0) <= 40

            if close_below and horizontally_related:
                next_block.kind = "caption"


def is_probable_sidebar(block: TextBlock, body_font_size: float) -> bool:

    block_width = block.x1 - block.x0

    width_ratio = block_width / block.page_width

    left_margin_block = block.x1 < block.page_width * 0.33

    right_margin_block = block.x0 > block.page_width * 0.67

    # A 28% width cutoff is too broad for indented lists and text extracted
    # from figure layouts. Only classify genuinely narrow margin content as a
    # sidebar.
    narrow = width_ratio < 0.18

    smaller_font = block.font_size < body_font_size * 0.95

    return narrow and smaller_font and (left_margin_block or right_margin_block)


def estimate_body_font_size(pages: list[list[TextBlock]]) -> float:

    sizes = []

    for blocks in pages:

        for block in blocks:

            if block.font_size > 0:
                sizes.append(round(block.font_size, 1))

    if not sizes:
        return 12.0

    counts = Counter(sizes)

    return counts.most_common(1)[0][0]


def is_probable_footnote(block: TextBlock, body_font_size: float) -> bool:

    near_bottom = block.y0 >= block.page_height * FOOTNOTE_BOTTOM_RATIO

    smaller_font = block.font_size < body_font_size * FOOTNOTE_FONT_RATIO

    return near_bottom and smaller_font


def classify_blocks(pages: list[list[TextBlock]]) -> list[list[TextBlock]]:

    repeated_margin_text = find_repeated_margin_text(pages)

    body_font_size = estimate_body_font_size(pages)

    for blocks in pages:

        for block in blocks:

            normalized = normalize_repeated_text(block.text)

            if is_page_number(block):
                block.kind = "page_number"

                continue

            if normalized in repeated_margin_text:
                block.kind = "header_footer"

                continue

            if is_probable_sidebar(block, body_font_size):
                block.kind = "sidebar"
                continue

            # Figure/image caption
            if is_probable_caption(block, body_font_size):
                block.kind = "caption"
                continue

            if is_probable_footnote(block, body_font_size):
                block.kind = "footnote"

                continue

            block.kind = "body"

    # Keep caption classification conservative. Neighboring blocks can be
    # normal body prose that starts immediately after a figure or caption.
    # Re-enable only after caption-neighbor detection has stronger evidence.
    # mark_caption_neighbors(pages)

    mark_terminal_sections(pages, body_font_size)

    return pages


def build_narration_pages(
    pages: list[list[TextBlock]], settings: NarrationSettings
) -> list[dict]:

    narration_pages = []

    for page_number, blocks in enumerate(pages, start=1):

        # Filter out blocks we don't want narrated
        kept = [block.text for block in blocks if should_keep(block, settings)]

        narration_pages.append({"page": page_number, "text": "\n\n".join(kept)})

    return narration_pages


TERMINAL_SECTIONS = {
    "appendix",
    "appendices",
    "references",
    "bibliography",
    "works cited",
    "index",
}


def normalize_heading(text: str) -> str:

    return text.strip().lower().rstrip(":")


def is_terminal_section_heading(block: TextBlock, body_font_size: float) -> bool:

    text = normalize_heading(block.text)

    matches = text in TERMINAL_SECTIONS or text.startswith("appendix ")

    if not matches:
        return False

    heading_like = block.font_size >= body_font_size * 1.05

    short = len(block.text.strip()) < 80

    return heading_like and short


def mark_terminal_sections(pages: list[list[TextBlock]], body_font_size: float):

    skipping = False

    for blocks in pages:

        for block in blocks:

            if is_terminal_section_heading(block, body_font_size):
                skipping = True
                block.kind = "terminal_section"
                continue

            if skipping:
                block.kind = "terminal_section"


def should_keep(block: TextBlock, settings: NarrationSettings) -> bool:

    if block.kind == "body":
        return True

    if block.kind == "footnote" and settings.read_footnotes:
        return True

    if block.kind == "header_footer" and settings.read_headers:
        return True

    if block.kind == "page_number" and settings.read_page_numbers:
        return True

    if block.kind == "caption" and settings.read_captions:
        return True

    if block.kind == "sidebar" and settings.read_sidebars:
        return True

    if block.kind == "terminal_section":
        return False

    return False
