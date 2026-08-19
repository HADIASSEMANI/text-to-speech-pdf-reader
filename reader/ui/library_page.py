from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
)

from reader.progress import get_recent_books


class LibraryPage(QWidget):
    open_document_requested = Signal()
    book_requested = Signal(str)

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

        self.open_button = QPushButton("Open Book")
        self.open_button.setObjectName("primaryButton")

        root.addWidget(self.open_button)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)

        self.container = QWidget()
        self.books_layout = QVBoxLayout(self.container)
        self.books_layout.setSpacing(12)

        self.scroll.setWidget(self.container)

        root.addWidget(self.scroll, 1)

        self.open_button.clicked.connect(self.open_document_requested.emit)

    def refresh(self):
        while self.books_layout.count():
            item = self.books_layout.takeAt(0)
            widget = item.widget()

            if widget is not None:
                widget.deleteLater()

        books = get_recent_books()

        if not books:
            empty = QLabel("No books yet. Open a book to begin.")
            empty.setObjectName("secondaryText")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

            self.books_layout.addWidget(empty)

        for book in books:
            resume_segment = book.current_segment + 1

            file_type = Path(book.path).suffix.lstrip(".").upper() or "FILE"

            missing = not Path(book.path).exists()

            subtitle = (
                "File missing" if missing else f"Segment {resume_segment} · Continue"
            )

            button = QPushButton(f"{book.title}\n{file_type} · {subtitle}")
            button.setObjectName("bookCardMissing" if missing else "bookCard")

            button.clicked.connect(
                lambda checked=False, path=book.path: self.book_requested.emit(path)
            )

            self.books_layout.addWidget(button)

        self.books_layout.addStretch()
