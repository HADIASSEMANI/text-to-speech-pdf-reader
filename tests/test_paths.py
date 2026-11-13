import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reader.paths import APP_NAME, user_data_dir


class TestPaths(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name) / "home"
        self.home.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self._tmp.cleanup()

    def test_windows_uses_localappdata(self):
        local_app_data = self.home / "AppData" / "Local"
        with (
            patch("reader.paths.sys.platform", "win32"),
            patch("reader.paths.Path.home", return_value=self.home),
            patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}, clear=False),
        ):
            result = user_data_dir()
            self.assertEqual(result, local_app_data / APP_NAME)
            self.assertTrue(result.is_dir())

    def test_windows_does_not_migrate_legacy_folder(self):
        local_app_data = self.home / "AppData" / "Local"
        legacy = self.home / APP_NAME
        legacy.mkdir(parents=True)
        (legacy / "reader.db").write_text("win-legacy", encoding="utf-8")

        with (
            patch("reader.paths.sys.platform", "win32"),
            patch("reader.paths.Path.home", return_value=self.home),
            patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}, clear=False),
        ):
            result = user_data_dir()
            self.assertEqual(result, local_app_data / APP_NAME)
            self.assertTrue((legacy / "reader.db").exists())

    def test_macos_uses_application_support(self):
        with (
            patch("reader.paths.sys.platform", "darwin"),
            patch("reader.paths.Path.home", return_value=self.home),
        ):
            result = user_data_dir()
            expected = self.home / "Library" / "Application Support" / APP_NAME
            self.assertEqual(result, expected)
            self.assertTrue(result.is_dir())

    def test_linux_uses_default_local_share_when_xdg_unset(self):
        env = {k: v for k, v in os.environ.items() if k != "XDG_DATA_HOME"}
        with (
            patch("reader.paths.sys.platform", "linux"),
            patch("reader.paths.Path.home", return_value=self.home),
            patch.dict(os.environ, env, clear=True),
        ):
            result = user_data_dir()
            expected = self.home / ".local" / "share" / APP_NAME
            self.assertEqual(result, expected)
            self.assertTrue(result.is_dir())

    def test_linux_uses_xdg_data_home_when_set(self):
        xdg_dir = self.home / "custom_xdg"
        with (
            patch("reader.paths.sys.platform", "linux"),
            patch("reader.paths.Path.home", return_value=self.home),
            patch.dict(os.environ, {"XDG_DATA_HOME": str(xdg_dir)}, clear=False),
        ):
            result = user_data_dir()
            expected = xdg_dir / APP_NAME
            self.assertEqual(result, expected)
            self.assertTrue(result.is_dir())

    def test_migrates_legacy_folder_when_new_does_not_exist(self):
        legacy = self.home / APP_NAME
        legacy.mkdir(parents=True)
        marker = legacy / "reader.db"
        marker.write_text("saved-progress", encoding="utf-8")

        with (
            patch("reader.paths.sys.platform", "darwin"),
            patch("reader.paths.Path.home", return_value=self.home),
        ):
            result = user_data_dir()
            expected = self.home / "Library" / "Application Support" / APP_NAME
            self.assertEqual(result, expected)
            self.assertFalse(legacy.exists())
            self.assertEqual(
                (expected / "reader.db").read_text(encoding="utf-8"),
                "saved-progress",
            )

    def test_leaves_legacy_untouched_when_new_already_exists(self):
        legacy = self.home / APP_NAME
        legacy.mkdir(parents=True)
        (legacy / "reader.db").write_text("old-data", encoding="utf-8")

        new_dir = self.home / "Library" / "Application Support" / APP_NAME
        new_dir.mkdir(parents=True)
        (new_dir / "reader.db").write_text("new-data", encoding="utf-8")

        with (
            patch("reader.paths.sys.platform", "darwin"),
            patch("reader.paths.Path.home", return_value=self.home),
        ):
            result = user_data_dir()
            self.assertEqual(result, new_dir)
            self.assertTrue(legacy.exists())
            self.assertEqual(
                (legacy / "reader.db").read_text(encoding="utf-8"),
                "old-data",
            )
            self.assertEqual(
                (new_dir / "reader.db").read_text(encoding="utf-8"),
                "new-data",
            )

    def test_falls_back_to_legacy_if_move_fails(self):
        legacy = self.home / APP_NAME
        legacy.mkdir(parents=True)
        (legacy / "reader.db").write_text("keep-safe", encoding="utf-8")

        with (
            patch("reader.paths.sys.platform", "darwin"),
            patch("reader.paths.Path.home", return_value=self.home),
            patch("reader.paths.shutil.move", side_effect=OSError("disk error")),
        ):
            result = user_data_dir()
            self.assertEqual(result, legacy)
            self.assertEqual(
                (legacy / "reader.db").read_text(encoding="utf-8"),
                "keep-safe",
            )


if __name__ == "__main__":
    unittest.main()
