import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from PySide6.QtCore import QCoreApplication, QEvent, QSettings
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QSignalSpy

from reader.cache import audio_cache_size, clear_audio_cache
from reader.models import Segment, TextCue
from reader.viewmodel.app_viewmodel import AppViewModel


class ClearAudioCacheTests(unittest.TestCase):
    @staticmethod
    def _write_pair(directory: Path, stem: str, wav_bytes: int = 10, json_bytes: int = 4):
        wav = directory / f"{stem}.wav"
        cue = directory / f"{stem}.json"
        wav.write_bytes(b"w" * wav_bytes)
        cue.write_bytes(b"j" * json_bytes)
        return wav, cue

    def test_removes_wav_and_cue_files_and_returns_bytes_freed(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            wav1, cue1 = self._write_pair(cache, "one", 10, 4)
            wav2, cue2 = self._write_pair(cache, "two", 20, 6)
            other = cache / "notes.txt"
            other.write_bytes(b"keep")

            with patch("reader.cache.CACHE_DIR", cache):
                self.assertEqual(40, audio_cache_size())
                freed = clear_audio_cache()
                self.assertEqual(0, audio_cache_size())

            self.assertEqual(40, freed)
            self.assertFalse(wav1.exists())
            self.assertFalse(cue1.exists())
            self.assertFalse(wav2.exists())
            self.assertFalse(cue2.exists())
            self.assertTrue(other.exists())

    def test_preserves_keep_paths_and_their_paired_files(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            keep_wav, keep_cue = self._write_pair(cache, "current", 12, 3)
            drop_wav, drop_cue = self._write_pair(cache, "other", 15, 5)

            with patch("reader.cache.CACHE_DIR", cache):
                freed = clear_audio_cache(keep=[keep_wav])
                remaining = audio_cache_size()

            self.assertEqual(20, freed)
            self.assertEqual(15, remaining)
            self.assertTrue(keep_wav.exists())
            self.assertTrue(keep_cue.exists())
            self.assertFalse(drop_wav.exists())
            self.assertFalse(drop_cue.exists())

    def test_skips_temporary_in_progress_files(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            wav, cue = self._write_pair(cache, "done", 10, 2)
            part_wav = cache / "inflight.part.wav"
            part_cue = cache / "inflight.part.json"
            part_wav.write_bytes(b"p" * 50)
            part_cue.write_bytes(b"q" * 10)

            with patch("reader.cache.CACHE_DIR", cache):
                self.assertEqual(12, audio_cache_size())
                freed = clear_audio_cache()
                self.assertEqual(0, audio_cache_size())

            self.assertEqual(12, freed)
            self.assertFalse(wav.exists())
            self.assertFalse(cue.exists())
            self.assertTrue(part_wav.exists())
            self.assertTrue(part_cue.exists())

    def test_undeletable_file_does_not_stop_remaining_deletions(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            locked_wav, locked_cue = self._write_pair(cache, "locked", 10, 4)
            free_wav, free_cue = self._write_pair(cache, "free", 20, 6)

            real_unlink = Path.unlink

            def flaky_unlink(path_self, *args, **kwargs):
                if path_self == locked_wav:
                    raise OSError("File is locked")
                return real_unlink(path_self, *args, **kwargs)

            with patch("reader.cache.CACHE_DIR", cache), patch.object(
                Path, "unlink", autospec=True, side_effect=flaky_unlink
            ):
                freed = clear_audio_cache()

            self.assertEqual(30, freed)
            self.assertTrue(locked_wav.exists())
            self.assertFalse(locked_cue.exists())
            self.assertFalse(free_wav.exists())
            self.assertFalse(free_cue.exists())

    def test_empty_or_missing_directory_returns_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            empty = Path(directory) / "empty"
            empty.mkdir()
            missing = Path(directory) / "missing"

            with patch("reader.cache.CACHE_DIR", empty):
                self.assertEqual(0, audio_cache_size())
                self.assertEqual(0, clear_audio_cache())

            with patch("reader.cache.CACHE_DIR", missing):
                self.assertEqual(0, audio_cache_size())
                self.assertEqual(0, clear_audio_cache())


class ViewModelClearCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.cache_dir = self.root / "cache"
        self.cache_dir.mkdir()
        self.settings_file = str(self.root / "settings.ini")

        self.settings_patch = patch(
            "reader.settings.QSettings",
            side_effect=lambda *args: QSettings(self.settings_file, QSettings.IniFormat),
        )
        self.cache_patch = patch("reader.cache.CACHE_DIR", self.cache_dir)
        self.books_patch = patch(
            "reader.viewmodel.book_list_model.get_recent_books",
            return_value=[],
        )

        self.settings_patch.start()
        self.cache_patch.start()
        self.books_patch.start()

        self.addCleanup(self.settings_patch.stop)
        self.addCleanup(self.cache_patch.stop)
        self.addCleanup(self.books_patch.stop)

        self.vm = None
        self.addCleanup(self._dispose_vm)

    def _dispose_vm(self):
        if self.vm is not None:
            self.vm.timer.stop()
            self.vm._narration_timer.stop()
            self.vm.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_clear_cache_updates_size_and_text_and_emits_signal(self):
        (self.cache_dir / "seg1.wav").write_bytes(b"a" * (2 * 1024 * 1024))
        (self.cache_dir / "seg1.json").write_bytes(b"c" * 512)

        self.vm = AppViewModel()
        self.vm.timer.stop()
        self.vm.showSettings()

        self.assertGreater(self.vm.cacheSizeBytes, 0)
        self.assertEqual("2.0 MB", self.vm.cacheSizeText)

        spy = QSignalSpy(self.vm.cacheSizeChanged)
        self.vm.clearCache()

        self.assertGreaterEqual(spy.count(), 1)
        self.assertEqual(0, self.vm.cacheSizeBytes)
        self.assertEqual("Empty", self.vm.cacheSizeText)

    def test_clear_cache_preserves_open_book_current_passage_and_resets_others(self):
        cur_wav = self.cache_dir / "cur.wav"
        cur_cue = self.cache_dir / "cur.json"
        next_wav = self.cache_dir / "next.wav"
        next_cue = self.cache_dir / "next.json"
        cur_wav.write_bytes(b"a" * 1024)
        cur_cue.write_bytes(b"c" * 256)
        next_wav.write_bytes(b"b" * 2048)
        next_cue.write_bytes(b"d" * 256)

        seg_cur = Segment(
            id=0,
            page=1,
            text="Current",
            cache_id="cur",
            audio_path=str(cur_wav),
            generated=True,
            cues=[TextCue("Current", 0.0, 1.0)],
        )
        seg_next = Segment(
            id=1,
            page=1,
            text="Next",
            cache_id="next",
            audio_path=str(next_wav),
            generated=True,
            cues=[TextCue("Next", 0.0, 1.0)],
        )

        self.vm = AppViewModel()
        self.vm.timer.stop()

        controller = Mock()
        controller.segments = [seg_cur, seg_next]
        controller.get_current_cache_paths.return_value = (cur_wav, cur_cue)
        self.vm.controller = controller

        self.vm.showSettings()
        self.assertEqual(1024 + 256 + 2048 + 256, self.vm.cacheSizeBytes)

        self.vm.clearCache()

        self.assertTrue(cur_wav.exists())
        self.assertTrue(cur_cue.exists())
        self.assertFalse(next_wav.exists())
        self.assertFalse(next_cue.exists())
        self.assertTrue(seg_cur.generated)
        self.assertEqual(1, len(seg_cur.cues))
        self.assertFalse(seg_next.generated)
        self.assertEqual([], seg_next.cues)
        self.assertEqual(1280, self.vm.cacheSizeBytes)
        self.assertEqual("1 KB", self.vm.cacheSizeText)


if __name__ == "__main__":
    unittest.main()
