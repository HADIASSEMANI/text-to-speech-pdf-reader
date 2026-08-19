from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QComboBox,
    QLabel,
    QPushButton,
    QTextEdit,
    QSpinBox,
)

from reader.ui.widgets.player_controls import PlayerControls


class ReaderPage(QWidget):
    library_requested = Signal()
    page_requested = Signal(int)
    chapter_requested = Signal(int)
    text_seek_requested = Signal(float)

    def __init__(self):
        super().__init__()

        self.current_cue_offsets = []
        self._cue_bounds = {}
        self._highlighted_cue = None
        self.book_title = "No book"

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(20)

        header = QHBoxLayout()

        self.library_button = QPushButton("Library")
        self.library_button.setObjectName("ghostButton")

        self.title_label = QLabel("No book")
        self.title_label.setObjectName("readerTitle")

        header.addWidget(self.library_button)
        header.addStretch()
        header.addWidget(self.title_label)
        header.addStretch()

        root.addLayout(header)

        self.status_label = QLabel("Page --")
        self.status_label.setObjectName("readerStatus")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        root.addWidget(self.status_label)

        chapter_row = QHBoxLayout()

        chapter_label = QLabel("Navigate")

        self.chapter_input = QComboBox()
        self.chapter_input.setVisible(False)

        chapter_row.addStretch()
        chapter_row.addWidget(chapter_label)
        chapter_row.addWidget(self.chapter_input)
        chapter_row.addStretch()

        self.chapter_row_widget = QWidget()
        self.chapter_row_widget.setLayout(chapter_row)
        self.chapter_row_widget.setVisible(False)

        root.addWidget(self.chapter_row_widget)

        self.text_display = QTextEdit()
        self.text_display.setReadOnly(True)
        self.text_display.setObjectName("readerText")

        root.addWidget(self.text_display, 1)

        page_row = QHBoxLayout()

        page_row.addStretch()

        page_label = QLabel("Page")

        self.page_input = QSpinBox()
        self.page_input.setMinimum(1)

        self.page_go_button = QPushButton("Go")

        page_row.addWidget(page_label)
        page_row.addWidget(self.page_input)
        page_row.addWidget(self.page_go_button)

        page_row.addStretch()

        root.addLayout(page_row)

        self.player_controls = PlayerControls()

        root.addWidget(self.player_controls)

        self.library_button.clicked.connect(self.library_requested.emit)
        self.page_go_button.clicked.connect(self._request_page)
        self.page_input.editingFinished.connect(self._request_page)
        self.chapter_input.activated.connect(self._request_chapter)

        # Clicking narrated text jumps playback to that point.
        self.text_display.viewport().installEventFilter(self)

    def eventFilter(self, watched, event):
        if (
            watched is self.text_display.viewport()
            and event.type() == QEvent.Type.MouseButtonRelease
            and event.button() == Qt.MouseButton.LeftButton
        ):
            self._handle_text_click(event)

        return super().eventFilter(watched, event)

    def _handle_text_click(self, event):
        cursor = self.text_display.cursorForPosition(event.position().toPoint())

        cue = self._cue_at_offset(cursor.position())

        if cue is None:
            return

        self.text_seek_requested.emit(cue.start)

    def _cue_at_offset(self, offset: int):
        """Cue covering this character, or the next one when a gap is clicked.

        Offsets are in reading order, so the first cue that ends after the
        click is either the one clicked or the one about to be read.
        """
        for cue, _start, end in self.current_cue_offsets:
            if offset < end:
                return cue

        return None

    def _request_page(self):
        self.page_requested.emit(self.page_input.value())

    def _request_chapter(self, index: int):
        self.chapter_requested.emit(index)

    def set_chapters(self, chapters):
        self.chapter_input.clear()

        for chapter in chapters:
            indent = "    " * max(chapter.level - 1, 0)

            self.chapter_input.addItem(f"{indent}{chapter.title}")

        has_chapters = bool(chapters)

        self.chapter_input.setVisible(has_chapters)
        self.chapter_row_widget.setVisible(has_chapters)

    def set_current_chapter(self, chapter_index: int | None):
        if (
            chapter_index is not None
            and 0 <= chapter_index < self.chapter_input.count()
        ):
            self.chapter_input.blockSignals(True)
            self.chapter_input.setCurrentIndex(chapter_index)
            self.chapter_input.blockSignals(False)

            chapter_title = self.chapter_input.itemText(chapter_index).strip()
            self.title_label.setText(chapter_title or self.book_title)
        else:
            self.title_label.setText(self.book_title)

    def set_reader_enabled(self, enabled: bool):
        self.page_input.setEnabled(enabled)
        self.page_go_button.setEnabled(enabled)
        self.chapter_input.setEnabled(enabled)
        self.player_controls.set_enabled_controls(enabled)

    def set_book(self, title: str, max_page: int):
        self.book_title = title
        self.title_label.setText(title)
        self.page_input.setMaximum(max(max_page, 1))

    def set_page_value(self, page: int):
        self.page_input.setValue(page)

    def show_segment(self, segment, current_index: int, total_segments: int):
        self.status_label.setText(
            f"Page {segment.page}  ·  "
            f"Segment {current_index + 1} / {total_segments}"
        )

        self.page_input.setValue(segment.page)

        display_text, offsets = self._build_highlight_text(segment)

        self._set_cue_offsets(offsets)

        self.text_display.setPlainText(display_text)

    def _build_highlight_text(self, segment):
        if not segment.cues:
            return segment.text, []

        offsets = []

        # Keep the segment text as-is. Rebuilding it from cues collapses
        # paragraph spacing added for the GUI.
        display_text = segment.text
        search_position = 0

        for cue in segment.cues:
            text = cue.text.strip()

            if not text:
                continue

            start = display_text.find(text, search_position)

            # TTS cue text normally matches the segment exactly. If a cue
            # cannot be mapped, skip its highlight rather than changing the
            # displayed text and losing its original newlines.
            if start == -1:
                continue

            end = start + len(text)

            offsets.append((cue, start, end))
            search_position = end

        return display_text, offsets

    def refresh_highlight_offsets(self, segment):
        _display_text, offsets = self._build_highlight_text(segment)
        self._set_cue_offsets(offsets)

    def _set_cue_offsets(self, offsets):
        """Store cue offsets and the lookup `highlight_cue` reads every tick.

        Keyed by identity because a cue is matched by object, not by text: two
        sentences in a segment can read the same.
        """
        self.current_cue_offsets = offsets

        self._cue_bounds = {
            id(cue): (start, end)
            for cue, start, end in offsets
        }

        # The document just changed, so nothing on screen is highlighted.
        self._highlighted_cue = None

    def highlight_cue(self, cue):
        if cue is self._highlighted_cue:
            # The reader ticks ten times a second. Re-applying the selection
            # it already shows costs a document re-layout and a repaint for
            # nothing, which is what made scrolled text feel sticky.
            return

        self._highlighted_cue = cue

        bounds = (
            self._cue_bounds.get(id(cue))
            if cue is not None
            else None
        )

        if bounds is None:
            self.text_display.setExtraSelections([])
            return

        start, end = bounds

        cursor = self.text_display.textCursor()

        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)

        selection = QTextEdit.ExtraSelection()

        selection.cursor = cursor

        palette = self.text_display.palette()

        selection.format.setBackground(palette.highlight())
        selection.format.setForeground(palette.highlightedText())

        self.text_display.setExtraSelections([selection])

    def clear(self):
        self.book_title = "No book"
        self.title_label.setText("No book")
        self.status_label.setText("Page --")
        self.text_display.clear()
        self._set_cue_offsets([])
        self.page_input.setMaximum(1)
        self.page_input.setValue(1)
        self.set_chapters([])
