from pathlib import Path

from PySide6.QtCore import (
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    Qt,
)

from reader.progress import get_recent_books


class BookListModel(QAbstractListModel):
    """The library, shaped for a QML ListView.

    The widget library built a row of buttons per book on every refresh. A
    model lets the view reuse its delegates instead, and keeps the wording of
    a row ("Continue", "File missing") in one place.
    """

    PathRole = Qt.ItemDataRole.UserRole + 1
    TitleRole = Qt.ItemDataRole.UserRole + 2
    SubtitleRole = Qt.ItemDataRole.UserRole + 3
    FileTypeRole = Qt.ItemDataRole.UserRole + 4
    MissingRole = Qt.ItemDataRole.UserRole + 5

    def __init__(self, parent=None):
        super().__init__(parent)

        self._books = []

    def roleNames(self):
        return {
            self.PathRole: QByteArray(b"path"),
            self.TitleRole: QByteArray(b"title"),
            self.SubtitleRole: QByteArray(b"subtitle"),
            self.FileTypeRole: QByteArray(b"fileType"),
            self.MissingRole: QByteArray(b"missing"),
        }

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0

        return len(self._books)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._books):
            return None

        book = self._books[index.row()]

        missing = not Path(book.path).exists()

        if role == self.PathRole:
            return book.path

        if role == self.TitleRole:
            return book.title

        if role == self.SubtitleRole:
            if missing:
                return "File missing"

            return f"Segment {book.current_segment + 1} · Continue"

        if role == self.FileTypeRole:
            extension = Path(book.path).suffix.lower()

            return "TEXT" if extension == ".txt" else (
                extension.lstrip(".").upper() or "FILE"
            )

        if role == self.MissingRole:
            return missing

        return None

    def refresh(self):
        self.beginResetModel()
        self._books = get_recent_books()
        self.endResetModel()

    def is_empty(self) -> bool:
        return not self._books
