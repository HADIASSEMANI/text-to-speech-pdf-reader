"""Guard the narration pipeline against unreviewed change.

The goldens record what the reader narrates *today*, defects included. They
are not a statement that the current output is correct: they exist so that
when segmentation changes, the diff is visible and deliberate.

After reviewing an intended change::

    .venv/bin/python -m tools.baseline --text --update-golden
"""

import json
import tempfile
import unittest
from pathlib import Path

from tools.baseline import golden_path
from tools.passages import ALL_PASSAGES
from tools.pipeline_dump import build_pdf, pdf_pipeline_dump, text_pipeline_dump


class PipelineGoldenTests(unittest.TestCase):
    maxDiff = None

    def _compare(self, name: str, section: str, actual: dict):
        path = golden_path(name)

        self.assertTrue(
            path.exists(),
            f"No golden for {name!r}. Run: "
            "python -m tools.baseline --text --update-golden",
        )

        expected = json.loads(path.read_text(encoding="utf-8"))[section]

        if expected == actual:
            return

        self.fail(
            f"{section} narration changed for passage {name!r}.\n"
            f"segments: {expected['segment_count']} -> "
            f"{actual['segment_count']}\n"
            f"pages:    {expected['pages_covered']} -> "
            f"{actual['pages_covered']}\n"
            "Review the change, then re-record with:\n"
            "  python -m tools.baseline --text --update-golden"
        )

    def test_text_pipeline_matches_golden(self):
        for passage in ALL_PASSAGES:
            with self.subTest(passage=passage.name):
                self._compare(
                    passage.name,
                    "text",
                    text_pipeline_dump(passage),
                )

    def test_pdf_pipeline_matches_golden(self):
        with tempfile.TemporaryDirectory() as directory:
            for passage in ALL_PASSAGES:
                with self.subTest(passage=passage.name):
                    pdf_path = build_pdf(
                        passage,
                        Path(directory) / f"{passage.name}.pdf",
                    )

                    self._compare(
                        passage.name,
                        "pdf",
                        pdf_pipeline_dump(passage, pdf_path),
                    )


if __name__ == "__main__":
    unittest.main()
