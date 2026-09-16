import os
import sys

# PyInstaller's windowed bootloader intentionally leaves these streams unset.
# Kokoro configures Loguru during import and requires a file-like stderr sink,
# so give GUI builds harmless null streams before importing the reader backend.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")

if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from reader.cache import clear_all_cache
from reader.database import initialize_database
from reader.paths import is_frozen, resource_path
from reader.viewmodel.app_viewmodel import AppViewModel


def _apply_style():
    """Pick the Windows 11 look, and fall back where it is not shipped.

    FluentWinUI3 only exists from Qt 6.8, and it does not implement every
    control, so the fallback draws a good part of what is on screen. Universal
    is the one that gives the buttons their shape here.

    It also keeps a theme of its own rather than following the colour scheme
    set in `main`, which is what drew the file dialog light inside a dark
    application. Naming the theme fixes that dialog without touching how any
    control is shaped.
    """
    os.environ.setdefault("QT_QUICK_CONTROLS_UNIVERSAL_THEME", "Dark")
    os.environ.setdefault("QT_QUICK_CONTROLS_UNIVERSAL_ACCENT", "#6695ff")

    QQuickStyle.setStyle("FluentWinUI3")
    QQuickStyle.setFallbackStyle("Universal")


def _purge_development_cache():
    """Drop generated audio on exit so a development run starts clean.

    Packaged builds keep their cache, which is the behaviour the reader is
    designed around. Set ``BOOKTTS_KEEP_CACHE=1`` to keep it here too, which
    is worth doing while debugging: regenerating a segment costs several
    seconds of synthesis.
    """
    if is_frozen():
        return

    if os.environ.get("BOOKTTS_KEEP_CACHE", "").strip().lower() in {"1", "true", "yes"}:
        return

    clear_all_cache()


def main():
    app = QGuiApplication(sys.argv)

    app.setOrganizationName("BookTTS")
    app.setApplicationName("BookTTSReader")
    app.setWindowIcon(QIcon(str(resource_path("assets/app-icon.png"))))

    initialize_database()

    _apply_style()

    try:
        app.styleHints().setColorScheme(Qt.ColorScheme.Dark)
    except AttributeError:
        # Older Qt follows the system scheme instead. The interface reads
        # correctly either way; only the chrome differs.
        pass

    engine = QQmlApplicationEngine()

    view_model = AppViewModel()

    engine.rootContext().setContextProperty("vm", view_model)

    qml_dir = resource_path("qml")

    engine.addImportPath(str(qml_dir))
    engine.load(QUrl.fromLocalFile(str(qml_dir / "Main.qml")))

    if not engine.rootObjects():
        return 1

    # The window is gone by the time this runs, so the controller shuts down
    # here rather than in a closing handler.
    app.aboutToQuit.connect(view_model.shutdown)

    # Connected second, and Qt runs slots in connection order, so the player
    # has already released its files by the time the cache is purged.
    app.aboutToQuit.connect(_purge_development_cache)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
