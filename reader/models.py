from dataclasses import dataclass


@dataclass
class Segment:
    id: int
    page: int
    text: str

    cache_id: str | None = None
    audio_path: str | None = None

    generated: bool = False