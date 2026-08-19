from PySide6.QtCore import QObject, Signal, Slot

from reader.book_loader import prepare_book


class BookLoaderWorker(QObject):

    finished = Signal(object)
    failed = Signal(str)
    status_changed = Signal(str)

    def __init__(
        self,
        path: str,
        voice: str = "af_heart",
        speed: float = 0.85,
        read_footnotes: bool = False,
        read_captions: bool = False,
        read_sidebars: bool = False,
    ):
        super().__init__()

        self.path = path
        self.voice = voice
        self.speed = speed
        self.read_footnotes = read_footnotes
        self.read_captions = read_captions
        self.read_sidebars = read_sidebars

    @Slot()
    def run(self):
        try:
            prepared_book = prepare_book(
                self.path,
                voice=self.voice,
                speed=self.speed,
                read_footnotes=self.read_footnotes,
                read_captions=self.read_captions,
                read_sidebars=self.read_sidebars,
                on_status=self.status_changed.emit,
            )

            self.finished.emit(prepared_book)

        except Exception as error:
            self.failed.emit(str(error))
