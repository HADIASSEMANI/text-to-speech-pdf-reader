from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QProgressBar,
)


class LoadingPage(QWidget):
    def __init__(self):
        super().__init__()

        root = QVBoxLayout(self)

        root.setContentsMargins(40, 40, 40, 40)

        root.addStretch()

        self.title = QLabel("Loading book...")
        self.title.setObjectName("pageTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        root.addWidget(self.title)

        self.status = QLabel("Preparing PDF")
        self.status.setObjectName("secondaryText")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)

        root.addWidget(self.status)

        self.progress = QProgressBar()

        # 0, 0 makes it indeterminate
        self.progress.setRange(0, 0)

        root.addWidget(self.progress)

        root.addStretch()

    def set_status(self, text: str):
        self.status.setText(text)
