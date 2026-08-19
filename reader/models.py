from dataclasses import dataclass, field


@dataclass
class TextBlock:
    page: int
    text: str

    x0: float
    y0: float
    x1: float
    y1: float

    font_size: float
    page_width: float
    page_height: float

    kind: str = "body"


@dataclass
class NarrationSettings:
    read_footnotes: bool = False
    read_headers: bool = False
    read_page_numbers: bool = False
    read_captions: bool = False
    read_sidebars: bool = False

    skip_appendix: bool = True
    skip_references: bool = True


@dataclass
class TextCue:
    text: str
    start: float
    end: float

    char_start: int = 0
    char_end: int = 0


@dataclass
class Segment:
    id: int
    page: int
    text: str

    cache_id: str
    audio_path: str

    generated: bool = False

    cues: list[TextCue] = field(default_factory=list)


@dataclass
class Chapter:
    level: int
    title: str
    page: int
    segment_index: int | None = None
