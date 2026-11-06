from pathlib import Path

from reader.models import Segment
from reader.text_cleaner import clean_text
from reader.chunker import chunk_text
from reader.cache import create_cache_id
from reader.paths import cache_dir


def create_segments(
    pages: list[dict],
    voice: str = "af_heart",
    speed: float = 1.0
) -> list[Segment]:

    segments = []
    segment_id = 0
    chunk_records = []

    for page in pages:
        page_number = page["page"]

        text = clean_text(page["text"])

        if not text:
            continue

        chunks = chunk_text(text)

        for chunk in chunks:
            chunk_records.append((page_number, chunk))

    # Merge short page-end/page-start fragments after all pages have been
    # chunked. This handles a one-line paragraph that is isolated only because
    # it happens to be the sole content of a PDF page.
    merged_records = []

    for page_number, chunk in chunk_records:
        if (
            merged_records
            and len(chunk) < 200
            and len(merged_records[-1][1]) + len(chunk) + 2 <= 1500
        ):
            previous_page, previous_text = merged_records[-1]
            merged_records[-1] = (
                previous_page,
                previous_text + "\n\n" + chunk,
            )
        else:
            merged_records.append((page_number, chunk))

    for page_number, chunk in merged_records:
        segment_id += 1

        cache_id = create_cache_id(
            text=chunk,
            voice=voice,
            speed=speed
        )

        # Name the file by cache id so voice/speed changes get their own
        # audio instead of reusing a clip generated with other settings.
        audio_path = str(cache_dir() / f"{cache_id}.wav")

        segment = Segment(
            id=segment_id,
            page=page_number,
            text=chunk,
            cache_id=cache_id,
            audio_path=audio_path,
            generated=Path(
                audio_path
            ).exists()
        )

        segments.append(segment)

    return segments


# ----------------------------------------------------------------------
# structured sources
# ----------------------------------------------------------------------


MAX_SEGMENT_CHARS = 1500


# Blocks are joined by a single newline, not a blank line.
#
# Qt counts one character for the boundary between two rich-text blocks, so
# the plain text the reader highlights against has to do the same or every
# cue offset drifts by one per paragraph. The visible separation between
# paragraphs comes from their margins instead, which is what it should have
# come from anyway.
BLOCK_SEPARATOR = "\n"


# Qt's rich text understands a small subset of CSS on block elements:
# margins, line-height and font properties. That is enough to give a heading
# room, set an equation off from the prose, and open the line spacing to
# something readable.
PARAGRAPH_STYLE = "white-space:pre-wrap; line-height:140%; margin-top:0px; margin-bottom:14px"
HEADING_STYLE = "white-space:pre-wrap; margin-top:22px; margin-bottom:10px"
EQUATION_STYLE = (
    "white-space:pre-wrap; margin-left:28px; margin-top:14px; margin-bottom:14px; line-height:150%"
)
LIST_STYLE = "white-space:pre-wrap; margin-left:18px; margin-top:0px; margin-bottom:4px; line-height:140%"


def _block_html(block) -> str:
    from reader.content_blocks import EQUATION, HEADING, LIST_ITEM

    if block.kind == HEADING:
        level = min(max(block.level, 1), 6)

        return (
            f'<h{level} style="{HEADING_STYLE}">'
            f"{block.display_html}</h{level}>"
        )

    if block.kind == EQUATION:
        return f'<p style="{EQUATION_STYLE}">{block.display_html}</p>'

    if block.kind == LIST_ITEM:
        return f'<p style="{LIST_STYLE}">{block.display_html}</p>'

    return f'<p style="{PARAGRAPH_STYLE}">{block.display_html}</p>'


def _page_number(block, fallback: int) -> int:
    """The book's own page number when it has one.

    An EPUB carries pagebreak anchors giving the printed page, which is what
    a reader means by "page 142". A layout-generated number is not.
    """
    label = block.page_label

    if label and label.isdigit():
        return int(label)

    return fallback


def create_segments_from_blocks(
    blocks: list,
    voice: str = "af_heart",
    speed: float = 1.0,
    max_chars: int = MAX_SEGMENT_CHARS,
) -> list[Segment]:
    """Group content blocks into narration segments.

    A block is never split. Chunking used to cut at a character count, which
    is how a production list became one run-on line and a sentence was broken
    in half; a paragraph or an equation is an indivisible unit here.
    """
    from reader.content_blocks import HEADING

    segments: list[Segment] = []

    group: list = []
    group_chars = 0

    def flush():
        nonlocal group, group_chars

        if not group:
            return

        text_parts = []
        html_parts = []
        spoken_parts = []
        speech_spans = []
        display_offset = spoken_offset = 0

        previous = None

        for block in group:
            if previous is not None:
                text_parts.append(BLOCK_SEPARATOR)
                spoken_parts.append("\n\n")
                display_offset += len(BLOCK_SEPARATOR)
                spoken_offset += 2

            speech_spans.append((spoken_offset, spoken_offset + len(block.spoken_text),
                                 display_offset, display_offset + len(block.display_text)))
            display_offset += len(block.display_text)
            spoken_offset += len(block.spoken_text)
            text_parts.append(block.display_text)
            html_parts.append(_block_html(block))
            spoken_parts.append(block.spoken_text)

            previous = block

        text = "".join(text_parts)

        if text:
            spoken = "".join(spoken_parts)

            cache_id = create_cache_id(text=spoken, voice=voice, speed=speed)

            segments.append(
                Segment(
                    id=len(segments) + 1,
                    page=_page_number(group[0], len(segments) + 1),
                    text=text,
                    html="".join(html_parts),
                    spoken_text=spoken,
                    speech_spans=speech_spans,
                    source_ids=[block.source_id for block in group],
                    page_label=group[0].page_label,
                    cache_id=cache_id,
                    audio_path=str(cache_dir() / f"{cache_id}.wav"),
                    generated=Path(
                        cache_dir() / f"{cache_id}.wav"
                    ).exists(),
                )
            )

        group = []
        group_chars = 0

    for block in blocks:
        if not block.display_text.strip():
            continue

        length = len(block.display_text)

        # A heading opens a passage rather than closing one.
        if block.kind == HEADING and group:
            flush()

        elif group and group_chars + length > max_chars:
            flush()

        group.append(block)
        group_chars += length + 2

    flush()

    return segments
