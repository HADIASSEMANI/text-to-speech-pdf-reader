import time
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
        self.pending_book_path = None

        self.audio_future = None
        self.audio_ready_action = None
        self.audio_segment_index = None

        self.returning_to_library = False
        self.library_return_started = 0.0

        self.choosing_document = False

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
        self.library_page.delete_book_requested.connect(self.delete_library_book)

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
        self.open_shortcut.setAutoRepeat(False)
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
            self.controller.running = False
            self.controller.player.stop()

            self.returning_to_library = True
            self.library_return_started = time.monotonic()

            self.loading_page.set_title("Returning to library...")
            self.loading_page.set_status("Finishing background audio work...")
            self.loading_page.set_progress(0)
            self.pages.setCurrentWidget(self.loading_page)
            return

        self._display_library()

    def _finish_show_library(self):
        if self.controller is not None:
            self.controller.shutdown()
            self.controller = None

        self._display_library()

    def _poll_library_return(self) -> bool:
        if not self.returning_to_library or self.controller is None:
            return False

        generating_indexes = [
            index
            for index, segment in enumerate(self.controller.segments)
            if segment.id in self.controller.generating
        ]

        if generating_indexes:
            progress = sum(
                self.controller.get_generation_progress(index)
                for index in generating_indexes
            ) // len(generating_indexes)

            self.loading_page.set_progress(progress)
            return True

        # Keep the transition visible briefly even when there is no pending
        # generation, so returning to the library reads as a deliberate state.
        if time.monotonic() - self.library_return_started < 0.35:
            self.loading_page.set_progress(90)
            return True

        self.loading_page.set_progress(100)
        self.returning_to_library = False
        self._finish_show_library()

        return True

    def _display_library(self):

        self.reader_page.set_reader_enabled(False)
        self.reader_page.clear()

        self.library_page.refresh()

        self.pages.setCurrentWidget(self.library_page)

    def open_document(self):
        if self.choosing_document:
            # Holding the shortcut or a second activation while the picker is
            # open would stack a second dialog behind the first.
            return

        self.choosing_document = True

        try:
            path = self._choose_document_path()
        finally:
            self.choosing_document = False

        if not path:
            return

        self.open_book(path)

    def _choose_document_path(self) -> str:
        """Ask for a book with the native platform file picker."""
        dialog = QFileDialog(self, "Open Book")

        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, False)
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)

        dialog.setNameFilters(
            [
                "Supported Books (*.pdf *.epub)",
                "PDF Files (*.pdf)",
                "EPUB Files (*.epub)",
            ]
        )

        if not dialog.exec():
            return ""

        selected = dialog.selectedFiles()

        return selected[0] if selected else ""

    def delete_library_book(self, path: str, title: str):
        answer = QMessageBox.question(
            self,
            "Remove book",
            f'Remove "{title}" from your library?\n\n'
            "The original book file will not be deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        remove_book(path)
        self.library_page.refresh()

    def open_book(self, path: str):
        # The worker thread can remain alive briefly after its result has been
        # displayed. Preserve a selection made during that shutdown window so
        # the user never has to choose the same file a second time.
        if self.loader_thread is not None and self.loader_thread.isRunning():
            self.pending_book_path = path
            self.loading_page.set_title("Opening book...")
            self.loading_page.set_status("Finishing the previous book...")
            self.loading_page.set_progress(0)
            self.pages.setCurrentWidget(self.loading_page)
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
        self.loading_page.set_title("Loading book...")
        self.loading_page.set_progress(0)

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
        self.loader_worker.progress_changed.connect(self.loading_page.set_progress)

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

        pending_path = self.pending_book_path
        self.pending_book_path = None

        if pending_path is not None:
            QTimer.singleShot(0, lambda path=pending_path: self.open_book(path))

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
        self.loading_page.set_progress(100)

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

        self.reader_page.set_current_chapter(chapter_index)

        self._update_play_state()

    def toggle_play(self):
        if self.controller is None:
            return

        if not self.controller.running:
            self._run_when_audio_ready(
                self.controller.get_current_index(),
                self.controller.start,
            )
            return
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

        target_index = self.controller.get_current_index() - 1

        if target_index < 0:
            return

        self._run_when_audio_ready(target_index, self.controller.previous)

    def next(self):
        if self.controller is None:
            return

        target_index = self.controller.get_current_index() + 1

        if target_index >= len(self.controller.segments):
            return

        self._run_when_audio_ready(target_index, self.controller.next)

    def _run_when_audio_ready(self, segment_index: int, action):
        if self.controller is None or self.audio_future is not None:
            return

        future = self.controller.prepare_segment_audio(segment_index)

        if future is None:
            action()
            self.pages.setCurrentWidget(self.reader_page)
            self.update_reader()
            return

        self.audio_future = future
        self.audio_ready_action = action
        self.audio_segment_index = segment_index

        self.loading_page.set_title("Preparing audio...")
        self.loading_page.set_status(
            f"Generating segment {segment_index + 1} "
            f"of {len(self.controller.segments)}..."
        )
        self.loading_page.set_progress(0)
        self.pages.setCurrentWidget(self.loading_page)

    def _poll_audio_generation(self) -> bool:
        if self.audio_future is None:
            return False

        if not self.audio_future.done():
            if self.controller is not None and self.audio_segment_index is not None:
                self.loading_page.set_progress(
                    self.controller.get_generation_progress(
                        self.audio_segment_index
                    )
                )
            return True

        future = self.audio_future
        action = self.audio_ready_action

        self.audio_future = None
        self.audio_ready_action = None
        self.audio_segment_index = None
        self.loading_page.set_progress(100)

        try:
            future.result()
        except Exception as error:
            if self.controller is not None:
                self.controller.running = False

            self.pages.setCurrentWidget(self.reader_page)
            QMessageBox.critical(self, "Unable to generate audio", str(error))
            self.update_reader()
            return True

        self.pages.setCurrentWidget(self.reader_page)

        if action is not None:
            action()

        self.update_reader()

        return True

    def _poll_pending_playback(self):
        """Show generation progress while the controller waits for its audio.

        `play_current` no longer blocks, so a cache miss surfaces here as a
        progress screen rather than as a frozen window.
        """
        index = self.controller.get_current_index()

        if self.pages.currentWidget() is not self.loading_page:
            self.loading_page.set_title("Preparing audio...")
            self.loading_page.set_status(
                f"Generating segment {index + 1} "
                f"of {len(self.controller.segments)}..."
            )

        self.loading_page.set_progress(
            self.controller.get_generation_progress(index)
        )

        self.controller.tick()

        if self.controller.awaiting_audio:
            return

        error = self.controller.take_generation_error()

        self.pages.setCurrentWidget(self.reader_page)
        self.update_reader()

        if error is not None:
            QMessageBox.critical(self, "Unable to generate audio", error)

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

        if self._poll_library_return():
            return

        if self._poll_audio_generation():
            return

        if self.controller.awaiting_audio and self.controller.running:
            self._poll_pending_playback()
            return

        previous_index = self.controller.get_current_index()

        player = self.controller.player

        if (
            self.controller.running
            and not player.is_paused
            and not player.is_playing()
            and previous_index < len(self.controller.segments) - 1
        ):
            self._run_when_audio_ready(
                previous_index + 1,
                self.controller.tick,
            )

            return

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
