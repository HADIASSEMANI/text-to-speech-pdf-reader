import os
import shutil
import sys
from pathlib import Path


APP_NAME = "BookTTSReader"


def is_frozen() -> bool:
    """True when running from a packaged build (PyInstaller sets this).

    False for ``python main.py``, which is how the development purge of the
    audio cache tells the two apart.
    """
    return getattr(sys, "frozen", False)


def user_data_dir() -> Path:
    """Writable per-user location. Keeps the database and cache out of the
    installation directory, which is read-only under Program Files.
    """
    home = Path.home()

    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", home))
        path = base / APP_NAME
    elif sys.platform == "darwin":
        path = home / "Library" / "Application Support" / APP_NAME
    else:
        xdg = os.environ.get("XDG_DATA_HOME", "").strip()
        base = Path(xdg) if xdg else (home / ".local" / "share")
        path = base / APP_NAME

    if sys.platform != "win32":
        legacy = home / APP_NAME
        if not path.exists() and legacy.exists():
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(legacy), str(path))
            except OSError:
                path = legacy

    path.mkdir(parents=True, exist_ok=True)

    return path


def cache_dir() -> Path:
    path = user_data_dir() / "cache"

    path.mkdir(parents=True, exist_ok=True)

    return path


def pasted_text_dir() -> Path:
    """App-managed source files created from the paste-text dialog."""
    path = user_data_dir() / "pasted-texts"

    path.mkdir(parents=True, exist_ok=True)

    return path


def database_path() -> Path:
    return user_data_dir() / "reader.db"


def resource_path(relative: str) -> Path:
    """Locate a bundled read-only asset. PyInstaller unpacks these under
    ``sys._MEIPASS`` and sets ``sys.frozen``.
    """
    if is_frozen():
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent.parent

    return base / relative
