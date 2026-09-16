import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from reader.progress import ProgressAnchor
from reader.text_source import extract_text, save_pasted_text


class PastedTextSourceTests(unittest.TestCase):
    def test_saves_exact_text_with_safe_unique_names(self):
        text = "First paragraph.\n\nSecond paragraph."

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            first = Path(save_pasted_text(text, 'Notes: chapter 1', target))
            second = Path(save_pasted_text(text, 'Notes: chapter 1', target))

            self.assertEqual(first.name, "Notes chapter 1.txt")
            self.assertEqual(second.name, "Notes chapter 1 (2).txt")
            self.assertEqual(first.read_text(encoding="utf-8"), text)

    def test_uses_first_nonempty_line_as_default_title(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(save_pasted_text("\n  A useful title  \nBody", directory=Path(directory)))

            self.assertEqual(path.name, "A useful title.txt")

    def test_rejects_empty_text(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "Paste some text"):
                save_pasted_text(" \n\t", directory=Path(directory))

    def test_plain_text_extraction_preserves_content(self):
        text = "Line one.\n\nLine two."

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.txt"
            path.write_text(text, encoding="utf-8")

            self.assertEqual(extract_text(str(path)), [{"page": 1, "text": text}])

    def test_pasted_text_uses_the_normal_book_preparation_pipeline(self):
        text = "First paragraph.\n\nSecond paragraph."

        with tempfile.TemporaryDirectory() as directory:
            path = save_pasted_text(text, "Pipeline test", Path(directory))
            statuses = []
            saved_book = SimpleNamespace(
                id=42,
                current_segment=0,
                playback_position=0.0,
                is_new=True,
                anchor=ProgressAnchor(),
            )

            with (
                patch(
                    "reader.book_loader.get_or_create_book",
                    return_value=saved_book,
                ),
                patch(
                    "reader.book_loader.KokoroTTS",
                    return_value="fake-tts",
                ),
            ):
                from reader.book_loader import prepare_book

                prepared = prepare_book(path, on_status=statuses.append)

            self.assertEqual(prepared.path, path)
            self.assertEqual(prepared.book_id, 42)
            self.assertEqual(prepared.tts, "fake-tts")
            self.assertEqual([segment.text for segment in prepared.segments], [text])
            self.assertIn("Reading pasted text...", statuses)


if __name__ == "__main__":
    unittest.main()
