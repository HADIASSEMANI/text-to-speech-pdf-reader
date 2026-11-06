from dataclasses import dataclass, field

from reader.chapter_finder import find_first_chapter_page
from reader.controller import ReaderController
from reader.document_reader import (
    extract_chapters,
    extract_epub,
    extract_pdf,
    extract_text,
    _check_supported,
)
from reader.layout_filter import (
    NarrationSettings,
    build_narration_pages,
    classify_blocks,
)
from reader.models import Chapter, Segment
from reader.progress import get_or_create_book, resolve_resume_point
from reader.epub_reader import extract_blocks as extract_epub_blocks
from reader.epub_reader import extract_nav
from reader.segmenter import create_segments, create_segments_from_blocks
from reader.tts import KokoroTTS


@dataclass
class PreparedBook:
    path: str
    segments: list[Segment]
    tts: KokoroTTS
    book_id: int
    start_index: int
    start_position: float = 0.0
    chapters: list[Chapter] = field(default_factory=list)


def load_book(
    pdf_path: str,
    voice: str = "af_heart",
    speed: float = 0.85,
    read_footnotes: bool = False,
    read_captions: bool = False,
    read_sidebars: bool = False,
    on_status=None,
) -> ReaderController:
    """Synchronously prepare a book and construct its playback controller."""
    prepared = prepare_book(
        pdf_path,
        voice=voice,
        speed=speed,
        read_footnotes=read_footnotes,
        read_captions=read_captions,
        read_sidebars=read_sidebars,
        on_status=on_status,
    )

    return ReaderController(
        segments=prepared.segments,
        tts=prepared.tts,
        book_id=prepared.book_id,
        start_index=prepared.start_index,
        start_position=prepared.start_position,
        preload_count=2,
        chapters=prepared.chapters,
    )


def prepare_book(
    pdf_path: str,
    voice: str = "af_heart",
    speed: float = 0.85,
    read_footnotes: bool = False,
    read_captions: bool = False,
    read_sidebars: bool = False,
    on_status=None,
) -> PreparedBook:
    """Prepare book data without initializing the audio player."""

    def status(message: str):
        if on_status is not None:
            on_status(message)

    status("Reading saved progress...")

    book = get_or_create_book(pdf_path)

    extension = _check_supported(pdf_path)

    raw_pages = None
    pages = None
    segments = None
    blocks = None

    if extension == ".pdf":
        status("Extracting PDF...")

        raw_pages = extract_pdf(pdf_path)

        status("Analyzing document layout...")

        classified_pages = classify_blocks(raw_pages)

        settings = NarrationSettings(
            read_footnotes=read_footnotes,
            read_headers=False,
            read_page_numbers=False,
            read_captions=read_captions,
            read_sidebars=read_sidebars,
        )

        status("Preparing narration...")

        pages = build_narration_pages(classified_pages, settings)

    elif extension == ".epub":
        status("Extracting EPUB...")

        # Structured extraction: the EPUB is XHTML, so headings, list
        # structure, superscripts and MathML are read rather than rendered
        # away. The plain-text path is kept as a fallback for a file this
        # cannot open.
        try:
            blocks = extract_epub_blocks(pdf_path)
        except Exception as error:
            print(f"Structured EPUB extraction failed, falling back: {error}")

            blocks = None

        if blocks:
            status("Preparing narration...")

            segments = create_segments_from_blocks(
                blocks,
                voice=voice,
                speed=speed,
            )
        else:
            pages = extract_epub(pdf_path)

    else:
        status("Reading pasted text...")

        pages = extract_text(pdf_path)

    if segments is None:
        status("Creating segments...")

        segments = create_segments(pages, voice=voice, speed=speed)

    if not segments:
        raise ValueError("No narratable text was found in this book.")

    status("Reading table of contents...")

    if blocks:
        chapters = _epub_chapters(pdf_path, segments)
    else:
        chapters = extract_chapters(pdf_path)

        for chapter in chapters:
            chapter.segment_index = next(
                (
                    index
                    for index, segment in enumerate(segments)
                    if segment.page >= chapter.page
                ),
                None,
            )

    # Resolved from the anchor rather than the stored index, so the saved
    # place survives a change of voice, speed, or chunking.
    start_index, start_position = resolve_resume_point(book, segments)

    if book.is_new:
        first_chapter_page = (
            find_first_chapter_page(raw_pages) if raw_pages is not None else None
        )

        if first_chapter_page is not None:
            start_index = next(
                (
                    index
                    for index, segment in enumerate(segments)
                    if segment.page >= first_chapter_page
                ),
                0,
            )
            print(
                "Starting at Chapter 1 "
                f"on PDF page {first_chapter_page}."
            )
        elif chapters and chapters[0].segment_index is not None:
            start_index = chapters[0].segment_index

    if start_index >= len(segments):
        start_index = 0
        start_position = 0.0

    status("Loading speech model...")

    tts = KokoroTTS(voice=voice, speed=speed)

    return PreparedBook(
        path=pdf_path,
        segments=segments,
        tts=tts,
        book_id=book.id,
        start_index=start_index,
        start_position=start_position,
        chapters=chapters,
    )


def _epub_chapters(epub_path: str, segments: list[Segment]) -> list[Chapter]:
    """Map the EPUB's own navigation onto segments.

    Entries point at a content document and sometimes an element inside it.
    Both are matched against the source identifiers the segments carry, so a
    chapter lands where the book says it does rather than on a page number
    that structured extraction no longer produces.
    """
    chapters: list[Chapter] = []

    # First segment that touches each document, and each fragment.
    document_index: dict[str, int] = {}
    fragment_index: dict[str, int] = {}

    for index, segment in enumerate(segments):
        for source_id in segment.source_ids:
            document = source_id.split("#")[0].split(":")[0]

            document_index.setdefault(document, index)

            if "#" in source_id:
                fragment_index.setdefault(source_id, index)

    for level, title, target in extract_nav(epub_path):
        document = target.split("#")[0]

        segment_index = fragment_index.get(target)

        if segment_index is None:
            segment_index = document_index.get(document)

        page = (
            segments[segment_index].page
            if segment_index is not None
            else 0
        )

        chapters.append(
            Chapter(
                level=level,
                title=title,
                page=page,
                segment_index=segment_index,
                target=target,
            )
        )

    return chapters
