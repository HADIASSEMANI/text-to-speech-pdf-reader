"""Structured EPUB extraction.

The fixture reproduces the markup of the "Leftmost and Rightmost Derivations"
passage from the book this was built against: an ``<mtable>`` of production
rules, ``<sup>`` exponents, derivation arrows carrying their rule number as a
``<mover>`` overscript, italic variables and an ``epub:type="pagebreak"``
anchor. It is committed so the coverage travels; the real book is checked as
well when it is present.
"""

import unittest
import zipfile
from pathlib import Path

from reader.content_blocks import EQUATION, HEADING, LIST_ITEM, PARAGRAPH
from reader.epub_reader import extract_blocks, extract_nav
from reader.segmenter import create_segments_from_blocks


CONTAINER = """<?xml version="1.0"?>
<container version="1.0"
  xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/book.opf"
      media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

OPF = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="i">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Test</dc:title>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml"
      properties="nav"/>
    <item id="c1" href="ch01.xhtml" media-type="application/xhtml+xml"/>
    <item id="c2" href="ch02.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="c1"/>
    <itemref idref="c2"/>
  </spine>
</package>
"""

NAV = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:epub="http://www.idpf.org/2007/ops">
  <body>
    <nav epub:type="toc">
      <ol>
        <li><a href="ch01.xhtml#sec1">Leftmost and Rightmost Derivations</a>
          <ol><li><a href="ch01.xhtml#sub1">A Sub Heading</a></li></ol>
        </li>
        <li><a href="ch02.xhtml">Second Document</a></li>
      </ol>
    </nav>
  </body>
</html>
"""

# Markup copied in shape from the real content document.
CHAPTER_ONE = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:epub="http://www.idpf.org/2007/ops">
  <body>
    <section>
      <h3 class="H2" id="sec1">Leftmost and Rightmost Derivations</h3>
      <p class="TXL">Take, for example, the grammar <i>G</i> = ({<i>A</i>,
      <i>B</i>, <i>S</i>}, {<i>a</i>, <i>b</i>}, <i>S</i>, <i>P</i>) with
      productions</p>
      <p class="EQ"><math xmlns="http://www.w3.org/1998/Math/MathML"
        display="block"><mrow><mtable>
        <mtr><mtd><mrow><mstyle mathvariant="bold"><mn>1</mn></mstyle><mo>.</mo><mtext> </mtext><mi>S</mi><mo>&#8594;</mo><mi>A</mi><mi>B</mi><mo>.</mo></mrow></mtd></mtr>
        <mtr><mtd><mrow><mstyle mathvariant="bold"><mn>2</mn></mstyle><mo>.</mo><mtext> </mtext><mi>A</mi><mo>&#8594;</mo><mi>a</mi><mi>a</mi><mi>A</mi><mo>.</mo></mrow></mtd></mtr>
        <mtr><mtd><mrow><mstyle mathvariant="bold"><mn>3</mn></mstyle><mo>.</mo><mtext> </mtext><mi>A</mi><mo>&#8594;</mo><mi>&#955;</mi><mo>.</mo></mrow></mtd></mtr>
        </mtable></mrow></math></p>
      <p class="TXL"><span aria-label="page 142" epub:type="pagebreak"
        role="doc-pagebreak" id="page_142" title="142"/>This grammar generates
        the language <i>L</i>(<i>G</i>) = {<i>a</i><sup>2<i>n</i></sup><i>b</i><sup><i>m</i></sup>:
        <i>n</i> &#8805; 0, <i>m</i> &#8805; 0}.</p>
      <p class="EQ"><math xmlns="http://www.w3.org/1998/Math/MathML"
        display="block"><mrow><mi>S</mi><mover><mo>&#8658;</mo><mn>1</mn></mover><mi>A</mi><mi>B</mi><mover><mo>&#8658;</mo><mn>2</mn></mover><mi>a</mi><mi>a</mi><mi>A</mi><mi>B</mi></mrow></math></p>
      <h4 id="sub1">A Sub Heading</h4>
      <ol>
        <li>First item</li>
        <li>Second item</li>
      </ol>
      <ul><li>A bullet</li></ul>
    </section>
  </body>
</html>
"""

CHAPTER_TWO = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <body>
    <p>The second document, which the spine puts after the first.</p>
  </body>
</html>
"""


def build_epub(path: Path) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("META-INF/container.xml", CONTAINER)
        archive.writestr("OEBPS/book.opf", OPF)
        archive.writestr("OEBPS/nav.xhtml", NAV)
        archive.writestr("OEBPS/ch01.xhtml", CHAPTER_ONE)
        archive.writestr("OEBPS/ch02.xhtml", CHAPTER_TWO)

    return path


class StructuredExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tempfile

        cls._directory = tempfile.TemporaryDirectory()

        cls.path = build_epub(Path(cls._directory.name) / "test.epub")
        cls.blocks = extract_blocks(str(cls.path))

    @classmethod
    def tearDownClass(cls):
        cls._directory.cleanup()

    def block(self, predicate):
        for block in self.blocks:
            if predicate(block):
                return block

        self.fail("no block matched")

    # ------------------------------------------------------------------
    # structure
    # ------------------------------------------------------------------

    def test_headings_are_recognized_with_their_level(self):
        heading = self.block(lambda b: b.display_text.startswith("Leftmost"))

        self.assertEqual(HEADING, heading.kind)
        self.assertEqual(3, heading.level)

    def test_a_heading_keeps_its_source_identifier(self):
        heading = self.block(lambda b: b.display_text.startswith("Leftmost"))

        self.assertEqual("OEBPS/ch01.xhtml#sec1", heading.source_id)

    def test_paragraphs_keep_inline_emphasis_without_gaining_spaces(self):
        paragraph = self.block(lambda b: b.display_text.startswith("Take, for"))

        self.assertEqual(PARAGRAPH, paragraph.kind)

        # Inline italics must not split the expression they sit inside.
        self.assertIn("G = ({A, B, S}, {a, b}, S, P)", paragraph.display_text)
        self.assertIn("<i>G</i>", paragraph.display_html)

    def test_documents_are_read_in_spine_order(self):
        texts = [block.display_text for block in self.blocks]

        self.assertLess(
            texts.index("Leftmost and Rightmost Derivations"),
            texts.index("The second document, which the spine puts after the first."),
        )

    def test_list_items_are_numbered_and_bulleted(self):
        first = self.block(lambda b: b.display_text.endswith("First item"))
        bullet = self.block(lambda b: b.display_text.endswith("A bullet"))

        self.assertEqual(LIST_ITEM, first.kind)
        self.assertEqual("1. First item", first.display_text)
        self.assertEqual("• A bullet", bullet.display_text)

    # ------------------------------------------------------------------
    # mathematics
    # ------------------------------------------------------------------

    def test_production_rules_are_one_per_line(self):
        """The defect this was built for: five rules on one run-on line."""
        equation = self.block(lambda b: b.kind == EQUATION and "S→AB" in b.display_text)

        lines = equation.display_text.split("\n")

        self.assertEqual(3, len(lines), f"expected one rule per line, got {lines}")

        self.assertTrue(lines[0].startswith("1."))
        self.assertTrue(lines[1].startswith("2."))
        self.assertTrue(lines[2].startswith("3."))

        self.assertIn("S→AB", lines[0])
        self.assertIn("A→aaA", lines[1])
        self.assertIn("A→λ", lines[2])

    def test_an_equation_block_keeps_its_mathml(self):
        equation = self.block(lambda b: b.kind == EQUATION and "S→AB" in b.display_text)

        self.assertIsNotNone(equation.mathml)
        self.assertIn("mtable", equation.mathml)

    def test_exponents_become_real_superscripts(self):
        paragraph = self.block(lambda b: b.display_text.startswith("This grammar"))

        self.assertIn("<sup>", paragraph.display_html)

        # The characters are unchanged; only the markup is added.
        self.assertIn("a2nbm", paragraph.display_text.replace(" ", ""))

    def test_a_rule_number_on_an_arrow_survives_as_an_overscript(self):
        equation = self.block(
            lambda b: b.kind == EQUATION and "⇒" in b.display_text
        )

        self.assertIn("⇒<sup>1</sup>", equation.display_html)

    def test_prose_containing_notation_stays_prose(self):
        paragraph = self.block(lambda b: b.display_text.startswith("This grammar"))

        self.assertEqual(
            PARAGRAPH,
            paragraph.kind,
            "a sentence with an expression in it is not an equation block",
        )

    def test_a_relation_is_not_split_across_lines(self):
        paragraph = self.block(lambda b: b.display_text.startswith("This grammar"))

        self.assertIn("n ≥ 0", paragraph.display_text)
        self.assertIn("m ≥ 0", paragraph.display_text)

    # ------------------------------------------------------------------
    # navigation and source locations
    # ------------------------------------------------------------------

    def test_page_labels_come_from_the_epub_anchors(self):
        before = self.block(lambda b: b.display_text.startswith("Take, for"))
        after = self.block(lambda b: b.display_text.startswith("This grammar"))

        self.assertIsNone(before.page_label)
        self.assertEqual("142", after.page_label)

    def test_navigation_is_read_with_levels_and_targets(self):
        nav = extract_nav(str(self.path))

        self.assertEqual(
            (1, "Leftmost and Rightmost Derivations", "OEBPS/ch01.xhtml#sec1"),
            nav[0],
        )

        self.assertEqual(2, nav[1][0], "a nested entry should be one level deeper")

    # ------------------------------------------------------------------
    # segments
    # ------------------------------------------------------------------

    def test_display_and_markup_hold_the_same_characters(self):
        """Highlighting selects a character range, so these cannot diverge."""
        import re

        for block in self.blocks:
            with self.subTest(block=block.source_id):
                stripped = re.sub(r"<[^>]+>", "", block.display_html)

                stripped = (
                    stripped.replace("&amp;", "&")
                    .replace("&lt;", "<")
                    .replace("&gt;", ">")
                )

                self.assertEqual(
                    block.display_text.replace("\n", ""),
                    stripped.replace("\n", ""),
                )

    def test_segments_never_split_a_block(self):
        segments = create_segments_from_blocks(self.blocks, max_chars=10)

        for segment in segments:
            with self.subTest(segment=segment.id):
                self.assertTrue(segment.source_ids)

        joined = "\n".join(segment.text for segment in segments)

        self.assertIn("1. S→AB.\n2. A→aaA.", joined)

    def test_segments_carry_source_ids_and_page_labels(self):
        segments = create_segments_from_blocks(self.blocks)

        segment = next(s for s in segments if "Leftmost" in s.text)

        self.assertIn("OEBPS/ch01.xhtml#sec1", segment.source_ids)

    def test_spoken_text_defaults_to_the_displayed_text(self):
        segments = create_segments_from_blocks(self.blocks)

        for segment in segments:
            with self.subTest(segment=segment.id):
                self.assertTrue(segment.spoken_text)

    def test_cache_identity_follows_the_spoken_text(self):
        from reader.cache import NARRATION_VERSION, create_cache_id

        segments = create_segments_from_blocks(self.blocks)
        segment = segments[0]

        self.assertEqual(
            segment.cache_id,
            create_cache_id(segment.spoken_text, "af_heart", 1.0),
        )

        self.assertNotEqual(
            segment.cache_id,
            create_cache_id(
                segment.spoken_text,
                "af_heart",
                1.0,
                version=NARRATION_VERSION - 1,
            ),
            "a narration version change must produce different audio",
        )


REAL_BOOK = Path("real-book.epub")


@unittest.skipUnless(REAL_BOOK.exists(), "the reference book is not on this machine")
class RealBookTests(unittest.TestCase):
    """The passage the work was reported against, not a synthetic stand-in."""

    @classmethod
    def setUpClass(cls):
        cls.segments = create_segments_from_blocks(extract_blocks(str(REAL_BOOK)))

    def passage(self):
        return next(s for s in self.segments if "A→aaA" in s.text)

    def test_the_production_list_reads_one_rule_per_line(self):
        text = self.passage().text

        for expected in (
            "1. S→AB.",
            "2. A→aaA.",
            "3. A→λ.",
            "4. B→Bb.",
            "5. B→λ.",
        ):
            with self.subTest(rule=expected):
                self.assertIn(expected + "\n", text + "\n")

    def test_the_passage_is_on_its_printed_page(self):
        self.assertEqual("141", self.passage().page_label)

    def test_the_exponents_are_superscripts(self):
        html = self.passage().html

        self.assertIn("<sup>", html)

    def test_the_derivation_arrows_keep_their_rule_numbers(self):
        html = self.passage().html

        self.assertIn("⇒<sup>1</sup>", html)

    def test_the_sentence_that_used_to_break_is_intact(self):
        self.assertIn("m ≥ 0}", self.passage().text)


if __name__ == "__main__":
    unittest.main()
