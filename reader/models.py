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

    # Markup for `text`, carrying exactly the same characters. The reader
    # highlights by selecting a character range, so the two must not drift.
    html: str = ""

    # What is spoken. Differs from `text` wherever notation is displayed and
    # a sentence is read: the equation on screen stays an equation.
    spoken_text: str = ""

    # Source identifiers of the blocks this segment was built from. These are
    # what a saved position is anchored to, because they survive a change to
    # how the book is chunked.
    source_ids: list[str] = field(default_factory=list)

    # The page as the book itself labels it, which for an EPUB comes from its
    # own pagebreak anchors rather than from a rendered layout.
    page_label: str | None = None

    # (spoken start/end, display start/end), in Python character offsets.
    speech_spans: list[tuple[int, int, int, int]] = field(default_factory=list)

    def __post_init__(self):
        if not self.spoken_text:
            self.spoken_text = self.text


@dataclass
class Chapter:
    level: int
    title: str
    page: int
    segment_index: int | None = None

    # For EPUB, the content document (and optional fragment) the entry
    # points at. Chapter positions are resolved through this rather than
    # through a page number the renderer invented.
    target: str | None = None
