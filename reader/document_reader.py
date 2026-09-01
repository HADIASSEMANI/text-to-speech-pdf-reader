from pathlib import Path

import pymupdf as fitz

from reader.models import Chapter, TextBlock
from reader.pdf_reader import extract_blocks
from reader.text_source import extract_text

SUPPORTED_EXTENSIONS = {".pdf", ".epub", ".txt"}


def extract_pdf(path: str) -> list[list[TextBlock]]:
    """Layout-aware PDF extraction, kept as-is for the filtering pipeline."""
    return extract_blocks(path)


def extract_epub(path: str) -> list[dict]:
    """EPUB is reflowable, so skip PDF-specific layout heuristics (headers,
    footers, sidebars, page numbers) and hand the segmenter plain page text.
    """
    document = fitz.open(path)

    pages = []

    for page_number, page in enumerate(document, start=1):
        text = page.get_text("text", sort=True).strip()

        if not text:
            continue

        pages.append({"page": page_number, "text": text})

    document.close()

    return pages


def extract_chapters(path: str) -> list[Chapter]:
    """Read the document outline/TOC. Works for EPUB TOC and PDF bookmarks
    alike; returns an empty list when the document has neither.
    """
    if Path(path).suffix.lower() == ".txt":
        return []

    document = fitz.open(path)

    toc = document.get_toc()

    chapters = []

    for level, title, page, *_ in toc:
        if not title:
            continue

        chapters.append(Chapter(level=level, title=title.strip(), page=page))

    document.close()

    return chapters


def _check_supported(path: str) -> str:
    extension = Path(path).suffix.lower()

    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported format: {extension}")

    return extension
