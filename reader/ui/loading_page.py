from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
)

from reader.ui.widgets.rainbow_spinner import RainbowSpinner


class LoadingPage(QWidget):
    def __init__(self):
        super().__init__()

        root = QVBoxLayout(self)

        root.setContentsMargins(40, 40, 40, 40)

        root.addStretch()

        self.spinner = RainbowSpinner()

        root.addWidget(
            self.spinner,
            alignment=Qt.AlignmentFlag.AlignCenter,
        )

        self.title = QLabel("Loading book...")
        self.title.setObjectName("pageTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        root.addWidget(self.title)

        self.status = QLabel("Preparing PDF")
        self.status.setObjectName("secondaryText")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)

        root.addWidget(self.status)

        self.percentage = QLabel("0%")
        self.percentage.setObjectName("readerStatus")
        self.percentage.setAlignment(Qt.AlignmentFlag.AlignCenter)

        root.addWidget(self.percentage)

        root.addStretch()

    def set_status(self, text: str):
        self.status.setText(text)

    def set_title(self, text: str):
        self.title.setText(text)

    def set_progress(self, value: int):
        value = max(0, min(int(value), 100))
        self.percentage.setText(f"{value}%")
