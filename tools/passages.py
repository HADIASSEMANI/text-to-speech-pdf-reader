"""Representative passages used for regression and listening baselines.

Each passage isolates one thing the narration pipeline has to get right.
They are written as source *pages* rather than one blob, because several of
the known defects only appear at a page boundary.

The text is deliberately plain and original so the corpus can be committed
and diffed. Keep additions small and single-purpose: a passage that exercises
five behaviours at once cannot tell you which one regressed.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Passage:
    name: str
    kind: str
    pages: tuple[str, ...]
    guards: str


DIALOGUE = Passage(
    name="dialogue",
    kind="prose",
    guards=(
        "Quoted speech, attribution tags, and a question inside a quote. "
        "Sentence splitting must not break on the period inside a quote, "
        "and the reader should not pause mid-exchange."
    ),
    pages=(
        '"You are early," she said, setting the lamp down on the crate.\n'
        '"The train was empty."\n'
        '\n'
        '"It usually is." He pulled the door closed behind him. "Did anyone '
        'see you come up the hill?"\n'
        '\n'
        '"No one is awake at this hour, Mr. Halloway. Not even the dogs."\n'
        '\n'
        'She waited. He said nothing, so she asked again, more slowly: "Did '
        'you bring it?"\n',
    ),
)


QUESTIONS = Passage(
    name="questions",
    kind="prose",
    guards=(
        "Consecutive short questions. Kokoro's intonation depends on the "
        "question mark surviving cleanup, and each question should be its "
        "own cue for highlighting."
    ),
    pages=(
        "What does a reader actually want from a machine voice? Not "
        "perfection. Who would claim to want that?\n"
        "\n"
        "The better question is narrower. Where does the voice lose you? Is "
        "it the pace, the flat cadence, or the way a paragraph ends without "
        "any sense that it has ended?\n",
    ),
)


ABBREVIATIONS = Passage(
    name="abbreviations",
    kind="prose",
    guards=(
        "Periods that do not end sentences (Dr., St., e.g., i.e., etc.), "
        "initials, and a decimal number. Naive sentence splitting fragments "
        "all of these."
    ),
    pages=(
        "Dr. A. M. Reyes arrived at St. Brendan's at 4.30 p.m. on a Tuesday, "
        "carrying no luggage. The porter, Mr. Ellis, had been told to expect "
        "someone from the U.S. — a researcher, i.e. not a patient.\n"
        "\n"
        "The file listed three conditions (fever, tremor, insomnia, etc.) and "
        "one note: approx. 12.5 hours since onset. Vol. II of the register "
        "had gone missing years ago.\n",
    ),
)


LONG_SENTENCE = Passage(
    name="long_sentence",
    kind="prose",
    guards=(
        "A single sentence long enough to exceed the old 1500-character "
        "chunk limit. The current chunker splits it at an arbitrary word; "
        "the replacement must split at a clause boundary or not at all."
    ),
    pages=(
        "It began, as these things generally do, with a small administrative "
        "decision that nobody present understood to be important at the time, "
        + (
            "a decision recorded in the minutes as a single line without "
            "discussion or dissent, passed between departments over the "
            "following weeks in the ordinary way that paperwork moves through "
            "an institution that has long since stopped asking why any "
            "particular form exists, "
        )
        * 6
        + "and by the following spring nobody could say who had signed it.\n",
    ),
)


HEADINGS = Passage(
    name="headings",
    kind="structure",
    guards=(
        "A heading followed immediately by body text. The heading must not "
        "be glued onto the sentence after it, and the boundary after a "
        "heading is one of the few that genuinely deserves a pause."
    ),
    pages=(
        "Chapter Four\n"
        "\n"
        "The Weather Station\n"
        "\n"
        "For eleven years the station reported nothing of interest. Its "
        "instruments were checked each spring, replaced each decade, and "
        "otherwise left alone.\n"
        "\n"
        "A Note on the Records\n"
        "\n"
        "The logs survive in two forms. Neither is complete.\n",
    ),
)


LISTS = Passage(
    name="lists",
    kind="structure",
    guards=(
        "Numbered and bulleted items. Each item is a unit; running them "
        "together sounds like one long sentence, and merging them into the "
        "preceding paragraph loses the structure entirely."
    ),
    pages=(
        "The procedure has four steps.\n"
        "\n"
        "1. Record the ambient temperature before opening the case.\n"
        "2. Remove the drum and set it aside on a dry surface.\n"
        "3. Inspect the pen arm for play at the hinge.\n"
        "4. Reassemble, then wait a full hour before reading the trace.\n"
        "\n"
        "Skipping the final step is the most common error. Others include:\n"
        "\n"
        "- opening the case in direct sun\n"
        "- handling the drum without gloves\n"
        "- recording the time from memory\n",
    ),
)


PAGE_CONTINUATION = Passage(
    name="page_continuation",
    kind="structure",
    guards=(
        "A sentence that runs across a page break, and a short final "
        "fragment on the second page. Today the join becomes a paragraph "
        "break mid-sentence, and the fragment loses its own page number."
    ),
    pages=(
        "The path climbed for another mile before it turned, and where it "
        "turned the trees thinned enough that you could see the valley "
        "floor, which at that hour was still holding the last of the mist, "
        "so she stopped walking and stood there until the wind moved "
        "through the",
        "branches and the whole view shifted at once.\n"
        "\n"
        "She kept walking after that.\n",
    ),
)


SHORT_PAGE = Passage(
    name="short_page",
    kind="structure",
    guards=(
        "A page holding a single short paragraph. It is merged into the "
        "previous page's segment today, which silently moves its page "
        "number and breaks page navigation."
    ),
    pages=(
        "The register was kept in a locked drawer beneath the counter, and "
        "only two people had ever been given a key to it, which is the "
        "detail that matters most in everything that follows.\n",
        "Neither of them is still alive.\n",
        "The drawer was opened again in March.\n",
    ),
)


HYPHENATION = Passage(
    name="hyphenation",
    kind="prose",
    guards=(
        "Line-wrap hyphens that must be repaired (under-standing) beside "
        "genuine compounds that must survive (well-known, twenty-three, "
        "self-evident)."
    ),
    pages=(
        "The well-known difficulty is not a lack of under-\n"
        "standing but a lack of patience. Twenty-three separate attempts\n"
        "were made before the self-evident answer was recorded, and the com-\n"
        "mittee never published the earlier ones.\n",
    ),
)


ALL_PASSAGES: tuple[Passage, ...] = (
    DIALOGUE,
    QUESTIONS,
    ABBREVIATIONS,
    LONG_SENTENCE,
    HEADINGS,
    LISTS,
    PAGE_CONTINUATION,
    SHORT_PAGE,
    HYPHENATION,
)


def get_passage(name: str) -> Passage:
    for passage in ALL_PASSAGES:
        if passage.name == name:
            return passage

    raise KeyError(f"No passage named {name!r}")
