from reader.models import Segment
from reader.text_cleaner import clean_text
from reader.chunker import chunk_text
from reader.cache import create_cache_id


def create_segments(
    pages: list[dict],
    voice: str = "af_heart",
    speed: float = 1.0
) -> list[Segment]:

    segments = []
    segment_id = 0

    for page in pages:
        page_number = page["page"]

        text = clean_text(page["text"])

        if not text:
            continue

        chunks = chunk_text(text)

        for chunk in chunks:
            segment_id += 1

            cache_id = create_cache_id(
                text=chunk,
                voice=voice,
                speed=speed
            )

            audio_path = (
                f"cache/segment_{cache_id}.wav"
            )

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