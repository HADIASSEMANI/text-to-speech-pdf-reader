import sys

from PySide6.QtWidgets import QApplication

from reader.database import initialize_database
from reader.paths import resource_path
from reader.ui.main_window import MainWindow


def main():

    app = QApplication(sys.argv)

    initialize_database()

    style_path = resource_path("styles/app.qss")

    if style_path.exists():
        app.setStyleSheet(style_path.read_text(encoding="utf-8"))

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
