"""Generated audio must appear in the cache whole, or not at all.

Synthesis can now outlive the book that asked for it, so a process exiting
mid-write would otherwise leave a truncated WAV that every later read of that
passage fails on.
"""

import tempfile
import unittest
from pathlib import Path

import soundfile as sf
import numpy as np

from reader.tts import KokoroTTS


class AtomicWriteTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

        self.root = Path(self.directory.name)

    def test_the_temporary_file_keeps_the_real_extension(self):
        """soundfile picks its format from the suffix, so ".part" alone fails."""
        target = self.root / "clip.wav"

        audio = np.zeros(2400, dtype="float32")

        KokoroTTS._write_atomically(
            target,
            lambda path: sf.write(path, audio, 24000),
        )

        self.assertTrue(target.exists())
        self.assertAlmostEqual(0.1, sf.info(target).duration, places=3)

    def test_a_failed_write_leaves_nothing_behind(self):
        target = self.root / "clip.wav"

        def explode(path: Path):
            path.write_bytes(b"partial")
            raise RuntimeError("interrupted")

        with self.assertRaises(RuntimeError):
            KokoroTTS._write_atomically(target, explode)

        self.assertFalse(target.exists())
        self.assertEqual([], list(self.root.iterdir()))

    def test_an_existing_entry_is_replaced_in_one_step(self):
        target = self.root / "clip.wav"
        target.write_bytes(b"old")

        KokoroTTS._write_atomically(
            target,
            lambda path: path.write_bytes(b"new"),
        )

        self.assertEqual(b"new", target.read_bytes())
        self.assertEqual([target], list(self.root.iterdir()))


if __name__ == "__main__":
    unittest.main()
