"""The acceptance criteria for narration quality, as executable tests.

Some of these pass today. The ones marked ``expectedFailure`` are the
Phase 3 targets: no text lost, no sentence cut in half, no paragraph break
inserted mid-sentence, every source page reachable, and wrapped words
rejoined. When Phase 3 lands they should start passing, and unittest will
report the unexpected success rather than letting it go unnoticed.
"""

import re
import unittest

from tools.passages import ALL_PASSAGES, get_passage
from tools.pipeline_dump import condense, text_pipeline_dump


def segment_texts(passage_name: str) -> list[str]:
    dump = text_pipeline_dump(get_passage(passage_name))

    return [segment["text"] for segment in dump["segments"]]


class TextFidelityTests(unittest.TestCase):
    """Nothing the author wrote may be dropped or repeated."""

    def test_every_passage_is_narrated_in_full(self):
        for passage in ALL_PASSAGES:
            with self.subTest(passage=passage.name):
                dump = text_pipeline_dump(passage)

                self.assertEqual(
                    condense("".join(passage.pages)),
                    condense("".join(s["text"] for s in dump["segments"])),
                    "narrated text differs from the source",
                )


class SentenceBoundaryTests(unittest.TestCase):
    @unittest.expectedFailure
    def test_segments_do_not_end_mid_sentence(self):
        """Phase 3: a synthesis request should end where a sentence ends."""
        texts = segment_texts("long_sentence")

        for index, text in enumerate(texts[:-1]):
            with self.subTest(segment=index):
                self.assertRegex(
                    text.rstrip(),
                    r'[.!?]["\')\]]?$',
                    f"segment {index} ends mid-sentence: ...{text[-60:]!r}",
                )

    @unittest.expectedFailure
    def test_no_paragraph_break_inside_a_sentence(self):
        """Phase 3: a page break is not a paragraph break."""
        for text in segment_texts("page_continuation"):
            for part in text.split("\n\n"):
                part = part.strip()

                if not part:
                    continue

                with self.subTest(part=part[:40]):
                    self.assertRegex(
                        part,
                        r'[.!?:]["\')\]]?$',
                        f"paragraph ends mid-sentence: ...{part[-60:]!r}",
                    )

    @unittest.expectedFailure
    def test_wrapped_words_are_rejoined(self):
        """Phase 3: line-wrap hyphens are repaired, real compounds are not."""
        joined = " ".join(segment_texts("hyphenation"))

        self.assertNotRegex(
            joined,
            r"\w-\s",
            "a line-wrap hyphen survived into the narration",
        )

        for compound in ("well-known", "twenty-three", "self-evident"):
            with self.subTest(compound=compound):
                self.assertIn(compound.lower(), joined.lower())


class PageMappingTests(unittest.TestCase):
    @unittest.expectedFailure
    def test_every_source_page_is_reachable(self):
        """Phase 3: merging a short page must not hide it from navigation."""
        for name in ("short_page", "page_continuation"):
            with self.subTest(passage=name):
                passage = get_passage(name)
                dump = text_pipeline_dump(passage)

                self.assertEqual(
                    list(range(1, len(passage.pages) + 1)),
                    dump["pages_covered"],
                    "a source page has no segment to navigate to",
                )


class HeadingAndListTests(unittest.TestCase):
    def test_headings_are_not_glued_to_following_prose(self):
        """A heading must stay on its own line so a pause can be placed."""
        joined = "\n\n".join(segment_texts("headings"))

        self.assertNotRegex(
            joined,
            r"The Weather Station +For eleven years",
            "heading was joined to the body text on one line",
        )

    def test_list_items_stay_separate(self):
        joined = "\n\n".join(segment_texts("lists"))

        self.assertNotRegex(
            joined,
            r"case\. *2\. Remove",
            "numbered items were merged into one line",
        )


if __name__ == "__main__":
    unittest.main()
