import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reader.cache import clear_all_cache, enforce_cache_limit, mark_cache_used


class CacheCleanupTests(unittest.TestCase):
    @staticmethod
    def _write_entry(directory: Path, stem: str, timestamp: int):
        audio = directory / f"{stem}.wav"
        cues = directory / f"{stem}.json"
        audio.write_bytes(b"a" * 10)
        cues.write_bytes(b"c" * 2)
        os.utime(audio, (timestamp, timestamp))
        os.utime(cues, (timestamp, timestamp))
        return audio

    def test_removes_oldest_entry_and_preserves_protected_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            old = self._write_entry(cache, "old", 100)
            recent = self._write_entry(cache, "recent", 300)
            protected = self._write_entry(cache, "protected", 200)

            with patch("reader.cache.CACHE_DIR", cache):
                result = enforce_cache_limit(
                    24,
                    protected_audio_paths=[protected],
                )

            self.assertFalse(old.exists())
            self.assertFalse(old.with_suffix(".json").exists())
            self.assertTrue(recent.exists())
            self.assertTrue(protected.exists())
            self.assertEqual(result.removed_entries, 1)
            self.assertEqual(result.removed_bytes, 12)
            self.assertEqual(result.remaining_bytes, 24)

    def test_never_removes_protected_entry_to_reach_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            protected = self._write_entry(cache, "protected", 100)

            with patch("reader.cache.CACHE_DIR", cache):
                result = enforce_cache_limit(
                    1,
                    protected_audio_paths=[protected],
                )

            self.assertTrue(protected.exists())
            self.assertEqual(result.removed_entries, 0)
            self.assertEqual(result.remaining_bytes, 12)

    def test_marking_audio_used_does_not_create_a_missing_cue_file(self):
        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "audio.wav"
            audio.write_bytes(b"audio")

            mark_cache_used(str(audio))

            self.assertTrue(audio.exists())
            self.assertFalse(audio.with_suffix(".json").exists())


class ClearAllCacheTests(unittest.TestCase):
    def test_removes_every_generated_file_and_leaves_others(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            audio = cache / "abc.wav"
            cues = cache / "abc.json"
            unrelated = cache / "notes.txt"
            audio.write_bytes(b"a" * 10)
            cues.write_bytes(b"c" * 2)
            unrelated.write_bytes(b"keep")

            with patch("reader.cache.CACHE_DIR", cache):
                result = clear_all_cache()

            self.assertFalse(audio.exists())
            self.assertFalse(cues.exists())
            self.assertTrue(unrelated.exists())
            self.assertEqual(result.removed_entries, 1)
            self.assertEqual(result.removed_bytes, 12)

    def test_missing_cache_directory_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "gone"

            with patch("reader.cache.CACHE_DIR", missing):
                result = clear_all_cache()

            self.assertEqual(result.removed_entries, 0)
            self.assertEqual(result.removed_bytes, 0)


if __name__ == "__main__":
    unittest.main()
