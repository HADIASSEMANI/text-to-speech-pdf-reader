import time
from pathlib import Path

from PySide6.QtCore import (
    Property,
    QObject,
    QThread,
    QTimer,
    QUrl,
    Signal,
    Slot,
)

from reader.book_loader_worker import BookLoaderWorker
from reader.cache import enforce_cache_limit
from reader.controller import ReaderController
from reader.progress import remove_book
from reader.settings import AppSettings
from reader.text_source import save_pasted_text
from reader.viewmodel.book_list_model import BookListModel


class AppViewModel(QObject):
    """Everything the QML shell binds to.

    The widget window polled the controller ten times a second and pushed the
    result straight into widgets. The same tick lives here, but it writes
    properties and lets bindings decide what actually needs redrawing.
    """

    LIBRARY = "library"
    LOADING = "loading"
    READER = "reader"
    SETTINGS = "settings"

    pageChanged = Signal()
    loadingChanged = Signal()
    bookChanged = Signal()
    segmentChanged = Signal()
    highlightChanged = Signal()
    playbackChanged = Signal()
    chaptersChanged = Signal()
    settingsChanged = Signal()

    errorRaised = Signal(str, str)
    deleteRequested = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.settings = AppSettings()

        self._books = BookListModel(self)
        self._books.refresh()

        self.controller = None
        self._shutdown_complete = False

        self.loader_thread = None
        self.loader_worker = None
        self.pending_book_path = None

        self.audio_future = None
        self.audio_ready_action = None
        self.audio_segment_index = None

        self.returning_to_library = False
        self.library_return_started = 0.0

        self._page = self.LIBRARY

        self._loading_title = "Loading book..."
        self._loading_status = ""
        self._loading_progress = 0

        self._book_title = "No book"
        self._status_text = "Page --"
        self._segment_text = ""
        self._current_page = 1
        self._max_page = 1

        self._cue_offsets = []
        self._cue_bounds = {}
        self._highlight_start = 0
        self._highlight_end = 0

        self._playing = False
        self._position = 0.0
        self._duration = 0.0

        self._chapter_titles = []
        self._current_chapter = -1

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(100)

    # ------------------------------------------------------------------
    # properties
    # ------------------------------------------------------------------

    def _assign(self, name, value) -> bool:
        if getattr(self, name) == value:
            return False

        setattr(self, name, value)

        return True

    @Property(QObject, constant=True)
    def books(self):
        return self._books

    @Property(str, notify=pageChanged)
    def page(self):
        return self._page

    @Property(bool, notify=bookChanged)
    def hasBook(self):
        return self.controller is not None

    @Property(str, notify=loadingChanged)
    def loadingTitle(self):
        return self._loading_title

    @Property(str, notify=loadingChanged)
    def loadingStatus(self):
        return self._loading_status

    @Property(int, notify=loadingChanged)
    def loadingProgress(self):
        return self._loading_progress

    @Property(str, notify=bookChanged)
    def bookTitle(self):
        return self._book_title

    @Property(str, notify=segmentChanged)
    def statusText(self):
        return self._status_text

    @Property(str, notify=segmentChanged)
    def segmentText(self):
        return self._segment_text

    @Property(int, notify=segmentChanged)
    def currentPage(self):
        return self._current_page

    @Property(int, notify=bookChanged)
    def maxPage(self):
        return self._max_page

    @Property(int, notify=highlightChanged)
    def highlightStart(self):
        return self._highlight_start

    @Property(int, notify=highlightChanged)
    def highlightEnd(self):
        return self._highlight_end

    @Property(bool, notify=playbackChanged)
    def playing(self):
        return self._playing

    @Property(float, notify=playbackChanged)
    def position(self):
        return self._position

    @Property(float, notify=playbackChanged)
    def duration(self):
        return self._duration

    @Property(list, notify=chaptersChanged)
    def chapterTitles(self):
        return self._chapter_titles

    @Property(int, notify=chaptersChanged)
    def currentChapter(self):
        return self._current_chapter

    # settings ---------------------------------------------------------

    @Property(str, notify=settingsChanged)
    def voice(self):
        return self.settings.get_voice()

    @voice.setter
    def voice(self, value: str):
        if value and value != self.settings.get_voice():
            self.settings.set_voice(value)
            self.settingsChanged.emit()

    @Property(float, notify=settingsChanged)
    def speed(self):
        return self.settings.get_speed()

    @speed.setter
    def speed(self, value: float):
        if abs(value - self.settings.get_speed()) > 1e-9:
            self.settings.set_speed(value)
            self.settingsChanged.emit()

    @Property(bool, notify=settingsChanged)
    def readFootnotes(self):
        return self.settings.get_read_footnotes()

    @readFootnotes.setter
    def readFootnotes(self, value: bool):
        if value != self.settings.get_read_footnotes():
            self.settings.set_read_footnotes(value)
            self.settingsChanged.emit()

    @Property(bool, notify=settingsChanged)
    def readCaptions(self):
        return self.settings.get_read_captions()

    @readCaptions.setter
    def readCaptions(self, value: bool):
        if value != self.settings.get_read_captions():
            self.settings.set_read_captions(value)
            self.settingsChanged.emit()

    @Property(bool, notify=settingsChanged)
    def readSidebars(self):
        return self.settings.get_read_sidebars()

    @readSidebars.setter
    def readSidebars(self, value: bool):
        if value != self.settings.get_read_sidebars():
            self.settings.set_read_sidebars(value)
            self.settingsChanged.emit()

    @Property(int, notify=settingsChanged)
    def cacheLimitMb(self):
        return self.settings.get_cache_limit_mb()

    @cacheLimitMb.setter
    def cacheLimitMb(self, value: int):
        value = max(256, int(value))

        if value != self.settings.get_cache_limit_mb():
            self.settings.set_cache_limit_mb(value)

            if self.controller is not None:
                self.controller.cache_limit_mb = value

            self.settingsChanged.emit()

    # ------------------------------------------------------------------
    # navigation between screens
    # ------------------------------------------------------------------

    def _set_page(self, page: str):
        if self._assign("_page", page):
            self.pageChanged.emit()

    @Slot()
    def showSettings(self):
        self._set_page(self.SETTINGS)

    @Slot()
    def closeSettings(self):
        self._set_page(
            self.READER if self.controller is not None else self.LIBRARY
        )

    @Slot()
    def showLibrary(self):
        if self.controller is not None:
            self.controller.running = False
            self.controller.player.stop()

            self.returning_to_library = True
            self.library_return_started = time.monotonic()

            self._set_loading(
                "Returning to library...",
                "Finishing background audio work...",
                0,
            )

            self._set_page(self.LOADING)
            return

        self._display_library()

    def _display_library(self):
        self._books.refresh()

        self._assign("_book_title", "No book")
        self._assign("_status_text", "Page --")
        self._assign("_segment_text", "")
        self._set_cue_offsets([])

        self.bookChanged.emit()
        self.segmentChanged.emit()

        self._set_page(self.LIBRARY)

    def _finish_show_library(self):
        if self.controller is not None:
            self.controller.shutdown()
            self.controller = None

        self._display_library()

    # ------------------------------------------------------------------
    # opening books
    # ------------------------------------------------------------------

    @Slot(str, str)
    def openPastedText(self, title: str, text: str):
        try:
            path = save_pasted_text(text, title)
        except Exception as error:
            self.errorRaised.emit("Unable to use pasted text", str(error))
            return

        self.openBook(path)

    @Slot(str)
    def openBook(self, path: str):
        path = self._to_local_path(path)

        if not path:
            return

        # The worker thread can remain alive briefly after its result has been
        # displayed. Preserve a selection made during that shutdown window so
        # the user never has to choose the same file a second time.
        if self.loader_thread is not None and self.loader_thread.isRunning():
            self.pending_book_path = path

            self._set_loading(
                "Opening book...",
                "Finishing the previous book...",
                0,
            )

            self._set_page(self.LOADING)
            return

        if not Path(path).exists():
            self.errorRaised.emit(
                "Book not found",
                f"This file is no longer available:\n{path}",
            )

            remove_book(path)
            self._display_library()
            return

        if self.controller is not None:
            self.controller.shutdown()
            self.controller = None
            self.bookChanged.emit()

        self._set_loading("Loading book...", "Preparing book...", 0)
        self._set_page(self.LOADING)

        self._start_book_loader(path)

    @staticmethod
    def _to_local_path(path: str) -> str:
        if path.startswith("file:"):
            return QUrl(path).toLocalFile()

        return path

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

        self.loader_worker.status_changed.connect(self._set_loading_status)
        self.loader_worker.progress_changed.connect(self._set_loading_progress)

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
            QTimer.singleShot(0, lambda path=pending_path: self.openBook(path))

    @Slot(object)
    def _book_loaded(self, prepared_book):
        # Queued onto the GUI thread, which is where ReaderController has to
        # be built: it constructs AudioPlayer and initializes pygame.
        try:
            controller = ReaderController(
                segments=prepared_book.segments,
                tts=prepared_book.tts,
                book_id=prepared_book.book_id,
                start_index=prepared_book.start_index,
                preload_count=2,
                chapters=prepared_book.chapters,
                cache_limit_mb=self.settings.get_cache_limit_mb(),
            )
        except Exception as error:
            self._book_load_failed(str(error))
            return

        self.controller = controller

        self._set_loading_progress(100)

        self._assign("_book_title", Path(prepared_book.path).stem)
        self._assign(
            "_max_page",
            max(segment.page for segment in controller.segments),
        )

        self._set_chapters(controller.chapters)

        self.bookChanged.emit()

        self._set_page(self.READER)

        self._update_reader()

        self._books.refresh()

    @Slot(str)
    def _book_load_failed(self, error: str):
        self.errorRaised.emit("Unable to open book", error)
        self._display_library()

    # ------------------------------------------------------------------
    # library rows
    # ------------------------------------------------------------------

    @Slot(str, str)
    def requestDelete(self, path: str, title: str):
        self.deleteRequested.emit(path, title)

    @Slot(str)
    def deleteBook(self, path: str):
        remove_book(path)
        self._books.refresh()

    # ------------------------------------------------------------------
    # playback
    # ------------------------------------------------------------------

    @Slot()
    def togglePlay(self):
        if self.controller is None:
            return

        if not self.controller.running:
            self._run_when_audio_ready(
                self.controller.get_current_index(),
                self.controller.start,
            )
            return

        self.controller.toggle_pause()

        segment = self.controller.get_current_segment()

        if segment is not None:
            # Starting playback loads cached cues. Refresh offsets now so
            # highlighting does not wait for a segment change.
            self._set_cue_offsets(self._build_cue_offsets(segment))

        self._update_playback()

    @Slot()
    def next(self):
        if self.controller is None:
            return

        target = self.controller.get_current_index() + 1

        if target >= len(self.controller.segments):
            return

        self._run_when_audio_ready(target, self.controller.next)

    @Slot()
    def previous(self):
        if self.controller is None:
            return

        target = self.controller.get_current_index() - 1

        if target < 0:
            return

        self._run_when_audio_ready(target, self.controller.previous)

    @Slot()
    def skipForward(self):
        if self.controller is not None:
            self.controller.seek_relative(15)

    @Slot()
    def skipBack(self):
        if self.controller is not None:
            self.controller.seek_relative(-15)

    @Slot(float)
    def seek(self, seconds: float):
        if self.controller is not None:
            self.controller.seek_to(seconds)

    @Slot(int)
    def seekToCharacter(self, offset: int):
        """Read from the sentence the listener clicked."""
        if self.controller is None:
            return

        cue = self._cue_at_offset(offset)

        if cue is None:
            return

        self.controller.seek_and_play(cue.start)

        self._update_reader()

    @Slot(int)
    def goToPage(self, page: int):
        if self.controller is None:
            return

        if self.controller.go_to_page(page) is None:
            return

        self._update_reader()

    @Slot(int)
    def goToChapter(self, chapter_index: int):
        if self.controller is None:
            return

        if self.controller.go_to_chapter(chapter_index):
            self._update_reader()

    def _run_when_audio_ready(self, segment_index: int, action):
        if self.controller is None or self.audio_future is not None:
            return

        future = self.controller.prepare_segment_audio(segment_index)

        if future is None:
            action()

            self._set_page(self.READER)
            self._update_reader()
            return

        self.audio_future = future
        self.audio_ready_action = action
        self.audio_segment_index = segment_index

        self._set_loading(
            "Preparing audio...",
            f"Generating segment {segment_index + 1} "
            f"of {len(self.controller.segments)}...",
            0,
        )

        self._set_page(self.LOADING)

    # ------------------------------------------------------------------
    # reader state
    # ------------------------------------------------------------------

    def _set_chapters(self, chapters):
        indent = "    "

        titles = [
            indent * max(chapter.level - 1, 0) + chapter.title
            for chapter in chapters
        ]

        self._assign("_chapter_titles", titles)
        self._assign("_current_chapter", -1)

        self.chaptersChanged.emit()

    def _update_reader(self):
        if self.controller is None:
            return

        segment = self.controller.get_current_segment()

        if segment is None:
            return

        index = self.controller.get_current_index()
        total = len(self.controller.segments)

        changed = self._assign("_segment_text", segment.text)

        changed |= self._assign(
            "_status_text",
            f"Page {segment.page}  ·  Segment {index + 1} / {total}",
        )

        changed |= self._assign("_current_page", segment.page)

        if changed:
            self.segmentChanged.emit()

        self._set_cue_offsets(self._build_cue_offsets(segment))

        chapter_index = self.controller.get_current_chapter_index()

        if self._assign(
            "_current_chapter",
            chapter_index if chapter_index is not None else -1,
        ):
            self.chaptersChanged.emit()

        self._update_playback()

    def _build_cue_offsets(self, segment):
        """Map each cue onto the segment text shown in the reader.

        The text is never rebuilt from cues: doing that collapses the
        paragraph spacing the reader adds for legibility.
        """
        if not segment.cues:
            return []

        offsets = []

        text = segment.text
        search_position = 0

        for cue in segment.cues:
            cue_text = cue.text.strip()

            if not cue_text:
                continue

            start = text.find(cue_text, search_position)

            # A cue that cannot be mapped is skipped rather than changing the
            # displayed text and losing its original newlines.
            if start == -1:
                continue

            end = start + len(cue_text)

            offsets.append((cue, start, end))
            search_position = end

        return offsets

    def _set_cue_offsets(self, offsets):
        self._cue_offsets = offsets

        self._cue_bounds = {
            id(cue): (start, end)
            for cue, start, end in offsets
        }

    def _cue_at_offset(self, offset: int):
        """Cue covering this character, or the next one when a gap is clicked.

        Offsets are in reading order, so the first cue that ends after the
        click is either the one clicked or the one about to be read.
        """
        for cue, _start, end in self._cue_offsets:
            if offset < end:
                return cue

        return None

    def _update_highlight(self):
        if self.controller is None:
            return

        cue = self.controller.get_current_cue()

        bounds = self._cue_bounds.get(id(cue)) if cue is not None else None

        start, end = bounds if bounds is not None else (0, 0)

        changed = self._assign("_highlight_start", start)
        changed |= self._assign("_highlight_end", end)

        if changed:
            self.highlightChanged.emit()

    def _update_playback(self):
        if self.controller is None:
            return

        player = self.controller.player

        playing = self.controller.running and not player.is_paused

        changed = self._assign("_playing", playing)

        changed |= self._assign(
            "_position",
            round(player.get_playback_position(), 2),
        )

        changed |= self._assign("_duration", round(player.get_duration(), 2))

        if changed:
            self.playbackChanged.emit()

    def _set_loading(self, title: str, status: str, progress: int):
        changed = self._assign("_loading_title", title)
        changed |= self._assign("_loading_status", status)
        changed |= self._assign("_loading_progress", progress)

        if changed:
            self.loadingChanged.emit()

    @Slot(str)
    def _set_loading_status(self, status: str):
        if self._assign("_loading_status", status):
            self.loadingChanged.emit()

    @Slot(int)
    def _set_loading_progress(self, progress: int):
        if self._assign("_loading_progress", progress):
            self.loadingChanged.emit()

    # ------------------------------------------------------------------
    # tick
    # ------------------------------------------------------------------

    def _tick(self):
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

        if self.controller.get_current_index() != previous_index:
            self._update_reader()

        self._update_highlight()
        self._update_playback()

    def _poll_library_return(self) -> bool:
        if not self.returning_to_library or self.controller is None:
            return False

        generating = [
            index
            for index, segment in enumerate(self.controller.segments)
            if segment.id in self.controller.generating
        ]

        if generating:
            progress = sum(
                self.controller.get_generation_progress(index)
                for index in generating
            ) // len(generating)

            self._set_loading_progress(progress)
            return True

        # Keep the transition visible briefly even when there is no pending
        # generation, so returning to the library reads as a deliberate state.
        if time.monotonic() - self.library_return_started < 0.35:
            self._set_loading_progress(90)
            return True

        self._set_loading_progress(100)
        self.returning_to_library = False

        self._finish_show_library()

        return True

    def _poll_audio_generation(self) -> bool:
        if self.audio_future is None:
            return False

        if not self.audio_future.done():
            if self.audio_segment_index is not None:
                self._set_loading_progress(
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

        self._set_loading_progress(100)

        try:
            future.result()
        except Exception as error:
            self.controller.running = False

            self._set_page(self.READER)
            self.errorRaised.emit("Unable to generate audio", str(error))
            self._update_reader()

            return True

        self._set_page(self.READER)

        if action is not None:
            action()

        self._update_reader()

        return True

    def _poll_pending_playback(self):
        """Show generation progress while the controller waits for its audio.

        `play_current` never blocks, so a cache miss surfaces as a progress
        screen rather than as a frozen window.
        """
        index = self.controller.get_current_index()

        if self._page != self.LOADING:
            self._set_loading(
                "Preparing audio...",
                f"Generating segment {index + 1} "
                f"of {len(self.controller.segments)}...",
                0,
            )

            self._set_page(self.LOADING)

        self._set_loading_progress(
            self.controller.get_generation_progress(index)
        )

        self.controller.tick()

        if self.controller.awaiting_audio:
            return

        error = self.controller.take_generation_error()

        self._set_page(self.READER)
        self._update_reader()

        if error is not None:
            self.errorRaised.emit("Unable to generate audio", error)

    # ------------------------------------------------------------------
    # shutdown
    # ------------------------------------------------------------------

    @Slot()
    def shutdown(self):
        if self._shutdown_complete:
            return

        self._shutdown_complete = True
        self.timer.stop()

        if self.loader_thread is not None and self.loader_thread.isRunning():
            self.loader_thread.quit()
            self.loader_thread.wait()

        if self.controller is not None:
            self.controller.shutdown()
            self.controller = None
        else:
            enforce_cache_limit(
                self.settings.get_cache_limit_mb() * 1024 * 1024
            )
