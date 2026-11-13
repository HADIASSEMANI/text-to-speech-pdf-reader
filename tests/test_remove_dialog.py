"""Acceptance tests for the remove-book dialog.

Rendered offscreen against the real QML, because the requirements here are
about geometry, button order and focus, none of which can be checked by
reading the file.
"""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import (  # noqa: E402
    QEventLoop,
    QMetaObject,
    QObject,
    QTimer,
    QUrl,
)
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402

from reader.paths import resource_path  # noqa: E402


LONG_TITLE = (
    "A Deliberately Long Sample Book Title, Seventh Edition -- by First "
    "Author and Second Author -- 7th edition, Sample City (State), 2023 -- "
    "Sample Publisher -- isbn13 0000000000000 -- 0123456789abcdef0123456789ab "
    "-- sample library export"
)

HARNESS = """
import QtQuick
import QtQuick.Controls

import "{qml}"

ApplicationWindow {{
    id: window

    width: 1100
    height: 760

    visible: true

    property int removals: 0
    property string removedPath: ""

    property alias dialog: dialog

    Button {{
        id: libraryAction
        objectName: "libraryAction"
        text: "Open Book"
    }}

    RemoveBookDialog {{
        id: dialog

        objectName: "removeDialog"

        returnFocusTo: libraryAction

        onAccepted: {{
            window.removals += 1
            window.removedPath = path
        }}
    }}
}}
"""


def settle(milliseconds: int = 60):
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


class RemoveDialogTests(unittest.TestCase):
    application = None

    @classmethod
    def setUpClass(cls):
        cls.application = QGuiApplication.instance() or QGuiApplication([])

        cls.qml_dir = resource_path("qml")

    def setUp(self):
        import tempfile
        from pathlib import Path

        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

        source = Path(self.directory.name) / "harness.qml"
        source.write_text(
            HARNESS.format(qml=QUrl.fromLocalFile(str(self.qml_dir)).toString()),
            encoding="utf-8",
        )

        self.engine = QQmlApplicationEngine()
        self.engine.addImportPath(str(self.qml_dir))
        self.engine.load(QUrl.fromLocalFile(str(source)))

        roots = self.engine.rootObjects()

        self.assertTrue(roots, "the harness window failed to load")

        self.window = roots[0]

        # Reached by objectName: a QML-declared type has no Python binding,
        # so the property itself cannot be converted.
        self.dialog = self.window.findChild(QObject, "removeDialog")

        self.addCleanup(self.engine.deleteLater)

    # ------------------------------------------------------------------

    def open_dialog(self, title: str = "Some Book", path: str = "/tmp/book.epub"):
        self.dialog.setProperty("bookTitle", title)
        self.dialog.setProperty("path", path)
        QMetaObject.invokeMethod(self.dialog, "open")

        settle()

    def buttons(self):
        """Every Button in the dialog.

        Filtered on the type, because a Button owns a Label carrying the same
        text and matching on text alone finds the label first.
        """
        return [
            child
            for child in self.dialog.findChildren(QObject)
            if "Button" in child.metaObject().className()
        ]

    def button(self, label: str):
        for child in self.buttons():
            if child.property("text") == label:
                return child

        self.fail(f"no {label!r} button in the dialog")

    def resize(self, width: int, height: int):
        self.window.setProperty("width", width)
        self.window.setProperty("height", height)

        settle()

    # ------------------------------------------------------------------
    # size and placement
    # ------------------------------------------------------------------

    def test_preferred_width_and_centering(self):
        self.open_dialog(LONG_TITLE)

        self.assertEqual(480, self.dialog.property("width"))

        centre = self.dialog.property("x") + self.dialog.property("width") / 2

        self.assertAlmostEqual(
            self.window.property("width") / 2,
            centre,
            delta=1.0,
            msg="the dialog is not centred in the window",
        )

    def test_a_long_title_does_not_widen_the_dialog(self):
        self.open_dialog("Short")
        narrow_width = self.dialog.property("width")

        QMetaObject.invokeMethod(self.dialog, "close")
        settle()

        self.open_dialog(LONG_TITLE)

        self.assertEqual(
            narrow_width,
            self.dialog.property("width"),
            "the dialog grew to fit the title",
        )

    def test_it_clamps_to_a_narrow_window_with_side_margins(self):
        self.resize(420, 460)

        self.open_dialog(LONG_TITLE)

        self.assertEqual(
            420 - 48,
            self.dialog.property("width"),
            "expected 24 logical pixels of margin on each side",
        )

        self.assertEqual(24, self.dialog.property("x"))

    def test_it_fits_inside_a_short_window(self):
        self.resize(420, 460)

        self.open_dialog(LONG_TITLE)

        self.assertLessEqual(
            self.dialog.property("height"),
            460 - 48,
            "the dialog is taller than the window allows",
        )

    # ------------------------------------------------------------------
    # buttons
    # ------------------------------------------------------------------

    def test_yes_sits_to_the_left_of_no(self):
        self.open_dialog()

        yes = self.button("Yes")
        no = self.button("No")

        # Both sit in the same footer row, so their own x values are directly
        # comparable and no coordinate mapping is needed.
        self.assertIs(yes.parent(), no.parent(), "the buttons are not siblings")

        self.assertLess(
            yes.property("x"),
            no.property("x"),
            "Yes must be to the left of No",
        )

    def test_the_buttons_are_compact_and_equal(self):
        self.open_dialog()

        widths = {
            label: self.button(label).property("width")
            for label in ("Yes", "No")
        }

        self.assertEqual(
            widths["Yes"],
            widths["No"],
            "the buttons are not the same width",
        )

        for label, width in widths.items():
            with self.subTest(button=label):
                self.assertGreaterEqual(width, 88)
                self.assertLessEqual(width, 100)

    def test_the_buttons_are_right_aligned_not_stretched(self):
        self.open_dialog()

        yes = self.button("Yes")
        no = self.button("No")

        row = no.parent()
        row_width = row.property("width")

        trailing_gap = row_width - (no.property("x") + no.property("width"))

        self.assertLess(
            trailing_gap,
            2.0,
            "the buttons are not sitting against the right edge of the footer",
        )

        combined = yes.property("width") + no.property("width")

        self.assertLess(
            combined,
            row_width * 0.75,
            "the buttons are stretched across the dialog instead of compact",
        )

    def test_no_generated_footer_duplicates_the_buttons(self):
        self.open_dialog()

        labels = [
            child.property("text")
            for child in self.buttons()
            if child.property("text") in ("Yes", "No")
        ]

        self.assertEqual(
            sorted(labels),
            ["No", "Yes"],
            f"expected exactly one Yes and one No, found {labels}",
        )

    # ------------------------------------------------------------------
    # behaviour
    # ------------------------------------------------------------------

    def test_no_is_focused_when_the_dialog_opens(self):
        self.open_dialog()

        self.assertTrue(
            self.button("No").property("activeFocus"),
            "the safe option should have focus",
        )

    def test_yes_removes_the_book_exactly_once(self):
        self.open_dialog(path="/tmp/some-book.epub")

        # Activating the button itself, not calling accept() directly, so
        # the wiring between the two is what is under test.
        QMetaObject.invokeMethod(self.button("Yes"), "clicked")
        settle()

        self.assertEqual(1, self.window.property("removals"))
        self.assertEqual("/tmp/some-book.epub", self.window.property("removedPath"))
        self.assertFalse(self.dialog.property("visible"))

    def test_no_closes_without_removing(self):
        self.open_dialog()

        QMetaObject.invokeMethod(self.button("No"), "clicked")
        settle()

        self.assertEqual(0, self.window.property("removals"))
        self.assertFalse(self.dialog.property("visible"))

    def test_focus_returns_to_the_library_after_closing(self):
        self.open_dialog()

        QMetaObject.invokeMethod(self.dialog, "reject")
        settle()

        library_action = self.window.findChild(object, "libraryAction")

        self.assertTrue(
            library_action.property("activeFocus"),
            "focus was left nowhere useful after the dialog closed",
        )

    def test_escape_cancels(self):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtCore import QEvent

        self.open_dialog()

        press = QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)

        QGuiApplication.sendEvent(self.window, press)

        settle()

        self.assertFalse(
            self.dialog.property("visible"),
            "Escape did not close the dialog",
        )

        self.assertEqual(
            0,
            self.window.property("removals"),
            "Escape removed the book",
        )


class RemovalKeepsTheFileTests(unittest.TestCase):
    """Removing a library entry must never touch the book on disk."""

    def test_remove_book_only_drops_the_database_row(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)

        root = Path(directory.name)

        book = root / "Book.epub"
        book.write_bytes(b"not really an epub")

        with patch("reader.database.DATABASE_PATH", root / "reader.db"):
            from reader.database import initialize_database
            from reader.progress import get_or_create_book, get_recent_books, remove_book

            initialize_database()

            get_or_create_book(str(book))

            self.assertEqual(1, len(get_recent_books()))

            remove_book(str(book))

            self.assertEqual(0, len(get_recent_books()))
            self.assertTrue(book.exists(), "the source file was deleted")


if __name__ == "__main__":
    unittest.main()
