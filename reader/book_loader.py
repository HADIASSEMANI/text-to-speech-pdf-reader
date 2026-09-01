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
from reader.progress import get_or_create_book
from reader.segmenter import create_segments
from reader.tts import KokoroTTS


@dataclass
class PreparedBook:
    path: str
    segments: list[Segment]
    tts: KokoroTTS
    book_id: int
    start_index: int
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

        pages = extract_epub(pdf_path)

    else:
        status("Reading pasted text...")

        pages = extract_text(pdf_path)

    status("Creating segments...")

    segments = create_segments(pages, voice=voice, speed=speed)

    if not segments:
        raise ValueError("No narratable text was found in this book.")

    status("Reading table of contents...")

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

    start_index = book.current_segment

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

    status("Loading speech model...")

    tts = KokoroTTS(voice=voice, speed=speed)

    return PreparedBook(
        path=pdf_path,
        segments=segments,
        tts=tts,
        book_id=book.id,
        start_index=start_index,
        chapters=chapters,
    )
