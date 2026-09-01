from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
)

from reader.progress import get_recent_books


class LibraryPage(QWidget):
    open_document_requested = Signal()
    paste_text_requested = Signal()
    book_requested = Signal(str)
    delete_book_requested = Signal(str, str)

    def __init__(self):
        super().__init__()

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)

        root.setContentsMargins(40, 32, 40, 32)
        root.setSpacing(24)

        header = QLabel("Your Library")
        header.setObjectName("pageTitle")

        root.addWidget(header)

        actions = QHBoxLayout()

        self.paste_button = QPushButton("Paste Text")

        self.open_button = QPushButton("Open Book")
        self.open_button.setObjectName("primaryButton")

        actions.addWidget(self.paste_button)
        actions.addWidget(self.open_button)
        root.addLayout(actions)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)

        self.container = QWidget()
        self.books_layout = QVBoxLayout(self.container)
        self.books_layout.setSpacing(12)

        self.scroll.setWidget(self.container)

        root.addWidget(self.scroll, 1)

        self.open_button.clicked.connect(self.open_document_requested.emit)
        self.paste_button.clicked.connect(self.paste_text_requested.emit)

    def refresh(self):
        while self.books_layout.count():
            item = self.books_layout.takeAt(0)
            widget = item.widget()

            if widget is not None:
                widget.deleteLater()

        books = get_recent_books()

        if not books:
            empty = QLabel(
                "No books or texts yet. Open a book or paste text to begin."
            )
            empty.setObjectName("secondaryText")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

            self.books_layout.addWidget(empty)

        for book in books:
            resume_segment = book.current_segment + 1

            extension = Path(book.path).suffix.lower()
            file_type = (
                "TEXT" if extension == ".txt"
                else extension.lstrip(".").upper() or "FILE"
            )

            missing = not Path(book.path).exists()

            subtitle = (
                "File missing" if missing else f"Segment {resume_segment} · Continue"
            )

            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(10)

            button = QPushButton(f"{book.title} · {file_type} · {subtitle}")
            button.setObjectName("bookCardMissing" if missing else "bookCard")

            button.clicked.connect(
                lambda checked=False, path=book.path: self.book_requested.emit(path)
            )

            delete_button = QPushButton("Delete")
            delete_button.setObjectName("deleteBookButton")
            delete_button.setToolTip("Remove this book from the library")
            delete_button.clicked.connect(
                lambda checked=False, path=book.path, title=book.title:
                self.delete_book_requested.emit(path, title)
            )

            row_layout.addWidget(button, 1)
            row_layout.addWidget(delete_button)

            self.books_layout.addWidget(row)

        self.books_layout.addStretch()
