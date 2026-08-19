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
