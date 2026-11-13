"""Run the narration text pipeline over a passage and describe the result.

Used by the golden regression tests and by ``tools/baseline.py``. Keeping one
implementation means the committed goldens and the recorded listening
baseline always describe the same thing.
"""

from pathlib import Path

from tools.passages import Passage

from reader.segmenter import create_segments


def condense(text: str) -> str:
    """Drop every whitespace character so text can be compared for fidelity.

    Whitespace is exactly what the pipeline is allowed to change: it collapses
    runs of spaces, rejoins wrapped lines, and inserts paragraph breaks for
    the reader. Anything else that differs is text the listener gained or lost.
    """
    return "".join(text.split())


def passage_pages(passage: Passage) -> list[dict]:
    return [
        {"page": number, "text": text}
        for number, text in enumerate(passage.pages, start=1)
    ]


def describe_segments(segments) -> list[dict]:
    return [
        {
            "index": index,
            "page": segment.page,
            "chars": len(segment.text),
            "text": segment.text,
        }
        for index, segment in enumerate(segments)
    ]


def text_pipeline_dump(
    passage: Passage,
    voice: str = "af_heart",
    speed: float = 0.85,
) -> dict:
    """Describe what the reader would narrate for a plain-text source."""
    segments = create_segments(passage_pages(passage), voice=voice, speed=speed)

    source = condense("".join(passage.pages))
    narrated = condense("".join(segment.text for segment in segments))

    return {
        "passage": passage.name,
        "kind": passage.kind,
        "guards": passage.guards,
        "source_pages": len(passage.pages),
        "source_chars": len(source),
        "segment_count": len(segments),
        "pages_covered": sorted({segment.page for segment in segments}),
        "text_is_faithful": source == narrated,
        "segments": describe_segments(segments),
    }


# ----------------------------------------------------------------------
# PDF round trip
# ----------------------------------------------------------------------


def build_pdf(passage: Passage, path: str | Path) -> Path:
    """Render a passage as a real PDF, one source page per PDF page.

    Each paragraph becomes its own text box so extraction sees several
    blocks per page, the way it does in a real book. A passage rendered as
    one box would hide every block-joining defect.
    """
    import pymupdf as fitz

    path = Path(path)

    document = fitz.open()

    margin = 60.0
    gap = 14.0

    for page_text in passage.pages:
        page = document.new_page()

        top = margin

        for paragraph in page_text.split("\n\n"):
            paragraph = " ".join(paragraph.split())

            if not paragraph:
                continue

            rect = fitz.Rect(
                margin,
                top,
                page.rect.width - margin,
                page.rect.height - margin,
            )

            if rect.height <= 0:
                break

            remaining = page.insert_textbox(
                rect,
                paragraph,
                fontsize=11,
                fontname="helv",
                align=0,
            )

            if remaining < 0:
                # Paragraph did not fit. Fixtures are sized to avoid this;
                # failing loudly beats silently truncating a baseline.
                raise ValueError(
                    f"Passage {passage.name!r} overflows a PDF page. "
                    "Shorten the paragraph or split the fixture."
                )

            top += (rect.height - remaining) + gap

    document.save(path)
    document.close()

    return path


def pdf_pipeline_dump(
    passage: Passage,
    pdf_path: str | Path,
    voice: str = "af_heart",
    speed: float = 0.85,
) -> dict:
    """Describe narration for the same passage taken through PDF extraction.

    Extraction may legitimately drop content (page numbers, running heads),
    so fidelity is reported as a coverage ratio rather than asserted.
    """
    from reader.document_reader import extract_pdf
    from reader.layout_filter import (
        NarrationSettings,
        build_narration_pages,
        classify_blocks,
    )

    raw_pages = extract_pdf(str(pdf_path))

    classified = classify_blocks(raw_pages)

    pages = build_narration_pages(classified, NarrationSettings())

    segments = create_segments(pages, voice=voice, speed=speed)

    source = condense("".join(passage.pages))
    narrated = condense("".join(segment.text for segment in segments))

    kept = sum(1 for character in narrated if character in source)

    return {
        "passage": passage.name,
        "source": "pdf",
        "segment_count": len(segments),
        "pages_covered": sorted({segment.page for segment in segments}),
        "block_counts": [len(page) for page in raw_pages],
        "coverage": round(len(narrated) / len(source), 4) if source else 0.0,
        "text_is_faithful": source == narrated,
        "unexpected_chars": len(narrated) - kept,
        "segments": describe_segments(segments),
    }
