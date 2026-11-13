"""Offscreen regression coverage for platform UI, focus and reader sizing."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from PySide6.QtCore import (QCoreApplication, QEvent, QMetaObject, QObject,
                            QSettings, Qt, QUrl, qInstallMessageHandler)
from PySide6.QtGui import QAccessible, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlProperty
from PySide6.QtQuick import QQuickItem  # Register item bindings for geometry/focus.
from PySide6.QtTest import QSignalSpy, QTest

from reader.paths import resource_path
from reader.settings import AppSettings
from tests.test_remove_dialog import settle


class UiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings_file = str(Path(self.directory.name) / "settings.ini")
        self.settings_patch = patch(
            "reader.settings.QSettings",
            side_effect=lambda *args: QSettings(self.settings_file, QSettings.IniFormat),
        )
        self.settings_patch.start()
        self.addCleanup(self.settings_patch.stop)
        self.engine = None
        self.vm = None
        self.addCleanup(self.dispose)

    def dispose(self):
        if self.engine is not None:
            for root in self.engine.rootObjects():
                root.close()
            self.engine.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        if self.vm is not None:
            self.vm.timer.stop()
            self.vm._narration_timer.stop()
            self.vm.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def view_model(self):
        from reader.viewmodel.app_viewmodel import AppViewModel
        with patch("reader.viewmodel.book_list_model.get_recent_books", return_value=[]):
            self.vm = AppViewModel()
        self.vm.timer.stop()
        return self.vm

    def load(self, content, properties=""):
        self.engine = QQmlApplicationEngine()
        qml_dir = resource_path("qml")
        self.engine.addImportPath(str(qml_dir))
        if self.vm is not None:
            self.engine.rootContext().setContextProperty("vm", self.vm)
        qml_url = QUrl.fromLocalFile(str(qml_dir)).toString()
        source = f'''import QtQuick
import QtQuick.Controls
import "{qml_url}"
ApplicationWindow {{
    width: 420; height: 460; visible: true
    {properties}
    {content}
}}'''
        self.engine.loadData(source.encode(), QUrl("file:///tmp/booktts-ui-test.qml"))
        self.assertTrue(self.engine.rootObjects(), "QML harness failed to load")
        self.window = self.engine.rootObjects()[0]
        self.window.requestActivate()
        settle()
        return self.window

    def key(self, key):
        QTest.keyClick(self.window, key)
        settle()


class PlatformUiTests(UiTestCase):
    def test_shortcut_labels_for_mac_and_windows(self):
        window = self.load("", '''
property string platform: "windows"
property string openLabel: Theme.shortcutLabel("O", platform)
property string pageLabel: Theme.shortcutLabel("L", platform)
property string themeFont: Theme.fontFamily
''')
        self.assertEqual("Ctrl O", window.property("openLabel"))
        self.assertEqual("Ctrl L", window.property("pageLabel"))
        window.setProperty("platform", "osx")
        self.assertEqual("⌘ O", window.property("openLabel"))
        self.assertEqual("⌘ L", window.property("pageLabel"))
        if sys.platform == "darwin":
            self.assertEqual(self.app.font().family(), window.property("themeFont"))

    def test_style_selection_preserves_windows(self):
        import main
        for platform, style, fallback in [
            ("win32", "FluentWinUI3", "Universal"),
            ("darwin", "Fusion", "Basic"),
        ]:
            with self.subTest(platform=platform), patch.object(main.sys, "platform", platform), \
                    patch.object(main, "QQuickStyle") as quick_style, \
                    patch.dict(os.environ, {}, clear=True):
                main._apply_style()
                quick_style.setStyle.assert_called_once_with(style)
                quick_style.setFallbackStyle.assert_called_once_with(fallback)
                if platform == "win32":
                    self.assertEqual("Dark", os.environ["QT_QUICK_CONTROLS_UNIVERSAL_THEME"])
                    self.assertEqual("#6695ff", os.environ["QT_QUICK_CONTROLS_UNIVERSAL_ACCENT"])

    def test_main_loads_with_production_style_without_qml_warnings(self):
        result = subprocess.run(
            [sys.executable, "-m", "tests.test_ui_accessibility", "--smoke"],
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "SDL_AUDIODRIVER": "dummy"},
            capture_output=True, text=True, timeout=90,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        report = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual([], report["qml_warnings"])
        unexpected = [
            message for message in report["qt_warnings"]
            if not message.startswith((
                "Populating font family aliases took",
                "QFontDatabase: Cannot find font directory",
            ))
        ]
        self.assertEqual([], unexpected)
        self.assertEqual([], report["unnamed_controls"])
        self.assertEqual([], report["geometry_issues"])


class BookCardTests(UiTestCase):
    def setUp(self):
        super().setUp()
        self.load('''
Button { id: start; objectName: "start"; text: "Start"
    Component.onCompleted: forceActiveFocus() }
BookCard { id: card; objectName: "card"; x: 20; y: 60; width: 380; height: 124
    title: "A book"; subtitle: "Page 8 of 20 · 40%"
    onOpened: windowOpens += 1
    onDeleted: windowDeletes += 1
}
Button { objectName: "end"; y: 200; text: "End" }
''', "property int windowOpens: 0; property int windowDeletes: 0")
        self.card = self.window.findChild(QObject, "card")
        self.remove = self.window.findChild(QObject, "removeBookButton")

    def test_tab_reaches_card_and_remove_then_next_control(self):
        self.key(Qt.Key_Tab)
        self.assertTrue(self.card.property("activeFocus"))
        self.assertEqual(2, QQmlProperty.read(self.card, "border.width"))
        self.assertEqual("#6695ff", QQmlProperty.read(self.card, "border.color").name())
        self.assertEqual(1.0, self.remove.property("opacity"))
        self.key(Qt.Key_Tab)
        self.assertTrue(self.remove.property("activeFocus"))
        self.assertEqual(1.0, self.remove.property("opacity"))
        self.key(Qt.Key_Tab)
        self.assertEqual("end", self.window.activeFocusItem().objectName())

    def test_enter_return_and_space_open_card_once(self):
        self.key(Qt.Key_Tab)
        for count, key in enumerate([Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space], 1):
            self.key(key)
            self.assertEqual(count, self.window.property("windowOpens"))
        self.assertEqual(0, self.window.property("windowDeletes"))

    def test_remove_is_keyboard_operable_without_opening_book(self):
        self.key(Qt.Key_Tab)
        self.key(Qt.Key_Tab)
        for count, key in enumerate([Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space], 1):
            self.key(key)
            self.assertEqual(count, self.window.property("windowDeletes"))
        self.assertEqual(0, self.window.property("windowOpens"))

    def test_pointer_remove_does_not_also_open_the_card(self):
        self.key(Qt.Key_Tab)
        point = self.remove.mapToScene(self.remove.boundingRect().center()).toPoint()
        QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, point)
        settle()
        self.assertEqual(1, self.window.property("windowDeletes"))
        self.assertEqual(0, self.window.property("windowOpens"))

    def test_accessible_names_include_title_and_progress(self):
        accessible = QAccessible.queryAccessibleInterface(self.card)
        self.assertIsNotNone(accessible)
        self.assertEqual(QAccessible.Button, accessible.role())
        for field in [QAccessible.Name, QAccessible.Description]:
            self.assertIn("A book", accessible.text(field))
            self.assertIn("40%", accessible.text(field))
        remove = QAccessible.queryAccessibleInterface(self.remove)
        self.assertEqual(QAccessible.Button, remove.role())
        self.assertEqual("Remove A book from the library", remove.text(QAccessible.Name))
        self.card.setProperty("title", "Another book")
        self.card.setProperty("subtitle", "Page 20 of 20 · 100%")
        self.assertIn("Another book", accessible.text(QAccessible.Name))
        self.assertIn("100%", accessible.text(QAccessible.Name))


class LibraryFocusTests(UiTestCase):
    def test_tab_scrolls_cards_into_view_in_the_real_grid(self):
        from reader.progress import BookProgress
        vm = self.view_model()
        book = Path(self.directory.name) / "book.txt"
        book.write_text("Book contents.")
        vm.books._books = [BookProgress(index, str(book), f"Book {index}", index, 0)
                           for index in range(8)]
        self.load('LibraryPage { anchors.fill: parent; shown: true }')
        actions = [item for item in self.window.findChildren(QObject)
                   if item.property("text") == "Open Book"
                   and "Button" in item.metaObject().className()]
        self.assertEqual(1, len(actions))
        QMetaObject.invokeMethod(actions[0], "forceActiveFocus")
        for index in range(4):
            self.key(Qt.Key_Tab)
            card = self.window.activeFocusItem()
            self.assertEqual(f"Book {index}", card.property("title"))
            position = card.mapToScene(card.boundingRect().topLeft())
            self.assertGreaterEqual(position.y(), 0)
            self.assertLessEqual(position.y() + card.height(), self.window.height())
            self.key(Qt.Key_Tab)
            self.assertEqual("removeBookButton", self.window.activeFocusItem().objectName())


class ReaderTextSizeTests(UiTestCase):
    def test_default_and_persistence_across_settings_instances(self):
        settings = AppSettings()
        self.assertEqual(18, settings.get_text_size())
        settings.set_text_size(24)
        settings.settings.sync()
        self.assertEqual(24, AppSettings().get_text_size())

    def test_setting_clamps_both_writes_and_stored_values(self):
        settings = AppSettings()
        for incoming, expected in [(0, 14), (14, 14), (32, 32), (99, 32), ("invalid", 18)]:
            with self.subTest(incoming=incoming):
                settings.set_text_size(incoming)
                self.assertEqual(expected, settings.get_text_size())
                self.assertEqual(expected, int(settings.settings.value("reader/text_size")))
                settings.settings.setValue("reader/text_size", incoming)
                self.assertEqual(expected, AppSettings().get_text_size())

    def test_view_model_property_notify_and_content_invariance(self):
        vm = self.view_model()
        vm._segment_text = "A passage.\nSecond line."
        vm._segment_html = "<p>A passage.</p><p>Second line.</p>"
        vm._highlight_start, vm._highlight_end = 2, 9
        notify = QSignalSpy(vm.textSizeChanged)
        segment = QSignalSpy(vm.segmentChanged)
        highlight = QSignalSpy(vm.highlightChanged)
        prop = vm.metaObject().property(vm.metaObject().indexOfProperty("textSize"))
        self.assertEqual("textSizeChanged", bytes(prop.notifySignal().name()).decode())
        vm.textSize = 24
        self.assertEqual(24, vm.textSize)
        self.assertEqual(24, AppSettings().get_text_size())
        self.assertEqual(1, notify.count())
        vm.textSize = 24
        self.assertEqual(1, notify.count())
        vm.textSize = 500
        self.assertEqual(32, vm.textSize)
        vm.textSize = -1
        self.assertEqual(14, vm.textSize)
        vm.textSize = -100
        self.assertEqual(3, notify.count())
        self.assertEqual(0, segment.count())
        self.assertEqual(0, highlight.count())
        self.assertEqual("A passage.\nSecond line.", vm.segmentText)
        self.assertEqual("<p>A passage.</p><p>Second line.</p>", vm.segmentHtml)
        self.assertEqual((2, 9), (vm.highlightStart, vm.highlightEnd))
        self.assertFalse(vm._narration_timer.isActive())

    def test_spinbox_is_keyboard_operable_and_fits_minimum_window(self):
        vm = self.view_model()
        self.load('SettingsPage { anchors.fill: parent; shown: true }')
        control = self.window.findChild(QObject, "textSizeControl")
        self.assertIsNotNone(control)
        QMetaObject.invokeMethod(control, "forceActiveFocus")
        self.key(Qt.Key_Up)
        self.assertEqual(19, vm.textSize)
        self.assertEqual(19, control.property("value"))
        self.key(Qt.Key_Down)
        self.assertEqual(18, vm.textSize)
        self.assertEqual("Text size", QAccessible.queryAccessibleInterface(control).text(QAccessible.Name))
        position = control.mapToScene(control.boundingRect().topLeft())
        self.assertGreaterEqual(position.x(), 0)
        self.assertLessEqual(position.x() + control.width(), self.window.width())
        self.assertGreaterEqual(position.y(), 0)
        self.assertLessEqual(position.y() + control.height(), self.window.height())

    def test_resize_preserves_plain_and_rich_selections_and_scrolls_highlight(self):
        vm = self.view_model()
        self.load('ReaderPage { anchors.fill: parent; shown: true }')
        body = self.window.findChild(QObject, "readerBody")
        # Find the enclosing ScrollView's Flickable through the visual parent.
        flick = body.parentItem()
        while flick is not None and flick.property("contentY") is None:
            flick = flick.parentItem()
        self.assertIsNotNone(flick)
        from reader.models import TextCue
        cue = TextCue("Target phrase.", 10, 11)
        controller = Mock()
        vm.controller = controller
        for rich in [False, True]:
            with self.subTest(rich=rich):
                text = "😀 Before.\n" + "Earlier words on many lines.\n" * 60 + "Target phrase.\nAfter."
                html = "" if not rich else "<p>" + text.replace("\n", "</p><p>") + "</p>"
                vm._segment_text, vm._segment_html = text, html
                vm.segmentChanged.emit()
                start = len(text[:text.index("Target")].encode("utf-16-le")) // 2
                vm._highlight_start, vm._highlight_end = start, start + len("Target phrase.")
                vm.highlightChanged.emit()
                settle()
                original = body.property("text")
                vm._set_cue_offsets([(cue, start, start + len("Target phrase."))])
                for size in [32, 14, 24]:
                    flick.setProperty("contentY", 0)
                    vm.textSize = size
                    settle()
                    self.assertEqual(size, body.property("font").pixelSize())
                    # Qt serializes RichText with its current font CSS. The
                    # source HTML and document characters must stay identical.
                    if not rich:
                        self.assertEqual(original, body.property("text"))
                    self.assertEqual("Target phrase.", body.property("selectedText"))
                    self.assertEqual(start, body.property("selectionStart"))
                    # A real Qt character rectangle must be inside the viewport.
                    from PySide6.QtCore import Q_ARG, Q_RETURN_ARG
                    rect = QMetaObject.invokeMethod(body, "positionToRectangle",
                        Q_RETURN_ARG("QRectF"), Q_ARG(int, start))
                    self.assertGreaterEqual(rect.y(), flick.property("contentY"))
                    self.assertLessEqual(rect.bottom(), flick.property("contentY") + flick.height())
                    # Hit-test the same character after reflow, through the
                    # real MouseArea and view-model slot.
                    with patch.object(vm, "_update_reader"):
                        point = body.mapToScene(rect.center()).toPoint()
                        QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, point)
                        controller.seek_and_play.assert_called_with(10)
                        controller.seek_and_play.reset_mock()
                QMetaObject.invokeMethod(body, "selectAll")
                self.assertEqual(text, body.property("selectedText").replace("\u2029", "\n").replace("\u2028", "\n"))
                self.assertEqual(html, vm.segmentHtml)


def smoke(capture_dir=None):
    """Use main's startup order in a fresh process, without real settings/data."""
    import main
    from reader.viewmodel.app_viewmodel import AppViewModel
    app = QGuiApplication([])
    main._apply_style()
    app.styleHints().setColorScheme(Qt.ColorScheme.Dark)
    warnings = []
    qml_warnings = []
    old_handler = qInstallMessageHandler(lambda kind, context, message: warnings.append(message))
    with tempfile.TemporaryDirectory() as root, \
            patch("reader.settings.QSettings", side_effect=lambda *args: QSettings(str(Path(root) / "settings.ini"), QSettings.IniFormat)), \
            patch("reader.viewmodel.book_list_model.get_recent_books", return_value=[]), \
            patch("reader.viewmodel.app_viewmodel.enforce_cache_limit"):
        vm = AppViewModel()
        vm.timer.stop()
        engine = QQmlApplicationEngine()
        engine.warnings.connect(lambda items: qml_warnings.extend(item.toString() for item in items))
        engine.rootContext().setContextProperty("vm", vm)
        engine.addImportPath(str(resource_path("qml")))
        engine.load(QUrl.fromLocalFile(str(resource_path("qml/Main.qml"))))
        if not engine.rootObjects():
            raise AssertionError(qml_warnings + warnings)
        window = engine.rootObjects()[0]
        window.setWidth(420)
        window.setHeight(460)
        settle()
        def capture(name):
            if capture_dir is not None:
                Path(capture_dir).mkdir(parents=True, exist_ok=True)
                window.grabWindow().save(str(Path(capture_dir) / (name + ".png")))
                for index, popup in enumerate(app.topLevelWindows()):
                    if popup is not window and popup.isVisible() and hasattr(popup, "grabWindow"):
                        popup.grabWindow().save(str(Path(capture_dir) / f"{name}-popup-{index}.png"))

        capture("library")
        unnamed = []
        geometry = []
        for name in ["pasteDialog", "shortcutsDialog", "errorDialog"]:
            dialog = window.findChild(QObject, name)
            if name == "errorDialog":
                dialog.setProperty("message", "A long error message. " * 500)
            QMetaObject.invokeMethod(dialog, "open")
            settle(220)
            capture(name)
            if name == "shortcutsDialog":
                def visual_items(item):
                    yield item
                    for child in item.childItems():
                        yield from visual_items(child)
                labels = [item.property("text") for item in visual_items(dialog.property("contentItem"))]
                modifier = "⌘ " if sys.platform == "darwin" else "Ctrl "
                if modifier + "O" not in labels or modifier + "L" not in labels:
                    raise AssertionError("shortcut dialog has incorrect platform labels")
            if dialog.property("width") > 420 or dialog.property("height") > 460:
                geometry.append(name)
            for item in dialog.findChildren(QObject):
                cls = item.metaObject().className()
                if any(kind in cls for kind in ["Button_QML", "TextField_QML", "TextArea_QML"]):
                    accessible = QAccessible.queryAccessibleInterface(item)
                    if accessible is not None and not accessible.text(QAccessible.Name):
                        unnamed.append(cls)
            QMetaObject.invokeMethod(dialog, "close")
            settle()
        # Exercise the QML file-picker fallback that originally rendered light.
        if sys.platform == "darwin":
            for scheme in [Qt.ColorScheme.Light, Qt.ColorScheme.Dark]:
                app.styleHints().setColorScheme(scheme)
                settle()
                if QQmlProperty.read(window, "palette.base").name() != "#12151a":
                    raise AssertionError("system appearance replaced the dark palette")
            # Open the picker with system light appearance to guard the
            # original light-dialog-inside-dark-app regression.
            app.styleHints().setColorScheme(Qt.ColorScheme.Light)
            dialog = window.findChild(QObject, "fileDialog")
            QMetaObject.invokeMethod(dialog, "open")
            settle(150)
            capture("fileDialog")
            # The popup must inherit the fixed palette even when the system
            # is light; inspect the actual fallback controls, not just Main.
            fallback_controls = [item for item in window.findChildren(QObject)
                                 if "FileDialog" in item.metaObject().className()
                                 and QQmlProperty.read(item, "palette.base") is not None]
            if not fallback_controls:
                raise AssertionError("QML file picker fallback was not created")
            for item in fallback_controls:
                if QQmlProperty.read(item, "palette.base").name() != "#12151a":
                    raise AssertionError("file picker did not inherit the dark palette")
            QMetaObject.invokeMethod(dialog, "close")
            app.styleHints().setColorScheme(Qt.ColorScheme.Dark)
        vm.showSettings()
        settle(220)
        capture("settings")
        vm.closeSettings()
        settle()
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        vm.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    qInstallMessageHandler(old_handler)
    print(json.dumps({"qml_warnings": qml_warnings, "qt_warnings": warnings,
                      "unnamed_controls": unnamed, "geometry_issues": geometry}))


if __name__ == "__main__":
    if "--smoke" in sys.argv:
        smoke(os.environ.get("BOOKTTS_UI_CAPTURE_DIR"))
    else:
        unittest.main()


class ClearCacheButtonTests(UiTestCase):
    def test_clear_cache_button_accessible_name_and_disabled_when_empty(self):
        empty_cache = Path(self.directory.name) / "empty_cache"
        empty_cache.mkdir()
        with patch("reader.cache.CACHE_DIR", empty_cache):
            vm = self.view_model()
            self.load('SettingsPage { anchors.fill: parent; shown: true }')
            button = self.window.findChild(QObject, "clearCacheButton")
            self.assertIsNotNone(button)
            accessible = QAccessible.queryAccessibleInterface(button)
            self.assertIsNotNone(accessible)
            self.assertEqual("Clear audio cache", accessible.text(QAccessible.Name))
            self.assertFalse(button.property("enabled"))
            self.assertEqual(0, vm.cacheSizeBytes)
            self.assertEqual("Empty", vm.cacheSizeText)
