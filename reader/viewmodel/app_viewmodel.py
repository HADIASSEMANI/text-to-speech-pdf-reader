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
from reader.cache import (
    audio_cache_size,
    clear_audio_cache,
    enforce_cache_limit,
)
from reader.controller import PlaybackState, ReaderController
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

    # A speed slider emits while it is being dragged. Wait for it to settle
    # before re-keying the open book's audio.
    NARRATION_APPLY_DELAY_MS = 400

    # How far the skip buttons move. The controller carries any overflow
    # into the neighbouring passage rather than clamping.
    SKIP_SECONDS = 15

    pageChanged = Signal()
    loadingChanged = Signal()
    bookChanged = Signal()
    segmentChanged = Signal()
    highlightChanged = Signal()
    playbackChanged = Signal()
    chaptersChanged = Signal()
    settingsChanged = Signal()
    textSizeChanged = Signal()
    cacheSizeChanged = Signal()
    preparationChanged = Signal()

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

        # Audio preparation is no longer a screen of its own. The reader
        # stays visible and reports progress in place, so the text can still
        # be read while the next passage is being synthesized.
        self._preparing = False
        self._preparing_progress = 0
        self._preparing_message = ""
        self._preparing_error = ""

        self._page = self.LIBRARY

        self._loading_title = "Loading book..."
        self._loading_status = ""
        self._loading_progress = 0

        self._book_title = "No book"
        self._status_text = "Page --"
        self._segment_text = ""
        self._segment_html = ""
        self._current_page = 1
        self._max_page = 1

        self._cue_offsets = []
        self._cue_bounds = {}

        # The cue list the offsets were built from. Cues arrive after the
        # passage does — a cold segment gets them when synthesis finishes,
        # on the same segment index — so the offsets cannot be rebuilt on
        # segment change alone.
        self._cue_source = None
        self._highlight_start = 0
        self._highlight_end = 0

        self._playing = False
        self._playback_state = PlaybackState.STOPPED.value
        self._position = 0.0
        self._duration = 0.0

        self._chapter_titles = []
        self._current_chapter = -1

        self._cache_size_bytes = 0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(100)

        self._narration_timer = QTimer(self)
        self._narration_timer.setSingleShot(True)
        self._narration_timer.timeout.connect(self._apply_narration_settings)

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

    @Property(str, notify=segmentChanged)
    def segmentHtml(self):
        """The passage with its structure: headings, paragraphs, notation.

        Carries exactly the characters of `segmentText`, so the character
        ranges used for highlighting and click-to-read still line up.
        """
        return self._segment_html

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

    @Property(str, notify=playbackChanged)
    def playbackState(self):
        """stopped, preparing, playing, paused or finished."""
        return self._playback_state

    @Property(bool, notify=preparationChanged)
    def preparing(self):
        return self._preparing

    @Property(int, notify=preparationChanged)
    def preparingProgress(self):
        return self._preparing_progress

    @Property(str, notify=preparationChanged)
    def preparingMessage(self):
        return self._preparing_message

    @Property(str, notify=preparationChanged)
    def preparingError(self):
        return self._preparing_error

    @Property(list, notify=chaptersChanged)
    def chapterTitles(self):
        return self._chapter_titles

    @Property(int, notify=chaptersChanged)
    def currentChapter(self):
        return self._current_chapter

    # settings ---------------------------------------------------------

    @Property(int, constant=True)
    def minimumTextSize(self):
        return AppSettings.MIN_TEXT_SIZE

    @Property(int, constant=True)
    def maximumTextSize(self):
        return AppSettings.MAX_TEXT_SIZE

    @Property(int, notify=textSizeChanged)
    def textSize(self):
        return self.settings.get_text_size()

    @textSize.setter
    def textSize(self, value: int):
        value = AppSettings.clamp_text_size(value)
        if value != self.textSize:
            self.settings.set_text_size(value)
            self.textSizeChanged.emit()

    @Property(str, notify=settingsChanged)
    def voice(self):
        return self.settings.get_voice()

    @voice.setter
    def voice(self, value: str):
        if value and value != self.settings.get_voice():
            self.settings.set_voice(value)
            self._schedule_narration_update()
            self.settingsChanged.emit()

    @Property(float, notify=settingsChanged)
    def speed(self):
        return self.settings.get_speed()

    @speed.setter
    def speed(self, value: float):
        if abs(value - self.settings.get_speed()) > 1e-9:
            self.settings.set_speed(value)
            self._schedule_narration_update()
            self.settingsChanged.emit()

    def _schedule_narration_update(self):
        """Apply voice and speed to the open book, once the slider settles.

        Dragging a speed slider emits a value per frame. Applying each one
        would re-key every segment and cancel the synthesis started by the
        previous value, so the change is debounced and applied once.
        """
        if self.controller is None:
            return

        self._narration_timer.start(self.NARRATION_APPLY_DELAY_MS)

    def _apply_narration_settings(self):
        if self.controller is None:
            return

        changed = self.controller.apply_narration_settings(
            voice=self.settings.get_voice(),
            speed=self.settings.get_speed(),
        )

        if changed:
            self._update_reader()

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

    @Property(int, notify=cacheSizeChanged)
    def cacheSizeBytes(self):
        return self._cache_size_bytes

    @Property(str, notify=cacheSizeChanged)
    def cacheSizeText(self):
        return self._format_cache_size(self._cache_size_bytes)

    @staticmethod
    def _format_cache_size(size_bytes: int) -> str:
        if size_bytes <= 0:
            return "Empty"

        gb = size_bytes / (1024 * 1024 * 1024)
        if gb >= 1.0:
            return f"{gb:.1f} GB"

        mb = size_bytes / (1024 * 1024)
        if mb >= 10:
            return f"{round(mb)} MB"
        if mb >= 1.0:
            return f"{mb:.1f} MB"

        kb = max(1, round(size_bytes / 1024))
        return f"{kb} KB"

    def _refresh_cache_size(self, force_emit: bool = False):
        changed = self._assign("_cache_size_bytes", audio_cache_size())

        if changed or force_emit:
            self.cacheSizeChanged.emit()

    @Slot()
    def clearCache(self):
        keep = ()

        if self.controller is not None:
            keep = self.controller.get_current_cache_paths()

        clear_audio_cache(keep=keep)

        if self.controller is not None:
            keep_stems = {Path(p).stem for p in keep if p}

            for segment in self.controller.segments:
                if not segment.audio_path:
                    continue

                audio = Path(segment.audio_path)

                if audio.stem in keep_stems or audio.exists():
                    continue

                segment.generated = False
                segment.cues = []

        self._refresh_cache_size(force_emit=True)

    # ------------------------------------------------------------------
    # navigation between screens
    # ------------------------------------------------------------------

    def _set_page(self, page: str):
        if self._assign("_page", page):
            self.pageChanged.emit()

    @Slot()
    def showSettings(self):
        self._refresh_cache_size()
        self._set_page(self.SETTINGS)

    @Slot()
    def closeSettings(self):
        self._set_page(
            self.READER if self.controller is not None else self.LIBRARY
        )

    @Slot()
    def showLibrary(self):
        """Close the book and show the library straight away.

        This used to hold a progress screen until every queued synthesis had
        finished, which could be tens of seconds. The position is written
        first, queued work is cancelled, and the audio device is closed
        synchronously so the next book can open one. Whatever was already
        being synthesized finishes on its own and lands in the cache.
        """
        self._close_book()

        self._display_library()

    def _close_book(self):
        if self.controller is None:
            return

        self._narration_timer.stop()

        self.controller.shutdown()
        self.controller = None

        self._set_preparation(False, 0, "", "")

        self.bookChanged.emit()

    def _display_library(self):
        self._books.refresh()

        self._assign("_book_title", "No book")
        self._assign("_status_text", "Page --")
        self._assign("_segment_text", "")
        self._assign("_segment_html", "")

        self._cue_source = None
        self._set_cue_offsets([])

        self.bookChanged.emit()
        self.segmentChanged.emit()

        self._set_page(self.LIBRARY)


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

        self._close_book()

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
        """Ask the controller to change transport state, and show the result.

        The interface no longer decides whether audio is ready: every
        transition goes through ReaderController, which is the only thing
        that knows. That is what stops the button and the audio disagreeing.
        """
        if self.controller is None:
            return

        self.controller.toggle_pause()

        self._update_reader()

    @Slot()
    def next(self):
        if self.controller is None:
            return

        self.controller.next()

        self._update_reader()

    @Slot()
    def previous(self):
        if self.controller is None:
            return

        self.controller.previous()

        self._update_reader()

    @Slot()
    def skipForward(self):
        if self.controller is None:
            return

        self.controller.seek_relative(self.SKIP_SECONDS)

        self._update_reader()

    @Slot()
    def skipBack(self):
        if self.controller is None:
            return

        self.controller.seek_relative(-self.SKIP_SECONDS)

        self._update_reader()

    @Slot(float)
    def seek(self, seconds: float):
        if self.controller is not None:
            self.controller.seek_to(seconds)

    @Slot()
    def cancelPreparation(self):
        if self.controller is None:
            return

        self.controller.cancel_preparation()

        self._set_preparation(False, 0, "", "")

        self._update_playback()

    @Slot()
    def retryPreparation(self):
        if self.controller is None:
            return

        self._set_preparation(False, 0, "", "")

        self.controller.retry_preparation()

        self._update_reader()

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
            "_segment_html",
            getattr(segment, "html", ""),
        )

        changed |= self._assign(
            "_status_text",
            f"Page {segment.page}  ·  Segment {index + 1} / {total}",
        )

        changed |= self._assign("_current_page", segment.page)

        if changed:
            # Two passages can begin with equal-length cues. Clearing the
            # old bounds ensures the new cue emits a change after deselection.
            self._highlight_start = self._highlight_end = 0
            self.highlightChanged.emit()
            self.segmentChanged.emit()

        self._refresh_cue_offsets(force=changed)

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
        from reader.cue_mapping import map_cues

        return map_cues(segment)

    def _refresh_cue_offsets(self, force: bool = False):
        """Map cues onto the displayed text whenever the cues change.

        Highlighting and click-to-read both read these offsets, so missing a
        rebuild leaves the passage unhighlighted and clicks inert.
        """
        if self.controller is None:
            return

        segment = self.controller.get_current_segment()

        if segment is None:
            return

        if not force and segment.cues is self._cue_source:
            return

        self._cue_source = segment.cues

        self._set_cue_offsets(self._build_cue_offsets(segment))

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

        # One source of truth. ``running`` covers playing and preparing, so
        # a passage that is still being synthesized still reads as playing:
        # the listener asked for it, and pressing the button again pauses.
        changed = self._assign("_playing", self.controller.running)

        changed |= self._assign(
            "_playback_state",
            self.controller.state.value,
        )

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

        previous_index = self.controller.get_current_index()

        self.controller.tick()

        if self.controller.get_current_index() != previous_index:
            self._update_reader()

        self._refresh_cue_offsets()

        self._update_preparation()
        self._update_highlight()
        self._update_playback()

    def _update_preparation(self):
        """Report synthesis progress without taking the reader off screen."""
        controller = self.controller

        if controller is None:
            return

        error = controller.take_generation_error()

        if error is not None:
            self._set_preparation(
                False,
                0,
                "",
                f"This passage could not be prepared. {error}",
            )

            return

        preparing = controller.state is PlaybackState.PREPARING

        if not preparing:
            if self._preparing:
                self._set_preparation(False, 0, "", self._preparing_error)

            return

        index = controller.get_current_index()

        self._set_preparation(
            True,
            controller.get_generation_progress(index),
            f"Preparing passage {index + 1} of {len(controller.segments)}",
            "",
        )

    def _set_preparation(
        self,
        preparing: bool,
        progress: int,
        message: str,
        error: str,
    ):
        changed = self._assign("_preparing", preparing)
        changed |= self._assign("_preparing_progress", progress)
        changed |= self._assign("_preparing_message", message)
        changed |= self._assign("_preparing_error", error)

        if changed:
            self.preparationChanged.emit()

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

        self._narration_timer.stop()

        if self.controller is not None:
            # Application exit is the one place worth waiting: it lets the
            # passage being synthesized finish and land in the cache.
            self.controller.shutdown(wait=True)
            self.controller = None
        else:
            enforce_cache_limit(
                self.settings.get_cache_limit_mb() * 1024 * 1024
            )
