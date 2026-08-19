import os
import sys
from pathlib import Path


APP_NAME = "BookTTSReader"


def user_data_dir() -> Path:
    """Writable per-user location. Keeps the database and cache out of the
    installation directory, which is read-only under Program Files.
    """
    base = Path(os.environ.get("LOCALAPPDATA", Path.home()))

    path = base / APP_NAME

    path.mkdir(parents=True, exist_ok=True)

    return path


def cache_dir() -> Path:
    path = user_data_dir() / "cache"

    path.mkdir(parents=True, exist_ok=True)

    return path


def database_path() -> Path:
    return user_data_dir() / "reader.db"


def resource_path(relative: str) -> Path:
    """Locate a bundled read-only asset. PyInstaller unpacks these under
    ``sys._MEIPASS`` and sets ``sys.frozen``.
    """
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent.parent

    return base / relative
