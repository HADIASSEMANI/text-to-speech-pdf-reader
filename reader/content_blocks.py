"""The unit the reader shows and speaks.

A book used to travel through the pipeline as flat text, which meant that by
the time anything wanted to know whether a line was a heading, a production
rule or ordinary prose, that had already been thrown away. A ``ContentBlock``
carries the three things that have to stay together:

* what is displayed, both as characters and as the markup that styles them,
* what is spoken, which for an equation is a sentence rather than notation,
* where it came from, so a saved position survives re-extraction.

``display_text`` and ``display_html`` always contain the *same characters* in
the same order; the html only adds markup around them. The reader highlights
by selecting a character range, so anything that changed the characters would
break highlighting and click-to-read.
"""

from dataclasses import dataclass, field


HEADING = "heading"
PARAGRAPH = "paragraph"
LIST_ITEM = "list_item"
EQUATION = "equation"
FIGURE = "figure"


@dataclass
class ContentBlock:
    source_id: str

    kind: str = PARAGRAPH

    display_text: str = ""
    display_html: str = ""

    # Filled in by the narration pass. Until then it is the displayed text,
    # which is what the reader spoke before any of this existed.
    spoken_text: str = ""

    # Heading depth, or 0 for anything else.
    level: int = 0

    # The printed page this block falls on, taken from the EPUB's own
    # pagebreak anchors rather than from a rendered layout.
    page_label: str | None = None

    # Source order within the book, used to keep spine order stable.
    document: str = ""
    position: int = 0

    # MathML for an equation block, kept so narration can read the structure
    # instead of guessing at flattened characters.
    mathml: str | None = None

    # Equation blocks that could not be understood keep their notation but
    # say so rather than inventing a reading.
    uncertain: bool = False

    # Image sources referenced by this block, resolved against the content
    # document they appeared in.
    images: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.spoken_text:
            self.spoken_text = self.display_text

    @property
    def is_math(self) -> bool:
        return self.kind == EQUATION

    def with_spoken(self, spoken: str, uncertain: bool = False) -> "ContentBlock":
        """Return a copy that says something different from what it shows."""
        from dataclasses import replace

        return replace(self, spoken_text=spoken, uncertain=uncertain)
