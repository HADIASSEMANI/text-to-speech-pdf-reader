from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Slot
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QMainWindow,
    QFileDialog,
    QMessageBox,
    QStackedWidget,
)

from reader.book_loader_worker import BookLoaderWorker
from reader.controller import ReaderController
from reader.progress import remove_book
from reader.settings import AppSettings

from reader.ui.library_page import LibraryPage
from reader.ui.loading_page import LoadingPage
from reader.ui.reader_page import ReaderPage
from reader.ui.settings_page import SettingsPage


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.settings = AppSettings()

        self.controller = None

        self.loader_thread = None
        self.loader_worker = None

        self.setWindowTitle("Book TTS Reader")

        self.resize(1100, 760)

        self._build_ui()
        self._connect_events()
        self._setup_shortcuts()
        self._start_timer()

        self.show_library()

    def _build_ui(self):
        self.pages = QStackedWidget()

        self.library_page = LibraryPage()
        self.reader_page = ReaderPage()
        self.settings_page = SettingsPage()
        self.loading_page = LoadingPage()

        self.pages.addWidget(self.library_page)
        self.pages.addWidget(self.reader_page)
        self.pages.addWidget(self.settings_page)
        self.pages.addWidget(self.loading_page)

        self.setCentralWidget(self.pages)

        self.settings_page.load_settings(self.settings)

        self.reader_page.set_reader_enabled(False)

    def _connect_events(self):
        self.library_page.open_document_requested.connect(self.open_document)
        self.library_page.book_requested.connect(self.open_book)

        self.reader_page.library_requested.connect(self.show_library)
        self.reader_page.page_requested.connect(self.go_to_page)
        self.reader_page.chapter_requested.connect(self.go_to_chapter)
        self.reader_page.text_seek_requested.connect(self.seek_to_text)

        controls = self.reader_page.player_controls

        controls.play_clicked.connect(self.toggle_play)
        controls.previous_clicked.connect(self.previous)
        controls.next_clicked.connect(self.next)
        controls.back_clicked.connect(self.skip_back)
        controls.forward_clicked.connect(self.skip_forward)
        controls.seek_requested.connect(self.seek_to)

        settings_page = self.settings_page

        settings_page.voice_input.currentTextChanged.connect(self.settings.set_voice)
        settings_page.speed_input.valueChanged.connect(self.settings.set_speed)

        settings_page.footnotes_input.toggled.connect(
            self.settings.set_read_footnotes
        )
        settings_page.captions_input.toggled.connect(self.settings.set_read_captions)
        settings_page.sidebars_input.toggled.connect(self.settings.set_read_sidebars)

    def _setup_shortcuts(self):
        self.play_shortcut = QShortcut(QKeySequence("Space"), self)
        self.play_shortcut.activated.connect(self._shortcut_toggle_play)

        self.next_shortcut = QShortcut(QKeySequence("Right"), self)
        self.next_shortcut.activated.connect(self._shortcut_next)

        self.previous_shortcut = QShortcut(QKeySequence("Left"), self)
        self.previous_shortcut.activated.connect(self._shortcut_previous)

        self.forward_shortcut = QShortcut(QKeySequence("Shift+Right"), self)
        self.forward_shortcut.activated.connect(self._shortcut_skip_forward)

        self.back_shortcut = QShortcut(QKeySequence("Shift+Left"), self)
        self.back_shortcut.activated.connect(self._shortcut_skip_back)

        self.open_shortcut = QShortcut(QKeySequence("Ctrl+O"), self)
        self.open_shortcut.activated.connect(self.open_document)

        self.page_shortcut = QShortcut(QKeySequence("Ctrl+L"), self)
        self.page_shortcut.activated.connect(self.focus_page_input)

    def _editing_text(self) -> bool:
        focus_widget = self.focusWidget()

        return focus_widget is self.reader_page.page_input

    def _shortcut_toggle_play(self):
        if self._editing_text():
            return

        self.toggle_play()

    def _shortcut_next(self):
        if self._editing_text():
            return

        self.next()

    def _shortcut_previous(self):
        if self._editing_text():
            return

        self.previous()

    def _shortcut_skip_forward(self):
        if self._editing_text():
            return

        self.skip_forward()

    def _shortcut_skip_back(self):
        if self._editing_text():
            return

        self.skip_back()

    def focus_page_input(self):
        self.reader_page.page_input.setFocus()
        self.reader_page.page_input.selectAll()

    def _start_timer(self):
        self.timer = QTimer(self)

        self.timer.timeout.connect(self.tick)

        self.timer.start(100)

    def show_library(self):
        if self.controller is not None:
            self.controller.shutdown()
            self.controller = None

        self.reader_page.set_reader_enabled(False)
        self.reader_page.clear()

        self.library_page.refresh()

        self.pages.setCurrentWidget(self.library_page)

    def open_document(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Book",
            "",
            (
                "Supported Books (*.pdf *.epub);;"
                "PDF Files (*.pdf);;"
                "EPUB Files (*.epub)"
            ),
        )

        if not path:
            return

        self.open_book(path)

    def open_book(self, path: str):
        # A load already in flight owns the loading page; ignore the new request
        # rather than leaving two workers racing for one controller slot.
        if self.loader_thread is not None and self.loader_thread.isRunning():
            return

        if not Path(path).exists():
            QMessageBox.warning(
                self,
                "Book not found",
                f"This file is no longer available:\n{path}",
            )

            remove_book(path)

            self.show_library()

            return

        if self.controller is not None:
            self.controller.shutdown()
            self.controller = None

        self.loading_page.set_status("Preparing book...")

        self.pages.setCurrentWidget(self.loading_page)

        self._start_book_loader(path)

    def _start_book_loader(self, path: str):
        if self.loader_thread is not None and self.loader_thread.isRunning():
            return

        self.loader_thread = QThread(self)
        self.loader_worker = BookLoaderWorker(
            path,
            voice=self.settings.get_voice(),
            speed=self.settings.get_speed(),
            read_footnotes=self.settings.get_read_footnotes(),
            read_captions=self.settings.get_read_captions(),
            read_sidebars=self.settings.get_read_sidebars(),
        )

        self.loader_worker.moveToThread(self.loader_thread)

        self.loader_thread.started.connect(self.loader_worker.run)

        self.loader_worker.status_changed.connect(self.loading_page.set_status)

        self.loader_worker.finished.connect(self._book_loaded)

        self.loader_worker.failed.connect(self._book_load_failed)

        self.loader_worker.finished.connect(self.loader_thread.quit)
        self.loader_worker.failed.connect(self.loader_thread.quit)

        self.loader_thread.finished.connect(self.loader_worker.deleteLater)
        self.loader_thread.finished.connect(self.loader_thread.deleteLater)
        self.loader_thread.finished.connect(self._loader_finished)

        self.loader_thread.start()

    def _loader_finished(self):
        self.loader_thread = None
        self.loader_worker = None

    @Slot(object)
    def _book_loaded(self, prepared_book):
        # This slot belongs to MainWindow, so Qt queues it onto the GUI thread.
        # ReaderController constructs AudioPlayer and initializes pygame here.
        try:
            controller = ReaderController(
                segments=prepared_book.segments,
                tts=prepared_book.tts,
                book_id=prepared_book.book_id,
                start_index=prepared_book.start_index,
                preload_count=2,
                chapters=prepared_book.chapters,
            )
        except Exception as error:
            self._book_load_failed(str(error))
            return

        self.controller = controller

        max_page = max(segment.page for segment in controller.segments)

        self.reader_page.set_book(Path(prepared_book.path).stem, max_page)
        self.reader_page.set_chapters(controller.chapters)
        self.reader_page.set_reader_enabled(True)

        self.pages.setCurrentWidget(self.reader_page)

        self.update_reader()

        self.library_page.refresh()

    def _book_load_failed(self, error: str):
        QMessageBox.critical(self, "Unable to open book", error)

        self.show_library()

    def update_reader(self):
        if self.controller is None:
            return

        segment = self.controller.get_current_segment()

        if segment is None:
            return

        self.reader_page.show_segment(
            segment,
            self.controller.get_current_index(),
            len(self.controller.segments),
        )

        chapter_index = self.controller.get_current_chapter_index()

        if chapter_index is not None:
            self.reader_page.set_current_chapter(chapter_index)

        self._update_play_state()

    def toggle_play(self):
        if self.controller is None:
            return

        if not self.controller.running:
            self.controller.start()
        else:
            self.controller.toggle_pause()

        segment = self.controller.get_current_segment()

        if segment is not None:
            # Starting playback generates audio or loads cached cues. Refresh
            # offsets now so highlighting does not wait for a segment change.
            self.reader_page.refresh_highlight_offsets(segment)

        self._update_play_state()

    def previous(self):
        if self.controller is None:
            return

        self.controller.previous()

        self.update_reader()

    def next(self):
        if self.controller is None:
            return

        self.controller.next()

        self.update_reader()

    def skip_back(self):
        if self.controller is None:
            return

        self.controller.seek_relative(-15)

    def skip_forward(self):
        if self.controller is None:
            return

        self.controller.seek_relative(15)

    def seek_to(self, seconds: float):
        if self.controller is None:
            return

        self.controller.seek_to(seconds)

    def seek_to_text(self, seconds: float):
        if self.controller is None:
            return

        self.controller.seek_and_play(seconds)

        self.update_reader()

    def go_to_page(self, page: int):
        if self.controller is None:
            return

        actual_page = self.controller.go_to_page(page)

        if actual_page is None:
            return

        self.update_reader()
        self.reader_page.set_page_value(actual_page)

    def go_to_chapter(self, chapter_index: int):
        if self.controller is None:
            return

        if self.controller.go_to_chapter(chapter_index):
            self.update_reader()

    def tick(self):
        if self.controller is None:
            return

        previous_index = self.controller.get_current_index()

        self.controller.tick()

        current_index = self.controller.get_current_index()

        if current_index != previous_index:
            self.update_reader()

        cue = self.controller.get_current_cue()

        self.reader_page.highlight_cue(cue)

        player = self.controller.player

        self.reader_page.player_controls.set_timing(
            player.get_playback_position(),
            player.get_duration(),
        )

        self._update_play_state()

    def _update_play_state(self):
        if self.controller is None:
            return

        playing = self.controller.running and not self.controller.player.is_paused

        self.reader_page.player_controls.set_playing(playing)

    def closeEvent(self, event):
        self.timer.stop()

        if self.loader_thread is not None and self.loader_thread.isRunning():
            self.loader_thread.quit()
            self.loader_thread.wait()

        if self.controller is not None:
            self.controller.shutdown()

        event.accept()
